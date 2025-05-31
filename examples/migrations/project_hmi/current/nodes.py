import datetime
import json  # Added for debug printing
from typing import Any, Dict

from models.shared import AgentState, DoctorInfo, SlotInfo


async def w1_rank_specialist(state: AgentState, **kwargs) -> Dict[str, Any]:
    """
    Call Specialist Ranking API (mcp.get_specialist_ranking) to get top N doctors.

    Args:
        state: The current agent state

    Returns:
        A dictionary containing the updated w1_context.
    """
    from tools.mcp_wrapper import HmiMcpWrapper

    mcp = HmiMcpWrapper()

    # Extract the specialty from the referral context
    specialty = None
    if state.referral_context and state.referral_context.referral_specialties:
        specialty = state.referral_context.referral_specialties[
            0
        ]  # Take the first specialty

    updated_w1_context = state.w1_context.model_copy()

    if not specialty:
        # Handle the case where no specialty is provided
        # This might be an error case that should be handled differently
        updated_w1_context.ranked_doctors_list = []
        return {"w1_context": updated_w1_context}

    # Call the Specialist Ranking API
    ranking_response = mcp.get_specialist_ranking(
        specialty=specialty, sort_by="rank", sort_order="asc"
    )

    # Process the response to create a list of DoctorInfo objects
    ranked_doctors = []
    # Check if the response is a list (based on actual API output)
    if isinstance(ranking_response, list):
        for doctor_data in ranking_response:
            # --- Determine system_id ---
            # Per user instruction, assuming system_id is 'starmed' for now.
            system_id_from_api = "starmed"
            print(
                f"INFO: Assuming system_id='{system_id_from_api}' for doctor {doctor_data.get('DoctorGivenID')} based on current testing assumption."
            )

            doctor_info = DoctorInfo(
                doctor_given_id=doctor_data.get("DoctorGivenID"),
                system_id=system_id_from_api,
                doctor_name=doctor_data.get("Doctor"),
                doctor_code=doctor_data.get(
                    "doctorcode"
                ),  # This field was not in API sample, might be None
                doctor_specialties=[
                    doctor_data.get("Speciality", specialty)
                ],  # Use API speciality if available
                clinic_name=doctor_data.get(
                    "clinicname"
                ),  # This field was not in API sample, might be None - or is it "Location"?
                clinic_location=doctor_data.get(
                    "Location"
                ),  # Using "Location" from API for clinic_location
                clinic_location_code=doctor_data.get(
                    "cliniclocationcode"
                ),  # Not in API sample
                contact_number=doctor_data.get("contactnumber"),  # Not in API sample
                photo_url=doctor_data.get("photourl"),  # Not in API sample
                raw_profile_data=doctor_data,
            )
            ranked_doctors.append(doctor_info)
    elif isinstance(ranking_response, dict) and "error" in ranking_response:
        print(f"Error in specialist ranking response: {ranking_response.get('error')}")
        # Keep ranked_doctors as an empty list
    else:
        print(
            f"Unexpected specialist ranking response format: {type(ranking_response)}. Content: {str(ranking_response)[:500]}..."
        )
        # Keep ranked_doctors as an empty list

    print(
        f"DEBUG w1_rank_specialist: Parsed ranked_doctors list (count: {len(ranked_doctors)}): {ranked_doctors}"
    )  # DEBUG
    updated_w1_context.ranked_doctors_list = ranked_doctors

    return {"w1_context": updated_w1_context}


async def w1_check_availability(state: AgentState, **kwargs) -> Dict[str, Any]:
    """
    For each doctor, call availability API (mcp.get_doctor_available_slots) until a slot < 7 days & ≥ 1 h ahead is found.
    On fail, set no_hmi_slot flag.

    Args:
        state: The current agent state

    Returns:
        A dictionary containing the updated w1_context.
    """

    from tools.mcp_wrapper import HmiMcpWrapper

    mcp = HmiMcpWrapper()
    now = datetime.datetime.now()
    one_hour_ahead = now + datetime.timedelta(hours=1)
    seven_days_ahead = now + datetime.timedelta(days=7)

    chosen_doctor = None
    earliest_slot = None

    ranked_doctors = state.w1_context.ranked_doctors_list
    print(
        f"DEBUG w1_check_availability: Processing {len(ranked_doctors)} ranked doctors."
    )  # DEBUG

    # Loop through ranked doctors to find the first available slot
    for doctor_idx, doctor in enumerate(ranked_doctors):
        print(
            f"DEBUG w1_check_availability: Checking doctor {doctor_idx + 1}/{len(ranked_doctors)}: ID={doctor.doctor_given_id}, System={doctor.system_id}"
        )  # DEBUG
        if not doctor.doctor_given_id or not doctor.system_id:
            print(
                f"DEBUG w1_check_availability: Skipping doctor {doctor.doctor_given_id} due to missing ID or system_id."
            )  # DEBUG
            continue

        # Call the availability API
        slots_response = mcp.get_doctor_available_slots(
            doctor_given_id=doctor.doctor_given_id, system_id=doctor.system_id
        )

        # ***** CRITICAL DEBUG: Print the raw slots_response for the first doctor *****
        if doctor_idx == 0:  # Only print for the first doctor (CKK in this case)
            # try:
            #     print(f"DEBUG w1_check_availability (RAW SLOTS RESPONSE for {doctor.doctor_given_id}): {json.dumps(slots_response, indent=2)}")
            # except TypeError:
            #     print(f"DEBUG w1_check_availability (RAW SLOTS RESPONSE for {doctor.doctor_given_id} - Non-serializable): {slots_response}")
            pass  # Removed large debug print as requested
        # ***** END CRITICAL DEBUG *****

        # Process the response to find a suitable slot
        # Assuming slots_response is directly the list of slots, based on user feedback and Postman output.
        if isinstance(slots_response, list):
            slot_list_from_response = slots_response
            print(
                f"DEBUG w1_check_availability: Processing {len(slot_list_from_response)} slots received as a direct list for doctor {doctor.doctor_given_id}."
            )
            valid_slots = []
            for slot_data_idx, slot_data in enumerate(slot_list_from_response):
                try:
                    # Extract date and time from slot_data
                    date_str = slot_data.get("date")  # e.g., "2025-07-29"
                    time_str = slot_data.get("time")  # e.g., "11:30 AM"
                    location = slot_data.get("location")
                    interval_minutes = slot_data.get(
                        "timeslotinterval", 30
                    )  # Default to 30 if not present

                    if not date_str or not time_str:
                        print(
                            f"DEBUG w1_check_availability: Skipping slot {slot_data_idx} due to missing date or time. Data: {slot_data}"
                        )
                        continue

                    # Combine date and time string and parse into a datetime object
                    # Example: "2025-07-29" and "11:30 AM" -> datetime object
                    combined_datetime_str = f"{date_str} {time_str}"
                    slot_start_dt = datetime.datetime.strptime(
                        combined_datetime_str, "%Y-%m-%d %I:%M %p"
                    )

                    # Calculate slot_end_dt
                    slot_end_dt = slot_start_dt + datetime.timedelta(
                        minutes=interval_minutes
                    )

                    # Check if the slot is within the desired timeframe (1 hour ahead, within 7 days)
                    if one_hour_ahead <= slot_start_dt <= seven_days_ahead:
                        slot_info = SlotInfo(
                            appointment_start_time=slot_start_dt.isoformat(),  # Store as ISO string
                            appointment_end_time=slot_end_dt.isoformat(),  # Store as ISO string
                            appointment_date_str=date_str,  # Keep original date string for HMI One API if needed
                            appointment_time_str=time_str,  # Keep original time string for HMI One API if needed
                            location=location,
                            system_id=doctor.system_id,
                            doctor_given_id=doctor.doctor_given_id,
                            raw_slot_data=slot_data,
                        )
                        valid_slots.append(slot_info)
                    # else: # Optional: debug for slots filtered out by time
                    # print(f"DEBUG w1_check_availability: Slot {slot_data_idx} for {doctor.doctor_given_id} ({slot_start_dt}) filtered out by time window.")
                except (ValueError, TypeError) as e:
                    print(
                        f"DEBUG w1_check_availability: Error parsing slot {slot_data_idx} for doctor {doctor.doctor_given_id}. Slot data: {slot_data}. Error: {e}"
                    )
                    continue

            if valid_slots:
                valid_slots.sort(
                    key=lambda s: s.appointment_start_time
                )  # Sort by ISO string start time
                earliest_slot = valid_slots[0]
                chosen_doctor = doctor
                break  # Found a doctor and slot, exit loop
        elif (
            isinstance(slots_response, dict) and "slots" in slots_response
        ):  # Original logic as a fallback
            slot_list_from_response = slots_response["slots"]
            print(
                f"DEBUG w1_check_availability: Found 'slots' key for doctor {doctor.doctor_given_id}. Number of slots received: {len(slot_list_from_response)}"
            )
            # ... (rest of the original logic for dict based response - can be DRYed up later)
            # For now, focusing on the list-based response, assuming it's the primary case.
            # This part would need the same datetime construction logic as above.
            pass  # Placeholder for brevity, as the main issue seems to be list response
        else:
            print(
                f"DEBUG w1_check_availability: 'slots' key not found or response is not a list for doctor {doctor.doctor_given_id}. Response type: {type(slots_response)}. Response: {str(slots_response)[:500]}..."
            )

    updated_w1_context = state.w1_context.model_copy()
    # Update the state
    if chosen_doctor and earliest_slot:
        print(
            f"DEBUG w1_check_availability: Slot found for Dr. {chosen_doctor.doctor_name} ({chosen_doctor.doctor_given_id}) at {earliest_slot.appointment_start_time}"
        )  # DEBUG
        updated_w1_context.current_doctor_under_consideration = chosen_doctor
        updated_w1_context.earliest_slot_found = earliest_slot
        updated_w1_context.no_hmi_slot_flag = False
    else:
        print(
            "DEBUG w1_check_availability: No suitable slot found after checking all ranked doctors."
        )  # DEBUG
        updated_w1_context.no_hmi_slot_flag = True

    return {"w1_context": updated_w1_context}


async def w1_get_profile(state: AgentState, **kwargs) -> Dict[str, Any]:
    """
    Fetch doctor profile (using mcp.get_doctors_list with specific ID if detailed profile isn't separate).

    Args:
        state: The current agent state

    Returns:
        A dictionary containing the updated w1_context.
    """
    from tools.mcp_wrapper import HmiMcpWrapper

    mcp = HmiMcpWrapper()

    # Extract the chosen doctor from the state
    chosen_doctor = state.w1_context.current_doctor_under_consideration
    updated_w1_context = state.w1_context.model_copy()

    if (
        not chosen_doctor
        or not chosen_doctor.doctor_given_id
        or not chosen_doctor.system_id
    ):
        # Handle the case where no doctor is available (e.g. if no_hmi_slot_flag was true and this node was still called)
        print(
            "DEBUG w1_get_profile: No chosen doctor available or doctor details incomplete. Skipping profile fetch."
        )  # DEBUG
        # Ensure current_doctor_under_consideration is consistent if it was None
        updated_w1_context.current_doctor_under_consideration = None
        return {"w1_context": updated_w1_context}

    print(
        f"DEBUG w1_get_profile: Fetching profile for Dr. {chosen_doctor.doctor_name} ({chosen_doctor.doctor_given_id}), System ID: {chosen_doctor.system_id}"
    )  # DEBUG
    # Call the API to get detailed doctor information
    doctor_details_response = mcp.get_doctors_list(system_id=chosen_doctor.system_id)

    # Find the specific doctor in the response
    doctor_profile_data = None
    if "doctorinfo" in doctor_details_response:
        for doc_data in doctor_details_response["doctorinfo"]:
            if (
                doc_data.get("Givenid") == chosen_doctor.doctor_given_id
                and doc_data.get("Entity", "").lower()
                == chosen_doctor.system_id.lower()
            ):
                doctor_profile_data = doc_data
                break

    # Update the doctor info in the state if more detailed information is found
    if doctor_profile_data:
        # Create a new DoctorInfo object with the updates
        updated_doctor_info = chosen_doctor.model_copy(
            update={"raw_profile_data": doctor_profile_data}
        )

        # Update other fields if available in the profile and the new data is not None/empty
        # This overwrites existing fields on chosen_doctor if new data is found in the profile.
        new_name = doctor_profile_data.get("Name")
        if new_name:
            updated_doctor_info.doctor_name = new_name

        new_phone = doctor_profile_data.get("PhoneNumber")
        if new_phone:
            updated_doctor_info.contact_number = new_phone

        new_photo_url = doctor_profile_data.get("PhotoUrl")
        if new_photo_url:
            updated_doctor_info.photo_url = new_photo_url

        # Update the state
        updated_w1_context.current_doctor_under_consideration = updated_doctor_info

    return {"w1_context": updated_w1_context}


async def w1_compose_message(state: AgentState, llm, **kwargs) -> Dict[str, Any]:
    """
    Fill template single_referral_HMI_recommend.

    Args:
        state: The current agent state
        llm: Language model for composing the message

    Returns:
        A dictionary containing the updated next_message_to_patient.
    """

    from langchain.schema import HumanMessage, SystemMessage
    from message_templates.workflow1_templates import WORKFLOW1_TEMPLATES

    doctor_profile = state.w1_context.current_doctor_under_consideration
    earliest_slot = state.w1_context.earliest_slot_found
    no_hmi_slot = state.w1_context.no_hmi_slot_flag

    print(
        f"DEBUG w1_compose_message: Doctor Profile available: {bool(doctor_profile)}, Earliest Slot available: {bool(earliest_slot)}, No HMI Slot Flag: {no_hmi_slot}"
    )

    if no_hmi_slot or not doctor_profile or not earliest_slot:
        error_msg = "I'm sorry, but I couldn't find an available HMI specialist slot based on your referral at this moment. Our team will look into this."
        print(
            f"DEBUG w1_compose_message: No HMI slot or missing details. Sending: {error_msg}"
        )
        return {"next_message_to_patient": error_msg}

    template_string = WORKFLOW1_TEMPLATES["single_referral_HMI_recommend"]

    # Prepare data specifically for the template and LLM
    patient_details_for_llm = {
        "patient_name": state.patient_details.patient_name
        or "Valued Patient"  # Fallback if name is None
    }

    doctor_profile_for_llm = {
        "name": doctor_profile.doctor_name or "Our Specialist",  # Fallback
        "specialty": (
            doctor_profile.doctor_specialties[0]
            if doctor_profile.doctor_specialties
            else "Relevant Specialty"
        ),  # Fallback
        "photoUrl": doctor_profile.photo_url
        or "",  # Add photoUrl, default to empty string if None
    }

    # Format appointment_start_time for human readability
    try:
        dt_obj = datetime.datetime.fromisoformat(earliest_slot.appointment_start_time)
        formatted_start_time = dt_obj.strftime(
            "%d %b %Y at %I:%M %p"
        )  # e.g., "19 May 2025 at 05:30 PM"
    except (ValueError, TypeError):
        formatted_start_time = "a near future date"  # Fallback if parsing fails
        print(
            f"WARN w1_compose_message: Could not parse earliest_slot.appointment_start_time: {earliest_slot.appointment_start_time}"
        )

    earliest_slot_for_llm = {
        "appointmentStartTime": formatted_start_time,
        "location": earliest_slot.location or "the clinic location",  # Fallback
    }

    # System prompt for the message composition
    system_prompt = """
    You are drafting a WhatsApp message to a patient.
    Your task is to fill all placeholders in the provided `template_string_to_fill`.
    You will be given the template string and three data objects: `patient_details_data`, `doctor_profile_data`, and `earliest_slot_data`.

    The template uses placeholders that directly correspond to the keys in these data objects, nested under the object name. For example:
    - To fill `{patient_details.patient_name}`, use the `patient_name` value from the `patient_details_data` object.
    - To fill `{doctor_profile.name}`, use the `name` value from the `doctor_profile_data` object.
    - To fill `{doctor_profile.specialty}`, use the `specialty` value from the `doctor_profile_data` object.
    - To fill `{doctor_profile.photoUrl}`, use the `photoUrl` value from the `doctor_profile_data` object. If the value is an empty string, render nothing for the line starting with 'Photo: ', or omit the line.
    - To fill `{earliest_slot.appointmentStartTime}`, use the `appointmentStartTime` (which is a pre-formatted string) from the `earliest_slot_data` object.
    - To fill `{earliest_slot.location}`, use the `location` value from the `earliest_slot_data` object.

    Replace these placeholders with their corresponding values from the data objects you are provided.
    Style: Use a friendly, clear, and concise tone.
    Constraint: The final message MUST NOT exceed 640 characters. Try to be well under this limit.
    Output: The fully composed WhatsApp message as a string ONLY. Do not add any preamble, explanation, or markdown formatting.
    """

    # Prepare the content for the human message
    # The keys here (patient_details, doctor_profile, earliest_slot) should match what the template expects after the dot.
    # The LLM will be instructed to map patient_details_data -> patient_details in the template, etc.
    human_message_content = {
        "template_string_to_fill": template_string,
        "patient_details_data": patient_details_for_llm,  # Data for {patient_details.xxx}
        "doctor_profile_data": doctor_profile_for_llm,  # Data for {doctor_profile.xxx}
        "earliest_slot_data": earliest_slot_for_llm,  # Data for {earliest_slot.xxx}
    }
    # Create messages for the LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=json.dumps(human_message_content)
        ),  # Ensure content is a string, e.g., JSON string
    ]

    print(
        f"DEBUG w1_compose_message: Sending to LLM: {json.dumps(human_message_content, indent=2)}"
    )  # DEBUG

    # Call the LLM
    response = await llm.ainvoke(messages)

    # Get the content from the response
    reply_payload = response.content

    # ***** DEBUG PRINT *****
    print(
        f"DEBUG w1_compose_message: LLM Response Content (reply_payload): {reply_payload}"
    )
    print(
        f"DEBUG w1_compose_message: Returning: {json.dumps({'next_message_to_patient': reply_payload}, indent=2)}"
    )
    # ***** END DEBUG PRINT *****

    # Store the message in state for the next node
    return {"next_message_to_patient": reply_payload}


async def w1_send(state: AgentState, **kwargs) -> Dict[str, Any]:
    """
    This node "sends" the message by ensuring it's in next_message_to_patient.
    The actual sending mechanism is outside the graph, handled by the chat loop.

    Args:
        state: The current agent state

    Returns:
        An empty dictionary as no further state update is needed by this node itself.
    """
    print(
        f"DEBUG w1_send: next_message_to_patient from state: {state.next_message_to_patient}"
    )  # DEBUG
    # The message is already set in state.next_message_to_patient by w1_compose_message
    # This node is more of a logical endpoint for the workflow before returning to the main loop.
    # No explicit state change needed here as the relevant state (next_message_to_patient)
    # was set by the previous node.
    return {}

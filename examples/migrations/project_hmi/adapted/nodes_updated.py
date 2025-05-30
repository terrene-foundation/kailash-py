"""
Custom nodes for the HMI project workflow using Kailash SDK with improved state management.

This module defines the custom node implementations for the HMI project,
implementing the Workflow 1 functionality with asynchronous support and
using the new immutable state management system.
"""

import asyncio
import datetime
import json
from typing import Any, Dict

from examples.migrations.project_hmi.adapted.mcp_wrapper import HmiMcpWrapper
from examples.migrations.project_hmi.adapted.message_templates import (
    WORKFLOW1_TEMPLATES,
)
from examples.migrations.project_hmi.adapted.shared import DoctorInfo, SlotInfo
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.workflow.state import WorkflowStateWrapper


@register_node(alias="w1_rank_specialist_v2")
class W1RankSpecialistNodeV2(AsyncNode):
    """
    Node that calls Specialist Ranking API to get top N doctors.

    Uses the new state management system for cleaner state updates.
    Implements asynchronous execution for API calls.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The wrapped agent state containing referral context",
            )
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The updated wrapped agent state with ranked doctors",
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        state = state_wrapper.get_state()
        mcp = HmiMcpWrapper()

        # Extract the specialty from the referral context
        specialty = None
        if state.referral_context and state.referral_context.referral_specialties:
            specialty = state.referral_context.referral_specialties[
                0
            ]  # Take the first specialty

        if not specialty:
            # Handle the case where no specialty is provided
            # This might be an error case that should be handled differently
            # Using clean state management for empty doctors list
            return {
                "state_wrapper": state_wrapper.update_in(
                    ["w1_context", "ranked_doctors_list"], []
                )
            }

        # Call the Specialist Ranking API
        # Note: In a real implementation, we would make this an async call
        # For now, we'll simulate an async delay and then make the synchronous call
        await asyncio.sleep(0.1)  # Simulate network delay
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
                self.logger.info(
                    f"Assuming system_id='{system_id_from_api}' for doctor {doctor_data.get('DoctorGivenID')} based on current testing assumption."
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
                    contact_number=doctor_data.get(
                        "contactnumber"
                    ),  # Not in API sample
                    photo_url=doctor_data.get("photourl"),  # Not in API sample
                    raw_profile_data=doctor_data,
                )
                ranked_doctors.append(doctor_info)
        elif isinstance(ranking_response, dict) and "error" in ranking_response:
            self.logger.error(
                f"Error in specialist ranking response: {ranking_response.get('error')}"
            )
            # Keep ranked_doctors as an empty list
        else:
            self.logger.error(
                f"Unexpected specialist ranking response format: {type(ranking_response)}. Content: {str(ranking_response)[:500]}..."
            )
            # Keep ranked_doctors as an empty list

        self.logger.debug(
            f"Parsed ranked_doctors list (count: {len(ranked_doctors)}): {ranked_doctors}"
        )

        # Clean state update using the new state management system
        return {
            "state_wrapper": state_wrapper.update_in(
                ["w1_context", "ranked_doctors_list"], ranked_doctors
            )
        }


@register_node(alias="w1_check_availability_v2")
class W1CheckAvailabilityNodeV2(AsyncNode):
    """
    Node that checks doctor availability by calling the slot API.

    For each doctor, call availability API until a slot < 7 days & ≥ 1 h ahead is found.
    On fail, set no_hmi_slot flag.

    Uses the new state management system for cleaner state updates.
    Implements asynchronous execution for API calls.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The wrapped agent state containing ranked doctors",
            )
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The updated wrapped agent state with availability information",
            ),
            "no_hmi_slot": NodeParameter(
                name="no_hmi_slot",
                type=bool,
                required=True,
                description="Flag indicating if no suitable slot was found",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        state = state_wrapper.get_state()
        mcp = HmiMcpWrapper()
        now = datetime.datetime.now()
        one_hour_ahead = now + datetime.timedelta(hours=1)
        seven_days_ahead = now + datetime.timedelta(days=7)

        chosen_doctor = None
        earliest_slot = None

        ranked_doctors = state.w1_context.ranked_doctors_list
        self.logger.debug(f"Processing {len(ranked_doctors)} ranked doctors.")

        # Loop through ranked doctors to find the first available slot
        for doctor_idx, doctor in enumerate(ranked_doctors):
            self.logger.debug(
                f"Checking doctor {doctor_idx + 1}/{len(ranked_doctors)}: ID={doctor.doctor_given_id}, System={doctor.system_id}"
            )
            if not doctor.doctor_given_id or not doctor.system_id:
                self.logger.debug(
                    f"Skipping doctor {doctor.doctor_given_id} due to missing ID or system_id."
                )
                continue

            # Call the availability API
            # Simulate an async API call with a delay
            await asyncio.sleep(0.2)  # Simulate network delay
            slots_response = mcp.get_doctor_available_slots(
                doctor_given_id=doctor.doctor_given_id, system_id=doctor.system_id
            )

            # Process the response to find a suitable slot
            # Assuming slots_response is directly the list of slots, based on user feedback and Postman output.
            if isinstance(slots_response, list):
                slot_list_from_response = slots_response
                self.logger.debug(
                    f"Processing {len(slot_list_from_response)} slots received as a direct list for doctor {doctor.doctor_given_id}."
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
                            self.logger.debug(
                                f"Skipping slot {slot_data_idx} due to missing date or time. Data: {slot_data}"
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
                    except (ValueError, TypeError) as e:
                        self.logger.error(
                            f"Error parsing slot {slot_data_idx} for doctor {doctor.doctor_given_id}. Slot data: {slot_data}. Error: {e}"
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
                self.logger.debug(
                    f"Found 'slots' key for doctor {doctor.doctor_given_id}. Number of slots received: {len(slot_list_from_response)}"
                )
                # ... (rest of the original logic for dict based response - can be DRYed up later)
                # For now, focusing on the list-based response, assuming it's the primary case.
                # This part would need the same datetime construction logic as above.
                pass  # Placeholder for brevity, as the main issue seems to be list response
            else:
                self.logger.warning(
                    f"'slots' key not found or response is not a list for doctor {doctor.doctor_given_id}. Response type: {type(slots_response)}. Response: {str(slots_response)[:500]}..."
                )

        # Determine no_hmi_slot flag value
        no_hmi_slot = not (chosen_doctor and earliest_slot)

        # Use batch_update for multiple state changes in one go
        if chosen_doctor and earliest_slot:
            self.logger.debug(
                f"Slot found for Dr. {chosen_doctor.doctor_name} ({chosen_doctor.doctor_given_id}) at {earliest_slot.appointment_start_time}"
            )

            # New immutable state management with batch updates
            updated_state_wrapper = state_wrapper.batch_update(
                [
                    (
                        ["w1_context", "current_doctor_under_consideration"],
                        chosen_doctor,
                    ),
                    (["w1_context", "earliest_slot_found"], earliest_slot),
                    (["w1_context", "no_hmi_slot_flag"], False),
                ]
            )
        else:
            self.logger.debug(
                "No suitable slot found after checking all ranked doctors."
            )

            # Set only the no_hmi_slot_flag to true
            updated_state_wrapper = state_wrapper.update_in(
                ["w1_context", "no_hmi_slot_flag"], True
            )

        return {"state_wrapper": updated_state_wrapper, "no_hmi_slot": no_hmi_slot}


@register_node(alias="w1_get_profile_v2")
class W1GetProfileNodeV2(AsyncNode):
    """
    Node that fetches detailed doctor profile.

    Fetch doctor profile (using mcp.get_doctors_list with specific ID if detailed profile isn't separate).

    Uses the new state management system for cleaner state updates.
    Implements asynchronous execution for API calls.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The wrapped agent state containing chosen doctor",
            )
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The updated wrapped agent state with detailed doctor profile",
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        state = state_wrapper.get_state()
        mcp = HmiMcpWrapper()

        # Extract the chosen doctor from the state
        chosen_doctor = state.w1_context.current_doctor_under_consideration

        if (
            not chosen_doctor
            or not chosen_doctor.doctor_given_id
            or not chosen_doctor.system_id
        ):
            # Handle the case where no doctor is available (e.g. if no_hmi_slot_flag was true and this node was still called)
            self.logger.debug(
                "No chosen doctor available or doctor details incomplete. Skipping profile fetch."
            )
            # Just return the current state with no changes
            return {"state_wrapper": state_wrapper}

        self.logger.debug(
            f"Fetching profile for Dr. {chosen_doctor.doctor_name} ({chosen_doctor.doctor_given_id}), System ID: {chosen_doctor.system_id}"
        )

        # Simulate async API call
        await asyncio.sleep(0.2)  # Simulate network delay

        # Call the API to get detailed doctor information
        doctor_details_response = mcp.get_doctors_list(
            system_id=chosen_doctor.system_id
        )

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

        # If no additional profile data found, just return current state
        if not doctor_profile_data:
            return {"state_wrapper": state_wrapper}

        # Update the doctor info
        # Create a new DoctorInfo object with the updates
        updated_doctor_info = chosen_doctor.model_copy(
            update={"raw_profile_data": doctor_profile_data}
        )

        # Update specific fields if available
        if doctor_profile_data.get("Name"):
            updated_doctor_info.doctor_name = doctor_profile_data.get("Name")

        if doctor_profile_data.get("PhoneNumber"):
            updated_doctor_info.contact_number = doctor_profile_data.get("PhoneNumber")

        if doctor_profile_data.get("PhotoUrl"):
            updated_doctor_info.photo_url = doctor_profile_data.get("PhotoUrl")

        # Use state_wrapper's update_in method for clean state update
        return {
            "state_wrapper": state_wrapper.update_in(
                ["w1_context", "current_doctor_under_consideration"],
                updated_doctor_info,
            )
        }


@register_node(alias="w1_compose_message_v2")
class W1ComposeMessageNodeV2(AsyncNode):
    """
    Node that composes a message to the patient using an LLM.

    Fill template single_referral_HMI_recommend.

    Uses the new state management system for cleaner state updates.
    Implements asynchronous execution for LLM calls.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The wrapped agent state containing doctor profile and slot",
            ),
            "llm": NodeParameter(
                name="llm",
                type=Any,  # Using Any for flexibility with different LLM implementations
                required=True,
                description="Language model for composing the message",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The updated wrapped agent state with composed message",
            ),
            "reply_payload": NodeParameter(
                name="reply_payload",
                type=str,
                required=True,
                description="The composed message to the patient",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        state = state_wrapper.get_state()
        llm = kwargs["llm"]

        doctor_profile = state.w1_context.current_doctor_under_consideration
        earliest_slot = state.w1_context.earliest_slot_found
        no_hmi_slot = state.w1_context.no_hmi_slot_flag

        self.logger.debug(
            f"Doctor Profile available: {bool(doctor_profile)}, Earliest Slot available: {bool(earliest_slot)}, No HMI Slot Flag: {no_hmi_slot}"
        )

        if no_hmi_slot or not doctor_profile or not earliest_slot:
            error_msg = "I'm sorry, but I couldn't find an available HMI specialist slot based on your referral at this moment. Our team will look into this."
            self.logger.debug(f"No HMI slot or missing details. Sending: {error_msg}")

            # Use update_in method for clean state update
            return {
                "state_wrapper": state_wrapper.update_in(
                    ["next_message_to_patient"], error_msg
                ),
                "reply_payload": error_msg,
            }

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
            dt_obj = datetime.datetime.fromisoformat(
                earliest_slot.appointment_start_time
            )
            formatted_start_time = dt_obj.strftime(
                "%d %b %Y at %I:%M %p"
            )  # e.g., "19 May 2025 at 05:30 PM"
        except (ValueError, TypeError):
            formatted_start_time = "a near future date"  # Fallback if parsing fails
            self.logger.warning(
                f"Could not parse earliest_slot.appointment_start_time: {earliest_slot.appointment_start_time}"
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
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(human_message_content),
            },  # Ensure content is a string, e.g., JSON string
        ]

        self.logger.debug(
            f"Sending to LLM: {json.dumps(human_message_content, indent=2)}"
        )

        # Call the LLM
        response = await llm.ainvoke(messages=messages)

        # Get the content from the response (assuming response structure can vary based on LLM implementation)
        if isinstance(response, dict) and "content" in response:
            reply_payload = response["content"]
        elif hasattr(response, "content"):
            reply_payload = response.content
        else:
            reply_payload = str(response)  # Fallback for unexpected response format

        self.logger.debug(f"LLM Response Content (reply_payload): {reply_payload}")

        # Use update_in method for clean state update
        return {
            "state_wrapper": state_wrapper.update_in(
                ["next_message_to_patient"], reply_payload
            ),
            "reply_payload": reply_payload,
        }


@register_node(alias="w1_send_v2")
class W1SendNodeV2(AsyncNode):
    """
    Node that represents sending a message to the patient.

    This node "sends" the message by ensuring it's in next_message_to_patient.
    The actual sending mechanism is outside the graph, handled by the chat loop.

    Uses the new state management system for cleaner state updates.
    Implements asynchronous execution for potential future integration with message sending services.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The wrapped agent state containing the message to send",
            ),
            "reply_payload": NodeParameter(
                name="reply_payload",
                type=str,
                required=True,
                description="The message payload to send",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="The updated wrapped agent state with message sent",
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        reply_payload = kwargs["reply_payload"]

        # Simulate an async operation (e.g. sending message to external service)
        await asyncio.sleep(0.1)

        # Ensure the message is set in state.next_message_to_patient
        # This is a bit redundant since it was set in the previous node,
        # but included for clarity and to ensure consistency
        return {
            "state_wrapper": state_wrapper.update_in(
                ["next_message_to_patient"], reply_payload
            )
        }

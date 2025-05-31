# Workflow 1: Present Initial Recommendation - Implementation Summary

This document summarizes the implementation details of Workflow 1, which is responsible for presenting an initial specialist recommendation to the patient based on their referral.

## 1. Overall Purpose

Workflow 1 aims to:
1.  Identify the top-ranked specialist(s) based on the patient's referred specialty.
2.  Find the earliest available appointment slot for a recommended specialist that is within a defined acceptable timeframe (currently < 7 days from now and ≥ 1 hour ahead).
3.  Fetch additional profile details for the chosen specialist.
4.  Compose a message to the patient presenting the recommendation, including the doctor's name, specialty, photo URL (if available), and the earliest slot details.
5.  If no suitable HMI slot is found, compose a message informing the patient accordingly.

## 2. Core Data Structures Utilized

-   **`AgentState`**: The central state object holding all conversation and context data.
    -   `AgentState.referral_context.referral_specialties`: Input for specialty.
    -   `AgentState.w1_context`: Stores data specific to Workflow 1:
        -   `ranked_doctors_list: List[DoctorInfo]`
        -   `current_doctor_under_consideration: Optional[DoctorInfo]`
        -   `earliest_slot_found: Optional[SlotInfo]`
        -   `no_hmi_slot_flag: bool`
    -   `AgentState.patient_details.patient_name`: Used in message composition.
    -   `AgentState.next_message_to_patient`: Output for the final message.
-   **`DoctorInfo` (from `models.shared`)**: Represents a doctor's details.
-   **`SlotInfo` (from `models.shared`)**: Represents an appointment slot's details.
-   **`WORKFLOW1_TEMPLATES` (from `message_templates.workflow1_templates`)**: Dictionary of message templates.

## 3. Node Details and Flow

The workflow is implemented as a subgraph within LangGraph, with nodes executed sequentially or conditionally. The nodes are defined in `workflows/w1/nodes.py` (and also refactored into individual files in `workflows/w1/individual_nodes/` for portability).

### 3.1. `w1_rank_specialist`

-   **Purpose**: To get a list of top-ranked doctors based on the patient's referred specialty.
-   **Inputs**:
    -   `state.referral_context.referral_specialties[0]` (the primary specialty).
-   **Processing**:
    -   Calls `mcp.get_specialist_ranking(specialty, sort_by="rank", sort_order="asc")`.
    -   **Crucial Assumption**: For each doctor returned by the ranking API, the `system_id` is currently hardcoded to **`"starmed"`**. This is a temporary assumption for testing and development. An `INFO` log indicates this assumption.
    -   Populates `DoctorInfo` objects for each ranked doctor, including fields like `doctor_given_id`, `system_id` (set to "starmed"), `doctor_name`, `doctor_specialties`, and `raw_profile_data`. Other fields like `clinic_name`, `clinic_location`, `contact_number`, `photo_url` are populated if present in the ranking API response, otherwise they remain `None`.
-   **Outputs / State Updates**:
    -   `state.w1_context.ranked_doctors_list` is updated with the list of `DoctorInfo` objects.

### 3.2. `w1_check_availability`

-   **Purpose**: To find the earliest suitable appointment slot for the ranked doctors.
-   **Inputs**:
    -   `state.w1_context.ranked_doctors_list`.
-   **Processing**:
    -   Iterates through the `ranked_doctors_list`.
    -   For each doctor, calls `mcp.get_doctor_available_slots(doctor_given_id, system_id)`.
    -   Assumes the API response (`slots_response`) is a direct list of slot objects.
    -   Parses each slot object:
        -   Extracts `"date"` (e.g., "YYYY-MM-DD") and `"time"` (e.g., "HH:MM AM/PM").
        -   Constructs a `datetime` object (`slot_start_dt`) from these.
        -   Calculates `slot_end_dt` using `timeslotinterval` (defaults to 30 mins).
    -   **Filtering Criteria**: A slot is considered "suitable" if:
        -   `slot_start_dt` is at least 1 hour from the current time (`now`).
        -   `slot_start_dt` is within 7 days from the current time (`now`).
    -   If suitable slots are found, the earliest one is selected.
-   **Outputs / State Updates**:
    -   If a suitable slot is found:
        -   `state.w1_context.current_doctor_under_consideration` is set to the `DoctorInfo` of the doctor with the earliest suitable slot.
        -   `state.w1_context.earliest_slot_found` is set to the `SlotInfo` of that earliest slot.
        -   `state.w1_context.no_hmi_slot_flag` is set to `False`.
    -   If no suitable slot is found for any ranked doctor:
        -   `state.w1_context.no_hmi_slot_flag` is set to `True`.
        -   `current_doctor_under_consideration` and `earliest_slot_found` remain `None`.

### 3.3. Graph Routing after `w1_check_availability`

-   (Defined in `workflows/w1/graph.py`)
-   If `state.w1_context.no_hmi_slot_flag` is `True`: The workflow routes directly to `w1_compose_message`.
-   If `state.w1_context.no_hmi_slot_flag` is `False`: The workflow routes to `w1_get_profile`.

### 3.4. `w1_get_profile`

-   **Purpose**: To fetch additional profile details for the `current_doctor_under_consideration`. This node is skipped if `no_hmi_slot_flag` was true.
-   **Inputs**:
    -   `state.w1_context.current_doctor_under_consideration`.
-   **Processing**:
    -   If `current_doctor_under_consideration` is `None` or lacks `doctor_given_id` or `system_id`, the function returns early.
    -   Calls `mcp.get_doctors_list(system_id=chosen_doctor.system_id)`.
    -   Filters the response list to find the doctor matching `chosen_doctor.doctor_given_id` and `chosen_doctor.system_id`.
    -   If a matching profile (`doctor_profile_data`) is found:
        -   Creates a copy of `chosen_doctor` using `model_copy(update={"raw_profile_data": doctor_profile_data})`.
        -   Updates fields like `doctor_name`, `contact_number`, and `photo_url` on this copied object if new, non-empty data is present in `doctor_profile_data`.
-   **Outputs / State Updates**:
    -   `state.w1_context.current_doctor_under_consideration` is updated with the `DoctorInfo` object that now includes the fetched `raw_profile_data` and potentially updated individual fields.

### 3.5. `w1_compose_message`

-   **Purpose**: To compose the message to be sent to the patient.
-   **Inputs**:
    -   `state.w1_context.current_doctor_under_consideration` (if a slot was found).
    -   `state.w1_context.earliest_slot_found` (if a slot was found).
    -   `state.w1_context.no_hmi_slot_flag`.
    -   `state.patient_details.patient_name`.
    -   `llm` (language model instance).
-   **Processing**:
    -   **If `no_hmi_slot_flag` is true OR `doctor_profile` or `earliest_slot` is `None`**:
        -   Sets `next_message_to_patient` to a predefined message: "I'm sorry, but I couldn't find an available HMI specialist slot based on your referral at this moment. Our team will look into this."
    -   **Else (if a doctor and slot are available)**:
        -   Loads the `single_referral_HMI_recommend` template from `WORKFLOW1_TEMPLATES`.
        -   Prepares data for the LLM:
            -   `patient_details_for_llm`: Contains `patient_name`.
            -   `doctor_profile_for_llm`: Contains `name`, `specialty`, and `photoUrl` (defaults to `""` if `None`).
            -   `earliest_slot_for_llm`: Contains `appointmentStartTime` (formatted as "DD MMM YYYY at HH:MM AM/PM") and `location`.
        -   Constructs a detailed system prompt instructing the LLM to fill the provided `template_string_to_fill` using the supplied data objects (`patient_details_data`, `doctor_profile_data`, `earliest_slot_data`). Includes instructions for handling an empty `photoUrl`.
        -   Calls the LLM with the system prompt and the human message containing the template and prepared data.
-   **Outputs / State Updates**:
    -   `state.next_message_to_patient` is updated with the message composed by the LLM or the predefined "no slot" message.

### 3.6. `w1_send`

-   **Purpose**: A logical endpoint for the workflow. The actual sending of the message is handled by the main chat loop based on `state.next_message_to_patient`.
-   **Inputs**:
    -   `state.next_message_to_patient`.
-   **Processing**:
    -   Currently, it only includes a debug print.
-   **Outputs / State Updates**:
    -   None. The graph transitions to `END` after this node.

## 4. Summary of Workflow 1 Completion (as per agentic_workflows_v2.md Section 2.1)

-   **W1_RankSpecialist**: Implemented. Fetches ranked doctors. `system_id` is currently hardcoded to "starmed".
-   **W1_CheckAvailability**: Implemented. Iterates doctors, calls slot API, filters by time. Handles direct list API response for slots and parses date/time correctly.
-   **W1_GetProfile**: Implemented. Fetches doctor profile if a slot was found. Uses `model_copy` and updates relevant fields. Client-side filtering is in place.
-   **W1_ComposeMessage**: Implemented. Uses `single_referral_HMI_recommend` template. Prepares data for LLM, including human-readable date and photo URL. Handles "no slot found" scenario.
-   **W1_Send**: Implemented as a pass-through node; message is in `next_message_to_patient`.

**Edge Case Handling**:
-   The `no_hmi_slot_flag` correctly routes to `w1_compose_message` to inform the patient if no initial HMI slots are found.
-   The `agentic_workflows_v2.md` mentions: `W1_CheckAvailability (no_hmi_slot) → AffiliateClinic_Workflow (not yet implemented)`. Currently, if `no_hmi_slot` is true, we inform the patient but do not yet branch to an `AffiliateClinic_Workflow`.

This documentation should provide a clear overview of the current state of Workflow 1.

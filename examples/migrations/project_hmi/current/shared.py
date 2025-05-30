from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal

# Literal types
NRIC_Type = Literal["NRIC", "PASSPORT", "FIN"]
AppointmentScheduleType = Literal["BOOK", "RESCH", "CANCEL"]
InsuranceStatusType = Literal[
    "Covered",  # MHC: Specialist on panel, fully covered
    "Pay_Claim",  # MHC: Off-panel, or general coverage for claim
    "Payment_Req",  # MHC: Co-payment or not covered
    "Covered_ext",  # External TPA: Covered
    "Not_covered_ext",  # External TPA: Not covered
    "Pending_Verification",
    "Unknown",
]

CaseStatusType = Literal[
    "Open",
    "Awaiting_Patient_Reply",
    "Recommendation_Presented",
    "Slot_Selection_Pending",
    "Booking_In_Progress",
    "Booking_Confirmed",
    "Booking_Failed",
    "Modification_In_Progress",
    "Modification_Confirmed",
    "Modification_Failed",
    "Cancellation_In_Progress",
    "Cancellation_Confirmed",
    "Cancellation_Failed",
    "Closed_Patient_Decline",
    "Closed_Booking_Completed",
    "Escalated_To_Human",
    "Error_State",
]

W2AIntentCategory = Literal[
    "own_arrangement",
    "private_doctor",
    "external_hospital",
    "GRH",  # Government Restructured Hospital
    "CHAS",
    "polyclinic",
    "unknown",
]


class PatientDetails(BaseModel):
    patient_nric: Optional[str] = Field(default=None)
    nric_type: Optional[NRIC_Type] = Field(default=None)
    patient_dob: Optional[str] = Field(default=None)  # YYYY-MM-DD
    patient_dob_verified: bool = Field(default=False)
    patient_sub_tpa: Optional[str] = Field(default=None)
    patient_name: Optional[str] = Field(default=None)
    patient_email: Optional[str] = Field(default=None)
    patient_id: Optional[str] = Field(default=None)
    patient_contact_number: Optional[str] = Field(default=None)
    patient_country_code: Optional[str] = Field(default=None)
    patient_nationality: Optional[str] = Field(default=None)
    patient_gender: Optional[str] = Field(default=None)
    patient_address_broad: Optional[str] = Field(default=None)
    patient_doctor_notes: Optional[str] = Field(default=None)
    enable_email_updates: bool = Field(default=True)
    pdpa_consent: Optional[bool] = Field(default=None)
    privacy_policy: Optional[bool] = Field(default=None)
    raw_mhc_member_details: Optional[Dict[str, Any]] = Field(default=None)


class ReferralContext(BaseModel):
    referral_specialties: List[str] = Field(default_factory=list)
    num_specialties_referred: Optional[int] = Field(default=None)
    referral_gp_clinic: Optional[str] = Field(default=None)
    referral_visit_date: Optional[str] = Field(default=None)  # YYYY-MM-DD
    referral_source_system_id: Optional[str] = Field(default=None)


class DoctorInfo(BaseModel):
    doctor_given_id: Optional[str] = Field(default=None)
    system_id: Optional[str] = Field(default=None)
    doctor_name: Optional[str] = Field(default=None)
    doctor_code: Optional[str] = Field(default=None)
    doctor_specialties: List[str] = Field(default_factory=list)
    clinic_name: Optional[str] = Field(default=None)
    clinic_location: Optional[str] = Field(default=None)
    clinic_location_code: Optional[str] = Field(default=None)
    contact_number: Optional[str] = Field(default=None)
    photo_url: Optional[str] = Field(default=None)
    raw_profile_data: Optional[Dict[str, Any]] = Field(default=None)


class SlotInfo(BaseModel):
    appointment_start_time: Optional[str] = Field(default=None)  # ISO 8601
    appointment_end_time: Optional[str] = Field(default=None)  # ISO 8601
    appointment_date_str: Optional[str] = Field(default=None)  # DD MMM YYYY
    appointment_time_str: Optional[str] = Field(default=None)  # H:MM AM/PM
    location: Optional[str] = Field(default=None)
    system_id: Optional[str] = Field(default=None)
    doctor_given_id: Optional[str] = Field(default=None)
    raw_slot_data: Optional[Dict[str, Any]] = Field(default=None)


class BookingContext(BaseModel):
    chosen_specialist_details: Optional[DoctorInfo] = Field(default=None)
    chosen_slot_details: Optional[SlotInfo] = Field(default=None)

    # HMI One specific fields
    hmi_one_appointment_type: str = Field(default="inperson")
    hmi_one_uploaded_files: Optional[str] = Field(default=None)
    hmi_one_cc_name: Optional[str] = Field(default=None)
    hmi_one_agent_name: Optional[str] = Field(default=None)
    hmi_one_schedule_type: Optional[AppointmentScheduleType] = Field(default=None)
    hmi_one_subject: Optional[str] = Field(default=None)
    hmi_one_notes: Optional[str] = Field(default=None)
    hmi_one_additional_notes: Optional[str] = Field(default=None)
    hmi_one_medical_condition: Optional[str] = Field(default=None)
    hmi_one_purpose: Optional[str] = Field(default=None)
    hmi_one_mysid_no: Optional[str] = Field(default=None)
    hmi_one_mysid_type: Optional[str] = Field(default=None)
    hmi_one_passport: Optional[str] = Field(default=None)
    hmi_one_passport_exp: Optional[str] = Field(default=None)
    hmi_one_existing_appointment_id: Optional[str] = Field(default=None)
    hmi_one_returning_patient: Optional[str] = Field(default=None)
    hmi_one_reason_for_cancellation: Optional[str] = Field(default=None)

    booking_id: Optional[str] = Field(default=None)
    patient_confirmed_choice: bool = Field(default=False)
    last_booking_response_raw: Optional[Dict[str, Any]] = Field(default=None)


class InterpreterOutput(BaseModel):
    workflow_id: Optional[str] = Field(default=None)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None)
    raw_llm_response: Optional[str] = Field(default=None)


class W1Context(BaseModel):
    ranked_doctors_list: List[DoctorInfo] = Field(default_factory=list)
    current_doctor_under_consideration: Optional[DoctorInfo] = Field(default=None)
    earliest_slot_found: Optional[SlotInfo] = Field(default=None)
    no_hmi_slot_flag: bool = Field(default=False)


class W2aContext(BaseModel):
    intent_category: Optional[W2AIntentCategory] = Field(default=None)
    provider_name_preference: Optional[str] = Field(default=None)
    location_preference: Optional[str] = Field(default=None)
    is_on_panel: Optional[bool] = Field(default=None)
    distance_ok: Optional[bool] = Field(default=None)
    subspecialty_match: Optional[bool] = Field(default=None)
    persuasion_template_id_suggestion: Optional[str] = Field(default=None)
    persuasion_variables_suggestion: Optional[Dict[str, Any]] = Field(default=None)


class W3Context(BaseModel):
    parsed_date_constraints: Optional[Dict[str, Any]] = Field(default=None)
    filtered_chosen_slot: Optional[SlotInfo] = Field(default=None)
    no_match_found_flag: bool = Field(default=False)
    no_match_reason: Optional[str] = Field(default=None)


class Coordinates(BaseModel):
    lat: float
    lng: float


class LocationContext(BaseModel):
    geocoding_available: bool = Field(default=True)
    patient_coordinates: Optional[Coordinates] = Field(default=None)
    preferred_provider_coordinates: Optional[Coordinates] = Field(default=None)
    recommended_doctor_coordinates: Optional[Coordinates] = Field(default=None)
    distance_to_preferred: Optional[float] = Field(default=None)
    distance_to_recommended: Optional[float] = Field(default=None)
    location_comparison_method: Optional[Literal["geocoding", "llm_knowledge"]] = Field(
        default=None
    )


class AgentState(BaseModel):
    # Core Identifiers & History
    request_id: Optional[str] = Field(default=None)

    # Patient & Referral Data
    patient_details: PatientDetails = Field(default_factory=PatientDetails)
    referral_context: ReferralContext = Field(default_factory=ReferralContext)

    # Booking Lifecycle
    booking_context: BookingContext = Field(default_factory=BookingContext)

    # Cross-Workflow Status & Control
    insurance_status: InsuranceStatusType = Field(default="Pending_Verification")
    error_counter: int = Field(default=0)
    handover_flag: bool = Field(default=False)
    case_status: CaseStatusType = Field(default="Open")

    # Interpreter & Routing
    interpreter_last_output: Optional[InterpreterOutput] = Field(default=None)
    current_workflow_id: Optional[str] = Field(default=None)

    # Last LLM / Tool interaction
    last_llm_node_id: Optional[str] = Field(default=None)
    last_llm_response_payload: Optional[Any] = Field(default=None)
    last_tool_node_id: Optional[str] = Field(default=None)
    last_tool_output_raw: Optional[Any] = Field(default=None)

    # Workflow-specific contexts
    w1_context: W1Context = Field(default_factory=W1Context)
    w2a_context: W2aContext = Field(default_factory=W2aContext)
    w3_context: W3Context = Field(default_factory=W3Context)
    location_context: LocationContext = Field(default_factory=LocationContext)

    # Communication payloads
    next_message_to_patient: Optional[str] = Field(default=None)

    def copy_with_updates(self, **updates: Dict[str, Any]) -> "AgentState":
        """
        Create a copy of the current state with specified updates.
        This is a convenience wrapper around model_copy(update=updates).

        Args:
            **updates: Dictionary of field updates to apply

        Returns:
            AgentState: A new AgentState instance with the updates applied
        """
        return self.model_copy(update=updates)

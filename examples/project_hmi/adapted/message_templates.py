"""
Message templates for the HMI project.

This module contains templates for different message types sent to patients.
"""

WORKFLOW1_TEMPLATES = {
    "single_referral_HMI_recommend": """
Hello {patient_details.patient_name},

I found an available appointment with {doctor_profile.name}, a {doctor_profile.specialty} specialist, on {earliest_slot.appointmentStartTime} at {earliest_slot.location}.
Photo: {doctor_profile.photoUrl}

Would you like me to book this appointment for you?
""",

    "multiple_referral_same_loc_HMI_recommend": """
Hello {patient_details.patient_name},

I've found available appointments with specialists for your referrals at {location}:

- {doctor_profile_1.name} ({doctor_profile_1.specialty}): {earliest_slot_1.appointmentStartTime}
- {doctor_profile_2.name} ({doctor_profile_2.specialty}): {earliest_slot_2.appointmentStartTime}

Would you like me to book any of these for you?
""",

    "multiple_referral_diff_loc_HMI_recommend": """
Hello {patient_details.patient_name},

I've found available appointments with specialists for your referrals:

- {doctor_profile_1.name} ({doctor_profile_1.specialty}) at {earliest_slot_1.location}: {earliest_slot_1.appointmentStartTime}
- {doctor_profile_2.name} ({doctor_profile_2.specialty}) at {earliest_slot_2.location}: {earliest_slot_2.appointmentStartTime}

Would you like me to book any of these for you?
"""
}

WORKFLOW2_TEMPLATES = {
    "patient_preference_own_arrangement": """
I understand you prefer to make your own arrangements. Would you like information about specialists you can see directly?
""",
    
    "patient_preference_private_doctor": """
I understand you prefer to see Dr. {doctor_name}. Would you like me to check if this doctor is covered by your insurance plan?
""",
    
    "patient_preference_external_hospital": """
I understand you prefer to go to {hospital_name}. Let me check if there are covered specialists there under your plan.
"""
}

WORKFLOW3_TEMPLATES = {
    "date_time_preference_confirmation": """
I'll look for an appointment on {preferred_date} around {preferred_time}. I'll get back to you shortly with options.
""",
    
    "no_slots_available": """
I'm sorry, but there are no available slots matching your date/time preference. Would you like to try different dates or see our next available slots?
"""
}

BOOKING_TEMPLATES = {
    "booking_confirmation": """
Your appointment has been confirmed:

Doctor: {doctor_name}
Date/Time: {appointment_date_time}
Location: {location}
Booking Reference: {booking_reference}

You will receive a confirmation email shortly. Please arrive 15 minutes before your appointment time.
""",
    
    "booking_failure": """
I'm sorry, but there was an issue with the booking process: {error_message}

Please let me know if you'd like to try again or select a different slot.
"""
}
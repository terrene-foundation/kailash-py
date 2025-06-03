"""
Example script demonstrating the HMI workflow with immutable state management.

This script initializes and runs the HMI workflow using the new immutable
state management system for cleaner, more reliable state transitions.
"""

import asyncio
import importlib.util
import json
import logging
from typing import Any, Dict, List

# First check if required modules are available
REQUIRED_MODULES = ["requests"]
MISSING_MODULES = []

for module in REQUIRED_MODULES:
    if importlib.util.find_spec(module) is None:
        MISSING_MODULES.append(module)

if MISSING_MODULES:
    print(
        f"Warning: The following modules are required but missing: {', '.join(MISSING_MODULES)}"
    )
    print("This example will run with mocked dependencies to demonstrate the concepts.")
    MOCK_EVERYTHING = True
else:
    MOCK_EVERYTHING = False

# We'll import our modules after patching to prevent import errors
from examples.migrations.project_hmi.adapted.shared import (  # noqa: E402
    AgentState,
    DoctorInfo,
    SlotInfo,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Simple LLM implementation for demonstration
class SimpleLLM:
    """
    A simple mock LLM for demonstration purposes.

    In a real-world scenario, this would be replaced with a connection
    to an actual language model service.
    """

    async def ainvoke(self, messages: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Simulate an async LLM call.

        Args:
            messages: The input messages

        Returns:
            Dict with content field containing the generated text
        """
        # Simulate some processing time
        await asyncio.sleep(0.5)

        # Check the messages and generate a response
        system_content = (
            messages[0].get("content", "")
            if messages and messages[0].get("role") == "system"
            else ""
        )
        user_content = (
            messages[1].get("content", "")
            if len(messages) > 1 and messages[1].get("role") == "user"
            else ""
        )

        # Simple template filling simulation
        if "fill" in system_content.lower() and "template" in system_content.lower():
            # Extract some data from the user content (which should be JSON)
            try:
                data = json.loads(user_content)
                template = data.get("template_string_to_fill", "")
                patient_data = data.get("patient_details_data", {})
                doctor_data = data.get("doctor_profile_data", {})
                slot_data = data.get("earliest_slot_data", {})

                # Very basic template replacement
                template = template.replace(
                    "{patient_details.patient_name}",
                    patient_data.get("patient_name", "Patient"),
                )
                template = template.replace(
                    "{doctor_profile.name}", doctor_data.get("name", "Doctor")
                )
                template = template.replace(
                    "{doctor_profile.specialty}",
                    doctor_data.get("specialty", "Specialist"),
                )

                # Handle photo URL
                if doctor_data.get("photoUrl"):
                    template = template.replace(
                        "{doctor_profile.photoUrl}",
                        f"Photo: {doctor_data.get('photoUrl')}",
                    )
                else:
                    # Remove the whole photo line
                    template = template.replace("Photo: {doctor_profile.photoUrl}", "")

                template = template.replace(
                    "{earliest_slot.appointmentStartTime}",
                    slot_data.get("appointmentStartTime", "soon"),
                )
                template = template.replace(
                    "{earliest_slot.location}", slot_data.get("location", "the clinic")
                )

                return {"content": template}
            except Exception as e:
                logger.error(f"Error in template filling: {e}")
                return {"content": "I couldn't process the template correctly."}

        # Default response
        return {"content": "Hello! This is a response from the simple LLM."}


# Mock API data for the W1RankSpecialistNodeImmutable
class MockMcpWrapper:
    """
    Mock MCP wrapper for testing without real API calls.

    This class provides mock responses for the API calls in the workflow.
    """

    def get_specialist_ranking(self, specialty=None, sort_by=None, sort_order=None):
        """Mock specialist ranking API response."""
        return [
            {
                "DoctorGivenID": "D12345",
                "Doctor": "Dr. John Smith",
                "Speciality": specialty or "Cardiology",
                "Location": "Central Medical Clinic",
            },
            {
                "DoctorGivenID": "D67890",
                "Doctor": "Dr. Jane Johnson",
                "Speciality": specialty or "Cardiology",
                "Location": "Downtown Health Center",
            },
        ]

    def get_doctor_available_slots(self, doctor_given_id, system_id):
        """Mock doctor available slots API response."""
        import datetime

        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        return [
            {
                "date": tomorrow.strftime("%Y-%m-%d"),
                "time": "10:30 AM",
                "location": "Central Medical Clinic",
                "timeslotinterval": 30,
            },
            {
                "date": tomorrow.strftime("%Y-%m-%d"),
                "time": "02:15 PM",
                "location": "Central Medical Clinic",
                "timeslotinterval": 30,
            },
        ]

    def get_doctors_list(
        self, system_id="", page_index=1, page_size=1000, sort_by="name"
    ):
        """Mock doctors list API response."""
        return {
            "doctorinfo": [
                {
                    "Givenid": "D12345",
                    "Entity": "starmed",
                    "Name": "Dr. John Smith",
                    "PhoneNumber": "555-123-4567",
                    "PhotoUrl": "https://example.com/doctor-smith.jpg",
                },
                {
                    "Givenid": "D67890",
                    "Entity": "starmed",
                    "Name": "Dr. Jane Johnson",
                    "PhoneNumber": "555-987-6543",
                    "PhotoUrl": "",
                },
            ]
        }


async def run_fully_mocked():
    """
    Run the workflow with all dependencies mocked.
    This is used when required modules are missing.
    """

    # Create a mocked version of the workflow that doesn't require external dependencies
    class MockedWorkflow:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_workflow1(self, state):
            # Simulate a successful workflow execution
            state.w1_context.no_hmi_slot_flag = False
            state.w1_context.current_doctor_under_consideration = DoctorInfo(
                doctor_given_id="D12345",
                system_id="starmed",
                doctor_name="Dr. John Smith",
                doctor_specialties=["Cardiology"],
                clinic_location="Central Medical Clinic",
            )
            state.w1_context.earliest_slot_found = SlotInfo(
                appointment_start_time="2025-05-30T10:30:00",
                appointment_end_time="2025-05-30T11:00:00",
                appointment_date_str="30 May 2025",
                appointment_time_str="10:30 AM",
                location="Central Medical Clinic",
            )
            state.next_message_to_patient = (
                "Hello John Doe, I found an available appointment with Dr. John Smith, "
                "a Cardiology specialist, on 30 May 2025 at 10:30 AM at Central Medical Clinic. "
                "Would you like me to book this appointment for you?"
            )
            return state

    # Create state and execute
    state = AgentState()
    state.request_id = "mocked-request-id"
    state.patient_details.patient_name = "John Doe"
    state.referral_context.referral_specialties = ["Cardiology"]

    workflow = MockedWorkflow(llm=None)
    updated_state = await workflow.execute_workflow1(state)

    # Print results
    logger.info("===== Mocked Workflow Result Summary =====")
    logger.info(
        "Note: Running with mocked dependencies to demonstrate immutable state concepts"
    )
    logger.info(f"Request ID: {updated_state.request_id}")
    logger.info(f"Patient: {updated_state.patient_details.patient_name}")
    logger.info(f"Specialties: {updated_state.referral_context.referral_specialties}")
    if updated_state.w1_context.current_doctor_under_consideration:
        logger.info(
            f"Doctor: {updated_state.w1_context.current_doctor_under_consideration.doctor_name}"
        )
    if updated_state.w1_context.earliest_slot_found:
        logger.info(
            f"Slot: {updated_state.w1_context.earliest_slot_found.appointment_date_str} at {updated_state.w1_context.earliest_slot_found.appointment_time_str}"
        )
        logger.info(
            f"Location: {updated_state.w1_context.earliest_slot_found.location}"
        )
    logger.info(f"Message: {updated_state.next_message_to_patient}")

    # Display example of immutable state update from comparison
    logger.info("\n===== Immutable State Management Example =====")
    logger.info("Traditional approach:")
    logger.info(
        """
    updated_w1_context = state.w1_context.model_copy()
    updated_w1_context.ranked_doctors_list = ranked_doctors
    updated_state = state.copy_with_updates(w1_context=updated_w1_context)
    return {"updated_state": updated_state}
    """
    )

    logger.info("Immutable state management approach:")
    logger.info(
        """
    return {
        "state_wrapper": state_wrapper.update_in(
            ["w1_context", "ranked_doctors_list"],
            ranked_doctors
        )
    }
    """
    )


async def run_with_mocked_apis():
    """Run the HMI workflow with mocked API responses."""
    # Import real implementation classes now
    # Patch the HmiMcpWrapper in nodes_immutable module
    import examples.migrations.project_hmi.adapted.nodes_immutable as nodes
    from examples.migrations.project_hmi.adapted.workflow_immutable import (
        HmiWorkflowImmutable,
        create_initial_state,
    )

    original_wrapper = nodes.HmiMcpWrapper
    nodes.HmiMcpWrapper = MockMcpWrapper

    try:
        await main(HmiWorkflowImmutable, create_initial_state)
    finally:
        # Restore original wrapper
        nodes.HmiMcpWrapper = original_wrapper


async def main(WorkflowClass, create_state_func):
    """Run the HMI workflow example with immutable state management."""
    # Create the LLM instance
    llm = SimpleLLM()

    # Create the workflow
    workflow = WorkflowClass(llm=llm)

    # Create the initial state
    state = create_state_func()

    # Execute the workflow
    logger.info("Starting workflow execution with immutable state management")
    try:
        updated_state = await workflow.execute_workflow1(state)

        # Check the result
        if updated_state.next_message_to_patient:
            logger.info(
                f"Workflow generated message: {updated_state.next_message_to_patient}"
            )
        else:
            logger.warning("No message generated by the workflow")

        # Additional state inspection
        if updated_state.w1_context.no_hmi_slot_flag:
            logger.info("No HMI slot was found")
        else:
            logger.info("Found an HMI slot")

        if updated_state.w1_context.current_doctor_under_consideration:
            doctor = updated_state.w1_context.current_doctor_under_consideration
            logger.info(
                f"Selected doctor: {doctor.doctor_name} ({doctor.doctor_specialties})"
            )

        # Print complete workflow result summary
        logger.info("\n===== Workflow Result Summary =====")
        logger.info(f"Request ID: {updated_state.request_id}")
        logger.info(f"Patient: {updated_state.patient_details.patient_name}")
        logger.info(
            f"Specialties: {updated_state.referral_context.referral_specialties}"
        )
        if (
            not updated_state.w1_context.no_hmi_slot_flag
            and updated_state.w1_context.current_doctor_under_consideration
        ):
            logger.info(
                f"Doctor: {updated_state.w1_context.current_doctor_under_consideration.doctor_name}"
            )
            if updated_state.w1_context.earliest_slot_found:
                logger.info(
                    f"Slot: {updated_state.w1_context.earliest_slot_found.appointment_date_str} at {updated_state.w1_context.earliest_slot_found.appointment_time_str}"
                )
                logger.info(
                    f"Location: {updated_state.w1_context.earliest_slot_found.location}"
                )
        logger.info(f"Message: {updated_state.next_message_to_patient}")

    except Exception as e:
        logger.error(f"Error executing workflow: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    if MOCK_EVERYTHING:
        # Run with all dependencies mocked when required modules are missing
        asyncio.run(run_fully_mocked())
    else:
        # Run with just mocked APIs for reliable testing
        try:
            # Only import workflow classes when dependencies are available
            from examples.migrations.project_hmi.adapted.workflow_immutable import (  # noqa: F401
                HmiWorkflowImmutable,
                create_initial_state,
            )

            asyncio.run(run_with_mocked_apis())
        except ImportError as e:
            logger.error(f"ImportError: {e}")
            logger.info("Falling back to fully mocked example")
            asyncio.run(run_fully_mocked())

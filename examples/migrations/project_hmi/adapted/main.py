"""
Main module for running the HMI project workflow.

This module demonstrates how to use the Kailash SDK to implement the HMI workflow.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


# Simple mock LLM implementation
class MockLLM:
    """Mock LLM class for demonstration purposes."""

    async def ainvoke(self, messages: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Mock LLM invocation.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with generated content
        """
        system_message = (
            messages[0]["content"]
            if messages and messages[0]["role"] == "system"
            else ""
        )
        user_message = (
            messages[1]["content"]
            if len(messages) > 1 and messages[1]["role"] == "user"
            else ""
        )

        logger.info(f"MockLLM received system message: {system_message[:100]}...")
        logger.info(f"MockLLM received user message: {user_message[:100]}...")

        # Parse the messages to simulate LLM behavior
        import json

        try:
            user_data = json.loads(user_message)
            template = user_data.get("template_string_to_fill", "")
            patient_data = user_data.get("patient_details_data", {})
            doctor_data = user_data.get("doctor_profile_data", {})
            slot_data = user_data.get("earliest_slot_data", {})

            # Simple template filling logic
            message = template.replace(
                "{patient_details.patient_name}",
                patient_data.get("patient_name", "Patient"),
            )
            message = message.replace(
                "{doctor_profile.name}", doctor_data.get("name", "Doctor")
            )
            message = message.replace(
                "{doctor_profile.specialty}", doctor_data.get("specialty", "Specialist")
            )

            # Handle photo URL
            if doctor_data.get("photoUrl"):
                message = message.replace(
                    "{doctor_profile.photoUrl}", doctor_data.get("photoUrl", "")
                )
            else:
                # Remove the entire Photo: line if no URL
                message = message.replace("Photo: {doctor_profile.photoUrl}\n", "")

            message = message.replace(
                "{earliest_slot.appointmentStartTime}",
                slot_data.get("appointmentStartTime", "soon"),
            )
            message = message.replace(
                "{earliest_slot.location}", slot_data.get("location", "the clinic")
            )

            # Clean up any extra whitespace
            message = "\n".join(line for line in message.split("\n") if line.strip())

            return {"content": message}
        except Exception as e:
            logger.error(f"Error in MockLLM: {e}")
            return {
                "content": "Hello! I've found an appointment for you with a specialist. Would you like me to book it?"
            }


async def main():
    """
    Main function to run the HMI workflow.
    """
    # Import here to avoid circular imports and ensure logging is configured first
    from examples.migrations.project_hmi.adapted.workflow import (
        HmiWorkflow,
        create_initial_state,
    )

    # Create a mock LLM for demonstration
    llm = MockLLM()

    # Create the workflow
    hmi_workflow = HmiWorkflow(llm)

    # Create an initial state
    state = create_initial_state()

    # Execute Workflow 1
    logger.info("Starting Workflow 1 execution")
    try:
        updated_state = await hmi_workflow.execute_workflow1(state)

        # Display the message that would be sent to the patient
        message = updated_state.next_message_to_patient
        if message:
            logger.info("=== Message to Patient ===")
            logger.info(message)
            logger.info("========================")
        else:
            logger.warning("No message generated for patient")

        # Display some information about the state
        if updated_state.w1_context.current_doctor_under_consideration:
            doctor = updated_state.w1_context.current_doctor_under_consideration
            logger.info(
                f"Selected doctor: {doctor.doctor_name} ({doctor.doctor_specialties})"
            )

        if updated_state.w1_context.earliest_slot_found:
            slot = updated_state.w1_context.earliest_slot_found
            logger.info(
                f"Selected slot: {slot.appointment_date_str} {slot.appointment_time_str} at {slot.location}"
            )

    except Exception as e:
        logger.error(f"Error executing workflow: {e}", exc_info=True)


if __name__ == "__main__":
    # Set environment variable to enable mocked slots
    os.environ["MOCK_SLOTS_FOR_DOCTOR_ID"] = (
        "CKK"  # Example doctor ID to mock slots for
    )

    # Run the async main function
    asyncio.run(main())

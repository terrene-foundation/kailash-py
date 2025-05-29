"""
Example demonstrating the improved state management in the Kailash SDK.

This script shows how to use the new immutable state management system
for cleaner and more robust state updates in workflows.
"""
import asyncio
import logging
from typing import Any, Dict

from kailash.workflow.state import WorkflowStateWrapper, StateManager
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from project_hmi.adapted.shared import AgentState
from project_hmi.adapted.workflow_updated import HmiWorkflowV2, create_initial_state


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleLLM:
    """Simple LLM mock for demonstration purposes."""
    
    async def ainvoke(self, messages: list) -> Dict[str, Any]:
        """
        Simulate an LLM response for the message template.
        
        Args:
            messages: List of message objects
            
        Returns:
            Simulated LLM response
        """
        # Just simulate a delay
        await asyncio.sleep(0.5)
        
        # Simple template filling for demonstration
        system_msg = messages[0]["content"]
        user_msg = messages[1]["content"]
        
        # For the demo, just return a canned response
        return {
            "content": "Hello John Doe, I've found a suitable appointment with Dr. Smith, " 
                       "Cardiologist, on 25 Jun 2025 at 10:30 AM at Central Clinic. "
                       "Please confirm if this works for you."
        }


def demonstrate_state_management_basics():
    """Demonstrate the basics of the new state management system."""
    print("\n===== Basic State Management Demonstration =====")
    
    # Create an initial state
    state = create_initial_state()
    print(f"Initial state: Patient name = {state.patient_details.patient_name}")
    
    # Show manual state updates (old way)
    updated_w1_context = state.w1_context.model_copy()
    updated_w1_context.no_hmi_slot_flag = True
    updated_state = state.copy_with_updates(w1_context=updated_w1_context)
    print(f"Old way - Updated state: no_hmi_slot_flag = {updated_state.w1_context.no_hmi_slot_flag}")
    
    # Now demonstrate the new way with StateManager
    # 1. Direct update_in
    new_state = StateManager.update_in(state, ["w1_context", "no_hmi_slot_flag"], False)
    print(f"New way - StateManager.update_in: no_hmi_slot_flag = {new_state.w1_context.no_hmi_slot_flag}")
    
    # 2. Batch update
    batch_updated_state = StateManager.batch_update(
        state,
        [
            (["w1_context", "no_hmi_slot_flag"], True),
            (["patient_details", "patient_name"], "Jane Doe"),
            (["current_workflow_id"], "w2")
        ]
    )
    print(f"New way - StateManager.batch_update: "
          f"no_hmi_slot_flag = {batch_updated_state.w1_context.no_hmi_slot_flag}, "
          f"patient_name = {batch_updated_state.patient_details.patient_name}, "
          f"workflow_id = {batch_updated_state.current_workflow_id}")
    
    # 3. Using WorkflowStateWrapper
    state_wrapper = WorkflowStateWrapper(state)
    
    # Single update
    updated_wrapper = state_wrapper.update_in(
        ["patient_details", "patient_name"], 
        "Alice Smith"
    )
    print(f"WorkflowStateWrapper.update_in: "
          f"patient_name = {updated_wrapper.get_state().patient_details.patient_name}")
    
    # Batch update
    batch_wrapper = state_wrapper.batch_update([
        (["patient_details", "patient_name"], "Bob Johnson"),
        (["referral_context", "referral_specialties"], ["Orthopedics", "Neurology"])
    ])
    print(f"WorkflowStateWrapper.batch_update: "
          f"patient_name = {batch_wrapper.get_state().patient_details.patient_name}, "
          f"specialties = {batch_wrapper.get_state().referral_context.referral_specialties}")
    
    # Demonstrate immutability
    print(f"Original state (unchanged): patient_name = {state.patient_details.patient_name}")


async def run_workflow_with_new_state_management():
    """Run the updated HMI workflow with the new state management system."""
    print("\n===== Running HMI Workflow with New State Management =====")
    
    # Create initial state
    state = create_initial_state()
    
    # Create a simple LLM mock
    llm = SimpleLLM()
    
    # Create the workflow with the LLM
    workflow = HmiWorkflowV2(llm)
    
    # Execute the workflow
    print("Executing workflow...")
    result_state = await workflow.execute_workflow1(state)
    
    # Show results
    print("\nWorkflow Execution Results:")
    print(f"Patient name: {result_state.patient_details.patient_name}")
    print(f"Doctor found: {result_state.w1_context.current_doctor_under_consideration and result_state.w1_context.current_doctor_under_consideration.doctor_name}")
    print(f"No slot flag: {result_state.w1_context.no_hmi_slot_flag}")
    print(f"Message to patient: {result_state.next_message_to_patient}")


async def main():
    """Run the demonstrations."""
    # First demonstrate basic state management
    demonstrate_state_management_basics()
    
    # Then run a more complete workflow example
    await run_workflow_with_new_state_management()


if __name__ == "__main__":
    asyncio.run(main())
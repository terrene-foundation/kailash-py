"""
Workflow definition for the HMI project using Kailash SDK with improved state management.

This module creates a workflow graph for the HMI project, implementing Workflow 1
for presenting initial specialist recommendations using the new immutable state
management system for cleaner, more reliable state updates.
"""

import logging
from typing import Any

from examples.project_hmi.adapted.nodes_updated import (
    W1CheckAvailabilityNodeV2,
    W1ComposeMessageNodeV2,
    W1GetProfileNodeV2,
    W1RankSpecialistNodeV2,
    W1SendNodeV2,
)
from examples.project_hmi.adapted.shared import AgentState
from kailash.nodes.logic.operations import Switch
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.runner import WorkflowRunner

logger = logging.getLogger(__name__)


class HmiWorkflowV2:
    """
    HMI workflow for processing patient referrals and recommending specialists.

    This class wraps the individual workflow implementations and provides a common
    interface for executing them using Kailash's new state management system.
    """

    def __init__(self, llm: Any):
        """
        Initialize the HMI workflow.

        Args:
            llm: Language model instance for message composition
        """
        self.llm = llm

        # Initialize the workflow runner
        self.runner = WorkflowRunner()

        # Initialize workflows
        self.workflow1 = self._create_workflow1()

        # Add workflows to the runner
        self.runner.add_workflow("w1", self.workflow1)

        logger.info("HMI workflow initialized with new state management")

    def _create_workflow1(self) -> Workflow:
        """
        Create the Workflow 1 graph (Present Initial Recommendation).

        Uses updated nodes that leverage the new state management system.

        Returns:
            Workflow instance for W1
        """
        workflow = Workflow(
            workflow_id="hmi_w1_v2",
            name="HMI_Workflow1_V2",
            description="Presents initial specialist recommendation based on referral with improved state management",
        )

        # Add nodes to the workflow
        workflow.add_node("rank_specialist", W1RankSpecialistNodeV2())
        workflow.add_node("check_availability", W1CheckAvailabilityNodeV2())

        # Add the switch node for conditional routing
        workflow.add_node(
            "route_by_availability",
            Switch(
                condition_field="no_hmi_slot",
                operator="==",
                value=True,
                pass_condition_result=True,
            ),
        )

        workflow.add_node("get_profile", W1GetProfileNodeV2())
        workflow.add_node("compose_message", W1ComposeMessageNodeV2(llm=self.llm))
        workflow.add_node("send", W1SendNodeV2())

        # Connect nodes - First part of the workflow
        workflow.connect(
            "rank_specialist", "check_availability", {"state_wrapper": "state_wrapper"}
        )

        # Connect check_availability to the switch node
        workflow.connect(
            "check_availability",
            "route_by_availability",
            {"state_wrapper": "input_data", "no_hmi_slot": "condition_field"},
        )

        # Conditional routing based on availability
        # If no_hmi_slot is true (true_output), route directly to compose_message
        workflow.connect(
            "route_by_availability", "compose_message", {"true_output": "state_wrapper"}
        )

        # If no_hmi_slot is false (false_output), route to get_profile first
        workflow.connect(
            "route_by_availability", "get_profile", {"false_output": "state_wrapper"}
        )

        # Connect get_profile to compose_message
        workflow.connect(
            "get_profile", "compose_message", {"state_wrapper": "state_wrapper"}
        )

        # Connect compose_message to send
        workflow.connect(
            "compose_message",
            "send",
            {"state_wrapper": "state_wrapper", "reply_payload": "reply_payload"},
        )

        logger.info(
            "Workflow 1 V2 created with 6 nodes including switch node for conditional routing"
        )
        return workflow

    async def execute_workflow1(self, state: AgentState) -> AgentState:
        """
        Execute Workflow 1 (Present Initial Recommendation).

        This asynchronous method executes the workflow using an AsyncLocalRuntime
        to handle async nodes properly.

        Args:
            state: Current agent state

        Returns:
            Updated agent state after workflow execution
        """
        logger.info(
            "Executing Workflow 1 V2 with AsyncLocalRuntime and improved state management"
        )

        # Create async runtime
        runtime = AsyncLocalRuntime(debug=True)

        # Create a state wrapper
        state_wrapper = self.workflow1.create_state_wrapper(state)

        # Run the workflow asynchronously
        try:
            # Use the execute_with_state method for cleaner state management
            results, run_id = await runtime.execute(
                self.workflow1, parameters={"state_wrapper": state_wrapper}
            )

            # Get the result from the last node
            if "send" in results and "state_wrapper" in results["send"]:
                final_state_wrapper = results["send"]["state_wrapper"]
                final_state = final_state_wrapper.get_state()
                logger.info(f"Workflow 1 V2 executed successfully. Run ID: {run_id}")
                return final_state
            else:
                logger.error("Workflow 1 V2 failed to return expected result")
                return state  # Return original state on failure
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            return state  # Return original state on failure

    def connect_workflows(self) -> None:
        """
        Connect multiple workflows to form a complete processing pipeline.

        This allows workflows to be chained together, with the output state of one
        becoming the input state for the next based on conditions.
        """
        # Example of how multiple workflows could be connected
        # In a real implementation, you would define additional workflows (w2, w3, etc.)
        # and add connections between them

        # For now, we just have workflow1, so no connections to make
        pass

    async def execute_pipeline(self, state: AgentState) -> AgentState:
        """
        Execute the entire workflow pipeline.

        This would use the WorkflowRunner to execute multiple connected workflows.
        For now, it just executes workflow1.

        Args:
            state: Current agent state

        Returns:
            Updated agent state after pipeline execution
        """
        # For now, since we only have one workflow, just execute it
        return await self.execute_workflow1(state)


def create_initial_state() -> AgentState:
    """
    Create an initial state for the HMI workflow.

    Returns:
        AgentState instance with some example data
    """
    state = AgentState()
    state.patient_details.patient_name = "John Doe"
    state.referral_context.referral_specialties = ["Cardiology"]
    state.current_workflow_id = "w1"

    return state

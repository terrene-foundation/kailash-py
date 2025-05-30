"""
Workflow definition for the HMI project using Kailash SDK with immutable state management.

This module creates a workflow graph for the HMI project, implementing Workflow 1
for presenting initial specialist recommendations using the robust immutable state
management system for cleaner, more reliable state transitions.
"""

import logging
import uuid
from typing import Any

from examples.migrations.project_hmi.adapted.nodes_immutable import (
    W1CheckAvailabilityNodeImmutable,
    W1ComposeMessageNodeImmutable,
    W1GetProfileNodeImmutable,
    W1RankSpecialistNodeImmutable,
    W1SendNodeImmutable,
)
from examples.migrations.project_hmi.adapted.shared import AgentState
from kailash.nodes.logic.operations import Switch
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.runner import WorkflowRunner

logger = logging.getLogger(__name__)


class HmiWorkflowImmutable:
    """
    HMI workflow for processing patient referrals and recommending specialists.

    This class implements the workflow using immutable state management,
    providing cleaner, more reliable state transitions between nodes.
    """

    def __init__(self, llm: Any):
        """
        Initialize the HMI workflow with immutable state management.

        Args:
            llm: Language model instance for message composition
        """
        self.llm = llm

        # Initialize the workflow runner
        self.runner = WorkflowRunner()

        # Initialize the different workflow graphs
        self.workflow1 = self._create_workflow1()

        # Register workflows with the runner
        self.runner.add_workflow("w1", self.workflow1)

        logger.info("HMI workflow with immutable state management initialized")

    def _create_workflow1(self) -> Workflow:
        """
        Create the Workflow 1 graph (Present Initial Recommendation).

        Uses immutable state management nodes for cleaner, more reliable state transitions.

        Returns:
            Workflow instance for W1
        """
        workflow = Workflow(
            workflow_id="hmi_w1_immutable",
            name="HMI_Workflow1_Immutable",
            description="Presents initial specialist recommendation based on referral with immutable state",
        )

        # Add nodes to the workflow
        workflow.add_node("rank_specialist", W1RankSpecialistNodeImmutable())
        workflow.add_node("check_availability", W1CheckAvailabilityNodeImmutable())

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

        workflow.add_node("get_profile", W1GetProfileNodeImmutable())
        workflow.add_node(
            "compose_message", W1ComposeMessageNodeImmutable(llm=self.llm)
        )
        workflow.add_node("send", W1SendNodeImmutable())

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
            "Workflow 1 (immutable) created with 6 nodes including switch node for conditional routing"
        )
        return workflow

    async def execute_workflow1(self, state: AgentState) -> AgentState:
        """
        Execute Workflow 1 (Present Initial Recommendation).

        Uses the immutable state management system for cleaner, more reliable state transitions.

        Args:
            state: Current agent state

        Returns:
            Updated agent state after workflow execution
        """
        logger.info(
            "Executing Workflow 1 with AsyncLocalRuntime and immutable state management"
        )

        # Create runtime
        runtime = AsyncLocalRuntime(debug=True)

        # Wrap the state with WorkflowStateWrapper
        state_wrapper = self.workflow1.create_state_wrapper(state)

        # Run the workflow asynchronously
        try:
            # Execute the workflow with state wrapper
            final_state, results = await runtime.execute_with_state(
                self.workflow1, state_model=state, wrap_state=True
            )

            logger.info("Workflow 1 (immutable) executed successfully")
            return final_state
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            return state  # Return original state on failure

    async def execute_workflow_pipeline(self, state: AgentState) -> AgentState:
        """
        Execute a pipeline of workflows.

        This uses the WorkflowRunner to connect and execute multiple workflows
        based on state conditions.

        Args:
            state: Initial agent state

        Returns:
            Final state after all relevant workflows are executed
        """
        # For now, we only have workflow1, so just execute that
        # In the future, we can add more workflows and connect them
        return await self.execute_workflow1(state)


def create_initial_state() -> AgentState:
    """
    Create an initial state for the HMI workflow.

    Returns:
        AgentState instance with some example data
    """
    state = AgentState()

    # Add a unique request ID for tracking
    state.request_id = str(uuid.uuid4())

    # Set patient details
    state.patient_details.patient_name = "John Doe"

    # Set referral information
    state.referral_context.referral_specialties = ["Cardiology"]

    # Set current workflow ID
    state.current_workflow_id = "w1"

    return state

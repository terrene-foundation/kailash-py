"""
Workflow definition for the HMI project using Kailash SDK.

This module creates a workflow graph for the HMI project, implementing Workflow 1
for presenting initial specialist recommendations.
"""

import logging
from typing import Any

from examples.migrations.project_hmi.adapted.nodes import (
    W1CheckAvailabilityNode,
    W1ComposeMessageNode,
    W1GetProfileNode,
    W1RankSpecialistNode,
    W1SendNode,
)
from examples.migrations.project_hmi.adapted.shared import AgentState

from kailash.nodes.logic.operations import Switch
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class HmiWorkflow:
    """
    HMI workflow for processing patient referrals and recommending specialists.

    This class wraps the individual workflow implementations and provides a common
    interface for executing them.
    """

    def __init__(self, llm: Any):
        """
        Initialize the HMI workflow.

        Args:
            llm: Language model instance for message composition
        """
        self.llm = llm

        # Initialize the different workflow graphs
        self.workflow1 = self._create_workflow1()

        logger.info("HMI workflow initialized")

    def _create_workflow1(self) -> Workflow:
        """
        Create the Workflow 1 graph (Present Initial Recommendation).

        Returns:
            Workflow instance for W1
        """
        workflow = Workflow(
            workflow_id="hmi_w1",
            name="HMI_Workflow1",
            description="Presents initial specialist recommendation based on referral",
        )

        # Add nodes to the workflow
        workflow.add_node("rank_specialist", W1RankSpecialistNode())
        workflow.add_node("check_availability", W1CheckAvailabilityNode())

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

        workflow.add_node("get_profile", W1GetProfileNode())
        workflow.add_node("compose_message", W1ComposeMessageNode(llm=self.llm))
        workflow.add_node("send", W1SendNode())

        # Connect nodes - First part of the workflow
        workflow.connect(
            "rank_specialist", "check_availability", {"updated_state": "state"}
        )

        # Connect check_availability to the switch node
        workflow.connect(
            "check_availability",
            "route_by_availability",
            {"updated_state": "input_data", "no_hmi_slot": "condition_field"},
        )

        # Conditional routing based on availability
        # If no_hmi_slot is true (true_output), route directly to compose_message
        workflow.connect(
            "route_by_availability", "compose_message", {"true_output": "state"}
        )

        # If no_hmi_slot is false (false_output), route to get_profile first
        workflow.connect(
            "route_by_availability", "get_profile", {"false_output": "state"}
        )

        # Connect get_profile to compose_message
        workflow.connect("get_profile", "compose_message", {"updated_state": "state"})

        # Connect compose_message to send
        workflow.connect(
            "compose_message",
            "send",
            {"updated_state": "state", "reply_payload": "reply_payload"},
        )

        logger.info(
            "Workflow 1 created with 6 nodes including switch node for conditional routing"
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
        from kailash.runtime.async_local import AsyncLocalRuntime

        logger.info("Executing Workflow 1 with AsyncLocalRuntime")

        # Create async runtime
        runtime = AsyncLocalRuntime(debug=True)

        # Run the workflow asynchronously
        try:
            results, run_id = await runtime.execute(
                self.workflow1, parameters={"state": state}
            )

            # Get the result from the last node
            if "send" in results and "updated_state" in results["send"]:
                updated_state = results["send"]["updated_state"]
                logger.info(f"Workflow 1 executed successfully. Run ID: {run_id}")
                return updated_state
            else:
                logger.error("Workflow 1 failed to return expected result")
                return state  # Return original state on failure
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            return state  # Return original state on failure


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

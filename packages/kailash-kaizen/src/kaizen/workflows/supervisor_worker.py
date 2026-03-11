"""
Supervisor-worker workflow template for multi-agent coordination.

This module provides supervisor-worker workflow templates that coordinate
a supervisor agent with multiple worker agents in hierarchical patterns.
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class SupervisorWorkerWorkflow:
    """
    Supervisor-worker coordination workflow template.

    Coordinates a supervisor agent with multiple worker agents in hierarchical
    delegation patterns. Built on Core SDK WorkflowBuilder for execution.
    """

    def __init__(
        self,
        supervisor: Any,
        workers: List[Any],
        task: str,
        coordination_pattern: str = "hierarchical",
        kaizen_instance: Optional[Any] = None,
    ):
        """
        Initialize supervisor-worker workflow.

        Args:
            supervisor: Supervisor agent
            workers: List of worker agents
            task: Task to coordinate
            coordination_pattern: Pattern for coordination
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.supervisor = supervisor
        self.workers = workers
        self.task = task
        self.coordination_pattern = coordination_pattern
        self.kaizen = kaizen_instance
        self.pattern = "supervisor_worker"

        # Coordination state
        self.coordination_flow = self._create_coordination_flow()

        logger.info(
            f"Initialized supervisor-worker workflow: '{task}' with 1 supervisor and {len(workers)} workers"
        )

    def _create_coordination_flow(self) -> Dict[str, Any]:
        """Create the coordination flow structure for supervisor-worker pattern."""
        return {
            "pattern": "supervisor_worker",
            "stages": [
                {"stage": "task_delegation", "participants": "supervisor"},
                {
                    "stage": "worker_execution",
                    "participants": "workers",
                    "pattern": self.coordination_pattern,
                },
                {"stage": "progress_monitoring", "participants": "supervisor"},
                {"stage": "result_synthesis", "participants": "supervisor"},
            ],
        }

    def build(self) -> WorkflowBuilder:
        """
        Build Core SDK workflow for supervisor-worker execution.

        Returns:
            WorkflowBuilder: Workflow ready for execution
        """
        workflow = WorkflowBuilder()

        # Add A2A Coordinator for hierarchical management
        coordinator_config = {
            "coordination_strategy": "delegation",
            "task": {
                "task_id": "supervisor_task",
                "description": self.task,
                "type": "coordination",
                "priority": "high",
                "required_skills": ["coordination", "supervision"],
            },
            "coordination_pattern": self.coordination_pattern,
            "supervisor": {
                "agent_id": (
                    self.supervisor.id
                    if hasattr(self.supervisor, "id")
                    else self.supervisor.agent_id
                ),
                "role": getattr(self.supervisor, "role", "Supervisor"),
                "authority_level": self.supervisor.config.get(
                    "authority_level", "supervisor"
                ),
            },
            "workers": [
                {
                    "agent_id": worker.id if hasattr(worker, "id") else worker.agent_id,
                    "role": getattr(worker, "role", "Worker"),
                    "specialization": worker.config.get("specialization", "general"),
                    "authority_level": worker.config.get("authority_level", "worker"),
                }
                for worker in self.workers
            ],
        }
        workflow.add_node(
            "A2ACoordinatorNode", "supervisor_coordinator", coordinator_config
        )

        # Add supervisor as A2A agent node
        supervisor_config = {
            "model": self.supervisor.config.get(
                "model", "gpt-4"
            ),  # Supervisor often needs more capable model
            "generation_config": self.supervisor.config.get(
                "generation_config",
                {
                    "temperature": self.supervisor.config.get(
                        "temperature", 0.4
                    ),  # Lower temp for coordination
                    "max_tokens": self.supervisor.config.get("max_tokens", 800),
                },
            ),
            "role": getattr(self.supervisor, "role", "Supervisor"),
            "supervision_context": {
                "task": self.task,
                "coordination_style": self.supervisor.config.get(
                    "coordination_style", "directive"
                ),
                "authority_level": "supervisor",
                "worker_count": len(self.workers),
            },
            "coordinator_id": "supervisor_coordinator",
            "a2a_enabled": True,
            "system_prompt": (
                f"You are {getattr(self.supervisor, 'role', 'the Supervisor')} leading a team. "
                f"Task: {self.task}. "
                f"You have {len(self.workers)} workers under your coordination. "
                f"Your coordination style: {self.supervisor.config.get('coordination_style', 'collaborative')}. "
                f"Provide clear direction, delegate effectively, monitor progress, "
                f"and synthesize results from your team members."
            ),
        }

        supervisor_id = (
            self.supervisor.id
            if hasattr(self.supervisor, "id")
            else self.supervisor.agent_id
        )
        workflow.add_node("A2AAgentNode", supervisor_id, supervisor_config)

        # Add each worker as A2A agent node
        for i, worker in enumerate(self.workers):
            worker_config = {
                "model": worker.config.get("model", "gpt-3.5-turbo"),
                "generation_config": worker.config.get(
                    "generation_config",
                    {
                        "temperature": worker.config.get("temperature", 0.7),
                        "max_tokens": worker.config.get("max_tokens", 600),
                    },
                ),
                "role": getattr(worker, "role", f"Worker {i+1}"),
                "work_context": {
                    "task": self.task,
                    "specialization": worker.config.get("specialization", "general"),
                    "authority_level": "worker",
                    "supervisor_id": supervisor_id,
                },
                "coordinator_id": "supervisor_coordinator",
                "a2a_enabled": True,
                "system_prompt": (
                    f"You are {getattr(worker, 'role', f'Worker {i+1}')} on a coordinated team. "
                    f"Task: {self.task}. "
                    f"Your specialization: {worker.config.get('specialization', 'general work')}. "
                    f"You report to the supervisor and work collaboratively with other team members. "
                    f"Execute your assigned work thoroughly and communicate progress clearly."
                ),
            }

            worker_id = worker.id if hasattr(worker, "id") else worker.agent_id
            workflow.add_node("A2AAgentNode", worker_id, worker_config)

        logger.info(
            f"Built supervisor-worker workflow with 1 supervisor and {len(self.workers)} workers"
        )
        return workflow

    def extract_coordination_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured coordination results from workflow execution results.

        Args:
            results: Raw results from workflow execution

        Returns:
            Structured coordination results
        """
        coordination_results = {
            "task": self.task,
            "coordination_pattern": self.coordination_pattern,
            "supervisor_instructions": "",
            "worker_outputs": [],
            "coordination_summary": "",
        }

        # Extract coordinator results
        coordinator_result = results.get("supervisor_coordinator", {})
        if coordinator_result:
            coordination_results["coordination_summary"] = coordinator_result

        # Extract supervisor results
        supervisor_id = (
            self.supervisor.id
            if hasattr(self.supervisor, "id")
            else self.supervisor.agent_id
        )
        supervisor_result = results.get(supervisor_id, {})
        if supervisor_result:
            response_text = str(
                supervisor_result.get("response", supervisor_result.get("content", ""))
            )
            coordination_results["supervisor_instructions"] = response_text

        # Extract worker results
        for worker in self.workers:
            worker_id = worker.id if hasattr(worker, "id") else worker.agent_id
            worker_result = results.get(worker_id, {})

            if worker_result:
                response_text = str(
                    worker_result.get("response", worker_result.get("content", ""))
                )
                coordination_results["worker_outputs"].append(
                    {
                        "agent": worker_id,
                        "role": getattr(worker, "role", "Worker"),
                        "specialization": worker.config.get(
                            "specialization", "general"
                        ),
                        "output": response_text,
                    }
                )

        # Generate coordination summary if not available from coordinator
        if not coordination_results["coordination_summary"]:
            coordination_results["coordination_summary"] = (
                f"Supervisor-worker coordination completed for task: {self.task}. "
                f"Supervisor provided instructions and {len(coordination_results['worker_outputs'])} "
                f"workers contributed specialized outputs."
            )

        return coordination_results

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the supervisor-worker coordination workflow.

        Args:
            inputs: Optional input parameters for the coordination

        Returns:
            Dict containing structured supervision results

        Examples:
            >>> supervisor_workflow = kaizen.create_supervisor_worker_workflow(supervisor, workers, task)
            >>> result = supervisor_workflow.execute()
            >>> print(result['task_completion_status'])
            >>> print(result['supervisor_coordination'])
        """
        import time

        from kailash.runtime.local import LocalRuntime

        # Initialize execution
        execution_start = time.time()

        try:
            # Build and execute workflow
            workflow = self.build()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                execution_params.update(inputs)

            # Execute the workflow with context manager for proper resource cleanup
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(workflow.build(), execution_params)

            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Extract structured coordination results
            coordination_results = self.extract_coordination_results(results)

            # Structure final results for supervision workflow
            final_results = {
                "task_completion_status": "completed",
                "supervisor_coordination": {
                    "task_assignments": {
                        (
                            worker.id if hasattr(worker, "id") else worker.agent_id
                        ): f"Assigned specialized task from main task: {self.task}"
                        for worker in self.workers
                    },
                    "progress_monitoring": "active",
                    "supervision_summary": coordination_results.get(
                        "supervisor_instructions", "Supervision provided"
                    ),
                },
                "worker_results": {
                    worker_output["agent"]: worker_output["output"]
                    for worker_output in coordination_results.get("worker_outputs", [])
                },
                "final_synthesis": coordination_results.get(
                    "coordination_summary", "Task coordination complete"
                ),
                "task": self.task,
                "coordination_pattern": self.coordination_pattern,
                "participants": len(self.workers) + 1,  # +1 for supervisor
                "execution_time_ms": execution_time,
                "run_id": run_id,
                "raw_results": results,
            }

            return final_results

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Return error result
            return {
                "task_completion_status": "failed",
                "supervisor_coordination": {
                    "task_assignments": {},
                    "progress_monitoring": "failed",
                    "supervision_summary": f"Supervision failed: {str(e)}",
                },
                "worker_results": {},
                "final_synthesis": f"Coordination failed: {str(e)}",
                "task": self.task,
                "coordination_pattern": self.coordination_pattern,
                "participants": len(self.workers) + 1,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

    async def execute_async(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the supervisor-worker coordination workflow asynchronously.

        This is the recommended execution method for multi-agent workflows as it
        leverages AsyncLocalRuntime for true concurrent execution without thread pools.

        Args:
            inputs: Optional input parameters for the coordination

        Returns:
            Dict containing structured supervision results

        Examples:
            >>> supervisor_workflow = kaizen.create_supervisor_worker_workflow(supervisor, workers, task)
            >>> result = await supervisor_workflow.execute_async()
            >>> print(result['task_completion_status'])
            >>> print(result['supervisor_coordination'])
        """
        import time

        from kailash.runtime import AsyncLocalRuntime

        # Initialize execution
        execution_start = time.time()

        try:
            # Build workflow for execution
            workflow = self.build()

            # Use AsyncLocalRuntime for true async execution (no thread pool)
            runtime = AsyncLocalRuntime()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                execution_params.update(inputs)

            # True async execution - uses AsyncLocalRuntime.execute_workflow_async()
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs=execution_params
            )

            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Extract structured coordination results
            coordination_results = self.extract_coordination_results(results)

            # Structure final results for supervision workflow
            final_results = {
                "task_completion_status": "completed",
                "supervisor_coordination": {
                    "task_assignments": {
                        (
                            worker.id if hasattr(worker, "id") else worker.agent_id
                        ): f"Assigned specialized task from main task: {self.task}"
                        for worker in self.workers
                    },
                    "progress_monitoring": "active",
                    "supervision_summary": coordination_results.get(
                        "supervisor_instructions", "Supervision provided"
                    ),
                },
                "worker_results": {
                    worker_output["agent"]: worker_output["output"]
                    for worker_output in coordination_results.get("worker_outputs", [])
                },
                "final_synthesis": coordination_results.get(
                    "coordination_summary", "Task coordination complete"
                ),
                "task": self.task,
                "coordination_pattern": self.coordination_pattern,
                "participants": len(self.workers) + 1,  # +1 for supervisor
                "execution_time_ms": execution_time,
                "run_id": run_id,
                "raw_results": results,
            }

            return final_results

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Return error result
            return {
                "task_completion_status": "failed",
                "supervisor_coordination": {
                    "task_assignments": {},
                    "progress_monitoring": "failed",
                    "supervision_summary": f"Supervision failed: {str(e)}",
                },
                "worker_results": {},
                "final_synthesis": f"Coordination failed: {str(e)}",
                "task": self.task,
                "coordination_pattern": self.coordination_pattern,
                "participants": len(self.workers) + 1,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

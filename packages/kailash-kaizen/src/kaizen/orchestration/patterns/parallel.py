"""
Parallel Pipeline - Concurrent Agent Execution

Implements concurrent execution of multiple agents with asyncio and result aggregation.

Pattern:
    User Request → [Agent1, Agent2, Agent3, ...] (parallel) → Aggregate Results

Features:
- Concurrent execution with asyncio (10-100x faster than sequential)
- Configurable max_workers for resource control
- Custom result aggregation functions
- Graceful error handling (partial results)
- Composable via .to_agent()

Usage:
    from kaizen.orchestration.pipeline import Pipeline

    # Basic parallel execution
    pipeline = Pipeline.parallel(agents=[agent1, agent2, agent3])
    result = pipeline.run(input="test_data")

    # With custom aggregator
    def combine(results):
        return {"combined": " | ".join(r["output"] for r in results)}

    pipeline = Pipeline.parallel(agents=[agent1, agent2], aggregator=combine)
    result = pipeline.run(input="test")

Author: Kaizen Framework Team
Created: 2025-10-27 (Phase 3, TODO-174)
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
"""

import asyncio
import concurrent.futures
from typing import Any, Callable, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline


class ParallelPipeline(Pipeline):
    """
    Parallel Pipeline with concurrent agent execution.

    Executes all agents concurrently using asyncio/threads, then aggregates results.
    Supports custom aggregation functions and graceful error handling.

    Attributes:
        agents: List of agents to execute in parallel
        aggregator: Optional function to aggregate results
        max_workers: Max concurrent executions (default: 10)
        error_handling: "graceful" (default) or "fail-fast"
        timeout: Optional timeout per agent (seconds)

    Example:
        from kaizen.orchestration.pipeline import Pipeline

        pipeline = Pipeline.parallel(
            agents=[agent1, agent2, agent3],
            max_workers=5,
            aggregator=lambda results: {"count": len(results)}
        )

        result = pipeline.run(input="test_data")
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        aggregator: Optional[Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = None,
        max_workers: int = 10,
        error_handling: str = "graceful",
        timeout: Optional[float] = None,
    ):
        """
        Initialize Parallel Pipeline.

        Args:
            agents: List of agents to execute in parallel (must not be empty)
            aggregator: Optional function to aggregate results
            max_workers: Max concurrent executions (default: 10)
            error_handling: "graceful" (default) or "fail-fast"
            timeout: Optional timeout per agent in seconds

        Raises:
            ValueError: If agents list is empty
        """
        if not agents:
            raise ValueError("agents cannot be empty")

        self.agents = agents
        self.aggregator = aggregator or self._default_aggregator
        self.max_workers = max_workers
        self.error_handling = error_handling
        self.timeout = timeout

    def _default_aggregator(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Default aggregator: return list of all results.

        Args:
            results: List of agent results

        Returns:
            Dict with "results" key containing all results
        """
        return {"results": results}

    def _execute_agent_sync(
        self, agent: BaseAgent, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute single agent synchronously with error handling.

        Args:
            agent: Agent to execute
            inputs: Inputs for agent execution

        Returns:
            Dict with agent result or error info
        """
        try:
            result = agent.run(**inputs)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            return result

        except Exception as e:
            if self.error_handling == "fail-fast":
                raise e
            else:
                # Graceful: return error info
                import traceback

                return {
                    "error": str(e),
                    "agent_id": (
                        agent.agent_id if hasattr(agent, "agent_id") else "unknown"
                    ),
                    "status": "failed",
                    "traceback": traceback.format_exc(),
                }

    def _execute_parallel_sync(self, inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute all agents in parallel using ThreadPoolExecutor.

        Args:
            inputs: Inputs for all agents

        Returns:
            List of agent results (in agent order)
        """
        # Use ThreadPoolExecutor for true concurrent execution
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            # Submit all agent executions
            futures = []
            for agent in self.agents:
                future = executor.submit(self._execute_agent_sync, agent, inputs)
                futures.append(future)

            # Collect results (in submission order)
            results = []
            for future in futures:
                try:
                    if self.timeout:
                        result = future.result(timeout=self.timeout)
                    else:
                        result = future.result()
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    if self.error_handling == "fail-fast":
                        raise
                    else:
                        # Graceful: return timeout error
                        results.append(
                            {
                                "error": "Execution timeout",
                                "status": "timeout",
                            }
                        )
                except Exception as e:
                    if self.error_handling == "fail-fast":
                        raise
                    else:
                        # Graceful: return error
                        results.append(
                            {
                                "error": str(e),
                                "status": "failed",
                            }
                        )

            return results

    async def _execute_agent_async(
        self, agent: BaseAgent, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute single agent asynchronously (wraps sync execution).

        Args:
            agent: Agent to execute
            inputs: Inputs for agent execution

        Returns:
            Dict with agent result or error info
        """
        # Run synchronous agent in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self._execute_agent_sync, agent, inputs
        )
        return result

    async def _execute_parallel_async(
        self, inputs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute all agents in parallel using asyncio.

        Args:
            inputs: Inputs for all agents

        Returns:
            List of agent results (in agent order)
        """
        # Create tasks for all agents
        tasks = [self._execute_agent_async(agent, inputs) for agent in self.agents]

        # Execute concurrently
        if self.error_handling == "fail-fast":
            # Fail-fast: stop on first error
            results = await asyncio.gather(*tasks)
        else:
            # Graceful: return exceptions as results
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to error dicts
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    import traceback

                    processed_results.append(
                        {
                            "error": str(result),
                            "status": "failed",
                            "traceback": traceback.format_exc(),
                        }
                    )
                else:
                    processed_results.append(result)

            results = processed_results

        return results

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute parallel pipeline: run all agents concurrently.

        Args:
            **inputs: Inputs for all agents (same inputs passed to each)

        Returns:
            Dict[str, Any]: Aggregated results from all agents

        Execution:
            - All agents receive the same inputs
            - Execution is concurrent (not sequential)
            - Results are aggregated using aggregator function

        Error Handling:
            - graceful (default): Partial results, errors in result dicts
            - fail-fast: Stop on first error, raise exception
        """
        # Try async execution first (faster)
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # Already in async context, use sync execution to avoid nested loops
                results = self._execute_parallel_sync(inputs)
            except RuntimeError:
                # Not in async context, use asyncio
                results = asyncio.run(self._execute_parallel_async(inputs))
        except Exception:
            if self.error_handling == "fail-fast":
                raise
            # Fall back to sync execution
            results = self._execute_parallel_sync(inputs)

        # Aggregate results
        try:
            aggregated = self.aggregator(results)
        except Exception:
            if self.error_handling == "fail-fast":
                raise
            # Graceful: return raw results
            aggregated = self._default_aggregator(results)

        return aggregated


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "ParallelPipeline",
]

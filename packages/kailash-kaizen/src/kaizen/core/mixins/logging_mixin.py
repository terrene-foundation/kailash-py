"""
Logging Mixin for BaseAgent.

Provides structured logging for agent operations including:
- Execution start/end logging with timing
- Error logging with stack traces
- Configurable log levels per operation
- Structured extra fields for log aggregation
"""

import functools
import inspect
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class LoggingMixin:
    """
    Mixin that adds structured logging to agents.

    Wraps the agent's run method with logging for:
    - Execution start with input summary
    - Execution success with result summary
    - Execution failure with error details
    - Timing metrics

    Example:
        config = BaseAgentConfig(logging_enabled=True)
        agent = SimpleQAAgent(config)
        # Agent.run() now logs start, end, and timing
    """

    @classmethod
    def apply(cls, agent: "BaseAgent") -> None:
        """
        Apply logging behavior to agent.

        Creates an agent-specific logger and wraps the run method
        with structured logging.

        Args:
            agent: The agent instance to apply logging to
        """
        # Create agent-specific logger
        agent_name = agent.__class__.__name__
        agent._agent_logger = logging.getLogger(f"kaizen.agent.{agent_name}")

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)

        def _log_start(execution_id: str, args: tuple, kwargs: dict) -> None:
            """Log execution start."""
            agent._agent_logger.info(
                f"Starting execution [{execution_id}]",
                extra={
                    "execution_id": execution_id,
                    "agent": agent_name,
                    "input_keys": list(kwargs.keys()) if kwargs else None,
                    "args_count": len(args) if args else 0,
                },
            )

        def _log_success(execution_id: str, duration_ms: float, result: Any) -> None:
            """Log execution success."""
            agent._agent_logger.info(
                f"Execution complete [{execution_id}] in {duration_ms:.2f}ms",
                extra={
                    "execution_id": execution_id,
                    "agent": agent_name,
                    "duration_ms": duration_ms,
                    "result_keys": (
                        list(result.keys()) if isinstance(result, dict) else None
                    ),
                    "success": True,
                },
            )

        def _log_failure(
            execution_id: str, duration_ms: float, error: Exception
        ) -> None:
            """Log execution failure."""
            agent._agent_logger.error(
                f"Execution failed [{execution_id}] after {duration_ms:.2f}ms: {error}",
                extra={
                    "execution_id": execution_id,
                    "agent": agent_name,
                    "duration_ms": duration_ms,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "success": False,
                },
                exc_info=True,
            )

        if is_async:

            @functools.wraps(original_run)
            async def logged_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with logging."""
                execution_id = f"{agent_name}_{int(time.time() * 1000)}"
                _log_start(execution_id, args, kwargs)

                start_time = time.monotonic()
                try:
                    result = await original_run(*args, **kwargs)
                    duration_ms = (time.monotonic() - start_time) * 1000
                    _log_success(execution_id, duration_ms, result)
                    return result
                except Exception as e:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    _log_failure(execution_id, duration_ms, e)
                    raise

            agent.run = logged_run_async
        else:

            @functools.wraps(original_run)
            def logged_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with logging."""
                execution_id = f"{agent_name}_{int(time.time() * 1000)}"
                _log_start(execution_id, args, kwargs)

                start_time = time.monotonic()
                try:
                    result = original_run(*args, **kwargs)
                    duration_ms = (time.monotonic() - start_time) * 1000
                    _log_success(execution_id, duration_ms, result)
                    return result
                except Exception as e:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    _log_failure(execution_id, duration_ms, e)
                    raise

            agent.run = logged_run_sync

    @classmethod
    def get_logger(cls, agent: "BaseAgent") -> logging.Logger:
        """
        Get the agent's logger.

        Args:
            agent: The agent instance

        Returns:
            The agent's logger instance
        """
        return getattr(agent, "_agent_logger", logger)

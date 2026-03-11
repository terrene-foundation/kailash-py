"""
Timeout Mixin for BaseAgent.

Provides operation timeout handling for agent operations including:
- Configurable timeout values
- Graceful cancellation
- Timeout event logging
- Support for asyncio.timeout (Python 3.11+) or asyncio.wait_for
"""

import asyncio
import functools
import inspect
import logging
import signal
import sys
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Default timeout in seconds
DEFAULT_TIMEOUT = 30.0


class TimeoutMixin:
    """
    Mixin that adds operation timeout handling to agents.

    Wraps operations with timeout protection:
    - Configurable timeout (default 30 seconds)
    - Graceful task cancellation
    - TimeoutError raised on expiration
    - Timeout events logged

    Example:
        config = BaseAgentConfig(timeout_enabled=True, timeout=60.0)
        agent = SimpleQAAgent(config)
        # If run() takes longer than 60 seconds, TimeoutError is raised
        result = await agent.run(question="complex question")
    """

    @classmethod
    def apply(cls, agent: "BaseAgent", timeout: float = DEFAULT_TIMEOUT) -> None:
        """
        Apply timeout behavior to agent.

        Args:
            agent: The agent instance to apply timeout to
            timeout: Timeout in seconds (default 30.0)
        """
        # Get timeout from config if available
        config_timeout = getattr(agent.config, "timeout", None)
        if config_timeout is not None:
            timeout = config_timeout

        agent._timeout = timeout

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)
        agent_name = agent.__class__.__name__

        def _log_timeout() -> None:
            """Log timeout event."""
            logger.warning(
                f"{agent_name}: Operation timed out after {timeout}s",
                extra={
                    "agent": agent_name,
                    "timeout": timeout,
                },
            )

        if is_async:

            @functools.wraps(original_run)
            async def timeout_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with timeout."""
                try:
                    # Use asyncio.timeout for Python 3.11+, otherwise wait_for
                    if sys.version_info >= (3, 11):
                        async with asyncio.timeout(timeout):
                            return await original_run(*args, **kwargs)
                    else:
                        return await asyncio.wait_for(
                            original_run(*args, **kwargs), timeout=timeout
                        )

                except asyncio.TimeoutError:
                    _log_timeout()
                    raise TimeoutError(
                        f"{agent_name} execution timed out after {timeout} seconds"
                    )

            agent.run = timeout_run_async
        else:

            @functools.wraps(original_run)
            def timeout_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with timeout using signal-based approach."""

                def _timeout_handler(signum: int, frame: Any) -> None:
                    raise TimeoutError(
                        f"{agent_name} execution timed out after {timeout} seconds"
                    )

                # Use signal-based timeout for sync functions (Unix only)
                # On Windows/non-signal systems, run without timeout protection
                try:
                    if hasattr(signal, "SIGALRM"):
                        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                        signal.setitimer(signal.ITIMER_REAL, timeout)
                        try:
                            return original_run(*args, **kwargs)
                        finally:
                            signal.setitimer(signal.ITIMER_REAL, 0)
                            signal.signal(signal.SIGALRM, old_handler)
                    else:
                        # No signal support - run without timeout
                        return original_run(*args, **kwargs)
                except TimeoutError:
                    _log_timeout()
                    raise

            agent.run = timeout_run_sync

    @classmethod
    def get_timeout(cls, agent: "BaseAgent") -> Optional[float]:
        """
        Get the agent's timeout value.

        Args:
            agent: The agent instance

        Returns:
            Timeout value in seconds or None
        """
        return getattr(agent, "_timeout", None)

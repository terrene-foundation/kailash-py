"""
Retry Mixin for BaseAgent.

Provides automatic retry with exponential backoff for agent operations including:
- Configurable retry count and delays
- Exponential backoff with jitter
- Exception filtering (only retry on specific errors)
- Retry event logging
"""

import asyncio
import functools
import inspect
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Set, Tuple, Type

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# Default exceptions that should trigger retry
DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


class RetryMixin:
    """
    Mixin that adds automatic retry with exponential backoff to agents.

    Retries failed operations with:
    - Configurable max retries (default 3)
    - Exponential backoff (default base 2 seconds)
    - Jitter to prevent thundering herd
    - Exception filtering

    Example:
        config = BaseAgentConfig(retry_enabled=True, max_retries=3)
        agent = SimpleQAAgent(config)
        # If run() fails with a retryable error, it will retry up to 3 times
        result = await agent.run(question="test")
    """

    @classmethod
    def apply(
        cls,
        agent: "BaseAgent",
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: float = 0.1,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    ) -> None:
        """
        Apply retry behavior to agent.

        Args:
            agent: The agent instance to apply retry to
            max_retries: Maximum number of retry attempts (default 3)
            base_delay: Base delay in seconds (default 1.0)
            max_delay: Maximum delay in seconds (default 60.0)
            exponential_base: Base for exponential backoff (default 2.0)
            jitter: Jitter factor as fraction of delay (default 0.1)
            retryable_exceptions: Tuple of exception types to retry on
        """
        # Get config values if available
        config_max_retries = getattr(agent.config, "max_retries", None)
        if config_max_retries is not None:
            max_retries = config_max_retries

        if retryable_exceptions is None:
            retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

        agent._retry_config = {
            "max_retries": max_retries,
            "base_delay": base_delay,
            "max_delay": max_delay,
            "exponential_base": exponential_base,
            "jitter": jitter,
            "retryable_exceptions": retryable_exceptions,
        }

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)
        agent_name = agent.__class__.__name__

        def _calculate_delay(attempt: int) -> float:
            """Calculate delay with exponential backoff and jitter."""
            delay = min(
                base_delay * (exponential_base**attempt),
                max_delay,
            )
            return delay * (1 + random.uniform(-jitter, jitter))

        def _log_retry(attempt: int, delay: float, error: Exception) -> None:
            """Log retry attempt."""
            logger.info(
                f"{agent_name}: Retry {attempt + 1}/{max_retries} "
                f"after {delay:.2f}s due to {type(error).__name__}",
                extra={
                    "agent": agent_name,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "delay": delay,
                    "error": str(error),
                },
            )

        def _log_max_retries(attempts: int, error: Exception) -> None:
            """Log max retries exceeded."""
            logger.warning(
                f"{agent_name}: Max retries ({max_retries}) exceeded",
                extra={
                    "agent": agent_name,
                    "attempts": attempts,
                    "error": str(error),
                },
            )

        if is_async:

            @functools.wraps(original_run)
            async def retry_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with retry logic."""
                last_exception: Optional[Exception] = None

                for attempt in range(max_retries + 1):
                    try:
                        return await original_run(*args, **kwargs)

                    except retryable_exceptions as e:
                        last_exception = e

                        if attempt >= max_retries:
                            _log_max_retries(attempt + 1, e)
                            raise

                        delay_with_jitter = _calculate_delay(attempt)
                        _log_retry(attempt, delay_with_jitter, e)
                        await asyncio.sleep(delay_with_jitter)

                    except Exception:
                        # Non-retryable exception, re-raise immediately
                        raise

                # Should not reach here, but just in case
                if last_exception:
                    raise last_exception
                raise RuntimeError("Retry logic error")

            agent.run = retry_run_async
        else:

            @functools.wraps(original_run)
            def retry_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with retry logic."""
                last_exception: Optional[Exception] = None

                for attempt in range(max_retries + 1):
                    try:
                        return original_run(*args, **kwargs)

                    except retryable_exceptions as e:
                        last_exception = e

                        if attempt >= max_retries:
                            _log_max_retries(attempt + 1, e)
                            raise

                        delay_with_jitter = _calculate_delay(attempt)
                        _log_retry(attempt, delay_with_jitter, e)
                        time.sleep(delay_with_jitter)

                    except Exception:
                        # Non-retryable exception, re-raise immediately
                        raise

                # Should not reach here, but just in case
                if last_exception:
                    raise last_exception
                raise RuntimeError("Retry logic error")

            agent.run = retry_run_sync

    @classmethod
    def get_retry_config(cls, agent: "BaseAgent") -> Optional[Dict[str, Any]]:
        """
        Get the agent's retry configuration.

        Args:
            agent: The agent instance

        Returns:
            Retry configuration dictionary or None
        """
        return getattr(agent, "_retry_config", None)

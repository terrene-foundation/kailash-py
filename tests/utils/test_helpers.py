"""
Test helper utilities for integration and E2E tests.
"""

import asyncio
import time
from typing import Any, Callable, Optional


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 10.0,
    poll_interval: float = 0.1,
    error_message: Optional[str] = None,
) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        error_message: Optional error message if timeout occurs

    Returns:
        True if condition was met, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if await asyncio.get_event_loop().run_in_executor(None, condition):
                return True
        except Exception:
            pass  # Condition might raise exceptions while waiting
        await asyncio.sleep(poll_interval)

    if error_message:
        print(f"Timeout waiting for condition: {error_message}")
    return False


def wait_for_condition_sync(
    condition: Callable[[], bool],
    timeout: float = 10.0,
    poll_interval: float = 0.1,
    error_message: Optional[str] = None,
) -> bool:
    """
    Synchronous version of wait_for_condition.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        error_message: Optional error message if timeout occurs

    Returns:
        True if condition was met, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if condition():
                return True
        except Exception:
            pass  # Condition might raise exceptions while waiting
        time.sleep(poll_interval)

    if error_message:
        print(f"Timeout waiting for condition: {error_message}")
    return False

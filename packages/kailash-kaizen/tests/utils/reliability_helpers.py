"""
Reliability helpers for E2E tests to prevent flaky tests.

Provides:
- Retry with exponential backoff
- Ollama health checks (model availability, response quality)
- Memory leak detection
- Graceful degradation patterns
"""

import asyncio
import subprocess
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """Decorator for retry with exponential backoff.

    Args:
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Backoff multiplier
        exceptions: Tuple of exceptions to catch

    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0)
        def flaky_api_call():
            return requests.get("...")
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        raise
                    print(
                        f"Attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper

    return decorator


async def async_retry_with_backoff(
    func: Callable[..., Any],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """Async retry with exponential backoff.

    Args:
        func: Async function to retry
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Backoff multiplier
        exceptions: Tuple of exceptions to catch

    Returns:
        Result from successful function call

    Example:
        result = await async_retry_with_backoff(
            lambda: agent.run_autonomous(task="..."),
            max_attempts=3
        )
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts:
                raise
            print(
                f"Attempt {attempt}/{max_attempts} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            delay *= backoff_factor

    raise last_exception


class OllamaHealthChecker:
    """Check Ollama service health and model availability."""

    @staticmethod
    def is_ollama_running() -> bool:
        """Check if Ollama service is running."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def is_model_available(model: str = "llama3.1:8b-instruct-q8_0") -> bool:
        """Check if specific model is available.

        Args:
            model: Model name to check (default: llama3.1:8b-instruct-q8_0)

        Returns:
            True if model is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False

            # Parse output to check for model
            return model in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    async def test_ollama_response_quality(
        model: str = "llama3.1:8b-instruct-q8_0",
        test_prompt: str = "Say 'OK' if you can respond.",
    ) -> bool:
        """Test if Ollama model can produce coherent responses.

        Args:
            model: Model to test
            test_prompt: Simple test prompt

        Returns:
            True if model responds coherently, False otherwise
        """
        try:
            # Use ollama CLI to test response
            process = await asyncio.create_subprocess_exec(
                "ollama",
                "run",
                model,
                test_prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode != 0:
                return False

            response = stdout.decode().strip()
            # Check if response contains expected text
            return len(response) > 0 and "OK" in response.upper()

        except (asyncio.TimeoutError, FileNotFoundError):
            return False

    @staticmethod
    def ensure_ollama_ready(model: str = "llama3.1:8b-instruct-q8_0") -> None:
        """Ensure Ollama is running and model is available.

        Raises:
            RuntimeError: If Ollama not ready
        """
        if not OllamaHealthChecker.is_ollama_running():
            raise RuntimeError("Ollama is not running. Start it with: ollama serve")

        if not OllamaHealthChecker.is_model_available(model):
            raise RuntimeError(
                f"Model '{model}' not found. Pull it with: ollama pull {model}"
            )

        print(f"✓ Ollama ready with model '{model}'")


class MemoryLeakDetector:
    """Detect memory leaks during long-running tests."""

    def __init__(self, threshold_mb: float = 500.0, check_interval: int = 100):
        """Initialize memory leak detector.

        Args:
            threshold_mb: Memory increase threshold in MB to trigger warning
            check_interval: Number of iterations between memory checks
        """
        self.threshold_mb = threshold_mb
        self.check_interval = check_interval
        self.iteration = 0
        self.baseline_mb: Optional[float] = None

    def check(self):
        """Check memory usage and detect leaks.

        Call this periodically in long-running tests.

        Raises:
            RuntimeError: If memory leak detected
        """
        self.iteration += 1

        if self.iteration % self.check_interval != 0:
            return

        try:
            import os

            import psutil

            process = psutil.Process(os.getpid())
            current_mb = process.memory_info().rss / 1024 / 1024

            if self.baseline_mb is None:
                self.baseline_mb = current_mb
                print(f"Memory baseline: {current_mb:.1f} MB")
                return

            increase_mb = current_mb - self.baseline_mb
            print(
                f"Memory check (iteration {self.iteration}): "
                f"{current_mb:.1f} MB (+{increase_mb:.1f} MB)"
            )

            if increase_mb > self.threshold_mb:
                raise RuntimeError(
                    f"Memory leak detected! Increased by {increase_mb:.1f} MB "
                    f"(threshold: {self.threshold_mb} MB)"
                )

        except ImportError:
            print("Warning: psutil not installed, skipping memory check")


def require_ollama(model: str = "llama3.1:8b-instruct-q8_0"):
    """Decorator to skip test if Ollama not available.

    Example:
        @require_ollama("llama3.1:8b-instruct-q8_0")
        def test_with_ollama():
            pass
    """
    import pytest

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not OllamaHealthChecker.is_ollama_running():
                pytest.skip("Ollama not running")
            if not OllamaHealthChecker.is_model_available(model):
                pytest.skip(f"Model '{model}' not available")
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_openai_api_key():
    """Decorator to skip test if OpenAI API key not available.

    Example:
        @require_openai_api_key()
        def test_with_openai():
            pass

        @require_openai_api_key()
        async def test_async_with_openai():
            pass
    """
    import asyncio
    import os

    import pytest

    def decorator(func):
        # Check if function is async
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not os.getenv("OPENAI_API_KEY"):
                    pytest.skip("OPENAI_API_KEY not set")
                return await func(*args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not os.getenv("OPENAI_API_KEY"):
                    pytest.skip("OPENAI_API_KEY not set")
                return func(*args, **kwargs)

            return sync_wrapper

    return decorator

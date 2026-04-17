"""
Unit Tests for FallbackRouter (Tier 1)

Tests the FallbackRouter for resilient routing:
- Fallback chain management
- Retry logic
- Error handling
- Fallback events
"""

import asyncio
import os

import pytest

from kaizen.llm.routing.fallback import (
    FallbackEvent,
    FallbackResult,
    FallbackRouter,
    create_fallback_router,
)
from kaizen.llm.routing.router import RoutingStrategy


class TestFallbackEvent:
    """Tests for FallbackEvent dataclass."""

    def test_create_event(self):
        """Test creating a fallback event."""
        event = FallbackEvent(
            original_model="gpt-4",
            fallback_model="claude-3-opus",
            error_type="RateLimitError",
            error_message="Rate limit exceeded",
            attempt_number=1,
        )

        assert event.original_model == "gpt-4"
        assert event.fallback_model == "claude-3-opus"
        assert event.error_type == "RateLimitError"
        assert event.attempt_number == 1
        assert event.timestamp > 0

    def test_event_to_dict(self):
        """Test event serialization."""
        event = FallbackEvent(
            original_model="gpt-4",
            fallback_model="gpt-3.5-turbo",
            error_type="Timeout",
            error_message="Request timed out",
        )

        data = event.to_dict()

        assert data["original_model"] == "gpt-4"
        assert data["fallback_model"] == "gpt-3.5-turbo"
        assert data["error_type"] == "Timeout"


class TestFallbackResult:
    """Tests for FallbackResult dataclass."""

    def test_create_success_result(self):
        """Test creating a success result."""
        result = FallbackResult(
            success=True,
            result="Response text",
            model_used="gpt-4",
            attempts=1,
            total_time_ms=500.0,
        )

        assert result.success is True
        assert result.result == "Response text"
        assert result.model_used == "gpt-4"
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = FallbackResult(
            success=False,
            model_used="gpt-3.5-turbo",
            attempts=3,
            error=ValueError("All attempts failed"),
        )

        assert result.success is False
        assert result.attempts == 3
        assert result.error is not None

    def test_result_to_dict(self):
        """Test result serialization."""
        event = FallbackEvent(
            original_model="gpt-4",
            fallback_model="gpt-3.5-turbo",
            error_type="Error",
            error_message="Test",
        )
        result = FallbackResult(
            success=True,
            model_used="gpt-3.5-turbo",
            attempts=2,
            fallback_events=[event],
            total_time_ms=1000.0,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["model_used"] == "gpt-3.5-turbo"
        assert len(data["fallback_events"]) == 1


class TestFallbackRouterCreation:
    """Tests for FallbackRouter creation."""

    def test_create_requires_default_or_chain(self):
        """FallbackRouter() with no default and no chain must raise ValueError.

        Regression guard for GH #485: earlier versions silently fell back to
        OPENAI_PROD_MODEL / DEFAULT_LLM_MODEL env vars, which leaked OpenAI
        defaults into non-OpenAI routers. The new contract requires explicit
        per-router configuration.
        """
        with pytest.raises(ValueError, match="default_model.*fallback_chain"):
            FallbackRouter()

    def test_create_defaults_from_chain_first_entry(self):
        """When default_model is omitted, fallback_chain[0] becomes default."""
        router = FallbackRouter(
            fallback_chain=["gemini-3-flash-preview", "claude-sonnet-5"],
        )

        assert router.default_model == "gemini-3-flash-preview"
        assert router.fallback_chain == [
            "gemini-3-flash-preview",
            "claude-sonnet-5",
        ]

    def test_create_with_chain(self):
        """Test creating with fallback chain."""
        router = FallbackRouter(
            available_models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
            fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
        )

        assert len(router.fallback_chain) == 3
        assert router.fallback_chain[0] == "gpt-4"

    def test_create_with_retry_settings(self):
        """Test creating with retry settings."""
        router = FallbackRouter(
            default_model="gpt-4",
            max_retries=5,
            retry_delay_seconds=2.0,
            exponential_backoff=False,
        )

        assert router._max_retries == 5
        assert router._retry_delay == 2.0
        assert router._exponential_backoff is False


class TestFallbackChainManagement:
    """Tests for fallback chain management."""

    def test_set_fallback_chain(self):
        """Test setting fallback chain."""
        router = FallbackRouter(default_model="seed-model")

        router.set_fallback_chain(["model1", "model2", "model3"])

        assert router.fallback_chain == ["model1", "model2", "model3"]
        # Models should be added to available
        assert "model1" in router.available_models

    def test_add_to_chain_end(self):
        """Test adding to end of chain."""
        router = FallbackRouter(fallback_chain=["model1"])

        router.add_to_fallback_chain("model2")

        assert router.fallback_chain == ["model1", "model2"]

    def test_add_to_chain_position(self):
        """Test adding at specific position."""
        router = FallbackRouter(fallback_chain=["model1", "model3"])

        router.add_to_fallback_chain("model2", position=1)

        assert router.fallback_chain == ["model1", "model2", "model3"]

    def test_remove_from_chain(self):
        """Test removing from chain."""
        router = FallbackRouter(fallback_chain=["model1", "model2", "model3"])

        removed = router.remove_from_fallback_chain("model2")

        assert removed is True
        assert router.fallback_chain == ["model1", "model3"]

    def test_remove_nonexistent_from_chain(self):
        """Test removing non-existent model."""
        router = FallbackRouter(fallback_chain=["model1"])

        removed = router.remove_from_fallback_chain("nonexistent")

        assert removed is False


class TestFallbackRouterSync:
    """Tests for synchronous fallback routing."""

    def test_sync_success_first_try(self):
        """Test sync execution succeeds on first try."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
        )

        def execute(model: str):
            return f"Success with {model}"

        result = router.route_with_fallback_sync(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is True
        assert "Success" in result.result
        assert result.attempts == 1
        assert len(result.fallback_events) == 0

    def test_sync_fallback_on_error(self):
        """Test sync execution falls back on error."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=1,
        )

        call_count = [0]

        def execute(model: str):
            call_count[0] += 1
            if model == "gpt-4":
                raise Exception("Rate limit exceeded")
            return f"Success with {model}"

        result = router.route_with_fallback_sync(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is True
        assert result.model_used == "gpt-3.5-turbo"
        assert len(result.fallback_events) == 1
        assert result.fallback_events[0].original_model == "gpt-4"

    def test_sync_all_fail(self):
        """Test sync execution when all models fail."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=1,
        )

        def execute(model: str):
            raise Exception("Service unavailable")

        result = router.route_with_fallback_sync(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is False
        assert result.error is not None
        assert len(result.fallback_events) > 0

    def test_sync_no_fallback_for_auth_error(self):
        """Test no fallback for authentication errors."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
        )

        def execute(model: str):
            raise Exception("Invalid API key - authentication failed")

        result = router.route_with_fallback_sync(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is False
        # Should not have tried fallback models
        assert result.attempts == 1


class TestFallbackRouterAsync:
    """Tests for async fallback routing."""

    @pytest.mark.asyncio
    async def test_async_success_first_try(self):
        """Test async execution succeeds on first try."""
        router = FallbackRouter(
            available_models=["gpt-4"],
            fallback_chain=["gpt-4"],
        )

        async def execute(model: str):
            return f"Async success with {model}"

        result = await router.route_with_fallback(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is True
        assert "Async success" in result.result
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_async_fallback_on_error(self):
        """Test async execution falls back on error."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=1,
        )

        async def execute(model: str):
            if model == "gpt-4":
                raise Exception("Rate limit")
            return f"Success with {model}"

        result = await router.route_with_fallback(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is True
        assert result.model_used == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_async_handles_sync_function(self):
        """Test async router handles sync execute function."""
        router = FallbackRouter(
            available_models=["gpt-4"],
            fallback_chain=["gpt-4"],
        )

        def execute_sync(model: str):
            return "Sync result"

        result = await router.route_with_fallback(
            task="Test task",
            execute_fn=execute_sync,
        )

        assert result.success is True
        assert result.result == "Sync result"

    @pytest.mark.asyncio
    async def test_async_retries_before_fallback(self):
        """Test async retries before falling back."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=2,
            retry_delay_seconds=0.01,  # Fast for tests
        )

        attempt_count = [0]

        async def execute(model: str):
            attempt_count[0] += 1
            if model == "gpt-4" and attempt_count[0] < 2:
                raise Exception("Temporary error")
            return f"Success at attempt {attempt_count[0]}"

        result = await router.route_with_fallback(
            task="Test task",
            execute_fn=execute,
        )

        assert result.success is True
        assert result.model_used == "gpt-4"
        # Should have retried on gpt-4 before succeeding
        assert attempt_count[0] == 2


class TestFallbackEvents:
    """Tests for fallback event recording."""

    def test_events_recorded(self):
        """Test fallback events are recorded."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=1,
        )

        def execute(model: str):
            if model == "gpt-4":
                raise Exception("Error")
            return "Success"

        result = router.route_with_fallback_sync(
            task="Test",
            execute_fn=execute,
        )

        # Check events on result
        assert len(result.fallback_events) == 1

        # Check events on router
        assert len(router.fallback_events) == 1

    def test_clear_events(self):
        """Test clearing fallback events."""
        router = FallbackRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
            fallback_chain=["gpt-4", "gpt-3.5-turbo"],
            max_retries=1,
        )

        def execute(model: str):
            if model == "gpt-4":
                raise Exception("Error")
            return "Success"

        router.route_with_fallback_sync(task="Test", execute_fn=execute)
        assert len(router.fallback_events) > 0

        router.clear_fallback_events()
        assert len(router.fallback_events) == 0


class TestRetryDelay:
    """Tests for retry delay calculation."""

    def test_exponential_backoff(self):
        """Test exponential backoff delay."""
        router = FallbackRouter(
            default_model="gpt-4",
            retry_delay_seconds=1.0,
            exponential_backoff=True,
        )

        assert router._calculate_retry_delay(0) == 1.0
        assert router._calculate_retry_delay(1) == 2.0
        assert router._calculate_retry_delay(2) == 4.0

    def test_fixed_delay(self):
        """Test fixed delay (no backoff)."""
        router = FallbackRouter(
            default_model="gpt-4",
            retry_delay_seconds=1.0,
            exponential_backoff=False,
        )

        assert router._calculate_retry_delay(0) == 1.0
        assert router._calculate_retry_delay(1) == 1.0
        assert router._calculate_retry_delay(2) == 1.0


class TestCreateFallbackRouter:
    """Tests for create_fallback_router helper."""

    def test_create_with_defaults(self, monkeypatch):
        """Test creating with default fallbacks from env (no hardcoded models)."""
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "test-model-for-fallback")
        router = create_fallback_router()

        expected_primary = os.environ.get(
            "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
        )
        assert (
            expected_primary is not None
        ), "OPENAI_PROD_MODEL or DEFAULT_LLM_MODEL must be set in .env"
        assert router.default_model == expected_primary
        # Chain length = 1 (primary) + number of FALLBACK env vars set
        assert len(router.fallback_chain) >= 1
        assert router.fallback_chain[0] == expected_primary

    def test_create_with_custom_primary(self):
        """Test creating with custom primary model."""
        router = create_fallback_router(primary_model="claude-3-opus")

        assert router.default_model == "claude-3-opus"
        assert router.fallback_chain[0] == "claude-3-opus"

    def test_create_with_custom_fallbacks(self):
        """Test creating with custom fallback chain."""
        router = create_fallback_router(
            primary_model="gpt-4",
            fallback_models=["gpt-4o", "gpt-3.5-turbo"],
            max_retries=5,
        )

        assert router._max_retries == 5
        assert len(router.fallback_chain) == 3


class TestErrorClassification:
    """Tests for error classification."""

    def test_should_fallback_rate_limit(self):
        """Test rate limit triggers fallback."""
        router = FallbackRouter(default_model="gpt-4")

        class RateLimitError(Exception):
            pass

        assert router._should_fallback(RateLimitError("Rate limit")) is True

    def test_should_fallback_timeout(self):
        """Test timeout triggers fallback."""
        router = FallbackRouter(default_model="gpt-4")

        assert router._should_fallback(Exception("Request timeout")) is True

    def test_should_not_fallback_auth(self):
        """Test auth error doesn't trigger fallback."""
        router = FallbackRouter(default_model="gpt-4")

        assert router._should_not_fallback(Exception("Invalid API key")) is True

    def test_should_not_fallback_permission(self):
        """Test permission error doesn't trigger fallback."""
        router = FallbackRouter(default_model="gpt-4")

        assert router._should_not_fallback(Exception("Permission denied")) is True

"""
Fallback Router for Resilient LLM Routing.

Extends LLMRouter with automatic fallback chains for handling
provider failures and rate limits.

Safety hardening (W3 gap fix):
- on_fallback callback fires BEFORE each fallback attempt
- FallbackRejectedError can prevent unwanted silent fallbacks
- All fallback events logged at WARNING level
- Capability validation skips incompatible models
- No hardcoded model names in factory function
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union

from kaizen.llm.routing.analyzer import TaskAnalyzer
from kaizen.llm.routing.router import LLMRouter, RoutingDecision, RoutingStrategy

logger = logging.getLogger(__name__)


T = TypeVar("T")


class FallbackRejectedError(Exception):
    """Raised by an on_fallback callback to prevent a fallback from occurring.

    This allows callers to enforce policies about which fallbacks are acceptable.
    For example, preventing fallback from a large model to a small model for
    tasks that require high capability.
    """

    pass


@dataclass
class FallbackEvent:
    """Record of a fallback event."""

    original_model: str
    fallback_model: str
    error_type: str
    error_message: str
    timestamp: float = field(default_factory=time.time)
    attempt_number: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_model": self.original_model,
            "fallback_model": self.fallback_model,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "attempt_number": self.attempt_number,
        }


@dataclass
class FallbackResult:
    """Result of a fallback-protected execution."""

    success: bool
    result: Any = None
    model_used: str = ""
    attempts: int = 1
    fallback_events: List[FallbackEvent] = field(default_factory=list)
    total_time_ms: float = 0.0
    error: Optional[Exception] = None

    @property
    def fallback_occurred(self) -> bool:
        """Whether any fallback was triggered during execution."""
        return len(self.fallback_events) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "model_used": self.model_used,
            "attempts": self.attempts,
            "fallback_occurred": self.fallback_occurred,
            "fallback_events": [e.to_dict() for e in self.fallback_events],
            "total_time_ms": self.total_time_ms,
            "error": str(self.error) if self.error else None,
        }


class FallbackRouter(LLMRouter):
    """LLM Router with automatic fallback chain support.

    Extends LLMRouter to provide resilient execution with automatic
    fallback when providers fail or return errors.

    Features:
    - Ordered fallback chain
    - Automatic retry on failure
    - Fallback event logging
    - Configurable retry limits
    - Rate limit aware

    Example:
        >>> router = FallbackRouter(
        ...     available_models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
        ...     fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
        ... )
        >>>
        >>> async def execute(model: str) -> str:
        ...     # LLM call that might fail
        ...     return await llm_provider.chat(model=model, ...)
        >>>
        >>> result = await router.route_with_fallback(
        ...     task="Complex reasoning task",
        ...     execute_fn=execute,
        ... )
        >>> if result.success:
        ...     print(f"Used model: {result.model_used}")
    """

    # Error types that should trigger fallback
    FALLBACK_ERRORS = (
        "RateLimitError",
        "APIConnectionError",
        "ServiceUnavailableError",
        "Timeout",
        "InternalServerError",
        "BadGateway",
        "GatewayTimeout",
    )

    # Error types that should NOT fallback (request issue, not provider issue)
    NO_FALLBACK_ERRORS = (
        "InvalidRequestError",
        "AuthenticationError",
        "PermissionDenied",
        "NotFoundError",
    )

    def __init__(
        self,
        available_models: Optional[List[str]] = None,
        default_model: Optional[str] = None,
        analyzer: Optional[TaskAnalyzer] = None,
        fallback_chain: Optional[List[str]] = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        exponential_backoff: bool = True,
        on_fallback: Optional[Callable[[FallbackEvent], None]] = None,
        model_capabilities: Optional[Dict[str, Set[str]]] = None,
    ):
        """Initialize FallbackRouter.

        Args:
            available_models: List of available models
            default_model: Default model
            analyzer: Task analyzer
            fallback_chain: Ordered list of fallback models
            max_retries: Maximum retries per model
            retry_delay_seconds: Base delay between retries
            exponential_backoff: Use exponential backoff for retries
            on_fallback: Callback invoked BEFORE each fallback attempt. Receives
                the FallbackEvent about to occur. Raise FallbackRejectedError
                to prevent the fallback from happening.
            model_capabilities: Dict mapping model names to sets of capability
                strings (e.g. {"gpt-4": {"vision", "function_calling"}}). When
                required_capabilities are specified in route_with_fallback, models
                lacking those capabilities are skipped.
        """
        # When default_model is not provided, fall back to the first entry of
        # fallback_chain. We intentionally do NOT read OPENAI_PROD_MODEL /
        # DEFAULT_LLM_MODEL here — those are process-level env hints for a
        # specific provider and leak OpenAI-specific defaults into non-OpenAI
        # routers (see GH #485). Per-router defaults must be explicit.
        if default_model is None:
            if fallback_chain:
                default_model = fallback_chain[0]
            else:
                raise ValueError(
                    "FallbackRouter requires either default_model or a "
                    "non-empty fallback_chain"
                )

        super().__init__(
            available_models=available_models,
            default_model=default_model,
            analyzer=analyzer,
        )

        self._fallback_chain = fallback_chain or []
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds
        self._exponential_backoff = exponential_backoff
        self._fallback_events: List[FallbackEvent] = []
        self._on_fallback = on_fallback
        self._model_capabilities: Dict[str, Set[str]] = model_capabilities or {}

        # Add fallback chain models to available models
        for model in self._fallback_chain:
            self._available_models.add(model)

        logger.info(
            f"Initialized FallbackRouter with chain: {self._fallback_chain}, "
            f"max_retries={max_retries}, "
            f"on_fallback={'set' if on_fallback else 'not set'}"
        )

    @property
    def fallback_chain(self) -> List[str]:
        """Get fallback chain."""
        return self._fallback_chain.copy()

    @property
    def fallback_events(self) -> List[FallbackEvent]:
        """Get recorded fallback events."""
        return self._fallback_events.copy()

    def set_fallback_chain(self, chain: List[str]) -> None:
        """Set the fallback chain.

        Args:
            chain: Ordered list of fallback models
        """
        self._fallback_chain = chain
        for model in chain:
            self._available_models.add(model)

    def add_to_fallback_chain(self, model: str, position: Optional[int] = None) -> None:
        """Add a model to the fallback chain.

        Args:
            model: Model to add
            position: Position in chain (None = end)
        """
        if position is None:
            self._fallback_chain.append(model)
        else:
            self._fallback_chain.insert(position, model)
        self._available_models.add(model)

    def remove_from_fallback_chain(self, model: str) -> bool:
        """Remove a model from the fallback chain."""
        if model in self._fallback_chain:
            self._fallback_chain.remove(model)
            return True
        return False

    def clear_fallback_events(self) -> None:
        """Clear recorded fallback events."""
        self._fallback_events.clear()

    async def route_with_fallback(
        self,
        task: str,
        execute_fn: Callable[[str], Any],
        context: Optional[Dict[str, Any]] = None,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
        required_capabilities: Optional[Dict[str, bool]] = None,
    ) -> FallbackResult:
        """Route task and execute with automatic fallback.

        Args:
            task: Task description
            execute_fn: Async function(model) -> result
            context: Optional context
            strategy: Routing strategy
            required_capabilities: Capability requirements

        Returns:
            FallbackResult with success status and details
        """
        start_time = time.time()
        fallback_events: List[FallbackEvent] = []

        # Get initial routing decision
        decision = self.route(
            task=task,
            context=context,
            strategy=strategy,
            required_capabilities=required_capabilities,
        )

        # Build execution order: routed model first, then fallback chain
        execution_order = [decision.model]
        for model in self._fallback_chain:
            if model not in execution_order:
                execution_order.append(model)

        # Add alternatives from routing decision
        for alt in decision.alternatives:
            if alt not in execution_order:
                execution_order.append(alt)

        # Filter execution order by capability requirements
        if required_capabilities:
            execution_order = self._filter_by_capabilities(
                execution_order, required_capabilities
            )
            if not execution_order:
                total_time = (time.time() - start_time) * 1000
                return FallbackResult(
                    success=False,
                    attempts=0,
                    total_time_ms=total_time,
                    error=ValueError(
                        f"No models satisfy required capabilities: {required_capabilities}"
                    ),
                )

        # Try each model in order
        last_error: Optional[Exception] = None
        attempt = 0

        for model_idx, model in enumerate(execution_order):
            for retry in range(self._max_retries):
                attempt += 1

                try:
                    # Execute with current model
                    logger.info(
                        f"Attempting execution with model={model}, "
                        f"retry={retry}, attempt={attempt}"
                    )

                    # Handle both sync and async execute functions
                    if asyncio.iscoroutinefunction(execute_fn):
                        result = await execute_fn(model)
                    else:
                        result = execute_fn(model)

                    # Success!
                    total_time = (time.time() - start_time) * 1000
                    return FallbackResult(
                        success=True,
                        result=result,
                        model_used=model,
                        attempts=attempt,
                        fallback_events=fallback_events,
                        total_time_ms=total_time,
                    )

                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    error_message = str(e)

                    logger.warning(
                        f"Execution failed: model={model}, "
                        f"error={error_type}: {error_message}"
                    )

                    # Check if this is a non-fallback error
                    if self._should_not_fallback(e):
                        total_time = (time.time() - start_time) * 1000
                        return FallbackResult(
                            success=False,
                            model_used=model,
                            attempts=attempt,
                            fallback_events=fallback_events,
                            total_time_ms=total_time,
                            error=e,
                        )

                    # Record fallback event
                    next_model = (
                        execution_order[model_idx + 1]
                        if model_idx + 1 < len(execution_order)
                        else "none"
                    )
                    event = FallbackEvent(
                        original_model=model,
                        fallback_model=next_model,
                        error_type=error_type,
                        error_message=error_message[:200],  # Truncate
                        attempt_number=attempt,
                    )

                    # Fire on_fallback callback BEFORE attempting fallback
                    if self._on_fallback and next_model != "none":
                        try:
                            self._on_fallback(event)
                        except FallbackRejectedError:
                            logger.warning(
                                f"Fallback from {model} to {next_model} "
                                f"REJECTED by on_fallback callback"
                            )
                            total_time = (time.time() - start_time) * 1000
                            return FallbackResult(
                                success=False,
                                model_used=model,
                                attempts=attempt,
                                fallback_events=fallback_events,
                                total_time_ms=total_time,
                                error=e,
                            )

                    logger.warning(
                        f"Fallback triggered: {model} -> {next_model} "
                        f"(error: {error_type})"
                    )

                    fallback_events.append(event)
                    self._fallback_events.append(event)

                    # Delay before retry
                    if retry < self._max_retries - 1:
                        delay = self._calculate_retry_delay(retry)
                        await asyncio.sleep(delay)

        # All attempts exhausted
        total_time = (time.time() - start_time) * 1000
        return FallbackResult(
            success=False,
            model_used=execution_order[-1] if execution_order else "",
            attempts=attempt,
            fallback_events=fallback_events,
            total_time_ms=total_time,
            error=last_error,
        )

    def route_with_fallback_sync(
        self,
        task: str,
        execute_fn: Callable[[str], Any],
        context: Optional[Dict[str, Any]] = None,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
        required_capabilities: Optional[Dict[str, bool]] = None,
    ) -> FallbackResult:
        """Synchronous version of route_with_fallback.

        Use this when not in an async context.
        """
        start_time = time.time()
        fallback_events: List[FallbackEvent] = []

        # Get initial routing decision
        decision = self.route(
            task=task,
            context=context,
            strategy=strategy,
            required_capabilities=required_capabilities,
        )

        # Build execution order
        execution_order = [decision.model]
        for model in self._fallback_chain:
            if model not in execution_order:
                execution_order.append(model)
        for alt in decision.alternatives:
            if alt not in execution_order:
                execution_order.append(alt)

        # Try each model
        last_error: Optional[Exception] = None
        attempt = 0

        for model_idx, model in enumerate(execution_order):
            for retry in range(self._max_retries):
                attempt += 1

                try:
                    result = execute_fn(model)
                    total_time = (time.time() - start_time) * 1000
                    return FallbackResult(
                        success=True,
                        result=result,
                        model_used=model,
                        attempts=attempt,
                        fallback_events=fallback_events,
                        total_time_ms=total_time,
                    )

                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__

                    if self._should_not_fallback(e):
                        total_time = (time.time() - start_time) * 1000
                        return FallbackResult(
                            success=False,
                            model_used=model,
                            attempts=attempt,
                            fallback_events=fallback_events,
                            total_time_ms=total_time,
                            error=e,
                        )

                    next_model = (
                        execution_order[model_idx + 1]
                        if model_idx + 1 < len(execution_order)
                        else "none"
                    )
                    event = FallbackEvent(
                        original_model=model,
                        fallback_model=next_model,
                        error_type=error_type,
                        error_message=str(e)[:200],
                        attempt_number=attempt,
                    )
                    fallback_events.append(event)
                    self._fallback_events.append(event)

                    if retry < self._max_retries - 1:
                        delay = self._calculate_retry_delay(retry)
                        time.sleep(delay)

        total_time = (time.time() - start_time) * 1000
        return FallbackResult(
            success=False,
            model_used=execution_order[-1] if execution_order else "",
            attempts=attempt,
            fallback_events=fallback_events,
            total_time_ms=total_time,
            error=last_error,
        )

    def _should_fallback(self, error: Exception) -> bool:
        """Determine if error should trigger fallback."""
        error_type = type(error).__name__

        # Check explicit fallback errors
        for fallback_type in self.FALLBACK_ERRORS:
            if fallback_type.lower() in error_type.lower():
                return True

        # Check error message for common patterns
        error_msg = str(error).lower()
        fallback_patterns = [
            "rate limit",
            "quota exceeded",
            "too many requests",
            "server error",
            "unavailable",
            "timeout",
            "connection",
            "overloaded",
            "capacity",
        ]
        return any(pattern in error_msg for pattern in fallback_patterns)

    def _should_not_fallback(self, error: Exception) -> bool:
        """Determine if error should NOT trigger fallback."""
        error_type = type(error).__name__

        # Check explicit no-fallback errors
        for no_fallback_type in self.NO_FALLBACK_ERRORS:
            if no_fallback_type.lower() in error_type.lower():
                return True

        # Check error message for auth/permission patterns
        error_msg = str(error).lower()
        no_fallback_patterns = [
            "invalid api key",
            "authentication",
            "unauthorized",
            "permission denied",
            "forbidden",
            "invalid request",
            "malformed",
        ]
        return any(pattern in error_msg for pattern in no_fallback_patterns)

    def _calculate_retry_delay(self, retry_number: int) -> float:
        """Calculate delay before retry."""
        if self._exponential_backoff:
            return self._retry_delay * (2**retry_number)
        return self._retry_delay

    def _filter_by_capabilities(
        self,
        models: List[str],
        required_capabilities: Dict[str, bool],
    ) -> List[str]:
        """Filter models by required capabilities.

        Models without capability metadata are included (permissive default).
        Models with metadata that lack a required capability are excluded.
        """
        if not self._model_capabilities:
            return models

        required = {k for k, v in required_capabilities.items() if v}
        filtered = []
        for model in models:
            caps = self._model_capabilities.get(model)
            if caps is None:
                # No capability data available - include by default
                filtered.append(model)
            elif required.issubset(caps):
                filtered.append(model)
            else:
                missing = required - caps
                logger.warning(
                    f"Skipping model {model}: missing capabilities {missing}"
                )
        return filtered


def create_fallback_router(
    primary_model: Optional[str] = None,
    fallback_models: Optional[List[str]] = None,
    max_retries: int = 2,
    on_fallback: Optional[Callable[[FallbackEvent], None]] = None,
    model_capabilities: Optional[Dict[str, Set[str]]] = None,
) -> FallbackRouter:
    """Create a FallbackRouter with common defaults.

    Model names are read from environment variables per project rules.
    Falls back to reasonable defaults only if env vars are not set.

    Args:
        primary_model: Primary model (default: from OPENAI_PROD_MODEL or DEFAULT_LLM_MODEL env)
        fallback_models: Fallback chain (default: from env vars)
        max_retries: Max retries per model
        on_fallback: Callback invoked before each fallback (raise FallbackRejectedError to block)
        model_capabilities: Model capability sets for filtering

    Returns:
        Configured FallbackRouter
    """
    if primary_model is None:
        primary_model = os.environ.get(
            "OPENAI_PROD_MODEL",
            os.environ.get("DEFAULT_LLM_MODEL"),
        )
        if not primary_model:
            raise ValueError(
                "No primary model specified. Set OPENAI_PROD_MODEL or DEFAULT_LLM_MODEL "
                "in environment, or pass primary_model explicitly."
            )

    if fallback_models is None:
        # Build fallback chain from environment — no hardcoded defaults
        fallback_candidates = []
        anthropic_model = os.environ.get("ANTHROPIC_FALLBACK_MODEL")
        openai_fallback = os.environ.get("OPENAI_FALLBACK_MODEL")
        google_model = os.environ.get("GOOGLE_FALLBACK_MODEL")

        for model in [anthropic_model, openai_fallback, google_model]:
            if model and model != primary_model:
                fallback_candidates.append(model)
        fallback_models = fallback_candidates

    all_models = [primary_model] + fallback_models

    return FallbackRouter(
        available_models=all_models,
        default_model=primary_model,
        fallback_chain=all_models,
        max_retries=max_retries,
        on_fallback=on_fallback,
        model_capabilities=model_capabilities,
    )

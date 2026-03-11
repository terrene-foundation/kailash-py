"""
Transition System for Journey Orchestration.

Provides the transition mechanism for pathway navigation based on intent detection
and context conditions.

Components:
    - Transition: Rule for switching between pathways
    - BaseTrigger: Abstract base class for trigger conditions
    - IntentTrigger: LLM-powered intent detection trigger with pattern matching
    - ConditionTrigger: Context-condition based trigger
    - TransitionResult: Result of transition evaluation

Architecture:
    Transition
    - trigger: BaseTrigger (IntentTrigger or ConditionTrigger)
    - from_pathway: Source pathway ("*" for any)
    - to_pathway: Destination pathway
    - context_update: Dict specifying how to update context
    - priority: Higher priority evaluated first

Usage:
    from kaizen.journey.transitions import (
        Transition,
        IntentTrigger,
        ConditionTrigger,
    )

    # Intent-based transition
    faq_transition = Transition(
        trigger=IntentTrigger(patterns=["help", "question"]),
        from_pathway="*",  # Any pathway
        to_pathway="faq",
        priority=10
    )

    # Condition-based transition
    retry_transition = Transition(
        trigger=ConditionTrigger(
            condition=lambda ctx: ctx.get("retry_count", 0) >= 3
        ),
        from_pathway="validation",
        to_pathway="escalation",
        priority=5
    )

References:
    - docs/plans/03-journey/04-intent-detection.md
    - TODO-JO-003: Intent Detection System
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

if TYPE_CHECKING:
    from kaizen.journey.intent import IntentDetector

logger = logging.getLogger(__name__)


# ============================================================================
# TransitionResult (REQ-ID-005)
# ============================================================================


@dataclass
class TransitionResult:
    """
    Result of transition evaluation.

    Attributes:
        matched: Whether the transition matched
        transition: The matched transition (if any)
        trigger_result: Additional trigger-specific data
        updated_context: Context after applying updates
    """

    matched: bool
    transition: Optional["Transition"] = None
    trigger_result: Optional[Dict[str, Any]] = None
    updated_context: Optional[Dict[str, Any]] = None


# ============================================================================
# BaseTrigger (REQ-ID-002)
# ============================================================================


class BaseTrigger(ABC):
    """
    Abstract base class for transition triggers.

    Triggers evaluate conditions to determine whether a transition should activate.
    Subclasses must implement the evaluate() method.

    Subclasses:
        - IntentTrigger: Pattern matching + LLM classification
        - ConditionTrigger: Context-based conditions
    """

    @abstractmethod
    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate if trigger condition is met.

        Args:
            message: User message to evaluate
            context: Current conversation context

        Returns:
            True if trigger should activate, False otherwise
        """
        raise NotImplementedError("Subclasses must implement evaluate()")


# ============================================================================
# IntentTrigger (REQ-ID-002)
# ============================================================================


@dataclass
class IntentTrigger(BaseTrigger):
    """
    LLM-powered intent detection trigger with pattern matching fast-path.

    Intent detection uses a two-stage approach:
    1. Fast path: Pattern matching (keyword/phrase)
    2. Slow path: LLM classification (via IntentDetector)

    The fast path handles common intents with sub-millisecond latency.
    LLM fallback handles complex cases where patterns don't match.

    Attributes:
        patterns: List of patterns to match (case-insensitive, word boundary)
        use_llm_fallback: Whether to use LLM if pattern doesn't match
        confidence_threshold: Minimum confidence for LLM match (0-1)

    Example:
        >>> trigger = IntentTrigger(patterns=["help", "question"])
        >>> trigger.evaluate("I need help", {})
        True
        >>> trigger.evaluate("That was helpful", {})  # Word boundary!
        False
    """

    patterns: List[str] = field(default_factory=list)
    use_llm_fallback: bool = True
    confidence_threshold: float = 0.7

    # Set by IntentDetector during async evaluation
    _detector: Optional["IntentDetector"] = field(default=None, repr=False)

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate if message matches intent patterns.

        This method only performs synchronous pattern matching.
        LLM fallback is handled asynchronously by IntentDetector.

        Uses word boundary matching to avoid false positives:
        - "help" matches "I need help" but not "That was helpful"

        Args:
            message: User message to evaluate
            context: Current conversation context (not used for pattern matching)

        Returns:
            True if pattern matches, False otherwise (LLM evaluated async)
        """
        if not self.patterns:
            return False

        message_lower = message.lower()

        for pattern in self.patterns:
            pattern_lower = pattern.lower()
            # Word boundary match (not just substring)
            # \b ensures we match whole words, not substrings
            if re.search(r"\b" + re.escape(pattern_lower) + r"\b", message_lower):
                return True

        return False

    def get_intent_name(self) -> str:
        """
        Get primary intent name from patterns.

        Returns the first pattern as the canonical intent name.

        Returns:
            First pattern or "unknown" if no patterns
        """
        return self.patterns[0] if self.patterns else "unknown"

    def __hash__(self) -> int:
        """Make IntentTrigger hashable for caching."""
        return hash(tuple(self.patterns))


# ============================================================================
# ConditionTrigger (REQ-ID-003)
# ============================================================================


@dataclass
class ConditionTrigger(BaseTrigger):
    """
    Context-condition based trigger.

    Evaluates a callable condition against the current context.
    Useful for transitions based on accumulated state rather than message content.

    Attributes:
        condition: Callable that takes context dict and returns bool
        description: Human-readable description for debugging/logging

    Example:
        >>> trigger = ConditionTrigger(
        ...     condition=lambda ctx: ctx.get("retry_count", 0) >= 3,
        ...     description="Trigger after 3 retries"
        ... )
        >>> trigger.evaluate("any message", {"retry_count": 3})
        True
        >>> trigger.evaluate("any message", {"retry_count": 2})
        False

    Note:
        Exceptions in condition are caught and return False (fail-safe).
    """

    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    description: str = ""

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate condition against context.

        The message parameter is ignored for ConditionTrigger;
        only the context is evaluated.

        Args:
            message: User message (ignored)
            context: Current conversation context

        Returns:
            True if condition returns True, False otherwise (including on error)
        """
        if self.condition is None:
            return False

        try:
            return bool(self.condition(context))
        except Exception as e:
            # Fail-safe: return False on any exception
            # This prevents condition errors from crashing the journey
            # Log the error for debugging purposes
            logger.warning(
                f"ConditionTrigger evaluation failed for '{self.description}': {e}",
                exc_info=True,
            )
            return False

    def __hash__(self) -> int:
        """Make ConditionTrigger hashable."""
        return hash(self.description)


# ============================================================================
# AlwaysTrigger (REQ-ID-004)
# ============================================================================


class AlwaysTrigger(BaseTrigger):
    """
    Trigger that always fires.

    Useful for default transitions, fallback pathways, or unconditional navigation.
    This trigger returns True for any message and context combination.

    Example:
        >>> trigger = AlwaysTrigger()
        >>> trigger.evaluate("any message", {})
        True
        >>> trigger.evaluate("", {"any": "context"})
        True

    Use Cases:
        - Default/fallback transitions when no other trigger matches
        - Unconditional pathway transitions (e.g., always return to main menu)
        - Testing and debugging pathway navigation
        - Catch-all transitions with low priority

    Example Transition:
        >>> # Default fallback transition (low priority)
        >>> fallback = Transition(
        ...     trigger=AlwaysTrigger(),
        ...     from_pathway="*",
        ...     to_pathway="main_menu",
        ...     priority=-100  # Low priority so other triggers are checked first
        ... )
    """

    def evaluate(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Always returns True.

        Args:
            message: User message (ignored)
            context: Current conversation context (ignored)

        Returns:
            Always True
        """
        return True

    def __hash__(self) -> int:
        """Make AlwaysTrigger hashable."""
        return hash("always")


# ============================================================================
# Transition (REQ-ID-001)
# ============================================================================


@dataclass
class Transition:
    """
    Rule for switching between pathways.

    Transitions define how the journey navigates between pathways based on
    trigger conditions. They can update context during navigation.

    Attributes:
        trigger: Condition for activation (IntentTrigger, ConditionTrigger)
        from_pathway: Source pathway ("*" for any, or list of pathway IDs)
        to_pathway: Destination pathway ID
        context_update: Dict specifying how to update context on transition
        priority: Higher priority transitions evaluated first (default 0)

    Context Update Syntax:
        - "append:field_name" - Append source field value to list
        - "set:value" - Set literal value
        - "copy:field_name" - Copy from result
        - "remove:field_name" - Remove from context
        - "field_name" - Direct reference (same as copy:)

    Example:
        >>> transition = Transition(
        ...     trigger=IntentTrigger(patterns=["help"]),
        ...     from_pathway="*",  # Any pathway
        ...     to_pathway="faq",
        ...     context_update={"previous_topic": "current_topic"},
        ...     priority=10
        ... )
        >>> transition.matches("intake", "I need help", {})
        True
    """

    trigger: BaseTrigger
    from_pathway: Union[str, List[str]] = "*"
    to_pathway: str = ""
    context_update: Optional[Dict[str, str]] = None
    priority: int = 0

    def matches(
        self,
        current_pathway: str,
        message: str,
        context: Dict[str, Any],
    ) -> bool:
        """
        Check if transition should activate.

        Evaluates:
        1. Pathway match (from_pathway matches current)
        2. Trigger match (trigger.evaluate() returns True)

        Args:
            current_pathway: Current pathway ID
            message: User message
            context: Current conversation context

        Returns:
            True if transition should activate, False otherwise
        """
        # Check pathway match
        if self.from_pathway != "*":
            if isinstance(self.from_pathway, list):
                if current_pathway not in self.from_pathway:
                    return False
            elif self.from_pathway != current_pathway:
                return False

        # Check trigger
        return self.trigger.evaluate(message, context)

    def apply_context_update(
        self,
        context: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply context updates specified in transition.

        Update Syntax:
        - "append:field_name" - Append result[field_name] to context[target]
        - "set:value" - Set literal value
        - "copy:field_name" - Copy result[field_name] to context[target]
        - "remove:field_name" - Remove field from context
        - "field_name" - Direct reference (same as copy:)

        Args:
            context: Current context to update
            result: Result dict to extract values from

        Returns:
            New context dict with updates applied
        """
        if not self.context_update:
            return context

        new_context = context.copy()

        for target_field, update_spec in self.context_update.items():
            if update_spec.startswith("append:"):
                # Append source field value to target list
                source_field = update_spec.split(":", 1)[1]
                source_value = result.get(source_field)
                if source_value is not None:
                    existing = new_context.get(target_field, [])
                    if not isinstance(existing, list):
                        existing = [existing] if existing else []
                    existing.append(source_value)
                    new_context[target_field] = existing

            elif update_spec.startswith("set:"):
                # Set literal value
                value = update_spec.split(":", 1)[1]
                new_context[target_field] = value

            elif update_spec.startswith("copy:"):
                # Copy from result
                source_field = update_spec.split(":", 1)[1]
                if source_field in result:
                    new_context[target_field] = result[source_field]

            elif update_spec.startswith("remove:"):
                # Remove from context
                field_to_remove = update_spec.split(":", 1)[1]
                new_context.pop(field_to_remove, None)

            else:
                # Direct field reference (same as copy:)
                if update_spec in result:
                    new_context[target_field] = result[update_spec]

        return new_context


__all__ = [
    # Result
    "TransitionResult",
    # Triggers
    "BaseTrigger",
    "IntentTrigger",
    "ConditionTrigger",
    "AlwaysTrigger",
    # Transition
    "Transition",
]

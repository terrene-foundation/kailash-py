# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Knowledge Clearance Enforcement -- classification-aware context filtering.

Bridges PACT's knowledge clearance system with the kaizen-agents orchestration
layer. Each context value carries a DataClassification (C0-C4); agents can only
see values at or below their effective clearance level.

Key properties:
- Monotonic floor: classifications can only be raised, never lowered
- Deterministic pre-filter for known patterns (API keys, PII regex) before
  any LLM classification call
- Integration with ScopedContext for invisible filtering
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DataClassification",
    "ClearanceEnforcer",
    "ClassificationAssigner",
    "ClassifiedValue",
]


class DataClassification(IntEnum):
    """Data classification levels C0 through C4.

    Numeric ordering enables direct comparison: C0 < C1 < C2 < C3 < C4.
    """

    C0_PUBLIC = 0
    C1_INTERNAL = 1
    C2_CONFIDENTIAL = 2
    C3_SECRET = 3
    C4_TOP_SECRET = 4


@dataclass(frozen=True)
class ClassifiedValue:
    """A context value with its data classification.

    Attributes:
        key: The context key name.
        value: The actual value.
        classification: The data classification level.
    """

    key: str
    value: Any
    classification: DataClassification


class ClearanceEnforcer:
    """Filters context values based on agent clearance level.

    Thread-safe. Agents can only see values at or below their clearance.

    Usage:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("api_key", "sk-...", DataClassification.C3_SECRET))
        visible = enforcer.filter_for_clearance(DataClassification.C1_INTERNAL)
        # visible == {} (C1 < C3, so api_key is invisible)
    """

    def __init__(self, max_values: int = 100_000) -> None:
        self._lock = threading.Lock()
        self._max_values = max_values
        self._values: dict[str, ClassifiedValue] = {}

    def register_value(self, cv: ClassifiedValue) -> None:
        """Register or update a classified value.

        If the key already exists, enforces monotonic floor: the new
        classification must be >= the existing classification.

        Args:
            cv: The classified value to register.

        Raises:
            ValueError: If attempting to lower the classification (monotonic floor).
        """
        with self._lock:
            existing = self._values.get(cv.key)
            if existing is not None and cv.classification < existing.classification:
                raise ValueError(
                    f"Monotonic floor violation: cannot lower classification of '{cv.key}' "
                    f"from {existing.classification.name} to {cv.classification.name}"
                )
            # R1-03: Bounded value tracking for new keys only
            if len(self._values) >= self._max_values and cv.key not in self._values:
                raise ValueError(
                    f"Classified value limit ({self._max_values}) reached. "
                    f"Cannot register key '{cv.key}'."
                )
            self._values[cv.key] = cv

    def filter_for_clearance(self, clearance: DataClassification) -> dict[str, Any]:
        """Return only values at or below the given clearance level.

        Args:
            clearance: The agent's effective clearance level.

        Returns:
            Dict mapping key → value for all visible values.
        """
        with self._lock:
            return {
                cv.key: cv.value for cv in self._values.values() if cv.classification <= clearance
            }

    def get_classification(self, key: str) -> DataClassification | None:
        """Get the classification of a specific key.

        Args:
            key: The context key to look up.

        Returns:
            The DataClassification, or None if key not registered.
        """
        with self._lock:
            cv = self._values.get(key)
            return cv.classification if cv is not None else None

    def is_visible(self, key: str, clearance: DataClassification) -> bool:
        """Check if a specific key is visible at the given clearance.

        Args:
            key: The context key.
            clearance: The agent's clearance level.

        Returns:
            True if the value is visible (classification <= clearance).
        """
        with self._lock:
            cv = self._values.get(key)
            if cv is None:
                return False
            return cv.classification <= clearance

    @property
    def value_count(self) -> int:
        """Number of registered classified values."""
        with self._lock:
            return len(self._values)


# ---------------------------------------------------------------------------
# Pre-filter patterns for deterministic classification
# ---------------------------------------------------------------------------

# Patterns that indicate sensitive data without needing LLM classification
_PREFILTER_PATTERNS: list[tuple[str, re.Pattern[str], DataClassification]] = [
    # API keys
    ("api_key_openai", re.compile(r"sk-[a-zA-Z0-9]{20,}"), DataClassification.C3_SECRET),
    (
        "api_key_anthropic",
        re.compile(r"sk-ant-[a-zA-Z0-9-]{20,}", re.IGNORECASE),
        DataClassification.C3_SECRET,
    ),
    (
        "api_key_generic",
        re.compile(
            r"(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{20,}", re.IGNORECASE
        ),
        DataClassification.C3_SECRET,
    ),
    # AWS keys
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}"), DataClassification.C3_SECRET),
    (
        "aws_secret",
        re.compile(r"(?:aws_secret|AWS_SECRET)[_A-Z]*\s*[:=]\s*['\"]?[a-zA-Z0-9/+=]{30,}"),
        DataClassification.C4_TOP_SECRET,
    ),
    # Email addresses (PII)
    (
        "email",
        re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        DataClassification.C2_CONFIDENTIAL,
    ),
    # SSN patterns
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), DataClassification.C4_TOP_SECRET),
    # Credit card patterns (basic Luhn-candidate)
    ("credit_card", re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"), DataClassification.C3_SECRET),
    # Phone numbers (US format)
    (
        "phone",
        re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        DataClassification.C2_CONFIDENTIAL,
    ),
    # Private key material
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
        DataClassification.C4_TOP_SECRET,
    ),
]


def _extract_string_leaves(value: Any, max_depth: int = 10, _depth: int = 0) -> list[str]:
    """Recursively extract all string leaves from nested dicts/lists.

    R1-04: Bounded recursion to prevent stack overflow on deeply nested
    or maliciously crafted input structures.

    Args:
        value: The value to extract leaves from.
        max_depth: Maximum recursion depth.
        _depth: Current recursion depth (internal).

    Returns:
        List of string representations of all leaf values.
    """
    if _depth > max_depth:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        leaves: list[str] = []
        for v in value.values():
            leaves.extend(_extract_string_leaves(v, max_depth, _depth + 1))
        return leaves
    if isinstance(value, (list, tuple)):
        leaves = []
        for item in value:
            leaves.extend(_extract_string_leaves(item, max_depth, _depth + 1))
        return leaves
    return [str(value)]


class ClassificationAssigner:
    """Assigns data classification levels using deterministic pre-filter.

    The pre-filter catches known sensitive patterns (API keys, PII, etc.)
    without needing an LLM call. For values that don't match any pre-filter
    pattern, falls back to a configurable default classification.

    Usage:
        assigner = ClassificationAssigner()
        level = assigner.classify("my_key", "sk-abc123def456ghi789jkl")
        # level == DataClassification.C3_SECRET (matched api_key_openai)
    """

    def __init__(
        self,
        default_classification: DataClassification = DataClassification.C1_INTERNAL,
    ) -> None:
        self._default = default_classification

    def classify(self, key: str, value: Any) -> DataClassification:
        """Classify a value using deterministic pre-filter.

        R1-04: Recursively extracts all string leaves from nested dicts/lists
        and runs pre-filter patterns against each leaf, so that sensitive data
        buried inside nested structures is detected.

        Args:
            key: The context key (used for key-name heuristics).
            value: The value to classify.

        Returns:
            The assigned DataClassification.
        """
        str_key = str(key).lower()

        highest = self._default

        # Check key name heuristics first
        key_sensitive = any(
            s in str_key
            for s in ("password", "secret", "token", "api_key", "private_key", "credential")
        )
        if key_sensitive:
            highest = max(highest, DataClassification.C3_SECRET)

        # R1-04: Collect all string leaves from value (recursive, bounded)
        leaves = _extract_string_leaves(value, max_depth=10)
        for leaf in leaves:
            for _, pattern, level in _PREFILTER_PATTERNS:
                if pattern.search(leaf):
                    highest = max(highest, level)

        return highest

    def classify_and_wrap(self, key: str, value: Any) -> ClassifiedValue:
        """Classify a value and wrap it in a ClassifiedValue.

        Args:
            key: The context key.
            value: The value to classify and wrap.

        Returns:
            A ClassifiedValue with the assigned classification.
        """
        classification = self.classify(key, value)
        return ClassifiedValue(key=key, value=value, classification=classification)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Classification policy — decorator, runtime lookup, and policy object.

Thread-safe: classification metadata is written at class-decoration time
(single-threaded import) and read-only at runtime.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

from dataflow.classification.types import (
    DataClassification,
    MaskingStrategy,
    RetentionPolicy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FieldClassification",
    "ClassificationPolicy",
    "classify",
    "get_field_classification",
]

T = TypeVar("T")

# Type alias for a classification entry stored on the class.
_ClassEntry = Tuple[str, DataClassification, RetentionPolicy, MaskingStrategy]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldClassification:
    """Classification metadata for a single model field.

    Attributes:
        classification: Sensitivity level.
        retention: Retention policy.
        masking: Masking strategy for display / export.
    """

    classification: DataClassification
    retention: RetentionPolicy
    masking: MaskingStrategy

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "classification": self.classification.value,
            "retention": self.retention.value,
            "masking": self.masking.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FieldClassification:
        """Deserialize from dictionary."""
        return cls(
            classification=DataClassification(data["classification"]),
            retention=RetentionPolicy(data["retention"]),
            masking=MaskingStrategy(data["masking"]),
        )


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def classify(
    field_name: str,
    classification: DataClassification,
    retention: RetentionPolicy = RetentionPolicy.INDEFINITE,
    masking: MaskingStrategy = MaskingStrategy.NONE,
) -> Callable[[Type[T]], Type[T]]:
    """Class decorator that attaches classification metadata to a field.

    Multiple ``@classify`` decorators can be stacked on a single class.
    Metadata is stored in a ``__field_classifications__`` class
    attribute (list of tuples).

    Args:
        field_name: Model field to classify.
        classification: Sensitivity level.
        retention: Retention policy (default: INDEFINITE).
        masking: Masking strategy (default: NONE).

    Returns:
        A class decorator.
    """

    def _decorator(cls: Type[T]) -> Type[T]:
        existing: List[_ClassEntry] = list(
            getattr(cls, "__field_classifications__", [])
        )
        existing.append((field_name, classification, retention, masking))
        cls.__field_classifications__ = existing  # type: ignore[attr-defined]
        return cls

    return _decorator


# ---------------------------------------------------------------------------
# Runtime lookup
# ---------------------------------------------------------------------------


def get_field_classification(
    model: Type[Any],
    field_name: str,
) -> Optional[FieldClassification]:
    """Look up the classification for a specific field on a model class.

    Args:
        model: The DataFlowModel class (not an instance).
        field_name: Name of the field.

    Returns:
        ``FieldClassification`` if the field is classified, else ``None``.
    """
    entries: List[_ClassEntry] = getattr(model, "__field_classifications__", [])
    for name, cls_level, ret, mask in entries:
        if name == field_name:
            return FieldClassification(
                classification=cls_level,
                retention=ret,
                masking=mask,
            )
    return None


# ---------------------------------------------------------------------------
# ClassificationPolicy — implements DataClassificationPolicy protocol
# ---------------------------------------------------------------------------


class ClassificationPolicy:
    """Maps model fields to classification metadata.

    Can be used standalone or passed to ``DataFlowEngine.builder()``
    via ``.classification_policy(policy)`` to satisfy the
    ``DataClassificationPolicy`` protocol defined in ``engine.py``.

    Thread-safe: all mutations are protected by a lock.

    Usage::

        policy = ClassificationPolicy()
        policy.register_model(User)          # reads @classify metadata
        policy.set_field("User", "ssn", DataClassification.HIGHLY_CONFIDENTIAL)

        level = policy.classify("User", "email")   # -> "pii"
        days = policy.get_retention_days("pii")     # -> None (indefinite)
    """

    # Default retention days per classification level.
    _DEFAULT_RETENTION: Dict[str, Optional[int]] = {
        DataClassification.PUBLIC.value: None,
        DataClassification.INTERNAL.value: None,
        DataClassification.SENSITIVE.value: 365,
        DataClassification.PII.value: None,
        DataClassification.GDPR.value: None,
        DataClassification.HIGHLY_CONFIDENTIAL.value: 2555,  # ~7 years
    }

    # Retention enum -> concrete days.
    _RETENTION_DAYS: Dict[str, Optional[int]] = {
        RetentionPolicy.INDEFINITE.value: None,
        RetentionPolicy.DAYS_30.value: 30,
        RetentionPolicy.DAYS_90.value: 90,
        RetentionPolicy.YEARS_1.value: 365,
        RetentionPolicy.YEARS_7.value: 2555,
        RetentionPolicy.UNTIL_CONSENT_REVOKED.value: None,
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {model_name: {field_name: FieldClassification}}
        self._registry: Dict[str, Dict[str, FieldClassification]] = {}

    # -- Protocol-compatible methods (DataClassificationPolicy) -------------

    def classify(self, model_name: str, field_name: str) -> str:
        """Return the classification level string for a field.

        Returns ``"public"`` for unclassified fields.
        """
        with self._lock:
            model_fields = self._registry.get(model_name, {})
            fc = model_fields.get(field_name)
            if fc is not None:
                return fc.classification.value
            return DataClassification.PUBLIC.value

    def get_retention_days(self, classification: str) -> Optional[int]:
        """Return retention period in days, or ``None`` for indefinite."""
        return self._DEFAULT_RETENTION.get(classification)

    # -- Extended API -------------------------------------------------------

    def register_model(self, model: Type[Any]) -> None:
        """Read ``@classify`` metadata from a model class and register it.

        Args:
            model: A DataFlowModel subclass decorated with ``@classify``.
        """
        model_name = model.__name__
        entries: List[_ClassEntry] = getattr(
            model, "__field_classifications__", []
        )
        with self._lock:
            if model_name not in self._registry:
                self._registry[model_name] = {}
            for name, cls_level, ret, mask in entries:
                self._registry[model_name][name] = FieldClassification(
                    classification=cls_level,
                    retention=ret,
                    masking=mask,
                )

    def set_field(
        self,
        model_name: str,
        field_name: str,
        classification: DataClassification,
        retention: RetentionPolicy = RetentionPolicy.INDEFINITE,
        masking: MaskingStrategy = MaskingStrategy.NONE,
    ) -> None:
        """Programmatically set a field's classification.

        Args:
            model_name: Name of the model class.
            field_name: Name of the field.
            classification: Sensitivity level.
            retention: Retention policy.
            masking: Masking strategy.
        """
        with self._lock:
            if model_name not in self._registry:
                self._registry[model_name] = {}
            self._registry[model_name][field_name] = FieldClassification(
                classification=classification,
                retention=retention,
                masking=masking,
            )

    def get_field(
        self,
        model_name: str,
        field_name: str,
    ) -> Optional[FieldClassification]:
        """Get full classification metadata for a field.

        Returns:
            ``FieldClassification`` or ``None`` if unclassified.
        """
        with self._lock:
            return self._registry.get(model_name, {}).get(field_name)

    def get_model_fields(
        self,
        model_name: str,
    ) -> Dict[str, FieldClassification]:
        """Get all classified fields for a model.

        Returns:
            Dict mapping field names to their classifications. Empty
            dict if the model has no classifications.
        """
        with self._lock:
            return dict(self._registry.get(model_name, {}))

    def retention_days_for_policy(
        self,
        policy: RetentionPolicy,
    ) -> Optional[int]:
        """Convert a ``RetentionPolicy`` enum to concrete days.

        Returns:
            Number of days, or ``None`` for indefinite / consent-based.
        """
        return self._RETENTION_DAYS.get(policy.value)

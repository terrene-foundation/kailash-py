"""
Provenance — Field-level source tracking for DataFlow models.

Provides a generic Provenance[T] wrapper that carries metadata about where
a field value came from, how confident we are in it, and its change history.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Generic, TypeVar, Any, Optional
import math

T = TypeVar("T")


class SourceType(str, Enum):
    """Classification of where a field value originated."""

    EXCEL_CELL = "excel_cell"
    API_QUERY = "api_query"
    CALCULATED = "calculated"
    AGENT_DERIVED = "agent_derived"
    MANUAL = "manual"
    DATABASE = "database"
    FILE = "file"


@dataclass
class ProvenanceMetadata:
    """Metadata describing the origin and confidence of a field value.

    Attributes:
        source_type: Where this value came from (e.g. API, spreadsheet, agent).
        source_detail: Human-readable description of the specific source.
        confidence: How reliable this value is, from 0.0 (unknown) to 1.0 (certain).
        previous_value: The value this field held before the current one. Set by the
            system on updates — callers may also set it explicitly.
        change_reason: Why the value was changed (free-text).
        extracted_at: When the value was captured. Defaults to now (UTC).
    """

    source_type: SourceType
    source_detail: str = ""
    confidence: float = 1.0
    previous_value: Any = None
    change_reason: str = ""
    extracted_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, SourceType):
            self.source_type = SourceType(self.source_type)
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be a finite number between 0.0 and 1.0, got {self.confidence}"
            )
        if self.extracted_at is None:
            self.extracted_at = datetime.now(UTC)

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON storage."""
        return {
            "source_type": self.source_type.value,
            "source_detail": self.source_detail,
            "confidence": self.confidence,
            "previous_value": self.previous_value,
            "change_reason": self.change_reason,
            "extracted_at": (
                self.extracted_at.isoformat() if self.extracted_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProvenanceMetadata":
        """Reconstruct from a dict produced by ``to_dict``."""
        data = dict(data)  # shallow copy so we don't mutate the caller's dict
        if "extracted_at" in data and isinstance(data["extracted_at"], str):
            data["extracted_at"] = datetime.fromisoformat(data["extracted_at"])
        return cls(**data)


@dataclass
class Provenance(Generic[T]):
    """A field value paired with its provenance metadata.

    Generic over the value type so that ``Provenance[float]``,
    ``Provenance[str]``, ``Provenance[int]``, etc. all carry full type
    information.
    """

    value: T
    metadata: ProvenanceMetadata

    def to_dict(self) -> dict:
        """Serialize to a flat dict with ``value`` plus all metadata keys."""
        return {"value": self.value, **self.metadata.to_dict()}

    @classmethod
    def from_dict(cls, data: dict, value_type: type = None) -> "Provenance":
        """Reconstruct from a dict produced by ``to_dict``.

        Args:
            data: Flat dict containing ``value`` and metadata fields.
            value_type: Optional type to coerce the value to (unused today,
                reserved for future schema-aware deserialization).
        """
        data = dict(data)  # shallow copy
        value = data.pop("value", None)
        metadata = ProvenanceMetadata.from_dict(data)
        return cls(value=value, metadata=metadata)

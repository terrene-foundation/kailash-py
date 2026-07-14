from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""GovernanceManifest — declares an agent's governance posture and constraints.

Maps to the ``[governance]`` section in agent TOML manifests and aligns
with the EATP trust posture model.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.manifest._coerce import coerce_list_field

logger = logging.getLogger(__name__)

__all__ = ["GovernanceManifest"]

_VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
_VALID_POSTURES = frozenset(
    {"pseudo_agent", "supervised", "shared_planning", "continuous_insight", "delegated"}
)


@dataclass
class GovernanceManifest:
    """Governance metadata for an agent or application manifest.

    Attributes:
        purpose: Human-readable description of why this agent exists.
        risk_level: One of low, medium, high, critical.
        data_access_needed: List of data categories the agent requires.
        suggested_posture: EATP trust posture (pseudo_agent through delegated).
        max_budget_microdollars: Optional spending cap in microdollars.
    """

    purpose: str = ""
    risk_level: str = "medium"
    data_access_needed: List[str] = field(default_factory=list)
    suggested_posture: str = "supervised"
    max_budget_microdollars: Optional[int] = None

    def __post_init__(self) -> None:
        if self.risk_level not in _VALID_RISK_LEVELS:
            raise ValueError(
                f"risk_level must be one of {sorted(_VALID_RISK_LEVELS)}, "
                f"got {self.risk_level!r}"
            )
        if self.suggested_posture not in _VALID_POSTURES:
            raise ValueError(
                f"suggested_posture must be one of {sorted(_VALID_POSTURES)}, "
                f"got {self.suggested_posture!r}"
            )
        if (
            self.max_budget_microdollars is not None
            and self.max_budget_microdollars < 0
        ):
            raise ValueError(
                f"max_budget_microdollars must be non-negative, "
                f"got {self.max_budget_microdollars}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        result: Dict[str, Any] = {
            "purpose": self.purpose,
            "risk_level": self.risk_level,
            "data_access_needed": list(self.data_access_needed),
            "suggested_posture": self.suggested_posture,
        }
        if self.max_budget_microdollars is not None:
            result["max_budget_microdollars"] = self.max_budget_microdollars
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GovernanceManifest:
        """Deserialize from a plain dict."""
        return cls(
            purpose=data.get("purpose", ""),
            risk_level=data.get("risk_level", "medium"),
            data_access_needed=coerce_list_field(
                data.get("data_access_needed", []), "data_access_needed"
            ),
            suggested_posture=data.get("suggested_posture", "supervised"),
            max_budget_microdollars=data.get("max_budget_microdollars"),
        )

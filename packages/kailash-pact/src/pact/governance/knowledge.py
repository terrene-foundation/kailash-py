# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Knowledge item classification -- the target object in access decisions.

A KnowledgeItem represents a piece of organizational knowledge with a
classification level, owning unit, and optional compartment restrictions.
Access decisions are made by comparing a role's clearance against the
item's classification and compartments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pact.build.config.schema import ConfidentialityLevel

logger = logging.getLogger(__name__)

__all__ = ["KnowledgeItem"]


@dataclass(frozen=True)
class KnowledgeItem:
    """A classified knowledge item in the organizational structure.

    Attributes:
        item_id: Unique identifier for this knowledge item.
        classification: Confidentiality level (PUBLIC through TOP_SECRET).
        owning_unit_address: The D or T prefix that owns this data.
            This determines containment -- roles within or above this
            unit have structural access (subject to clearance checks).
        compartments: Named compartments this item belongs to.
            For SECRET and TOP_SECRET items, accessing roles must hold
            ALL compartments the item belongs to.
        description: Human-readable description of the knowledge item.
    """

    item_id: str
    classification: ConfidentialityLevel
    owning_unit_address: str  # D or T prefix that owns this data
    compartments: frozenset[str] = field(default_factory=frozenset)
    description: str = ""

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Reasoning Traces — structured decision transparency.

Captures WHY a decision was made during trust delegation and audit operations:

- :class:`ReasoningTrace` — Structured trace with decision, rationale, evidence,
  and confidentiality classification.
- :class:`ConfidentialityLevel` — Enterprise classification
  (PUBLIC through TOP_SECRET) with ordering support.
- :class:`EvidenceReference` — Typed evidence pointer for reasoning traces.
"""

from __future__ import annotations

from kailash.trust.reasoning.traces import (
    ConfidentialityLevel,
    EvidenceReference,
    ReasoningTrace,
    reasoning_completeness_score,
)

__all__ = [
    "ConfidentialityLevel",
    "ReasoningTrace",
    "EvidenceReference",
    "reasoning_completeness_score",
]

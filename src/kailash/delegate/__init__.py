# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash.delegate -- Apache 2.0 OSS Delegate composition primitive.

The audit-grade composition surface ``(Connector x Signature x ConstraintEnvelope
x Executor)`` under EATP audit per Terrene Delegate Specification v0.

DISAMBIGUATION: NOT ``kaizen_agents.delegate.Delegate`` (LLM execution facade).
The kaizen-agents Delegate is one possible ``executor=`` argument here.

Cross-implementation conformance: shares vendored conformance vectors with the
proprietary kailash-rs implementation; ``receipts_agree(rs, py)`` is the
cross-language verification gate.

Per #1035: this package MUST have zero proprietary dependencies. The
``tools/lint-delegate-fences.py`` lint enforces this fence.
"""

# Public surface populated by subsequent shards (S2..S8).
__all__: list[str] = []

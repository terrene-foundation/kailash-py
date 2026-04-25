# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT N4/N5 cross-SDK conformance vector runner.

This module implements the Python side of the PACT N6 cross-implementation
conformance contract. The same JSON vectors (under
``crates/kailash-pact/tests/conformance/vectors/`` in the kailash-rs tree)
MUST be loadable by both SDKs and produce byte-for-byte identical canonical
JSON for every vector input.

Two contracts:

- **N4** -- ``TieredAuditEvent`` canonicalisation. Each vector pins the
  expected ``DurabilityTier`` derived from the caller's
  ``TrustPostureLevel`` (snake_case Rust names like ``pseudo_agent``,
  ``shared_planning``, ``delegated``) and the canonical JSON the SDK MUST
  emit when given the verdict + posture.

- **N5** -- ``Evidence`` canonicalisation. Each vector pins the canonical
  JSON the SDK MUST emit when constructing an evidence record from a verdict
  via ``Evidence.from_verdict(verdict, source)``.

The runner -- :mod:`pact.conformance.runner` -- drives both contracts by
loading every ``*.json`` vector through :mod:`pact.conformance.vectors`,
reconstructing the domain objects, and asserting byte-equality against
``expected.canonical_json``.

Cross-SDK contract reference:
``kailash-rs/crates/kailash-pact/tests/conformance/vectors/`` and
``kailash-rs/crates/kailash-pact/tests/conformance_vectors.rs``.
"""

from __future__ import annotations

from pact.conformance.runner import (
    ConformanceRunner,
    RunnerReport,
    VectorOutcome,
    VectorStatus,
    run_vectors,
)
from pact.conformance.vectors import (
    ConformanceVector,
    ConformanceVectorError,
    ConformanceVectorExpected,
    ConformanceVectorInput,
    ConformanceVectorVerdict,
    DurabilityTier,
    Evidence,
    GradientZone,
    PactPostureLevel,
    TieredAuditEvent,
    canonical_json_dumps,
    durability_tier_from_posture,
    load_vectors_from_dir,
    parse_vector,
)

__all__ = [
    # Vector schema + canonical types
    "ConformanceVector",
    "ConformanceVectorError",
    "ConformanceVectorExpected",
    "ConformanceVectorInput",
    "ConformanceVectorVerdict",
    "DurabilityTier",
    "Evidence",
    "GradientZone",
    "PactPostureLevel",
    "TieredAuditEvent",
    "canonical_json_dumps",
    "durability_tier_from_posture",
    "load_vectors_from_dir",
    "parse_vector",
    # Runner
    "ConformanceRunner",
    "RunnerReport",
    "VectorOutcome",
    "VectorStatus",
    "run_vectors",
]

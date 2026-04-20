# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Diagnostics protocols for Kailash — cross-SDK contract surface.

This package defines the Terrene Foundation's cross-SDK contract for
runtime diagnostics: a `Diagnostic` Protocol, a `TraceEvent` schema for
agent/tool/LLM observability, and a `JudgeCallable` Protocol for
LLM-as-judge scoring.

Design principles (see `workspaces/issue-567-mlfp-diagnostics/02-plans/`):

1. Protocol-only — zero runtime logic lives here. Concrete adapters
   (`kailash_ml.diagnostics.DLDiagnostics`, `kaizen.interpretability`,
   `kailash_align.diagnostics`, ...) implement these protocols in their
   own framework packages.
2. Zero optional deps — no numpy, no polars, no plotly. The core SDK
   stays slim. Adapters pull their own runtime deps behind extras.
3. Cross-SDK definitive — the JSON Schema at `schemas/trace-event.v1.json`
   at the repo root is the single source of truth. Rust SDK (kailash-rs)
   reads the same file; semantics MUST match byte-for-byte per EATP D6.
4. Stable on day 1 — instability in the contract defeats cross-SDK
   parity. Adapters may evolve at sub-package minor-bump cadence, but
   these protocols ship stable on first merge.

Related: kailash-py#567, esperie/kailash-rs#449 (audit-chain fingerprint
reconciliation), kailash-rs BP-052 (AgentDiagnostics + TraceEvent parity).
"""

from __future__ import annotations

from kailash.diagnostics.protocols import (
    Diagnostic,
    JudgeCallable,
    JudgeInput,
    JudgeResult,
    JudgeWinner,
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)

__all__ = [
    "Diagnostic",
    "JudgeCallable",
    "JudgeInput",
    "JudgeResult",
    "JudgeWinner",
    "TraceEvent",
    "TraceEventType",
    "TraceEventStatus",
    "compute_trace_event_fingerprint",
]

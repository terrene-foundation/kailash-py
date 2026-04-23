# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared ``CostDelta`` wire format — integer microdollars, cross-SDK-locked.

Per ``specs/kaizen-ml-integration.md`` §4 (Shared CostTracker Wire Format),
every cost-propagation surface in the Kailash ecosystem MUST serialize
cost deltas as integer microdollars (``1 USD = 1_000_000 microdollars``).
This module defines the single canonical ``CostDelta`` shape used by:

    * ``kaizen.cost.tracker`` (Kaizen agent cost accumulation)
    * ``kailash_pact.costs`` (PACT governance cost guardrails)
    * ``kailash_ml.engines.automl_engine`` (``GuardrailConfig.max_llm_cost_usd``)

A ``CostDelta`` serialized by ANY of the three producers MUST deserialize
byte-identically on the other two. Round-trip parity is enforced by the
Tier 2 wiring test at
``tests/integration/ml/test_cost_tracker_cross_sdk_parity_wiring.py``.

The microdollar unit replaces Kaizen 2.11.x's ``cents`` wire format —
``cents`` truncates any charge below ``$0.01`` to zero, which silently
drops sub-cent embedding and log-probability API charges
(OpenAI text-embedding-ada-002 = ``$0.0001 / 1k tokens`` resolves to
100 microdollars; the same value in cents truncates to ``0``).

Security note: per ``rules/security.md`` § Financial-Field Precision,
``from_usd`` rejects non-finite or negative inputs before any integer
coercion — NaN / Inf USD → ``ValueError`` rather than silent coercion
to a Python ``int`` (which would raise a cryptic ``OverflowError`` later
in the accumulator).

Cross-SDK contract: the JSON shape MUST match kailash-rs v3.17.1+
``crates/kailash-kaizen/src/cost/delta.rs::CostDelta::to_json``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

__all__ = ["CostDelta", "CostDeltaError"]


# Integer microdollars per USD — BLOCKED to change without a cross-SDK
# coordination pass. ``kaizen.cost.tracker`` defines ``_MICRODOLLARS_PER_USD``
# at the same value; they MUST stay in lock-step.
_MICRODOLLARS_PER_USD: int = 1_000_000


class CostDeltaError(ValueError):
    """Raised on invalid ``CostDelta`` construction.

    Inherits :class:`ValueError` so existing ``except ValueError`` call
    sites (including the sanitizer path at
    ``packages/kailash-dataflow/src/dataflow/core/nodes.py``) continue to
    catch it without code change.
    """


@dataclass(frozen=True)
class CostDelta:
    """Single cost-accumulation event — cross-SDK wire-format record.

    Frozen because downstream sinks may compute a SHA-256 fingerprint
    for audit correlation (matching the ``TraceEvent`` discipline at
    ``kailash.diagnostics.protocols.compute_trace_event_fingerprint``);
    mutation after fingerprint would invalidate the audit anchor.

    Args:
        microdollars: Integer microdollars for this delta. MUST be
            ``>= 0``. Negative deltas are BLOCKED — refunds / corrections
            are a separate accounting surface and would mask accumulator
            drift if absorbed here.
        provider: LLM provider identifier (``"openai"`` / ``"anthropic"``
            / ``"google"`` / ``"ollama"`` / ...). Free-form string —
            cardinality control is the caller's responsibility per
            ``rules/tenant-isolation.md`` §4.
        model: Model identifier within the provider.
        prompt_tokens: Prompt-side token count.
        completion_tokens: Completion-side token count.
        at: UTC timestamp. MUST carry ``tzinfo`` — naive timestamps are
            BLOCKED so ``.isoformat()`` produces an explicit offset
            suffix (``+00:00``) matching the cross-SDK fingerprint rule
            at ``kailash.diagnostics.protocols.compute_trace_event_fingerprint``.
        tenant_id: Optional tenant scope (``rules/tenant-isolation.md``).
        actor_id: Optional agent / actor id (PACT D/T/R envelope).
    """

    microdollars: int
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    at: datetime
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None

    def __post_init__(self) -> None:
        # Frozen dataclass — use object.__setattr__ only for validation
        # errors raised BEFORE the instance escapes.
        if not isinstance(self.microdollars, int) or isinstance(
            self.microdollars, bool
        ):
            raise CostDeltaError(
                f"microdollars must be int, got {type(self.microdollars).__name__}"
            )
        if self.microdollars < 0:
            raise CostDeltaError(
                f"microdollars must be >= 0 (negative deltas not supported); "
                f"got {self.microdollars}"
            )
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise CostDeltaError(
                "prompt_tokens and completion_tokens must be >= 0 "
                f"(got prompt={self.prompt_tokens}, completion={self.completion_tokens})"
            )
        if self.at.tzinfo is None:
            raise CostDeltaError(
                "CostDelta.at must be a tz-aware datetime "
                "(naive timestamps produce ambiguous fingerprints cross-SDK)"
            )

    # ── Constructors ────────────────────────────────────────────────

    @classmethod
    def from_usd(
        cls,
        usd: float,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        at: datetime,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> "CostDelta":
        """Construct from a float USD value, rounding to integer microdollars.

        Raises :class:`CostDeltaError` on non-finite or negative USD —
        ``rules/security.md`` § Financial-Field Precision requires
        ``math.isfinite`` on every budget field before coercion.
        """
        if not math.isfinite(usd):
            raise CostDeltaError(f"usd must be finite (NaN / Inf blocked), got {usd!r}")
        if usd < 0:
            raise CostDeltaError(
                f"usd must be >= 0 (negative charges not supported), got {usd!r}"
            )
        microdollars = int(round(usd * _MICRODOLLARS_PER_USD))
        return cls(
            microdollars=microdollars,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            at=at,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    # ── Serialization (cross-SDK wire format) ───────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the cross-SDK canonical dict shape.

        Key order is intentionally alphabetic to match the canonical
        form produced by ``json.dumps(..., sort_keys=True)`` in the
        ``kailash.diagnostics.protocols.compute_trace_event_fingerprint``
        path — any future fingerprint helper on ``CostDelta`` will
        produce byte-identical digests with the Rust counterpart.
        """
        return {
            "actor_id": self.actor_id,
            "at": self.at.isoformat(),
            "completion_tokens": self.completion_tokens,
            "microdollars": self.microdollars,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "provider": self.provider,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostDelta":
        """Deserialize from the cross-SDK canonical dict shape."""
        try:
            at_raw = data["at"]
            at_parsed = (
                at_raw
                if isinstance(at_raw, datetime)
                else datetime.fromisoformat(at_raw)
            )
            return cls(
                microdollars=int(data["microdollars"]),
                provider=str(data["provider"]),
                model=str(data["model"]),
                prompt_tokens=int(data["prompt_tokens"]),
                completion_tokens=int(data["completion_tokens"]),
                at=at_parsed,
                tenant_id=data.get("tenant_id"),
                actor_id=data.get("actor_id"),
            )
        except KeyError as e:
            raise CostDeltaError(
                f"CostDelta.from_dict: missing required field {e.args[0]!r}"
            ) from e

    # ── Convenience accessors ──────────────────────────────────────

    @property
    def usd(self) -> float:
        """Return the equivalent USD value (float). Lossy for sub-microdollar values."""
        return self.microdollars / _MICRODOLLARS_PER_USD

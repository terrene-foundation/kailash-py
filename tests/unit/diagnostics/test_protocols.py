# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for kailash.diagnostics.protocols — the cross-SDK contract.

These tests pin every contract clause documented in ``protocols.py`` and
``schemas/trace-event.v1.json``. Any regression here means the contract
has drifted and the kailash-rs parity PR (BP-052) will silently break on
the same inputs.

Scope:
  - Mandatory-field enforcement on ``TraceEvent``.
  - Frozen-dataclass invariants (no post-emission mutation).
  - ``to_dict`` / ``from_dict`` round-trip preserves every field and
    the canonical fingerprint.
  - ``compute_trace_event_fingerprint`` is deterministic and matches
    the schema-canonicalization contract byte-for-byte.
  - Schema validation: Python-emitted ``TraceEvent.to_dict()`` passes
    the language-neutral schema at ``schemas/trace-event.v1.json``.
  - Protocol conformance: ``isinstance`` runtime check on
    ``Diagnostic`` and ``JudgeCallable``.
  - ``JudgeInput`` / ``JudgeResult`` validation (winner enum, integer
    token/cost fields).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from kailash.diagnostics import (
    Diagnostic,
    JudgeCallable,
    JudgeInput,
    JudgeResult,
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "trace-event.v1.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    with SCHEMA_PATH.open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


# ---------------------------------------------------------------------------
# TraceEvent — mandatory field enforcement
# ---------------------------------------------------------------------------


class TestTraceEventMandatoryFields:
    def test_minimal_valid_event(self) -> None:
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        assert evt.event_id == "evt-1"
        assert evt.event_type is TraceEventType.AGENT_RUN_START

    def test_naive_timestamp_rejected(self) -> None:
        """Naive datetimes break cross-SDK fingerprint parity (no offset in
        output) and MUST be rejected at construction time."""
        with pytest.raises(ValueError, match="timezone-aware"):
            TraceEvent(
                event_id="evt-1",
                event_type=TraceEventType.AGENT_RUN_START,
                timestamp=datetime(2026, 4, 20, 12, 0, 0),  # naive
                run_id="run-1",
                agent_id="agent-1",
                cost_microdollars=0,
            )

    def test_non_integer_cost_rejected(self) -> None:
        """Floats would drift between emitters over accumulation. Only int
        microdollars are allowed."""
        with pytest.raises(TypeError, match="must be an int"):
            TraceEvent(  # type: ignore[arg-type]
                event_id="evt-1",
                event_type=TraceEventType.AGENT_RUN_START,
                timestamp=datetime.now(UTC),
                run_id="run-1",
                agent_id="agent-1",
                cost_microdollars=1.5,
            )

    def test_bool_cost_rejected(self) -> None:
        """``bool`` is a subclass of ``int`` in Python; must be explicitly
        rejected so ``True`` doesn't silently land as 1 microdollar."""
        with pytest.raises(TypeError, match="must be an int"):
            TraceEvent(  # type: ignore[arg-type]
                event_id="evt-1",
                event_type=TraceEventType.AGENT_RUN_START,
                timestamp=datetime.now(UTC),
                run_id="run-1",
                agent_id="agent-1",
                cost_microdollars=True,
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            TraceEvent(
                event_id="evt-1",
                event_type=TraceEventType.AGENT_RUN_START,
                timestamp=datetime.now(UTC),
                run_id="run-1",
                agent_id="agent-1",
                cost_microdollars=-1,
            )


class TestTraceEventFrozen:
    def test_frozen_blocks_mutation(self) -> None:
        """Frozen dataclasses prevent post-emission mutation, which would
        invalidate any fingerprint already computed by a downstream
        consumer."""
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime.now(UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            evt.event_id = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TraceEvent — to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestTraceEventRoundTrip:
    def _full_event(self) -> TraceEvent:
        return TraceEvent(
            event_id="evt-full",
            event_type=TraceEventType.LLM_CALL_END,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-xyz",
            agent_id="D1-R1-D2-R2",
            cost_microdollars=1500,
            parent_event_id="evt-parent",
            trace_id="trace-otel",
            span_id="span-otel",
            tenant_id="tenant-acme",
            envelope_id="env-prod-001",
            tool_name=None,
            llm_model="claude-opus-4-7",
            prompt_tokens=120,
            completion_tokens=340,
            duration_ms=2145.0,
            status=TraceEventStatus.OK,
            payload_hash="sha256:a1b2c3d4",
            payload={"k": "v"},
        )

    def test_round_trip_preserves_every_field(self) -> None:
        evt = self._full_event()
        d = evt.to_dict()
        restored = TraceEvent.from_dict(d)
        assert restored == evt

    def test_round_trip_preserves_fingerprint(self) -> None:
        evt = self._full_event()
        restored = TraceEvent.from_dict(evt.to_dict())
        assert compute_trace_event_fingerprint(evt) == compute_trace_event_fingerprint(
            restored
        )

    def test_to_dict_preserves_none_optional_fields(self) -> None:
        """Optional fields that are ``None`` must remain in the dict so
        the shape is stable — cross-SDK consumers can always expect the
        full set of known keys."""
        evt = self._full_event()
        d = evt.to_dict()
        for opt in (
            "parent_event_id",
            "trace_id",
            "span_id",
            "tenant_id",
            "envelope_id",
            "tool_name",
            "llm_model",
            "prompt_tokens",
            "completion_tokens",
            "duration_ms",
            "status",
            "payload_hash",
            "payload",
        ):
            assert opt in d

    def test_to_dict_timestamp_has_utc_offset(self) -> None:
        evt = self._full_event()
        assert evt.to_dict()["timestamp"].endswith("+00:00")

    def test_from_dict_parses_iso_timestamp(self) -> None:
        d = {
            "event_id": "evt-1",
            "event_type": "agent.run.start",
            "timestamp": "2026-04-20T12:00:00+00:00",
            "run_id": "run-1",
            "agent_id": "agent-1",
            "cost_microdollars": 0,
        }
        evt = TraceEvent.from_dict(d)
        assert evt.timestamp == datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# compute_trace_event_fingerprint — cross-SDK canonicalization
# ---------------------------------------------------------------------------


class TestCanonicalFingerprint:
    def test_fingerprint_is_64_hex_chars(self) -> None:
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        fp = compute_trace_event_fingerprint(evt)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_deterministic(self) -> None:
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        assert compute_trace_event_fingerprint(evt) == compute_trace_event_fingerprint(
            evt
        )

    def test_fingerprint_matches_manual_compact_json(self) -> None:
        """Pinned byte-for-byte expectation: fingerprint is SHA-256 over
        compact-separator + sorted-keys + ensure_ascii canonical JSON.
        Rust ``serde_json::to_string(&BTreeMap)`` produces identical
        bytes on the same logical input."""
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        expected_canonical = json.dumps(
            evt.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        expected_fp = hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()
        assert compute_trace_event_fingerprint(evt) == expected_fp

    def test_fingerprint_differs_on_field_change(self) -> None:
        evt_a = TraceEvent(
            event_id="evt-A",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        evt_b = TraceEvent(
            event_id="evt-B",  # different event_id
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        assert compute_trace_event_fingerprint(
            evt_a
        ) != compute_trace_event_fingerprint(evt_b)


# ---------------------------------------------------------------------------
# Schema validation — the language-neutral contract
# ---------------------------------------------------------------------------


class TestSchemaConformance:
    def test_minimal_event_passes_schema(self, validator: Draft202012Validator) -> None:
        evt = TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )
        validator.validate(evt.to_dict())

    def test_full_event_passes_schema(self, validator: Draft202012Validator) -> None:
        evt = TraceEvent(
            event_id="evt-full",
            event_type=TraceEventType.LLM_CALL_END,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
            run_id="run-xyz",
            agent_id="D1-R1-D2-R2",
            cost_microdollars=1500,
            parent_event_id="evt-parent",
            trace_id="trace-otel",
            span_id="span-otel",
            tenant_id="tenant-acme",
            envelope_id="env-prod-001",
            tool_name=None,
            llm_model="claude-opus-4-7",
            prompt_tokens=120,
            completion_tokens=340,
            duration_ms=2145.0,
            status=TraceEventStatus.OK,
            payload_hash="sha256:a1b2c3d4",
            payload={"k": "v"},
        )
        validator.validate(evt.to_dict())

    def test_invalid_timestamp_format_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        from jsonschema import ValidationError

        # Z-form timestamp is banned by the pattern.
        bad = {
            "event_id": "evt-1",
            "event_type": "agent.run.start",
            "timestamp": "2026-04-20T12:00:00Z",
            "run_id": "run-1",
            "agent_id": "agent-1",
            "cost_microdollars": 0,
        }
        with pytest.raises(ValidationError):
            validator.validate(bad)

    def test_invalid_payload_hash_format_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        from jsonschema import ValidationError

        # payload_hash must match ^sha256:[0-9a-f]{8}$ — wrong length.
        bad = {
            "event_id": "evt-1",
            "event_type": "agent.run.start",
            "timestamp": "2026-04-20T12:00:00+00:00",
            "run_id": "run-1",
            "agent_id": "agent-1",
            "cost_microdollars": 0,
            "payload_hash": "sha256:abcd",  # 4 hex, not 8
        }
        with pytest.raises(ValidationError):
            validator.validate(bad)

    def test_unknown_event_type_rejected(self, validator: Draft202012Validator) -> None:
        from jsonschema import ValidationError

        bad = {
            "event_id": "evt-1",
            "event_type": "agent.run.UNKNOWN",
            "timestamp": "2026-04-20T12:00:00+00:00",
            "run_id": "run-1",
            "agent_id": "agent-1",
            "cost_microdollars": 0,
        }
        with pytest.raises(ValidationError):
            validator.validate(bad)

    def test_additional_properties_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        """Schema is closed — unknown fields are a contract violation."""
        from jsonschema import ValidationError

        bad = {
            "event_id": "evt-1",
            "event_type": "agent.run.start",
            "timestamp": "2026-04-20T12:00:00+00:00",
            "run_id": "run-1",
            "agent_id": "agent-1",
            "cost_microdollars": 0,
            "unknown_extension": "value",
        }
        with pytest.raises(ValidationError):
            validator.validate(bad)


# ---------------------------------------------------------------------------
# JudgeInput / JudgeResult
# ---------------------------------------------------------------------------


class TestJudgeInputResult:
    def test_judge_input_round_trip(self) -> None:
        inp = JudgeInput(
            prompt="Is the sky blue?",
            candidate_a="Yes, the sky is blue due to Rayleigh scattering.",
            candidate_b="No, the sky is green.",
            reference="The sky appears blue.",
            rubric="factual accuracy",
        )
        assert JudgeInput.from_dict(inp.to_dict()) == inp

    def test_judge_input_pointwise_minimal(self) -> None:
        inp = JudgeInput(prompt="Q?", candidate_a="A.")
        assert inp.candidate_b is None
        assert inp.reference is None
        assert inp.rubric is None

    def test_judge_result_valid(self) -> None:
        res = JudgeResult(
            score=0.85,
            winner="A",
            reasoning="A is more factually accurate.",
            judge_model="claude-opus-4-7",
            cost_microdollars=1500,
            prompt_tokens=120,
            completion_tokens=80,
        )
        assert res.winner == "A"

    def test_judge_result_winner_enum_enforced(self) -> None:
        with pytest.raises(ValueError, match="winner"):
            JudgeResult(
                score=0.5,
                winner="FIRST",  # invalid
                reasoning=None,
                judge_model="claude-opus-4-7",
                cost_microdollars=0,
                prompt_tokens=0,
                completion_tokens=0,
            )

    def test_judge_result_winner_none_accepted(self) -> None:
        res = JudgeResult(
            score=0.5,
            winner=None,  # no verdict yet
            reasoning=None,
            judge_model="claude-opus-4-7",
            cost_microdollars=0,
            prompt_tokens=0,
            completion_tokens=0,
        )
        assert res.winner is None

    def test_judge_result_integer_fields_enforced(self) -> None:
        with pytest.raises(TypeError, match="cost_microdollars"):
            JudgeResult(  # type: ignore[arg-type]
                score=0.5,
                winner="A",
                reasoning=None,
                judge_model="claude-opus-4-7",
                cost_microdollars=1.5,
                prompt_tokens=0,
                completion_tokens=0,
            )

    def test_judge_result_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            JudgeResult(
                score=0.5,
                winner="A",
                reasoning=None,
                judge_model="claude-opus-4-7",
                cost_microdollars=-1,
                prompt_tokens=0,
                completion_tokens=0,
            )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class _SampleJudge:
    """Structural conformance — async __call__ matching the Protocol."""

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        return JudgeResult(
            score=1.0,
            winner="A",
            reasoning="stub",
            judge_model="stub-model",
            cost_microdollars=0,
            prompt_tokens=0,
            completion_tokens=0,
        )


class _SampleDiagnostic:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def report(self) -> dict:
        return {"run_id": self.run_id, "ok": True}


class TestProtocolConformance:
    def test_judge_callable_runtime_check_accepts_conforming(self) -> None:
        assert isinstance(_SampleJudge(), JudgeCallable)

    def test_judge_callable_runtime_check_rejects_non_conforming(self) -> None:
        class _NotAJudge:
            pass

        assert not isinstance(_NotAJudge(), JudgeCallable)

    def test_diagnostic_runtime_check_accepts_conforming(self) -> None:
        assert isinstance(_SampleDiagnostic("run-1"), Diagnostic)

    def test_diagnostic_runtime_check_rejects_non_conforming(self) -> None:
        class _Half:
            run_id = "run-half"

            def __enter__(self):
                return self

            # Missing __exit__ and report()

        assert not isinstance(_Half(), Diagnostic)

    def test_diagnostic_report_returns_dict(self) -> None:
        with _SampleDiagnostic("run-1") as d:
            report = d.report()
        assert isinstance(report, dict)
        assert report["run_id"] == "run-1"

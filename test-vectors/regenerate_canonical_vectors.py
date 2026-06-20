# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Authoritative generator for the audit-chain + trace-event canonical fixtures.

Run from the repo root with the project venv:

    .venv/bin/python test-vectors/regenerate_canonical_vectors.py

This script is the documented PRODUCER referenced by each fixture's
``provenance`` block (issue #1402): every ``expected_*`` value is reproduced by
calling the PRODUCTION canonical path — ``AuditAnchor._canonical_input`` /
``AuditAnchor.compute_hash`` and ``kailash.diagnostics.protocols._canonical_json``
/ ``compute_trace_event_fingerprint`` — never a hand-mirror. Re-running it must
be a no-op against a clean tree; a diff means production canonical bytes changed
and the change must be reviewed as a cross-SDK byte-contract change
(kailash-rs#449 §2 — coordinate the rust side in lockstep).

Typed-scalar vectors (U5 metadata, V6 payload) carry their non-JSON-native
values under a ``__pytype__`` tag so the fixture stays valid JSON yet round-trips
to real Python objects. The convention (a sibling SDK loader implements the
inverse to consume the same vectors):

    Decimal  -> {"__pytype__": "Decimal",  "repr": "1.50"}
    UUID     -> {"__pytype__": "UUID",     "repr": "<8-4-4-4-12>"}
    datetime -> {"__pytype__": "datetime", "repr": "<iso8601 with offset>"}
    set      -> {"__pytype__": "set",      "items": [ ... ]}
    bytes    -> {"__pytype__": "bytes",    "b64": "<base64>"}
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from kailash.diagnostics.protocols import (  # noqa: E402
    TraceEvent,
    _canonical_json,
    compute_trace_event_fingerprint,
)
from kailash.trust.pact.audit import AuditAnchor  # noqa: E402
from kailash.trust.pact.config import VerificationLevel  # noqa: E402

# Frozen so the fixtures are byte-reproducible across runs (no Date.now()).
_GENERATED_AT = "2026-06-20T00:00:00+00:00"
_PYTHON_VERSION = "3.13"


# --------------------------------------------------------------------------- #
# __pytype__ codec
# --------------------------------------------------------------------------- #
def encode_typed(value: Any) -> Any:
    """Encode a Python typed scalar to its ``__pytype__`` JSON tag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return {"__pytype__": "Decimal", "repr": str(value)}
    if isinstance(value, uuid.UUID):
        return {"__pytype__": "UUID", "repr": str(value)}
    if isinstance(value, datetime):
        return {"__pytype__": "datetime", "repr": value.isoformat()}
    if isinstance(value, (set, frozenset)):
        return {"__pytype__": "set", "items": [encode_typed(v) for v in sorted(value)]}
    if isinstance(value, bytes):
        return {"__pytype__": "bytes", "b64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {k: encode_typed(v) for k, v in value.items()}
    return value


def decode_typed(obj: Any) -> Any:
    """Inverse of :func:`encode_typed` — reconstruct real Python objects.

    Importable by the regression tests so the fixture loader and the generator
    share ONE codec. A sibling SDK implements the same inverse to consume the
    same vectors.
    """
    if isinstance(obj, dict):
        tag = obj.get("__pytype__")
        if tag == "Decimal":
            return Decimal(obj["repr"])
        if tag == "UUID":
            return uuid.UUID(obj["repr"])
        if tag == "datetime":
            return datetime.fromisoformat(obj["repr"])
        if tag == "set":
            return {decode_typed(v) for v in obj["items"]}
        if tag == "bytes":
            return base64.b64decode(obj["b64"])
        return {k: decode_typed(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- #
# audit-chain vectors
# --------------------------------------------------------------------------- #
# (name, input_repr) — metadata holds REAL Python objects; typed values are
# __pytype__-encoded into the fixture on write.
_AUDIT_VECTORS: list[tuple[str, dict[str, Any]]] = [
    (
        "U1_bmp_metadata_key_and_value",
        dict(
            anchor_id="anc-u1-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u1",
            action="envelope_created",
            verification_level="AUTO_APPROVED",
            envelope_id="env-u1",
            result="success",
            timestamp="2026-01-15T11:00:00+00:00",
            metadata={"role": "café", "中文": "value"},
        ),
    ),
    (
        "U2_above_bmp_emoji_metadata_value",
        dict(
            anchor_id="anc-u2-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u2",
            action="envelope_created",
            verification_level="AUTO_APPROVED",
            envelope_id="env-u2",
            result="success",
            timestamp="2026-01-15T12:00:00+00:00",
            metadata={"celebration": "🎉🚀"},
        ),
    ),
    (
        "U3_nonzero_microsecond",
        dict(
            anchor_id="anc-u3-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u3",
            action="access_granted",
            verification_level="AUTO_APPROVED",
            envelope_id="env-u3",
            result="success",
            timestamp="2026-01-15T13:00:00.123456+00:00",
            metadata={"role": "operator"},
        ),
    ),
    (
        "U4_whole_second_explicit_000000",
        dict(
            anchor_id="anc-u4-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u4",
            action="access_granted",
            verification_level="AUTO_APPROVED",
            envelope_id="env-u4",
            result="success",
            timestamp="2026-01-15T14:00:00+00:00",
            metadata={"role": "operator"},
        ),
    ),
    (
        "U5_typed_scalar_metadata",
        dict(
            anchor_id="anc-u5-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u5",
            action="budget_check",
            verification_level="AUTO_APPROVED",
            envelope_id="env-u5",
            result="success",
            timestamp="2026-01-15T15:00:00.500000+00:00",
            metadata={
                "amount": Decimal("1.50"),
                "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
                "when": datetime.fromisoformat("2026-03-04T05:06:07.000123+00:00"),
                "tags": {"beta", "alpha", "gamma"},
            },
        ),
    ),
]


def _build_anchor(input_repr: dict[str, Any]) -> AuditAnchor:
    return AuditAnchor(
        anchor_id=input_repr["anchor_id"],
        sequence=input_repr["sequence"],
        previous_hash=input_repr.get("previous_hash"),
        agent_id=input_repr["agent_id"],
        action=input_repr["action"],
        verification_level=VerificationLevel(input_repr["verification_level"]),
        envelope_id=input_repr.get("envelope_id"),
        result=input_repr["result"],
        metadata=input_repr.get("metadata") or {},
        timestamp=datetime.fromisoformat(input_repr["timestamp"]),
    )


def build_audit_fixture() -> dict[str, Any]:
    vectors = []
    for name, input_repr in _AUDIT_VECTORS:
        anchor = _build_anchor(input_repr)
        fixture_input = dict(input_repr)
        fixture_input["metadata"] = encode_typed(input_repr.get("metadata") or {})
        vectors.append(
            {
                "name": name,
                "expected_source": "kailash-py:AuditAnchor.compute_hash (self-consistent)",
                "input_repr": fixture_input,
                "expected_canonical_input": anchor._canonical_input(),
                "expected_sha256": anchor.compute_hash(),
            }
        )
    return {
        "spec_version": "1.1",
        "description": (
            "Cross-SDK canonical fixtures for AuditAnchor.compute_hash() "
            "byte-equality + SHA-256 hex digest stability between kailash-py and "
            "kailash-rs (kailash-rs#449 audit-chain canonical-input contract). "
            "spec_version 1.1 (2026-06-20): timestamp is ALWAYS rendered "
            'isoformat(timespec="microseconds") (six fractional digits) and '
            "metadata typed scalars route through the canonical_scalars whitelist "
            "(no default=str) — issues #1400/#1405. Canonical content: "
            "{anchor_id}:{sequence}:{previous_hash_or_GENESIS_HASH}:{agent_id}:"
            "{action}:{verification_level}:{envelope_id_or_empty}:{result}:"
            "{iso8601_+00:00_with_6_microsecond_digits}"
            "[:{metadata_json_sorted_compact_ensure_ascii}]. "
            "Typed-scalar metadata values use the __pytype__ tag convention "
            "(see test-vectors/regenerate_canonical_vectors.py)."
        ),
        "genesis_hash": "0" * 64,
        "provenance": {
            "producer": "kailash-py:AuditAnchor._canonical_input / compute_hash",
            "generator_script": "test-vectors/regenerate_canonical_vectors.py",
            "python_version": _PYTHON_VERSION,
            "generated_at": _GENERATED_AT,
            "cross_impl_status": "python-self-consistent",
            "cross_impl_note": (
                "expected_* values are reproduced by the Python production path. "
                "kailash-rs is expected to reproduce each value byte-for-byte; "
                "the independent rust digest is verified at the post-Wave-6 "
                "cross-SDK gate, NOT in this repo's CI. See test-vectors/README.md."
            ),
        },
        "vectors": vectors,
    }


# --------------------------------------------------------------------------- #
# trace-event vectors
# --------------------------------------------------------------------------- #
_TRACE_VECTORS: list[tuple[str, dict[str, Any]]] = [
    (
        "V1_zero_microsecond",
        dict(
            event_id="evt-V1",
            run_id="run-V1",
            agent_id="agent-V1",
            cost_microdollars=0,
            event_type="agent.run.start",
            timestamp="2026-04-20T12:00:00.000000+00:00",
        ),
    ),
    (
        "V2_nonzero_microsecond",
        dict(
            event_id="evt-V2",
            run_id="run-V2",
            agent_id="agent-V2",
            cost_microdollars=150,
            tool_name="search",
            duration_ms=42.5,
            event_type="tool.call.start",
            timestamp="2026-04-20T12:00:00.123456+00:00",
        ),
    ),
    (
        "V3_full_event",
        dict(
            event_id="evt-V3",
            run_id="run-V3",
            agent_id="agent-V3",
            cost_microdollars=2500,
            trace_id="trace-V3",
            span_id="span-V3",
            tenant_id="tenant-V3",
            envelope_id="env-V3",
            llm_model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=1234.5,
            payload_hash="sha256:deadbeef",
            payload=None,
            event_type="agent.run.end",
            timestamp="2026-12-31T23:59:59.999999+00:00",
            status="ok",
        ),
    ),
    (
        "V4_bmp_non_ascii_agent_id",
        dict(
            event_id="evt-v4-bmp",
            run_id="run-v4",
            agent_id="agent-café-中文",
            cost_microdollars=0,
            event_type="agent.run.start",
            timestamp="2026-04-20T12:00:00.000000+00:00",
        ),
    ),
    (
        "V5_above_bmp_emoji_tool_name",
        dict(
            event_id="evt-v5-above-bmp",
            run_id="run-v5",
            agent_id="agent-v5",
            cost_microdollars=0,
            tool_name="🎉🚀",
            duration_ms=10.0,
            event_type="tool.call.end",
            timestamp="2026-04-20T12:00:00.000000+00:00",
            status="ok",
        ),
    ),
    (
        "V6_typed_scalar_payload",
        dict(
            event_id="evt-v6-typed",
            run_id="run-v6",
            agent_id="agent-v6",
            cost_microdollars=99,
            event_type="agent.step",
            timestamp="2026-04-20T12:00:00.654321+00:00",
            payload={
                "amount": Decimal("3.14"),
                "request_id": uuid.UUID("00000000-0000-0000-0000-0000000000ff"),
                "deadline": datetime.fromisoformat("2026-05-06T07:08:09.000999+00:00"),
                "labels": {"z", "a", "m"},
            },
        ),
    ),
]

_TRACE_OPTIONAL = (
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
)


def _build_event(input_repr: dict[str, Any]) -> TraceEvent:
    from kailash.diagnostics.protocols import TraceEventStatus, TraceEventType

    kwargs: dict[str, Any] = dict(
        event_id=input_repr["event_id"],
        event_type=TraceEventType(input_repr["event_type"]),
        timestamp=datetime.fromisoformat(input_repr["timestamp"]),
        run_id=input_repr["run_id"],
        agent_id=input_repr["agent_id"],
        cost_microdollars=int(input_repr["cost_microdollars"]),
    )
    for k in _TRACE_OPTIONAL:
        if k in input_repr:
            kwargs[k] = input_repr[k]
    if "status" in kwargs and kwargs["status"] is not None:
        kwargs["status"] = TraceEventStatus(kwargs["status"])
    return TraceEvent(**kwargs)


def build_trace_fixture() -> dict[str, Any]:
    vectors = []
    for name, input_repr in _TRACE_VECTORS:
        event = _build_event(input_repr)
        fixture_input = dict(input_repr)
        if input_repr.get("payload"):
            fixture_input["payload"] = encode_typed(input_repr["payload"])
        vectors.append(
            {
                "name": name,
                "expected_source": "kailash-py:compute_trace_event_fingerprint (self-consistent)",
                "input_repr": fixture_input,
                "expected_canonical_json": _canonical_json(event),
                "expected_fingerprint": compute_trace_event_fingerprint(event),
            }
        )
    return {
        "spec_version": "1.1",
        "description": (
            "Cross-SDK canonical fixtures for TraceEvent.to_dict() byte-equality + "
            "fingerprint stability between kailash-py and kailash-rs. spec_version "
            "1.1 (2026-06-20): adds V6 typed-scalar payload exercising the "
            "canonical_scalars whitelist that replaced default=str on the "
            "fingerprint path (issues #1403/#1405). V1-V5 bytes are unchanged "
            "from spec 1.0 (to_dict already emitted timespec=microseconds). The "
            "ensure_ascii=True contract requires non-ASCII codepoints render as "
            "\\uXXXX escapes (and surrogate pairs above U+FFFF) per RFC 8259 §7. "
            "Typed payload values use the __pytype__ tag convention "
            "(see test-vectors/regenerate_canonical_vectors.py)."
        ),
        "provenance": {
            "producer": "kailash-py:protocols._canonical_json / compute_trace_event_fingerprint",
            "generator_script": "test-vectors/regenerate_canonical_vectors.py",
            "python_version": _PYTHON_VERSION,
            "generated_at": _GENERATED_AT,
            "cross_impl_status": "python-self-consistent",
            "cross_impl_note": (
                "expected_* values are reproduced by the Python production path. "
                "kailash-rs is expected to reproduce each value byte-for-byte; "
                "the independent rust digest is verified at the post-Wave-6 "
                "cross-SDK gate, NOT in this repo's CI. See test-vectors/README.md."
            ),
        },
        "vectors": vectors,
    }


def main() -> None:
    audit_path = _REPO_ROOT / "test-vectors" / "audit-chain-canonical.json"
    trace_path = _REPO_ROOT / "test-vectors" / "trace-event-canonical.json"
    audit_path.write_text(
        json.dumps(build_audit_fixture(), indent=2, ensure_ascii=False) + "\n"
    )
    trace_path.write_text(
        json.dumps(build_trace_fixture(), indent=2, ensure_ascii=False) + "\n"
    )
    print(f"wrote {audit_path.relative_to(_REPO_ROOT)}")
    print(f"wrote {trace_path.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()

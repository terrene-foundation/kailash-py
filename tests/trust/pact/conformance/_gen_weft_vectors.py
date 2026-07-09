# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""One-shot generator for the WEFT (#1591) conformance vectors.

Constructs each fixture through the REAL production implementation
(``WeftEvent`` / ``jcs_encode`` / ``jcs_subject_hash``) and writes the
byte-pinned vector JSON into ``vectors/``. Re-run to regenerate after an
intentional canonical change, then re-pin ``PACT_VECTORS.sha256`` in the same
commit (``cross-sdk-inspection.md`` Rule 4c). NOT collected by pytest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kailash.trust._jcs import jcs_encode, jcs_subject_hash
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.weft import WeftEvent, WeftKind

VECTORS = Path(__file__).parent / "vectors"


def _event_vector(
    filename: str,
    description: str,
    *,
    kind: WeftKind,
    ts: str,
    session: str,
    identity_ref: str,
    payload: dict[str, Any],
    prev_link: str | None,
) -> None:
    event = WeftEvent(
        schema_version=SCHEMA_VERSION_V3,
        kind=kind,
        ts=ts,
        session=session,
        identity_ref=identity_ref,
        payload=payload,
        prev_link=prev_link,
    )
    vector = {
        "description": description,
        "pact_type": "WeftEvent",
        "conformance_requirement": "WEFT",
        "schema_version": SCHEMA_VERSION_V3,
        "input": event.to_dict(),
        "expected_canonical_json": event.canonical_json(),
        "expected_content_hash": event.content_hash(),
    }
    _write(filename, vector)


def _write(filename: str, vector: dict[str, Any]) -> None:
    path = VECTORS / filename
    # ensure_ascii=False keeps unicode raw so the committed vector is byte-stable
    # under the utf-8 loader (issue #1590 Windows-CI fix). trailing newline.
    path.write_text(
        json.dumps(vector, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {filename}")


# A stable genesis chain head so chained vectors reference a real content_hash.
_GENESIS_MINT = WeftEvent(
    schema_version=SCHEMA_VERSION_V3,
    kind=WeftKind.MINT,
    ts="2026-01-15T10:00:00+00:00",
    session="weft-sess-001",
    identity_ref="Eng-CTO-Backend-Lead",
    payload={"subject_ref": "kb-42", "origin": "authored"},
    prev_link=None,
)
_GENESIS_HASH = _GENESIS_MINT.content_hash()
_GATE = WeftEvent(
    schema_version=SCHEMA_VERSION_V3,
    kind=WeftKind.HUMAN_GATE,
    ts="2026-01-15T10:01:00+00:00",
    session="weft-sess-001",
    identity_ref="Eng-CTO",
    payload={"subject_ref": "kb-42", "approver": "Eng-CTO"},
    prev_link=_GENESIS_HASH,
)
_GATE_HASH = _GATE.content_hash()


def main() -> None:
    # 1. Mint — genesis (prev_link null)
    _event_vector(
        "weft_mint.json",
        "WEFT Mint event at chain genesis (prev_link null); citable content_hash "
        "is sha256 of the RFC 8785 (JCS) canonical envelope (#1591).",
        kind=WeftKind.MINT,
        ts="2026-01-15T10:00:00+00:00",
        session="weft-sess-001",
        identity_ref="Eng-CTO-Backend-Lead",
        payload={"subject_ref": "kb-42", "origin": "authored"},
        prev_link=None,
    )

    # 2. HumanGate — chained to the mint
    _event_vector(
        "weft_human_gate.json",
        "WEFT HumanGate event chained to a Mint (prev_link set); recording the "
        "gate is the fail-closed precondition for Distribute (#1591).",
        kind=WeftKind.HUMAN_GATE,
        ts="2026-01-15T10:01:00+00:00",
        session="weft-sess-001",
        identity_ref="Eng-CTO",
        payload={"subject_ref": "kb-42", "approver": "Eng-CTO"},
        prev_link=_GENESIS_HASH,
    )

    # 3. Distribute — chained after the gate
    _event_vector(
        "weft_distribute.json",
        "WEFT Distribute event chained after its HumanGate; the provenance edge "
        "from gated subject to recipient (#1591).",
        kind=WeftKind.DISTRIBUTE,
        ts="2026-01-15T10:02:00+00:00",
        session="weft-sess-001",
        identity_ref="Eng-CTO-Backend-Lead-DevTeam-SeniorDev",
        payload={"subject_ref": "kb-42", "recipient": "Sales-VP"},
        prev_link=_GATE_HASH,
    )

    # 4. Decline — with a reason
    _event_vector(
        "weft_decline.json",
        "WEFT Decline event (fail-closed refusal of a distribution request), "
        "carrying a human-readable reason (#1591).",
        kind=WeftKind.DECLINE,
        ts="2026-01-15T10:03:00+00:00",
        session="weft-sess-002",
        identity_ref="Eng-CTO",
        payload={"subject_ref": "kb-99", "reason": "insufficient clearance"},
        prev_link=None,
    )

    # 5. Obsolete
    _event_vector(
        "weft_obsolete.json",
        "WEFT Obsolete event retiring a subject from the fabric (#1591).",
        kind=WeftKind.OBSOLETE,
        ts="2026-01-15T10:04:00+00:00",
        session="weft-sess-002",
        identity_ref="Eng-CTO",
        payload={"subject_ref": "kb-42", "superseded_by": "kb-43"},
        prev_link=None,
    )

    # 6. Distribute deeper in a chain (distinct prev_link)
    _event_vector(
        "weft_distribute_chained.json",
        "WEFT Distribute event deeper in a chain, referencing a non-genesis "
        "prev_link content_hash (chain continuity) (#1591).",
        kind=WeftKind.DISTRIBUTE,
        ts="2026-01-15T10:05:00+00:00",
        session="weft-sess-001",
        identity_ref="Eng-CTO-Backend-Lead",
        payload={"subject_ref": "kb-42", "recipient": "Ops-Lead"},
        prev_link="sha256:"
        + "0" * 64,  # a fixed non-null predecessor for a stable byte-pin
    )

    # 7. Unicode payload (cross-platform utf-8 decode)
    _event_vector(
        "weft_unicode_payload.json",
        "WEFT event with a unicode + supplementary-plane payload; pins RFC 8785 "
        "raw-UTF-8 string emission + UTF-16 key ordering (utf-8 loader) (#1591).",
        kind=WeftKind.MINT,
        ts="2026-01-15T10:06:00+00:00",
        session="weft-sess-003",
        identity_ref="Eng-CTO",
        # keys chosen to exercise UTF-16 code-unit ordering (BMP vs supplementary)
        payload={"note": "café ☕ \U0001f9f5", "étiquette": "é", "z": 1},
        prev_link=None,
    )

    # 8. Nested payload (dict + list)
    _event_vector(
        "weft_nested_payload.json",
        "WEFT event with a nested dict/list payload; pins recursive JCS "
        "canonicalization (#1591).",
        kind=WeftKind.DISTRIBUTE,
        ts="2026-01-15T10:07:00+00:00",
        session="weft-sess-003",
        identity_ref="Eng-CTO",
        payload={
            "subject_ref": "kb-7",
            "recipients": ["Sales-VP", "Ops-Lead"],
            "meta": {"priority": "high", "tags": ["fx", "risk"]},
        },
        prev_link=None,
    )

    # 9. Big-integer payload (>= 10**21) — JCS int-path inside a WEFT event
    _event_vector(
        "weft_bigint_payload.json",
        "WEFT event whose payload carries an integer >= 10**21; pins the py-side "
        "exact-decimal int serialization inside a WEFT envelope (the deliberate "
        "documented JCS int-path choice — #1590 security review, #1591).",
        kind=WeftKind.MINT,
        ts="2026-01-15T10:08:00+00:00",
        session="weft-sess-004",
        identity_ref="Eng-CTO",
        payload={"subject_ref": "ledger-1", "balance": 10**21, "seq": 9},
        prev_link=None,
    )

    # 10. Bool / null / float scalar coverage
    _event_vector(
        "weft_scalar_payload.json",
        "WEFT event pinning JCS scalar emission for bool / null / float payload "
        "values (#1591).",
        kind=WeftKind.MINT,
        ts="2026-01-15T10:09:00+00:00",
        session="weft-sess-004",
        identity_ref="Eng-CTO",
        payload={"subject_ref": "kb-8", "active": True, "prior": None, "ratio": 0.5},
        prev_link=None,
    )

    # 11. Unknown-kind reader must-ignore vector (forward-compat)
    _write(
        "weft_unknown_kind.json",
        {
            "description": "WEFT forward-compat vector: an event whose kind is not "
            "one of the five known kinds. A reader MUST ignore it gracefully "
            "(never crash), preserving cross-schema_version continuity (#1591).",
            "pact_type": "WeftEvent",
            "conformance_requirement": "WEFT-forward-compat",
            "input": {
                "schema_version": "v4",
                "kind": "Provenance",
                "ts": "2026-01-15T10:10:00+00:00",
                "session": "weft-sess-005",
                "identity_ref": "Eng-CTO",
                "payload": {"subject_ref": "kb-42"},
                "prev_link": None,
            },
            "expected_reader_disposition": "ignore",
        },
    )

    # 12. JCS big-integer SUBJECT vector — the cross-SDK int-path contract pin
    #     (flagged by #1590's security review). Pins the py-side jcs_subject_hash
    #     bytes for a subject with an integer value >= 10**21.
    subject = {
        "account": "acct-9",
        "amount": 10**21,
        "huge": 123456789012345678901234567890,
    }
    _write(
        "jcs_bigint_subject.json",
        {
            "description": "JCS subject with integer values >= 10**21. The py "
            "encoder emits exact-decimal str() for ints (a deliberate documented "
            "choice); pinned here as the cross-SDK contract so the eventual Rust "
            "alignment is byte-verified (#1590 security review, #1591).",
            "pact_type": "JcsSubject",
            "conformance_requirement": "JCS-bigint",
            "rfc8785_reference": "RFC 8785 numbers apply to JSON NUMBER tokens; a "
            "Python int is serialized as its exact decimal integer token (str(int)), "
            "NOT the ECMAScript double form — 10**21 -> "
            "'1000000000000000000000', not '1e+21'. This is the documented py "
            "int-path; the vector pins those bytes.",
            "input": {"subject": subject},
            "expected_subject_jcs": jcs_encode(subject),
            "expected_subject_hash": jcs_subject_hash(subject),
        },
    )


if __name__ == "__main__":
    main()

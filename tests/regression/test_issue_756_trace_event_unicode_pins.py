# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #756 — TraceEvent canonical-JSON fingerprint Unicode pins.

Pinned cross-SDK byte vectors that lock the ``ensure_ascii=True`` contract in
``compute_trace_event_fingerprint``. Two algorithmic-drift failure modes this
guards against:

1. ``ensure_ascii=False`` regression — non-ASCII codepoints would emit raw UTF-8
   instead of ``\\uXXXX`` escapes, breaking byte-equivalence with kailash-rs's
   ``serde_json::to_string(&BTreeMap)`` (which emits ASCII-escaped output).

2. Above-BMP surrogate-pair drift — a JSON writer that emits codepoints above
   U+FFFF as 4-byte UTF-8 (``\\ud83c\\udf89`` ↔ ``🎉``) instead of surrogate
   pairs would silently break cross-SDK fingerprint correlation for any
   payload carrying emoji or other above-BMP content.

The vectors live in ``test-vectors/trace-event-canonical.json`` (cross-SDK
contract — kailash-rs reads the same file). This module asserts named V4/V5
cases per the issue's acceptance criteria; ``test_issue_731_*`` already
auto-iterates the full fixture for byte-and-fingerprint parity.

Cross-SDK alignment per ``rules/cross-sdk-inspection.md`` MUST Rule 4 (byte
vectors pinned, ≥3 vectors with sentinel coverage — V1/V2/V3 cover the
ASCII-only / micros-padding sentinels; V4/V5 cover BMP / above-BMP).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)


@pytest.mark.regression
class TestV4BMPNonASCIIAgentID:
    """V4 pinned vector — BMP non-ASCII codepoints in ``agent_id``.

    Codepoints exercised:
      - U+00E9 (é, Latin-1 supplement)
      - U+4E2D (中, CJK)
      - U+6587 (文, CJK)

    All MUST emit as ``\\uXXXX`` escapes per RFC 8259 §7 + the
    ``ensure_ascii=True`` contract.
    """

    EXPECTED_CANONICAL_JSON = (
        '{"agent_id":"agent-caf\\u00e9-\\u4e2d\\u6587",'
        '"completion_tokens":null,"cost_microdollars":0,"duration_ms":null,'
        '"envelope_id":null,"event_id":"evt-v4-bmp",'
        '"event_type":"agent.run.start","llm_model":null,'
        '"parent_event_id":null,"payload":null,"payload_hash":null,'
        '"prompt_tokens":null,"run_id":"run-v4","span_id":null,'
        '"status":null,"tenant_id":null,'
        '"timestamp":"2026-04-20T12:00:00.000000+00:00",'
        '"tool_name":null,"trace_id":null}'
    )
    EXPECTED_FINGERPRINT = (
        "67bade44e4044933396f8035e725929a4aa54ae274d4e2058871367a93abe95b"
    )

    def _make_event(self) -> TraceEvent:
        return TraceEvent(
            event_id="evt-v4-bmp",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
            run_id="run-v4",
            agent_id="agent-café-中文",
            cost_microdollars=0,
        )

    def test_canonical_json_byte_equal(self) -> None:
        evt = self._make_event()
        canonical = json.dumps(
            evt.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        assert canonical == self.EXPECTED_CANONICAL_JSON

    def test_fingerprint_matches_pinned_sha256(self) -> None:
        assert (
            compute_trace_event_fingerprint(self._make_event())
            == self.EXPECTED_FINGERPRINT
        )

    def test_canonical_json_emits_ascii_only_bytes(self) -> None:
        """Structural invariant: ASCII-only output proves ``ensure_ascii=True``
        is not silently regressed to ``False``. A regression would surface
        as raw multi-byte UTF-8 in the canonical-JSON output."""
        canonical = json.dumps(
            self._make_event().to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        assert canonical.isascii(), (
            "canonical-JSON output must be pure ASCII; non-ASCII byte means "
            "ensure_ascii=True regressed to False — cross-SDK byte-parity broken."
        )

    def test_fingerprint_is_sha256_of_canonical_bytes(self) -> None:
        """The fingerprint MUST equal SHA-256 of the canonical-JSON UTF-8 bytes
        — no transformation other than the pinned canonicalization step."""
        evt = self._make_event()
        canonical = json.dumps(
            evt.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert compute_trace_event_fingerprint(evt) == expected


@pytest.mark.regression
class TestV5AboveBMPEmojiToolName:
    """V5 pinned vector — above-BMP emoji codepoints in ``tool_name``.

    Codepoints exercised (each requires a UTF-16 surrogate pair):
      - U+1F389 🎉 → ``\\ud83c\\udf89``
      - U+1F680 🚀 → ``\\ud83d\\ude80``

    Both MUST emit as surrogate-pair ``\\uXXXX\\uXXXX`` sequences per
    RFC 8259 §7 + the ``ensure_ascii=True`` contract.
    """

    EXPECTED_CANONICAL_JSON = (
        '{"agent_id":"agent-v5","completion_tokens":null,'
        '"cost_microdollars":0,"duration_ms":10.0,"envelope_id":null,'
        '"event_id":"evt-v5-above-bmp","event_type":"tool.call.end",'
        '"llm_model":null,"parent_event_id":null,"payload":null,'
        '"payload_hash":null,"prompt_tokens":null,"run_id":"run-v5",'
        '"span_id":null,"status":"ok","tenant_id":null,'
        '"timestamp":"2026-04-20T12:00:00.000000+00:00",'
        '"tool_name":"\\ud83c\\udf89\\ud83d\\ude80","trace_id":null}'
    )
    EXPECTED_FINGERPRINT = (
        "2d372a1a42a2221ba3fb014062d735b076d11371b0f1390919b53fe908a23d1f"
    )

    def _make_event(self) -> TraceEvent:
        return TraceEvent(
            event_id="evt-v5-above-bmp",
            event_type=TraceEventType.TOOL_CALL_END,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
            run_id="run-v5",
            agent_id="agent-v5",
            cost_microdollars=0,
            tool_name="🎉🚀",
            duration_ms=10.0,
            status=TraceEventStatus.OK,
        )

    def test_canonical_json_byte_equal(self) -> None:
        evt = self._make_event()
        canonical = json.dumps(
            evt.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        assert canonical == self.EXPECTED_CANONICAL_JSON

    def test_fingerprint_matches_pinned_sha256(self) -> None:
        assert (
            compute_trace_event_fingerprint(self._make_event())
            == self.EXPECTED_FINGERPRINT
        )

    def test_above_bmp_emits_surrogate_pairs(self) -> None:
        """Structural invariant: each above-BMP codepoint MUST emit as
        ``\\uXXXX\\uXXXX``. A regression that emits a single ``\\uXXXXX`` or
        raw 4-byte UTF-8 would diverge from kailash-rs's surrogate-pair
        output and silently break cross-SDK forensic correlation."""
        canonical = json.dumps(
            self._make_event().to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        # U+1F389 🎉 → high surrogate D83C + low surrogate DF89
        assert "\\ud83c\\udf89" in canonical
        # U+1F680 🚀 → high surrogate D83D + low surrogate DE80
        assert "\\ud83d\\ude80" in canonical
        # And no raw above-BMP characters survive in the canonical output.
        assert "🎉" not in canonical
        assert "🚀" not in canonical

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #959 — trust-plane canonical-bytes byte pins.

The trust-plane hash-chain helpers (``DecisionRecord.content_hash``,
``ReasoningTrace.content_hash``, and
``plane.models.ConstraintEnvelope.envelope_hash``) build canonical bytes via
``kailash.trust.signing.crypto.serialize_for_signing`` and feed them into
SHA-256. Cross-SDK signature parity (kailash-py ↔ kailash-rs) requires
byte-for-byte identical output for identical inputs — otherwise the SAME
logical record signed on Python verifies-differently on Rust and chain-hash
audit fails silently.

These tests pin the canonical-bytes shape AND the SHA-256 output for
representative input vectors covering: ASCII, UTC datetime, tz-aware
datetime, Decimal, UUID, Unicode BMP, above-BMP emoji, the empty-dict
sentinel, and a negative case (unsupported type rejection). One
``TestCrossSDKFixtureParity`` class auto-iterates the vendored fixture
``tests/test-vectors/trust-plane-canonical.json`` for kailash-rs to mirror
per ``cross-sdk-inspection.md`` Rule 4a.

Plus a verifier-behavior class pinning the ``strict=True`` raise contract
on ``TrustProject.verify`` (issue-959 silent-fallback fix).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from kailash.trust.plane.exceptions import ChainHashMismatchError
from kailash.trust.plane.models import ConstraintEnvelope, DecisionRecord, DecisionType
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace
from kailash.trust.signing.crypto import serialize_for_signing

# Path to the cross-SDK canonical fixture this test pins. See
# ``tests/test-vectors/trust-plane-canonical.json`` for the contract; the
# sibling kailash-rs binding consumes the same file per
# ``rules/cross-sdk-inspection.md`` Rule 4a.
_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "test-vectors"
    / "trust-plane-canonical.json"
)


def _sha256_hex(s: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string. Mirrors the production
    hash path used by ``DecisionRecord.content_hash`` /
    ``ConstraintEnvelope.envelope_hash``."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Vector V1 — ASCII keys/values
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV1AsciiPayload:
    """Pin canonical bytes + SHA-256 for a minimal ASCII-only payload.

    Sanity check that the canonical helper emits the expected compact form
    (``sort_keys=True``, no whitespace, ``ensure_ascii=True``) for the
    common case. Non-ASCII codepoints are exercised by V6/V7 below.
    """

    EXPECTED_CANONICAL_JSON: str = '{"action":"approve","agent":"a1","cost":42}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"agent": "a1", "action": "approve", "cost": 42}

    def test_canonical_json_byte_equal(self) -> None:
        actual = serialize_for_signing(self._payload())
        assert actual == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        actual = _sha256_hex(serialize_for_signing(self._payload()))
        assert actual == self.EXPECTED_SHA256


# ---------------------------------------------------------------------------
# Vector V2 — UTC datetime preserves ISO-8601 with explicit +00:00 suffix
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV2UtcDatetime:
    EXPECTED_CANONICAL_JSON: str = '{"ts":"2026-01-01T00:00:00+00:00"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"ts": datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def test_canonical_json_byte_equal(self) -> None:
        assert serialize_for_signing(self._payload()) == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )


# ---------------------------------------------------------------------------
# Vector V3 — non-UTC tz-aware datetime preserves offset
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV3NonUtcDatetime:
    EXPECTED_CANONICAL_JSON: str = '{"ts":"2026-01-01T12:00:00+08:00"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {
            "ts": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        }

    def test_canonical_json_byte_equal(self) -> None:
        assert serialize_for_signing(self._payload()) == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )


# ---------------------------------------------------------------------------
# Vector V4 — Decimal preserves precision (issue-959 core: Decimal("1.50")
# MUST serialize as "1.50" not "1.5")
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV4DecimalPreservesPrecision:
    EXPECTED_CANONICAL_JSON: str = '{"amount":"1.50","zero":"0"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"amount": Decimal("1.50"), "zero": Decimal("0")}

    def test_decimal_emits_with_trailing_zero(self) -> None:
        """``Decimal("1.50")`` MUST emit ``"1.50"`` not ``"1.5"`` — this is
        the byte-identity contract issue #959 fixes."""
        actual = serialize_for_signing(self._payload())
        assert '"1.50"' in actual
        assert (
            '"1.5"' not in actual or '"1.50"' in actual
        )  # 1.5 only as substring of 1.50

    def test_canonical_json_byte_equal(self) -> None:
        assert serialize_for_signing(self._payload()) == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )

    def test_distinct_decimal_precisions_produce_distinct_canonical(self) -> None:
        """``Decimal("1.5")`` and ``Decimal("1.50")`` MUST produce distinct
        canonical bytes — they are different Decimal instances per spec."""
        a = serialize_for_signing({"x": Decimal("1.5")})
        b = serialize_for_signing({"x": Decimal("1.50")})
        assert a != b
        assert a == '{"x":"1.5"}'
        assert b == '{"x":"1.50"}'


# ---------------------------------------------------------------------------
# Vector V5 — UUID canonical 8-4-4-4-12 form
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV5Uuid:
    EXPECTED_CANONICAL_JSON: str = '{"id":"00000000-0000-0000-0000-000000000001"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"id": UUID("00000000-0000-0000-0000-000000000001")}

    def test_canonical_json_byte_equal(self) -> None:
        assert serialize_for_signing(self._payload()) == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )


# ---------------------------------------------------------------------------
# Vector V6 — Unicode BMP (e.g. CJK) is escaped to \uXXXX (ensure_ascii=True)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV6UnicodeBmp:
    """Unicode BMP characters are emitted as ``\\uXXXX`` escape sequences
    (``json.dumps`` ``ensure_ascii=True`` default — same as
    ``cross-sdk-inspection.md`` Rule 4's PACT/TraceEvent contracts)."""

    EXPECTED_CANONICAL_JSON: str = '{"name":"\\u6f22\\u5b57"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"name": "漢字"}

    def test_canonical_json_byte_equal(self) -> None:
        actual = serialize_for_signing(self._payload())
        assert actual == self.EXPECTED_CANONICAL_JSON
        # Verify the bytes are ASCII-safe (the ensure_ascii=True contract)
        assert (
            actual.isascii()
        ), "canonical bytes MUST be ASCII-only for cross-SDK byte parity"

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )


# ---------------------------------------------------------------------------
# Vector V7 — above-BMP emoji
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV7AboveBmpEmoji:
    """Above-BMP codepoints are emitted as UTF-16 surrogate-pair escapes,
    matching ``cross-sdk-inspection.md`` Rule 4's PACT contract."""

    EXPECTED_CANONICAL_JSON: str = '{"flag":"\\ud83c\\udf89"}'
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def _payload(self) -> dict:
        return {"flag": "🎉"}

    def test_canonical_json_byte_equal(self) -> None:
        assert serialize_for_signing(self._payload()) == self.EXPECTED_CANONICAL_JSON

    def test_sha256_matches_pinned(self) -> None:
        assert (
            _sha256_hex(serialize_for_signing(self._payload())) == self.EXPECTED_SHA256
        )


# ---------------------------------------------------------------------------
# Vector V8 — ReasoningTrace.content_hash (T05)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV8ReasoningTraceContentHash:
    """Pin the hash output of ``ReasoningTrace.content_hash`` for a
    representative trace built with stable fields (no UUID, no Decimal)."""

    EXPECTED_SHA256_HEX: str = (
        "9152497d56e367541417d4a277531c7e21cd9a693a2937a4feaebaf2fb619c2a"
    )

    def _trace(self) -> ReasoningTrace:
        return ReasoningTrace(
            decision="approve-deployment",
            rationale="all checks green",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            evidence=[{"src": "ci", "id": "abc"}],
            methodology="risk_assessment",
            confidence=0.95,
        )

    def test_content_hash_is_deterministic(self) -> None:
        t = self._trace()
        assert t.content_hash() == t.content_hash()

    def test_content_hash_matches_pinned(self) -> None:
        assert self._trace().content_hash().hex() == self.EXPECTED_SHA256_HEX


# ---------------------------------------------------------------------------
# Vector V9 — plane.models.ConstraintEnvelope.envelope_hash (T06)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestV9PlaneConstraintEnvelopeHash:
    EXPECTED_SHA256_HEX: str = (
        "d47812fb45378d1950b3f32ea0eaf2f94312e34cd58d2e3e38312bfe9af30166"
    )

    def _envelope(self) -> ConstraintEnvelope:
        return ConstraintEnvelope.from_legacy(["no-deploy", "no-prod"], "agent-1")

    def test_envelope_hash_is_deterministic(self) -> None:
        e = self._envelope()
        assert e.envelope_hash() == e.envelope_hash()

    def test_envelope_hash_matches_pinned(self) -> None:
        assert self._envelope().envelope_hash() == self.EXPECTED_SHA256_HEX


# ---------------------------------------------------------------------------
# Sentinel — empty dict
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestEmptyDictSentinel:
    EXPECTED_CANONICAL_JSON: str = "{}"
    EXPECTED_SHA256: str = _sha256_hex(EXPECTED_CANONICAL_JSON)

    def test_empty_dict_canonical(self) -> None:
        assert serialize_for_signing({}) == self.EXPECTED_CANONICAL_JSON

    def test_empty_dict_sha256(self) -> None:
        assert _sha256_hex(serialize_for_signing({})) == self.EXPECTED_SHA256


# ---------------------------------------------------------------------------
# Negative — unsupported types raise TypeError, not silent coerce
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestNegativeRejectsUnsupportedType:
    """Issue #959 contract: unsupported types MUST raise at signing time,
    NOT be silently coerced via ``str()`` (the prior ``default=str`` bug)."""

    def test_custom_class_raises_type_error(self) -> None:
        class Custom:
            def __init__(self) -> None:
                self.x = 1

        with pytest.raises(TypeError):
            serialize_for_signing({"obj": Custom()})

    def test_complex_number_raises(self) -> None:
        with pytest.raises(TypeError):
            serialize_for_signing({"z": complex(1, 2)})


# ---------------------------------------------------------------------------
# Whitelist hardening — date / time / Decimal pass through
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestSerializerWhitelistHandlesAllRequiredTypes:
    """Whitelist contract: every type in the documented list MUST round-trip
    deterministically. This pins the helper's public contract."""

    def test_date_emits_isoformat(self) -> None:
        out = serialize_for_signing({"d": date(2026, 1, 1)})
        assert out == '{"d":"2026-01-01"}'

    def test_time_emits_isoformat(self) -> None:
        out = serialize_for_signing({"t": time(12, 0, 0)})
        assert out == '{"t":"12:00:00"}'

    def test_decimal_string_preserves_trailing_zero(self) -> None:
        out = serialize_for_signing({"x": Decimal("0.10")})
        assert out == '{"x":"0.10"}'

    def test_uuid_lowercase_hex(self) -> None:
        u = UUID("12345678-1234-5678-1234-567812345678")
        out = serialize_for_signing({"u": u})
        assert out == '{"u":"12345678-1234-5678-1234-567812345678"}'


# ---------------------------------------------------------------------------
# Verifier-behavior pin — strict=True raises, default warns + summary
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestVerifyIntegrityRaisesOnMismatchInStrictMode:
    """Issue #959 silent-fallback fix: ``TrustProject.verify(strict=True)``
    raises ``ChainHashMismatchError`` on a tampered decision record instead
    of silently flipping ``chain_valid=False``."""

    async def _make_project_with_tampered_decision(self, tmp_path: Path):
        """Set up: create a TrustProject, record one decision, tamper the
        on-disk decision JSON to break its stored content_hash. Returns
        ``(project, decision_id)``."""
        from kailash.trust.plane.project import TrustProject

        project = await TrustProject.create(
            trust_dir=tmp_path,
            project_name="issue-959 verify-strict test",
            author="agent-1",
            constraints=["no-prod"],
        )
        decision = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="approve",
            rationale="all checks green",
            author="agent-1",
            cost=0.0,
        )
        decision_id = await project.record_decision(decision)
        # Tamper: rewrite the decision JSON with a different `decision`,
        # leaving the original content_hash field intact so it diverges.
        # File name is "{seq:04d}-{decision_id}.json"; glob to find it.
        candidates = list((tmp_path / "decisions").glob(f"*-{decision_id}.json"))
        assert (
            len(candidates) == 1
        ), f"decision file MUST exist after record; found {candidates!r}"
        decision_file = candidates[0]
        data = json.loads(decision_file.read_text(encoding="utf-8"))
        data["decision"] = "tampered!"  # break the stored hash
        decision_file.write_text(json.dumps(data))
        return project, decision_id

    @pytest.mark.asyncio
    async def test_strict_mode_raises_on_tampered_record(self, tmp_path: Path) -> None:
        project, decision_id = await self._make_project_with_tampered_decision(tmp_path)
        with pytest.raises(ChainHashMismatchError) as exc_info:
            await project.verify(strict=True)
        assert exc_info.value.record_type == "decision"
        assert exc_info.value.record_id == decision_id
        assert exc_info.value.computed_hash != exc_info.value.stored_hash

    @pytest.mark.asyncio
    async def test_default_mode_reports_summary_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        project, _ = await self._make_project_with_tampered_decision(tmp_path)
        report = await project.verify()
        assert report["chain_valid"] is False
        assert any("hash mismatch" in issue for issue in report["integrity_issues"])


# ---------------------------------------------------------------------------
# Cross-SDK fixture parity (per cross-sdk-inspection.md Rule 4a)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCrossSDKFixtureParity:
    """Iterate the vendored ``tests/test-vectors/trust-plane-canonical.json``
    and assert every vector's pinned canonical-bytes / SHA-256 reproduces
    via this SDK's ``serialize_for_signing`` + ``hashlib.sha256``. The
    sibling kailash-rs binding consumes the same file."""

    @pytest.fixture(scope="class")
    def fixture(self) -> dict:
        assert _FIXTURE_PATH.exists(), (
            f"cross-SDK trust-plane fixture missing at {_FIXTURE_PATH}; "
            "this fixture is the cross-SDK byte contract per issue #959"
        )
        return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_loads_with_required_floor(self, fixture: dict) -> None:
        assert fixture["contract"] == "trust-plane-canonical-bytes"
        # ≥3 byte-vectors + sentinels per cross-sdk-inspection.md Rule 4.
        assert len(fixture["vectors"]) >= 7

    def _reify_input(self, input_repr: dict) -> dict:
        """Reify input_repr scalar tags into Python objects.

        The fixture stores typed values via small tags (``{"$type": ..., "$value": ...}``)
        so the JSON file can hold them losslessly. This reifier turns them
        back into the Python objects the helper expects. Top-level fixture
        input is always a dict.
        """

        def reify(node: Any) -> Any:
            if isinstance(node, dict):
                if set(node.keys()) == {"$type", "$value"}:
                    t = node["$type"]
                    v = node["$value"]
                    if t == "datetime":
                        return datetime.fromisoformat(v)
                    if t == "date":
                        return date.fromisoformat(v)
                    if t == "time":
                        return time.fromisoformat(v)
                    if t == "decimal":
                        return Decimal(v)
                    if t == "uuid":
                        return UUID(v)
                    raise ValueError(f"unknown $type {t!r} in fixture")
                return {k: reify(v) for k, v in node.items()}
            if isinstance(node, list):
                return [reify(x) for x in node]
            return node

        out = reify(input_repr)
        assert isinstance(out, dict), "fixture input_repr top-level must be a dict"
        return out

    def test_every_vector_canonical_json_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            payload = self._reify_input(v["input_repr"])
            actual = serialize_for_signing(payload)
            assert actual == v["expected_canonical_json"], (
                f"vector {v['name']}: canonical-bytes divergence — "
                f"got {actual!r}, expected {v['expected_canonical_json']!r}"
            )

    def test_every_vector_sha256_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            payload = self._reify_input(v["input_repr"])
            actual = _sha256_hex(serialize_for_signing(payload))
            assert actual == v["expected_sha256"], (
                f"vector {v['name']}: SHA-256 divergence — "
                f"got {actual}, expected {v['expected_sha256']}"
            )

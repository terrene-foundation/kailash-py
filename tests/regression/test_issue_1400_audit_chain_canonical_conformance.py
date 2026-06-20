# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the 2026-06-20 audit-chain canonical-conformance fix.

Covers the behavioral contracts that the cross-SDK byte-pin fixtures (#757,
#731) do not directly assert:

* #1400 — ``AuditAnchor`` timestamps always render six microsecond digits.
* #1401 — naive timestamps rejected on construction, non-UTC normalized,
  ``from_dict`` lenient on read.
* #1404 — ``compute_hash`` hashes exactly what ``_canonical_input`` builds.
* #1405 / #1403 — metadata + trace-fingerprint typed scalars route through the
  shared ``canonical_scalars`` whitelist (no ``default=str``).
* backward-compat — ``verify_chain_integrity`` reads a pre-fix-format chain as
  "re-seal required", not "tampered", and still distinguishes real tampering.
* #1403 — the ``ensure_ascii=True`` signing/hash encoder family shares ONE
  typed-scalar policy; the delegate ``ensure_ascii=False`` encoder is unchanged.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventType,
    compute_trace_event_fingerprint,
)
from kailash.trust._canonical import canonical_scalars
from kailash.trust.pact.audit import AuditAnchor, AuditChain
from kailash.trust.pact.config import VerificationLevel
from kailash.trust.pact.exceptions import PactError

UTC = timezone.utc


def _anchor(
    *, timestamp: datetime, metadata: dict | None = None, anchor_id: str = "anc-x"
) -> AuditAnchor:
    return AuditAnchor(
        anchor_id=anchor_id,
        sequence=0,
        previous_hash=None,
        agent_id="agent-x",
        action="access_granted",
        verification_level=VerificationLevel.AUTO_APPROVED,
        envelope_id="env-x",
        result="success",
        metadata=metadata,
        timestamp=timestamp,
    )


@pytest.mark.regression
class TestMicrosecondPadding:
    """#1400 — fixed-width six-digit microseconds regardless of value."""

    @pytest.mark.parametrize("microsecond", [0, 1, 999, 100_000, 999_999])
    def test_canonical_input_always_six_microsecond_digits(
        self, microsecond: int
    ) -> None:
        ci = _anchor(
            timestamp=datetime(2026, 1, 1, 0, 0, 0, microsecond, tzinfo=UTC)
        )._canonical_input()
        # The timestamp segment carries exactly six digits between '.' and '+00:00'.
        ts_segment = ci.rsplit(":success:", 1)[1]
        fractional = ts_segment.split(".")[1].split("+")[0]
        assert len(fractional) == 6, (
            f"microsecond={microsecond} produced fractional={fractional!r} "
            f"(len={len(fractional)}); expected exactly 6 digits."
        )

    def test_whole_second_and_sub_second_hash_differently(self) -> None:
        """The elision bug: µ==0 and µ==1 must NOT collide (they did pre-fix
        because µ==0 emitted no fractional part)."""
        z = _anchor(timestamp=datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC))
        o = _anchor(timestamp=datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=UTC))
        assert z.compute_hash() != o.compute_hash()


@pytest.mark.regression
class TestTimezoneDiscipline:
    """#1401 — strict on construction, lenient + normalizing on read."""

    def test_naive_timestamp_rejected_on_construction(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _anchor(timestamp=datetime(2026, 1, 1, 0, 0, 0))

    def test_non_utc_offset_normalized_to_utc(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        a = _anchor(timestamp=datetime(2026, 1, 1, 5, 30, 0, tzinfo=ist))
        # +05:30 05:30:00 is the same instant as +00:00 00:00:00.
        assert "2026-01-01T00:00:00.000000+00:00" in a._canonical_input()

    def test_from_dict_normalizes_naive_instead_of_raising(self) -> None:
        a = AuditAnchor.from_dict(
            {
                "anchor_id": "anc-naive",
                "sequence": 0,
                "agent_id": "g",
                "action": "x",
                "verification_level": "AUTO_APPROVED",
                "result": "ok",
                "timestamp": "2026-01-01T00:00:00",  # no offset
            }
        )
        assert a.timestamp.tzinfo is not None
        assert "2026-01-01T00:00:00.000000+00:00" in a._canonical_input()

    def test_to_dict_round_trip_preserves_hash(self) -> None:
        a = _anchor(timestamp=datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=UTC))
        a.seal()
        b = AuditAnchor.from_dict(a.to_dict())
        assert b.compute_hash() == a.compute_hash()
        assert b.verify_integrity()


@pytest.mark.regression
class TestCanonicalInputIsProductionSource:
    """#1404 — compute_hash hashes exactly _canonical_input()'s output."""

    def test_compute_hash_is_sha256_of_canonical_input(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 1, 0, 0, 0, 5, tzinfo=UTC),
            metadata={"k": "v"},
        )
        assert (
            a.compute_hash()
            == hashlib.sha256(a._canonical_input().encode()).hexdigest()
        )


@pytest.mark.regression
class TestTypedScalarMetadataWhitelist:
    """#1405 / #1403 — metadata typed scalars use the canonical whitelist."""

    def test_decimal_uuid_datetime_set_are_deterministic(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            metadata={
                "amount": Decimal("1.50"),
                "id": uuid.UUID(int=5),
                "when": datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
                "tags": {3, 1, 2},
            },
        )
        seg = a._canonical_input().rsplit("+00:00:", 1)[1]
        assert seg == (
            '{"amount":"1.50","id":"00000000-0000-0000-0000-000000000005",'
            '"tags":[1,2,3],"when":"2026-03-04T05:06:07+00:00"}'
        ), seg

    def test_non_whitelisted_metadata_raises_typeerror(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            metadata={"obj": object()},
        )
        with pytest.raises(TypeError):
            a.compute_hash()


@pytest.mark.regression
class TestBackwardCompatLadder:
    """verify_chain_integrity disambiguates pre-fix format from tampering."""

    def _single_anchor_chain(self, anchor: AuditAnchor) -> AuditChain:
        chain = AuditChain(chain_id="c")
        chain.anchors = [anchor]
        return chain

    def test_pre_fix_format_chain_reads_as_reseal_not_tampered(self) -> None:
        # An anchor whose hash changed under the fix (whole-second timestamp):
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.content_hash = a._compute_hash_prefix_format()  # sealed under OLD format
        ok, errors = self._single_anchor_chain(a).verify_chain_integrity()
        assert not ok
        assert any("pre-2026-06-20 canonical format" in e for e in errors), errors
        assert not any("tampered" in e for e in errors), errors

    def test_legacy_genesis_chain_still_recognized(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.content_hash = a._compute_hash_legacy()  # pre-2026-04-20 format
        ok, errors = self._single_anchor_chain(a).verify_chain_integrity()
        assert not ok
        assert any("legacy genesis sentinel" in e for e in errors), errors
        assert not any("tampered" in e for e in errors), errors

    def test_real_tampering_reads_as_tampered(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.seal()
        a.metadata = {"role": "HACKED"}  # mutate after sealing
        ok, errors = self._single_anchor_chain(a).verify_chain_integrity()
        assert not ok
        assert any("tampered" in e for e in errors), errors

    def test_current_format_chain_verifies_clean(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, 123456, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.seal()
        ok, errors = self._single_anchor_chain(a).verify_chain_integrity()
        assert ok, errors


@pytest.mark.regression
class TestEncoderFamilyConsistency:
    """#1403 — the ensure_ascii=True signing/hash family shares one typed-scalar
    policy (canonical_scalars); the delegate ensure_ascii=False encoder differs.
    """

    def test_serialize_for_signing_byte_identical_after_refactor(self) -> None:
        from kailash.trust.signing.crypto import serialize_for_signing

        # The documented example output is unchanged by the convert()→
        # canonical_scalars extraction.
        assert serialize_for_signing({"b": 2, "a": 1}) == '{"a":1,"b":2}'
        # Typed scalars encode via the shared whitelist (no default=str).
        out = serialize_for_signing({"d": Decimal("1.50"), "u": uuid.UUID(int=0)})
        assert out == ('{"d":"1.50","u":"00000000-0000-0000-0000-000000000000"}'), out

    def test_signing_family_rejects_non_whitelisted_uniformly(self) -> None:
        from kailash.trust.signing.crypto import serialize_for_signing

        with pytest.raises(TypeError):
            serialize_for_signing({"x": object()})

    def test_delegate_encoder_remains_ensure_ascii_false(self) -> None:
        from kailash.trust._json import canonical_json_dumps

        # Delegate family is raw UTF-8 (NOT \\uXXXX) — unchanged by this fix.
        assert canonical_json_dumps({"name": "café"}) == '{"name":"café"}'

    def test_canonical_scalars_shared_policy(self) -> None:
        # The exact policy the audit/fingerprint/signing paths now share.
        assert canonical_scalars({3, 1, 2}) == [1, 2, 3]
        assert canonical_scalars(Decimal("1.50")) == "1.50"
        assert canonical_scalars(uuid.UUID(int=0)) == (
            "00000000-0000-0000-0000-000000000000"
        )


@pytest.mark.regression
class TestAllowNanRejection:
    """Round-2: non-finite floats in metadata / payload MUST raise, matching
    serialize_for_signing + RFC-8259 (allow_nan=False), not emit invalid JSON."""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_audit_metadata_nonfinite_raises(self, bad: float) -> None:
        a = _anchor(timestamp=datetime(2026, 1, 1, tzinfo=UTC), metadata={"v": bad})
        with pytest.raises(ValueError):
            a.compute_hash()

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_trace_payload_nonfinite_raises(self, bad: float) -> None:
        ev = TraceEvent(
            event_id="e",
            event_type=TraceEventType.AGENT_STEP,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            run_id="r",
            agent_id="ag",
            cost_microdollars=0,
            payload={"x": bad},
        )
        with pytest.raises(ValueError):
            compute_trace_event_fingerprint(ev)


@pytest.mark.regression
class TestMetadataDatetimeAsymmetry:
    """Round-2: a datetime VALUE inside metadata renders bare isoformat() (no
    fraction at microsecond==0), while the anchor's own timestamp always emits
    six digits — the deliberate signing-family-contract asymmetry (issue #959
    vs #1400). Pinned so a future change to canonical_scalars is caught."""

    def test_metadata_datetime_is_bare_isoformat(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 16, 0, 0, tzinfo=UTC),
            metadata={"when": datetime(2026, 3, 4, 5, 6, 0, tzinfo=UTC)},
        )
        ci = a._canonical_input()
        # Anchor's own timestamp: six digits.
        assert "16:00:00.000000+00:00" in ci, ci
        # Metadata datetime at microsecond==0: NO fractional part.
        assert '"when":"2026-03-04T05:06:00+00:00"' in ci, ci
        assert "05:06:00.000000" not in ci, ci

    def test_canonical_scalars_datetime_bare(self) -> None:
        assert canonical_scalars(datetime(2026, 3, 4, 5, 6, 0, tzinfo=UTC)) == (
            "2026-03-04T05:06:00+00:00"
        )


@pytest.mark.regression
class TestFromDictReSealSurfacing:
    """Round-2: AuditChain.from_dict surfaces the per-anchor errors in the
    raised message AND a machine-readable reseal_only flag, distinguishing a
    benign pre-canonical-fix chain from possible tampering (fail-closed either
    way)."""

    def _prefix_sealed_chain_dict(self) -> dict:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.content_hash = a._compute_hash_prefix_format()  # pre-fix seal
        return {"chain_id": "c", "anchors": [a.to_dict()]}

    def test_pre_fix_chain_surfaces_reseal_guidance(self) -> None:
        with pytest.raises(PactError) as exc:
            AuditChain.from_dict(self._prefix_sealed_chain_dict())
        assert exc.value.details["reseal_only"] is True
        msg = str(exc.value)
        assert "re-seal" in msg.lower()
        assert "NOT tampering" in msg

    def test_tampered_chain_reads_possible_tampering(self) -> None:
        a = _anchor(
            timestamp=datetime(2026, 1, 15, 11, 0, 0, 123456, tzinfo=UTC),
            metadata={"role": "x"},
        )
        a.seal()
        a.metadata = {"role": "HACKED"}
        with pytest.raises(PactError) as exc:
            AuditChain.from_dict({"chain_id": "c", "anchors": [a.to_dict()]})
        assert exc.value.details["reseal_only"] is False
        assert "possible tampering" in str(exc.value)


@pytest.mark.regression
class TestPreFixNaiveNonUtcLimitation:
    """Round-2: documents the KNOWN, NARROW limitation — a pre-fix anchor sealed
    with an EXPLICIT naive or non-UTC timestamp cannot be byte-reproduced after
    load-time normalization (lossy), so it reads as a hash mismatch rather than
    a re-seal advisory. Re-seal is the correct disposition regardless. The
    common UTC default-path population IS recognized correctly (see
    TestBackwardCompatLadder). This test PINS the documented behavior so a
    future change that silently alters it is caught."""

    def _load_prefix_naive(self) -> tuple:
        import json

        from kailash.trust.pact.audit import GENESIS_HASH

        # Reproduce the EXACT pre-fix bytes for a NAIVE timestamp (bare
        # isoformat, no offset), then load via from_dict (which normalizes).
        naive = "2026-01-01T12:00:00"
        meta = {"role": "x"}
        content = (
            f"anc-naive:0:{GENESIS_HASH}:g:x:AUTO_APPROVED::ok:{naive}:"
            + json.dumps(
                meta,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
                ensure_ascii=True,
            )
        )
        stored = hashlib.sha256(content.encode()).hexdigest()
        d = {
            "anchor_id": "anc-naive",
            "sequence": 0,
            "previous_hash": None,
            "agent_id": "g",
            "action": "x",
            "verification_level": "AUTO_APPROVED",
            "envelope_id": "",
            "result": "ok",
            "metadata": meta,
            "timestamp": naive,
            "content_hash": stored,
        }
        loaded = AuditAnchor.from_dict(d)
        chain = AuditChain(chain_id="c")
        chain.anchors = [loaded]
        return chain.verify_chain_integrity()

    def test_naive_prefix_anchor_documented_as_mismatch(self) -> None:
        ok, errors = self._load_prefix_naive()
        assert not ok
        # Documented limitation: the lossy naive->UTC normalization means the
        # original no-offset bytes are unrecoverable, so it reads as a mismatch
        # (NOT a re-seal advisory). Re-seal is still the correct action.
        assert any("tampered" in e for e in errors), errors

    def test_from_dict_loads_naive_without_raising_on_normalization(self) -> None:
        # The naive->UTC normalization itself does NOT raise (lenient on read);
        # the integrity check is what surfaces the mismatch.
        a = AuditAnchor.from_dict(
            {
                "anchor_id": "a",
                "sequence": 0,
                "agent_id": "g",
                "action": "x",
                "verification_level": "AUTO_APPROVED",
                "result": "ok",
                "timestamp": "2026-01-01T12:00:00",
            }
        )
        assert a.timestamp.tzinfo is not None
        assert a.timestamp.isoformat() == "2026-01-01T12:00:00+00:00"

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #1258 - the two trust-layer canonical-JSON encoders.

The trust layer ships TWO canonical-JSON encoders, each matching a DIFFERENT
Rust ``serde`` byte contract for a DIFFERENT subsystem:

* ``kailash.trust._json.canonical_json_dumps`` -- ``kailash.delegate.*``
  (SPEC-09 S8.2). ``ensure_ascii=False`` -> RAW UTF-8 output, matching
  ``serde_json``'s default ``to_string``.
* ``kailash.trust.signing.crypto.serialize_for_signing`` -- trust-plane
  signing (Ed25519 / W3C-VC / multi-sig / PACT envelopes). ``ensure_ascii=True``
  (``json.dumps`` default) -> ASCII-escaped ``\\uXXXX`` output, matching the
  pinned cross-SDK fixture ``tests/test-vectors/trust-plane-canonical.json``
  (issue #959).

The two NEVER cross-mix and the divergence is INTENTIONAL -- unifying them
would be a breaking cross-SDK signing-format migration requiring coordinated
Rust-side regeneration (issue #1258 acceptance criterion 3; disposition: do
NOT unify).

This module pins:

1. The delegate encoder's non-ASCII byte-vectors via the vendored fixture
   ``tests/test-vectors/delegate-canonical.json`` (the #959 fixture already
   pins the signing encoder; #1258 extended it with V8/V9/V10).
2. The two-encoder divergence contract (agree on ASCII, diverge on non-ASCII).
3. The no-Unicode-normalization invariant (NFC != NFD) for BOTH encoders.
4. The ASCII-only-output contract: signing encoder output is ASCII-only;
   delegate encoder output is raw UTF-8 for non-ASCII.

These are BEHAVIORAL pins (call the function, assert the bytes) -- not
source-greps -- per ``rules/testing.md`` "Behavioral Regression Tests Over
Source-Grep". The NFC/NFD ``é`` pair is built via ``unicodedata.normalize`` so the two
forms are byte-distinct BY CONSTRUCTION; astral code points use ``\\U``
escapes. This prevents an editor or formatter from silently collapsing the
NFC-vs-NFD distinction these tests assert.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from kailash.trust._json import canonical_json_dumps
from kailash.trust.signing.crypto import serialize_for_signing

_DELEGATE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "test-vectors"
    / "delegate-canonical.json"
)

# Non-ASCII building blocks. The NFC/NFD pair is constructed via
# unicodedata.normalize so the two forms are byte-distinct BY CONSTRUCTION
# (a raw "é" literal pair risks an editor/formatter normalizing both to one
# form, silently defeating the NFC-vs-NFD distinction these tests assert);
# astral code points use explicit \U escapes.
_BMP_CJK = "漢字"  # CJK two-char string
_NFC_E_ACUTE = unicodedata.normalize("NFC", "é")  # -> U+00E9 (1 code point)
_NFD_E_ACUTE = unicodedata.normalize("NFD", "é")  # -> U+0065 U+0301 (2 code points)
_ASTRAL_EMOJI = "\U0001f389"  # party popper
_ASTRAL_KEY = "\U0001d11e"  # musical symbol G clef


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cross-SDK fixture parity for the delegate encoder (mirror of the #959
# TestCrossSDKFixtureParity for serialize_for_signing).
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestDelegateCanonicalFixtureParity:
    """Iterate ``tests/test-vectors/delegate-canonical.json`` and assert every
    vector's pinned RAW-UTF-8 canonical bytes / SHA-256 reproduce via
    ``canonical_json_dumps``. The sibling kailash-rs ``serde_json`` path
    consumes the same file per ``cross-sdk-inspection.md`` Rule 4a."""

    @pytest.fixture(scope="class")
    def fixture(self) -> dict:
        assert _DELEGATE_FIXTURE_PATH.exists(), (
            f"cross-SDK delegate fixture missing at {_DELEGATE_FIXTURE_PATH}; "
            "this fixture is the cross-SDK byte contract per issue #1258"
        )
        return json.loads(_DELEGATE_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_loads_with_required_floor(self, fixture: dict) -> None:
        assert fixture["contract"] == "delegate-canonical-bytes"
        # >=3 non-ASCII byte-vectors + sentinel per cross-sdk-inspection.md Rule 4.
        assert len(fixture["vectors"]) >= 6

    def test_every_vector_canonical_json_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            actual = canonical_json_dumps(v["input_repr"])
            assert actual == v["expected_canonical_json"], (
                f"vector {v['name']}: canonical-bytes divergence - "
                f"got {actual!r}, expected {v['expected_canonical_json']!r}"
            )

    def test_every_vector_sha256_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            actual = _sha256_hex(canonical_json_dumps(v["input_repr"]))
            assert actual == v["expected_sha256"], (
                f"vector {v['name']}: SHA-256 divergence - "
                f"got {actual}, expected {v['expected_sha256']}"
            )

    def test_nfc_and_nfd_vectors_are_byte_distinct(self, fixture: dict) -> None:
        """The encoder does NOT Unicode-normalize: the NFC and NFD vectors MUST
        pin DIFFERENT canonical bytes / SHA-256 (else a future normalization
        refactor would silently change every existing signing pre-image)."""
        by_name = {v["name"]: v for v in fixture["vectors"]}
        nfc = by_name["D3_unicode_nfc_composed_raw"]
        nfd = by_name["D4_unicode_nfd_decomposed_raw"]
        assert nfc["expected_canonical_json"] != nfd["expected_canonical_json"]
        assert nfc["expected_sha256"] != nfd["expected_sha256"]


# ---------------------------------------------------------------------------
# Two-encoder divergence contract - the heart of #1258.
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestTwoEncoderDivergenceContract:
    """The delegate (raw-UTF-8) and signing (ASCII-escaped) encoders AGREE on
    pure-ASCII payloads and DIVERGE on every non-ASCII payload. This is the
    intentional, documented per-subsystem split (#1258)."""

    _ASCII_PAYLOAD = {"agent": "a1", "action": "approve", "cost": 42}
    _NON_ASCII_PAYLOADS = [
        {"name": _BMP_CJK},  # BMP CJK
        {"name": _NFC_E_ACUTE},  # NFC composed (U+00E9)
        {"name": _NFD_E_ACUTE},  # NFD decomposed (e + U+0301)
        {"flag": _ASTRAL_EMOJI},  # astral emoji
        {_ASTRAL_KEY: "clef"},  # astral object KEY
    ]

    def test_ascii_payload_encoders_agree(self) -> None:
        assert canonical_json_dumps(self._ASCII_PAYLOAD) == serialize_for_signing(
            self._ASCII_PAYLOAD
        )

    @pytest.mark.parametrize("payload", _NON_ASCII_PAYLOADS)
    def test_non_ascii_payload_encoders_diverge(self, payload: dict) -> None:
        delegate = canonical_json_dumps(payload)
        signing = serialize_for_signing(payload)
        assert delegate != signing, (
            f"encoders MUST diverge on non-ASCII {payload!r}: "
            f"delegate={delegate!r} signing={signing!r}"
        )

    @pytest.mark.parametrize("payload", _NON_ASCII_PAYLOADS)
    def test_signing_output_is_ascii_only_delegate_is_raw(self, payload: dict) -> None:
        """``serialize_for_signing`` (ensure_ascii=True) MUST emit ASCII-only
        bytes; ``canonical_json_dumps`` (ensure_ascii=False) MUST emit raw
        non-ASCII for the same input. This is the load-bearing behavioral
        signature of the two contracts (not a source-grep)."""
        assert serialize_for_signing(payload).isascii(), (
            "serialize_for_signing MUST be ASCII-only (ensure_ascii=True) for "
            "cross-SDK signing byte parity"
        )
        assert not canonical_json_dumps(payload).isascii(), (
            "canonical_json_dumps MUST emit raw UTF-8 (ensure_ascii=False) for "
            "non-ASCII, matching serde_json's default to_string"
        )

    def test_both_encoders_preserve_nfc_nfd_distinction(self) -> None:
        """Neither encoder Unicode-normalizes: NFC (U+00E9) and NFD
        (U+0065 U+0301) are distinct pre-images on BOTH encoders."""
        nfc = {"name": _NFC_E_ACUTE}
        nfd = {"name": _NFD_E_ACUTE}
        assert canonical_json_dumps(nfc) != canonical_json_dumps(nfd)
        assert serialize_for_signing(nfc) != serialize_for_signing(nfd)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1258 (follow-up) - the four MCP protocol-message
canonical-JSON encoders.

``kailash_mcp.protocol.messages`` ships FOUR ``to_canonical_json`` encoders
(``JsonRpcError`` / ``JsonRpcRequest`` / ``JsonRpcResponse`` / ``McpToolInfo``),
each emitting the cross-SDK canonical wire form per SPEC-01 §7 / SPEC-09 §2.1.
All four use ``json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`` -> RAW UTF-8 output, matching ``serde_json``'s default
``to_string`` on the Rust side so both SDKs produce byte-identical canonical
JSON.

This is the MCP-package counterpart to the trust-layer encoder pins in
``tests/regression/test_issue_1258_canonical_encoder_parity.py`` (PR #1269,
which covered ``canonical_json_dumps`` + ``serialize_for_signing``). Issue #1258
explicitly carved the 4th-encoder family (MCP) into a separate shard because it
lives in a separate package / spec / Rust counterpart.

This module pins:

1. The byte contract via the vendored fixture
   ``tests/test-vectors/mcp-messages-canonical.json`` (every vector's RAW-UTF-8
   canonical bytes + SHA-256 reproduce via ``<type>.from_dict(...).
   to_canonical_json()``). The sibling kailash-rs ``serde_json`` path consumes
   the same file per ``cross-sdk-inspection.md`` Rule 4a.
2. The no-Unicode-normalization invariant (NFC != NFD) - M3 vs M4.
3. The ``ensure_ascii=False`` raw-UTF-8 contract for ALL FOUR encoders - a
   behavioral guard that fails loudly if a future edit flips any encoder to
   ASCII-escaped output (which would break byte-parity with serde_json). This
   is the disposition for #1258 acceptance criterion 3: do NOT unify / do NOT
   flip ``ensure_ascii``.
4. Round-trip stability: ``from_canonical_json`` parses the pinned bytes back
   and re-serializes to the identical canonical form.

These are BEHAVIORAL pins (call the encoder, assert the bytes) - not
source-greps - per ``rules/testing.md`` "Behavioral Regression Tests Over
Source-Grep".
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest
from kailash_mcp.protocol.messages import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpToolInfo,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "test-vectors" / "mcp-messages-canonical.json"
)

# Map the fixture's ``type`` discriminator to the concrete class so each vector
# is reconstructed via the same from_dict -> to_canonical_json surface a
# cross-SDK consumer uses.
_TYPES = {
    "JsonRpcError": JsonRpcError,
    "JsonRpcRequest": JsonRpcRequest,
    "JsonRpcResponse": JsonRpcResponse,
    "McpToolInfo": McpToolInfo,
}


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_from_vector(vector: dict) -> str:
    cls = _TYPES[vector["type"]]
    obj = cls.from_dict(vector["input_wire"])
    return obj.to_canonical_json()


@pytest.mark.regression
class TestMcpCanonicalFixtureParity:
    """Iterate ``tests/test-vectors/mcp-messages-canonical.json`` and assert
    every vector's pinned RAW-UTF-8 canonical bytes / SHA-256 reproduce."""

    @pytest.fixture(scope="class")
    @classmethod
    def fixture(cls) -> dict:
        # classmethod form (not an instance method) per pytest's
        # class-scoped-fixture-as-instance-method deprecation
        # (PytestRemovedIn10Warning) — a class-scoped fixture defined as an
        # instance method runs against a throwaway `self` (a NEW instance
        # per test), so instance-attribute writes would silently vanish.
        # This fixture only returns a value (no `self.` writes), but the
        # classmethod form is pytest's documented forward-compatible shape
        # and eliminates the warning without changing behavior — the fixture
        # value is still injected into each test method identically.
        assert _FIXTURE_PATH.exists(), (
            f"cross-SDK MCP canonical fixture missing at {_FIXTURE_PATH}; "
            "this fixture is the cross-SDK byte contract per issue #1258"
        )
        return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_contract_and_floor(self, fixture: dict) -> None:
        assert fixture["contract"] == "mcp-messages-canonical-bytes"
        # >=3 non-ASCII byte-vectors + sentinel per cross-sdk-inspection.md
        # Rule 4.
        assert len(fixture["vectors"]) >= 6
        non_ascii = [
            v for v in fixture["vectors"] if not v["expected_canonical_json"].isascii()
        ]
        assert len(non_ascii) >= 3, "need >=3 non-ASCII byte-vectors"

    def test_all_four_encoders_covered(self, fixture: dict) -> None:
        """Every one of the four ``to_canonical_json`` encoders MUST have at
        least one pinned vector (the orphan-coverage guard for this family)."""
        covered = {v["type"] for v in fixture["vectors"]}
        assert covered == set(_TYPES), (
            f"fixture covers {sorted(covered)}; "
            f"missing {sorted(set(_TYPES) - covered)}"
        )

    def test_every_vector_canonical_json_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            actual = _canonical_from_vector(v)
            assert actual == v["expected_canonical_json"], (
                f"vector {v['name']}: canonical-bytes divergence - "
                f"got {actual!r}, expected {v['expected_canonical_json']!r}"
            )

    def test_every_vector_sha256_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            actual = _sha256_hex(_canonical_from_vector(v))
            assert actual == v["expected_sha256"], (
                f"vector {v['name']}: SHA-256 divergence - "
                f"got {actual}, expected {v['expected_sha256']}"
            )

    def test_nfc_and_nfd_vectors_are_byte_distinct(self, fixture: dict) -> None:
        """The encoders do NOT Unicode-normalize: the NFC and NFD vectors MUST
        pin DIFFERENT canonical bytes / SHA-256 (else a future normalization
        refactor would silently change every existing pre-image)."""
        by_name = {v["name"]: v for v in fixture["vectors"]}
        nfc = by_name["M3_request_nfc_composed"]
        nfd = by_name["M4_request_nfd_decomposed"]
        assert nfc["expected_canonical_json"] != nfd["expected_canonical_json"]
        assert nfc["expected_sha256"] != nfd["expected_sha256"]
        # And the encoder reproduces the distinction live.
        assert _canonical_from_vector(nfc) != _canonical_from_vector(nfd)

    def test_round_trip_through_from_canonical_json(self, fixture: dict) -> None:
        """``from_canonical_json`` parses the pinned bytes and re-serializes to
        the identical canonical form (parse/emit stability)."""
        for v in fixture["vectors"]:
            cls = _TYPES[v["type"]]
            obj = cls.from_canonical_json(v["expected_canonical_json"])
            assert (
                obj.to_canonical_json() == v["expected_canonical_json"]
            ), f"vector {v['name']}: round-trip divergence"


@pytest.mark.regression
class TestMcpEncodersRawUtf8Contract:
    """Behavioral guard for issue #1258 acceptance criterion 3: ALL FOUR MCP
    encoders MUST keep ``ensure_ascii=False`` (raw UTF-8). A future edit that
    flips any encoder to ASCII-escaped output would break byte-parity with the
    Rust ``serde_json`` default and MUST fail here loudly."""

    _CJK = "漢字"  # BMP CJK; raw UTF-8 must appear, never \\u escapes

    def test_jsonrpc_error_raw_utf8(self) -> None:
        out = JsonRpcError(code=-32000, message=self._CJK).to_canonical_json()
        assert self._CJK in out
        assert "\\u" not in out

    def test_jsonrpc_request_raw_utf8(self) -> None:
        out = JsonRpcRequest(
            method="notify", params={"name": self._CJK}, id=1
        ).to_canonical_json()
        assert self._CJK in out
        assert "\\u" not in out

    def test_jsonrpc_response_raw_utf8(self) -> None:
        out = JsonRpcResponse(id=1, result={"flag": self._CJK}).to_canonical_json()
        assert self._CJK in out
        assert "\\u" not in out

    def test_mcp_tool_info_raw_utf8(self) -> None:
        out = McpToolInfo(
            name="t", description=self._CJK, input_schema={"k": self._CJK}
        ).to_canonical_json()
        assert self._CJK in out
        assert "\\u" not in out

    def test_no_unicode_normalization_in_encoder(self) -> None:
        """An NFC pre-image and its NFD decomposition MUST serialize to
        byte-distinct canonical forms through the live encoder (no
        normalization step)."""
        nfc = unicodedata.normalize("NFC", "é")
        nfd = unicodedata.normalize("NFD", "é")
        assert nfc != nfd  # distinct by construction
        out_nfc = JsonRpcError(code=-32000, message=nfc).to_canonical_json()
        out_nfd = JsonRpcError(code=-32000, message=nfd).to_canonical_json()
        assert out_nfc != out_nfd

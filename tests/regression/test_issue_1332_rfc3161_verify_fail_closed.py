# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Regression: issue #1332 — RFC-3161 ``verify_timestamp`` must NOT fail open.

Before the fix, ``RFC3161TimestampAuthority.verify_timestamp`` returned ``True``
with **zero cryptographic verification** whenever ``rfc3161ng`` was importable:
the docstring promised "full ASN.1 verification" but the body was a bare
``return True``. A forged/tampered token whose ``source``/``authority`` metadata
happened to match the configured TSA was accepted as valid (security fail-open).

These tests pin the corrected **fail-closed** contract:

1. Metadata-match alone never returns ``True`` (the core security regression).
2. Missing verification material (no library / no raw DER token / no trusted
   certificate) returns ``False``.
3. With all material present, the result is the genuine cryptographic verdict —
   a tampered token (message-imprint mismatch) is rejected, a valid token is
   accepted. ``rfc3161ng`` is simulated via a stub module so the dispatch logic
   is exercised deterministically without a live TSA / the optional dependency
   (which is not installed in CI).

``verify_anchor`` is also covered: it MUST thread ``response.raw_response`` into
``verify_timestamp`` (dropping it was the architectural gap that forced the
fail-open stub).
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pytest

from kailash.trust.signing.timestamping import (
    LocalTimestampAuthority,
    RFC3161TimestampAuthority,
    TimestampAnchorManager,
    TimestampRequest,
    TimestampResponse,
    TimestampSource,
    TimestampToken,
)

TSA_URL = "https://tsa.example.test/tsr"
GOOD_HASH = "a" * 64  # 32-byte sha256 imprint, hex
TAMPERED_HASH = "b" * 64
FAKE_CERT = b"-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n"
RAW_DER = b"\x30\x82\x01\x00fake-der-timestamp-token"


def _rfc3161_token(
    hash_value: str = GOOD_HASH, *, authority: str = TSA_URL
) -> TimestampToken:
    return TimestampToken(
        token_id="tok-1",
        hash_value=hash_value,
        timestamp=datetime.now(timezone.utc),
        source=TimestampSource.RFC3161,
        authority=authority,
        nonce="00112233445566778899aabbccddeeff",
    )


@pytest.fixture
def fake_rfc3161ng(monkeypatch):
    """Inject a stub ``rfc3161ng`` whose ``check_timestamp`` performs a real
    message-imprint comparison.

    The stub mirrors the library contract: it RAISES on a mismatch (the library
    raises rather than returning False), so a token whose hash_value differs
    from the imprint the TSA signed is rejected by the production catch-log-False
    path. Production passes the already-computed imprint via ``digest=`` (NOT
    ``data=`` — ``data`` would be re-hashed by the real library); the stub
    asserts ``digest`` is bound and compares it against the signed imprint. The
    real-library round-trip is covered by
    ``test_issue_1332_rfc3161_live_binding.py``.
    """

    class _ValidationError(Exception):
        pass

    def check_timestamp(
        tst, *, certificate, hashname, digest=None, data=None, **kwargs
    ):
        # Trust anchor + materials must be present (production already gates
        # these, but assert the contract the library would enforce).
        assert certificate == FAKE_CERT
        assert hashname == "sha256"
        assert isinstance(tst, (bytes, bytearray))
        # Production MUST pass the pre-computed imprint as digest=, not data=
        # (data= would be double-hashed by the real library). Guard the binding.
        assert digest is not None, "production must pass digest=, not data="
        assert data is None, "production must NOT pass data= (it would re-hash)"
        # Simulate imprint verification: the raw token encodes the imprint it
        # was issued for; mismatch => library raises.
        signed_imprint = bytes.fromhex(GOOD_HASH)
        if digest != signed_imprint:
            raise _ValidationError("message imprint does not match")
        return True

    module = types.ModuleType("rfc3161ng")
    module.check_timestamp = check_timestamp  # type: ignore[attr-defined]
    module.ValidationError = _ValidationError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rfc3161ng", module)
    return module


# --------------------------------------------------------------------------- #
# Core security regression: metadata-match alone NEVER returns True.
# --------------------------------------------------------------------------- #


async def test_verify_fails_closed_when_rfc3161ng_absent(monkeypatch):
    """Without the verification library, a metadata-matching token is rejected.

    This is the exact fail-open the issue reported: previously this returned
    True. It MUST now return False — an unverifiable token is not valid.
    """
    monkeypatch.setitem(sys.modules, "rfc3161ng", None)  # force ImportError path
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token()
    assert await authority.verify_timestamp(token, RAW_DER) is False


async def test_verify_rejects_wrong_source(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token()
    token.source = TimestampSource.LOCAL
    assert await authority.verify_timestamp(token, RAW_DER) is False


async def test_verify_rejects_wrong_authority(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token(authority="https://evil.example.test/tsr")
    assert await authority.verify_timestamp(token, RAW_DER) is False


# --------------------------------------------------------------------------- #
# Missing verification material -> fail closed (even with the library present).
# --------------------------------------------------------------------------- #


async def test_verify_fails_closed_without_raw_token(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token()
    # No raw DER token -> cannot verify a TSA signature -> reject.
    assert await authority.verify_timestamp(token, None) is False


async def test_verify_fails_closed_without_certificate(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL)  # no trust anchor
    token = _rfc3161_token()
    assert await authority.verify_timestamp(token, RAW_DER) is False


async def test_verify_fails_closed_on_non_hex_hash(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token(hash_value="not-hex!!")
    assert await authority.verify_timestamp(token, RAW_DER) is False


# --------------------------------------------------------------------------- #
# All material present -> genuine cryptographic verdict.
# --------------------------------------------------------------------------- #


async def test_verify_accepts_valid_token(fake_rfc3161ng):
    """Valid token + trusted cert + raw DER + matching imprint -> True."""
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token(hash_value=GOOD_HASH)
    assert await authority.verify_timestamp(token, RAW_DER) is True


async def test_verify_rejects_tampered_imprint(fake_rfc3161ng):
    """A token whose hash_value was altered (imprint mismatch) is rejected.

    Acceptance criterion #2: a tampered token whose source/authority still
    match the configured TSA is rejected.
    """
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token(hash_value=TAMPERED_HASH)
    assert await authority.verify_timestamp(token, RAW_DER) is False


# --------------------------------------------------------------------------- #
# verify_anchor threads response.raw_response into verify_timestamp.
# --------------------------------------------------------------------------- #


def _rfc3161_response(raw_response: bytes | None) -> TimestampResponse:
    token = _rfc3161_token()
    request = TimestampRequest(hash_value=GOOD_HASH, nonce=token.nonce)
    return TimestampResponse(
        request=request, token=token, raw_response=raw_response, verified=True
    )


async def test_verify_anchor_threads_raw_response(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    manager = TimestampAnchorManager(primary=authority, local_fallback=False)
    # raw_response present + valid -> verified True
    assert await manager.verify_anchor(_rfc3161_response(RAW_DER)) is True


async def test_verify_anchor_fails_closed_without_raw_response(fake_rfc3161ng):
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    manager = TimestampAnchorManager(primary=authority, local_fallback=False)
    # raw_response dropped -> RFC3161 path cannot verify -> False.
    assert await manager.verify_anchor(_rfc3161_response(None)) is False


async def test_verify_anchor_rejects_imprint_substitution(fake_rfc3161ng):
    """A token whose imprint differs from the anchored request hash is rejected.

    Even with a (simulated) legitimately-TSA-signed token over the substituted
    imprint, ``verify_anchor`` MUST reject when ``token.hash_value`` diverges
    from ``request.hash_value`` — otherwise an attacker-chosen-but-TSA-signed
    imprint could be substituted for the one the caller actually anchored.
    """
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    manager = TimestampAnchorManager(primary=authority, local_fallback=False)
    # Build a response whose token anchors GOOD_HASH (the imprint the fake
    # check_timestamp accepts) but whose request anchored a DIFFERENT hash.
    token = _rfc3161_token(hash_value=GOOD_HASH)
    request = TimestampRequest(hash_value=TAMPERED_HASH, nonce=token.nonce)
    substituted = TimestampResponse(
        request=request, token=token, raw_response=RAW_DER, verified=True
    )
    assert await manager.verify_anchor(substituted) is False


# --------------------------------------------------------------------------- #
# Regression guard: the working local-authority round-trip still verifies.
# --------------------------------------------------------------------------- #


async def test_verify_timestamp_token_helper_threads_raw_token(fake_rfc3161ng):
    """The module-level ``verify_timestamp_token`` helper forwards ``raw_token``.

    Without the forwarded raw DER token the RFC-3161 path fails closed; with it
    (valid imprint) it verifies — proving the helper's optional ``raw_token``
    argument reaches the authority rather than being dropped.
    """
    from kailash.trust.signing.timestamping import verify_timestamp_token

    authority = RFC3161TimestampAuthority(TSA_URL, certificate=FAKE_CERT)
    token = _rfc3161_token(hash_value=GOOD_HASH)
    assert await verify_timestamp_token(token, authority) is False  # no raw_token
    assert await verify_timestamp_token(token, authority, RAW_DER) is True


async def test_local_authority_roundtrip_unaffected():
    """The new raw_token parameter must not break self-contained local tokens."""
    authority = LocalTimestampAuthority()
    response = await authority.get_timestamp(GOOD_HASH)
    assert await authority.verify_timestamp(response.token) is True
    # Tampered local token is rejected.
    response.token.hash_value = TAMPERED_HASH
    assert await authority.verify_timestamp(response.token) is False

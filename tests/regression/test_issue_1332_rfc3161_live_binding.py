# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Live binding regression: issue #1332 — real ``rfc3161ng`` verification.

The companion ``test_issue_1332_rfc3161_verify_fail_closed.py`` exercises the
fail-closed dispatch with a STUB ``rfc3161ng`` (the optional dependency is not
installed in the default CI matrix). A stub cannot prove the real library's
argument binding — and it didn't: the first cut passed the pre-computed message
imprint as ``data=`` (which ``rfc3161ng.check_timestamp`` RE-HASHES), so every
valid token would have been rejected. The fix passes the imprint as ``digest=``.

This module pins the real-library round-trip against committed fixtures minted
offline with ``openssl ts`` (a self-signed TSA cert with the ``timeStamping``
EKU + a real signed RFC-3161 ``TimeStampToken`` over a known SHA-256 imprint):

- ``tests/fixtures/rfc3161/tsa-cert.pem``   — the trusted TSA certificate
- ``tests/fixtures/rfc3161/valid-token.der``— a real DER ``TimeStampToken``
- ``tests/fixtures/rfc3161/imprint.hex``    — the SHA-256 imprint it covers

The test is SKIPPED when ``rfc3161ng`` is not installed, so the default offline
suite stays green; CI installs the ``rfc3161`` extra so this runs there (see
``.github/workflows/trust-tests.yml``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

rfc3161ng = pytest.importorskip(
    "rfc3161ng",
    reason="rfc3161 extra not installed (pip install 'kailash[rfc3161]')",
)

from kailash.trust.signing.timestamping import (  # noqa: E402
    RFC3161TimestampAuthority,
    TimestampAnchorManager,
    TimestampRequest,
    TimestampResponse,
    TimestampSource,
    TimestampToken,
)

_FIX = Path(__file__).parent.parent / "fixtures" / "rfc3161"
TSA_URL = "https://tsa.example.test/tsr"


def _load():
    cert = (_FIX / "tsa-cert.pem").read_bytes()
    der = (_FIX / "valid-token.der").read_bytes()
    imprint = (_FIX / "imprint.hex").read_text().strip()
    return cert, der, imprint


def _token(imprint: str) -> TimestampToken:
    return TimestampToken(
        token_id="live",
        hash_value=imprint,
        timestamp=datetime.now(timezone.utc),
        source=TimestampSource.RFC3161,
        authority=TSA_URL,
        nonce="00ff",
    )


@pytest.mark.regression
async def test_real_rfc3161ng_verifies_valid_token():
    """A real TSA-signed token over the anchored imprint verifies True.

    This is the live proof the ``digest=`` binding is correct — with the real
    library, a genuine token cryptographically verifies. (The pre-fix ``data=``
    binding returned False here, which is the bug this test locks out.)
    """
    cert, der, imprint = _load()
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=cert)
    assert await authority.verify_timestamp(_token(imprint), der) is True


@pytest.mark.regression
async def test_real_rfc3161ng_rejects_tampered_imprint():
    """A token whose recorded imprint differs from the TSA-signed one is rejected."""
    cert, der, imprint = _load()
    tampered = "f" * 64 if imprint != "f" * 64 else "e" * 64
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=cert)
    assert await authority.verify_timestamp(_token(tampered), der) is False


@pytest.mark.regression
async def test_real_rfc3161ng_rejects_untrusted_certificate():
    """A token verified against the WRONG trust anchor is rejected (fail-closed)."""
    _, der, imprint = _load()
    # A different self-signed cert is not the TSA that signed the token.
    wrong_cert = (
        b"-----BEGIN CERTIFICATE-----\nnot-the-tsa\n-----END CERTIFICATE-----\n"
    )
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=wrong_cert)
    assert await authority.verify_timestamp(_token(imprint), der) is False


@pytest.mark.regression
async def test_real_rfc3161ng_through_verify_anchor():
    """The full public path (manager.verify_anchor) verifies a real token."""
    cert, der, imprint = _load()
    authority = RFC3161TimestampAuthority(TSA_URL, certificate=cert)
    manager = TimestampAnchorManager(primary=authority, local_fallback=False)
    request = TimestampRequest(hash_value=imprint, nonce="00ff")
    response = TimestampResponse(
        request=request, token=_token(imprint), raw_response=der, verified=True
    )
    assert await manager.verify_anchor(response) is True

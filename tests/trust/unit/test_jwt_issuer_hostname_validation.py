# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for JWT issuer hostname validation (issue #613).

Closes CodeQL finding ``py/incomplete-url-substring-sanitization`` at
``src/kailash/trust/auth/jwt.py:364-370``. The prior implementation used
``"github.com" in issuer_lower`` which is bypassed by crafted issuers
such as ``https://evilgithub.com`` or ``https://attacker.example/?host=
login.microsoftonline.com``. The fix parses the issuer as a URL and
compares the ``hostname`` against a trusted-host allowlist with
hostname-equality or hostname-suffix (``.trusted``) match only.
"""

from __future__ import annotations

from kailash.trust.auth.jwt import JWTConfig, JWTValidator


def _validator() -> JWTValidator:
    return JWTValidator(JWTConfig(secret="x" * 32))


class TestIssuerHostnameValidation:
    def test_trusted_issuer_microsoft(self) -> None:
        v = _validator()
        assert (
            v._determine_provider("https://login.microsoftonline.com/TENANT/v2.0")
            == "azure"
        )

    def test_trusted_issuer_google(self) -> None:
        v = _validator()
        assert v._determine_provider("https://accounts.google.com") == "google"

    def test_trusted_issuer_apple(self) -> None:
        v = _validator()
        assert v._determine_provider("https://appleid.apple.com") == "apple"

    def test_trusted_issuer_github(self) -> None:
        v = _validator()
        assert v._determine_provider("https://github.com") == "github"

    def test_trusted_issuer_github_subdomain(self) -> None:
        # Subdomains of trusted hosts match via the hostname-suffix check.
        v = _validator()
        assert (
            v._determine_provider("https://token.actions.githubusercontent.com/foo")
            == "github"
        )

    # --- Bypass payloads from CodeQL py/incomplete-url-substring-sanitization ---

    def test_substring_bypass_evilgithub_rejected(self) -> None:
        """``evilgithub.com`` MUST NOT match ``github.com``."""
        v = _validator()
        assert v._determine_provider("https://evilgithub.com/token") == "local"

    def test_substring_bypass_microsoft_prefix_rejected(self) -> None:
        v = _validator()
        assert (
            v._determine_provider("https://login.microsoftonline.com.evil/path")
            == "local"
        )

    def test_substring_bypass_host_in_path_rejected(self) -> None:
        """Trusted host name appearing in the path, NOT the host, is rejected."""
        v = _validator()
        assert (
            v._determine_provider("https://attacker.example/login.microsoftonline.com")
            == "local"
        )

    def test_substring_bypass_host_in_query_rejected(self) -> None:
        v = _validator()
        assert (
            v._determine_provider("https://attacker.example/?host=accounts.google.com")
            == "local"
        )

    def test_non_url_issuer_returns_local(self) -> None:
        """Non-URL issuers are rejected into the default 'local' provider
        — trust is only granted when we can parse a hostname."""
        v = _validator()
        assert v._determine_provider("github.com") == "local"
        assert v._determine_provider("") == "local"
        assert v._determine_provider("not-a-url") == "local"

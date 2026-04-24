# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #617 — SHA-256 → fingerprint_secret sweep.

Asserts every call site listed in #617 acceptance routes through
`fingerprint_secret` (BLAKE2b) and NOT `hashlib.sha256`. Per-variant
direct-call tests per `rules/testing.md` § "One Direct Test Per Variant".
"""

from __future__ import annotations

import inspect

import pytest
from kailash.utils.url_credentials import fingerprint_secret
from pydantic import SecretStr


class TestNoSha256InKaizenLlm:
    """Mechanical sweep — source-level verification no migrated site reverts."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "kaizen.llm.auth.bearer",
            "kaizen.llm.errors",
            "kaizen.llm.presets",
            "kaizen.llm.from_env",
            "kaizen.llm.auth.gcp",
        ],
    )
    def test_module_uses_fingerprint_secret_not_sha256(self, module_path: str) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        src = inspect.getsource(mod)
        assert "hashlib.sha256" not in src, (
            f"{module_path}: hashlib.sha256 regression — "
            f"#617 requires fingerprint_secret (BLAKE2b) for "
            f"credential-adjacent fingerprinting"
        )
        assert "fingerprint_secret" in src, (
            f"{module_path}: fingerprint_secret import missing — "
            f"#617 migration regressed"
        )


class TestDirectCallPerSite:
    """Per-variant direct tests — exercises each migrated call path."""

    def test_bearer_apikey_fingerprint_is_blake2b(self) -> None:
        from kaizen.llm.auth.bearer import ApiKey

        key = ApiKey("sk-test1234567890abcdef")
        # fingerprint is 8-char hex (BLAKE2b-derived)
        assert len(key.fingerprint) == 8
        assert all(c in "0123456789abcdef" for c in key.fingerprint)
        # Deterministic
        key2 = ApiKey("sk-test1234567890abcdef")
        assert key.fingerprint == key2.fingerprint

    def test_bearer_apikey_fingerprint_matches_fingerprint_secret(self) -> None:
        """Cross-check: ApiKey fingerprint == fingerprint_secret(plaintext)."""
        from kaizen.llm.auth.bearer import ApiKey

        raw = "sk-test-exact-match-vector"
        key = ApiKey(raw)
        assert key.fingerprint == fingerprint_secret(raw)

    def test_errors_fingerprint_helper(self) -> None:
        from kaizen.llm.errors import _fingerprint

        result = _fingerprint("secret-payload")
        assert len(result) == 8
        assert result == fingerprint_secret("secret-payload")

    def test_errors_fingerprint_accepts_bytes(self) -> None:
        from kaizen.llm.errors import _fingerprint

        result = _fingerprint(b"secret-payload")
        expected = fingerprint_secret("secret-payload")
        assert result == expected

    def test_presets_fingerprint_helper(self) -> None:
        from kaizen.llm.presets import _fingerprint

        result = _fingerprint("preset-name-x")
        assert len(result) == 8
        assert result == fingerprint_secret("preset-name-x")

    def test_from_env_selector_fingerprint(self) -> None:
        from kaizen.llm.from_env import _fingerprint_selector

        result = _fingerprint_selector("my-selector")
        assert len(result) == 8
        assert result == fingerprint_secret("my-selector")

    def test_gcp_cached_token_fingerprint(self) -> None:
        from kaizen.llm.auth.gcp import CachedToken

        token = CachedToken(
            token=SecretStr("gcp-access-token-abc"),
            expiry_epoch=9_999_999_999.0,
        )
        assert len(token.fingerprint) == 8
        assert token.fingerprint == fingerprint_secret("gcp-access-token-abc")


class TestFingerprintSecretDocstringEnhancements:
    """#617 MEDIUM-2 — docstring must name collision-stability + caveats."""

    def test_docstring_documents_collision_stability(self) -> None:
        doc = fingerprint_secret.__doc__
        assert doc is not None
        assert "collision-stable" in doc, (
            "fingerprint_secret docstring MUST document collision-stability "
            "per #617 MEDIUM-2"
        )

    def test_docstring_warns_not_per_tenant_unique(self) -> None:
        doc = fingerprint_secret.__doc__
        assert doc is not None
        assert "per-tenant-unique" in doc or "per-tenant unique" in doc

    def test_docstring_warns_not_a_secret(self) -> None:
        doc = fingerprint_secret.__doc__
        assert doc is not None
        assert "MUST NOT be treated as secrets" in doc

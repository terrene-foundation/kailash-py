# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for SPEC-02 provider error hierarchy.

Covers:
- All error classes are importable from ``kaizen.providers.errors``.
- Inheritance: every error is a subclass of ``ProviderError``.
- ``ProviderError`` carries ``provider_name`` and ``original_error``.
- Each subclass is independently catchable.
"""

from __future__ import annotations

import pytest

from kaizen.providers.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    UnknownProviderError,
)

ALL_ERROR_CLASSES = [
    ProviderError,
    UnknownProviderError,
    ProviderUnavailableError,
    CapabilityNotSupportedError,
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
]


class TestErrorHierarchy:
    """All provider errors inherit from ProviderError."""

    @pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
    def test_is_exception(self, cls):
        assert issubclass(cls, Exception)

    @pytest.mark.parametrize(
        "cls",
        [
            UnknownProviderError,
            ProviderUnavailableError,
            CapabilityNotSupportedError,
            AuthenticationError,
            RateLimitError,
            ModelNotFoundError,
        ],
    )
    def test_subclass_of_provider_error(self, cls):
        assert issubclass(cls, ProviderError)


class TestProviderErrorAttributes:
    """ProviderError carries structured metadata."""

    def test_message(self):
        e = ProviderError("something broke")
        assert str(e) == "something broke"

    def test_provider_name_default(self):
        e = ProviderError("msg")
        assert e.provider_name == ""

    def test_provider_name_explicit(self):
        e = ProviderError("msg", provider_name="openai")
        assert e.provider_name == "openai"

    def test_original_error_default(self):
        e = ProviderError("msg")
        assert e.original_error is None

    def test_original_error_explicit(self):
        orig = ValueError("bad value")
        e = ProviderError("msg", original_error=orig)
        assert e.original_error is orig

    def test_combined_kwargs(self):
        orig = RuntimeError("timeout")
        e = AuthenticationError(
            "auth failed",
            provider_name="anthropic",
            original_error=orig,
        )
        assert e.provider_name == "anthropic"
        assert e.original_error is orig
        assert str(e) == "auth failed"
        assert isinstance(e, ProviderError)


class TestCatchability:
    """Each error subclass can be caught independently."""

    def test_catch_unknown_provider(self):
        with pytest.raises(UnknownProviderError):
            raise UnknownProviderError("not found", provider_name="foo")

    def test_catch_provider_unavailable(self):
        with pytest.raises(ProviderUnavailableError):
            raise ProviderUnavailableError("no key")

    def test_catch_capability_not_supported(self):
        with pytest.raises(CapabilityNotSupportedError):
            raise CapabilityNotSupportedError("no streaming")

    def test_catch_authentication_error(self):
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("invalid key")

    def test_catch_rate_limit_error(self):
        with pytest.raises(RateLimitError):
            raise RateLimitError("429")

    def test_catch_model_not_found(self):
        with pytest.raises(ModelNotFoundError):
            raise ModelNotFoundError("gpt-5 not available")

    def test_catch_subclass_via_base(self):
        """All subclasses are catchable via ProviderError."""
        with pytest.raises(ProviderError):
            raise RateLimitError("quota exceeded", provider_name="openai")

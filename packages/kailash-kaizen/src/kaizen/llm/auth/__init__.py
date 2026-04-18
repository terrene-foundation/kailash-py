# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Auth strategy interface for LLM deployments.

Every wire protocol (OpenAI, Anthropic, Google, Bedrock, Azure, ...) accepts
its credential through a uniform `AuthStrategy` interface so presets, env
loaders, and BYOK clients share one contract.

Protocol method names (`apply`, `auth_strategy_kind`, `refresh`) MUST
byte-match the Rust trait in `kailash-rs/crates/kaizen/src/llm/auth/mod.rs`
so cross-SDK parity snapshots compare trivially.

This module exposes:

* `AuthStrategy`       -- typing.Protocol the concrete strategies implement
* `Custom`             -- wraps a user-supplied callable as an AuthStrategy
* Re-exports from `bearer`: `StaticNone`, `ApiKey`, `ApiKeyHeaderKind`,
  `ApiKeyBearer`. Imports of those names from `kaizen.llm.auth` MUST be
  supported so Session 2+'s preset code can route through the package
  entry point.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from kaizen.llm.auth.aws import (
    BEDROCK_SUPPORTED_REGIONS,
    AwsBearerToken,
    AwsCredentials,
    AwsSigV4,
    ClockSkew,
    RegionNotAllowed,
)
from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.auth.gcp import (
    CLOUD_PLATFORM_SCOPE,
    DEFAULT_SCOPES,
    CachedToken,
    GcpOauth,
)


@runtime_checkable
class AuthStrategy(Protocol):
    """Uniform credential-application interface.

    An `apply(request)` call mutates (or returns a new) request with auth
    material installed (header, query param, signed body, ...). Concrete
    strategies either mutate in place or return a new immutable request; the
    Protocol accepts both. Callers assume the return value is the request
    they should send next, mirroring Rust's `AuthStrategy::apply` signature.

    `auth_strategy_kind()` returns a short stable string (e.g. "api_key",
    "aws_sigv4", "azure_entra", "static_none") used by the observability
    layer so dashboards can break down traffic by auth kind.

    `refresh()` refreshes time-bound credentials (OAuth tokens, Entra access
    tokens) in place. For static-credential strategies it is a no-op.
    """

    def apply(self, request: Any) -> Any: ...

    def auth_strategy_kind(self) -> str: ...

    def refresh(self) -> None: ...


class Custom:
    """Wrap a user-supplied callable as an AuthStrategy.

    The callable receives the same `request` object as `apply(request)` and
    returns the replacement. `auth_strategy_kind()` returns `"custom"` so
    observability distinguishes user-supplied strategies from framework ones.
    """

    def __init__(
        self,
        apply_fn: Callable[[Any], Any],
        *,
        refresh_fn: Callable[[], None] | None = None,
    ) -> None:
        if not callable(apply_fn):
            raise TypeError("Custom.apply_fn must be callable")
        if refresh_fn is not None and not callable(refresh_fn):
            raise TypeError("Custom.refresh_fn must be callable")
        self._apply_fn = apply_fn
        self._refresh_fn = refresh_fn

    def apply(self, request: Any) -> Any:
        return self._apply_fn(request)

    def auth_strategy_kind(self) -> str:
        return "custom"

    def refresh(self) -> None:
        if self._refresh_fn is not None:
            self._refresh_fn()

    def __repr__(self) -> str:
        # Do not call repr on the callable — users might pass a lambda that
        # closes over a credential.
        return "Custom(apply_fn=<opaque>, refresh_fn={})".format(
            "<opaque>" if self._refresh_fn is not None else "None"
        )


__all__ = [
    "AuthStrategy",
    "Custom",
    "ApiKey",
    "ApiKeyBearer",
    "ApiKeyHeaderKind",
    "StaticNone",
    # AWS auth (S4a + S4b-i)
    "AwsBearerToken",
    "AwsCredentials",
    "AwsSigV4",
    "BEDROCK_SUPPORTED_REGIONS",
    "RegionNotAllowed",
    "ClockSkew",
    # GCP OAuth (S5)
    "GcpOauth",
    "CachedToken",
    "CLOUD_PLATFORM_SCOPE",
    "DEFAULT_SCOPES",
]

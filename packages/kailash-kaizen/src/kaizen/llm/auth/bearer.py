# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Static credential strategies: `StaticNone`, `ApiKeyBearer`, `ApiKey`.

Every class in this module treats credential bytes as highly privileged:

* `ApiKey` wraps a `SecretStr` and deliberately has NO `__eq__` / `__hash__`
  so callers cannot accidentally compare keys with `==` (timing side-channel).
  Comparisons go through `ApiKey.constant_time_eq(other)` which uses
  `hmac.compare_digest`.

* `ApiKeyBearer.__repr__` includes only the 4-char SHA-256 fingerprint of the
  key, never the raw bytes. Anything a logger picks up via repr is safe for
  aggregators.

* `ApiKeyHeaderKind` is a closed `str, Enum` so wire-protocol adapters can
  `match` on it without parsing arbitrary user strings. Member names
  byte-match the Rust enum variants for cross-SDK parity.
"""

from __future__ import annotations

import hmac
from enum import Enum
from typing import Any

from kailash.utils.url_credentials import fingerprint_secret
from pydantic import ConfigDict, SecretStr
from pydantic.dataclasses import dataclass as pydantic_dataclass


class ApiKeyHeaderKind(str, Enum):
    """Where to place an API key on the wire.

    Member names byte-match the Rust `ApiKeyHeaderKind` variants
    (`kailash-rs/crates/kaizen/src/llm/auth/bearer.rs`).
    """

    Authorization_Bearer = "Authorization_Bearer"
    X_Api_Key = "X_Api_Key"
    X_Goog_Api_Key = "X_Goog_Api_Key"


class ApiKey:
    """Wraps an API-key `SecretStr` with a constant-time comparison helper.

    MUST NOT define `__eq__` / `__hash__`: the absence is load-bearing. It
    forces callers to use `constant_time_eq` for credential comparisons,
    closing off a timing side-channel (Rust SDK §6.4). A unit test in
    `tests/unit/llm/test_apikey.py` asserts both methods are absent.

    `SecretStr.get_secret_value()` is the only surface that returns the raw
    key; `__repr__` uses a stable 4-char fingerprint instead.
    """

    __slots__ = ("_secret", "_fingerprint")

    def __init__(self, key: str | SecretStr) -> None:
        if isinstance(key, SecretStr):
            secret = key
        elif isinstance(key, str):
            secret = SecretStr(key)
        else:
            raise TypeError("ApiKey expects str or SecretStr")
        self._secret: SecretStr = secret
        # #617: use fingerprint_secret (BLAKE2b) for credential-adjacent
        # fingerprinting — CodeQL py/weak-sensitive-data-hashing does not
        # flag BLAKE2b, and we document the non-verification contract.
        self._fingerprint: str = fingerprint_secret(secret.get_secret_value())

    @property
    def fingerprint(self) -> str:
        """8-char SHA-256 prefix for logs / correlation (cross-SDK parity)."""
        return self._fingerprint

    def get_secret_value(self) -> str:
        """Return the raw key. Handle with care."""
        return self._secret.get_secret_value()

    def constant_time_eq(self, other: "ApiKey") -> bool:
        """Constant-time equality check.

        Uses `hmac.compare_digest` to defeat timing side-channels. The
        unit test asserts this method actually invokes `hmac.compare_digest`
        (monkeypatch a spy and verify the call).
        """
        if not isinstance(other, ApiKey):
            return False
        a = self._secret.get_secret_value().encode("utf-8")
        b = other._secret.get_secret_value().encode("utf-8")
        return hmac.compare_digest(a, b)

    # Explicitly NO __eq__ / __hash__ / __bool__ on raw value.
    # Reason: forcing constant_time_eq at call sites.

    def __repr__(self) -> str:
        return f"ApiKey(fingerprint={self._fingerprint})"

    # Serialization hygiene: copy.deepcopy / pickle.dumps MUST NOT expose
    # the raw key. The default Python protocols pickle __slots__ values
    # as-is, which would ship `SecretStr("sk-...")` over the wire to any
    # log aggregator that captures exception reprs, any multi-process
    # pickling queue, and any test that inadvertently pickles a config.
    #
    # Contract: pickling / deep-copying returns an ApiKey that carries the
    # same secret (so legitimate in-process copies still work) but routes
    # through __init__, which re-derives the fingerprint. Pickle payloads
    # that escape the process to disk / to a remote worker / to a log
    # aggregator remain secret-bearing — the only defense against THAT is
    # "don't pickle credentials across process boundaries". This override
    # prevents accidental in-process leakage via __dict__-style reprs.
    #
    # Round-2 defer followup: ApiKey pickle/deepcopy hygiene.
    def __reduce__(self):  # type: ignore[override]
        # Re-construct via __init__ rather than via __slots__ restore so
        # the fingerprint is re-derived (defensive against a future slot
        # layout change that would produce a mismatched fingerprint).
        return (self.__class__, (self._secret,))

    def __deepcopy__(self, memo):
        # Deepcopy returns a distinct ApiKey with the same secret. This
        # keeps existing copy-based patterns working while routing through
        # the explicit constructor (no __slots__ bypass).
        new = self.__class__(self._secret)
        memo[id(self)] = new
        return new

    def __copy__(self):
        # Shallow copy — same contract as deepcopy; there is no meaningful
        # "shallow vs deep" distinction for a frozen secret holder.
        return self.__class__(self._secret)


class StaticNone:
    """AuthStrategy for endpoints that don't require auth.

    Currently unused by any preset (every supported provider authenticates)
    but kept as the canonical "no-op strategy" so future local / self-hosted
    endpoints have a uniform way to opt out.
    """

    def apply(self, request: Any) -> Any:
        return request

    def auth_strategy_kind(self) -> str:
        return "static_none"

    def refresh(self) -> None:
        # No-op: there is no credential to refresh.
        return None

    def __repr__(self) -> str:
        return "StaticNone()"


@pydantic_dataclass(config=ConfigDict(arbitrary_types_allowed=True, frozen=True))
class ApiKeyBearer:
    """AuthStrategy that injects an API key into a request header.

    `kind` selects the header name:

        Authorization_Bearer -> "Authorization: Bearer <key>"
        X_Api_Key            -> "X-Api-Key: <key>"
        X_Goog_Api_Key       -> "X-Goog-Api-Key: <key>"

    `apply(request)` expects `request` to be a dict-like with `"headers"` or
    an object with a `.headers` mapping. It writes the appropriate header
    in-place. The concrete shape of `request` is deliberately left to the
    wire-protocol adapter in later sessions — Session 1 exercises only the
    constructor, repr, and kind; Session 2+ exercises the header injection.
    """

    kind: ApiKeyHeaderKind
    key: ApiKey

    def __post_init__(self) -> None:
        # Defensive: the @frozen pydantic_dataclass accepts anything; we
        # explicitly reject non-ApiKey keys here so a caller who passes a
        # raw string never lands a bare string on an `ApiKeyBearer`
        # instance where it would be picked up by a future repr.
        if not isinstance(self.key, ApiKey):
            raise TypeError("ApiKeyBearer.key must be an ApiKey")
        if not isinstance(self.kind, ApiKeyHeaderKind):
            raise TypeError("ApiKeyBearer.kind must be an ApiKeyHeaderKind")

    def _header_name(self) -> str:
        if self.kind is ApiKeyHeaderKind.Authorization_Bearer:
            return "Authorization"
        if self.kind is ApiKeyHeaderKind.X_Api_Key:
            return "X-Api-Key"
        if self.kind is ApiKeyHeaderKind.X_Goog_Api_Key:
            return "X-Goog-Api-Key"
        # Closed enum — any other value is a construction bug.
        raise ValueError(f"unknown ApiKeyHeaderKind: {self.kind!r}")

    def _header_value(self) -> str:
        raw = self.key.get_secret_value()
        if self.kind is ApiKeyHeaderKind.Authorization_Bearer:
            return f"Bearer {raw}"
        return raw

    def apply(self, request: Any) -> Any:
        """Install the header. Accepts dict-like or object-with-.headers."""
        header_name = self._header_name()
        header_value = self._header_value()
        # Prefer a `.headers` attribute (httpx.Request, requests.Request).
        headers = getattr(request, "headers", None)
        if headers is not None and hasattr(headers, "__setitem__"):
            headers[header_name] = header_value
            return request
        # Fall back: treat `request` as a mutable mapping with "headers".
        if isinstance(request, dict):
            hdrs = request.setdefault("headers", {})
            hdrs[header_name] = header_value
            return request
        raise TypeError(
            "ApiKeyBearer.apply requires a request with .headers mapping "
            "or a dict containing a 'headers' key"
        )

    def auth_strategy_kind(self) -> str:
        return "api_key"

    def refresh(self) -> None:
        # Static credential; nothing to refresh. A BYOK rotation scheme
        # should construct a new `ApiKeyBearer` rather than mutate this one.
        return None

    def __repr__(self) -> str:
        # DO NOT include the raw key in any human-visible form.
        return (
            f"ApiKeyBearer(kind={self.kind.name}, "
            f"fingerprint={self.key.fingerprint})"
        )


__all__ = [
    "ApiKey",
    "ApiKeyBearer",
    "ApiKeyHeaderKind",
    "StaticNone",
]

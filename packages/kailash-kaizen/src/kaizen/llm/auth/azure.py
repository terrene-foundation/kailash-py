# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Azure auth strategy: `AzureEntra` -- api-key + Entra token variants.

Session 6 (S6) of #498. Implements three auth variants for Azure OpenAI
deployments:

1. **API-key** -- static `api-key: <KEY>` header (NOT `Authorization: Bearer`).
   `auth_strategy_kind() == "azure_entra_api_key"`.

2. **Workload identity** -- token fetched via `azure.identity.DefaultAzureCredential`
   (resolves federated credentials, service principal env vars, etc.).
   `auth_strategy_kind() == "azure_entra_workload_identity"`.

3. **Managed identity** -- token fetched via `azure.identity.ManagedIdentityCredential`
   pinned to a caller-supplied client id.
   `auth_strategy_kind() == "azure_entra_managed_identity"`.

Token variants share the single-flight refresh lock + CachedToken
contract used by `GcpOauth` (S5). The Entra audience scope is hardcoded
to `https://cognitiveservices.azure.com/.default` -- NOT user-configurable
in v0 -- matching the Rust SDK's audience constant byte-for-byte.

Secret hygiene:

* API key: wrapped in `pydantic.SecretStr`; `__repr__` fingerprints only.
* Entra token: wrapped in `SecretStr` inside `CachedToken`; never logged.
* Azure credential handles (DefaultAzureCredential / ManagedIdentityCredential)
  stored on the instance; `repr()` does NOT recurse into them.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    from azure.identity import (  # type: ignore[import-not-found]
        DefaultAzureCredential as _DefaultAzureCredential,
        ManagedIdentityCredential as _ManagedIdentityCredential,
    )
except ImportError:  # pragma: no cover - optional-extra guard
    _DefaultAzureCredential = None  # type: ignore[assignment]
    _ManagedIdentityCredential = None  # type: ignore[assignment]

from pydantic import SecretStr

from kaizen.llm.errors import AuthError, LlmClientError

logger = logging.getLogger(__name__)


# Azure Entra audience scope -- byte-identical to the Rust constant
# (`kailash-rs/crates/kailash-kaizen/src/llm/auth/azure.rs::COGNITIVE_SERVICES_SCOPE`).
# Hardcoded in v0 to prevent misconfiguration; widening to user-supplied
# scopes requires a security review because a different scope can enable
# token reuse across unintended APIs.
COGNITIVE_SERVICES_SCOPE: str = "https://cognitiveservices.azure.com/.default"

# Token refresh lead time -- 60s mirrors GcpOauth. A token within 60s of
# expiry is treated as stale so the refresh completes before it ships.
_REFRESH_LEAD_SECONDS: float = 60.0


@dataclass
class CachedToken:
    """SecretStr-wrapped Entra token + expiry epoch."""

    __slots__ = ("_token", "_expires_at", "_fingerprint")

    _token: SecretStr
    _expires_at: float
    _fingerprint: str

    @classmethod
    def from_raw(cls, raw: str, expires_at: float) -> "CachedToken":
        if not isinstance(raw, str) or not raw:
            raise AuthError("CachedToken raw token must be a non-empty string")
        fp = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
        return cls(_token=SecretStr(raw), _expires_at=expires_at, _fingerprint=fp)

    @property
    def token(self) -> str:
        return self._token.get_secret_value()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def expires_at(self) -> float:
        return self._expires_at

    def is_expiring(self, *, now: Optional[float] = None) -> bool:
        clock = now if now is not None else time.time()
        return self._expires_at - clock <= _REFRESH_LEAD_SECONDS

    def __repr__(self) -> str:
        return (
            f"CachedToken(fingerprint={self._fingerprint}, "
            f"expires_at={self._expires_at:.0f})"
        )


class AzureEntra:
    """Azure authentication across api-key + Entra token variants.

    Construct with EXACTLY ONE of `api_key`, `workload_identity=True`, or
    `managed_identity_client_id=<id>`. The variants are mutually exclusive;
    passing zero or multiple raises `AuthError`.
    """

    __slots__ = (
        "_variant",
        "_api_key",
        "_api_key_fingerprint",
        "_workload_credential",
        "_managed_credential",
        "_managed_client_id",
        "_cached_token",
        "_refresh_lock",
        "_refresh_count",
    )

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        workload_identity: bool = False,
        managed_identity_client_id: Optional[str] = None,
    ) -> None:
        provided = [
            api_key is not None,
            workload_identity,
            managed_identity_client_id is not None,
        ]
        count = sum(1 for x in provided if x)
        if count != 1:
            raise AuthError(
                "AzureEntra requires exactly one of "
                "api_key=, workload_identity=True, or "
                "managed_identity_client_id=; "
                f"got {count} provided"
            )

        self._api_key: Optional[SecretStr] = None
        self._api_key_fingerprint: Optional[str] = None
        self._workload_credential: Any = None
        self._managed_credential: Any = None
        self._managed_client_id: Optional[str] = None
        self._cached_token: Optional[CachedToken] = None
        self._refresh_lock = asyncio.Lock()
        self._refresh_count: int = 0

        if api_key is not None:
            if not isinstance(api_key, str) or not api_key:
                raise AuthError("AzureEntra.api_key must be a non-empty string")
            self._variant: str = "api_key"
            self._api_key = SecretStr(api_key)
            self._api_key_fingerprint = hashlib.sha256(
                api_key.encode("utf-8")
            ).hexdigest()[:8]
        elif workload_identity:
            if _DefaultAzureCredential is None:
                raise LlmClientError(
                    "azure-identity is not installed; install the [azure] "
                    "extra: pip install kailash-kaizen[azure]"
                )
            self._variant = "workload_identity"
            self._workload_credential = _DefaultAzureCredential()
        else:
            # managed_identity_client_id path
            if _ManagedIdentityCredential is None:
                raise LlmClientError(
                    "azure-identity is not installed; install the [azure] "
                    "extra: pip install kailash-kaizen[azure]"
                )
            if (
                not isinstance(managed_identity_client_id, str)
                or not managed_identity_client_id
            ):
                raise AuthError(
                    "AzureEntra.managed_identity_client_id must be a non-empty string"
                )
            self._variant = "managed_identity"
            self._managed_client_id = managed_identity_client_id
            self._managed_credential = _ManagedIdentityCredential(
                client_id=managed_identity_client_id
            )

    def auth_strategy_kind(self) -> str:
        """Stable label per variant for cross-SDK observability parity."""
        if self._variant == "api_key":
            return "azure_entra_api_key"
        if self._variant == "workload_identity":
            return "azure_entra_workload_identity"
        if self._variant == "managed_identity":
            return "azure_entra_managed_identity"
        # Closed enum -- any other value is a construction bug.
        raise ValueError(f"AzureEntra._variant invalid: {self._variant!r}")

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    async def _acquire_token_async(self) -> CachedToken:
        """Fetch a fresh token via the underlying azure-identity credential."""
        credential = (
            self._workload_credential
            if self._variant == "workload_identity"
            else self._managed_credential
        )
        if credential is None:
            raise AuthError("AzureEntra token variant missing underlying credential")
        # azure-identity's get_token returns a namedtuple with token + expires_on.
        token_result = credential.get_token(COGNITIVE_SERVICES_SCOPE)
        raw = getattr(token_result, "token", None)
        expires_on = getattr(token_result, "expires_on", None)
        if not raw or expires_on is None:
            raise AuthError("azure-identity get_token returned invalid token response")
        self._refresh_count += 1
        return CachedToken.from_raw(raw, float(expires_on))

    async def refresh(self) -> CachedToken:
        """Force a token re-fetch. No-op for api-key variant."""
        if self._variant == "api_key":
            raise AuthError("refresh() is not applicable to api-key variant")
        async with self._refresh_lock:
            token = await self._acquire_token_async()
            self._cached_token = token
            return token

    async def _ensure_token_async(self) -> CachedToken:
        """Return a valid cached token; refresh if expired/missing."""
        if self._cached_token is not None and not self._cached_token.is_expiring():
            return self._cached_token
        async with self._refresh_lock:
            # Re-check under lock (another caller may have refreshed).
            if self._cached_token is not None and not self._cached_token.is_expiring():
                return self._cached_token
            token = await self._acquire_token_async()
            self._cached_token = token
            return token

    def apply(self, request: Any) -> Any:
        """Install the appropriate auth header on the request (sync path).

        For api-key variant, installs `api-key: <KEY>` header directly.
        For token variants, installs `Authorization: Bearer <token>` using
        the currently-cached token; callers MUST invoke `_ensure_token_async`
        before calling apply on token variants.
        """
        headers = self._request_headers(request)
        if self._variant == "api_key":
            assert self._api_key is not None
            headers["api-key"] = self._api_key.get_secret_value()
            return request
        if self._cached_token is None:
            raise AuthError(
                "AzureEntra token variant requires a cached token; "
                "call `await auth._ensure_token_async()` before `apply()`."
            )
        headers["Authorization"] = f"Bearer {self._cached_token.token}"
        return request

    async def apply_async(self, request: Any) -> Any:
        """Install the auth header, fetching/refreshing token as needed."""
        if self._variant == "api_key":
            return self.apply(request)
        await self._ensure_token_async()
        return self.apply(request)

    @staticmethod
    def _request_headers(request: Any) -> dict:
        """Find-or-create the headers dict on the request."""
        if isinstance(request, dict):
            hdrs = request.setdefault("headers", {})
            return hdrs
        headers_attr = getattr(request, "headers", None)
        if headers_attr is None:
            headers_attr = {}
            try:
                setattr(request, "headers", headers_attr)
            except (AttributeError, TypeError):
                raise AuthError(
                    "AzureEntra.apply: request has no settable .headers attribute"
                )
        return headers_attr

    def __repr__(self) -> str:
        if self._variant == "api_key":
            return (
                f"AzureEntra(variant=api_key, fingerprint={self._api_key_fingerprint})"
            )
        if self._variant == "workload_identity":
            return "AzureEntra(variant=workload_identity)"
        return (
            "AzureEntra(variant=managed_identity, "
            f"client_id={self._managed_client_id})"
        )


__all__ = [
    "AzureEntra",
    "CachedToken",
    "COGNITIVE_SERVICES_SCOPE",
]

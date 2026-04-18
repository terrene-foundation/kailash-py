# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""GCP auth strategy: `GcpOauth` -- single-flight OAuth2 token via google-auth.

Session 5 (S5) of #498. Implements the auth strategy for Vertex AI deployments
(Claude-on-Vertex, Gemini). Vertex requires an OAuth2 access token bound to
the `https://www.googleapis.com/auth/cloud-platform` scope; the token is
short-lived (3600s default) and MUST be refreshed before expiry.

Concurrency contract (cross-SDK parity with kailash-rs):

* N concurrent `apply()` callers that observe an expired or missing token
  produce exactly ONE refresh request to the GCP token endpoint. The other
  N-1 await the in-flight refresh under `asyncio.Lock`.
* The cached token's expiry is checked under the lock so the refresh
  decision is race-free. A token whose expiry is within the
  `_REFRESH_LEAD_SECONDS` window (60s) is treated as expired so callers
  don't burn the boundary case.

Secret-handling contract (rules/security.md):

* Token bytes are wrapped in `pydantic.SecretStr` from the moment google-auth
  hands them over. `__repr__` redacts to a fingerprint + expiry; the raw
  token never appears in any human-visible string.
* `refresh_count` is a non-sensitive operational counter -- safe to log.

The `google-auth` library is the single source of truth for credential
canonicalization (provider chain, JWT signing, refresh response parsing).
Inlining the OAuth2 token-fetch flow is BLOCKED by zero-tolerance Rule 4.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from google.auth import default as _google_auth_default
    from google.auth.transport.requests import Request as _GoogleAuthRequest
    from google.oauth2 import service_account as _google_service_account
except ImportError:  # pragma: no cover - optional-extra guard
    _google_auth_default = None
    _GoogleAuthRequest = None
    _google_service_account = None

from pydantic import SecretStr

from kaizen.llm.errors import AuthError, LlmClientError, MissingCredential

logger = logging.getLogger(__name__)


# Vertex AI access tokens are scoped to the platform-wide scope. This is
# byte-identical to the kailash-rs constant
# (`crates/kailash-kaizen/src/llm/auth/gcp.rs::CLOUD_PLATFORM_SCOPE`) so a
# token minted by either SDK works against the same Vertex deployment.
CLOUD_PLATFORM_SCOPE: str = "https://www.googleapis.com/auth/cloud-platform"

DEFAULT_SCOPES: tuple[str, ...] = (CLOUD_PLATFORM_SCOPE,)

# Refresh tokens that are within this window of expiry. 60s mirrors the Rust
# SDK's lead time and is comfortably larger than typical request RTT so we
# don't ship an expired token while the wire request is in flight.
_REFRESH_LEAD_SECONDS: float = 60.0


# ---------------------------------------------------------------------------
# CachedToken -- SecretStr-wrapped token + expiry
# ---------------------------------------------------------------------------


@dataclass
class CachedToken:
    """OAuth2 access token cache slot.

    `token` is wrapped in `pydantic.SecretStr` so `__repr__`, pickle, and
    log captures NEVER contain the raw bearer value. `expiry_epoch` is the
    absolute UTC unix timestamp at which the token stops being valid.

    `refresh_count` increments every time the token is replaced via
    `GcpOauth.refresh()`. It is a non-sensitive operational metric used
    by the single-flight unit test to assert "N concurrent callers, 1
    refresh".
    """

    token: SecretStr
    expiry_epoch: float
    refresh_count: int = 0
    fingerprint: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.token, SecretStr):
            raise TypeError("CachedToken.token must be a SecretStr")
        if not self.fingerprint:
            raw = self.token.get_secret_value().encode("utf-8")
            object.__setattr__(
                self,
                "fingerprint",
                hashlib.sha256(raw).hexdigest()[:8],
            )

    def is_expired(self, *, now_epoch: Optional[float] = None) -> bool:
        """True iff the token is within the refresh-lead window of expiry."""
        now = now_epoch if now_epoch is not None else time.time()
        return self.expiry_epoch - now <= _REFRESH_LEAD_SECONDS

    def __repr__(self) -> str:
        return (
            f"CachedToken(fingerprint={self.fingerprint}, "
            f"expiry_epoch={self.expiry_epoch:.0f}, "
            f"refresh_count={self.refresh_count})"
        )


# ---------------------------------------------------------------------------
# GcpOauth -- single-flight OAuth2 strategy
# ---------------------------------------------------------------------------


class GcpOauth:
    """OAuth2 access-token auth strategy for GCP / Vertex AI.

    Construction accepts either a service-account-key dict (already-parsed
    JSON) or a filesystem path to a service-account JSON file. `from_env()`
    uses the standard `GOOGLE_APPLICATION_CREDENTIALS` env var per the GCP
    convention.

    `apply(request)` installs `Authorization: Bearer <access_token>` on the
    request, refreshing the cached token if it is within the
    `_REFRESH_LEAD_SECONDS` window of expiry. Concurrent callers are
    serialized through `self._refresh_lock` so a thundering herd produces
    exactly one google-auth refresh per wave.

    `refresh()` forces a token re-fetch regardless of cache state. Used for
    explicit credential rotation (e.g. after an upstream 401 indicates the
    token was revoked).

    Cross-SDK parity:

    * `auth_strategy_kind() == "gcp_oauth"` byte-matches the Rust strategy.
    * Token-cache shape matches the kailash-rs `CachedToken` (token bytes
      + expiry epoch + monotonic refresh counter).
    * Default scope `https://www.googleapis.com/auth/cloud-platform` is the
      same in both SDKs.

    Secret hygiene:

    * `__repr__` reveals only fingerprint + expiry + refresh count -- never
      the raw token.
    * The service-account key dict is stored on the instance for refresh
      purposes; calling `repr()` on the instance does NOT recurse into the
      key dict.
    """

    __slots__ = (
        "_service_account_info",
        "_service_account_path",
        "_scopes",
        "_cached_token",
        "_refresh_lock",
        "_refresh_count",
    )

    def __init__(
        self,
        service_account_key: dict | str,
        scopes: Optional[list[str]] = None,
    ) -> None:
        if _google_auth_default is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra: "
                "pip install kailash-kaizen[vertex]"
            )
        # Accept either an already-parsed service-account dict OR a path
        # string to a JSON file. Path strings are resolved at refresh time
        # so a key file rotated on disk is picked up by the next refresh.
        if isinstance(service_account_key, dict):
            if not service_account_key:
                raise AuthError(
                    "GcpOauth service_account_key dict must not be empty"
                )
            self._service_account_info: Optional[dict] = dict(service_account_key)
            self._service_account_path: Optional[str] = None
        elif isinstance(service_account_key, str):
            if not service_account_key:
                raise AuthError(
                    "GcpOauth service_account_key path must not be an empty string"
                )
            self._service_account_info = None
            self._service_account_path = service_account_key
        else:
            raise TypeError(
                "GcpOauth.service_account_key must be dict or str (file path); "
                f"got {type(service_account_key).__name__}"
            )
        # Scopes default to cloud-platform per Vertex spec. Caller may
        # narrow scopes for least-privilege deployments but cannot widen
        # past the GCP authorization model.
        if scopes is None:
            resolved_scopes = list(DEFAULT_SCOPES)
        else:
            if not isinstance(scopes, list) or not scopes:
                raise AuthError(
                    "GcpOauth.scopes must be a non-empty list of strings"
                )
            for s in scopes:
                if not isinstance(s, str) or not s:
                    raise AuthError(
                        "GcpOauth.scopes entries must be non-empty strings"
                    )
            resolved_scopes = list(scopes)
        self._scopes: list[str] = resolved_scopes
        self._cached_token: Optional[CachedToken] = None
        # Lock guards single-flight refresh. Acquiring the lock before
        # checking expiry serializes the "is the token still valid?"
        # decision so two callers can't both decide "expired -> refresh".
        self._refresh_lock = asyncio.Lock()
        self._refresh_count: int = 0

    @classmethod
    def from_env(cls, scopes: Optional[list[str]] = None) -> "GcpOauth":
        """Construct from `GOOGLE_APPLICATION_CREDENTIALS`.

        The env var MUST point at a service-account JSON file that exists
        and is readable. A missing or empty env var raises
        `MissingCredential("GOOGLE_APPLICATION_CREDENTIALS")` so operators
        can grep for the precise envelope that failed.
        """
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or ""
        if not path:
            raise MissingCredential("GOOGLE_APPLICATION_CREDENTIALS")
        return cls(service_account_key=path, scopes=scopes)

    @property
    def scopes(self) -> tuple[str, ...]:
        """Immutable view of the configured scopes."""
        return tuple(self._scopes)

    @property
    def cached_token(self) -> Optional[CachedToken]:
        """Snapshot of the current cached token (for tests / observability)."""
        return self._cached_token

    @property
    def refresh_count(self) -> int:
        """Total number of refresh() calls that produced a new token."""
        return self._refresh_count

    def _build_credentials(self) -> Any:
        """Construct a google-auth `Credentials` object from the configured
        service-account material.

        Routed through google-auth's official constructors -- inlining the
        JWT-bearer flow here is BLOCKED by zero-tolerance Rule 4. If
        google-auth has a bug, the fix lives in google-auth.
        """
        if _google_service_account is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra"
            )
        if self._service_account_info is not None:
            return _google_service_account.Credentials.from_service_account_info(
                self._service_account_info, scopes=list(self._scopes)
            )
        # Path-based: re-read the file on every refresh so a rotated key
        # file is picked up. The file is read inside the refresh lock so
        # the read is serialized too.
        if self._service_account_path is None:
            raise AuthError(
                "GcpOauth has neither a service-account dict nor a path; "
                "this is a construction bug"
            )
        return _google_service_account.Credentials.from_service_account_file(
            self._service_account_path, scopes=list(self._scopes)
        )

    async def _ensure_token(self) -> CachedToken:
        """Return a non-expired cached token, refreshing if needed.

        The expiry check happens UNDER the lock so the "expired -> refresh"
        decision is race-free. Two concurrent callers that observed an
        expired token will both acquire the lock in series; the second
        sees the refreshed token from the first and returns immediately.
        """
        # Fast path: token cached and not expired -- no lock needed for
        # the read because CachedToken instances are replaced atomically
        # via the slot (Python's GIL serializes attribute writes).
        cached = self._cached_token
        if cached is not None and not cached.is_expired():
            return cached
        async with self._refresh_lock:
            # Re-check under the lock. The first caller refreshes; every
            # subsequent caller sees the post-refresh slot and returns it.
            cached = self._cached_token
            if cached is not None and not cached.is_expired():
                return cached
            return await self._refresh_locked()

    async def _refresh_locked(self) -> CachedToken:
        """Run the actual refresh under the held lock.

        google-auth's `refresh()` is synchronous; we run it in the default
        executor to avoid blocking the event loop. The resulting token is
        wrapped in `CachedToken` and stored as the new slot.
        """
        if _GoogleAuthRequest is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra"
            )
        loop = asyncio.get_running_loop()
        creds = await loop.run_in_executor(None, self._build_credentials)
        # Refresh runs in executor because google-auth uses requests
        # internally (blocking IO).
        await loop.run_in_executor(
            None, lambda: creds.refresh(_GoogleAuthRequest())
        )
        token_value = getattr(creds, "token", None)
        expiry = getattr(creds, "expiry", None)
        if not token_value:
            raise AuthError(
                "google-auth refresh returned no token; check the service "
                "account key and scopes"
            )
        # google-auth's `expiry` is a naive datetime in UTC. Convert to a
        # Unix epoch float; if missing, default to a 60-minute window
        # (the typical access-token lifetime) so we don't trust a
        # never-expiring token by accident.
        if expiry is not None:
            try:
                expiry_epoch = expiry.timestamp()
            except Exception:
                # Older google-auth versions return a naive datetime;
                # treat it as UTC.
                from datetime import timezone

                expiry_epoch = expiry.replace(tzinfo=timezone.utc).timestamp()
        else:
            expiry_epoch = time.time() + 3600.0
        self._refresh_count += 1
        new_token = CachedToken(
            token=SecretStr(token_value),
            expiry_epoch=expiry_epoch,
            refresh_count=self._refresh_count,
        )
        self._cached_token = new_token
        logger.info(
            "gcp_oauth.token_refreshed",
            extra={
                "auth_strategy_kind": "gcp_oauth",
                "refresh_count": self._refresh_count,
                "expiry_epoch": int(expiry_epoch),
                "fingerprint": new_token.fingerprint,
            },
        )
        return new_token

    async def refresh(self) -> CachedToken:
        """Force a token re-fetch via google-auth's provider chain.

        Used for explicit rotation (e.g. after a 401 from Vertex). The
        refresh runs under `self._refresh_lock` so concurrent callers
        coalesce into a single google-auth invocation.
        """
        async with self._refresh_lock:
            return await self._refresh_locked()

    async def apply_async(self, request: Any) -> Any:
        """Async variant that ensures a fresh token before installing it.

        Use `apply_async` from async call sites to take advantage of the
        single-flight refresh. The sync `apply()` raises if the token has
        not been pre-fetched, because acquiring `asyncio.Lock` from a sync
        context would block the event loop.
        """
        token = await self._ensure_token()
        header_value = f"Bearer {token.token.get_secret_value()}"
        headers = getattr(request, "headers", None)
        if headers is not None and hasattr(headers, "__setitem__"):
            headers["Authorization"] = header_value
            return request
        if isinstance(request, dict):
            hdrs = request.setdefault("headers", {})
            hdrs["Authorization"] = header_value
            return request
        raise TypeError(
            "GcpOauth.apply_async requires a request with .headers mapping "
            "or a dict containing a 'headers' key"
        )

    def apply(self, request: Any) -> Any:
        """Install `Authorization: Bearer <token>` from the cached token.

        Sync entry point. The cached token MUST be present and non-expired
        -- callers that need refresh-on-demand use `apply_async`. Sync
        callers in async contexts would deadlock on `asyncio.Lock`, so the
        sync path simply asserts the cache is populated.

        For pure-sync deployments without an event loop, the recommended
        pattern is to pre-fetch the token with `asyncio.run(strategy.refresh())`
        once at startup, then call `apply()` on every request.
        """
        cached = self._cached_token
        if cached is None:
            raise AuthError(
                "GcpOauth.apply called with no cached token; call "
                "`await strategy.apply_async(request)` from async code "
                "or pre-fetch via `asyncio.run(strategy.refresh())` "
                "from sync code"
            )
        if cached.is_expired():
            raise AuthError(
                "GcpOauth.apply found expired cached token; call "
                "`await strategy.apply_async(request)` to refresh"
            )
        header_value = f"Bearer {cached.token.get_secret_value()}"
        headers = getattr(request, "headers", None)
        if headers is not None and hasattr(headers, "__setitem__"):
            headers["Authorization"] = header_value
            return request
        if isinstance(request, dict):
            hdrs = request.setdefault("headers", {})
            hdrs["Authorization"] = header_value
            return request
        raise TypeError(
            "GcpOauth.apply requires a request with .headers mapping "
            "or a dict containing a 'headers' key"
        )

    def auth_strategy_kind(self) -> str:
        return "gcp_oauth"

    def __repr__(self) -> str:
        # Never include service-account material or the raw token. The
        # cached-token fingerprint + scope count is enough for forensic
        # correlation across logs.
        cached = self._cached_token
        cached_repr = repr(cached) if cached is not None else "None"
        return (
            f"GcpOauth(scopes={len(self._scopes)}, "
            f"refresh_count={self._refresh_count}, "
            f"cached_token={cached_repr})"
        )


__all__ = [
    "CLOUD_PLATFORM_SCOPE",
    "DEFAULT_SCOPES",
    "CachedToken",
    "GcpOauth",
]

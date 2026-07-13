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
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from kailash.utils.url_credentials import fingerprint_secret

try:
    from google.auth import default as _google_auth_default
    from google.auth import load_credentials_from_dict as _google_load_creds_from_dict
    from google.auth.transport.requests import Request as _GoogleAuthRequest
    from google.oauth2 import service_account as _google_service_account
except ImportError:  # pragma: no cover - optional-extra guard
    _google_auth_default = None
    _google_load_creds_from_dict = None
    _GoogleAuthRequest = None
    _google_service_account = None

try:
    from google.auth import compute_engine as _google_compute_engine
except ImportError:  # pragma: no cover - optional-extra guard
    _google_compute_engine = None

from kaizen.llm.errors import AuthError, LlmClientError, MissingCredential
from pydantic import SecretStr

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
            # #617: BLAKE2b via fingerprint_secret (consistent cross-kaizen)
            object.__setattr__(
                self,
                "fingerprint",
                fingerprint_secret(self.token.get_secret_value()),
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

    Four credential-source modes are supported, each with a distinct
    `auth_strategy_kind()` discriminant:

    * `gcp_oauth` -- a service-account key: an already-parsed dict OR a
      filesystem path to a service-account JSON file (the historical
      default). A path whose JSON `type` field is `external_account` is
      transparently routed to the WIF loader at credential-build time
      (JSON-type dispatch), so `GOOGLE_APPLICATION_CREDENTIALS` may point
      at either a service-account OR a workload-identity-federation file.
    * `gcp_wif` -- an explicit `external_account` (Workload Identity
      Federation) config: dict OR path. Routed through google-auth's
      external-account loader, which performs the STS token exchange and,
      when the config carries `service_account_impersonation_url`, the
      service-account impersonation step.
    * `gcp_metadata` -- keyless: the GCE / Cloud Run metadata server
      (`use_metadata_server=True`).
    * `gcp_adc` -- keyless: Application Default Credentials via
      `google.auth.default()` (the fallback when no explicit credential
      material is supplied).

    `from_env()` reads the standard `GOOGLE_APPLICATION_CREDENTIALS` env
    var per the GCP convention (service-account OR external-account file).

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
        "_external_account_info",
        "_external_account_path",
        "_auth_mode",
        "_scopes",
        "_cached_token",
        "_refresh_lock",
        "_refresh_count",
    )

    def __init__(
        self,
        service_account_key: dict | str | None = None,
        scopes: Optional[list[str]] = None,
        *,
        external_account: dict | str | None = None,
        use_metadata_server: bool = False,
    ) -> None:
        if _google_auth_default is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra: "
                "pip install kailash-kaizen[vertex]"
            )
        # A credential is sourced from AT MOST one place. A caller who
        # supplies both a service-account key and an external-account
        # config has an ambiguous intent -- fail loudly rather than pick
        # one silently.
        if service_account_key is not None and external_account is not None:
            raise AuthError(
                "GcpOauth accepts service_account_key OR external_account, " "not both"
            )
        # Scopes default to cloud-platform per Vertex spec. Caller may
        # narrow scopes for least-privilege deployments but cannot widen
        # past the GCP authorization model.
        if scopes is None:
            resolved_scopes = list(DEFAULT_SCOPES)
        else:
            if not isinstance(scopes, list) or not scopes:
                raise AuthError("GcpOauth.scopes must be a non-empty list of strings")
            for s in scopes:
                if not isinstance(s, str) or not s:
                    raise AuthError("GcpOauth.scopes entries must be non-empty strings")
            resolved_scopes = list(scopes)
        self._scopes: list[str] = resolved_scopes

        # Credential-source slots -- exactly one branch below populates the
        # material and sets the auth-mode discriminant. Path strings are
        # resolved at refresh time so a key file rotated on disk is picked
        # up by the next refresh.
        self._service_account_info: Optional[dict] = None
        self._service_account_path: Optional[str] = None
        self._external_account_info: Optional[dict] = None
        self._external_account_path: Optional[str] = None

        if external_account is not None:
            self._auth_mode: str = "gcp_wif"
            if isinstance(external_account, dict):
                if not external_account:
                    raise AuthError("GcpOauth external_account dict must not be empty")
                self._external_account_info = dict(external_account)
            elif isinstance(external_account, str):
                if not external_account:
                    raise AuthError(
                        "GcpOauth external_account path must not be an empty string"
                    )
                self._external_account_path = external_account
            else:
                raise TypeError(
                    "GcpOauth.external_account must be dict or str (file path); "
                    f"got {type(external_account).__name__}"
                )
        elif service_account_key is not None:
            if isinstance(service_account_key, dict):
                if not service_account_key:
                    raise AuthError(
                        "GcpOauth service_account_key dict must not be empty"
                    )
                info = dict(service_account_key)
                # A dict whose `type` is `external_account` is a WIF config
                # supplied through the service_account_key arg -- classify
                # it as WIF (the dict `type` is free to read; no file IO).
                if info.get("type") == "external_account":
                    self._auth_mode = "gcp_wif"
                    self._external_account_info = info
                else:
                    self._auth_mode = "gcp_oauth"
                    self._service_account_info = info
            elif isinstance(service_account_key, str):
                if not service_account_key:
                    raise AuthError(
                        "GcpOauth service_account_key path must not be an empty string"
                    )
                # A path is NOT read at construction (existing contract: a
                # path to a not-yet-present key file constructs cleanly).
                # The JSON `type` dispatch (service_account vs
                # external_account) happens at credential-build time.
                self._auth_mode = "gcp_oauth"
                self._service_account_path = service_account_key
            else:
                raise TypeError(
                    "GcpOauth.service_account_key must be dict or str (file path); "
                    f"got {type(service_account_key).__name__}"
                )
        elif use_metadata_server:
            # Keyless: the GCE / Cloud Run metadata server mints tokens for
            # the attached service account.
            self._auth_mode = "gcp_metadata"
        else:
            # Keyless: Application Default Credentials resolution chain
            # (google.auth.default) -- env var, gcloud SDK creds, metadata.
            self._auth_mode = "gcp_adc"

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

    @classmethod
    def adc(cls, scopes: Optional[list[str]] = None) -> "GcpOauth":
        """Keyless Application Default Credentials strategy.

        Resolves credentials via `google.auth.default()` at refresh time --
        the standard ADC chain (`GOOGLE_APPLICATION_CREDENTIALS`, gcloud SDK
        user creds, attached service account). Use when no explicit key or
        external-account config is available and the runtime environment
        already carries ambient credentials.
        """
        return cls(scopes=scopes)

    @classmethod
    def metadata_server(cls, scopes: Optional[list[str]] = None) -> "GcpOauth":
        """Keyless GCE / Cloud Run metadata-server strategy.

        Mints tokens for the service account attached to the compute
        instance via `google.auth.compute_engine.Credentials`. Use on
        GCE / Cloud Run / GKE where the metadata server is reachable and
        no key material should ever touch disk.
        """
        return cls(scopes=scopes, use_metadata_server=True)

    @classmethod
    def workload_identity(
        cls,
        external_account: dict | str,
        scopes: Optional[list[str]] = None,
    ) -> "GcpOauth":
        """Workload Identity Federation (external_account) strategy.

        `external_account` is a WIF config -- an already-parsed dict OR a
        path to an `external_account` JSON file. Routed through
        google-auth's external-account loader, which performs the STS
        token exchange and, when the config carries
        `service_account_impersonation_url`, the impersonation step.
        """
        return cls(external_account=external_account, scopes=scopes)

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
        """Construct a google-auth `Credentials` object for the configured mode.

        Dispatches on `self._auth_mode`. Every branch is routed through a
        google-auth official constructor -- inlining any token-fetch flow
        here is BLOCKED by zero-tolerance Rule 4. If google-auth has a bug,
        the fix lives in google-auth.
        """
        mode = self._auth_mode
        if mode == "gcp_oauth":
            return self._build_service_account_credentials()
        if mode == "gcp_wif":
            return self._build_wif_credentials()
        if mode == "gcp_metadata":
            return self._build_metadata_credentials()
        if mode == "gcp_adc":
            return self._build_adc_credentials()
        raise AuthError(
            f"GcpOauth has an unknown auth mode {mode!r}; this is a construction bug"
        )

    def _read_credentials_file(self, path: str) -> dict:
        """Read + JSON-parse a credentials file, failing with a typed error.

        The raw path is NEVER echoed -- only a fingerprint -- so a
        misconfigured path cannot leak a filesystem layout into a log line.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise AuthError(
                "GcpOauth credentials file not found "
                f"(path_fingerprint={fingerprint_secret(path)})"
            ) from exc
        except (OSError, ValueError) as exc:
            # ValueError covers json.JSONDecodeError.
            raise AuthError(
                "GcpOauth credentials file is unreadable or not valid JSON "
                f"(path_fingerprint={fingerprint_secret(path)})"
            ) from exc
        if not isinstance(data, dict):
            raise AuthError(
                "GcpOauth credentials file must contain a JSON object "
                f"(path_fingerprint={fingerprint_secret(path)})"
            )
        return data

    def _build_service_account_credentials(self) -> Any:
        """`gcp_oauth` mode: service-account key (dict or path).

        A path is re-read on every refresh so a rotated key file is picked
        up. JSON-`type` dispatch happens here: a path whose file declares
        `type == "external_account"` is routed to the WIF loader, so
        `GOOGLE_APPLICATION_CREDENTIALS` transparently supports both a
        service-account AND a workload-identity-federation file.
        """
        if _google_service_account is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra"
            )
        if self._service_account_info is not None:
            return _google_service_account.Credentials.from_service_account_info(
                self._service_account_info, scopes=list(self._scopes)
            )
        if self._service_account_path is None:
            raise AuthError(
                "GcpOauth has neither a service-account dict nor a path; "
                "this is a construction bug"
            )
        info = self._read_credentials_file(self._service_account_path)
        cred_type = info.get("type")
        if cred_type == "external_account":
            # JSON-type dispatch: the path points at a WIF config.
            return self._build_wif_from_info(info)
        if cred_type == "service_account":
            return _google_service_account.Credentials.from_service_account_file(
                self._service_account_path, scopes=list(self._scopes)
            )
        raise AuthError(
            "GcpOauth credentials file has an unsupported credential type "
            f"(expected 'service_account' or 'external_account'; "
            f"path_fingerprint={fingerprint_secret(self._service_account_path)})"
        )

    def _build_wif_credentials(self) -> Any:
        """`gcp_wif` mode: explicit external_account (dict or path)."""
        if self._external_account_info is not None:
            info = self._external_account_info
        elif self._external_account_path is not None:
            info = self._read_credentials_file(self._external_account_path)
        else:
            raise AuthError(
                "GcpOauth WIF mode has neither an external_account dict nor "
                "a path; this is a construction bug"
            )
        return self._build_wif_from_info(info)

    def _build_wif_from_info(self, info: dict) -> Any:
        """Route an external_account config through google-auth's WIF loader.

        `load_credentials_from_dict` builds the correct external-account
        subclass (identity-pool, AWS, ...), performs the STS token exchange
        on refresh, and -- when `service_account_impersonation_url` is
        present in the config -- wraps the result in
        `impersonated_credentials.Credentials`. Inlining any of that is
        BLOCKED by zero-tolerance Rule 4.
        """
        if _google_load_creds_from_dict is None:
            raise LlmClientError(
                "google-auth external_account (WIF) support is unavailable; "
                "install the [vertex] extra"
            )
        creds, _project = _google_load_creds_from_dict(info, scopes=list(self._scopes))
        return creds

    def _build_metadata_credentials(self) -> Any:
        """`gcp_metadata` mode: the GCE / Cloud Run metadata server."""
        if _google_compute_engine is None:
            raise LlmClientError(
                "google-auth compute_engine (metadata-server) support is "
                "unavailable; install the [vertex] extra"
            )
        return _google_compute_engine.Credentials(scopes=list(self._scopes))

    def _build_adc_credentials(self) -> Any:
        """`gcp_adc` mode: Application Default Credentials resolution."""
        if _google_auth_default is None:
            raise LlmClientError(
                "google-auth is not installed; install the [vertex] extra"
            )
        creds, _project = _google_auth_default(scopes=list(self._scopes))
        return creds

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
        # Capture into a local so the guard above narrows the type inside the
        # deferred executor closure (a module global is not narrowed in a lambda).
        request_factory = _GoogleAuthRequest
        loop = asyncio.get_running_loop()
        creds = await loop.run_in_executor(None, self._build_credentials)
        # Refresh runs in executor because google-auth uses requests
        # internally (blocking IO).
        await loop.run_in_executor(None, lambda: creds.refresh(request_factory()))
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
                "auth_strategy_kind": self._auth_mode,
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
        """Stable discriminant for the configured credential source.

        One of `gcp_oauth` (service-account key), `gcp_wif` (explicit
        external_account / Workload Identity Federation), `gcp_metadata`
        (GCE / Cloud Run metadata server), or `gcp_adc` (Application
        Default Credentials). A path-based service-account key reports
        `gcp_oauth` even when the file is later found to be an
        external_account config -- the file is not read at construction, so
        the discriminant reflects the construction API used.
        """
        return self._auth_mode

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

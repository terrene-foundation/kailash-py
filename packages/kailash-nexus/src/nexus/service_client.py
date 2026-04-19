# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Typed service-to-service HTTP client — ServiceClient.

Built on top of ``HttpClient``. Adds:

* A typed exception hierarchy (``ServiceClientError`` base + subclasses per
  failure mode) so callers can ``except ServiceClientHttpStatusError`` and
  recover without catching every other HTTP error.
* Eager header + bearer-token validation at construction time. Invalid
  headers fail fast, not at first request, and never silently pollute the
  header map.
* Convenient JSON-in / JSON-out methods (``get`` / ``post`` / ``put`` /
  ``delete``) alongside raw variants (``get_raw`` / ``post_raw`` / …) that
  return ``HttpResponse`` without status checking.
* SSRF-on-by-default inherited from ``HttpClient``. Layer order is fixed
  per issue #473 non-negotiable 1: the private-IP check runs BEFORE the
  host allowlist, so an allowlisted private IP is still rejected.

# Secrets hygiene

The bearer token is stored privately and validated for CRLF injection at
``__init__``. It is NEVER logged. Log lines derived from this client emit
``has_auth=true`` only, never the token. Error messages for status failures
truncate the response body to ~512 bytes so a provider echoing the submitted
Authorization in a 4xx body is bounded in the resulting exception string.

# Cross-SDK parity

Semantic match with ``kailash-rs#400`` ServiceClient. The exception
hierarchy names and triggers mirror the Rust ``ServiceClientError`` variants
exactly so callers porting between SDKs hit the same ``isinstance`` checks.
"""

from __future__ import annotations

import json as _json
import logging
import re
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlparse

import httpx

from .http_client import (
    HttpClient,
    HttpClientConfig,
    HttpResponse,
    InvalidEndpointError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception hierarchy — matches kailash-rs ServiceClientError variants
# ---------------------------------------------------------------------------


class ServiceClientError(Exception):
    """Base class for ServiceClient failures.

    Every typed subclass inherits from this, so a caller can
    ``except ServiceClientError`` and catch every failure mode without
    caring about the specific variant. New subclasses added in future
    sessions MUST continue to inherit from this base.
    """


class ServiceClientHttpError(ServiceClientError):
    """Transport-layer failure: SSRF blocked, timeout, connection error,
    invalid URL, unsupported scheme.

    Maps to ``kailash-rs::ServiceClientError::Http`` variant. The ``cause``
    attribute carries the underlying exception (httpx.ConnectError,
    httpx.TimeoutException, InvalidEndpointError) for callers that need to
    inspect the low-level failure.
    """

    def __init__(self, message: str, *, cause: Optional[BaseException] = None) -> None:
        self.cause = cause
        super().__init__(message)


class ServiceClientHttpStatusError(ServiceClientError):
    """Non-2xx HTTP status received from the upstream service.

    The response body is truncated to ~512 bytes in the exception message
    so a provider that echoes the submitted Authorization header in its
    4xx body does not leak the full token into ``str(err)`` / tracing
    spans.
    """

    _BODY_LIMIT = 512

    def __init__(self, status_code: int, body: bytes, url: str) -> None:
        self.status_code = status_code
        self.url = url
        # Decode for message; keep raw bytes available on the attribute.
        self.body = body
        try:
            decoded = body.decode("utf-8", errors="replace")
        except Exception:
            decoded = "<non-utf8 body>"
        if len(decoded) > self._BODY_LIMIT:
            decoded = decoded[: self._BODY_LIMIT] + "...[truncated]"
        # Do NOT include the full URL in the message — the path may carry
        # a sensitive query-string value; fingerprint it via its host only.
        host = urlparse(url).hostname or "<unknown-host>"
        super().__init__(f"HTTP {status_code} from {host}: {decoded!r}")


class ServiceClientSerializeError(ServiceClientError):
    """Request body could not be serialized to JSON.

    Triggered when a caller passes a non-JSON-serializable value
    (e.g. a custom object without ``__dict__``) to a typed JSON method.
    """


class ServiceClientDeserializeError(ServiceClientError):
    """Response body was not valid JSON for the expected type."""


class ServiceClientInvalidPathError(ServiceClientError):
    """Base URL + path could not be joined into a valid URL.

    Triggered when the path fails to produce a well-formed URL when joined
    with the base (empty host after join, malformed path, unsupported
    scheme). Separate from ``InvalidEndpointError`` which signals SSRF.
    """


class ServiceClientInvalidHeaderError(ServiceClientError):
    """Header name/value rejected by eager validation.

    Raised at ``__init__`` for headers supplied via the ``headers`` kwarg,
    and for the bearer token. Catches CRLF injection (``X-Good: v\\r\\nX-Bad: 1``),
    empty name/value, and control-byte injection.
    """


# ---------------------------------------------------------------------------
# Header validation
# ---------------------------------------------------------------------------

# HTTP header name: RFC 7230 — a ``token`` character set. Disallow
# whitespace, control bytes, and the reserved separators so the header name
# is always a safe grep target.
_HEADER_NAME_REGEX = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

# Control-byte probe for header values. Rejects ``\r``, ``\n``, and every
# other C0 control except HTAB (``\t`` is permitted in structured header
# values). We match the Rust ``is_valid_header_value`` contract exactly.
_HEADER_VALUE_BAD = re.compile(r"[\x00-\x08\x0A-\x1F\x7F]")


def _validate_header_name(name: Any) -> str:
    if not isinstance(name, str):
        raise ServiceClientInvalidHeaderError(
            f"header name must be a string (got {type(name).__name__})"
        )
    if not name:
        raise ServiceClientInvalidHeaderError("header name must not be empty")
    if not _HEADER_NAME_REGEX.match(name):
        # Do NOT echo the raw name — it may carry an injection payload that
        # would end up in log aggregators. Fingerprint length + a short
        # prefix for forensic correlation.
        prefix = name[:8].encode("unicode_escape").decode("ascii")
        raise ServiceClientInvalidHeaderError(
            f"header name failed RFC 7230 token validation "
            f"(len={len(name)}, prefix={prefix!r})"
        )
    return name


def _validate_header_value(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ServiceClientInvalidHeaderError(
            f"header '{name}' value must be a string " f"(got {type(value).__name__})"
        )
    if not value:
        raise ServiceClientInvalidHeaderError(
            f"header '{name}' value must not be empty"
        )
    if _HEADER_VALUE_BAD.search(value):
        # Don't echo the raw value — CRLF payload goes into logs otherwise.
        raise ServiceClientInvalidHeaderError(
            f"header '{name}' contains CRLF / control bytes " f"(len={len(value)})"
        )
    return value


def _validate_bearer_token(token: str) -> str:
    """Bearer-token validation shares the header-value rule set.

    Same CRLF / control-byte rejection. Empty string permitted here only
    to signal 'no auth' — callers pass ``None`` for that path; an empty
    string is treated as an invalid explicit value.
    """
    if not isinstance(token, str):
        raise ServiceClientInvalidHeaderError(
            f"bearer_token must be a string (got {type(token).__name__})"
        )
    if not token:
        raise ServiceClientInvalidHeaderError(
            "bearer_token must not be empty; pass None for no auth"
        )
    if _HEADER_VALUE_BAD.search(token):
        raise ServiceClientInvalidHeaderError(
            f"bearer_token contains CRLF / control bytes (len={len(token)})"
        )
    return token


# ---------------------------------------------------------------------------
# ServiceClient
# ---------------------------------------------------------------------------


class ServiceClient:
    """Typed service-to-service HTTP client.

    Constructor validates every header and the bearer token eagerly.
    Invalid inputs fail at construction, not at first request. This is
    non-negotiable per issue #473 — CRLF injection in a header must never
    silently reach the wire.

    Usage::

        client = ServiceClient(
            "https://api.example.com",
            bearer_token="...",
            allowed_hosts=["api.example.com"],
            timeout_secs=30.0,
            headers={"X-Client": "my-app"},
        )

        user = await client.get("/users/42")          # typed JSON
        resp = await client.get_raw("/healthz")        # HttpResponse, no status check

    Layer order (issue #473 NN1): the SSRF private-IP / metadata check runs
    BEFORE ``allowed_hosts`` is consulted. An allowlisted private IP is
    still rejected. The allowlist narrows the already-safe public set, it
    does NOT provide a bypass.
    """

    __slots__ = (
        "_base_url",
        "_http",
        "_headers",
        "_has_auth",
    )

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: Optional[str] = None,
        allowed_hosts: Optional[Sequence[str]] = None,
        timeout_secs: float = 30.0,
        connect_timeout_secs: float = 10.0,
        headers: Optional[Mapping[str, str]] = None,
        follow_redirects: bool = False,
        allow_loopback: bool = False,
    ) -> None:
        # ---- Base URL validation ----------------------------------------
        # httpx requires a well-formed absolute URL. Reject malformed base
        # URLs eagerly so the first request doesn't surface a cryptic error.
        if not isinstance(base_url, str) or not base_url:
            raise ServiceClientInvalidPathError("base_url must be a non-empty string")
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ServiceClientInvalidPathError(
                f"base_url must be an absolute http/https URL "
                f"(scheme={parsed.scheme!r})"
            )
        # httpx's urljoin with a trailing-slash-less base URL strips the
        # final segment on join. Normalise by ensuring exactly one trailing
        # slash so path joins are intuitive (``/foo`` -> ``base/foo``).
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self._base_url = base_url

        # ---- Eager header validation ------------------------------------
        merged: dict[str, str] = {}
        if headers is not None:
            for name, value in headers.items():
                vname = _validate_header_name(name)
                vvalue = _validate_header_value(vname, value)
                merged[vname] = vvalue

        # ---- Bearer-token validation ------------------------------------
        self._has_auth = False
        if bearer_token is not None:
            token = _validate_bearer_token(bearer_token)
            merged["Authorization"] = f"Bearer {token}"
            self._has_auth = True

        self._headers = merged

        # ---- Build underlying HttpClient --------------------------------
        config = HttpClientConfig(
            timeout_seconds=timeout_secs,
            connect_timeout_seconds=connect_timeout_secs,
            follow_redirects=follow_redirects,
            host_allowlist=list(allowed_hosts) if allowed_hosts else None,
            allow_loopback=allow_loopback,
            structured_log_prefix="nexus.service_client",
            default_headers={
                "Accept": "application/json",
                "User-Agent": "kailash-nexus/service-client",
            },
        )
        self._http = HttpClient(config)

        logger.info(
            "nexus.service_client.init",
            extra={
                "base_host": parsed.hostname,
                "has_auth": self._has_auth,
                "allowed_hosts_count": len(allowed_hosts) if allowed_hosts else 0,
                "timeout_secs": timeout_secs,
            },
        )

    # ---- Lifecycle --------------------------------------------------------

    async def __aenter__(self) -> "ServiceClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def has_auth(self) -> bool:
        return self._has_auth

    # ---- Path joining -----------------------------------------------------

    def _join(self, path: str) -> str:
        if not isinstance(path, str) or not path:
            raise ServiceClientInvalidPathError("path must be a non-empty string")
        # Strip a leading slash so urljoin uses the full base URL path
        # prefix. Example: base "https://api.example.com/v1/" + path
        # "/users" should produce "https://api.example.com/v1/users", NOT
        # "https://api.example.com/users".
        if path.startswith("/"):
            path = path.lstrip("/")
        try:
            joined = urljoin(self._base_url, path)
        except Exception as exc:
            raise ServiceClientInvalidPathError(
                f"could not join base_url + path: {type(exc).__name__}"
            ) from exc
        parsed = urlparse(joined)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ServiceClientInvalidPathError(
                "joined URL is not a well-formed http/https URL"
            )
        return joined

    # ---- Raw request — no status check -----------------------------------

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        url = self._join(path)
        # Merge instance headers with per-call headers. Per-call values win.
        headers: dict[str, str] = dict(self._headers)
        if extra_headers is not None:
            for name, value in extra_headers.items():
                vname = _validate_header_name(name)
                vvalue = _validate_header_value(vname, value)
                headers[vname] = vvalue

        # Serialise JSON up-front so a SerializeError surfaces cleanly
        # distinct from an httpx-layer failure.
        body_bytes: Optional[bytes] = None
        if json is not None:
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
            try:
                body_bytes = _json.dumps(json).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ServiceClientSerializeError(
                    f"request body is not JSON-serialisable: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        try:
            return await self._http.request(
                method,
                url,
                headers=headers,
                content=body_bytes,
            )
        except InvalidEndpointError as exc:
            # SSRF rejection at URL-parse or connect time. Translate into
            # the transport-layer ServiceClientHttpError so callers get one
            # typed surface for every "request did not reach upstream"
            # condition.
            raise ServiceClientHttpError(f"request blocked: {exc}", cause=exc) from exc
        except httpx.TimeoutException as exc:
            raise ServiceClientHttpError(
                f"request timeout: {type(exc).__name__}", cause=exc
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceClientHttpError(
                f"request error: {type(exc).__name__}", cause=exc
            ) from exc

    # ---- Public RAW variants — return HttpResponse, no status check ------

    async def get_raw(
        self,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        return await self._raw_request("GET", path, extra_headers=headers)

    async def post_raw(
        self,
        path: str,
        body: Any = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        return await self._raw_request("POST", path, json=body, extra_headers=headers)

    async def put_raw(
        self,
        path: str,
        body: Any = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        return await self._raw_request("PUT", path, json=body, extra_headers=headers)

    async def delete_raw(
        self,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        return await self._raw_request("DELETE", path, extra_headers=headers)

    # ---- Public TYPED variants — status-checked, JSON in/out -------------

    async def get(
        self,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        resp = await self.get_raw(path, headers=headers)
        return self._ensure_ok_and_decode(resp)

    async def post(
        self,
        path: str,
        body: Any = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        resp = await self.post_raw(path, body, headers=headers)
        return self._ensure_ok_and_decode(resp)

    async def put(
        self,
        path: str,
        body: Any = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        resp = await self.put_raw(path, body, headers=headers)
        return self._ensure_ok_and_decode(resp)

    async def delete(
        self,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        resp = await self.delete_raw(path, headers=headers)
        return self._ensure_ok_and_decode(resp)

    # ---- Response handling ------------------------------------------------

    def _ensure_ok_and_decode(self, resp: HttpResponse) -> Any:
        if 200 <= resp.status_code < 300:
            # Empty-body 2xx (e.g. 204 No Content) returns None rather than
            # raising a deserialize error. Callers that want a strict
            # "body must be JSON" contract use the raw variant + decode.
            if not resp.body:
                return None
            try:
                return _json.loads(resp.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ServiceClientDeserializeError(
                    f"response body is not valid UTF-8 JSON: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        raise ServiceClientHttpStatusError(
            status_code=resp.status_code,
            body=resp.body,
            url=resp.url,
        )


__all__ = [
    "ServiceClient",
    "ServiceClientError",
    "ServiceClientHttpError",
    "ServiceClientHttpStatusError",
    "ServiceClientSerializeError",
    "ServiceClientDeserializeError",
    "ServiceClientInvalidPathError",
    "ServiceClientInvalidHeaderError",
]

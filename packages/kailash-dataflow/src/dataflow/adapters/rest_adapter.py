# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
REST Source Adapter — fetch data from HTTP/JSON APIs.

Implements BaseSourceAdapter for REST endpoints with:
- Bearer, API key, Basic, and OAuth2 authentication
- Conditional GET (ETag / Last-Modified) with content-hash fallback (RT-5)
- Auto-pagination via Link header ``next`` or offset parameter
- SSRF protection on all outbound URLs
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urljoin, urlparse

# httpx is declared under `kailash-dataflow[fabric]` — gate the import so a
# base install without the fabric extra still imports this module (lazy
# adapter dispatch from `dataflow.core.engine` touches the file even when
# no REST source is configured). Fail loudly at call time if the extra
# was not installed; see rules/dependencies.md § "Declared = Gated Consistently".
try:
    import httpx  # noqa: F401
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from dataflow.adapters.source_adapter import BaseSourceAdapter
from dataflow.fabric.config import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuth2Auth,
    RestSourceConfig,
)
from dataflow.fabric.ssrf import validate_url_safe

logger = logging.getLogger(__name__)

__all__ = ["RestSourceAdapter"]


class RestSourceAdapter(BaseSourceAdapter):
    """Source adapter for REST/JSON APIs.

    Manages an ``httpx.AsyncClient`` lifecycle, applies per-request auth,
    and supports conditional GET with automatic fallback to content-hash
    comparison when the API does not provide ``ETag`` or ``Last-Modified``.
    """

    def __init__(self, name: str, config: RestSourceConfig, **kwargs: Any) -> None:
        if httpx is None:
            raise ImportError(
                "RestSourceAdapter requires the [fabric] extra: "
                "`pip install kailash-dataflow[fabric]`"
            )
        super().__init__(name=name, **kwargs)
        config.validate()
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

        # ETag / Last-Modified detection state (RT-5)
        self._supports_etag: Optional[bool] = None
        self._supports_last_modified: Optional[bool] = None
        self._last_etag: Optional[str] = None
        self._last_modified: Optional[str] = None
        self._last_content_hash: Optional[str] = None
        self._oauth2_manager: Optional[Any] = None

    # ------------------------------------------------------------------
    # BaseAdapter / BaseSourceAdapter properties
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> str:
        return "rest"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """Create ``httpx.AsyncClient`` with SSRF-validated base URL."""
        validate_url_safe(self.config.url)
        base_headers = dict(self.config.headers)
        base_headers.setdefault("Accept", "application/json")

        auth = None
        if isinstance(self.config.auth, BasicAuth):
            username, password = self.config.auth.get_credentials()
            auth = httpx.BasicAuth(username=username, password=password)

        self._client = httpx.AsyncClient(
            base_url=self.config.url,
            headers=base_headers,
            auth=auth,
            timeout=httpx.Timeout(self.config.timeout),
        )
        logger.info("REST source '%s' connected to %s", self.name, self.config.url)

    async def _disconnect(self) -> None:
        """Close the httpx client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("REST source '%s' disconnected", self.name)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    async def _apply_request_auth(self, headers: Dict[str, str]) -> None:
        """Apply per-request auth headers (Bearer / API key / OAuth2).

        BasicAuth is handled at the client level.
        """
        auth = self.config.auth
        if isinstance(auth, BearerAuth):
            headers["Authorization"] = f"Bearer {auth.get_token()}"
        elif isinstance(auth, ApiKeyAuth):
            headers[auth.header] = auth.get_key()
        elif isinstance(auth, OAuth2Auth):
            if self._oauth2_manager is None:
                from dataflow.fabric.auth import OAuth2TokenManager

                self._oauth2_manager = OAuth2TokenManager(auth)
            token = await self._oauth2_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        # BasicAuth is configured on self._client — nothing to do here.

    def _ensure_connected(self) -> httpx.AsyncClient:
        """Return the httpx client, raising if not connected."""
        if self._client is None:
            raise ConnectionError(
                f"REST source '{self.name}' is not connected. Call connect() first."
            )
        return self._client

    # ------------------------------------------------------------------
    # URL safety
    # ------------------------------------------------------------------

    def _safe_url(self, path: str) -> str:
        """Build and SSRF-validate a full URL from a relative *path*.

        For paths that are fully-qualified URLs we validate directly.
        For relative paths we join with the base URL and validate the result.
        """
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            validate_url_safe(path)
            return path
        full = urljoin(self.config.url.rstrip("/") + "/", path.lstrip("/"))
        validate_url_safe(full)
        return path  # httpx resolves relative paths against base_url

    # ------------------------------------------------------------------
    # Change detection (RT-5)
    # ------------------------------------------------------------------

    async def detect_change(self) -> bool:
        """Detect whether the source data has changed.

        On the first call a HEAD request probes for ``ETag`` and
        ``Last-Modified`` support.  Subsequent calls use conditional GET
        (``If-None-Match`` / ``If-Modified-Since``) when available, or
        fall back to SHA-256 content hashing.
        """
        client = self._ensure_connected()
        headers: Dict[str, str] = {}
        await self._apply_request_auth(headers)

        # First call: probe for conditional GET support
        if self._supports_etag is None and self._supports_last_modified is None:
            probe = await client.head("/", headers=headers)
            self._supports_etag = "etag" in probe.headers
            self._supports_last_modified = "last-modified" in probe.headers

            if self._supports_etag:
                self._last_etag = probe.headers["etag"]
            if self._supports_last_modified:
                self._last_modified = probe.headers["last-modified"]

            # First call always reports changed (no prior baseline).
            return True

        # Conditional GET using ETag
        if self._supports_etag and self._last_etag:
            headers["If-None-Match"] = self._last_etag
            resp = await client.get("/", headers=headers)
            if resp.status_code == 304:
                return False
            # Data changed -- update stored ETag
            new_etag = resp.headers.get("etag")
            if new_etag:
                self._last_etag = new_etag
            return True

        # Conditional GET using Last-Modified
        if self._supports_last_modified and self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
            resp = await client.get("/", headers=headers)
            if resp.status_code == 304:
                return False
            new_lm = resp.headers.get("last-modified")
            if new_lm:
                self._last_modified = new_lm
            return True

        # Fallback: content-hash comparison (SHA-256)
        return await self._detect_via_content_hash(client, headers)

    async def _detect_via_content_hash(
        self, client: httpx.AsyncClient, headers: Dict[str, str]
    ) -> bool:
        """Full GET + SHA-256 comparison for APIs without conditional support."""
        resp = await client.get("/", headers=headers)
        resp.raise_for_status()
        content_hash = hashlib.sha256(resp.content).hexdigest()

        if self._last_content_hash is None:
            self._last_content_hash = content_hash
            return True  # No prior baseline -- report changed

        changed = content_hash != self._last_content_hash
        if changed:
            self._last_content_hash = content_hash
        return changed

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """GET ``{base_url}/{path}`` and return parsed JSON."""
        client = self._ensure_connected()
        safe_path = self._safe_url(path) if path else "/"
        headers: Dict[str, str] = {}
        await self._apply_request_auth(headers)

        resp = await client.get(safe_path, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        self._record_successful_data(path, data)
        return data

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Stream pages of JSON array data.

        Pagination strategy (tried in order):

        1. **Link header** -- follow ``rel="next"`` URLs (RFC 8288).
        2. **Offset parameter** -- increment ``offset`` by ``page_size``
           until an empty page is returned.
        """
        client = self._ensure_connected()
        safe_path = self._safe_url(path) if path else "/"
        headers: Dict[str, str] = {}
        await self._apply_request_auth(headers)

        # First request
        params: Dict[str, Any] = {"limit": page_size, "offset": 0}
        resp = await client.get(safe_path, headers=headers, params=params)
        resp.raise_for_status()
        page = resp.json()

        if isinstance(page, list):
            if not page:
                return
            yield page
        else:
            # If API returns a wrapper object, try common keys
            items = (
                page.get("results")
                or page.get("data")
                or page.get("items")
                or page.get("records")
            )
            if items is None:
                yield [page]
                return
            if not items:
                return
            yield items

        # Follow Link: <url>; rel="next" if present
        next_url = self._parse_next_link(resp.headers.get("link", ""))

        while True:
            if next_url:
                validate_url_safe(next_url)
                next_headers: Dict[str, str] = {}
                await self._apply_request_auth(next_headers)
                resp = await client.get(next_url, headers=next_headers)
            else:
                params["offset"] += page_size
                resp = await client.get(safe_path, headers=headers, params=params)

            resp.raise_for_status()
            page = resp.json()

            if isinstance(page, list):
                if not page:
                    break
                yield page
            else:
                items = (
                    page.get("results")
                    or page.get("data")
                    or page.get("items")
                    or page.get("records")
                )
                if not items:
                    break
                yield items

            # Check for next link on this response
            next_url = self._parse_next_link(resp.headers.get("link", ""))

    @staticmethod
    def _parse_next_link(link_header: str) -> Optional[str]:
        """Extract the ``next`` URL from an RFC 8288 Link header."""
        if not link_header:
            return None
        for part in link_header.split(","):
            part = part.strip()
            if 'rel="next"' in part or "rel='next'" in part:
                # Extract URL between < and >
                start = part.find("<")
                end = part.find(">")
                if start != -1 and end != -1:
                    return part[start + 1 : end]
        return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(self, path: str, data: Any) -> Any:
        """POST JSON data to ``{base_url}/{path}``."""
        client = self._ensure_connected()
        safe_path = self._safe_url(path) if path else "/"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        await self._apply_request_auth(headers)

        resp = await client.post(safe_path, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Feature support
    # ------------------------------------------------------------------

    def supports_feature(self, feature: str) -> bool:
        """REST adapters support detect_change, fetch, fetch_pages, and write."""
        return feature in {"detect_change", "fetch", "fetch_pages", "write"}

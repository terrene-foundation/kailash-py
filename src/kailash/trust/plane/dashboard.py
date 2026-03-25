# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Web-based Trust Status Dashboard for TrustPlane.

Serves a read-only HTML dashboard using only stdlib ``http.server``.
Binds to ``127.0.0.1`` only (never ``0.0.0.0``) for security.

Usage:
    from kailash.trust.plane.dashboard import serve_dashboard
    serve_dashboard(trust_dir="./trust-plane", port=8080)
"""

from __future__ import annotations

import hmac as hmac_mod
import html
import json
import logging
import os
import secrets
import stat
import tempfile
from datetime import timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from kailash.trust.plane.dashboard_templates import render_template
from kailash.trust.plane.holds import HoldManager
from kailash.trust.plane.models import (
    DecisionRecord,
    MilestoneRecord,
    _decision_type_value,
)
from kailash.trust.plane.project import TrustProject

logger = logging.getLogger(__name__)

__all__ = [
    "serve_dashboard",
    "create_dashboard_handler",
    "load_or_create_token",
]

_ITEMS_PER_PAGE = 25
_API_DEFAULT_LIMIT = 100
_API_MAX_LIMIT = 1000
_TOKEN_FILENAME = ".dashboard-token"


def _generate_token() -> str:
    """Generate a cryptographically secure bearer token.

    Returns:
        A URL-safe base64-encoded token string (43 characters).
    """
    return secrets.token_urlsafe(32)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write a plain text file atomically via temp file + rename.

    Uses the same crash-safety pattern as ``atomic_write()`` in
    ``_locking.py`` but writes plain text instead of JSON.  The file
    is created with ``0o600`` permissions (owner read/write only).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            fd = -1  # os.fdopen took ownership
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        os.replace(tmp_path, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_or_create_token(trust_dir: str | Path) -> str:
    """Load an existing dashboard token or create a new one.

    The token is stored in ``{trust_dir}/.dashboard-token`` with
    ``0o600`` permissions.  If the file already exists, its contents
    are returned.  Otherwise a new token is generated and persisted.

    Args:
        trust_dir: Path to the trust-plane directory.

    Returns:
        The bearer token string.
    """
    token_path = Path(trust_dir) / _TOKEN_FILENAME
    if token_path.exists():
        from kailash.trust._locking import safe_read_text

        try:
            token = safe_read_text(token_path).strip()
            if token:
                return token
        except OSError:
            pass  # File unreadable — generate a new token
    token = _generate_token()
    _atomic_write_text(token_path, token)
    logger.info("Generated new dashboard bearer token at %s", token_path)
    return token


def _esc(value: object) -> str:
    """HTML-escape a value for safe rendering in templates."""
    return html.escape(str(value))


def _format_timestamp(dt: Any) -> str:
    """Format a datetime for display."""
    if dt is None:
        return ""
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(dt)


def _trust_badge_html(chain_valid: bool) -> str:
    """Return an HTML badge for the trust posture."""
    if chain_valid:
        return '<span class="badge badge-pass">VALID</span>'
    return '<span class="badge badge-fail">INVALID</span>'


def _hold_status_badge(status: str) -> str:
    """Return an HTML badge for a hold status."""
    if status == "approved":
        return '<span class="badge badge-pass">APPROVED</span>'
    if status == "denied":
        return '<span class="badge badge-fail">DENIED</span>'
    return '<span class="badge badge-pending">PENDING</span>'


def _milestone_badge(file_hash: str) -> str:
    """Return an HTML badge for milestone verification status."""
    if file_hash:
        return '<span class="badge badge-pass">HASHED</span>'
    return '<span class="badge badge-info">NO FILE</span>'


def _render_decisions_table(decisions: list[DecisionRecord]) -> str:
    """Render an HTML table of decisions."""
    if not decisions:
        return '<div class="empty-state"><p>No decisions recorded yet.</p></div>'

    rows = []
    for d in decisions:
        dt_val = _esc(_decision_type_value(d.decision_type))
        rows.append(
            f"<tr>"
            f"<td><code>{_esc(d.decision_id)}</code></td>"
            f"<td>{dt_val}</td>"
            f"<td>{_esc(d.decision)}</td>"
            f"<td>{_esc(d.rationale)}</td>"
            f"<td>{d.confidence:.2f}</td>"
            f"<td>{_format_timestamp(d.timestamp)}</td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<thead><tr>"
        "<th>ID</th><th>Type</th><th>Decision</th>"
        "<th>Rationale</th><th>Confidence</th><th>Timestamp</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _render_milestones_table(milestones: list[MilestoneRecord]) -> str:
    """Render an HTML table of milestones."""
    if not milestones:
        return '<div class="empty-state"><p>No milestones recorded yet.</p></div>'

    rows = []
    for m in milestones:
        badge = _milestone_badge(m.file_hash)
        file_display = _esc(m.file_path) if m.file_path else "—"
        hash_display = (
            f"<code>{_esc(m.file_hash[:16])}...</code>" if m.file_hash else "—"
        )
        rows.append(
            f"<tr>"
            f"<td><code>{_esc(m.milestone_id)}</code></td>"
            f"<td>{_esc(m.version)}</td>"
            f"<td>{_esc(m.description)}</td>"
            f"<td>{file_display}</td>"
            f"<td>{hash_display}</td>"
            f"<td>{badge}</td>"
            f"<td>{_format_timestamp(m.timestamp)}</td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<thead><tr>"
        "<th>ID</th><th>Version</th><th>Description</th>"
        "<th>File</th><th>Hash</th><th>Status</th><th>Timestamp</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _render_holds_table(holds: list[Any]) -> str:
    """Render an HTML table of holds."""
    if not holds:
        return '<div class="empty-state"><p>No active holds.</p></div>'

    rows = []
    for h in holds:
        badge = _hold_status_badge(h.status)
        rows.append(
            f"<tr>"
            f"<td><code>{_esc(h.hold_id)}</code></td>"
            f"<td>{_esc(h.action)}</td>"
            f"<td>{_esc(h.resource)}</td>"
            f"<td>{_esc(h.reason)}</td>"
            f"<td>{badge}</td>"
            f"<td>{_format_timestamp(h.created_at)}</td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<thead><tr>"
        "<th>ID</th><th>Action</th><th>Resource</th>"
        "<th>Reason</th><th>Status</th><th>Created</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _render_pagination(current_page: int, total_pages: int, base_url: str) -> str:
    """Render pagination links."""
    if total_pages <= 1:
        return ""

    links = []
    if current_page > 1:
        links.append(f'<a href="{base_url}&page={current_page - 1}">Previous</a>')

    for p in range(1, total_pages + 1):
        active = " active" if p == current_page else ""
        links.append(f'<a class="{active}" href="{base_url}&page={p}">{p}</a>')

    if current_page < total_pages:
        links.append(f'<a href="{base_url}&page={current_page + 1}">Next</a>')

    return f'<div class="pagination">{"".join(links)}</div>'


def _wrap_in_base(content: str, active_nav: str, title_suffix: str = "") -> str:
    """Wrap content in the base layout template."""
    nav_classes = {
        "overview": "",
        "decisions": "",
        "milestones": "",
        "holds": "",
        "verify": "",
    }
    nav_classes[active_nav] = " active"
    if title_suffix:
        title_suffix = f" - {title_suffix}"
    return render_template(
        "base",
        content=content,
        title_suffix=title_suffix,
        nav_overview=nav_classes["overview"],
        nav_decisions=nav_classes["decisions"],
        nav_milestones=nav_classes["milestones"],
        nav_holds=nav_classes["holds"],
        nav_verify=nav_classes["verify"],
    )


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    import asyncio

    return asyncio.run(coro)


def create_dashboard_handler(
    project: TrustProject,
    hold_manager: HoldManager,
    auth_token: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class bound to the given project.

    Args:
        project: A loaded TrustProject.
        hold_manager: A HoldManager for the project.
        auth_token: If set, all ``/api/`` endpoints require an
            ``Authorization: Bearer <token>`` header matching this value.
            Pass ``None`` to disable authentication (``--no-auth`` mode).

    Returns:
        A subclass of BaseHTTPRequestHandler.
    """

    class DashboardHandler(BaseHTTPRequestHandler):
        """HTTP request handler for the TrustPlane dashboard."""

        _project = project
        _hold_manager = hold_manager
        _auth_token: str | None = auth_token

        def log_message(self, format: str, *args: Any) -> None:
            """Route HTTP logs through the trustplane logger."""
            logger.info(format, *args)

        def _check_auth(self, path: str) -> bool:
            """Verify bearer token for API endpoints.

            Returns ``True`` if the request is authorized to proceed.
            Returns ``False`` after sending a 401 response.
            """
            if self._auth_token is None:
                return True  # auth disabled (--no-auth)

            if not path.startswith("/api/"):
                return True  # non-API paths don't require auth

            auth_header = self.headers.get("Authorization", "")
            if not auth_header:
                self._send_json_error(
                    HTTPStatus.UNAUTHORIZED,
                    "Authentication required. Provide an "
                    "'Authorization: Bearer <token>' header. "
                    "The token was displayed when the dashboard started.",
                )
                return False

            # Expect "Bearer <token>"
            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0] != "Bearer":
                self._send_json_error(
                    HTTPStatus.UNAUTHORIZED,
                    "Invalid Authorization header format. "
                    "Expected: 'Authorization: Bearer <token>'",
                )
                return False

            provided_token = parts[1]
            if not hmac_mod.compare_digest(provided_token, self._auth_token):
                self._send_json_error(
                    HTTPStatus.UNAUTHORIZED,
                    "Invalid bearer token.",
                )
                return False

            return True

        def do_GET(self) -> None:  # noqa: N802
            """Handle GET requests."""
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)

            # Check authentication before routing
            if not self._check_auth(path):
                return

            routes: dict[str, Any] = {
                "/": self._handle_overview,
                "/decisions": self._handle_decisions,
                "/milestones": self._handle_milestones,
                "/holds": self._handle_holds,
                "/verify": self._handle_verify,
                "/api/decisions": self._handle_api_decisions,
                "/api/milestones": self._handle_api_milestones,
                "/api/holds": self._handle_api_holds,
                "/api/verify": self._handle_api_verify,
            }

            handler = routes.get(path)
            if handler is None:
                self._send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return

            handler(query)

        # --- HTML pages ---

        def _handle_overview(self, query: dict[str, list[str]]) -> None:
            proj = self._project
            m = proj.manifest

            decisions = proj.get_decisions()
            milestones = proj.get_milestones()
            pending_holds = self._hold_manager.list_pending()

            # Run verification
            try:
                report = _run_async(proj.verify())
                chain_valid = report.get("chain_valid", False)
            except Exception:
                chain_valid = False

            # Recent decisions (last 5)
            recent = sorted(decisions, key=lambda d: d.timestamp, reverse=True)[:5]

            content = render_template(
                "overview",
                project_name=_esc(m.project_name),
                project_author=_esc(m.author),
                project_id=_esc(m.project_id),
                genesis_id=_esc(m.genesis_id),
                created_at=_format_timestamp(m.created_at),
                chain_hash=_esc(m.chain_hash or "—"),
                trust_badge=_trust_badge_html(chain_valid),
                total_decisions=str(len(decisions)),
                total_milestones=str(len(milestones)),
                active_holds=str(len(pending_holds)),
                recent_decisions_table=_render_decisions_table(recent),
            )
            page = _wrap_in_base(content, "overview")
            self._send_html(page)

        def _handle_decisions(self, query: dict[str, list[str]]) -> None:
            decisions = self._project.get_decisions()

            # Type filter
            type_filter = query.get("type", [""])[0]
            if type_filter:
                decisions = [
                    d
                    for d in decisions
                    if _decision_type_value(d.decision_type) == type_filter
                ]

            # Collect all types for the filter dropdown
            all_decisions = self._project.get_decisions()
            all_types = sorted(
                {_decision_type_value(d.decision_type) for d in all_decisions}
            )
            type_options = '<option value="">All</option>'
            for t in all_types:
                selected = " selected" if t == type_filter else ""
                type_options += (
                    f'<option value="{_esc(t)}"{selected}>{_esc(t)}</option>'
                )

            # Pagination
            try:
                page_num = int(query.get("page", ["1"])[0])
            except (ValueError, IndexError):
                page_num = 1
            total_pages = max(
                1, (len(decisions) + _ITEMS_PER_PAGE - 1) // _ITEMS_PER_PAGE
            )
            page_num = max(1, min(page_num, total_pages))
            start = (page_num - 1) * _ITEMS_PER_PAGE
            page_items = decisions[start : start + _ITEMS_PER_PAGE]

            base_url = f"/decisions?type={_esc(type_filter)}"
            pagination = _render_pagination(page_num, total_pages, base_url)

            content = render_template(
                "decisions",
                total_count=str(len(decisions)),
                type_options=type_options,
                decisions_table=_render_decisions_table(page_items),
                pagination=pagination,
            )
            page = _wrap_in_base(content, "decisions", "Decisions")
            self._send_html(page)

        def _handle_milestones(self, query: dict[str, list[str]]) -> None:
            milestones = self._project.get_milestones()

            content = render_template(
                "milestones",
                total_count=str(len(milestones)),
                milestones_table=_render_milestones_table(milestones),
            )
            page = _wrap_in_base(content, "milestones", "Milestones")
            self._send_html(page)

        def _handle_holds(self, query: dict[str, list[str]]) -> None:
            holds = self._hold_manager.list_pending()

            content = render_template(
                "holds",
                total_count=str(len(holds)),
                holds_table=_render_holds_table(holds),
            )
            page = _wrap_in_base(content, "holds", "Holds")
            self._send_html(page)

        def _handle_verify(self, query: dict[str, list[str]]) -> None:
            report: dict[str, Any] = {}
            try:
                report = _run_async(self._project.verify())
                chain_valid = report.get("chain_valid", False)
                issues = report.get("integrity_issues", [])
            except Exception as e:
                chain_valid = False
                issues = [str(e)]

            if chain_valid:
                result_class = "verify-pass"
                result_title = "Chain Integrity: VALID"
            else:
                result_class = "verify-fail"
                result_title = "Chain Integrity: INVALID"

            issues_html = ""
            if issues:
                items = "".join(f"<li>{_esc(i)}</li>" for i in issues)
                issues_html = f'<ul class="verify-issues">{items}</ul>'

            # Build verify content inline (no separate template needed,
            # keeps template count minimal)
            content = (
                '<div class="page-header">'
                "<h2>Verification</h2>"
                "<p>EATP trust chain integrity check</p>"
                "</div>"
                f'<div class="verify-result {result_class}">'
                f"<h3>{result_title}</h3>"
                f"<p>Anchors: {report.get('total_anchors', 0)} | "
                f"Decisions: {report.get('total_decisions', 0)} | "
                f"Milestones: {report.get('total_milestones', 0)} | "
                f"Audits: {report.get('total_audits', 0)}</p>"
                f"{issues_html}"
                "</div>"
            )
            page = _wrap_in_base(content, "verify", "Verify")
            self._send_html(page)

        # --- JSON API ---

        def _parse_pagination_params(
            self, query: dict[str, list[str]]
        ) -> tuple[int, int] | None:
            """Parse and validate limit/offset query parameters.

            Returns:
                A (limit, offset) tuple on success, or None if a 400
                error response was already sent due to invalid parameters.
            """
            # Parse limit
            raw_limit = query.get("limit", [""])[0]
            if raw_limit:
                try:
                    limit = int(raw_limit)
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Invalid limit parameter: {raw_limit!r} is not an integer",
                    )
                    return None
                if limit <= 0:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Invalid limit parameter: {limit} must be greater than 0",
                    )
                    return None
                if limit > _API_MAX_LIMIT:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Invalid limit parameter: {limit} exceeds maximum of {_API_MAX_LIMIT}",
                    )
                    return None
            else:
                limit = _API_DEFAULT_LIMIT

            # Parse offset
            raw_offset = query.get("offset", [""])[0]
            if raw_offset:
                try:
                    offset = int(raw_offset)
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Invalid offset parameter: {raw_offset!r} is not an integer",
                    )
                    return None
                if offset < 0:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        f"Invalid offset parameter: {offset} must not be negative",
                    )
                    return None
            else:
                offset = 0

            return limit, offset

        def _paginate_items(
            self, items: list[dict[str, Any]], limit: int, offset: int
        ) -> dict[str, Any]:
            """Apply pagination to a list of serialized items.

            Returns a pagination envelope dict with keys:
                items, total_count, has_more, next_offset.
            """
            total_count = len(items)
            page_items = items[offset : offset + limit]
            has_more = (offset + limit) < total_count
            next_offset = (offset + limit) if has_more else None

            return {
                "items": page_items,
                "total_count": total_count,
                "has_more": has_more,
                "next_offset": next_offset,
            }

        def _handle_api_decisions(self, query: dict[str, list[str]]) -> None:
            params = self._parse_pagination_params(query)
            if params is None:
                return  # 400 already sent
            limit, offset = params

            decisions = self._project.get_decisions()

            type_filter = query.get("type", [""])[0]
            if type_filter:
                decisions = [
                    d
                    for d in decisions
                    if _decision_type_value(d.decision_type) == type_filter
                ]

            data = [d.to_dict() for d in decisions]
            self._send_json(self._paginate_items(data, limit, offset))

        def _handle_api_milestones(self, query: dict[str, list[str]]) -> None:
            params = self._parse_pagination_params(query)
            if params is None:
                return  # 400 already sent
            limit, offset = params

            milestones = self._project.get_milestones()
            data = [m.to_dict() for m in milestones]
            self._send_json(self._paginate_items(data, limit, offset))

        def _handle_api_holds(self, query: dict[str, list[str]]) -> None:
            params = self._parse_pagination_params(query)
            if params is None:
                return  # 400 already sent
            limit, offset = params

            holds = self._hold_manager.list_all()
            data = [h.to_dict() for h in holds]
            self._send_json(self._paginate_items(data, limit, offset))

        def _handle_api_verify(self, query: dict[str, list[str]]) -> None:
            try:
                report = _run_async(self._project.verify())
            except Exception as e:
                report = {"chain_valid": False, "error": str(e)}
            self._send_json(report)

        # --- Response helpers ---

        def _send_security_headers(self) -> None:
            """Add security headers to prevent XSS, clickjacking, MIME sniffing."""
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'",
            )

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, data: Any) -> None:
            body = json.dumps(data, indent=2, default=str).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_json_error(self, status: HTTPStatus, message: str) -> None:
            """Send a JSON error response for API endpoints."""
            error_body = {"error": message}
            body = json.dumps(error_body, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            body = f"<h1>{status.value} {message}</h1>".encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def serve_dashboard(
    trust_dir: str,
    port: int = 8080,
    open_browser: bool = False,
    no_auth: bool = False,
) -> None:
    """Start the dashboard HTTP server.

    Args:
        trust_dir: Path to the trust-plane directory.
        port: Port to bind on (default: 8080).
        open_browser: If True, open the dashboard in the default browser.
        no_auth: If True, disable bearer token authentication.
            A security warning is printed when this is enabled.

    Raises:
        FileNotFoundError: If no project exists at trust_dir.
    """
    import asyncio

    project = asyncio.run(TrustProject.load(trust_dir))
    hold_manager = HoldManager(Path(trust_dir), store=project._tp_store)

    # Token management
    if no_auth:
        auth_token = None
        print(
            "WARNING: Dashboard authentication is DISABLED (--no-auth). "
            "API endpoints are accessible without a token."
        )
    else:
        auth_token = load_or_create_token(trust_dir)

    handler_class = create_dashboard_handler(
        project, hold_manager, auth_token=auth_token
    )

    server = HTTPServer(("127.0.0.1", port), handler_class)
    url = f"http://127.0.0.1:{port}"

    logger.info("Dashboard server starting at %s", url)
    print(f"TrustPlane Dashboard running at {url}")

    if auth_token is not None:
        print(f"Bearer token: {auth_token}")
        print(
            "Use this token in API requests: "
            f"curl -H 'Authorization: Bearer {auth_token}' {url}/api/verify"
        )

    print("Press Ctrl+C to stop.")

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
    finally:
        server.server_close()

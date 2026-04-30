# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""WebSocket Origin allowlist validation (issue #673).

Pre-upgrade ``Origin`` and ``Host`` allowlist enforcement is the
structural defense against DNS-rebinding attacks on WebSocket
endpoints (per ``rules/security.md`` § "Network Transport
Hardening" + ``rules/ui-backend-defense.md`` Rule 3 layered defense).

This module exposes:

- :func:`validate_origin_allowlist` — validates an allowlist entry
  list at registration time, refusing the literal ``"*"`` wildcard
  unless the env flag ``KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN=true``
  is set.

- :func:`origin_matches_allowlist` — runtime predicate used by the
  :class:`MessageHandlerRegistry` BEFORE invoking ``on_connect``.
  Returns ``True`` only when the supplied origin matches at least
  one allowlist entry exactly OR matches a ``https://*.example.com``
  wildcard pattern.

- :func:`fingerprint_origin` — produces an 8-char SHA-256 prefix
  used in WARN-level audit logs per ``rules/observability.md``
  Rule 6 + Rule 8 (schema-revealing identifiers MUST be hashed at
  WARN; raw values MUST NOT be echoed).

Cross-SDK parity: kailash-rs is expected to ship the same surface
semantically (per EATP D6) at the equivalent register_websocket
surface. Filed cross-SDK followup issue tracks the Rust side.
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List, Optional

__all__ = [
    "WILDCARD_ORIGIN_ENV_FLAG",
    "WildcardOriginRefusedError",
    "fingerprint_origin",
    "origin_matches_allowlist",
    "validate_origin_allowlist",
]


WILDCARD_ORIGIN_ENV_FLAG = "KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN"
"""Env flag that opts in to the literal ``"*"`` wildcard allowlist entry.

When this env var is set to the case-insensitive string ``"true"``,
:func:`validate_origin_allowlist` will accept the literal ``"*"``
entry. In every other case (unset, ``"false"``, ``"0"``, etc.), the
literal ``"*"`` is rejected with :class:`WildcardOriginRefusedError`.

This is intentionally fail-closed: production deployments MUST list
explicit origins; the ``"*"`` opt-in is for development / private
internal services where the operator has explicitly accepted that
any browser-reachable origin can open the socket.
"""


class WildcardOriginRefusedError(ValueError):
    """Raised when ``"*"`` appears in ``allowed_origins`` without env opt-in.

    Subclass of ``ValueError`` so callers using broad ``except
    ValueError`` still catch it; the typed subclass lets careful
    callers distinguish wildcard refusal from other validation
    failures.
    """


def _wildcard_env_set() -> bool:
    """Return True iff ``KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN`` opts in.

    Read at validation time (not at module import) so test fixtures
    using ``monkeypatch.setenv`` can flip the flag per test.
    """
    return os.environ.get(WILDCARD_ORIGIN_ENV_FLAG, "").strip().lower() == "true"


def validate_origin_allowlist(
    allowed_origins: Optional[Iterable[str]],
) -> Optional[List[str]]:
    """Validate the ``allowed_origins`` parameter at registration time.

    Returns the validated list (a fresh ``list[str]``) or ``None`` if
    the input was ``None``. Raises ``ValueError`` (or its subclass
    :class:`WildcardOriginRefusedError`) on any invalid entry.

    Validation rules:

    - ``None`` → returned as-is. Caller MUST emit a one-time WARN log
      naming the path so operators see the gap (handled at the
      registration site, not here).
    - Must be a non-string iterable (a bare ``str`` is BLOCKED — a
      common bug where someone writes ``allowed_origins="https://x"``
      instead of ``allowed_origins=["https://x"]``).
    - Must be non-empty when non-``None``.
    - Each entry MUST be a non-empty string.
    - The literal ``"*"`` is BLOCKED unless
      ``KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN=true`` is set in env.
    - Each non-wildcard entry MUST start with ``https://`` or
      ``http://`` (case-insensitive scheme check).
    - Wildcard subdomain entries MUST take the form
      ``https://*.example.com`` (a single ``*`` immediately after
      the scheme separator and before the rest of the host). Other
      ``*`` placements are BLOCKED.
    """
    if allowed_origins is None:
        return None
    if isinstance(allowed_origins, str):
        # Bare-string trap: someone wrote allowed_origins="https://x"
        # expecting it to allowlist that origin. Reject loudly.
        raise ValueError(
            "allowed_origins must be a list of strings, not a single string "
            '(did you mean allowed_origins=["https://..."]?)'
        )
    entries: List[str] = list(allowed_origins)
    if not entries:
        raise ValueError(
            "allowed_origins must be a non-empty list when not None; "
            "pass None to disable SDK enforcement"
        )
    validated: List[str] = []
    for raw in entries:
        if not isinstance(raw, str):
            raise ValueError(
                f"allowed_origins entries must be str; " f"got {type(raw).__name__}"
            )
        entry = raw.strip()
        if not entry:
            raise ValueError("allowed_origins entries must be non-empty strings")
        if entry == "*":
            if not _wildcard_env_set():
                raise WildcardOriginRefusedError(
                    "allowed_origins=['*'] is fail-closed by default; set "
                    f"{WILDCARD_ORIGIN_ENV_FLAG}=true in env to opt in. "
                    "This is intentionally noisy: '*' allows ANY browser-"
                    "reachable origin to open the socket and disables the "
                    "DNS-rebinding defense the allowlist exists to provide."
                )
            validated.append("*")
            continue
        # Scheme check (https:// or http://, case-insensitive).
        lower = entry.lower()
        if not (lower.startswith("https://") or lower.startswith("http://")):
            raise ValueError(
                f"allowed_origins entries must start with 'https://' or "
                f"'http://' (got {entry!r})"
            )
        # Wildcard subdomain shape check: only allowed pattern is
        # "<scheme>://*.<host>"; any other "*" is rejected.
        if "*" in entry:
            scheme_sep = "://"
            sep_idx = entry.index(scheme_sep)
            after_scheme = entry[sep_idx + len(scheme_sep) :]
            if not after_scheme.startswith("*."):
                raise ValueError(
                    f"wildcard subdomain entries must take the form "
                    f"'<scheme>://*.<host>' (got {entry!r})"
                )
            if "*" in after_scheme[2:]:
                raise ValueError(
                    f"wildcard subdomain entries may contain only one '*' "
                    f"immediately after the scheme separator (got {entry!r})"
                )
        validated.append(entry)
    return validated


def origin_matches_allowlist(origin: object, allowed_origins: List[str]) -> bool:
    """Return True iff ``origin`` matches at least one allowlist entry.

    Shape-rejects non-string origins explicitly per
    ``rules/ui-backend-defense.md`` Rule 2: a non-string ``origin``
    (e.g., a header that arrived as ``None`` because the client did
    not send it, or somehow as a list) raises ``ValueError``. The
    caller is the registry which catches the raise and rejects the
    upgrade — converting a runtime crash into a clean reject.

    An empty-string origin returns ``False`` (no match) — empty is
    not a valid origin and never matches a non-empty allowlist
    entry.

    Matching rules:

    - Exact-string match (case-sensitive comparison of the full
      origin including scheme + host + optional port).
    - ``"*"`` wildcard entry matches every non-empty origin (only
      reachable when env opt-in already validated at
      :func:`validate_origin_allowlist`).
    - ``"https://*.example.com"`` style wildcard matches origins
      whose host is a strict subdomain of ``example.com`` AND
      whose scheme matches the entry's scheme. Does NOT match the
      bare ``example.com`` (the entry says ``*.``, requiring at
      least one subdomain label) and does NOT match
      ``example.com.evil.com`` (suffix-with-dot defense — the
      candidate host MUST end with ``.example.com`` AND the dot is
      mandatory).
    """
    if origin is None:
        return False
    if not isinstance(origin, str):
        # Shape rejection — not a typed-error path because the
        # registry's role is to close the connection, not to crash.
        # Returning False is the safe disposition here; the registry
        # logs a fingerprint of the type for triage.
        return False
    if not origin:
        return False
    for entry in allowed_origins:
        if entry == "*":
            return True
        if entry == origin:
            return True
        if "*" in entry:
            # Already validated as "<scheme>://*.<host>" at registration.
            scheme_sep = "://"
            sep_idx = entry.index(scheme_sep)
            entry_scheme = entry[:sep_idx]
            entry_suffix = entry[sep_idx + len(scheme_sep) + 1 :]  # ".host"
            # Origin MUST share scheme and end with .<host> and have
            # at least one character before the dot (no bare host
            # match).
            origin_lower_scheme = origin.split("://", 1)
            if len(origin_lower_scheme) != 2:
                continue
            o_scheme, o_rest = origin_lower_scheme
            if o_scheme.lower() != entry_scheme.lower():
                continue
            # Strip optional port and path: origin host is the part
            # before the first "/" or ":" after the scheme.
            o_host = o_rest.split("/", 1)[0].split(":", 1)[0]
            if not o_host:
                continue
            if o_host == entry_suffix.lstrip("."):
                # Bare host match disallowed: entry "https://*.x.com"
                # MUST NOT match "https://x.com".
                continue
            if o_host.endswith(entry_suffix):
                # Defense against suffix-injection like
                # "x.com.evil.com": ensure the character before the
                # entry suffix exists (the lstrip("."), since
                # entry_suffix already starts with ".") AND that the
                # subdomain label has at least one char.
                prefix_len = len(o_host) - len(entry_suffix)
                if prefix_len >= 1:
                    return True
    return False


def fingerprint_origin(origin: object) -> str:
    """Return an 8-char SHA-256 prefix of ``origin`` for audit logs.

    Per ``rules/observability.md`` Rule 6 (mask helpers) + Rule 8
    (schema-revealing identifiers at WARN MUST be hashed): WARN logs
    on origin rejection MUST NOT echo the raw origin string back to
    log aggregators (Datadog/Splunk/CloudWatch) where attackers can
    correlate log entries with the URLs they attempted.

    Returns ``"00000000"`` sentinel for ``None`` / empty / non-string
    so the caller can still emit a fingerprint field even when the
    upstream is malformed.
    """
    if origin is None:
        return "00000000"
    if not isinstance(origin, str):
        # Hash the type name + repr for some signal without leaking
        # the underlying object.
        material = f"<non-string:{type(origin).__name__}>".encode("utf-8")
    else:
        material = origin.encode("utf-8")
    if not material:
        return "00000000"
    return hashlib.sha256(material).hexdigest()[:8]

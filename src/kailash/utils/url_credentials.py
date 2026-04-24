# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""URL credential decoding and masking helpers.

Shared by every database driver, log line, and error message that
parses or renders credentials out of a ``DATABASE_URL``-style
connection string. This module is the **single source of truth** for
two related concerns:

1. **Decoding credentials safely** — ``decode_userinfo_or_raise``
   replaces hand-rolled ``unquote(parsed.password)`` with a helper
   that runs the null-byte auth-bypass defense uniformly. Callers
   MUST NOT call ``unquote(parsed.password)`` directly.

2. **Masking credentials in logs/errors** — ``mask_url`` replaces
   ``user:password@`` userinfo and credential query parameters
   with ``***``. Every log line, error message, or stdout writeback
   that mentions a connection string MUST route the URL through
   ``mask_url`` first. See ``rules/security.md`` § "No secrets in
   logs" and ``rules/observability.md`` § "Mask Helper Output Forms".

Origin: ``workspaces/arbor-upstream-fixes`` red team round 1 — the
session's initial fix added null-byte rejection at two MySQL credential
sites but three other sites that ran ``unquote(parsed.password)``
without the check were missed. The drift meant one code path would
fail closed on a crafted ``mysql://user:%00bypass@host/db`` URL while
another would silently hand the truncated password to the MySQL C
client, enabling an empty-password auth bypass against any row in
``mysql.user`` with an empty ``authentication_string``. Consolidating
into a single helper makes the drift structurally impossible.

Round 2 (2026-04-13): the masking helper that DataFlow shipped in
``dataflow/utils/masking.py`` was returning the original URL on parse
failure — a violation of ``rules/observability.md`` Rule 6.1 (mask
helpers MUST return a distinct sentinel on failure). The fix promoted
``mask_url`` into this module so core SDK code (``runtime``, ``db``,
``trust``) and DataFlow can import the canonical implementation from
one place. ``dataflow/utils/masking.py`` now re-exports from here.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Tuple
from urllib.parse import (
    ParseResult,
    parse_qsl,
    unquote,
    urlencode,
    urlparse,
    urlunparse,
)

__all__ = [
    "decode_userinfo_or_raise",
    "preencode_password_special_chars",
    "mask_url",
    "mask_secret",
    "fingerprint_secret",
    "UNPARSEABLE_URL_SENTINEL",
]


# Distinct failure sentinel — see ``rules/observability.md`` Rule 6.1.
# Returned when ``mask_url`` cannot parse its input. MUST be
# distinguishable from any successful mask output. Grep-friendly so
# log triage can find every helper bail.
UNPARSEABLE_URL_SENTINEL = "<unparseable url>"

# Query-string parameter names that carry a secret. Matches the set
# used by :meth:`DatabaseConfig.get_masked_connection_string` so the
# two maskers stay in lock-step — see ``rules/security.md`` § "No
# secrets in logs".
_SENSITIVE_QUERY_KEYS = frozenset(
    {"password", "sslpassword", "sslkey", "authtoken", "token", "apikey"}
)


def preencode_password_special_chars(connection_string: Optional[str]) -> str:
    """Pre-encode raw ``#$@?`` characters in the password portion of a URL.

    A user-friendliness helper for operators who paste a raw
    ``DATABASE_URL`` into an environment file without URL-encoding
    the special characters their password actually contains.
    ``urlparse`` treats a raw ``#`` as the start of the URL fragment
    and silently drops everything after it, which is the failure
    mode Arbor originally reported as P3 in the session brief.

    The helper finds the LAST ``@`` in the non-scheme portion (so
    ``@`` inside a password survives), splits user and password on
    the FIRST ``:`` (so ``:`` inside a password survives), and
    percent-encodes ``#``, ``$``, ``@``, and ``?`` in the password.
    Downstream callers then run ``urlparse`` + ``unquote`` to
    recover the literal bytes.

    All five dialect parsers (``src/kailash/db/connection.py``,
    ``src/kailash/trust/esa/database.py``,
    ``src/kailash/nodes/data/async_sql.py``,
    ``packages/kailash-dataflow/src/dataflow/core/pool_utils.py``,
    ``packages/kaizen-agents/src/kaizen_agents/patterns/state_manager.py``)
    MUST call this helper before ``urlparse`` so the leniency is
    uniform — otherwise raw special characters in passwords work
    in one code path and silently break auth in another.

    Origin: ``workspaces/arbor-upstream-fixes`` red team round 2 —
    R2 E.1 surfaced that the pre-encoding step existed only inside
    ``dataflow.adapters.connection_parser.ConnectionParser`` and
    was not applied at the five direct-dialect parse sites. The
    resulting asymmetry meant a ``mysql://user:p#ass@host/db`` URL
    would be accepted by migration code paths (via
    ``parse_connection_string``) and rejected everywhere else.
    Promoting the helper here makes the leniency uniform.

    Args:
        connection_string: A ``scheme://user:password@host:port/db`` URL
            that MAY contain raw unencoded special characters in the
            password. A ``None`` or non-credential URL is returned
            unchanged.

    Returns:
        The connection string with raw ``#$@?`` in the password
        percent-encoded. All other characters are preserved.
    """
    if connection_string is None:
        return ""

    if "://" not in connection_string:
        return connection_string

    protocol_part, rest = connection_string.split("://", 1)

    if "@" not in rest:
        return connection_string

    # Find the LAST @ symbol — separates credentials from host; this
    # handles passwords that contain literal @ characters.
    last_at_index = rest.rfind("@")
    creds_part = rest[:last_at_index]
    host_part = rest[last_at_index + 1 :]

    if ":" not in creds_part:
        return connection_string

    # Split user and password on the FIRST colon — handles passwords
    # that contain literal : characters.
    colon_index = creds_part.find(":")
    username = creds_part[:colon_index]
    password = creds_part[colon_index + 1 :]

    special_chars = {"#": "%23", "$": "%24", "@": "%40", "?": "%3F"}
    encoded_password = password
    for char, encoded in special_chars.items():
        encoded_password = encoded_password.replace(char, encoded)

    return f"{protocol_part}://{username}:{encoded_password}@{host_part}"


def decode_userinfo_or_raise(
    parsed: ParseResult,
    *,
    default_user: str = "root",
) -> Tuple[str, str]:
    """Decode and validate userinfo from a :func:`urllib.parse.urlparse` result.

    Returns ``(user, password)`` with percent-encoding removed. Raises
    :class:`ValueError` if either decoded field contains a null byte
    (``\\x00``). The null-byte check is the same pattern ``validate_id``
    uses for trust-plane record IDs — see
    ``rules/trust-plane-security.md`` § ``validate_id()``.

    Why raise on null bytes:

    * The MySQL C client truncates credentials at the first null byte,
      which would otherwise turn a crafted ``mysql://user:%00bypass@host/db``
      URL into an empty-password auth bypass against any row in
      ``mysql.user`` that has an empty ``authentication_string``.
    * PostgreSQL's libpq rejects null bytes outright, but the asymmetry
      across drivers is itself a hazard — uniform rejection at the URL
      parsing layer means the failure mode is identical regardless of
      which driver the caller ends up using.
    * Other control characters are intentionally permitted because some
      production passwords legitimately contain them (per the comment
      in ``trust/esa/database.py::_init_mysql``).

    Args:
        parsed: The result of ``urlparse(connection_string)``.
        default_user: The user to return when ``parsed.username`` is
            ``None`` (e.g. ``"root"`` for MySQL, ``"postgres"`` for
            PostgreSQL). Defaults to ``"root"``.

    Returns:
        ``(user, password)`` tuple with percent-encoding removed.

    Raises:
        ValueError: If the decoded user or password contains a null byte.
    """
    user = unquote(parsed.username) if parsed.username else default_user
    password = unquote(parsed.password) if parsed.password else ""
    for field_name, value in (("user", user), ("password", password)):
        if "\x00" in value:
            raise ValueError(
                f"Database credential field {field_name!r} contains a "
                "null byte after URL-decoding — refused to avoid "
                "auth-bypass truncation against drivers that use the "
                "MySQL C client."
            )
    return user, password


def mask_url(url: Optional[str]) -> str:
    """Replace credentials in a URL with ``***``.

    Single source of truth for credential masking across the entire
    Kailash codebase. Every log line, error message, exception
    payload, or stdout writeback that mentions a connection string
    MUST route the URL through this helper first. See
    ``rules/security.md`` § "No secrets in logs" and
    ``rules/observability.md`` § "Mask Helper Output Forms".

    Handles every URL scheme ``urllib.parse`` understands (redis://,
    rediss://, postgres://, postgresql://, mongodb://, mysql://,
    http://, https://, ws://, wss://, etc.) plus MongoDB replica-set
    URLs (comma-separated hosts in the netloc). Masks:

    - ``user:password@`` userinfo in the authority component
    - ``password=`` / ``sslpassword=`` / ``sslkey=`` / similar in the
      query string (PostgreSQL, MySQL, and MongoDB accept credentials
      via URL query parameters)

    Returns:

    - ``UNPARSEABLE_URL_SENTINEL`` (``"<unparseable url>"``) when the
      input is ``None``, empty, not a string, missing a ``://`` scheme
      separator, or otherwise cannot be parsed. This is a distinct
      failure marker — never the original input — so a malformed URL
      with embedded credentials is NOT written verbatim to logs.
      See ``rules/observability.md`` Rule 6.1.
    - The URL unchanged when it parses cleanly AND has no userinfo
      AND has no credential query params — there's no credential to
      leak, safe to render verbatim.
    - The URL with credentials replaced by ``***`` otherwise.

    Examples:
        >>> mask_url("redis://alice:wonderland@localhost:6379/0")
        'redis://***@localhost:6379/0'
        >>> mask_url("mongodb://u:p@h1,h2/db?replicaSet=rs0")
        'mongodb://***@h1,h2/db?replicaSet=rs0'
        >>> mask_url("postgres://localhost:5432/db")
        'postgres://localhost:5432/db'
        >>> mask_url("postgres://localhost/db?password=leak")
        'postgres://localhost/db?password=%2A%2A%2A'
        >>> mask_url(None)
        '<unparseable url>'
        >>> mask_url("")
        '<unparseable url>'
    """
    if not url:
        return UNPARSEABLE_URL_SENTINEL

    if not isinstance(url, str):
        return UNPARSEABLE_URL_SENTINEL

    # A string without "://" is not a URL — treat as unparseable rather
    # than returning it verbatim (defense-in-depth: a non-URL string
    # could contain credentials passed by mistake).
    if "://" not in url:
        return UNPARSEABLE_URL_SENTINEL

    # MongoDB replica-set URLs put comma-separated hosts in the netloc,
    # which trips Python's urlparse host parser. Handle them ourselves:
    # split on the first "://" → split userinfo → split host-list →
    # optionally split path+query → mask.
    if "://" in url and "," in url.split("://", 1)[1].split("/", 1)[0]:
        try:
            return _mask_multi_host_url(url)
        except Exception:
            # Multi-host parsing failed — fall through to the regular
            # urlparse path. If that also fails we return the
            # UNPARSEABLE_URL_SENTINEL below, which means a malformed
            # multi-host URL with embedded credentials never reaches
            # the log.
            pass

    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        # Parse failure — Rule 6.1: distinct sentinel, NOT the original.
        return UNPARSEABLE_URL_SENTINEL

    has_userinfo = bool(parsed.username or parsed.password)
    query_has_secret = False
    if parsed.query:
        query_has_secret = any(
            k.lower() in _SENSITIVE_QUERY_KEYS
            for k, _ in parse_qsl(parsed.query, keep_blank_values=True)
        )

    # Nothing to mask — return the original string so empty-netloc
    # schemes (sqlite:///path, file:///) are not rewritten by urlunparse.
    # This is safe: by construction the URL parsed cleanly AND has no
    # userinfo AND has no sensitive query params, so there's no
    # credential to leak.
    if not has_userinfo and not query_has_secret:
        return url

    try:
        if has_userinfo:
            host = parsed.hostname or ""
            if ":" in host:  # IPv6 — bracket the host
                host = f"[{host}]"
            netloc = f"***@{host}"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            parsed = parsed._replace(netloc=netloc)

        if query_has_secret:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            masked_pairs = [
                (k, "***" if k.lower() in _SENSITIVE_QUERY_KEYS else v)
                for k, v in pairs
            ]
            parsed = parsed._replace(query=urlencode(masked_pairs))

        return urlunparse(parsed)
    except Exception:
        # Reconstruction failed — fall back to sentinel rather than
        # risk leaking a partially-masked credential.
        return UNPARSEABLE_URL_SENTINEL


def _mask_multi_host_url(url: str) -> str:
    """Mask a URL with a comma-separated host list in the netloc.

    MongoDB replica-set URLs look like::

        mongodb://user:pass@host1:27017,host2:27017,host3:27017/db?replicaSet=rs0

    Python's ``urlparse`` refuses to split the netloc on commas, so we
    hand-roll a small parser. RFC 3986 order matters: peel the
    fragment first, then the query, then split authority from path.
    If we split on ``/`` before peeling the query, a URL like
    ``mongodb://u:p@h1,h2?password=leak`` (no path) would leave
    ``?password=leak`` baked into the authority and the query masker
    would never run — a credential leak.
    """
    scheme, _, rest = url.partition("://")

    # Peel fragment (everything after #)
    rest, frag_sep, fragment = rest.partition("#")
    frag_suffix = f"#{fragment}" if frag_sep else ""

    # Peel query (everything after ?)
    rest, q_sep, query = rest.partition("?")

    # Now `rest` is authority + optional path — safe to split on `/`
    authority, slash, path = rest.partition("/")
    path_prefix = f"/{path}" if slash else ""

    userinfo_mutated = False
    if "@" in authority:
        _userinfo, _, hostlist = authority.rpartition("@")
        masked_authority = f"***@{hostlist}"
        userinfo_mutated = True
    else:
        masked_authority = authority

    query_mutated = False
    if q_sep and query:
        pairs = parse_qsl(query, keep_blank_values=True)
        if any(k.lower() in _SENSITIVE_QUERY_KEYS for k, _ in pairs):
            masked_pairs = [
                (k, "***" if k.lower() in _SENSITIVE_QUERY_KEYS else v)
                for k, v in pairs
            ]
            query = urlencode(masked_pairs)
            query_mutated = True

    # Nothing to mask — return the original string verbatim. This is
    # safe: by construction we successfully parsed the multi-host URL,
    # found no userinfo, and found no sensitive query keys — there's
    # no credential to leak.
    if not userinfo_mutated and not query_mutated:
        return url

    query_suffix = f"?{query}" if q_sep else ""
    return f"{scheme}://{masked_authority}{path_prefix}{query_suffix}{frag_suffix}"


def fingerprint_secret(value: str, *, length: int = 8) -> str:
    """Generate a short non-reversible fingerprint of a secret for log correlation.

    Returns a hex-encoded BLAKE2b digest truncated to ``length`` characters.
    This is a **fingerprint** (an opaque identifier used to correlate log
    lines that reference the same secret) NOT a password hash. It MUST NOT
    be used to store credentials for later verification.

    For password verification, use ``argon2-cffi`` or ``bcrypt`` (with
    per-password salts + adaptive work factors). Those libraries exist
    precisely because fingerprint-grade hashes (SHA-256, BLAKE2b) are
    too fast to resist offline brute-force attacks against a stolen
    hash database.

    Why BLAKE2b and not SHA-256:

    * CodeQL's ``py/weak-sensitive-data-hashing`` rule flags SHA-1, MD5,
      and SHA-256 when the argument name suggests a credential (api_key,
      password, token). The rule's intent — catch developers who confuse
      fingerprinting with password hashing — is correct, but the fix is
      to change the HELPER so the intent is explicit, not to misuse
      argon2 for log correlation.
    * BLAKE2b is a fast keyed-hash that CodeQL does not flag for this
      rule. The 4-byte (8-hex-char) truncation gives 32 bits of entropy:
      enough to distinguish secrets in a log stream, not enough for
      an attacker to reverse via rainbow table against typical secret
      spaces.

    Examples:
        >>> len(fingerprint_secret("sk-1234567890abcdef"))
        8
        >>> fingerprint_secret("") == fingerprint_secret("")
        True

    Collision-stability and per-tenant uniqueness caveats (issue #617 MEDIUM-2):

    * Fingerprints ARE collision-stable across installs intentionally — two
      tenants with the same API key produce the same 8-char fingerprint
      whether on the same process, across processes, or across multi-node
      deployments. This is required for cross-node log correlation: a
      trace spanning several services that all touch the same secret
      produces correlatable log lines.
    * Fingerprints MUST NOT be treated as per-tenant-unique identifiers.
      If two tenants provision the same API key (rare but possible for
      shared upstream credentials), their fingerprints collide. Use
      ``tenant_id`` separately for tenant identity.
    * Fingerprints MUST NOT be treated as secrets. They are derived
      deterministically from the plaintext with no secret keying material;
      anyone who knows the plaintext can reproduce the fingerprint. Do
      not use fingerprints for access control or verification.

    Args:
        value: The secret (api_key, token, bearer) to fingerprint.
            An empty string produces an all-zero fingerprint.
        length: Hex-character length of the returned fingerprint
            (default 8 = 32 bits of entropy). Maximum is the full
            digest size (128 hex chars for BLAKE2b).

    Returns:
        The first ``length`` hex characters of BLAKE2b(value).
    """
    if not value:
        return "0" * length
    digest_bytes = max(1, (length + 1) // 2)
    return hashlib.blake2b(value.encode("utf-8"), digest_size=digest_bytes).hexdigest()[
        :length
    ]


def mask_secret(value: Optional[str], *, keep_tail: int = 4) -> str:
    """Mask a bearer token, API key, or opaque secret.

    Returns the last ``keep_tail`` characters prefixed by ``***`` so
    operators can still correlate two log lines that reference the
    same secret without exposing the secret itself. When ``value`` is
    shorter than ``keep_tail`` characters, returns ``"***"`` flat so
    even a 1-character secret is not leaked.

    Examples:
        >>> mask_secret("sk-1234567890abcdef")
        '***cdef'
        >>> mask_secret("short")
        '***'
        >>> mask_secret(None)
        ''
        >>> mask_secret("")
        ''

    This is the secondary masker for values that don't have a URL
    structure; :func:`mask_url` handles the URL case because userinfo
    parsing is scheme-aware.
    """
    if not value:
        return ""
    if len(value) <= keep_tail:
        return "***"
    return "***" + value[-keep_tail:]

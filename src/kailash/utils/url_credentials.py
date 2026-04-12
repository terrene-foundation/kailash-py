# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""URL credential decoding helpers.

Shared by every database driver that parses credentials out of a
``DATABASE_URL``-style connection string. Callers MUST use
``decode_userinfo_or_raise`` instead of calling ``unquote(parsed.password)``
directly so that the null-byte auth-bypass defense runs uniformly
everywhere.

Origin: ``workspaces/arbor-upstream-fixes`` red team round 1 — the
session's initial fix added null-byte rejection at two MySQL credential
sites but three other sites that ran ``unquote(parsed.password)``
without the check were missed. The drift meant one code path would
fail closed on a crafted ``mysql://user:%00bypass@host/db`` URL while
another would silently hand the truncated password to the MySQL C
client, enabling an empty-password auth bypass against any row in
``mysql.user`` with an empty ``authentication_string``. Consolidating
into a single helper makes the drift structurally impossible.
"""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import ParseResult, unquote

__all__ = [
    "decode_userinfo_or_raise",
    "preencode_password_special_chars",
]


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

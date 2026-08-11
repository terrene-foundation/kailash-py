"""Hygiene helpers for values that reach a security/audit log record.

``SecurityEventNode.execute`` renders its record with an unescaped f-string::

    log_message = f"[{severity.value}] {event_type}: {message}"
    if user_id:
        log_message += f" (User: {user_id})"

Every node in this package supplies ``user_id`` from caller-controlled input,
so a value containing a newline writes a SECOND well-formed record: an attacker
can fabricate arbitrary security-log lines and bury the real ones underneath
them (issue #2060).

This was unreachable until #2060 was fixed -- each of these call sites awaited a
method the sink does not define and raised ``AttributeError`` before reaching
the logger. Resolving those calls is what makes the injection live, so the
sanitizer lands with it.

One helper, used at every sink call site in this package, rather than an inline
``replace`` per site: five hand-rolled copies is how the sites drift
(``rules/security.md`` § Multi-Site Kwarg Plumbing).

The durable fix belongs one layer down, inside ``SecurityEventNode.execute``
and ``AuditLogNode.execute``, so that EVERY caller in the SDK is covered rather
than only this package's. That is outside this change's file scope; the helper
here closes the exposure this change creates.
"""

from typing import Any

__all__ = ["log_safe", "redact_mapping"]

# Keys whose values are credential material or bulk personal data and must not
# be copied into a log record. Matched case-insensitively as substrings, so
# "access_token", "refresh_token" and "totp_secret" are all caught.
_SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "backup_code",
    "recovery_code",
    "private_key",
    "api_key",
    "qr_code",
    "provisioning_uri",
    "assertion",
    "authorization",
    "cookie",
    "session_id",
)


def log_safe(value: Any, limit: int = 256) -> str:
    """Flatten a value to one bounded, single-line token for a log record.

    Non-printable characters -- newline, carriage return, and the terminal
    escape sequences that can rewrite a console operator's screen -- are
    replaced with a space, and the result is truncated. One call can therefore
    only ever produce one line.
    """
    text = "" if value is None else str(value)
    flattened = "".join(ch if ch.isprintable() else " " for ch in text)
    return flattened[:limit]


def redact_mapping(data: Any, _depth: int = 0) -> Any:
    """Recursively replace credential-bearing values with a redaction marker.

    Used for the free-form attribute bags the SSO and directory nodes attach to
    audit records: a provisioning record carries whatever the IdP returned,
    which routinely includes tokens and, for a directory sync, the full mapped
    LDAP/AD entry. The record keeps its shape -- the key stays, so an auditor
    can still see WHICH fields were present -- while the value is withheld.

    Depth is bounded so a self-referential or pathologically nested attribute
    bag cannot exhaust the stack inside a logging call.
    """
    if _depth >= 6:
        return "[REDACTED_DEPTH]"
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_mapping(value, _depth + 1)
        return redacted
    if isinstance(data, (list, tuple)):
        return [redact_mapping(item, _depth + 1) for item in data]
    return data

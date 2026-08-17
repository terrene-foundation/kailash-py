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

The durable fix DID land one layer down, inside ``SecurityEventNode.execute``
and ``AuditLogNode.execute``, so every caller in the SDK is covered rather than
only this package's (issue #2167). ``redact_mapping`` moved with it, to
``kailash.utils.secure_logging`` beside ``sanitize_log_value``, because a node
outside this package must not reach into a private module of it. Import it from
there; this module no longer defines it.
"""

from typing import Any

from kailash.utils.secure_logging import sanitize_log_value

__all__ = ["log_safe"]


def log_safe(value: Any, limit: int = 256) -> str:
    """Flatten a value to one bounded, single-line token for a log record.

    A THIN ALIAS for :func:`kailash.utils.secure_logging.sanitize_log_value`,
    which is the public, documented value-sanitizer for the whole SDK
    (issue #2040). It is kept because five call sites in this package import
    it by this name, but it holds NO implementation of its own: two copies of
    a sanitizer is exactly the drift this module's header warns about, and the
    copy that is not the canonical one is the one that stops getting fixed
    (``rules/security.md`` § Credential Decode Helpers -- one shared helper,
    never per-package copies).

    ``None`` renders as the empty string here rather than ``"None"``, which is
    the one behaviour this wrapper adds: these call sites pass optional
    identifier fields, and a record reading ``(User: None)`` is noise.
    """
    if value is None:
        return ""
    return sanitize_log_value(value, limit)

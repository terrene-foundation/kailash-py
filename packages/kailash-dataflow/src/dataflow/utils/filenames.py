"""Filesystem-safe filename construction for workflow-derived outputs.

DataFlow CLI commands that derive a filesystem path from
``workflow.name`` (or any other dynamic, user-influenced string)
MUST use :func:`safe_workflow_filename` to validate the input
against a strict allowlist before interpolating it into a
:class:`pathlib.Path`. Direct interpolation
(``f"{workflow.name}.md"``) is BLOCKED — unvalidated names can be
path-traversal vectors, can contain filesystem-unsafe characters,
or can be a Mock-object repr leaked from a test fixture.

This is the filename-surface sibling of
``rules/dataflow-identifier-safety.md`` MUST Rule 1
(``dialect.quote_identifier()`` for SQL) and
``rules/security.md`` § "Input Validation" — same "validate at the
trust boundary" principle, applied to filesystem identifiers.

Origin: 2026-05-06 — ``Mock(name="X")`` does NOT set ``Mock.name``;
accessing ``.name`` returns a child Mock whose ``__str__`` is
``<Mock name='X.name' id='...'>``. ``generate.py:156`` interpolated
this into a real filename, leaking 108 orphan files into ``docs/``
across the repo before this helper landed.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Final

logger = logging.getLogger(__name__)

# Filesystem-safe allowlist for workflow names:
#   - First char: alphanumeric or underscore (no leading dot, no leading hyphen)
#   - Remaining chars: alphanumeric, underscore, hyphen, dot
#   - Length 1..128 (conservative across POSIX/NTFS/HFS+; FS limit is 255 but
#     workflow names that long are almost certainly bugs)
_WORKFLOW_NAME_RE: Final = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")

# Path-traversal substring that the regex above CAN technically allow
# (e.g. "x..y" matches the regex but contains "..", which on some
# filesystems produces ambiguous traversal behavior).
_PATH_TRAVERSAL_SUBSTR: Final = ".."

# Extension allowlist: short alphanumeric only (md, json, txt, html, csv, ...)
_EXT_RE: Final = re.compile(r"^[A-Za-z0-9]{1,16}$")


class WorkflowNameError(ValueError):
    """Raised when a workflow name is unsafe to interpolate into a filename.

    The exception message NEVER echoes the raw offending name (that
    would be a log-poisoning / stored-XSS vector for user-influenced
    inputs); instead it carries a short ``sha256[:8]`` fingerprint
    of the input for forensic correlation across logs.

    Subclass of :class:`ValueError` so callers that catch
    ``ValueError`` continue to work.
    """


def _fingerprint(raw: object) -> str:
    """Return ``sha256[:8]`` of ``str(raw)`` (best-effort, never raises)."""
    try:
        encoded = str(raw).encode("utf-8", errors="replace")
    except Exception:  # pragma: no cover — defensive; str() can rarely fail
        return "________"
    return hashlib.sha256(encoded).hexdigest()[:8]


def safe_workflow_filename(name: object, ext: str) -> str:
    """Return a filesystem-safe ``"<name>.<ext>"`` filename or raise.

    Parameters
    ----------
    name
        The workflow name. MUST be a string matching
        ``^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`` AND MUST NOT contain
        the substring ``..``.
    ext
        File extension WITHOUT the leading dot (``"md"``, not
        ``".md"``). MUST match ``^[A-Za-z0-9]{1,16}$``.

    Returns
    -------
    str
        A filename of the form ``"<name>.<ext>"`` safe to interpolate
        into ``Path()`` joins.

    Raises
    ------
    WorkflowNameError
        When ``name`` is not a string, is empty, exceeds 128 chars,
        contains characters outside the allowlist, contains the
        path-traversal substring ``..``, or when ``ext`` fails its
        own allowlist. Logs at WARN with a hashed fingerprint
        (per ``rules/observability.md`` Rule 8 — never log the raw
        name, which may be a schema identifier).
    """
    # Validate ext first (fixed-form internal parameter, fast reject).
    if not isinstance(ext, str) or not _EXT_RE.match(ext):
        raise WorkflowNameError(
            "invalid extension: must be 1-16 alphanumeric chars "
            f"(fingerprint={_fingerprint(ext)})"
        )

    fp = _fingerprint(name)

    if not isinstance(name, str):
        logger.warning(
            "filename.invalid_workflow_name",
            extra={
                "reason": "not_a_string",
                "fingerprint": fp,
                "type": type(name).__name__,
            },
        )
        raise WorkflowNameError(
            f"workflow name must be a string (got {type(name).__name__}, "
            f"fingerprint={fp}). This often indicates a Mock object whose "
            "`.name` attribute returned a child Mock — use "
            "`mock.name = 'X'` (post-construction) instead of "
            "`Mock(name='X')`, which sets the Mock's repr-name, NOT `.name`."
        )

    if _PATH_TRAVERSAL_SUBSTR in name:
        logger.warning(
            "filename.invalid_workflow_name",
            extra={"reason": "path_traversal", "fingerprint": fp},
        )
        raise WorkflowNameError(
            "workflow name contains path-traversal substring '..' "
            f"(fingerprint={fp})"
        )

    if not _WORKFLOW_NAME_RE.match(name):
        logger.warning(
            "filename.invalid_workflow_name",
            extra={
                "reason": "regex_mismatch",
                "fingerprint": fp,
                "length": len(name),
            },
        )
        raise WorkflowNameError(
            "workflow name failed allowlist validation: must match "
            r"`^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$` "
            f"(fingerprint={fp}, length={len(name)})"
        )

    return f"{name}.{ext}"


__all__ = ["WorkflowNameError", "safe_workflow_filename"]

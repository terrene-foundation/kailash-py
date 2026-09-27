"""
Deliberate on-disk locations for the audit trail (#2110 defect 2).

The audit trail is a compliance artifact whose value is that it is COMPLETE.
A location relative to the process working directory defeats that twice over:
it drops a ``.kaizen/`` directory into whatever tree the operator happened to
launch from, and -- the part that actually matters -- running the same agent
from two directories produces two disjoint trails, NEITHER of which is the
record an auditor asked for.

So the default is anchored to the XDG *state* directory. State is the correct
XDG category for this data: the spec reserves it for information that should
persist between restarts but is neither cached (recoverable) nor
configuration (user-authored) -- an append-only audit log is exactly that.

This module is deliberately tiny and dependency-free so it can be imported
from config layers that must not pull in the observability stack.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: Subdirectory under the XDG state root that owns every Kaizen state file.
STATE_SUBDIR = "kaizen"

#: Filename of the active audit segment. Rotated segments are this name with
#: a ``.1`` / ``.2`` / ... suffix (see ``FileAuditStorage``).
AUDIT_FILENAME = "audit.jsonl"


def state_home() -> Path:
    """
    Resolve the XDG state root.

    ``$XDG_STATE_HOME`` when set to an ABSOLUTE path, else
    ``~/.local/state`` (the fallback the XDG Base Directory spec names).

    A RELATIVE ``$XDG_STATE_HOME`` is ignored rather than honoured, which is
    what the spec requires -- and honouring it would silently reintroduce the
    exact CWD-relative defect this module exists to remove. The override is
    announced, because an ignored environment variable that changes where a
    compliance artifact lands is not something to drop quietly.
    """
    raw = os.environ.get("XDG_STATE_HOME")
    if raw:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        logger.warning(
            "XDG_STATE_HOME=%r is relative and is being IGNORED (the XDG "
            "Base Directory spec requires absolute paths). Falling back to "
            "~/.local/state. Set an absolute path to control where the audit "
            "trail is written.",
            raw,
        )
    return Path.home() / ".local" / "state"


def default_audit_path() -> Path:
    """
    Absolute default location of the active audit segment.

    ``$XDG_STATE_HOME/kaizen/audit.jsonl``, else
    ``~/.local/state/kaizen/audit.jsonl``.

    The path is NOT created here -- ``FileAuditStorage`` owns creation and the
    0o600/0o700 mode pinning that goes with it. This function only decides
    WHERE, so that a caller wanting to display or override the default does
    not have to create anything as a side effect of asking.

    Returns:
        Absolute path to the active audit JSONL segment.
    """
    return state_home() / STATE_SUBDIR / AUDIT_FILENAME


__all__ = [
    "AUDIT_FILENAME",
    "STATE_SUBDIR",
    "default_audit_path",
    "state_home",
]

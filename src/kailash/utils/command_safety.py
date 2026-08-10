# Copyright 2026 Terrene Foundation
"""Disclosure-safe references for untrusted spawn commands.

A local-server spawn command is untrusted input (agent output, a registry
entry, a discovery response) and routinely carries a credential as a CLI
flag::

    npx -y @vendor/mcp-server --token=<secret>

Every rejection path for such a command wants to say *which* command was
rejected, and every naive way of saying so — ``f"{command!r}"`` in the
message, ``data={"command": command}`` on the exception, ``shlex.join`` into
a debug log — publishes the credential.

Why a reference rather than a scrubber
--------------------------------------
The obvious remedy is to scrub the command at each sink with the existing
credential masker (:func:`kailash.utils.url_credentials.mask_error_text`).
That helper redacts URL userinfo and credential query parameters; it does
NOT redact a CLI-flag credential, which is the shape this input actually
takes. Routing a spawn command through it produces a change that looks like
a fix and leaks exactly as before.

Scrubbing is also the wrong shape structurally: it has to be applied at
every sink, so it is only ever as complete as the last enumeration of sinks,
and a sink added later inherits nothing. A secret that is never stored
cannot leak from a sink nobody remembered.

So the contract here is: convert the command ONCE, at the point where it
would otherwise be captured, into a reference that is safe to put anywhere —
a log record, an exception attribute, a JSON-RPC error payload.

The reference
-------------
``<launcher>#<fingerprint>``, e.g. ``npx#3f2a91cc``.

* **launcher** — the basename of the first whitespace-delimited token, i.e.
  the executable. Arguments (where credentials live) are never included.
  The label is a debugging *hint*: if the token does not look like a plain
  program name it is replaced with :data:`REDACTED_LABEL`, so the failure
  direction is disclosure-safe.
* **fingerprint** — a truncated BLAKE2b digest of the WHOLE command via
  :func:`~kailash.utils.url_credentials.fingerprint_secret`. It is stable
  across calls and processes, so two log lines about the same command
  correlate, and distinct commands do not collapse together.

A fingerprint is not a secret and not a password hash; see that function's
docstring for the collision-stability and reversibility caveats.
"""

from __future__ import annotations

import os
import re

from kailash.utils.url_credentials import fingerprint_secret

__all__ = [
    "safe_command_ref",
    "EMPTY_REF",
    "NON_STRING_REF",
    "REDACTED_LABEL",
]

# Distinct, grep-able sentinels — see ``rules/observability.md`` Rule 6.1.
# Each names a different input defect so log triage can tell "the caller
# passed nothing" from "the caller passed the wrong type" from "the command
# was present but its first token did not look like a program name".
EMPTY_REF = "<empty>"
NON_STRING_REF = "<non-string>"
REDACTED_LABEL = "<redacted>"

# What an executable basename looks like: starts alphanumeric (or ``_``) and
# continues with the characters real launcher names use. Deliberately
# EXCLUDES ``=``, ``:``, ``@``, quotes and whitespace — the characters that
# appear when the "first token" is actually a flag (``--token=...``), a URL
# userinfo pair (``user:pw@host``), or a fused flag/value.
#
# The 24-character cap is a conservative upper bound on real launcher names
# (``mcp-server-filesystem`` is 21); a credential pasted where the executable
# belongs is typically longer and higher-entropy. The cap is defense in
# depth, not the security boundary: the boundary is that only the FIRST
# token is ever considered, and a credential is never the executable.
_SAFE_LAUNCHER_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+-]{0,23}")


def _launcher_label(command: str) -> str:
    """Best-effort, fail-closed label for the executable in ``command``."""
    tokens = command.split()
    if not tokens:
        return REDACTED_LABEL
    basename = os.path.basename(tokens[0].replace("\\", "/"))
    if _SAFE_LAUNCHER_NAME.fullmatch(basename):
        return basename
    return REDACTED_LABEL


def safe_command_ref(command: object) -> str:
    """Return a disclosure-safe reference to an untrusted spawn ``command``.

    Use this anywhere a spawn command would otherwise be rendered, stored, or
    serialized — log messages and ``extra=`` blocks, exception messages,
    structured error ``data`` payloads, returned status dicts.

    Args:
        command: The spawn command. Any object is accepted, because callers
            validate untrusted input whose type is not yet established; a
            non-string yields :data:`NON_STRING_REF` rather than raising.

    Returns:
        ``"<launcher>#<fingerprint>"`` for a non-empty command string,
        :data:`EMPTY_REF` for an empty string, or :data:`NON_STRING_REF` for
        anything that is not a string. The return value never contains any
        substring of the command's arguments.

    Examples:
        >>> safe_command_ref("npx -y @vendor/server --token=s3cret").startswith("npx#")
        True
        >>> safe_command_ref("/usr/local/bin/python3").startswith("python3#")
        True
        >>> safe_command_ref("--token=s3cret").startswith("<redacted>#")
        True
        >>> safe_command_ref("")
        '<empty>'
        >>> safe_command_ref(None)
        '<non-string>'
    """
    if not isinstance(command, str):
        return NON_STRING_REF
    if not command:
        return EMPTY_REF
    return f"{_launcher_label(command)}#{fingerprint_secret(command)}"

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared payload-logging helpers for hooks (#2070).

ONE implementation, because there were two. `LoggingHook`
(`builtin/logging_hook.py`) and `SecureLoggingHook` (`security/redaction.py`)
carried near-verbatim copies of the same log body, and the copies had already
diverged in exactly the way duplication predicts: the fix for one would have
left the other publishing payloads under a class name promising the opposite.

The contract both share:

- At the hook's configured level, emit STRUCTURE — key names and counts. Key
  names come from the signature / event schema rather than from user input, so
  they carry no payload content.
- Emit VALUES only behind two independent gates: a deliberate opt-in AND the
  logger actually at DEBUG. Either gate alone is routinely satisfied by
  accident — turning DEBUG on globally is routine during incident response.
- Scrub what does get emitted. Scrubbing claims credential SHAPES, not
  arbitrary prose, which is why the opt-in gate is the load-bearing protection
  and the scrub is defence in depth rather than the other way round.
"""

from __future__ import annotations

import logging
from typing import Any

#: Cap on a rendered payload before it reaches the DEBUG sink. Applied BEFORE
#: scrubbing: `scrub_credentials` runs ~25 regex passes, each building a fresh
#: string, and it was written for error text — whereas a hook payload can carry
#: a whole retrieved document. Capping first bounds both scrub cost and log
#: volume.
MAX_PAYLOAD_CHARS = 2000


def summarize_payload(payload: Any) -> dict[str, Any]:
    """Describe a payload's SHAPE without reproducing any of its values."""
    if isinstance(payload, dict):
        return {"count": len(payload), "keys": sorted(str(k) for k in payload)}
    return {"count": 0 if payload is None else 1, "keys": []}


def render_scrubbed_payload(payload: Any) -> str:
    """Render a payload for a DEBUG sink: truncated first, then scrubbed.

    Callers are responsible for the two gates (opt-in + DEBUG); this function
    only formats. Imported lazily so that merely importing a hook module does
    not pull in the credential-scrub regex table.
    """
    from kaizen.utils.credential_scrub import scrub_credentials

    rendered = repr(payload)
    if len(rendered) > MAX_PAYLOAD_CHARS:
        rendered = f"{rendered[:MAX_PAYLOAD_CHARS]}...[truncated {len(rendered)} chars]"
    return scrub_credentials(rendered)


def should_log_full_payload(enabled: bool, logger: logging.Logger) -> bool:
    """Both gates, in one place, so neither hook can implement only one."""
    return bool(enabled) and logger.isEnabledFor(logging.DEBUG)

"""Log-hygiene helpers for the agent execution path (#2030).

Agent inputs and results routinely carry user prompts, retrieved documents,
PII and — for agents that take credentials as parameters — secrets. NOTHING
here ever renders a VALUE into a log record at INFO or above. The structured
summary (key names + counts) is what makes a trace useful; the values are what
make it a disclosure.

Extracted from ``base_agent.py`` rather than inlined there: that module carries
a hard line-count guard (``tests/unit/core/test_base_agent_slimming.py``)
protecting it against re-inlined helper code, and these helpers are generic log
hygiene with no dependency on ``BaseAgent`` state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["summarize_payload", "safe_log_extra", "log_full_payload"]


def summarize_payload(payload: Any) -> Dict[str, Any]:
    """Value-FREE description of an agent I/O dict: key names and a count.

    Key names are schema, not data — they are what an operator needs in order
    to correlate a run, and they are safe. Values never appear.
    """
    if isinstance(payload, dict):
        return {"keys": sorted(str(key) for key in payload), "count": len(payload)}
    return {"keys": [], "count": 0, "type": type(payload).__name__}


def safe_log_extra(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize a caller-supplied context into record attributes safe to emit.

    ``AgentLoop`` calls ``_handle_error(error, {"inputs": inputs})``, so passing
    the context straight through as ``extra=`` put the FULL agent inputs onto
    the LogRecord at ERROR — a level that survives every production log config.
    Default formatters drop extra attributes, but structured handlers
    (python-json-logger, structlog, OTel log export) render them, which is
    precisely where logs get shipped off-host.

    Every emitted name is ``ctx_``-prefixed, which cannot collide with a
    reserved ``LogRecord`` attribute (none of them start with ``ctx_``); a
    collision would otherwise make ``logging`` raise at the call site.
    """
    safe: Dict[str, Any] = {}
    for key, value in (context or {}).items():
        name = f"ctx_{key}"
        if isinstance(value, dict):
            summary = summarize_payload(value)
            safe[f"{name}_keys"] = summary["keys"]
            safe[f"{name}_count"] = summary["count"]
        else:
            safe[f"{name}_type"] = type(value).__name__
    return safe


def log_full_payload(
    config: Any, logger: logging.Logger, label: str, payload: Any
) -> None:
    """Dump a full agent payload at DEBUG — opt-in only, always scrubbed.

    Two independent gates, both of which must open:

    1. ``config.log_full_payloads`` — defaults False, so turning DEBUG on
       globally (routine during incident response) does NOT start dumping user
       prompts, retrieved documents and PII.
    2. the logger actually being at DEBUG.

    Even then the rendered payload routes through ``scrub_credentials``, the
    single credential-scrub implementation in Kaizen. Scrubbing claims
    credential SHAPES, not arbitrary PII — gate (1) is what protects PII, which
    is why it fails closed (``rules/security.md`` § Secure-Default).
    """
    if not getattr(config, "log_full_payloads", False):
        return
    if not logger.isEnabledFor(logging.DEBUG):
        return

    from kaizen.utils.credential_scrub import scrub_credentials

    logger.debug("Full %s payload: %s", label, scrub_credentials(repr(payload)))

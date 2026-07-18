# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Process/env ``governance_required`` posture for direct LLM egress (#1779).

Governance of outbound LLM effects is an OPT-IN seam today: unless a caller
wraps the provider (``GovernedProvider``) or installs a process-global
interceptor (``install_interceptor`` in ``kailash.trust.pact.outbound``), a
bare client makes silently ungoverned real egress. This module adds the
OPT-OUT posture on top: when the posture is ACTIVE, a bare un-governed client
that WOULD make real egress is refused at construction (enforced from Kaizen,
which owns the client) unless the caller attaches a governance pair OR passes
``ungoverned=True``.

Layering (framework-first): core ``kailash`` (PACT) owns the posture state +
the typed :class:`~kailash.trust.pact.exceptions.UngovernedEgressRefused`
error; Kaizen owns the client and performs the enforcement by reading
``kailash.is_governance_required()`` at its construction/egress gate. EATP D6
parity: the posture semantics mirror the Rust SDK's per-deployment
``governance_required`` posture.

Resolution (most-specific wins):

1. programmatic override — :func:`set_governance_required` (``True``/``False``)
2. env ``KAILASH_GOVERNANCE_REQUIRED`` truthy in ``{1,true,yes,on}``
   (case-insensitive)
3. default **OFF** — and an *unrecognized* env value also resolves OFF, so an
   unset or garbage env var is byte-identical to today.

The state mirrors the exact shape of ``_active_interceptor`` / ``_active_lock``
in :mod:`kailash.trust.pact.outbound`: a module-global guarded by a lock.

Coverage (what an ACTIVE posture gates) — enforced from Kaizen:

* the four-axis ``LlmClient`` — every constructor + a defense-in-depth re-check
  at real-transport binding (``embed`` / ``complete`` / ``stream``);
* ``kaizen.agent.Agent`` construction, and ``BaseAgent`` egress (both the
  four-axis path AND the ``LLMAgentNode`` primary path, which routes through the
  four-axis ``LlmClient``);
* the ``LLMAgentNode`` legacy provider-chat fallback (providers with no
  four-axis wire, e.g. ``azure_ai_foundry``) — gated explicitly at that
  chokepoint;
* ``EmbeddingGeneratorNode`` — four-axis embed path AND the ollama legacy
  fallback;
* the ``kaizen_agents.llm.LLMClient`` construction chokepoint — the orchestration
  components (planner / recovery / protocols / monitor / context) that INJECT
  that client are covered through it;
* the **``kaizen-agents`` DELEGATE / adapter egress layer** — every direct
  provider-client construction is gated at its adapter ``__init__`` /
  ``AgentLoop`` client factory: ``delegate/adapters/*`` (OpenAI stream /
  Anthropic / Google / Ollama chat + embedding), ``orchestration/adapters.py``
  (OpenAI / Anthropic structured adapters), ``runtime_adapters/*`` (openai_codex
  / gemini_cli), and ``delegate/loop.py``'s ``AgentLoop`` client factory. The
  ``ungoverned`` opt-out is threaded top-down through ``Delegate`` →
  ``AgentLoop`` → the adapter registry → each adapter.

NON-coverage (the posture does NOT gate — an operator relying on the posture as a
hard egress boundary MUST NOT treat these as governed; tracked for a dedicated
follow-up audit of the kaizen provider/backend layer):

* the LEGACY ``kaizen.providers.llm.*`` providers (openai / anthropic / google /
  docker / perplexity) + their ``BYOKClientCache`` — the pre-#1720 provider layer.
  Reached VIA ``LLMAgentNode`` they ARE gated (at ``_provider_llm_response`` /
  ``_legacy_provider_chat``); direct standalone use is NOT. Retiring in #1720
  Wave C;
* the VISION / MULTIMODAL providers — ``kaizen.providers.document.*`` (vision /
  OCR) and ``kaizen.providers.multi_modal_adapter`` — construct provider clients
  directly for a distinct (non-chat) egress capability;
* the AZURE backend layer — ``kaizen.nodes.ai.azure_backends`` /
  ``unified_azure_provider`` (standalone Azure chat/embed).

These construct provider clients (``openai`` / ``anthropic`` / ``genai``)
DIRECTLY, outside the gated four-axis / adapter surfaces. Comprehensively gating
this provider/backend layer is a separate substantial workstream (its own audit)
and is NOT covered by this landing.

An installed process-global interceptor does NOT waive the posture for the
four-axis ``LlmClient`` (it does not route through the interceptor — see
``kaizen.llm.governance_gate``).
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

__all__ = [
    "is_governance_required",
    "set_governance_required",
    "GOVERNANCE_REQUIRED_ENV_VAR",
]

GOVERNANCE_REQUIRED_ENV_VAR = "KAILASH_GOVERNANCE_REQUIRED"

# Truthy tokens for the env var, case-insensitive. Anything else (including a
# garbage value) resolves OFF so an unset/garbage env is byte-identical to the
# pre-#1779 behaviour (invariant 2: most-specific-wins, unrecognized => OFF).
_TRUTHY_TOKENS = frozenset({"1", "true", "yes", "on"})

# Module-global posture override + lock (invariant 6: thread-safe posture
# state), mirroring outbound.py's _active_interceptor / _active_lock shape.
_posture_lock = threading.Lock()
_posture_override: bool | None = None


def set_governance_required(value: bool | None) -> None:
    """Set (or clear) the process-global governance-required override.

    * ``True``  — posture ON: a bare un-governed client/agent that would make
      real egress is refused at construction.
    * ``False`` — posture OFF: byte-identical to no posture (an explicit OFF
      override also masks a truthy env var).
    * ``None``  — clear the override; resolution falls back to the env var
      then the default OFF.
    """
    global _posture_override
    if value is not None and not isinstance(value, bool):
        raise TypeError(
            "set_governance_required expects bool | None; "
            f"got {type(value).__name__}"
        )
    with _posture_lock:
        _posture_override = value
    logger.debug("governance_posture.set", extra={"override": value})


def is_governance_required() -> bool:
    """Return whether the ``governance_required`` posture is active.

    Resolution order (most-specific wins): programmatic override →
    ``KAILASH_GOVERNANCE_REQUIRED`` env var (truthy in ``{1,true,yes,on}``,
    case-insensitive) → default ``False``. An unrecognized env value resolves
    ``False`` (byte-identical to today).
    """
    with _posture_lock:
        override = _posture_override
    if override is not None:
        return override
    raw = os.environ.get(GOVERNANCE_REQUIRED_ENV_VAR)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_TOKENS

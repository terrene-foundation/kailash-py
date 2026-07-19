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
  ``AgentLoop`` → the adapter registry → each adapter;
* **#1803 — the remaining ``kaizen.providers.*`` provider/backend layer**,
  extending the #1779 landing to every non-retiring direct-egress
  construction chokepoint:

  * ``kaizen.providers.llm.azure.AzureAIFoundryProvider`` — the ONE legacy
    chat provider #1720 Wave-2 did not retire (``resolve_deployment_for``
    declines to map ``azure_ai_foundry``). Direct standalone construction
    (``AzureAIFoundryProvider().chat(...)``, bypassing ``LLMAgentNode``) is
    now gated at each real-egress method (``chat`` / ``chat_async`` /
    ``stream_chat`` / ``embed`` / ``embed_async``) — construction and
    metadata-only methods (``is_available`` / ``get_capabilities`` /
    ``get_available_providers``) are NOT gated, mirroring the
    deployment-less ``LlmClient`` exemption. ``kaizen.providers.registry.
    get_provider(..., ungoverned=...)`` threads the caller's opt-out into
    the constructed instance so ``LLMAgentNode._legacy_provider_chat``'s
    outer gate and the instance's own inner gate agree;
  * the VISION / document-extraction providers —
    ``kaizen.providers.document.landing_ai_provider.LandingAIProvider``,
    ``.openai_vision_provider.OpenAIVisionProvider``, and
    ``.ollama_vision_provider.OllamaVisionProvider`` — gated at the top of
    ``extract()``, before file validation or any real HTTP/SDK egress.
    ``ProviderManager`` forwards its own ``ungoverned`` constructor arg to
    every sub-provider;
  * ``kaizen.providers.multi_modal_adapter`` — ``OpenAIMultiModalAdapter``
    is gated at the top of ``process_multi_modal`` (covering its vision /
    Whisper / text branches, each of which constructs ``openai.OpenAI()``);
    ``OllamaMultiModalAdapter`` is gated transitively through
    ``OllamaProvider.__init__`` (below), reached via
    ``_get_ollama_vision_provider``'s lazy construction. Locality (a local
    ``base_url``) is NOT a governance exemption for either Ollama surface —
    parity with the four-axis ``LlmClient`` path, which gates Ollama
    deployments too;
  * ``kaizen.providers.ollama_provider.OllamaProvider`` (re-exported as
    ``kaizen.providers.LegacyOllamaProvider``) — gated at ``__init__``,
    before ``_check_ollama_available()``'s unconditional real ``ollama.
    list()`` egress. The ``ungoverned`` field lives on ``OllamaConfig``
    (inherited by ``OllamaVisionConfig``), so
    ``kaizen.providers.ollama_vision_provider.OllamaVisionProvider``
    (top-level) is covered through its base-class construction — no
    instance of either class can exist without passing through the gate;
  * ``kaizen.nodes.ai.semantic_memory.SimpleEmbeddingProvider`` — a
    security-review follow-up finding (not caught by the initial parity
    sweep's regex, which had no aiohttp/requests pattern): real aiohttp
    embedding-host egress in ``embed_text()``, gated at the top of that
    method before the cache check or the aiohttp session. ``ungoverned``
    is threaded top-down from every consumer — ``SemanticMemoryStoreNode``,
    ``SemanticMemorySearchNode``, ``SemanticAgentMatchingNode``
    (``kaizen.nodes.ai.semantic_memory``), and
    ``SemanticHybridSearchNode`` / ``AdaptiveSearchNode``
    (``kaizen.nodes.ai.hybrid_search``, the latter composing the former)
    — each constructs its own INSTANCE-level provider (not class-cached,
    so one node's ``ungoverned=True`` never leaks into a sibling
    instance's default-governed provider).

  Two subsystems the #1803 audit found were retired, not gated — recorded
  here so a future reader does not re-discover the same dead ends:

  * ``BYOKClientCache`` (``kaizen.nodes.ai.client_cache``) is ORPHANED — a
    grep across ``kaizen/`` found zero production call sites (only its own
    regression tests construct it). It is a generic bounded cache over an
    opaque caller-supplied ``factory`` callable; there is no live
    construction to gate today. The mechanical parity sweep
    (``test_no_ungated_egress_construction_site_outside_known_files``)
    exempts it explicitly with this reasoning — if a future PR wires a
    real provider-client factory through it, that factory's construction
    site is the gate point, not the cache itself;
  * ``kaizen.nodes.ai.azure_backends`` / ``unified_azure_provider`` do not
    exist — #1820 retired the legacy unified-azure provider stack
    (``unified_azure_provider`` / ``azure_backends`` / ``azure_capabilities``
    / ``azure_detection``) in favour of the four-axis ``LlmClient`` path
    (see ``kaizen.llm.azure_env`` module docstring). Nothing to gate.

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

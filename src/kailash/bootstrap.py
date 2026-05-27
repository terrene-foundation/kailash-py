# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``kailash.bootstrap()`` — single-call configuration-from-intent.

Closes issue #1125 acceptance criteria 4 + 9:

    AC 4: ``kailash.bootstrap(brief, profile='dev')`` returns a
    :class:`BootstrapConfig` resolving ``db_url``, ``llm_model``,
    ``runtime``, and ``deployment_target`` consistent with the brief +
    profile.

    AC 9: env-var resolution honors :mod:`rules/env-models.md` — model
    names read from ``DEFAULT_LLM_MODEL`` / ``OPENAI_PROD_MODEL``; no
    hardcoded model strings; credentials never logged.

This is the configuration-resolution surface of the ``from_brief()``
family. The pipeline composes the S1 foundation modules at
:mod:`kailash._from_brief` so the LLM-mediation discipline
(scrubbing, confidence gating, allowlist enforcement, typed
exceptions) is identical with the workflow / DataFlow / Kaizen surfaces
shipped in S2 / S3 / S4.

## Pipeline

::

    brief (prose), profile
      → profile allowlist gate (NOT LLM — structural input validation)
      → scrub_brief()                              # credential scrub
      → BootstrapPlanSignature (meta-Signature)    # LLM emits typed plan
      → validate_plan() (confidence + enum allowlists)  # gate
      → coerce_plan() (Pydantic v2 structural gate)
      → BootstrapConfig(**plan_dict)               # AC 4 return shape
      → return BootstrapConfig

## Architecture Context

See ``workspaces/from-brief-1125/02-plans/01-architecture.md`` § 3.4.
This module is the Sg-Bootstrap surface (row F in §11) and the LAST of
the five user-facing ``from_brief()`` shards. Sibling shards: Sg-Workflow
(S2, ``kailash.workflow.from_brief``), Sg-Pipeline (S3,
``dataflow.from_brief``), Sg-Agent (S4, ``kaizen.signature_from_brief``).

## LLM-First Reasoning (rules/agent-reasoning.md)

The Signature description tells the LLM what to emit; the realizer is
DETERMINISTIC structural plumbing — no ``if``/``elif`` on brief
content, no keyword routing, no regex classification. The LLM IS the
extractor that maps brief + profile into the four config fields.

Permitted deterministic logic (per agent-reasoning.md
§ "Permitted Deterministic Logic"):
- exception 1: input validation (profile allowlist gate — structural,
  NOT content-based)
- exception 3: output formatting (BootstrapConfig dataclass assembly)
- exception 5: configuration branching (provider inference for the
  Kaizen agent from the model-name prefix)
- exception 6: tool result parsing (validator → dataclass realizer)

## Import-Time Circularity Note

All Kaizen imports are LAZY (deferred to call-time inside
:func:`bootstrap` and :func:`_build_agent`) because ``kaizen.__init__``
chains into ``kailash.trust.posture`` which reads
``kailash.__version__``; ``kailash.__init__`` imports
``kailash.bootstrap`` BEFORE ``__version__`` is bound. Any top-level
kaizen import in this module would trigger a circular-import
``ImportError`` at package load time. The :class:`BootstrapPlanSignature`
class is therefore also lazy — accessed via :func:`_signature_cls`,
NOT defined at module scope. Same fence pattern as
:mod:`kailash.workflow.from_brief` (S2).

Origin: issue #1125 — the brief asserts (AC 4) that
``kailash.bootstrap(brief, profile)`` returns a resolved config; today
the call raises ``AttributeError``. This module promotes the documented
contract to executable behavior. User-anchored value source (a): the
issue body.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

if TYPE_CHECKING:
    pass

__all__ = [
    "ALLOWED_PROFILES",
    "ALLOWED_RUNTIMES",
    "ALLOWED_DEPLOYMENT_TARGETS",
    "BootstrapConfig",
    "BootstrapPlan",
    "BootstrapPlanSignature",
    "bootstrap",
]

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Allowlists (Q2 + Q6 closed enums)                                           #
# --------------------------------------------------------------------------- #
#
# Per architecture plan §3.4 + Q2/Q6 decision records: every enum that the
# LLM is permitted to emit OR that the user is permitted to pass MUST be
# enumerated as a closed allowlist. Hallucinated values (LLM) and invalid
# inputs (user) both raise BriefInterpretationError(unknown_value=...) so
# the failure mode is uniform and the offending value is in the typed
# exception's discriminator field.
#
# Extending these sets requires an explicit code change so a new profile,
# runtime, or deployment target cannot land silently. Same closed-allowlist
# discipline as S4's ALLOWED_FIELD_TYPES.

ALLOWED_PROFILES: Set[str] = {"dev", "prod"}
"""Closed allowlist of valid ``profile=`` values per Q2."""

ALLOWED_RUNTIMES: Set[str] = {"local", "async", "nexus"}
"""Closed allowlist of LLM-emittable ``resolved_runtime`` values per Q6."""

ALLOWED_DEPLOYMENT_TARGETS: Set[str] = {"dev", "prod", "containerized"}
"""Closed allowlist of LLM-emittable ``resolved_deployment_target`` per Q6."""


# --------------------------------------------------------------------------- #
# BootstrapConfig (frozen dataclass — the AC 4 return shape)                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BootstrapConfig:
    """Resolved configuration returned by :func:`bootstrap`.

    Frozen so callers cannot mutate a returned config post-resolution
    (the dataclass IS the contract the realizer enforces; mutation
    would silently desynchronize fields the LLM jointly reasoned
    about).

    Fields per issue #1125 AC 4:

    - ``db_url``: connection string. Format varies by backend (e.g.
      ``postgresql://...``, ``sqlite:///:memory:``,
      ``sqlite:///app.db``). Credential-bearing URLs are scrubbed at
      logging boundaries per ``rules/security.md``; the field itself
      may legitimately contain user-supplied credentials passed
      through unchanged from the brief.
    - ``llm_model``: LLM model name resolved per
      ``rules/env-models.md`` — preferentially from
      ``OPENAI_PROD_MODEL`` / ``DEFAULT_LLM_MODEL`` env, falling back
      to the LLM-emitted suggestion only when the env has no relevant
      override.
    - ``runtime``: one of :data:`ALLOWED_RUNTIMES`. Selects the Kailash
      runtime engine the deployment will use.
    - ``deployment_target``: one of :data:`ALLOWED_DEPLOYMENT_TARGETS`.
      Names the operational context (local dev / production / a
      containerized release).

    The four fields are intentionally narrow: this surface is
    "what would I configure if the user told me X?" — NOT a full
    application bootstrap. Downstream code consumes the four fields
    and instantiates DataFlow / Nexus / Kaizen surfaces from them.
    """

    db_url: str
    llm_model: str
    runtime: str
    deployment_target: str


# --------------------------------------------------------------------------- #
# Lazy plan class (defers kaizen import past kailash.__version__ bind)        #
# --------------------------------------------------------------------------- #
#
# BootstrapPlan extends `BriefPlan` from `kailash._from_brief.validator`.
# Importing the validator submodule triggers `kailash._from_brief.__init__`
# which eagerly loads `signatures.py` → `kaizen.signatures` → `kaizen.core`
# → `kailash.trust.posture` → `kailash.__version__` (circular at package-load
# time before kailash/__init__.py binds __version__). Same fence as S2.

_BOOTSTRAP_PLAN_CLS_CACHE: Optional[type] = None


def _bootstrap_plan_cls() -> type:
    """Return the :class:`BootstrapPlan` class, constructed lazily.

    Defers the ``kailash._from_brief.__init__`` chain to call time so
    the kailash package can finish initialising (binding ``__version__``)
    before the kaizen transitive dependency lands.

    Returns:
        The lazily-constructed :class:`BootstrapPlan` subclass, cached
        after first invocation.
    """
    global _BOOTSTRAP_PLAN_CLS_CACHE
    if _BOOTSTRAP_PLAN_CLS_CACHE is not None:
        return _BOOTSTRAP_PLAN_CLS_CACHE

    from kailash._from_brief.validator import BriefPlan

    class BootstrapPlan(BriefPlan):
        """The LLM-emitted bootstrap plan.

        Extends :class:`~kailash._from_brief.validator.BriefPlan` with
        the four bootstrap-specific fields :func:`bootstrap` consumes.
        Pydantic's ``extra="forbid"`` (inherited from
        :class:`BriefPlan`) rejects any field the LLM hallucinates
        outside this schema. The enum allowlist gate downstream of
        construction additionally rejects out-of-set values for
        ``resolved_runtime`` and ``resolved_deployment_target``.
        """

        resolved_db_url: str
        resolved_llm_model: str
        resolved_runtime: str
        resolved_deployment_target: str

    _BOOTSTRAP_PLAN_CLS_CACHE = BootstrapPlan
    return BootstrapPlan


# --------------------------------------------------------------------------- #
# Lazy Signature class (defers kaizen import past kailash.__version__ bind)   #
# --------------------------------------------------------------------------- #


_SIGNATURE_CLS_CACHE: Optional[type] = None


def _signature_cls() -> type:
    """Return the BootstrapPlanSignature class, constructed lazily.

    The class is built on first access (NOT at module import) because
    ``kaizen.signatures`` triggers ``kaizen.__init__`` which imports
    ``kailash.trust.posture`` which reads ``kailash.__version__`` —
    creating a circular import if invoked during ``kailash.bootstrap``
    package load (kailash's ``__init__.py`` may import bootstrap BEFORE
    binding ``__version__``). The lazy access pattern defers kaizen
    import to call-time, when ``kailash`` is fully initialized.

    Returns:
        The :class:`BootstrapPlanSignature` class, cached after first
        construction.
    """
    global _SIGNATURE_CLS_CACHE
    if _SIGNATURE_CLS_CACHE is not None:
        return _SIGNATURE_CLS_CACHE

    from kailash._from_brief.signatures import BriefPlanSignature
    from kaizen.signatures import (  # type: ignore[import-not-found]
        InputField,
        OutputField,
    )

    class BootstrapPlanSignature(BriefPlanSignature):
        """Kaizen Signature for Sg-Bootstrap configuration emission.

        Inherits the floor contract from :class:`BriefPlanSignature`
        (``brief: str`` input + ``interpretation_confidence: float``
        output). Adds the ``profile`` input the user supplies AND the
        four resolved-config OutputFields the LLM is asked to emit:

        - ``resolved_db_url`` — connection string honoring profile +
          any env hints embedded in the brief.
        - ``resolved_llm_model`` — LLM model name. The realizer
          downstream may override with the env-resolved value per
          ``rules/env-models.md``.
        - ``resolved_runtime`` — one of ``{local, async, nexus}``.
        - ``resolved_deployment_target`` — one of
          ``{dev, prod, containerized}``.

        Per ``rules/agent-reasoning.md`` MUST Rule 3, the Signature
        DESCRIBES the reasoning the LLM is to perform; Python does
        not pre-classify the brief or filter its content.
        """

        # Pyright suppressions cite the Kaizen-wide ``reportAssignmentType``
        # pattern documented at ``_from_brief/signatures.py:110-138``.
        # Runtime safety: ``Signature`` uses ``SignatureMeta`` as its
        # metaclass; the metaclass rebinds class attributes at class
        # creation so the declarations never hold the raw Field instances
        # at runtime.
        profile: str = InputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "Operator profile naming the operational context. "
                "MUST be one of: 'dev' (local development), 'prod' "
                "(production deployment). Other values are rejected "
                "BEFORE this Signature runs — the realizer's structural "
                "input-validation gate guards the profile axis."
            )
        )
        resolved_db_url: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "Database connection string consistent with the brief "
                "+ profile. Examples: 'sqlite:///:memory:' (dev, "
                "ephemeral); 'sqlite:///app.db' (dev, file-backed); "
                "'postgresql://localhost/app' (prod, local Postgres); "
                "'postgresql://user:pass@host:5432/db' (prod, remote). "
                "When the brief embeds an explicit URL, use it verbatim. "
                "When the brief is silent, infer a sensible default "
                "from the profile: 'dev' → sqlite ephemeral; 'prod' "
                "→ postgres on localhost."
            )
        )
        resolved_llm_model: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "LLM model name suggestion. Per ``rules/env-models.md``, "
                "model names MUST come from environment variables — "
                "this field is a SUGGESTION the realizer honors ONLY "
                "when the env has no override. Suggest a profile-"
                "appropriate model: a smaller / cheaper model for "
                "'dev', a capable model for 'prod'. Use model NAMES "
                "(e.g. 'gpt-4o-mini', 'claude-haiku') — NOT env var "
                "names. The realizer will substitute the env-resolved "
                "value when DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL "
                "is set."
            )
        )
        resolved_runtime: str = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "Kailash runtime engine. MUST be one of: 'local' "
                "(LocalRuntime — sync CLI scripts), 'async' "
                "(AsyncLocalRuntime — Docker/FastAPI/Nexus), 'nexus' "
                "(multi-channel server deployment). Infer from the "
                "brief: a sync script → 'local'; a server / API / "
                "Docker mention → 'async'; an explicit Nexus / multi-"
                "channel request → 'nexus'. If unsure, lower "
                "interpretation_confidence so the realizer refuses."
            )
        )
        resolved_deployment_target: str = (
            OutputField(  # pyright: ignore[reportAssignmentType]
                description=(
                    "Operational deployment target. MUST be one of: "
                    "'dev' (local developer machine), 'prod' (production "
                    "deployment), 'containerized' (Docker / Kubernetes "
                    "/ container runtime). Profile=dev usually maps "
                    "to target=dev; profile=prod may map to target=prod "
                    "OR target=containerized depending on whether the "
                    "brief mentions Docker / containers / orchestration. "
                    "If unsure, lower interpretation_confidence."
                )
            )
        )

    _SIGNATURE_CLS_CACHE = BootstrapPlanSignature
    return BootstrapPlanSignature


def __getattr__(name: str) -> Any:
    """PEP 562 module-level ``__getattr__`` for lazy class resolution.

    Per ``rules/orphan-detection.md`` § 6b, lazy-loaded symbols MUST
    stay discoverable through the module's public surface. This hook
    resolves ``from kailash.bootstrap import BootstrapPlanSignature``
    and ``from kailash.bootstrap import BootstrapPlan`` at call-time
    (the symbols are in ``__all__``, have lazy resolvers, and have
    ``TYPE_CHECKING`` entries below).
    """
    if name == "BootstrapPlanSignature":
        return _signature_cls()
    if name == "BootstrapPlan":
        return _bootstrap_plan_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # Surface lazy classes to static analyzers (CodeQL py/undefined-export,
    # pyright, mypy) per ``rules/orphan-detection.md`` § 6b. Runtime
    # bodies live inside ``_signature_cls`` / ``_bootstrap_plan_cls``.
    class BootstrapPlanSignature:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_signature_cls`."""

        brief: str
        profile: str
        interpretation_confidence: float
        resolved_db_url: str
        resolved_llm_model: str
        resolved_runtime: str
        resolved_deployment_target: str

    class BootstrapPlan:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_bootstrap_plan_cls`."""

        interpretation_confidence: float
        resolved_db_url: str
        resolved_llm_model: str
        resolved_runtime: str
        resolved_deployment_target: str


# --------------------------------------------------------------------------- #
# Env-grounded LLM model resolution (rules/env-models.md)                     #
# --------------------------------------------------------------------------- #


def _resolve_llm_model_from_env() -> Optional[str]:
    """Return the LLM model name from env, or ``None`` when unset.

    Resolution order per ``rules/env-models.md`` § Model-Key Pairings
    + the canonical recipe at the top of that file:

    1. ``OPENAI_PROD_MODEL`` (production-tier OpenAI override).
    2. ``DEFAULT_LLM_MODEL`` (project-wide default).
    3. ``None`` — the caller substitutes the LLM-emitted suggestion.

    Loads ``.env`` via :func:`dotenv.load_dotenv` per
    ``rules/env-models.md`` § "ALWAYS Load .env Before Operations".
    When ``python-dotenv`` is unavailable (extras-only install) the
    function silently uses ``os.environ`` as-is — the failure mode
    is "env var absent" which falls through to the LLM suggestion,
    NOT a crash. This matches the optional-dependency contract at
    ``rules/dependencies.md`` § BLOCKED Anti-Patterns (loud failure
    at call site is permitted; here the call-site failure is "the
    LLM suggestion is used", which is loud at the test-fixture level).

    Returns:
        The resolved model name, or ``None`` when no override is set.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        # dotenv unavailable — env is read as-is. The "no env override"
        # branch is the correct fallthrough; we DO NOT swallow another
        # exception class here.
        pass
    # The two env vars in priority order. The list is short and
    # data-driven, not a routing if/elif on user input — permitted per
    # agent-reasoning.md § "Permitted Deterministic Logic" exception 5
    # (configuration branching).
    for var in ("OPENAI_PROD_MODEL", "DEFAULT_LLM_MODEL"):
        value = os.environ.get(var)
        if value:
            return value
    return None


# --------------------------------------------------------------------------- #
# Agent factory (mirrors S2 _build_agent)                                     #
# --------------------------------------------------------------------------- #


def _build_agent(model: str, signature: Any) -> Any:
    """Construct the Kaizen BaseAgent that emits the bootstrap plan.

    Per ``rules/framework-first.md`` § Kaizen, agents are Kaizen
    primitives (BaseAgent + Signature). The agent is constructed with
    a structured-output ``response_format`` derived from the signature
    so the LLM returns schema-conformant JSON the validator can coerce
    without regex post-processing.

    Args:
        model: The LLM model name from ``DEFAULT_LLM_MODEL`` per
            ``rules/env-models.md``.
        signature: The signature instance the agent runs against.

    Returns:
        A constructed :class:`~kaizen.core.base_agent.BaseAgent`.
    """
    from kaizen.core.base_agent import BaseAgent  # type: ignore[import-not-found]
    from kaizen.core.config import BaseAgentConfig  # type: ignore[import-not-found]
    from kaizen.core.structured_output import (  # type: ignore[import-not-found]
        create_structured_output_config,
    )

    # Provider inference from the model string prefix (structural plumbing,
    # NOT a decision on user input content — ``rules/agent-reasoning.md``
    # § "Permitted Deterministic Logic" exception 5 + 6). Mirrors the
    # identical pattern in src/kailash/workflow/from_brief.py::_build_agent.
    provider = "openai"
    lower = model.lower()
    if lower.startswith("claude"):
        provider = "anthropic"
    elif lower.startswith("gemini"):
        provider = "google"
    elif lower.startswith("deepseek"):
        provider = "deepseek"
    elif lower.startswith(("mistral", "mixtral")):
        provider = "mistral"

    response_format = create_structured_output_config(signature, strict=False)
    config = BaseAgentConfig(
        llm_provider=provider,
        model=model,
        temperature=0.1,
        response_format=response_format,
        structured_output_mode="explicit",
    )
    return BaseAgent(config=config, signature=signature)


# --------------------------------------------------------------------------- #
# Realizer (deterministic plumbing — permitted per agent-reasoning § 6)        #
# --------------------------------------------------------------------------- #


def _realize_config(plan: Any, *, env_llm_model: Optional[str]) -> BootstrapConfig:
    """Realize a validated plan into a :class:`BootstrapConfig`.

    Pure structural plumbing per ``rules/agent-reasoning.md`` §
    "Permitted Deterministic Logic" (exception 6, tool-result parsing).
    The function does NOT inspect brief CONTENT — it only:

    1. Reads four already-LLM-validated string fields off the plan.
    2. Substitutes the env-resolved LLM model when present per
       ``rules/env-models.md`` (configuration branching, exception 5).
    3. Constructs the frozen :class:`BootstrapConfig` dataclass.

    Args:
        plan: A :class:`BootstrapPlan` already validated by
            :func:`validate_plan` (typed + confidence + enum
            allowlists).
        env_llm_model: The env-resolved LLM model name (from
            :func:`_resolve_llm_model_from_env`), or ``None`` when no
            env override exists.

    Returns:
        A frozen :class:`BootstrapConfig` with the four resolved
        fields.
    """
    # rules/env-models.md "single source of truth" — env wins when set;
    # the LLM-emitted suggestion is the documented fallback per the
    # Signature description.
    resolved_model = env_llm_model if env_llm_model else plan.resolved_llm_model
    return BootstrapConfig(
        db_url=plan.resolved_db_url,
        llm_model=resolved_model,
        runtime=plan.resolved_runtime,
        deployment_target=plan.resolved_deployment_target,
    )


# --------------------------------------------------------------------------- #
# Public entrypoint                                                           #
# --------------------------------------------------------------------------- #


def bootstrap(
    brief: str,
    profile: str = "dev",
    *,
    model: Optional[str] = None,
    confidence_threshold: float = 0.6,
) -> BootstrapConfig:
    """Realize a natural-language brief + profile into a :class:`BootstrapConfig`.

    This function is the configuration-resolution surface of the
    ``from_brief()`` family (issue #1125 AC 4 + AC 9). It composes the
    full S1 pipeline:

    1. **Profile allowlist gate** — ``profile`` MUST be one of
       :data:`ALLOWED_PROFILES`. Out-of-set values raise
       :class:`~kailash._from_brief.exceptions.BriefInterpretationError`
       (``unknown_value="profile=<value>"``) BEFORE any LLM call.
    2. **Credential scrub** — :func:`scrub_brief` strips embedded
       credentials before the LLM sees the brief.
    3. **LLM plan emission** — a Kaizen agent runs
       :class:`BootstrapPlanSignature` against the configured model.
    4. **Typed validation** — :func:`coerce_plan` enforces the
       :class:`BootstrapPlan` shape; :func:`validate_plan` enforces
       the confidence floor and the enum allowlists for
       ``resolved_runtime`` and ``resolved_deployment_target``.
    5. **Realization** — :func:`_realize_config` assembles the
       :class:`BootstrapConfig`, substituting the env-resolved LLM
       model when available per ``rules/env-models.md``.

    Args:
        brief: A natural-language description of the application
            being configured. Credentials in the brief are scrubbed
            before any logging or LLM call.
        profile: One of :data:`ALLOWED_PROFILES`. Defaults to
            ``"dev"``.
        model: Optional LLM model name override for the meta-call
            that emits the plan. When ``None``, reads
            ``DEFAULT_LLM_MODEL`` from the environment per
            ``rules/env-models.md``. NOTE: this is the model used to
            RUN the bootstrap LLM call, distinct from the
            ``llm_model`` field of the returned :class:`BootstrapConfig`
            (which is the model the configured app will use).
        confidence_threshold: Minimum ``interpretation_confidence``
            the LLM must emit. Defaults to 0.6 per S1's
            :data:`DEFAULT_CONFIDENCE_THRESHOLD`.

    Returns:
        A frozen :class:`BootstrapConfig` with ``db_url``,
        ``llm_model``, ``runtime``, and ``deployment_target``
        resolved consistent with the brief + profile.

    Raises:
        MissingDefaultLLMModelError: When ``DEFAULT_LLM_MODEL`` is
            unset and no ``model`` override was provided.
        BriefInterpretationError: With ``unknown_value="profile=<v>"``
            when the profile is out of allowlist (raised BEFORE the
            LLM call). With ``low_confidence=True`` when the LLM
            emits ``interpretation_confidence`` below threshold. With
            ``unknown_value="runtime=<v>"`` /
            ``unknown_value="deployment_target=<v>"`` when the LLM
            emits an enum value outside the allowlist. With
            ``malformed=True`` when the plan is structurally invalid.
    """
    # Step 1 — profile allowlist gate. Structural input validation per
    # agent-reasoning.md § "Permitted Deterministic Logic" exception 1
    # (input validation, NOT content-based decision). Raised BEFORE
    # the LLM call so an invalid profile never reaches the LLM
    # provider AND never incurs an LLM token cost.
    #
    # The exception import + this gate are hoisted to the TOP of the
    # function — ABOVE the ``signatures`` import below — so the
    # profile-allowlist rejection fires kaizen-free. ``exceptions`` is a
    # kaizen-free ``_from_brief`` submodule (it imports nothing from
    # kaizen), whereas ``signatures.py:33`` does ``from kaizen.signatures
    # import ...`` at module scope. kaizen is a downstream optional package
    # (kailash-kaizen) absent in the core "Test"/"Base" CI jobs; an invalid
    # profile (``test_bootstrap_rejects_unknown_profile_before_llm_call``
    # and siblings) MUST raise its typed error WITHOUT requiring kaizen —
    # the test name encodes "before LLM call", and the LLM path is the only
    # thing that needs kaizen. Per ``rules/zero-tolerance.md`` Rule 3 (a loud
    # fail-fast with a typed exception, before the optional import) + the
    # wave-2 ml precedent (``kailash_ml/from_brief.py`` hoisted polars-only
    # guards above the kaizen import) + ``rules/dependencies.md`` § "Declared
    # = Imported" (core imports optional kaizen lazily; the kaizen-free input
    # gate runs without it).
    from kailash._from_brief.exceptions import BriefInterpretationError

    if profile not in ALLOWED_PROFILES:
        raise BriefInterpretationError(
            f"profile={profile!r} is not in the allowlist "
            f"(allowed: {sorted(ALLOWED_PROFILES)!r}); valid profiles "
            f"are 'dev' for local development and 'prod' for "
            f"production deployment",
            unknown_value=f"profile={profile}",
        )

    # Lazy imports — the remaining `_from_brief` submodules. ``scrubber`` +
    # ``validator`` are kaizen-free; ``signatures`` transitively imports
    # kaizen (see module docstring). Deferring to call-time fences the
    # circular load against the kailash package-init order AND keeps the
    # profile gate above kaizen-free (the LLM path below is the only part
    # that needs kaizen installed).
    from kailash._from_brief.scrubber import scrub_brief
    from kailash._from_brief.signatures import get_default_llm_model
    from kailash._from_brief.validator import coerce_plan, validate_plan

    # Step 2 — credential scrub (pre-LLM, pre-logging).
    scrubbed = scrub_brief(brief)
    logger.info(
        "bootstrap.start",
        extra={"brief_length": len(scrubbed), "profile": profile},
    )

    # Step 3 — derive the LLM model the meta-call runs against. This
    # is the model used to EMIT the bootstrap plan — distinct from the
    # model the configured app will use (which is the
    # ``llm_model`` field of the returned BootstrapConfig).
    resolved_model = model if model is not None else get_default_llm_model()

    # Step 4 — resolve the app-level LLM model from env (rules/env-models.md).
    # Done BEFORE the LLM call so the realizer has the value ready when the
    # plan returns. None means "no env override; honor the LLM suggestion".
    env_llm_model = _resolve_llm_model_from_env()

    # Step 5 — LLM plan emission. The Signature description tells the
    # LLM exactly what to emit; the response_format-bound agent forces
    # JSON conforming to BootstrapPlanSignature's shape so the
    # validator can coerce without regex post-processing.
    signature = _signature_cls()()
    agent = _build_agent(resolved_model, signature)
    raw = agent.run(brief=scrubbed, profile=profile)
    # SEC-6: schema-revealing field names (the keys of the LLM-emitted
    # plan dict) stay at DEBUG with a count-only surface per
    # rules/observability.md Rule 8.
    logger.debug(
        "bootstrap.llm_returned",
        extra={"field_count": len(raw) if isinstance(raw, dict) else 0},
    )

    # Step 6 — typed validation. coerce_plan wraps pydantic.ValidationError
    # in BriefInterpretationError(malformed=True). validate_plan enforces
    # the confidence floor AND the two enum allowlists via
    # allowed_config_values — but our enums are output fields on the
    # plan, not nested in a `config` dict, so we run two explicit
    # allowlist checks here on the validated plan instead. The shape
    # mirrors S1's allowlist contract (validate_config_value-like checks).
    plan: Any = coerce_plan(raw, _bootstrap_plan_cls())
    validate_plan(plan, confidence_threshold=confidence_threshold)

    # Step 7 — enum allowlist gates for the two closed-set fields.
    # Both fields are direct OutputFields on the plan (not nested in a
    # `config` dict), so validate_plan's allowed_config_values argument
    # doesn't apply structurally; the explicit checks below close the
    # same contract per S1 invariant 2 (allowlist enforcement).
    if plan.resolved_runtime not in ALLOWED_RUNTIMES:
        raise BriefInterpretationError(
            f"runtime={plan.resolved_runtime!r} is not in the allowlist "
            f"(allowed: {sorted(ALLOWED_RUNTIMES)!r}); the LLM emitted "
            f"an unknown runtime engine",
            unknown_value=f"runtime={plan.resolved_runtime}",
        )
    if plan.resolved_deployment_target not in ALLOWED_DEPLOYMENT_TARGETS:
        raise BriefInterpretationError(
            f"deployment_target={plan.resolved_deployment_target!r} is "
            f"not in the allowlist (allowed: "
            f"{sorted(ALLOWED_DEPLOYMENT_TARGETS)!r}); the LLM emitted "
            f"an unknown deployment target",
            unknown_value=f"deployment_target={plan.resolved_deployment_target}",
        )

    # Step 8 — realize into a frozen BootstrapConfig.
    config = _realize_config(plan, env_llm_model=env_llm_model)
    logger.info(
        "bootstrap.ok",
        extra={
            "profile": profile,
            "runtime": config.runtime,
            "deployment_target": config.deployment_target,
            "confidence": plan.interpretation_confidence,
            "llm_model_source": "env" if env_llm_model else "llm_suggestion",
        },
    )
    return config

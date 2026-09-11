"""Shared env-first provider-detection fallback.

Single source of truth for the narrow "which provider gets dispatched when
none was explicitly configured" fallback used across the Agent deployment
surface (`kaizen/core/agents.py`, `kaizen/core/base_agent.py`,
`kaizen/signatures/core.py`, `kaizen/integrations/nexus/base.py`). Extracted
after the SAME openai/anthropic/mock env-check logic was found duplicated
across 3-4 LLMAgentNode-param-building sites during the provider-gate
hardening sweep (rules/security.md "Multi-Site Kwarg Plumbing" — a helper
this widely duplicated drifts silently unless consolidated).

This is intentionally NOT `kaizen.config.providers.auto_detect_provider()`:
that function checks 7 providers (openai/azure/anthropic/google/perplexity/
ollama/docker) and RAISES `ConfigurationError` when none is available — a
different, fail-loud contract used by a different call path. This helper
mirrors only `Agent._get_provider_for_config()`'s narrower openai -> anthropic
order for the KEYED case.

#1952 — keyless NO LONGER silently resolves to "mock". #1947 closed the
silent-mock/fabricated-content class at the NODE: `LLMAgentNode` raises a
typed `ConfigurationError` when `provider` resolves to `None`, and the mock
provider stays reachable only when `provider="mock"` is passed EXPLICITLY.
This helper is the residual keyless surface #1947 left open: a real (non-test)
caller with no OPENAI/ANTHROPIC key and no explicit provider used to receive
"mock" here and dispatch fabricated content as a real answer, PASSING the
#1947 gate. It now returns `None` for the keyless case, so the unresolved
provider flows to the node's #1947 fail-loud gate — the single, structural
fail-loud point. The mock provider is legitimate; ONLY the silent keyless
default was the hazard.

#2220 — `resolve_agent_provider` NO LONGER composes this helper for a
model-bearing call. `detect_provider_from_env` answers "which credentials
exist", and #2069 left that answer standing in for "which vendor serves this
model" whenever a key was present, so an unregistered model still resolved
silently to `openai`. The two questions are unrelated; only `llm_provider=`
or the registry prefix table may answer the second. This helper keeps its own
contract unchanged — it is the COMPOSITION that was wrong, not the helper.

#2220 RESIDUAL — the other doors are now closed too. The paragraph that used
to stand here said they were not, and that was accurate when written: the
primary fix covered `resolve_agent_provider`, whose only production consumer
is `AgentConfig`, while ~33 other sites called `detect_provider_from_env`
DIRECTLY and paired its answer with a model in the same node config. Measured
then, with the primary fix applied:

    Agent(config={"model": "llama-3.1"})._get_provider_for_config()
      -> 'openai' under OPENAI_API_KEY, 'anthropic' under ANTHROPIC_API_KEY

Those sites now route through `resolve_node_provider` below: `core/agents.py`,
`core/base_agent.py`, `core/workflow_generator.py`, `signatures/core.py`,
`integrations/nexus/base.py`, and the whole `nodes/rag/*` family. The two
cache-key sites (`core/mixins/caching_mixin.py`,
`integrations/nexus/deployment_cache.py`) use `describe_node_provider`, which
mirrors the same answer without ever raising.

The one remaining direct caller of `detect_provider_from_env` is
`resolve_node_provider` itself, on its no-model path, and
`tests/unit/test_provider_routing_shape.py` fails CI if a new one appears — so
the fail-closed contract IS now a package-wide guarantee for model-bearing
calls, which it deliberately was not before.

A prefix HIT is also not proof of a remote vendor: Ollama serves
`deepseek-r1:7b` and `gpt-oss:20b`, which match the `deepseek-` and `gpt-`
rows and so route REMOTE without ever reaching the guard below. Closing that
needs a positive signal for local serving, not another name heuristic.

Precisely on the "no Ollama row" point, which is easy to overstate: a PARTIAL
row IS possible and one already exists as a substring table in
`kaizen/nodes/_env_model.py` (`llama`/`mistral`/`mixtral`/`bakllava` ->
ollama). What is impossible is a COMPLETE or SOUND one. Ollama serves
arbitrary names, so the table misses everything outside its list, and it is
wrong in the other direction too — its `"gpt" in lowered` arm claims
`gpt-oss:20b`, an Ollama model, for OpenAI. A name is not a location, so no
name table can decide this; that is why the fix below refuses rather than
guessing, and why no new heuristic is introduced here.

The kaizen test harness runs deliberately keyless (the root `conftest.py`
cost-guard actively scrubs provider secrets) with the mock provider registered
in `tests/conftest.py`. It opts back into keyless->mock via the EXPLICIT
`KAIZEN_ALLOW_KEYLESS_MOCK=1` env flag (set only by `tests/conftest.py`, in the
same unit-mode branch that patches the mock provider registry) — mirroring the
existing `KAIZEN_ALLOW_REAL_LLM` / `USE_REAL_PROVIDERS` opt-in shape. A real
user never sets it, so real keyless callers fail loud.
"""

import os
from typing import Optional


def _real_llm_run() -> bool:
    """True when the harness has EXPLICITLY enabled real, billed LLM calls.

    Read as a VETO on the mock opt-in below. ``tests/conftest.py`` sets
    ``KAIZEN_ALLOW_KEYLESS_MOCK`` whenever ``USE_REAL_PROVIDERS`` is unset, but
    ``KAIZEN_ALLOW_REAL_LLM`` is a SEPARATE gate (``pytest.ini``'s
    ``requires_real_llm`` marker), so the two can both be on. Without this
    veto, a real-LLM test naming an unregistered model would silently resolve
    to ``"mock"`` and assert green against fabricated content — in the one
    suite whose entire purpose is to exercise the real wire. Flag-vs-flag, not
    credential-keyed, so it preserves the #2220 invariant that an unregistered
    model's outcome never depends on WHICH credentials exist.
    """
    return os.environ.get("KAIZEN_ALLOW_REAL_LLM") == "1"


def _keyless_mock_allowed() -> bool:
    """True only when a test harness has EXPLICITLY opted into keyless->mock.

    Real callers never set ``KAIZEN_ALLOW_KEYLESS_MOCK``; a keyless resolution
    therefore returns ``None`` for them and fails loud at the node's #1947 gate.
    The kaizen unit harness sets it in ``tests/conftest.py`` so the deliberately
    keyless unit suite keeps dispatching to the registered mock provider.
    """
    return os.environ.get("KAIZEN_ALLOW_KEYLESS_MOCK") == "1"


def detect_provider_from_env() -> Optional[str]:
    """
    Env-first provider fallback: openai -> anthropic -> None (keyless).

    .. warning::

       This answers "WHICH CREDENTIALS EXIST", and nothing else. It is NOT
       an answer to "which vendor serves this model", and pairing its result
       with a model in the same node config IS the #2220 defect. A
       model-bearing caller MUST use :func:`resolve_node_provider` below; a
       direct call from such a site is rejected by the shape guard in
       ``tests/unit/test_provider_routing_shape.py``.

    Returns:
        "openai" if OPENAI_API_KEY is set, else "anthropic" if
        ANTHROPIC_API_KEY is set, else ``None`` (#1952 — keyless no longer
        silently resolves to "mock"). Callers with an explicit provider
        configured MUST check that first and only fall back to this helper when
        none was given, so a real API key is never silently ignored. When this
        returns ``None`` the unresolved provider flows to ``LLMAgentNode``'s
        #1947 fail-loud ``ConfigurationError`` gate rather than dispatching
        fabricated mock content as a real answer.

        Exception (explicit test-harness opt-in): when
        ``KAIZEN_ALLOW_KEYLESS_MOCK=1`` is set — only the kaizen unit harness
        sets it — the keyless case returns "mock" so the deliberately-keyless
        unit suite keeps working. Real callers never set it and fail loud.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _keyless_mock_allowed():
        return "mock"
    return None


def resolve_agent_provider(model: Optional[str], *, component: str = "") -> str:
    """Public provider resolution for an agent config (#2022).

    WHICH RESOLVER OWNS WHICH QUESTION
    ----------------------------------
    Kaizen deliberately keeps several provider resolvers, because they answer
    genuinely different questions with genuinely different failure contracts.
    #1952 ratified that non-equivalence; what it did NOT do is say which one a
    caller building an agent config should reach for. This function is that
    answer, and it is the ONLY one callers outside kaizen should use.

    * "Given a MODEL, which provider serves it?" -> canonical:
      :meth:`kaizen.llm.LlmProvider.from_model`. Its prefix table is DERIVED
      from the provider registry (``_PREFIX_TO_NAME``), so it cannot drift, and
      it fails closed with ``UnknownModelProvider``.
    * "Given the ENVIRONMENT, which provider is usable?" -> canonical:
      :func:`detect_provider_from_env` above.
    * "Given a full config, which provider plus credentials and endpoint?" ->
      canonical: ``kaizen.config.auto_detect_provider``.

    This function ADDS NO MAPPING OF ITS OWN, and since #2220 it no longer
    composes the second: it delegates to the model-keyed resolver ALONE and
    raises when that cannot answer. (It previously composed the two in a
    defined order; that composition WAS the #2220 defect.) Publishing a fourth
    model->provider table would recreate exactly the drift #1952 ended, so in
    particular it deliberately does NOT publish
    ``kaizen.nodes._env_model.detect_provider``, whose hand-maintained
    substring table is a weaker duplicate of the registry-derived one and is
    pinned to no registry.

    ONLY THE MODEL ANSWERS THE VENDOR QUESTION (#2220)
    --------------------------------------------------
    The model wins, and when the model cannot answer, NOTHING here answers.
    A ``claude-*`` model must dispatch to Anthropic even when
    ``OPENAI_API_KEY`` happens to be set; the env-first order sent it to
    OpenAI, which is a silent wrong-vendor dispatch.

    #2069 fixed that only for the KEYLESS case. With a credential present —
    the common developer configuration — an unregistered model still resolved
    through the env fallback, so ``model="llama-3.1"`` with ``OPENAI_API_KEY``
    exported dispatched a LOCAL model's prompt to OpenAI: off the machine,
    billed, and with no log line, warning, or exception.

    The env fallback is therefore NO LONGER consulted for a model-bearing
    call. A credential says which vendor the caller holds an ACCOUNT with; it
    never says which vendor SERVES THIS MODEL. Those are unrelated facts, and
    no quantity of credential evidence bridges them. Ollama makes the gap
    structural rather than incidental: it serves arbitrary model names, so no
    prefix can identify it and every local model name misses the registry by
    construction — the guess was not an edge case, it was the whole Ollama
    population.

    Callers with a model outside the registry's prefixes (local/Ollama builds,
    ``chatgpt-4o-latest``, fine-tuned ``ft:`` names) pass ``llm_provider``
    explicitly. That is a BREAKING change for anyone who relied on the guess,
    which is the point: that reliance was silent and sometimes wrong, and it
    now fails at config-construction time — before any network call — with an
    error naming the model and the exact kwarg that fixes it.

    Args:
        model: The model identifier the agent will run.
        component: Short caller identifier surfaced in the error message.

    Returns:
        A provider name suitable for ``BaseAgentConfig.llm_provider``.

    Raises:
        ConfigurationError: No registered provider prefix serves the model (or
            no usable model was supplied). Fails LOUD and names the fix —
            never returns ``None`` into the ``LLMAgentNode`` #1947 gate, whose
            error cannot say which model or component was responsible, and
            never guesses a vendor from an unrelated credential.
    """
    from kaizen.config.providers import ConfigurationError
    from kaizen.llm.provider import LlmProvider, UnknownModelProvider

    where = f" (component: {component})" if component else ""

    if isinstance(model, str) and model.strip():
        try:
            return LlmProvider.from_model(model).name
        except UnknownModelProvider:
            # #2220 — the environment is NOT consulted for a vendor answer.
            #
            # Reaching here means no registered prefix serves the model, so
            # any env-derived answer would be a GUESS keyed on a fact about
            # the caller's ACCOUNTS rather than about the MODEL. The previous
            # code returned that guess, which is how an Ollama user's prompt
            # reached OpenAI under an unrelated exported key.
            #
            # The test-harness opt-in is deliberately still honoured: it is
            # not a credential guess but an EXPLICIT flag that a real caller
            # never sets, and "mock" dispatches nowhere off-machine. Keeping
            # it preserves #1952's deliberately-keyless unit suite.
            #
            # Checked BEFORE any credential, which is a deliberate change of
            # precedence: pre-#2220 the flag was reached only when no key was
            # set, so a harness with a stray key exported resolved to that
            # key's vendor instead. The invariant this function now holds is
            # that for an unregistered model the outcome does not depend on
            # WHICH credentials exist — so the flag's answer cannot depend on
            # them either. Real callers never set it and reach the raise
            # below whatever their environment holds.
            #
            # Vetoed by an explicit real-LLM run, so a `requires_real_llm`
            # test naming an unregistered model fails loud (and names the
            # kwarg) instead of quietly asserting against mock content. The
            # veto is flag-vs-flag, so the credential-independence invariant
            # above still holds. `detect_provider_from_env` is deliberately
            # NOT given this veto: its keyless->mock branch is #1952's
            # contract for ~50 other call sites and is not this fix's to move.
            if _keyless_mock_allowed() and not _real_llm_run():
                return "mock"
        raise ConfigurationError(
            f"Could not resolve an LLM provider for model {model!r}{where}. "
            "No registered provider prefix serves this model. A provider "
            "credential in the environment (OPENAI_API_KEY / "
            "ANTHROPIC_API_KEY) is NOT used to answer this: it says which "
            "vendor you hold an account with, never which vendor serves this "
            "model, and guessing from it dispatched local-model prompts to "
            "third-party APIs (#2220). Fix by passing llm_provider= "
            "explicitly on the agent config — for example "
            'llm_provider="ollama" for a locally-served model, or '
            'llm_provider="openai" for an OpenAI model whose name carries no '
            'registered prefix (such as "chatgpt-4o-latest" or a fine-tuned '
            '"ft:..." name). Where the calling API exposes no llm_provider '
            "argument (the RAG node constructors, which read their model from "
            "DEFAULT_LLM_MODEL), declare the matching half in the environment "
            "instead: DEFAULT_LLM_PROVIDER (or KAIZEN_DEFAULT_PROVIDER). That "
            "is a setting whose only purpose is to name a provider, so it is "
            "read as configuration; a credential is not, which is why "
            "OPENAI_API_KEY / ANTHROPIC_API_KEY are ignored here."
        )

    # Distinguish "no model" from "a model of the wrong type" — reporting
    # b"gpt-4o" as "no model was supplied" sends the reader looking for a
    # missing env var instead of at the value they actually passed.
    if model is None or (isinstance(model, str) and not model.strip()):
        detail = "no model was supplied"
    else:
        detail = f"model must be a non-empty string, got {type(model).__name__}"
    raise ConfigurationError(
        f"Could not resolve an LLM provider: {detail}{where}. "
        "Pass a model, and pass llm_provider= explicitly if the model is not "
        "served by a registered provider prefix."
    )


def _declared_provider() -> Optional[str]:
    """A provider the operator DECLARED, or ``None``.

    Distinct in kind from a credential. ``KAIZEN_DEFAULT_PROVIDER`` (already
    honoured by ``kaizen.config.providers.auto_detect_provider``) and
    ``DEFAULT_LLM_PROVIDER`` (already paired with ``DEFAULT_LLM_MODEL`` in
    ``kaizen.llm.reasoning``) exist for no purpose other than naming a
    provider, so reading one is reading configuration — not inferring a vendor
    from an unrelated fact, which is what #2220 removed.

    Neither name is introduced here; both are pre-existing settings in this
    package, and this function is the single place the node path reads them.
    """
    for var in ("KAIZEN_DEFAULT_PROVIDER", "DEFAULT_LLM_PROVIDER"):
        value = os.environ.get(var)
        if value and value.strip():
            return value.strip().lower()
    return None


def resolve_node_provider(
    model: Optional[str],
    *,
    explicit: Optional[str] = None,
    component: str = "",
) -> Optional[str]:
    """Provider resolution for an ``LLMAgentNode`` config (#2220 residual).

    THE ONE PREDICATE EVERY MODEL-BEARING SITE ROUTES THROUGH
    ---------------------------------------------------------
    #2220's primary fix closed the composition at
    :func:`resolve_agent_provider`, whose only production consumer is
    ``AgentConfig``. Roughly thirty other sites built an ``LLMAgentNode``
    config by calling :func:`detect_provider_from_env` DIRECTLY and writing
    its answer into the same dict as a ``model`` key — the identical
    "a credential answers the vendor question" composition through a
    different door, measured live at
    ``Agent(config={"model": "llama-3.1"})._get_provider_for_config()`` and
    at every ``nodes/rag/*`` workflow builder.

    Repairing those sites one by one would leave the class open: the next
    node added re-opens it. So they all delegate HERE instead, and a shape
    guard fails CI when a new site calls the env helper directly.

    THE DISTINCTION THIS FUNCTION ENCODES
    -------------------------------------
    The question a caller is entitled to ask depends on whether it has a
    MODEL in hand, and that is the whole of it:

    * **A model was supplied** -> only the model may answer. Delegates to
      :func:`resolve_agent_provider`, which consults the registry-derived
      prefix table and RAISES ``ConfigurationError`` when no registered
      prefix serves the model. The environment is never consulted. A
      credential says which vendor the caller holds an ACCOUNT with; it
      never says which vendor SERVES THIS MODEL.
    * **No model was supplied** -> there is no model whose vendor could be
      mis-attributed, so "which credentials exist" IS the right question and
      :func:`detect_provider_from_env` answers it. This is #1952's
      unchanged contract, NOT a fallback for the case above, and it is
      deliberately not reached when a model is present.

    No new name table, substring test, or vendor heuristic is introduced:
    guessing a vendor from a model name is the defect, not the fix.

    Args:
        model: The model the node will run, or ``None``/empty when the node
            configures no model and leaves ``LLMAgentNode``'s own default.
        explicit: A provider the caller configured explicitly. Always wins,
            unvalidated and unmodified — an explicit choice is the one
            signal that is never a guess.
        component: Short caller identifier surfaced in the error message, so
            a raise names which node config was responsible.

    Returns:
        A provider name for the node config, or ``None`` when no model was
        supplied and the environment is keyless (flowing to ``LLMAgentNode``'s
        #1947 fail-loud gate, exactly as before).

    Raises:
        ConfigurationError: A model was supplied and no registered provider
            prefix serves it. The message names the model and the exact
            ``llm_provider=`` kwarg that fixes it.
    """
    if explicit:
        return explicit

    # The harness mock opt-in is deliberately NOT checked here.
    #
    # An earlier revision short-circuited to "mock" ahead of the registry, so
    # the deliberately-keyless kaizen unit suite would keep working for
    # registered models too. That was wrong, and measurably so: it made a
    # REGISTERED model's provider depend on a harness flag, and #1946's RAG
    # tests — which set a real credential and assert the sites resolve to a
    # real provider — saw "mock" at all seven modules.
    #
    # `resolve_agent_provider` already honours the flag, on a registry MISS
    # only. Delegating to it unchanged gives this path exactly that
    # precedence, which is the point: two predicates that disagree about when
    # the harness wins are two contracts, and the drift between them is what
    # #2220 was in the first place.
    from kaizen.config.providers import ConfigurationError

    if isinstance(model, str) and model.strip():
        try:
            return resolve_agent_provider(model, component=component)
        except ConfigurationError:
            # The registry cannot name a vendor for this model. Before
            # refusing, honour an explicitly DECLARED provider.
            #
            # This is not the guess #2220 removed, and the distinction is the
            # whole point: `DEFAULT_LLM_PROVIDER` / `KAIZEN_DEFAULT_PROVIDER`
            # are settings whose ONLY purpose is to name a provider, so setting
            # one is an affirmative statement by the operator. A credential is
            # not — it says which vendor they hold an account with, and it is
            # routinely exported for an unrelated tool. Reading the first is
            # config; reading the second as a vendor answer was the defect.
            #
            # It is checked AFTER the registry, never before, so declaring a
            # default cannot silently redirect a model the registry does know
            # (a `claude-*` model still goes to Anthropic). It replaces the
            # raise, and nothing else.
            #
            # This is also the migration path for callers that expose no
            # `llm_provider` argument — the RAG node constructors take their
            # model from `DEFAULT_LLM_MODEL`, so `DEFAULT_LLM_PROVIDER` is the
            # matching half and the two are meant to be set together.
            declared = _declared_provider()
            if declared:
                return declared
            raise

    # No model in hand. See the docstring: this is the credential question,
    # asked by a caller that has no model to mis-attribute, and it is the
    # ONLY path on which the environment still answers.
    return detect_provider_from_env()


def describe_node_provider(
    model: Optional[str], *, explicit: Optional[str] = None
) -> str:
    """Non-dispatching mirror of :func:`resolve_node_provider`, for CACHE KEYS.

    #1948 put the resolved provider into two cache keys so a result computed
    under one provider is never replayed after the provider changes. Those
    keys must track whatever the dispatch path resolves — but a cache key
    must never RAISE, and it never sends anything anywhere.

    So this returns the same answer :func:`resolve_node_provider` would, and
    substitutes the sentinel ``"<unresolved>"`` where that would raise. That
    is strictly stronger than the previous ``llm_provider or
    detect_provider_from_env()``: the key for an unregistered model no longer
    varies with which credentials happen to be exported, which is #2220's
    invariant applied to the key itself. A sentinel here cannot cause a wrong
    dispatch, because the dispatch path raises on this same input.
    """
    from kaizen.config.providers import ConfigurationError

    try:
        return str(resolve_node_provider(model, explicit=explicit))
    except ConfigurationError:
        return "<unresolved>"

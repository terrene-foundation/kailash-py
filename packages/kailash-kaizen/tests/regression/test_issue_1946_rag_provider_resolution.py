"""Issue #1946 regression — ``kaizen.nodes.rag`` LLMAgentNode sites must
RESOLVE a provider instead of silently mock-dispatching.

kaizen 2.41.0 (#1943) resolved provider omission across the ``Agent``
deployment surface via the shared helper
``kaizen.core._provider_env.detect_provider_from_env()`` (env-first:
``OPENAI_API_KEY`` -> openai, ``ANTHROPIC_API_KEY`` -> anthropic, else mock).
But every ``kaizen.nodes.rag.*`` workflow node built its inner
``LLMAgentNode`` stages WITHOUT a ``provider`` key, and
``LLMAgentNode.get_parameters()["provider"]`` defaults to ``"mock"`` — so
those RAG nodes silently mock-dispatched their LLM stages regardless of any
configured real API key. #1946 threads ``detect_provider_from_env()`` through
all 26 provider-omitting LLMAgentNode construction sites across the 7 affected
files (query_processing, agentic, conversational, evaluation, graph,
similarity, multimodal); ``workflows.py`` already set a provider and is left
untouched.

Assertion surface — the UNBUILT builder config, not the built workflow:
``WorkflowBuilder.build()`` materialises each ``LLMAgentNode`` into a
``NodeInstance`` whose ``.config`` AUTO-FILLS the ``"mock"`` provider default,
which would MASK a missing ``provider`` key (a built node always reports
``provider="mock"`` whether or not the raw config carried the key). So these
tests spy on ``WorkflowBuilder.build`` to snapshot the RAW ``self.nodes`` dict
(``{id: {"type": ..., "config": {...}}}``) BEFORE the build auto-fill runs —
exactly the surface the 2.41.0 (#1943) provider tests assert against.

Two contracts, one representative node per affected file:
  1. ``test_rag_llm_agent_carries_provider_key`` — the raw config for every
     ``LLMAgentNode`` site carries a ``provider`` key. This is the env-INDEPENDENT
     regression driver: reverting the fix removes the key, and the built
     node's "mock" auto-fill cannot mask a raw-config absence here.
  2. ``test_rag_provider_resolves_from_env`` — with ``OPENAI_API_KEY`` set the
     resolved provider is ``"openai"`` (env-first), proving the value is
     resolved through ``detect_provider_from_env()`` and NOT a hardcoded
     ``"mock"`` literal.

Env-var isolation (rules/testing.md § Env-Var Test Isolation MUST): every test
that reads or mutates the provider-affecting environment acquires the
module-scope ``_ENV_LOCK`` via the ``env`` fixture so xdist-parallel runs
cannot race, and clears ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` so an
ambient ``.env`` cannot bleed into assertions. These are Tier-1 unit tests: no
network call and no real LLM dispatch — the inner workflow is only built, never
executed.
"""

import threading
import warnings
from typing import Callable, Dict, Iterator, Tuple

import pytest

from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression

# Module-scope env lock per rules/testing.md § Env-Var Test Isolation.
_ENV_LOCK = threading.Lock()

# Env vars that steer detect_provider_from_env()'s env-first fallback. Cleared
# before each test so an ambient .env never leaks into a provider assertion.
_PROVIDER_VARS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Serialized + cleared provider environment for a deterministic fallback."""
    with _ENV_LOCK:
        for var in _PROVIDER_VARS:
            monkeypatch.delenv(var, raising=False)
        yield monkeypatch


def _representative_factories() -> Dict[str, Callable[[], object]]:
    """One representative node per affected file whose ``_create_workflow``
    builds >=1 provider-resolving ``LLMAgentNode`` stage. Imports are local so
    a collection-time import error in one RAG module cannot mask the others."""
    from kaizen.nodes.rag.agentic import AgenticRAGNode
    from kaizen.nodes.rag.conversational import ConversationalRAGNode
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode
    from kaizen.nodes.rag.graph import GraphRAGNode
    from kaizen.nodes.rag.multimodal import MultimodalRAGNode
    from kaizen.nodes.rag.query_processing import QueryDecompositionNode
    from kaizen.nodes.rag.similarity import CrossEncoderRerankNode

    # WorkflowNode subclasses build their inner workflow inside __init__
    # (super().__init__(workflow=self._create_workflow())); plain Node
    # subclasses build lazily, so call _create_workflow() explicitly. Either
    # way the build spy captures the raw LLMAgentNode config.
    return {
        "query_processing": lambda: QueryDecompositionNode()._create_workflow(),
        "agentic": lambda: AgenticRAGNode(),
        "conversational": lambda: ConversationalRAGNode(),
        "evaluation": lambda: RAGEvaluationNode(),
        "graph": lambda: GraphRAGNode(),
        "similarity": lambda: CrossEncoderRerankNode()._create_workflow(),
        "multimodal": lambda: MultimodalRAGNode(),
    }


def _capture_llm_agent_configs(
    factory: Callable[[], object],
) -> Dict[str, Tuple[bool, object]]:
    """Run ``factory`` while spying on ``WorkflowBuilder.build`` to snapshot the
    RAW (pre-build-auto-fill) config of every ``LLMAgentNode`` stage.

    Returns ``{node_id: (provider_key_present, provider_value)}``. The snapshot
    reads ``self.nodes`` — the unbuilt builder dict — so the built
    ``NodeInstance``'s ``provider="mock"`` auto-fill never masks an omission.
    """
    captured: Dict[str, Tuple[bool, object]] = {}
    original_build = WorkflowBuilder.build

    def _spy(self, *args, **kwargs):
        for node_id, spec in self.nodes.items():
            if spec.get("type") == "LLMAgentNode":
                config = spec.get("config", {})
                captured[node_id] = ("provider" in config, config.get("provider"))
        return original_build(self, *args, **kwargs)

    # PythonCodeNode line-count UserWarnings are cosmetic build-time noise.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(WorkflowBuilder, "build", _spy)
            factory()

    assert captured, "factory built no LLMAgentNode stage — test wiring is stale"
    return captured


@pytest.mark.parametrize("module", sorted(_representative_factories()))
def test_rag_llm_agent_carries_provider_key(env, module: str) -> None:
    """Every LLMAgentNode's RAW config carries a ``provider`` key.

    Env-independent regression driver: with the fix the key is present (value
    resolves to "mock" only because no key is set here); reverting the fix drops
    the key entirely — and the built node's "mock" auto-fill cannot mask a
    raw-config absence, so this assertion flips to fail on revert.
    """
    factory = _representative_factories()[module]
    captured = _capture_llm_agent_configs(factory)

    missing = [nid for nid, (present, _) in captured.items() if not present]
    assert not missing, (
        f"{module}: LLMAgentNode site(s) {missing} omit the 'provider' key — "
        f"they silently mock-dispatch (issue #1946)"
    )


@pytest.mark.parametrize("module", sorted(_representative_factories()))
def test_rag_provider_resolves_from_env(env, module: str) -> None:
    """With ``OPENAI_API_KEY`` set, every LLMAgentNode resolves ``provider`` to
    ``"openai"`` — proving env-first resolution through
    ``detect_provider_from_env()``, not a hardcoded ``"mock"`` literal."""
    env.setenv("OPENAI_API_KEY", "sk-test-1946")
    factory = _representative_factories()[module]
    captured = _capture_llm_agent_configs(factory)

    unresolved = {
        nid: value for nid, (_, value) in captured.items() if value != "openai"
    }
    assert not unresolved, (
        f"{module}: LLMAgentNode site(s) did not resolve provider from env "
        f"(expected 'openai', got {unresolved}) — issue #1946"
    )

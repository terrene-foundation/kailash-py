"""Regression test — keyless provider resolution fails loud (#1952).

#1947 (kaizen 2.43.0) closed the silent-mock / fabricated-content class at the
NODE: ``LLMAgentNode.get_parameters()["provider"].default`` is ``None`` and
``run()`` raises ``ConfigurationError`` when ``provider`` resolves to ``None``.
Mock stays reachable only when ``provider="mock"`` is passed EXPLICITLY.

#1952 closes the RESIDUAL surface #1947 left open — the *keyless dispatch
resolution*:

1. ``kaizen.core._provider_env.detect_provider_from_env()`` used to return
   ``"mock"`` when NO ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` was set. The
   Agent surface (``core/agents.py`` ``_get_provider_for_config``,
   ``core/base_agent.py``) and ~30 RAG dispatch sites pass that resolved string
   straight into ``LLMAgentNode(provider=...)``. So a real caller with no key
   and no explicit provider silently received ``"mock"`` (never ``None``),
   PASSED the #1947 fail-loud gate, and got FABRICATED content as a real answer.
   ``detect_provider_from_env()`` now returns ``None`` when keyless, so the
   unresolved provider flows to the node's #1947 gate — the single, structural
   fail-loud point. This is a STRUCTURAL closure, not an env heuristic.

2. ``EmbeddingGeneratorNode.run()`` used ``kwargs.get("provider", "mock")`` —
   a forgotten provider silently produced mock vectors returned as real
   embeddings. It now resolves ``None`` and fails loud with a typed
   ``ConfigurationError`` for every embedding-producing operation.

The mock provider is LEGITIMATE and stays fully reachable when requested
explicitly (``provider="mock"``); only the SILENT keyless default was the
hazard.

Env discipline: the kaizen unit harness runs deliberately keyless (the
package-root cost-guard scrubs provider secrets) with the mock provider
registered, and opts back into keyless->mock via the explicit
``KAIZEN_ALLOW_KEYLESS_MOCK=1`` flag set in ``tests/conftest.py``. These tests
reproduce a REAL keyless user by removing that flag (and the API keys) via
``monkeypatch`` — so they assert the real user's fail-loud behaviour regardless
of the harness opt-in. The embedding-surface tests need no env control:
``EmbeddingGeneratorNode`` reads ``provider`` straight from kwargs and never
consults the env fallback.
"""

import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.core._provider_env import detect_provider_from_env
from kaizen.nodes.ai.embedding_generator import EmbeddingGeneratorNode
from kaizen.nodes.ai.llm_agent import LLMAgentNode

pytestmark = pytest.mark.regression

_MESSAGES = [{"role": "user", "content": "What is 2 + 2?"}]


@pytest.fixture
def _keyless_env(monkeypatch):
    """Reproduce a REAL keyless user: no provider key, no test-mode opt-in.

    The root cost-guard already scrubs ``*_API_KEY``; this also removes the
    harness's ``KAIZEN_ALLOW_KEYLESS_MOCK`` opt-in so ``detect_provider_from_env``
    resolves the way it does for a real keyless caller, not the way the unit
    harness configures it. ``monkeypatch`` restores every var at teardown.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
    # A model is required to construct/execute an Agent (env-models.md); the
    # provider fail-loud fires before any model is used, but construction needs
    # the value present.
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")


class TestDetectProviderKeylessDoesNotReturnMock:
    """Structural pin (task deliverable iii): keyless resolution is NOT 'mock'."""

    def test_keyless_returns_none_not_mock(self, _keyless_env):
        # The load-bearing structural invariant. If a future edit reverts this
        # to `return "mock"`, the keyless-mock class re-opens and this fails.
        resolved = detect_provider_from_env()
        assert resolved is None, (
            f"detect_provider_from_env() returned {resolved!r} when keyless; "
            f'expected None. A "mock" keyless default re-opens the fabricated-'
            f"content class (#1952, the residual of #1947)."
        )
        assert resolved != "mock"

    def test_openai_key_still_resolves_openai(self, _keyless_env, monkeypatch):
        # A real key is never ignored — the keyed path is unchanged by #1952.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        assert detect_provider_from_env() == "openai"

    def test_anthropic_key_still_resolves_anthropic(self, _keyless_env, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
        assert detect_provider_from_env() == "anthropic"

    def test_explicit_test_opt_in_restores_keyless_mock(
        self, _keyless_env, monkeypatch
    ):
        # The harness contract: an EXPLICIT opt-in (never set by a real user)
        # restores keyless->mock so the deliberately-keyless unit suite works.
        monkeypatch.setenv("KAIZEN_ALLOW_KEYLESS_MOCK", "1")
        assert detect_provider_from_env() == "mock"


class TestAgentSurfaceKeylessFailsLoud:
    """Task deliverable (i), Agent surface: keyless -> fail-loud, not fabricated."""

    def test_agent_get_provider_is_none_when_keyless(self, _keyless_env):
        from kaizen.core.agents import Agent

        # The resolution seam every Agent dispatch site feeds into. None here
        # is what flows to LLMAgentNode(provider=None) -> the #1947 gate.
        assert Agent("qa", {})._get_provider_for_config() is None

    def test_agent_get_provider_explicit_mock_still_works(self, _keyless_env):
        from kaizen.core.agents import Agent

        assert Agent("qa", {"provider": "mock"})._get_provider_for_config() == "mock"

    def test_agent_resolved_none_dispatched_to_node_fails_loud(self, _keyless_env):
        from kaizen.core.agents import Agent

        # Composition: the None the Agent surface resolves, handed to a real
        # LLMAgentNode exactly as every dispatch site does, fails loud — no
        # fabricated content is producible on the keyless Agent path.
        resolved = Agent("qa", {})._get_provider_for_config()
        assert resolved is None
        with pytest.raises(ConfigurationError) as exc_info:
            LLMAgentNode().run(provider=resolved, messages=_MESSAGES)
        assert "provider" in str(exc_info.value).lower()

    def test_agent_execute_keyless_surfaces_error_not_fabricated_content(
        self, _keyless_env
    ):
        # Real end-to-end: a genuine Kaizen agent executed keyless surfaces the
        # fail-loud provider error, NOT a fabricated mock answer. No mocking —
        # a real framework runs the real workflow and hits the node's gate.
        from kaizen.core.framework import Kaizen

        agent = Kaizen().create_agent("qa", signature="question -> answer")
        raised = None
        result = None
        try:
            result = agent.execute(question="What is 2+2?")
        except Exception as e:  # noqa: BLE001 - asserting fail-loud either shape
            raised = e

        # Whether the framework raises or surfaces the error in the result, the
        # observable must be the fail-loud provider error, never a fabricated
        # answer produced by a silent mock.
        surfaced = str(raised) if raised is not None else repr(result)
        lowered = surfaced.lower()
        assert "provider" in lowered and (
            "unresolved" in lowered or "#1947" in surfaced or "#1952" in surfaced
        ), (
            "keyless Agent execute did not surface the fail-loud provider error; "
            f"observed: {surfaced[:300]!r}"
        )


class TestEmbeddingSurfaceKeylessFailsLoud:
    """Task deliverable (i), embedding surface + (ii) explicit mock still works.

    Env-independent: EmbeddingGeneratorNode reads `provider` from kwargs and
    never consults the env fallback, so no monkeypatch is needed.
    """

    @pytest.mark.parametrize(
        "op_kwargs",
        [
            {"operation": "embed_text", "input_text": "hello world"},
            {"operation": "embed_batch", "input_texts": ["a", "b"]},
            {"operation": "embed_mcp_resource", "mcp_resource_uri": "data://x.json"},
        ],
    )
    def test_keyless_embedding_operation_raises(self, op_kwargs):
        # A forgotten provider on an embedding-PRODUCING op fails loud (raise),
        # never silently returns fabricated mock vectors as real embeddings.
        with pytest.raises(ConfigurationError) as exc_info:
            EmbeddingGeneratorNode().run(**op_kwargs)
        msg = str(exc_info.value)
        assert "provider" in msg.lower()
        assert "#1952" in msg

    def test_keyless_similarity_from_texts_raises(self):
        # calculate_similarity from TEXTS needs a provider to embed them first.
        with pytest.raises(ConfigurationError):
            EmbeddingGeneratorNode().run(
                operation="calculate_similarity",
                input_texts=["cat", "dog"],
            )

    def test_similarity_of_two_supplied_vectors_needs_no_provider(self):
        # Pure vector math needs no provider — must NOT fail loud.
        result = EmbeddingGeneratorNode().run(
            operation="calculate_similarity",
            embedding_1=[0.1, 0.2, 0.3],
            embedding_2=[0.1, 0.2, 0.3],
        )
        assert isinstance(result, dict)
        assert result.get("success") is True

    def test_explicit_mock_embedding_still_works(self):
        # The test-harness contract: explicit provider="mock" produces a
        # deterministic mock embedding — legitimate, never a silent default.
        result = EmbeddingGeneratorNode().run(
            operation="embed_text", input_text="hello world", provider="mock"
        )
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("embedding"), "explicit mock provider returned no embedding"

    def test_explicit_mock_embedding_via_execute_still_works(self):
        # execute() applies get_parameters() defaults then run(); explicit mock
        # dispatches the mock embedding through the full Node.execute path.
        result = EmbeddingGeneratorNode().execute(
            operation="embed_text", input_text="hello world", provider="mock"
        )
        assert isinstance(result, dict)
        assert result.get("success") is True

    def test_keyless_execute_fails_loud_not_silent_mock(self):
        # execute() runs validate_inputs (applies the None default) then run();
        # run()'s ConfigurationError is raised BEFORE the try block, so the
        # framework surfaces a LOUD failure — never a fabricated-embedding dict.
        with pytest.raises(Exception) as exc_info:  # noqa: PT011 - chain asserted
            EmbeddingGeneratorNode().execute(
                operation="embed_text", input_text="hello world"
            )
        chain = []
        err = exc_info.value
        while err is not None:
            chain.append(err)
            err = getattr(err, "__cause__", None)
        assert any(isinstance(e, ConfigurationError) for e in chain) or (
            "ConfigurationError" in str(exc_info.value)
        ), f"expected ConfigurationError in the failure chain, got {chain!r}"

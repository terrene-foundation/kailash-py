"""Regression test — A2AAgentNode drops the silent provider="mock" default (#1952).

#1952 eliminated the silent ``kwargs.get("provider", "mock")`` default across the
LLM-node family so a keyless/omitted provider fails LOUD (resolves ``None`` → the
#1947 node gate raises ``ConfigurationError``) instead of silently dispatching the
mock provider and returning fabricated content as a real answer.

A holistic closure-parity review of #1952 found ``A2AAgentNode`` (a subclass of
``LLMAgentNode``) was NOT among #1952's audited construction sites and still
carried the exact anti-pattern SHAPE at 8 sites in ``kaizen/nodes/ai/a2a.py``
(``kwargs.get("provider", "mock")`` / ``getattr(self, "_current_provider",
"mock")`` / ``"mock-model"``).

Here ``"mock"`` was a DISCRIMINATOR default, NOT a fabrication path: the
secondary LLM insight-extraction / summarization branches skip to honest
rule-based / simple degradation when the provider is ``"mock"``. The PRIMARY
answer path (``super().run(**kwargs)``) is ALREADY #1947-fail-loud-gated, so a
keyless A2A call raises today. The residual closed here is the fragile SHAPE —
the ``"mock"`` string default when provider is omitted — which #1952's AC
("audit EVERY construction site") required removing. The fix is a
behavior-preserving ``"mock"``→``None`` substitution: an omitted provider now
resolves ``None`` (never the string ``"mock"``) and the discriminators route the
unresolved provider to the SAME rule-based / simple fallback ``"mock"`` did.

These tests pin three observable behaviors:

(a) keyless primary path → fail-loud ConfigurationError (NOT fabricated success);
(b) provider-omitted → ``_current_provider`` is ``None``, never the string "mock"
    (the residual SHAPE is gone);
(c) explicit ``provider="mock"`` is still honored (the explicit-opt-in mock path
    works — legitimate deterministic testing, never a silent default).

Env discipline mirrors ``test_issue_1952_keyless_provider_fail_loud.py``: the
keyless fixture reproduces a REAL keyless user by removing the provider keys AND
the harness's ``KAIZEN_ALLOW_KEYLESS_MOCK`` opt-in via ``monkeypatch`` (restored
at teardown). ``LLMAgentNode.run`` reads ``provider`` straight from kwargs and
never consults the env fallback, so the primary-path gate fires regardless — the
env control keeps the test faithful to a real keyless caller.
"""

import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.nodes.ai.a2a import A2AAgentNode

pytestmark = pytest.mark.regression

_MESSAGES = [{"role": "user", "content": "What is 2 + 2?"}]


@pytest.fixture
def _keyless_env(monkeypatch):
    """Reproduce a REAL keyless user: no provider key, no test-mode opt-in.

    Mirrors the fixture in ``test_issue_1952_keyless_provider_fail_loud.py`` so
    the A2A residual is asserted against the same real-keyless-caller conditions.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
    # A model is required to construct/execute an Agent (env-models.md); the
    # provider fail-loud fires before any model is used, but construction needs
    # the value present.
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")


class TestA2AKeylessPrimaryPathFailsLoud:
    """Deliverable (a): keyless A2A primary answer path fails loud, not fabricated."""

    def test_keyless_a2a_run_raises_configuration_error(self, _keyless_env):
        # A2AAgentNode.run reads provider via kwargs.get("provider") (None when
        # omitted after the fix), sets _current_provider, then calls
        # super().run(**kwargs) — the #1947-gated LLMAgentNode path — which
        # raises ConfigurationError on the unresolved (None) provider. No
        # fabricated mock answer is producible on the keyless primary path.
        with pytest.raises(ConfigurationError) as exc_info:
            A2AAgentNode().run(agent_id="agent-1", messages=_MESSAGES)
        assert "provider" in str(exc_info.value).lower()

    def test_keyless_a2a_never_returns_fabricated_success(self, _keyless_env):
        # Structural: the keyless call must RAISE, never return a success dict
        # with fabricated content. Assert the failure shape explicitly.
        raised = None
        result = None
        try:
            result = A2AAgentNode().run(agent_id="agent-2", messages=_MESSAGES)
        except ConfigurationError as e:
            raised = e
        assert raised is not None, (
            "keyless A2AAgentNode.run returned instead of failing loud; "
            f"got result={result!r} — the silent-mock class re-opened."
        )


class TestA2AProviderOmittedShapeIsNone:
    """Deliverable (b): omitted provider yields None, never the string 'mock'."""

    def test_current_provider_is_none_when_omitted(self, _keyless_env):
        # _current_provider is assigned at the top of run() (before the primary
        # super().run() fail-loud), so it is inspectable after the raise. The
        # load-bearing SHAPE pin: if a future edit reverts to
        # kwargs.get("provider", "mock"), this flips to "mock" and fails.
        node = A2AAgentNode()
        with pytest.raises(ConfigurationError):
            node.run(agent_id="agent-3", messages=_MESSAGES)
        assert node._current_provider is None, (
            f"_current_provider is {node._current_provider!r} when provider was "
            f'omitted; expected None. A "mock" default re-opens the fragile '
            f"silent-mock SHAPE (#1952 residual in A2AAgentNode)."
        )
        assert node._current_provider != "mock"
        assert node._current_model is None
        assert node._current_model != "mock-model"

    def test_source_carries_no_mock_string_default(self):
        # Mechanical grep pin: the fragile string defaults must be gone from the
        # source. Guards against a merge silently re-inlining the pre-fix shape.
        from pathlib import Path

        import kaizen.nodes.ai.a2a as a2a_mod

        src = Path(a2a_mod.__file__).read_text()
        assert 'kwargs.get("provider", "mock")' not in src, (
            'A2AAgentNode source still contains kwargs.get("provider", "mock") — '
            "the #1952 residual SHAPE was reintroduced."
        )
        assert 'kwargs.get("model", "mock-model")' not in src
        assert '"_current_provider", "mock"' not in src
        assert '"_current_model", "mock-model"' not in src


class TestA2AExplicitMockStillHonored:
    """Deliverable (c): explicit provider="mock" is still honored (opt-in works)."""

    def test_explicit_mock_provider_does_not_fail_loud(self):
        # The explicit-opt-in mock path is legitimate deterministic testing and
        # MUST still work — provider="mock" passed EXPLICITLY never triggers the
        # #1947 fail-loud gate. Env-independent: explicit provider bypasses any
        # env resolution.
        node = A2AAgentNode()
        result = node.run(
            provider="mock",
            model="mock-model",
            messages=_MESSAGES,
            agent_id="agent-4",
        )
        assert isinstance(result, dict)
        assert result.get("success") is True, (
            f"explicit provider='mock' did not succeed on A2AAgentNode; "
            f"got {result!r} — the explicit-opt-in mock path regressed."
        )
        # The explicit value is honored and stored — not coerced away.
        assert node._current_provider == "mock"
        assert node._current_model == "mock-model"

    def test_explicit_mock_uses_rulebased_insight_fallback(self):
        # Behavior-preservation of the DISCRIMINATOR: explicit provider="mock"
        # (like an omitted/None provider) routes insight extraction to the
        # honest rule-based fallback, NOT the LLM path. Exercised end-to-end
        # through a real SharedMemoryPoolNode so the insight branch runs.
        from kaizen.nodes.ai.a2a import SharedMemoryPoolNode

        pool = SharedMemoryPoolNode()
        node = A2AAgentNode()
        result = node.run(
            provider="mock",
            model="mock-model",
            messages=_MESSAGES,
            agent_id="agent-5",
            agent_role="analyst",
            memory_pool=pool,
        )
        assert isinstance(result, dict)
        assert result.get("success") is True
        stats = result.get("a2a_metadata", {}).get("insight_statistics", {})
        # Discriminator preserved: mock provider → rule-based extraction, never
        # the LLM path (which "mock" and None both skip, identically).
        assert stats.get("extraction_method") == "rule-based"

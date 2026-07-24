"""Regression tests — issue #1948 provider-handling minor follow-ups.

Four small, independent provider-handling fixes, one test class each:

1. ``CachingMixin._make_cache_key`` was provider-BLIND — the response-cache
   key omitted the resolved provider, so a response computed under one
   provider could replay across a provider change (an agent with no explicit
   ``llm_provider`` resolves the provider from ambient env keys, so identical
   inputs can dispatch to different providers across calls). FIX: the resolved
   provider is now part of the key.

2. The ``CachingMixin`` docstring documented ``caching_enabled=True`` as the
   enable flag, but the real gate BaseAgent maps to this mixin is
   ``batch_processing_enabled``; ``caching_enabled`` is not a BaseAgentConfig
   field, so the documented enable-path was a no-op (zero-tolerance Rule 3c).
   FIX: the docstring now names the real gate.

3. ``workflow_generator`` used the literal fallback ``llm_provider or "openai"``
   at the LLMAgentNode-provider sites, so an agent with only ``ANTHROPIC_API_KEY``
   set and no explicit provider was wrongly dispatched to OpenAI. FIX: the
   sites now resolve the provider via ``detect_provider_from_env()``.

4. ``DeploymentCache.create_cache_key`` omitted ``system_prompt`` and
   ``temperature``, so two agents sharing name+provider+model+signature but
   different prompts (or temperatures) collided under the module-global cache.
   FIX: both dimensions are now part of the key.
"""

import dataclasses
import hashlib
from types import SimpleNamespace

import pytest

from kaizen.core.config import BaseAgentConfig
from kaizen.core.mixins.caching_mixin import CachingMixin
from kaizen.integrations.nexus.deployment_cache import DeploymentCache
from kaizen.signatures import InputField, OutputField, Signature


def _fake_agent(llm_provider=None):
    """Minimal stand-in for a BaseAgent as _make_cache_key consumes it.

    _make_cache_key reads only ``agent.__class__.__name__`` and
    ``agent.config.llm_provider``; SimpleNamespace supplies both without
    dragging in the full BaseAgent construction path.
    """
    return SimpleNamespace(config=SimpleNamespace(llm_provider=llm_provider))


# ---------------------------------------------------------------------------
# Item 1 — CachingMixin cache key includes the resolved provider
# ---------------------------------------------------------------------------
class TestItem1CachingMixinCacheKeyProvider:
    def test_explicit_provider_is_part_of_key(self):
        """Same inputs, different explicit providers -> different keys."""
        key_openai = CachingMixin._make_cache_key(
            _fake_agent(llm_provider="openai"), question="test"
        )
        key_anthropic = CachingMixin._make_cache_key(
            _fake_agent(llm_provider="anthropic"), question="test"
        )
        assert key_openai != key_anthropic, (
            "cache key MUST differ across providers for identical inputs; "
            "a key blind to the provider replays one provider's response "
            "after a provider change (#1948 item 1)"
        )

    def test_same_provider_same_inputs_same_key(self):
        """The key stays stable for the same provider + inputs (real cache hit)."""
        key_a = CachingMixin._make_cache_key(
            _fake_agent(llm_provider="openai"), question="test"
        )
        key_b = CachingMixin._make_cache_key(
            _fake_agent(llm_provider="openai"), question="test"
        )
        assert key_a == key_b

    def test_env_resolved_provider_is_part_of_key(self, monkeypatch):
        """No explicit provider -> the env-resolved provider still keys it.

        This is the exact drift the fix targets: an agent that leaves
        ``llm_provider`` unset resolves the provider from ambient env keys,
        so the key MUST change when that ambient resolution changes.
        """
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
        key_under_openai = CachingMixin._make_cache_key(
            _fake_agent(llm_provider=None), question="test"
        )

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
        key_under_anthropic = CachingMixin._make_cache_key(
            _fake_agent(llm_provider=None), question="test"
        )

        assert key_under_openai != key_under_anthropic

    def test_key_does_not_embed_credentials(self, monkeypatch):
        """security.md: the resolved provider is a bare name, never the key."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-do-not-leak")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        key = CachingMixin._make_cache_key(
            _fake_agent(llm_provider=None), question="test"
        )
        # Key is a bare sha256 hex digest; assert it is exactly that and that
        # the secret cannot be recovered from it.
        assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# Item 2 — CachingMixin docstring names the REAL gate (batch_processing_enabled)
# ---------------------------------------------------------------------------
class TestItem2CachingMixinGateConsistency:
    def test_docstring_names_real_gate_not_phantom_field(self):
        doc = CachingMixin.__doc__ or ""
        assert "batch_processing_enabled" in doc, (
            "the docstring MUST document the real enable gate "
            "(batch_processing_enabled)"
        )
        assert "caching_enabled=True" not in doc, (
            "the docstring MUST NOT document caching_enabled — it is not a "
            "BaseAgentConfig field and enabling via it is a no-op "
            "(zero-tolerance Rule 3c)"
        )

    def test_documented_gate_is_a_real_config_field(self):
        field_names = {f.name for f in dataclasses.fields(BaseAgentConfig)}
        assert (
            "batch_processing_enabled" in field_names
        ), "the documented enable gate MUST be a real config field"

    def test_phantom_gate_is_not_a_config_field(self):
        field_names = {f.name for f in dataclasses.fields(BaseAgentConfig)}
        assert "caching_enabled" not in field_names, (
            "caching_enabled is NOT a BaseAgentConfig field; the old docstring "
            "advertised a dead enable-path"
        )

    def test_config_rejects_the_phantom_flag(self):
        """Passing the phantom flag is a hard error, proving it never gated."""
        with pytest.raises(TypeError):
            BaseAgentConfig(caching_enabled=True)  # type: ignore[call-arg]

    def test_real_gate_constructs(self):
        cfg = BaseAgentConfig(batch_processing_enabled=True)
        assert cfg.batch_processing_enabled is True

    def test_docstring_example_is_constructible(self):
        """The docstring example MUST use only real BaseAgentConfig kwargs.

        The old example passed cache_ttl (a KaizenConfig field, not a
        BaseAgentConfig one) alongside the phantom caching_enabled — a
        double-phantom example that raised TypeError if a user copied it.
        """
        assert "cache_ttl=600" not in (CachingMixin.__doc__ or ""), (
            "the docstring example MUST NOT pass cache_ttl to BaseAgentConfig "
            "(it is a KaizenConfig field; the constructor rejects it)"
        )


# ---------------------------------------------------------------------------
# Item 3 — workflow_generator resolves provider from env, not the "openai" literal
# ---------------------------------------------------------------------------
class TestItem3WorkflowGeneratorEnvDetection:
    def _provider_of(self, workflow, node_id):
        return workflow.nodes[node_id]["config"]["provider"]

    def test_fallback_workflow_uses_anthropic_when_only_anthropic_key(
        self, monkeypatch
    ):
        from kaizen.core.workflow_generator import WorkflowGenerator

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")

        gen = WorkflowGenerator(config=BaseAgentConfig(llm_provider=None))
        wf = gen.generate_fallback_workflow()
        assert self._provider_of(wf, "agent_fallback") == "anthropic", (
            "an agent with only ANTHROPIC_API_KEY MUST resolve to anthropic, "
            "not the hardcoded 'openai' literal (#1948 item 3)"
        )

    def test_fallback_workflow_uses_openai_when_openai_key(self, monkeypatch):
        from kaizen.core.workflow_generator import WorkflowGenerator

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

        gen = WorkflowGenerator(config=BaseAgentConfig(llm_provider=None))
        wf = gen.generate_fallback_workflow()
        assert self._provider_of(wf, "agent_fallback") == "openai"

    def test_explicit_provider_still_wins(self, monkeypatch):
        from kaizen.core.workflow_generator import WorkflowGenerator

        # Even with an OpenAI key present, an explicit provider is honored.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
        gen = WorkflowGenerator(config=BaseAgentConfig(llm_provider="anthropic"))
        wf = gen.generate_fallback_workflow()
        assert self._provider_of(wf, "agent_fallback") == "anthropic"

    def test_source_has_no_hardcoded_openai_provider_fallback(self):
        """The `llm_provider or "openai"` provider literal is gone from the source."""
        import kaizen.core.workflow_generator as wg

        src = __import__("pathlib").Path(wg.__file__).read_text()
        assert 'llm_provider or "openai"' not in src, (
            "no provider-dispatch site may fall back to the 'openai' literal; "
            "resolve via detect_provider_from_env() instead (#1948 item 3)"
        )
        assert "detect_provider_from_env" in src


# ---------------------------------------------------------------------------
# Item 4 — DeploymentCache key includes the REAL effective prompt + temperature
#
# These tests use a REAL BaseAgent + BaseAgentConfig (NOT SimpleNamespace).
# The prior SimpleNamespace-based test fabricated a `system_prompt` field that
# no real config has, so it proved nothing about real agents (the round-1
# redteam INVEST-NOW). The effective prompt now comes from
# agent._generate_system_prompt() — which varies by discovered MCP tools and
# subclass overrides — so these tests exercise the collision that actually
# occurs in production.
# ---------------------------------------------------------------------------
class _QASignature(Signature):
    question: str = InputField(description="the question")
    answer: str = OutputField(description="the answer")


class TestItem4DeploymentCacheKeyDimensions:
    def _real_agent(self, *, temperature=0.1):
        from kaizen.core.base_agent import BaseAgent

        cfg = BaseAgentConfig(
            llm_provider="openai",  # pin provider so the key isn't env-dependent
            model="test-model",
            temperature=temperature,
        )
        # mcp_servers=[] disables MCP auto-connect so construction is
        # deterministic and offline (Tier-1); _discovered_mcp_tools stays {}.
        return BaseAgent(config=cfg, signature=_QASignature(), mcp_servers=[])

    def test_different_effective_prompt_yields_different_key(self):
        """Real agents differing ONLY in discovered MCP tools MUST key apart.

        Two agents share name+provider+model+signature; the sole difference is
        the discovered-tools set, which changes _generate_system_prompt()'s
        output — the exact collision the fix closes. `str(signature)` does NOT
        capture the tool difference, so this fails without the effective-prompt
        dimension.
        """
        agent_a = self._real_agent()
        agent_b = self._real_agent()
        agent_a._discovered_mcp_tools = {}
        agent_b._discovered_mcp_tools = {
            "srv": [{"name": "read_file", "description": "reads a file"}]
        }
        # Sanity: the effective prompts genuinely differ.
        assert agent_a._generate_system_prompt() != agent_b._generate_system_prompt()

        key_a = DeploymentCache.create_cache_key(agent_a, "wf")
        key_b = DeploymentCache.create_cache_key(agent_b, "wf")
        assert key_a != key_b, (
            "two agents sharing name+provider+model+signature but different "
            "effective prompts (discovered MCP tools) MUST NOT collide "
            "(#1948 item 4)"
        )

    def test_custom_prompt_override_yields_different_key(self):
        """A subclass override of _generate_system_prompt is keyed on."""
        agent_a = self._real_agent()
        agent_b = self._real_agent()
        agent_a._generate_system_prompt = lambda: "You are agent A"
        agent_b._generate_system_prompt = lambda: "You are agent B"

        key_a = DeploymentCache.create_cache_key(agent_a, "wf")
        key_b = DeploymentCache.create_cache_key(agent_b, "wf")
        assert key_a != key_b

    def test_different_temperature_yields_different_key(self):
        key_cold = DeploymentCache.create_cache_key(
            self._real_agent(temperature=0.0), "wf"
        )
        key_warm = DeploymentCache.create_cache_key(
            self._real_agent(temperature=0.9), "wf"
        )
        assert key_cold != key_warm, (
            "different temperatures build different workflows and MUST key "
            "distinctly (#1948 item 4)"
        )

    def test_identical_agents_yield_same_key(self):
        key_a = DeploymentCache.create_cache_key(
            self._real_agent(temperature=0.3), "wf"
        )
        key_b = DeploymentCache.create_cache_key(
            self._real_agent(temperature=0.3), "wf"
        )
        assert key_a == key_b

    def test_config_system_prompt_field_is_a_no_op_for_real_agents(self):
        """Guard the redteam finding: system_prompt is NOT a BaseAgentConfig
        field, so the old getattr(config, 'system_prompt') dimension could
        never discriminate a real agent. Pin that the field is absent so a
        future 'fix' cannot silently reintroduce the vacuous dimension."""
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(BaseAgentConfig)}
        assert "system_prompt" not in field_names

    def test_key_is_sha256_hex(self):
        key = DeploymentCache.create_cache_key(self._real_agent(), "wf")
        assert len(key) == len(hashlib.sha256(b"x").hexdigest())
        assert all(c in "0123456789abcdef" for c in key)

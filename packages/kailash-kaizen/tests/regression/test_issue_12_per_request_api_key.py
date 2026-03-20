"""
Regression test for GitHub Issue #12:
feat(kaizen): Support per-request API key override in provider config functions.

Tests that API keys and base URLs can be provided at call time instead of
requiring environment variables, enabling BYOK (Bring Your Own Key) multi-tenant
scenarios.
"""

import os
from unittest.mock import patch

import pytest

from kaizen.config.providers import (
    ConfigurationError,
    ProviderConfig,
    get_anthropic_config,
    get_google_config,
    get_ollama_config,
    get_openai_config,
    get_perplexity_config,
    get_provider_config,
    provider_config_to_dict,
)
from kaizen.core.config import BaseAgentConfig


class TestProviderConfigApiKeyOverride:
    """Test per-request API key override in provider config functions."""

    def test_openai_config_with_explicit_api_key(self):
        """get_openai_config should use explicit api_key over env var."""
        with patch.dict(os.environ, {}, clear=True):
            # Without env var, explicit key should work
            config = get_openai_config(api_key="sk-tenant-123")
            assert config.api_key == "sk-tenant-123"
            assert config.provider == "openai"

    def test_openai_config_explicit_key_overrides_env(self):
        """Explicit api_key should take precedence over env var."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-key"}, clear=True):
            config = get_openai_config(api_key="sk-tenant-override")
            assert config.api_key == "sk-tenant-override"

    def test_openai_config_falls_back_to_env(self):
        """When no explicit key, should fall back to env var as before."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-key"}, clear=True):
            config = get_openai_config()
            assert config.api_key == "sk-env-key"

    def test_openai_config_no_key_raises(self):
        """When neither explicit key nor env var, should raise ConfigurationError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError):
                get_openai_config()

    def test_anthropic_config_with_explicit_api_key(self):
        """get_anthropic_config should accept explicit api_key."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_anthropic_config(api_key="sk-ant-tenant-456")
            assert config.api_key == "sk-ant-tenant-456"
            assert config.provider == "anthropic"

    def test_google_config_with_explicit_api_key(self):
        """get_google_config should accept explicit api_key."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_google_config(api_key="AIza-tenant-789")
            assert config.api_key == "AIza-tenant-789"
            assert config.provider == "google"

    def test_perplexity_config_with_explicit_api_key(self):
        """get_perplexity_config should accept explicit api_key."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_perplexity_config(api_key="pplx-tenant-101")
            assert config.api_key == "pplx-tenant-101"
            assert config.provider == "perplexity"

    def test_ollama_config_with_explicit_base_url(self):
        """get_ollama_config should accept explicit base_url."""
        with patch.dict(os.environ, {}, clear=True):
            # Ollama doesn't require API key, but we can override base_url
            # Skip if ollama not running (availability check may fail)
            try:
                config = get_ollama_config(base_url="http://custom-host:11434")
                assert config.base_url == "http://custom-host:11434"
            except ConfigurationError:
                pytest.skip("Ollama not available")

    def test_get_provider_config_with_api_key(self):
        """get_provider_config should thread api_key to specific provider."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_provider_config(
                provider="openai", model="gpt-4o", api_key="sk-byok-key"
            )
            assert config.api_key == "sk-byok-key"
            assert config.model == "gpt-4o"

    def test_provider_config_to_dict_excludes_api_key(self):
        """provider_config_to_dict must NOT include api_key (security hardening)."""
        config = ProviderConfig(
            provider="openai",
            model="gpt-4o",
            api_key="sk-tenant-key",
        )
        config_dict = provider_config_to_dict(config)
        assert "api_key" not in config_dict


class TestBaseAgentConfigApiKey:
    """Test api_key and base_url fields on BaseAgentConfig."""

    def test_base_agent_config_has_api_key_field(self):
        """BaseAgentConfig should accept api_key parameter."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
            api_key="sk-tenant-key",
        )
        assert config.api_key == "sk-tenant-key"

    def test_base_agent_config_has_base_url_field(self):
        """BaseAgentConfig should accept base_url parameter."""
        config = BaseAgentConfig(
            llm_provider="ollama",
            model="llama3.2",
            base_url="http://custom:11434",
        )
        assert config.base_url == "http://custom:11434"

    def test_base_agent_config_api_key_defaults_none(self):
        """api_key should default to None for backward compatibility."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4o")
        assert config.api_key is None

    def test_base_agent_config_from_domain_config_threads_api_key(self):
        """from_domain_config should pick up api_key from domain config."""
        from dataclasses import dataclass

        @dataclass
        class TenantConfig:
            llm_provider: str = "openai"
            model: str = "gpt-4o"
            api_key: str = "sk-tenant-key"
            base_url: str = "https://custom-proxy.example.com/v1"

        tenant_config = TenantConfig()
        base_config = BaseAgentConfig.from_domain_config(tenant_config)
        assert base_config.api_key == "sk-tenant-key"
        assert base_config.base_url == "https://custom-proxy.example.com/v1"

    def test_base_agent_config_from_dict_threads_api_key(self):
        """from_domain_config with dict input should pick up api_key."""
        config_dict = {
            "llm_provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-dict-key",
            "base_url": "https://proxy.example.com/v1",
        }
        base_config = BaseAgentConfig.from_domain_config(config_dict)
        assert base_config.api_key == "sk-dict-key"
        assert base_config.base_url == "https://proxy.example.com/v1"


class TestWorkflowGeneratorApiKey:
    """Test that WorkflowGenerator threads api_key via CredentialStore."""

    def test_workflow_generator_storescredential_ref_not_api_key(self):
        """WorkflowGenerator should store credential_ref, NOT api_key in node_config."""
        from kailash.workflow.credentials import get_credential_store

        from kaizen.core.workflow_generator import WorkflowGenerator
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSig(Signature):
            """Test signature."""

            question: str = InputField(desc="Question")
            answer: str = OutputField(desc="Answer")

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
            api_key="sk-workflow-key",
            base_url="https://proxy.example.com/v1",
        )

        generator = WorkflowGenerator(config=config, signature=TestSig())
        workflow = generator.generate_signature_workflow()

        # Inspect the built workflow's node config
        built = workflow.build()
        node = built.nodes.get("agent_exec")
        assert node is not None
        # api_key and base_url must NOT be in node_config (security)
        assert "api_key" not in node.config
        assert "base_url" not in node.config
        # credential_ref must be present
        cred_ref = node.config.get("credential_ref")
        assert cred_ref is not None
        assert cred_ref.startswith("cred_")
        # Credential must resolve to the correct values
        cred = get_credential_store().resolve(cred_ref)
        assert cred is not None
        assert cred.api_key == "sk-workflow-key"
        assert cred.base_url == "https://proxy.example.com/v1"


class TestRedTeamR1Fixes:
    """Regression tests for red team R1 findings."""

    def test_empty_string_api_key_raises(self):
        """Empty-string api_key must raise ConfigurationError, not silently pass."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError, match="empty"):
                get_openai_config(api_key="")

    def test_whitespace_api_key_raises(self):
        """Whitespace-only api_key must raise ConfigurationError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError, match="empty"):
                get_openai_config(api_key="   ")

    def test_empty_base_url_raises(self):
        """Empty-string base_url must raise ConfigurationError."""
        from kaizen.config.providers import _validate_base_url

        with pytest.raises(ConfigurationError, match="empty"):
            _validate_base_url("")

    def test_ssrf_metadata_url_blocked(self):
        """base_url targeting cloud metadata service must be blocked."""
        from kaizen.config.providers import _validate_base_url

        with pytest.raises(ConfigurationError, match="blocked"):
            _validate_base_url("http://169.254.169.254/latest/meta-data/")

    def test_fallback_workflow_storescredential_ref_not_api_key(self):
        """generate_fallback_workflow must store credential_ref, NOT api_key."""
        from kailash.workflow.credentials import get_credential_store

        from kaizen.core.workflow_generator import WorkflowGenerator

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
            api_key="sk-fallback-key",
            base_url="https://proxy.example.com/v1",
        )

        generator = WorkflowGenerator(config=config)
        workflow = generator.generate_fallback_workflow()

        built = workflow.build()
        node = built.nodes.get("agent_fallback")
        assert node is not None
        # api_key and base_url must NOT be in node_config (security)
        assert "api_key" not in node.config
        assert "base_url" not in node.config
        # credential_ref must be present and resolvable
        cred_ref = node.config.get("credential_ref")
        assert cred_ref is not None
        cred = get_credential_store().resolve(cred_ref)
        assert cred is not None
        assert cred.api_key == "sk-fallback-key"
        assert cred.base_url == "https://proxy.example.com/v1"

    def test_provider_config_to_dict_never_includes_api_key(self):
        """provider_config_to_dict must never include api_key (hardened)."""
        config = ProviderConfig(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
        )
        result = provider_config_to_dict(config)
        assert "api_key" not in result

        # None api_key should also NOT be in dict
        config_no_key = ProviderConfig(provider="openai", model="gpt-4o")
        result_no_key = provider_config_to_dict(config_no_key)
        assert "api_key" not in result_no_key


class TestLLMAgentNodeApiKey:
    """Test that LLMAgentNode accepts and uses api_key parameter."""

    def test_llm_agent_node_has_api_key_parameter(self):
        """LLMAgentNode should have api_key in its parameters."""
        from kaizen.nodes.ai.llm_agent import LLMAgentNode

        node = LLMAgentNode()
        params = node.get_parameters()
        assert "api_key" in params
        assert "base_url" in params


class TestCredentialStoreLifecycle:
    """Tests for CredentialStore register/resolve/clear lifecycle."""

    def test_register_and_resolve(self):
        """CredentialStore should register and resolve credentials."""
        from kailash.workflow.credentials import CredentialStore

        store = CredentialStore()
        ref = store.register(api_key="sk-test", base_url="https://example.com")
        assert ref.startswith("cred_")
        cred = store.resolve(ref)
        assert cred is not None
        assert cred.api_key == "sk-test"
        assert cred.base_url == "https://example.com"

    def test_clear_all(self):
        """CredentialStore.clear() should remove all credentials."""
        from kailash.workflow.credentials import CredentialStore

        store = CredentialStore()
        ref1 = store.register(api_key="sk-1")
        ref2 = store.register(api_key="sk-2")
        assert len(store) == 2
        store.clear()
        assert len(store) == 0
        assert store.resolve(ref1) is None
        assert store.resolve(ref2) is None

    def test_clear_single(self):
        """CredentialStore.clear(ref_id) should remove only that credential."""
        from kailash.workflow.credentials import CredentialStore

        store = CredentialStore()
        ref1 = store.register(api_key="sk-1")
        ref2 = store.register(api_key="sk-2")
        store.clear(ref1)
        assert store.resolve(ref1) is None
        assert store.resolve(ref2) is not None

    def test_resolve_unknown_returns_none(self):
        """Resolving unknown ref should return None, not raise."""
        from kailash.workflow.credentials import CredentialStore

        store = CredentialStore()
        assert store.resolve("cred_nonexistent") is None


class TestSerializationLeak:
    """Tests that serialized workflows never contain plaintext API keys."""

    def test_workflow_to_dict_no_api_key(self):
        """Workflow.to_dict() must not contain plaintext api_key anywhere."""
        import json

        from kailash.workflow.credentials import get_credential_store

        from kaizen.core.config import BaseAgentConfig
        from kaizen.core.workflow_generator import WorkflowGenerator
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSig(Signature):
            """Test."""

            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
            api_key="sk-SUPER-SECRET-KEY-12345",
        )
        generator = WorkflowGenerator(config=config, signature=TestSig())
        workflow = generator.generate_signature_workflow()
        built = workflow.build()

        serialized = json.dumps(built.to_dict())
        assert "sk-SUPER-SECRET-KEY-12345" not in serialized
        assert "api_key" not in serialized


class TestSafeSerializeRedaction:
    """Tests that _safe_serialize strips sensitive keys."""

    def test_safe_serialize_strips_api_key(self):
        """_safe_serialize must strip api_key from dicts."""
        from kailash.runtime.local import _safe_serialize

        data = {"model": "gpt-4o", "api_key": "sk-secret", "temperature": 0.7}
        result = _safe_serialize(data)
        assert "api_key" not in result
        assert result["model"] == "gpt-4o"

    def test_safe_serialize_strips_nested(self):
        """_safe_serialize must strip sensitive keys from nested dicts."""
        from kailash.runtime.local import _safe_serialize

        data = {"config": {"api_key": "sk-secret", "model": "gpt-4o"}, "name": "test"}
        result = _safe_serialize(data)
        assert "api_key" not in result.get("config", {})


class TestAsyncLLMProviderUnlock:
    """Test that use_async_llm is no longer restricted to OpenAI."""

    def test_anthropic_async_allowed(self):
        """BaseAgentConfig with anthropic + use_async_llm should not raise."""
        config = BaseAgentConfig(
            llm_provider="anthropic",
            model="claude-3-haiku-20240307",
            use_async_llm=True,
        )
        assert config.use_async_llm is True

    def test_google_async_allowed(self):
        """BaseAgentConfig with google + use_async_llm should not raise."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            use_async_llm=True,
        )
        assert config.use_async_llm is True


class TestBYOKClientCache:
    """Tests for the BYOK client cache."""

    def test_cache_returns_same_client(self):
        """get_or_create with same credentials should return cached client."""
        from kaizen.nodes.ai.client_cache import BYOKClientCache

        cache = BYOKClientCache(max_size=10, ttl_seconds=60)

        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"client": call_count}

        c1 = cache.get_or_create("sk-test", "https://api.example.com", factory)
        c2 = cache.get_or_create("sk-test", "https://api.example.com", factory)
        assert c1 is c2
        assert call_count == 1

    def test_cache_different_keys_different_clients(self):
        """Different credentials should create different clients."""
        from kaizen.nodes.ai.client_cache import BYOKClientCache

        cache = BYOKClientCache(max_size=10, ttl_seconds=60)

        c1 = cache.get_or_create("sk-1", None, lambda: "client-1")
        c2 = cache.get_or_create("sk-2", None, lambda: "client-2")
        assert c1 != c2
        assert len(cache) == 2

    def test_cache_eviction_at_capacity(self):
        """Cache should evict oldest entry when at max_size."""
        from kaizen.nodes.ai.client_cache import BYOKClientCache

        cache = BYOKClientCache(max_size=2, ttl_seconds=60)

        cache.get_or_create("sk-1", None, lambda: "c1")
        cache.get_or_create("sk-2", None, lambda: "c2")
        cache.get_or_create("sk-3", None, lambda: "c3")
        assert len(cache) == 2

    def test_cache_clear(self):
        """cache.clear() should remove all entries."""
        from kaizen.nodes.ai.client_cache import BYOKClientCache

        cache = BYOKClientCache(max_size=10)
        cache.get_or_create("sk-1", None, lambda: "c1")
        cache.get_or_create("sk-2", None, lambda: "c2")
        cache.clear()
        assert len(cache) == 0

    def test_cache_ttl_expiry(self):
        """Expired entries should be recreated."""
        import time

        from kaizen.nodes.ai.client_cache import BYOKClientCache

        cache = BYOKClientCache(max_size=10, ttl_seconds=0.1)

        c1 = cache.get_or_create("sk-1", None, lambda: "c1-v1")
        time.sleep(0.15)
        c2 = cache.get_or_create("sk-1", None, lambda: "c1-v2")
        assert c2 == "c1-v2"


class TestExportRedaction:
    """Tests that export utility strips sensitive keys."""

    def test_export_config_no_api_key(self):
        """Export data node config must not contain api_key."""
        from kailash.workflow.credentials import SENSITIVE_KEYS

        # Simulate what export does
        from copy import deepcopy

        config = {"model": "gpt-4o", "api_key": "sk-secret", "temperature": 0.7}
        config_copy = deepcopy(config)
        for key in SENSITIVE_KEYS:
            config_copy.pop(key, None)
        assert "api_key" not in config_copy
        assert config_copy["model"] == "gpt-4o"

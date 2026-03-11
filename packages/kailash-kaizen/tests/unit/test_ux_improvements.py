"""
Comprehensive tests for UX improvements.

Tests the following enhancements:
1. Config Duplication Fix - BaseAgentConfig.from_domain_config()
2. Convenience Methods - write_to_memory(), extract_*()
3. Auto-conversion of domain configs in BaseAgent.__init__

Author: Kaizen Framework Team
Created: 2025-10-03
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===================================================================
# Test Fixtures: Domain Configs
# ===================================================================


@dataclass
class SimpleWorkflowConfig:
    """Simple domain config with minimal fields."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"


@dataclass
class CompleteWorkflowConfig:
    """Complete domain config with all BaseAgentConfig fields."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    provider_config: Optional[Dict[str, Any]] = None
    signature_programming_enabled: bool = True
    optimization_enabled: bool = True
    monitoring_enabled: bool = False
    logging_enabled: bool = True
    performance_enabled: bool = True
    error_handling_enabled: bool = True
    batch_processing_enabled: bool = False
    memory_enabled: bool = False
    transparency_enabled: bool = False
    mcp_enabled: bool = False
    strategy_type: str = "single_shot"
    max_cycles: int = 5


@dataclass
class CustomWorkflowConfig:
    """Domain config with custom fields plus BaseAgentConfig fields."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.1

    # Custom domain-specific fields
    max_iterations: int = 3
    retrieval_strategy: str = "semantic"
    quality_threshold: float = 0.8


class UXTestSignature(Signature):
    """Test signature for agent testing."""

    input_field: str = InputField(desc="Test input")
    output_field: str = OutputField(desc="Test output")


# ===================================================================
# GAP 1: Config Duplication Fix
# ===================================================================


class TestConfigAutoExtraction:
    """Test BaseAgentConfig.from_domain_config() method."""

    def test_from_domain_config_simple(self):
        """Test extraction from simple domain config."""
        domain_config = SimpleWorkflowConfig()

        base_config = BaseAgentConfig.from_domain_config(domain_config)

        assert base_config.llm_provider == "mock"
        assert base_config.model == "gpt-3.5-turbo"
        assert base_config.temperature == 0.1  # Default value
        assert base_config.max_tokens is None  # Default value

    def test_from_domain_config_complete(self):
        """Test extraction from complete domain config."""
        domain_config = CompleteWorkflowConfig()

        base_config = BaseAgentConfig.from_domain_config(domain_config)

        # LLM provider config
        assert base_config.llm_provider == "openai"
        assert base_config.model == "gpt-4"
        assert base_config.temperature == 0.7
        assert base_config.max_tokens == 1000

        # Framework features
        assert base_config.signature_programming_enabled is True
        assert base_config.optimization_enabled is True
        assert base_config.monitoring_enabled is False

        # Agent behavior
        assert base_config.logging_enabled is True
        assert base_config.performance_enabled is True
        assert base_config.error_handling_enabled is True
        assert base_config.batch_processing_enabled is False

        # Advanced features
        assert base_config.memory_enabled is False
        assert base_config.transparency_enabled is False
        assert base_config.mcp_enabled is False

        # Strategy
        assert base_config.strategy_type == "single_shot"
        assert base_config.max_cycles == 5

    def test_from_domain_config_custom_fields_ignored(self):
        """Test that custom domain fields are safely ignored."""
        domain_config = CustomWorkflowConfig()

        base_config = BaseAgentConfig.from_domain_config(domain_config)

        # BaseAgentConfig fields extracted
        assert base_config.llm_provider == "mock"
        assert base_config.model == "gpt-3.5-turbo"
        assert base_config.temperature == 0.1

        # Custom fields not in BaseAgentConfig
        assert not hasattr(base_config, "max_iterations")
        assert not hasattr(base_config, "retrieval_strategy")
        assert not hasattr(base_config, "quality_threshold")

    def test_from_domain_config_partial_fields(self):
        """Test extraction when domain config has subset of fields."""

        @dataclass
        class PartialConfig:
            llm_provider: str = "anthropic"
            model: str = "claude-3-opus"
            # Missing other fields

        domain_config = PartialConfig()
        base_config = BaseAgentConfig.from_domain_config(domain_config)

        # Extracted fields
        assert base_config.llm_provider == "anthropic"
        assert base_config.model == "claude-3-opus"

        # Default values for missing fields
        assert base_config.temperature == 0.1
        assert base_config.max_tokens is None
        assert base_config.signature_programming_enabled is True


class TestBaseAgentAutoConversion:
    """Test BaseAgent automatic domain config conversion."""

    def test_baseagent_accepts_baseagentconfig(self):
        """Test that BaseAgent accepts BaseAgentConfig directly."""
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = BaseAgent(config=config, signature=UXTestSignature())

        assert isinstance(agent.config, BaseAgentConfig)
        assert agent.config.llm_provider == "mock"
        assert agent.config.model == "gpt-3.5-turbo"

    def test_baseagent_autoconverts_domain_config(self):
        """Test that BaseAgent auto-converts domain configs."""
        domain_config = SimpleWorkflowConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=domain_config, signature=UXTestSignature())

        # Should be auto-converted to BaseAgentConfig
        assert isinstance(agent.config, BaseAgentConfig)
        assert agent.config.llm_provider == "openai"
        assert agent.config.model == "gpt-4"

    def test_baseagent_autoconverts_custom_config(self):
        """Test auto-conversion of custom domain config."""
        domain_config = CustomWorkflowConfig()

        agent = BaseAgent(config=domain_config, signature=UXTestSignature())

        # Converted to BaseAgentConfig
        assert isinstance(agent.config, BaseAgentConfig)
        assert agent.config.llm_provider == "mock"
        assert agent.config.temperature == 0.1

        # Original domain config still accessible via closure
        # but agent uses BaseAgentConfig internally


# ===================================================================
# GAP 2: Verbose Shared Memory API
# ===================================================================


class TestWriteToMemoryConvenience:
    """Test write_to_memory() convenience method."""

    def test_write_to_memory_dict_content(self):
        """Test writing dict content to shared memory."""
        shared_pool = SharedMemoryPool()
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=shared_pool,
            agent_id="test_agent",
        )

        content = {"key": "value", "number": 42}
        agent.write_to_memory(
            content=content, tags=["test", "demo"], importance=0.9, segment="testing"
        )

        # Verify insight written
        insights = shared_pool.read_relevant(
            agent_id="test_agent",
            tags=["test"],
            segments=["testing"],
            exclude_own=False,  # Include own insights for testing
        )

        assert len(insights) == 1
        assert insights[0]["agent_id"] == "test_agent"
        assert json.loads(insights[0]["content"]) == content
        assert "test" in insights[0]["tags"]
        assert insights[0]["importance"] == 0.9
        assert insights[0]["segment"] == "testing"

    def test_write_to_memory_list_content(self):
        """Test writing list content to shared memory."""
        shared_pool = SharedMemoryPool()
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=shared_pool,
            agent_id="test_agent",
        )

        content = ["item1", "item2", "item3"]
        agent.write_to_memory(content=content, tags=["list"])

        insights = shared_pool.read_relevant(
            agent_id="test_agent", tags=["list"], exclude_own=False
        )
        assert len(insights) == 1
        assert json.loads(insights[0]["content"]) == content

    def test_write_to_memory_string_content(self):
        """Test writing string content to shared memory."""
        shared_pool = SharedMemoryPool()
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=shared_pool,
            agent_id="test_agent",
        )

        content = "Simple text message"
        agent.write_to_memory(content=content)

        insights = shared_pool.read_relevant(agent_id="test_agent", exclude_own=False)
        assert len(insights) == 1
        assert insights[0]["content"] == content

    def test_write_to_memory_no_shared_memory(self):
        """Test that write_to_memory is safe when no shared memory."""
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=None,  # No shared memory
        )

        # Should not raise error
        agent.write_to_memory(content={"test": "data"})

    def test_write_to_memory_defaults(self):
        """Test write_to_memory with default parameters."""
        shared_pool = SharedMemoryPool()
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=shared_pool,
            agent_id="test_agent",
        )

        agent.write_to_memory(content="test")

        insights = shared_pool.read_relevant(agent_id="test_agent", exclude_own=False)
        assert len(insights) == 1
        assert insights[0]["tags"] == []
        assert insights[0]["importance"] == 0.5
        assert insights[0]["segment"] == "execution"
        assert insights[0]["metadata"] == {}


# ===================================================================
# GAP 3: JSON Parsing Boilerplate
# ===================================================================


class TestExtractListMethod:
    """Test extract_list() convenience method."""

    def test_extract_list_from_list(self):
        """Test extracting when field is already a list."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"items": ["a", "b", "c"]}

        items = agent.extract_list(result, "items")

        assert items == ["a", "b", "c"]

    def test_extract_list_from_json_string(self):
        """Test extracting when field is JSON string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"items": '["a", "b", "c"]'}

        items = agent.extract_list(result, "items")

        assert items == ["a", "b", "c"]

    def test_extract_list_empty_string(self):
        """Test extracting from empty string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"items": ""}

        items = agent.extract_list(result, "items")

        assert items == []

    def test_extract_list_invalid_json(self):
        """Test extracting from invalid JSON string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"items": "not valid json"}

        items = agent.extract_list(result, "items", default=["default"])

        assert items == ["default"]

    def test_extract_list_missing_field(self):
        """Test extracting missing field."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {}

        items = agent.extract_list(result, "items", default=["missing"])

        assert items == ["missing"]

    def test_extract_list_wrong_type(self):
        """Test extracting when field is wrong type."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"items": 123}  # Not a list or JSON string

        items = agent.extract_list(result, "items")

        assert items == []


class TestExtractDictMethod:
    """Test extract_dict() convenience method."""

    def test_extract_dict_from_dict(self):
        """Test extracting when field is already a dict."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"config": {"key": "value"}}

        config = agent.extract_dict(result, "config")

        assert config == {"key": "value"}

    def test_extract_dict_from_json_string(self):
        """Test extracting when field is JSON string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"config": '{"key": "value"}'}

        config = agent.extract_dict(result, "config")

        assert config == {"key": "value"}

    def test_extract_dict_invalid_json(self):
        """Test extracting from invalid JSON."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"config": "invalid"}

        config = agent.extract_dict(result, "config", default={"default": "value"})

        assert config == {"default": "value"}

    def test_extract_dict_missing_field(self):
        """Test extracting missing field."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {}

        config = agent.extract_dict(result, "config")

        assert config == {}


class TestExtractFloatMethod:
    """Test extract_float() convenience method."""

    def test_extract_float_from_float(self):
        """Test extracting when field is already a float."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"score": 0.95}

        score = agent.extract_float(result, "score")

        assert score == 0.95

    def test_extract_float_from_int(self):
        """Test extracting when field is an int."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"score": 1}

        score = agent.extract_float(result, "score")

        assert score == 1.0

    def test_extract_float_from_string(self):
        """Test extracting when field is string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"score": "0.85"}

        score = agent.extract_float(result, "score")

        assert score == 0.85

    def test_extract_float_invalid_string(self):
        """Test extracting from invalid string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"score": "not a number"}

        score = agent.extract_float(result, "score", default=0.5)

        assert score == 0.5

    def test_extract_float_missing_field(self):
        """Test extracting missing field."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {}

        score = agent.extract_float(result, "score", default=0.0)

        assert score == 0.0


class TestExtractStrMethod:
    """Test extract_str() convenience method."""

    def test_extract_str_from_string(self):
        """Test extracting when field is already a string."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"message": "Hello World"}

        message = agent.extract_str(result, "message")

        assert message == "Hello World"

    def test_extract_str_from_number(self):
        """Test extracting when field is a number."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"message": 42}

        message = agent.extract_str(result, "message")

        assert message == "42"

    def test_extract_str_from_none(self):
        """Test extracting when field is None."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {"message": None}

        message = agent.extract_str(result, "message", default="default")

        assert message == "default"

    def test_extract_str_missing_field(self):
        """Test extracting missing field."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())
        result = {}

        message = agent.extract_str(result, "message", default="missing")

        assert message == "missing"


# ===================================================================
# Integration Tests: Real-World Usage
# ===================================================================


class TestRealWorldUsage:
    """Test UX improvements in realistic scenarios."""

    def test_agent_with_custom_config_simplified(self):
        """Test creating agent with custom config using new UX."""

        @dataclass
        class RAGConfig:
            llm_provider: str = "mock"
            model: str = "gpt-4"
            max_iterations: int = 3
            top_k: int = 5

        config = RAGConfig()

        # OLD WAY would require:
        # agent_config = BaseAgentConfig(
        #     llm_provider=config.llm_provider,
        #     model=config.model
        # )
        # agent = BaseAgent(config=agent_config, ...)

        # NEW WAY (simplified):
        agent = BaseAgent(config=config, signature=UXTestSignature())

        assert agent.config.llm_provider == "mock"
        assert agent.config.model == "gpt-4"

    def test_shared_memory_write_simplified(self):
        """Test writing to shared memory with new UX."""
        shared_pool = SharedMemoryPool()
        agent = BaseAgent(
            config=BaseAgentConfig(),
            signature=UXTestSignature(),
            shared_memory=shared_pool,
            agent_id="rag_agent",
        )

        result = {"documents": ["doc1", "doc2"], "scores": [0.9, 0.8]}

        # OLD WAY would require:
        # if self.shared_memory:
        #     self.shared_memory.write_insight({
        #         "agent_id": self.agent_id,
        #         "content": json.dumps(result),
        #         "tags": ["retrieval", "complete"],
        #         "importance": 0.9,
        #         "segment": "rag_pipeline"
        #     })

        # NEW WAY (simplified):
        agent.write_to_memory(
            content=result,
            tags=["retrieval", "complete"],
            importance=0.9,
            segment="rag_pipeline",
        )

        # Verify
        insights = shared_pool.read_relevant(agent_id="rag_agent", exclude_own=False)
        assert len(insights) == 1

    def test_result_parsing_simplified(self):
        """Test parsing agent results with new UX."""
        agent = BaseAgent(config=BaseAgentConfig(), signature=UXTestSignature())

        # Simulate LLM result with mixed types
        result = {
            "documents": '["doc1", "doc2", "doc3"]',  # JSON string
            "scores": [0.9, 0.85, 0.8],  # Already list
            "config": '{"top_k": 5}',  # JSON string
            "confidence": "0.95",  # String number
            "answer": "This is the answer",  # String
        }

        # OLD WAY would require 50+ lines of boilerplate

        # NEW WAY (simplified):
        documents = agent.extract_list(result, "documents")
        scores = agent.extract_list(result, "scores")
        config = agent.extract_dict(result, "config")
        confidence = agent.extract_float(result, "confidence")
        answer = agent.extract_str(result, "answer")

        assert documents == ["doc1", "doc2", "doc3"]
        assert scores == [0.9, 0.85, 0.8]
        assert config == {"top_k": 5}
        assert confidence == 0.95
        assert answer == "This is the answer"

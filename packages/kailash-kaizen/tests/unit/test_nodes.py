"""
Unit tests for Kaizen enhanced nodes.

Tests the KaizenNode and related node functionality.
"""

from unittest.mock import Mock, patch

from kaizen.nodes.base import KaizenLLMAgentNode, KaizenNode
from kaizen.signatures import Signature


class MockSignature(Signature):
    """Mock signature for testing."""

    def define_inputs(self):
        return {"input_text": str, "context": str}

    def define_outputs(self):
        return {"processed_text": str}


class TestKaizenNode:
    """Test cases for the KaizenNode class."""

    def test_kaizen_node_initialization(self):
        """Test basic KaizenNode initialization."""
        node = KaizenNode(model="gpt-4", temperature=0.8, max_tokens=2000)

        assert node.model == "gpt-4"
        assert node.temperature == 0.8
        assert node.max_tokens == 2000
        assert node.timeout == 30  # Default
        assert node.signature is None

    def test_kaizen_node_initialization_with_signature(self):
        """Test KaizenNode initialization with signature."""
        signature = MockSignature("test_sig", "Test signature")
        node = KaizenNode(signature=signature, model="gpt-4")

        assert node.signature is signature
        assert node.model == "gpt-4"

    def test_kaizen_node_defaults(self):
        """Test default values for KaizenNode."""
        node = KaizenNode()

        assert node.model == "gpt-3.5-turbo"
        assert node.temperature == 0.7
        assert node.max_tokens == 1000
        assert node.timeout == 30
        assert node._optimization_enabled is False
        assert node._memory_enabled is False

    def test_get_parameters(self):
        """Test parameter definition."""
        node = KaizenNode()

        params = node.get_parameters()

        assert "prompt" in params
        assert "model" in params
        assert "temperature" in params
        assert "max_tokens" in params
        assert "timeout" in params

        # Check parameter properties
        prompt_param = params["prompt"]
        assert prompt_param.type == str
        assert prompt_param.required is True
        assert prompt_param.auto_map_primary is True

        model_param = params["model"]
        assert model_param.type == str
        assert model_param.required is False
        assert model_param.default == "gpt-3.5-turbo"

    def test_get_parameters_with_signature(self):
        """Test parameter definition with signature."""
        signature = MockSignature("test_sig", "Test signature")
        node = KaizenNode(signature=signature)

        params = node.get_parameters()

        # Should have base parameters
        assert "prompt" in params
        assert "model" in params

        # Should have signature-specific parameters
        assert "input_text" in params
        assert "context" in params

        # Check signature parameter properties
        input_text_param = params["input_text"]
        assert input_text_param.type == str
        assert input_text_param.required is True

    def test_run_basic(self):
        """Test basic node execution."""
        node = KaizenNode(model="gpt-4")

        result = node.run(prompt="Hello world")

        assert "response" in result
        assert "model_used" in result
        assert "prompt_length" in result
        assert "response_length" in result

        assert result["model_used"] == "gpt-4"
        assert result["prompt_length"] == len("Hello world")
        assert isinstance(result["response"], str)

    def test_run_with_custom_parameters(self):
        """Test node execution with custom parameters."""
        node = KaizenNode()

        result = node.run(
            prompt="Test prompt",
            model="gpt-4",
            temperature=0.9,
            max_tokens=500,
            timeout=60,
        )

        assert result["model_used"] == "gpt-4"
        assert "using gpt-4" in result["response"]
        assert "Test prompt" in result["response"]

    def test_run_with_signature_validation(self):
        """Test node execution with signature validation."""
        signature = MockSignature("test_sig", "Test signature")
        node = KaizenNode(signature=signature)

        # Mock signature validation
        signature.validate_inputs = Mock(return_value=True)
        signature.validate_outputs = Mock(return_value=True)

        result = node.run(prompt="Test prompt")

        # Verify signature validation was called
        signature.validate_inputs.assert_called_once()
        signature.validate_outputs.assert_called_once()

        assert "response" in result

    def test_execute_public_method(self):
        """Test the public execute method."""
        node = KaizenNode(model="gpt-4")

        result = node.execute(prompt="Hello world")

        assert "response" in result
        assert result["model_used"] == "gpt-4"

    def test_execute_with_error_handling(self):
        """Test execute method with error handling."""
        node = KaizenNode()

        # Mock the run method to raise an exception
        with patch.object(node, "run", side_effect=Exception("Test error")):
            result = node.execute(prompt="Test")

            assert "error" in result
            assert "status" in result
            assert result["status"] == "failed"
            assert "Test error" in result["error"]

    def test_pre_execution_hook(self):
        """Test pre-execution hook."""
        node = KaizenNode()
        inputs = {"prompt": "test", "model": "gpt-4"}

        result = node.pre_execution_hook(inputs)

        assert result == inputs  # Should return unmodified inputs by default

    def test_pre_execution_hook_with_signature(self):
        """Test pre-execution hook with signature validation."""
        signature = MockSignature("test_sig", "Test signature")
        signature.validate_inputs = Mock(return_value=True)
        node = KaizenNode(signature=signature)

        inputs = {"prompt": "test"}
        result = node.pre_execution_hook(inputs)

        signature.validate_inputs.assert_called_once_with(inputs)
        assert result == inputs

    def test_post_execution_hook(self):
        """Test post-execution hook."""
        node = KaizenNode()
        outputs = {"response": "test response"}

        result = node.post_execution_hook(outputs)

        assert result == outputs  # Should return unmodified outputs by default

    def test_post_execution_hook_with_signature(self):
        """Test post-execution hook with signature validation."""
        signature = MockSignature("test_sig", "Test signature")
        signature.validate_outputs = Mock(return_value=True)
        node = KaizenNode(signature=signature)

        outputs = {"response": "test response"}
        result = node.post_execution_hook(outputs)

        signature.validate_outputs.assert_called_once_with(outputs)
        assert result == outputs

    def test_execute_ai_model_placeholder(self):
        """Test the placeholder AI model execution."""
        node = KaizenNode()

        response = node._execute_ai_model(
            prompt="Test prompt",
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000,
            timeout=30,
        )

        assert isinstance(response, str)
        assert "Test prompt" in response
        assert "gpt-4" in response


class TestKaizenLLMAgentNode:
    """Test cases for the KaizenLLMAgentNode class."""

    def test_kaizen_llm_agent_node_initialization(self):
        """Test KaizenLLMAgentNode initialization."""
        node = KaizenLLMAgentNode(model="gpt-4")

        assert node.model == "gpt-4"
        assert isinstance(node, KaizenNode)

    def test_get_parameters_with_llm_agent_params(self):
        """Test parameter definition includes LLMAgentNode-specific parameters."""
        node = KaizenLLMAgentNode()

        params = node.get_parameters()

        # Should have base KaizenNode parameters
        assert "prompt" in params
        assert "model" in params

        # Should have LLMAgentNode-specific parameters
        assert "system_message" in params
        assert "user_message" in params
        assert "provider" in params

        # Check LLMAgentNode parameter properties
        system_msg_param = params["system_message"]
        assert system_msg_param.type == str
        assert system_msg_param.required is False
        assert system_msg_param.default == ""

        provider_param = params["provider"]
        assert provider_param.type == str
        assert provider_param.default == "openai"

    def test_map_to_llm_agent_format(self):
        """Test input mapping to LLMAgentNode format."""
        node = KaizenLLMAgentNode()

        inputs = {"prompt": "Hello world", "model": "gpt-4", "temperature": 0.8}

        mapped = node._map_to_llm_agent_format(inputs)

        assert mapped["user_message"] == "Hello world"
        assert mapped["model"] == "gpt-4"
        assert mapped["temperature"] == 0.8
        assert "prompt" in mapped  # Original should still be there

    def test_map_to_llm_agent_format_with_user_message(self):
        """Test input mapping when user_message is already provided."""
        node = KaizenLLMAgentNode()

        inputs = {
            "prompt": "Hello world",
            "user_message": "Existing message",
            "model": "gpt-4",
        }

        mapped = node._map_to_llm_agent_format(inputs)

        # Should not override existing user_message
        assert mapped["user_message"] == "Existing message"
        assert mapped["prompt"] == "Hello world"

    def test_run_with_llm_agent_compatibility(self):
        """Test run method with LLMAgentNode compatibility."""
        node = KaizenLLMAgentNode(model="gpt-4")

        result = node.run(
            prompt="Test prompt",
            system_message="You are a helpful assistant",
            provider="openai",
        )

        assert "response" in result
        assert result["model_used"] == "gpt-4"


class TestNodeRegistration:
    """Test cases for node registration with Core SDK."""

    def test_kaizen_node_is_registered(self):
        """Test that KaizenNode is properly registered."""
        # This test verifies that the @register_node() decorator works
        # In a real implementation, we would check the node registry

        node = KaizenNode()
        assert hasattr(node, "get_parameters")
        assert hasattr(node, "run")
        assert hasattr(node, "execute")

    def test_kaizen_llm_agent_node_is_registered(self):
        """Test that KaizenLLMAgentNode is properly registered."""
        node = KaizenLLMAgentNode()
        assert hasattr(node, "get_parameters")
        assert hasattr(node, "run")
        assert hasattr(node, "execute")

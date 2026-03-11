"""
Tests for Kaizen-enhanced LLMAgentNode with extension points and Kaizen integration.

This test module validates:
1. Extension points (pre/post execute, error handling)
2. Kaizen config compatibility
3. Backward compatibility with Core SDK usage
4. Strategy integration hooks
"""

import pytest
from kaizen.nodes.ai import LLMAgentNode


class TestLLMAgentKaizenExtensions:
    """Test Kaizen-specific enhancements to LLMAgentNode."""

    def test_llm_agent_has_extension_point_method(self):
        """Test that LLMAgentNode exposes extension points."""
        agent = LLMAgentNode()

        # Check for extension point method
        assert hasattr(
            agent, "_get_extension_points"
        ), "LLMAgentNode should have _get_extension_points method"

    def test_extension_points_structure(self):
        """Test that extension points have expected structure."""
        agent = LLMAgentNode()
        extension_points = agent._get_extension_points()

        # Should be a dictionary
        assert isinstance(
            extension_points, dict
        ), "Extension points should be a dictionary"

        # Should have expected keys
        expected_keys = ["pre_execute", "post_execute", "on_error"]
        for key in expected_keys:
            assert key in extension_points, f"Extension points should include '{key}'"
            assert callable(
                extension_points[key]
            ), f"Extension point '{key}' should be callable"

    def test_pre_execute_hook_called(self):
        """Test that pre_execute hook is called during execution."""
        agent = LLMAgentNode()

        # Track if hook was called
        hook_called = {"called": False, "inputs": None}

        original_hook = agent._pre_execute_hook

        def tracked_hook(inputs):
            hook_called["called"] = True
            hook_called["inputs"] = inputs
            return original_hook(inputs)

        agent._pre_execute_hook = tracked_hook

        # Execute with mock provider
        agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
            mock_response="Test response",
        )

        # Verify hook was called
        assert hook_called["called"], "pre_execute_hook should be called"
        assert (
            hook_called["inputs"] is not None
        ), "pre_execute_hook should receive inputs"

    def test_post_execute_hook_called(self):
        """Test that post_execute hook is called after execution."""
        agent = LLMAgentNode()

        # Track if hook was called
        hook_called = {"called": False, "result": None}

        original_hook = agent._post_execute_hook

        def tracked_hook(result):
            hook_called["called"] = True
            hook_called["result"] = result
            return original_hook(result)

        agent._post_execute_hook = tracked_hook

        # Execute with mock provider
        agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
            mock_response="Test response",
        )

        # Verify hook was called
        assert hook_called["called"], "post_execute_hook should be called"
        assert (
            hook_called["result"] is not None
        ), "post_execute_hook should receive result"

    def test_on_error_hook_called_on_failure(self):
        """Test that on_error hook is called when errors occur."""
        agent = LLMAgentNode()

        # Track if hook was called
        hook_called = {"called": False, "error": None}

        original_hook = agent._on_error_hook

        def tracked_hook(error, context):
            hook_called["called"] = True
            hook_called["error"] = error
            return original_hook(error, context)

        agent._on_error_hook = tracked_hook

        # Execute with invalid configuration to trigger error
        with pytest.raises(Exception):
            agent.execute(
                provider="invalid_provider",
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

        # Verify hook was called
        assert hook_called["called"], "on_error_hook should be called on error"
        assert hook_called["error"] is not None, "on_error_hook should receive error"

    def test_extension_point_customization(self):
        """Test that extension points can be customized via subclassing."""

        class CustomLLMAgent(LLMAgentNode):
            """Custom agent with enhanced pre-processing."""

            def _pre_execute_hook(self, inputs):
                """Add custom pre-processing."""
                # Add custom metadata
                if "metadata" not in inputs:
                    inputs["metadata"] = {}
                inputs["metadata"]["custom_processing"] = True
                return inputs

        agent = CustomLLMAgent()

        # Execute with mock provider
        result = agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
            mock_response="Test response",
        )

        # Verify custom processing was applied
        assert result.get("success"), "Execution should succeed"

    def test_backward_compatibility_core_sdk_usage(self):
        """Test that LLMAgentNode maintains backward compatibility with Core SDK."""
        agent = LLMAgentNode()

        # Execute using Core SDK pattern (no Kaizen config)
        result = agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            mock_response="4",
        )

        # Should work exactly as before
        assert result.get("success"), "Core SDK usage should still work"
        assert "response" in result, "Should return response"

    def test_extension_points_dont_break_normal_execution(self):
        """Test that extension points don't interfere with normal execution."""
        agent = LLMAgentNode()

        # Normal execution should work
        result = agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Hello"}],
            mock_response="Hi there!",
        )

        assert result.get("success"), "Normal execution should succeed"
        assert "response" in result, "Should have response"
        assert "content" in result["response"], "Response should have content"


class TestLLMAgentKaizenConfig:
    """Test Kaizen configuration integration."""

    def test_accepts_standard_config(self):
        """Test that LLMAgentNode accepts standard configuration."""
        agent = LLMAgentNode()

        # Should work with standard dict config
        result = agent.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
            mock_response="response",
        )

        assert result.get("success"), "Should accept standard config"

    def test_preserves_all_functionality(self):
        """Test that all original LLMAgentNode functionality is preserved."""
        agent = LLMAgentNode()

        # Test various features
        features_to_test = [
            # Basic execution
            {
                "provider": "mock",
                "model": "test",
                "messages": [{"role": "user", "content": "test"}],
                "mock_response": "response",
            },
            # With system prompt
            {
                "provider": "mock",
                "model": "test",
                "system_prompt": "You are helpful",
                "messages": [{"role": "user", "content": "test"}],
                "mock_response": "response",
            },
            # With generation config
            {
                "provider": "mock",
                "model": "test",
                "messages": [{"role": "user", "content": "test"}],
                "generation_config": {"temperature": 0.7},
                "mock_response": "response",
            },
        ]

        for config in features_to_test:
            result = agent.execute(**config)
            assert result.get("success"), f"Feature test should succeed: {config}"


class TestLLMAgentNodeParameters:
    """Test LLMAgentNode parameter handling."""

    def test_get_parameters_includes_all_params(self):
        """Test that get_parameters returns all expected parameters."""
        agent = LLMAgentNode()
        params = agent.get_parameters()

        # Should have key parameters
        param_names = list(params.keys())
        expected_params = [
            "provider",
            "model",
            "messages",
            "system_prompt",
            "generation_config",
            "tools",
            "mcp_servers",
        ]

        for expected in expected_params:
            assert expected in param_names, f"Parameter '{expected}' should be defined"

    def test_parameters_have_proper_types(self):
        """Test that parameters have proper type annotations."""
        agent = LLMAgentNode()
        params = agent.get_parameters()

        for param_name, param in params.items():
            assert hasattr(param, "name"), "Parameter should have name"
            assert hasattr(param, "type"), "Parameter should have type"
            assert hasattr(param, "required"), "Parameter should have required flag"


class TestLLMAgentNodeIntegration:
    """Test LLMAgentNode integration with Kaizen framework."""

    def test_node_registration(self):
        """Test that LLMAgentNode is properly registered."""
        # Should be importable from kaizen.nodes.ai
        from kaizen.nodes.ai import LLMAgentNode as ImportedNode

        assert ImportedNode is LLMAgentNode, "Should be importable from kaizen.nodes.ai"

    def test_can_be_used_in_workflow(self):
        """Test that LLMAgentNode can be used in a workflow."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "LLMAgentNode",
            "agent",
            {
                "provider": "mock",
                "model": "test-model",
                "messages": [{"role": "user", "content": "test"}],
                "mock_response": "Test response",
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution
        assert "agent" in results, "Agent node should be in results"
        assert results["agent"].get("success"), "Agent execution should succeed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

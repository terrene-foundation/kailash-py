"""
Comprehensive Signature Programming Tests - Consolidated from 3 overlapping files.

This file replaces and consolidates:
- test_signature_programming.py (285 lines, signature parsing/compilation)
- test_real_signature_programming.py (198 lines, real component testing)
- test_signature_system_fixes.py (156 lines, specific bug fixes)

Eliminated overlaps:
- 8+ duplicated signature parsing tests
- 6+ duplicated signature compilation tests
- 10+ duplicated framework integration tests
- 5+ duplicated performance validation tests
- 4+ duplicated error handling tests

Signature Programming Requirements:
- Signature compilation: <50ms for complex signatures
- Signature validation: <10ms for type checking
- Memory usage: <10MB additional overhead
- Framework initialization: <100ms with signature system

Tier 1 Requirements:
- Performance: <1 second per test, no external dependencies
- NO MOCKING of Core SDK components
- Real functionality testing with proper error handling
"""

import pytest

from kaizen.core.config import KaizenConfig
from kaizen.core.framework import Kaizen
from kaizen.signatures import Signature
from kaizen.signatures.core import (
    Signature,
    SignatureCompiler,
    SignatureParser,
    SignatureValidator,
)

# Import standardized test fixtures
from tests.fixtures.consolidated_test_fixtures import consolidated_fixtures


class TestSignatureParsingFunctionality:
    """Comprehensive signature parsing tests - consolidated from 3 files."""

    def test_parse_basic_signature(self, performance_tracker):
        """Test parsing basic 'input -> output' signatures."""
        performance_tracker.start_timer("basic_signature_parse")

        parser = SignatureParser()
        signature_text = "question -> answer"

        result = parser.parse(signature_text)
        performance_tracker.end_timer("basic_signature_parse")

        # Validate parsing results
        assert result.inputs == ["question"]
        assert result.outputs == ["answer"]
        assert result.is_valid is True
        assert result.signature_type == "basic"

        # Performance validation
        performance_tracker.assert_performance("basic_signature_parse", 10.0)  # <10ms

    def test_parse_multi_input_signature(self, performance_tracker):
        """Test parsing multi-input signatures."""
        performance_tracker.start_timer("multi_input_parse")

        parser = SignatureParser()
        signature_text = "context, question -> reasoning, answer"

        result = parser.parse(signature_text)
        performance_tracker.end_timer("multi_input_parse")

        # Validate parsing results
        assert result.inputs == ["context", "question"]
        assert result.outputs == ["reasoning", "answer"]
        assert result.is_valid is True
        assert result.signature_type == "basic"

        # Performance validation
        performance_tracker.assert_performance("multi_input_parse", 10.0)

    def test_parse_complex_multimodal_signature(self, performance_tracker):
        """Test parsing complex multi-modal signatures."""
        parser = SignatureParser()
        signature_text = "context, question, image, audio -> visual_analysis, audio_transcription, reasoning, answer, confidence"

        performance_tracker.start_timer("complex_signature_parse")
        result = parser.parse(signature_text)
        performance_tracker.end_timer("complex_signature_parse")

        # Validate complex parsing
        assert len(result.inputs) == 4
        assert len(result.outputs) == 5
        assert "image" in result.inputs
        assert "audio" in result.inputs
        assert "visual_analysis" in result.outputs
        assert "audio_transcription" in result.outputs
        assert result.is_valid is True

        # Complex parsing should still be fast
        performance_tracker.assert_performance("complex_signature_parse", 20.0)  # <20ms

    def test_parse_invalid_signature_syntax(self):
        """Test parsing invalid signature syntax returns proper errors."""
        parser = SignatureParser()

        invalid_signatures = [
            "invalid -> -> syntax",  # Double arrow
            "no_arrow_here",  # No arrow
            "-> missing_input",  # Missing input
            "missing_output ->",  # Missing output
            "",  # Empty string
        ]

        for invalid_sig in invalid_signatures:
            with pytest.raises(ValueError, match="Invalid signature"):
                parser.parse(invalid_sig)

    def test_parse_list_outputs_signature(self):
        """Test parsing signatures with list outputs."""
        parser = SignatureParser()
        signature_text = "topic -> [analysis1, analysis2], summary"

        result = parser.parse(signature_text)

        assert result.inputs == ["topic"]
        assert "analysis1" in result.outputs
        assert "analysis2" in result.outputs
        assert "summary" in result.outputs
        assert result.is_valid is True


class TestSignatureCompilationFunctionality:
    """Comprehensive signature compilation tests - consolidated from 3 files."""

    def test_signature_compilation_to_workflow_params(self, performance_tracker):
        """Test signature compilation to workflow parameters."""
        parser = SignatureParser()
        parse_result = parser.parse("question -> answer, confidence")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )

        compiler = SignatureCompiler()

        performance_tracker.start_timer("signature_compilation")
        workflow_params = compiler.compile_to_workflow_params(signature)
        compilation_time = performance_tracker.end_timer("signature_compilation")

        # Verify compilation result structure
        assert "node_type" in workflow_params
        assert "parameters" in workflow_params
        assert workflow_params["node_type"] == "LLMAgentNode"

        # Verify signature parameters are included
        params = workflow_params["parameters"]
        assert "inputs" in params
        assert "outputs" in params
        assert params["inputs"] == ["question"]
        assert set(params["outputs"]) == {"answer", "confidence"}

        # Performance validation
        performance_tracker.assert_performance("signature_compilation", 50)
        assert (
            compilation_time < 50
        ), f"Signature compilation took {compilation_time:.2f}ms, expected <50ms"

    def test_complex_signature_compilation_performance(self, performance_tracker):
        """Test complex signature compilation maintains performance."""
        parser = SignatureParser()
        parse_result = parser.parse(
            "context, question, image -> reasoning, visual_analysis, answer, confidence"
        )
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            supports_multi_modal=True,
        )

        compiler = SignatureCompiler()

        performance_tracker.start_timer("complex_signature_compilation")
        workflow_params = compiler.compile_to_workflow_params(signature)
        compilation_time = performance_tracker.end_timer(
            "complex_signature_compilation"
        )

        # Verify compilation result
        assert "node_type" in workflow_params
        assert "parameters" in workflow_params

        # Complex signatures may take longer but should still be reasonable
        assert (
            compilation_time < 100
        ), f"Complex signature compilation took {compilation_time:.2f}ms, expected <100ms"


class TestKaizenFrameworkIntegration:
    """Comprehensive framework integration tests - consolidated from 3 files."""

    def test_kaizen_create_signature_functionality(self):
        """Test kaizen.create_signature() works correctly."""
        kaizen = Kaizen()

        # This should work: kaizen.create_signature("question -> answer")
        signature = kaizen.create_signature("question -> answer")
        assert signature is not None
        assert hasattr(signature, "inputs")
        assert hasattr(signature, "outputs")
        assert signature.inputs == ["question"]
        assert signature.outputs == ["answer"]

    def test_agent_with_signature_creation(self):
        """Test creating agent with signature using kaizen.create_signature()."""
        kaizen = Kaizen()

        # Create signature
        signature = kaizen.create_signature("question -> answer")

        # Create agent with signature
        agent = kaizen.create_agent(
            "qa_agent", {"model": "gpt-4", "signature": signature}
        )

        # Agent should have signature
        assert agent.has_signature is True
        assert agent.signature is not None
        assert agent.signature.inputs == ["question"]
        assert agent.signature.outputs == ["answer"]

    def test_agent_signature_string_integration(self):
        """Test agent creation with string signature."""
        kaizen = Kaizen()

        # Create agent with string signature
        agent = kaizen.create_agent(
            "qa_agent", {"model": "gpt-4", "signature": "question -> answer"}
        )

        # Agent should have parsed signature
        assert agent.has_signature is True
        assert agent.signature is not None
        assert agent.signature.inputs == ["question"]
        assert agent.signature.outputs == ["answer"]

    def test_framework_initialization_with_signature_system(self, performance_tracker):
        """Test framework initialization with signature system enabled."""
        config = consolidated_fixtures.get_configuration("minimal")
        config["signature_programming_enabled"] = True

        performance_tracker.start_timer("framework_init_with_signatures")
        kaizen = Kaizen(config=KaizenConfig(**config))
        initialization_time = performance_tracker.end_timer(
            "framework_init_with_signatures"
        )

        # Verify signature system is enabled
        assert kaizen.config.signature_programming_enabled is True
        assert hasattr(kaizen, "create_signature")

        # Performance requirement
        assert (
            initialization_time < 100
        ), f"Framework init with signatures took {initialization_time:.1f}ms, expected <100ms"


class TestSignatureSystemBugFixes:
    """Comprehensive bug fix tests - consolidated from 3 files."""

    def test_has_signature_property_behavior(self):
        """Test that has_signature property works correctly and is NOT callable."""
        kaizen = Kaizen()

        # Test agent without signature
        agent_no_sig = kaizen.create_agent("test", {"model": "gpt-4"})

        # Property should return boolean
        assert isinstance(agent_no_sig.has_signature, bool)
        assert agent_no_sig.has_signature is False

        # Property should NOT be callable - this should raise TypeError
        with pytest.raises(TypeError, match="'bool' object is not callable"):
            agent_no_sig.has_signature()

    def test_agent_compile_to_workflow_without_signature(self):
        """Test compile_to_workflow() fails correctly when agent has no signature."""
        kaizen = Kaizen()
        agent = kaizen.create_agent("test", {"model": "gpt-4"})

        # Should fail with clear error message
        with pytest.raises(
            ValueError, match="does not have a signature for workflow compilation"
        ):
            agent.compile_to_workflow()

    def test_agent_compile_to_workflow_with_signature(self):
        """Test compile_to_workflow() works when agent has signature."""
        kaizen = Kaizen()

        # Create signature
        signature = kaizen.create_signature("question -> answer")

        # Create agent with signature
        agent = kaizen.create_agent(
            "qa_agent", {"model": "gpt-4", "signature": signature}
        )

        # Should work and return workflow
        workflow = agent.compile_to_workflow()
        assert workflow is not None
        assert hasattr(workflow, "nodes")
        assert len(workflow.nodes) > 0

    def test_signature_validation_edge_cases(self):
        """Test signature validation handles edge cases correctly."""
        parser = SignatureParser()

        # Test empty inputs/outputs
        with pytest.raises(ValueError, match="Invalid signature"):
            parser.parse(" -> answer")

        with pytest.raises(ValueError, match="Invalid signature"):
            parser.parse("question -> ")

        # Test whitespace handling
        result = parser.parse(" question , context  ->  answer , confidence ")
        assert result.inputs == ["question", "context"]
        assert result.outputs == ["answer", "confidence"]


class TestSignaturePerformanceValidation:
    """Comprehensive performance validation tests - consolidated from 3 files."""

    def test_signature_validation_performance(self, performance_tracker):
        """Test that signature validation is fast (<10ms)."""
        parser = SignatureParser()
        parse_result = parser.parse(
            "context, question, image, audio -> visual_analysis, audio_transcription, reasoning, answer, confidence"
        )
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            supports_multi_modal=True,
            requires_privacy_check=True,
            requires_audit_trail=True,
        )

        validator = SignatureValidator()

        performance_tracker.start_timer("signature_validation")
        validation_result = validator.validate(signature)
        validation_time = performance_tracker.end_timer("signature_validation")

        assert validation_result.is_valid is True

        # Verify validation performance requirement
        performance_tracker.assert_performance("signature_validation", 10)
        assert (
            validation_time < 10
        ), f"Signature validation took {validation_time:.2f}ms, expected <10ms"

    def test_memory_usage_during_signature_operations(self):
        """Test memory overhead during signature operations is minimal."""
        try:
            import os

            import psutil
        except ImportError:
            pytest.skip("psutil not available for memory testing")

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Perform multiple signature operations
        kaizen = Kaizen()
        signatures = []

        for i in range(10):
            signature = kaizen.create_signature(f"input_{i} -> output_{i}")
            signatures.append(signature)

            kaizen.create_agent(
                f"agent_{i}", {"model": "gpt-4", "signature": signature}
            )

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Memory overhead should be reasonable
        assert (
            memory_increase < 10
        ), f"Memory overhead {memory_increase:.1f}MB exceeds 10MB limit"

    def test_signature_system_integration_performance(self, performance_tracker):
        """Test end-to-end signature system performance."""
        config = consolidated_fixtures.get_configuration("minimal")
        config["signature_programming_enabled"] = True

        performance_tracker.start_timer("end_to_end_signature")

        # Full signature workflow
        kaizen = Kaizen(config=KaizenConfig(**config))
        signature = kaizen.create_signature("question -> answer, confidence")
        agent = kaizen.create_agent(
            "qa_agent", {"model": "gpt-4", "signature": signature}
        )
        workflow = agent.compile_to_workflow()

        total_time = performance_tracker.end_timer("end_to_end_signature")

        # Verify all components are working
        assert signature is not None
        assert agent.has_signature is True
        assert workflow is not None

        # End-to-end should be reasonably fast
        assert (
            total_time < 200
        ), f"End-to-end signature workflow took {total_time:.1f}ms, expected <200ms"

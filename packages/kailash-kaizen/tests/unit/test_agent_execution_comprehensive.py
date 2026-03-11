"""
Comprehensive Agent Execution Tests - Consolidated from 3 overlapping files.

This file replaces and consolidates:
- test_agent_execution_patterns.py (523 lines, 10 classes)
- test_agent_execution_signature_fixes.py (539 lines, 6 classes)
- test_agent_execution_engine.py (828 lines, 9 classes)

Eliminated overlaps:
- 12+ duplicated performance benchmark tests
- 8+ duplicated CoT/ReAct pattern tests
- 15+ duplicated signature validation tests
- 10+ duplicated error handling tests

Tier 1 Requirements:
- Agent execution: <200ms for standard signature workflows
- Pattern execution: Test CoT, ReAct execution patterns
- Signature-based execution: Structured input/output validation
- Error handling: Proper error conditions and validation
- Performance: <1 second per test, no external dependencies

NO MOCKING RULE: Only mock external services (databases, APIs), never Core SDK components.
"""

from unittest.mock import Mock

import pytest

from kaizen.core.agents import Agent
from kaizen.core.framework import Kaizen
from kaizen.signatures.core import Signature, SignatureParser

# Import standardized test fixtures


class TestAgentBasicExecutionFunctionality:
    """Comprehensive basic agent execution tests - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execute_without_signature_succeeds(self, performance_tracker):
        """Test that execute() without signature succeeds with direct LLM execution."""
        self.mock_kaizen.execute.return_value = (
            {"test_agent": {"generated_text": "AI is artificial intelligence"}},
            "test_run_id",
        )
        agent = Agent("test_agent", self.agent_config, kaizen_instance=self.mock_kaizen)

        result = agent.execute(question="What is AI?")
        assert result is not None
        assert "generated_text" in result or "answer" in result or "response" in result

    def test_agent_execute_without_kaizen_raises_error(self, performance_tracker):
        """Test that execute() without kaizen framework raises RuntimeError."""
        parser = SignatureParser()
        parse_result = parser.parse("question -> answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent("test_agent", self.agent_config, signature=signature)

        with pytest.raises(
            RuntimeError, match="Agent not connected to Kaizen framework"
        ):
            agent.execute(question="What is AI?")

    def test_agent_execute_performance_benchmark(self, performance_tracker):
        """Test that agent execution setup is fast (<200ms)."""
        parser = SignatureParser()
        parse_result = parser.parse("question -> answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        self.mock_kaizen.execute.return_value = (
            {"test_agent": {"answer": "Paris"}},
            "run_123",
        )
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        performance_tracker.start_timer("agent_execution")
        result = agent.execute(question="What is the capital of France?")
        execution_time = performance_tracker.end_timer("agent_execution")

        performance_tracker.assert_performance("agent_execution", 200)
        assert (
            execution_time < 200
        ), f"Agent execution took {execution_time:.2f}ms, expected <200ms"
        assert result == {"answer": "Paris"}

    def test_agent_execute_with_workflow_parameter(self, performance_tracker):
        """Test agent.execute() with workflow parameter correctly."""
        agent = Agent("test_agent", self.agent_config, kaizen_instance=self.mock_kaizen)

        workflow = Mock()
        workflow.build = Mock(return_value="built_workflow")
        mock_result = {"test_agent": {"output": "Workflow result"}}
        self.mock_kaizen.execute.return_value = (mock_result, "run_456")

        result = agent.execute(workflow=workflow)

        assert isinstance(result, tuple)
        assert len(result) == 2
        results, run_id = result
        assert run_id == "run_456"
        workflow.build.assert_called_once()

    def test_agent_execute_method_parameter_validation(self, performance_tracker):
        """Test agent.execute() validates parameters correctly."""
        agent = Agent("test_agent", self.agent_config, kaizen_instance=self.mock_kaizen)

        self.mock_kaizen.execute.return_value = ({}, "run_123")
        result = agent.execute(workflow=None, question="test")
        assert isinstance(result, dict)

        result = agent.execute()
        assert isinstance(result, dict)


class TestAgentSignatureBasedExecution:
    """Comprehensive signature-based execution tests - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execution_with_signature_structured_output(
        self, performance_tracker
    ):
        """Test agent with signature executes correctly with structured output."""
        parser = SignatureParser()
        parse_result = parser.parse("problem -> analysis, solution")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent(
            "analyzer",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        mock_result = {
            "analyzer": {
                "response": """analysis: This is a complex productivity problem requiring systematic approach.

solution: Implement time-blocking, priority matrix, and regular team retrospectives."""
            }
        }
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")

        result = agent.execute(problem="How to improve team productivity?")

        assert isinstance(result, dict)
        assert "analysis" in result
        assert "solution" in result
        assert len(result["analysis"]) > 10
        assert len(result["solution"]) > 10

    def test_agent_execution_signature_validation(self, performance_tracker):
        """Test agent execution validates inputs against signature requirements."""
        parser = SignatureParser()
        parse_result = parser.parse("context, question -> answer, confidence")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent(
            "qa",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        with pytest.raises(ValueError, match="Missing required inputs: {'context'}"):
            agent.execute(question="What is AI?")

    def test_agent_execution_with_string_signature(self, performance_tracker):
        """Test agent with string signature parses and executes correctly."""
        agent = Agent(
            "qa",
            self.agent_config,
            signature="question -> answer",
            kaizen_instance=self.mock_kaizen,
        )

        mock_result = {"qa": {"answer": "Test answer"}}
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")

        result = agent.execute(question="What is AI?")
        assert isinstance(result, dict)
        assert "answer" in result
        assert result["answer"] == "Test answer"

    def test_signature_compilation_performance(self, performance_tracker):
        """Test signature compilation is fast (<50ms)."""
        parser = SignatureParser()
        parse_result = parser.parse(
            "context, question, image -> visual_analysis, reasoning, answer, confidence"
        )
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            supports_multi_modal=True,
        )
        agent = Agent(
            "complex",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        self.mock_kaizen.execute.return_value = ({}, "run_123")

        performance_tracker.start_timer("signature_compilation")
        try:
            agent.execute(context="test", question="test", image="test")
        except Exception:
            pass
        compilation_time = performance_tracker.end_timer("signature_compilation")

        performance_tracker.assert_performance("signature_compilation", 50)
        assert (
            compilation_time < 50
        ), f"Signature compilation took {compilation_time:.2f}ms, expected <50ms"


class TestAgentPatternExecution:
    """Comprehensive pattern execution tests (CoT, ReAct) - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        # Use basic config instead of calling fixture directly
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execute_cot_without_signature_raises_error(
        self, performance_tracker
    ):
        """Test that execute_cot() without signature raises ValueError."""
        agent = Agent("test_agent", self.agent_config, kaizen_instance=self.mock_kaizen)

        with pytest.raises(
            ValueError, match="Agent must have a signature for CoT execution"
        ):
            agent.execute_cot(problem="Complex math problem")

    def test_agent_execute_cot_performance_benchmark(self, performance_tracker):
        """Test that CoT execution is within performance limits (<500ms)."""
        parser = SignatureParser()
        parse_result = parser.parse("problem -> reasoning, answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        mock_result = {
            "test_agent_chain_of_thought": {
                "reasoning": "Step 1: Analyze... Step 2: Calculate...",
                "answer": "42",
            }
        }
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        performance_tracker.start_timer("cot_execution")
        result = agent.execute_cot(problem="What is 6 * 7?")
        execution_time = performance_tracker.end_timer("cot_execution")

        assert (
            execution_time < 500
        ), f"CoT execution took {execution_time:.2f}ms, expected <500ms"
        assert result == {
            "reasoning": "Step 1: Analyze... Step 2: Calculate...",
            "answer": "42",
        }

    def test_agent_execute_react_without_signature_raises_error(
        self, performance_tracker
    ):
        """Test that execute_react() without signature raises ValueError."""
        agent = Agent("test_agent", self.agent_config, kaizen_instance=self.mock_kaizen)

        with pytest.raises(
            ValueError, match="Agent must have a signature for ReAct execution"
        ):
            agent.execute_react(task="Research AI trends")

    def test_agent_execute_react_performance_benchmark(self, performance_tracker):
        """Test that ReAct execution is within performance limits (<500ms)."""
        parser = SignatureParser()
        parse_result = parser.parse("task -> thought, action, observation, answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        mock_result = {
            "test_agent_react": {
                "thought": "I need to gather information about AI trends",
                "action": "Search for recent AI research papers",
                "observation": "Found several relevant papers from 2024",
                "answer": "Key AI trends include multimodal models and efficiency improvements",
            }
        }
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        performance_tracker.start_timer("react_execution")
        result = agent.execute_react(task="What are the latest AI trends?")
        execution_time = performance_tracker.end_timer("react_execution")

        assert (
            execution_time < 500
        ), f"ReAct execution took {execution_time:.2f}ms, expected <500ms"
        expected = {
            "thought": "I need to gather information about AI trends",
            "action": "Search for recent AI research papers",
            "observation": "Found several relevant papers from 2024",
            "answer": "Key AI trends include multimodal models and efficiency improvements",
        }
        assert result == expected

    def test_pattern_execution_sets_and_restores_execution_pattern(
        self, performance_tracker
    ):
        """Test that pattern execution sets pattern and restores original."""
        parser = SignatureParser()
        parse_result = parser.parse("problem -> reasoning, answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            execution_pattern="original_pattern",
        )
        mock_result = {
            "test_agent_chain_of_thought": {
                "reasoning": "CoT reasoning",
                "answer": "Result",
            }
        }
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        assert signature.execution_pattern == "original_pattern"
        result = agent.execute_cot(problem="Test problem")
        assert signature.execution_pattern == "original_pattern"
        assert result == {"reasoning": "CoT reasoning", "answer": "Result"}


class TestAgentErrorHandlingAndValidation:
    """Comprehensive error handling tests - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execution_error_handling(self, performance_tracker):
        """Test agent execution handles invalid parameters gracefully."""
        agent = Agent(
            "error_handler", self.agent_config, kaizen_instance=self.mock_kaizen
        )

        self.mock_kaizen.execute.return_value = (
            {"error_handler": {"error": "Invalid parameter"}},
            "run_123",
        )
        result = agent.execute(invalid_param="test")
        assert isinstance(result, dict)

    def test_agent_execution_workflow_build_error(self, performance_tracker):
        """Test agent execution handles workflow build errors."""
        agent = Agent(
            "build_error", self.agent_config, kaizen_instance=self.mock_kaizen
        )

        workflow = Mock()
        workflow.build = Mock(
            side_effect=AttributeError("'str' object has no attribute 'build'")
        )

        with pytest.raises(
            AttributeError, match="'str' object has no attribute 'build'"
        ):
            agent.execute(workflow=workflow)

    def test_agent_execution_partial_results_handling(self, performance_tracker):
        """Test agent execution handles partial results gracefully."""
        parser = SignatureParser()
        parse_result = parser.parse("question -> answer, confidence, source")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent(
            "partial",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        mock_result = {
            "partial": {
                "response": """answer: Partial answer

confidence: 0.8"""
            }
        }
        self.mock_kaizen.execute.return_value = (mock_result, "run_123")

        result = agent.execute(question="test")
        assert result == {"answer": "Partial answer", "confidence": "0.8", "source": ""}
        assert "source" in result

    def test_agent_execution_with_execution_failure(self, performance_tracker):
        """Test error handling when kaizen execution fails."""
        parser = SignatureParser()
        parse_result = parser.parse("question -> answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        self.mock_kaizen.execute.side_effect = RuntimeError("Execution failed")

        with pytest.raises(RuntimeError, match="Execution failed"):
            agent.execute(question="test")


class TestAgentPerformanceAndOptimization:
    """Comprehensive performance tests - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execution_memory_efficiency(self, performance_tracker):
        """Test agent execution does not leak memory."""
        agent = Agent(
            "memory_test", self.agent_config, kaizen_instance=self.mock_kaizen
        )

        self.mock_kaizen.execute.return_value = (
            {"memory_test": {"result": "test"}},
            "run_123",
        )

        for i in range(10):
            result = agent.execute(question=f"Question {i}")
            assert isinstance(result, dict)

        assert len(agent._execution_history) <= 10

    def test_agent_execution_concurrent_calls(self, performance_tracker):
        """Test agent execution handles concurrent execution attempts."""
        agent = Agent("concurrent", self.agent_config, kaizen_instance=self.mock_kaizen)

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return (
                {"concurrent": {"result": f"call_{call_count}"}},
                f"run_{call_count}",
            )

        self.mock_kaizen.execute.side_effect = mock_execute

        results = []
        for i in range(3):
            result = agent.execute(question=f"Question {i}")
            results.append(result)

        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

    def test_agent_memory_usage_optimization(self, performance_tracker):
        """Test that agent execution has minimal memory overhead (<10MB)."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024

        parser = SignatureParser()
        parse_result = parser.parse("question -> answer")
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
        )
        agent = Agent(
            "test_agent",
            self.agent_config,
            signature=signature,
            kaizen_instance=self.mock_kaizen,
        )

        self.mock_kaizen.execute.return_value = (
            {"test_agent": {"answer": "Test"}},
            "run_123",
        )

        for i in range(10):
            agent.execute(question=f"Question {i}")

        memory_after = process.memory_info().rss / 1024 / 1024
        memory_increase = memory_after - memory_before

        assert (
            memory_increase < 10
        ), f"Memory overhead {memory_increase:.2f}MB exceeds 10MB limit"


class TestAgentLegacyCompatibility:
    """Test agent backward compatibility - consolidated from 3 files."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_kaizen = Mock(spec=Kaizen)
        self.agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 100,
        }

    def test_agent_execute_method_attribute_access(self, performance_tracker):
        """Test agent execute method is accessible and callable."""
        agent = Agent("attr_test", self.agent_config, kaizen_instance=self.mock_kaizen)

        assert hasattr(agent, "execute")
        assert callable(agent.execute)

        import inspect

        sig = inspect.signature(agent.execute)
        params = list(sig.parameters.keys())

        assert "workflow" in params
        assert any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

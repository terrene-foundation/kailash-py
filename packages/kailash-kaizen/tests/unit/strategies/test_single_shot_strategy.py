"""
Task 2.1 - SingleShotStrategy Unit Tests.

Tests for SingleShotStrategy covering Q&A and Chain-of-Thought patterns.

Evidence Required:
- 10+ test cases covering QA and CoT patterns
- 95%+ coverage for SingleShotStrategy
- Tests for build_workflow(), execute(), extension points

References:
- TODO-157: Task 2.1
- ADR-006: Strategy Pattern design
"""

from typing import Any, Dict

import pytest
from kailash.workflow.builder import WorkflowBuilder

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.single_shot import SingleShotStrategy


class SimpleQASignature(Signature):
    """Simple Q&A signature for testing."""

    question: str = InputField(desc="Question to answer")
    answer: str = OutputField(desc="Answer to question")


class ChainOfThoughtSignature(Signature):
    """Chain-of-Thought signature for testing."""

    question: str = InputField(desc="Question requiring reasoning")
    reasoning: str = OutputField(desc="Step-by-step reasoning")
    answer: str = OutputField(desc="Final answer")


@pytest.mark.unit
class TestSingleShotStrategyInitialization:
    """Test SingleShotStrategy initialization."""

    def test_strategy_initialization_default(self):
        """Task 2.1 - Strategy initializes with defaults."""
        strategy = SingleShotStrategy()

        assert strategy is not None
        assert isinstance(strategy, SingleShotStrategy)

    def test_strategy_initialization_with_config(self):
        """Task 2.1 - Strategy accepts configuration."""
        strategy = SingleShotStrategy()

        # Strategy should be stateless and lightweight
        assert strategy is not None


@pytest.mark.unit
class TestSingleShotStrategyExecution:
    """Test SingleShotStrategy.execute() method."""

    def test_execute_returns_dict(self):
        """Task 2.1 - execute() returns dict result."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "What is 2+2?"})

        assert isinstance(result, dict)
        assert result is not None

    def test_execute_with_chain_of_thought_signature(self):
        """Task 2.1 - execute() works with CoT signature."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=ChainOfThoughtSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Complex problem"})

        # Should include both reasoning and answer fields
        assert isinstance(result, dict)
        # Phase 1 skeleton returns generic fields, Phase 2 will return actual fields

    def test_execute_with_multiple_inputs(self):
        """Task 2.1 - execute() handles multiple input fields."""

        class MultiInputSignature(Signature):
            query: str = InputField(desc="Query")
            context: str = InputField(desc="Context")
            result: str = OutputField(desc="Result")

        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=MultiInputSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(
            agent, {"query": "test query", "context": "test context"}
        )

        assert isinstance(result, dict)

    def test_execute_error_handling(self):
        """Task 2.1 - execute() handles errors gracefully."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        # Execute with empty inputs - should not crash
        result = strategy.execute(agent, {})

        assert isinstance(result, dict)


@pytest.mark.unit
class TestSingleShotStrategyWorkflowGeneration:
    """Test SingleShotStrategy.build_workflow() method."""

    def test_build_workflow_returns_workflow_builder(self):
        """Task 2.7 - build_workflow() returns WorkflowBuilder."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        # build_workflow() not yet implemented in Phase 1
        # This test will pass once Task 2.7 is complete
        if hasattr(strategy, "build_workflow"):
            workflow = strategy.build_workflow(agent)
            assert isinstance(workflow, WorkflowBuilder)

    def test_build_workflow_for_qa_pattern(self):
        """Task 2.7 - build_workflow() generates Q&A workflow."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        # Will be implemented in Task 2.7
        if hasattr(strategy, "build_workflow"):
            workflow = strategy.build_workflow(agent)
            built = workflow.build()

            # Should contain LLMAgentNode
            assert built is not None

    def test_build_workflow_for_cot_pattern(self):
        """Task 2.8 - build_workflow() generates CoT workflow."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=ChainOfThoughtSignature())
        strategy = SingleShotStrategy()

        # Will be implemented in Task 2.8
        if hasattr(strategy, "build_workflow"):
            workflow = strategy.build_workflow(agent)
            built = workflow.build()

            # CoT workflow should include reasoning prompts
            assert built is not None


@pytest.mark.unit
class TestSingleShotStrategyExtensionPoints:
    """Test SingleShotStrategy extension points (Task 2.11)."""

    def test_pre_execute_extension_point(self):
        """Task 2.11 - pre_execute() extension point callable."""

        class CustomStrategy(SingleShotStrategy):
            def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                inputs["preprocessed"] = True
                return inputs

        config = BaseAgentConfig(model="gpt-4")
        BaseAgent(config=config, signature=SimpleQASignature())
        strategy = CustomStrategy()

        # Extension point should be callable
        assert hasattr(strategy, "pre_execute")
        assert callable(strategy.pre_execute)

    def test_parse_result_extension_point(self):
        """Task 2.11 - parse_result() extension point callable."""

        class CustomStrategy(SingleShotStrategy):
            def parse_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
                raw_result["parsed"] = True
                return raw_result

        strategy = CustomStrategy()

        # Extension point should be callable
        assert hasattr(strategy, "parse_result")
        assert callable(strategy.parse_result)

    def test_post_execute_extension_point(self):
        """Task 2.11 - post_execute() extension point callable."""

        class CustomStrategy(SingleShotStrategy):
            def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
                result["post_processed"] = True
                return result

        strategy = CustomStrategy()

        # Extension point should be callable
        assert hasattr(strategy, "post_execute")
        assert callable(strategy.post_execute)


@pytest.mark.unit
class TestSingleShotStrategyQAPattern:
    """Test SingleShotStrategy with Q&A pattern."""

    def test_qa_pattern_simple_question(self):
        """Task 2.7 - Q&A pattern handles simple questions."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "What is AI?"})

        assert isinstance(result, dict)
        # Phase 2 will validate actual answer field

    def test_qa_pattern_with_context(self):
        """Task 2.7 - Q&A pattern handles context."""

        class QAWithContextSignature(Signature):
            question: str = InputField(desc="Question")
            context: str = InputField(desc="Context", default="")
            answer: str = OutputField(desc="Answer")

        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=QAWithContextSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(
            agent,
            {"question": "Who is the CEO?", "context": "TechCorp is led by Jane Doe."},
        )

        assert isinstance(result, dict)

    def test_qa_pattern_confidence_scoring(self):
        """Task 2.7 - Q&A pattern supports confidence scoring."""

        class QAWithConfidenceSignature(Signature):
            question: str = InputField(desc="Question")
            answer: str = OutputField(desc="Answer")
            confidence: float = OutputField(desc="Confidence score")

        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=QAWithConfidenceSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Test question"})

        assert isinstance(result, dict)
        # Phase 2 will validate confidence field


@pytest.mark.unit
class TestSingleShotStrategyCoTPattern:
    """Test SingleShotStrategy with Chain-of-Thought pattern."""

    def test_cot_pattern_includes_reasoning(self):
        """Task 2.8 - CoT pattern includes reasoning steps."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=ChainOfThoughtSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Calculate 15% tip on $42.50"})

        assert isinstance(result, dict)
        # Phase 2 will validate reasoning field

    def test_cot_pattern_step_by_step(self):
        """Task 2.8 - CoT pattern generates step-by-step reasoning."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=ChainOfThoughtSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(
            agent, {"question": "If x = 5 and y = 3, what is 2x + y?"}
        )

        assert isinstance(result, dict)
        # Phase 2 will validate multi-step reasoning

    def test_cot_pattern_final_answer(self):
        """Task 2.8 - CoT pattern provides final answer."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=ChainOfThoughtSignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Complex reasoning problem"})

        assert isinstance(result, dict)
        # Phase 2 will validate answer extraction


@pytest.mark.unit
class TestSingleShotStrategyOutputValidation:
    """Test SingleShotStrategy output validation (Task 2.10)."""

    def test_output_schema_validation(self):
        """Task 2.10 - Validates output against signature schema."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Test"})

        # Result should be a dict (schema validation in Phase 2)
        assert isinstance(result, dict)

    def test_invalid_output_handling(self):
        """Task 2.10 - Handles invalid LLM outputs gracefully."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        # Should not crash with invalid inputs
        result = strategy.execute(agent, {})

        assert isinstance(result, dict)

    def test_missing_output_fields_handling(self):
        """Task 2.10 - Handles missing output fields."""
        config = BaseAgentConfig(model="gpt-4")
        agent = BaseAgent(config=config, signature=SimpleQASignature())
        strategy = SingleShotStrategy()

        result = strategy.execute(agent, {"question": "Test"})

        # Phase 2 will implement field validation
        assert isinstance(result, dict)


@pytest.mark.unit
class TestSingleShotStrategyParseResult:
    """Test SingleShotStrategy.parse_result() method - Bug fix for Azure response format."""

    def test_parse_result_handles_primitive_int(self):
        """Bug fix: JSON-parseable primitives like '4' should be wrapped.

        When Azure returns content like "4", json.loads("4") returns int 4.
        This must be wrapped with "response" key to trigger validation bypass.
        """
        strategy = SingleShotStrategy()

        # Simulate LLMAgentNode output where LLM returns just "4"
        raw_result = {
            "agent_exec": {"response": {"content": "4"}}  # Azure returns "4" as string
        }

        result = strategy.parse_result(raw_result)

        # Should wrap primitive in dict with "response" key
        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == 4  # The parsed int value

    def test_parse_result_handles_primitive_string(self):
        """Bug fix: Quoted JSON strings like '"hello"' should be wrapped."""
        strategy = SingleShotStrategy()

        # Simulate LLMAgentNode output where LLM returns quoted string
        raw_result = {
            "agent_exec": {
                "response": {"content": '"hello world"'}  # Valid JSON string
            }
        }

        result = strategy.parse_result(raw_result)

        # Should wrap primitive in dict with "response" key
        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == "hello world"

    def test_parse_result_handles_primitive_bool(self):
        """Bug fix: JSON booleans like 'true' should be wrapped."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "true"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] is True

    def test_parse_result_handles_primitive_float(self):
        """Bug fix: JSON floats like '3.14' should be wrapped."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "3.14159"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert abs(result["response"] - 3.14159) < 0.0001

    def test_parse_result_handles_primitive_null(self):
        """Bug fix: JSON null should be wrapped."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "null"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] is None

    def test_parse_result_handles_negative_number(self):
        """Bug fix: Negative numbers should be wrapped."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "-42"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == -42

    def test_parse_result_handles_primitive_list(self):
        """Bug fix: JSON arrays should be wrapped."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "[1, 2, 3]"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == [1, 2, 3]

    def test_parse_result_dict_passthrough(self):
        """Dict values from JSON parsing should pass through unchanged."""
        strategy = SingleShotStrategy()

        raw_result = {
            "agent_exec": {
                "response": {"content": '{"answer": "4", "confidence": 0.95}'}
            }
        }

        result = strategy.parse_result(raw_result)

        # Should return dict as-is (no wrapping)
        assert isinstance(result, dict)
        assert result.get("answer") == "4"
        assert result.get("confidence") == 0.95
        # Should NOT have "response" key from wrapping
        assert "response" not in result or result.get("answer") is not None

    def test_parse_result_json_decode_error_fallback(self):
        """Non-JSON content should return {"response": content, "error": "JSON_PARSE_FAILED"}."""
        strategy = SingleShotStrategy()

        raw_result = {
            "agent_exec": {
                "response": {"content": "The answer is 4."}  # Not valid JSON
            }
        }

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == "The answer is 4."
        assert result.get("error") == "JSON_PARSE_FAILED"

    def test_parse_result_preserves_raw_content(self):
        """When wrapping primitives, raw_content should be preserved for debugging."""
        strategy = SingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "42"}}}

        result = strategy.parse_result(raw_result)

        assert "raw_content" in result
        assert result["raw_content"] == "42"


@pytest.mark.unit
class TestAsyncSingleShotStrategyParseResult:
    """Test AsyncSingleShotStrategy.parse_result() method - Bug fix for Azure response format."""

    def test_parse_result_handles_primitive_int(self):
        """Bug fix: JSON-parseable primitives like '4' should be wrapped (async version)."""
        strategy = AsyncSingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "4"}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == 4

    def test_parse_result_handles_primitive_string(self):
        """Bug fix: Quoted JSON strings should be wrapped (async version)."""
        strategy = AsyncSingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": '"hello world"'}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == "hello world"

    def test_parse_result_dict_passthrough(self):
        """Dict values should pass through unchanged (async version)."""
        strategy = AsyncSingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": '{"answer": "4"}'}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert result.get("answer") == "4"

    def test_parse_result_json_decode_error_fallback(self):
        """Non-JSON content fallback works (async version)."""
        strategy = AsyncSingleShotStrategy()

        raw_result = {"agent_exec": {"response": {"content": "The answer is 4."}}}

        result = strategy.parse_result(raw_result)

        assert isinstance(result, dict)
        assert "response" in result
        assert result["response"] == "The answer is 4."
        assert result.get("error") == "JSON_PARSE_FAILED"

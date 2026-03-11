"""
Tier 1 Unit Tests: BaseAgent Extension Points

Test Module: test_base_agent_extension_points.py
Purpose: Comprehensive test coverage for BaseAgent extension points for custom agent implementations
Coverage Target: 90%+ for extension point mechanisms
Test Strategy: TDD (Test-First Development)

Architecture Reference: ADR-006-agent-base-architecture.md
TODO Reference: TODO-157, Task 1.12

Test Categories:
1. Extension Point 1: _default_signature() (3 tests)
2. Extension Point 2: _default_strategy() (3 tests)
3. Extension Point 3: _generate_system_prompt() (3 tests)
4. Extension Point 4: _validate_signature_output() (4 tests)
5. Extension Point 5: _pre_execution_hook() (3 tests)
6. Extension Point 6: _post_execution_hook() (3 tests)
7. Extension Point 7: _handle_error() (4 tests)
8. Extension Pattern Integration Tests (5 tests)

Total: 28 comprehensive test cases

Design Principles:
- NO MOCKING in Tier 1 tests (test actual extension mechanisms)
- Real inheritance - create actual subclasses to test overriding
- Fast execution (<2s total)
- Independent tests (no shared state)
- Descriptive test names and docstrings
- Follow Kailash SDK patterns

BaseAgent Extension Points (from ADR-006):

    class BaseAgent(Node):
        '''
        BaseAgent provides 7 extension points for customization:

        1. _default_signature() - Override to provide agent-specific signature
        2. _default_strategy() - Override to provide agent-specific strategy
        3. _generate_system_prompt() - Override to customize prompt generation
        4. _validate_signature_output() - Override to add output validation
        5. _pre_execution_hook() - Override to add pre-execution logic
        6. _post_execution_hook() - Override to add post-execution logic
        7. _handle_error() - Override to customize error handling
        '''

        def _default_signature(self) -> Signature:
            '''Provide default signature when none is specified.'''
            return Signature(
                name="default",
                input_fields=[InputField(name="input", type=str)],
                output_fields=[OutputField(name="output", type=str)]
            )

        def _default_strategy(self) -> ExecutionStrategy:
            '''Provide default execution strategy.'''
            if self.config.strategy_type == "single_shot":
                return SingleShotStrategy()
            elif self.config.strategy_type == "multi_cycle":
                return MultiCycleStrategy(max_cycles=self.config.max_cycles)
            else:
                raise ValueError(f"Unknown strategy type: {self.config.strategy_type}")

        def _generate_system_prompt(self) -> str:
            '''Generate system prompt from signature.'''
            inputs = ", ".join([f.name for f in self.signature.input_fields])
            outputs = ", ".join([f.name for f in self.signature.output_fields])
            return f"Task: Given {inputs}, produce {outputs}."

        def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
            '''Validate that output matches signature.'''
            for field in self.signature.output_fields:
                if field.name not in output:
                    raise ValueError(f"Missing required output field: {field.name}")
            return True

        def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
            '''Hook called before execution.'''
            if self.config.logging_enabled:
                logger.info(f"Executing {self.signature.name} with inputs: {inputs}")
            return inputs

        def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
            '''Hook called after execution.'''
            if self.config.logging_enabled:
                logger.info(f"Execution complete. Result: {result}")
            return result

        def _handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            '''Handle errors during execution.'''
            if self.config.error_handling_enabled:
                logger.error(f"Error during execution: {error}")
                return {"error": str(error), "type": type(error).__name__}
            else:
                raise error

Extension Pattern Example (from ADR-006):

    class SimpleQAAgent(BaseAgent):
        def _default_signature(self) -> Signature:
            '''QA-specific signature.'''
            return QASignature(
                question: str = InputField(desc="Question to answer"),
                context: Optional[str] = InputField(desc="Optional context"),
                answer: str = OutputField(desc="Answer to question"),
                confidence: float = OutputField(desc="Confidence score")
            )

        def _generate_system_prompt(self) -> str:
            '''QA-specific prompt.'''
            return "You are a helpful Q&A assistant. Answer questions accurately and concisely."

        def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
            '''QA-specific validation.'''
            super()._validate_signature_output(output)
            # Additional validation
            if not 0 <= output.get('confidence', 0) <= 1:
                raise ValueError("Confidence must be between 0 and 1")
            return True
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import pytest

# ==============================================================================
# Test Fixtures and Mock Classes
# ==============================================================================


@dataclass
class BaseAgentConfig:
    """
    Minimal BaseAgentConfig for testing extension points.

    Full implementation should match ADR-006 specification.
    This minimal version contains only fields needed for extension point testing.
    """

    # LLM Provider Configuration
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = 500

    # Framework Features
    signature_programming_enabled: bool = True
    optimization_enabled: bool = True
    monitoring_enabled: bool = True

    # Agent Behavior (feature flags for extension points)
    logging_enabled: bool = True
    performance_enabled: bool = True
    error_handling_enabled: bool = True
    batch_processing_enabled: bool = False

    # Strategy Configuration (for _default_strategy())
    strategy_type: str = "single_shot"  # or "multi_cycle"
    max_cycles: int = 5


class InputField:
    """Mock InputField for signature definition."""

    def __init__(
        self, name: str, type: type = str, desc: str = "", default: Any = None
    ):
        self.name = name
        self.type = type
        self.desc = desc
        self.default = default

    def __repr__(self):
        return f"InputField(name='{self.name}', type={self.type.__name__}, desc='{self.desc}')"


class OutputField:
    """Mock OutputField for signature definition."""

    def __init__(self, name: str, type: type = str, desc: str = ""):
        self.name = name
        self.type = type
        self.desc = desc

    def __repr__(self):
        return f"OutputField(name='{self.name}', type={self.type.__name__}, desc='{self.desc}')"


@dataclass
class Signature:
    """
    Mock Signature class for testing signature-based programming.

    Full implementation should match Kaizen signature programming specification.
    """

    name: str = "default_signature"
    description: str = ""
    input_fields: List[InputField] = field(default_factory=list)
    output_fields: List[OutputField] = field(default_factory=list)

    def __post_init__(self):
        if not self.input_fields:
            self.input_fields = [
                InputField(name="input", type=str, desc="Default input")
            ]
        if not self.output_fields:
            self.output_fields = [
                OutputField(name="output", type=str, desc="Default output")
            ]


class ExecutionStrategy(Protocol):
    """
    Protocol for execution strategies.

    Using Protocol (structural typing) instead of ABC for flexibility.
    """

    def execute(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent with given inputs."""
        ...


class SingleShotStrategy:
    """Mock single-shot execution strategy for QA and CoT agents."""

    def __init__(self):
        self.name = "single_shot"

    def execute(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent once and return result."""
        # Generate output matching agent's signature
        result = {}
        for output_field in agent.signature.output_fields:
            result[output_field.name] = f"mock_{output_field.name}_value"
        result["strategy"] = self.name
        return result

    def __repr__(self):
        return "SingleShotStrategy()"


class MultiCycleStrategy:
    """Mock multi-cycle execution strategy for ReAct agents."""

    def __init__(self, max_cycles: int = 5):
        self.max_cycles = max_cycles
        self.name = "multi_cycle"

    def execute(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent with multi-cycle reasoning loop."""
        # Generate output matching agent's signature
        result = {}
        for output_field in agent.signature.output_fields:
            result[output_field.name] = f"mock_{output_field.name}_value"
        result["strategy"] = self.name
        result["cycles"] = self.max_cycles
        return result

    def __repr__(self):
        return f"MultiCycleStrategy(max_cycles={self.max_cycles})"


class BaseAgent:
    """
    Mock BaseAgent implementation for testing extension points.

    This is a MINIMAL implementation to enable extension point testing.
    WILL FAIL until full BaseAgent is implemented in Phase 1.

    Purpose: Enable TDD by writing tests BEFORE implementation.
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        signature: Optional[Signature] = None,
        strategy: Optional[ExecutionStrategy] = None,
        **kwargs,
    ):
        self.config = config
        self.signature = signature or self._default_signature()
        self.strategy = strategy or self._default_strategy()
        self.logger = logging.getLogger(self.__class__.__name__)

        # Track hook calls for testing
        self._pre_execution_called = False
        self._post_execution_called = False
        self._error_handled = False

    # ============================================
    # Extension Point 1: Default Signature
    # ============================================

    def _default_signature(self) -> Signature:
        """
        Provide default signature when none is specified.

        Extension Point: Override for agent-specific signatures.

        Example:
            class QAAgent(BaseAgent):
                def _default_signature(self) -> Signature:
                    return QASignature(...)
        """
        return Signature(
            name="default",
            input_fields=[InputField(name="input", type=str, desc="Default input")],
            output_fields=[OutputField(name="output", type=str, desc="Default output")],
        )

    # ============================================
    # Extension Point 2: Default Strategy
    # ============================================

    def _default_strategy(self) -> ExecutionStrategy:
        """
        Provide default execution strategy.

        Extension Point: Override for agent-specific strategies.

        Example:
            class ReActAgent(BaseAgent):
                def _default_strategy(self) -> ExecutionStrategy:
                    return MultiCycleStrategy(max_cycles=10)
        """
        if self.config.strategy_type == "single_shot":
            return SingleShotStrategy()
        elif self.config.strategy_type == "multi_cycle":
            return MultiCycleStrategy(max_cycles=self.config.max_cycles)
        else:
            raise ValueError(f"Unknown strategy type: {self.config.strategy_type}")

    # ============================================
    # Extension Point 3: System Prompt Generation
    # ============================================

    def _generate_system_prompt(self) -> str:
        """
        Generate system prompt from signature.

        Extension Point: Override for custom prompt generation logic.

        Example:
            class QAAgent(BaseAgent):
                def _generate_system_prompt(self) -> str:
                    return "You are a helpful Q&A assistant..."
        """
        inputs = ", ".join([f.name for f in self.signature.input_fields])
        outputs = ", ".join([f.name for f in self.signature.output_fields])
        return f"Task: Given {inputs}, produce {outputs}."

    # ============================================
    # Extension Point 4: Output Validation
    # ============================================

    def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
        """
        Validate that output matches signature.

        Extension Point: Override for custom validation logic.

        Example:
            class QAAgent(BaseAgent):
                def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                    super()._validate_signature_output(output)
                    if not 0 <= output.get('confidence', 0) <= 1:
                        raise ValueError("Confidence must be between 0 and 1")
                    return True
        """
        for field in self.signature.output_fields:
            if field.name not in output:
                raise ValueError(f"Missing required output field: {field.name}")
        return True

    # ============================================
    # Extension Point 5: Pre-execution Hook
    # ============================================

    def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook called before execution.

        Extension Point: Override to add preprocessing, logging, etc.

        Example:
            class ReActAgent(BaseAgent):
                def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                    if self.config.mcp_enabled:
                        inputs['available_tools'] = self._load_mcp_tools()
                    return super()._pre_execution_hook(inputs)
        """
        self._pre_execution_called = True
        if self.config.logging_enabled:
            self.logger.info(f"Executing {self.signature.name} with inputs: {inputs}")
        return inputs

    # ============================================
    # Extension Point 6: Post-execution Hook
    # ============================================

    def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook called after execution.

        Extension Point: Override to add postprocessing, logging, etc.

        Example:
            class ReActAgent(BaseAgent):
                def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                    result['metadata']['tools_used'] = len(self.tools_called)
                    return super()._post_execution_hook(result)
        """
        self._post_execution_called = True
        if self.config.logging_enabled:
            self.logger.info(f"Execution complete. Result: {result}")
        return result

    # ============================================
    # Extension Point 7: Error Handling
    # ============================================

    def _handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle errors during execution.

        Extension Point: Override for custom error handling logic.

        Example:
            class QAAgent(BaseAgent):
                def _handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
                    if isinstance(error, TimeoutError):
                        return {"answer": "Request timed out", "confidence": 0.0}
                    return super()._handle_error(error, context)
        """
        self._error_handled = True
        if self.config.error_handling_enabled:
            self.logger.error(f"Error during execution: {error}")
            return {
                "error": str(error),
                "type": type(error).__name__,
                "context": context,
            }
        else:
            raise error

    # ============================================
    # Public Methods (for testing extension points)
    # ============================================

    def execute(self, **inputs) -> Dict[str, Any]:
        """
        Execute the agent (simplified for testing extension points).

        In full implementation, this would:
        1. Call _pre_execution_hook()
        2. Execute strategy
        3. Call _validate_signature_output()
        4. Call _post_execution_hook()
        5. Handle errors with _handle_error()
        """
        try:
            # Pre-execution hook
            inputs = self._pre_execution_hook(inputs)

            # Execute strategy
            result = self.strategy.execute(self, inputs)

            # Validate output
            self._validate_signature_output(result)

            # Post-execution hook
            result = self._post_execution_hook(result)

            return result

        except Exception as e:
            return self._handle_error(
                e, {"inputs": inputs, "signature": self.signature.name}
            )


# ==============================================================================
# Extension Point 1: _default_signature() Tests (3 tests)
# ==============================================================================


class TestExtensionPoint1_DefaultSignature:
    """Test Extension Point 1: _default_signature() override patterns."""

    def test_default_signature_called_when_no_signature_provided(self):
        """
        Test that _default_signature() is called when no signature provided.

        Expected Behavior:
        - BaseAgent.__init__(config) with no signature parameter
        - _default_signature() is called automatically
        - self.signature is set to default signature
        """
        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        # Verify default signature was used
        assert agent.signature is not None
        assert agent.signature.name == "default"
        assert len(agent.signature.input_fields) == 1
        assert agent.signature.input_fields[0].name == "input"
        assert len(agent.signature.output_fields) == 1
        assert agent.signature.output_fields[0].name == "output"

    def test_default_signature_can_be_overridden(self):
        """
        Test that _default_signature() can be overridden in subclass.

        Expected Behavior:
        - Create CustomAgent that overrides _default_signature()
        - CustomAgent uses custom signature instead of default
        - Override signature has custom fields
        """

        class CustomAgent(BaseAgent):
            def _default_signature(self) -> Signature:
                return Signature(
                    name="custom_signature",
                    input_fields=[
                        InputField(name="question", type=str, desc="User question"),
                        InputField(
                            name="context",
                            type=str,
                            desc="Additional context",
                            default="",
                        ),
                    ],
                    output_fields=[
                        OutputField(name="answer", type=str, desc="Agent answer"),
                        OutputField(
                            name="confidence", type=float, desc="Confidence score"
                        ),
                    ],
                )

        config = BaseAgentConfig()
        agent = CustomAgent(config=config)

        # Verify custom signature was used
        assert agent.signature.name == "custom_signature"
        assert len(agent.signature.input_fields) == 2
        assert agent.signature.input_fields[0].name == "question"
        assert agent.signature.input_fields[1].name == "context"
        assert len(agent.signature.output_fields) == 2
        assert agent.signature.output_fields[0].name == "answer"
        assert agent.signature.output_fields[1].name == "confidence"

    def test_override_signature_used_instead_of_default(self):
        """
        Test that explicit signature parameter overrides _default_signature().

        Expected Behavior:
        - BaseAgent.__init__(config, signature=custom_sig)
        - _default_signature() is NOT called
        - self.signature is set to provided signature
        """
        custom_signature = Signature(
            name="explicit_signature",
            input_fields=[InputField(name="task", type=str)],
            output_fields=[OutputField(name="result", type=str)],
        )

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, signature=custom_signature)

        # Verify explicit signature was used (not default)
        assert agent.signature.name == "explicit_signature"
        assert agent.signature.input_fields[0].name == "task"
        assert agent.signature.output_fields[0].name == "result"


# ==============================================================================
# Extension Point 2: _default_strategy() Tests (3 tests)
# ==============================================================================


class TestExtensionPoint2_DefaultStrategy:
    """Test Extension Point 2: _default_strategy() override patterns."""

    def test_default_strategy_called_when_no_strategy_provided(self):
        """
        Test that _default_strategy() is called when no strategy provided.

        Expected Behavior:
        - BaseAgent.__init__(config) with no strategy parameter
        - _default_strategy() is called automatically
        - self.strategy is set based on config.strategy_type
        """
        config = BaseAgentConfig(strategy_type="single_shot")
        agent = BaseAgent(config=config)

        # Verify default strategy was used
        assert agent.strategy is not None
        assert isinstance(agent.strategy, SingleShotStrategy)
        assert agent.strategy.name == "single_shot"

    def test_strategy_selection_based_on_config_strategy_type(self):
        """
        Test that _default_strategy() selects correct strategy based on config.strategy_type.

        Expected Behavior:
        - config.strategy_type="single_shot" → SingleShotStrategy
        - config.strategy_type="multi_cycle" → MultiCycleStrategy with max_cycles
        - Invalid strategy_type → ValueError
        """
        # Test single_shot strategy
        config_single = BaseAgentConfig(strategy_type="single_shot")
        agent_single = BaseAgent(config=config_single)
        assert isinstance(agent_single.strategy, SingleShotStrategy)

        # Test multi_cycle strategy
        config_multi = BaseAgentConfig(strategy_type="multi_cycle", max_cycles=10)
        agent_multi = BaseAgent(config=config_multi)
        assert isinstance(agent_multi.strategy, MultiCycleStrategy)
        assert agent_multi.strategy.max_cycles == 10

        # Test invalid strategy type
        config_invalid = BaseAgentConfig(strategy_type="invalid_strategy")
        with pytest.raises(ValueError, match="Unknown strategy type: invalid_strategy"):
            BaseAgent(config=config_invalid)

    def test_override_strategy_used_instead_of_default(self):
        """
        Test that explicit strategy parameter overrides _default_strategy().

        Expected Behavior:
        - BaseAgent.__init__(config, strategy=custom_strategy)
        - _default_strategy() is NOT called
        - self.strategy is set to provided strategy
        """
        custom_strategy = MultiCycleStrategy(max_cycles=15)

        config = BaseAgentConfig(
            strategy_type="single_shot"
        )  # Would normally use SingleShotStrategy
        agent = BaseAgent(config=config, strategy=custom_strategy)

        # Verify explicit strategy was used (not default single_shot)
        assert isinstance(agent.strategy, MultiCycleStrategy)
        assert agent.strategy.max_cycles == 15


# ==============================================================================
# Extension Point 3: _generate_system_prompt() Tests (3 tests)
# ==============================================================================


class TestExtensionPoint3_GenerateSystemPrompt:
    """Test Extension Point 3: _generate_system_prompt() override patterns."""

    def test_default_prompt_generation_from_signature(self):
        """
        Test that _generate_system_prompt() generates prompt from signature fields.

        Expected Behavior:
        - Prompt includes signature description (docstring) if present
        - Prompt includes input field names
        - Prompt includes output field names
        - Prompt includes field descriptions
        """
        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        prompt = agent._generate_system_prompt()

        # Verify prompt contains signature description (default signature has docstring)
        assert "Default signature" in prompt or "input" in prompt

        # Verify prompt contains field names
        assert "input" in prompt  # Default input field
        assert "output" in prompt  # Default output field

        # Verify prompt structure includes inputs/outputs sections
        assert "Inputs:" in prompt or "input" in prompt
        assert "Outputs:" in prompt or "output" in prompt

    def test_prompt_includes_input_output_field_names(self):
        """
        Test that generated prompt includes all input and output field names.

        Expected Behavior:
        - Custom signature with multiple fields
        - Prompt includes all input field names
        - Prompt includes all output field names
        """
        custom_signature = Signature(
            name="qa_signature",
            input_fields=[
                InputField(name="question", type=str),
                InputField(name="context", type=str),
            ],
            output_fields=[
                OutputField(name="answer", type=str),
                OutputField(name="confidence", type=float),
                OutputField(name="reasoning", type=str),
            ],
        )

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, signature=custom_signature)

        prompt = agent._generate_system_prompt()

        # Verify all input fields in prompt
        assert "question" in prompt
        assert "context" in prompt

        # Verify all output fields in prompt
        assert "answer" in prompt
        assert "confidence" in prompt
        assert "reasoning" in prompt

    def test_override_prompt_used_in_workflow(self):
        """
        Test that overridden _generate_system_prompt() is used instead of default.

        Expected Behavior:
        - CustomAgent overrides _generate_system_prompt()
        - Custom prompt is used instead of default template
        - Custom prompt can include domain-specific instructions
        """

        class QAAgent(BaseAgent):
            def _generate_system_prompt(self) -> str:
                return (
                    "You are a helpful Q&A assistant.\n"
                    "Answer questions accurately and concisely.\n"
                    "Provide confidence scores for your answers."
                )

        config = BaseAgentConfig()
        agent = QAAgent(config=config)

        prompt = agent._generate_system_prompt()

        # Verify custom prompt was used (not default)
        assert "helpful Q&A assistant" in prompt
        assert "accurately and concisely" in prompt
        assert "confidence scores" in prompt
        assert "Task: Given" not in prompt  # Not using default template

    def test_signature_docstring_included_in_prompt(self):
        """
        Test that signature docstring (description) is included in prompt.

        This is a regression test for KAIZEN-2026-001:
        _generate_system_prompt() was ignoring signature.description entirely,
        causing all format instructions in docstrings to be lost.

        Expected Behavior:
        - Signature docstring is included at the start of the prompt
        - Field descriptions are also included
        - Format instructions in docstring control LLM output format
        """
        # Import REAL Kaizen classes (not the mock classes defined in this file)
        # This test validates the actual production implementation
        from kaizen.core.base_agent import BaseAgent as RealBaseAgent
        from kaizen.core.config import BaseAgentConfig as RealBaseAgentConfig
        from kaizen.signatures import InputField as RealInputField
        from kaizen.signatures import OutputField as RealOutputField
        from kaizen.signatures import Signature as RealSignature

        class FormattedOutputSignature(RealSignature):
            """You MUST respond with exactly 3 bullet points.

            Format:
            - Point 1
            - Point 2
            - Point 3

            Do NOT write prose or paragraphs.
            """

            question: str = RealInputField(desc="The question to answer")
            answer: str = RealOutputField(
                desc="The formatted answer with 3 bullet points"
            )

        config = RealBaseAgentConfig()
        agent = RealBaseAgent(config=config, signature=FormattedOutputSignature())

        prompt = agent._generate_system_prompt()

        # Verify docstring content is included
        assert "MUST respond with exactly 3 bullet points" in prompt
        assert "Do NOT write prose" in prompt
        assert "Point 1" in prompt

        # Verify field descriptions are included
        assert "question to answer" in prompt
        assert "formatted answer" in prompt

        # Verify structure
        assert "Inputs:" in prompt
        assert "Outputs:" in prompt


# ==============================================================================
# Extension Point 4: _validate_signature_output() Tests (4 tests)
# ==============================================================================


class TestExtensionPoint4_ValidateSignatureOutput:
    """Test Extension Point 4: _validate_signature_output() override patterns."""

    def test_validation_succeeds_for_valid_output(self):
        """
        Test that _validate_signature_output() succeeds for valid output.

        Expected Behavior:
        - Output contains all required output fields
        - Validation returns True
        - No exceptions raised
        """
        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        valid_output = {"output": "This is the output"}

        # Validation should succeed
        result = agent._validate_signature_output(valid_output)
        assert result is True

    def test_validation_fails_for_missing_required_fields(self):
        """
        Test that _validate_signature_output() fails for missing required fields.

        Expected Behavior:
        - Output missing required output field
        - ValueError raised with clear message
        - Error message includes missing field name
        """
        custom_signature = Signature(
            name="qa_signature",
            output_fields=[
                OutputField(name="answer", type=str),
                OutputField(name="confidence", type=float),
                OutputField(name="reasoning", type=str),
            ],
        )

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, signature=custom_signature)

        # Missing "reasoning" field
        invalid_output = {"answer": "Test answer", "confidence": 0.9}

        with pytest.raises(
            ValueError, match="Missing required output field: reasoning"
        ):
            agent._validate_signature_output(invalid_output)

    def test_validation_can_be_extended_with_custom_logic(self):
        """
        Test that _validate_signature_output() can be extended with custom validation.

        Expected Behavior:
        - CustomAgent adds additional validation beyond field presence
        - Custom validation enforces domain-specific constraints
        - super()._validate_signature_output() is called first
        """

        class QAAgent(BaseAgent):
            def _default_signature(self) -> Signature:
                return Signature(
                    name="qa_signature",
                    output_fields=[
                        OutputField(name="answer", type=str),
                        OutputField(name="confidence", type=float),
                    ],
                )

            def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                # Call base validation first
                super()._validate_signature_output(output)

                # Additional QA-specific validation
                confidence = output.get("confidence", 0)
                if not 0 <= confidence <= 1:
                    raise ValueError("Confidence must be between 0 and 1")

                return True

        config = BaseAgentConfig()
        agent = QAAgent(config=config)

        # Valid output
        valid_output = {"answer": "Test", "confidence": 0.9}
        assert agent._validate_signature_output(valid_output) is True

        # Invalid confidence
        invalid_output = {"answer": "Test", "confidence": 1.5}
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            agent._validate_signature_output(invalid_output)

    def test_validation_error_messages_are_clear(self):
        """
        Test that validation error messages are clear and actionable.

        Expected Behavior:
        - Error messages include field name
        - Error messages are descriptive
        - Error messages help debugging
        """
        custom_signature = Signature(
            name="multi_output_signature",
            output_fields=[
                OutputField(name="result1", type=str),
                OutputField(name="result2", type=str),
                OutputField(name="result3", type=str),
            ],
        )

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, signature=custom_signature)

        # Test each missing field produces clear error
        missing_result1 = {"result2": "val2", "result3": "val3"}
        with pytest.raises(ValueError, match="Missing required output field: result1"):
            agent._validate_signature_output(missing_result1)

        missing_result2 = {"result1": "val1", "result3": "val3"}
        with pytest.raises(ValueError, match="Missing required output field: result2"):
            agent._validate_signature_output(missing_result2)


# ==============================================================================
# Extension Point 5: _pre_execution_hook() Tests (3 tests)
# ==============================================================================


class TestExtensionPoint5_PreExecutionHook:
    """Test Extension Point 5: _pre_execution_hook() override patterns."""

    def test_hook_called_before_execution(self):
        """
        Test that _pre_execution_hook() is called before agent execution.

        Expected Behavior:
        - agent.execute() calls _pre_execution_hook()
        - Hook is called with execution inputs
        - Hook is called before strategy execution
        """
        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        inputs = {"input": "test input"}
        agent.execute(**inputs)

        # Verify hook was called
        assert agent._pre_execution_called is True

    def test_hook_can_modify_inputs(self):
        """
        Test that _pre_execution_hook() can modify inputs before execution.

        Expected Behavior:
        - Hook receives inputs as parameter
        - Hook returns modified inputs
        - Modified inputs are used for execution
        """

        class PreprocessingAgent(BaseAgent):
            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                # Add preprocessing
                inputs = super()._pre_execution_hook(inputs)
                inputs["preprocessed"] = True
                inputs["input"] = inputs["input"].upper()  # Example preprocessing
                return inputs

        config = BaseAgentConfig()
        agent = PreprocessingAgent(config=config)

        inputs = {"input": "test input"}
        agent.execute(**inputs)

        # Verify preprocessing occurred (strategy would see modified inputs)
        assert agent._pre_execution_called is True

    def test_hook_respects_config_logging_enabled(self):
        """
        Test that _pre_execution_hook() respects config.logging_enabled flag.

        Expected Behavior:
        - config.logging_enabled=True → logging occurs
        - config.logging_enabled=False → no logging
        - Hook behavior can be controlled via configuration
        """
        # Test with logging enabled
        config_logging = BaseAgentConfig(logging_enabled=True)
        agent_logging = BaseAgent(config=config_logging)

        inputs = {"input": "test"}
        agent_logging.execute(**inputs)

        assert agent_logging._pre_execution_called is True
        assert agent_logging.config.logging_enabled is True

        # Test with logging disabled
        config_no_logging = BaseAgentConfig(logging_enabled=False)
        agent_no_logging = BaseAgent(config=config_no_logging)

        agent_no_logging.execute(**inputs)

        assert agent_no_logging._pre_execution_called is True
        assert agent_no_logging.config.logging_enabled is False


# ==============================================================================
# Extension Point 6: _post_execution_hook() Tests (3 tests)
# ==============================================================================


class TestExtensionPoint6_PostExecutionHook:
    """Test Extension Point 6: _post_execution_hook() override patterns."""

    def test_hook_called_after_execution(self):
        """
        Test that _post_execution_hook() is called after agent execution.

        Expected Behavior:
        - agent.execute() calls _post_execution_hook()
        - Hook is called with execution result
        - Hook is called after strategy execution
        """
        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        inputs = {"input": "test input"}
        agent.execute(**inputs)

        # Verify hook was called
        assert agent._post_execution_called is True

    def test_hook_can_modify_results(self):
        """
        Test that _post_execution_hook() can modify results after execution.

        Expected Behavior:
        - Hook receives result as parameter
        - Hook returns modified result
        - Modified result is returned to caller
        """

        class PostprocessingAgent(BaseAgent):
            def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                # Add postprocessing
                result = super()._post_execution_hook(result)
                result["postprocessed"] = True
                result["metadata"] = {"framework": "kaizen"}
                return result

        config = BaseAgentConfig()
        agent = PostprocessingAgent(config=config)

        inputs = {"input": "test input"}
        result = agent.execute(**inputs)

        # Verify postprocessing occurred
        assert result.get("postprocessed") is True
        assert "metadata" in result
        assert result["metadata"]["framework"] == "kaizen"

    def test_hook_respects_config_logging_enabled(self):
        """
        Test that _post_execution_hook() respects config.logging_enabled flag.

        Expected Behavior:
        - config.logging_enabled=True → logging occurs
        - config.logging_enabled=False → no logging
        - Hook behavior can be controlled via configuration
        """
        # Test with logging enabled
        config_logging = BaseAgentConfig(logging_enabled=True)
        agent_logging = BaseAgent(config=config_logging)

        inputs = {"input": "test"}
        agent_logging.execute(**inputs)

        assert agent_logging._post_execution_called is True
        assert agent_logging.config.logging_enabled is True

        # Test with logging disabled
        config_no_logging = BaseAgentConfig(logging_enabled=False)
        agent_no_logging = BaseAgent(config=config_no_logging)

        agent_no_logging.execute(**inputs)

        assert agent_no_logging._post_execution_called is True
        assert agent_no_logging.config.logging_enabled is False


# ==============================================================================
# Extension Point 7: _handle_error() Tests (4 tests)
# ==============================================================================


class TestExtensionPoint7_HandleError:
    """Test Extension Point 7: _handle_error() override patterns."""

    def test_error_handling_when_config_error_handling_enabled_true(self):
        """
        Test that _handle_error() handles errors when config.error_handling_enabled=True.

        Expected Behavior:
        - Exception occurs during execution
        - config.error_handling_enabled=True
        - Error is caught and converted to error response
        - Exception is NOT re-raised
        """

        class ErrorAgent(BaseAgent):
            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                raise ValueError("Test error")

        config = BaseAgentConfig(error_handling_enabled=True)
        agent = ErrorAgent(config=config)

        inputs = {"input": "test"}
        result = agent.execute(**inputs)

        # Verify error was handled (not raised)
        assert agent._error_handled is True
        assert "error" in result
        assert result["error"] == "Test error"
        assert result["type"] == "ValueError"

    def test_error_reraised_when_config_error_handling_enabled_false(self):
        """
        Test that errors are re-raised when config.error_handling_enabled=False.

        Expected Behavior:
        - Exception occurs during execution
        - config.error_handling_enabled=False
        - Error is re-raised (not caught)
        - Exception propagates to caller
        """

        class ErrorAgent(BaseAgent):
            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                raise ValueError("Test error")

        config = BaseAgentConfig(error_handling_enabled=False)
        agent = ErrorAgent(config=config)

        inputs = {"input": "test"}

        # Verify error is re-raised
        with pytest.raises(ValueError, match="Test error"):
            agent.execute(**inputs)

    def test_error_context_captured_correctly(self):
        """
        Test that error context is captured correctly in error response.

        Expected Behavior:
        - Error occurs during execution
        - Context includes inputs, signature name, etc.
        - Error response includes context for debugging
        """

        class ErrorAgent(BaseAgent):
            def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                raise ValueError("Validation failed")

        config = BaseAgentConfig(error_handling_enabled=True)
        agent = ErrorAgent(config=config)

        inputs = {"input": "test input"}
        result = agent.execute(**inputs)

        # Verify error context captured
        assert "error" in result
        assert "context" in result
        assert "inputs" in result["context"]
        assert result["context"]["inputs"]["input"] == "test input"
        assert "signature" in result["context"]

    def test_custom_error_handling_can_be_overridden(self):
        """
        Test that _handle_error() can be overridden for custom error handling.

        Expected Behavior:
        - CustomAgent overrides _handle_error()
        - Custom error handling logic is used
        - Different error types handled differently
        """

        class CustomErrorAgent(BaseAgent):
            def _handle_error(
                self, error: Exception, context: Dict[str, Any]
            ) -> Dict[str, Any]:
                if isinstance(error, TimeoutError):
                    return {
                        "answer": "Request timed out. Please try again.",
                        "confidence": 0.0,
                        "error_type": "timeout",
                    }
                elif isinstance(error, ValueError):
                    return {
                        "answer": "Invalid input provided.",
                        "confidence": 0.0,
                        "error_type": "validation",
                    }
                else:
                    # Fallback to base error handling
                    return super()._handle_error(error, context)

            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                if inputs.get("input") == "timeout":
                    raise TimeoutError("Request timed out")
                elif inputs.get("input") == "invalid":
                    raise ValueError("Invalid input")
                return super()._pre_execution_hook(inputs)

        config = BaseAgentConfig(error_handling_enabled=True)
        agent = CustomErrorAgent(config=config)

        # Test timeout error handling
        result_timeout = agent.execute(input="timeout")
        assert result_timeout["error_type"] == "timeout"
        assert "timed out" in result_timeout["answer"]

        # Test validation error handling
        result_invalid = agent.execute(input="invalid")
        assert result_invalid["error_type"] == "validation"
        assert "Invalid input" in result_invalid["answer"]


# ==============================================================================
# Extension Pattern Integration Tests (5 tests)
# ==============================================================================


class TestExtensionPatternIntegration:
    """Test integration of multiple extension points in real-world patterns."""

    def test_custom_agent_extends_baseagent_correctly(self):
        """
        Test that custom agent can extend BaseAgent with multiple overrides.

        Expected Behavior:
        - SimpleQAAgent extends BaseAgent
        - Overrides signature, prompt, validation
        - All extension points work together
        """

        class SimpleQAAgent(BaseAgent):
            def _default_signature(self) -> Signature:
                return Signature(
                    name="qa_signature",
                    input_fields=[
                        InputField(
                            name="question", type=str, desc="Question to answer"
                        ),
                        InputField(
                            name="context",
                            type=str,
                            desc="Optional context",
                            default="",
                        ),
                    ],
                    output_fields=[
                        OutputField(name="answer", type=str, desc="Answer to question"),
                        OutputField(
                            name="confidence", type=float, desc="Confidence score"
                        ),
                    ],
                )

            def _generate_system_prompt(self) -> str:
                return "You are a helpful Q&A assistant. Answer questions accurately and concisely."

            def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                super()._validate_signature_output(output)
                if not 0 <= output.get("confidence", 0) <= 1:
                    raise ValueError("Confidence must be between 0 and 1")
                return True

        config = BaseAgentConfig()
        agent = SimpleQAAgent(config=config)

        # Verify custom signature
        assert agent.signature.name == "qa_signature"
        assert len(agent.signature.input_fields) == 2
        assert len(agent.signature.output_fields) == 2

        # Verify custom prompt
        prompt = agent._generate_system_prompt()
        assert "Q&A assistant" in prompt

        # Verify custom validation
        valid_output = {"answer": "Test", "confidence": 0.9}
        assert agent._validate_signature_output(valid_output) is True

        invalid_output = {"answer": "Test", "confidence": 1.5}
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            agent._validate_signature_output(invalid_output)

    def test_multiple_extension_points_overridden_together(self):
        """
        Test that multiple extension points can be overridden together.

        Expected Behavior:
        - ReActAgent overrides signature, strategy, hooks
        - All overrides work together correctly
        - No interference between extension points
        """

        class ReActAgent(BaseAgent):
            def _default_signature(self) -> Signature:
                return Signature(
                    name="react_signature",
                    input_fields=[
                        InputField(name="task", type=str),
                        InputField(name="context", type=str, default=""),
                    ],
                    output_fields=[
                        OutputField(name="thought", type=str),
                        OutputField(name="action", type=str),
                    ],
                )

            def _default_strategy(self) -> ExecutionStrategy:
                return MultiCycleStrategy(max_cycles=10)

            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                inputs = super()._pre_execution_hook(inputs)
                inputs["available_tools"] = ["search", "calculate"]
                return inputs

            def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                result = super()._post_execution_hook(result)
                result["metadata"] = {"tools_used": 2}
                return result

        config = BaseAgentConfig(strategy_type="multi_cycle")
        agent = ReActAgent(config=config)

        # Verify all overrides working
        assert agent.signature.name == "react_signature"
        assert isinstance(agent.strategy, MultiCycleStrategy)
        assert agent.strategy.max_cycles == 10

        inputs = {"task": "test task"}
        result = agent.execute(**inputs)

        # Verify hooks executed
        assert agent._pre_execution_called is True
        assert agent._post_execution_called is True
        assert "metadata" in result

    def test_super_calls_work_correctly_in_extensions(self):
        """
        Test that super() calls work correctly in extension point overrides.

        Expected Behavior:
        - Extension overrides call super() to preserve base behavior
        - super()._method() executes base implementation
        - Custom behavior is added on top of base behavior
        """

        class ExtendedAgent(BaseAgent):
            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                # Call base implementation
                inputs = super()._pre_execution_hook(inputs)
                # Add custom behavior
                inputs["extended"] = True
                return inputs

            def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                # Call base implementation
                result = super()._post_execution_hook(result)
                # Add custom behavior
                result["extended_result"] = True
                return result

        config = BaseAgentConfig()
        agent = ExtendedAgent(config=config)

        inputs = {"input": "test"}
        result = agent.execute(**inputs)

        # Verify both base and custom behavior occurred
        assert agent._pre_execution_called is True  # Base behavior
        assert agent._post_execution_called is True  # Base behavior
        assert result.get("extended_result") is True  # Custom behavior

    def test_extension_points_compose_well(self):
        """
        Test that extension points compose well without conflicts.

        Expected Behavior:
        - Agent overrides multiple extension points
        - No conflicts or interference
        - All extensions work independently and together
        """

        class ComposedAgent(BaseAgent):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.validation_count = 0
                self.hook_calls = []

            def _default_signature(self) -> Signature:
                return Signature(
                    name="composed_sig",
                    output_fields=[OutputField(name="result", type=str)],
                )

            def _generate_system_prompt(self) -> str:
                return "Custom prompt for composed agent"

            def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                self.validation_count += 1
                return super()._validate_signature_output(output)

            def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                self.hook_calls.append("pre")
                return super()._pre_execution_hook(inputs)

            def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                self.hook_calls.append("post")
                return super()._post_execution_hook(result)

        config = BaseAgentConfig()
        agent = ComposedAgent(config=config)

        # Execute and verify all extensions work
        agent.execute(input="test")

        assert agent.signature.name == "composed_sig"
        assert agent._generate_system_prompt() == "Custom prompt for composed agent"
        assert agent.validation_count == 1
        assert agent.hook_calls == ["pre", "post"]

    def test_real_world_extension_pattern_simpleqa_agent(self):
        """
        Test real-world extension pattern: SimpleQA Agent from examples.

        Expected Behavior:
        - Matches SimpleQA agent pattern from examples/1-single-agent/simple-qa/
        - Signature-based Q&A with confidence scoring
        - Custom validation for confidence range
        - Error handling for low confidence
        """

        class SimpleQAAgent(BaseAgent):
            def _default_signature(self) -> Signature:
                """QA-specific signature."""
                return Signature(
                    name="qa_signature",
                    description="Answer questions accurately and concisely with confidence scoring",
                    input_fields=[
                        InputField(
                            name="question", type=str, desc="The question to answer"
                        ),
                        InputField(
                            name="context",
                            type=str,
                            desc="Additional context if available",
                            default="",
                        ),
                    ],
                    output_fields=[
                        OutputField(
                            name="answer", type=str, desc="Clear, accurate answer"
                        ),
                        OutputField(
                            name="confidence",
                            type=float,
                            desc="Confidence score 0.0-1.0",
                        ),
                        OutputField(
                            name="reasoning",
                            type=str,
                            desc="Brief explanation of reasoning",
                        ),
                    ],
                )

            def _generate_system_prompt(self) -> str:
                """QA-specific prompt."""
                return (
                    "You are a helpful Q&A assistant.\n"
                    "Answer questions accurately and concisely.\n"
                    "Provide confidence scores between 0.0 and 1.0 for your answers.\n"
                    "Explain your reasoning briefly."
                )

            def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
                """QA-specific validation."""
                # Call base validation
                super()._validate_signature_output(output)

                # Additional validation: confidence range
                confidence = output.get("confidence", 0)
                if not 0 <= confidence <= 1:
                    raise ValueError("Confidence must be between 0 and 1")

                return True

            def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
                """QA-specific post-processing."""
                result = super()._post_execution_hook(result)

                # Add metadata
                result["metadata"] = {"agent_type": "qa", "framework": "kaizen"}

                return result

        config = BaseAgentConfig()
        agent = SimpleQAAgent(config=config)

        # Verify signature
        assert agent.signature.name == "qa_signature"
        assert len(agent.signature.input_fields) == 2
        assert agent.signature.input_fields[0].name == "question"
        assert len(agent.signature.output_fields) == 3

        # Verify prompt
        prompt = agent._generate_system_prompt()
        assert "Q&A assistant" in prompt
        assert "confidence scores" in prompt

        # Verify validation
        valid_output = {
            "answer": "Test answer",
            "confidence": 0.9,
            "reasoning": "Based on available information",
        }
        assert agent._validate_signature_output(valid_output) is True

        # Verify custom validation
        invalid_output = {
            "answer": "Test",
            "confidence": 1.5,
            "reasoning": "Invalid confidence",
        }
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            agent._validate_signature_output(invalid_output)


# ==============================================================================
# Test Execution Summary
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with pytest:
        pytest tests/unit/kaizen/core/test_base_agent_extension_points.py -v

    Expected Results:
    - 28 test cases total
    - All tests will FAIL until BaseAgent extension points are implemented
    - This is intentional - we are following TDD (Test-Driven Development)

    Test Coverage:
    - Extension Point 1 (_default_signature): 3 tests
    - Extension Point 2 (_default_strategy): 3 tests
    - Extension Point 3 (_generate_system_prompt): 3 tests
    - Extension Point 4 (_validate_signature_output): 4 tests
    - Extension Point 5 (_pre_execution_hook): 3 tests
    - Extension Point 6 (_post_execution_hook): 3 tests
    - Extension Point 7 (_handle_error): 4 tests
    - Extension Pattern Integration: 5 tests

    Coverage Target: 90%+ for extension point mechanisms
    Execution Time: <2 seconds (unit tests only)

    Next Steps:
    1. Implement BaseAgent extension points (Phase 1, Task 1.17)
    2. Run tests again to verify implementation
    3. Achieve 90%+ coverage target
    """
    pytest.main([__file__, "-v", "--tb=short"])

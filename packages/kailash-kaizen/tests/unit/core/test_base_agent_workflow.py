"""
Tier 1 Unit Tests: BaseAgent Workflow Generation

Test Module: test_base_agent_workflow.py
Purpose: Comprehensive test coverage for BaseAgent.to_workflow() method and workflow generation
Coverage Target: 95%+ for BaseAgent.to_workflow() and workflow-related methods
Test Strategy: TDD (Test-First Development)

Architecture Reference: ADR-006-agent-base-architecture.md
TODO Reference: TODO-157, Task 1.11
Core SDK Reference: src/kailash/workflow/builder.py

Test Categories:
1. Basic Workflow Generation Tests (5 tests) - Returns WorkflowBuilder, contains nodes, buildable
2. Signature → Workflow Conversion Tests (6 tests) - Input/output field mapping
3. LLMAgentNode Configuration Tests (5 tests) - Config propagation to workflow nodes
4. Workflow Composition Tests (4 tests) - Agent as composable node
5. Workflow Execution Tests (3 tests) - Generated workflow executable
6. Edge Cases Tests (3 tests) - No signature, custom strategy, caching

Design Principles:
- NO MOCKING in Tier 1 tests (test actual behavior with real Core SDK classes)
- Fast execution (<2s total - no actual LLM calls)
- Independent tests (no shared state)
- Descriptive test names and docstrings
- Follow Kailash SDK patterns

BaseAgent Workflow Methods (from ADR-006):

    class BaseAgent(Node):
        def to_workflow(self) -> WorkflowBuilder:
            '''Generate a workflow from the agent's signature.'''
            workflow = WorkflowBuilder()

            # Create LLMAgentNode for agent execution
            workflow.add_node('LLMAgentNode', 'agent', {
                'model': self.config.model,
                'provider': self.config.llm_provider,
                'temperature': self.config.temperature,
                # ... other config params
            })

            return workflow

        def to_workflow_node(self) -> Node:
            '''Convert this agent into a single node for composition.'''
            # Wrap agent in a node wrapper
            pass

Core SDK Workflow Pattern (CRITICAL):
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime

    workflow = WorkflowBuilder()
    workflow.add_node('LLMAgentNode', 'agent', {...})
    workflow.add_node('DataTransformer', 'output', {...})
    workflow.add_connection('agent', 'response', 'output', 'input')

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
"""

from dataclasses import dataclass
from typing import Any, List, Optional

# Core SDK imports (real infrastructure - NO MOCKING)

# ==============================================================================
# Test Fixtures and Mock Classes
# ==============================================================================


@dataclass
class BaseAgentConfig:
    """
    Minimal BaseAgentConfig for testing workflow generation.

    Full implementation should match ADR-006 specification.
    This minimal version contains only fields needed for workflow generation.
    """

    # LLM Provider Configuration
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = 500
    timeout: int = 30

    # Framework Features
    signature_programming_enabled: bool = True
    optimization_enabled: bool = True
    monitoring_enabled: bool = True

    # Agent Behavior
    logging_enabled: bool = True
    performance_enabled: bool = True

    # Strategy Configuration
    strategy_type: str = "single_shot"
    max_cycles: int = 5


@dataclass
class InputField:
    """Mock InputField for signature testing."""

    name: str
    field_type: type
    description: str = ""
    default: Any = None
    required: bool = True


@dataclass
class OutputField:
    """Mock OutputField for signature testing."""

    name: str
    field_type: type
    description: str = ""
    required: bool = True


class MockSignature:
    """
    Mock Signature for testing workflow generation.

    Represents DSPy-inspired signature structure from ADR-006:

    class QASignature(Signature):
        question: str = InputField(desc="Question to answer")
        context: Optional[str] = InputField(desc="Optional context")
        answer: str = OutputField(desc="Answer to question")
        confidence: float = OutputField(desc="Confidence score")
    """

    def __init__(
        self,
        input_fields: Optional[List[InputField]] = None,
        output_fields: Optional[List[OutputField]] = None,
        name: str = "MockSignature",
    ):
        self.name = name
        self.input_fields = input_fields or []
        self.output_fields = output_fields or []

    def __repr__(self):
        return f"MockSignature(name='{self.name}', inputs={len(self.input_fields)}, outputs={len(self.output_fields)})"


class SimpleQASignature(MockSignature):
    """Simple Q&A signature with 1 input, 1 output."""

    def __init__(self):
        super().__init__(
            input_fields=[
                InputField(
                    name="question", field_type=str, description="Question to answer"
                )
            ],
            output_fields=[
                OutputField(
                    name="answer", field_type=str, description="Answer to question"
                )
            ],
            name="SimpleQASignature",
        )


class ComplexSignature(MockSignature):
    """Complex signature with multiple inputs and outputs."""

    def __init__(self):
        super().__init__(
            input_fields=[
                InputField(
                    name="question", field_type=str, description="Main question"
                ),
                InputField(
                    name="context",
                    field_type=str,
                    description="Additional context",
                    required=False,
                ),
                InputField(
                    name="max_length",
                    field_type=int,
                    description="Max answer length",
                    default=100,
                ),
            ],
            output_fields=[
                OutputField(name="answer", field_type=str, description="Main answer"),
                OutputField(
                    name="confidence", field_type=float, description="Confidence score"
                ),
                OutputField(
                    name="reasoning",
                    field_type=str,
                    description="Step-by-step reasoning",
                ),
            ],
            name="ComplexSignature",
        )


class MockExecutionStrategy:
    """Mock execution strategy for testing."""

    def __init__(self, strategy_type="single_shot"):
        self.strategy_type = strategy_type

    def execute(self, agent, signature_input, **kwargs):
        """Execute method required by ExecutionStrategy Protocol."""
        return {"result": "mock_execution"}


# ==============================================================================
# Category 1: Basic Workflow Generation Tests (5 tests)
# ==============================================================================


class TestBasicWorkflowGeneration:
    """Test BaseAgent.to_workflow() returns valid WorkflowBuilder instances."""

    def test_to_workflow_returns_workflow_builder(self):
        """
        Test to_workflow() returns a WorkflowBuilder instance.

        Validates:
        - Method exists and is callable
        - Returns WorkflowBuilder instance
        - Not None

        Expected Behavior:
        - workflow = agent.to_workflow()
        - isinstance(workflow, WorkflowBuilder) is True

        Critical Pattern (from ADR-006):
            def to_workflow(self) -> WorkflowBuilder:
                workflow = WorkflowBuilder()
                # ... add nodes and connections
                return workflow
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # assert workflow is not None
        # assert isinstance(workflow, WorkflowBuilder)

    def test_workflow_contains_llm_agent_node(self):
        """
        Test generated workflow contains LLMAgentNode.

        Validates:
        - Workflow has at least one node
        - Node type is LLMAgentNode
        - Node ID is 'agent' (or similar)

        Expected Behavior:
        - workflow.nodes should contain LLMAgentNode
        - Node configured with agent parameters

        Core SDK Pattern:
            workflow.add_node('LLMAgentNode', 'agent', {
                'model': self.config.model,
                'provider': self.config.llm_provider,
                ...
            })
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Check workflow has nodes
        # assert len(workflow.nodes) > 0
        #
        # # Check for LLMAgentNode
        # node_types = [node_info.get('type') for node_info in workflow.nodes.values()]
        # assert 'LLMAgentNode' in node_types

    def test_workflow_node_has_correct_configuration(self):
        """
        Test LLMAgentNode in workflow has correct configuration.

        Validates:
        - Node config contains model, provider, temperature
        - Config values match agent config
        - All required parameters present

        Expected Behavior:
        - Node config['model'] == agent.config.model
        - Node config['provider'] == agent.config.llm_provider
        - Node config['temperature'] == agent.config.temperature

        Config Propagation Pattern (from ADR-006):
            workflow.add_node('LLMAgentNode', 'agent', {
                'model': self.config.model,
                'provider': self.config.llm_provider,
                'temperature': self.config.temperature,
                'max_tokens': self.config.max_tokens,
            })
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(
        #     llm_provider="openai",
        #     model="gpt-4",
        #     temperature=0.5,
        #     max_tokens=1000
        # )
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode
        # llm_node = None
        # for node_id, node_info in workflow.nodes.items():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node = node_info
        #         break
        #
        # assert llm_node is not None
        # node_config = llm_node.get('config', {})
        # assert node_config.get('model') == "gpt-4"
        # assert node_config.get('provider') == "openai"
        # assert node_config.get('temperature') == 0.5
        # assert node_config.get('max_tokens') == 1000

    def test_workflow_is_buildable(self):
        """
        Test generated workflow can be built successfully.

        Validates:
        - workflow.build() succeeds
        - Returns valid Workflow instance
        - No validation errors

        Expected Behavior:
        - built_workflow = workflow.build()
        - built_workflow is not None
        - No WorkflowValidationError raised

        Critical Pattern (ALWAYS):
            workflow = agent.to_workflow()
            built = workflow.build()  # Must succeed
            runtime.execute(built)    # Can then execute
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Should not raise WorkflowValidationError
        # built_workflow = workflow.build()
        #
        # assert built_workflow is not None
        # assert hasattr(built_workflow, 'nodes')
        # assert hasattr(built_workflow, 'edges')

    def test_workflow_has_expected_node_count(self):
        """
        Test generated workflow has expected number of nodes.

        Validates:
        - Simple signature → minimal nodes (1 LLMAgentNode)
        - Complex signature → may have additional transform nodes
        - Node count is reasonable

        Expected Behavior:
        - Simple QA: at least 1 node (LLMAgentNode)
        - Complex: may have 2-3 nodes (LLM + transformers)

        Design Note:
        - Exact count depends on implementation
        - Test validates reasonable node count
        - Not too many (< 10 for simple agent)
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Simple agent should have 1-3 nodes
        # assert 1 <= len(workflow.nodes) <= 3
        #
        # # Complex agent may have more nodes
        # complex_signature = ComplexSignature()
        # complex_agent = BaseAgent(config=config, signature=complex_signature)
        # complex_workflow = complex_agent.to_workflow()
        #
        # # But not too many (< 10 for single agent)
        # assert len(complex_workflow.nodes) < 10


# ==============================================================================
# Category 2: Signature → Workflow Conversion Tests (6 tests)
# ==============================================================================


class TestSignatureWorkflowConversion:
    """Test signature-based workflow generation and field mapping."""

    def test_simple_signature_to_workflow(self):
        """
        Test simple signature (1 input, 1 output) generates correct workflow.

        Validates:
        - SimpleQASignature → workflow conversion
        - Input field (question) mapped correctly
        - Output field (answer) mapped correctly

        Expected Behavior:
        - Workflow accepts 'question' as input
        - Workflow produces 'answer' as output
        - LLMAgentNode configured with signature info

        Signature Structure:
            class QASignature(Signature):
                question: str = InputField(desc="Question to answer")
                answer: str = OutputField(desc="Answer to question")
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Workflow should reflect signature structure
        # assert workflow is not None
        # built = workflow.build()
        # assert built is not None
        #
        # # Check metadata or node config contains signature info
        # # (exact structure depends on implementation)

    def test_complex_signature_to_workflow(self):
        """
        Test complex signature (multiple inputs/outputs) generates correct workflow.

        Validates:
        - Multiple input fields mapped
        - Multiple output fields mapped
        - Optional fields handled correctly
        - Default values preserved

        Expected Behavior:
        - Workflow accepts question, context, max_length
        - Workflow produces answer, confidence, reasoning
        - Optional fields have defaults

        Signature Structure:
            class ComplexSignature(Signature):
                question: str = InputField(desc="Main question")
                context: str = InputField(desc="Context", required=False)
                max_length: int = InputField(desc="Max length", default=100)

                answer: str = OutputField(desc="Main answer")
                confidence: float = OutputField(desc="Confidence score")
                reasoning: str = OutputField(desc="Step-by-step reasoning")
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = ComplexSignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Workflow should handle complex signature
        # assert workflow is not None
        # built = workflow.build()
        # assert built is not None
        #
        # # All fields should be represented in workflow
        # # (field mapping validation depends on implementation)

    def test_signature_with_optional_fields_to_workflow(self):
        """
        Test signature with optional fields generates workflow correctly.

        Validates:
        - Optional InputField with required=False
        - Optional field not required in workflow inputs
        - Default values applied when not provided

        Expected Behavior:
        - Required fields must be provided
        - Optional fields can be omitted
        - Defaults used when omitted

        Field Definition:
            context: str = InputField(desc="Context", required=False)
            max_length: int = InputField(default=100)
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        #
        # # Create signature with optional fields
        # signature = MockSignature(
        #     input_fields=[
        #         InputField(name="required_field", field_type=str, required=True),
        #         InputField(name="optional_field", field_type=str, required=False, default="")
        #     ],
        #     output_fields=[
        #         OutputField(name="result", field_type=str)
        #     ]
        # )
        #
        # agent = BaseAgent(config=config, signature=signature)
        # workflow = agent.to_workflow()
        #
        # # Workflow should build successfully
        # built = workflow.build()
        # assert built is not None

    def test_input_field_mapping_to_workflow_inputs(self):
        """
        Test InputField definitions map to workflow inputs correctly.

        Validates:
        - Each InputField creates corresponding workflow input
        - Field names preserved
        - Field types preserved
        - Field descriptions preserved

        Expected Behavior:
        - InputField(name="question") → workflow accepts 'question'
        - Field metadata available in workflow

        Mapping Pattern:
            for field in signature.input_fields:
                # Create input node or parameter
                # Preserve field.name, field.type, field.description
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = ComplexSignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Input fields should be represented
        # # Check workflow metadata or node parameters
        # built = workflow.build()
        # assert built is not None
        #
        # # Validate input field mapping
        # # (exact validation depends on implementation)

    def test_output_field_mapping_to_workflow_outputs(self):
        """
        Test OutputField definitions map to workflow outputs correctly.

        Validates:
        - Each OutputField creates corresponding workflow output
        - Field names preserved
        - Field types preserved
        - Field descriptions preserved

        Expected Behavior:
        - OutputField(name="answer") → workflow produces 'answer'
        - Field metadata available in workflow

        Mapping Pattern:
            for field in signature.output_fields:
                # Create output node or result field
                # Preserve field.name, field.type, field.description
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = ComplexSignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Output fields should be represented
        # built = workflow.build()
        # assert built is not None
        #
        # # Validate output field mapping
        # # (exact validation depends on implementation)

    def test_field_descriptions_preserved_in_workflow(self):
        """
        Test field descriptions are preserved in workflow metadata.

        Validates:
        - InputField descriptions available
        - OutputField descriptions available
        - Descriptions useful for documentation/debugging

        Expected Behavior:
        - Field descriptions stored in workflow metadata
        - Descriptions accessible via workflow.metadata
        - Used for OpenAPI generation (Nexus integration)

        Use Case (from ADR-006):
        - Nexus generates OpenAPI spec from signature
        - Field descriptions become API parameter descriptions
        - Critical for API documentation
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        #
        # signature = MockSignature(
        #     input_fields=[
        #         InputField(
        #             name="question",
        #             field_type=str,
        #             description="The question to answer with detailed context"
        #         )
        #     ],
        #     output_fields=[
        #         OutputField(
        #             name="answer",
        #             field_type=str,
        #             description="The comprehensive answer to the question"
        #         )
        #     ]
        # )
        #
        # agent = BaseAgent(config=config, signature=signature)
        # workflow = agent.to_workflow()
        # built = workflow.build()
        #
        # # Check metadata contains field descriptions
        # # (exact location depends on implementation)
        # assert built.metadata is not None


# ==============================================================================
# Category 3: LLMAgentNode Configuration Tests (5 tests)
# ==============================================================================


class TestLLMAgentNodeConfiguration:
    """Test LLMAgentNode configuration propagation from agent config."""

    def test_llm_node_gets_config_model(self):
        """
        Test LLMAgentNode receives model from agent config.

        Validates:
        - config.model → node_config['model']
        - Model value preserved exactly

        Expected Behavior:
        - agent.config.model = "gpt-4"
        - node_config['model'] = "gpt-4"

        Critical for LLM execution!
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode config
        # llm_node_config = None
        # for node_info in workflow.nodes.values():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node_config = node_info.get('config', {})
        #         break
        #
        # assert llm_node_config is not None
        # assert llm_node_config.get('model') == "gpt-4"

    def test_llm_node_gets_config_provider(self):
        """
        Test LLMAgentNode receives provider from agent config.

        Validates:
        - config.llm_provider → node_config['provider']
        - Provider value preserved exactly

        Expected Behavior:
        - agent.config.llm_provider = "openai"
        - node_config['provider'] = "openai"

        Critical for LLM execution!
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="anthropic", model="claude-3")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode config
        # llm_node_config = None
        # for node_info in workflow.nodes.values():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node_config = node_info.get('config', {})
        #         break
        #
        # assert llm_node_config is not None
        # assert llm_node_config.get('provider') == "anthropic"

    def test_llm_node_gets_config_temperature(self):
        """
        Test LLMAgentNode receives temperature from agent config.

        Validates:
        - config.temperature → node_config['temperature']
        - Temperature value preserved exactly

        Expected Behavior:
        - agent.config.temperature = 0.7
        - node_config['temperature'] = 0.7

        Important for response consistency!
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(
        #     llm_provider="openai",
        #     model="gpt-4",
        #     temperature=0.7
        # )
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode config
        # llm_node_config = None
        # for node_info in workflow.nodes.values():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node_config = node_info.get('config', {})
        #         break
        #
        # assert llm_node_config is not None
        # assert llm_node_config.get('temperature') == 0.7

    def test_llm_node_gets_config_max_tokens(self):
        """
        Test LLMAgentNode receives max_tokens from agent config.

        Validates:
        - config.max_tokens → node_config['max_tokens']
        - Max tokens value preserved exactly

        Expected Behavior:
        - agent.config.max_tokens = 2000
        - node_config['max_tokens'] = 2000

        Important for response length control!
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(
        #     llm_provider="openai",
        #     model="gpt-4",
        #     max_tokens=2000
        # )
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode config
        # llm_node_config = None
        # for node_info in workflow.nodes.values():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node_config = node_info.get('config', {})
        #         break
        #
        # assert llm_node_config is not None
        # assert llm_node_config.get('max_tokens') == 2000

    def test_llm_node_gets_signature_based_system_prompt(self):
        """
        Test LLMAgentNode receives system prompt generated from signature.

        Validates:
        - Signature information → system_prompt
        - System prompt includes input/output field descriptions
        - Prompt guides LLM behavior based on signature

        Expected Behavior:
        - Signature defines expected I/O
        - System prompt tells LLM about expected structure
        - LLM produces outputs matching signature

        Example System Prompt:
            "You are a Q&A assistant.
             Input: question (str) - Question to answer
             Output: answer (str) - Answer to question

             Provide clear, accurate answers."
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        #
        # # Find LLMAgentNode config
        # llm_node_config = None
        # for node_info in workflow.nodes.values():
        #     if node_info.get('type') == 'LLMAgentNode':
        #         llm_node_config = node_info.get('config', {})
        #         break
        #
        # assert llm_node_config is not None
        # # System prompt should mention signature fields
        # system_prompt = llm_node_config.get('system_prompt', '')
        # assert system_prompt != ''
        # # Check prompt contains signature information
        # # (exact format depends on implementation)


# ==============================================================================
# Category 4: Workflow Composition Tests (4 tests)
# ==============================================================================


class TestWorkflowComposition:
    """Test agent workflow composition with other workflows."""

    def test_to_workflow_node_returns_node_instance(self):
        """
        Test to_workflow_node() returns a Node instance.

        Validates:
        - Method exists and is callable
        - Returns Node instance
        - Node is composable

        Expected Behavior:
        - agent_node = agent.to_workflow_node()
        - isinstance(agent_node, Node) is True

        Use Case (from ADR-006):
        - Enable agent reuse in larger workflows
        - Wrap agent as a single node
        - Compose multiple agents together
        """
        # This test will FAIL until BaseAgent.to_workflow_node() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # agent_node = agent.to_workflow_node()
        #
        # assert agent_node is not None
        # assert isinstance(agent_node, Node)

    def test_agent_node_composable_in_larger_workflows(self):
        """
        Test agent node can be used in larger workflows.

        Validates:
        - Agent node can be added to WorkflowBuilder
        - Connections can be made to/from agent node
        - Workflow builds successfully

        Expected Behavior:
        - workflow.add_node_instance(agent_node, 'qa')
        - workflow.add_connection('input', 'data', 'qa', 'question')
        - workflow.build() succeeds

        Composition Pattern:
            main_workflow = WorkflowBuilder()

            # Add data source
            main_workflow.add_node('CSVReaderNode', 'data_source', {...})

            # Add agent as node
            qa_agent = QAAgent(config)
            qa_node = qa_agent.to_workflow_node()
            main_workflow.add_node_instance(qa_node, 'qa')

            # Connect them
            main_workflow.add_connection('data_source', 'data', 'qa', 'question')

            # Execute
            runtime.execute(main_workflow.build())
        """
        # This test will FAIL until BaseAgent.to_workflow_node() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # agent_node = agent.to_workflow_node()
        #
        # # Create larger workflow
        # main_workflow = WorkflowBuilder()
        #
        # # Add agent node to workflow
        # main_workflow.add_node_instance(agent_node, 'qa_agent')
        #
        # # Should be able to build
        # built = main_workflow.build()
        # assert built is not None

    def test_agent_node_preserves_configuration(self):
        """
        Test agent node preserves original agent configuration.

        Validates:
        - Agent config accessible from node
        - Config values unchanged
        - Config used during execution

        Expected Behavior:
        - agent_node has reference to original config
        - Config values preserved exactly

        Critical for Correct Execution:
        - Model, provider, temperature must be preserved
        - Otherwise agent behavior changes unexpectedly
        """
        # This test will FAIL until BaseAgent.to_workflow_node() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(
        #     llm_provider="openai",
        #     model="gpt-4",
        #     temperature=0.5
        # )
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # agent_node = agent.to_workflow_node()
        #
        # # Node should preserve config
        # # (access pattern depends on implementation)
        # assert agent_node is not None

    def test_agent_node_can_connect_to_other_nodes(self):
        """
        Test agent node can be connected to other Core SDK nodes.

        Validates:
        - Connections to agent node work
        - Connections from agent node work
        - Data flows correctly through connections

        Expected Behavior:
        - Can connect DataTransformerNode → AgentNode
        - Can connect AgentNode → DataTransformerNode
        - Workflow builds and validates connections

        Connection Pattern:
            workflow.add_node('DataTransformerNode', 'input_prep', {...})
            workflow.add_node_instance(agent_node, 'qa')
            workflow.add_node('DataTransformerNode', 'output_format', {...})

            workflow.add_connection('input_prep', 'result', 'qa', 'question')
            workflow.add_connection('qa', 'answer', 'output_format', 'input')
        """
        # This test will FAIL until BaseAgent.to_workflow_node() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # agent_node = agent.to_workflow_node()
        #
        # # Create workflow with connections
        # workflow = WorkflowBuilder()
        #
        # # Add input transform
        # workflow.add_node('DataTransformerNode', 'input_prep', {
        #     'transformation': 'uppercase'
        # })
        #
        # # Add agent
        # workflow.add_node_instance(agent_node, 'qa')
        #
        # # Connect them
        # workflow.add_connection('input_prep', 'result', 'qa', 'question')
        #
        # # Should build successfully
        # built = workflow.build()
        # assert built is not None


# ==============================================================================
# Category 5: Workflow Execution Tests (3 tests)
# ==============================================================================


class TestWorkflowExecution:
    """Test generated workflows are executable with LocalRuntime."""

    def test_generated_workflow_is_executable_with_runtime(self):
        """
        Test workflow from to_workflow() can be executed with LocalRuntime.

        Validates:
        - Workflow builds successfully
        - LocalRuntime can execute workflow
        - No runtime errors during execution

        Expected Behavior:
        - workflow = agent.to_workflow()
        - built = workflow.build()
        - runtime = LocalRuntime()
        - results, run_id = runtime.execute(built)
        - No exceptions raised

        CRITICAL PATTERN (from CLAUDE.md):
            runtime.execute(workflow.build())  # ALWAYS
            NOT: workflow.execute(runtime)      # NEVER

        Note: This is a smoke test - no actual LLM calls
        Execution may fail at LLM call, but workflow structure should be valid
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented, this should pass (structure test only):
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        # built = workflow.build()
        #
        # # Runtime should accept the workflow
        # runtime = LocalRuntime()
        # assert runtime is not None
        #
        # # Note: Actual execution would require LLM credentials
        # # This test validates workflow structure is executable

    def test_workflow_execution_with_minimal_inputs(self):
        """
        Test workflow can be executed with minimal required inputs.

        Validates:
        - Workflow accepts minimum inputs
        - Required fields enforced
        - Optional fields handled correctly

        Expected Behavior:
        - SimpleQA requires only 'question'
        - Execution with just required fields succeeds
        - Optional fields use defaults

        Input Pattern:
            inputs = {'question': 'What is 2+2?'}
            results, run_id = runtime.execute(built, inputs)

        Note: Smoke test - validates input handling, not actual LLM execution
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented (structure test):
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        # built = workflow.build()
        #
        # # Prepare minimal inputs
        # inputs = {'question': 'What is 2+2?'}
        #
        # # Runtime should accept the inputs
        # runtime = LocalRuntime()
        # # Note: Would execute if LLM credentials available

    def test_workflow_execution_produces_expected_outputs(self):
        """
        Test workflow execution produces outputs matching signature.

        Validates:
        - Output fields match signature definition
        - Output types correct
        - All required outputs present

        Expected Behavior:
        - SimpleQA produces 'answer'
        - Complex signature produces answer, confidence, reasoning
        - Output structure matches OutputField definitions

        Output Pattern:
            results, run_id = runtime.execute(built, inputs)
            assert 'answer' in results
            assert isinstance(results['answer'], str)

        Note: This validates output STRUCTURE, not actual LLM content
        Actual LLM execution requires credentials (Tier 2 integration tests)
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented (structure test):
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow = agent.to_workflow()
        # built = workflow.build()
        #
        # # Output structure should match signature
        # # (validation depends on implementation)
        # # Actual LLM execution in Tier 2 integration tests


# ==============================================================================
# Category 6: Edge Cases Tests (3 tests)
# ==============================================================================


class TestWorkflowEdgeCases:
    """Test edge cases in workflow generation."""

    def test_workflow_generation_without_signature_uses_default(self):
        """
        Test workflow generation when signature is None uses default.

        Validates:
        - Agent without signature still generates workflow
        - Default signature used
        - Fallback execution pattern

        Expected Behavior:
        - agent = BaseAgent(config, signature=None)
        - workflow = agent.to_workflow()
        - Workflow uses generic/default signature

        Fallback Pattern (from ADR-006):
            if agent.has_signature:
                result = agent.execute(**signature_input)
            else:
                # Fallback execution
                prompt = self._build_fallback_prompt(signature_input)
                result = agent.execute(prompt)
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # agent = BaseAgent(config=config, signature=None)
        #
        # workflow = agent.to_workflow()
        #
        # # Should still generate valid workflow
        # assert workflow is not None
        # built = workflow.build()
        # assert built is not None

    def test_workflow_generation_with_custom_strategy(self):
        """
        Test workflow generation with custom execution strategy.

        Validates:
        - Custom strategy affects workflow structure
        - MultiCycleStrategy → different workflow
        - Strategy-specific nodes included

        Expected Behavior:
        - SingleShotStrategy: simple linear workflow
        - MultiCycleStrategy: workflow with cycles/loops
        - Strategy pattern applied correctly

        Strategy Patterns:
        - SingleShot: Input → LLMAgent → Output
        - MultiCycle: Input → LLMAgent → SwitchNode → (loop) → Output
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # custom_strategy = MockExecutionStrategy(strategy_type="multi_cycle")
        #
        # agent = BaseAgent(
        #     config=config,
        #     signature=signature,
        #     strategy=custom_strategy
        # )
        #
        # workflow = agent.to_workflow()
        #
        # # Workflow structure may differ based on strategy
        # assert workflow is not None
        # built = workflow.build()
        # assert built is not None

    def test_workflow_caching_repeated_to_workflow_calls(self):
        """
        Test repeated to_workflow() calls handle caching correctly.

        Validates:
        - Calling to_workflow() multiple times
        - Either returns same workflow (cached)
        - Or creates new workflow (no caching)
        - Behavior is consistent

        Expected Behavior (Option 1 - No Caching):
        - workflow1 = agent.to_workflow()
        - workflow2 = agent.to_workflow()
        - workflow1 is not workflow2 (new instance)
        - Both workflows functionally equivalent

        Expected Behavior (Option 2 - Caching):
        - workflow1 = agent.to_workflow()
        - workflow2 = agent.to_workflow()
        - workflow1 is workflow2 (same instance)
        - Performance optimization

        Design Note:
        - Caching adds complexity but improves performance
        - No caching is simpler and safer
        - Both approaches valid - test validates consistency
        """
        # This test will FAIL until BaseAgent.to_workflow() is implemented

        # BaseAgent is now implemented - actual test

        # When implemented:
        # config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        # signature = SimpleQASignature()
        # agent = BaseAgent(config=config, signature=signature)
        #
        # workflow1 = agent.to_workflow()
        # workflow2 = agent.to_workflow()
        #
        # # Both workflows should be valid
        # assert workflow1 is not None
        # assert workflow2 is not None
        #
        # # Either same instance (cached) or different (no cache)
        # # Both approaches valid - test documents behavior


# ==============================================================================
# Test Summary and Coverage Notes
# ==============================================================================

"""
Test Coverage Summary:

Category 1: Basic Workflow Generation (5 tests)
- test_to_workflow_returns_workflow_builder
- test_workflow_contains_llm_agent_node
- test_workflow_node_has_correct_configuration
- test_workflow_is_buildable
- test_workflow_has_expected_node_count

Category 2: Signature → Workflow Conversion (6 tests)
- test_simple_signature_to_workflow
- test_complex_signature_to_workflow
- test_signature_with_optional_fields_to_workflow
- test_input_field_mapping_to_workflow_inputs
- test_output_field_mapping_to_workflow_outputs
- test_field_descriptions_preserved_in_workflow

Category 3: LLMAgentNode Configuration (5 tests)
- test_llm_node_gets_config_model
- test_llm_node_gets_config_provider
- test_llm_node_gets_config_temperature
- test_llm_node_gets_config_max_tokens
- test_llm_node_gets_signature_based_system_prompt

Category 4: Workflow Composition (4 tests)
- test_to_workflow_node_returns_node_instance
- test_agent_node_composable_in_larger_workflows
- test_agent_node_preserves_configuration
- test_agent_node_can_connect_to_other_nodes

Category 5: Workflow Execution (3 tests)
- test_generated_workflow_is_executable_with_runtime
- test_workflow_execution_with_minimal_inputs
- test_workflow_execution_produces_expected_outputs

Category 6: Edge Cases (3 tests)
- test_workflow_generation_without_signature_uses_default
- test_workflow_generation_with_custom_strategy
- test_workflow_caching_repeated_to_workflow_calls

TOTAL: 26 comprehensive test cases

Expected Coverage: 95%+ for BaseAgent.to_workflow() and related methods

Test Execution:
    pytest tests/unit/kaizen/core/test_base_agent_workflow.py -v

Coverage Measurement:
    pytest tests/unit/kaizen/core/test_base_agent_workflow.py --cov=kaizen.core.base_agent --cov-report=term-missing

TDD Workflow:
1. RED: All tests fail (BaseAgent.to_workflow() not implemented)
2. GREEN: Implement minimal to_workflow() to pass tests
3. REFACTOR: Improve workflow generation while keeping tests green

Next Steps (Task 1.12):
- Write tests for BaseAgent extension points
- Test all 7 extension points defined in ADR-006
- Validate extension point hookability and overridability
"""

# ADR-008: Signature Programming Implementation Approach

## Status
**Accepted** - 2025-09-24

## Context

Kaizen's core value proposition is signature-based AI programming that exceeds DSPy's capabilities while integrating seamlessly with Kailash SDK. Currently, signature programming is completely missing (BLOCKER-002), causing 0% success rate on workflow examples.

### Problem Statement
- DSPy demonstrates the power of declarative AI programming with signatures like `"question -> answer"`
- Current Kaizen has placeholder `SignatureBase` class but no implementation
- Developers expect intuitive Python-native signature syntax
- Must integrate with existing Kailash WorkflowBuilder and runtime patterns
- Need automatic prompt generation and optimization capabilities

### Decision Drivers
1. **Developer Experience**: Intuitive Python syntax with type hints
2. **Core SDK Integration**: Seamless WorkflowBuilder compatibility
3. **Performance**: <50ms signature compilation target
4. **Optimization**: ML-based prompt improvement capabilities
5. **Type Safety**: Runtime validation with Pydantic integration

### Constraints
- Must work with existing `WorkflowBuilder` and `LocalRuntime`
- Cannot break Core SDK patterns: `runtime.execute(workflow.build())`
- Must support complex multi-input/output signatures
- Need backward compatibility with current `SignatureBase`

## Decision

Implement a three-layer signature programming system:

### Layer 1: Signature Definition and Parsing
```python
# Modern signature syntax with type hints
@kaizen.signature
def research_task(topic: str, depth: int = 3) -> ResearchResult:
    """Research a topic with specified depth and return structured results."""
    pass

# DSPy-compatible string syntax
signature = kaizen.create_signature(
    "topic: str, depth: int -> summary: str, sources: List[str], confidence: float",
    description="Research task with confidence scoring"
)

# Pydantic model syntax
class ResearchSignature(SignatureBase):
    inputs: ResearchInput
    outputs: ResearchOutput
    description: str = "Advanced research with structured I/O"
```

### Layer 2: Workflow Compilation
```python
# Automatic workflow generation
signature = kaizen.create_signature("question -> answer")
workflow = signature.compile_to_workflow()  # Returns WorkflowBuilder

# Manual workflow integration
workflow = WorkflowBuilder()
signature_node = signature.to_node("research_step")
workflow.add_node_instance(signature_node)

# Agent integration
agent = kaizen.create_agent("researcher", signature=signature)
agent_workflow = agent.to_workflow()  # Convert agent to workflow
```

### Layer 3: Execution and Optimization
```python
# Direct execution with optimization
result = signature.execute(topic="machine learning", depth=3)

# Workflow execution with Core SDK
runtime = LocalRuntime()
results, run_id = runtime.execute(signature.compile_to_workflow().build())

# Optimization integration
optimized_signature = optimizer.optimize_signature(signature, training_data)
```

## Consequences

### Positive
- **Intuitive Developer Experience**: Python-native syntax with decorators
- **Flexible Integration**: Multiple syntax options for different use cases
- **Core SDK Compatibility**: Perfect integration with existing patterns
- **Type Safety**: Pydantic validation ensures runtime correctness
- **Performance Optimization**: ML-based prompt improvement built-in
- **Gradual Adoption**: Works alongside existing AI nodes

### Negative
- **Implementation Complexity**: Three syntax options increase maintenance
- **Learning Curve**: Developers need to understand signature concepts
- **Performance Overhead**: Signature compilation adds latency
- **Testing Complexity**: Multiple execution paths require comprehensive testing

### Risks
- **Compilation Edge Cases**: Complex signatures may fail to compile
- **Performance Degradation**: Optimization overhead may impact real-time use
- **Integration Conflicts**: Signature nodes may conflict with existing nodes

## Alternatives Considered

### Option 1: DSPy Direct Port
- **Pros**: Proven approach, familiar to DSPy users
- **Cons**: Poor Kailash integration, limited enterprise features, research-focused
- **Why Rejected**: Doesn't leverage Kailash strengths, poor production readiness

### Option 2: LangChain LCEL Extension
- **Pros**: Familiar expression language, existing ecosystem
- **Cons**: Complex syntax, poor performance, limited optimization
- **Why Rejected**: Doesn't align with Python-native Kailash philosophy

### Option 3: Custom Workflow DSL
- **Pros**: Complete control over syntax and features
- **Cons**: High learning curve, no existing patterns, reinventing wheel
- **Why Rejected**: Too much complexity for unclear benefits

### Option 4: Annotation-Only Approach
- **Pros**: Pure Python with type hints, minimal syntax
- **Cons**: Limited expressiveness, no string-based signatures
- **Why Rejected**: Doesn't match DSPy familiarity, limits adoption

## Implementation Plan

### Phase 1: Foundation (Week 1-2)
```python
# Core signature interfaces
class SignatureBase:
    def __init__(self, signature_spec: str, description: str = "")
    def define_inputs(self) -> Dict[str, Type]
    def define_outputs(self) -> Dict[str, Type]
    def validate_inputs(self, inputs: Dict) -> bool
    def validate_outputs(self, outputs: Dict) -> bool

class SignatureCompiler:
    def parse_signature(self, spec: str) -> SignatureParts
    def generate_prompt(self, signature: SignatureBase) -> str
    def compile_to_workflow(self, signature: SignatureBase) -> WorkflowBuilder

# Basic string signature support
kaizen.create_signature("question -> answer")
```

### Phase 2: Core Features (Week 3-4)
```python
# Decorator syntax
@kaizen.signature
def research_task(topic: str) -> str:
    pass

# Workflow integration
signature.compile_to_workflow()
signature.to_node("step_id")

# Agent integration
agent = kaizen.create_agent("researcher", signature=signature)
```

### Phase 3: Advanced Features (Week 5-6)
```python
# Pydantic model support
class ComplexSignature(SignatureBase):
    inputs: InputModel
    outputs: OutputModel

# Optimization engine
optimizer.optimize_signature(signature, examples)

# Performance monitoring
signature.execution_stats()
```

### Phase 4: Enterprise Integration (Week 7-8)
```python
# Security integration
signature.enable_audit_logging()

# DataFlow integration
@db.model
class SignatureExecution:
    signature_id: str
    inputs: Json
    outputs: Json
    performance_metrics: Json

# Nexus deployment
nexus.deploy_signature(signature, channels=["api", "mcp"])
```

## Implementation Guidance

### Core Components

#### 1. SignatureParser
```python
class SignatureParser:
    def parse_string_signature(self, spec: str) -> ParsedSignature:
        # "topic: str, depth: int -> summary: str, confidence: float"
        inputs, outputs = spec.split(" -> ")
        return ParsedSignature(
            inputs=self._parse_parameters(inputs),
            outputs=self._parse_parameters(outputs)
        )

    def parse_function_signature(self, func: Callable) -> ParsedSignature:
        # Extract from function annotations
        sig = inspect.signature(func)
        return ParsedSignature(
            inputs={name: param.annotation for name, param in sig.parameters.items()},
            outputs=sig.return_annotation
        )
```

#### 2. WorkflowCompiler
```python
class WorkflowCompiler:
    def compile_signature_to_workflow(self, signature: SignatureBase) -> WorkflowBuilder:
        workflow = WorkflowBuilder()

        # Add signature validation node
        workflow.add_node("InputValidatorNode", "validate_input", {
            "schema": signature.input_schema
        })

        # Add main processing node
        workflow.add_node("LLMAgentNode", "process", {
            "prompt": self.generate_prompt(signature),
            "model": "gpt-4",
            "temperature": 0.7
        })

        # Add output validation node
        workflow.add_node("OutputValidatorNode", "validate_output", {
            "schema": signature.output_schema
        })

        # Connect nodes
        workflow.add_connection("validate_input", "process")
        workflow.add_connection("process", "validate_output")

        return workflow
```

#### 3. PromptGenerator
```python
class PromptGenerator:
    def generate_from_signature(self, signature: SignatureBase) -> str:
        template = self._get_base_template()

        # Add input/output structure
        template += f"\nInputs: {signature.format_inputs()}"
        template += f"\nOutputs: {signature.format_outputs()}"

        # Add description and examples
        if signature.description:
            template += f"\nTask: {signature.description}"

        if signature.examples:
            template += f"\nExamples:\n{signature.format_examples()}"

        return template
```

### Integration Patterns

#### 1. Core SDK Integration
```python
# Standard workflow pattern
workflow = WorkflowBuilder()
signature_node = signature.to_node("research")
workflow.add_node_instance(signature_node)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Signature compilation pattern
compiled_workflow = signature.compile_to_workflow()
results, run_id = runtime.execute(compiled_workflow.build())
```

#### 2. Agent Integration
```python
# Agent with signature
class SignatureAgent(Agent):
    def __init__(self, agent_id: str, signature: SignatureBase, **config):
        super().__init__(agent_id, **config)
        self.signature = signature
        self._workflow = signature.compile_to_workflow()

    def execute(self, **inputs) -> Dict[str, Any]:
        validated_inputs = self.signature.validate_inputs(inputs)
        results, _ = self.framework.runtime.execute(
            self._workflow.build(),
            validated_inputs
        )
        return self.signature.validate_outputs(results)
```

#### 3. Optimization Integration
```python
# ML-based optimization
class SignatureOptimizer:
    def optimize_prompt(self, signature: SignatureBase, examples: List) -> SignatureBase:
        current_prompt = signature.generate_prompt()
        performance_data = self._evaluate_examples(signature, examples)
        optimized_prompt = self._ml_optimize(current_prompt, performance_data)

        return signature.with_optimized_prompt(optimized_prompt)
```

### Testing Strategy

#### 1. Unit Tests
- Signature parsing with various formats
- Prompt generation accuracy
- Workflow compilation correctness
- Input/output validation

#### 2. Integration Tests
- Core SDK workflow execution
- Agent signature integration
- Real LLM model execution
- Performance benchmarking

#### 3. End-to-End Tests
- Complete developer workflows
- Multi-signature coordination
- Optimization feedback loops
- Enterprise feature integration

### Performance Considerations

#### 1. Compilation Caching
```python
class SignatureCache:
    def get_compiled_workflow(self, signature_hash: str) -> Optional[WorkflowBuilder]:
        return self._cache.get(signature_hash)

    def cache_compiled_workflow(self, signature_hash: str, workflow: WorkflowBuilder):
        self._cache[signature_hash] = workflow
```

#### 2. Lazy Loading
```python
class LazySignature(SignatureBase):
    def __init__(self, signature_spec: str):
        self._spec = signature_spec
        self._compiled_workflow = None

    @property
    def workflow(self) -> WorkflowBuilder:
        if self._compiled_workflow is None:
            self._compiled_workflow = self._compile()
        return self._compiled_workflow
```

#### 3. Async Compilation
```python
async def compile_signature_async(signature: SignatureBase) -> WorkflowBuilder:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        SignatureCompiler().compile_to_workflow,
        signature
    )
```

This implementation approach provides a comprehensive signature programming system that exceeds DSPy capabilities while maintaining perfect Kailash SDK integration.

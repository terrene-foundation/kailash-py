# ADR-0025: Hierarchical Document Processing Architecture

## Status
Proposed

## Context
We need to implement OpenAI's hierarchical document processing method as a reusable workflow template. This method involves:

1. **Iterative Splitting**: Break document into 3 parts, identify relevant sections, then recursively split relevant parts
2. **Multi-Model Strategy**: Different models for different tasks (splitting/selection, generation, validation)
3. **Iteration Control**: 3-5 iterations or until all parts are selected
4. **Query-Driven Processing**: All processing is guided by a user query

This represents a complex, multi-step workflow that should be reusable across different document types and use cases.

## Decision
Implement this as a **Workflow Template** with specialized nodes, providing:

### Core Components

1. **Specialized Document Processing Nodes**:
   - `HierarchicalDocumentSplitter`: Intelligent 3-way document splitting
   - `RelevanceSelector`: Query-based relevance scoring and selection
   - `DocumentCombiner`: Combines selected parts with context awareness
   - `LLMGenerationNode`: Configurable LLM for response generation
   - `LLMValidationNode`: Validation using reasoning models
   - `IterationController`: Loop control with termination conditions

2. **Workflow Template**: `HierarchicalRAGTemplate`
   - Parameterized model selection
   - Configurable iteration limits
   - Pluggable splitting strategies
   - Query customization
   - Output format control

3. **Composability Features**:
   - Works as a SubWorkflow in larger pipelines
   - Connects to preprocessing (OCR, parsing) workflows
   - Integrates with postprocessing (formatting, storage) workflows

### Architecture Benefits

1. **Reusability**: Template can be instantiated for different document types
2. **Flexibility**: Model choices can be configured per use case
3. **Composability**: Can be embedded in larger document processing pipelines
4. **Maintainability**: Single implementation serves multiple use cases
5. **Testability**: Each node can be tested independently

### Model Configuration Strategy

```python
model_config = {
    "splitting_model": {
        "provider": "openai",
        "model": "gpt-4o-mini",  # Large context + cheap
        "temperature": 0.1
    },
    "generation_model": {
        "provider": "openai",
        "model": "gpt-4o",      # High accuracy
        "temperature": 0.3
    },
    "validation_model": {
        "provider": "openai",
        "model": "o1-mini",     # Strong reasoning
        "temperature": 0.1
    }
}
```

### Template Parameterization

```python
template_params = {
    "max_iterations": 5,
    "min_iterations": 3,
    "splitting_strategy": "semantic",  # semantic, length, hybrid
    "relevance_threshold": 0.7,
    "combination_strategy": "hierarchical",  # flat, hierarchical, weighted
    "output_format": "structured"  # structured, narrative, bullet_points
}
```

## Implementation Plan

### Phase 1: Core Nodes
1. Implement base document processing nodes
2. Create LLM integration nodes with model switching
3. Build iteration control logic

### Phase 2: Workflow Template
1. Design template interface and parameters
2. Implement hierarchical RAG workflow template
3. Create template registration and discovery

### Phase 3: Composability
1. Enable SubWorkflow integration
2. Create preprocessing/postprocessing connectors
3. Build template packaging system

### Phase 4: Optimization
1. Add caching for repeated processing
2. Implement parallel processing where possible
3. Add monitoring and performance metrics

## Consequences

### Positive
- Provides reusable implementation of sophisticated RAG pattern
- Enables easy model experimentation and switching
- Integrates seamlessly with existing SDK architecture
- Can be composed with other workflows for complex pipelines
- Template approach enables sharing and distribution

### Negative
- Complex implementation requiring careful state management
- Multiple LLM calls can be expensive
- Iteration logic adds complexity to workflow execution
- Template system adds abstraction layer

### Mitigations
- Implement comprehensive caching to reduce costs
- Provide cost estimation and monitoring tools
- Create clear documentation and examples
- Build debugging and visualization tools for template workflows

## Related ADRs
- ADR-0015: API Integration Architecture (LLM providers)
- ADR-0016: Immutable State Management (iteration state)
- ADR-0018: Performance Metrics Architecture (cost tracking)

## References
- OpenAI hierarchical document processing methodology
- RAG (Retrieval-Augmented Generation) best practices
- Document chunking and semantic splitting techniques

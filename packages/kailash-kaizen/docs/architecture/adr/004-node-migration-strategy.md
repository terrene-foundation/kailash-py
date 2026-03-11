# ADR-004: Node Migration Strategy from Core SDK

## Status
**Proposed**

## Context

Kailash Core SDK currently has extensive AI capabilities with 20+ AI nodes including:
- LLMAgentNode, IterativeLLMAgentNode
- A2AAgentNode, A2ACoordinatorNode
- SemanticMemoryStoreNode, SemanticMemorySearchNode
- EmbeddingGeneratorNode, HybridSearchNode
- Various AI provider integrations

The introduction of Kaizen requires a careful migration strategy that:
- Preserves existing functionality for current users
- Provides a clear upgrade path to Kaizen capabilities
- Maintains backward compatibility during transition
- Leverages investment in existing AI infrastructure

## Decision

We will implement a **phased migration strategy** that introduces Kaizen capabilities alongside existing AI nodes, with enhanced versions that provide signature programming while maintaining full backward compatibility.

### Migration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MIGRATION STRATEGY                       │
├─────────────────────────────────────────────────────────────┤
│  Phase 1: Kaizen-Enhanced Nodes (Backward Compatible)      │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ KaizenLLMAgent  │ │ KaizenA2AAgent  │ │ KaizenMemory    ││
│  │ + Signatures    │ │ + Orchestration │ │ + Enterprise    ││
│  │ + Original API  │ │ + Original API  │ │ + Original API  ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Legacy Compatibility Layer                                │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ LLMAgentNode    │ │ A2AAgentNode    │ │ SemanticMemory  ││
│  │ (Unchanged)     │ │ (Unchanged)     │ │ (Unchanged)     ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────┤
│              KAILASH CORE SDK FOUNDATION                   │
│  WorkflowBuilder • LocalRuntime • Node Architecture        │
└─────────────────────────────────────────────────────────────┘
```

### Enhanced Node Design Pattern

Each Kaizen-enhanced node provides dual interfaces:

```python
# Enhanced node with signature programming AND legacy compatibility
@register_node()
class KaizenLLMAgentNode(LLMAgentNode):
    """Enhanced LLM Agent with Kaizen signature programming."""

    # Legacy parameter support (100% backward compatible)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kaizen_enabled = kwargs.get('kaizen_enabled', False)

    # Legacy execute method (unchanged behavior)
    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if self.kaizen_enabled and hasattr(self, '_signature'):
            return await self._execute_with_signature(inputs)
        else:
            return await super().execute(inputs)

    # New signature programming interface
    @classmethod
    def from_signature(cls, signature_class, **config):
        """Create node from Kaizen signature."""
        node = cls(kaizen_enabled=True, **config)
        node._signature = signature_class
        node._compile_signature()
        return node

    # Signature-based execution
    async def _execute_with_signature(self, inputs):
        # Use signature for enhanced prompt generation
        # Apply automatic optimization
        # Leverage memory system
        # Provide enterprise features
        pass
```

### Migration Phases

#### Phase 1: Enhanced Nodes (Months 1-2)
Create Kaizen-enhanced versions of core AI nodes:

```python
# Core AI nodes with Kaizen enhancements
KaizenLLMAgentNode(LLMAgentNode)          # Signature programming + optimization
KaizenA2AAgentNode(A2AAgentNode)          # Enhanced orchestration
KaizenMemoryNode(SemanticMemoryStoreNode) # Enterprise memory system
KaizenEmbeddingNode(EmbeddingGeneratorNode) # Multi-modal embeddings
KaizenSearchNode(HybridSearchNode)        # Advanced search capabilities
```

#### Phase 2: Workflow Integration (Months 3-4)
Seamless integration between legacy and enhanced nodes:

```python
# Mixed workflows with legacy and Kaizen nodes
workflow = WorkflowBuilder()

# Legacy node (unchanged)
workflow.add_node("LLMAgentNode", "legacy_llm", {
    "prompt": "Analyze this data: {data}",
    "model": "gpt-4"
})

# Kaizen-enhanced node with signature
@signature
class DataAnalysis:
    data: str = context.input()
    insights: List[str] = context.output()

kaizen_node = KaizenLLMAgentNode.from_signature(DataAnalysis)
workflow.add_node_instance(kaizen_node, "kaizen_llm")

# Connect legacy and Kaizen nodes
workflow.connect("legacy_llm", "kaizen_llm")
```

#### Phase 3: Migration Tools (Months 5-6)
Automated migration utilities:

```python
from kailash.kaizen.migration import NodeMigrator

# Automatic migration from legacy to Kaizen
migrator = NodeMigrator()

# Analyze existing workflow
legacy_workflow = workflow_builder.build()
migration_plan = migrator.analyze(legacy_workflow)

# Generate Kaizen signatures from existing prompts
signatures = migrator.generate_signatures(migration_plan)

# Create enhanced workflow
kaizen_workflow = migrator.migrate(legacy_workflow, signatures)
```

#### Phase 4: Deprecation Path (Year 2+)
Optional migration to pure Kaizen approach:

```python
# Pure Kaizen workflow (future state)
@signature.workflow
class DocumentProcessingPipeline:
    document: str = context.input()
    analysis: DocumentAnalysis = context.intermediate()
    summary: str = context.output()

# Automatic deployment across Nexus platforms
await pipeline.deploy_to_nexus(
    api=True,
    cli=True,
    mcp=True
)
```

## Consequences

### Positive
- **Zero Breaking Changes**: Existing workflows continue to work unchanged
- **Gradual Adoption**: Teams can migrate at their own pace
- **Investment Protection**: Existing AI node development remains valuable
- **Learning Curve**: Developers can learn Kaizen incrementally
- **Risk Mitigation**: Fallback to legacy nodes if issues arise

### Negative
- **Code Duplication**: Maintaining both legacy and enhanced versions
- **Complexity**: Dual interfaces increase system complexity
- **Performance Overhead**: Additional abstraction layers
- **Testing Burden**: Need to test both legacy and enhanced paths

## Alternatives Considered

### Option 1: Full Replacement
**Description**: Replace existing AI nodes with Kaizen versions
- **Pros**: Clean architecture, no duplication
- **Cons**: Breaking changes for existing users, high migration cost
- **Why Rejected**: Too disruptive for enterprise users

### Option 2: Separate Package
**Description**: Create separate kailash-kaizen package
- **Pros**: Clean separation, optional adoption
- **Cons**: Fragmented ecosystem, integration complexity
- **Why Rejected**: Doesn't leverage existing infrastructure effectively

### Option 3: Configuration-Based
**Description**: Add Kaizen features via configuration flags
- **Pros**: Single codebase, simpler maintenance
- **Cons**: Complex parameter system, unclear upgrade path
- **Why Rejected**: Insufficient separation of concerns

## Implementation Strategy

### Node Enhancement Priority

1. **High Priority** (Month 1)
   - KaizenLLMAgentNode (most used)
   - KaizenMemoryNode (foundational)
   - KaizenA2AAgentNode (orchestration)

2. **Medium Priority** (Month 2)
   - KaizenEmbeddingNode (multi-modal)
   - KaizenSearchNode (retrieval)
   - KaizenProviderNode (model management)

3. **Low Priority** (Month 3)
   - Specialized nodes (sentiment, NER, etc.)
   - Experimental nodes
   - Legacy compatibility helpers

### Migration Utilities

```python
# Migration assessment tool
class MigrationAssessment:
    def analyze_workflow(self, workflow):
        """Analyze workflow for migration opportunities."""
        return {
            "nodes_compatible": ["llm_agent_1", "memory_1"],
            "nodes_require_changes": ["custom_prompt_1"],
            "estimated_effort": "2-4 hours",
            "benefits": ["10x faster development", "auto-optimization"]
        }

# Signature generation from existing prompts
class SignatureGenerator:
    def from_prompt(self, prompt_template, examples=None):
        """Generate Kaizen signature from existing prompt."""
        # Analyze prompt structure
        # Infer input/output types
        # Generate signature class
        pass
```

### Testing Strategy

```python
# Dual testing for legacy and Kaizen modes
class TestKaizenLLMAgent:
    async def test_legacy_compatibility(self):
        """Ensure legacy functionality unchanged."""
        node = KaizenLLMAgentNode(kaizen_enabled=False)
        result = await node.execute(legacy_inputs)
        assert result == expected_legacy_result

    async def test_kaizen_enhancements(self):
        """Test new signature programming features."""
        node = KaizenLLMAgentNode.from_signature(TestSignature)
        result = await node.execute(signature_inputs)
        assert result.validates_against_signature()

    async def test_mixed_workflows(self):
        """Test legacy + Kaizen node integration."""
        workflow = create_mixed_workflow()
        results = await runtime.execute(workflow.build())
        assert workflow_produces_expected_results(results)
```

## Success Criteria

### Technical Metrics
- **Compatibility**: 100% backward compatibility with existing workflows
- **Performance**: Enhanced nodes perform within 10% of legacy nodes
- **Adoption**: 50% of new workflows use Kaizen features within 6 months
- **Migration**: 90% of existing workflows can be automatically assessed

### Business Metrics
- **User Satisfaction**: 90%+ satisfaction with migration experience
- **Support Load**: No increase in support tickets during migration
- **Time to Value**: 80% reduction in time to develop new AI workflows
- **Risk**: Zero production incidents related to migration

## Migration Timeline

### Month 1: Foundation
- Core enhanced nodes (KaizenLLMAgent, KaizenMemory)
- Basic signature programming interface
- Legacy compatibility testing

### Month 2: Expansion
- Additional enhanced nodes
- Migration assessment tools
- Mixed workflow testing

### Month 3: Tools
- Signature generation utilities
- Migration automation
- Documentation and examples

### Month 4: Validation
- Large-scale migration testing
- Performance optimization
- User feedback integration

### Month 5-6: Rollout
- Gradual rollout to user base
- Migration support and training
- Continuous improvement

## Related ADRs
- ADR-001: Kaizen Framework Architecture
- ADR-002: Signature Programming Model Implementation
- ADR-003: Memory System Architecture
- ADR-005: Security and Compliance Framework

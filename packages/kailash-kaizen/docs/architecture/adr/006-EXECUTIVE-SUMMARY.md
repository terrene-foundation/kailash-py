# ADR-006: Agent Base Architecture - Executive Summary

**Date**: 2025-10-01
**Status**: Proposed
**Related Documents**:
- ADR-006-agent-base-architecture.md (Full architecture decision)
- ADR-006-REQUIREMENTS-MATRIX.md (Comprehensive requirements)

---

## Problem Statement

Our Kaizen agent examples suffer from **massive code duplication** (1,400 lines across 3 agents, 91% duplicated), creating a maintenance nightmare and poor developer experience.

### Current State (Before)

```
SimpleQAAgent: 496 lines
ChainOfThoughtAgent: 442 lines
KaizenReActAgent: 599 lines
────────────────────────
Total: 1,537 lines

Code Duplication: 91%
```

**Impact**:
- Bug fixes require changes in 3+ locations
- Inconsistent behavior across agents
- Testing overhead (3x redundant tests)
- New agents require 400+ lines before domain logic

### Target State (After)

```
BaseAgent: 200-250 lines (SHARED)
────────────────────────
QAAgent: 15-20 lines
CoTAgent: 25-30 lines
ReActAgent: 30-35 lines
────────────────────────
Total: ~320 lines

Code Reduction: 90%+
Code Duplication: <5%
```

**Benefits**:
- Single source of truth for all shared functionality
- Consistent behavior across all agents
- Test once, use everywhere
- New agents in 15-35 lines

---

## Solution Overview

**Unified BaseAgent Architecture** using:
- **Strategy Pattern** for execution flows (SingleShot vs MultiCycle)
- **Mixin Composition** for optional capabilities (Logging, Error, Performance, Batch)
- **Extension Points** for specialization without modifying base

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     BaseAgent                               │
│                                                             │
│  Core: Framework init, provider detection, execution       │
│  Mixins: Logging, Error, Performance, Batch (opt-in)      │
│  Strategy: SingleShot (QA/CoT) | MultiCycle (ReAct)       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ inherits (15-35 lines)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│       QAAgent    │    CoTAgent    │    ReActAgent          │
│    (15 lines)    │   (25 lines)   │   (30 lines)           │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

1. **BaseAgent**: Handles all common functionality
   - Framework initialization (Kaizen + Core SDK)
   - Provider auto-detection (OpenAI/Ollama)
   - Signature compilation and execution
   - Configuration management
   - Extension point definitions

2. **Execution Strategies**: Decoupled execution patterns
   - `SingleShotStrategy`: For QA and CoT agents (execute once)
   - `MultiCycleStrategy`: For ReAct agent (multi-cycle reasoning)
   - Extension hooks: pre_execute, parse_result, post_execute

3. **Specialized Agents**: Minimal implementations
   - Define signature (structured I/O)
   - Override specific behaviors via hooks
   - 15-35 lines vs 400-600 lines previously

---

## Implementation Comparison

### Before: SimpleQAAgent (496 lines)

```python
class SimpleQAAgent:
    def __init__(self, config: QAConfig):
        # 80 lines: Framework initialization
        # 30 lines: Provider auto-detection
        # 20 lines: Logging setup
        # 30 lines: Performance tracking
        self._initialize_framework()

    def _initialize_framework(self):
        # 80 lines of duplicated initialization

    def ask(self, question: str, context: str = ""):
        # 100 lines: Execution logic
        # 50 lines: Error handling
        # 20 lines: Result parsing
        # ...

    def _error_response(self, ...):
        # 30 lines: Error formatting

    def batch_ask(self, questions: list):
        # 40 lines: Batch processing
```

### After: QAAgent (15 lines)

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField


class QASignature(Signature):
    question: str = InputField(desc="The question to answer")
    context: str = InputField(desc="Additional context", default="")

    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")
    reasoning: str = OutputField(desc="Brief reasoning")


class QAAgent(BaseAgent):
    """Q&A Agent - 15 lines vs 496 lines previously."""

    def create_signature(self) -> Signature:
        return QASignature()

    def _get_agent_id(self) -> str:
        return "qa_agent"


# Usage (exactly the same as before)
config = BaseAgentConfig(temperature=0.1)
agent = QAAgent(config)
result = agent.execute(
    question="What is machine learning?",
    context="Explain for general audience"
)
```

**Result**: 33x reduction in code (496 → 15 lines)

---

## Requirements Summary

### Functional Requirements (20 Total)

**Core Base Agent** (FR-001 to FR-009):
- Framework initialization with auto-detection
- Signature-based and fallback execution
- Unified configuration with feature flags
- Standardized error handling
- Optional capabilities (logging, performance, batch)

**Execution Strategies** (FR-010 to FR-013):
- SingleShotStrategy for QA/CoT
- MultiCycleStrategy for ReAct (10 cycles max)
- Extension hooks at all critical points

**Specialized Agents** (FR-014 to FR-020):
- QA Agent: Q&A with confidence scoring, batch processing
- CoT Agent: 5-step reasoning with performance tracking
- ReAct Agent: MCP tools, multi-cycle, action history

### Non-Functional Requirements (19 Total)

**Performance** (NFR-001 to NFR-007):
- Framework init: <100ms
- Agent creation: <200ms
- QA execution: <500ms average
- CoT execution: <1000ms average
- Abstraction overhead: <1%

**Quality** (NFR-008 to NFR-013):
- Test coverage: 95%+ for base architecture
- Code reduction: 90%+ from current
- Duplication: <5%
- Backward compatibility: 100%
- Zero functional regression

**Security & Scalability** (NFR-014 to NFR-019):
- API key protection (no logging)
- 100+ concurrent agents
- 1000+ batch items
- 50+ ReAct cycles

---

## Extension Points

### BaseAgent Extension Points (7 total)

1. **create_signature()**: Define structured I/O
2. **_get_agent_id()**: Set agent identifier
3. **_get_framework_config_extensions()**: Add framework config
4. **_get_agent_config_extensions()**: Add agent config
5. **_create_execution_strategy()**: Override execution pattern
6. **_get_performance_targets()**: Set performance targets
7. **post_execute()**: Process results before returning

### Strategy Extension Points

**SingleShotStrategy** (3 hooks):
- `pre_execute()`: Prepare inputs
- `parse_result()`: Parse execution result
- `post_execute()`: Post-process result

**MultiCycleStrategy** (4 hooks):
- `pre_cycle()`: Prepare cycle inputs
- `parse_cycle_result()`: Parse cycle result
- `should_terminate()`: Check termination
- `extract_observation()`: Extract observation

**Total**: 14 extension points for complete customization

---

## Implementation Plan

### Phase 1: Foundation (3 days)

**Deliverables**:
- BaseAgent class (200-250 lines)
- BaseAgentConfig with feature flags
- SingleShotStrategy and MultiCycleStrategy
- Comprehensive Tier 1 unit tests (95%+ coverage)

**Success Criteria**:
- All unit tests pass
- <100ms framework init, <200ms agent creation
- Zero impact on existing agents

### Phase 2: Specialized Agents (4 days)

**Deliverables**:
- QAAgent (15-20 lines)
- CoTAgent (25-30 lines)
- ReActAgent (30-35 lines)
- Tier 2 integration tests (real LLMs)
- Tier 3 E2E tests (complete workflows)

**Success Criteria**:
- All tests pass (Tier 1-3)
- Functional parity with old implementations
- Performance targets met

### Phase 3: Migration & Documentation (3 days)

**Deliverables**:
- Migration guide for existing code
- Extension point guide with examples
- Performance comparison report
- Updated architecture documentation

**Success Criteria**:
- Migration guide validated
- All documentation examples working
- Zero regressions

### Phase 4: Polish (Parallel with Phase 2-3)

**Deliverables**:
- Mixin implementations
- Debugging utilities
- Performance optimizations

**Total Timeline**: ~2.5 weeks (10 working days)

---

## Testing Strategy

### 3-Tier Testing Approach

**Tier 1: Unit Tests** (No external dependencies)
- 95%+ coverage for base architecture
- Mock all external dependencies
- Fast execution (<1 second total)

**Tier 2: Integration Tests** (Real infrastructure)
- Real LLM providers (OpenAI, Ollama)
- NO MOCKING of LLM calls
- Validate actual behavior

**Tier 3: E2E Tests** (Complete workflows)
- Run exact examples from documentation
- Validate end-to-end functionality
- Test all agent types

**Total Tests**: ~1,500-2,000 lines of test code

---

## Migration Path

### Backward Compatibility Strategy

**100% backward compatible** via compatibility shims:

```python
# Old code continues to work
from examples.simple_qa.workflow import SimpleQAAgent, QAConfig

config = QAConfig(temperature=0.1)
agent = SimpleQAAgent(config)
result = agent.ask("What is ML?")  # Still works!
```

**Compatibility shim** (temporary, deprecated):

```python
# examples/simple_qa/workflow.py
from kaizen.agents import QAAgent as NewQAAgent
from kaizen.core import BaseAgentConfig
import warnings

class SimpleQAAgent(NewQAAgent):
    def __init__(self, config):
        warnings.warn("SimpleQAAgent is deprecated. Use kaizen.agents.QAAgent instead.")
        super().__init__(config)

    def ask(self, question: str, context: str = ""):
        return self.execute(question=question, context=context)

QAConfig = BaseAgentConfig  # Alias for compatibility
```

**Timeline**:
- **v0.10.0**: New architecture available, old works with warnings
- **v0.11.0**: Old implementations removed

---

## Success Metrics

### Quantitative Metrics

| Metric | Before | After | Target | Status |
|--------|--------|-------|--------|---------|
| Total Lines of Code | 1,537 | ~320 | 90% reduction | Pending |
| Code Duplication | 91% | <5% | <5% | Pending |
| Test Coverage (base) | N/A | TBD | 95%+ | Pending |
| New Agent Creation | 400-600 lines | 15-35 lines | <50 lines | Pending |
| Framework Init Time | Varies | TBD | <100ms | Pending |
| Agent Creation Time | Varies | TBD | <200ms | Pending |
| Bug Fix Locations | 3+ places | 1 place | 1 place | Pending |

### Qualitative Metrics

- **Developer Experience**: Dramatically improved (create agent in <30 min vs 2-3 hours)
- **Maintainability**: Single source of truth for all shared functionality
- **Consistency**: All agents behave identically for common operations
- **Extensibility**: Easy to add new agent types or modify behavior
- **Testing**: Test shared functionality once, use everywhere

---

## Risk Assessment

### Critical Risks (Mitigation Required)

1. **Performance Regression** (Medium probability, High impact)
   - **Mitigation**: Comprehensive benchmarks, profiling, optimization
   - **Status**: Planned for Phase 4

2. **Breaking Changes Not Caught** (Medium probability, High impact)
   - **Mitigation**: Extensive Tier 2-3 tests, manual validation, compatibility shims
   - **Status**: Planned for Phase 2

3. **Abstraction Too Complex** (Medium probability, Medium impact)
   - **Mitigation**: User testing, clear documentation, examples for all extension points
   - **Status**: Planned for Phase 3

### Low Risks (Accept)

- Documentation drift → Automated doc tests
- Mixin interaction issues → Comprehensive mixin tests
- Edge case bugs → 95%+ test coverage

---

## Decision Rationale

### Why This Approach?

**Considered Alternatives**:
1. **Deep inheritance hierarchy**: Too rigid, diamond problem
2. **Hook-only approach**: Insufficient for MultiCycle execution
3. **Keep current duplication**: Unacceptable technical debt
4. **Configuration-driven**: Too much "magic", poor DX

**Why Strategy Pattern + Mixins**:
- ✅ Separates execution logic from base agent
- ✅ Easy to test in isolation
- ✅ Supports different execution patterns (SingleShot, MultiCycle, Streaming)
- ✅ Mixins provide optional capabilities without inheritance complexity
- ✅ Pythonic and familiar to developers
- ✅ Minimal performance overhead
- ✅ Clear extension points

### Alignment with Ultrathink Analysis

The deep-analyst deep analysis identified:
- **8 critical/high risks** → All addressed by this architecture
- **Inconsistent error handling** → Standardized in BaseAgent
- **No configuration approach** → BaseAgentConfig with feature flags
- **Performance tracking varies** → PerformanceMixin
- **Logging creates duplicates** → LoggingMixin with handler checks

**Recommendation alignment**: 100%

---

## Next Steps

### Immediate Actions

1. **Review & Approval** (1 day)
   - Review ADR-006 with team
   - Gather feedback on architecture
   - Approve or iterate

2. **Phase 1 Implementation** (3 days)
   - Create BaseAgent and strategies
   - Write comprehensive unit tests
   - Validate performance targets

3. **Phase 2 Implementation** (4 days)
   - Implement specialized agents
   - Write integration and E2E tests
   - Update all examples

4. **Phase 3 Documentation** (3 days)
   - Create migration guide
   - Create extension point guide
   - Update architecture docs

### Long-Term Vision

**Extensibility**:
- Add StreamingStrategy for streaming responses
- Add BatchStrategy for efficient batch processing
- Add more mixins as needed (Caching, RateLimiting, etc.)

**Performance**:
- Optimize framework initialization (<100ms consistently)
- Add lazy loading for optional features
- Implement agent pooling for high-throughput scenarios

**Developer Experience**:
- Agent creation wizards/templates
- Interactive extension point selector
- Performance profiling tools

---

## Conclusion

The Unified BaseAgent Architecture solves the massive code duplication problem (91% → <5%) while dramatically improving developer experience (400+ lines → 15-35 lines for new agents).

**Key Benefits**:
- 90%+ code reduction (1,537 → ~320 lines)
- Single source of truth for all shared functionality
- Consistent behavior across all agents
- Easy to extend and customize
- 100% backward compatible
- Comprehensive testing (Tier 1-3)
- Clear migration path

**Recommendation**: **APPROVE** and proceed with phased implementation.

---

## References

### Related Documents
- **ADR-006-agent-base-architecture.md**: Full architecture decision with detailed design
- **ADR-006-REQUIREMENTS-MATRIX.md**: Comprehensive functional and non-functional requirements
- **ADR-002-signature-programming-model.md**: Signature programming foundation
- **ADR-005-testing-strategy-alignment.md**: Testing strategy for all tiers

### Code References
- Current implementations: `examples/1-single-agent/*/workflow.py`
- Proposed location: `src/kaizen/core/base_agent.py`
- Test location: `tests/unit/core/test_base_agent.py`

### External References
- Strategy Pattern: Gang of Four design patterns
- Mixin Composition: Python multiple inheritance patterns
- Ultrathink Analysis: Deep failure analysis (referenced context)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-01
**Next Review**: After Phase 1 completion

# ADR-016: Universal Tool Integration for All 25 Kaizen Agents

**Status**: ✅ Accepted
**Date**: 2025-10-22
**Deciders**: Kaizen Team
**Related**: ADR-012 (BaseAgent Tool Integration), ADR-013 (Objective Convergence), ADR-014 (MCP Integration)

## Context

### Current State

BaseAgent has full tool calling infrastructure since ADR-012:
- ✅ `tool_registry` parameter in BaseAgent.__init__()
- ✅ `mcp_servers` parameter for MCP integration
- ✅ 4 tool methods: `has_tool_support()`, `discover_tools()`, `execute_tool()`, `execute_tool_chain()`
- ✅ 12 builtin tools (file, HTTP, bash, web)
- ✅ Approval workflows with danger-level based controls
- ✅ 182 tests passing (50 tool integration + 132 BaseAgent)

**Gap**: 25 agent classes extending BaseAgent do NOT expose tool_registry parameter.

### Agent Inventory

**Specialized Agents (11)**:
1. SimpleQAAgent - Question answering
2. ChainOfThoughtAgent - Step-by-step reasoning
3. ReActAgent - Reasoning + acting cycles
4. RAGResearchAgent - Retrieval-augmented generation
5. CodeGenerationAgent - Code synthesis
6. MemoryAgent - Memory-enhanced conversations
7. BatchProcessingAgent - High-throughput processing
8. HumanApprovalAgent - Human-in-the-loop workflows
9. ResilientAgent - Error recovery and retry
10. SelfReflectionAgent - Self-evaluation and improvement
11. StreamingChatAgent - Streaming responses

**Multi-Modal Agents (3)**:
12. VisionAgent - Image analysis (Ollama + GPT-4V)
13. TranscriptionAgent - Audio transcription (Whisper)
14. MultiModalAgent - Unified orchestration

**Coordination Agents (11)**:
15. SupervisorAgent - Task delegation
16. WorkerAgent - Task execution
17. CoordinatorAgent - Progress monitoring
18. DebateModeratorAgent - Argument moderation
19. DebateParticipantAgent - Argument generation
20. DebateJudgeAgent - Decision making
21. ConsensusModeratorAgent - Consensus facilitation
22. ConsensusParticipantAgent - Proposal generation
23. ConsensusJudgeAgent - Agreement validation
24. HandoffAgent - Task handoff coordination
25. SequentialPipelineAgent - Sequential execution

### Requirements

**R1: Universal Tool Support Pattern**
- ALL 25 agents MUST support `tool_registry` and `mcp_servers` parameters
- Parameters MUST be optional (None by default)
- 100% backward compatibility (no breaking changes)

**R2: Appropriate Tool Usage by Agent Type**

**Specialized Agents**: Full tool calling autonomy
- ReActAgent: Execute tools in reasoning loops (objective convergence)
- ChainOfThoughtAgent: Tools for verification and fact-checking
- RAGResearchAgent: Tools for document retrieval, web search, file access
- CodeGenerationAgent: Tools for file operations, execution, testing
- MemoryAgent: Tools for external memory stores (databases, files)
- BatchProcessingAgent: Tools for data access and transformation
- HumanApprovalAgent: Tools for approval workflows (pre-execution checks)
- ResilientAgent: Tools for health checks, fallback operations
- SelfReflectionAgent: Tools for metric collection, validation
- StreamingChatAgent: Tools for real-time data access
- SimpleQAAgent: Optional tools for fact verification

**Multi-Modal Agents**: Selective tool calling
- VisionAgent: Tools for image file access, OCR, preprocessing
- TranscriptionAgent: Tools for audio file access, format conversion
- MultiModalAgent: Orchestrate tool calls across modalities

**Coordination Agents**: Delegated tool calling
- SupervisorAgent: Tools for task decomposition, resource allocation
- WorkerAgent: Execute specialized tools assigned by supervisor
- CoordinatorAgent: Tools for monitoring, metrics collection
- Debate agents: Tools for evidence gathering, fact-checking
- Consensus agents: Tools for data validation, agreement tracking
- Handoff/Pipeline agents: Tools for state persistence, data transfer

**R3: Integration with Existing Infrastructure**

- Tool execution MUST integrate with MultiCycleStrategy for iterative agents
- Tool calls MUST respect objective convergence (ADR-013: `tool_calls` field)
- Tool approvals MUST use existing ControlProtocol (ADR-011)
- MCP tools MUST integrate seamlessly with builtin tools

**R4: Production Readiness**

- 3 tests per agent minimum (75 total tests)
- NO MOCKING in Tier 2-3 tests (real LLM, real tools)
- All tests MUST pass before merge
- 100% backward compatibility validation

## Decision

**Add `tool_registry` and `mcp_servers` parameters to all 25 agent __init__() methods.**

### Implementation Pattern

All agents will follow this universal pattern:

```python
from typing import Any, Dict, List, Optional
from kaizen.core.base_agent import BaseAgent
from kaizen.tools.registry import ToolRegistry

class AnyAgent(BaseAgent):
    """Production-ready agent with optional tool calling."""

    def __init__(
        self,
        # Existing agent-specific parameters
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        # ... other existing parameters ...
        config: Optional[AgentConfig] = None,

        # NEW: Universal tool parameters (ALWAYS at end, before **kwargs)
        tool_registry: Optional[ToolRegistry] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ):
        """
        Initialize agent with optional tool calling.

        Args:
            # ... existing parameter docs ...
            tool_registry: Optional tool registry for autonomous tool execution
            mcp_servers: Optional MCP server configurations for MCP tool access
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Build config from parameters (existing pattern)
        if config is None:
            config = AgentConfig()
            # ... apply parameter overrides ...

        # Initialize BaseAgent with tool support
        super().__init__(
            config=config,
            signature=AgentSignature(),
            strategy=strategy,  # if applicable
            tools="all"  # Enable tools via MCP
            mcp_servers=mcp_servers,       # NEW: Pass through
            **kwargs,
        )

        # Agent-specific initialization
        # ...
```

**Key Points**:
1. **Position**: `tool_registry` and `mcp_servers` ALWAYS appear after all agent-specific parameters, before `**kwargs`
2. **Default**: Both parameters default to `None` (opt-in)
3. **Pass-through**: Both parameters passed directly to `super().__init__()` with no modification
4. **Documentation**: Clear docstring explaining tool support (copy from template)

### Tool Execution Integration Points

**For Iterative Agents (ReAct, ChainOfThought, RAG)**:

Integration with MultiCycleStrategy execution loop:

```python
class ReActAgent(BaseAgent):
    def solve_task(self, task: str, context: str = "") -> Dict[str, Any]:
        """Execute ReAct cycles with optional tool calling."""

        # Execute via BaseAgent with MultiCycleStrategy
        result = self.run(
            task=task.strip(),
            context=context.strip() if context else "",
            available_tools=self.available_tools,  # Discovered tools
            previous_actions=self.action_history,
        )

        # MultiCycleStrategy handles:
        # 1. Check result["tool_calls"] for objective convergence
        # 2. If tool_calls present → execute via self.execute_tool_chain()
        # 3. Feed results back to LLM in next cycle
        # 4. Continue until tool_calls is empty (converged)

        return result
```

**Implementation Note**: Tool execution logic resides in MultiCycleStrategy, NOT in agent classes. Agents only need to:
1. Pass `tool_registry` to BaseAgent
2. Optionally discover tools and pass to LLM context
3. Trust MultiCycleStrategy to handle tool execution loops

**For Single-Shot Agents (SimpleQA, Vision, Transcription)**:

Tool calling is optional, used for data access:

```python
class SimpleQAAgent(BaseAgent):
    def ask(self, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Answer question with optional tool support for fact-checking."""

        # Tools discovered automatically if tool_registry provided
        # LLM can request tools via tool_calls field in response
        # BaseAgent + AsyncSingleShotStrategy handle execution

        result = self.run(question=question)

        # Tool execution (if any) already completed by strategy
        return result
```

**For Coordination Agents (Supervisor, Worker, Coordinator)**:

Tools delegated or monitored:

```python
class SupervisorAgent(BaseAgent):
    def delegate_tasks(self, request: str) -> List[Dict[str, Any]]:
        """Delegate tasks with optional tool support for decomposition."""

        # Supervisor can use tools for:
        # - Task decomposition (analyze request complexity)
        # - Resource allocation (check available workers)
        # - Schema validation (verify task formats)

        result = self.run(request=request, num_tasks=3)

        # Tools provide additional context for delegation
        return result
```

## Consequences

### Positive

1. **Universal Capability**: All 25 agents gain tool calling autonomously
2. **Consistent API**: Same pattern across all agent types
3. **Backward Compatible**: Existing code works unchanged
4. **Opt-In Design**: Tools disabled by default, enabled when needed
5. **Production Ready**: Full test coverage with real infrastructure
6. **Future-Proof**: MCP integration ready for all agents

### Negative

1. **Parameter Proliferation**: Every agent __init__() gains 2+ parameters
2. **Documentation Burden**: 25 agent docstrings need updating
3. **Test Expansion**: 75 new tests required (3 per agent × 25)
4. **Migration Effort**: 25 agent files need modification
5. **Potential Confusion**: Users might not understand when to use tools

### Mitigations

**Parameter Proliferation**:
- Use `**kwargs` to accept tool parameters without explicit declarations
- Future: Consider `ToolConfig` wrapper to reduce parameter count

**Documentation Burden**:
- Create standard docstring template (copy-paste)
- Update examples/autonomy/tools/ with all agent types

**Test Expansion**:
- Reuse test patterns across similar agents
- Focus Tier 2-3 tests on high-value agents first
- Batch test execution by phase

**Migration Effort**:
- Provide code template (exact pattern to follow)
- Automate via search-replace where possible
- Phased rollout (4 phases, prioritize high-value agents)

**User Confusion**:
- Clear documentation on when to enable tools
- Examples for each agent type showing tool usage
- Default to disabled (explicit opt-in prevents accidental tool execution)

## Implementation Strategy

### Phase 1: High-Value Specialized Agents (Week 1, 3 agents)

**Priority**: Agents with immediate tool execution value

1. **ReActAgent**: Autonomous tool calling in reasoning loops
2. **RAGResearchAgent**: Document retrieval, web search, file access
3. **CodeGenerationAgent**: File operations, code execution, testing

**Effort**: 3 days
- 1 day: Implementation (3 agents × 30 min each + buffer)
- 1 day: Testing (9 tests: 3 per agent)
- 1 day: Documentation and validation

**Tests per Agent**:
- Test 1: Tool discovery with registry
- Test 2: Tool execution in agent workflow
- Test 3: Backward compatibility (no tools)

**Deliverables**:
- 3 modified agent files
- 9 new tests (all passing)
- Updated examples/autonomy/tools/ with 3 examples
- Migration guide for remaining agents

### Phase 2: All Specialized Agents (Week 2, 8 agents)

**Priority**: Remaining specialized agents

4. ChainOfThoughtAgent
5. MemoryAgent
6. SimpleQAAgent
7. BatchProcessingAgent
8. HumanApprovalAgent
9. ResilientAgent
10. SelfReflectionAgent
11. StreamingChatAgent

**Effort**: 4 days
- 2 days: Implementation (8 agents × 30 min each)
- 1 day: Testing (24 tests: 3 per agent)
- 1 day: Integration validation and documentation

**Tests per Agent**: Same 3-test pattern as Phase 1

**Deliverables**:
- 8 modified agent files
- 24 new tests (all passing)
- Updated documentation for all specialized agents

### Phase 3: Multi-Modal Agents (Week 3, 3 agents)

**Priority**: Vision and audio agents

12. VisionAgent
13. TranscriptionAgent
14. MultiModalAgent

**Effort**: 2 days
- 1 day: Implementation (3 agents × 30 min each + buffer)
- 0.5 day: Testing (9 tests: 3 per agent)
- 0.5 day: Multi-modal specific examples

**Special Considerations**:
- Vision tools: Image file access, preprocessing
- Audio tools: Audio file access, format conversion
- Multi-modal orchestration: Cross-modality tool chains

**Deliverables**:
- 3 modified agent files
- 9 new tests (all passing)
- Multi-modal tool usage examples

### Phase 4: Coordination Agents (Week 4, 11 agents)

**Priority**: Multi-agent coordination patterns

15-25. All coordination agents (Supervisor, Worker, Coordinator, Debate×3, Consensus×3, Handoff, Pipeline)

**Effort**: 5 days
- 3 days: Implementation (11 agents × 30 min each)
- 1.5 days: Testing (33 tests: 3 per agent)
- 0.5 day: Multi-agent coordination examples

**Special Considerations**:
- Supervisor: Task decomposition tools
- Worker: Specialized tool execution
- Coordinator: Monitoring and metrics tools
- Debate/Consensus: Evidence gathering tools
- Handoff/Pipeline: State persistence tools

**Deliverables**:
- 11 modified agent files
- 33 new tests (all passing)
- Multi-agent tool coordination examples

### Total Effort Estimate

**Timeline**: 4 weeks (phased rollout)
**Total Implementation**: 14 days
**Total Testing**: 7 days (75 tests total)
**Total Documentation**: 3 days

**Breakdown**:
- Phase 1: 3 days (3 agents)
- Phase 2: 4 days (8 agents)
- Phase 3: 2 days (3 agents)
- Phase 4: 5 days (11 agents)

**Buffer**: +20% for integration issues, edge cases, reviews

## Testing Strategy

### Test Template (3 Tests per Agent)

**Location**: `tests/unit/agents/test_{agent_name}_tool_integration.py`

```python
"""
Test {AgentName} tool integration.

3-tier testing strategy:
- Tier 1 (Unit): Mocked LLM, real tool registry
- Tier 2 (Integration): Real Ollama LLM, real tools, real file system
- Tier 3 (E2E): Real OpenAI LLM, real tools, production validation
"""

import pytest
import asyncio
from kaizen.agents import {AgentName}
from kaizen.agents.{module}.{agent_file} import {AgentConfig}
from kaizen.tools.registry import ToolRegistry



class Test{AgentName}ToolDiscovery:
    """Test tool discovery capabilities."""

    def test_tool_discovery_with_registry(self):
        """Verify agent can discover tools when registry provided."""

        # 12 builtin tools enabled via MCP

        agent = {AgentName}(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        assert agent.has_tool_support()

        # Discover all tools
        tools = asyncio.run(agent.discover_tools())
        assert len(tools) == 12  # 12 builtin tools

        # Discover safe tools only
        safe_tools = asyncio.run(agent.discover_tools(safe_only=True))
        assert all(t.danger_level == DangerLevel.SAFE for t in safe_tools)


class Test{AgentName}ToolExecution:
    """Test tool execution in agent workflow (Tier 2)."""

    @pytest.mark.tier2
    def test_tool_execution_in_workflow(self, tmp_path):
        """Verify agent executes tools during workflow (real LLM)."""
        # Setup real file for tool operations
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Setup registry

        # 12 builtin tools enabled via MCP

        # Create agent with tools
        agent = {AgentName}(
            llm_provider="ollama",  # Real LLM (free, local)
            model="llama2",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Execute workflow that should use tools
        result = agent.{method_name}("Read file: " + str(test_file))

        # Verify tool was called and result contains file content
        # (Exact verification depends on agent type)
        assert result is not None
        # Additional agent-specific assertions


class Test{AgentName}BackwardCompatibility:
    """Test backward compatibility without tools."""

    def test_agent_works_without_tools(self):
        """Verify agent works without tool_registry (backward compatibility)."""
        agent = {AgentName}(
            llm_provider="mock",
            model="mock-model"
            # NO tool_registry parameter
        )

        # Agent should work without tool support
        assert not agent.has_tool_support()

        # Agent's main method should still work
        result = agent.{method_name}("Test query")
        assert result is not None
        # Additional agent-specific assertions
```

### Test Prioritization

**Tier 1 (Unit)**: All 75 tests
- Fast execution (<1s per test)
- Mocked LLM providers
- Real tool registry, real tool definitions
- Focus on parameter passing, initialization

**Tier 2 (Integration)**: 25 tests (1 per agent)
- Real Ollama LLM (free, local)
- Real file system operations
- Real tool execution with approval workflows
- Focus on tool execution integration

**Tier 3 (E2E)**: 3 tests (high-value agents only)
- Real OpenAI LLM (budget-controlled)
- Production validation
- ReActAgent, RAGResearchAgent, CodeGenerationAgent
- Focus on complete tool workflows

### Success Criteria

**Per Agent**:
- ✅ 3 tests passing (discovery, execution, backward compatibility)
- ✅ No breaking changes to existing tests
- ✅ Docstring updated with tool parameters
- ✅ Example added to examples/autonomy/tools/

**Per Phase**:
- ✅ All agents in phase have 3 passing tests
- ✅ Integration tests pass with real LLM
- ✅ Documentation updated
- ✅ Code review approved

**Overall**:
- ✅ 75 tests passing (25 agents × 3 tests)
- ✅ 100% backward compatibility
- ✅ All 25 agents support tool_registry parameter
- ✅ Examples demonstrate tool usage for all agent types

## Migration Guide

### For Developers Adding Tools to Agents

**Step 1**: Modify `__init__()` signature

```python
def __init__(
    self,
    # ... existing parameters ...
    config: Optional[AgentConfig] = None,
    tool_registry: Optional[ToolRegistry] = None,  # ADD
    mcp_servers: Optional[List[Dict[str, Any]]] = None,  # ADD
    **kwargs,
):
```

**Step 2**: Update docstring

```python
    """
    Initialize agent with optional tool calling.

    Args:
        # ... existing parameter docs ...
        tool_registry: Optional tool registry for autonomous tool execution
        mcp_servers: Optional MCP server configurations for MCP tool access
        **kwargs: Additional arguments passed to BaseAgent
    """
```

**Step 3**: Pass parameters to BaseAgent

```python
    super().__init__(
        config=config,
        signature=signature,
        strategy=strategy,  # if applicable
        tools="all"  # Enable tools via MCP
        mcp_servers=mcp_servers,       # ADD
        **kwargs,
    )
```

**Step 4**: Write 3 tests (use template above)

**Step 5**: Add example to examples/autonomy/tools/{agent_name}_example.py

### For Users Enabling Tools in Agents

**Without Tools (backward compatible)**:
```python
from kaizen.agents import ReActAgent

agent = ReActAgent(llm_provider="openai", model="gpt-4")
result = agent.solve_task("Calculate tax on $100")
```

**With Tools (opt-in)**:
```python
from kaizen.agents import ReActAgent
# Tools auto-configured via MCP


# Setup tools

# 12 builtin tools enabled via MCP

# Create agent with tools
agent = ReActAgent(
    llm_provider="openai",
    model="gpt-4",
    tools="all"  # Enable 12 builtin tools via MCP
)

# Agent can now autonomously execute tools
result = agent.solve_task("Read file data.txt and calculate sum")
```

## Alternatives Considered

### Alternative 1: Implicit Tool Discovery

**Approach**: BaseAgent automatically discovers tools from global registry.

**Pros**:
- No parameter changes needed
- Zero configuration for users

**Cons**:
- ❌ Implicit behavior (hard to debug)
- ❌ No way to disable tools
- ❌ Global state (not thread-safe)
- ❌ Violates explicit-is-better-than-implicit

**Rejected**: Too much magic, reduces control.

### Alternative 2: Separate ToolAgent Mixin

**Approach**: Create `ToolAgentMixin` with tool methods, agents opt-in via inheritance.

```python
class ReActAgent(BaseAgent, ToolAgentMixin):
    pass
```

**Pros**:
- Clean separation of concerns
- Opt-in via inheritance

**Cons**:
- ❌ Breaking change (modifies class hierarchy)
- ❌ Multiple inheritance complexity
- ❌ Doesn't work for existing agent instances
- ❌ Still needs registry parameter

**Rejected**: More complex than parameter approach.

### Alternative 3: Decorator Pattern

**Approach**: Wrap agents with `@with_tools` decorator.

```python
@with_tools(registry)
class ReActAgent(BaseAgent):
    pass
```

**Pros**:
- Non-invasive
- Declarative

**Cons**:
- ❌ Runtime decoration complexity
- ❌ Harder to test
- ❌ Doesn't work for dynamic tool configuration
- ❌ Obscures initialization parameters

**Rejected**: Too clever, reduces clarity.

### Alternative 4: Tool-Specific Agent Subclasses

**Approach**: Create `ToolEnabledReActAgent` subclass for each agent.

**Pros**:
- Clean separation
- Explicit naming

**Cons**:
- ❌ 25 new classes to maintain
- ❌ Code duplication
- ❌ Confusing for users (which class to use?)
- ❌ Doesn't scale

**Rejected**: Maintenance nightmare.

## References

### Related ADRs
- **ADR-012**: BaseAgent Tool Integration (foundation)
- **ADR-013**: Objective Convergence Detection (tool_calls field)
- **ADR-014**: MCP Integration Comprehensive (MCP tools)
- **ADR-011**: Control Protocol Architecture (approval workflows)
- **ADR-006**: Agent Base Architecture (BaseAgent design)

### Documentation
- `docs/features/baseagent-tool-integration.md` - Tool integration guide
- `examples/autonomy/tools/` - Tool usage examples
- `tests/unit/tool_integration/` - Tool integration tests

### Implementation Files
- `src/kaizen/core/base_agent.py` - BaseAgent with tool support
- `src/kaizen/tools/registry.py` - ToolRegistry
- `src/kaizen/tools/executor.py` - ToolExecutor
- `src/kaizen/tools/builtin/` - 12 builtin tools

## Approval

**Approved by**: Kaizen Team
**Date**: 2025-10-22

**Next Steps**:
1. Begin Phase 1 implementation (ReActAgent, RAGResearchAgent, CodeGenerationAgent)
2. Create test templates and migration guide
3. Update documentation with tool integration patterns
4. Coordinate with todo-manager for task tracking

# Component Ownership Matrix: Claude Agent SDK → Kaizen Framework

**Date**: 2025-10-18
**Purpose**: Define which Kaizen layer owns each Claude Agent SDK component
**Status**: Strategic Architecture

---

## Ownership Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                           │
│  (User Code: Custom Agents, Workflows, Business Logic)          │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT LAYER (BaseAgent)                       │
│  - Mixins (Logging, Performance, Error Handling)                │
│  - Specialized Agents (RAG, CoT, ReAct, etc.)                   │
│  - Agent-specific hooks and strategies                          │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    KAIZEN CORE FRAMEWORK                         │
│  - Control Protocol                                              │
│  - Hook System                                                   │
│  - Permission System                                             │
│  - State Persistence                                             │
│  - Interrupt Mechanism                                           │
│  - Event System                                                  │
│  - Tracing System                                                │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  INTEGRATION LAYER                               │
│  DataFlow       │    Nexus     │      MCP      │    Other        │
│  (Database)     │ (Multi-Chan) │   (Tools)     │  (Custom)       │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    KAILASH CORE SDK                              │
│  - WorkflowBuilder                                               │
│  - LocalRuntime / AsyncLocalRuntime                              │
│  - Node System                                                   │
│  - Parameter System                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Assignment Table

| Component | Current Status | Should Be Owned By | Priority | Reason |
|-----------|---------------|-------------------|----------|---------|
| **Control & Communication** | | | | |
| Bidirectional Protocol | ❌ Missing | Kaizen Core | P0 | Universal need for all agents |
| ControlChannel Interface | ❌ Missing | Kaizen Core | P0 | Abstract transport layer |
| SSE Transport | ❌ Missing | Nexus Integration | P1 | HTTP-specific, Nexus owns HTTP |
| WebSocket Transport | ❌ Missing | Nexus Integration | P2 | HTTP-specific, Nexus owns HTTP |
| Stdio Transport | ❌ Missing | MCP Integration | P1 | MCP-specific, MCP owns stdio |
| CLI Transport | ❌ Missing | Kaizen Core | P1 | CLI is core use case |
| Protocol Versioning | ❌ Missing | Kaizen Core | P2 | Framework-wide concern |
| **Hooks & Extension** | | | | |
| Hook System (base) | ⚠️ Partial (stubs) | Kaizen Core | P0 | Universal extension mechanism |
| ExecutionContext | ❌ Missing | Kaizen Core | P0 | Provides runtime context to hooks |
| Pre-execution Hooks | ✅ BaseAgent | BaseAgent | - | Agent-specific logic |
| Post-execution Hooks | ✅ BaseAgent | BaseAgent | - | Agent-specific logic |
| Runtime Intervention | ❌ Missing | Kaizen Core | P0 | Framework-level pause/resume |
| Error Recovery Hooks | ⚠️ Partial | BaseAgent | P1 | Agent-specific error handling |
| **State & Persistence** | | | | |
| Checkpoint System | ❌ Missing | Kaizen Core | P0 | All agents need save/resume |
| State Serialization | ❌ Missing | Kaizen Core | P0 | Generic state persistence |
| DataFlow Persistence | ❌ Missing | DataFlow Integration | P0 | Database-backed checkpoints |
| Nexus Session Mgmt | ✅ Nexus | Nexus Integration | - | Already correctly placed |
| Rollback/Replay | ❌ Missing | Kaizen Core | P1 | Framework-wide debugging |
| **Permissions & Guardrails** | | | | |
| Permission System | ❌ Missing | Kaizen Core | P0 | Enterprise security requirement |
| Permission Policies | ❌ Missing | Kaizen Core | P0 | Policy engine for all agents |
| Approval Prompts | ⚠️ HumanApprovalAgent | Kaizen Core (hook) | P0 | Should be hook, not agent |
| Tool Guardrails | ❌ Missing | Kaizen Core | P0 | Prevent unauthorized actions |
| Budget Limits | ✅ CostTracker | BaseAgent (mixin) | - | Agent-level cost control |
| Rate Limiting | ❌ Missing | Kaizen Core | P1 | Framework-wide throttling |
| Sensitive Data Filter | ❌ Missing | Kaizen Core | P0 | Security requirement |
| **Tool Execution** | | | | |
| Tool Registry | ✅ Node registry | Kailash Core SDK | - | Already in Core SDK |
| In-Process Execution | ✅ PythonCode | Kailash Core SDK | - | Already in Core SDK |
| Sandboxed Execution | ❌ Missing | Kaizen Core | P1 | Security for untrusted code |
| Resource Limits | ❌ Missing | Kaizen Core | P1 | Prevent resource exhaustion |
| MCP Tool Integration | ✅ MCP nodes | MCP Integration | - | Already correctly placed |
| Permission Checks | ❌ Missing | Kaizen Core | P0 | Tied to permission system |
| **Streaming & Events** | | | | |
| Token Streaming | ✅ StreamingChatAgent | BaseAgent (mixin) | P1 | Many agents need streaming |
| Progress Streaming | ❌ Missing | Kaizen Core | P1 | Universal UX improvement |
| Event Emission | ✅ Nexus | Kaizen Core | P1 | Should be framework-wide |
| Event Subscription | ✅ Nexus | Kaizen Core | P1 | Should be framework-wide |
| Event Replay | ❌ Missing | Kaizen Core | P2 | Debugging feature |
| Backpressure Handling | ❌ Missing | Kaizen Core | P1 | Streaming performance |
| **Interrupts & Control** | | | | |
| Pause Execution | ❌ Missing | Kaizen Core | P0 | Runtime control |
| Resume Execution | ❌ Missing | Kaizen Core | P0 | Runtime control |
| Cancel Execution | ⚠️ Timeout only | Kaizen Core | P1 | User cancellation |
| Interrupt Handling | ❌ Missing | Kaizen Core | P0 | Signal handling |
| **Error Handling** | | | | |
| Automatic Retry | ✅ ResilientAgent | BaseAgent (mixin) | P1 | Should be mixin, not agent |
| Fallback Strategies | ✅ ResilientAgent | BaseAgent (mixin) | P1 | Should be mixin, not agent |
| Circuit Breaker | ❌ Missing | Kaizen Core | P1 | Framework-wide pattern |
| Partial Success | ❌ Missing | Kaizen Core | P1 | Framework-wide pattern |
| Error Context | ❌ Missing | Kaizen Core | P2 | Enhanced error reporting |
| Actionable Errors | ❌ Missing | BaseAgent | P2 | Agent-specific suggestions |
| **Observability** | | | | |
| Distributed Tracing | ❌ Missing | Kaizen Core | P1 | Multi-agent observability |
| Span Hierarchy | ❌ Missing | Kaizen Core | P2 | Trace detail level |
| Trace Correlation | ❌ Missing | Kaizen Core | P2 | Cross-service tracing |
| Performance Metrics | ✅ PerformanceMixin | BaseAgent (mixin) | - | Already correctly placed |
| Cost Metrics | ✅ CostTracker | BaseAgent (mixin) | - | Already correctly placed |
| Custom Metrics | ✅ MonitoringNode | BaseAgent | - | Agent-specific metrics |
| **Multi-Agent** | | | | |
| A2A Protocol | ✅ A2A nodes | Kaizen Core | - | Already correctly placed |
| Capability Discovery | ✅ to_a2a_card() | BaseAgent | - | Already correctly placed |
| Semantic Matching | ✅ SupervisorWorker | Agent Patterns | - | Already correctly placed |
| Coordination Patterns | ✅ 6 patterns | Agent Patterns | - | Already correctly placed |
| Distributed State | ⚠️ SharedMemoryPool | Kaizen Core | P1 | Needs distributed locks |
| Conflict Resolution | ❌ Missing | Kaizen Core | P2 | Multi-agent state conflicts |
| **Debugging** | | | | |
| Step-by-Step Exec | ❌ Missing | Kaizen Core | P2 | Developer experience |
| State Inspection | ⚠️ Memory | Kaizen Core | P2 | Enhance memory inspection |
| Breakpoints | ❌ Missing | Kaizen Core | P2 | Interactive debugging |

---

## Migration Plan

### Components to Move

| Component | From | To | Reason | Effort |
|-----------|------|----|---------| ------|
| Event System | Nexus | Kaizen Core | Should be framework-wide | Medium |
| Streaming Mixin | StreamingChatAgent | BaseAgent (mixin) | Reusable across agents | Low |
| Resilience Mixin | ResilientAgent | BaseAgent (mixin) | Reusable across agents | Low |
| HumanApproval | Dedicated agent | BaseAgent (hook) | Should be hook, not agent | Medium |

### Components to Create

| Component | Owner | Depends On | Effort |
|-----------|-------|-----------|--------|
| ControlChannel | Kaizen Core | Protocol design | High |
| ExecutionContext | Kaizen Core | Permission system | Medium |
| Permission System | Kaizen Core | Policy engine | High |
| Checkpoint System | Kaizen Core | State serialization | High |
| Interrupt Mechanism | Kaizen Core | Signal handling | Medium |
| Circuit Breaker | Kaizen Core | Error tracking | Medium |
| Distributed Tracing | Kaizen Core | Trace correlation | High |

---

## Priority Matrix

### Phase 1: Autonomy Foundations (P0 - 12 weeks)

**Goal**: Enable basic autonomous agent capabilities

| Component | Owner | Dependencies | Weeks |
|-----------|-------|-------------|-------|
| ControlChannel Interface | Kaizen Core | None | 2 |
| CLI Transport | Kaizen Core | ControlChannel | 1 |
| ExecutionContext | Kaizen Core | None | 1 |
| Hook Enhancement | Kaizen Core | ExecutionContext | 2 |
| Permission System | Kaizen Core | ExecutionContext | 3 |
| Checkpoint System | Kaizen Core | State serialization | 3 |

**Deliverables**:
- Agents can communicate bidirectionally with CLI
- Agents respect permission policies
- Agents can save/resume state

---

### Phase 2: Production Readiness (P1 - 10 weeks)

**Goal**: Production-grade control and observability

| Component | Owner | Dependencies | Weeks |
|-----------|-------|-------------|-------|
| SSE Transport | Nexus | ControlChannel | 2 |
| Stdio Transport | MCP | ControlChannel | 1 |
| Interrupt Mechanism | Kaizen Core | ControlChannel | 2 |
| Progress Streaming | Kaizen Core | Event system | 2 |
| Circuit Breaker | Kaizen Core | Error tracking | 1 |
| Distributed Tracing | Kaizen Core | Trace design | 3 |

**Deliverables**:
- Multi-channel agent control (HTTP, CLI, MCP)
- Real-time interrupts
- Production observability

---

### Phase 3: Enterprise Features (P2 - 8 weeks)

**Goal**: Enterprise-grade debugging and compliance

| Component | Owner | Dependencies | Weeks |
|-----------|-------|-------------|-------|
| Distributed State Locks | Kaizen Core | SharedMemoryPool | 2 |
| Event Replay | Kaizen Core | Event system | 2 |
| Step-by-Step Debug | Kaizen Core | Breakpoint system | 3 |
| Actionable Errors | BaseAgent | Error categorization | 1 |

**Deliverables**:
- Multi-agent state coordination
- Interactive debugging
- Enhanced error reporting

---

## Ownership Decision Rules

### Rule 1: Universal Needs → Kaizen Core

If ALL agents need the feature, it belongs in Kaizen Core.

**Examples**:
- ✅ Control protocol (all agents communicate)
- ✅ Permission system (all agents need security)
- ✅ Checkpoint system (all agents need persistence)

**Counterexamples**:
- ❌ Streaming (only some agents need it) → BaseAgent mixin
- ❌ Vision (specialized capability) → VisionAgent
- ❌ MCP tools (integration-specific) → MCP Integration

---

### Rule 2: Agent-Specific → BaseAgent or Mixins

If only SOME agents need the feature, it's a mixin or specialized agent.

**Examples**:
- ✅ Streaming → StreamingMixin (composable)
- ✅ Resilience → ResilienceMixin (composable)
- ✅ Performance tracking → PerformanceMixin (composable)

**Counterexamples**:
- ❌ Control protocol (all agents need it) → Kaizen Core
- ❌ Permission checks (security requirement) → Kaizen Core

---

### Rule 3: Integration-Specific → Integration Layer

If the feature ties to a specific platform (Nexus, DataFlow, MCP), it belongs in that integration.

**Examples**:
- ✅ SSE transport → Nexus (HTTP-specific)
- ✅ Stdio transport → MCP (MCP protocol)
- ✅ DataFlow persistence → DataFlow (database-backed)

**Counterexamples**:
- ❌ Checkpoint abstraction (generic) → Kaizen Core
- ❌ Event system (framework-wide) → Kaizen Core

---

### Rule 4: Cross-Cutting Concerns → Kaizen Core

If the feature affects multiple layers (agents, integrations, observability), it belongs in Kaizen Core.

**Examples**:
- ✅ Distributed tracing (spans across agents, integrations)
- ✅ Event system (consumed by all layers)
- ✅ Interrupt mechanism (runtime control for all)

**Counterexamples**:
- ❌ Agent-specific metrics → BaseAgent
- ❌ MCP tool discovery → MCP Integration

---

## Architecture Principles

### Principle 1: Separation of Concerns

Each layer has a clear responsibility:
- **Kaizen Core**: Framework-wide services (control, permissions, state)
- **BaseAgent**: Agent composition and extension points
- **Integration**: Platform-specific implementations
- **Application**: User-defined agents and workflows

### Principle 2: Dependency Inversion

Higher layers depend on abstractions in lower layers:
- Nexus depends on ControlChannel (Kaizen Core), not vice versa
- BaseAgent depends on Checkpoint (Kaizen Core), not vice versa
- Applications depend on BaseAgent, not Kaizen Core internals

### Principle 3: Progressive Enhancement

Features can be adopted incrementally:
- ControlChannel is optional (defaults to None)
- Mixins are composable (add only what you need)
- Integration layers are pluggable (use Nexus OR DataFlow OR both)

### Principle 4: Backward Compatibility

New features don't break existing code:
- ✅ `BaseAgent(config, signature)` still works
- ✅ `BaseAgent(config, signature, control_channel=...)` is optional
- ✅ Old agents work in new runtime

---

## Testing Ownership

### Kaizen Core Tests

**Location**: `tests/core/`

Tests for:
- ControlChannel interface
- Permission system
- Checkpoint system
- Hook execution
- Event system
- Interrupt handling

**Strategy**: Unit tests + integration tests with real transports

---

### BaseAgent Tests

**Location**: `tests/agents/`

Tests for:
- Agent initialization
- Hook customization
- Mixin composition
- Workflow generation
- Strategy execution

**Strategy**: Unit tests (mocked LLM) + integration tests (real LLM)

---

### Integration Tests

**Location**: `tests/integration/`

Tests for:
- Nexus + ControlChannel + SSE
- DataFlow + Checkpointing
- MCP + Stdio transport
- Multi-agent + Distributed state

**Strategy**: Real infrastructure (NO MOCKING in Tier 2-3)

---

## Success Metrics

### Ownership Clarity

- [ ] Every component has a single owner (no ambiguity)
- [ ] No circular dependencies between layers
- [ ] Clear upgrade path for existing code

### Development Velocity

- [ ] New features don't require touching multiple layers
- [ ] Mixin composition reduces code duplication by 80%+
- [ ] Integration layers can be developed independently

### Maintainability

- [ ] Test failures clearly identify responsible layer
- [ ] Bug fixes are isolated to owning component
- [ ] Deprecations follow clear migration path

---

## Next Steps

1. **Review & Approve**: Stakeholder review of ownership matrix
2. **Create ADRs**: Document each ownership decision
3. **Refactor Phase 1**: Move Event System from Nexus → Kaizen Core
4. **Implement Phase 1**: Build ControlChannel, ExecutionContext, Permissions
5. **Validate**: Test ownership boundaries with real implementations

---

**Conclusion**: Clear component ownership prevents architectural drift and enables parallel development across layers.

# Competitive Landscape — Agent Orchestration Frameworks (2026)

## 1. Framework Comparison

### 1.1 CrewAI

- **Model**: Role-based agents with tasks and crews
- **Concepts**: 3 (Agent, Task, Crew)
- **Governance**: None — no budget tracking, no envelope enforcement, no access control
- **Failure handling**: Basic retry, no gradient-based escalation
- **Context scoping**: None — agents share a flat context
- **Strengths**: Simple mental model, fast prototyping, large community
- **Weaknesses**: No governance, no audit trail, no budget control, no classification

### 1.2 AutoGen (Microsoft)

- **Model**: Conversation-based multi-agent with group chat
- **Concepts**: 3-5 (Agent, GroupChat, ConversableAgent, AssistantAgent)
- **Governance**: None built-in
- **Failure handling**: Conversation-level retry
- **Context scoping**: Shared conversation (no filtering)
- **Strengths**: Flexible conversation patterns, Microsoft ecosystem
- **Weaknesses**: No structured governance, conversation overhead, no budget tracking

### 1.3 LangGraph (LangChain)

- **Model**: Graph-based state machines
- **Concepts**: 3 (Node, Edge, State)
- **Governance**: None built-in (add-on via LangSmith)
- **Failure handling**: Node-level retry, conditional edges
- **Context scoping**: Shared state object
- **Strengths**: Explicit control flow, good for deterministic workflows, strong observability
- **Weaknesses**: No agent governance, no budget enforcement, manual state management

### 1.4 DSPy (Stanford)

- **Model**: Signature-based programming with optimization
- **Concepts**: 3 (Signature, Module, Optimizer)
- **Governance**: None
- **Failure handling**: None (optimization handles quality)
- **Context scoping**: None
- **Strengths**: Automatic prompt optimization, academic rigor, clean abstractions
- **Weaknesses**: Single-agent focus, no multi-agent coordination, no governance

### 1.5 OpenAI Swarm

- **Model**: Handoff-based agent coordination
- **Concepts**: 2 (Agent, Handoff)
- **Governance**: None
- **Failure handling**: None
- **Context scoping**: None
- **Strengths**: Minimal API, easy to understand
- **Weaknesses**: No persistence, no governance, educational only (not production)

---

## 2. Differentiation Analysis

### 2.1 What kaizen-agents Offers That Others Don't

| Capability                                   | CrewAI | AutoGen | LangGraph | DSPy | kaizen-agents                 |
| -------------------------------------------- | ------ | ------- | --------- | ---- | ----------------------------- |
| 5-dimension budget enforcement               | No     | No      | No        | No   | Yes (via EnvelopeTracker)     |
| Classification-based access control          | No     | No      | No        | No   | Yes (C0-C4 via ScopedContext) |
| Monotonic tightening (child <= parent)       | No     | No      | No        | No   | Yes (invariant I-01)          |
| Cascade termination with budget reclamation  | No     | No      | No        | No   | Yes (invariant I-02)          |
| Verification gradient (auto/flag/hold/block) | No     | No      | No        | No   | Yes (PACT integration)        |
| Typed message protocols                      | No     | No      | No        | No   | Yes (6 message types)         |
| Dead letter handling                         | No     | No      | No        | No   | Yes (DeadLetterStore)         |
| EATP audit trail                             | No     | No      | No        | No   | Yes (per-operation records)   |
| Conformance testing across SDKs              | No     | No      | No        | No   | Yes (Rust + Python parity)    |
| Agent lineage tracking                       | No     | No      | No        | No   | Yes (parent_id chain)         |

### 2.2 What Others Offer That kaizen-agents Must Match

| Capability                        | Best Implementation   | kaizen-agents Strategy                            |
| --------------------------------- | --------------------- | ------------------------------------------------- |
| Simple getting-started experience | CrewAI (3 concepts)   | Provide high-level `Supervisor` + `Worker` facade |
| Automatic prompt optimization     | DSPy                  | Leverage Kaizen's existing signature system       |
| Visual workflow builder           | LangGraph + LangSmith | Future: Nexus integration for observability       |
| Large community + ecosystem       | LangChain/AutoGen     | Apache 2.0 Foundation model attracts contributors |
| Streaming output                  | Most frameworks       | Kaizen already supports streaming                 |

### 2.3 Honest Assessment

**The governance story IS the differentiation.** No other framework provides:

- Runtime budget enforcement across 5 dimensions
- Hierarchical access control with data classification
- Formal verification gradient for failure handling
- Audit-grade traceability with EATP records

But governance matters ONLY when:

1. Agents are autonomous (not just chat bots)
2. Agents spend real resources (API costs, tool execution)
3. Compliance requires audit trails (regulated industries)
4. Multi-tenant systems need isolation (enterprise SaaS)

**Market timing**: The market is transitioning from "make agents work at all" to "make agents work safely at scale." CrewAI/AutoGen serve the first phase. kaizen-agents is positioned for the second.

---

## 3. Target Market

### 3.1 Ideal Customer Profile

- **Regulated industries** (finance, healthcare, legal) where audit trails are mandatory
- **Enterprise AI teams** deploying 10+ agent types with budget constraints
- **Platform builders** offering agent orchestration as a service (multi-tenant)
- **Safety-conscious organizations** that need formal governance before deploying autonomous agents

### 3.2 Non-Customers (for now)

- Individual developers prototyping agents (CrewAI is simpler)
- Academic researchers (DSPy is more suitable)
- Teams that just need a chat bot (overkill)

---

## 4. Value Proposition

**For enterprise AI teams deploying autonomous agents at scale:**

Kailash Kaizen provides the only open-source agent orchestration framework with formal governance: 5-dimension budget enforcement, classification-based access control, verification gradient for failure handling, and EATP audit traceability. Agents operate autonomously within provable constraint boundaries. When things go wrong, the gradient system escalates deterministically — no agent can exceed its authority.

**The one-liner**: "Autonomous agents with provable constraint boundaries."

---

## 5. Risks

### 5.1 Over-Engineering Risk

The governance surface area is large. If the getting-started experience requires understanding PACT, EATP, envelopes, gradients, and classification before writing a single agent — adoption will be near zero.

**Mitigation**: Progressive disclosure. Default envelope with sensible limits. Classification defaults to PUBLIC. Gradient uses standard thresholds. User writes agents first, adds governance later.

### 5.2 Market Timing Risk

If the market stays in "make agents work" phase for another 12-18 months, the governance differentiation doesn't matter yet.

**Mitigation**: kaizen-agents must also be excellent at basic orchestration. The L0-L2 patterns continue to work. L3 governance is opt-in, not mandatory.

### 5.3 Complexity Tax

Every LLM call in the orchestration layer (TaskDecomposer, PlanComposer, etc.) adds latency and cost. For simple tasks, the overhead of plan generation + validation + evaluation may exceed the task itself.

**Mitigation**: Simple tasks should use L0-L2 patterns (direct execution). L3 plan generation is for complex, multi-step objectives where the overhead is justified.

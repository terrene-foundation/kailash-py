# Orchestration Layer User Flows (Revised)

**Date**: 2026-03-23
**Constraint**: SDK as-is (sync PlanExecutor, phantom HELD, string Signatures)

---

## Flow 1: Single-Agent Task (kz CLI direct mode)

User runs `kz "fix the linting errors"`. Task is simple — no decomposition needed.

```
User → kz CLI
  ├── Load config (.kz/config.toml, KZ.md)
  ├── Load session (new or resumed)
  ├── LLM call: "fix the linting errors" + tools + context
  │   ├── LLM decides: call Grep tool to find errors
  │   ├── LLM decides: call Edit tool to fix
  │   ├── LLM decides: call Bash tool to verify
  │   └── LLM says: "Done. Fixed 3 linting errors."
  ├── EnvelopeEnforcer.check() on each tool call (budget gating)
  ├── Permission rules applied (deny > ask > allow)
  └── Session saved
```

**SDK integration points**: EnvelopeEnforcer for budget gating, no multi-agent orchestration needed.

---

## Flow 2: Multi-Agent Task (orchestration mode)

User runs `kz "build a REST API for user management with tests"`. Task requires decomposition.

```
User → kz CLI
  ├── LLM call: assess complexity
  │   └── Result: multi-step task, triggers orchestration
  │
  ├── TaskDecomposer (LLM)
  │   └── Produces: [subtask1: "design API schema", subtask2: "implement endpoints", subtask3: "write tests"]
  │
  ├── AgentDesigner (LLM) × 3
  │   └── Produces: AgentSpec per subtask (tools, capabilities, envelope allocation)
  │
  ├── EnvelopeSplitter.split() (SDK)
  │   └── Divides parent budget across 3 child agents
  │
  ├── PlanComposer (LLM)
  │   └── Produces: Plan DAG (subtask1 → subtask2 → subtask3)
  │   └── PlanValidator.validate() (SDK) — structural + envelope check
  │
  ├── PlanMonitor (async execution loop — OUR code, not SDK PlanExecutor)
  │   ├── Node 1: "design API schema"
  │   │   ├── AgentFactory.spawn() (SDK) — creates AgentInstance
  │   │   ├── ContextInjector → ContextScope.create_child() (SDK)
  │   │   ├── DelegationProtocol → MessageRouter.route() (SDK)
  │   │   ├── Agent executes (LLM + tools within envelope)
  │   │   ├── EnvelopeEnforcer.check() on each action (SDK)
  │   │   ├── CompletionProtocol → result back to parent
  │   │   └── EnvelopeTracker: reclaim unused budget
  │   │
  │   ├── Node 2: "implement endpoints" (depends on node 1 output)
  │   │   └── Same flow, receives node 1's output as context
  │   │
  │   └── Node 3: "write tests" (depends on node 2 output)
  │       └── Same flow
  │
  └── Session saved with full audit trail
```

**SDK integration points**: All L3 types (Plan, AgentSpec, AgentInstance), EnvelopeSplitter, PlanValidator, AgentFactory, ContextScope, MessageRouter, EnvelopeEnforcer, EnvelopeTracker.

---

## Flow 3: Failure Recovery (event-driven HELD)

Node 2 fails during multi-agent execution. The SDK's HELD is phantom — the node stays FAILED and emits a "held" event.

```
PlanMonitor executing node 2...
  ├── Agent calls API endpoint → 500 error
  ├── Agent retries × 2 → still failing
  ├── Agent reports failure
  │
  ├── PlanMonitor classifies failure via GradientZone:
  │   ├── GradientZone.AUTO_APPROVED: minor, auto-retry ← NOT this
  │   ├── GradientZone.FLAGGED: log and continue ← NOT this
  │   ├── GradientZone.HELD: pause and diagnose ← THIS ONE
  │   └── GradientZone.BLOCKED: abort ← NOT this
  │
  ├── Node stays FAILED (SDK state)
  ├── PlanMonitor creates HoldRecord in hold registry (OUR state)
  │   └── {node_id, timeout=60s, reason="API 500", pending_resolution=True}
  │
  ├── FailureDiagnoser (LLM)
  │   ├── Input: error details, node context, plan state
  │   └── Output: "API endpoint doesn't exist yet. Need to create it first."
  │
  ├── Recomposer (LLM)
  │   ├── Input: diagnosis, current plan, available agents
  │   └── Output: PlanModification — add new node "create endpoint" before node 2
  │
  ├── apply_modification() (SDK) — structurally validates the modification
  ├── PlanValidator.validate() (SDK) — re-validates modified plan
  │
  ├── PlanMonitor executes new node "create endpoint"
  │   └── Agent creates the endpoint successfully
  │
  ├── PlanMonitor retries node 2 (now FAILED → re-execute)
  │   └── Agent succeeds with the endpoint now available
  │
  └── Hold resolved, plan continues
```

**Key adaptation**: HELD is managed by our hold registry, not SDK state. We listen for gradient classification, not state transitions.

---

## Flow 4: Governance Enforcement (PACT)

An agent attempts an action that exceeds its envelope.

```
Agent "write tests" (child) executing...
  ├── Agent decides: "I should deploy to production to verify"
  ├── Agent calls: Bash("kubectl apply -f deploy.yaml")
  │
  ├── EnvelopeEnforcer.check() (SDK)
  │   ├── Check operational constraints: "kubectl" not in allowed_tools
  │   ├── Verdict: BLOCKED
  │   └── Reason: "Tool 'kubectl' not permitted for role 'test-writer'"
  │
  ├── Action denied. Agent receives structured denial.
  │
  ├── EATP Audit Trail:
  │   ├── Audit Anchor: {action: "bash:kubectl", verdict: BLOCKED, agent: "test-writer", parent: "api-builder"}
  │   └── Hash chain: links to previous audit record
  │
  ├── D/T/R Accountability:
  │   └── Agent address: org:project/dept:engineering/team:api/role:test-writer
  │   └── Traceable to human who defined the "test-writer" envelope
  │
  └── Agent proceeds with alternative approach (runs tests locally)
```

---

## Flow 5: Budget Exhaustion + Reclamation

Parent has $1.00 budget split across 3 children. Child 1 finishes under budget.

```
Parent envelope: $1.00
  ├── EnvelopeSplitter.split():
  │   ├── Child 1: $0.33
  │   ├── Child 2: $0.33
  │   └── Child 3: $0.34
  │
  ├── Child 1 completes: spent $0.15, unspent $0.18
  │   ├── EnvelopeTracker: reclaim $0.18 to parent pool
  │   ├── Parent available: $0.00 + $0.18 = $0.18
  │   └── BudgetPolicy: reallocate to child 3 (highest estimated remaining cost)
  │
  ├── Child 3 now has: $0.34 + $0.18 = $0.52
  │
  ├── Child 2 at 70% projected exhaustion:
  │   ├── Predictive warning emitted
  │   ├── PlanMonitor evaluates: can reallocate? No available pool.
  │   └── Continue with warning. If actual exhaustion → HELD → recovery flow.
  │
  └── All children complete within total $1.00 budget
```

---

## Flow 6: Protocol Exchange (Delegation + Clarification)

Parent delegates to child, child needs clarification.

```
Parent agent "api-builder" spawns child "schema-designer"
  │
  ├── DelegationProtocol:
  │   ├── Parent composes delegation message (LLM):
  │   │   "Design a REST API schema for user management with CRUD operations"
  │   ├── MessageRouter.route() (SDK):
  │   │   ├── Validate: parent → child directionality ✓
  │   │   ├── Validate: TTL not expired ✓
  │   │   ├── Deliver to child's MessageChannel
  │   └── EATP: Delegation Record created
  │
  ├── Child "schema-designer" working...
  │   ├── Needs clarification: "Should I include soft delete or hard delete?"
  │   │
  │   ├── ClarificationProtocol:
  │   │   ├── Child composes clarification request (LLM)
  │   │   ├── MessageRouter.route() (SDK):
  │   │   │   ├── Validate: child → parent directionality ✓ (clarification allowed upward)
  │   │   │   ├── Deliver to parent's MessageChannel
  │   │   ├── Parent receives, LLM decides: "Use soft delete (is_deleted flag)"
  │   │   ├── MessageRouter.route() response back to child
  │   │   └── Child incorporates answer into design
  │   │
  │   ├── Child completes schema design
  │   │
  │   └── CompletionProtocol:
  │       ├── Child composes completion message with results
  │       ├── MessageRouter.route() (SDK)
  │       └── Parent receives result, continues plan
  │
  └── Delegation chain fully resolved
```

# EATP SDK Gap Details — kailash-py

**Date**: 2026-03-14
**Package**: `packages/eatp/src/eatp/`

---

## G1: Behavioral Trust Scoring

**Severity**: CRITICAL
**File**: `scoring.py`

### Current State
The scoring module implements structural trust scoring with 5 factors:
- Chain completeness (30%)
- Delegation depth (15%)
- Constraint coverage (25%)
- Posture level (20%)
- Chain recency (10%)

### What's Missing
Behavioral scoring — evaluating agents based on runtime behavior:
- **Interaction history** — track record of actions taken
- **Approval rate** — ratio of actions approved vs denied
- **Error rate** — frequency of failed operations
- **Posture stability** — how often the agent's posture changes
- **Time at posture** — duration at current trust level

### Why It Matters
Structural scoring tells you about the trust chain's quality. Behavioral scoring tells you about the agent's actual performance. Both are needed for informed posture evolution decisions. Without behavioral scoring, posture recommendations are based only on chain structure, not agent behavior.

### Implementation Notes
- Create a `BehavioralScorer` alongside the existing structural scorer
- Define behavioral factors with configurable weights
- Zero-data should score 0 (fail-safe)
- Behavioral score should be complementary to structural score, not replace it
- Consider: should this be defined in the CARE spec first? (CC BY 4.0 spec addition)

---

## G2: Constraint Proximity Thresholds

**Severity**: CRITICAL
**File**: `enforce/` directory

### Current State
The verification gradient classifies actions into 4 levels (AUTO_APPROVED, FLAGGED, HELD, BLOCKED) but does not scan constraint utilization ratios to detect proximity to limits.

### What's Missing
Proximity scanning with configurable thresholds:
- **FLAG threshold** (default 0.70) — usage at 70% of limit → FLAGGED
- **HELD threshold** (default 0.90) — usage at 90% of limit → HELD
- **BLOCKED threshold** (1.00) — usage at 100% → BLOCKED

Scan across utilization dimensions:
- Budget utilization (financial)
- Token consumption (operational)
- API call rates (operational)
- Tool invocation counts (operational)

### Why It Matters
Without proximity scanning, an agent at 95% of its budget limit gets AUTO_APPROVED. The next action might push it over, resulting in a sudden BLOCKED with no warning. Proximity thresholds provide the early-warning signal that makes the verification gradient useful in practice.

### Implementation Notes
- Extend the enforcement module, not the core gradient classifier
- Configurable thresholds per dimension
- Note: kailash-rs already has this with configurable `flag_threshold` (0.80) and `hold_threshold` (0.95) in `VerificationConfig`. Consider aligning defaults.

---

## G3: EATP Lifecycle Hooks

**Severity**: CRITICAL
**New module needed**

### Current State
No hook system exists. The only enforcement mechanism is decorators (`@verified`, `@audited`, `@shadow`), which require wrapping individual functions.

### What's Missing
A hook registry with lifecycle event types:
- `PRE_TOOL_USE` — before an agent uses a tool
- `POST_TOOL_USE` — after tool use completes
- `SUBAGENT_SPAWN` — when an agent creates a sub-agent
- `PRE_DELEGATION` — before trust is delegated
- `POST_DELEGATION` — after delegation completes

Hook features:
- Priority ordering (hooks execute in priority order)
- Hook registry (register/unregister hooks at runtime)
- Async-first with sync compatibility
- Hooks can abort the operation (fail-closed)

### Why It Matters
Decorators require modifying the function being enforced. Hooks intercept at the runtime level — they work on any function without modification. This is essential for:
- Kaizen agent runtime integration (intercept agent tool calls without modifying tool code)
- Defense-in-depth (hooks + decorators layer independently)
- Plugin architecture (third parties add enforcement without modifying core code)

### Implementation Notes
- Define hook protocol/ABC in EATP SDK
- Registration and execution in a separate module
- Kaizen framework implements the concrete hooks
- Hooks are the mechanism; decorators are the DX — both are needed

---

## G4: Per-Agent Circuit Breaker Registry

**Severity**: HIGH
**File**: `circuit_breaker.py`

### Current State
`PostureCircuitBreaker` tracks state per agent internally (keyed by `agent_id`). But there is no registry that lazily creates and manages isolated breaker instances per agent.

### What's Missing
`PerAgentCircuitBreakerRegistry`:
- Lazy creation of breakers per `agent_id`
- Configurable defaults (threshold, recovery_time)
- Per-agent configuration overrides
- Bulk status query (which agents are in open/half-open state)
- Cleanup of idle breakers

### Why It Matters
In production, you need to manage dozens or hundreds of agent breakers. The registry pattern makes this manageable. Without it, consumers must manually create and track breaker instances per agent, which is error-prone and doesn't scale.

### Implementation Notes
- Thin wrapper over existing `PostureCircuitBreaker`
- `registry.get_or_create(agent_id)` → returns isolated breaker
- Thread-safe (or async-safe, see G9)

---

## G5: ShadowEnforcer Bounded Memory

**Severity**: HIGH
**File**: `enforce/shadow.py`

### Current State
`ShadowEnforcer._records` list grows unbounded. `ShadowMetrics` with `pass_rate` and `block_rate` already exists. Missing `change_rate` metric.

### What's Missing
1. **Bounded memory**: maxlen cap (e.g., 10,000 records) with oldest-10% trimming
2. **`change_rate` metric**: frequency of enforcement decisions changing (indicates policy instability)
3. **Fail-safe error handling**: no try/except around shadow evaluation — errors in shadow enforcement should not crash the main execution path

### Implementation Notes
- `PostureStateMachine` already has bounded history — follow the same pattern
- `change_rate` = number of decision flips / total evaluations in window

---

## G6: Dual-Signature on Audit Anchors

**Severity**: HIGH

### Current State
Ed25519 signing only.

### What's Missing
Optional HMAC-SHA256 fast-path for internal verification alongside Ed25519 for external non-repudiation. Internal verification (within an organization) can use symmetric HMAC for speed. External verification (across organizations) uses Ed25519 for non-repudiation.

### Implementation Notes
- HMAC should be optional, not required
- Default to Ed25519-only for simplicity
- HMAC key management separate from Ed25519 key management

---

## G7-G11: Medium/Low Gaps

See brief (`briefs/01-eatp-sdk-gaps.md`) for details on:
- G7: AWSKMSKeyManager stub
- G8: Deprecated `get_event_loop()` in sync path
- G9: asyncio.Lock vs threading.Lock on circuit breaker
- G10: Posture/dimension adapter modules
- G11: Built-in dimension registry naming alignment

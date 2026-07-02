# PACT Engine Research — Issues #232-#241

## All 8 Issues Confirmed Against Source Code

### Issue #234: Single-Gate Governance — No Per-Node verify_action (HIGH)

**Location**: `packages/kailash-pact/src/pact/engine.py`, lines 148-189

```python
# submit() calls verify_action() ONCE at submit time
verdict = self._governance.verify_action(
    role_address=role, action="submit", context=ctx,
)
if not verdict.allowed:
    return WorkResult(...)

# Then supervisor executes freely — no per-node checks
supervisor = self._get_or_create_supervisor()
supervisor_result = await supervisor.run(objective=objective, context=ctx)
```

After the single gate, GovernedSupervisor's `run()` (kaizen-agents/supervisor.py, lines 309-430) never calls `verify_action()` per node. Actions in `blocked_actions`, per-step financial limits, temporal blackout periods, and knowledge compartments are all bypassed.

**Fix**: Add GovernanceCallback protocol, create `_DefaultGovernanceCallback` that calls verify_action() per node, pass to supervisor.run(execute_node=callback).

**Complexity**: Large

---

### Issue #235: Stale Supervisor Budget (HIGH)

**Location**: `packages/kailash-pact/src/pact/engine.py`, lines 391-431

```python
def _get_or_create_supervisor(self):
    if self._supervisor is not None:
        return self._supervisor  # Reuses cached supervisor with STALE budget
    supervisor = GovernedSupervisor(
        budget_usd=(self._costs.remaining if self._costs.remaining is not None else 1.0),
        ...
    )
    self._supervisor = supervisor
    return supervisor
```

Budget is computed once at first creation. Second submit() reuses cached supervisor with original budget, not updated remaining.

**Complexity**: Small — recreate supervisor per submit() or pass budget to run()

---

### Issue #236: Mutable GovernanceEngine Exposed (HIGH)

**Location**: `packages/kailash-pact/src/pact/engine.py`, lines 324-333

```python
@property
def governance(self):
    return self._governance  # Returns full mutable engine
```

Agent code receiving this reference can call `update_envelope()`, `modify_envelope()`, `register_vacancy()` — self-modifying its own governance constraints. Violates pact-governance.md Rule 1.

**Complexity**: Small — return `_ReadOnlyView` wrapper or `GovernanceEngine.create_verifier()`

---

### Issue #237: NaN-Guard Missing on budget_consumed (MEDIUM)

**Location**: `packages/kailash-pact/src/pact/engine.py`, lines 220-222

```python
cost_usd = supervisor_result.budget_consumed  # No validation
if cost_usd > 0:  # NaN > 0 is False — cost silently dropped
    self._costs.record(cost_usd, f"submit: {objective[:80]}")
```

If budget_consumed is NaN, the cost is never recorded. Budget remains artificially high, future submissions pass.

**Complexity**: Small — add `math.isfinite()` guard

---

### Issue #238: HELD Verdicts Treated as BLOCKED (MEDIUM)

**Location**: `src/kailash/trust/pact/verdict.py`, lines 57-64

```python
@property
def allowed(self):
    return self.level in ("auto_approved", "flagged")
    # HELD returns False — same as BLOCKED
```

The 4-level gradient (AUTO_APPROVED, FLAGGED, HELD, BLOCKED) collapses to 3. HELD should trigger human-in-the-loop approval, not permanent rejection.

**Complexity**: Medium — add HeldActionCallback protocol, distinguish HELD from BLOCKED in PactEngine

---

### Issue #239: No Enforcement Modes (HIGH for production)

**Status**: Confirmed — no `EnforcementMode` enum exists anywhere in codebase. PactEngine is always enforce.

**Complexity**: Large — enum + config propagation + conditional verdict handling + shadow logging

---

### Issue #240: Envelope-to-Execution Adapter (HIGH)

**Nuance from research**: GovernanceEngine DOES resolve effective envelopes per role internally (line 861, `_compute_envelope_locked`). The gap is that PactEngine doesn't expose per-role envelope resolution at L1 or map all 5 constraint dimensions to supervisor parameters.

| Constraint Dimension          | Supervisor Parameter    | PactEngine Status                        |
| ----------------------------- | ----------------------- | ---------------------------------------- |
| Financial (max_spend_usd)     | budget_usd              | Uses top-level budget, not role envelope |
| Operational (allowed_actions) | tools list              | Not mapped                               |
| Confidentiality               | data_clearance          | Uses constructor param, not envelope     |
| Temporal (active_hours)       | timeout_seconds         | Not mapped                               |
| Delegation depth              | max_children, max_depth | Not mapped                               |

**Complexity**: Medium — add `_adapt_envelope(role_address)` with NaN guards

---

### Issue #241: Degenerate Envelope Detection Missing at Init (MEDIUM)

**Status**: Confirmed — `check_degenerate_envelope()` exists at line 1059 of envelopes.py but is never called during init or compile_org().

**Complexity**: Small — add validation loop in **init** after compilation

---

## Additional Gaps Found (Not in GH Issues)

1. **No governance audit event persistence** — verdicts are not persisted to EATP audit trail
2. **No per-role or per-task clearance narrowing** — PactEngine sets global clearance only
3. **No GovernanceContext (frozen) passed to agents** — only mutable engine exposed

## Fix Dependency Graph

```
Independent (land first):
  #241 (degenerate check at init)
  #237 (NaN guard)
  #236 (freeze governance property)

Sequential chain:
  #235 (fix stale budget) → #234 (per-node verify) → #240 (per-role envelope)
  #238 (HELD state)       → #234 (per-node verify)
  #239 (enforcement mode) → #234 (per-node verify)
```

**Recommended landing order**:

1. #241, #237, #236 (independent, small)
2. #235 (prerequisite for #234)
3. #238 (prerequisite for #234)
4. #234 (the big one — per-node governance)
5. #240 (builds on #234)
6. #239 (builds on #234)

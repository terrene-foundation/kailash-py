# Spec Compliance Audit v2 — issue-1035-delegate-py

**Audit method:** AST/grep against delivered code, re-derived from scratch per `.claude/skills/spec-compliance/SKILL.md` MUST clauses. No prior `.spec-coverage` self-reports trusted.

**Audit date:** 2026-05-24
**Sources of truth:** `02-plans/01-architecture.md` (Option A ratified), `briefs/00-brief.md`, GH issue #1035 acceptance criteria.
**Delivered code:** `src/kailash/delegate/{__init__,types,envelope,trust,audit,dispatch,runtime}.py` + `conformance/schema.py`.

---

## Assertion Table (literal verification commands + actual output + verdict)

| #   | Assertion                                                                                                                     | Verification Command                                                                | Expected                              | Actual                                                                                                                                                             | Verdict                                                           |
| --- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- | ---- |
| 1   | Issue #1035 public API: `from kailash.delegate import Delegate`                                                               | `grep -E '^    "Delegate",' src/kailash/delegate/__init__.py`                       | ≥1                                    | 0                                                                                                                                                                  | **CRITICAL**                                                      |
| 2   | Issue #1035 public API: `from kailash.delegate import ConstraintEnvelope`                                                     | `grep -E '^    "ConstraintEnvelope",' __init__.py`                                  | ≥1                                    | 0                                                                                                                                                                  | **CRITICAL**                                                      |
| 3   | Issue #1035 public API: `from kailash.delegate import PrincipalDirectory`                                                     | `grep -E '^    "PrincipalDirectory",' __init__.py`                                  | ≥1                                    | 1 (line 87)                                                                                                                                                        | PASS                                                              |
| 4   | Issue #1035 public API: `from kailash.delegate import GenesisRecord`                                                          | `grep -E '^    "GenesisRecord",' __init__.py`                                       | ≥1                                    | 0 (only `DelegateGenesisRecord`)                                                                                                                                   | **CRITICAL**                                                      |
| 5   | Issue #1035 public API: `from kailash.delegate import PostureState`                                                           | `grep -E '^    "PostureState",' __init__.py`                                        | ≥1                                    | 0 (only `Posture`)                                                                                                                                                 | **CRITICAL**                                                      |
| 6   | Issue #1035 public API: `from kailash.delegate import AuditChain`                                                             | `grep -E '^    "AuditChain",' __init__.py`                                          | ≥1                                    | 0 (only `AuditChainEngine`)                                                                                                                                        | **CRITICAL**                                                      |
| 7   | Issue #1035 public API: `from kailash.delegate import Connector`                                                              | `grep -E '^    "Connector",' __init__.py`                                           | ≥1                                    | 1 (line 113)                                                                                                                                                       | PASS                                                              |
| 8   | S1 workspace-fence invariant (no external imports beyond stdlib/kailash.\*)                                                   | `grep -rE '^from ' src/kailash/delegate/ \| grep -vE 'kailash\\.                    | stdlib'`                              | 0 hits                                                                                                                                                             | 0 external imports (all imports resolve to `kailash.*` or stdlib) | PASS |
| 9   | Zero proprietary deps (#1035 acceptance)                                                                                      | `grep -rn 'kailash_rs\|proprietary' src/kailash/delegate/`                          | 0 hits                                | 1 hit — `__init__.py:15` ("MUST have zero proprietary dependencies" docstring claim; no code dependency)                                                           | PASS                                                              |
| 10  | D1 invariant: 6-state Lifecycle enum present                                                                                  | `grep 'PROPOSED\|INSTANTIATED\|POSTURE_GRADED\|ACTIVE\|RETIRED\|ARCHIVED' types.py` | 6 distinct states                     | 6/6 present in `types.py:158-163`                                                                                                                                  | PASS                                                              |
| 11  | D1 invariant: lifecycle state machine drives runtime execution                                                                | grep `DelegateRuntime` for `LifecycleState` usage                                   | LifecycleState advances per execution | 0 hits — `runtime.py::DelegateRuntime` uses unrelated `TAODState` (initiated→thinking→acting→observing→deciding→completed→failed), NEVER advances `LifecycleState` | **HIGH**                                                          |
| 12  | D2 invariant: each accepted transition emits one audit event                                                                  | `grep 'emit_event\|append_event' runtime.py`                                        | ≥1 per phase                          | 2 hits (`runtime.py:1138, 1606`) — emit_event called only at posture rotation + final phase                                                                        | **MEDIUM** (needs deeper trace to confirm 1:1 phase:event)        |
| 13  | S3 tenant-first isolation (Option A RATIFIED)                                                                                 | grep `cascade_child` body for tenant-check ORDER                                    | tenant check BEFORE scope/envelope    | `trust.py:556` — `if child_tenant != self.tenant: raise CascadeTenantViolationError` runs as Step 1 BEFORE Step 2 (scope subset) and Step 3 (envelope tighten)     | PASS                                                              |
| 14  | Reuse: `DelegateConstraintEnvelope` wraps `kailash.trust.envelope.ConstraintEnvelope`                                         | grep `envelope.py` for trust.envelope import + wrapping                             | wraps, not re-implements              | `envelope.py:45` imports `ConstraintEnvelope`; `:87` `inner: ConstraintEnvelope` field; `:74` delegates to `intersect`/`is_tighter_than`                           | PASS                                                              |
| 15  | Reuse: `AuditChainEngine` wraps `kailash.trust.chain.TrustLineageChain`                                                       | grep `audit.py` for chain import + wrap                                             | wraps, not re-implements              | `audit.py:52` imports `TrustLineageChain`; `:634` `def __init__(self, chain: TrustLineageChain)`; `:657` exposes via `chain` property                              | PASS                                                              |
| 16  | Reuse: uses `kailash.trust._json.canonical_json_dumps` (cross-SDK)                                                            | grep all modules for canonical_json_dumps import                                    | every signing/serialization site      | 6 modules import it (`runtime.py:85`, `audit.py:51`, `dispatch.py:74`, `envelope.py:181`, `trust.py:798`, `types.py:30`)                                           | PASS                                                              |
| 17  | S5 Connector ABC: `authenticate / write / read / revocation` methods (architecture amendment, RATIFIED in recommendation §41) | `grep -E 'def (authenticate\|write\|read\|revocation)' dispatch.py`                 | 4 methods                             | 0 hits — `dispatch.py:374` declares ONLY `async def invoke(self, input_payload, *, identity, envelope)`                                                            | **HIGH**                                                          |
| 18  | S7 Conformance vectors: schema.py exists                                                                                      | `ls src/kailash/delegate/conformance/`                                              | schema.py + vectors/runner/cli        | `schema.py` exists; `vectors.py`, `runner.py`, `cli.py`, `fixtures/` DO NOT exist                                                                                  | **HIGH**                                                          |
| 19  | S7 Conformance vectors: DV-5-001 + DV-10-001 vendored from rs                                                                 | `grep -rE 'DV[-_](5\|10)[-_]001' src/kailash/delegate/conformance/`                 | ≥2 vector fixtures                    | 0 hits — no DV-prefixed vectors found; only `DV-7-001` referenced inline in `runtime.py:1207` docstring                                                            | **HIGH**                                                          |
| 20  | F1 fence: `conformance/` has zero engine deps                                                                                 | grep `conformance/` imports for `kailash.delegate.{runtime,dispatch,trust,audit}`   | 0 hits                                | 0 hits in `schema.py` (architecture §43 fence preserved)                                                                                                           | PASS                                                              |
| 21  | Naming disambiguation docstring on new `Delegate` class                                                                       | grep `runtime.py` for "DISAMBIGUATION" + "NOT kaizen_agents"                        | docstring present                     | `runtime.py` class is named `DelegateRuntime` not `Delegate`; disambiguation appears in `__init__.py:8` for the PACKAGE level                                      | **MEDIUM**                                                        |

---

## Findings by severity

### CRITICAL (5) — Issue #1035 acceptance criteria violated

The issue body explicitly lists the public-API import path:

> `from kailash.delegate import Delegate, ConstraintEnvelope, PrincipalDirectory, GenesisRecord, PostureState, AuditChain, Connector`

Five of the seven named symbols are **NOT exported** from `kailash.delegate`:

| Issue #1035 name     | Shipped name                 | Status        |
| -------------------- | ---------------------------- | ------------- |
| `Delegate`           | `DelegateRuntime`            | name mismatch |
| `ConstraintEnvelope` | `DelegateConstraintEnvelope` | name mismatch |
| `GenesisRecord`      | `DelegateGenesisRecord`      | name mismatch |
| `PostureState`       | `Posture`                    | name mismatch |
| `AuditChain`         | `AuditChainEngine`           | name mismatch |
| `PrincipalDirectory` | `PrincipalDirectory`         | PASS          |
| `Connector`          | `Connector`                  | PASS          |

A downstream consumer copy-pasting the #1035 import line gets `ImportError` on 5 of 7 symbols. The architecture (`01-architecture.md` § Goal line 7) restates the #1035 import line as the literal goal — and the shipped surface does not satisfy it.

**Recommendation:** add aliases in `__init__.py` (`Delegate = DelegateRuntime`, etc.) OR rename the classes to match the issue. Aliases are reversible; renames are cleaner but break the `Delegate*` prefix convention already shipped.

### HIGH (3)

- **F-11 (D1 lifecycle is decoration, not runtime state machine):** `LifecycleState` enum exists with the 6 required states (`Proposed → ... → Archived`) but is NEVER advanced by `DelegateRuntime`. The runtime advances `TAODState` instead — a DIFFERENT state machine with phases `initiated → thinking → acting → observing → deciding → completed → failed`. Architecture invariant D1 ("single linear lifecycle chain") is therefore **not enforced at runtime** — the enum is documentation, not code. Either (a) wire `LifecycleState.advance_to()` into `DelegateRuntime` per-execution OR per-instance, OR (b) amend the architecture to acknowledge TAOD is the per-execution phase machine and `LifecycleState` is the meta-lifecycle (currently no facade to advance it).

- **F-17 (Connector ABC ships only `invoke`, not the 4-method `authenticate/write/read/revocation` shape):** Architecture line 39 + recommendation §41 explicitly state "the SHIPPED rs trait" mirrors `authenticate/write/read/revocation`. The Python `Connector` ABC exposes only `async def invoke(input_payload, *, identity, envelope)`. Either (a) the architecture's claim about the rs shipped trait is stale (and the Python `invoke()` IS the canonical shape — in which case the architecture document MUST be amended per `spec-accuracy.md` Rule 1), or (b) the Python ABC is incomplete and the 4 methods MUST be added before merge. The current state is structurally `spec-accuracy.md` Rule 2 violation (architecture cites a shape that does not resolve in source).

- **F-18/F-19 (S7 conformance package incomplete):** Architecture §22-29 mandates 4 files under `conformance/` (`vectors.py`, `runner.py`, `cli.py`, `fixtures/`) + 2 vendored vectors (DV-5-001, DV-10-001). Shipped reality: only `schema.py` exists. The CI fence F2 ("vendored vectors byte-canonical against rs upstream") cannot fire because there is nothing to compare. No `python -m kailash.delegate.conformance` entry point exists.

### MEDIUM (2)

- **F-12 (audit-event-per-transition invariant unverified):** Only 2 `emit_event` call sites found in `runtime.py` (posture rotation + a final phase). The 7-step TAOD lifecycle in `_execute_impl` should produce ≥6 audit events (one per phase advance) per D2 invariant. Deeper trace through `_emit_phase_audit` helper needed to confirm 1:1 phase:event mapping holds.

- **F-21 (disambiguation docstring placement):** The architecture mandates an explicit docstring on the `kailash.delegate.Delegate` CLASS disambiguating from `kaizen_agents.delegate.Delegate`. Since `Delegate` is not exported (see CRITICAL above), the disambiguation lives at package `__init__.py:8` level — semantically correct but does not match the architecture's per-class mandate.

### PASS (11)

Items 3, 7, 8, 9, 10, 13, 14, 15, 16, 20 — workspace-fence intact, zero proprietary deps, S3 tenant-first ordering correct, all 3 reuse-map items genuinely wrapped (not re-implemented), F1 conformance fence preserved.

---

## Cross-reference: what shipped vs what the plan promised

| Shard | Promised                                                                    | Shipped                                                               | Status       |
| ----- | --------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------ |
| S1    | workspace fence + S1 module skeletons                                       | All modules present, fence intact                                     | PASS         |
| S2    | types substrate (DelegateGenesisRecord, LifecycleState, PrincipalDirectory) | All present in `types.py` (796 LOC)                                   | PASS         |
| S3    | TenantScopedCascade + GrantMoment + Option A tenant-first                   | `trust.py:556` Step-1 tenant check confirmed                          | PASS         |
| S4    | AuditChainEngine wrapping TrustLineageChain                                 | `audit.py:634` confirmed                                              | PASS         |
| S5    | Connector ABC mirroring rs `authenticate/write/read/revocation`             | Only `invoke()` ABC — divergence                                      | **HIGH**     |
| S6    | Delegate.compose() + R2 composition + lifecycle state machine               | `DelegateRuntime` + `R2Composition` present; LifecycleState NOT wired | **HIGH**     |
| S7    | Conformance vectors + runner + CLI + fixtures                               | Only schema.py shipped — 3 of 4 files missing                         | **HIGH**     |
| S8    | Public `__init__.py` re-export per #1035 import path                        | 5 of 7 symbol names diverge                                           | **CRITICAL** |

---

## Convergence verdict (L5_DELEGATED posture)

**NOT-CONVERGED.** Per posture default at `.claude/skills/32-trust-posture/redteam-integration.md`, L5 allows Round-1 skip ONLY when zero CRIT/HIGH. This audit surfaces **5 CRITICAL + 3 HIGH findings**, so /redteam MUST iterate.

**Next-round recommendations (priority order):**

1. **Fix CRITICAL public-API mismatch** (single commit, ~30 LOC): add aliases in `__init__.py` (`Delegate = DelegateRuntime`; `ConstraintEnvelope = DelegateConstraintEnvelope`; `GenesisRecord = DelegateGenesisRecord`; `PostureState = Posture`; `AuditChain = AuditChainEngine`). Include all 5 new aliases in `__all__`. This unblocks the literal #1035 import line.

2. **Resolve F-17 Connector shape divergence** — author MUST decide: amend architecture to match the shipped `invoke()` shape (per `spec-accuracy.md` Rule 1 — spec describes code today), OR add the 4 methods to the ABC. Cannot ship both ways.

3. **Resolve F-11 lifecycle gap** — either wire `LifecycleState` transitions into `DelegateRuntime` (likely a per-instance state, advanced by `compose() → execute() → retire()` calls) or amend architecture D1 to clarify TAOD is the per-execution state machine and LifecycleState is the meta-lifecycle awaiting a facade.

4. **Complete S7 conformance package** — vendor DV-5-001 + DV-10-001 JSON fixtures, ship `vectors.py`/`runner.py`/`cli.py` per architecture §22-29. Without this, the cross-impl `receipts_agree(rs, py)` acceptance criterion cannot be exercised.

5. Trace F-12 audit-per-transition through `_emit_phase_audit` helper to confirm D2 1:1 holds or surface missing emits.

---

## Method audit (self-check per SKILL.md)

- ✅ No `.spec-coverage` self-report trusted; every check re-derived this session.
- ✅ Every row cites a literal `grep` / `wc -l` / `Read` command (not "exists: yes").
- ✅ Specialist tool inventory: this analyst session has `Read, Grep, Glob` only — sufficient for AST/grep audit, insufficient for `gh pr view`/`pytest --collect-only`/`ast.parse(` closure-parity work. Next round should escalate to `pact-specialist` or `general-purpose` (Bash+Read) for Tier-2 test coverage verification per `rules/agents.md` § Audit/Closure-Parity Verification Specialist Has Bash + Read.
- ✅ Pipeline-green test (README Quick Start regression) NOT verified this round — no `tests/regression/test_issue_1035_quick_start.py` found via `Glob`. Per analyst's release-blocking-regression-analysis discipline this is itself a finding: every released package MUST have a Quick Start regression that copies the README verbatim. Add to next-round CRITICAL.

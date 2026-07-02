# TRADE-OFF — `__getattr__` resolution as WARN-only in v1.0 (not blocking)

**Date:** 2026-04-26
**Phase:** /todos
**Workspace:** spec-drift-gate

## Trade-off

When the gate detects that a top-level package symbol resolves through a `__getattr__` lazy-import map to a different module than the spec asserts (the W6.5 motivating example: `kailash_ml.AutoMLEngine` → LEGACY scaffold), the gate emits a **WARN** finding in v1.0 — not a hard FAIL. Hard-fail integration with FR-6 is deferred to v1.1.

This is the day-1 CRIT mitigation per failure-points § B1 + redteam REQ-HIGH-1. The trade-off is "blocking enforcement now" vs "blocking enforcement later".

## Two options evaluated

### Option A — Hard-fail in v1.0

Treat `__getattr__` resolution mismatch as a FAIL finding. PR fails CI. Specialist must fix the `__getattr__` map (or update the spec) before the PR merges.

**Pro:** strongest enforcement; prevents the W6.5 pattern from recurring.
**Con:** the existing legacy `kailash_ml.AutoMLEngine` → LEGACY case is ALREADY documented in `specs/ml-automl.md` v2 § 1.3 as a known transitional state (Wave 6 follow-up #640.1 will fix). A v1.0 hard-fail would block PR merges on a known-and-tracked drift the gate's baseline can't gracefully grandfather without the kind of nuance the v1.0 grace logic doesn't yet support.
**Con:** the `__getattr__` AST traversal needs more edge-case hardening before hard-fail (q9.3 explicitly recommends WARN-only in v1.0 + full hard-fail in v1.1 with regression test).

### Option B — WARN-only in v1.0; FAIL in v1.1 (DECIDED)

Emit B1-class WARN; exit code stays 0 unless OTHER FAIL findings exist. Specialists see the divergence in CI output but it doesn't block. v1.1 promotes to FAIL once:

1. The Wave 6 follow-up #640.1 lands (flips the legacy → canonical map entry), removing the canonical existing case
2. SDG-203's `__getattr__` resolver has hardened against edge cases (nested maps, conditional resolution, version-gated imports)
3. A `--strict` flag is added that promotes WARN → FAIL for opt-in callers

**Pro:** ships v1.0 without blocking on a tracked Wave 6 fix
**Pro:** the WARN is highly visible in PR review (per ADR-6 fix-hint format) and creates social pressure to address
**Pro:** v1.0 gate carries a clear roadmap to v1.1 hardening
**Con:** weaker enforcement than Option A; specialists could ignore the WARN

## Why decided

Two factors weighted Option B:

1. **Concrete blocker in v1.0 ship-path:** the AutoMLEngine map entry is the canonical example of the pattern the gate exists to catch. Hard-failing on it before the source-side fix lands creates a chicken-and-egg: the gate ships, immediately blocks every spec-touching PR until #640.1 ships, but #640.1 needs a spec-touching PR to ship. Option B breaks the cycle.
2. **Q9.3 analyst recommendation:** `01-analysis/02-requirements-and-adrs.md` § 9 Q9.3 explicitly recommends "ship FR-6 as `__all__`-only for v1.0; document `__getattr__`-resolved exports as a known gap; add in v1.1 with a regression test". The analyst surfaced this trade-off; we follow.

## Mitigation if WARN gets ignored

If specialists routinely ignore B1 WARNs after v1.0 ships:

- Quarterly review of `gh pr list --search "WARN B1"` to surface PRs that landed despite the warning
- Promote to FAIL in v1.1 (planned)
- If still ignored in v1.1, escalate to `--strict` mandatory mode + per-spec opt-out via `<!-- spec-assert-skip -->` directive (forces explicit acknowledgment)

## References

- Spec: `specs/spec-drift-gate.md` § 11.1 (M2 deferred — but partial WARN ships in v1.0)
- Failure-points: § B1 (CRIT day-1)
- Redteam: REQ-HIGH-1 + Q9.3
- Wave 6 follow-up: GitHub issue #640 item 1 (the source-side fix)
- Todo: SDG-203 (the WARN-emission implementation)

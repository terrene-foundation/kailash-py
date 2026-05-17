# RISK: Class-4 pattern not surfaced by 30-row sample

**Date:** 2026-05-03
**Phase:** /todos
**Severity:** MEDIUM (tractable, mitigated)

## Risk

The cluster-C verification agent sampled 30 rows uniformly from the 254-hit production-source surface and found 0 markers fitting NONE of the three brief classes. But 30/254 ≈ 12% sample — a class shape with prevalence < 4% (10 hits or fewer) is statistically likely to be missed.

If T1 surfaces a 4th class shape (e.g. an inline `f"... TODO-NNN ..."` string literal, a pyproject.toml tag in metadata, an `__all__` export name with `TODO_NNN` substring), the dispositions in T1's PR may not cover it cleanly.

## Mitigation

1. **T1 disposition catalog includes an "OTHER" bucket.** If any T1 hit doesn't map to 1a/1b/2/3/ambiguous, route to OTHER and treat that row as a plan-revision trigger before continuing.
2. **T6 final audit re-runs canonical grep against the FULL post-cleanup tree.** Any non-zero is a blocking gap, not a closing rationalization.
3. **T5 gate is staged AFTER cleanup.** A new pattern surfacing during T1–T4 doesn't trip a CI gate that's not yet live; the team has space to revise dispositions.
4. **Wider regex `TODO-[0-9]+` is now canonical.** The brief's narrow regex would have hidden ≥6 IDs in the 300+ band; the wider regex closes that gap. Other syntactic shapes (FIXME, HACK, STUB, XXX) are NOT in scope of #781 — `rules/zero-tolerance.md` covers them but the issue is `TODO-NNN` specifically.

## Residual risk

If a Class-4 shape is genuinely novel AND high-prevalence (>10 hits) AND surfaces only mid-T2/T3/T4 (not T1), the in-flight shard would need to spawn an ad-hoc disposition under `rules/autonomous-execution.md` MUST Rule 4 (fix-immediately when surfaced same-class within budget). Acceptable tail risk; no further mitigation warranted at /todos.

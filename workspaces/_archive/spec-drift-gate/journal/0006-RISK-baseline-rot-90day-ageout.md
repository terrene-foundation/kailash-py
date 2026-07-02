# RISK — Baseline rot is the dominant long-term failure mode

**Date:** 2026-04-26
**Phase:** /todos
**Workspace:** spec-drift-gate

## Risk

Per `01-failure-points.md` § D4 (one of the Top-5 must-not-fail-day-1 modes): the `.spec-drift-baseline.jsonl` will accumulate every drift the team chose not to fix. Over 12 months, a starting 36-entry baseline could grow to 100+ entries if no structural defense exists. The gate then provides a false sense of confidence: "we ship clean PRs" while the entire backlog of legacy drift sits unaddressed in baseline.

## Why this is the dominant risk

Three of the gate's 28 enumerated failure modes (D1, D3, D4) are sociological rather than technical. Of those, D4 is uniquely structural — the failure happens INSIDE the baseline file (not in the gate's logic) and the gate's correctness on every PR makes it harder to notice. Compare:

- **D1 (gate becomes the new mock — too many `spec-assert-skip` markers):** visible to grep audit (`grep -rn spec-assert-skip specs/`), specialists can audit overrides quarterly
- **D3 (false-positive fatigue):** visible in PR-review fatigue metrics, mitigatable by FP triage
- **D4 (baseline rot):** invisible — the file is JSONL, looks fine, gate passes, drift compounds silently

## Three-layer defense (per spec § 5.4)

The plan + spec wire three structural defenses:

1. **`origin` field required on every entry.** No untracked drift; every entry traces back to an audit ID, PR, or issue. Enforced at SDG-301 baseline schema validation.
2. **90-day age-out timestamps.** Entries older than 90 days emit WARN; older than 180 days emit FAIL (force resolution). Implemented at SDG-303.
3. **PR description prompt + quarterly review.** When `.spec-drift-baseline.jsonl` is touched in a PR, the PR template asks "are you adding to the baseline (justify) or resolving an entry (cite SHA)?". Quarterly `chore(spec-drift): refresh baseline` PRs surface resolved entries for cleanup.

These defenses are necessary but not sufficient. The age-out FAIL only fires after 180 days; if the team learns to extend `ageout` reactively (just to keep CI green), the rot continues.

## What might go wrong despite defenses

- **Defense circumvention:** specialist hits an expired entry, extends `ageout` by another 90 days without addressing the underlying drift. The journal entry of "extending the deferral" must be visible — recommend logging extensions to a separate `.spec-drift-baseline-history.jsonl` so the audit trail of "how many times has this entry been re-extended" is grep-able.
- **Migration to "permanent" markers:** team marks every legacy entry with `<!-- spec-assert-skip ... reason:"legacy v0.x scaffold, never to be removed" -->` instead of resolving. Mitigation: D1 mitigation (quarterly review of skip markers) catches this.
- **Baseline staleness on architecture change:** when the codebase undergoes major refactor (e.g., new package added, errors module split), baseline entries reference old paths. SDG-303's `--refresh-baseline --resolved-by-sha <sha>` is the recovery path; needs documentation in skill doc + onboarding.

## Monitoring metrics post-v1.0

After the gate ships, track quarterly:

| Metric                               | Target                          | Alert threshold    |
| ------------------------------------ | ------------------------------- | ------------------ |
| Baseline entry count                 | ≤36 (initial); grow ≤10/quarter | >50 entries        |
| Entries past `ageout`                | 0 (resolve before age-out)      | >5 expired entries |
| `spec-assert-skip` directive count   | ≤30 across 72 specs             | >50 directives     |
| Resolved-archive entries / quarter   | ≥10 (steady resolution rate)    | <3 per quarter     |
| Mean time from `added` to resolution | <60 days                        | >120 days          |

If any threshold trips for two consecutive quarters, escalate: introduce mandatory `--strict` mode, tighten `ageout` to 60 days, OR retire the baseline entirely (force resolution of all remaining entries before next minor version release).

## References

- Spec: `specs/spec-drift-gate.md` § 5.4 (anti-rot mechanisms)
- Failure-points: § D4 (the risk this entry codifies)
- Plan: `02-plans/01-implementation-plan.md` § 4 (D4 row)
- Todos: SDG-301 (baseline schema with required origin), SDG-303 (age-out logic), SDG-502 (initial capture)
- Maintenance reference: `specs/spec-drift-gate.md` § 12 (Maintenance Notes)

---
type: AMENDMENT
date: 2026-07-08
slug: independent-reconvergence-enrollment-ops-length-rationale
relates_to: 0028-DECISION-merged-main-redteam-convergence-and-phase2-authorization
---

# AMENDMENT — Independent re-convergence of the onboarding suite on merged main (post PR #1620)

Extends journal/0028. That entry re-validated the suite to convergence on merged main and
shipped 17 accuracy corrections (PR #1620). This session (user directive: `/autonomize` +
`/redteam to convergence`) ran a FRESH, fully-independent 3-lens redteam on the CURRENT
merged-main state (HEAD 8e85319b7 — i.e. WITH the 17 fixes) — treating journal/0028's
convergence claim as an input to verify, not evidence to trust (`/redteam` Step-1 re-derivation
doctrine + `verify-resource-existence.md` MUST-4).

## Result — CONVERGED (independently confirmed + 2 residual LOWs fixed)

| Round | Team                                                                                                                                                                                  | Verdict                                                                        |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| R1    | reviewer + security-reviewer + cc-architect (2 lenses throttled on first wave → re-run serially per `worktree-isolation.md` Rule 4 back-off; evidence gate honored — errored ≠ clean) | 0 CRIT / 0 HIGH / 0 MED; 2 LOW actionable (fixed) + advisories (dispositioned) |
| R2    | cc-architect                                                                                                                                                                          | CLEAN 0/0/0/0                                                                  |
| R3    | reviewer                                                                                                                                                                              | CLEAN 0/0/0/0                                                                  |

Convergence criteria met: 0 CRITICAL, 0 HIGH, 2 consecutive fully-clean rounds (R2+R3).
Criteria 5-7 (new-tests / frontend-mock / eval-harness) N/A — CC-artifact accuracy
re-validation, no new code / frontend / semantic success-criteria.

## The 2 residual LOWs fixed (both in `enrollment-operations.md` § "Length rationale")

Both were self-contradictions in the rule's own meta-rationale paragraph — the
`verify-claims-before-write` class — that the prior 10-round pass did not catch:

1. **Stale self-cited line count.** The paragraph claimed "266 lines (per `wc -l`)"; actual
   `wc -l` = 268. (The SECOND APPEND had corrected 264→266; this session's own phrasing fix
   to nit #2 shifted the count to 268, and the number was re-derived against final ground
   truth AFTER the edit per `verify-claims-before-write.md` MUST-1.)
2. **Guard-count over-claim.** "SIX distinct fail-closed boundary guards as MUST clauses"
   counted all six MUSTs as guards, contradicting the same file's § "Violation scope"
   (MUST 1/2/3 guard-enforced; MUST 4/5/6 gate-review) and the Severity field. Corrected to
   "SIX MUST clauses — three fail-closed boundary guards (MUST 1/2/3) + three gate-review
   clauses (MUST 4/5/6)", now consistent across the Violation-scope, Severity, and
   Detection-mechanism fields and the actual 6-MUST body structure.

## Evidence gaps closed by direct re-derivation this session (NOT trusting prior self-reports)

- `scan-synced-disclosure.mjs` RAN clean — 0 findings across 1558 files (the journal/0028
  "0 findings" claim independently re-confirmed with the actual scanner run this session).
- `host_role:ci` forever-ineligible + 2-of-N owner co-sign re-derived from `fold-rule-9c.js`
  (":127/:148/:393/:753" owner-role + host_role!=ci; ":10/:386/:745" 2-of-N).
- `business_roles` enum = exactly 3 (platform/capability/business; product-owner excluded)
  re-derived from `operators.roster.schema.json`.
- `permissions.deny` set (posture.json + violations.jsonl + .initialized + .posture-upgrade-nonce
  only) re-derived from `settings.json`; roster/coord-log on STATE_PATH_RX + integrity-guard.

## Dispositioned (NOT fixed — recorded for transparency)

- cc-architect advisory: extract MUST-1 passthrough detail (~19 lines) to skill 45 —
  ACCEPT no-change (advisory "recommend, don't block"; restructures a load-bearing MUST; the
  rule is within its named length-rationale budget).
- reviewer informational: `runEnrollmentCeremony` success branch also returns `record` (un-
  enumerated in the shorthand) — ACCEPT no-change ("nothing stated is false"; under-spec, not
  a defect).
- My R1 dispatch brief mis-attributed a "private org slug — scrub" note to journal/0028; the
  note actually lives in the loom proposal's Gate-1 scrub prose, and the merged-main artifact
  carries no slug (only `{owner}`/`{org}` placeholders) — verified by full read + shape-grep.

## Disposition

Fix landed as a working-tree edit on codify branch `codify/esperie-2026-07-08` (BUILD repo —
owner-gated). Appended to `.claude/.proposals/latest.yaml` `onboarding-suite-accuracy-corrections`
as the THIRD APPEND (status stays pending_review) so loom Gate-1 distributes the correction to
every downstream consumer of the synced suite. `last_codified` NOT advanced (scoped accuracy
landing, not the full-backlog codify; the 66 `test_pattern` telemetry observations remain).

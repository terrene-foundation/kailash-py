# DECISION — /redteam re-convergence on the post-v2.48.0 codify wave (polish)

**Date:** 2026-07-11
**Phase:** 04-validate (re-run to convergence)
**Posture:** L5_DELEGATED (un-enrolled PUBLIC repo; no `posture.json`; coordination OFF/solo)

## Scope

Independent re-run of `/redteam` to convergence over the post-v2.48.0 codify delta on main
(the 3 artifacts changed since tag `v2.48.0`): `.claude/rules/handoff-completion.md` (NEW
baseline rule), `.claude/rules/cross-sdk-inspection.md` (new Rule 4d + shared-ack
normalization, PRs #1674/#1682), `.claude/.proposals/latest.yaml`. Parallelized — 3 adversarial
agents R1 (rule-quality / code-example-correctness / disclosure+citation), 1 R2 (post-fix diff
re-read), 1 R3 (fresh-eyes full-file), + R4 mechanical sweep battery.

## Convergence — 2 consecutive clean rounds (R3 + R4), 0 CRIT / 0 HIGH

Criteria 1-3 met; 4 (assertion tables AST/grep-verified), 5 (Rule 4d behavioral pin
`tests/regression/test_issue_1510_bh5_circuit_breaker.py:175/197` verified by the R1 code agent),
6-7 N/A (no frontend; the adversarial agents are the semantic-probe layer for a COC-artifact wave).

## Findings + dispositions

| #      | Sev       | Finding                                                                                                                                                                                                                                  | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------ | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MED-A  | MED       | `handoff-completion.md` Origin miscited `Grant + receipt: journal/0010` (0010 = grant only; the rs#1732 receipt is `journal/0011`) — the rule dogfooding its own MUST-2 / verify-claims-before-write                                     | FIXED → `Grant: journal/0010; receipt: journal/0011`                                                                                                                                                                                                                                                                                                                                                                                                                  |
| MED-B  | MED       | `cross-sdk-inspection.md` Rule 4d (post-MUST-8-cutoff clause) minted an unregistered dedicated trigger key `cross_sdk_signed_field_addition`, deviating from the fleet convention (generic `regression_within_grace`)                    | FIXED → routes generic, canonical "Named deviation" phrasing matching `security.md`/`git.md`                                                                                                                                                                                                                                                                                                                                                                          |
| MED-C  | MED       | **self-introduced by the MED-B fix** — the first rationale draft wrongly called Rule 6 "grandfathered pre-cutoff"; Rule 6 landed via `journal/0402` (same `/sync-from-build` py Shard B batch as security.md/git.md post-cutoff clauses) | FIXED R2 → dropped the false sibling claim, adopted fleet-standard canonical-key-per-clause phrasing                                                                                                                                                                                                                                                                                                                                                                  |
| LOW-B  | LOW       | PR #1682's shared-ack normalization skipped Rule 4b's Receipt line                                                                                                                                                                       | FIXED → 4b/4c/4d/6 now uniform                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| LOW-A  | LOW       | bare `journal/NNNN` citations are workspace-ambiguous                                                                                                                                                                                    | ACCEPTED — established citation convention across the whole rule corpus                                                                                                                                                                                                                                                                                                                                                                                               |
| C-DISC | HIGH→disp | `.claude/.proposals/latest.yaml` reason-prose carries the real own-org `esperie-enterprise` at 10 sites (repo is PUBLIC)                                                                                                                 | NOT wave-introduced / NON-BLOCKING — both NEW rule files are 0-hit; org is loom's **allowlisted own-org** already in 127 tracked files; file is `isNeverSynced` (non-cascading); every hit is meta-commentary where a mechanical scrub would falsify the Gate-1 templatize-at-source directives the proposal itself carries (`:350-356`); already self-flagged for loom Gate-1 (`:24-25`). Repo-wide own-org question → **surfaced to human**, routed to loom Gate-1. |

MUST-2 dogfood PASS: all 7 cited-as-landed PR/issues verified via `gh` (#1510 CLOSED; #1671/#1672/#1682/#1678/#1679/#1674 MERGED).

## Landed

Fixes on `codify/redteam-postconvergence-polish` — 2 files, 3 lines. Interim BUILD-side to keep
main correct; the rules are loom-bound (proposal → Gate-1) so the durable home is `latest.yaml`.

## Open for human (surfaced, not self-authorized)

- **latest.yaml own-org disclosure (C-DISC):** repo-wide `esperie-enterprise`-in-public question.
Recommend loom Gate-1 templatize-at-source (`esperie-enterprise/kailash-rs` → `build.rs`) as the
proposal already directs; a BUILD-side mechanical scrub is BLOCKED (corrupts the Gate-1 directives).
</content>

</invoke>

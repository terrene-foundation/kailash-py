---
type: DECISION
date: 2026-07-11
topic: Fifth-pass /redteam independent re-convergence — 1 MED found+fixed, then 2 clean rounds
relates_to: 0018-DECISION-redteam-fourthpass-reconvergence
report: workspaces/sdk-backlog/04-validate/redteam-2026-07-11-fifthpass.md
---

# DECISION — fifth-pass /redteam re-convergence (post-v2.48.0 codify wave)

## Verdict

**CONVERGED** on current main (`4947a4a2d`), posture L5_DELEGATED, solo/coordination-OFF.
3 rounds, 10 adversarial clusters + 3 orchestrator Bash evidence-gate sweeps, all under
`/autonomize` parallelized. Unlike passes 1–4 (which independently re-confirmed a clean state),
**this pass surfaced a genuine MED that all four prior passes missed** — the value of re-deriving
per `verify-resource-existence.md` MUST-4 rather than inheriting a prior verdict.

## What changed (the one durable edit)

`.claude/.proposals/latest.yaml` — the `handoff-completion` `rule_add` entry gained the
loom-Gate-1 rule-authoring-Rule-10 emission-budget flag it was missing (matching the
`security.md`/`git.md` sibling entries appended the same cycle). BUILD-owned `isNeverSynced`
proposal → the annotation is durable BUILD-side (not `/sync`-reverted). Verified: YAML parses
25/pending_review; only this entry differs from HEAD (semantic deep-equal on the other 24);
esperie-enterprise count unchanged (9); cited named-rationale template exists.

## Findings

- **R1 MED (found by the analyst fresh-eyes lens, fixed same session):** the new priority:0
  baseline rule `handoff-completion.md` had its latest.yaml entry dispose Rule 10 (which fires
  AS IF the whole ~116-line body were new load-bearing content — the largest emission class) with
  only a one-line note, omitting the `emit.mjs --all --dry-run` headroom-check flag its ~25-line-clause
  siblings carry. Root-cause fix applied BUILD-side; same-bug-class sweep confirmed handoff was the
  SOLE new-baseline entry missing it (security/git already flagged; command-skill-parity path-scoped-exempt).
- **R2-A candidate LOW → NON-FINDING:** "codify_session prose omits tenant-isolation" was adjudicated
  a false positive — the same-bug-class sweep showed ~17 of 25 entries are un-narrated because
  `codify_session` is by-wave prose, not a per-entry index (the authoritative `changes[]` manifest,
  which Gate-1 processes, carries the complete self-contained entry). An exploratory reconciliation edit
  was made then REVERTED. Independently re-confirmed by two Round-3 clusters.
- **R3-C OBSERVATION (non-blocking):** the latest.yaml git line-diff is large (quote-style
  reserialization by the deployment formatter) though semantically one entry changed — flagged so a
  future line-diff reviewer isn't misled.

## Convergence criteria

1 (0 CRIT) ✅ · 2 (0 HIGH) ✅ · 3 (2 consecutive clean rounds, every reviewer genuinely ran) ✅ (R2+R3) ·
4 (spec = rule-authoring/trust-posture contract, grep/AST-verified) ✅ · 5/6/7 N/A (0 `*.py`, no frontend,
adversarial clusters ARE the semantic-probe layer).

**Evidence-gate honesty:** several clusters hit `ENOENT rg` (ripgrep unavailable); per
`evidence-first-claims.md` MUST-3 those errored returns were counted as ZERO evidence — each fell back to
direct Read, and the orchestrator closed the one residual gap (secrets/esperie across the non-enumerable
journal span) with a Bash `grep -rnE` sweep (0 secrets; all 32 esperie hits own-org). No dimension was
certified clean on an errored tool. Pytest tiers N/A by construction (artifact-only wave), stated explicitly.

## Follow-ups (loom Gate-1, surfaced not self-authorized)

- **NEW this pass:** run `emit.mjs --all --dry-run` for the `handoff-completion` baseline-rule emission
  budget (the R1 MED's loom-side resolution — now flagged in latest.yaml matching the security/git siblings).
- Carried (unchanged): F5 handoff-completion eval-harness validation; F6 latest.yaml own-org
  `esperie-enterprise` templatize-at-source; F7 cross-sdk-inspection 306-line length-rationale;
  handoff-completion self-referential-codify allowlist decision.

## User-gated action (BUILD repo)

The R1 MED fix is a working-tree change in `.claude/.proposals/latest.yaml`, **not committed** — BUILD-repo
commits stay with the user per the operating envelope. Surfaced for the user to commit/PR.

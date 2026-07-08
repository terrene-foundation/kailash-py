---
type: DECISION
date: 2026-07-08
slug: merged-main-redteam-convergence-and-phase2-authorization
---

# DECISION — Onboarding suite re-validated to convergence on MERGED main + Phase-2 cross-repo authorization

## What (Part 1 — merged-main redteam convergence)

Re-ran `/redteam` to convergence on the **merged `main` state** of the Phase-1 onboarding
COC suite (the state shipped by PR #1619), by independent multi-agent re-derivation —
NOT trusting the prior convergence self-report (journal/0027, which validated the
PRE-MERGE working-tree edits). Doctrine: `/redteam` Step-1 "re-derive every check from
scratch; a prior round's self-report is an input to verify" + `user-flow-validation.md`
MUST-1 (validate the actually-shipped artifact).

**Result: CONVERGED.** 0 CRIT / 0 HIGH held EVERY round (R1–R10); 2 consecutive fully-clean
rounds (R9 + R10, all three specialists — reviewer + security-reviewer + cc-architect —
genuinely run). This satisfies the `self-referential-codify.md` Rule-1 mandatory multi-agent
gate for the allowlisted surfaces touched (enrollment-operations.md,
multi-operator-coordination-substrate.md, genesis-migration-n1, the skills).

## GAP — the pre-merge pass missed drift only visible on merged main

Every claim below was verified against ground-truth source (settings.json / fold-rule-9c.js /
operators.roster.schema.json / operator-id.js / workspace-utils.js /
validate-bash-command.js / sync-flow.md). ~17 corrections across 9 files:

- **permissions.deny false-claim residual (same class as journal/0027's rule-file fix, but
  MISSED in the depth files):** skills/43-ecosystem-init:122 credited settings.json
  `permissions.deny` as covering roster/coordination-log ("matching the same paths"). Real
  deny = posture.json + violations.jsonl + .initialized + .posture-upgrade-nonce ONLY;
  roster/coord-log rest on STATE_PATH_RX + integrity-guard. Same-class sweep
  (`zero-tolerance.md` 1a) found + fixed the identical residual in
  genesis-migration-n1:137 + multi-operator-coordination-substrate.md:326.
- **skills/41-onboard read-only-contract table:** roster shape `{operators:[...]}` → the real
  `persons` MAP `{genesis, persons:{<pid>:{...}}}`; resolveIdentity under-spec → full shape;
  team-memory → runbook-accurate `{slug,body,signed,promoted_by}`; detectActiveWorkspace →
  actual `{name,path}`; skill `name:` → `41-onboard` (sibling convention). `--json` 7→8 keys
  ("eight section keys"; onboard.md gains `action_items`).
- **skills/44-enroll:37 + commands/enroll.md:47:** "four business roles" → "three" (enum has 3;
  product-owner excluded per schema).
- **stale fold-rule-9c.js LINE citations** (shifted by the F122 ADO insertion) → grep-stable
  SYMBOLS (`foldGenesisMigration`, `CO_SIGN_ANCHOR_KIND_ORG_ADMIN`) per
  `symbol-anchored-citations.md`, at genesis-migration-n1:11 + substrate:303/361. The
  substrate:378 F86 CLOSED-forest historical closure-receipt line-range is LEFT AS-IS
  (frozen point-in-time audit record, commit-SHA-anchored, `spec-accuracy.md` Rule 6 exempt).
- **skills/45-genesis-bootstrap:14 + enrollment-operations.md:249:** "loom-only and absent from
  BUILD/USE repos" was FALSE — the guide IS present in BUILD repos
  (.claude/guides/co-setup/11-genesis-ceremony.md), `use_excluded` from USE consumers per
  sync-flow.md. Corrected to accurate `use_excluded` framing, consistent with the suite's
  own other files (skill 43:95, whoami.md:152).

## Refuted / dispositioned (NOT defects)

- Security grep flagged `esperie-enterprise/loom` in validate-bash-command.js:888 — **REFUTED**
  by the authoritative `scan-synced-disclosure.mjs` (0 findings across 1558 files;
  esperie-enterprise is loom's ALLOWLISTED own-org).
- substrate:378 F86 closure-receipt stale line-range — historical audit record, exempt.
- skills/42-certify `name: certify` — out-of-suite-scope + genuinely-mixed repo naming
  convention; cc-architect below-LOW non-finding, NOT changed.

## Disposition

11 fixes → 17 corrections landed as working-tree edits on codify branch
`codify/esperie-2026-07-08` (BUILD repo — owner-gated). Appended to
`.claude/.proposals/latest.yaml` `onboarding-suite-accuracy-corrections` (SECOND APPEND,
status stays pending_review) so loom Gate-1 distributes the corrected mechanics to every
downstream consumer of the synced suite. `last_codified` NOT advanced (this is a scoped
accuracy landing, not the full-backlog codify; the 66 telemetry observations remain).

## Cross-repo authorization (Phase 2) — receipt-before-command per repo-scope-discipline.md

User (`esperie`, owner) explicitly re-confirmed Phase 2 in this session (2026-07-08): verbatim
"approved both" in direct response to the agent restating the target repos + bounded actions
(the two decisions surfaced at end of the redteam-convergence report). This re-confirms the
prior verbatim authorization recorded in `00-PROGRAM.md` (2026-06-23):

cross-repo-authorized: esperie-enterprise/kailash-rs
requester: esperie (owner)
action: (1) read-only inspect rs multi-operator substrate state; (2) enroll multi-operator
(genesis bootstrap, esperie owner, adjusted for the esperie-enterprise org/owner);
(3) roll out the Phase-1 onboarding artifact suite (PRs to rs main, each its own redteam/CI).
verbatim (2026-06-23): "see kailash-rs and I authorize you to update that" + "roll this out
to kailash-rs."
reconfirmed (2026-07-08): "approved both".

cross-repo-authorized: terrene-foundation/loom
requester: esperie (owner)
action: file ONE scrubbed GH issue — the genesis-ceremony bootstrap runbook
(guides/co-setup/11-genesis-ceremony.md) is loom-only + use_excluded from BUILD/USE
consumers; recommend syncing it (or the reconstructed onboarding skill) downstream.
Scrub per upstream-issue-hygiene.md; per-issue human gate on the body before filing.
verbatim (2026-06-23): "file 2 into loom as gh issue."
reconfirmed (2026-07-08): "approved both".

Discipline still holds per repo-scope-discipline.md § User-Authorized Exception: this receipt
lands BEFORE the first command in each target; each cross-repo write stays scoped exactly to
the named action against the named repo; the loom issue body passes a per-issue human gate
(upstream-issue-hygiene.md MUST-1) before submission.

# 0001 — DECISION: Onboarding COC artifact suite authored + codified (BUILD→loom)

**Date:** 2026-06-23 (UTC; matches the codify branch + lease stamps)
**Workspace:** mops-onboarding (Phase 05-codify)
**Author:** agent, operating under genesis owner `esperie` (`pid-esperie-2b8cb994`)
**Program:** `workspaces/mops-onboarding/00-PROGRAM.md` (APPROVED by user 2026-06-23)

## Value-anchor (user directive, verbatim)

> "create the coc artifacts as experts and skills and rules to help with the enrolment and
> genesis onboarding / operations. So far, teams are seriously struggling! roll this out to
> kailash-rs and then codify a proposal for loom" + "the proposal for loom should remind it
> to roll out to all downstream use as well."

## Decision

Authored the **Phase-1 onboarding COC artifact suite** — the reconstruction of the loom-only
genesis-bootstrap runbook (`guides/co-setup/11-genesis-ceremony.md`, absent from BUILD/USE
repos) plus the five hard-won fail-closed guard traps surfaced during the 2026-06-23 kailash-py
multi-operator enrollment:

1. **Skill** `.claude/skills/45-genesis-bootstrap/SKILL.md` — fresh-repo first-owner bootstrap
   runbook (pre-flight 5 gates, sequence, org-vs-user + #358 org-admin relaxation, the
   script-by-path trap, fold-clean verify, troubleshooting matrix).
2. **Rule** `.claude/rules/enrollment-operations.md` — path-scoped (priority:10), 6 MUST clauses
   (signing-first, codify-branch+lease, script-by-path, fold-clean-before-enrolled,
   self-enroll-own-machine, org-admin-relaxation-org-only) + canonical 8-field Trust Posture
   Wiring + Length rationale.
3. **Agent** `.claude/agents/onboarding/coc-onboarding-specialist.md` — operator-lifecycle expert
   tying /ecosystem-init → /enroll → genesis bootstrap → /onboard → /claim//posture//release-claim
   - the guard-trap recovery table.

All three are **generic** (no operator-specific identity values; placeholders only) — they sync
to loom → all downstream.

## Ground-truth correction (verify-claims-before-write MUST-2)

The prior session's `.session-notes` TRAP imprecisely claimed "`node -e`/`python3 -c` are BLOCKED
(all inline interpreters flagged, even read-only)." Re-verified against
`validate-bash-command.js`: the actual mechanism is `detectStateFileMutation` — a three-layer
detector (redirects / file-utilities / interpreter `-c`/`-e`/`-m` bodies, docstring at
`violation-patterns.js:794-806`) that blocks ONLY a body that **writes a watched state file**
matching `STATE_PATH_RX` (roster, coordination-log, posture, violations, .initialized, caches).
Read-only `node -e` passes. The artifacts encode the corrected, precise mechanism.

## Multi-agent redteam — convergence receipt (self-referential-codify MUST-1)

Self-referential surface (`.claude/rules/**`, `.claude/skills/**`) → mandatory multi-agent
redteam. Dispatched reviewer + security-reviewer + cc-architect; throttle hit the 3-concurrent
cold-start burst (worktree-isolation Rule 4 falsifiable signal: ≥2 deaths in ~30-48s, "not your
usage limit"), so re-ran SERIALLY (concurrency back-off).

| Reviewer          | task-id             | R1 (original)               | R2 (final/fixed state)                                   |
| ----------------- | ------------------- | --------------------------- | -------------------------------------------------------- |
| reviewer          | `ad97b31f23c501e4c` | 1 MED + 1 LOW               | **CLEAN** (0/0/0/0; all citations re-grep-resolve)       |
| security-reviewer | `a4a3c6fb36bd7236d` | CLEAN                       | **CLEAN** (4 dims; disclosure re-scan of rewritten rule) |
| cc-architect      | `a92bd9db52f23d3d6` | 2 HIGH + 1 LOW + 1 advisory | **CLEAN** (+ explicit fix-regression check)              |

R1 findings, all resolved: HIGH-1 rule 238>200 (trimmed redundant API depth → pointed MUST-3 to
the skill + added named Length rationale, verified count); HIGH-2 agent desc 135>120 (→119);
MED skill desc 327>200 (→180); LOW-1 CC tool-nouns in prescriptive prose (4 sites → neutral
"tracked-file write"; kept literal `permissions.deny on Edit/Write`). Convergence = all three
specialists CLEAN on the byte-identical final state, cc-architect performed the fix-induced
regression check the 2-consecutive criterion exists to guarantee. No code test-tiers apply
(prose artifacts); verification = the redteam + the post-merge user-flow walk.

## Allowlist-omission DECISION (cc-architect advisory; verify-claims omission-precedent shape)

`enrollment-operations.md` + `45-genesis-bootstrap` are **NOT added** to
`self-referential-codify.md` Rule 2's allowlist. They govern the one-time genesis/enrollment
CEREMONY, not `/codify`'s own machinery; the rule is a CONSUMER of the codify lease, not the
lease's contract author (`codify-lease.js` + `knowledge-convergence.md` MUST-3 remain the
authoritative + already-allowlisted lease surfaces). THIS codify's redteam fired regardless
because the artifacts land under the Rule-2 `paths:` load-trigger globs (`.claude/rules/**`,
`.claude/skills/**`). If a future edit wires the rule into the lease CONTRACT (not just its use),
add it then with named rationale.

## Phase status + outstanding

- **Phase 1 (build):** DONE — suite authored + converged + this codify.
- **Phase 3 (loom proposal):** appended 3 changes (suggested GLOBAL) to the pending_review
  `latest.yaml`, carrying the user's reminder: loom MUST distribute to **ALL downstream USE
  templates via `/sync-to-use`, not only the BUILD repos**.
- **Phase 2 (cross-repo — DEFERRED to a fresh user re-confirmation):** the program records
  user authorization (2026-06-23) for (a) ONE scrubbed loom GH issue re the absent runbook, and
  (b) enrolling + rolling out to `esperie-enterprise/kailash-rs`. Per `repo-scope-discipline.md`
  these require a journaled `cross-repo-authorized:` receipt + a genuine user re-confirm BEFORE
  the first command in each target. NOT executed this session; surfaced to the user for the gate.

# PROGRAM — Multi-Operator Onboarding Artifacts + Cross-SDK Rollout + Loom Proposal

**Status:** APPROVED by user 2026-06-23. Execute in a fresh session.
**Origin/value-anchor:** user directive — _"create the coc artifacts as experts and
skills and rules to help with the enrolment and genesis onboarding / operations. So far,
teams are seriously struggling! roll this out to kailash-rs and then codify a proposal for
loom"_ + _"the proposal for loom should remind it to roll out to all downstream use as well."_

## Context (what already happened, 2026-06-23 session)

kailash-py was **enrolled for multi-operator coordination** this session (the substrate was
installed-but-unenrolled). Done: SSH signing (`id_ed25519`, repo-local), bootstrap roster
(esperie = sole genesis owner, PR #1435 on main), genesis-anchor folded clean (accepted, 0
rejected/forks), `allowed_signers` wired. The codify-lease etc. now function. **This session's
hands-on enrollment IS the reference procedure** the Phase-1 artifacts must capture — teams
struggle precisely because the authoritative runbook (`guides/co-setup/11-genesis-ceremony.md`)
is loom-only and absent from BUILD/USE repos.

## Phase 1 — Onboarding COC artifact suite (kailash-py, in-scope; build FIRST)

Author via a Workflow with the **mandatory self-referential-codify multi-agent redteam**
(agents/skills/rules are allowlisted surfaces → reviewer + security-reviewer + cc-architect
to convergence). Three artifacts:

1. **Agent — `agents/onboarding/coc-onboarding-specialist.md`** (synced specialist). The
   operator-lifecycle expert: `/ecosystem-init` (fork) → `/enroll` (operator) → genesis
   bootstrap → `/onboard` → `/claim`/`/posture`/`/release-claim`, plus the operational traps
   below. Tools: Read, Bash, Grep, Glob (+ Edit for config fixes).
2. **Skill — `skills/45-coc-onboarding/SKILL.md`** (or extend `43-ecosystem-init`/`44-enroll`
   — design call). The **genesis-bootstrap runbook reconstructed** (the absent loom runbook):
   fresh-repo first-owner bootstrap; org-vs-user; the org-owned-admin relaxation (issue #358);
   the 5 gates + pre-flight; troubleshooting; the script-by-path patterns.
3. **Rule — `rules/enrollment-operations.md`** (`scope: path-scoped` → no baseline budget;
   paths: `.claude/operators.roster.json`, `.claude/commands/{enroll,whoami,ecosystem-init,onboard}.md`).
   MUST clauses (8-field Trust Posture Wiring): configure signing key BEFORE any roster write
   (degraded-read-only mode); roster writes on a `codify/<id>-<date>` branch; ceremony via
   **script-by-path, never `node -e`/`python -c`** (the bash tripwire blocks all inline
   interpreters); verify the genesis **folds clean** before declaring "enrolled"; teammates
   self-enroll from their OWN machines; org-admin relaxation ONLY for org-owned repos.

### THE OPERATIONAL PROCEDURE / TRAPS the artifacts must encode (hard-won this session)

- **Degraded read-only until a signing key is configured** (`signing-mutation-guard.js`) —
  configure SSH signing (`git config --local gpg.format ssh; user.signingkey <pub>`) FIRST,
  else every tracked-file mutation is blocked.
- **`node -e` / `python3 -c` are BLOCKED** by `validate-bash-command.js` (all inline
  interpreters flagged as Layer-3 state-mutation, even read-only). Route every ceremony step
  through a **Write-tool script run as `node <file>`** (script-by-path works; bundling `node`
  with heredocs/`gh` in one command re-trips the detector — keep `node <file>` a bare command).
- **Roster write path:** `integrity-guard.js` permits `operators.roster.json` writes on a
  `codify/<id>-<date>` branch (block off-codify-branch). The first roster is hand-authored on
  that branch (the `/whoami --register` node script assumes an existing roster). Schema-validate
  via `node <script>` calling `roster-schema-validate.js` (`valid:true` is a hard gate).
- **coordination-log.jsonl + .initialized are gitignored** (per-clone local state) — the
  genesis-anchor append is local; no commit/PR; the genesis-anchor-guard tool-bypass marker is
  NOT needed when appending via `node` fs.
- **person_id** = map-key (resolveIdentity matches by `keys[].fingerprint`, not by re-deriving
  the short-fp). py used `pid-esperie-2b8cb994`.
- **Genesis ceremony** = `runEnrollmentCeremony({roster, repo:{owner,name}, signingKeyPath:
<PRIVATE key>, signingKeyFingerprint:<SHA256:..>, ghApi:<gh-subprocess wrapper>,
transportAppend:<sync fs.appendFileSync of the signed record>})`. Fail-closed.
- **Verify** with `coordination-log.js::foldLog(records, roster, {})` → accepted=1, rejected=[],
  forks=[]. Then `operator-id.js::resolveIdentity(repo)` → owner.
- **allowed_signers** (`gpg.ssh.allowedSignersFile`) for local commit verify — consider
  generating it FROM the roster (all operators' keys) as part of the skill.

## Phase 2 — Cross-repo (USER-AUTHORIZED 2026-06-23; receipt-gated)

> **`repo-scope-discipline.md` — the fresh session MUST land a `cross-repo-authorized:` journal
> receipt (requester, target, action, verbatim instruction, timestamp) AND re-confirm with the
> user (a genuine user turn) BEFORE the first command in each target.** The authorization below
> was given this session; record it, but the receipt-before-command discipline still holds.

- **`cross-repo-authorized: <loom>`** — file ONE scrubbed GH issue: the genesis-ceremony
  bootstrap runbook (`guides/co-setup/11-genesis-ceremony.md`) is loom-only and absent from
  BUILD/USE repos; recommend syncing it (or the new onboarding skill) downstream. Scrub per
  `upstream-issue-hygiene.md` (no operator-key material; terrene-foundation paths are canonical/OK).
  No other loom writes. Verbatim: _"file 2 into loom as gh issue."_
- **`cross-repo-authorized: esperie-enterprise/kailash-rs`** — Verbatim: _"see kailash-rs and I
  authorize you to update that"_ + _"roll this out to kailash-rs."_ Steps: (1) read-only inspect
  rs substrate state (enrolled? `esperie-enterprise` is a DIFFERENT org → the genesis owner/
  admin checks differ from py's terrene-foundation; rs may be user- or org-owned — check);
  (2) enroll multi-operator (genesis bootstrap, esperie owner, mirroring py, adjusted for the
  org/owner); (3) roll out the Phase-1 artifact suite (PRs to rs main). Each its own redteam/CI.

## Phase 3 — Loom proposal (kailash-py, in-scope)

`/codify` BUILD→loom proposal (`.claude/.proposals/latest.yaml`, append-or-archive per
`artifact-flow.md`) carrying the Phase-1 suite, suggested **GLOBAL**. **EXPLICITLY remind loom:
distribute to ALL downstream USE templates via `/sync-to-use`, not only the BUILD repos**
(user directive). The loom GH issue (Phase 2-loom) + this proposal are the paired fix for the
absent-runbook gap.

## Recommended order

Phase 1 (build + redteam to convergence) → Phase 2-loom issue → Phase 2-rs (enroll + rollout)
→ Phase 3 proposal. Building Phase 1 first means rs-rollout and the loom proposal both carry the
finished, converged suite.

# Phase 2-rs Handoff Brief — Enroll + Roll Out the Onboarding Suite to kailash-rs

**Status:** READY TO RUN — in a fresh Claude Code session opened **inside the kailash-rs repo**.
**Authored:** 2026-06-24, from the kailash-py mops-onboarding workspace (the reference enrollment was kailash-py, 2026-06-23).
**Decision (2026-06-24):** user chose to run Phase 2-rs from a **dedicated kailash-rs session** (not cross-repo from kailash-py). This brief is the bridge.

---

## 0. Why this is in-scope for the rs session (NOT a cross-repo action)

When you open Claude Code **inside kailash-rs**, that repo IS the session's CWD and entire scope.
Enrolling rs and rolling out artifacts to rs is **in-scope, ordinary work** for that session — it does
NOT need a `cross-repo-authorized:` receipt (that discipline only applies when a session reaches OUT
to a different repo). The kailash-py→kailash-rs gating only existed because the _prior_ sessions ran
in kailash-py. Running natively in rs dissolves it.

What you DO still owe in the rs session: the genesis-bootstrap gates below (signing-first, codify-branch
roster write, fold-clean verify) — these are enrollment-ceremony discipline, not cross-repo discipline.

## 1. Objective

1. **Inspect** rs substrate state (is the multi-operator substrate present? is rs already enrolled? is rs org- or user-owned?).
2. **Enroll** rs for multi-operator coordination — genesis bootstrap, `esperie` as the sole genesis owner, mirroring the kailash-py enrollment, adjusted for rs's org/owner.
3. **Roll out** the onboarding suite (agent + skill + rule) to rs.

## 2. Context — what already shipped (kailash-py side)

The kailash-py enrollment on 2026-06-23 WAS the reference procedure. Its codified output — the suite you
are rolling out — is already on kailash-py `main` (PR #1436) and staged in the loom proposal pipeline:

- **Agent:** `.claude/agents/onboarding/coc-onboarding-specialist.md` — operator-lifecycle expert.
- **Skill:** `.claude/skills/45-genesis-bootstrap/SKILL.md` — the fresh-repo first-owner bootstrap runbook.
- **Rule:** `.claude/rules/enrollment-operations.md` — `scope: path-scoped` MUST clauses for enrollment.
- **Loom proposal:** kailash-py `.claude/.proposals/latest.yaml` (`status: pending_review`) carries these as
  suggested **GLOBAL**, with the reminder to loom to `/sync-to-use` to ALL downstream USE templates.

## 3. Pre-flight — inspect rs substrate (read-only, run FIRST)

```bash
# (a) Is rs org-owned or user-owned? (determines the genesis anchor — see §5)
gh api repos/esperie-enterprise/kailash-rs --jq '.owner.type'   # "Organization" vs "User"

# (b) Is the multi-operator substrate even PRESENT in rs?
ls .claude/hooks/lib/coordination-log.js \
   .claude/hooks/lib/operator-id.js \
   .claude/hooks/signing-mutation-guard.js 2>/dev/null
#   -> if MISSING: the substrate must arrive first. Pull the latest COC artifacts
#      (the rs USE-template sync / loom /sync-to-build) BEFORE enrolling. The
#      ceremony helpers (runEnrollmentCeremony, foldLog) live in these libs.

# (c) Is rs ALREADY enrolled? (don't double-enroll)
ls .claude/operators.roster.json 2>/dev/null            # roster present == likely enrolled
ls .claude/learning/coordination-log.jsonl .claude/learning/.initialized 2>/dev/null
#   -> if a roster + genesis-anchor chain already exist and fold clean, rs is enrolled;
#      skip §5, go to §6 (suite rollout) only.
```

**Disposition from §3:**

- Substrate absent → roll out / sync the COC artifacts to rs first, THEN enroll.
- Substrate present, not enrolled → proceed to §5.
- Already enrolled → skip to §6.

## 4. The 5 enrollment traps (hard-won on kailash-py — do NOT relearn them)

1. **Degraded read-only until a signing key is configured.** `signing-mutation-guard.js` blocks every
   tracked-file mutation until SSH signing is set. Configure it FIRST:
   `git config --local gpg.format ssh` ; `git config --local user.signingkey <PUBLIC-key-path>`.
2. **`node -e` / `python3 -c` are BLOCKED** by `validate-bash-command.js` (all inline interpreters are
   flagged as state-mutation, even read-only). Route every ceremony step through a **Write-tool script run
   as a bare `node <file>`** — do NOT bundle `node` with heredocs/`gh` in one command (re-trips the detector).
3. **Roster write path:** `integrity-guard.js` permits `operators.roster.json` writes ONLY on a
   `codify/<display_id>-<date>` branch. Hand-author the first roster on that branch (the `/whoami --register`
   script assumes an existing roster). Schema-validate via `node <script>` calling `roster-schema-validate.js`
   (`valid:true` is a hard gate).
4. **`coordination-log.jsonl` + `.initialized` are gitignored** (per-clone local state). The genesis-anchor
   append is local — no commit/PR for it.
5. **Verify the genesis FOLDS CLEAN before declaring "enrolled":** `foldLog(records, roster, {})` →
   `accepted=1, rejected=[], forks=[]`; then `operator-id.js::resolveIdentity(repo)` → returns the owner.

(`person_id` is the roster map-key — `resolveIdentity` matches by `keys[].fingerprint`, not by re-deriving a
short fingerprint. kailash-py used `pid-esperie-2b8cb994`; rs gets its own.)

## 5. Genesis bootstrap (esperie = sole genesis owner)

Run the `45-genesis-bootstrap` skill if it is available in the rs session; otherwise follow its shape directly:

1. Configure SSH signing (trap 1).
2. Create the codify branch: `git checkout -b codify/esperie-<date>` (trap 3).
3. Hand-author `.claude/operators.roster.json` on that branch — `esperie` as sole `role: owner`, the enrolled
   signing key, the rs genesis facts (`repo_owner` = the rs org/user from §3a, `provider: github`).
4. Schema-validate the roster (`roster-schema-validate.js` → `valid:true`).
5. Run the ceremony via a `node <file>` script:
   `runEnrollmentCeremony({ roster, repo: { owner: <from §3a>, name: "kailash-rs" }, signingKeyPath: <PRIVATE key>, signingKeyFingerprint: "SHA256:...", ghApi: <gh subprocess wrapper>, transportAppend: <fs.appendFileSync of the signed genesis-anchor record> })`. Fail-closed.
6. **org-vs-user anchor (the one real rs difference from py):**
   - **Org-owned** (`Organization` from §3a) → the genesis anchor uses the **#358 org-admin relaxation**:
     a fresh gh-api-bound **verified-active org-admin attestation** (`role: admin` + `state: active`) is the
     structural anchor in place of a signed root commit. Captured into the signed `genesis-anchor` record.
   - **User-owned** (`User`) → the **signed root commit** is the only anchor (as on kailash-py). No relaxation.
7. Verify the fold is clean (trap 5). Wire `allowed_signers` (`gpg.ssh.allowedSignersFile`) — consider
   generating it FROM the roster as part of the skill.
8. Land the roster via PR on the codify branch + admin-merge (owner workflow).

## 6. Roll out the onboarding suite to rs

Two paths — **prefer the pipeline**:

- **Preferred — via loom (the canonical COC flow):** the suite is already in the Phase-3 loom proposal
  (`status: pending_review`). Once loom ingests it at Gate-1 and runs `/sync-to-build` to kailash-rs, rs
  receives the agent/skill/rule with rs-variant overlays automatically. No direct authoring needed; this is
  the audit-trailed path. (rs may need its own pull/sync cadence to pick it up.)
- **Direct (only if you want it in rs immediately, ahead of the pipeline):** author the three artifacts as
  PRs to rs `main`, using the kailash-py versions as the reference, adapted to rs's `.claude/` layout +
  variant structure. Each gets its own redteam (reviewer + security-reviewer + cc-architect, per
  `self-referential-codify.md` — agents/skills/rules are allowlisted surfaces) + CI. Mind cross-SDK-first.

## 7. Definition of done

- [ ] rs substrate confirmed present (§3b).
- [ ] rs ownership type confirmed (§3a) → correct genesis anchor chosen (§5.6).
- [ ] genesis-anchor folds clean (`accepted=1, rejected=[], forks=[]`); `resolveIdentity` → esperie owner.
- [ ] roster landed on rs `main` via codify-branch PR + admin-merge.
- [ ] onboarding suite present in rs (via loom pipeline OR direct PRs), each redteam-converged.
- [ ] update kailash-py `.session-notes` / mops-onboarding ledger: F-MOPS CLOSED.

## 8. References

- This workspace: `workspaces/mops-onboarding/00-PROGRAM.md` (full program), `journal/0001` (Phase-1 codify
  receipt — what the suite IS), `journal/0002` (the loom cross-repo authorization receipt).
- The runbook: kailash-py `.claude/skills/45-genesis-bootstrap/SKILL.md` (the same skill being rolled out).
- rs location: `esperie-enterprise/kailash-rs` (PRIVATE; a DIFFERENT org than terrene-foundation).

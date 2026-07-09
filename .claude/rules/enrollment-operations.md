---
priority: 10
scope: path-scoped
paths:
  - ".claude/operators.roster.json"
  - ".claude/commands/enroll.md"
  - ".claude/commands/whoami.md"
  - ".claude/commands/ecosystem-init.md"
  - ".claude/commands/onboard.md"
---

# Enrollment Operations — Genesis Bootstrap Discipline

Standing up the multi-operator trust root and enrolling operators run through a chain of
fail-CLOSED boundary guards. A first run that ignores the order below hits a guard mid-ceremony,
leaves a half-written roster or an un-folded anchor, and the operator concludes "the substrate is
broken" — it is not; the guards are working. This rule is the MUST-clause discipline; the
step-by-step runbook + guard-behavior depth live in `skills/45-genesis-bootstrap/SKILL.md`.

## MUST Rules

### 1. Configure The Signing Key BEFORE Any Roster Or Coordination Write

The commit-signing key MUST be configured before the first tracked-file mutation of a ceremony.
When coordination is ON, `signing-mutation-guard.js` enforces **degraded read-only** — a
working-tree-mutation predicate (a `git status --porcelain` before/after delta on tracked paths),
NOT a tool-name allowlist, so every tracked-file write is blocked and writing the roster first is
BLOCKED. **Coordination-opt-in caveat (W1, 2026-06-25, journal/0330):** on a genuinely fresh
bootstrap repo (no roster + no genesis anchor) coordination resolves OFF via the implicit fallback,
so `signing-mutation-guard.js` and `integrity-guard.js` **passthrough** (they early-return when
`!isCoordinationEnabled`) — the degraded-read-only trap does NOT fire during the first bootstrap
run. `genesis-anchor-guard.js` ALSO advisory-passes-through on the genuinely-fresh state (F72
fresh-substrate-adopter / scaffold-roster branches, so the ceremony can land its first commits);
its fail-closed BLOCK engages only AFTER a real (non-scaffold) roster exists without a folded
anchor. The coordination-independent teeth that enforce signing-key-first during bootstrap are
(a) the **unconditional** `validate-bash-command.js` `STATE_PATH_RX` block on Bash state-file
mutation, and (b) fold-clean verification (MUST-4 / fold rule 9a) — an **unsigned** genesis-anchor
never folds into a trust root, so enrollment cannot COMPLETE without the key.
`signing-mutation-guard.js`'s degraded-read-only begins enforcing MUST-1/2 once the owner enrolls
and coordination turns ON.

```bash
# DO — signing key first, then any tracked write
git config --local gpg.format ssh
git config --local user.signingkey "$HOME/.ssh/id_ed25519.pub"
git config --local commit.gpgsign true

# DO NOT — write the roster first (STATE_PATH_RX refuses a Bash state-path mutation unconditionally,
# even on a fresh coordination-OFF repo; the Edit/Write-tool path is additionally codify-branch-gated
# by integrity-guard when coordination is ON — the roster is NOT in settings.json permissions.deny)
node -e 'require("fs").writeFileSync(".claude/operators.roster.json","{}")'  # blocked: STATE_PATH_RX before signing-key config
```

**BLOCKED rationalizations:** "I'll configure signing after the roster is drafted" / "the guard
is over-eager, I'll force degraded off" / "read-only mode is a bug, not a gate" / "I only need
the key at commit time."

**Why:** The guard exists so an unsigned operator cannot mutate the working tree the trust
substrate rests on; configuring signing last makes the entire ceremony fight a guard one
`git config` line silences. Order is the cheapest fix.

### 2. Roster, Coordination, And Journal Writes Land On A Codify Branch — Never Direct To Main

Every write to a watched path (roster, `operators.roster.schema.json`, `coordination-log.jsonl`,
`posture.json`, `violations.jsonl`, `observations.jsonl`, `team-memory/**`, `journal/**`) MUST
occur on a branch matching `^codify/<display_id>-YYYY-MM-DD$` (the date-terminal predicate in
`integrity-guard.js`; suffixed names are rejected) AND under a covering codify lease
(`codify-lease.js::acquireCodifyLease`). The branch is cut from `main`; branch protection rejects
a direct roster push to `main`. A write off the codify branch is BLOCKED.

```bash
# DO — date-terminal codify branch off main, then acquire the lease
git checkout -b "codify/<display_id>-$(date -u +%Y-%m-%d)" origin/main
# acquireCodifyLease({displayId, repoDir, scopeFiles}) bound to this branch

# DO NOT — roster edit on main, or a suffixed branch the guard won't honor
git checkout main && node -e 'require("fs").writeFileSync(".claude/operators.roster.json","{}")'  # blocked: STATE_PATH_RX refuses the roster mutation on any branch; Edit/Write-tool writes are additionally codify-branch-gated by integrity-guard when coordination is ON
git checkout -b codify/<display_id>-2026-06-23-b                # rejected: not date-terminal
```

**BLOCKED rationalizations:** "it's a one-line roster fix, main is fine" / "the date suffix keeps
two same-day branches apart" / "the lease is overhead for a solo owner" / "I'll PR it later,
editing on main first is harmless."

**Why:** The codify branch + lease is the anchor `integrity-guard.js::findCoveringLease` matches
(branch + signer + scope); a write off it bypasses the concurrency + provenance substrate, and a
suffixed branch name silently disagrees with the guard about what a codify branch IS.

### 3. Ceremony State-Mutations Keep The Watched-State Path Off The Mutating Command Line

Any ceremony step that RAW-MUTATES a watched state file — an inline `node -e` / `python -c`
body, a redirect, or a file-utility (`cp`/`mv`/`tee`/`sed -i`) — MUST NOT put the
`STATE_PATH_RX` write on the bash command line. The satisfying pattern for an AUTHORED mutation
is script-by-path: a bare `node <file>` (a script authored to disk, then run by path) keeps the
watched path in the script body, off the scanned command line (mechanics in
`skills/45-genesis-bootstrap` § The script-by-path pattern).
`validate-bash-command.js`'s `detectStateFileMutationSegmentAware` guard (the segment-aware
wrapper from `violation-patterns.js`) fires on EXACTLY this — it blocks an interpreter
(`-c`/`-e`/`-m`), redirect, or file-utility body ONLY when a path matching `STATE_PATH_RX` (the
watched state files) appears as a literal on the command line (each layer requires a
`STATE_PATH_RX` match on the command line — or a redirect target — before it fires). A FOURTH
whole-command pass (`detectHeredocWriteRunBundle`) additionally fires when ONE command BOTH
authors a heredoc script whose body carries a `STATE_PATH_RX` literal AND then runs that same
script — so author the script in a SEPARATE command from its bare `node <file>` run. A raw
inline mutation that puts the watched-state path on the command line is BLOCKED — including a path
assembled by string concatenation to dodge the literal match (a raw inline write of a watched
state file is BLOCKED regardless of how its path is spelled; the guard's literal-match is
defense-in-depth, not the whole contract).

**SAFE — a signed-emit helper call is NOT a raw inline mutation, but only a specific shape
qualifies.** An inline `node -e` is PERMITTED only when BOTH hold: (a) no `STATE_PATH_RX` literal
appears in the call's command-line arguments, AND (b) the write is DELEGATED to a signed-emit
helper that routes its watched-path write through `coc-emit.js::emitSignedRecord`, enforcing the
stamp / chain / sign contract (`multi-operator-coordination.md` MUST-1). Two of the ceremony's
signed-emit helpers satisfy both (condition (b) is the governing test, not this list):
`reserveJournalSlotSigned` (builds the coordination-log path INTERNALLY, routes through
`emitSignedRecord`) and `emitSignedRecord` itself (opts-only; the path is derived from
`opts.repoDir`) — this is how `/certify` Step 2 reserves its journal slot inline
(`reserveJournalSlotSigned(process.cwd(), {...})`). "Owns the write internally" is NECESSARY BUT
NOT SUFFICIENT: a function hiding a raw `fs.writeFileSync` of a watched path is NOT a signed-emit
helper (it does not enforce MUST-1) and is BLOCKED exactly like the concat-evasion above; and a
helper whose SIGNATURE takes the watched path as an ARGUMENT — e.g.
`appendStamped(repoDir, filePath, …)` (`coc-append.js`, the observations/violations stamped-append
helper) — puts the literal on the command line, DOES trip the guard, and MUST be script-by-path
(`skills/42-certify/SKILL.md` Step 4). The MUST targets a RAW inline write OR an arg-supplied
watched path; it does NOT license every helper call — while a categorical "no inline interpreter
body" would over-block the safe `reserveJournalSlotSigned` case.

```bash
# DO — author the script, run it bare; the watched path is in the file body
node /tmp/scratch/ceremony-step.js

# DO — inline SIGNED-EMIT helper; the watched path is INTERNAL to the helper (guard passes)
node -e 'require("./.claude/hooks/lib/journal-reserve.js").reserveJournalSlotSigned(process.cwd(), {dir, identity, type, topic})'

# DO NOT — raw inline body writing a watched-state-path LITERAL on the command line
node -e 'require("fs").writeFileSync(".claude/operators.roster.json", x)'    # severity: block
python3 -c 'open(".claude/learning/coordination-log.jsonl","a").write(rec)'  # severity: block

# DO NOT — helper whose signature carries the watched path as an ARGUMENT (literal reaches the line)
node -e 'require("./.claude/hooks/lib/coc-append.js").appendStamped(cwd, ".claude/learning/violations.jsonl", rec, {})'  # severity: block → use script-by-path

# DO NOT — author-and-run a heredoc bundle in ONE command (the whole-command bundle pass fires)
cat > /tmp/s.cjs <<'EOF' … coordination-log.jsonl … EOF && node /tmp/s.cjs  # severity: block → author + run as TWO separate commands
```

**BLOCKED rationalizations:** "one-liner is faster" / "my read of the log is fine inline" (WRONG —
the guard is read/write-AGNOSTIC: it fires on ANY interpreter `-c`/`-e`/`-m` body that names a
watched-state-path LITERAL on the command line, read OR write; run even READS script-by-path, as
MUST-4 does) / "I'll disable the bash
guard for the ceremony" / "bundling node with the gh call in one command is tidier" (re-introduces
a scanned token) / "I'll build the watched path by string concat so the literal never matches" (a
raw inline write of a watched state file is BLOCKED regardless — use script-by-path or a
signed-emit helper) / "it's a helper call, so it's blessed" (only a signed-emit helper that keeps
the watched path off the command line qualifies — a helper taking the path as an argument, or one
hiding a raw `fs` write, does not).

**Why:** The guard closes the bypass where `permissions.deny` on Edit/Write does not cover
bash-mediated mutations; the guard-enforced invariant is "no watched-state-path LITERAL in an
interpreter / redirect / file-utility body on the command line (interpreter bodies fire on a read
too)." Script-by-path (authored mutation, or even a read of the log) and a
signed-emit helper that keeps the path internal (delegated mutation) both satisfy it; a categorical
"no inline interpreter body" over-claims and
falsely flags `/certify`'s safe `reserveJournalSlotSigned` call, while an unqualified "any helper
is fine" under-claims and licenses an arg-supplied `appendStamped` the guard blocks.

### 4. Verify The Genesis Folds Clean Before Declaring "Enrolled"

A signed-and-appended `genesis-anchor` is NOT a trust root until it FOLDS clean. Before declaring
the repo enrolled, confirm (a) `coordination-log.js::foldLog(records, roster, opts)` returns the
anchor in `accepted` with `rejected: []` AND `forks: []`, AND (b)
`operator-id.js::resolveIdentity(repoDir)` returns `role: "owner"` with a non-null `person_id`.
Declaring enrolled on an appended-but-unverified anchor is BLOCKED.

```text
# DO — verify fold + identity (script-by-path; both read the gitignored log)
foldLog(...) → { accepted: [genesis-anchor, …], rejected: [], forks: [] }
resolveIdentity(repo) → { role: "owner", person_id: "pid-<display_id>-<short-fp>", … }   → say "enrolled"

# DO NOT — "the record appended, so we're enrolled"
appendFileSync(coordination-log, anchor)  # appended ≠ folded-clean ≠ trust root
```

**BLOCKED rationalizations:** "the append succeeded, that's enough" / "fold is an internal detail"
/ "I'll verify if something breaks later" / "the ceremony returned ok, I don't need to fold."

**Why:** A non-empty `rejected`/`forks` fold means the anchor never became the trust root (bad
signature, wrong owner-bind, or a competing anchor); shipping "enrolled" on an un-folded anchor
leaves the next session to discover the substrate has no trust root — a
`verify-resource-existence.md`-class declaration of state that was never verified.

### 5. Teammates Self-Enroll From Their OWN Machines

Each additional operator MUST run `/enroll` (→ `/whoami --register`) from THEIR OWN machine with
THEIR OWN signing key. The genesis owner MUST NOT generate a key for a teammate, register a
teammate's `person_id` on their behalf, or share a key across humans. Bootstrapping an identity
for another human is BLOCKED.

```text
# DO — each human enrolls themselves
teammate@their-laptop: /enroll  → /whoami --register (their key, their PR)

# DO NOT — owner registers a teammate or shares a key
owner: register pid-<teammate> with a key the owner generated   # BLOCKED
```

**BLOCKED rationalizations:** "it's faster if I set them all up" / "they can rotate the key later"
/ "one shared team key is simpler" / "they're not technical, I'll do it for them."

**Why:** `verified_id` authenticates a RECORD to a key; a key one human generated for another
collapses the identity triple — the substrate can no longer attribute a signed record to the
human who acted, defeating the `multi-operator-coordination.md` authority model.

### 6. The Org-Admin Relaxation Applies ONLY To Org-Owned Repos

The issue-#358 relaxation — substituting a verified active org-admin attestation
(`gh api orgs/{org}/memberships/{login}` → `role: "admin"` + `state: "active"`) for an unverified
root commit — MUST be used ONLY when `roster.genesis.repo_owner_kind == "org"` AND the signer is a
verified active admin. For a user-owned repo the SIGNED ROOT COMMIT (`commits/{root_commit}` →
`verification.verified == true`, author == declared owner) is the only anchor. Applying the
org-admin path to a user-owned repo is BLOCKED.

```text
# DO — anchor by owner kind
repo_owner_kind: "org"  → verified active org-admin attestation (the #358 relaxation)
repo_owner_kind: "user" → signed root commit (verification.verified == true)

# DO NOT — substitute admin attestation on a user-owned repo
repo_owner_kind: "user" → "I'm an admin somewhere, use that"   # BLOCKED — wrong anchor
```

**BLOCKED rationalizations:** "admin is admin, the anchor is equivalent" / "the root commit isn't
signed, use the relaxation anyway" / "user-vs-org is a formality."

**Why:** The org-admin attestation is the structurally-equivalent anchor to a signed root commit
ONLY because a gh-api-bound active admin is an external, unforgeable-offline fact for an ORG; a
user-owned repo's trust root IS its signed root commit, and substituting an unrelated admin claim
anchors it to the wrong fact.

## MUST NOT

- Declare a repo "enrolled" before the genesis anchor folds clean (`rejected: []`, `forks: []`)

**Why:** An appended-but-unfolded anchor is not a trust root; the claim is unverified state.

- Force `signing-mutation-guard` degraded mode off, or disable any boundary guard, to push a
  ceremony step through

**Why:** The guards fail-CLOSED by design; disabling one converts a loud, fixable refusal into a
silent substrate corruption.

## Trust Posture Wiring

- **Severity:** `advisory` at the hook layer — structural enforcement already lives in the
  fail-closed boundary guards (`signing-mutation-guard.js`, `integrity-guard.js`,
  `validate-bash-command.js`'s `detectStateFileMutationSegmentAware`, `journal-write-guard.js`,
  `genesis-anchor-guard.js`), which carry their own `block` teeth; this rule's non-hook clauses
  (fold-clean verify, self-enroll, org-admin scope) surface `halt-and-report` at gate-review per
  `hook-output-discipline.md` MUST-2.
- **Grace period:** 7 days from rule landing.
- **Cumulative posture impact:** same-class violations (ceremony out-of-order, write off the
  codify branch, inline state-mutation, declare-before-fold, cross-machine enroll, org-admin
  misapplication) contribute to `trust-posture.md` MUST-4 cumulative math (3× same-rule / 5× total
  in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within 7 days of landing fires the generic
  `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture);
  no new trigger key is introduced.
- **Receipt requirement:** SessionStart `[ack: enrollment-operations]` in the agent's first
  response IFF `posture.json::pending_verification` includes this rule_id. Soft-gate.
- **Detection mechanism:** Phase 1 — the fail-closed boundary guards ARE the runtime detector for
  MUST 1/2/3 (existing fixtures `.claude/audit-fixtures/{integrity-guard,genesis-anchor-guard}/`);
  cc-architect / reviewer gate-review at `/codify` confirms MUST 4/5/6 (fold-clean receipt per
  `verify-resource-existence.md` MUST-4; self-enroll + org-admin scope read from the signed
  `genesis-anchor` content). No new sweep tool ships, so no new fixtures (`cc-artifacts.md` Rule 9
  fires only on new tools). Phase 2 (deferred): a Stop-event detector is unnecessary — the guards
  already block at the tool boundary. **No-check disposition:** this rule ships NO new detector and
  NO new `validate-emit.mjs` structural check — MUST-3 is enforced UNCONDITIONALLY by the
  `validate-bash-command.js` `detectStateFileMutationSegmentAware` `STATE_PATH_RX` block. MUST-1/2's
  `signing-mutation-guard.js` / `integrity-guard.js` degraded-read-only + codify-branch/lease fences
  are **coordination-ON-gated** (opt-in per W1 2026-06-25 — they passthrough on a fresh coordination-OFF
  bootstrap repo, per MUST-1's caveat); `genesis-anchor-guard.js` LIKEWISE advisory-passes-through on
  the genuinely-fresh state (F72), blocking only AFTER a real non-scaffold roster exists without a
  folded anchor — NOT on the first fresh commit. So during bootstrap MUST-1/2 rest on the unconditional
  STATE_PATH_RX block + fold-clean verification (an unsigned genesis-anchor never folds into a trust
  root → enrollment cannot COMPLETE without the key); the signing/integrity guards enforce MUST-1/2
  once coordination turns ON. `journal-write-guard.js` backs the journal-slot discipline. MUST 4/5/6 are
  gate-review clauses read by cc-architect. Per the sync-from-build.md new-rule discipline the loom
  placement records this no-check disposition rather than adding a structural check with no detector
  to key on.
- **Violation scope:** MUST 1/2/3 are guard-enforced structural clauses; MUST 4/5/6 are gate-review
  clauses. Every `violations.jsonl` row records which MUST fired.
- **Origin:** See § Origin.

## Origin

2026-06-23 — the kailash-py multi-operator enrollment session: the substrate was
installed-but-unenrolled, and standing up the genesis owner surfaced five fail-closed guard traps
in sequence (degraded read-only until signing configured; `validate-bash` state-file-mutation
block on an inline `node -e` roster write; the codify-branch + lease gate; the genesis-anchor
fold-clean requirement; per-machine self-enroll). The authoritative runbook
(`guides/co-setup/11-genesis-ceremony.md`) is loom-authored and `use_excluded` — NOT distributed to
USE-template / downstream consumer repos (`sync-manifest.yaml::use_excluded`), so the
hard-won procedure was reconstructed in-repo as `skills/45-genesis-bootstrap/SKILL.md` + the agent
`agents/onboarding/coc-onboarding-specialist.md`, with this rule as the MUST-clause backing.
Verified against `validate-bash-command.js`, `integrity-guard.js`, `signing-mutation-guard.js`,
`genesis-ceremony.js`, `coordination-log.js`, and `operator-id.js`. Distributes to BUILD + USE
repos via `/codify` → loom Gate-1 → `/sync`.

## Distributable-Repo Caveat — Public / Fork-Template Repos Ship Un-Enrolled

A repo that is publicly downloadable or forked as a template (this repo IS one) MUST ship
**un-enrolled**: the committed `operators.roster.json` MUST carry a `PLACEHOLDER-` genesis
(`repo_owner: "PLACEHOLDER-owner"`, `root_commit: "0000000"`), NOT a live `genesis.root_commit`.
`coordination-mode.js::isCoordinationEnabled` resolves Tier-4 implicit-ON from the **committed**
roster's anchored genesis, and `.claude/learning/` (the local genesis-anchor + `.initialized`) is
gitignored — so a committed LIVE genesis makes every clone resolve coordination **ON** by
inheritance, while a `PLACEHOLDER-` genesis (`_isGenesisAnchored` → false) keeps clones **OFF**. A
forker enrolls their OWN clone via `/ecosystem-init` / `/whoami --register`. Committing a live
genesis to a distributable repo is BLOCKED.

The coordination-ENFORCEMENT PreToolUse hooks (`integrity-guard.js`, `signing-mutation-guard.js`,
`journal-write-guard.js`, `genesis-anchor-guard.js`, `adjacency-leasecheck.js`, `operator-gate.js`)
MUST NOT be registered in the **committed** `.claude/settings.json` of a distributable repo: paired
with a live committed genesis they would fire in every clone, and `signing-mutation-guard.js` would
drop a fresh forker (no signing key) into degraded read-only — bricking their fork. Operator-local
enforcement belongs in the gitignored `.claude/settings.local.json` (per-operator, never inherited
by a clone). A lockfile-gated hook like `probe-phase-guard.js` (fires only during an active
`/certify` gate) IS clone-safe in the committed `settings.json` and SHOULD ship there so every
consumer's `/certify` no-assist gate has structural teeth.

**Length rationale (per `rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** File is
~335 lines (per `wc -l`), over the 200 guidance. Named rationale: **guard-trap scope** — the rule
codifies SIX MUST clauses — three fail-closed boundary guards (MUST 1/2/3) + three gate-review
clauses (MUST 4/5/6), consistent with § "Violation scope" above — each requiring the
DO / DO NOT + BLOCKED-corpus + `**Why:**` structure `rule-authoring.md` Rules 2/3/4 mandate, plus
the canonical 8-field Trust Posture Wiring (`trust-posture.md` MUST-8). The API-depth and
step-by-step procedure are already extracted to `skills/45-genesis-bootstrap/SKILL.md` (the
depth-home), so the residual is the irreducible six-clause + 8-field structure; collapsing any
guard's example/Why/BLOCKED would weaken the structural defense. This rule is `priority: 10` +
`scope: path-scoped`, so it pays NO baseline-emission cost (loaded only in sessions matching its
`paths:` globs) and Rule 10's proximity-band gate does NOT fire. Sibling precedent:
`user-flow-validation.md` + `multi-operator-coordination.md` Origins.

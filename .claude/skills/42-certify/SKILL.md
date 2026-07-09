---
name: certify
description: "/certify procedure: brief → probe → gate at 100%; loops failed questions until pass. NO Claude-assistance during gate phase. Curated bank, not LLM-generated."
---

# /certify — knowledge gate for new devs/consultants

This skill is the procedural detail for the `/certify` command (`.claude/commands/certify.md`). The command is the entry point; this skill is the runbook the orchestrator follows. Three phases — **Brief → Probe → Gate**, gated at 100%.

## When to use

- A new dev or consultant joins the repo and is about to claim their first piece of non-trivial work.
- An existing operator returns after a long absence (>30 days) and the question bank or critical-rule corpus has materially changed since their last certification.
- A repo owner wants to re-certify the whole team after a major architectural shift recorded in `specs/`.

`/certify` does NOT replace `/onboard` — `/onboard` answers "what's the current team state" (read-only, ~5 min). `/certify` answers "does this person KNOW the critical surface well enough to claim work" (write-receipts + journal pass, ~30–60 min). Run `/onboard` first; then `/certify`.

## Read-only vs state-write contract

`/certify` writes state, but a narrow set:

| Surface                                                 | Phase                        | Write?                                                                                                                                                                            |
| ------------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `workspaces/_certify/.pending/*`                        | Brief                        | Yes — ephemeral read receipts, OUTSIDE any `journal/` subtree (dodges integrity-guard's `workspaces/<name>/journal/` watch); scrubbed per `user-flow-validation.md` MUST-6        |
| In-session probe state                                  | Probe                        | No persisted file; tally lives in orchestrator context                                                                                                                            |
| `journal/NNNN-<display_id>-DECISION-certify-pass-*.md`  | Pass (gate met)              | Yes — committed pass receipt (name from `reserveJournalSlotSigned`)                                                                                                               |
| `journal/NNNN-<display_id>-DECISION-certify-defer-*.md` | Abandon mid-gate             | Yes — deferral receipt (`type: "DECISION"`, `topic: "certify-defer-<display_id>"` — `DEFER` is NOT a canonical journal type per `rules/journal.md`); operator stays L2_SUPERVISED |
| `posture.json`                                          | (n/a — no posture write)     | No — trust-posture machinery already enforces L2 for unrostered operators                                                                                                         |
| `operators.roster.json`                                 | (n/a — no roster write)      | No — certify never writes the roster; registration is a PREREQUISITE authored before the entry gate                                                                               |
| `.claude/learning/codify-lease.json` (on-disk mutex)    | Pass + Abandon (Steps 1.5/5) | Yes — a covering codify-lease acquired around the pass OR DEFER write, released at Step 5                                                                                         |
| `.claude/learning/coordination-log.jsonl`               | Pass + Abandon (Steps 1.5–5) | Yes (coordination-ON) — signed `codify-lease` / `journal-slot-reservation` / `journal-body-anchor` / `codify-lease-release` records via canonical emit helpers                    |

Pass is captured in the journal entry, NOT in a roster row. The roster row is authored by the separate registration step (a PREREQUISITE the entry gate requires present); certification is recorded in `journal/` and gates the operator's first `/claim`.

## Section-by-section runbook

### Phase 0 — Prerequisites (identity + bank validation + consent)

Runs BEFORE Phase A. Three structural STOP gates — mirror of `commands/certify.md` Step 1; all three are structural (exit code + file existence + explicit user input), not LLM-judgment, so a session that skims this prose still fails on the wire.

**Step 0.a — Resolve identity structurally** (NOT by prose-claim):

```bash
node -e 'const r = require("./.claude/hooks/lib/operator-id.js").resolveIdentity(process.cwd()); process.stdout.write(JSON.stringify(r));'
```

STOP (do NOT fall through to Phase A) when the parsed JSON has ANY of: `verified_id == null`, `person_id == null`, `posture == "L2_SUPERVISED"` AND no roster row, OR a non-zero exit code. On STOP surface — **branched on the just-enrolled case**: if the operator just ran `/enroll` or `/whoami --register`, their roster row is on their `codify/<display_id>-<date>` branch but not yet merged to `main` → "Run `/certify` FROM your `codify/<display_id>-<date>` branch — `resolveIdentity` reads the WORKING-TREE roster (`operator-id.js` `_readJsonSafe(rosterPath)`), so your row is visible there and the pass entry lands on the same branch (riding your enrollment PR); OR await the PR merge and run it on `main`. On `main` before the merge you resolve as not-yet-rostered."; otherwise → "Identity check failed: you are not rostered (`/whoami --register` first) — `/certify` needs a roster row to record the pass against."

**Step 0.b — Validate the bank file structurally** (the security scan — NOT the schema-shape-only check):

```bash
node .claude/bin/validate-cert-bank.mjs specs/_certification.yaml
```

STOP on non-zero exit (any CRIT/HIGH finding). The validator covers: bank existence + YAML validity, schema shape (version, sections, per-question id/kind/expected), **citation-path allowlist (`{specs,rules,.claude}/**` only — no `..` traversal, no absolute paths), length caps (advisory/MED — flagged, non-blocking) on prompt/options/rubric/expected, prompt-injection signal scan, and secret-shaped-token rejection.** A bank that fails any CRIT/HIGH check (citation/injection/secret) is institutionally untrusted; do NOT proceed to brief. This binary validator IS the authoritative bank-trust gate — the § Question bank schema check at probe start is a re-confirmation of shape, NOT a substitute for this security scan.

**Step 0.c — Consent gate** (the bank's `bank_version` + record-of-pass-tied-to-`verified_id` implications):

```
Surface to operator:
  "/certify will record a per-question pass/fail tally tied to your
   verified_id in a committed journal entry. The bank version is
   <bank_version>. Proceed? (y/N)"
```

STOP unless the operator answers `y` — explicit per-operator consent is required before institutional knowledge about the operator's competency lands in the audit trail.

### Phase A — Brief

Walk these surfaces in fixed order; for each, summarize in plain language (per `rules/communication.md`), then write a read receipt to `workspaces/_certify/.pending/certify-brief-<display_id>-<YYYY-MM-DD>.md` (ephemeral scratch, deliberately OUTSIDE any `journal/` subtree — `integrity-guard` watches `workspaces/<name>/journal/`, so a Phase-A receipt under `journal/` would halt un-leased under coordination-ON; these receipts are NOT codify-class journal entries):

1. `specs/_index.md` if present (domain truth surface). If absent, surface "this repo has no specs index; brief covers rules + journal only."
2. Repo `CLAUDE.md` — the always-loaded directives and navigation.
3. CO-category rules in this fixed order: `rules/autonomous-execution.md`, `rules/agent-reasoning.md`, `rules/artifact-flow.md`. These are the load-bearing CO rules; if the consumer repo lacks one, note it explicitly in the receipt.
4. `/posture show` output — current trust posture, repo floor, pending verifications.
5. `.claude/team-memory/` — list each `<slug>.md` with its signed/promoted_by metadata (skip `README.md`).
6. Last 5 `journal/DECISION-*.md` entries — read filename + first H2.

The receipt format per section: `## <section name>` heading + a 3–5 sentence plain-language summary + `Cite: <path>` line. Receipts are SCRUBBED before write per `rules/user-flow-validation.md` MUST-6 — no secrets, no downstream-client tokens, no PII.

### Phase B — Probe

Load `specs/_certification.yaml`. Validate the schema (see § Question bank schema). Present questions in YAML order — the bank's author ordered them easy → hard; the orchestrator MUST NOT re-order.

**Step 0 (probe entry): create the lockfile that activates `probe-phase-guard.js`:**

```bash
touch ".claude/.certify-in-probe-${VERIFIED_ID}.lock"
```

While this lockfile exists, the `.claude/hooks/probe-phase-guard.js` PreToolUse hook (registered in `.claude/settings.json` for matcher `Read|Grep|Glob|WebFetch`) emits `severity: block` on every orchestrator retrieval call. This is the structural defense backing the no-assist discipline below — the hook fires whether the orchestrator's prose-compliance is intact or not.

For each question:

1. Print the question id + prompt + `Cites: <spec-section>` so the operator knows which section they're being tested on.
2. For `multiple_choice`: print options A–N; wait for the operator's letter.
3. For `short_answer`: wait for the operator's prose answer.
4. Judge:
   - `multiple_choice`: exact match against `expected:`.
   - `short_answer`: orchestrator LLM judges the answer against `expected:` (canonical answer) + the `grading_rubric:` bullets (acceptance criteria). Return `{verdict: pass|fail, rationale: <one sentence>}`.
5. Record the per-question result in orchestrator context: `{id, verdict, attempts: 1}`.

**The lockfile PERSISTS through Phase C — do NOT remove it at the Phase B→C transition.** Phase C's gate retry loop RE-RUNS the probe on the failed questions (§ Phase C below, `re-run probe on q`), and those retries MUST stay no-assist exactly as the initial probe does. The structural `probe-phase-guard.js` guard therefore MUST remain active until the gate is fully resolved — removing the lockfile before Phase C would open an un-guarded retrieval window during the exact retry loop the gate exists to protect (an operator asking "what's the answer?" during a retry could then be assisted via an orchestrator Read/Grep). The lockfile is removed at Phase C exit ONLY — see Phase C § Step N. This matches `commands/certify.md` § "Phase B — Probe": `rm` fires at "Probe exit (Phase C complete OR abandoned mid-gate)", never before.

**NO Claude-assistance during the probe.** If the operator asks "can you explain that section again?" or "what's the answer?", the orchestrator MUST refuse with one sentence: "I cannot assist during the gate phase; re-read the cited section and answer when ready." This refusal is now belt-and-suspenders — the structural hook is the primary defense; the prose refusal handles edge cases (operator pasting in a Read tool call directly via the orchestrator's tool surface would be blocked by the hook; operator asking for prose rephrasing is blocked by this refusal). Both layers fire together per `probe-driven-verification.md` MUST-4 (structural hook + prose-discipline gate-review counterpart).

### Phase C — Gate

After the full pass:

```
if all(q.verdict == "pass" for q in questions):
  → pass path (§ pass receipt below)
else:
  failed = [q for q in questions if q.verdict == "fail"]
  for q in failed:
    print(f"Re-read {q.cites_spec_section}. Then we'll retry question {q.id}.")
  wait for operator to indicate ready
  for q in failed:
    re-run probe on q  # increment q.attempts
  → loop until all pass
```

The gate is 100% strict. There is no partial credit, no "close enough", no "the operator clearly understands the concept but worded it differently." If the answer fails the rubric, it fails the gate. The operator re-reads the cited section and retries.

**Step N (gate exit): remove the lockfile — the SINGLE removal site, on BOTH the pass path AND the abandon path:**

```bash
rm -f ".claude/.certify-in-probe-${VERIFIED_ID}.lock"
```

The `probe-phase-guard.js` guard spanned Phase B AND the Phase C retry loop; this is the one place it is torn down — once the gate is fully resolved (100% pass recorded) OR the operator abandons mid-gate (§ Failure modes: the same `rm` runs so the lockfile is never left stale). If the orchestrator crashes mid-gate, the operator removes the stale lockfile manually (`rm .claude/.certify-in-probe-*.lock`) before re-running `/certify`.

### Pass receipt

Pass-receipts MUST route through the canonical journal-slot reservation + signed body-anchor helpers per `rules/knowledge-convergence.md` MUST-2. Hand-writing the file directly is BLOCKED — a hand-written receipt is forgeable, breaks the per-emitter chain, and bypasses the body-anchor cryptographic gate that distinguishes a real pass from a fabricated one.

**Step 1 — Resolve identity for the receipt:**

```bash
node -e 'const r = require("./.claude/hooks/lib/operator-id.js").resolveIdentity(process.cwd()); process.stdout.write(JSON.stringify(r));'
```

Parse and bind `verified_id`, `person_id`, `display_id` from the JSON result. STOP if any are null.

**Step 1.5 — Get on a codify branch + acquire a covering codify-lease (the pass entry is a codify-class `journal/` write).** Under coordination-ON, `integrity-guard.js` requires a `journal/` Write to be BOTH on a `codify/<display_id>-<date>` branch (`isCodifyBranch` — a write on `main` is `severity: block` BEFORE the lease is even consulted) AND under a covering `codify-lease` record (`findCoveringLease` → `halt-and-report` otherwise). So, before the Step-3 Write:

- **(a) Ensure HEAD is your `codify/<display_id>-<date>` branch** — the enrollment branch if certifying same-day pre-merge, ELSE cut one: `git checkout -b "codify/<display_id>-$(date -u +%Y-%m-%d)" origin/main`. `acquireCodifyLease` only COMPUTES the branch NAME (it does NOT `git switch`), so YOU must be on the branch first.
- **(b) Acquire the lease** via a script-by-path `node <file>` (state-mutating ceremony step per `enrollment-operations.md` MUST-3 — author the script with the same `cat > "${TMPDIR:-/tmp}/…cjs" <<'CEREMONY'` … `CEREMONY` write-then-run wrapper Step 4 uses) calling:

```js
acquireCodifyLease({
  displayId,
  scopeFiles: ["journal/"],
  repoDir: process.cwd(),
});
```

`scopeFiles: ["journal/"]` (trailing-slash DIRECTORY scope) is load-bearing: `findCoveringLease` matches a scope entry against the `journal/`-prefixed rel-path only by exact-equality, trailing-slash-dir-prefix, or bare-dir-prefix — a bare filename (`NNNN-…md`) would NOT match, and `MANDATORY_SCOPE` (`learning-codified.json` + `latest.yaml`) does not cover `journal/`. `acquireCodifyLease` (`.claude/hooks/lib/codify-lease.js`) returns `{ ok, lease, branch, record_emit }`. On `{ ok: true }` proceed to Step 2; if `record_emit.ok` is false surface its `reason` (a lease invisible to siblings per `knowledge-convergence.md` MUST-3 — the lease still holds). On `{ ok: false }` STOP and surface the conflicting holder + `reason`. **Note:** `acquireCodifyLease` also fail-closes on a dirty SCOPE working tree (the lease scope is `MANDATORY_SCOPE ∪ ["journal/"]`, so an unrelated uncommitted `journal/` entry ALSO triggers the `scope-dirty` STOP) or a git error EVEN under coordination-OFF (only the record-emit + integrity-guard enforcement are OFF no-ops) — surface and resolve rather than assume a no-op.

**Step 2 — Reserve the slot via the fold-anchored helper.** Supply the Step-1 JSON
as `IDENTITY_JSON` ON the invocation (the helper reads it from `process.env`; without
the prefix `identity` is `undefined` and the reserve fails closed):

```bash
IDENTITY_JSON="$identity_json" node -e '
const { reserveJournalSlotSigned } = require("./.claude/hooks/lib/journal-reserve.js");
const identity = JSON.parse(process.env.IDENTITY_JSON);
const r = reserveJournalSlotSigned(process.cwd(), {
  dir: "journal",
  identity,
  type: "DECISION",
  topic: "certify-pass-" + identity.display_id
});
process.stdout.write(JSON.stringify(r));
' < /dev/null
```

(`$identity_json` is the raw JSON captured from Step 1's stdout.)

Inline `node -e` is safe HERE (unlike Step 4's `appendStamped`, which MUST be script-by-path per `enrollment-operations.md` MUST-3): `validate-bash-command.js`'s `detectStateFileMutationSegmentAware` scans the COMMAND LINE for a `STATE_PATH_RX` literal, and this invocation passes only `process.cwd()` — the `coordination-log.jsonl` path the helper emits to is internal to `journal-reserve.js`, never on the command line. Step 4's `appendStamped(cwd, COORD_LOG, …)` puts the state path in an argument, so it MUST be hidden in a `node <file>` script.

The **fold-anchored** helper is `reserveJournalSlotSigned` — NOT the pure `reserveJournalSlot`, which computes off the filesystem only and emits nothing, so the Step-3 Write would halt "slot unreserved" at `journal-write-guard.js`. It returns `{ ok: true, reservation: { slot: "NNNN", filename: "NNNN-<display_id>-DECISION-certify-pass-<display_id>.md", ... }, record }` on success, or `{ ok: false, error, reason, step }` on failure — STOP and surface `reason` when `ok` is false. The slot is `max(disk high-water, fold-accepted reservation high-water)` AND the helper emits the signed `journal-slot-reservation` coordination-log record `journal-write-guard.js` folds — so the Step-3 Write is permitted and two concurrent `/certify` sessions remain distinguishable on disk.

**Step 3 — Write the journal file at the returned `r.reservation.filename`:**

```yaml
---
type: DECISION
date: <YYYY-MM-DD>
author: co-authored
project: <repo-name>
topic: "certify-pass: <display_id>"
phase: codify
tags: [certify, onboarding, roster-prerequisite]
verified_id: <from-Step-1>
person_id: <from-Step-1>
display_id: <from-Step-1>
bank_version: <specs/_certification.yaml::bank_version>
---
```

Body sections (REQUIRED): per-question tally (id, verdict-on-final-attempt, attempts), total wall-clock, scrubbed brief-receipt index, next-step instruction. Also REQUIRED: the `## For Discussion` section per `rules/journal.md` Requirements (3 probing questions about what was learned and what gaps remain — at least one counterfactual, at least one referencing specific tally data).

**Step 4 — Emit the signed `journal-body-anchor` coordination-log record.** `coordination-log.jsonl` is a
protected state-file owned by the `validate-bash-command.js` state-file-write guard (`detectStateFileMutation`,
Layer 3): only the canonical emit path may write the log. The anchor ceremony IS that sanctioned canonical
writer — it keeps the protected path inside the script body (off the run command line) and writes-then-runs
as two separate Bash commands. This two-step canonical-writer shape is the form the guard sanctions; a single
bundled write+run command is not. First create the script:

```bash
cat > "${TMPDIR:-/tmp}/coc-certify-anchor.cjs" <<'CEREMONY'
const path = require("path");
// require() resolves relative to the SCRIPT's own dir (/tmp), not the operator's cwd —
// so path.resolve() rebinds each lib to the repo root the ceremony runs FROM.
const { buildAnchorRecord } = require(path.resolve(".claude/hooks/lib/journal-body-anchor.js"));
const { appendStamped } = require(path.resolve(".claude/hooks/lib/coc-append.js"));
const COORD_LOG = ".claude/learning/coordination-log.jsonl";   // path in the body, not the command line
const identity = JSON.parse(process.env.IDENTITY_JSON);
const journalPath = process.env.JOURNAL_PATH;          // absolute path from Step 3
const relPath = path.relative(process.cwd(), journalPath);
const slotRecordRef = process.env.SLOT_RECORD_REF;     // from Step 2 helper return
const partial = buildAnchorRecord({ journalPath, relPath, slotRecordRef, identity });
const r = appendStamped(process.cwd(), COORD_LOG, partial, { identity });
process.stdout.write(JSON.stringify(r));
CEREMONY
```

Then run it by its own path (a separate command) **from the repo root** (the cwd both the
coordination-log write and the `path.resolve(...)` lib lookups resolve against), supplying the
script's inputs ON the invocation — the script reads each from `process.env`, so without the env
prefix it writes `undefined` and the append fails closed: `IDENTITY_JSON` (Step 1 JSON),
`JOURNAL_PATH` (the absolute path written in Step 3), `SLOT_RECORD_REF` (the Step-2 helper return):

```bash
IDENTITY_JSON="$identity_json" JOURNAL_PATH="$journal_path" SLOT_RECORD_REF="$slot_record_ref" \
  node "${TMPDIR:-/tmp}/coc-certify-anchor.cjs" < /dev/null   # canonical writer, run by its own path
```

The `appendStamped()` helper stamps `verified_id`+`person_id`+`seq`+`prev_hash`+`ts`+`sig` and refuses to write rather than truncate per `knowledge-convergence.md` MUST-6. A `{ ok: false }` result MUST be surfaced + STOP — do NOT retry by hand-writing.

**Why this matters:** at fold time, `foldAnchorPredicate` re-hashes the journal body and compares against `sha256_of_content_bytes` in the signed anchor. Tamper post-write fails verification AND names the anchor's SIGNER per `knowledge-convergence.md` MUST NOT clause "Treat a body-anchor finding as accusing the journal's frontmatter author when the anchor predicate names a DIFFERENT signer." The pass receipt's cryptographic integrity is what distinguishes /certify from theater.

**Step 5 — Release the covering codify-lease** (paired with Step 1.5). After the pass entry + body-anchor land, release via a script-by-path `node <file>` (same `cat > …cjs <<'CEREMONY'` write-then-run wrapper as Step 4) calling `releaseCodifyLease({ repoDir: process.cwd(), displayId })` (`.claude/hooks/lib/codify-lease.js` — the helper derives the `leasePath` from `repoDir` internally per Sec-MED-3; callers MUST NOT supply `leasePath`). This emits the paired `codify-lease-release` coordination-log record under coordination-ON. In a coordination-OFF repo it releases the on-disk mutex with no record.

## Question bank schema

`specs/_certification.yaml` (consumer repo's curated bank). The authoritative bank-trust gate is the Phase-0 `validate-cert-bank.mjs` binary (schema shape + citation-path allowlist + injection scan + secret-token rejection); the probe-start re-confirmation of this schema shape is a defence-in-depth re-check, NOT a substitute — missing required fields → STOP with the offending question id.

```yaml
version: 1 # schema version (currently 1)
bank_version: "<repo>-2026-05-25" # operator-visible bank version (free text)
sections:
  - id: <slug> # e.g. "co-foundations", "trust-posture", "framework-first"
    title: <human-readable name>
    cites_spec: <path:line-range> # e.g. "rules/artifact-flow.md:1-40"
    questions:
      - id: <slug>-q1 # unique across the whole bank
        prompt: <one or two sentences>
        kind: multiple_choice | short_answer
        cites_spec_section: <path:line-range>
        options: # multiple_choice only
          - A: <option text>
          - B: <option text>
          - C: <option text>
        expected: A # multiple_choice: the correct letter; short_answer: canonical answer prose
        grading_rubric: # short_answer ONLY — 3–5 acceptance criteria
          - <must mention X>
          - <must distinguish Y from Z>
          - <must NOT claim W>
```

Ordering convention: easy questions first, hard last. The bank's curator owns ordering; the orchestrator does NOT re-sort.

## Failure modes

- **Empty bank** (`questions: []` after expansion): STOP, surface "bank is empty — seed it from `.claude/templates/specs/_certification.yaml` before running /certify."
- **Schema invalid** (missing `expected:`, missing `grading_rubric:` on a `short_answer`, unknown `kind:`): STOP, name the offending question id.
- **Operator abandons mid-gate**: write a deferral entry via the same `reserveJournalSlotSigned` helper with `type: "DECISION"`, `topic: "certify-defer-<display_id>"` (→ `NNNN-<display_id>-DECISION-certify-defer-<display_id>.md` at its returned `r.reservation.filename`). The entry carries the SAME frontmatter shape as the pass receipt (Step 3) — `type: DECISION`, `author: co-authored`, `verified_id`/`person_id`/`display_id` from Step 1, `bank_version` — with `topic: "certify-defer: <display_id>"` and the attempts-so-far tally in the body; the same Step-4 body-anchor applies. **`DEFER` is NOT a canonical journal `type`** (`journal-reserve.js::VALID_TYPES` = DECISION/DISCOVERY/TRADE-OFF/RISK/CONNECTION/GAP/AMENDMENT per `rules/journal.md`); passing `type: "DEFER"` fails the reservation closed. Operator stays `L2_SUPERVISED`. Re-running `/certify` restarts from question 1 — the gate is full-bank; partial-bank carry-forward is intentionally NOT supported (the bank is the unit of certification, not individual questions). **The deferral write is a codify-class `journal/` write too** — under coordination-ON it MUST follow the SAME ceremony as the pass receipt (Step 1.5: ensure the `codify/<display_id>-<date>` branch + `acquireCodifyLease({ scopeFiles: ["journal/"], displayId, repoDir })`; Step 5: `releaseCodifyLease`). Without it, `integrity-guard` hard-blocks the deferral write on `main` (off-codify-branch) or halts it un-leased on a codify branch — the same gate the pass path clears. Under coordination-OFF `integrity-guard` passes through and the ceremony is a no-op.
- **Bank's cited spec section missing on disk**: warn in the brief receipt; the question is still asked (the operator is being tested on the rule's content as the bank's curator captured it; the missing spec is a separate fix-the-bank task).

## Next steps after certify

Pass → `/onboard` (re-read team state with verified identity) → `/claim <path>` (start work). No registration nudge — the entry gate already required the roster row present, so the operator is rostered by construction.

Until pass, the operator stays `L2_SUPERVISED` via `posture.json` (no certify-side write needed — `multi-operator-coordination.md` §1 already enforces L2 default for unrostered operators).

## Composition with other commands

- **`/onboard`** answers "who am I + what's the team state" (read-only). `/certify` adds the knowledge-gate. Run `/onboard` first.
- **`/whoami --register`** is the roster-write and a PREREQUISITE — the entry gate requires the roster row present (`resolveIdentity` reads the working-tree roster, so it is visible on the enrollment `codify/<display_id>-<date>` branch or on `main` after merge). `/certify` does NOT register. Run on the enrollment branch (the pass entry rides the roster PR) or after merge; the pass gates the operator's first `/claim`.
- **`/codify`** authors rules; `/certify` tests knowledge of rules. When a `/codify` lands a load-bearing rule, the consumer repo's bank curator should add a question covering it; without that, the bank goes stale relative to the live rule corpus.

## Origin

2026-05-25 co-owner-directed COC tooling. Receipt: `journal/0158-DECISION-certify-onboarding-mechanism-2026-05-25.md`. Skill body follows `rules/cc-artifacts.md` Rule 2 (progressive disclosure — SKILL.md answers 80% of routine questions without sub-file reads).

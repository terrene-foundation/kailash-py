---
priority: 10
scope: path-scoped
cli_delivery: skill-channel
paths:
  - "**/workspaces/**"
  - "**/.session-notes*"
  - "journal/**"
---

# Orchestration Launch-Ledger — Track Spawned Agents In A Durable Artifact That Survives Context Boundaries

An orchestrator that spawns background / parallel agents holds the map of what it launched — track → agent → branch → status — in WORKING MEMORY. A context boundary (compaction, `/clear`, resume, sub-agent handoff) ERASES that memory while the agents keep running. On the far side the orchestrator (a) spawns a DUPLICATE of a track already in-flight, and (b) mis-attributes its OWN already-pushed branches to a "parallel session" it did not launch. The fix is a DURABLE artifact: an on-disk launch-ledger the compaction cannot erase, consulted BEFORE every spawn and matched AGAINST every completion notification.

This rule owns the DURABLE-LEDGER + DEDUP-BEFORE-SPAWN + MATCH-COMPLETION-BEFORE-REACTING discipline. It composes with the orchestration rules that govern WHEN to parallelize and WHETHER work is real — it does not restate them (§ Distinct From).

## MUST Rules

### 1. The Ledger Is LANE-KEYED, And Every Lane Row Carries A TASK SET And An AGENT ROSTER

Any orchestrator that spawns ≥1 background / parallel / worktree-isolated agent MUST record the work in a DURABLE on-disk ledger — a table in the active workspace, `.session-notes`, or a workspace ledger file — that SURVIVES compaction. In-memory-only tracking is BLOCKED; the transcript is exactly what the context boundary erases.

**The unit of a row is the LANE — the ceiling-bound resource (worktree + branch) — NOT the agent and NOT the task.** Each lane row carries: lane → branch → **task set** (every issue/task that lane is covering) → **agent roster** (each sub-agent with its own status) → lane status. A one-task-one-agent-one-branch row is the under-packed shape MUST-6 forbids; a ledger whose rows cannot express N tasks and M agents inside ONE lane structurally prevents the packing that rule mandates.

```markdown
# DO — LANE-keyed row: one ceiling-bound lane, many tasks, many agents

| lane   | branch       | tasks (issues)      | agents (status)                                  | lane status |
| ------ | ------------ | ------------------- | ------------------------------------------------ | ----------- |
| L1-api | fix/api-wave | #2230, #2231, #1971 | a1 rest-shape ✅ · a2 auth-plumb ⏳ · a3 warn ⏳ | in-flight   |
| L2-db  | fix/db-wave  | #2112, #2075        | b1 pool ✅ · b2 reaper ✅                        | landed      |

# DO NOT — one track, one agent, one branch (the serial-worker shape)

| track | agent | branch | status |
| engine-feature | W2-engine | feat/engine-x | in-flight |
```

The roster is not bookkeeping: it is what MUST-2's pre-spawn dedup, MUST-3's notification matching, and MUST-4's resume-by-name all key on once a lane holds more than one agent. Record the resume transition (`in-flight → fragment → resumed → landed`) on the AGENT cell, not the lane cell — a lane is not stalled because one of its agents is.

**Why:** The launch map in working memory is destroyed by the exact event (compaction / `/clear` / resume) the orchestrator cannot predict. Keying rows by lane rather than by track is what makes the durable artifact able to express depth at all — a track-keyed ledger silently caps the fleet at one agent per ceiling-bound unit, which is the throughput loss MUST-6 exists to prevent.

### 2. Check The Ledger BEFORE Spawning — Never Spawn A Track Already Present

Before spawning any agent, the orchestrator MUST consult the launch-ledger and confirm the track is NOT already present as `in-flight` (or `landed`). Spawning a track that the ledger shows already running is BLOCKED — that is the duplicate-agent failure mode directly. If the ledger is absent or stale, RECONCILE it (re-read the workspace / `git branch` / the task registry) BEFORE spawning, not after the collision surfaces.

```markdown
# DO — consult the ledger, find store-adapter already in-flight, do NOT re-spawn

Ledger shows `store-adapter → W2-store → in-flight` → skip; monitor the existing agent.

# DO NOT — spawn without checking → duplicate of an already-running track

Spawn a second store-adapter agent (the first fell out of context after a compaction)
```

**Why:** The duplicate spawn wastes the run, races the original for the same branch/scope, and is invisible until the collision surfaces at merge; a 2-second ledger read before every spawn converts a silent duplicate into a no-op skip.

### 3. Match Every Completion Notification Against The Ledger BEFORE Reacting

When an agent-completion notification arrives, the orchestrator MUST match its agent id/name against the launch-ledger BEFORE reacting to the landed work. A branch/PR the ledger attributes to a SELF-LAUNCHED agent MUST NOT be reasoned about as another session's output. Reacting to a completion (merging, re-launching, re-attributing) WITHOUT the ledger match is BLOCKED.

```markdown
# DO — notification for W2-store → match ledger row → it is MY launch, treat as such

Completion: agent W2-store, branch feat/store-y → ledger row confirms self-launched → merge as planned

# DO NOT — react to a self-launched landed branch as a "parallel session's" work

"feat/store-y appeared — another session must have produced it" (the ledger shows YOU launched it)
```

**Why:** A self-launched branch mis-read as external work leads the orchestrator to either re-do it, abandon it, or reason about phantom concurrent sessions — the mis-attribution half of the amnesia failure; the ledger match is the one check that tells own-work from other-work after the boundary.

### 4. A Quota / Rate-Limit Failure Is A PAUSE, Not A Death — Resume By Name, Or Stand Down And CONFIRM, Before Launching Any Replacement

An agent stopped by a quota, rate-limit, or session-limit failure has NOT terminated: it retains its transcript and RESUMES when addressed by name. Treating that state as death and launching a replacement into the SAME worktree puts two live agents on one directory under ONE git identity, where `--author` cannot separate them. The orchestrator MUST either (a) resume the original by name, or (b) stand it down explicitly AND confirm the stand-down, BEFORE any replacement is launched.

**Liveness is established by a PROCESS check, never by a timestamp or a clean tree** — an old last-commit and an empty `git status` are equally consistent with "gone" and "40 minutes into a test run that has written nothing yet". The check MUST fail CLOSED, and "failed" is defined PER TOOL: `ps` returns non-zero only on genuine failure, but **`lsof` returns 1 when it finds NOTHING**, so a blanket "non-zero means OCCUPIED" doctrine reads `lsof`'s all-clear as occupied and produces a gate that can never return free. An unproven empty is ZERO EVIDENCE (`evidence-first-claims.md` MUST-3), never an all-clear. If a concurrent writer IS found, STOP and report — `kill` is a HUMAN gate, never self-authorized. A ledger row moves to `stopped` ONLY on a confirmed stand-down or a process check demonstrated capable of the opposite verdict, NEVER on a quota error. **Runnable check (topology guard, per-tool exit conventions, bounded positive control), full BLOCKED corpus, measured evidence: `skills/30-claude-code-patterns/quota-pause-and-rescue-hygiene.md` § MUST-4.**

```text
# DO — cwd-based process check from OUTSIDE the worktree, positive control first, then relaunch
# DO NOT — infer death from the worktree's own state (old last commit; clean `git status`)
```

**Why:** The two observables an orchestrator naturally reaches for — commit recency and tree cleanliness — are precisely the two a long-running agent also produces, so the inference is unfalsifiable at the moment it is made; only the process check separates the cases.

### 5. A Rescue Checkpoint Is Inspected, Secret-Scanned, And Blob-Scanned BEFORE It Is Pushed

Preserving an interrupted agent's uncommitted work is CORRECT — losing it is worse than any cleanup. But a blanket `git add -A` rescue is indiscriminate: it stages build outputs, scratch harnesses, measurement binaries, probe files, **and anything holding a credential**. Prefer EXPLICIT-PATH staging (`coc-sync-landing.md` MUST-2 already BLOCKS `git add -u`/`-A`/`.`); use `-A` only when the interrupted set is genuinely unknown, and then inspect it. Between staging and `git push` the orchestrator MUST (a) INSPECT the staged set rather than committing blind, (b) scan for **secrets/credentials** over a range PROVEN non-empty, and (c) scan for oversized blobs and artefact-shaped paths.

**The secret scan is the non-negotiable one** — an oversized blob costs a history rewrite, but a pushed credential is unrecoverable and costs ROTATION. The checkpoint MUST land on `recovery/<name>` (`worktree-isolation.md` Rule 8, which owns WHEN a rescue is mandatory and requires `git ls-remote` as the proof it landed) and MUST declare itself with the literal subject prefix **`checkpoint(UNREVIEWED):`**, so a merge gate can mechanically detect one reaching a PR — a negative-control pass that was interrupted mid-mutation leaves a deliberately-broken mechanism that reads as a normal edit. Pushing a per-operator scratch tree to a shared branch is a sensitivity escalation carrying `recommendation-quality.md` MUST-8's confirm-before-persist gate. **Scan commands, the empty-range trap, full BLOCKED corpus: `skills/30-claude-code-patterns/quota-pause-and-rescue-hygiene.md` § MUST-5.**

```text
# DO — inspect → secret-scan (non-empty range proven) → blob-scan → recovery/<name> + checkpoint(UNREVIEWED):
# DO NOT — git add -A && commit && push, then discover the 16.6MB binary and the mid-edit code in review
```

**Why:** The rescue is a correct reflex applied under time pressure, which is exactly when the scan is skipped; both failure modes it prevents are silent — an oversized blob is permanent in history, and an un-flagged live mutation is indistinguishable from work.

### 6. WIP Ceilings Bind LANES, Never AGENTS — Every Lane Is A Mini-Orchestrator, Packed To Depth

A WIP / concurrency / fleet ceiling constrains the **ceiling-bound resources**: worktrees, branches, open PRs. It does **NOT** constrain how many agents work inside a lane, nor how many tasks a lane covers. Treating a lane as a single serial worker — one task, one agent, one branch — spends a scarce ceiling slot on the cheapest possible payload and is BLOCKED.

Every lane MUST therefore be dispatched as a **MINI-ORCHESTRATOR**: it receives a TASK SET, not a task, and fans out its own sub-agents against that set. Where ≥2 same-scope tasks are dispatchable, a lane carrying exactly ONE is under-packed; leaving a dispatchable same-scope task unassigned because "the lanes are taken" is the failure this rule names.

```markdown
# DO — 3 ceiling slots carrying 9 tasks; each lane fans out internally

L1-api (fix/api-wave) ← #2230 #2231 #1971 → lane dispatches a1/a2/a3, reviews, lands ONE branch

# DO NOT — 3 ceiling slots carrying 3 tasks, one serial worker each

L1 ← #2230 only · L2 ← #2231 only · L3 ← #1971 only (6 dispatchable tasks left unstarted)
```

**Three bounds, none of which this clause lifts.** (a) **Per-agent attention** — each sub-agent still gets its OWN shard budget (`autonomous-execution.md` § Per-Session Capacity Budget Rule 1), which binds one implementation pass, not one worktree; packing a lane NEVER licenses one oversized pass. (b) **Simultaneous concurrency** — `worktree-isolation.md` Rule 10's adaptive back-off still governs how many Opus-tier agents run AT ONCE; depth is packed over the lane's LIFE, in adaptive waves, not by firing the whole roster simultaneously. (c) **Task independence** — tasks packed into one lane MUST be co-landable on that lane's single branch; work that is not jointly revert-safe splits by `ci-cost-discipline.md` MUST-2 regardless of ceiling pressure.

**BLOCKED rationalizations:** "the WIP ceiling is 3, so we can only work 3 issues" / "one agent per worktree is the isolation contract" (isolation is per-TREE, and sub-agents of one lane share it by design) / "packing risks merge conflicts" (co-landability is bound (c), not a reason to under-pack) / "the lane agent should just do them in sequence" (that is the serial worker this rule forbids) / "more agents per lane will hit the rate limit" (that is bound (b), an adaptive back-off, not a WIP ceiling) / "we'll start the next task when a lane frees up" / "the ledger only has one agent column".

**Why:** The ceiling exists to bound the number of unlanded, un-reapable work products — branches and worktrees — because those are what cost reconciliation at merge. Agents cost neither. Sizing a wave by agent count therefore throttles throughput against a constraint that does not exist, and the loss compounds: every ceiling slot spent on a single task is the same reconciliation cost carrying a fraction of the payload it could have carried.

## MUST NOT

- Size a wave, or defer a dispatchable same-scope task, by AGENT count rather than by the worktree / branch / open-PR ceiling

**Why:** The ceiling bounds unlanded work products, which is what costs reconciliation; agents are not a ceiling-bound resource, so counting them throttles throughput against a constraint that does not exist.

- Dispatch a lane brief that assigns exactly ONE task when ≥2 same-scope tasks are dispatchable, or that does not instruct the lane to fan out its own sub-agents

**Why:** The brief is where packing is decided; a single-task brief spends a scarce ceiling slot on the cheapest possible payload, and no later step recovers it.

- Spawn a background / parallel agent whose track the launch-ledger already shows `in-flight` or `landed`

**Why:** The originating duplicate-agent failure mode — spawning a track already running wastes the run and races the original.

- React to an agent-completion notification (merge / re-launch / re-attribute) without first matching its agent id against the ledger

**Why:** Without the match, a self-launched landed branch is mis-attributed to a "parallel session," and the orchestrator reasons about work it actually produced as if it were external.

- Rely on the session transcript / working memory as the launch record instead of a durable on-disk ledger

**Why:** The transcript is precisely what compaction / `/clear` / resume erases; a launch record that lives only there is gone at the boundary where dedup and attribution are needed.

- Conclude an agent is dead from a quota / rate-limit signal, a stale last-commit, or a clean tree, and launch a replacement into its worktree

**Why:** A quota-paused agent resumes when addressed by name; two live agents on one worktree under one git identity is the collision `--author` cannot untangle, and it silently sweeps a sibling's mid-edit work into someone else's commit.

- Push a rescue checkpoint without inspecting the staged set, without a secret scan over a proven non-empty range, on a branch outside `recovery/<name>`, or without the `checkpoint(UNREVIEWED):` subject prefix

**Why:** The push is the sink — an oversized blob is permanent in history and a pushed credential costs rotation; the prefix is the only greppable signal that an unreviewed checkpoint (possibly carrying a live negative-control mutation) reached a PR.

## Trust Posture Wiring — MUST-4 / MUST-5 (clause-scoped)

Applies to **MUST-4** (quota-pause is not death) and **MUST-5** (rescue-checkpoint hygiene) ONLY, both added 2026-08-10; ships canonical-8-field-compliant per `trust-posture.md` MUST-8. The rule-wide block below governs MUST-1/2/3 and is unchanged — a separate block is required here because that block's grace window closed 2026-07-26, so it can supply no `regression_within_grace` teeth to clauses landing today. Same clause-scoped shape as `worktree-isolation.md` Rules 7 / 8 and `security.md` § Enforcement-Surface Parity.

- **Severity:** `halt-and-report` at gate-review (reviewer at `/redteam` + cc-architect at `/codify` confirm that any relaunch into an occupied-or-unknown worktree was preceded by a process check demonstrated capable of the opposite verdict, and that any rescue checkpoint was inspected + secret-scanned + `checkpoint(UNREVIEWED):`-prefixed before push); `advisory` at the hook layer per `hook-output-discipline.md` MUST-2 — whether a liveness inference was sound is judgment over the session's command history, not a tool-call-time structural signal.
- **Grace period:** 7 days from clause landing at loom (2026-08-10 → 2026-08-17).
- **Cumulative posture impact:** same-class violations (an agent treated as dead on a quota/rate-limit signal without a process check; a ledger row moved to `stopped` on that basis; a rescue checkpoint pushed without the secret scan, without the non-empty-range proof, or without the `checkpoint(UNREVIEWED):` prefix) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause key. A liveness-inference property is review-layer judgment over command history, and minting a key would drag `trust-posture.md`, a `self-referential-codify.md` allowlist file, into a self-referential edit. Named deviation from the key-per-clause shape, recorded here per `trust-posture.md` Rule 8 — the same disposition `security.md` § Enforcement-Surface Parity and `git.md` § CI-check/merge took. A pushed CREDENTIAL additionally routes to the pre-existing `critical` (secret leak → L1) trigger, unchanged; this clause mints no second key for it.
- **Receipt requirement:** SessionStart soft-gate `[ack: orchestration-launch-ledger]` IFF `posture.json::pending_verification` includes this rule_id (shared rule_id; one ack covers MUST-1..5).
- **Detection mechanism:** Phase 1 (manual, gate-review) — reviewer at `/redteam` + cc-architect at `/codify` inspect any session that relaunched, stood down, or marked a track `stopped` and confirm (d) a cwd-based process check ran with its positive control and its per-tool exit convention honored, and any session that pushed a rescue branch and confirm (e) the staged set was inspected, the secret scan ran over a NON-EMPTY revision range, the branch is `recovery/<name>`, and the subject carries the literal `checkpoint(UNREVIEWED):` prefix. **Semantic tier: NO probe suite ships at loom for these two clauses OR for the paired skill — recorded, not implied.** The scope of the omission is exactly three prose artifacts: MUST-4, MUST-5, and `skills/30-claude-code-patterns/quota-pause-and-rescue-hygiene.md`. The originating repo registers one; loom's `.claude/test-harness/**` is never-synced, so that suite did not arrive with the clauses, and authoring a DISCRIMINATING one is real work this placement did not carry — the comparable in-corpus suite registered for `instrument-discipline.md` is 12 bipolar rows over a candidate-fixture corpus, and a suite authored below that bar would be a non-discriminating instrument banked as coverage, which `instrument-discipline.md` MUST-3 blocks outright. Per `coc-artifact-eval-coverage.md` MUST-1 this is an eval-coverage omission on new load-bearing clauses, recorded here rather than left to be inferred from the absent file. **Graduation:** remove this sentence in the same change that registers, in the eval manifest, a bipolar probe suite covering MUST-4/5 (efficacy + no-false-positive + meta-compliance) and the paired skill (guidance-compliance + outcome-fidelity). MUST-4 of that same rule also asks this block to NAME the probe file. That path is deliberately left unnamed until the suite exists, and the reason is measured, not assumed: `detection-binding-check.mjs` treats a probes path in a Detection block as a LIVE binding and reds its CRITICAL `dangling-probes-binding` on one that does not resolve (observed against an otherwise `VALID (score 100)` baseline), whereas an absent DEFERRED fixtures path is sanctioned as reported-not-fatal. The deferred sanction has a fixtures arm and no probes arm, so MUST-4's probe clause and its own does-not-resolve clause cannot both be satisfied before the suite lands; naming it is the strictly worse half of that trade. Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout) — a merge-gate grep for `checkpoint(UNREVIEWED):` in a PR's commit subjects is the one mechanically-detectable half; audit fixtures land with it at `.claude/audit-fixtures/orchestration-launch-ledger/rescue-checkpoint/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST-4 (death inferred from a quota signal, from a timestamp, or from a clean tree; a process check whose result is banked without its positive control; `kill` of a discovered writer without the human gate) + MUST-5 (rescue pushed without inspection / secret scan / non-empty-range proof / `recovery/<name>` branch / `checkpoint(UNREVIEWED):` prefix). MUST-1/2/3 keep their existing scope below.
- **Origin:** See § Origin — 2026-08-10, ingested from the BUILD stream.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (reviewer at `/redteam` + cc-architect at `/codify` confirm any session that spawned background agents maintained a durable launch-ledger, checked it before spawning, and matched completions against it); `advisory` at the hook layer (whether a spawn was ledger-checked and a completion was ledger-matched is a session-history judgment per `hook-output-discipline.md` MUST-2 — no structural tool-call-time signal, so no `block`).
- **Grace period:** 7 days from rule landing (2026-07-19 → 2026-07-26).
- **Cumulative posture impact:** same-class violations (a background-agent orchestration run with no durable ledger; a duplicate spawn of an in-flight track; a completion reacted to without a ledger match) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause trigger key (a launch-tracking property is a session-history judgment; the universal `regression_within_grace` trigger already covers it). Named deviation from the canonical key-per-clause shape, recorded here per `trust-posture.md` Rule 8 — the same no-dedicated-key disposition `wave-loop.md` MUST-6/7 + `agents.md` § Triad took.
- **Receipt requirement:** SessionStart soft-gate `[ack: orchestration-launch-ledger]` IFF `posture.json::pending_verification` includes this rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — reviewer at `/redteam` + cc-architect at `/codify` inspect any session that spawned background agents and confirm (a) a durable on-disk launch-ledger exists with a row per launched agent, (b) the transcript shows a ledger consult before each spawn, (c) each completion was matched against the ledger before the orchestrator reacted; probes `.claude/test-harness/probes/orchestration-launch-ledger.probes.json` — NOT YET AUTHORED, and declared with a graduation condition and a calendar expiry in `.claude/test-harness/phase2-deferrals.json::probe_authorship_deferrals` (an undeclared absence would red `detection-binding-check.mjs`). Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout) — an advisory `Stop`/`PostToolUse` detector flagging a background-agent spawn with no adjacent durable-ledger write, paired with the review layer per `probe-driven-verification.md` MUST-4; audit fixtures land with the Phase-2 detector at `.claude/audit-fixtures/orchestration-launch-ledger/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST-1 (no durable ledger) + MUST-2 (duplicate spawn of an in-flight track) + MUST-3 (completion reacted to without a ledger match).
- **Origin:** See § Origin.

## Trust Posture Wiring — MUST-1 (lane-keyed rows) / MUST-6 (ceilings bind lanes) (clause-scoped)

Applies to the **MUST-1 lane-keying rewrite and MUST-6** ONLY (both added 2026-09-12, co-owner-directed origination); ships canonical-8-field-compliant per `trust-posture.md` MUST-8. The pre-existing rule-wide block above governs MUST-2/3 and the MUST-4/5 block governs those, each unchanged until itself `/codify`-touched — the clause-scoped precedent `security.md` § Enforcement-Surface Parity and `git.md` § CI-check/merge set.

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` + cc-architect at `/codify` confirm the ledger is lane-keyed with a task set and an agent roster per row, and that no wave was sized by agent count while same-scope tasks stayed dispatchable); `advisory` at the hook layer per `hook-output-discipline.md` MUST-2 — whether a lane was under-packed is a judgment over the dispatchable task set, which has no structural tool-call-time signal.
- **Grace period:** 7 days from clause landing (2026-09-12 → 2026-09-19).
- **Cumulative posture impact:** same-class violations (a track-keyed ledger row that cannot express N tasks / M agents; a lane brief assigning one task while ≥2 same-scope tasks were dispatchable; a wave sized or deferred by agent count) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause key. Named deviation from the key-per-clause shape, recorded here per `trust-posture.md` Rule 8, with this clause's own reason rather than an inherited one: under-packing costs THROUGHPUT, never correctness — nothing is corrupted and no gate is bypassed — so it does not warrant an instant-drop key, and minting one would drag `trust-posture.md`, a `self-referential-codify.md` allowlist file, into a self-referential edit.
- **Receipt requirement:** SessionStart soft-gate `[ack: orchestration-launch-ledger]` IFF `posture.json::pending_verification` includes this rule_id (shared rule_id; one ack covers MUST-1..6).
- **Detection mechanism:** Phase 1 (manual, gate-review) — reviewer at `/implement` + cc-architect at `/codify` inspect any session that dispatched ≥1 lane and confirm (a) each ledger row is keyed by lane and carries BOTH a task set and a per-agent roster, (b) for every lane holding one task, the transcript shows no second same-scope dispatchable task was available at dispatch time, (c) each lane brief instructed internal fan-out rather than serial execution. **Structural detection is DECLINED, not deferred, and the reason is stated rather than booked:** under-packing is a property of the DISPATCHABLE SET — the tasks that existed and were co-landable at dispatch time — which is nowhere in the tool-call input, so any detector would have to infer the counterfactual and would be the non-discriminating instrument `instrument-discipline.md` MUST-1 blocks. No Phase-2 detector is booked and no audit-fixture directory is named here; fixtures land with detectors that own them. Probes: the rule's existing `probe_authorship_deferrals` row covers this file and is widened to these clauses rather than given a new key — `completion-criterion.md` MUST-6 forbids the agent proposing a residual from also accepting it, so folding keeps the gap DATED under an acceptance that already exists.
- **Violation scope:** the MUST-1 lane-keying rewrite + MUST-6 ONLY (clause-scoped). Every `violations.jsonl` row names the lane, its task count, its agent count, and the same-scope tasks left dispatchable.
- **Origin:** See § Origin — 2026-09-12 co-owner directive.

## Distinct From / Cross-References

- **Distinct from** `wave-loop.md` MUST-6 (never idle-wait while independent in-budget work is launchable) — that governs WHETHER to launch more; this governs TRACKING what was already launched. MUST-7 (reconcile a pre-existing backlog item against ground truth before implementing) is the backlog-item analogue; this rule is the same reconcile reflex applied to SPAWNED AGENTS across a context boundary.
- **Distinct from** `agents.md` § The Default Execution Mode Is The Triad + § Worktree Orchestration — those govern HOW to parallelize (decompose, isolate, verify deliverables); this governs the durable LEDGER that survives compaction so the parallel launches are not lost.
- **Composes with** `knowledge-convergence.md` MUST-1 (`.session-notes` single-writer) — the ledger commonly lives in the workspace/session-notes surface that rule governs; this rule adds the launch-tracking CONTENT, not a second writer.
- **Same epistemic family as** `zero-tolerance.md` Rule 1c / `verify-claims-before-write.md` MUST-2 — a launch map carried across a context boundary is structurally unfalsifiable until re-derived; the durable ledger is the re-derivation surface.

## Origin

**MUST-1 lane-keying + MUST-6 — 2026-09-12, co-owner-directed origination** (`artifact-flow.md` § Co-Owner-Directed Origination), verbatim: _"The ceilings explicitly bind worktrees and branches AND NOT AGENTS. Thus, all repos MUST structure their work ledger such that they can maximally pack depth (more agents covering more tasks/issues) into each lane. Each lane must be a mini-orchestrator rather than a single serial worker."_

The ledger's ROW SHAPE was the binding constraint, which is why MUST-1 changed with MUST-6 rather than after it. The prior shape — `track → agent → branch → status` — admitted exactly one agent and one task per ceiling-bound unit, so an orchestrator filling the ledger correctly was structurally prevented from packing depth: the artifact had nowhere to record a second agent or a second issue on the same lane. A mandate to pack, laid over a ledger that cannot express packing, would have been unenforceable and silently ignored. Measured in the originating session: three lanes were dispatched carrying three tasks total, one serial worker each, while the correctness and security reviews on that same wave produced nine further findings that were co-landable on those very branches and went unassigned.

The three named bounds exist because the directive is easy to over-read into two real hazards the corpus already governs — an oversized single implementation pass (`autonomous-execution.md` § Per-Session Capacity Budget Rule 1, which this change amends to bind the AGENT rather than the worktree) and a simultaneous-dispatch throttle (`worktree-isolation.md` Rule 10's adaptive back-off, which is a rate signal, not a WIP ceiling). Packing depth means many tasks per lane over the lane's life, dispatched in adaptive waves — not the whole roster fired at once.

**MUST-4 / MUST-5 — 2026-08-10, ingested from the BUILD stream.** A sixteen-track wave hit three account quota-limits in one session. Both clauses are orchestrator errors, both measured: ten tracks were relaunched into the SAME worktrees after the first limit, the originals resumed on the account swap, and one resulting commit swept in a sibling's in-flight edit while a negative control run minutes later went **vacuous** (a sibling's restore put back the very entry the control meant to remove — and a vacuous control reports SUCCESS). The same false premise then had an agent `kill` another's in-flight test run, truncating output at 120,867 bytes. Separately, a blanket `git add -A` rescue pushed two 16.6MB measurement binaries, a scratch probe, and unformatted mid-edit code that reddened a required format check. The checkpoint reflex itself was CORRECT — ~10,400 lines across twelve branches were preserved and nothing was lost; what the clauses add is the scan between staging and push, and the process check before relaunching.

Landed at loom via `/sync-from-build` Gate-1 classification of the `kailash-rs` proposal `ORCHESTRATION-QUOTA-PAUSE-AND-RESCUE-HYGIENE-2026-08-10`, classified **GLOBAL on both axes** — the quota-pause and rescue-scan contracts reference no language runtime and no CLI-native delegation primitive, so neither a language-axis nor a CLI-axis overlay is warranted. The originating repo's language-specific tooling names were genericized at placement per the sync-reviewer BUILD-internal-reference contract; the measured byte counts and the failure sequence carry verbatim because they are the evidence. Depth split to `skills/30-claude-code-patterns/quota-pause-and-rescue-hygiene.md` under `rule-authoring.md` Rule 10 path (a): the `workspace-note` path-scoped injection profile carried 9,013 B of headroom against ~20 KB of authored clause text, so the executable checks and BLOCKED corpora live in the skill and the rule body carries the thin contract.

2026-07-19 — GitHub issue #1232, filed from an orchestrator session in a downstream consumer repo where the failure and the fix were observed. Two background agents (an engine feature + a store-adapter) were launched, fell out of context after a compaction, and a DUPLICATE store-adapter agent was spawned before the collision surfaced; the self-launched, already-pushed branches were momentarily reasoned about as if another session had produced them. Landed at loom via `/sync-from-build` Gate-1 classification (Wave-1 of the sync-from-backlog follow-ups, journal/0552); the generic launch-tracking principle cascades, the downstream-consumer identifier stays in the local `/codify` receipt per `upstream-issue-hygiene.md` MUST-2. Authored `priority:10` + `scope:path-scoped` + `cli_delivery:skill-channel` under the measured saturated-baseline constraint (codex 10.13% / gemini 10.43% headroom, within the 15% proximity band) and scoped to the workspace / session-notes surfaces where the ledger lives — the same orchestration-surface path-scoping `wave-loop.md` uses; a genuinely-first spawn before any workspace file is touched is the one reachability edge (surfaced as a residual at land-time), bounded because a background-agent orchestrator is by construction doing plan-/workspace-anchored work that fires the glob early.

**Length rationale (per `rules/rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** Rule body is ~155 lines, UNDER the 200-line guidance — recorded because the originating BUILD-side rule carries its own overage rationale at ~320 lines and a reader comparing the two would otherwise infer content was lost. It was not de-scoped: the depth was EXTRACTED to `skills/30-claude-code-patterns/quota-pause-and-rescue-hygiene.md` under `rule-authoring.md` Rule 10 path (a), which is why loom's body is shorter while the contract is the same. This rule is `priority: 10` + `scope: path-scoped`, so it pays NO baseline-emission cost and Rule 10's proximity-band gate does NOT fire on it; the binding constraint here was the `workspace-note` path-scoped injection profile, measured at placement.

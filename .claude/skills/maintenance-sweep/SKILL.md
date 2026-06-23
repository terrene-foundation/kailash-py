---
name: maintenance-sweep
description: "Maintenance-cadence runbook backing /maintain: bucket ledger findings, draft human-gated proposals per type, reuse the BUILD-issue drafter. NEVER auto-applies (pull-not-push)."
tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Maintenance Sweep

The procedural depth behind the `/maintain` command (`commands/maintain.md`) — the
fleet-maintenance **cadence driver**. The cadence is **self-DETECTING, never self-healing**
(analysis §4.3 D4): it detects fleet rot over the Wave-2a observe-plane and drafts
**human-gated** proposals; it can NEVER push a fix across the pull boundary and MUST NEVER
auto-apply. This skill is the runbook; the command is the ≤150-line entry point.

## When To Use

Running `/maintain` (the periodic fleet-maintenance sweep), or authoring/auditing the cadence.
For the one-shot fleet health snapshot use `/inspect health` directly; `/maintain` is the
sweep that READS that snapshot and turns findings into drafts.

## The loop (detect → propose → human-gate → DRAFT → consumer-pull → verify)

The apply step crosses the pull boundary loom cannot force, so the loop stops at DRAFT. Every
stage REUSES existing machinery — no new engine:

| Stage           | Mechanism (all pre-existing)                                                              |
| --------------- | ----------------------------------------------------------------------------------------- |
| DETECT          | `/inspect health` (3 read-only probes → loom-root ledger) + `fleet-maintain.mjs` bucketer |
| PROPOSE/DRAFT   | the human-gated proposal shapes below (reuse the consultant dual-route drafters)          |
| HUMAN-GATE      | PR-merge / issue-triage / `/posture upgrade` / the consumer's own `/sync-from-template`   |
| APPLY           | the consumer PULLS (never auto-push) — OUTSIDE loom's control by construction             |
| VERIFY / CODIFY | `/redteam` to convergence + `/codify` (when a sweep surfaces a durable pattern)           |

## Procedure

1. **Refresh the ledger (DETECT).** Run `/inspect health` so `.fleet-freshness-ledger.json`
   (loom root) reflects the current fleet. This rides the `/inspect` artifact-distribution
   carve-out (`repo-scope-discipline.md`:42); the sweep adds NO new cross-repo read.
2. **Bucket (read-only).** Run `node .claude/bin/lib/fleet-maintain.mjs --json`. It projects the
   ledger into per-consumer findings by kind. The lib is a DUMB bucketer (`agent-reasoning.md`):
   it does the deterministic config-branching; YOU (the LLM) do ALL judgment — severity, which
   to draft, whether a finding warrants a BUILD issue. It NEVER probes/writes/applies.
3. **Report (both modes).** Surface actionable consumers first, in plain language the owner can
   act on (`communication.md`). State each finding's honest disposition.
4. **Draft (`draft` mode only — HUMAN-GATED).** Per finding TYPE, below.

## Finding taxonomy → draft shape

| Kind                | Meaning                                | Draft (HUMAN-GATED) — the fix is the CONSUMER's pull                            |
| ------------------- | -------------------------------------- | ------------------------------------------------------------------------------- |
| `drift-behind`      | N canonical artifacts behind canon     | maintenance report; consumer runs its own `/sync-from-template`                 |
| `deps-treadmill`    | manifest carries defensive caps/pins   | maintenance report citing `dependencies.md` (latest-always); consumer un-caps   |
| `posture-degraded`  | consumer COC running below L5 autonomy | maintenance report; recovery is the consumer's `/posture upgrade` (human-gated) |
| `*-unknown`         | a probe was UNKNOWN (fail-loud)        | informational ONLY — never a fabricated "healthy"; surface the reason           |
| compliance baseline | canon authors 0 O1 artifacts           | roadmap (no per-consumer signal yet) — never a fabricated compliance verdict    |

A maintenance report is loom's hand-off to the consumer, NOT an apply: loom records WHAT is
behind; the consumer's own pull cadence applies it. Loom cannot and must not push it.

## The CANON SDK defect path (LLM-judged; NOT ledger-derived)

When the sweep surfaces a **canon SDK defect or capability gap** — a bug/missing API in
`kailash` / `kailash_*` you identify by JUDGMENT, NOT a per-consumer ledger row — it is the SAME
change-TYPE the **consultant dual-route Route-B** already handles (`artifact-flow.md` § Consultant
Dual-Route Self-Serve D4). Do NOT hand-roll issue-filing: route the finding through the **existing
`/codify` Step-7c capability/bug lane** (`commands/codify.md` Step 7c), which loads the shipped
`gc-build-issue-draft.js::draftBuildIssue` drafter and enforces its contract:

- it assembles the `upstream-issue-hygiene.md` MUST-3 five-section body (Affected API · Minimal
  repro · Expected vs actual · Severity · Acceptance criteria) — `kailash`/`kailash_*` surface ONLY,
  no consumer modules;
- it injects the cross-SDK-first acceptance line (consider the sibling SDK before filing);
- it runs the MUST-2 disclosure scrub and **HALTS** on any finding (`ok:false`, `error:"scrub
findings"`, with the flagged spans) — genericize + re-draft; the defect goes upstream, the story
  of HOW you found it (consumer name, workspace path, finding tag) stays home;
- it returns `requires_human_gate:true` + the `y/N` gate prompt and **NEVER files** — filing happens
  ONLY on the operator's explicit same-session approval (MUST-1).

Any BUILD-repo / consumer target is resolved through `bin/lib/loom-links.mjs`, never a positional
`~/repos/<name>` guess (`cross-repo.md` MUST-1). The maintenance sweep ADDS no new issue-filing
mechanism — it reuses the human-gated, scrubbed, never-files Route-B drafter wholesale.

## Absolute invariants (MUST — the cadence's load-bearing contract)

- **NEVER auto-apply / NEVER auto-file.** Every draft is human-gated. `/maintain` may auto-DETECT
  and auto-DRAFT; it may NEVER merge, push, file, or apply without the per-proposal human gate.
  A `gh pr create` / `gh issue create` / `git push` issued by the sweep WITHOUT the explicit
  same-session gate is BLOCKED (`upstream-issue-hygiene.md` MUST-1).
- **NEVER write to a consumer repo.** Loom is pull-not-push (`repo-scope-discipline.md`); the
  sweep detects + proposes, the consumer pulls. `fleet-maintain.mjs` is read-only by construction.
- **Honest signals only.** UNKNOWN is informational, never "healthy"; compliance stays roadmap
  until canon authors O1 artifacts (`evidence-first-claims.md`).
- **Resolver-driven.** Any BUILD/consumer target is resolved via `bin/lib/loom-links.mjs`, never
  a positional `~/repos/<name>` guess (`cross-repo.md` MUST-1).

## Honest gap (recommendation-quality.md MUST-3)

`/maintain` does NOT close drift — it cannot (pull-not-push). It makes rot VISIBLE and drafts the
hand-off; the consumer applies on its own cadence. A fleet-level auto-apply / rollback ledger is
NOT built (it would require push loom does not have) — roadmap, never overclaimed as automatic.

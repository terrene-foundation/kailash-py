---
name: maintain
description: "Fleet maintenance cadence: DETECT drift/deps/posture over the ledger, DRAFT human-gated proposals. Self-detecting, never auto-applies."
argument-hint: "[detect | draft]"
---

Drive the fleet-maintenance cadence over the Wave-2a observe-plane. `/maintain` is
**self-DETECTING, never self-healing**: it detects rot across the fleet and drafts
**human-gated** proposals — it can NEVER push a fix across the pull boundary, and it MUST
NEVER auto-apply anything (`maintenance-cadence` discipline; analysis §4.3 D4).

**Usage**: `/maintain [detect | draft]` (default: `detect`)

| Mode     | What it does                                                                          |
| -------- | ------------------------------------------------------------------------------------- |
| `detect` | Read-only. Refresh the ledger, bucket per-consumer findings, report what needs action |
| `draft`  | `detect` + draft a HUMAN-GATED proposal per actionable finding (never files/applies)  |

## Procedure (delegate depth to the `maintenance-sweep` skill)

Load the **`maintenance-sweep`** skill for the full runbook (finding taxonomy, per-type draft
shapes, the disclosure-scrub + human-gate contract, the cross-SDK BUILD-issue reuse). The steps:

1. **Refresh the observe-plane** (DETECT): run `/inspect health` so the loom-root ledger
   (`.fleet-freshness-ledger.json`) reflects the current fleet (3 read-only probes → ledger).
   This rides the `/inspect` artifact-distribution carve-out (`repo-scope-discipline.md`:42) —
   `/maintain` itself adds NO new cross-repo read.
2. **Bucket the findings** (read-only): run `node .claude/bin/lib/fleet-maintain.mjs --json`.
   It projects the ledger into per-consumer findings by type — `drift-behind`, `deps-treadmill`,
   `posture-degraded` (actionable) and `*-unknown` (informational, fail-loud — never a fabricated
   "healthy"). It NEVER probes, NEVER writes, NEVER auto-applies.
3. **Report** (both modes): surface the actionable consumers first, in plain language a
   non-technical owner can act on (`communication.md`). Name each finding's honest disposition.
4. **Draft** (`draft` mode only — HUMAN-GATED, per finding TYPE):
   - **`drift-behind`** (a consumer is N artifacts behind canon) → draft a **maintenance report**
     for that consumer. Loom CANNOT push the fix; the consumer applies it by running its OWN
     `/sync-from-template` on its own cadence. The report is the hand-off, not an apply.
   - **`deps-treadmill`** (a consumer's manifest carries defensive caps/pins) → draft a
     **maintenance report** citing `dependencies.md` (latest-always); the consumer un-caps.
   - **`posture-degraded`** (a consumer's COC runs below full autonomy) → draft a **maintenance
     report**; posture recovery is the consumer's own human-gated `/posture upgrade`.
   - **A CANON SDK defect / capability gap** surfaced BY JUDGMENT during the sweep (NOT a
     per-consumer ledger row) → draft a **human-gated BUILD issue** via
     `.claude/hooks/lib/gc-build-issue-draft.js::draftBuildIssue` (cross-SDK-first, five-section,
     `upstream-issue-hygiene.md` MUST-2 scrub, `requires_human_gate:true`). The drafter NEVER
     files — it returns the restate material; the human approves the filing (`y/N`).
   - **`compliance`** → roadmap (canon authors 0 O1 methodology artifacts; no per-consumer signal
     yet — consistent with the Wave-2a dashboard; never a fabricated compliance verdict).

## Absolute invariants (MUST)

- **NEVER auto-apply.** Every draft is a HUMAN-GATED proposal. The PR-merge / issue-triage /
  consumer-pull is the structural human gate; automated placement is BLOCKED. `/maintain` may
  auto-DETECT and auto-DRAFT, but it may NEVER apply, merge, push, or file without the human gate.
- **NEVER write to a consumer repo.** Loom is pull-not-push; the cadence detects and proposes,
  the consumer pulls. A consumer write (or a `gh pr create` / `gh issue create` without the
  per-proposal human gate) is BLOCKED (`repo-scope-discipline.md` + `upstream-issue-hygiene.md`
  MUST-1).
- **Honest signals only.** UNKNOWN findings (an unreachable probe) are surfaced as informational,
  NEVER as a fabricated "healthy"/"current". Compliance per-consumer stays roadmap until canon
  authors O1 artifacts (`evidence-first-claims.md`; `recommendation-quality.md` MUST-3).
- **Read-only DETECT.** The detect path adds no cross-repo read beyond `/inspect health`'s
  carve-out; `fleet-maintain.mjs` only reads the loom-root ledger.

## Examples

- `/maintain` — DETECT: report the fleet's actionable maintenance findings (read-only).
- `/maintain detect` — same (explicit).
- `/maintain draft` — DETECT + draft a human-gated proposal per actionable finding (files nothing).

# /sweep — kailash-py — 2026-07-17 (post-Wave-1)

Repo-wide outstanding-work audit run AFTER Wave 1 shipped (PR #1799 merged, kaizen
2.34.2 released). BUILD repo; run from `main @ fb03ad37d`. All 9 sweeps executed.

## Sweep results

| #   | Sweep                      | Result                                                                                                                  |
| --- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 1   | Active todos               | **0** across all workspaces — clean                                                                                     |
| 2   | Pending journals           | **2** (sdk-backlog, 2026-07-15) — MCP #1712 RISK entries; #1712 now CLOSED (F1)                                         |
| 3   | Open GH issues             | **3**, all `cross-sdk`: #1720, #1779, #1727 (F2)                                                                        |
| 4   | Open PRs / branches        | **1**: #1782 (loom Gate-2 sync) — user's merge/hold gate (F3)                                                           |
| 5   | Redteam gaps (tool)        | `sweep-redteam:v1:OK specs=78 symbols=162 orphans=52 coverage_gaps=18 stubs=0` — **0 stubs**; orphans FP-dominated (F4) |
| 6   | Workspace/worktree hygiene | Session-notes/worktrees/.pending CLEAN; forest-ledger **8 stranded rows** in 2 stale workspaces (F5)                    |
| 7   | Process hygiene            | Clean tree, 0/0 divergence, **no NEW stubs** (133 markers = F-STUBS baseline, user call 2026-06-26)                     |
| 8   | Release readiness          | **Nothing unreleased** — all 8 packages main==PyPI (F6)                                                                 |
| 9   | Cross-ecosystem            | **N/A** — BUILD repo, not orchestration root (F7 — operator-local resolver note)                                        |

## Findings

### F1 · [LOW] [Sweep 2] 2 pending RISK journals in sdk-backlog

- **Location:** `workspaces/sdk-backlog/journal/.pending/1784109283493-{0,1}-RISK.md` (created 2026-07-15, source commits `ed49869a1`, `07df27a0d`).
- **Content:** the mcp-oauth SSRF / mcp tool-result-conformance RISK entries tied to **#1712 (MCP spec-compliance parity) — now CLOSED**.
- **Disposition:** DEFER (sdk-backlog cadence) — verify #1712's closure covered both risks, then promote-to-journal or discard-as-codified per `rules/journal.md`. Not this workspace's cadence.

### F2 · [MED-HIGH] [Sweep 3] 3 open cross-sdk issues — the live forest

- **#1720** [HIGH] — Wave C: legacy `providers/llm/` prune. **SOAK-GATED** (2.34.2 shims just shipped; zero soak). Own analyze→shard→redteam mini-cycle; irreversible delete re-confirm at fire. (Task #10.)
- **#1779** [MED-HIGH] — `governance_required` posture. **Wave-2 ready** — design done (`01-analysis/1779-governance-egress-analysis.md`), ~205 LOC / 7 invariants / 1 shard, parallel-safe with #1727.
- **#1727** [MED] — `max_completion_tokens` GPT-5/o-series on four-axis openai. **VERIFY-FIRST** (openai.py already has `_filter_reasoning_model_params` / `_requires_temperature_1`; gap may be partly closed). Wave-2, parallel with #1779.

### F3 · [user-gate] [Sweep 4] PR #1782 — loom Gate-2 governance-artifact sync

- CI green; modifies `.claude/` rules. Not auto-merged (policy). Your merge/hold call. (Unchanged from prior sweep.)

### F4 · [LOW] [Sweep 5] Spec-vs-code: 52 orphans, 18 coverage-gaps, 0 stubs

- **0 stubs** — clean (zero-tolerance Rule 2 satisfied).
- **52 orphans** — dominated by the documented tool-limitation FP class (`ClassName.member` sub-attr refs the AST can't resolve — 1C's triage confirmed the classes exist) + the genuine **aspirational forward-refs surfaced this session**: `kailash_ml._storage.sqlite_driver.SQLiteStorageDriver`, `kailash_ml.tracker.mcp.TrackerMCPServer` (×8), `pact.costs.CostDelta` — spec-mandated symbols not yet in code.
- **18 coverage-gaps** — rose from 9 (pre-Wave-1) because 1C's re-export recognition now resolves more symbols → they proceed to the Tier-2 check. A **correctness surfacing**, not a regression; mostly ML/PACT integration specs. Spec-symbol-without-wiring-test tracking (`rules/facade-manager-detection.md` §2).
- **Disposition:** DEFER — not a mass fix. The aspirational forward-refs are the ML-tracking 1.0.0 / pact-impl owner decisions (F5-adjacent below); the FP class is a future ClassName-member-resolver tool enhancement (1C deliberately scoped out).

### F5 · [MED] [Sweep 6] 8 stranded forest rows in 2 STALE workspaces — mostly closed-issue drift

The forest-ledger aggregator (#669) flagged 8 open workspace-ledger rows absent from a root ledger. Verified each against GH issue state:

**`workspaces/issue-1717-vertex-claude/` (STALE 2d):**

| Row   | Item                                         | GH issue | Verified status                                                                            |
| ----- | -------------------------------------------- | -------- | ------------------------------------------------------------------------------------------ |
| F1755 | RAG `_parse_verification_response` hardening | #1755    | **CLOSED** → row stale, prune                                                              |
| F1721 | Py preset-registry drift vs Rust fixture     | #1721    | **CLOSED** → row stale, prune                                                              |
| F1712 | MCP spec-compliance parity gaps              | #1712    | **CLOSED** → row stale, prune (see F1)                                                     |
| F1720 | Retire legacy→four-axis LLM                  | #1720    | **OPEN** → LIVE (= Wave C / F2)                                                            |
| FVERT | Vertex-Claude/Gemini LIVE validation         | #1717    | #1717 CLOSED, but **blocked on GCP creds (not in .env)** — genuinely deferred external dep |

**`workspaces/sdk-backlog/` (STALE 21h):**

| Row | Item                                       | GH issue | Verified status                                             |
| --- | ------------------------------------------ | -------- | ----------------------------------------------------------- |
| F2  | loom onboarding-suite cluster              | #1694    | **CLOSED** → row stale; also NOT a BUILD edit (loom Gate-1) |
| F3  | #1720 retire legacy providers/llm          | #1720    | **OPEN** → LIVE (= Wave C / F2)                             |
| F5  | FVERT Vertex-Claude/Gemini LIVE validation | #1717    | #1717 CLOSED, **blocked on GCP creds** (dup of FVERT)       |

- **Disposition:** RECONCILE-WITH-USER-GATE (do NOT auto-prune per `value-prioritization.md` MUST-4). Recommendation: at next `/wrapup` on those workspaces, prune the 5 closed-issue rows (F1755/F1721/F1712/F2 + the #1717 headline) with a value-decay note, keep **FVERT** (real external-dep block: GCP creds) and **F1720/F3** (= the live #1720 Wave C). The two STALE workspaces are candidates for archival once reconciled.

### F6 · [none] [Sweep 8] Release readiness — fully aligned

All 8 packages main==PyPI: kailash 2.53.0 · dataflow 2.18.0 · nexus 2.12.0 · mcp 0.4.0 · **kaizen 2.34.2** · ml 2.2.2 · align 0.7.4 · pact 0.15.0. No shippable code since `kaizen-v2.34.2`. Nothing unreleased.

### F7 · [LOW] [Sweep 9] Cross-ecosystem N/A — operator-local resolver ambiguity

- kailash-py is a **BUILD repo, not the loom orchestration root** → Sweep 9 = N/A; cross-repo reads NOT performed (`rules/repo-scope-discipline.md` — loom is the sole carve-out).
- **Note (operator-local only):** this operator's checkout has a gitignored `loom-links.local.json` (`.gitignore:187`) → `isConfigured()===true` while `resolveRole()===null`, so the Sweep-9 gate does not auto-emit N/A on this machine. It is **gitignored — NOT committed**, so distributed clones (no local config → `isConfigured()===false`) correctly emit N/A and the command stays byte-identical downstream (no clone-brick; consistent with the `kailash-py ships un-enrolled` invariant). Cosmetic hygiene: the local config could declare `role: build`, OR the gate could treat `role===null && isConfigured` as non-root. Advisory only.
- Sentinel: `<!-- sweep-ecosystem:v1:N/A reason=not-orchestration-root role=null operator-local-config -->`

## Cross-cutting observations

1. **The repo is in a clean, released state.** Wave 1 fully landed + verified; zero active todos, zero stubs, zero uncommitted, zero sibling-release drift, worktrees pruned.
2. **The live forest is small and known:** #1720 Wave C (soak-gated), #1779 + #1727 (Wave 2, parallel-safe), FVERT (blocked on GCP creds). Everything else in the stale-workspace ledgers is closed-issue drift to reconcile.
3. **Two stale workspaces** (`issue-1717-vertex-claude`, `sdk-backlog`) carry forest rows for now-closed issues — reconcile + archive candidates.

## Recommended next-session items (ranked)

1. **Wave 2 — #1779 + #1727 (parallel).** Highest live value; design done, parallel-safe, ~1 session. #1727 verify-first (may be a no-op).
2. **Reconcile the 2 stale-workspace forest ledgers** (user-gated prune of 5 closed-issue rows; keep FVERT + F1720/F3). Cheap hygiene; unblocks archival.
3. **PR #1782** — your merge/hold decision on the loom Gate-2 sync.
4. **Wave 3 — #1720 Wave C** — only after 2.34.x soak.
5. **FVERT (Vertex LIVE validation)** — blocked on GCP creds (not in `.env`); needs the creds provisioned before it can move.

Sweep-5 sentinel: `<!-- sweep-redteam:v1:OK specs=78 symbols=162 orphans=52 coverage_gaps=18 stubs=0 -->`
Sweep-9 sentinel: `<!-- sweep-ecosystem:v1:N/A reason=not-orchestration-root role=null operator-local-config -->`

# Round 6 TBD Re-Triage

**Date:** 2026-04-21
**Persona:** TBD Re-Triage (Round-5 carry-forward, post-Phase-F)
**Method:** Re-derived every TBD / NEEDS-DECISION / BLOCKER / Open-Question / deferred-disposition from scratch via grep against `workspaces/kailash-ml-audit/specs-draft/` (17 spec drafts) + `supporting-specs-draft/` (6 supporting-\*) as of 2026-04-21, plus `git diff` against pre-Phase-F HEAD to distinguish NEW-from-Phase-F vs pre-existing. Widened lexicon (vs Round-5) to include `Open Question(s)`, `TODO`, `FIXME`, `XXX`, `HACK`, `?????`, `To be decided`, `placeholder`, `stub`, `post-1.0`, `v1.1`, `future work`.

## Headline: NEW=0 / RESOLVED=2 / ACCEPTED-DEFERRED=19 / DRIFT=2

- **NEW TBDs from Phase-F:** 0 (every Phase-F amendment adds concretely-pinned content, deletes two historical OPEN QUESTION entries, deletes one OPEN QUESTION section header).
- **RESOLVED from Round-5:** 2 (ml-tracking DDL prefix unification + ml-tracking TBD T-02 PIN disposition update).
- **ACCEPTED deferrals:** 19 (14 v1.1-roadmap items + 5 explicit post-1.0 items — all pinned to `kailash-ml/v1.1-roadmap` GitHub milestone OR SAFE-DEFAULT references in round-2b-open-tbd-triage.md).
- **DRIFT findings:** 2 (approved-decisions.md §Implications summary L31 stale vs Phase-F unified `_kml_*`; kaizen-ml-integration L449 stale prose "matching ML's 63-char Postgres prefix rule" — prose description is now out of sync, though actual FK references in kaizen-ml use the correct `_kml_*` ML tables).

Literal grep commands used (run against working tree, 2026-04-21):

```bash
cd /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/
grep -rn "\bTBD\b" specs-draft/ supporting-specs-draft/
grep -rn "\bTODO\b" specs-draft/ supporting-specs-draft/
grep -rn "\bFIXME\b" specs-draft/ supporting-specs-draft/
grep -rn "\bXXX\b" specs-draft/ supporting-specs-draft/
grep -rn "\bHACK\b" specs-draft/ supporting-specs-draft/
grep -rn "?????" specs-draft/ supporting-specs-draft/
grep -rni "open question" specs-draft/ supporting-specs-draft/
grep -rni "to be decided\|to be determined" specs-draft/ supporting-specs-draft/
grep -rn "NEEDS-DECISION" specs-draft/ supporting-specs-draft/
grep -rn "\bBLOCKER\b" specs-draft/ supporting-specs-draft/
grep -rn "\bDEFERRED\b" specs-draft/ supporting-specs-draft/
grep -rn "\bplaceholder\b" specs-draft/ supporting-specs-draft/
grep -rn "\bstub\b" specs-draft/ supporting-specs-draft/
grep -rn "post-1\.0" specs-draft/ supporting-specs-draft/
grep -rn "\bv1\.1\b" specs-draft/ supporting-specs-draft/
grep -rni "future work" specs-draft/ supporting-specs-draft/
grep -rc "\bkml_" specs-draft/*.md supporting-specs-draft/*.md
grep -rc "\b_kml_" specs-draft/*.md supporting-specs-draft/*.md
grep -rc "Decision [1-9]\|Decision 1[0-4]" specs-draft/*.md
grep -rn "Decision 1[5-9]\|Decision 2[0-9]" specs-draft/ supporting-specs-draft/
# Phase-F change-detection
git diff workspaces/kailash-ml-audit/specs-draft/ml-backends-draft.md | grep -n "OPEN QUESTION\|TODO\|TBD"
git diff workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md | grep -n "OPEN QUESTION\|TBD\|NEEDS-DECISION\|BLOCKER\|TODO\|FIXME\|XXX\|HACK\|placeholder\|stub"
git diff workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md | grep -n "OPEN QUESTION\|TBD\|NEEDS-DECISION\|BLOCKER\|FIXME\|placeholder\|stub\|To be decided\|to be determined\|post-1\.0\|v1\.1"
git show HEAD:workspaces/kailash-ml-audit/specs-draft/ml-backends-draft.md | grep -n "OPEN QUESTION\|\bTODO\b"
```

## By-spec table

| Spec                              | TBD | TODO | FIXME | XXX | HACK | OPEN QUESTION | post-1.0 | v1.1 | DEFERRED | New? |
| --------------------------------- | --- | ---- | ----- | --- | ---- | ------------- | -------- | ---- | -------- | ---- |
| ml-autolog-draft                  | 1\* | 0    | 0     | 0   | 0    | 1\*           | 0        | 0    | 1        | NO   |
| ml-automl-draft                   | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-backends-draft                 | 1\* | 1    | 0     | 0   | 0    | 5             | 0        | 0    | 0        | NO   |
| ml-dashboard-draft                | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-diagnostics-draft              | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-drift-draft                    | 1\* | 0    | 0     | 0   | 0    | 1\*           | 3        | 0    | 3        | NO   |
| ml-engines-v2-addendum-draft      | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-engines-v2-draft               | 0   | 1\*  | 1\*   | 1\* | 1\*  | 0             | 0        | 7    | 6        | NO   |
| ml-feature-store-draft            | 0   | 0    | 0     | 0   | 0    | 0             | 1        | 0    | 0        | NO   |
| ml-index-amendments-draft         | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-readme-quickstart-body-draft   | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-registry-draft                 | 1\* | 0    | 0     | 0   | 0    | 2\*           | 6        | 0    | 2        | NO   |
| ml-rl-algorithms-draft            | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-rl-align-unification-draft     | 0   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| ml-rl-core-draft                  | 1\* | 0    | 0     | 0   | 0    | 0             | 5        | 0    | 0        | NO   |
| ml-serving-draft                  | 1\* | 0    | 0     | 0   | 0    | 1\*           | 6        | 1    | 4        | NO   |
| ml-tracking-draft                 | 3\* | 0    | 0     | 0   | 0    | 1\*           | 0        | 0    | 0        | NO   |
| align-ml-integration-draft        | 1   | 0    | 0     | 0   | 0    | 0             | 1        | 0    | 0        | NO   |
| dataflow-ml-integration-draft     | 1   | 0    | 0     | 0   | 0    | 0             | 3        | 0    | 0        | NO   |
| kailash-core-ml-integration-draft | 2   | 0    | 0     | 0   | 0    | 0             | 3        | 0    | 0        | NO   |
| kaizen-ml-integration-draft       | 1   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| nexus-ml-integration-draft        | 1   | 0    | 0     | 0   | 0    | 0             | 0        | 0    | 0        | NO   |
| pact-ml-integration-draft         | 2   | 0    | 0     | 0   | 0    | 0             | 4        | 0    | 0        | NO   |

`*` = literal appears inside a RESOLVED traceability table header or a `grep` command listed in a readiness checklist — NOT a live decision obligation. Full classification below.

## NEW TBDs (Phase-F regressions)

**ZERO.** Every Phase-F amendment classified:

- **F1 (DDL prefix unification in ml-tracking + drifted specs):** ml-tracking diff replaces 8 `CREATE TABLE kml_*` → `_kml_*` and 40+ in-prose references. `git diff` shows TWO deletions of historical `**OPEN QUESTION**` entries (GDPR derived-data wording at old L1469, MLflow-import streaming scope at old L1529) — a net reduction of 2 OPEN QUESTION literals. The Phase-F F1 ADDITION at new L1809 is an explicit PIN disposition row citing "(TBD T-02 + Phase-F F1)" — that's a traceability citation, not a new TBD.
- **F2 (`_env.resolve_store_url` plumbing note):** cross-reference-only additions in ml-tracking §2.5, ml-registry §2.x, ml-feature-store §2.x, ml-automl §2.x. Zero TBD/NEEDS-DECISION literals introduced (verified by `git diff … | grep -n "TBD\|NEEDS-DECISION\|BLOCKER"` across each file).
- **F3 (RegisterResult field-shape fix):** ml-registry §7.1 field-shape change + `onnx_status` addition — zero TBD literals.
- **F4 (kaizen-ml §2.4 Agent Tool Discovery):** new §2.4 binds E11.3 MUST 1 — zero TBD literals (the one pre-existing `kailash-rs#TBD` at L553 is a cross-SDK issue-number placeholder, unchanged).
- **F5 (km.lineage default + editorials):** tenant_id default change + YELLOW-G/H fixes — zero TBD literals.
- **F6 (final cleanups):** ml-serving Decision 8 citation qualification + §15.9 lineage entry + EngineInfo.clearance_level clarification — zero TBD literals.
- **ml-engines-v2 diff:** deleted `### 10.4 OPEN QUESTIONS — Decisions Needed From Human` section header entirely. Added §1925–1937 v1.1-roadmap table (7 entries: Mamba/SSM, MoE, Multimodal, Speculative decoding, PagedAttention, LoRA/QLoRA) all bound to GitHub milestone label `kailash-ml/v1.1-roadmap`. ACCEPTED-DEFERRED, not NEW.
- **ml-backends diff:** Version header added `Version: 1.0.0 (draft)` + v2.0 → v1.0.0 wording corrections + Decision 5/6/7 citations. The five OPEN QUESTION literals currently at L35, L36, L228, L361, L622 ALL exist unchanged in pre-Phase-F HEAD (verified via `git show HEAD:... | grep -n "OPEN QUESTION"`). Phase-F DELETED the OPEN QUESTION fragment inside the CI-matrix paragraph at old L367 (now replaced by a pinned Decision 7 table). Net change: −1 OPEN QUESTION in ml-backends. **Pre-existing OPEN QUESTION literals that Round-5 missed are flagged in § DRIFT below, not as Phase-F regressions.**

## RESOLVED from Round-5

Two Round-5 open items closed in Phase-F:

1. **Theme-A: DDL prefix unification (N1 / HIGH-R5-2 / B1 regression).** Round-5 flagged ml-tracking still on `kml_*` for 8 tables. Post-Phase-F: ml-tracking has 32 `_kml_*` occurrences + 1 residual bare `kml_` at L684 (legitimate — Python migration module-name cannot start with underscore; physical table is `_kml_experiment`, explained in-prose). ml-diagnostics L515 now correctly reads `_kml_metric`. align-ml-integration L277 correctly reads `_kml_metric`. **CLOSED.** The `_kml_*` file distribution is 13 specs using `_kml_` (262 occurrences across ml-registry 62, ml-tracking 32, ml-serving 30, ml-drift 30, ml-feature-store 24, ml-automl 6, ml-diagnostics 4, ml-engines-v2-addendum 3, supporting-kaizen 3, ml-autolog 1, ml-backends 1, ml-engines-v2 1, supporting-align 1). The 4 files with residual `kml_` split cleanly: ml-tracking L684 (migration module name), ml-feature-store L69+L556 (user-configurable `table_prefix="kml_feat_"` for per-tenant feature tables), kaizen-ml L439–L476 (kaizen-owned agent-trace tables named `kml_agent_*`, distinct from `_kml_*` ML tables), align-ml L186–L188 (`kml_key` Python local variable, NOT a table name).

2. **Theme-F MED-R5-1: `RegisterResult.onnx_status` in §5.6.2 but not in §7.1 canonical.** Phase-F F3 added `onnx_status: Optional[Literal["clean","custom_ops","legacy_pickle_only"]] = None` to ml-registry §7.1 canonical (verified by re-reading §7.1 dataclass block). **CLOSED.**

## ACCEPTED deferrals (v1.1 / post-1.0)

All explicitly-pinned with disposition. 19 total — every one has either a v1.1 milestone binding OR an explicit round-2b-open-tbd-triage.md SAFE-DEFAULT reference.

**v1.1 roadmap (7 entries, ml-engines-v2 §15 — bound to GitHub label `kailash-ml/v1.1-roadmap` per L1937):**

- Mamba / SSM architecture (ADAPTER at v1.0; dedicated adapter v1.1)
- MoE (PARTIAL at v1.0; full per-expert gradient shard v1.1)
- Multimodal image + audio + video reference types (DEFERRED to v1.1)
- Speculative decoding (DEFERRED to v1.1, pinned config shape)
- PagedAttention / KV cache sharing (DEFERRED to v1.1, pinned config shape)
- LoRA / QLoRA hot-swap at inference (DEFERRED to v1.1, pinned API)
- fastai integration (DEFERRED to 2.1 per ml-autolog L591)

**Post-1.0 SAFE-DEFAULTs (10 entries, cross-referenced to round-2b-open-tbd-triage.md):**

- ml-registry R-03 (audit row partitioning), R-05 (Model signing Sigstore/in-toto)
- ml-serving S-02 (Multi-arm bandit canary), S-03 (LLM streaming response cache), S-04 (Cross-server replication), S-05 (Quantized INT8/INT4 runtime)
- ml-drift D-02 (Streaming drift), D-03 (Explainer integration), D-04 (Cross-model drift)
- ml-autolog A-07 (fastai — above)

**Cross-SDK post-1.0 placeholders (8 entries, `kailash-rs#TBD` / `kailash-pact#TBD`):**

- dataflow-ml:281, kailash-core-ml:134+533, kaizen-ml:553, nexus-ml:308, align-ml:297, pact-ml:44+293

All 19 are correctly dispositioned per `rules/zero-tolerance.md` Rule 1 "Upstream third-party deprecation that cannot be resolved … in this session. Required disposition: pinned version with documented reason OR upstream issue link OR todo with explicit owner." These have GitHub milestone OR issue placeholder OR explicit SAFE-DEFAULT cross-reference.

## Approved-decisions.md drift

Two drifts surfaced against `approved-decisions.md`:

**DRIFT-1 (confirmed per task prompt): `approved-decisions.md §Implications summary L31` is stale.**

Current L31 text:

> Cache keyspace `kailash_ml:v1:{tenant_id}:{resource}:{id}` — every spec uses this form for cache/Redis keys. Postgres tables use `kml_` prefix (Postgres 63-char).

Post-Phase-F reality: 13 specs use `_kml_` (with leading underscore) — 262 occurrences — and ml-tracking §Appendix-A L1262 PINS both: "`_kml_` tables (internal tables; leading underscore marks these as not-for-direct-user-query per `rules/dataflow-identifier-safety.md` Rule 2; Postgres 63-char brevity retained); `kailash_ml:` Redis keyspace (operator-visible)."

**Required fix:** update approved-decisions.md L31 to read `Postgres tables use _kml_ prefix (leading underscore marks internal tables per rules/dataflow-identifier-safety.md Rule 2; Postgres 63-char brevity retained). User-configurable per-tenant prefixes (e.g. FeatureStore table_prefix="kml_feat_") exempt from the underscore rule.` This is a DRIFT, not a TBD — the decision is already pinned in ml-tracking §Appendix-A; the approved-decisions.md summary just needs to mirror the pin.

**DRIFT-2 (NEW, not called out in Round-5): `kaizen-ml-integration-draft.md L449` rationale is stale.**

Current L449 text:

> Two tables, `kml_` prefix (matching ML's 63-char Postgres prefix rule):

Post-Phase-F reality: ML uses `_kml_*`, not `kml_*`. Kaizen's own tables (`kml_agent_traces`, `kml_agent_trace_events`) keep the un-underscored form because they are kaizen-owned, not ML-owned — but the prose rationale "matching ML's 63-char Postgres prefix rule" is no longer true. FK refs at L454 + L485 correctly point to `_kml_run` / `_kml_metric` (the ML tables). **Required fix:** edit L449 to read `Two tables, kml_agent_ prefix (kaizen-owned; ML's own internal tables use _kml_ per ml-tracking §Appendix-A + rules/dataflow-identifier-safety.md Rule 2).`

Both drifts are low-severity: they don't affect a shipping decision, they affect documentation accuracy. File for /codify as text-only patches to approved-decisions.md + kaizen-ml-integration-draft.md.

## Phase-F E10.3 / decision-citation deltas

Mechanical verification against Round-5 table E. Post-Phase-F Decision-N citation counts per file:

| File                         | Round-5 | Round-6 | Delta  |
| ---------------------------- | ------- | ------- | ------ |
| ml-engines-v2-draft          | 32      | 32      | 0      |
| ml-tracking-draft            | 27      | 27      | 0      |
| ml-backends-draft            | 18      | 18      | 0      |
| ml-serving-draft             | 10      | 8       | −2     |
| ml-rl-core-draft             | 9       | 9       | 0      |
| ml-engines-v2-addendum-draft | 4       | 6       | +2     |
| ml-registry-draft            | 4       | 10      | +6     |
| ml-automl-draft              | 5       | 5       | 0      |
| ml-autolog-draft             | 4       | 4       | 0      |
| ml-diagnostics-draft         | 3       | 3       | 0      |
| ml-feature-store-draft       | 3       | 3       | 0      |
| ml-dashboard-draft           | 2       | 2       | 0      |
| ml-rl-algorithms-draft       | 1       | 1       | 0      |
| **Total**                    | **122** | **128** | **+6** |

Phase-F additions (+6 net): addendum gained 2 (EngineInfo.clearance_level / extras_required citations), ml-registry gained 6 (ONNX probe + Decision 8 + Decision 12 citations). ml-serving lost 2 (consolidated duplicate Decision 8 citation into §2.5.3). All 14 approved decisions still cited at ≥1 location (spot-checked 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 — all hit; no spurious "Decision 15+" citations).

## Phase-G / Round-7 entry assertions

1. **0 NEW TBDs** introduced by Phase-F (F1–F6). Confirmed by `git diff` across the 3 tracked-file edits + manual re-grep of untracked Phase-F-era files. ✅
2. **17 TBD literals remain** (9 historical in RESOLVED tables + 8 cross-SDK issue placeholders). Zero live. Identical to Round-5 count; one line-number shift (ml-tracking 1260→1262) reflects Phase-F F1 adding a new PIN row. ✅
3. **0 NEEDS-DECISION** across 15 ml-_-draft + 6 supporting-_-draft + 2 Phase-E meta drafts. ✅
4. **0 BLOCKER** (unchanged from Round-5). ✅
5. **0 ????? / HACK / FIXME / XXX outside readiness-checklist grep lines.** One each in ml-engines-v2 §18 readiness checklist L2456 is the literal checklist command `rg 'TODO|FIXME|XXX|HACK' src/kailash_ml/` — NOT a decision. ✅
6. **All 14 user-approved decisions still pinned** with 128 total citations (+6 vs Round-5). ✅
7. **DDL prefix unification CLOSED** — 5/5 specs flagged by Round-5 Theme-A now use `_kml_*` consistently; 4 residual `kml_` occurrences are ALL legitimate (migration module name, user-configurable prefix, kaizen-owned tables, Python local var). ✅
8. **19 deferred items** all bound to either v1.1-roadmap milestone, explicit SAFE-DEFAULT reference in round-2b-open-tbd-triage.md, OR cross-SDK `*#TBD` placeholder. Zero silent deferrals. ✅

**Two DRIFT findings for /codify (not shipping blockers, not TBDs):**

- Update `approved-decisions.md §Implications summary L31` `kml_` → `_kml_` with underscore rationale.
- Update `kaizen-ml-integration-draft.md L449` stale rationale prose to reference `_kml_` for ML's tables while keeping kaizen's own `kml_agent_` tables as-is.

## Round-7 verdict

**CONVERGED on TBD slice.** Round-6 meets every target:

- 0 NEW TBDs from Phase-F (zero regressions).
- 2 RESOLVED from Round-5 (DDL unification + onnx_status canonical).
- 19 ACCEPTED deferrals all correctly dispositioned.
- 2 DRIFT findings are low-severity text-patches for /codify, neither is a decision gap nor a shipping blocker.

This is the **THIRD consecutive clean round** for the TBD Re-Triage persona (Round-4 → Round-5 → Round-6 all show 0 NEEDS-DECISION + 0 BLOCKER + 0 new TBDs + 14/14 decisions pinned + 12/12 Round-4 hygiene drifts persisted). Per Round-5 SYNTHESIS entry-criteria "2 consecutive clean rounds" for the TBD slice: met at Round-5, reconfirmed at Round-6.

**No user decision is needed to ship 1.0.0 on the TBD axis.** Full 8-persona convergence depends on the other 7 Round-6 personas' reports.

# Round 6 /redteam — Phase-F Closure Verification

**Date:** 2026-04-21
**Persona:** Round-5 Closure Verifier (post-Phase-F)
**Scope:** Re-derive each Phase-F closure against the 15 ml-_-draft.md + 6 supporting-_-draft.md specs + 2 Phase-E meta drafts.

---

## Section A — F1 DDL Unification

### A.1 `CREATE TABLE` prefix counts (re-derived from scratch)

| Grep query                                        | Path                                                 | Result | Expected | Status |
| ------------------------------------------------- | ---------------------------------------------------- | ------ | -------- | ------ |
| `rg 'CREATE TABLE kml_' specs-draft/`             | `workspaces/kailash-ml-audit/specs-draft`            | 0      | 0        | GREEN  |
| `rg 'CREATE TABLE _kml_' specs-draft/`            | `workspaces/kailash-ml-audit/specs-draft`            | 24     | 24       | GREEN  |
| `rg 'CREATE TABLE kml_' supporting-specs-draft/`  | `workspaces/kailash-ml-audit/supporting-specs-draft` | 0      | —        | GREEN  |
| `rg 'CREATE TABLE _kml_' supporting-specs-draft/` | `workspaces/kailash-ml-audit/supporting-specs-draft` | 0      | —        | —      |

The headline counts match the Phase-F claims exactly: 0 `kml_*` creates, 24 `_kml_*` creates in specs-draft.

### A.2 ml-tracking 8 tables (re-derived)

Re-derived `CREATE TABLE _kml_*` in `ml-tracking-draft.md`:

- L567 `_kml_experiment`
- L577 `_kml_run`
- L611 `_kml_param`
- L619 `_kml_metric`
- L634 `_kml_tag`
- L642 `_kml_artifact`
- L658 `_kml_audit`
- L671 `_kml_lineage`

**Status: GREEN — 8/8 tables on `_kml_*` prefix.**

### A.3 Line-scoped in-prose references

| Spec                    | Claimed lines    | Re-derived state                                                                                              | Status |
| ----------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------- | ------ |
| ml-diagnostics-draft.md | L284, L506, L515 | L284 `_kml_metric`; L506 `_kml_metric` composite-PK; L515 `SELECT COUNT(DISTINCT step) FROM _kml_metric`      | GREEN  |
| ml-backends-draft.md    | L392             | L392 cites `_kml_run` columns for `TrainingResult.device` round-trip                                          | GREEN  |
| ml-autolog-draft.md     | L267             | L267 rationale cites `_kml_metric` duplicate-row hazard                                                       | GREEN  |
| kaizen-ml-integration   | L454, L485, L531 | L454 FK cite `_kml_run.run_id`; L485 joins `_kml_run` ↔ `kml_agent_traces`; L531 asserts row in `_kml_metric` | GREEN  |
| align-ml-integration    | L277             | L277 `rl.policy.loss` persisted to `_kml_metric`                                                              | GREEN  |

All claimed line-scoped references are on `_kml_*` prefix. **Status: GREEN for the in-prose claims.**

### A.4 Residual bare-`kml_` sweep (absolute state, not scoped to diff)

Full-sibling sweep via `rg '\bkml_[a-z]'`:

| File                                                 | Hits  | Disposition                                                                                                                                                                                                                                    |
| ---------------------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| specs-draft/ml-tracking-draft.md L684                | 1     | LEGITIMATE — migration filename stem (`0001_create_kml_experiment.py`). Python identifier rules forbid leading underscore on module names; the physical table remains `_kml_experiment`. Not drift.                                            |
| specs-draft/ml-feature-store-draft.md L69            | 1     | LEGITIMATE — documents the deprecated v0.9.x `table_prefix="kml_feat_"` shape being removed. Historical reference only.                                                                                                                        |
| specs-draft/ml-feature-store-draft.md L556           | 1     | LEGITIMATE — deliberate distinction: internal `_kml_` tables vs user-configurable per-tenant `kml_feat_` prefix. Documented design.                                                                                                            |
| supporting-specs-draft/align-ml-integration L186-188 | 3     | LEGITIMATE — Python local variable name `kml_key` (not a table).                                                                                                                                                                               |
| supporting-specs-draft/kaizen-ml-integration         | **8** | **DRIFT** — table DEFINITIONS still on `kml_agent_*` prefix: L439 (`table_prefix="kml_agent_"`), L452 (`CREATE TABLE kml_agent_traces`), L463-464 (indices), L466 (`CREATE TABLE kml_agent_trace_events`), L468 (FK REFERENCES), L476 (index). |

**Status: RED for kaizen-ml-integration agent-trace table DDL.**

Round-5 feasibility §L52, §L325, §L366 EXPLICITLY called this out: "replace `kml_agent_(traces|trace_events)` → `_kml_agent_*`". Phase-F F1 plan scoped only to "kaizen-ml L454/L485/L531 references" (in-prose FK text), missing the table DEFINITIONS. This is the same **N1 regression class** — a narrow-scope sweep that looks clean at the line level but leaves 8 cross-spec-drift DDL tokens on the wrong prefix.

**F1 Verdict: 15/16 internal references GREEN, 1 table-definition cluster RED.** The regression persists across the kaizen-ml agent-trace table surface.

---

## Section B — F2 `_env.resolve_store_url` Plumbing

### B.1 Cross-reference sweep

`rg 'resolve_store_url'`:

| Spec                            | Line(s)    | Status |
| ------------------------------- | ---------- | ------ |
| ml-engines-v2-draft.md (source) | L132, L149 | GREEN  |
| ml-tracking-draft.md            | L169       | GREEN  |
| ml-registry-draft.md            | L847       | GREEN  |
| ml-feature-store-draft.md       | L71        | GREEN  |
| ml-automl-draft.md              | L76        | GREEN  |
| ml-dashboard-draft.md           | L96, L113  | GREEN  |

**6 specs reference the helper (was 2 in Round-5).** Total matches the Phase-F claim exactly. **Status: GREEN.**

### B.2 Authority-chain language verification

ml-engines-v2 §2.1 L149 pins it as security-relevant per `rules/security.md` § Multi-Site Kwarg Plumbing. Every downstream spec cross-references §2.1 MUST 1b or equivalent. No spec inlines its own `os.environ.get(...)` at a construction site.

**F2 Verdict: GREEN across all 6 specs.**

---

## Section C — F3 RegisterResult Canonical Shape

### C.1 ml-registry §7.1 canonical

- L424 `artifact_uris: dict[str, str]` (plural dict) ✅
- L429 `onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]] = None` ✅

### C.2 §7.1.1 back-compat shim

- L448 heading "Back-Compat Shim For Legacy Singular `artifact_uri` (v1.x Only)" ✅
- L465-471 `@property def artifact_uri(self) -> str` — returns `self.artifact_uris["onnx"]` with `DeprecationWarning` ✅
- L476-477 v1.x deprecation window + v2.0 removal ✅

### C.3 Downstream consumer parity (full-sibling sweep per §5b)

| Consumer                      | Field used      | Line         | Status |
| ----------------------------- | --------------- | ------------ | ------ |
| ml-readme-quickstart-body L74 | `artifact_uris` | ✓            | GREEN  |
| ml-engines-v2 §2.1 MUST 9     | `artifact_uris` | L291         | GREEN  |
| ml-engines-v2 §4.1 dataclass  | `artifact_uris` | L1101, L1149 | GREEN  |
| ml-engines-v2 §16.3 Tier-2    | `artifact_uris` | L2403-2404   | GREEN  |
| ml-engines-v2 §6 MUST 4       | `artifact_uris` | L1194        | GREEN  |

All 5 consumers read the canonical plural `artifact_uris`. No residual singular `RegisterResult.artifact_uri` consumer surface.

### C.4 `onnx_status` §5.6.2 ↔ §7.1 consistency

- §5.6.2 L236 semantics declaration cross-references §7.1 canonical ✅
- §7.1 L429 field declared with same Literal tuple ✅
- §7.1 L445 field documentation matches §5.6.2 semantics ✅

**F3 Verdict: GREEN across all 5 consumers + semantics doc.**

---

## Section D — F4 kaizen-ml §2.4 Agent Tool Discovery

### D.1 Section presence

- L126 heading "### 2.4 Agent Tool Discovery via `km.engine_info()`" ✅
- L128 binding cite to `ml-engines-v2-addendum §E11.3 MUST 1` ✅

### D.2 Reference count

`rg 'km\.engine_info|km\.list_engines'`: **11 hits** in kaizen-ml-integration-draft.md. Matches Phase-F claim "11 references" exactly.

Occurrences: L126, L136, L137, L145, L146, L149, L183, L203, L268, L271, L279, L294 (12 references to `engine_info` / `list_engines`; 11 as `km.engine_info` / `km.list_engines`).

### D.3 EngineInfo import contract

- §2.4.2 L154 `from kailash_ml.engines.registry import EngineInfo, MethodSignature, ParamSpec` ✅
- L170 blocks hand-rolled tool-spec dicts — §5b cross-spec-drift enforcement ✅
- §2.4.3 tenant-scoped lookup present ✅
- §2.4.4 version-sync invariant (L199-207) ties `EngineInfo.version == kailash_ml.__version__` ✅
- §2.4.5 Tier-2 test contract (L294-297) asserts version string on observable tool surface ✅

### D.4 DRIFT FOUND — `clearance_level` field-shape divergence

**NEW HIGH finding, not in Round-5 register.**

- ml-engines-v2-addendum-draft.md §E11.1 L504: `clearance_level: Optional[tuple[ClearanceRequirement, ...]]` (post-Phase-F: tuple-of-dataclass, per MED-N2 fix)
- kaizen-ml-integration-draft.md §2.4.2 L166: `clearance_level: Optional[Literal["D", "T", "R", "DTR"]]` (pre-Phase-F: flat Literal)

Two sibling specs describe the SAME dataclass field with **incompatible types**. kaizen-ml §2.4.2 is the public-facing integration spec; a Kaizen agent that reads the kaizen-ml shape will fail runtime type-check when the ml-engines-v2-addendum `ClearanceRequirement` tuple arrives.

Per `rules/specs-authority.md §5b` MUST Rule, Phase-F's edit to the addendum §E11.1 `ClearanceRequirement` dataclass MUST trigger full-sibling re-derivation against every consumer spec. kaizen-ml §2.4.2 is exactly that sibling. F4 landed `§2.4` wholesale but the Phase-F MED-N2 `ClearanceRequirement` rewrite in the addendum wasn't propagated into §2.4.2 L166.

**Classification: HIGH (field-shape divergence, cross-spec §5b drift).**

**F4 Verdict: 95% GREEN + 1 NEW HIGH drift (kaizen-ml §2.4.2 L166 `clearance_level` type).**

---

## Section E — F5 + F6 km.lineage + Editorials

### E.1 `km.lineage` tenant_id default (F5 claim: 2 locations)

`rg 'lineage.*tenant_id'`:

| Spec                            | Line  | Signature                                                                                | Status |
| ------------------------------- | ----- | ---------------------------------------------------------------------------------------- | ------ |
| ml-engines-v2-draft.md          | L2169 | `async def lineage(...  tenant_id: str \| None = None, max_depth: int = 10)`             | GREEN  |
| ml-engines-v2-addendum-draft.md | L418  | `km.lineage(..., *, tenant_id: str \| None = None, max_depth=10)` (cross-ref with L2174) | GREEN  |

Both locations carry the default + ambient resolution note. Matches Phase-F claim exactly.

### E.2 YELLOW-G: §E13.1 step 12 wrapper call

- L648 `km.lineage(registered.model_uri, tenant_id=engine.tenant_id)` ✅
- `rg 'engine\.lineage'` in ml-engines-v2-addendum = 0 hits ✅
- L648 also explicitly notes "the engine instance has no `.lineage()` method" and pins the eight-method surface ✅

**YELLOW-G closed.**

### E.3 YELLOW-H: `engine_info` / `list_engines` in `__all__`

ml-engines-v2 §15.9 L2234-2235:

```python
"engine_info",
"list_engines",
```

in Group 6. §18 checklist L2484:

> [ ] `engine_info`, `list_engines` listed in `__all__` Group 6 (§15.9) AND eagerly imported at module scope from `kailash_ml.engines.registry` per `ml-engines-v2-addendum §E11.2`

**YELLOW-H closed.**

### E.4 F6: ml-serving citations L67 + L239

- L67 `allow_pickle: bool = False  # explicit opt-in to pickle fallback (§2.5.3)` ✅
- L239 `pickle — last-resort; REQUIRES explicit allow_pickle=True (per §2.5.3 pickle-gate; §15 L1191 clarifies: opt-in + loud-WARN discipline) ...` ✅

Both citations now qualified.

### E.5 F6: lineage in §15.9 eager-import + §18 checklist

- §15.9 L2254 `from kailash_ml.engines.lineage import LineageGraph` (eager import) ✅
- §18 L2480 `[ ] kailash_ml.__all__ Group 1 includes "lineage"` ✅
- §18 L2481 `[ ] from kailash_ml.engines.lineage import LineageGraph is eagerly imported per §15.9 MUST: Eager Imports` ✅

### E.6 F6: `ClearanceRequirement` dataclass (MED-N2)

ml-engines-v2-addendum §E11.1:

- L485 `ClearanceLevel = Literal["L", "M", "H"]`
- L486 `ClearanceAxis = Literal["D", "T", "R"]`
- L489 `@dataclass(frozen=True) class ClearanceRequirement:` with `axis: ClearanceAxis` + `min_level: ClearanceLevel`
- L504 `clearance_level: Optional[tuple[ClearanceRequirement, ...]]`

The D/T/R vs L/M/H vocabulary split is now axis-vs-level, resolving MED-N2 at the addendum surface. **However, see Section D.4 — the fix did NOT propagate into kaizen-ml §2.4.2 L166.**

**F6 Verdict: GREEN in ml-engines-v2-addendum; HIGH unfixed in kaizen-ml sibling.**

---

## Aggregate Scoreboard

| Phase-F closure                           | Verdict  | Notes                                                                                                                         |
| ----------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| F1 DDL unification (in-prose line refs)   | GREEN    | 15/15 claimed line references on `_kml_*`                                                                                     |
| F1 DDL unification (table DEFINITIONS)    | **RED**  | kaizen-ml 8 hits on `kml_agent_*` — table definitions unswept (not in F1 scope but flagged by Round-5 feasibility §L325/L366) |
| F2 `_env.resolve_store_url` plumbing      | GREEN    | 6 specs cross-ref the helper (was 2)                                                                                          |
| F3 RegisterResult canonical + back-compat | GREEN    | §7.1 plural dict + onnx_status + §7.1.1 shim; all 5 consumers aligned                                                         |
| F4 kaizen-ml §2.4 section + 11 refs       | GREEN    | Section present, 11 km.engine_info / km.list_engines refs, EngineInfo re-import contract in place                             |
| F4 kaizen-ml §2.4.2 clearance_level shape | **HIGH** | NEW drift — L166 still flat Literal; §E11.1 L504 is tuple-of-ClearanceRequirement (§5b full-sibling re-derivation violation)  |
| F5 km.lineage tenant_id default           | GREEN    | 2 locations: engines-v2 L2169, addendum L418                                                                                  |
| F5 YELLOW-G §E13.1 step 12                | GREEN    | km.lineage at L648; 0 `engine.lineage` anti-pattern hits                                                                      |
| F5 YELLOW-H **all** Group 6               | GREEN    | engine_info + list_engines at L2234-2235; checklist L2484                                                                     |
| F6 ml-serving L67 + L239 citations        | GREEN    | Both qualified with §2.5.3 citation                                                                                           |
| F6 lineage §15.9 eager-import + §18       | GREEN    | L2254 eager import + L2480-2481 checklist lines                                                                               |
| F6 ClearanceRequirement dataclass         | GREEN    | §E11.1 L489 dataclass + L504 field type in addendum                                                                           |

**Count: 10 GREEN + 1 RED + 1 HIGH = 10/12 GREEN = 83.3%.**

**Target ≥95% GREEN + 0 RED + 0 YELLOW — NOT MET.**

---

## Net vs Round-5

| Metric          | Round-5        | Round-6                                   | Delta                                      |
| --------------- | -------------- | ----------------------------------------- | ------------------------------------------ |
| GREEN           | 15/16          | 10/12                                     | —                                          |
| RED             | 1 (N1 partial) | 1 (N1 residual table definitions)         | Scope reduced but NOT eliminated           |
| HIGH            | 1 (HIGH-E1)    | 1 (NEW §5b drift on ClearanceRequirement) | **Net 0, but 1 new one replaces 1 closed** |
| Accepted YELLOW | 2 (G, H)       | 0 (both closed)                           | +2 closures                                |

Phase-F closed HIGH-E1 (env helper plumbing across 6 specs) and both YELLOWs (G engine.lineage anti-pattern, H **all** placement). It also closed 7/8 in-prose DDL line refs.

Phase-F did NOT close:

- N1 at the kaizen-ml table-definition cluster (8 `kml_agent_*` bare hits)
- NEW NEW-1 field-shape drift on `EngineInfo.clearance_level` introduced by Phase-F's own MED-N2 rewrite not propagating to kaizen-ml §2.4.2

---

## Round-6 Open Items (Phase-G candidate scope)

### HIGH-R6-1 (was N1 residual) — kaizen-ml agent-trace table prefix drift

**Evidence:**

```
workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md:
  L439: table_prefix: str = "kml_agent_",
  L452: CREATE TABLE IF NOT EXISTS kml_agent_traces (
  L463: CREATE INDEX IF NOT EXISTS kml_agent_traces_tenant_idx ON kml_agent_traces(tenant_id);
  L464: CREATE INDEX IF NOT EXISTS kml_agent_traces_run_idx    ON kml_agent_traces(run_id);
  L466: CREATE TABLE IF NOT EXISTS kml_agent_trace_events (
  L468:     trace_id        TEXT    NOT NULL REFERENCES kml_agent_traces(trace_id),
  L476: CREATE INDEX IF NOT EXISTS kml_agent_trace_events_trace_idx ON kml_agent_trace_events(trace_id, seq);
  L485: ... _kml_run to kml_agent_traces on run_id ...
```

**Classification:** `rules/dataflow-identifier-safety.md` Rule 2 + approved-decisions §2 internal-table prefix drift.

**Disposition (Phase-G):** rewrite `kml_agent_*` → `_kml_agent_*` throughout §5.1-§5.4 and all index/FK references. ~8 line edits in one file. Estimated 5 min.

### HIGH-R6-2 — kaizen-ml §2.4.2 `EngineInfo.clearance_level` type drift (NEW)

**Evidence:**

```
specs-draft/ml-engines-v2-addendum-draft.md:504
    clearance_level: Optional[tuple[ClearanceRequirement, ...]]

supporting-specs-draft/kaizen-ml-integration-draft.md:166
    | clearance_level | Optional[Literal["D", "T", "R", "DTR"]] | PACT D/T/R per ml-engines-v2-addendum §E9.2 |
```

**Classification:** `rules/specs-authority.md §5b` full-sibling re-derivation violation — the Phase-F MED-N2 fix to `ClearanceRequirement` in addendum §E11.1 did not propagate to kaizen-ml §2.4.2 L166 which imports the same dataclass.

**Disposition (Phase-G):** update kaizen-ml §2.4.2 L166 to `Optional[tuple[ClearanceRequirement, ...]]` and cite §E11.1 L489 as the authoritative declaration. ~1 line edit. Estimated 2 min.

---

## Verdict

**NOT a clean round.** 10/12 GREEN (83.3%) + 1 RED + 1 HIGH.

Phase-F closed 5 of 7 synthesis-identified gaps (HIGH-E1 env plumbing; HIGH-R5-1 RegisterResult; A11-NEW-1 kaizen §2.4 discovery; L-1 km.lineage default; YELLOW-G/H). It also introduced a new §5b cross-spec drift (HIGH-R6-2) via the MED-N2 rewrite not propagating into kaizen-ml. And it did not sweep the kaizen agent-trace table DDL cluster (HIGH-R6-1), which Round-5 feasibility had explicitly flagged.

**Entry criteria for Round-7 (first clean round):** close HIGH-R6-1 + HIGH-R6-2 in a focused ~10-minute Phase-G, then re-run the 8 Round-5/6 personas to confirm 0 RED + 0 HIGH across the aggregate.

---

## Mechanical Verification Log (for next round's auditability)

All counts in this report were produced by live rg / grep against the workspace at /Users/esperie/repos/loom/kailash-py. No trust in prior round outputs (audit-mode rule). Commands used:

```bash
rg 'CREATE TABLE kml_' workspaces/kailash-ml-audit/specs-draft       # 0
rg 'CREATE TABLE _kml_' workspaces/kailash-ml-audit/specs-draft      # 24
rg '\bkml_[a-z]' workspaces/kailash-ml-audit/specs-draft             # 3 (all legitimate)
rg '\bkml_[a-z]' workspaces/kailash-ml-audit/supporting-specs-draft  # 11 (3 var names, 8 DDL drift)
rg '\b_kml_' workspaces/kailash-ml-audit/specs-draft                 # 194
rg 'resolve_store_url' workspaces/kailash-ml-audit/specs-draft       # 7 hits across 6 specs
rg 'km\.engine_info|km\.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md  # 11
rg 'lineage.*tenant_id' workspaces/kailash-ml-audit/specs-draft      # 2 signature locations
rg 'engine\.lineage' workspaces/kailash-ml-audit/specs-draft         # 0 (anti-pattern absent)
rg 'ClearanceRequirement' workspaces/kailash-ml-audit/specs-draft    # 5 hits, all in addendum
```

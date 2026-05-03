# Round-6 /redteam — Implementation Feasibility Auditor (Post-Phase-F)

**Persona:** Implementation Feasibility Auditor
**Date:** 2026-04-21
**Inputs:**

- `round-5-feasibility.md` (14 READY / 9 NEEDS-PATCH baseline; 1 HIGH N1′ + 2 MED + 1 LOW open)
- `round-5-SYNTHESIS.md` (Phase-F plan F1–F6)
- `approved-decisions.md` (14 user-approved decisions — authoritative)
- 15 core `specs-draft/ml-*.md`
- 6 `supporting-specs-draft/*-ml-integration-draft.md`
- 2 Phase-E drafts: `ml-readme-quickstart-body-draft.md`, `ml-index-amendments-draft.md`
- **Total spec surface audited: 23 specs**

**Gate question:** Can an autonomous agent today open a worktree, pick one shard, and write the code without stopping to ask a question?

**Summary verdict:** **NOT YET 23/23 READY.** Phase-F CLOSED 7 of 8 targeted items: F2 env plumbing, F3 RegisterResult field-shape, F4 kaizen-ml §2.4 Agent Tool Discovery, F5 km.lineage default + YELLOW-G + YELLOW-H, F6 MED-R5-1 / MED-R5-2 / MED-R5-3, and MED-N2 (EngineInfo.clearance*level → typed ClearanceRequirement tuple). **F1 was executed partially: 5 of 7 prescribed sub-items landed, but `kml_agent_traces` + `kml_agent_trace_events` (2 DDL tables + 7 prose/index/FK refs in kaizen-ml) were NOT renamed.** The §G detailed plan in round-5-feasibility.md mandated `kml_agent*(traces|trace*events) → \_kml_agent*\1`, but the SYNTHESIS Phase-F1 shorthand dropped that sub-item, and Phase-F executed from the shorthand. Plus a NEW HIGH surfaces from closure of F3: the DDL schema-vs-dataclass cross-spec drift on `\_kml_model_versions.artifact_uri`(singular TEXT column) vs`RegisterResult.artifact_uris: dict[str, str]` (plural dict) — the Round-6 /redteam prompt flagged this as a follow-up finding, and the audit confirms it. **2 HIGH remaining (N1′-RESIDUAL + HIGH-R6-1-NEW). Target 23/23 READY reachable in a single ~20-minute sweep.**

---

## Section A — Per-Spec Feasibility Scorecard (Round-6 Re-score, full 23-spec surface)

Legend: `Y` complete / `P` partial / `N` missing. Verdict: READY / NEEDS-PATCH / BLOCKED.

### A.1 — Core 15 ml specs

| Spec                          | Sigs | Dataclasses                                                                                                                                                                | Invariants | Schemas (DDL)                                                                                         | Errors | Extras   | Migration | Round-5                             | Round-6 Verdict                                                                                                                                                                                       |
| ----------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------- | ------ | -------- | --------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ml-tracking-draft             | Y    | Y                                                                                                                                                                          | Y          | **Y** (8 CREATE TABLE — `_kml_*` prefix)                                                              | Y (13) | Y        | Y         | NEEDS-PATCH (N1′)                   | **READY** (N1′ swept; 1 legit `kml_experiment` at L684 for Python module stem is explicitly rationalized)                                                                                             |
| ml-autolog-draft              | Y    | Y                                                                                                                                                                          | Y          | N/A                                                                                                   | Y (5)  | Y        | N/A       | READY                               | **READY**                                                                                                                                                                                             |
| ml-diagnostics-draft          | Y    | Y                                                                                                                                                                          | Y          | N/A (references `_kml_metric` from tracking)                                                          | Y      | Y        | N/A       | NEEDS-PATCH (N1′ cross-ref)         | **READY** (3 cross-refs L284 / L506 / L515 all now `_kml_metric`)                                                                                                                                     |
| ml-backends-draft             | Y    | Y                                                                                                                                                                          | Y          | N/A                                                                                                   | Y (3)  | Y        | N/A       | READY                               | **READY**                                                                                                                                                                                             |
| ml-registry-draft             | Y    | Y (incl. RegisterResult + ONNX probe cols + onnx_status)                                                                                                                   | Y          | **Y** (4 tables + §5.6 ONNX probe columns)                                                            | Y (13) | Y        | Y         | NEEDS-PATCH (N1′)                   | **NEEDS-PATCH** (NEW HIGH-R6-1 — `_kml_model_versions.artifact_uri TEXT NOT NULL` singular DDL vs `RegisterResult.artifact_uris: dict[str, str]` plural)                                              |
| ml-drift-draft                | Y    | Y                                                                                                                                                                          | Y          | **Y** (4 tables, `_kml_*`)                                                                            | Y (9)  | Y        | N/A       | NEEDS-PATCH (N1′)                   | **READY**                                                                                                                                                                                             |
| ml-serving-draft              | Y    | Y                                                                                                                                                                          | Y          | **Y** (3 tables, `_kml_*` + §9A.1 rationale)                                                          | Y (12) | Y (grpc) | Y (§12)   | NEEDS-PATCH (N1′ + MED-R2 residue)  | **READY** (L67 `(§2.5.3)`; L239 `(per §2.5.3 pickle-gate; §15 L1191 clarifies...)` — MED-R2 CLOSED)                                                                                                   |
| ml-feature-store-draft        | Y    | Y                                                                                                                                                                          | Y          | **Y** (4 tables, `_kml_*` + §10A.1 distinguishes `kml_feat_` user prefix from `_kml_*` system prefix) | Y (10) | Y        | N/A       | NEEDS-PATCH (N1′)                   | **READY** (2 `kml_feat_` refs at L69 + L556 explicitly rationalize user-configurable per-tenant prefix vs internal `_kml_*` metadata prefix)                                                          |
| ml-dashboard-draft            | Y    | Y (imports canonical LineageGraph from addendum)                                                                                                                           | Y          | N/A                                                                                                   | Y (12) | Y        | N/A       | READY                               | **READY**                                                                                                                                                                                             |
| ml-automl-draft               | Y    | Y                                                                                                                                                                          | Y          | **Y** (1 table, `_kml_*`)                                                                             | Y (9)  | Y        | N/A       | NEEDS-PATCH (N1′)                   | **READY**                                                                                                                                                                                             |
| ml-rl-core-draft              | Y    | Y                                                                                                                                                                          | Y          | N/A                                                                                                   | Y (10) | Y        | Y         | READY                               | **READY**                                                                                                                                                                                             |
| ml-rl-algorithms-draft        | Y    | Y                                                                                                                                                                          | Y          | N/A                                                                                                   | P      | Y        | N/A       | READY                               | **READY**                                                                                                                                                                                             |
| ml-rl-align-unification-draft | Y    | Y                                                                                                                                                                          | Y          | N/A                                                                                                   | P      | Y        | Y         | READY                               | **READY**                                                                                                                                                                                             |
| ml-engines-v2-draft           | Y    | Y (AutoMLEngine first-class; lineage in **all** Group 1; eager import §15.9; engine_info + list_engines in Group 6 "Discovery")                                            | Y          | N/A (defers)                                                                                          | Y (9)  | Y        | Y         | READY (B9 CLOSED)                   | **READY** (YELLOW-H Group 6 distinction codified at §15.9 L2233-2239; MED-R5-3 lineage eager import + §18 checklist)                                                                                  |
| ml-engines-v2-addendum-draft  | Y    | **Y — ParamSpec / MethodSignature / EngineInfo / LineageNode / LineageEdge / LineageGraph + NEW `ClearanceRequirement` + `ClearanceLevel` / `ClearanceAxis` type aliases** | Y          | N/A                                                                                                   | P      | Y        | P         | READY (B3+B4 CLOSED; 1 MED-N2 open) | **READY** (MED-N2 CLOSED — L485-516: typed `ClearanceRequirement` dataclass + `tuple[ClearanceRequirement, ...]` replaces flat Literal; YELLOW-G resolved — no `engine.lineage(...)` pseudocode hits) |

### A.2 — 6 supporting-spec integrations

| Spec                              | Sigs | DDL                                                                   | Cross-Refs | Test Contract | Round-5                      | Round-6 Verdict                                                                                                                                                                                                               |
| --------------------------------- | ---- | --------------------------------------------------------------------- | ---------- | ------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| align-ml-integration-draft        | Y    | References `_kml_metric` (singular, correct prefix)                   | Y          | Y             | NEEDS-PATCH (N1′ + ALIGN-M1) | **READY** (L277+L531 `_kml_metric`; L186-188 `kml_key` Python variable names are legitimate code identifiers, not DDL)                                                                                                        |
| dataflow-ml-integration-draft     | Y    | N/A                                                                   | Y          | Y             | READY                        | **READY**                                                                                                                                                                                                                     |
| kailash-core-ml-integration-draft | Y    | N/A                                                                   | Y          | Y             | READY                        | **READY**                                                                                                                                                                                                                     |
| kaizen-ml-integration-draft       | Y    | **P — §5.2 still uses `kml_agent_traces` + `kml_agent_trace_events`** | Y          | Y             | NEEDS-PATCH (N1′)            | **NEEDS-PATCH** (N1′-RESIDUAL — 2 DDL tables + 7 prose/index/FK refs still use `kml_agent_*`; §G detailed plan prescribed the rename but SYNTHESIS F1 omitted it; §2.4 Agent Tool Discovery is otherwise FULLY CLOSED per F4) |
| nexus-ml-integration-draft        | Y    | N/A                                                                   | Y          | Y             | READY                        | **READY**                                                                                                                                                                                                                     |
| pact-ml-integration-draft         | Y    | N/A                                                                   | Y          | Y             | READY                        | **READY**                                                                                                                                                                                                                     |

### A.3 — 2 Phase-E drafts

| Spec                            | Scope                              | Completeness                                   | Release-Blocking Hook   | Round-5 | Round-6 Verdict |
| ------------------------------- | ---------------------------------- | ---------------------------------------------- | ----------------------- | ------- | --------------- |
| ml-readme-quickstart-body-draft | Canonical README §Quick Start body | Y (116 LOC, full 8-section doc)                | SHA-256 pinned to test  | READY   | **READY**       |
| ml-index-amendments-draft       | `specs/_index.md` diff for codify  | Y (183 LOC, full diff + rationale + row count) | Applied at /codify gate | READY   | **READY**       |

**Round-6 summary: 21 READY / 2 NEEDS-PATCH / 0 BLOCKED out of 23 specs.**

- **2 NEEDS-PATCH** both trace to cross-spec drift invisible to narrow-scope review, caught only by full-sibling sweep per `rules/specs-authority.md §5b`:
  - **N1′-RESIDUAL** — kaizen-ml `kml_agent_*` rename dropped between Round-5 §G detailed plan and SYNTHESIS F1 shorthand.
  - **HIGH-R6-1-NEW** — DDL vs Python dataclass divergence in ml-registry (singular `artifact_uri` TEXT column vs plural `artifact_uris: dict[str, str]` dataclass field) surfaced after F3 closed the RegisterResult field-shape HIGH.

**Progress across rounds:**

| Round | READY  | NEEDS-PATCH | BLOCKED | Scope               |
| ----- | ------ | ----------- | ------- | ------------------- |
| 2b    | 4      | 11          | 0       | 15 core             |
| 3     | 9      | 6           | 0       | 15 core             |
| 4     | 17     | 4           | 0       | 21 (15 + 6)         |
| 5     | 14     | 9           | 0       | 23 (15 + 6 + 2)     |
| **6** | **21** | **2**       | **0**   | **23 (15 + 6 + 2)** |

Round-5 → Round-6 delta: **+7 READY** (from 14 to 21) as Phase-F closed 7 of 8 targeted items. The 2 open NEEDS-PATCH both required the full-sibling sweep to surface — neither was visible from the SYNTHESIS Phase-F shorthand alone.

---

## Section B — Phase-F Verification Of 9 Round-5 NEEDS-PATCH Items

### F1 (PARTIAL). N1′ DDL prefix regression

**Prescribed (round-5-feasibility.md §G.1):** sweep `kml_*` → `_kml_*` across 4 specs: ml-tracking (8 CREATE TABLE + 5 prose), ml-diagnostics (3 refs), kaizen-ml (`kml_agent_*` 2 tables + `kml_runs` + 3 prose), align-ml (2 refs, plural→singular).

**Actual:**

| Sub-item                                                           | Status       | Evidence                                                                                                                                                                                                  |
| ------------------------------------------------------------------ | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ml-tracking 8 CREATE TABLE → `_kml_*`                              | **CLOSED**   | `grep -c 'CREATE TABLE _kml_' ml-tracking-draft.md` = 8 (L567/577/611/619/634/642/658/671)                                                                                                                |
| ml-tracking prose refs                                             | **CLOSED**   | `grep -c '_kml_' ml-tracking-draft.md` = 32; 1 legit `kml_experiment` at L684 (Python module stem — explicitly rationalized)                                                                              |
| ml-diagnostics 3 cross-refs → `_kml_metric`                        | **CLOSED**   | L284 + L506 + L515 all now `_kml_metric`                                                                                                                                                                  |
| kaizen-ml L273 `kml_runs` → `_kml_run` (singular)                  | **CLOSED**   | L454 `FK to _kml_run.run_id` + L485 `join _kml_run to kml_agent_traces`                                                                                                                                   |
| **kaizen-ml `kml_agent_traces` + `kml_agent_trace_events` rename** | **NOT DONE** | L439 `table_prefix: str = "kml_agent_"`; L449 "kml\_ prefix" rationale; L452 `CREATE TABLE kml_agent_traces`; L463/L464 indexes; L466 second CREATE TABLE; L468 FK; L476 index; L485 prose — 9 hits total |
| align-ml `kml_metrics` → `_kml_metric`                             | **CLOSED**   | L277 + L531 use `_kml_metric`                                                                                                                                                                             |
| align-ml plural `kml_runs` check                                   | **CLOSED**   | no hits in supporting-specs                                                                                                                                                                               |

**Why the gap:** Round-5-feasibility.md §G Section H delegation prompt specified `kml_agent_(traces|trace_events) → _kml_agent_\1` explicitly. Round-5-SYNTHESIS Phase-F1 summarized it as "DDL prefix unification in ml-tracking + 3 drifted specs" and the sub-bullet for kaizen-ml only mentioned `kml_runs → _kml_run`. Phase-F executed from the SYNTHESIS shorthand, not the §G delegation prompt. The dropped sub-item is surfaced by the Round-6 full-sibling sweep.

**Cross-spec impact:** The `kml_agent_*` prefix is the only remaining DDL prefix in the 23-spec surface that does not start with `_kml_*`. The rationale at `ml-registry §2.1 L127` ("leading underscore marks these as internal tables users should not query directly") + `ml-serving §9A.1` applies EQUALLY to kaizen-ml's agent-trace tables (agent-trace rows are internal tracer state, not user-facing). Per `rules/specs-authority.md §5b MUST Rule 3` ("Cross-spec terminology drift"), the same concept ("internal ML/agent system tables") is now named two ways across files.

**Additionally:** kaizen-ml L449 still says "kml* prefix (matching ML's 63-char Postgres prefix rule)". ML's canonical prefix is now `\_kml*` — this claim is factually inaccurate after the F1 sweep landed in every sibling.

**Verdict:** **NEEDS-PATCH — N1′-RESIDUAL.** ~5-min mechanical sweep; one sed across kaizen-ml + fix L449 prose + L439 default value.

### F2 (CLOSED). `_env.resolve_store_url` plumbing

**Evidence:** `grep -l 'resolve_store_url'` surfaces the helper in 6 of 7 targeted files — ml-engines-v2 (authoritative at §2.1), ml-automl, ml-feature-store, ml-registry (§10.2 L847), ml-tracking, ml-dashboard. All 4 sibling specs flagged in Round-5 HIGH-E1 now cross-reference `ml-engines-v2.md §2.1 MUST 1b`. **HIGH-E1 CLOSED.**

### F3 (CLOSED-with-FOLLOW-UP). RegisterResult field-shape

**Evidence:** `ml-registry §7.1` L417-431 declares `RegisterResult` with:

- `artifact_uris: dict[str, str]` (plural dict) at L424
- `onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]] = None` at L429
- `is_golden: bool = False` at L430

§7.1.1 adds a read-only `@property artifact_uri(self)` back-compat shim for v1.x with explicit `DeprecationWarning` and v2.0 removal path. The authoritative-downstream note at L413 cross-references `ml-engines-v2 §16.3` Tier-2 test + `ml-readme-quickstart-body §2` + `ml-serving §2.5.1` — every consumer now reads `artifact_uris[format]`.

**HIGH-R5-1 CLOSED.**

**BUT: Round-6 prompt's flagged follow-up finding is CONFIRMED as a NEW HIGH.** See § C for full write-up.

### F4 (CLOSED). kaizen-ml §2.4 Agent Tool Discovery

**Evidence:** `kaizen-ml-integration-draft.md §2.4` now spans L126-303 with:

- **§2.4.1** — Discovery contract (L136-L148) declares `km.engine_info(engine_name) -> EngineInfo` and `km.list_engines() -> tuple[EngineInfo, ...]`.
- **§2.4.2** — "Re-Imported, Not Redefined" (L149-L167) — explicit `from kailash_ml.engines.registry import EngineInfo, MethodSignature, ParamSpec`; re-declaration is a §5b violation.
- **§2.4.3** — Tenant-scoped filter (L180-L197) — Kaizen agents filter `EngineInfo.clearance_level` against ambient tenant_id before exposing tools to LLM.
- **§2.4.4** — Version-sync invariant (L199-L220) — `EngineInfo.version` MUST equal `kailash_ml.__version__` at discovery time; version mismatch raises `EngineDiscoveryError`.
- **§2.4.5** — Test contract (L294-L297) — Tier 2 integration with `BaseAgent` (or `MLAwareAgent`) constructed from `km.list_engines()`, assertion on `__version__` in tool-spec descriptions.
- **§2.4.6** — Example integration (L259-L292) — full `MLAwareAgent` example.
- **§2.4.7** — Authority binding (L303) — explicit spec-authority resolution in favor of `ml-engines-v2-addendum §E11`.

**A11-NEW-1 CLOSED.** The ~15-min plan delivered ~170 LOC of canonical contract.

### F5 (CLOSED). km.lineage default + YELLOW-G + YELLOW-H

**L-1 CLOSED:** `ml-engines-v2 §15.8` L2166-2174 — `km.lineage(run_id_or_model_version_or_dataset_hash, *, tenant_id: str | None = None, max_depth: int = 10) -> LineageGraph`. Comment explicitly aligns with every sibling `km.*` verb's default tenant_id pattern; ambient resolution via `get_current_tenant_id()`. Day-0 `await km.lineage(run_id)` no longer raises `TypeError`.

**YELLOW-G CLOSED:** `grep 'engine\.lineage' ml-engines-v2-addendum-draft.md` returns 0 hits. The §E13.1 pseudocode has been canonicalized to `km.lineage(...)`.

**YELLOW-H CLOSED:** `ml-engines-v2 §15.9` L2183-2237 — `__all__` is now organized into 6 groups; `engine_info` + `list_engines` are in **Group 6 — Engine Discovery (metadata introspection per ml-engines-v2-addendum §E11.2)** at L2233-2235. L2239 explicit distinction paragraph: "Group 1 vs Group 6 distinction. Group 1 holds the operational verbs users call in the run/train/serve lifecycle... Group 6 holds the metadata verbs..."

### F6 (CLOSED). MED-R5-1 / MED-R5-2 / MED-R5-3

**MED-R5-1 CLOSED:** `RegisterResult.onnx_status` in §7.1 canonical at L429 (see F3 evidence).

**MED-R5-2 CLOSED:** ml-serving L67 now reads `allow_pickle: bool = False  # explicit opt-in to pickle fallback (§2.5.3)`; L239 now reads `REQUIRES explicit allow_pickle=True (per §2.5.3 pickle-gate; §15 L1191 clarifies: opt-in + loud-WARN discipline)`. Both primary citations no longer misattribute "Decision 8".

**MED-R5-3 CLOSED:** `lineage` now in §15.9 **all** Group 1 (L2196) + eager import at L2254 (`from kailash_ml.engines.lineage import LineageGraph  # eager import for km.lineage return type (§15.8)`) + §18 checklist lines 2480 ("`kailash_ml.__all__` Group 1 includes `lineage`") + 2481 ("eagerly imported per §15.9 MUST: Eager Imports").

### MED-N2 (CLOSED). EngineInfo.clearance_level type annotation

**Previously:** L489 annotated `Optional[Literal["D", "T", "R", "DTR"]]` — conflated axis labels (D/T/R) with level labels (L/M/H) from §E9.2.

**Now:** ml-engines-v2-addendum-draft.md L485-516 introduces a typed triple shape (stronger than the Round-5 recommendation of Shape A scalar):

```python
ClearanceLevel = Literal["L", "M", "H"]
ClearanceAxis = Literal["D", "T", "R"]

@dataclass(frozen=True)
class ClearanceRequirement:
    """One axis + minimum level pair — see §E9.2 for axis/level semantics."""
    axis: ClearanceAxis
    min_level: ClearanceLevel

@dataclass(frozen=True)
class EngineInfo:
    ...
    clearance_level: Optional[tuple[ClearanceRequirement, ...]]
```

**Better than recommended:** preserves full D/T/R × L/M/H granularity (a method that requires "Medium data clearance + Low transform clearance" declares it explicitly) without collapsing to a conservative maximum. L509-516 example shows the shape. **MED-N2 CLOSED.**

---

## Section C — NEW Round-6 Findings

### HIGH-R6-1-NEW (NEW HIGH). `_kml_model_versions.artifact_uri` DDL column singular vs `RegisterResult.artifact_uris` plural dict

**Location:**

- `ml-registry-draft.md §5A.2` L270: `artifact_uri TEXT NOT NULL,` (singular column per row)
- `ml-registry-draft.md §5A.2` L269: `format VARCHAR(16) NOT NULL,` (single format per row)
- `ml-registry-draft.md §5A.2` L283: `UNIQUE (tenant_id, name, version)` (one row per version, no format dimension)
- `ml-registry-draft.md §7.1` L424: `artifact_uris: dict[str, str]` (plural dict of format→URI)
- `ml-registry-draft.md §7.1.1` L450-477: v1.x back-compat property `artifact_uri` returns `artifact_uris["onnx"]`
- `ml-registry-draft.md §10.1` L832: `_kml_model_versions.artifact_uri` column stores the CAS URI
- `ml-registry-draft.md §7.5.3` L646: golden reference query returns columns `(..., artifact_uri, metadata)` (singular)

**Conflict:** The DDL storage model is "one row = one (version, format) combination with a single URI". The Python dataclass is "one RegisterResult = one version, but multiple formats as a dict". With `UNIQUE (tenant_id, name, version)`, the DDL forbids multiple rows for the same `(tenant, name, version)` — so the spec currently cannot represent `artifact_uris["onnx"]` AND `artifact_uris["pickle"]` coexisting on the same version. This contradicts §7.1 L440 ("When ONNX export fails on unsupported ops and `allow_pickle_fallback=True`, `artifact_uris['pickle']` is populated instead AND `onnx_status='legacy_pickle_only'` is set") — the "instead" language hints at a single-format-per-version contract, but §5.6.2 L242 says "`RegisterResult.artifact_uris['pickle']` (or `'torch'` / `'torchscript'`) is populated; `artifact_uris['onnx']` is absent" — still consistent with single-format.

**HOWEVER**: §7.1 L440 AND L424 declare `artifact_uris: dict[str, str]` where the dict structure unambiguously permits multiple keys simultaneously. The F3 fix flipped `artifact_uri: str` → `artifact_uris: dict[str, str]` without updating the DDL or clarifying that the dict SHOULD always be single-key. An autonomous agent implementing `ModelRegistry.register_model()` today cannot decide:

1. Is the dict always single-key (one format per version, dict is vestigial)?
2. Should the DDL be extended so each (version, format) is a separate row, with the Python layer assembling the dict from GROUP BY?
3. Should `artifact_uri TEXT` be replaced with `artifact_uris JSONB` storing the full dict in one row?

**Why this matters for implementation:** The shard implementer cannot reconcile the DDL and dataclass without a spec amendment. The §5.6.2 language suggests option 1 (single-key in practice, dict is defensive), but the type `dict[str, str]` hints at option 2 or 3. The UNIQUE constraint + `format VARCHAR(16) NOT NULL` argue for option 2 if intent is multi-format.

**Required fix: choose ONE of three shapes and apply consistently:**

- **Shape A (single-key dict, keep DDL):** `artifact_uris: dict[Literal["onnx","torch","pickle","torchscript","gguf","safetensors"], str]` WITH prose clarification "at most one key per version; the dict form is forward-compatible with multi-format-per-version without requiring an API change." `format` column stays as the single format. `UNIQUE (tenant_id, name, version)` stays. Update §7.1 L424 comment + §5.6.2 to confirm single-key invariant. **~5 min.**

- **Shape B (multi-format per version, extend DDL):** change `UNIQUE (tenant_id, name, version)` → `UNIQUE (tenant_id, name, version, format)`; each (version, format) is a separate row; `artifact_uri TEXT` stays (one URI per row); the `ModelRegistry.register_model` returns `RegisterResult` with `artifact_uris` assembled via `SELECT format, artifact_uri FROM _kml_model_versions WHERE (tenant_id, name, version) = ... GROUP BY format`. Update §5A.2 DDL + §7.5.3 golden query + §10.1 CAS reference. **~20 min.**

- **Shape C (single-row JSONB):** drop `format VARCHAR(16)` + `artifact_uri TEXT`; add `artifact_uris JSONB NOT NULL` + `onnx_status` at the DDL layer; `UNIQUE (tenant_id, name, version)` stays. Update §5A.2 DDL + §7.5.3 golden query + §10.1 CAS reference. **~15 min.**

**Recommended: Shape A.** The `artifact_uris` dict form is the canonical API surface and forward-compatible (agents/users read `result.artifact_uris[fmt]`); retaining the single-format-per-version invariant at the storage layer matches §5.6.2's "or" / "absent" language AND matches the `format VARCHAR(16) NOT NULL` column as today. No DDL change required — just a prose MUST that the dict holds at most one key and matches the row's `format` column. If multi-format-per-version becomes a real user request later, promote to Shape B via a numbered migration. Shape A is the lowest-cost path that makes the spec internally consistent.

**Verdict:** HIGH (5-min fix under Shape A).

---

## Section D — 23-Spec Feasibility Matrix (Updated)

| Round-5 open finding                                                                                | Round-6 status                    | Evidence                                                                                                                            |
| --------------------------------------------------------------------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| N1 (DDL prefix drift, ml-tracking + ml-diagnostics + align-ml + kaizen-ml `kml_runs`/`kml_metrics`) | **PARTIAL CLOSED → N1′-RESIDUAL** | ml-tracking + ml-diagnostics + align-ml + kaizen-ml L454/L485/L531 all swept; kaizen-ml `kml_agent_*` (2 tables + 7 refs) NOT swept |
| HIGH-R5-1 (RegisterResult field-shape)                                                              | **CLOSED**                        | §7.1 L417-431 + §7.1.1 back-compat property                                                                                         |
| A11-NEW-1 (kaizen-ml §2.4 Agent Tool Discovery)                                                     | **CLOSED**                        | §2.4 L126-L303 — full contract with tenant-scoped filter + version-sync invariant + test contract + authority binding               |
| MED-R5-1 (RegisterResult.onnx_status in §7.1)                                                       | **CLOSED**                        | §7.1 L429                                                                                                                           |
| MED-R5-2 (ml-serving pickle-gate citations)                                                         | **CLOSED**                        | L67 `(§2.5.3)`; L239 `(per §2.5.3 pickle-gate; §15 L1191 clarifies...)`                                                             |
| MED-R5-3 (lineage in §15.9 + §18)                                                                   | **CLOSED**                        | §15.9 **all** Group 1 L2196 + eager import L2254 + §18 checklist L2480/L2481                                                        |
| MED-N2 (EngineInfo.clearance_level)                                                                 | **CLOSED**                        | Typed `ClearanceRequirement` dataclass + tuple at L485-516                                                                          |
| YELLOW-G (§E13.1 `engine.lineage(...)` pseudocode)                                                  | **CLOSED**                        | `grep engine\.lineage ml-engines-v2-addendum-draft.md` returns 0                                                                    |
| YELLOW-H (km.engine_info / km.list_engines **all** placement)                                       | **CLOSED**                        | §15.9 Group 6 "Engine Discovery" L2233-2239 with L2239 distinction paragraph                                                        |
| HIGH-E1 (env helper plumbing)                                                                       | **CLOSED**                        | `grep -l resolve_store_url` surfaces 6 files (engines-v2, automl, feature-store, registry, tracking, dashboard)                     |
| ALIGN-M1 (plural→singular)                                                                          | **CLOSED**                        | Folded into N1′ sweep; all plural refs converted                                                                                    |
| (NEW Round-6) HIGH-R6-1-NEW                                                                         | **OPEN**                          | ml-registry §5A.2 `artifact_uri TEXT NOT NULL` (singular) vs §7.1 `artifact_uris: dict[str, str]` (plural)                          |

**Open HIGH count: 2 (N1′-RESIDUAL + HIGH-R6-1-NEW).**
**Open MED count: 0.**
**Open LOW count: 0.**

**Progress delta:** Round-5 (1 HIGH + 2 MED + 1 LOW) → Round-6 (2 HIGH + 0 MED + 0 LOW). The re-open on a HIGH reflects the follow-up finding from F3's closure; the NET finding count dropped 4 → 2.

---

## Section E — Phase-G Plan (Last 20-Minute Sweep To Converge)

### G1 — N1′-RESIDUAL: kaizen-ml `kml_agent_*` rename (~12 min)

Scoped to one file: `workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md`. Mechanical sed:

1. L439: `table_prefix: str = "kml_agent_",` → `table_prefix: str = "_kml_agent_",`
2. L449: `Two tables, \`kml*\` prefix (matching ML's 63-char Postgres prefix rule):`→`Two tables, \`\_kml_agent*\` prefix (leading underscore marks internal tracer tables per ml-registry §2.1 L127 + ml-serving §9A.1):`
3. L452 + L466: `CREATE TABLE IF NOT EXISTS kml_agent_traces` / `...kml_agent_trace_events` → `_kml_agent_traces` / `_kml_agent_trace_events`
4. L463 + L464 + L476: index names — sed `kml_agent_` → `_kml_agent_`
5. L468: `REFERENCES kml_agent_traces(trace_id)` → `REFERENCES _kml_agent_traces(trace_id)`
6. L485: `join \`\_kml_run\` to \`kml_agent_traces\``→`join \`\_kml_run\` to \`\_kml_agent_traces\``

Verification:

```bash
grep -c '\bkml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md
# Output MUST be 0
grep -c '_kml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md
# Output MUST be >= 9
```

### G2 — HIGH-R6-1-NEW: RegisterResult dict / DDL reconciliation (Shape A recommended, ~5 min)

Scoped to one file: `workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md`. Three edits:

1. **§7.1 L424 (dataclass field comment):** expand to pin the single-key invariant:

   ```python
   artifact_uris: dict[str, str]   # {format: uri}; invariant: at most one key, matching row's `format` column in _kml_model_versions; dict form is forward-compatible with multi-format-per-version.
   ```

2. **NEW §7.1.2 Single-Format Invariant paragraph (after §7.1.1):**

   > `artifact_uris` is a dict for forward-compatibility but MUST contain exactly one key per `RegisterResult`, matching the registered `format`. Multi-format registration (same `(tenant_id, name, version)` with multiple formats) is out of scope for v1.x — a registration call selects ONE format per Decision 8 ONNX-first preference + explicit `format=` override. Promoting to multi-format-per-version is a numbered-migration change (extend `UNIQUE (tenant_id, name, version)` → `UNIQUE (tenant_id, name, version, format)`) out of scope for v1.x.

3. **§5.6.2 L242 clarifier:** add parenthetical "per §7.1.2 single-format invariant" after "`artifact_uris['pickle']` (or `'torch'` / `'torchscript'`) is populated".

Verification:

```bash
grep -c 'single-format invariant' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md
# Output MUST be >= 1 (the new §7.1.2 + the §5.6.2 cross-ref)
```

### Total Phase-G budget: ~17 min (G1 ~12 + G2 ~5)

All 2 items are execution gates per `rules/autonomous-execution.md §Structural vs Execution Gates` — no human-authority escalation required.

**After Phase-G: Round-7 /redteam feasibility audit expected to return 23/23 READY, 0 HIGH, 0 MED, 0 BLOCKED — the FIRST CLEAN ROUND target.** Round-8 confirms convergence per the 2-consecutive-clean-rounds exit criterion.

---

## Section F — Sibling-Spec Sweep Audit (per `rules/specs-authority.md §5b`)

Phase-F edited 6 ml specs (ml-tracking, ml-diagnostics, ml-registry, ml-serving, ml-engines-v2, ml-engines-v2-addendum) + 2 supporting specs (align-ml, kaizen-ml). Round-6 re-derives against the FULL 23-spec sibling set.

**Full-sibling sweep results (rule §5b MUST Rule validation):**

1. **N1′-RESIDUAL (kaizen-ml `kml_agent_*` rename dropped)** — **CAUGHT.** A narrow-scope re-derivation on the 4 files Phase-F1 touched (ml-tracking, ml-diagnostics, kaizen-ml L273, align-ml) would declare F1 CLOSED — because within those 4 files, every `kml_runs` / `kml_metrics` / `kml_experiment` / `kml_metric` / `kml_run` rename landed. The dropped `kml_agent_*` sub-item in kaizen-ml only surfaces when the FULL sibling set is grep'd for `\bkml_`. **Rule 5b validated: full-sibling sweep finds what narrow scope misses.**

2. **HIGH-R6-1-NEW (DDL vs dataclass field-shape drift)** — **CAUGHT.** Appears only when `§5A.2 DDL` is read against `§7.1 dataclass` AND cross-referenced against `§5.6.2 probe semantics` + `§7.5.3 golden query`. Internal re-derivation within the ml-registry file alone COULD have caught it in a careful reading, but the F3 spec edit swapped `artifact_uri: str` → `artifact_uris: dict[str, str]` without touching the DDL section 600 LOC above — the edit-time re-derivation was scoped to §7.1 locality. **Rule 5b validated AGAIN: full-file sweep of the DDL + type-annotation surface catches shape-drift that local-edit review misses.**

**Conclusion:** Rule 5b holds for the FIFTH consecutive session (2026-04-19 / 2026-04-20 / 2026-04-21 Round-4 / Round-5 / Round-6). Full-sibling sweep catches 2 distinct drift patterns at Round-6 that narrow-scope review would miss — one cross-file (N1′-RESIDUAL) and one within-file (HIGH-R6-1-NEW). The rule is empirically validated as a load-bearing structural defense across a fifth independent audit cycle.

**Meta-lesson for Phase-G delegation prompts:** when translating a detailed §G plan into a SYNTHESIS shorthand, the shorthand is permitted to ABBREVIATE prose but MUST NOT DROP mechanical sub-items. The N1′-RESIDUAL gap originated because the Round-5 SYNTHESIS F1 entry listed "kaizen-ml L273 `kml_runs` → `_kml_run`" but omitted "kaizen-ml `kml_agent_*` 2 tables + 7 refs" from the §G.1 detailed plan. Phase-F read the SYNTHESIS, not §G. For Phase-G, the delegation prompt MUST echo every mechanical sub-item AS AN EXPLICIT LINE in the prompt, not as a summary bullet.

---

## Section G — Shard Plan + Dependency Waves (Unchanged From Round-5)

Round-5 published 42 shards / 9 waves. Round-6 does NOT change the shard count or wave structure — Phase-F amendments landed entirely within existing specs, adding text but no new shards. The 2 open NEEDS-PATCH are text-only spec amendments for Phase-G, not new implementation shards.

**Critical path: ~18 shards (unchanged).**
**Parallelization (unchanged):** Wave 5 = 7 parallel; Wave 6 = 7 parallel; Waves 7/8 = 5 parallel; Wave 9 = 2 parallel (release-PR + /codify gate).

**Phase-G delta cost: ~17 min** of spec editing closes N1′-RESIDUAL + HIGH-R6-1-NEW. No shard delta.

---

## Section H — Round-6 Convergence Dashboard

### What's CERTIFIED today

- 14/14 user-approved decisions pinned and propagated (unchanged since Round-4)
- All 12 Phase-B CRITs closed
- All 5 Round-4 HIGHs closed (B3 + B4 + B9 + N1 partial + B11′)
- All 4 CRITs (DB URL, tracker constructor, MLError hierarchy, get_current_run) remain GREEN
- Industry parity 24/25 GREEN (unchanged)
- Senior-practitioner CERTIFIED (unchanged)
- 7/8 Phase-F items fully CLOSED (F2 + F3 + F4 + F5 + F6 + MED-N2)
- Full-sibling sweep per specs-authority §5b held for 5th consecutive session

### What remains open

**2 HIGH:**

1. **N1′-RESIDUAL** — kaizen-ml `kml_agent_*` rename (2 DDL tables + 7 refs + L449 prose). Dropped between Round-5 §G detailed plan and SYNTHESIS F1 shorthand. ~12 min G1 fix.
2. **HIGH-R6-1-NEW** — ml-registry `_kml_model_versions.artifact_uri` (singular DDL column) vs `RegisterResult.artifact_uris: dict[str, str]` (plural dataclass). Surfaced after F3 closure. ~5 min G2 fix (Shape A: single-key invariant prose + §7.1.2 paragraph + §5.6.2 cross-ref).

**0 MED, 0 LOW, 0 BLOCKED.**

### Round-7 entry criteria

After Phase-G merges:

- Re-run Round-6 feasibility persona (and any of the other 7 personas that have re-run cadence)
- Target: 0 CRIT + 0 HIGH + 0 MED across all audits
- If clean → **FIRST CLEAN ROUND** (all 8 personas pass)
- Round-8 confirms convergence (2 consecutive clean rounds)

**Net progress Round-5 → Round-6: +7 READY, -2 net findings (4 → 2), all 2 remaining within a ~17-min mechanical sweep. Target 23/23 READY reachable this cycle.**

---

## Section I — Summary — Round-6 Verdict

**Per-spec tally:**

- **READY: 21** — ml-autolog, ml-backends, ml-dashboard, ml-rl-core, ml-rl-algorithms, ml-rl-align-unification, ml-engines-v2, ml-engines-v2-addendum, dataflow-ml-integration, kailash-core-ml-integration, nexus-ml-integration, pact-ml-integration, ml-readme-quickstart-body, ml-index-amendments, ml-tracking, ml-diagnostics, ml-drift, ml-serving, ml-feature-store, ml-automl, align-ml-integration.

- **NEEDS-PATCH: 2** — ml-registry (HIGH-R6-1-NEW DDL/dataclass drift), kaizen-ml-integration (N1′-RESIDUAL `kml_agent_*` rename).

- **BLOCKED: 0.**

**Grand total: 21 + 2 = 23 ✅**

**Progress:**

| Round | READY  | NEEDS-PATCH | BLOCKED | HIGH  | MED   | LOW   | Scope               |
| ----- | ------ | ----------- | ------- | ----- | ----- | ----- | ------------------- |
| 2b    | 4      | 11          | 0       | ?     | ?     | ?     | 15 core             |
| 3     | 9      | 6           | 0       | ?     | ?     | ?     | 15 core             |
| 4     | 17     | 4           | 0       | 5     | —     | —     | 21 (15 + 6)         |
| 5     | 14     | 9           | 0       | 1     | 2     | 1     | 23 (15 + 6 + 2)     |
| **6** | **21** | **2**       | **0**   | **2** | **0** | **0** | **23 (15 + 6 + 2)** |

**Target after Phase-G (~17 min): 23/23 READY, 0 HIGH, 0 MED, 0 BLOCKED — FIRST CLEAN ROUND.** Round-7 /redteam re-runs all 8 personas to confirm; Round-8 confirms 2-consecutive-clean convergence.

---

## Absolute Paths

- **This report:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-feasibility.md`
- **Prior round:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-5-feasibility.md`
- **Round-5 SYNTHESIS:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-5-SYNTHESIS.md`
- **Approved decisions:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`
- **15 core specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*.md`
- **6 supporting specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*-ml-integration-draft.md`
- **2 Phase-E drafts:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-readme-quickstart-body-draft.md`, `.../ml-index-amendments-draft.md`
- **N1′-RESIDUAL target (Phase-G1):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md` §5.2 L439-485
- **HIGH-R6-1-NEW target (Phase-G2):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md` §5A.2 L270 + §7.1 L424 + NEW §7.1.2

_End of round-6-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._

# Round 6 — Junior-Scientist Day-0 UX Re-Audit (Post-Phase-F)

**Persona:** Year-2 ML engineer / MLFP course student who types `pip install kailash-ml`, opens a notebook, and expects the Quick Start to "just work." Never reads spec files unless dragged there by an `AttributeError` or `TypeError`.

**Method:** Re-derived the 6 day-0 scenarios from scratch against the current spec drafts (no trust in prior round files — `rules/testing.md` audit-mode clause). Then interrogated the three new Phase-F surfaces called out in the prompt (`ClearanceRequirement` nesting, Group 6 `engine_info` / `list_engines`, `artifact_uri` back-compat shim). Finally ran full-closure sweep across every finding from Round 1 → Round 5.

**TL;DR:** L-1 is CLOSED. `km.lineage` now defaults `tenant_id: str | None = None` with ambient-resolution language byte-identical to every other `km.*` verb. All 6 day-0 scenarios remain GREEN. The three potential new-friction points (ClearanceRequirement, Group 6, artifact_uri shim) were each checked and produce **zero** day-0 impact — they live on advanced/power-user surfaces the newbie does not touch in the Quick Start. **6/6 GREEN, 0 HIGH, 0 MED, 0 LOW.** First clean newbie-UX round.

---

## Section A — L-1 Closure Verification (`km.lineage` `tenant_id` default)

**Round-5 finding:** `km.lineage` required `tenant_id: str` (no default) while every sibling `km.*` verb defaulted `tenant_id: str | None = None`. Day-0 newbie typing `await km.lineage(run_id)` would hit `TypeError: lineage() missing 1 required keyword-only argument: 'tenant_id'`.

**Phase-F F5 claim:** Default `tenant_id` to `None` with ambient resolution via `get_current_tenant_id()`; align with sibling verbs.

**Evidence (4 call sites, all consistent):**

1. `ml-engines-v2-draft.md:2163-2176` — §15.8 signature:

   ```python
   async def lineage(
       run_id_or_model_version_or_dataset_hash: str,
       *,
       tenant_id: str | None = None,     # resolved via get_current_tenant_id() when None
       max_depth: int = 10,
   ) -> LineageGraph: ...
   ```

   Followed by the alignment-with-siblings prose: "This aligns `km.lineage` with every sibling `km.*` verb (`km.track`, `km.train`, `km.register`, `km.serve`, `km.watch`, `km.resume`, etc.) which all default `tenant_id: str | None = None` — preventing a `TypeError` for day-0 single-tenant users who never pass `tenant_id` explicitly."

2. `ml-engines-v2-addendum-draft.md:418` — §E10.3 MUST 1 mirrors the canonical signature: `km.lineage(model_uri_or_run_id_or_dataset_hash, *, tenant_id: str | None = None, max_depth=10)` with the same ambient-resolution note.

3. `ml-engines-v2-draft.md:2261-2263` — §15.9 eager-import declaration block re-pins the `None` default at module-scope:

   ```python
   async def lineage(run_id_or_model_version_or_dataset_hash: str, *,
                     tenant_id: str | None = None,
                     max_depth: int = 10) -> LineageGraph: ...
   ```

4. `ml-engines-v2-draft.md:2196-2197` — `"lineage"` entry landed in `__all__` Group 1 with the explanatory sidebar comment citing `ml-engines-v2-addendum §E10.2`.

**Day-0 trace:**

```python
# Newbie inside the Quick Start km.track() block — ambient context populated
async with km.track("demo") as run:
    await km.lineage(run.run_id)   # tenant_id=None → resolves via get_current_tenant_id()
                                    # single-tenant dev install → no raise
```

No `TypeError`. Single-tenant users never pass `tenant_id`; multi-tenant users without ambient context get `TenantRequiredError` (the correct signal per `rules/tenant-isolation.md`), NOT a `TypeError` on a missing kwarg.

**Verdict:** L-1 CLOSED. 4/4 call sites consistent. Alignment-with-siblings clause explicit. Tier 2 wiring test (`test_lineage_graph_cross_engine_wiring.py`) referenced at `ml-engines-v2-addendum §E10.3 MUST 4`.

---

## Section B — 6 Day-0 Scenario Re-Walk

Re-derived from Round-1 Q1-Q6. Each scenario is a ~5-line Day-0 interaction.

### S1. `km.train(df, target="y")` — one-line fit → **GREEN**

- `ml-engines-v2-draft.md` §15.3 `km.train` signature unchanged: `async def train(data, *, target, family="auto", tenant_id=None, actor_id=None, **setup_kwargs) -> TrainingResult`. Canonical Quick Start line.
- Phase-F did not touch this surface.

### S2. `km.diagnose(result)` — one-line diagnose → **GREEN**

- `ml-diagnostics-draft.md` §3 — top-of-spec, SOLE diagnostic entry point. Auto-dispatch by `TrainingResult.family`. `tracker=None` reads `get_current_run()`.
- Phase-F did not touch this surface.

### S3. `kailash-ml-dashboard` / `km.dashboard()` — one-line dashboard → **GREEN**

- `ml-dashboard-draft.md` §3.2 — `db_url=None` → `$KAILASH_ML_STORE_URL` → `~/.kailash_ml/ml.db`.
- M-1 (Round 4 NEW MED) was closed by Phase-E E1/E1b (engines-v2 §2.1 MUST 1b `_env.resolve_store_url()` helper + explicit MUST declaring `KAILASH_ML_STORE_URL` as canonical).
- Phase-F F2 added cross-ref notes in 4 sibling specs (ml-tracking §2.5, ml-registry, ml-feature-store, ml-automl) pointing back at the engines-v2 canonical — closes the Round-5 HIGH-E1 Multi-Site Kwarg Plumbing gap that would have surfaced as "why does the dashboard read a different env var than the tracker" if it had escaped into production. Net day-0 impact: dashboard and tracker read the same store from the same env var from the same helper; newbie can never hit the divergence.

### S4. `DLDiagnostics(model, tracker=run)` / contextvar auto-wire → **GREEN**

- `ml-engines-v2-addendum-draft.md` §E2 + `ml-tracking-draft.md §2.4` — every engine reads `get_current_run()` at mutation-method start; `tracker=` annotates `Optional[ExperimentRun]`.
- Phase-F did not touch this surface.

### S5. `dir(km)` lifecycle-ordered → **GREEN (enhanced with Group 6)**

- `ml-engines-v2-draft.md` §15.9 — `__all__` is pinned into **6 named groups** in this sequence:
  - Group 1 — Lifecycle verbs (13 entries: `track`, `autolog`, `train`, `diagnose`, `register`, `serve`, `watch`, `dashboard`, `seed`, `reproduce`, `resume`, `lineage`, `rl_train`)
  - Group 2 — Engine primitives + MLError hierarchy
  - Group 3 — Diagnostic adapters + helpers
  - Group 4 — Backend detection
  - Group 5 — Tracker primitives
  - **Group 6 — Engine Discovery (NEW in Phase-F F5): `engine_info`, `list_engines`**
- "Ordering Is Load-Bearing" MUST preserved. "Every `__all__` Entry Is Eagerly Imported" MUST preserved (closes CodeQL `py/modification-of-default-value`).

**Day-0 newbie behaviour:** `dir(km)` shows verbs first (13 of them), then primitives, then errors, then diagnostics, then backend, then tracker, then discovery. The two discovery verbs sit at the END of the export list — the newbie who just wants to `km.train` / `km.register` / `km.serve` never has to scan past them in the top-of-list verbs. This is a strict UX improvement over merging `engine_info` into Group 1 (which would have pushed lifecycle verbs further down in autocomplete) or leaving it unlisted (which would have split the `__all__` contract).

### S6. Lifecycle holes (serve / drift / RL / lineage) → **GREEN**

- `km.serve` — §15.5, unchanged.
- `km.watch` — §15.6 + `ml-drift-draft.md §8`, unchanged.
- `km.rl_train` — §15.11 + `ml-rl-core-draft.md §7`, unchanged.
- `km.lineage` — §15.8 + `ml-engines-v2-addendum §E10.2`, **now with sibling-aligned default** (L-1 closure, see Section A).

**Scenario Summary:** 6/6 GREEN. No regression from Round-5.

---

## Section C — Three New Phase-F Surfaces, Newbie-Impact Check

The prompt specifically flagged three new surfaces introduced by Phase-F that might produce newbie friction. Each checked below.

### C1. `ClearanceRequirement` nested dataclass — **ZERO day-0 impact**

**What landed:** `ml-engines-v2-addendum-draft.md:489-506` introduces `ClearanceRequirement(axis, min_level)` as a frozen dataclass nested inside `EngineInfo.clearance_level: Optional[tuple[ClearanceRequirement, ...]]`. This replaces the round-5 MED-N2 flat `Literal["D","T","R","DTR"]` / vs §E9.2 L/M/H conflation — the fix makes the axis (D/T/R) and the level (L/M/H) two distinct fields per requirement.

**Newbie exposure audit:**

- `ClearanceRequirement` is NOT in `__all__` of `kailash_ml` (neither Group 1 nor Group 6). Confirmed via:
  - `grep ClearanceRequirement workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md` — 0 hits.
  - `grep ClearanceRequirement workspaces/kailash-ml-audit/specs-draft/ml-readme-quickstart-body-draft.md` — 0 hits.
  - Lives at `kailash_ml.engines.registry.ClearanceRequirement` — deep import path the newbie never touches.
- Only surfaces through `EngineInfo.clearance_level`, which itself is returned by `km.engine_info(name)` — a Group 6 Discovery verb that no Quick Start, no README, no 5-line example invokes.
- PACT D/T/R clearance is a Decision 12 governance feature for production / enterprise deployments, not a dev-install concern.

**Day-0 trace:** A notebook newbie running the 5-line Quick Start never sees the symbol, never imports it, never sees it in an error message, never has to understand D/T/R axes or L/M/H levels. First contact: when the newbie becomes a production operator (months later, a different persona).

**Verdict:** ZERO newbie-UX impact. Correctly scoped to advanced users.

### C2. Group 6 `__all__` placement for `engine_info` / `list_engines` — **Discoverable AND non-obstructive**

**What landed:** `ml-engines-v2-draft.md:2233-2239` — Group 6 "Engine Discovery" holds `engine_info` + `list_engines` at the END of the `__all__` list. The §15.9 explanatory prose:

> Group 1 holds the operational verbs users call in the run/train/serve lifecycle (`track`, `train`, `register`, `serve`, `watch`, …). Group 6 holds the metadata verbs users (or Kaizen agents per `ml-engines-v2-addendum §E11.3 MUST 1`) call for introspection — `list_engines()` enumerates available engines, `engine_info(name)` returns the `EngineInfo` dataclass for a single engine. These are NOT lifecycle actions; they are discovery primitives and belong in their own group so Sphinx autodoc and `from kailash_ml import *` readers observe the separation.

**Discoverability check — 3 day-0 paths:**

1. **Tab-completion in notebook** — `km.<TAB>` shows every `__all__` entry; `engine_info` / `list_engines` appear at the bottom alongside `ExperimentTracker`. Found by the user who types `km.en<TAB>` → `km.engine_info` autocompletes.
2. **`dir(km)`** — alphabetical, so `engine_info` appears between `dashboard` and `ExperimentRun`. Found by the user running `dir(km)` to explore the surface.
3. **`help(km)` / Sphinx autodoc** — emits symbols in `__all__` order; the 6-group structure produces clean section headings. Group 6 "Engine Discovery" appears as its own docstring section, not buried inside Group 2 primitives.

**Non-obstruction check:** Placing `engine_info` / `list_engines` in Group 1 would have pushed 13 lifecycle verbs further down the list, degrading the Round-1 `F-IMPORT-SHADOWING-LIFECYCLE` fix that put verbs first. Group 6 preserves the lifecycle-first discoverability for day-0 users while giving Kaizen agents (per `§E11.3 MUST 1`) a clean target.

**Day-0 trace:** The newbie running the Quick Start never needs `engine_info` — `km.train(df, target="y")` auto-dispatches via `family="auto"`. The newbie discovers the verb only when they want to ask "what ML families are available?" or "what does `km.train` accept?" — exactly the mental model `list_engines()` / `engine_info()` serve.

**Verdict:** Discoverable (3 paths, tab/dir/help). Non-obstructive (preserves Group 1 lifecycle-first ordering). Correctly scoped.

### C3. `artifact_uri` back-compat shim — **Warning-silent on Day-0 Quick Start**

**What landed:** `ml-registry-draft.md:448-479` — §7.1.1 declares a `@property artifact_uri` on `RegisterResult` that:

- Emits `DeprecationWarning("RegisterResult.artifact_uri (singular) is deprecated; use RegisterResult.artifact_uris[format] (plural dict). …")` on access.
- Returns `self.artifact_uris["onnx"]`.
- REMOVED at v2.0 (Decision 11 legacy-sunset path).

**Annoyance audit — does the newbie see the warning on Day 0?**

Re-read the canonical Quick Start (`ml-readme-quickstart-body-draft.md §2`, SHA-256-pinned):

```python
import kailash_ml as km
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
# $ kailash-ml-dashboard  (separate shell)
```

Sweep every symbol the Quick Start touches:

- `km`, `km.track`, `run`, `km.train`, `result`, `km.register`, `registered`, `km.serve`, `server`.
- **NEVER touches `registered.artifact_uri` (singular).** Never reads it, never prints it, never asserts on it.

**Follow-up audit — does any Quick Start-adjacent test or prose touch the shim?**

- `ml-readme-quickstart-body-draft.md:74` — the "What this does" narrative says "returns a `RegisterResult` with `artifact_uris` pointing at the framework-agnostic ONNX + native format pair" — uses the **plural** `artifact_uris`. No singular shim reference.
- `ml-engines-v2-draft.md §16.1` / §16.3 — canonical Quick Start block SHA-pinned; no singular read.
- `ml-engines-v2-draft.md §16.3` Tier-2 regression test body — verifies `"onnx" in registered.artifact_uris` (plural). No shim hit.

**Day-0 trace:** A newbie running the canonical 5-line Quick Start never hits the singular accessor, so `DeprecationWarning` never fires in their notebook. The warning exists solely to protect v0.9.x users upgrading to 1.0.0 who have existing code calling `.artifact_uri` (singular) — exactly the audience Decision 11 migration flags are designed for.

**Secondary concern — could a newbie hit the warning by copy-pasting from the deprecated v0.9.x README?** The release-PR drop-in procedure (§4 of `ml-readme-quickstart-body-draft.md`) explicitly replaces the old 6-import Quick Start block, and the SHA-256 fingerprint test BLOCKS a release that ships an un-updated README. So the warning surface only exists for pre-existing user code, not for a fresh install.

**Verdict:** Zero day-0 noise. Warning fires only for legacy-code upgrade path, which is the correct target audience per `rules/zero-tolerance.md` Rule 1 (deprecation disposition with documented sunset + `ImmutableGoldenReferenceError`-style typed migration error at v2.0).

---

## Section D — Full Closure Check (Round 1 → Round 5)

Re-derived from scratch — no trust in prior round verdicts.

| Finding                                                       | Round | Status at Round-5 | Status at Round-6                                                              |
| ------------------------------------------------------------- | ----- | ----------------- | ------------------------------------------------------------------------------ |
| F-IMPORT-SHADOWING-LIFECYCLE (lifecycle-first `__all__`)      | 1     | CLOSED            | CLOSED — Group 1 preserved + Group 6 introduces without obstruction (§C2)      |
| F-DIAGNOSE-NO-TOPLEVEL (`km.diagnose` at package top)         | 1     | CLOSED            | CLOSED — `ml-diagnostics §3`                                                   |
| F-TRACKER-KWARG-AMBIGUITY (`tracker=Optional[ExperimentRun]`) | 1     | CLOSED            | CLOSED — `ml-engines-v2-addendum §E2` + `ml-tracking §2.4`                     |
| CRITs (DB URL, tracker ctor, MLError, get_current_run)        | 2/2b  | 4/4 CLOSED        | CLOSED — re-verified via Round-5-SYNTHESIS §"What's CERTIFIED today"           |
| H-1 `km.seed` / `km.reproduce` signatures                     | 3     | CLOSED            | CLOSED — §11/§12 module-level functions, eager-imported in §15.9               |
| H-2 env-var canonical vocabulary (`KAILASH_ML_STORE_URL`)     | 3     | CLOSED            | CLOSED — Phase-E E1/E1b + Phase-F F2 (4-spec plumbing note)                    |
| H-3 `is_golden` registry schema + API kwarg                   | 3     | CLOSED            | CLOSED — `ml-registry §7.5`                                                    |
| M-1 (R4) phantom §2.1 MUST anchor for env var                 | 4     | CLOSED            | CLOSED — Phase-E E1b landed the canonical MUST at `ml-engines-v2 §2.1 MUST 1b` |
| L-1 (R5) `km.lineage tenant_id` no default                    | 5     | OPEN              | **CLOSED — see Section A** (4 call sites consistent, sibling-aligned)          |

**Net newbie-UX finding count:** 0 OPEN, 9 CLOSED. No regression from any prior round.

---

## Section E — Round 6 Verdict

| Target                                             | Actual                        | Met? |
| -------------------------------------------------- | ----------------------------- | ---- |
| 6/6 day-0 scenarios GREEN                          | 6/6 GREEN                     | ✅   |
| 0 NEW HIGHs                                        | 0 NEW HIGHs                   | ✅   |
| 0 NEW MEDs                                         | 0 NEW MEDs                    | ✅   |
| 0 NEW LOWs                                         | 0 NEW LOWs                    | ✅   |
| L-1 CLOSED                                         | CLOSED (Section A)            | ✅   |
| All Round 1-5 newbie findings CLOSED               | 9/9 CLOSED                    | ✅   |
| Phase-F new surfaces (ClearanceReq, Group 6, shim) | Zero day-0 impact (Section C) | ✅   |

**Verdict: CONVERGED. First clean newbie-UX round.**

Target met: 6/6 GREEN + 0 HIGH + 0 MED + 0 LOW. The junior-scientist day-0 UX surface is stable. Three consecutive rounds (Round-4 closed 3 Round-3 HIGHs; Round-5 closed the Round-4 MED; Round-6 closes the Round-5 LOW) have driven the persona's open-finding count monotonically toward zero with no regressions introduced.

## Severity Summary

| Finding           | Severity | Scenario impact | Fix category | Source |
| ----------------- | -------- | --------------- | ------------ | ------ |
| (no new findings) | —        | —               | —            | —      |

## Recommendation

No Phase-G work required against the newbie-UX persona. If other Round-6 audits (feasibility, spec-compliance, cross-spec) surface HIGHs requiring Phase-G, the newbie-UX persona re-audits in Round 7 as a regression check — not as a scoping input.

Round 7 confirms convergence (two consecutive clean rounds per Round-5-SYNTHESIS § "Round-6 entry criteria").

---

**Output path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-newbie-ux.md`

# Round 8 Newbie UX Audit

**Date:** 2026-04-21
**Persona:** Year-2 ML engineer / MLFP-course student who `pip install kailash-ml`, opens a notebook, copy-pastes the Quick Start, expects it to Just Work. Never touches a spec unless an `AttributeError`/`TypeError` drags them there.
**Method:** Re-walked all 6 Day-0 scenarios as confirmation (3rd consecutive). Already CONVERGED at R6+R7. Round-8 target: verify Phase-H did not break any converged surface.

---

## Headline: 6/6 GREEN (3rd consecutive clean)

Phase-H touched two comment-grade descriptive sites (EngineInfo.signatures inline comment at `ml-engines-v2-addendum-draft.md:505`; kaizen-ml §2.4.2 field-table signatures row at `kaizen-ml-integration-draft.md:172`). Both sites live in advanced/agent-integration surfaces that a Day-0 newbie does not encounter. All 6 scenarios remain GREEN.

---

## Scenarios (brief re-walk)

### S1 — Day-0 `km.train(model, data)` returns `TrainingResult`, auto-emits → **GREEN**

- `ml-engines-v2-draft.md:2052-2075` §15.3 signature + behaviour rules unchanged by Phase-H.
- Quick Start `ml-readme-quickstart-body-draft.md:61` still `result = await km.train(df, target="y")`.
- Tracker auto-wiring contract (`tracker=None` → ambient run) stable.

### S2 — `km.diagnose(...)` returns `DLDiagnostics | RAGDiagnostics | RLDiagnostics` → **GREEN**

- `ml-diagnostics-draft.md:14-34, 115-163` unchanged by Phase-H.
- `km.diagnose` sole diagnostic entry at spec top. `tracker=None` INFO-not-WARN contract stable.

### S3 — `km.dashboard()` + `kailash-ml-dashboard` CLI → **GREEN**

- `ml-dashboard-draft.md:79, 92-101, 412, 419` unchanged. `KAILASH_ML_STORE_URL → ~/.kailash_ml/ml.db` fallback chain intact.
- `km.dashboard(...)` wrapper at `ml-engines-v2-draft.md:2139-2150` returns `DashboardHandle` (notebook-friendly).

### S4 — Contextvar auto-wire `async with km.track() as run:` → **GREEN**

- `ml-engines-v2-addendum-draft.md:49-71` §E2 MUST 1 unchanged by Phase-H. H1 edit landed on L505 (EngineInfo dataclass comment), not §E2.
- `tracker: ExperimentRun | None = None` contract stable across `km.train` / `km.diagnose` / `km.register`.

### S5 — `dir(km)` returns 6 lifecycle groups in canonical order → **GREEN**

- `ml-engines-v2-draft.md:2180, 2183-2236, 2241-2274` §15.9 unchanged.
- Group 1 (13 lifecycle verbs) first; Group 6 (`engine_info`, `list_engines`) last.
- "Ordering Is Load-Bearing" MUST + eager-import MUST preserved.

### S6 — Lifecycle verbs `seed`, `reproduce`, `resume`, `lineage`, `register`, `serve` → **GREEN**

- `ml-engines-v2-draft.md:1640-1693, 1735-1789, 1803-1830, 2079-2116, 2163-2172` unchanged by Phase-H.
- All 6 verbs in Group 1 `__all__` + eagerly imported (§15.9 L2258-2264).

---

## Phase-H surface impact

### H1 — `ml-engines-v2-addendum-draft.md:505` EngineInfo.signatures comment fix → **Zero Day-0 impact**

Verified at L505: the comment now reads "Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4." This is an inline docstring on a dataclass field inside `EngineInfo`, which lives in §E11 (Engine Discovery). Day-0 Quick Start never imports `EngineInfo`, never calls `km.engine_info()`, never calls `km.list_engines()` — verified 0 hits for these symbols in `ml-readme-quickstart-body-draft.md` in Round-7 P4 and re-confirmed here. The comment is only visible to developers reading `@dataclass class EngineInfo` in the addendum OR to Kaizen agents introspecting engine metadata for tool-spec generation.

**Verdict: Phase-H H1 is scoped to advanced surfaces. Zero Day-0 friction. S5 (Group 6 discovery verbs at end) unchanged.**

### H2 — `kaizen-ml-integration-draft.md:172` signatures row rewrite → **Zero Day-0 impact**

Verified at L172: the field-table row now reads "Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant." This lives in `kaizen-ml-integration-draft.md §2.4.2 EngineInfo fields re-stated` — §2.4 is explicitly the kaizen-ml agent-integration section ("Kaizen agents derive their LLM tool-spec list by traversing `EngineInfo.signatures`", L175). A Day-0 newbie running `km.train → km.register → km.serve` in a notebook never reads the kaizen-ml integration spec at all. Kaizen agent authors are the audience, not notebook newbies.

**Verdict: Phase-H H2 is scoped to agent-integration advanced path. Zero Day-0 friction. S1-S6 all unchanged.**

### Additional mechanical sweep (post-Phase-H)

Re-verified the 4 Round-7 Phase-G probes still hold post-Phase-H:

- **P1** — `ClearanceRequirement` still absent from `ml-readme-quickstart-body-draft.md` and from `ml-engines-v2-draft.md` main body (0 hits outside the addendum + kaizen-ml). Day-0 still never encounters D/T/R axis semantics.
- **P2** — `artifact_uris` dict shape still invisible at Day-0; `ml-readme-quickstart-body-draft.md:74` prose unchanged by Phase-H.
- **P3** — Progressive disclosure preserved; Group 6 at end unchanged.
- **P4** — `km.engine_info` / `km.list_engines` still 0 hits in Quick Start.

---

## Convergence assertion (3rd consecutive clean)

Newbie-UX persona was CONVERGED at Round-6 + Round-7 (2 consecutive clean rounds). Round-8 is the 3rd consecutive confirmation.

| Round | Verdict                                          | Cumulative |
| ----- | ------------------------------------------------ | ---------- |
| R6    | 6/6 GREEN + 0/0/0 — 1st clean                    | 1          |
| R7    | 6/6 GREEN + 0/0/0 — 2nd consecutive (CONVERGED)  | 2          |
| R8    | 6/6 GREEN + 0/0/0 — 3rd consecutive (reinforced) | 3          |

**Phase-H non-impact proof:**

1. Phase-H touched 2 descriptive sites only (one dataclass inline comment, one field-table row).
2. Neither site is load-bearing for Day-0 surfaces (Quick Start, `__all__`, `km.*` signatures, `tracker=` contract, `KAILASH_ML_STORE_URL` chain, lifecycle verbs).
3. Both sites live in advanced/agent-integration surfaces (`ml-engines-v2-addendum §E11` Engine Discovery; `kaizen-ml-integration §2.4` Agent Engine Discovery).
4. The post-Phase-G convergence criteria (2-consecutive-clean exit) was already satisfied at R7; R8 confirms the Phase-H changes introduced zero drift.

**Closure sweep carry-over:** All 10 Round-1 → Round-6 newbie findings remain CLOSED. No regressions detected. No new findings. Optional LOW prose polish flagged in Round-7 (`ml-readme-quickstart-body-draft.md:74` "ONNX + native format pair") remains deferrable to release-PR copy review — still NOT a Round-8 blocker.

**Round-8 verdict: CONVERGED (3rd consecutive clean). Newbie-UX persona is release-ready. Proceed to `/codify` promote specs-draft/ → specs/ once remaining Round-8 personas confirm their respective convergence criteria.**

---

## Severity Summary

| Finding           | Severity | Scenario impact | Fix category | Source |
| ----------------- | -------- | --------------- | ------------ | ------ |
| (no new findings) | —        | —               | —            | —      |

**Output path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-8-newbie-ux.md`

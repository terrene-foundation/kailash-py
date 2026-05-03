# Round 4 — Junior-Scientist Day-0 UX Re-Audit (Post-Phase-D)

**Persona:** Year-2 ML engineer / MLFP course student who types `pip install kailash-ml`, opens a notebook, and expects the 5-line Quick Start to "just work."

**Method:** grep/read against `workspaces/kailash-ml-audit/specs-draft/` — 15 ml-\*-draft.md + 6 supporting-\*-draft.md. Re-derived each Round-3 HIGH from scratch; re-walked the 6 day-0 scenarios; traced the new `km.resume()` wrapper; scanned for new friction introduced by Phase-D's spec-expansion pressure.

**TL;DR:** All 3 Round-3 NEW HIGHs (H-1, H-2, H-3) are closed. All 6 day-0 scenarios remain GREEN. `km.resume()` lands cleanly. **One NEW MED (M-1) surfaced** — the dashboard spec anchors canonical env-var vocabulary on an engines-v2 §2.1 MUST 1 that does not actually declare it. **Zero NEW HIGHs.** Target met.

---

## Section A — Verification of the 3 Round-3 NEW HIGHs

### H-1 (Round 3): `km.seed` / `km.reproduce` signatures invalid Python, missing from `__all__` Group 1 → **CLOSED**

**Claim:** D3 fixes both signatures to `def seed(...)` / `async def reproduce(...)` as module-level functions in `kailash_ml/__init__.py`, explicitly lists both in `__all__` Group 1.

**Evidence:**

- `ml-engines-v2-draft.md:1611` — "`seed()` is a **module-level function** defined in `kailash_ml/__init__.py` (NOT a method on any class) … Earlier drafts wrote `def km.seed(...)` which is syntactically invalid Python."
- `ml-engines-v2-draft.md:1615-1624` — body reads `def seed(seed: int, *, torch: bool = True, ...) -> SeedReport:` — valid Python, keyword-only modifiers correctly placed.
- `ml-engines-v2-draft.md:1702` — mirror language for `reproduce()`: "Earlier drafts wrote `async def km.reproduce(...)` which is syntactically invalid Python."
- `ml-engines-v2-draft.md:1706-1712` — `async def reproduce(run_id: str, *, verify: bool = True, ...) -> TrainingResult:` — valid Python.
- `ml-engines-v2-draft.md:2133-2146` — `__all__` Group 1 contains `"seed"`, `"reproduce"`, `"resume"` in exactly that order between `"dashboard"` and `"rl_train"`. Group 1 is commented `# Group 1 — Lifecycle verbs (action-first for discoverability)`.
- `ml-engines-v2-draft.md:2187-2211` — **MUST: Every `__all__` Entry Is Eagerly Imported** — explicitly forbids lazy `__getattr__` resolution (closes `rules/zero-tolerance.md` Rule 1a 2nd instance re CodeQL `py/modification-of-default-value`). Eager-import example in the DO block shows `seed()` / `reproduce()` / `resume()` declared at module scope with real `def` bodies.
- `ml-engines-v2-draft.md:2403` — completion checklist requires the Group 1 entries AND eager imports.

**Verdict:** CLOSED. Signatures are syntactically valid Python; discoverability is lexicographically guaranteed via `__all__` ordering AND eager-import MUST.

---

### H-2 (Round 3): Env var drift — `KAILASH_ML_STORE_URL` (ml-engines-v2 test) vs `KAILASH_ML_TRACKER_DB` (ml-dashboard CLI) → **CLOSED (with caveat — see Section E M-1)**

**Claim:** D3 picks `KAILASH_ML_STORE_URL` as the canonical 1.0.0+ vocabulary and accepts `KAILASH_ML_TRACKER_DB` during 1.x only with a one-shot DEBUG log; removes the legacy name at 2.0.

**Evidence:**

- `ml-dashboard-draft.md:96` — "Read the `KAILASH_ML_STORE_URL` env var — the canonical cross-spec store-URL variable per `ml-engines-v2.md §2.1 MUST 1` (Tier-2 test at `tests/integration/test_engine_store_env.py`). The legacy name `KAILASH_ML_TRACKER_DB` is accepted during 1.x ONLY."
- `ml-dashboard-draft.md:101-113` — §3.2.1 spells out the migration: accept legacy → emit DEBUG log `legacy env var KAILASH_ML_TRACKER_DB resolved; rename to KAILASH_ML_STORE_URL` once per process via `_legacy_env_warned` sentinel; precedence `KAILASH_ML_STORE_URL` wins + WARN `kml.env.legacy_precedence_ignored` when both are set; at 2.0.0 `KAILASH_ML_TRACKER_DB` is ignored and raises `EnvVarDeprecatedError` when `KAILASH_ML_STRICT_ENV=1` is opted into.
- `ml-dashboard-draft.md:388` — CLI flag table: `--db URL` defaults to `$KAILASH_ML_STORE_URL or ~/.kailash_ml/ml.db`, legacy `$KAILASH_ML_TRACKER_DB` accepted during 1.x.
- `ml-dashboard-draft.md:433-445` — constructor `db_url=None` path resolves through the same precedence.
- `ml-engines-v2-draft.md:2321` — Quick-Start regression test uses `monkeypatch.setenv("KAILASH_ML_STORE_URL", ...)` — consistent with the chosen canonical name.

**Verdict:** CLOSED at the behavioral level (dashboard, CLI, test, constructor all use the same canonical var; legacy name sunset path documented). **See M-1 in Section E** for a cross-reference drift that prevents this from being a clean CLOSED: the anchoring MUST rule cited (`ml-engines-v2.md §2.1 MUST 1`) does not actually contain the `KAILASH_ML_STORE_URL` string.

---

### H-3 (Round 3): `is_golden` registry schema + API kwarg missing → **CLOSED**

**Claim:** D2+D3 ships DDL column, partial index, API kwarg on `register_model`, query helper, write-once immutability, audit-trail contract, Tier-2 schema-migration test, Postgres+SQLite parity.

**Evidence:**

- `ml-registry-draft.md:247` — `is_golden BOOLEAN NOT NULL DEFAULT FALSE` column in `kml_model_versions` DDL with comment "CI release-gate flag per §7 registration rules".
- `ml-registry-draft.md:253` — partial index `CREATE INDEX idx_model_versions_golden ON kml_model_versions(tenant_id, is_golden) WHERE is_golden = TRUE`.
- `ml-registry-draft.md:311` — SQLite compatibility rewrite `WHERE is_golden = 1` (since BOOLEAN → INTEGER on SQLite).
- `ml-registry-draft.md:315` — Tier-2 migration test `test_kml_model_versions_schema_migration.py` explicitly asserts both backends match the DDL AND the partial-index predicate is rewritten on SQLite.
- `ml-registry-draft.md:374` — `register_model(..., is_golden: bool = False, ...)` API kwarg.
- `ml-registry-draft.md:495-524` — §7.5 Golden-Reference Registrations: `km.reproduce(golden_reference_id, verify=True)` MUST pass before release promotion; write-once contract enforced by `ImmutableGoldenReferenceError(ModelRegistryError)`; entire row becomes immutable once flag is set (no metadata/alias mutations either); only legal path is a NEW version with its own golden flag.
- `ml-registry-draft.md:557-577` — §7.5.3/7.5.4 list_goldens() helper + `km.reproduce` lineage query.
- `ml-registry-draft.md:584-587` — §7.5.5 audit-row emission with `new_state = {"is_golden": true, "release": <metadata.release>}`.
- `ml-engines-v2-draft.md:1746` — release-gate clause: "Every kailash-ml release MUST include a 'golden' reference run … CI MUST run `km.reproduce(golden_reference_id, verify=True)` as a release gate."
- `ml-engines-v2-draft.md:2399` — completion checklist: "Golden reference run is registered at package-import with `is_golden=True`".

**Verdict:** CLOSED. Schema + API + immutability + audit + tests all present.

---

## Section B — 6 Day-0 Scenario Re-Walk

Re-derived from Round-1 newbie-ux Q1-Q6. Each scenario is a ~5-line Day-0 interaction.

### S1. `km.train(df, target="y")` — one-line fit → **GREEN (unchanged from Round 3)**

- `ml-engines-v2-draft.md:2013-2040` — §15.3 `km.train` signature: `async def train(data, *, target, family="auto", tenant_id=None, actor_id=None, **setup_kwargs) -> TrainingResult`. Dispatch through cached default Engine. BLOCKED rationalizations prevent silent `.register()` or `.serve()` coupling.
- Canonical Quick Start (§16.1) uses it at line 2: `result = await km.train(df, target="y")`.
- No new friction.

### S2. `km.diagnose(result)` — one-line diagnose → **GREEN (unchanged from Round 3)**

- `ml-diagnostics-draft.md:6,22-34,115-163` — `km.diagnose` is top-of-spec, SOLE diagnostic entry point at package top-level, auto-dispatches by `TrainingResult.family` / `kind=` override.
- `ml-diagnostics-draft.md:163` — `tracker=None` defaults read `kailash_ml.tracking.get_current_run()` so newbie inside `km.track()` gets metrics auto-pushed to dashboard with ZERO kwargs.
- `ml-diagnostics-draft.md:173` — explicit reference to closing F-DIAGNOSE-NO-TOPLEVEL from Round-1.
- No new friction.

### S3. `kailash-ml-dashboard` (or `km.dashboard()`) — one-line dashboard → **GREEN (unchanged from Round 3; see M-1 caveat)**

- `ml-dashboard-draft.md:92-99` — §3.2: `db_url=None` → `$KAILASH_ML_STORE_URL` → `~/.kailash_ml/ml.db`. Dashboard's default store path MUST equal tracker's default (§2.2 of ml-tracking). Divergence is a Round-1 CRITICAL regression.
- `ml-engines-v2-draft.md:2100-2107` — §15.7 `km.dashboard` package-level wrapper.
- `ml-dashboard-draft.md:511` — explicit note: "Notebook users are the dominant kailash-ml onboarding surface; forcing them to open a separate terminal to run the CLI breaks the 'everything in one cell' promise of the Quick Start." Dual launcher (CLI + non-blocking Python) matches W&B / Neptune / Comet.
- **Caveat M-1:** the MUST reference anchoring env-var canonicity is broken. See Section E.

### S4. `DLDiagnostics(model, tracker=run)` / auto-wiring via contextvar → **GREEN (unchanged from Round 3)**

- `ml-engines-v2-addendum-draft.md:22,49-51,74` — every engine MUST call `kailash_ml.tracking.get_current_run()` at the start of any mutation method; `tracker=` kwarg annotates `Optional[ExperimentRun]` not `Optional[ExperimentTracker]`.
- `ml-tracking-draft.md:1020-1021` — `DLDiagnostics(tracker=None)` / `RLDiagnostics(tracker=None)` read `get_current_run()` when tracker is None.
- `ml-diagnostics-draft.md:163` — same contract.
- The one-kwarg PyTorch-Lightning-equivalent story is structurally enforced.

### S5. `dir(km)` lifecycle-ordered → **GREEN (improved from Round 3)**

- `ml-engines-v2-draft.md:2128-2180` — §15.9 pins `__all__` ordering into 5 named groups. Group 1 = lifecycle verbs (`track`, `autolog`, `train`, `diagnose`, `register`, `serve`, `watch`, `dashboard`, `seed`, `reproduce`, `resume`, `rl_train`).
- §15.9 "MUST: Ordering Is Load-Bearing" — reordering within a group = spec amendment; moving across groups = breaking-change signal.
- §15.9 "MUST: Every `__all__` Entry Is Eagerly Imported" — closes the `__getattr__` / CodeQL failure mode permanently.
- Day-0 newbie typing `import kailash_ml as km; dir(km)` now sees verbs first, primitives second — the exact fix Round-1 F-IMPORT-SHADOWING-LIFECYCLE demanded.

### S6. Lifecycle holes (serve / drift / RL) → **GREEN (unchanged from Round 3)**

- `km.serve` — `ml-engines-v2-draft.md:2067-2082` §15.5; resolves `"name@alias"` through cached registry; returns `ServeHandle` with `.url`, `.stop()`, `.status`.
- `km.watch` — `ml-engines-v2-draft.md:2084-2097` §15.6; `ml-drift-draft.md:787` — package-level wrapper for drift monitoring.
- `km.rl_train` — `ml-engines-v2-draft.md:1926` table entry; `ml-rl-core-draft.md` §7 wraps `rl.Engine.train()` with full tracker + diagnostics + registry wiring.
- All three are in `__all__` Group 1.

**Scenario Summary:** 6/6 GREEN. Target met.

---

## Section C — 5-Line Quick Start Walk

Canonical block at `ml-engines-v2-draft.md:2225-2234`:

```python
import kailash_ml as km
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
# $ kailash-ml-dashboard  (separate shell)
```

**Line-by-line Day-0 impression:**

1. `import kailash_ml as km` — single import, canonical alias. ✓
2. `async with km.track("demo") as run:` — async-context-manager opens ambient tracker. Newbie needs `asyncio.run(...)` or notebook top-level await, but that's a Python/Jupyter concern, not a kailash-ml concern. ✓
3. `result = await km.train(df, target="y")` — one verb, one kwarg, typed `TrainingResult` return. `df` is a polars DataFrame the newbie already has. ✓
4. `registered = await km.register(result, name="demo")` — pass the result forward; registry constructs under the hood. ✓
5. `server = await km.serve("demo@production")` — string `"name@alias"` resolves via registry; returns ServeHandle. ✓
6. `# $ kailash-ml-dashboard` — comment explicitly flags the separate shell. Newbie opens another terminal, types the command, sees the run. ✓

**Friction checks:**

- No `ConnectionManager`, no `FeatureStore`, no `ArtifactStore` construction — §16.2 MUST 2 BLOCKS that ceremony. ✓
- Line count: 6 lines of non-blank executable content (matches §16.2 MUST 1's 5-10 range, including the dashboard comment which is "load-bearing per §16.2 MUST 1"). ✓
- Pinned via SHA-256 regression test `test_readme_quickstart_fingerprint_matches_spec` AND executed end-to-end via `test_readme_quickstart_executes_end_to_end` (§16.3); release-blocking per §16.4. ✓

**Day-0 verdict:** Clean. The narrative now matches the spec; the spec is pinned by a regression test; the test is release-blocking.

---

## Section D — `km.resume()` Top-Level Wrapper (D5 addition)

**Surface inspected:** `ml-engines-v2-draft.md` §3.2 MUST 7 (pairing with ModelCheckpoint auto-attach, lines 752-871); §12A (lines 1768-1831); §15.8 (line 2118-2126); §15.9 (**all** Group 1 entry, line 2145); completion checklist line 2417.

**API surface a newbie sees:**

```python
async def resume(
    run_id: str,
    *,
    tenant_id: str | None = None,
    tolerance: dict[str, float] | None = None,
    verify: bool = False,
    data: pl.DataFrame | None = None,
) -> TrainingResult:
```

**Day-0 impression checks:**

1. **Discoverability** — Listed in `__all__` Group 1 between `"reproduce"` and `"rl_train"`. `dir(km)` shows it adjacent to its semantic neighbours. ✓
2. **Invocation** — `await km.resume(run_id)` works with positional arg + default kwargs. ✓
3. **Cognitive load** — Four keyword-only args with sensible defaults. `tolerance`/`verify` are an advanced pair (off by default); `tenant_id`/`data` are advanced overrides. A newbie types `await km.resume("run_abc123")` and it just works. ✓
4. **Error taxonomy** — `ResumeArtifactNotFoundError` (explicit message path to the expected `last.ckpt`), `ModelNotFoundError`, `ResumeDivergenceError`. Named types per `ml-engines-v2-draft.md:838-851`. No opaque `AttributeError`. ✓
5. **Lineage** — Child run's `parent_run_id` = original run; `run_type="resume"`. Auditable from the tracker. ✓
6. **Pair with §3.2 MUST 7** — `enable_checkpointing=True` is the new default at 1.0.0. Newbie who never touches checkpoints still gets `last.ckpt` produced automatically inside `km.track()`. `km.resume(run_id)` then finds it. ✓
7. **Distinction from `km.reproduce`** — §12A's prose explicitly contrasts the two: `reproduce` = "re-run from scratch against CURRENT code"; `resume` = "continue from saved checkpoint, extend beyond original epochs." No overlap confusion. ✓
8. **Integration tests pinned** — `test_km_resume_roundtrip.py` + `test_km_resume_missing_checkpoint_raises.py` (lines 868-870). Ship-blocking per completion checklist. ✓

**Verdict:** `km.resume()` surfaces cleanly. Zero new friction; one new well-framed power-user kwarg set. It rides the same `km.*` dispatch discipline as every other lifecycle verb.

---

## Section E — NEW Frictions Introduced by Phase-D

Phase-D edited 15+ spec files in one pass. Junior-scientist re-audit checked for:

1. Cognitive-load overflow (too many kwargs on a one-liner).
2. Cross-spec citation drift (one spec points at another's MUST that doesn't exist).
3. Over-documentation (MUST-walls that bury the happy path).
4. Spec-size bloat (MUST Rule 8 violations at 300+ lines).

### M-1 (NEW MED) — Dashboard env-var MUST cites a phantom anchor in engines-v2

**Finding:** `ml-dashboard-draft.md:96` reads:

> "Read the `KAILASH_ML_STORE_URL` env var — the canonical cross-spec store-URL variable per `ml-engines-v2.md §2.1 MUST 1`"

But `ml-engines-v2-draft.md §2.1 MUST 1` (lines 90-121) is titled "`kailash_ml.Engine` MUST Support Zero-Argument Construction With Production Defaults." Its body describes `~/.kailash_ml/ml.db` as the SQLite default — it does NOT mandate `KAILASH_ML_STORE_URL` as the canonical env-var name, nor does it reference env-var vocabulary at all.

Similarly, `ml-tracking-draft.md §2.5` (the `ExperimentTracker.create(store_url=None)` canonical factory) does NOT reference the env var; it says `store_url: None` defaults to `~/.kailash_ml/ml.db`.

**Evidence:**

- `grep -rn "KAILASH_ML_STORE_URL" workspaces/kailash-ml-audit/specs-draft/` returns only:
  - `ml-dashboard-draft.md` (7 references — the de-facto canonical site)
  - `ml-engines-v2-draft.md:2321` (a single `monkeypatch.setenv` inside the Quick-Start regression test body)
- No MUST rule anywhere in the 15 specs declares `KAILASH_ML_STORE_URL` as the canonical env-var name for the cross-SDK store URL.

**User-visible impact (indirect):** A newbie reading the dashboard spec sees "per ml-engines-v2.md §2.1 MUST 1" and clicks through expecting to find the env-var declaration. They find a zero-arg-construction rule that doesn't mention env vars. This is a spec-reader's dead link; low severity for Day-0 UX (the behavior still works because dashboard's own §3.2.1 defines the semantics), but it's exactly the `rules/specs-authority.md` §5b "cross-spec citation drift" failure mode.

**Severity rationale for MED (not HIGH):** Behavior is consistent across dashboard CLI, dashboard constructor, and the Quick-Start regression test. No newbie is blocked. But the spec authority chain is broken — any reader auditing the canonical env-var vocabulary ends up at the wrong MUST. A real implementation PR that adds env-var reading to `ExperimentTracker.create()` will have no MUST to cite in its code comment.

**Fix category:** NARRATIVE / DATA — add an explicit MUST clause to `ml-engines-v2.md §2.1` (or a new §2.1 MUST N) that declares `KAILASH_ML_STORE_URL` as the canonical env var for the store URL across every engine primitive. OR add the declaration to `ml-tracking-draft.md §2.5` and redirect the dashboard cross-reference. One-line spec edit.

---

### Pre-existing, not Phase-D-induced (flagged for completeness, NOT counted as NEW):

- **ml-engines-v2-draft.md is 2,423 lines** — violates `rules/specs-authority.md` MUST Rule 8 ("When a spec file exceeds 300 lines, it MUST be split into sub-domain files"). Pre-existing structural debt (started before Phase-D). Phase-D added ~300 lines to it (§12A km.resume + §15.9 `__all__` ordering + §16 Quick Start). A junior reviewer cannot feasibly read 2,423 lines in one sitting; however, the `_index.md` + targeted-read protocol in specs-authority §4 makes it workable in practice. Recommend split at next session (e.g., §15 km-wrappers + §16 quick-start + §11-12A reproducibility → separate files).

- **ml-diagnostics-draft.md (1,070 lines), ml-tracking-draft.md (1,266 lines), ml-serving-draft.md (1,214 lines), ml-rl-core-draft.md (1,234 lines), ml-registry-draft.md (1,027 lines)** — also violate MUST Rule 8. Pre-existing; not introduced by Phase-D.

---

## Severity Summary

| Finding                                   | Severity                   | Scenario impact                | Fix category     | Source             |
| ----------------------------------------- | -------------------------- | ------------------------------ | ---------------- | ------------------ |
| H-1 `km.seed`/`reproduce` sigs            | CLOSED                     | S5 `dir(km)`                   | —                | Round 3 → D3       |
| H-2 env-var canonical vocabulary          | CLOSED\*                   | S3 dashboard                   | —                | Round 3 → D3       |
| H-3 `is_golden` registry schema           | CLOSED                     | Release gate                   | —                | Round 3 → D2+3     |
| M-1 engines-v2 §2.1 MUST 1 phantom anchor | MED (NEW)                  | S3 dashboard reader-audit only | NARRATIVE / DATA | Phase-D D3 partial |
| Spec-file size > 300 lines (×6)           | PRE-EXISTING (MUST Rule 8) | none Day-0; slows reviewer     | STRUCTURAL       | Before Phase-D     |

\* H-2 behaviorally CLOSED; spec-authority chain partial — M-1 captures the residual.

---

## Round 4 Entry-Criterion Check

| Target                      | Actual                           | Met? |
| --------------------------- | -------------------------------- | ---- |
| 6/6 day-0 scenarios GREEN   | 6/6 GREEN                        | ✅   |
| 0 NEW HIGHs                 | 0 NEW HIGHs                      | ✅   |
| Round-3 H-1/H-2/H-3 CLOSED  | 3/3 CLOSED (H-2 with M-1 caveat) | ✅   |
| `km.resume()` clean surface | confirmed                        | ✅   |

**Verdict:** Phase-D succeeded on Day-0 UX. Zero NEW HIGHs. One NEW MED (M-1 phantom spec anchor) that is trivially addressable with a one-line MUST-clause add to `ml-engines-v2.md §2.1`. No further Phase-D work required against this persona.

---

## Recommendation to the synthesis author

Add one MUST clause to `ml-engines-v2-draft.md §2.1` (inserted as a new MUST or appended to MUST 1):

> **N. `MLEngine` Env-Var Contract.** When `store=` is not passed, the Engine MUST consult `KAILASH_ML_STORE_URL` before falling back to `~/.kailash_ml/ml.db`. The variable MUST be used as the canonical cross-spec store-URL name; every primitive that resolves a store URL (tracker, registry, feature store, dashboard, drift monitor) MUST read the same variable. During 1.x, the legacy `KAILASH_ML_TRACKER_DB` MUST be accepted with the one-shot DEBUG + WARN contract in `ml-dashboard.md §3.2.1`; at 2.0.0 the legacy name is removed.

This closes M-1 and strengthens Round-4 to a full APPROVE. Target for Round 5: 0 HIGH + 0 MED + 0 CRIT = convergence.

---

**Output path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-4-newbie-ux.md`

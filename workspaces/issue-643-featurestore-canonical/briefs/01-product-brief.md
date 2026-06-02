# Brief — #643 FeatureStore canonical-surface migration (Step 1: bridge release)

**Source issue:** terrene-foundation/kailash-py#643 (filed 2026-04-30)
**Scope of THIS workspace:** Step 1 only (the non-breaking bridge release). Step 3 (the
breaking 2.0.0 cutover) is explicitly a later cycle and OUT OF SCOPE here.

## Value anchor (spec § success criterion — source e per value-prioritization MUST-1)

`specs/ml-feature-store.md:6` declares **verbatim**:

> **Canonical module:** `kailash_ml.features` (1.0+ surface)
> **Legacy module:** `kailash_ml.engines.feature_store` (0.x surface, retained for 0.x callers; not specified here)

The drift this brief closes: the spec declares `kailash_ml.features` canonical, but the
top-level `from kailash_ml import FeatureStore` still resolves to the **legacy** module.

## Verified state at launch (2026-06-02 — supersedes stale issue claims per specs-authority Rule 5c)

| Issue claim (2026-04-30)                                           | Verified-current state (2026-06-02)                                                   | Disposition                                                 |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| kailash-ml at **1.1.1**                                            | kailash-ml at **1.7.4** (`pyproject.toml` + `_version.py`)                            | Bridge release = **1.8.0** (NOT 1.2.0); cutover stays 2.0.0 |
| `_engine_map["FeatureStore"] = "kailash_ml.engines.feature_store"` | **CONFIRMED** still legacy at `__init__.py:631`                                       | drift real & current                                        |
| Canonical `features/store.py` exists, canonical docstring          | **CONFIRMED** (15.7 KB, ctor `FeatureStore(dataflow, *, default_tenant_id=None)`)     | —                                                           |
| Legacy `engines/feature_store.py`, `ConnectionManager`-based       | **CONFIRMED** (ctor `FeatureStore(conn, *, table_prefix="kml_feat_")`) — incompatible | hard-flip would TypeError every caller                      |
| 4 documented caller sites                                          | **CONFIRMED** all 4 present                                                           | see below                                                   |
| (caller list as of 1.1.1)                                          | **2 ADDITIONAL** doc callers found that the issue never enumerated                    | expand scope                                                |
| spec header says "Version 1.1.1"                                   | spec header (`ml-feature-store.md:3`) **STILL says 1.1.1** — stale                    | fix in spec-sync step                                       |

### Full caller sweep (`grep -rln 'from kailash_ml import FeatureStore'`)

Issue-cited (4): `MIGRATION.md` (×3), `README.md`, `.claude/skills/34-kailash-ml/SKILL.md`,
`.claude/skills/02-dataflow/dataflow-ml-integration.md`.
**Newly surfaced (2, not in issue):** `.claude/skills/34-kailash-ml/ml-feature-pipelines.md`,
`.claude/skills/project/ml-quick-reference.md`.
Historical (leave): `packages/kailash-ml/CHANGELOG.md`, `__init__.py` (the `_engine_map` source itself).

## Step 1 acceptance (bridge release 1.8.0 — non-breaking)

1. `_engine_map["FeatureStore"]` keeps **legacy** resolution BUT emits `DeprecationWarning` on
   first top-level access, pointing at `from kailash_ml.features import FeatureStore`.
   (Per zero-tolerance Rule 6a — public-API removal requires a deprecation cycle; this is the
   warning half, not a permanent shim.)
2. Update **all 6** doc/skill caller sites to the canonical import + canonical constructor in
   fresh examples; keep one legacy example with an explicit deprecation banner.
3. Add `packages/kailash-ml/tests/integration/test_feature_store_wiring.py` per
   `rules/facade-manager-detection.md` Rule 1 — exercises `kailash_ml.features.FeatureStore`
   via real `DataFlow` + real Postgres + the `dataflow.ml_feature_source` binding.
   Closes the spec's Wave-6 follow-up at `ml-feature-store.md:352`.
4. Spec-sync: update `ml-feature-store.md` header (line 3, stale 1.1.1) + lines 6/348/352 to
   reflect what shipped. Full sibling re-derivation per specs-authority Rule 5b (the `ml-*.md`
   set + `dataflow-ml-integration.md`).
5. PyPI release cycle for kailash-ml 1.8.0 via `/release` (the one irreversible step — human-gated).

## Open coordination questions for /analyze + /todos to resolve

- **`.claude/skills/` caller updates are loom-synced artifacts.** Updating example imports in
  `SKILL.md` / `ml-feature-pipelines.md` / `dataflow-ml-integration.md` / `ml-quick-reference.md`
  is a BUILD-side edit that flows back via `/sync`. Confirm the edit-here-then-/sync path vs
  a /codify-origination path during /todos. (`ml-quick-reference.md` is `skills/project/` —
  project-local, writable here.)
- **Cross-SDK check (issue acceptance criterion 3):** verify whether kailash-rs has the same
  `features` vs `engines.feature_store` split. This is a cross-repo READ against a private
  Foundation repo — **requires an explicit user gate** per repo-scope-discipline. Surface as a
  user-gated follow-up; do NOT self-authorize.

## Out of scope (do not pull in)

- Step 3 cutover (2.0.0 breaking flip) — later cycle.
- The 5 gate-idiom B1 WARNs (MLDashboard + DataExplorer/ModelVisualizer/ModelExplainer/FeatureEngineer).
- Removing the FeatureStore entry from the gate seed corpus (that's a post-step-3 action).

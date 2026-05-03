# Spec (draft) — Canonical README Quick Start Body for `packages/kailash-ml/README.md`

Version: 1.0.0 (draft)
Status: DRAFT — Phase-E sub-shard E3 artifact for HIGH-11 release-PR prep. Authoritative body for the release-PR rewrite. Not yet landed in `packages/kailash-ml/README.md`.
Package: `kailash-ml` (target: 1.0.0).
Purpose: Canonical README Quick Start section body that the release PR (v0.9.x → 1.0.0) will drop in verbatim, replacing the current 6-import primitive Quick Start.
Companion specs: `ml-engines-v2-draft.md §16` (authoritative Quick Start spec — THIS file implements its §16.1 literal block + §16.3 fingerprint contract).
Related finding: Round-4 cross-spec-consistency HIGH-11 (release-PR prep, `packages/kailash-ml/README.md` version 0.9.0 → 1.0.0 upgrade).
Release-blocking test: `packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py::test_readme_quickstart_fingerprint_matches_spec` — the Tier-2 SHA-256 fingerprint guard specced in `ml-engines-v2-draft.md §16.3`.

---

## 1. Canonical Fingerprint (MUST pin — test compares against this)

The SHA-256 fingerprint of the canonical Python block (literal bytes, LF-terminated) is:

```
c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00
```

Block byte length: 246 bytes. Block line count (non-blank executable Python): 6 lines (inclusive of the dashboard comment line, which is load-bearing per `ml-engines-v2-draft.md §16.2 MUST 1`).

Verification command (reproducible):

```bash
python3 -c "
import hashlib
canonical = '''import kailash_ml as km
async with km.track(\"demo\") as run:
    result = await km.train(df, target=\"y\")
    registered = await km.register(result, name=\"demo\")
server = await km.serve(\"demo@production\")
# \$ kailash-ml-dashboard  (separate shell)
'''
print(hashlib.sha256(canonical.encode()).hexdigest())
# c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00
"
```

**Contract:** Any byte-level drift between this fingerprint and the canonical block embedded in `packages/kailash-ml/README.md` at release-PR merge time fails `test_readme_quickstart_fingerprint_matches_spec`. Fix the README to match this body, OR amend `ml-engines-v2-draft.md §16.1` via a spec-change PR that also updates the `CANONICAL_SHA` constant in the test file and this body — never both in isolation.

---

## 2. Canonical Quick Start Section Body (drop-in for README.md)

The `## Quick Start` section in `packages/kailash-ml/README.md` MUST contain the BODY below VERBATIM. Everything between the `## Quick Start` header and the `## What this does` sub-header is load-bearing. The fingerprint test only guards the first ```python block — but the surrounding prose is equally required for newbie UX and `ml-engines-v2-draft.md §16` compliance.

---

### --- BEGIN CANONICAL BODY ---

## Quick Start

`df` below is any `polars.DataFrame` whose columns include a target you want to predict (supply the column name via `target="..."`).

Install with `pip install kailash-ml`. The following block is executed by CI against a real DataFrame and is the canonical Quick Start for the 1.0.0 release. Every line is load-bearing — do NOT abbreviate it in copy-paste examples on external sites.

```python
import kailash_ml as km
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
# $ kailash-ml-dashboard  (separate shell)
```

### What this does

Each line maps to a single deliberate effect:

- **`import kailash_ml as km`** — imports the package. Every public entry point is a `km.*` function; there are no constructors to wire in the Quick Start (see `specs/ml-engines-v2.md §2.1 MUST 1`, zero-arg construction).
- **`async with km.track("demo") as run:`** — opens an ambient `ExperimentRun` context named `"demo"`. Every `km.train(...)` / `km.register(...)` / checkpoint / metric emitted inside the block is auto-attached to this run (`specs/ml-tracking.md §2.4`). The run finalises (status, end time, artifact manifest) on context exit.
- **`result = await km.train(df, target="y")`** — picks the best model family for the target's dtype and row count, trains it on the chosen backend (CPU / CUDA / MPS / ROCm / XPU / TPU auto-detected per `specs/ml-backends.md`), and returns a `TrainingResult` with populated `metrics` and `device: DeviceReport` (`specs/ml-engines-v2.md §4.2 MUST 1`).
- **`registered = await km.register(result, name="demo")`** — creates a new `ModelVersion` under the logical name `"demo"` (auto-bumped version number), serialises the trained artefact as ONNX by default (`specs/ml-engines-v2.md §2.1 MUST 9`), and returns a `RegisterResult` with `artifact_uris` pointing at the framework-agnostic ONNX + native format pair.
- **`server = await km.serve("demo@production")`** — resolves the `"demo"` model's `production` alias to its current version, spins up a local in-process inference server exposing REST (default) and MCP channels, and returns a `ServeHandle` with `.uris["rest"]`, `.stop()`, and `.status` (`specs/ml-serving.md §2.2`).
- **`# $ kailash-ml-dashboard  (separate shell)`** — invites the reader to launch the optional ML dashboard CLI from a second shell. The dashboard is a non-blocking visualisation surface for runs, models, and serving handles (`specs/ml-dashboard.md`). The comment is retained verbatim because the Quick Start's 5-to-10-line budget (`specs/ml-engines-v2.md §16.2 MUST 1`) accommodates exactly this one-line operational pointer, and newbies otherwise never discover the dashboard exists.

For the full engine surface, multi-tenancy, checkpoint / resume, RL, AutoML, drift monitoring, and production deployment patterns, see the full spec set under `specs/ml-*.md`. The canonical Quick Start is intentionally narrow — it demonstrates the zero-ceremony promise of the 1.0.0 Engine and nothing beyond that.

### --- END CANONICAL BODY ---

---

## 3. Spec Cross-Links (for reviewer convenience — NOT to be copied into README)

The README Quick Start is the user-visible surface. The authoritative specs behind each line:

| Line                                             | Authoritative Spec                   | Reference                                                      |
| ------------------------------------------------ | ------------------------------------ | -------------------------------------------------------------- |
| `import kailash_ml as km`                        | `ml-engines-v2.md`                   | §2.1 MUST 1 (zero-arg construction), §15 (`km.*` wrappers)     |
| `async with km.track("demo") as run:`            | `ml-tracking.md`                     | §2 (ExperimentTracker), §2.4 (ambient-run scope)               |
| `result = await km.train(df, target="y")`        | `ml-engines-v2.md`, `ml-backends.md` | §15.3 (km.train signature), §4.2 (DeviceReport), backends §1-6 |
| `registered = await km.register(result, name=…)` | `ml-engines-v2.md`, `ml-registry.md` | §15.4 (km.register signature), §2.1 MUST 9 (ONNX default)      |
| `server = await km.serve("demo@production")`     | `ml-engines-v2.md`, `ml-serving.md`  | §15.5 (km.serve signature), §2.2 (ServeHandle dispatch)        |
| `# $ kailash-ml-dashboard  (separate shell)`     | `ml-dashboard.md`                    | §8 (CLI entry point)                                           |

Full fingerprint guard + end-to-end test contract: `ml-engines-v2.md §16.3`.

---

## 4. Release-PR Drop-In Procedure (for release-specialist reference)

This is a procedural note — NOT part of the spec body. The release PR executes the following sequence to land this body into `packages/kailash-ml/README.md`:

1. Open `packages/kailash-ml/README.md`.
2. Locate the existing `## Quick Start` section (currently the 6-import primitive form: FeatureStore + ModelRegistry + ExperimentTracker + TrainingPipeline + ConnectionManager + LocalFileArtifactStore).
3. Replace the section with the body in § 2 above, VERBATIM (everything between `--- BEGIN CANONICAL BODY ---` and `--- END CANONICAL BODY ---` exclusive of those two marker lines).
4. Land the Tier-2 regression test `packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py` (full listing in `ml-engines-v2-draft.md §16.3`) with `CANONICAL_SHA = "c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00"`.
5. Run the fingerprint guard locally: `.venv/bin/pytest packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py::test_readme_quickstart_fingerprint_matches_spec -q`. Must pass byte-for-byte before PR submission.
6. Bump `packages/kailash-ml/pyproject.toml` version to `1.0.0` and `packages/kailash-ml/src/kailash_ml/__init__.py::__version__` in the same commit (atomic version consistency per `rules/zero-tolerance.md` Rule 5).

---

## 5. Scope Boundary

This file specifies ONLY the Quick Start section body. The full `packages/kailash-ml/README.md` rewrite (Installation section, Feature overview, Dependencies matrix, Contributing, License) is out of scope for this spec artifact — those sections are authored/reviewed in the release PR directly and are not release-blocking in the same structural sense as the Quick Start. The Quick Start is the single section that carries a cross-SDK fingerprint contract; the rest of the README is ordinary release-PR copy.

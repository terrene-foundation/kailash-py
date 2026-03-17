# /deploy - SDK Release Command

Standalone SDK release command. Not a workspace phase — runs independently after any number of implement/redteam cycles. Handles PyPI publishing, documentation deployment, and CI management for the `kailash` Python SDK and its framework packages.

## Deployment Config

Read `deploy/deployment-config.md` at the project root. This is the single source of truth for how this SDK publishes releases.

## Mode Detection

### If `deploy/deployment-config.md` does NOT exist → Onboard Mode

Run the SDK release onboarding process:

1. **Analyze the codebase**
   - What packages exist? (main `kailash` package + sub-packages like `kailash-dataflow`, `kailash-nexus`, `kailash-kaizen`)
   - What build system? (`pyproject.toml` — setuptools, hatch, maturin, etc.)
   - Existing CI workflows? (`.github/workflows/`)
   - Documentation setup? (sphinx `conf.py`, mkdocs.yml, docs/ directory)
   - Test infrastructure? (pytest config, tox, nox)
   - Multi-package structure? (monorepo vs separate packages)

2. **Ask the human**
   - PyPI publishing strategy: TestPyPI first? Wheel-only (proprietary)?
   - API token setup: `~/.pypirc` or CI secrets?
   - Documentation hosting: ReadTheDocs, GitHub Pages, or other?
   - CI system: GitHub Actions? Self-hosted runners?
   - Multi-package versioning strategy: lockstep or independent?
   - Changelog format: Keep a Changelog, conventional-changelog, or custom?
   - Release cadence: on-demand, scheduled, or tag-triggered?

3. **Research current best practices**
   - Use web search for current PyPI publishing guidance
   - Use web search for current CI/CD patterns for Python packages
   - Check current `build`, `twine`, `maturin` tool versions and syntax
   - Do NOT rely on encoded knowledge — tools and best practices change

4. **Create `deploy/deployment-config.md`**
   - Document all decisions with rationale
   - Include step-by-step SDK release runbook
   - Include rollback procedure (PyPI yank + corrective release)
   - Include release checklist

5. **STOP — present to human for review**

### If `deploy/deployment-config.md` EXISTS → Execute Mode

Read the config and execute the appropriate track:

#### Step 0: Release Scope Detection

Before any release work, determine WHAT needs releasing by analyzing unreleased changes:

1. **Diff analysis** — Compare `main` against the last release tag for each package:

   ```
   git log <last-tag>..HEAD -- src/kailash/           → Core SDK changes?
   git log <last-tag>..HEAD -- packages/kailash-dataflow/  → DataFlow changes?
   git log <last-tag>..HEAD -- packages/kailash-kaizen/    → Kaizen changes?
   git log <last-tag>..HEAD -- packages/kailash-nexus/     → Nexus changes?
   ```

2. **Present release plan to human** — Show which packages have unreleased changes and propose:
   - Which packages to release
   - Version bump type for each (major/minor/patch)
   - Whether framework packages need SDK dependency updates
   - **STOP and wait for human approval before proceeding**

#### Step 1: Version Bump (All Affected Packages)

For each package being released, update version in ALL THREE locations. Missing any location causes install/import mismatches.

##### Core SDK (`kailash`)

| File                      | Field                   | Example                  |
| ------------------------- | ----------------------- | ------------------------ |
| `pyproject.toml`          | `version = "X.Y.Z"`     | `version = "0.13.0"`     |
| `setup.py`                | `version="X.Y.Z"`       | `version="0.13.0"`       |
| `src/kailash/__init__.py` | `__version__ = "X.Y.Z"` | `__version__ = "0.13.0"` |

##### Framework Packages

Each framework has 3 version locations PLUS the SDK dependency pin:

**kailash-dataflow:**

| File                                                 | Field                              |
| ---------------------------------------------------- | ---------------------------------- |
| `packages/kailash-dataflow/pyproject.toml`           | `version = "X.Y.Z"`                |
| `packages/kailash-dataflow/setup.py`                 | `version="X.Y.Z"`                  |
| `packages/kailash-dataflow/src/dataflow/__init__.py` | `__version__ = "X.Y.Z"`            |
| `packages/kailash-dataflow/pyproject.toml`           | `dependencies: kailash>=A.B.C`     |
| `packages/kailash-dataflow/setup.py`                 | `install_requires: kailash>=A.B.C` |

**kailash-kaizen:**

| File                                             | Field                              |
| ------------------------------------------------ | ---------------------------------- |
| `packages/kailash-kaizen/pyproject.toml`         | `version = "X.Y.Z"`                |
| `packages/kailash-kaizen/setup.py`               | `version="X.Y.Z"`                  |
| `packages/kailash-kaizen/src/kaizen/__init__.py` | `__version__ = "X.Y.Z"`            |
| `packages/kailash-kaizen/pyproject.toml`         | `dependencies: kailash>=A.B.C`     |
| `packages/kailash-kaizen/setup.py`               | `install_requires: kailash>=A.B.C` |

**kailash-nexus:**

| File                                           | Field                              |
| ---------------------------------------------- | ---------------------------------- |
| `packages/kailash-nexus/pyproject.toml`        | `version = "X.Y.Z"`                |
| `packages/kailash-nexus/setup.py`              | `version="X.Y.Z"`                  |
| `packages/kailash-nexus/src/nexus/__init__.py` | `__version__ = "X.Y.Z"`            |
| `packages/kailash-nexus/pyproject.toml`        | `dependencies: kailash>=A.B.C`     |
| `packages/kailash-nexus/setup.py`              | `install_requires: kailash>=A.B.C` |

##### SDK Dependency Pin Update Rule

When the core SDK version is bumped, ALL framework packages MUST update their `kailash>=` dependency pin to the new SDK version — even if the framework itself is not being released. This ensures `pip install kailash-dataflow` always pulls the correct minimum SDK.

Also update the main SDK's optional extras in `setup.py` to reference the latest framework versions.

#### Step 2: Version Consistency Verification

After bumping, verify ALL versions are consistent:

```bash
# Core SDK — all three must match
grep 'version' pyproject.toml | head -1
grep 'version=' setup.py | head -1
grep '__version__' src/kailash/__init__.py

# Each framework — version + dependency must be correct
for fw in packages/kailash-dataflow packages/kailash-kaizen packages/kailash-nexus; do
  echo "=== $fw ==="
  grep 'version' $fw/pyproject.toml | head -1
  grep 'version=' $fw/setup.py | head -1
  grep '__version__' $fw/src/*/__init__.py
  grep 'kailash>=' $fw/pyproject.toml
  grep 'kailash>=' $fw/setup.py
done
```

**BLOCK release if any mismatch is found.** Fix before proceeding.

#### Step 3: Pre-release Prep

1. Run full test suite across all supported Python versions
2. Run linting and formatting checks (`black --check`, `ruff check`)
3. Update CHANGELOG.md for each package being released
4. Security review (MANDATORY)
5. **Update README.md** (MANDATORY for minor/major releases)
   - Verify "Why Kailash?" section reflects new capabilities
   - Update architecture diagram version number
   - Verify all feature claims match actual implementation (no overselling)
   - Check that new entry points, CLI commands, or REST endpoints are documented
6. **Verify Sphinx docs build** (MANDATORY)
   - Run `cd docs && python build_docs.py` locally — must succeed
   - Verify new module docstrings appear in API reference
   - Check that docstrings updated during implementation (TODO-035 pattern) are accurate
   - The `docs-deploy.yml` CI workflow auto-deploys on push to main when `docs/**`, `README.md`, or `CHANGELOG.md` change

#### Step 4: Build and Validate

1. Build wheels (and sdist if open-source): `python -m build`
2. For frameworks: `cd apps/kailash-<name> && python -m build`
3. Upload to TestPyPI: `twine upload --repository testpypi dist/*.whl`
4. Verify TestPyPI install in clean venv
5. For major/minor releases: run smoke tests against TestPyPI package

#### Step 5: Git Workflow

1. Commit with conventional message: `chore: release vX.Y.Z`
2. Push (or create PR if protected branch)
3. Watch CI, merge when green

#### Step 6: Publish to Production PyPI

Publish in dependency order — core MUST be available before frameworks:

1. `kailash` (core) → verify available: `pip install kailash==X.Y.Z --dry-run`
2. `kailash-dataflow` → verify available
3. `kailash-nexus` → verify available
4. `kailash-kaizen` → verify available

For each: upload wheels, verify production install in clean venv, create GitHub Release with tag.

#### Step 7: Post-release

1. **Update COC template repo** (MANDATORY)

   The USE repo (`kailash-coc-claude-py`) is the COC template users clone for new projects. Its dependency pins MUST be updated to match the just-published versions, otherwise new projects start with stale SDK versions.

   Update `pyproject.toml` in the USE repo:

   ```
   kailash-coc-claude-py/pyproject.toml
   ```

   Dependency pins to update:

   ```
   "kailash>=X.Y.Z"           → new core SDK version
   "kailash-dataflow>=X.Y.Z"  → new or current DataFlow version
   "kailash-kaizen>=X.Y.Z"    → new or current Kaizen version
   "kailash-nexus>=X.Y.Z"     → new or current Nexus version
   ```

   Commit and push the change to the USE repo with message: `chore: bump SDK dependency pins to latest release`

2. **Verify documentation deployed** (MANDATORY)
   - Check `gh run list --workflow=docs-deploy.yml --limit=1` — must be `completed success`
   - If failed: check logs with `gh run view <id> --log-failed`, fix, and re-trigger
   - Verify live docs at the GitHub Pages URL
   - GitHub Pages must be configured: Settings → Pages → Source: "GitHub Actions"
3. Document release in `deploy/deployments/YYYY-MM-DD-vX.Y.Z.md`
4. Announce if applicable

#### CI Management Track

1. **Monitor CI runs** — `gh run list`, `gh run watch`
2. **Debug CI failures** — download logs, reproduce locally
3. **Manage workflows** — update GitHub Actions, test matrix, runner config

## Package Registry

Quick reference for all version locations in this monorepo:

| Package          | pyproject.toml                             | setup.py                             | **init**.py                                          | SDK Dep     |
| ---------------- | ------------------------------------------ | ------------------------------------ | ---------------------------------------------------- | ----------- |
| kailash          | `pyproject.toml`                           | `setup.py`                           | `src/kailash/__init__.py`                            | —           |
| kailash-dataflow | `packages/kailash-dataflow/pyproject.toml` | `packages/kailash-dataflow/setup.py` | `packages/kailash-dataflow/src/dataflow/__init__.py` | `kailash>=` |
| kailash-kaizen   | `packages/kailash-kaizen/pyproject.toml`   | `packages/kailash-kaizen/setup.py`   | `packages/kailash-kaizen/src/kaizen/__init__.py`     | `kailash>=` |
| kailash-nexus    | `packages/kailash-nexus/pyproject.toml`    | `packages/kailash-nexus/setup.py`    | `packages/kailash-nexus/src/nexus/__init__.py`       | `kailash>=` |

## Agent Teams

- **deployment-specialist** — Analyze codebase, run onboarding, guide SDK release
- **git-release-specialist** — Git workflow, PR creation, version management
- **security-reviewer** — Pre-release security audit (MANDATORY)
- **testing-specialist** — Verify test coverage before release
- **documentation-validator** — Verify documentation builds and code examples

## Critical Rules

- NEVER publish to PyPI without running the full test suite first
- NEVER skip TestPyPI validation for major or minor releases
- NEVER commit PyPI tokens to source — use `~/.pypirc` or CI secrets
- NEVER skip security review before publishing
- NEVER release a framework without updating its `kailash>=` dependency to match the current SDK version
- ALWAYS update version in ALL THREE locations (pyproject.toml, setup.py, **init**.py)
- ALWAYS verify the published package installs correctly in a clean venv
- ALWAYS publish in dependency order: core SDK first, then frameworks
- ALWAYS document releases in `deploy/deployments/`
- ALWAYS update the COC template repo (`kailash-coc-claude-py/pyproject.toml`) dependency pins after publishing
- Research current tool syntax — do not assume stale knowledge is correct

**Automated enforcement**: `validate-deployment.js` hook automatically blocks commits containing credentials (AWS keys, Azure secrets, GCP service account JSON, private keys, GitHub/PyPI/Docker tokens) in deployment files.

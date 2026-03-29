# /release - SDK Release Command

Standalone SDK release command for the BUILD repo. Not a workspace phase — runs independently after any number of implement/redteam cycles. Handles PyPI publishing, documentation deployment, and CI management for the `kailash` Python SDK and its framework packages.

**IMPORTANT**: This is `/release` (BUILD repo command). `/deploy` is for USE repos only. See `rules/zero-tolerance.md` for the BUILD vs USE boundary.

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

For each package being released, update version in BOTH locations. Missing either causes install/import mismatches that break users.

**CRITICAL**: The `__version__` in `__init__.py` MUST match `pyproject.toml`. This is the #1 source of "my package didn't update" complaints. The session-start hook verifies this automatically.

##### Core SDK (`kailash`)

| File                      | Field                   | Example                 |
| ------------------------- | ----------------------- | ----------------------- |
| `pyproject.toml`          | `version = "X.Y.Z"`     | `version = "1.0.0"`     |
| `src/kailash/__init__.py` | `__version__ = "X.Y.Z"` | `__version__ = "1.0.0"` |

##### Framework Packages

Each framework has 2 version locations PLUS the SDK dependency pin:

**kailash-dataflow:**

| File                                                 | Field                          |
| ---------------------------------------------------- | ------------------------------ |
| `packages/kailash-dataflow/pyproject.toml`           | `version = "X.Y.Z"`            |
| `packages/kailash-dataflow/src/dataflow/__init__.py` | `__version__ = "X.Y.Z"`        |
| `packages/kailash-dataflow/pyproject.toml`           | `dependencies: kailash>=A.B.C` |

**kailash-kaizen:**

| File                                             | Field                          |
| ------------------------------------------------ | ------------------------------ |
| `packages/kailash-kaizen/pyproject.toml`         | `version = "X.Y.Z"`            |
| `packages/kailash-kaizen/src/kaizen/__init__.py` | `__version__ = "X.Y.Z"`        |
| `packages/kailash-kaizen/pyproject.toml`         | `dependencies: kailash>=A.B.C` |

**kailash-nexus:**

| File                                           | Field                          |
| ---------------------------------------------- | ------------------------------ |
| `packages/kailash-nexus/pyproject.toml`        | `version = "X.Y.Z"`            |
| `packages/kailash-nexus/src/nexus/__init__.py` | `__version__ = "X.Y.Z"`        |
| `packages/kailash-nexus/pyproject.toml`        | `dependencies: kailash>=A.B.C` |

##### SDK Dependency Pin Update Rule

When the core SDK version is bumped, ALL framework packages MUST update their `kailash>=` dependency pin to the new SDK version — even if the framework itself is not being released. This ensures `pip install kailash-dataflow` always pulls the correct minimum SDK.

Also update the main SDK's optional extras in `pyproject.toml` to reference the latest framework versions.

#### Step 2: Version Consistency Verification

After bumping, verify ALL versions are consistent:

**Full reference**: `.claude/skills/management/release-checklist.md`

# /deploy - SDK Release Command

Standalone SDK release command. Not a workspace phase — runs independently after any number of implement/redteam cycles. Handles PyPI publishing, documentation deployment, and CI management for the `kailash` Python SDK.

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

#### Package Release Track

1. **Pre-release prep**
   - Run full test suite across all supported Python versions
   - Run linting and formatting checks
   - Update CHANGELOG.md with release entry
   - Bump version in `pyproject.toml` and any `__version__` references
   - Ensure version consistency across all sub-packages
   - Security review

2. **Build and validate**
   - Build wheels (and sdist if open-source): `python -m build`
   - Upload to TestPyPI: `twine upload --repository testpypi dist/*.whl`
   - Verify TestPyPI install in clean venv
   - For major/minor releases: run smoke tests against TestPyPI package

3. **Git workflow**
   - Commit with conventional message: `chore: release vX.Y.Z`
   - Push (or create PR if protected branch)
   - Watch CI, merge when green

4. **Publish to production PyPI**
   - Upload wheels: `twine upload dist/*.whl`
   - Verify production install in clean venv
   - Create GitHub Release with tag and release notes

5. **Post-release**
   - Deploy documentation (ReadTheDocs trigger or manual)
   - Document release in `deploy/deployments/YYYY-MM-DD-vX.Y.Z.md`
   - Announce if applicable

#### CI Management Track

1. **Monitor CI runs** — `gh run list`, `gh run watch`
2. **Debug CI failures** — download logs, reproduce locally
3. **Manage workflows** — update GitHub Actions, test matrix, runner config

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
- ALWAYS verify the published package installs correctly in a clean venv
- ALWAYS document releases in `deploy/deployments/`
- Research current tool syntax — do not assume stale knowledge is correct

**Automated enforcement**: `validate-deployment.js` hook automatically blocks commits containing credentials (AWS keys, Azure secrets, GCP service account JSON, private keys, GitHub/PyPI/Docker tokens) in deployment files.

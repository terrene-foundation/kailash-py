# /release - SDK Release Command

Standalone SDK release command for the BUILD repo. Not a workspace phase -- runs independently after any number of implement/redteam cycles. Handles PyPI publishing, documentation deployment, and CI management for the `kailash` Python SDK and its framework packages.

**IMPORTANT**: This is `/release` (BUILD repo command). `/deploy` is for USE repos only.

## Deployment Config

Read `deploy/deployment-config.md` at the project root. This is the single source of truth for how this SDK publishes releases.

## Mode Detection

### If `deploy/deployment-config.md` does NOT exist -> Onboard Mode

Run the SDK release onboarding process:

1. **Analyze the codebase** -- packages, build system, CI workflows, docs setup, test infrastructure, multi-package structure
2. **Ask the human** -- PyPI strategy, token setup, docs hosting, CI system, versioning strategy, changelog format, release cadence
3. **Research current best practices** -- web search for current PyPI/CI/build tool guidance. Do NOT rely on encoded knowledge.
4. **Create `deploy/deployment-config.md`** -- document all decisions with rationale, step-by-step runbook, rollback procedure, release checklist
5. **STOP -- present to human for review**

### If `deploy/deployment-config.md` EXISTS -> Execute Mode

Read the config and execute:

#### Step 0: Release Scope Detection

1. **Diff analysis** -- compare `main` against last release tag per package:
   ```
   git log <last-tag>..HEAD -- kailash/           # Core SDK changes?
   git log <last-tag>..HEAD -- kailash-dataflow/   # DataFlow changes?
   git log <last-tag>..HEAD -- kailash-kaizen/     # Kaizen changes?
   git log <last-tag>..HEAD -- kailash-nexus/      # Nexus changes?
   ```
2. **Present release plan** -- which packages, version bump type, dependency updates. **STOP and wait for human approval.**

#### Step 1: Version Bump

Update version in BOTH `pyproject.toml` AND `__init__.py` for each package. The `__version__` MUST match `pyproject.toml` -- this is the #1 source of "my package didn't update" complaints.

For detailed version locations, dependency pin rules, and verification commands, see `skills/10-deployment-git/release-runbook.md`.

#### Step 2: Version Consistency Verification

Run the verification script from the release runbook. **BLOCK release if any mismatch.**

#### Step 3: Pre-Release Prep

Run tests, linting, CHANGELOG, security review, README update (MANDATORY for minor/major), Sphinx docs build verification. See release runbook for full checklist.

#### Step 4: Build and Validate

Build wheels, upload to TestPyPI, verify install in clean venv. See release runbook.

#### Step 5: Git Workflow

Create release branch, PR, merge, tag on main. Tags trigger publish-pypi.yml. See release runbook.

#### Step 6: Publish to Production PyPI

Publish in dependency order: core first, then frameworks. See release runbook.

#### Step 7: Post-Release

Update COC template repo pins, verify docs deployed, document release. See release runbook.

## Agent Teams

- **release-specialist** -- Analyze codebase, run onboarding, guide SDK release
- **release-specialist** -- Git workflow, PR creation, version management
- **security-reviewer** -- Pre-release security audit (MANDATORY)
- **testing-specialist** -- Verify test coverage before release
- **reviewer** -- Verify documentation builds and code examples

## Critical Rules

- NEVER publish without full test suite passing
- NEVER skip TestPyPI for major/minor releases
- NEVER commit PyPI tokens -- use `~/.pypirc` or CI secrets
- NEVER skip security review before publishing
- NEVER release a framework without updating its `kailash>=` dependency
- ALWAYS update version in BOTH locations (pyproject.toml AND __init__.py)
- ALWAYS verify published package installs in clean venv
- ALWAYS publish in dependency order: core SDK first, then frameworks
- ALWAYS document releases in `deploy/deployments/`
- ALWAYS update COC template repo dependency pins after publishing
- Research current tool syntax -- do not assume stale knowledge is correct

**Automated enforcement**: `validate-deployment.js` hook blocks commits containing credentials in deployment files.

## Skill References

- `skills/10-deployment-git/release-runbook.md` -- Version tables, step-by-step procedures, verification commands
- `skills/10-deployment-git/deployment-packages.md` -- Package release patterns
- `skills/10-deployment-git/deployment-ci.md` -- CI/CD infrastructure

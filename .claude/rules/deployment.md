# SDK Release Rules

## Scope

These rules apply to all SDK release operations and release-related files (`deploy/**`, `.github/workflows/**`, `pyproject.toml`, `CHANGELOG.md`).

## MUST Rules

### 1. Full Test Suite Before Release

All releases MUST pass the full test suite across all supported Python versions before publishing.

```bash
# Run full test matrix
pytest
# Or via tox/nox if configured
tox
```

**Enforced by**: deployment-specialist agent, CI pipeline
**Violation**: BLOCK release

### 2. TestPyPI Validation Before Production PyPI

Major and minor releases MUST be validated on TestPyPI before publishing to production PyPI.

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*.whl

# Verify install
python -m venv /tmp/verify --clear
/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ kailash==X.Y.Z
/tmp/verify/bin/python -c "import kailash; print(kailash.__version__)"
```

**Exception**: Patch releases (bug fixes only) may skip TestPyPI with explicit human approval.

### 3. Version Consistency Across All Packages

All packages in the SDK MUST have consistent, compatible versions before release.

**Check**:

- `pyproject.toml` version field in each package
- `__version__` in `__init__.py` files
- Cross-package dependency version pins

### 4. CHANGELOG.md Updated for Every Release

Every release MUST have a corresponding entry in `CHANGELOG.md` with:

- Version number and date
- Added, Changed, Fixed, Removed sections as applicable
- Breaking changes clearly marked

### 5. Security Review Before Publishing

Security review by **security-reviewer** is MANDATORY before any PyPI publish.

**Check for**:

- No hardcoded secrets in package source
- No sensitive data in wheel contents
- Dependencies are pinned and audited
- No known vulnerabilities in dependencies

**Enforced by**: agents.md Rule 2, validate-deployment.js hook
**Violation**: BLOCK release

### 6. Wheel-Only Publishing for Proprietary Code

Proprietary packages MUST publish wheels only — never sdist (source distribution).

```bash
# Correct: wheels only
twine upload dist/*.whl

# Incorrect for proprietary code
❌ twine upload dist/*        # includes .tar.gz sdist
❌ twine upload dist/*.tar.gz  # sdist exposes source
```

### 7. Release Config Documented

Every SDK that publishes releases MUST have `deploy/deployment-config.md` at the project root. Run `/deploy` to create it via the onboarding process.

### 8. Research Before Executing

PyPI tooling and CI patterns change frequently. MUST verify current syntax via web search or `--help` before running release commands. Do NOT rely on memorized commands that may be outdated.

## MUST NOT Rules

### 1. No Publishing Without CI Green

MUST NOT publish to PyPI when CI is failing. All checks must pass first.

### 2. No Skipping TestPyPI for Major/Minor Releases

MUST NOT skip TestPyPI validation for major (X.0.0) or minor (X.Y.0) releases. These carry higher risk of breaking changes.

### 3. No PyPI Tokens in Source

MUST NOT commit PyPI tokens or credentials to source control.

**Correct**:

- `~/.pypirc` (local, gitignored)
- CI secrets (GitHub Actions secrets)
- Trusted publisher (OIDC — no tokens needed)

**Incorrect**:

```
❌ TWINE_PASSWORD=pypi-... in .env
❌ TWINE_PASSWORD=pypi-... in CI config files
❌ ~/.pypirc committed to repo
```

**Enforced by**: validate-deployment.js hook, security-reviewer agent
**Violation**: BLOCK commit

### 4. No Publishing Without Version Bump

MUST NOT publish a release without bumping the version number. PyPI does not allow overwriting existing versions.

### 5. No Uncommitted Changes During Release

MUST NOT publish from a dirty working tree. All changes must be committed and pushed before building release artifacts.

## Release Checklist

Before any SDK release:

- [ ] All tests pass (full matrix: Python versions x OS)
- [ ] Security review completed
- [ ] CHANGELOG.md updated with release entry
- [ ] Version bumped consistently across all packages
- [ ] Linting and formatting checks pass
- [ ] TestPyPI validation passed (required for major/minor)
- [ ] Production PyPI publish successful
- [ ] Clean venv install verification passed
- [ ] GitHub Release created with release notes
- [ ] Documentation deployed and verified
- [ ] Release logged in `deploy/deployments/`

## Exceptions

Release rule exceptions require:

1. Explicit human approval
2. Documentation in deployment-config.md
3. Justification (e.g., critical hotfix skipping TestPyPI)

# EATP Deployment Configuration

Package: `eatp`
Created: 2026-03-12
Last updated: 2026-03-12

## Package Summary

| Field              | Value                                                             |
| ------------------ | ----------------------------------------------------------------- |
| PyPI name          | `eatp`                                                            |
| Current version    | `0.1.0`                                                           |
| Status             | First release — never published to PyPI                           |
| License            | Apache-2.0 (Terrene Foundation)                                   |
| Python requirement | `>=3.11`                                                          |
| Build backend      | hatchling (NOT setuptools)                                        |
| Package directory  | `packages/eatp/` (inside `terrene-foundation/kailash_python_sdk`) |
| Tag format         | `eatp-v0.1.0`                                                     |
| Distribution       | Wheel + sdist                                                     |
| Authentication     | API token (OIDC migration pending — see Known Issues)             |

## Version Locations (2 only — no setup.py)

| File                                 | Field         | Current Value |
| ------------------------------------ | ------------- | ------------- |
| `packages/eatp/pyproject.toml`       | `version`     | `0.1.0`       |
| `packages/eatp/src/eatp/__init__.py` | `__version__` | `0.1.0`       |

Both locations must always match. There is no `setup.py` — hatchling reads version only from `pyproject.toml`.

## Build System Notes

EATP uses hatchling, which differs from the other packages in this monorepo (which use setuptools).

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/eatp"]
```

`python -m build` works identically to the setuptools packages — the difference is invisible to the build frontend. When debugging build failures, check hatchling-specific config under `[tool.hatch.*]` in `pyproject.toml`.

## Dependencies

| Dependency         | Pin   | Purpose                            |
| ------------------ | ----- | ---------------------------------- |
| `pynacl>=1.5`      | lower | Ed25519 cryptographic primitives   |
| `pydantic>=2.6`    | lower | Trust chain model validation       |
| `jsonschema>=4.21` | lower | Wire format JSON schema validation |
| `click>=8.0`       | lower | CLI (10 commands)                  |

Optional extras:

- `eatp[postgres]`: adds `asyncpg>=0.29`, `sqlalchemy[asyncio]>=2.0`
- `eatp[all]`: same as postgres

EATP has **no dependency on `kailash`**. It is an independent package.

## Known Issues Before First Publish

### 1. pyproject.toml URLs point to a non-existent repository

`packages/eatp/pyproject.toml` currently lists:

```toml
[project.urls]
Documentation = "https://docs.terrenefoundation.org/eatp"
Repository = "https://github.com/terrene-foundation/eatp-python"
Issues = "https://github.com/terrene-foundation/eatp-python/issues"
```

`https://github.com/terrene-foundation/eatp-python` does not exist. The actual source is in `terrene-foundation/kailash_python_sdk` under `packages/eatp/`. Users who click these links from the PyPI project page will hit 404s.

**Required fix before publishing:**

```toml
[project.urls]
Documentation = "https://docs.terrenefoundation.org/eatp"
Repository = "https://github.com/terrene-foundation/kailash_python_sdk/tree/main/packages/eatp"
Issues = "https://github.com/terrene-foundation/kailash_python_sdk/issues"
```

### 2. CI workflow not yet wired for EATP

`publish-pypi.yml` does not handle `eatp-v*` tags. Tag-triggered publishing will silently do nothing until the workflow is updated.

**Required diff for `.github/workflows/publish-pypi.yml`:**

```diff
 on:
   push:
     tags:
       - "v*"
       - "dataflow-v*"
       - "kaizen-v*"
       - "nexus-v*"
+      - "eatp-v*"
   workflow_dispatch:
     inputs:
       package:
         description: "Package to publish"
         type: choice
         options:
           - kailash
           - kailash-dataflow
           - kailash-kaizen
           - kailash-nexus
+          - eatp
```

In the `determine-package` job's tag-parsing step, add before the final `elif` for `v*`:

```diff
+            elif [[ "$TAG" =~ ^eatp-v(.+)$ ]]; then
+              echo "package=eatp" >> $GITHUB_OUTPUT
+              echo "package_dir=packages/eatp" >> $GITHUB_OUTPUT
+              VERSION="${BASH_REMATCH[1]}"
```

And in the `workflow_dispatch` case block:

```diff
+              eatp)              echo "package_dir=packages/eatp" >> $GITHUB_OUTPUT ;;
```

### 3. Authentication uses API tokens, not OIDC

The CI workflow uses `PYPI_API_TOKEN` and `TESTPYPI_API_TOKEN` secrets. OIDC trusted publisher was the intended approach for EATP but is not yet implemented in the workflow. API tokens work correctly for publishing; OIDC migration is a future improvement.

If migrating to OIDC for EATP, register a trusted publisher on both pypi.org and test.pypi.org with:

- Owner: `terrene-foundation`
- Repository: `kailash_python_sdk`
- Workflow filename: `publish-pypi.yml`
- Environment: `pypi` (production) or `testpypi` (test)

## Pre-Release Checklist (First Release — v0.1.0)

### Blockers (all resolved for v0.1.0)

- [x] Fix `pyproject.toml` URLs to point to `terrene-foundation/kailash_python_sdk`
- [x] Update `publish-pypi.yml` to handle `eatp-v*` tags
- [x] Ensure `PYPI_API_TOKEN` secret in GitHub has permission to create new packages
- [x] Ensure `TESTPYPI_API_TOKEN` secret in GitHub has permission to create new packages

### Standard checks (all passed for v0.1.0)

- [x] All 1557 tests pass (`cd packages/eatp && pytest`)
- [x] Security review completed (security-reviewer agent)
- [x] `CHANGELOG.md` has entry for 0.1.0
- [x] Version consistent: `pyproject.toml` and `src/eatp/__init__.py` both show `0.1.0`
- [x] TestPyPI validation passed
- [x] Clean venv install verification passed
- [x] Production PyPI install verification passed

## Release Runbook

### Step 1: Resolve blockers

Fix the `pyproject.toml` URLs and update the CI workflow as described in Known Issues above. Commit and push to main via PR.

### Step 2: Verify versions

```bash
grep '^version' packages/eatp/pyproject.toml
grep '__version__' packages/eatp/src/eatp/__init__.py
```

Both must show `0.1.0`.

### Step 3: Run tests

```bash
cd packages/eatp
pytest
```

All tests must pass. The test suite uses `asyncio_mode = "auto"` — no special flags needed.

### Step 4: Build artifacts

```bash
cd packages/eatp
python -m build
```

This produces in `packages/eatp/dist/`:

- `eatp-0.1.0-py3-none-any.whl`
- `eatp-0.1.0.tar.gz`

Note: A pre-built `dist/` already exists from a prior `python -m build` run. Rebuild fresh before publishing to avoid stale artifacts.

### Step 5: Publish to TestPyPI

```bash
python -m twine upload --repository-url https://test.pypi.org/legacy/ packages/eatp/dist/*
```

With CI: use `workflow_dispatch` on `publish-pypi.yml` → package=`eatp`, target=`testpypi`.

### Step 6: Verify TestPyPI install

```bash
python -m venv /tmp/eatp-verify --clear
/tmp/eatp-verify/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  eatp==0.1.0
/tmp/eatp-verify/bin/python -c "import eatp; print(eatp.__version__)"
/tmp/eatp-verify/bin/eatp version
```

Expected output: `0.1.0`

### Step 7: Push production tag

```bash
git tag eatp-v0.1.0
git push origin eatp-v0.1.0
```

CI will detect the `eatp-v*` tag, build, and publish to production PyPI.

### Step 8: Verify production PyPI install

```bash
python -m venv /tmp/eatp-prod-verify --clear
/tmp/eatp-prod-verify/bin/pip install eatp==0.1.0
/tmp/eatp-prod-verify/bin/python -c "import eatp; print(eatp.__version__)"
/tmp/eatp-prod-verify/bin/eatp version
```

### Step 9: Create GitHub Release

CI creates the GitHub Release automatically on tag push (via `gh release create` in the workflow). Verify it was created at:
`https://github.com/terrene-foundation/kailash_python_sdk/releases/tag/eatp-v0.1.0`

Review the auto-generated notes and edit if needed.

### Step 10: Log the release

Create `packages/eatp/deploy/deployments/0.1.0.md` documenting what was published.

## Rollback Procedure

PyPI does not allow overwriting published versions.

1. **Yank the bad version** (hides from default `pip install`, preserves explicit pins):
   - Via PyPI web UI: `https://pypi.org/project/eatp/` → Manage → 0.1.0 → Options → Yank
   - Or: `twine yank eatp==0.1.0`

2. **Publish corrective release** `0.1.1` with the fix applied.

3. **Update `CHANGELOG.md`** with yank notice and corrective release entry.

4. **Announce** via GitHub Release notes on the corrective release.

## Future Considerations

- **CLI entry point**: EATP ships a `[project.scripts]` entry `eatp = "eatp.cli:main"`. Verify the CLI installs correctly in the clean venv verification step.
- **Optional dependencies**: `eatp[postgres]` adds `asyncpg` + `sqlalchemy`. Tests marked `@pytest.mark.postgres` are skipped unless a PostgreSQL instance is available. These are excluded from the standard CI run.
- **Documentation**: `mkdocs.yml` exists at `packages/eatp/mkdocs.yml`. Documentation is not yet deployed. When deploying, the base URL path must account for the monorepo layout.
- **OIDC migration**: Preferred long-term. Token-based auth works for now but OIDC eliminates token rotation risk.

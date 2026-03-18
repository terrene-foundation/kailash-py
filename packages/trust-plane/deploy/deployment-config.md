# TrustPlane Deployment Configuration

Package: `trust-plane`
Created: 2026-03-15
Last updated: 2026-03-18

## Package Summary

| Field              | Value                                                                    |
| ------------------ | ------------------------------------------------------------------------ |
| PyPI name          | `trust-plane`                                                            |
| Current version    | `0.2.1`                                                                  |
| Status             | Published on PyPI (v0.2.0, 2026-03-15)                                   |
| License            | Apache-2.0 (Terrene Foundation)                                          |
| Python requirement | `>=3.11`                                                                 |
| Build backend      | hatchling (NOT setuptools)                                               |
| Package directory  | `packages/trust-plane/` (inside `terrene-foundation/kailash_python_sdk`) |
| Tag format         | `trust-plane-v0.2.0`                                                     |
| Distribution       | Wheel + sdist (open source, Apache-2.0)                                  |
| Authentication     | API token (OIDC migration pending)                                       |

## Version Locations (2 only — no setup.py)

| File                                              | Field         | Current Value |
| ------------------------------------------------- | ------------- | ------------- |
| `packages/trust-plane/pyproject.toml`             | `version`     | `0.2.0`       |
| `packages/trust-plane/src/trustplane/__init__.py` | `__version__` | `0.2.0`       |

Both locations must always match. There is no `setup.py` — hatchling reads version only from `pyproject.toml`.

## Build System Notes

TrustPlane uses hatchling (same as EATP), which differs from the other packages in this monorepo (which use setuptools).

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/trustplane"]
```

`python -m build` works identically to the setuptools packages — the difference is invisible to the build frontend. When debugging build failures, check hatchling-specific config under `[tool.hatch.*]` in `pyproject.toml`.

**Dev dependency note**: `pyproject.toml` contains a local path reference for development:

```toml
[tool.hatch.envs.default]
dependencies = [
    "eatp @ {root:uri}/../eatp",
]
```

This is a hatch development environment config only — it does NOT affect the published wheel. The published package depends on `eatp>=0.1.0,<1.0.0` from PyPI.

## Dependencies

| Dependency | Pin              | Purpose                                       |
| ---------- | ---------------- | --------------------------------------------- |
| `eatp`     | `>=0.1.0,<1.0.0` | EATP trust protocol (MUST be published first) |
| `click`    | `>=8.0`          | CLI framework (`attest` command)              |
| `filelock` | `>=3.0`          | Cross-process file locking                    |
| `mcp`      | `>=1.0.0`        | MCP server (`trustplane-mcp`)                 |

Optional extras:

- `trust-plane[dev]`: adds `pytest>=7.0`, `pytest-asyncio>=0.21`
- `trust-plane[postgres]`: adds `psycopg[binary]>=3.0`, `psycopg_pool>=3.0`
- `trust-plane[aws]`: adds `boto3>=1.26`
- `trust-plane[azure]`: adds `azure-keyvault-keys>=4.8`, `azure-identity>=1.12`
- `trust-plane[vault]`: adds `hvac>=2.0`
- `trust-plane[encryption]`: adds `cryptography>=41.0`
- `trust-plane[sso]`: adds `PyJWT>=2.8`, `cryptography>=41.0`
- `trust-plane[windows]`: adds `pywin32` (Windows only)

**Critical dependency**: EATP (`eatp>=0.1.0`) MUST be available on PyPI before trust-plane can be published. EATP v0.1.0 is already published: https://pypi.org/project/eatp/0.1.0/

## Known Issues

### 1. Authentication uses API tokens, not OIDC

The CI workflow uses `PYPI_API_TOKEN` and `TESTPYPI_API_TOKEN` secrets (same as EATP). OIDC trusted publisher migration is a future improvement — not a blocker for publishing.

## Pre-Release Checklist (First Release — v0.2.0)

### Blockers (all resolved for v0.2.0)

- [x] Add `[project.urls]` to `pyproject.toml`
- [x] Update `publish-pypi.yml` to handle `trust-plane-v*` tags
- [x] `CHANGELOG.md` exists with entry for 0.2.0
- [x] Version consistent: `pyproject.toml` and `src/trustplane/__init__.py` both show `0.2.0`
- [x] PyPI API token has permission to create new packages
- [x] TestPyPI API token works for new package registration

### Standard checks (all passed for v0.2.0)

- [x] All 1473 tests pass (`cd packages/trust-plane && pytest`)
- [x] Security review completed (security-reviewer agent)
- [x] TestPyPI validation passed
- [x] Clean venv install verification passed
- [x] Production PyPI install verification passed

## Release Runbook

### Step 1: Verify blockers resolved

Confirm `[project.urls]` exists in `pyproject.toml` and `publish-pypi.yml` handles `trust-plane-v*` tags. Both were resolved on 2026-03-15.

### Step 2: Verify versions

```bash
grep '^version' packages/trust-plane/pyproject.toml
grep '__version__' packages/trust-plane/src/trustplane/__init__.py
```

Both must show `0.2.0`.

### Step 3: Run tests

```bash
cd packages/trust-plane
pytest
```

All 1473 tests must pass. The test suite uses `asyncio_mode = "auto"` — no special flags needed.

### Step 4: Build artifacts

```bash
cd packages/trust-plane
python -m build
```

This produces in `packages/trust-plane/dist/`:

- `trust_plane-0.2.0-py3-none-any.whl`
- `trust_plane-0.2.0.tar.gz`

### Step 5: Publish to TestPyPI

```bash
python -m twine upload --repository-url https://test.pypi.org/legacy/ packages/trust-plane/dist/*
```

With CI: use `workflow_dispatch` on `publish-pypi.yml` -> package=`trust-plane`, target=`testpypi`.

### Step 6: Verify TestPyPI install

```bash
python -m venv /tmp/tp-verify --clear
/tmp/tp-verify/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  trust-plane==0.2.0
/tmp/tp-verify/bin/python -c "import trustplane; print(trustplane.__version__)"
/tmp/tp-verify/bin/attest --help
```

Expected output: `0.2.0` and the CLI help page.

### Step 7: Push production tag

```bash
git tag trust-plane-v0.2.0
git push origin trust-plane-v0.2.0
```

CI will detect the `trust-plane-v*` tag, build, and publish to production PyPI.

### Step 8: Verify production PyPI install

```bash
python -m venv /tmp/tp-prod-verify --clear
/tmp/tp-prod-verify/bin/pip install trust-plane==0.2.0
/tmp/tp-prod-verify/bin/python -c "import trustplane; print(trustplane.__version__)"
/tmp/tp-prod-verify/bin/attest --help
```

### Step 9: Create GitHub Release

CI creates the GitHub Release automatically on tag push. Verify at:
`https://github.com/terrene-foundation/kailash_python_sdk/releases/tag/trust-plane-v0.2.0`

### Step 10: Log the release

Create `packages/trust-plane/deploy/deployments/0.2.0.md` documenting what was published.

## Rollback Procedure

PyPI does not allow overwriting published versions.

1. **Yank the bad version** (hides from default `pip install`, preserves explicit pins):
   - Via PyPI web UI: `https://pypi.org/project/trust-plane/` -> Manage -> 0.2.0 -> Options -> Yank
   - Or: `twine yank trust-plane==0.2.0`

2. **Publish corrective release** `0.2.1` with the fix applied.

3. **Update `CHANGELOG.md`** with yank notice and corrective release entry.

4. **Announce** via GitHub Release notes on the corrective release.

## Dependency Publishing Order

TrustPlane depends on EATP. When both packages are releasing simultaneously:

1. Publish `eatp` first -> verify available on PyPI
2. Publish `trust-plane` second -> it can resolve `eatp>=0.1.0` from PyPI

Never publish trust-plane before its EATP dependency is available.

## Future Considerations

- **CLI entry points**: TrustPlane ships two `[project.scripts]` entries: `attest` (CLI) and `trustplane-mcp` (MCP server). Verify both install correctly in clean venv.
- **Optional dependencies**: 7 optional extras cover postgres, cloud KMS providers, encryption, SSO, and Windows. Tests for cloud providers require credentials and are skipped in standard CI.
- **Documentation**: No Sphinx/MkDocs config exists yet. Markdown documentation is in `packages/trust-plane/`. Deploy documentation hosting when needed.
- **OIDC migration**: Preferred long-term. Token-based auth works for now but OIDC eliminates token rotation risk.
- **CHANGELOG.md**: Exists with entries for v0.1.0 and v0.2.0.

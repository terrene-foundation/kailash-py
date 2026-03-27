# Release Checklist Reference

Reference material for the /release command.


```bash
# Core SDK — both must match
grep 'version' pyproject.toml | head -1
grep '__version__' src/kailash/__init__.py

# Each framework — version + dependency must be correct
for fw in packages/kailash-dataflow packages/kailash-kaizen packages/kailash-nexus; do
  echo "=== $fw ==="
  grep 'version' $fw/pyproject.toml | head -1
  grep '__version__' $fw/src/*/__init__.py
  grep 'kailash>=' $fw/pyproject.toml
done
```

**BLOCK release if any mismatch is found.** Fix before proceeding.

#### Step 3: Pre-release Prep

1. Run full test suite across all supported Python versions
2. Run linting and formatting checks (`black --check`, `ruff check`)
3. Update CHANGELOG.md for each package being released
4. Security review (MANDATORY)
5. **Update README.md** (MANDATORY for minor/major releases — BLOCKS release if skipped)
   - Verify "Why Kailash?" section reflects new capabilities added in this release
   - Update architecture diagram version number to match release version
   - Verify all feature claims match actual implementation (no overselling — R4 audit checks this)
   - Check that new entry points, CLI commands, or REST endpoints are documented
   - Run: `grep -c 'v0.XX.X' README.md` to confirm version appears
   - **BLOCK release if README still references old version or omits major new features**
6. **Verify Sphinx docs build** (MANDATORY — BLOCKS release if build fails)
   - Run `cd docs && python build_docs.py` locally — must succeed with zero errors
   - Verify new module docstrings appear in API reference (spot-check 3 new modules)
   - Check that docstrings updated during implementation are accurate (no stale "TODO" or "simulated" claims)
   - The `docs-deploy.yml` CI workflow auto-deploys on push to main when `docs/**`, `README.md`, or `CHANGELOG.md` change
   - **BLOCK release if Sphinx build fails or new modules are missing from API reference**

#### Step 4: Build and Validate

1. Build wheels (and sdist if open-source): `python -m build`
2. For frameworks: `cd apps/kailash-<name> && python -m build`
3. Upload to TestPyPI: `twine upload --repository testpypi dist/*.whl`
4. Verify TestPyPI install in clean venv
5. For major/minor releases: run smoke tests against TestPyPI package

#### Step 5: Git Workflow

Main branch is protected — all changes require a PR with review.

1. Create release branch: `git checkout -b release/vX.Y.Z`
2. Commit with conventional message: `chore: release vX.Y.Z`
3. Push branch: `git push -u origin release/vX.Y.Z`
4. Create PR: `gh pr create --title "chore: release vX.Y.Z" --body "..."`
5. Wait for CI to pass, then merge (admin can self-approve)
6. After merge, tag on main: `git checkout main && git pull && git tag -a vX.Y.Z -m "..." && git push --tags`
7. Tags trigger the publish-pypi.yml workflow automatically

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

| Package          | pyproject.toml                             | **init**.py                                          | SDK Dep     |
| ---------------- | ------------------------------------------ | ---------------------------------------------------- | ----------- |
| kailash          | `pyproject.toml`                           | `src/kailash/__init__.py`                            | —           |
| kailash-dataflow | `packages/kailash-dataflow/pyproject.toml` | `packages/kailash-dataflow/src/dataflow/__init__.py` | `kailash>=` |
| kailash-kaizen   | `packages/kailash-kaizen/pyproject.toml`   | `packages/kailash-kaizen/src/kaizen/__init__.py`     | `kailash>=` |
| kailash-nexus    | `packages/kailash-nexus/pyproject.toml`    | `packages/kailash-nexus/src/nexus/__init__.py`       | `kailash>=` |

## Agent Teams

Deploy specialist agents as needed. See agent definitions for review criteria.

## Critical Rules

- NEVER publish to PyPI without running the full test suite first
- NEVER skip TestPyPI validation for major or minor releases
- NEVER commit PyPI tokens to source — use `~/.pypirc` or CI secrets
- NEVER skip security review before publishing
- NEVER release a framework without updating its `kailash>=` dependency to match the current SDK version
- ALWAYS update version in BOTH locations (pyproject.toml AND **init**.py) — missing **init**.py causes "my package didn't update" bugs
- ALWAYS verify the published package installs correctly in a clean venv
- ALWAYS publish in dependency order: core SDK first, then frameworks
- ALWAYS document releases in `deploy/deployments/`
- ALWAYS update the COC template repo (`kailash-coc-claude-py/pyproject.toml`) dependency pins after publishing
- Research current tool syntax — do not assume stale knowledge is correct

**Automated enforcement**: `validate-deployment.js` hook automatically blocks commits containing credentials (AWS keys, Azure secrets, GCP service account JSON, private keys, GitHub/PyPI/Docker tokens) in deployment files.

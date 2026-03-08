# Package Release Workflow

Stable patterns for releasing Python packages to PyPI and creating GitHub releases.

## Pre-Release Checklist

1. **Update documentation**
   - README.md — version badge, new features, breaking changes
   - CHANGELOG.md — add release entry with date
   - Build docs if using sphinx (`cd docs && make html`) or mkdocs (`mkdocs build`)

2. **Run full quality pipeline**

   ```bash
   ruff format . && ruff check . && pytest
   ```

3. **Run security review**
   - Delegate to security-reviewer agent before proceeding

4. **Bump version**
   - Update version in `pyproject.toml`
   - Update any `__version__` in `__init__.py` files
   - Update any version badges in README.md
   - Ensure all version references are consistent

## Git Workflow

### Direct Push (if allowed)

```bash
git add .
git commit -m "chore: release vX.Y.Z"
git push
```

### Protected Branch (PR workflow)

```bash
git checkout -b release/vX.Y.Z
git add .
git commit -m "chore: release vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "Release vX.Y.Z" --body "Release vX.Y.Z"
# Watch CI, merge when green
```

## GitHub Release

```bash
# Create tag
git tag vX.Y.Z
git push origin vX.Y.Z

# Create GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

## PyPI Publish

### Build

```bash
# Standard Python package
python -m build
```

### Upload

```bash
# Test on TestPyPI first (recommended)
twine upload --repository testpypi dist/*.whl
pip install --index-url https://test.pypi.org/simple/ package-name==X.Y.Z

# Upload wheels only (NEVER upload sdist for proprietary code)
twine upload dist/*.whl

# Or if sdist is safe (open source)
twine upload dist/*
```

**Credentials**: Use `~/.pypirc` or environment variables (`TWINE_USERNAME`, `TWINE_PASSWORD`). Never pass credentials as command-line arguments.

### Verify

```bash
# Install in clean environment
python -m venv /tmp/verify-release --clear
/tmp/verify-release/bin/pip install package-name==X.Y.Z
/tmp/verify-release/bin/python -c "import package_name; print('OK')"
```

## CI-Triggered Release

If CI handles publishing (common pattern):

1. Push tag → CI builds wheels for all platforms
2. CI runs tests on built wheels
3. CI publishes to PyPI
4. CI creates GitHub Release with artifacts

The agent should monitor CI after tagging:

```bash
# Watch the CI run triggered by the tag
gh run list --limit 5
gh run watch [run-id]
```

## Rollback

### PyPI

- Yank the version on PyPI (Project Settings > Yank Version) — PyPI does not allow deletion
- Publish corrected version with bumped patch number

### GitHub

```bash
gh release delete vX.Y.Z --yes
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
```

## npm Publish (if applicable)

```bash
npm version patch  # or minor/major
npm publish
```

## Critical Rules

- NEVER publish without running tests first
- NEVER publish without security review
- ALWAYS verify the published package installs correctly
- ALWAYS create a GitHub release with release notes
- For proprietary code: NEVER upload sdist, only wheels

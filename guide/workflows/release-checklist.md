# Release Checklist

Step-by-step guide for releasing a new version of Kailash Python SDK.

## Pre-Release Checklist

### 1. □ Version Management
```bash
# Check current version
grep version pyproject.toml
grep __version__ src/kailash/__init__.py

# Update version (example: 0.1.4 → 0.1.5)
# Edit: pyproject.toml, src/kailash/__init__.py
```

### 2. □ Update CHANGELOG.md
```markdown
## [0.1.5] - 2024-01-07

### Added
- New feature X
- Support for Y

### Changed
- Improved Z performance
- Updated documentation for W

### Fixed
- Bug in A component
- Issue with B validation

### Security
- Patched vulnerability in C
```

### 3. □ Update Documentation
- [ ] Update README.md if needed
- [ ] Update docs/index.rst with new features
- [ ] Check all links in documentation
- [ ] Update installation instructions if needed

### 4. □ Run Full Validation
```bash
# See guide/workflows/validation-checklist.md
make validate  # or run all validation commands
```

## Release Process

### 1. □ Create Release Branch
```bash
git checkout -b release/v0.1.5
git push -u origin release/v0.1.5
```

### 2. □ Final Checks
```bash
# Clean workspace
git status  # Should be clean

# Run all tests one more time
pytest
cd examples && python _utils/test_all_examples.py
cd ../docs && python build_docs.py
```

### 3. □ Build Distribution
```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source and wheel
python -m build

# Check the built files
ls -la dist/
twine check dist/*
```

### 4. □ Test Installation
```bash
# Create test environment
python -m venv test-release
source test-release/bin/activate  # or test-release\Scripts\activate on Windows

# Install from wheel
pip install dist/kailash-*.whl

# Test import and version
python -c "import kailash; print(kailash.__version__)"

# Run a simple example
python examples/workflow_examples/workflow_basic.py

# Cleanup
deactivate
rm -rf test-release
```

### 5. □ Upload to Test PyPI (Optional)
```bash
# Upload to test.pypi.org first
twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ kailash
```

### 6. □ Upload to PyPI
```bash
# Upload to production PyPI
twine upload dist/*

# Verify on PyPI
# Visit: https://pypi.org/project/kailash/
```

### 7. □ Create GitHub Release
1. Go to: https://github.com/[org]/kailash_python_sdk/releases
2. Click "Draft a new release"
3. Tag: `v0.1.5`
4. Target: `release/v0.1.5`
5. Title: `v0.1.5 - [Brief Description]`
6. Description: Copy from CHANGELOG.md
7. Attach: `dist/*` files
8. Publish release

### 8. □ Merge Release Branch
```bash
# Create PR from release/v0.1.5 to main
# After approval and merge:
git checkout main
git pull origin main
git tag v0.1.5
git push origin v0.1.5
```

## Post-Release

### 1. □ Verify Installation
```bash
# In a fresh environment
pip install kailash==0.1.5
python -c "import kailash; print(kailash.__version__)"
```

### 2. □ Update Documentation
- [ ] Update stable docs if using ReadTheDocs
- [ ] Update any external documentation
- [ ] Announce in relevant channels

### 3. □ Create Next Version Placeholder
```bash
# In CHANGELOG.md
## [Unreleased]
### Added
### Changed
### Fixed
### Security

## [0.1.5] - 2024-01-07
...
```

### 4. □ Archive Release Artifacts
In `releases/` directory:
```
releases/
├── notes/
│   └── v0.1.5.md          # Detailed release notes
├── checklists/
│   └── v0.1.5-checklist.md # This completed checklist
└── announcements/
    └── v0.1.5-announcement.md # Marketing copy
```

## Release Troubleshooting

### PyPI Upload Issues
```
HTTPError: 400 Bad Request
```
**Fix**: Check version doesn't already exist on PyPI

### Twine Authentication
```
Uploading distributions to https://upload.pypi.org/legacy/
Enter your username:
```
**Fix**: Use API token:
```bash
# Create .pypirc or use:
twine upload dist/* --username __token__ --password pypi-[your-token]
```

### Build Errors
```
ERROR: Could not build wheels
```
**Fix**:
- Check `pyproject.toml` syntax
- Ensure all dependencies are specified
- Try `pip install build --upgrade`

### Version Mismatch
```
Version in pyproject.toml doesn't match __init__.py
```
**Fix**: Update both files to same version

## Release Communication Template

### Internal Announcement
```markdown
# Kailash Python SDK v0.1.5 Released! 🎉

**What's New:**
- [Key feature 1]
- [Key feature 2]
- [Important fix]

**Breaking Changes:** None / [List if any]

**Upgrade Instructions:**
```bash
pip install --upgrade kailash
```

**Documentation:** [Updated docs link]
**Full Changelog:** [GitHub release link]
```

### External Announcement
```markdown
We're excited to announce Kailash Python SDK v0.1.5!

Highlights:
✨ [User-facing feature]
🚀 [Performance improvement]
🔧 [Important fix]

Get started:
```bash
pip install kailash==0.1.5
```

Learn more: [Documentation link]
```

## Quick Reference

```bash
# Version bump
# Edit: pyproject.toml, src/kailash/__init__.py, CHANGELOG.md

# Build
rm -rf dist/ && python -m build

# Upload
twine upload dist/*

# Tag
git tag v0.1.5 && git push origin v0.1.5
```

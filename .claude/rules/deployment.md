---
paths:
  - "deploy/**"
  - ".github/**"
  - "pyproject.toml"
  - "CHANGELOG.md"
---

# SDK Release Rules

## Before Any Release

1. Full test suite passes across all supported Python versions
2. Security review by **security-reviewer** (mandatory)
3. CHANGELOG.md updated (version, date, Added/Changed/Fixed/Removed, breaking changes marked)
4. Version bumped consistently across all packages (`pyproject.toml` + `__init__.py`)
5. No uncommitted changes

## TestPyPI Validation

Major/minor releases MUST validate on TestPyPI before production PyPI:

```bash
twine upload --repository testpypi dist/*.whl
python -m venv /tmp/verify --clear
/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ kailash==X.Y.Z
/tmp/verify/bin/python -c "import kailash; print(kailash.__version__)"
```

**Exception**: Patch releases may skip TestPyPI with explicit human approval.

## Publishing Rules

- Proprietary packages: wheels only (`twine upload dist/*.whl`), never sdist
- No publishing when CI is failing
- No PyPI tokens in source — use `~/.pypirc`, CI secrets, or trusted publisher (OIDC)
- Research current syntax (`--help` or web search) before running release commands

## Release Config

Every SDK MUST have `deploy/deployment-config.md`. Run `/deploy` to create it.

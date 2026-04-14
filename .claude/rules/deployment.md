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

**Why:** Skipping any pre-release step risks publishing a broken, insecure, or version-mismatched package to PyPI where it becomes immediately available to every downstream user.

## TestPyPI Validation

Major/minor releases MUST validate on TestPyPI before production PyPI:

```bash
twine upload --repository testpypi dist/*.whl
python -m venv /tmp/verify --clear
/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ kailash==X.Y.Z
/tmp/verify/bin/python -c "import kailash; print(kailash.__version__)"
```

**Why:** PyPI uploads are immutable -- a broken release cannot be overwritten, only yanked, leaving a permanent gap in the version sequence.

**Exception**: Patch releases may skip TestPyPI with explicit human approval.

## Publishing Rules

- Proprietary packages: wheels only (`twine upload dist/*.whl`), never sdist
- No publishing when CI is failing
- No PyPI tokens in source — use `~/.pypirc`, CI secrets, or trusted publisher (OIDC)
- Research current syntax (`--help` or web search) before running release commands

**Why:** Publishing sdist for proprietary packages exposes source code, publishing on failing CI ships known-broken artifacts, and committed tokens grant anyone with repo access full PyPI publishing rights.

## Release Config

Every SDK MUST have `deploy/deployment-config.md`. Run `/deploy` to create it.

**Why:** Without a deployment config, release agents guess at package names, registries, and credentials, leading to failed or misdirected publishes.

## MUST: Optional Dependencies Pin to PyPI-Resolvable Versions

`[project.optional-dependencies]` extras MUST pin to versions already on PyPI at the time of the commit. Bumping an extras pin to the version being released in the same commit is BLOCKED — CI installs from PyPI before the release is published, so the pin fails to resolve.

```toml
# DO — extras pin to currently-published minimum compatible version
[project.optional-dependencies]
dataflow = ["kailash-dataflow>=2.0.3"]   # 2.0.3 is on PyPI; 2.0.8 is being released
nexus    = ["kailash-nexus>=2.0.0"]
kaizen   = ["kailash-kaizen>=2.7.1"]

# DO NOT — extras pin to the version being released
[project.optional-dependencies]
dataflow = ["kailash-dataflow>=2.0.8"]   # 2.0.8 is not on PyPI yet → pip resolution fails
```

**BLOCKED rationalizations:**

- "The version will exist by the time CI runs"
- "We can fix CI after the release lands"
- "The lockfile pins the right version anyway"

**Why:** CI for the release PR runs `pip install -e ".[dev]"` against PyPI, which has the OLD versions. Pinning to the unreleased version produces `ERROR: No matching distribution found for kailash-mcp>=0.2.4` and the release CI fails. The framework SDK pins inside each package's own pyproject.toml (`kailash>=2.8.6` in `packages/kailash-dataflow/pyproject.toml`) ARE allowed to bump because they resolve against the local editable install of kailash, not PyPI. Source: PR #467 fix (commit a50d3119).

## MUST: All Files Imported By package `__init__.py` Tracked In Git

Before tagging a release, every `from .X import Y` and `from .pkg import Z` in any package's `__init__.py` MUST resolve to a file tracked in git. Imports that resolve to local-only files (untracked, .gitignored, generated) are BLOCKED — the published wheel will `ImportError` from a clean checkout.

```bash
# DO — verify all package imports are tracked
for init in packages/*/src/*/__init__.py; do
  pkg_dir="$(dirname "$init")"
  python -c "import ast, pathlib
init = pathlib.Path('$init')
tree = ast.parse(init.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and node.level > 0 and node.module:
        candidate = init.parent / node.module.replace('.', '/')
        for path in (candidate.with_suffix('.py'), candidate / '__init__.py'):
            if path.exists():
                rel = path.relative_to(pathlib.Path.cwd())
                import subprocess
                tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', str(rel)],
                                         capture_output=True).returncode == 0
                if not tracked:
                    print(f'UNTRACKED: {rel} imported by {init}')
                break
"
done

# DO NOT — release with untracked files imported by __init__.py
# packages/kailash-nexus/src/nexus/__init__.py:
#   from .auth.guards import AuthGuard          # auth/guards.py UNTRACKED
#   from .errors import NexusError              # errors.py UNTRACKED
# Result: pip install kailash-nexus → ImportError on first import
```

**BLOCKED rationalizations:**

- "The file exists on my machine, the test passed"
- "It was supposed to be in the previous PR"
- "We'll add it in the next release"
- "The CI passed because it uses editable install"

**Why:** Editable installs see the local working tree, including untracked files. PyPI users get only what's in the wheel, which is built from `git ls-files`. PR #459/#460 merged with `nexus/__init__.py` importing `.auth.guards` and `.errors` — both untracked. Tests passed because the local files existed. The wheel published to PyPI would have failed with `ImportError` on every fresh install. Caught by `/release` audit and fixed in PR #467.

Origin: PR #467 (2026-04-14) — bundled the missing nexus/auth/guards.py and nexus/errors.py files that PR #459/#460 left untracked.

---
priority: 10
scope: path-scoped
paths:
  - "deploy/**"
  - ".github/**"
  - "pyproject.toml"
  - "CHANGELOG.md"
---

# SDK Release Rules


<!-- slot:neutral-body -->


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

## MUST: Multi-Package Release Tags Pushed Individually

Coordinated multi-package releases MUST push each release tag in a separate `git push` command, with a brief pause between pushes. Batch-pushing 3+ tags in a single command is BLOCKED — GitHub's `push.tags` webhook drops workflow triggers silently.

```bash
# DO — one tag per push, trigger fires reliably
for tag in v2.8.6 dataflow-v2.0.8 kaizen-v2.7.4 nexus-v2.0.2 mcp-v0.2.4; do
  git push origin "$tag"
  sleep 1
done

# DO NOT — batch push, workflows silently skipped
git push origin v2.8.6 dataflow-v2.0.8 kaizen-v2.7.4 nexus-v2.0.2 mcp-v0.2.4
# Observed 2026-04-14: ZERO of 5 tags triggered publish-pypi.yml.
# Required manual workflow_dispatch for each package.
```

**BLOCKED rationalizations:**

- "Batch push is faster"
- "The workflow should handle multiple tag events"
- "We can check for missing runs after"
- "It worked last time with 2 tags"

**Why:** GitHub Actions' `push.tags` webhook delivery has undocumented rate-limiting when multiple tags arrive in a single push event. Batch pushes of 3+ tags fail to trigger the workflow for most (or all) of the tags. The failure is silent — the tags are created successfully, but `publish-pypi.yml` runs never appear in the Actions tab. Recovery requires manual `workflow_dispatch` per package, which is error-prone (must remember every package) and leaves a paper-trail asymmetry. Source: 2026-04-14 release where `git push origin v2.8.6 dataflow-v2.0.8 kaizen-v2.7.4 nexus-v2.0.2 mcp-v0.2.4` triggered zero workflow runs.

Origin: PR #469 (2026-04-14) — validated empirically when the single-tag push of nexus-v2.0.3 auto-triggered correctly while the prior 5-tag batch push triggered zero runs.

## MUST: TestPyPI Trusted-Publisher Registration Is Per-Package

Every package published via PyPI OIDC trusted-publishing MUST be registered as a pending publisher on BOTH `pypi.org` AND `test.pypi.org` separately. TestPyPI registration does NOT carry over from PyPI — they are independent indexes with independent publisher configs.

```yaml
# DO — register the package on test.pypi.org BEFORE the first
# workflow_dispatch run with publish_to=testpypi:
# https://test.pypi.org/manage/account/publishing/
#
# Required field values MUST match exactly:
#   PyPI Project Name:  kailash-ml
#   Owner:              terrene-foundation
#   Repository:         kailash-py
#   Workflow filename:  publish-pypi.yml
#   Environment name:   testpypi

# DO NOT — assume PyPI registration carries over
# pypi.org publisher config exists for kailash-ml ✓
# test.pypi.org publisher config does NOT exist ✗
# → workflow_dispatch publish_to=testpypi fails:
#   400 "Non-user identities cannot create new projects"
```

**BLOCKED rationalizations:**

- "We registered on PyPI, TestPyPI should work"
- "TestPyPI is just a mirror"
- "We can register after the first failed run"
- "The CI error message will explain it"

**Why:** Tag-triggered publishes (`push` of `v*` / `<pkg>-v*`) flow direct to PyPI only and never touch TestPyPI. The TestPyPI path requires `workflow_dispatch` with `publish_to=testpypi`, which requires the project to be pre-registered on test.pypi.org as a pending publisher. Without that one-time UI step, the upload returns `400 "Non-user identities cannot create new projects"` — a confusing error message that costs a release-cycle round-trip. Registration is a one-time UI step per package; document it in the repo's release runbook so the next package release does not re-discover it.

Origin: kailash-py 2026-04-19 release — kailash-ml PyPI publish succeeded via tag push, TestPyPI workflow_dispatch failed with 400 because `kailash_ml` was not pre-registered on test.pypi.org.

## MUST: Sibling-Package CI Installs Root SDK Editable For Unreleased Core Modules

When a new public module lands in `src/kailash/` (or any core SDK module tree) and is not yet published to PyPI, every sibling-package CI workflow that imports from it MUST prepend `uv pip install -e "."` to its install block BEFORE installing the sub-package's own `[dev]` extras. Sub-package CI workflows that install only `packages/<pkg>[dev]` silently resolve `kailash>=X.Y.Z` from PyPI — where the new module does NOT yet exist — and every test importing the new module fails at collection with `ModuleNotFoundError`.

```yaml
# DO — root kailash editable installed FIRST, then sub-package
- name: Install kailash-<subpkg>[dev]
  run: |
    uv venv .venv
    # Install root kailash first so kailash.<new_module> resolves
    # (not yet on PyPI; depends on PR #<N> of issue #<M>).
    uv pip install -e "." --python .venv/bin/python
    uv pip install -e "packages/kailash-<subpkg>[dev]" --python .venv/bin/python

# DO NOT — only sub-package; transitively pulls kailash from PyPI
- name: Install kailash-<subpkg>[dev]
  run: |
    uv venv .venv
    uv pip install -e "packages/kailash-<subpkg>[dev]" --python .venv/bin/python
    # → ModuleNotFoundError: No module named 'kailash.<new_module>'
```

**BLOCKED rationalizations:**

- "The sub-package's `kailash>=X.Y.Z` dep should pull it in"
- "We'll publish kailash first, then the sub-package CI will resolve"
- "This workflow happened to pass last time; must be fine"
- "The leading `uv pip install -e \".\"` is redundant with the sub-package dep"
- "We'll add the root install when we see the first failure"

**Why:** The sub-package's declared `kailash>=X.Y.Z` dependency resolves against PyPI, where the NEW module is not yet published. The build step succeeds (installs stable kailash from PyPI) but test collection fails because tests import the new module that exists only in the local editable source tree. Every `uv pip install -e "packages/..."` block in every sibling-package CI workflow MUST be preceded by `uv pip install -e "."`. No exceptions — even workflows that happen to pass today silently "work" because they do not import the new module yet. The comment in the CI step explaining the ordering is mandatory institutional knowledge: future contributors must understand that the leading root install is NOT redundant with the sub-package's declared kailash dep.

Origin: kailash-py Session 2026-04-20 (issue #567 Session 3b) — PR #570 landed `kailash.diagnostics.protocols` in `src/kailash/` (not yet on PyPI). PR #577 extended the editable-root prepend to Base/DL/RL/Unit/Inter-Package CI jobs across `test-kailash-ml.yml` + `test-kailash-align.yml`, unblocking PRs #574/#575/#576 which all failed at collection with `ModuleNotFoundError: No module named 'kailash.diagnostics'`.

### Bi-Directional At Bridge Boundaries (MUST)

The rule above covers the one-way case (sub-package imports from root core). At cross-package BRIDGE boundaries — where two sub-packages import each other's modules (e.g. `kailash-ml` ↔ `kailash-align` RL bridge; `kailash-dataflow` ↔ `kailash-ml` fabric bridge) — BOTH sibling CI jobs MUST install BOTH packages editable. The uni-directional form is insufficient at bridges.

```yaml
# DO — BOTH directions install BOTH packages at bridge boundaries
# .github/workflows/test-kailash-ml.yml (bridge: ml tests import kailash_align)
- run: |
    uv venv .venv
    uv pip install -e "." --python .venv/bin/python
    uv pip install -e "packages/kailash-align[dev]" --python .venv/bin/python   # reciprocal
    uv pip install -e "packages/kailash-ml[dev]" --python .venv/bin/python
# .github/workflows/test-kailash-align.yml (bridge: align tests import kailash_ml.rl.align_adapter)
- run: |
    uv venv .venv
    uv pip install -e "." --python .venv/bin/python
    uv pip install -e "packages/kailash-ml[dev]" --python .venv/bin/python      # reciprocal
    uv pip install -e "packages/kailash-align[dev]" --python .venv/bin/python

# DO NOT — install only one direction; the other fails on the next test run that imports across
- run: |
    uv pip install -e "packages/kailash-ml[dev]"   # ml tests import kailash_align
    # → ModuleNotFoundError: No module named 'kailash_align'
```

**BLOCKED rationalizations:**

- "The bridge module is in one direction only" (false — bridges are dual by nature)
- "We'll add the reverse install when tests fail on it" (cascades: one direction surfaces, the other waits until next PR)
- "Editable installs are dev-only, CI can rely on PyPI for the sibling"
- "The sibling's declared version is enough"
- "We can lazy-import across the bridge to avoid the editable"

**Why:** Bridge modules are by definition dual-import — each side's tests exercise paths that import the other package's modules. A one-way editable install surfaces only one direction's `ModuleNotFoundError`; the other direction surfaces in the NEXT PR that runs the opposite test suite, cascading fixes across two release cycles. Pre-declaring BOTH reciprocal installs in BOTH CI workflows catches it at the FIRST collection pass. Evidence: PR #611 release cycle — align→ml reciprocal install landed at commit `e7c5a33b`; the ml→align direction surfaced as the next collection failure at commit `c59c30da`. Both directions needed identical discipline.

Origin: kailash-py PR #611 release cycle (2026-04-23) — ML↔Align bridge CI cascade.

<!-- /slot:neutral-body -->

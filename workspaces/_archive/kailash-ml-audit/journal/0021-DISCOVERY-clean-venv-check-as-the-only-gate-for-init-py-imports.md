---
type: DISCOVERY
date: 2026-04-25
created_at: 2026-04-25T18:45:00Z
author: agent
project: kailash-ml-audit
topic: clean-venv install is the only test that catches __init__.py import-chain latent failures
phase: codify
tags: [discovery, clean-venv, editable-install, init-py, latent-failure, pypi]
---

# DISCOVERY — Clean-venv install is the only gate that catches **init**.py import-chain latent failures

## Discovery

Editable installs (`pip install -e`) mask cross-package `__init__.py` import failures because the dev environment ALWAYS has every sibling package present. A clean PyPI install of one package without its co-installed sibling is the only configuration that exercises the import chain in the user-visible state.

Three observations crystallized:

1. **Editable installs uniformly hide the failure.** Every dev environment (workspace .venv, M1 worktree .venvs, CI integration matrix that uses `uv pip install -e packages/*`) has all 8 sub-packages installed editable. None of them surface a failure that emerges when only ONE package is installed.
2. **Test suites uniformly hide the failure.** The kailash-kaizen test suite includes `kaizen_agents` integration tests; the test environment installs `kaizen-agents` as an extra. So `pytest packages/kailash-kaizen/tests/` passes 100% with the broken proxy imports active — the imports succeed because `kaizen_agents` is co-installed for testing.
3. **The ONLY environment that catches the failure is `pip install kailash-kaizen` from PyPI without any sibling.** This is exactly the configuration `build-repo-release-discipline.md` Rule 2's clean-venv check exercises. It is also exactly the configuration the user sees on day 1.

## Evidence

- kaizen 2.13.0 shipped 2026-04-25 with 4 broken `kaizen_agents.patterns.*` imports in `kaizen/orchestration/__init__.py`.
- 3 of 4 had been broken since refactor #75 (2026-03-12). They had survived 12 prior releases (2.7.5 through 2.12.3) because every release-time check was either a test (sibling co-installed) OR an editable-install verification (sibling co-installed).
- The clean-venv check that caught it was added by Rule 2 (2026-04-04 origin, applied per discipline starting with the M1 release wave 2026-04-23). The 2.13.0 release on 2026-04-25 was the FIRST time the check ran against `kailash-kaizen` standalone — and it failed immediately.

## What this means for the rule set

The clean-venv check is not a polish step or a smoke test — it is the ONLY structural gate that catches the `__init__.py` import-chain failure class. Three implications:

1. **The check is mandatory, not optional.** If the workflow skips it (PyPI cache lag, tag-collision retries, "we'll verify after the next merge"), the package ships broken.
2. **The check's pass-criterion is import success, not test success.** A `pytest` invocation in the clean venv is necessary but not sufficient — the failure occurs at module-load before any test can run. The test runner sees `ModuleNotFoundError` and reports collection failure; the agent reading the report needs to recognize that as the same failure class as a passing-test-with-broken-import.
3. **Hotfix scope is the broken pattern, not the latest PR.** When the check fails, the agent's instinct is to fix what THIS PR introduced. The kaizen 2.13.1 hotfix instead fixed all 4 imports, including the 3 that predated #602 by 6 weeks. This is now codified in `rules/build-repo-release-discipline.md` Rule 2's "Latent failures count" clause.

## Open questions

1. Are there other artifacts that ONLY exercise on a clean install? Console scripts (`kailash`, `nexus`) emerge from the wheel's `[project.scripts]` table — the check verifies importability of the entry point but not of the full `argparse` tree. A console script that imports a missing dep at parse time would only fail at the CLI invocation, not at import.
2. Should the clean-venv check be extended to a matrix of `(package, with-extras=False, with-extras=True)`? Today it tests `pip install <pkg>` with no extras. The kaizen pattern would also have been caught by `pip install kailash-kaizen[dev]` if `[dev]` did not pull in `kaizen-agents` — but `[dev]` does include it, so the matrix point that catches it is the bare-install column.
3. The Rule 2 retry protocol for PyPI cache lag has a 3-attempt × 60s ceiling. If the legitimate publish takes longer than 3 minutes to propagate (rare but observed), the retry loop reports failure for the wrong reason. Should we extend to 5 × 90s? The Origin commit shows the kaizen retry succeeded on attempt 2; not load-bearing for this hotfix but worth tracking.

## For Discussion

1. The kaizen 2.13.1 hotfix took ~30 minutes from clean-venv failure to PyPI publication. The `dependencies.md` MUST sub-rule we just added would have prevented the merge. But `/redteam` runs at PR-time; the rule needs a `paths:` scope that includes `**/__init__.py` for the path-scoped load to fire. Did we configure the path scope correctly, or does the rule only load on `pyproject.toml` edits?
2. Counterfactual: if no clean-venv check existed and the kaizen-2.13.0 release shipped, when would users have noticed? `pypi-stats kailash-kaizen` shows ~50 downloads/day. The first user without `kaizen_agents` co-installed would have hit the failure within hours. The 30-minute hotfix beat a P0 incident by maybe 6 hours.
3. The session notes from 2026-04-25 carry forward `deploy/deployment-config.md` not yet bumped to the 1.2.0 wave. That carryover predates this codify cycle and is a polish item. Should `/codify` ALSO have caught it as a leak in our release-discipline checklist, or is it correctly out of scope (the rule is "release per session"; the carryover is "documentation lag", not a release-discipline failure)?

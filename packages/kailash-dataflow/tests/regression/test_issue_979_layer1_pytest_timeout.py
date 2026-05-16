"""Regression for issue #979 Workstream-B B-5 — PR #976 failure-layer 1.

PR #976 failure-layer 1 (per
`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-32`):

    1. **pytest-timeout missing** — `--timeout` flag required the
       pytest-timeout plugin that wasn't installed in the workflow.

The #898 CI gate (re-enabled by #979 S6) catches NEW occurrences of any
of the 5 PR #976 failure layers. This dedicated regression file makes
the layer-1 prevention grep-able and survives a CI-workflow refactor
(per `rules/testing.md` § Regression Testing — the CI gate alone is not
a substitute for a permanent in-suite test).

Layer-1 invariant: a clean `pip install -e
packages/kailash-dataflow[dev]` MUST install `pytest-timeout>=2.3.0`,
AND pytest.ini MUST carry `timeout = 120` + `timeout_method = thread`.
Without the plugin pin, the pytest.ini `timeout = 120` directive
silently becomes a no-op; a hung test then consumes the whole job's
wall-clock instead of failing with a per-test traceback.

These are structural assertions on configuration files (TOML + INI
parsing). They are Tier-1: pure filesystem + stdlib parsing, no
external infrastructure, well under the <2min tier-1 suite budget.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
PYTEST_INI = PACKAGE_ROOT / "pytest.ini"

# Guard: tomllib is stdlib from Python 3.11. The dataflow package targets
# 3.11+, but make the dependency explicit so a future 3.10 run fails
# loudly with an actionable message rather than an opaque ImportError.
if sys.version_info < (3, 11):  # pragma: no cover - environment guard
    pytest.skip(
        "tomllib requires Python 3.11+ (issue #979 layer-1 regression)",
        allow_module_level=True,
    )


def _dev_extras() -> list[str]:
    """Return the [project.optional-dependencies].dev list, structurally parsed."""
    data = tomllib.loads(PYPROJECT.read_text())
    optional = data.get("project", {}).get("optional-dependencies", {})
    dev = optional.get("dev")
    assert isinstance(dev, list), (
        "pyproject.toml [project.optional-dependencies].dev missing or not a "
        "list — required by issue #979 layer-1 (pytest-timeout pin lives here)."
    )
    return dev


@pytest.mark.regression
@pytest.mark.unit
def test_pytest_timeout_pinned_in_dev_extras():
    """Layer 1a: `pytest-timeout>=2.3.0` is declared in [dev] extras.

    Without this pin a clean `pip install -e
    packages/kailash-dataflow[dev]` omits the plugin, and pytest.ini's
    `timeout = 120` directive silently becomes a no-op (PR #976
    failure-layer 1). The #898 CI gate runs against a clean install,
    so the missing pin re-converts every hung test into a job-wall-clock
    timeout instead of a per-test traceback.
    """
    dev = _dev_extras()
    # Find the pytest-timeout requirement string and parse its lower bound.
    matches = [
        spec for spec in dev if re.match(r"^\s*pytest-timeout\b", spec, re.IGNORECASE)
    ]
    assert matches, (
        "pytest-timeout missing from [project.optional-dependencies].dev in "
        "packages/kailash-dataflow/pyproject.toml. PR #976 failure-layer 1: "
        "the `--timeout`/`timeout=` mechanism requires the pytest-timeout "
        "plugin; without the pin a clean [dev] install omits it. See "
        "workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-25."
    )
    spec = matches[0]
    bound = re.search(r">=\s*(\d+)\.(\d+)(?:\.(\d+))?", spec)
    assert bound is not None, (
        f"pytest-timeout requirement {spec!r} has no `>=X.Y` lower bound; "
        "issue #979 layer-1 requires `pytest-timeout>=2.3.0`."
    )
    major, minor = int(bound.group(1)), int(bound.group(2))
    patch = int(bound.group(3) or 0)
    assert (major, minor, patch) >= (2, 3, 0), (
        f"pytest-timeout pinned to >={major}.{minor}.{patch}; issue #979 "
        f"layer-1 requires >=2.3.0 (the version whose `timeout_method=thread` "
        f"behaviour the unit-suite triage validated). Found: {spec!r}."
    )


@pytest.mark.regression
@pytest.mark.unit
def test_pytest_ini_carries_timeout_directives():
    """Layer 1b: pytest.ini declares `timeout = 120` + `timeout_method = thread`.

    The plugin pin (1a) is only half the contract — the directives in
    pytest.ini are what actually arm the per-test timeout. Losing either
    to a config-consolidation refactor re-opens PR #976 failure-layer 1:
    a hung test exhausts the job wall-clock instead of raising
    `Failed: Timeout >120.0s` with a per-test traceback.
    """
    text = PYTEST_INI.read_text()
    assert re.search(r"^timeout\s*=\s*120\s*$", text, re.MULTILINE), (
        "pytest.ini missing `timeout = 120` directive (issue #979 layer-1 / "
        "PR #976 failure-layer 1). The pytest-timeout plugin is installed "
        "(see test_pytest_timeout_pinned_in_dev_extras) but inert without "
        "this directive."
    )
    assert re.search(r"^timeout_method\s*=\s*thread\s*$", text, re.MULTILINE), (
        "pytest.ini missing `timeout_method = thread` directive (issue #979 "
        "layer-1 / PR #976 failure-layer 1). The default `signal` method "
        "does not interrupt blocked C-extension / event-loop code; `thread` "
        "is required for the DataFlow unit suite's async-heavy tests."
    )

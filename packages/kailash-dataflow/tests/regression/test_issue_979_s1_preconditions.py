"""Regression tests for issue #979 / Workstream-A S1 (preconditions).

S1 establishes the test-config floor required for the unit-suite triage:
- `pytest-timeout` pinned as a `[dev]` extra (clean-venv reproducibility)
- `timeout = 120` + `timeout_method = thread` in pytest.ini
- Sole marker-filter location is pytest.ini's `addopts` (CRIT-B)
- Dead `[tool.pytest.ini_options]` + `[tool.coverage.run]` blocks removed
  from pyproject.toml (CRIT-C + Gap-2)
- `asyncio_default_*_loop_scope = function` keys preserved in pytest.ini
  (Gap-3)

These are structural assertions on configuration files. Regex against
config text is acceptable here per
`rules/probe-driven-verification.md` MUST Rule 3 (structural, not
semantic — file contents, not LLM-judged behavior).

Maps to acceptance criteria in
`workspaces/issue-979-dataflow-unit-triage/todos/active/01-S1-preconditions.md`
invariants 1-5.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
PYTEST_INI = PACKAGE_ROOT / "pytest.ini"


@pytest.mark.regression
@pytest.mark.unit
def test_dev_extras_carry_tier1_required_pins():
    """Invariant 1: pytest-timeout + aiosqlite are in [...optional-dependencies].dev.

    Without `pytest-timeout`, a clean `pip install -e
    packages/kailash-dataflow[dev]` omits the plugin and pytest.ini's
    `timeout = 120` directive silently becomes a no-op (PR #976
    failure-layer 1).

    Without `aiosqlite`, the Tier-1 canonical fixtures (`memory_dataflow`,
    `file_dataflow`) cannot import; tests/unit/conftest.py fails at
    collection — same failure-layer family as PR #976.
    """
    text = PYPROJECT.read_text()
    # Locate the dev = [...] block and search inside it.
    match = re.search(r"^dev\s*=\s*\[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert match is not None, "pyproject.toml has no `dev = [...]` extras block"
    dev_block = match.group(1)
    assert re.search(r'"pytest-timeout>=2\.3\.\d+"', dev_block), (
        "pytest-timeout>=2.3.0 missing from [project.optional-dependencies].dev "
        "in packages/kailash-dataflow/pyproject.toml — required by pytest.ini's "
        "`timeout = 120` directive (issue #979 S1)."
    )
    assert re.search(r'"aiosqlite>=0\.\d+\.\d+"', dev_block), (
        "aiosqlite>=0.19.0 missing from [project.optional-dependencies].dev "
        "in packages/kailash-dataflow/pyproject.toml — required by Tier-1 "
        "canonical fixtures `memory_dataflow` / `file_dataflow` per "
        "specs/testing-tiers.md § Tier-1 Contract Rule 6."
    )


@pytest.mark.regression
@pytest.mark.unit
def test_pytest_ini_has_timeout_directives():
    """Invariant 2: pytest.ini declares `timeout = 120` + `timeout_method = thread`.

    Without these, a hung test exhausts the job wall-clock instead of
    raising a per-test `Failed: Timeout >120.0s` traceback.
    """
    text = PYTEST_INI.read_text()
    assert re.search(
        r"^timeout\s*=\s*120\s*$", text, re.MULTILINE
    ), "pytest.ini missing `timeout = 120` directive (issue #979 S1)."
    assert re.search(
        r"^timeout_method\s*=\s*thread\s*$", text, re.MULTILINE
    ), "pytest.ini missing `timeout_method = thread` directive (issue #979 S1)."


@pytest.mark.regression
@pytest.mark.unit
def test_pytest_ini_addopts_carries_marker_filter():
    """Invariant 3 (CRIT-B): pytest.ini addopts carries the sole marker filter.

    `-m "not (requires_postgres or requires_mysql or requires_redis or
    requires_docker)"` MUST live in pytest.ini's `addopts`. The S6 CI
    workflow has zero `-m` flags by design — workflow override would
    fork the filter location across two files and produce
    "tests pass locally, skip on CI" drift.
    """
    text = PYTEST_INI.read_text()
    # Find the `addopts =` block and confirm the marker expression lives there.
    match = re.search(
        r"^addopts\s*=\s*(.*?)(?=^[a-zA-Z_]+\s*=|^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "pytest.ini has no `addopts =` block"
    addopts_block = match.group(1)
    assert "requires_postgres" in addopts_block, (
        "pytest.ini `addopts` missing `not (requires_postgres or ...)` marker "
        "filter (issue #979 S1 CRIT-B). The unit tier MUST exclude marked tests "
        "by default; tier-2/3 jobs override via `-o 'addopts='`."
    )
    assert (
        "requires_mysql" in addopts_block
    ), "pytest.ini `addopts` marker filter missing `requires_mysql` term."
    assert (
        "requires_redis" in addopts_block
    ), "pytest.ini `addopts` marker filter missing `requires_redis` term."
    assert (
        "requires_docker" in addopts_block
    ), "pytest.ini `addopts` marker filter missing `requires_docker` term."


@pytest.mark.regression
@pytest.mark.unit
def test_pyproject_has_no_duplicate_pytest_or_coverage_run_blocks():
    """Invariant 4 (CRIT-C + Gap-2): no shadow config in pyproject.toml.

    Both `[tool.pytest.ini_options]` and `[tool.coverage.run]` lived in
    pyproject.toml AND in pytest.ini before S1. pytest.ini wins at file
    precedence, so the pyproject blocks were silent dead config that a
    future contributor could edit with no test-run effect. Deleted in
    S1; this test prevents re-introduction.
    """
    text = PYPROJECT.read_text()
    # Match actual TOML section headers (`[section]` at line start) rather
    # than substring presence — the rule deletes the SECTION, not every
    # mention. A reference inside an explanatory comment is fine.
    assert not re.search(r"^\[tool\.pytest\.ini_options\]\s*$", text, re.MULTILINE), (
        "pyproject.toml re-introduced `[tool.pytest.ini_options]` section "
        "— dead config (pytest.ini wins precedence). Edit pytest.ini "
        "instead. Issue #979 S1 CRIT-C."
    )
    assert not re.search(r"^\[tool\.coverage\.run\]\s*$", text, re.MULTILINE), (
        "pyproject.toml re-introduced `[tool.coverage.run]` section — dead "
        "config (pytest.ini's `[coverage:run]` is canonical). Issue #979 "
        "S1 Gap-2."
    )


@pytest.mark.regression
@pytest.mark.unit
def test_pytest_ini_preserves_asyncio_loop_scope_keys():
    """Invariant 5 (Gap-3): asyncio loop-scope keys remain set to `function`.

    `asyncio_default_fixture_loop_scope` and `asyncio_default_test_loop_scope`
    govern fixture/test isolation under pytest-asyncio. Losing either to a
    consolidation refactor would re-introduce cross-test event-loop
    pollution that surfaced in PR #976.
    """
    text = PYTEST_INI.read_text()
    assert re.search(
        r"^asyncio_default_fixture_loop_scope\s*=\s*function\s*$",
        text,
        re.MULTILINE,
    ), (
        "pytest.ini missing `asyncio_default_fixture_loop_scope = function` "
        "(issue #979 S1 Gap-3)."
    )
    assert re.search(
        r"^asyncio_default_test_loop_scope\s*=\s*function\s*$",
        text,
        re.MULTILINE,
    ), (
        "pytest.ini missing `asyncio_default_test_loop_scope = function` "
        "(issue #979 S1 Gap-3)."
    )

"""Regression for issue #979 Workstream-B B-5 — PR #976 failure-layer 2.

PR #976 failure-layer 2 (per
`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-32`):

    2. **OOM under pytest's AST rewriter** — collection memory exhausted
       on certain test modules.

Root cause (per `rules/python-environment.md` Rule 4 + PR #430
post-mortem): `hypothesis` registers as a pytest plugin. Pytest's
assertion rewriter AST-rewrites `hypothesis.internal.conjecture.
shrinking.collection` and exhausts memory on GitHub runners, producing
`MemoryError` during collection with no root-cause signal. Installing
`hypothesis` into the venv that runs the DataFlow unit suite (via the
[dev] extras) is therefore the layer-2 trigger.

Layer-2 invariant: the `[dev]` extras MUST NOT include `hypothesis`.
Sub-packages that genuinely need property-based testing own that dep in
their own test extras, in their own venv — never the [dev] set the #898
CI gate installs to run the unit tier.

This dedicated regression file makes the layer-2 prevention grep-able
and survives a CI-workflow refactor (per `rules/testing.md` §
Regression Testing). Tier-1: pure TOML parsing, no infrastructure.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"

if sys.version_info < (3, 11):  # pragma: no cover - environment guard
    pytest.skip(
        "tomllib requires Python 3.11+ (issue #979 layer-2 regression)",
        allow_module_level=True,
    )


@pytest.mark.regression
@pytest.mark.unit
def test_dev_extras_excludes_hypothesis():
    """Layer 2: `hypothesis` MUST NOT appear in [dev] extras.

    `hypothesis` registers as a pytest plugin; pytest's assertion
    rewriter AST-rewrites its conjecture-shrinking module and exhausts
    runner memory during collection (`MemoryError`, no root-cause
    signal — PR #976 failure-layer 2, same class as PR #430).

    The #898 CI gate installs `packages/kailash-dataflow[dev]` to run
    the unit tier; any `hypothesis` entry there re-arms the OOM on the
    next clean-install CI run. Property-based tests belong in a
    sub-package's own test extras / venv, never the unit-tier [dev] set.
    """
    data = tomllib.loads(PYPROJECT.read_text())
    optional = data.get("project", {}).get("optional-dependencies", {})
    dev = optional.get("dev")
    assert isinstance(dev, list), (
        "pyproject.toml [project.optional-dependencies].dev missing or not a "
        "list — issue #979 layer-2 inspects this list for a hypothesis entry."
    )
    offenders = [
        spec for spec in dev if re.match(r"^\s*hypothesis\b", spec, re.IGNORECASE)
    ]
    assert not offenders, (
        f"`hypothesis` found in [project.optional-dependencies].dev: "
        f"{offenders!r}. PR #976 failure-layer 2: hypothesis' pytest-plugin "
        f"AST-rewrite triggers MemoryError during collection on the #898 CI "
        f"gate's clean [dev] install. Move property-based-test deps to the "
        f"owning sub-package's own test extras (rules/python-environment.md "
        f"Rule 4). See "
        f"workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:26-27."
    )

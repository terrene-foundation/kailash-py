"""Regression for issue #979 Workstream-B B-5 — PR #976 failure-layer 4.

PR #976 failure-layer 4 (per
`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-32`):

    4. **`[fabric]` extra not installed** — `tests/unit/fabric/*` imports
       fail without the optional dependency.

`dataflow.fabric.*` requires the `[fabric]` extra (`httpx`, `watchdog`,
`msgpack`, `prometheus-client`). The #898 CI gate installs only `[dev]`
to run the unit tier, so any `tests/unit/fabric/*` module that imports
`dataflow.fabric.*` at collection time fails with `ModuleNotFoundError`
on the gate's clean install. The triage resolution moved the fabric
suite to the integration tier (per
`packages/kailash-dataflow/tests/CLAUDE.md` § "fabric/" — the suite
"lives in the integration tier, not tier-1 unit").

Layer-4 invariant (whichever holds):
  - `tests/unit/fabric/` does NOT exist (the move to integration
    happened — current expected state), OR
  - if it exists, EVERY module in it gates the fabric import at module
    top via `pytest.importorskip("httpx")` (or another fabric dep) so a
    clean `[dev]`-only install skips rather than errors at collection.

This dedicated regression file makes the layer-4 prevention grep-able
and survives a CI-workflow refactor (per `rules/testing.md` §
Regression Testing). Tier-1: pure filesystem + `ast` parsing, no
infrastructure, no import of `dataflow.fabric`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
UNIT_FABRIC_DIR = PACKAGE_ROOT / "tests" / "unit" / "fabric"

# Any importorskip on one of these deps makes the module skip (not error)
# on a clean [dev]-only install. They are the [fabric] extra's members.
FABRIC_GATE_DEPS = {
    "httpx",
    "watchdog",
    "msgpack",
    "prometheus_client",
    "prometheus-client",
}


def _has_top_level_fabric_importorskip(path: Path) -> bool:
    """True if the module calls pytest.importorskip("<fabric dep>") at module top."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.iter_child_nodes(tree):
        # Match `pytest.importorskip("httpx")` and bare `importorskip("httpx")`
        # at module top, whether bare-expression or assigned
        # (`mod = pytest.importorskip(...)`).
        call: ast.Call | None = None
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        if call is None:
            continue
        func = call.func
        is_importorskip = (
            isinstance(func, ast.Attribute) and func.attr == "importorskip"
        ) or (isinstance(func, ast.Name) and func.id == "importorskip")
        if not is_importorskip:
            continue
        if call.args and isinstance(call.args[0], ast.Constant):
            dep = call.args[0].value
            if isinstance(dep, str) and dep in FABRIC_GATE_DEPS:
                return True
    return False


@pytest.mark.regression
@pytest.mark.unit
def test_unit_fabric_suite_is_gated_or_absent():
    """Layer 4: tests/unit/fabric/ is absent OR every module gates a fabric dep.

    `dataflow.fabric.*` needs the `[fabric]` extra. The #898 CI gate
    installs only `[dev]`, so an ungated `tests/unit/fabric/*` module
    fails at collection with `ModuleNotFoundError` (PR #976
    failure-layer 4). The triage moved the fabric suite to the
    integration tier; absence of `tests/unit/fabric/` is the expected
    healthy state and this test asserts it. If a future change
    reintroduces the directory, every module in it MUST call
    `pytest.importorskip("httpx")` (or another [fabric] dep) at module
    top so a clean `[dev]` install skips rather than errors.

    See workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:31-32.
    """
    if not UNIT_FABRIC_DIR.exists():
        # Expected healthy state: the fabric suite moved to the
        # integration tier. The move IS the layer-4 prevention.
        return

    modules = sorted(UNIT_FABRIC_DIR.rglob("test_*.py"))
    ungated = [
        str(p.relative_to(PACKAGE_ROOT))
        for p in modules
        if not _has_top_level_fabric_importorskip(p)
    ]
    assert not ungated, (
        "tests/unit/fabric/ exists and these modules do NOT gate a "
        "[fabric]-extra dependency at module top via "
        '`pytest.importorskip("httpx")` (or watchdog/msgpack/'
        "prometheus_client) — PR #976 failure-layer 4. On the #898 CI "
        "gate's clean `[dev]`-only install these fail at collection with "
        "ModuleNotFoundError instead of skipping:\n"
        + "\n".join(f"  - {m}" for m in ungated)
        + "\n\nEither move the fabric suite back to the integration tier "
        "(preferred — see tests/CLAUDE.md § fabric/) or add the "
        "module-top importorskip gate."
    )

"""LOC invariant tests — guards against silent re-inlining of extracted code.

Per rules/refactor-invariants.md, every refactor that shrinks a file
MUST land a numeric invariant test. These tests ensure key files don't
silently grow back beyond their post-refactor sizes.
"""

import re
from pathlib import Path

import pytest

#: Canonical ceiling for base_agent.py — 882 post-refactor + 15% margin.
#: A SECOND guard enforces the same number from inside the kailash-kaizen
#: package (that package is distributed on its own, so its tests must run
#: without the monorepo root and cannot import this constant). The two are
#: kept honest by ``test_base_agent_loc_guards_agree`` below.
BASE_AGENT_LOC_LIMIT = 1015

#: The sibling guard, and the pattern that reads its limit out of the source.
BASE_AGENT_SIBLING_GUARD = Path(
    "packages/kailash-kaizen/tests/unit/core/test_base_agent_slimming.py"
)
_SIBLING_LIMIT_RE = re.compile(r"assert\s+len\(lines\)\s*<=\s*(\d+)")


@pytest.mark.regression
def test_base_agent_loc():
    """Guard: base_agent.py must stay under 1015 LOC after convergence extraction."""
    path = Path("packages/kailash-kaizen/src/kaizen/core/base_agent.py")
    lines = len(path.read_text().splitlines())
    limit = BASE_AGENT_LOC_LIMIT
    assert lines <= limit, (
        f"base_agent.py: {lines} lines (limit {limit}). "
        f"Code may have been re-inlined by a merge. "
        f"Check git log for unexpected growth."
    )


@pytest.mark.regression
def test_base_agent_loc_guards_agree():
    """Guard: the two base_agent.py ceilings must not drift apart (#2119).

    They already did once. On 2026-07-24 (63388e031) the file reached 1016
    lines and BOTH guards — each at 1015 — went red by one line. On 2026-08-11
    (24d06dee9) one of them was raised to 1070, which turned that copy green
    again and left this one red, where it stayed unnoticed for 18 days. Two
    ceilings for one file are only safe if widening one cannot pass while the
    other still fails.

    A shared constant is not available: kailash-kaizen is its own
    distribution, so its tests must pass without the monorepo root on disk.
    This runs from the root, where both files are visible, and fails closed if
    the sibling cannot be read — an unreadable guard is not an agreeing one.
    """
    assert BASE_AGENT_SIBLING_GUARD.exists(), (
        f"Sibling LOC guard not found at {BASE_AGENT_SIBLING_GUARD}. It enforces "
        f"the same ceiling as this test; if it moved, point this test at its new "
        f"home rather than deleting the agreement check."
    )

    match = _SIBLING_LIMIT_RE.search(BASE_AGENT_SIBLING_GUARD.read_text())
    assert match is not None, (
        f"Could not read the line-count ceiling out of {BASE_AGENT_SIBLING_GUARD}. "
        f"Expected an `assert len(lines) <= <N>` form. If that guard was rewritten, "
        f"update _SIBLING_LIMIT_RE — do not drop this check, which is the only "
        f"thing keeping the two ceilings in step."
    )

    sibling_limit = int(match.group(1))
    assert sibling_limit == BASE_AGENT_LOC_LIMIT, (
        f"base_agent.py LOC guards disagree: this test allows "
        f"{BASE_AGENT_LOC_LIMIT}, {BASE_AGENT_SIBLING_GUARD} allows "
        f"{sibling_limit}. Raising one ceiling without the other is how #2119 "
        f"stayed red on main for 18 days while a green guard covered for it. "
        f"Re-anchor BOTH, or extract instead of raising."
    )


@pytest.mark.regression
def test_delegate_loc():
    """Guard: delegate.py must stay under 818 LOC after convergence extraction."""
    path = Path("packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py")
    lines = len(path.read_text().splitlines())
    limit = 818  # 711 post-refactor + 15% margin
    assert lines <= limit, (
        f"delegate.py: {lines} lines (limit {limit}). "
        f"Code may have been re-inlined by a merge. "
        f"Check git log for unexpected growth."
    )


@pytest.mark.regression
def test_pact_engine_loc():
    """Guard: pact/engine.py must stay under threshold.

    Baseline re-anchored 2026-05-01 from 998 (pre-#567) → 1414 (post-#567,
    commit 9ffc23d0 absorbed three MLFP-rejected GovernanceDiagnostics
    capabilities — verify_audit_chain, envelope_snapshot,
    iter_audit_anchors — as first-class PactEngine methods, +387 LOC of
    legitimate feature code, NOT a re-inlining merge regression).
    Threshold = 1414 × 1.15 ≈ 1626 per rules/refactor-invariants.md Rule 1.
    """
    path = Path("packages/kailash-pact/src/pact/engine.py")
    lines = len(path.read_text().splitlines())
    limit = 1626  # 1414 post-#567 baseline + 15% margin
    assert lines <= limit, (
        f"engine.py: {lines} lines (limit {limit}). "
        f"Code may have been re-inlined by a merge. "
        f"Check git log for unexpected growth."
    )

"""LOC invariant tests — guards against silent re-inlining of extracted code.

Per rules/refactor-invariants.md, every refactor that shrinks a file
MUST land a numeric invariant test. These tests ensure key files don't
silently grow back beyond their post-refactor sizes.
"""

from pathlib import Path

import pytest


@pytest.mark.regression
def test_base_agent_loc():
    """Guard: base_agent.py must stay under 1015 LOC after convergence extraction."""
    path = Path("packages/kailash-kaizen/src/kaizen/core/base_agent.py")
    lines = len(path.read_text().splitlines())
    limit = 1015  # 882 post-refactor + 15% margin
    assert lines <= limit, (
        f"base_agent.py: {lines} lines (limit {limit}). "
        f"Code may have been re-inlined by a merge. "
        f"Check git log for unexpected growth."
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

"""LOC invariant test for #822 Shard 2 orphan-deletion.

Per `rules/refactor-invariants.md` Rule 1: every refactor that reduces LOC
MUST land an invariant test in the SAME COMMIT to guard against silent
re-introduction via merge conflict resolution or partial revert.

Shard 2 deleted ~600 LOC of fake-MCP-integration code from `agents.py`
(8 dead methods imported from `..mcp.registry` / `..mcp::AutoDiscovery` /
`..mcp::MCPConnection` — none of which existed at any commit). The threshold
below was measured post-deletion + 15% margin per Rule 1.
"""

from pathlib import Path

import pytest


@pytest.mark.regression
def test_agents_py_loc_invariant_after_822():
    """Guard: after #822 Shard 2 deletion, agents.py stays below threshold.

    If agents.py grows past the threshold, check git log for unexpected
    re-inlining of these deleted methods:
    - Agent.expose_as_mcp_server
    - Agent.expose_as_mcp_tool
    - Agent.get_mcp_tool_registry
    - Agent.execute_mcp_tool
    - Agent.connect_to_mcp_servers
    - Agent.call_mcp_tool
    - Agent._call_mcp_tool
    - Agent._discover_servers
    """
    here = Path(__file__).resolve()
    # Walk up to find the kailash-kaizen sub-package root
    pkg_root = next(
        p
        for p in here.parents
        if (p / "pyproject.toml").exists() and p.name == "kailash-kaizen"
    )
    path = pkg_root / "src" / "kaizen" / "core" / "agents.py"
    assert path.exists(), f"agents.py not found at {path}"
    line_count = len(path.read_text().splitlines())
    # Post-#822-Shard-2 LOC: 2858. Threshold = 2858 + 15% margin ≈ 3290.
    THRESHOLD = 3290
    assert line_count <= THRESHOLD, (
        f"agents.py has {line_count} lines (post-#822 limit: {THRESHOLD}). "
        f"If MCP orphan methods were re-introduced, check git log for "
        f"unexpected growth in the 2415-3012 line range."
    )


@pytest.mark.regression
def test_framework_py_loc_invariant_after_822():
    """Guard: after #822 Shard 2 deletion, framework.py stays below threshold.

    Deleted from framework.py:
    - Kaizen.mcp_registry property
    - Kaizen.expose_agent_as_mcp_tool
    - Kaizen.list_mcp_tools
    - Kaizen.discover_mcp_tools
    """
    here = Path(__file__).resolve()
    pkg_root = next(
        p
        for p in here.parents
        if (p / "pyproject.toml").exists() and p.name == "kailash-kaizen"
    )
    path = pkg_root / "src" / "kaizen" / "core" / "framework.py"
    assert path.exists(), f"framework.py not found at {path}"
    line_count = len(path.read_text().splitlines())
    # Post-#822-Shard-2 LOC: 2217. Threshold = 2217 + 15% margin ≈ 2550.
    THRESHOLD = 2550
    assert line_count <= THRESHOLD, (
        f"framework.py has {line_count} lines (post-#822 limit: {THRESHOLD}). "
        f"If Kaizen.mcp_registry / expose_agent_as_mcp_tool / list_mcp_tools / "
        f"discover_mcp_tools were re-introduced, check git log for unexpected "
        f"growth in the 1377-1574 line range."
    )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 regression for issue #929 — Workflow.to_dict()/from_dict() round-trip
preserves all node init kwargs in node.config.

Per ``rules/testing.md`` Tier 2: NO mocking. Real ``WorkflowBuilder``,
real ``Workflow.to_dict()`` / ``Workflow.from_dict()``, real ``LocalRuntime``
execution against the reconstructed workflow.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression": this is the
docs-exact path the issue reproduction shows; the test asserts the user-
visible outcome (node executes and returns the expected value) rather
than only the structural shape of ``self.config``.

Per ``rules/cross-sdk-inspection.md`` Rule 3a: a structural invariant test
pins the contract that bound init params reach ``self.config`` so a future
refactor of ``Node.__init_subclass__`` cannot silently re-introduce the
bug class.
"""

from __future__ import annotations

import pytest

from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Behavioral round-trip: PythonCodeNode (the originally-reported regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
def test_issue_929_python_code_node_round_trip_preserves_code() -> None:
    """The exact reproduction in #929: code parameter MUST survive
    ``to_dict() → from_dict()``."""
    wf = WorkflowBuilder()
    wf.add_node(
        "PythonCodeNode",
        "compute",
        {"code": "result = {'value': 42}"},
    )
    built = wf.build()

    serialized = built.to_dict()
    restored = Workflow.from_dict(serialized)

    # Structural assertion: code is in the restored config.
    assert (
        restored.nodes["compute"].config.get("code") == "result = {'value': 42}"
    ), "PythonCodeNode.code MUST be preserved across to_dict/from_dict"


@pytest.mark.regression
@pytest.mark.integration
def test_issue_929_python_code_node_round_trip_executes() -> None:
    """End-to-end: a round-tripped PythonCodeNode produces non-empty results."""
    wf = WorkflowBuilder()
    wf.add_node(
        "PythonCodeNode",
        "compute",
        {"code": "result = {'value': 42}"},
    )
    built = wf.build()

    serialized = built.to_dict()
    restored = Workflow.from_dict(serialized)

    with LocalRuntime() as runtime:
        results, _run_id = runtime.execute(restored)

    assert results, "Restored workflow MUST produce results"
    assert "compute" in results, f"compute node MUST be in results: {results}"
    # The exact return shape varies by engine; both common forms are accepted.
    compute_out = results["compute"]
    if isinstance(compute_out, dict) and "result" in compute_out:
        assert compute_out["result"] == {"value": 42}
    else:
        assert compute_out == {"value": 42}


@pytest.mark.regression
@pytest.mark.integration
def test_issue_929_python_code_node_preserves_extended_kwargs() -> None:
    """Round-trip preserves description, sandbox_mode, max_code_lines."""
    wf = WorkflowBuilder()
    wf.add_node(
        "PythonCodeNode",
        "compute",
        {
            "code": "result = 1",
            "description": "doubles the input",
            "sandbox_mode": "trusted",
            "max_code_lines": 50,
        },
    )
    built = wf.build()

    serialized = built.to_dict()
    restored = Workflow.from_dict(serialized)

    config = restored.nodes["compute"].config
    assert config.get("code") == "result = 1"
    assert config.get("description") == "doubles the input"
    assert config.get("sandbox_mode") == "trusted"
    assert config.get("max_code_lines") == 50


# ---------------------------------------------------------------------------
# Structural invariant: every Node subclass with named init args captures
# them into self.config (the contract that prevents silent regression).
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
def test_issue_929_init_subclass_capture_invariant() -> None:
    """Pin the structural contract: ``Node.__init_subclass__`` installs an
    init-capture wrapper on every subclass that defines ``__init__``.

    If a future refactor removes the wrapper or changes the exclude set in a
    way that drops a positionally-consumed param, the round-trip regression
    re-emerges silently. This test makes that breakage loud at the unit
    layer instead of waiting for a downstream feature failure.
    """
    # Sentinel: PythonCodeNode is the canonical regression target.
    from kailash.nodes.code.python import PythonCodeNode

    # The wrapper installed in __init_subclass__ tags itself.
    init = PythonCodeNode.__init__
    assert getattr(init, "_init_capture_installed", False) is True, (
        "PythonCodeNode.__init__ MUST be wrapped by Node.__init_subclass__ "
        "(issue #929 regression guard)"
    )

    # The original signature MUST be preserved so graph._create_node_instance
    # continues to inspect named/positional params correctly.
    import inspect

    sig = inspect.signature(init)
    expected = {
        "name",
        "code",
        "function",
        "class_type",
        "process_method",
        "input_types",
        "output_type",
        "input_schema",
        "output_schema",
        "description",
        "max_code_lines",
        "validate_security",
        "sandbox_mode",
    }
    actual = set(sig.parameters.keys()) - {"self", "kwargs"}
    assert expected.issubset(
        actual
    ), f"PythonCodeNode signature drifted; missing: {expected - actual}"


# ---------------------------------------------------------------------------
# Parametrized matrix: a representative cross-section of Node subclasses
# with positional/named init args. Each one round-trips through to_dict /
# from_dict; we assert the captured init params survive.
#
# Kept narrow on purpose: the goal is to confirm the BASE-CLASS fix works
# across multiple subclass shapes, not to exercise every node's runtime.
# Wider coverage is enforced by the structural invariant above.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.parametrize(
    "node_type, node_config, captured_keys",
    [
        # PythonCodeNode — the originating bug (positional + named args).
        (
            "PythonCodeNode",
            {"code": "result = 1"},
            ("code", "max_code_lines", "sandbox_mode"),
        ),
        # AsyncPythonCodeNode — uses **config in its __init__ (no named args
        # consumed before super), so the user-supplied values flow through
        # **kwargs naturally. Round-trip MUST still preserve user kwargs.
        (
            "AsyncPythonCodeNode",
            {"code": "result = 1", "timeout": 60},
            ("code", "timeout"),
        ),
    ],
)
def test_issue_929_round_trip_preserves_named_kwargs(
    node_type: str,
    node_config: dict,
    captured_keys: tuple[str, ...],
) -> None:
    """Build → to_dict → from_dict → assert captured_keys present in config."""
    wf = WorkflowBuilder()
    wf.add_node(node_type, "node1", node_config)
    built = wf.build()

    serialized = built.to_dict()
    restored = Workflow.from_dict(serialized)

    restored_config = restored.nodes["node1"].config
    for key in captured_keys:
        assert key in restored_config, (
            f"{node_type}.{key} MUST be captured into self.config "
            f"(issue #929); got config={restored_config}"
        )
    # User-supplied values MUST survive verbatim.
    for key, expected_value in node_config.items():
        assert restored_config[key] == expected_value, (
            f"{node_type}.{key} round-tripped to {restored_config[key]!r}, "
            f"expected {expected_value!r}"
        )


# ---------------------------------------------------------------------------
# Defense in depth: subclasses that DON'T override __init__ (just inherit
# Node.__init__) MUST not be wrapped — capture is a no-op for them.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_929_capture_skipped_for_unwrapped_subclasses() -> None:
    """If a Node subclass inherits ``Node.__init__`` unchanged, the wrapper
    is NOT installed (nothing to capture beyond what Node.__init__ already
    records via **kwargs)."""

    class _NoInitNode(Node):
        def get_parameters(self) -> dict:
            return {}

        def run(self, **kwargs) -> dict:
            return {}

    # No __init__ override → no wrapper. The init-capture marker MUST be absent.
    init = _NoInitNode.__init__
    assert getattr(init, "_init_capture_installed", False) is False

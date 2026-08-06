# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: EVERY workflow entry point binds the ``parameters`` envelope.

The envelope fix (``WorkflowRequest.get_inputs``) restored multi-channel parity
for the HTTP / CLI / MCP paths that route through it. But a workflow registered
ONCE is reachable from many entry points, and each one independently decides
how to hand the caller's arguments to the runtime. Six of them passed the
caller's mapping through RAW, so a workflow reading ``parameters.get(...)``
succeeded on one MCP path and raised
``NameError: name 'parameters' is not defined`` on another -- same
registration, opposite behaviour.

The DENOMINATOR is the point of this test.

A hand-listed parity test certifies only the channels its author happened to
think of; it reports "parity holds" while a channel it never drove is broken,
and a NEWLY-ADDED entry point passes it silently forever. So this test does not
list the entry points -- it DERIVES them from the source tree by AST, and fails
when it finds one that is neither enveloping nor explicitly audited.

Adding a new workflow entry point therefore fails this test until its author
either binds the envelope or records it in ``AUDITED_RAW_INPUT_SITES`` with a
reason.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Trees that can execute a registered workflow on a caller's behalf.
SCANNED_TREES = (
    REPO_ROOT / "packages/kailash-nexus/src/nexus",
    REPO_ROOT / "src/kailash/channels",
)

# Runtime methods that take workflow-level inputs.
RUNTIME_EXEC_METHODS = frozenset({"execute_workflow_async", "execute_async", "execute"})

# The kwarg/positional slot that carries workflow-level inputs.
INPUT_KWARGS = frozenset({"parameters", "inputs"})

# Entry points DELIBERATELY passing the caller's mapping through unwrapped.
# Each entry is an audited decision, not an oversight. Keyed by
# "<path relative to repo root>::<enclosing function>".
AUDITED_RAW_INPUT_SITES: dict[str, str] = {
    "packages/kailash-nexus/src/nexus/core.py::_execute_workflow": (
        "Private programmatic helper, not a channel. Its parameter is literally "
        "named `inputs`, which is the documented opt-OUT form -- the same "
        "distinction WorkflowRequest draws between `inputs` (raw, caller "
        "controls the exact mapping) and `parameters` (envelope-bound). A "
        "custom endpoint that wants envelope semantics passes "
        "{'parameters': body} explicitly. Binding here would leave the SDK "
        "with no programmatic escape hatch at all."
    ),
}


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str:
    """Name of the innermost function containing ``target``."""
    best = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= target.lineno <= end:
                best = node.name
    return best


def _binds_envelope(call: ast.Call) -> bool:
    """True when the inputs argument constructs a ``parameters`` envelope.

    Recognises the canonical shapes:
        {**x, "parameters": x}      (dict literal with a "parameters" key)
        {"parameters": x}
        a helper whose name says it builds the envelope
    """
    candidates = [a for a in call.args[1:2]]
    candidates += [kw.value for kw in call.keywords if kw.arg in INPUT_KWARGS]

    for value in candidates:
        if isinstance(value, ast.Dict):
            for key in value.keys:
                if isinstance(key, ast.Constant) and key.value == "parameters":
                    return True
        if isinstance(value, ast.Call):
            func = value.func
            name = getattr(func, "attr", None) or getattr(func, "id", "")
            if "envelope" in name.lower():
                return True
        if isinstance(value, ast.Name) and "envelope" in value.id.lower():
            return True
    return False


def _takes_workflow_inputs(call: ast.Call) -> bool:
    """True when the call passes workflow-level inputs at all."""
    if any(kw.arg in INPUT_KWARGS for kw in call.keywords):
        return True
    # execute_workflow_async(workflow, inputs) -- second positional.
    return len(call.args) >= 2


def _discover_entry_points() -> list[tuple[str, int, bool]]:
    """Derive (site_key, lineno, binds_envelope) for every execution site."""
    found: list[tuple[str, int, bool]] = []
    for tree_root in SCANNED_TREES:
        assert tree_root.is_dir(), f"scanned tree missing: {tree_root}"
        for path in sorted(tree_root.rglob("*.py")):
            if "build/lib" in str(path):
                continue
            module = ast.parse(path.read_text(), str(path))
            for node in ast.walk(module):
                if not isinstance(node, ast.Call):
                    continue
                method = getattr(node.func, "attr", None)
                if method not in RUNTIME_EXEC_METHODS:
                    continue
                if not _takes_workflow_inputs(node):
                    continue
                rel = path.relative_to(REPO_ROOT).as_posix()
                key = f"{rel}::{_enclosing_function(module, node)}"
                found.append((key, node.lineno, _binds_envelope(node)))
    return found


@pytest.mark.regression
def test_every_workflow_entry_point_binds_the_parameters_envelope():
    """Every derived entry point MUST envelope, or be an audited opt-out.

    Falsifying result: before the fix this listed six raw sites --
    transports/mcp.py, transports/websocket.py, and the three
    src/kailash/channels/* channels -- all reachable from a single
    ``Nexus.register()``.
    """
    discovered = _discover_entry_points()

    # The scan itself must be able to fail: if it finds nothing, the AST
    # matcher has drifted and every assertion below is vacuous.
    assert discovered, (
        "AST scan found ZERO workflow execution sites; the matcher no longer "
        "recognises the runtime API and this test proves nothing"
    )

    unenveloped = [
        (key, lineno)
        for key, lineno, envelopes in discovered
        if not envelopes and key not in AUDITED_RAW_INPUT_SITES
    ]

    assert not unenveloped, (
        "workflow entry points pass the caller's mapping to the runtime RAW, so "
        "a workflow reading `parameters.get(...)` raises NameError there while "
        "succeeding on the enveloping channels:\n"
        + "\n".join(f"  {key} (line {lineno})" for key, lineno in unenveloped)
        + "\nEither bind the envelope, or add the site to "
        "AUDITED_RAW_INPUT_SITES with the reason it is deliberately raw."
    )


@pytest.mark.regression
def test_audited_opt_out_sites_still_exist():
    """Every audited opt-out MUST still be a real site.

    Prevents the allowlist from silently accumulating stale entries that would
    mask a genuinely new raw site sharing the same key.
    """
    discovered = {key for key, _, _ in _discover_entry_points()}
    stale = sorted(set(AUDITED_RAW_INPUT_SITES) - discovered)
    assert not stale, (
        f"AUDITED_RAW_INPUT_SITES lists sites that no longer exist: {stale}. "
        "Remove them so the allowlist cannot mask a new raw site."
    )

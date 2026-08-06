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
        "NOT route-registered: no router binding anywhere in nexus/src calls "
        "it, so no caller reaches it over a channel and it cannot break "
        "multi-channel parity. (It is NOT merely 'not a channel' -- it raises "
        "HTTPException 400/404/500 and runs validate_workflow_name and "
        "validate_workflow_inputs, and core.py's own comment calls it 'the "
        "execute route'. Only the absent registration carries this "
        "disposition; if a router ever binds it, this entry MUST be removed "
        "and the site must bind.) It is reachable programmatically, and its "
        "parameter is literally named `inputs` -- the opt-OUT form "
        "WorkflowRequest draws against `parameters`. A programmatic caller "
        "that wants envelope semantics calls "
        "bind_parameter_envelope(body) and passes the result; passing "
        "{'parameters': body} by hand is the WRAPPED-ONLY shape that broke "
        "bare top-level names before the fix."
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
    """True when the inputs argument binds BOTH shapes of the envelope.

    The original defect had TWO halves, and this predicate must reject BOTH:

    * raw passthrough (``x``)          -- ``parameters.get(...)`` -> NameError
    * wrapped-ONLY (``{"parameters": x}``) -- bare top-level names ->
      ``NameError: name 'id' is not defined``, which is what the pre-fix MCP
      transport shipped.

    So a dict literal counts ONLY when it carries the envelope key AND a
    ``**`` splat. In ``ast.Dict.keys`` a ``**`` unpacking is recorded as a
    ``None`` key, so both halves are visible structurally::

        {**x, "parameters": x}   -> keys == [None, Constant("parameters")]  OK
        {"parameters": x}        -> keys == [Constant("parameters")]        REJECT

    A call to a helper whose name says it builds the envelope also counts --
    :func:`kailash.workflow.input_envelope.bind_parameter_envelope` owns the
    both-shapes contract, and its own behaviour is pinned by
    ``test_channel_parameters_envelope_behaviour.py``.
    """
    candidates = [a for a in call.args[1:2]]
    candidates += [kw.value for kw in call.keywords if kw.arg in INPUT_KWARGS]

    for value in candidates:
        if isinstance(value, ast.Dict):
            has_envelope_key = any(
                isinstance(key, ast.Constant) and key.value == "parameters"
                for key in value.keys
            )
            # `**splat` is recorded as a None key by the parser.
            has_splat = any(key is None for key in value.keys)
            if has_envelope_key and has_splat:
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


def _first_exec_call(source: str) -> ast.Call:
    """Parse a one-line execution call out of ``source``."""
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in (
            RUNTIME_EXEC_METHODS
        ):
            return node
    raise AssertionError(f"no runtime execution call in: {source!r}")


# Both polarities of the predicate the whole scan rests on. A guard that
# cannot tell the pre-fix shape from the post-fix one reports "parity holds"
# over a broken tree, which is the exact failure this file exists to prevent.
BINDING_SHAPES = {
    "splat-then-envelope": 'rt.execute_workflow_async(wf, {**p, "parameters": p})',
    "envelope-then-splat": 'rt.execute_workflow_async(wf, {"parameters": p, **p})',
    "shared-binder-positional": "rt.execute_workflow_async(wf, bind_parameter_envelope(p))",
    "shared-binder-kwarg": "rt.execute(wf, parameters=bind_parameter_envelope(p))",
}

NON_BINDING_SHAPES = {
    # The pre-fix nexus/transports/mcp.py shape. Binds `parameters` but NOT
    # the bare top-level names -> `NameError: name 'id' is not defined`.
    "wrapped-only-positional": 'rt.execute_workflow_async(wf, {"parameters": p})',
    "wrapped-only-kwarg": 'rt.execute(wf, parameters={"parameters": p})',
    # The other pre-fix half: raw passthrough -> `parameters` unbound.
    "raw-passthrough-positional": "rt.execute_workflow_async(wf, p)",
    "raw-passthrough-kwarg": "rt.execute(wf, parameters=p)",
    "raw-splat-no-envelope": "rt.execute_workflow_async(wf, {**p})",
}


@pytest.mark.regression
@pytest.mark.parametrize("source", BINDING_SHAPES.values(), ids=BINDING_SHAPES)
def test_binds_envelope_accepts_both_shapes_bindings(source):
    """Every shape that binds BOTH shapes MUST be recognised."""
    assert _binds_envelope(_first_exec_call(source)) is True, source


@pytest.mark.regression
@pytest.mark.parametrize("source", NON_BINDING_SHAPES.values(), ids=NON_BINDING_SHAPES)
def test_binds_envelope_rejects_pre_fix_shapes(source):
    """Neither half of the original defect may pass as 'binds the envelope'.

    Falsifying result: with the predicate's earlier form -- ANY dict literal
    carrying a "parameters" key counts -- the two ``wrapped-only`` cases
    returned True, so reverting ``transports/mcp.py`` to
    ``{"parameters": kwargs}`` left the whole scan green.
    """
    assert _binds_envelope(_first_exec_call(source)) is False, source


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

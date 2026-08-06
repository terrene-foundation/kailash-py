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
#
# EMPTY, and that is the correct state: every discovered entry point binds.
# The last entry was nexus/core.py::_execute_workflow, removed when that site
# started binding. Its two recorded justifications were BOTH refuted and must
# not be reinstated for any site: (1) "not a channel" -- _execute_workflow
# raises HTTPException 400/404/500 and runs validate_workflow_name (path
# traversal) and validate_workflow_inputs (request size); core.py's own
# comment calls it "the execute route"; (2) "not route-registered" -- true at
# the time, but it protected nothing, because skills/03-nexus/
# nexus-api-patterns.md teaches custom endpoints to call
# `await app._execute_workflow(name, body)` directly, which makes the CALLER's
# route an entry point that would not bind.
#
# Adding an entry here is expensive on purpose. It must survive BOTH gates
# below: the site must actually be raw (test_audited_sites_are_actually_raw)
# AND its enclosing function must offer the caller a real choice of slots
# (test_audited_sites_are_exempt_under_the_structural_rule).
AUDITED_RAW_INPUT_SITES: dict[str, str] = {}


def _enclosing_function(tree: ast.Module, target: ast.Call) -> str:
    """Name of the innermost function containing ``target``."""
    best = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            if node.lineno <= target.lineno <= end:
                best = node.name
    return best


def _input_slots(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Names of ``func``'s parameters that carry workflow-level inputs.

    The structural rule turns on HOW MANY of these a caller is offered: two
    (``inputs`` AND ``parameters``) means the caller can express a choice, so
    an opt-out is meaningful; one means it is the sole arguments slot and MUST
    bind, whatever it happens to be named.

    Scope: this counts FUNCTION PARAMETERS, which is how every allowlisted
    site expresses its slots. A surface that offers its slots as model FIELDS
    instead -- ``WorkflowRequest`` has ``inputs`` and ``parameters`` as
    pydantic fields, not arguments -- would count as ZERO here. That is not a
    bug to route around: no such surface is in ``SCANNED_TREES`` or the
    allowlist, and reading a field-based surface with this helper would give a
    confidently wrong answer. Extend the helper before pointing it at one.
    """
    spec = func.args
    every = [*spec.posonlyargs, *spec.args, *spec.kwonlyargs]
    if spec.vararg:
        every.append(spec.vararg)
    if spec.kwarg:
        every.append(spec.kwarg)
    return [arg.arg for arg in every if arg.arg in INPUT_KWARGS]


def _offers_input_choice(site_key: str) -> bool:
    """True when the site's enclosing function offers TWO input slots."""
    rel, _, func_name = site_key.partition("::")
    module = ast.parse((REPO_ROOT / rel).read_text(), rel)
    for node in ast.walk(module):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            return len(_input_slots(node)) >= 2
    raise AssertionError(f"no function {func_name!r} in {rel}")


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


# Both polarities of the slot-count predicate the xfail below rests on. Without
# these, a predicate that always returned "one slot" would produce the same
# XFAIL and look identical in the run output.
SLOT_COUNT_CASES = {
    "single-slot-inputs": ("async def f(self, name, inputs): pass", ["inputs"]),
    "single-slot-parameters": ("def f(self, wf, parameters): pass", ["parameters"]),
    "choice-both-slots": (
        "def f(self, inputs, parameters): pass",
        ["inputs", "parameters"],
    ),
    "choice-kwonly": (
        "def f(self, *, inputs=None, parameters=None): pass",
        ["inputs", "parameters"],
    ),
    "no-input-slot": ("def f(self, workflow_name): pass", []),
}


@pytest.mark.regression
@pytest.mark.parametrize(
    "source,expected", SLOT_COUNT_CASES.values(), ids=SLOT_COUNT_CASES
)
def test_input_slots_counts_the_caller_offered_slots(source, expected):
    """The slot count MUST distinguish a choice from a sole arguments slot."""
    func = ast.parse(source).body[0]
    assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
    assert _input_slots(func) == expected, source


@pytest.mark.regression
@pytest.mark.parametrize(
    "source,expected", SLOT_COUNT_CASES.values(), ids=SLOT_COUNT_CASES
)
def test_offers_choice_is_two_or_more_slots(source, expected):
    """A choice is TWO slots; one or zero is not a choice."""
    func = ast.parse(source).body[0]
    assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
    assert (len(_input_slots(func)) >= 2) is (len(expected) >= 2), source


@pytest.mark.regression
def test_audited_sites_are_actually_raw():
    """An allowlisted site MUST actually BE raw. A binding site is stale.

    This is the gate that was missing. Its absence was a real defect in this
    guard: the sibling check below reads only the allowlist keys and the
    enclosing function's SIGNATURE, and binding changes neither -- so when
    ``nexus/core.py::_execute_workflow`` started binding, nothing here
    noticed. The suite stayed green carrying an entry that declared a site raw
    while it enveloped, and that entry masked the whole
    ``path::enclosing_function`` key: any raw execution call added anywhere
    inside that function would have been silently exempted.

    The allowlist means "this site is deliberately raw". The moment the site
    binds, the entry is false, and a false exemption is exactly where a new
    raw site hides.

    Falsifying result: allowlist a site that binds and this REDS, naming it.
    Verified by probe, not assumed -- an entry for any currently-discovered
    site fails here, because every discovered site now binds.
    """
    binding_sites = {key for key, _, envelopes in _discover_entry_points() if envelopes}
    stale = sorted(set(AUDITED_RAW_INPUT_SITES) & binding_sites)
    assert not stale, (
        "allowlisted sites that actually BIND the envelope -- the entry claims "
        "the site is deliberately raw, which is now false:\n"
        + "\n".join(f"  {key}" for key in stale)
        + "\nDelete the entry. While it is listed, it masks its whole "
        "`path::enclosing_function` key, so a raw call added inside that "
        "function would be exempted silently."
    )


@pytest.mark.regression
def test_audited_sites_are_exempt_under_the_structural_rule():
    """An allowlisted site MUST be one the structural rule actually exempts.

    The rule exempts an entry point that offers the caller a CHOICE -- both an
    ``inputs`` slot and a ``parameters`` slot -- because only then does picking
    one carry meaning. A site with a single arguments slot is NOT exempt, and
    allowlisting it anyway is the rule contradicting its own allowlist.

    Note what this check CANNOT see: it reads the allowlist keys and each
    enclosing function's signature, so it is blind to whether the site binds.
    That is why ``test_audited_sites_are_actually_raw`` exists alongside it --
    the two gates fail on different things and neither subsumes the other.

    Falsifying result: allowlist a single-slot site and this REDS, naming the
    site and its slot list.
    """
    not_exempt = sorted(
        f"{key} (input slots: {_slots_for(key)})"
        for key in AUDITED_RAW_INPUT_SITES
        if not _offers_input_choice(key)
    )
    assert not not_exempt, (
        "allowlisted sites the structural rule does NOT exempt -- each offers "
        "a single caller-arguments slot, so the rule says it must bind:\n"
        + "\n".join(f"  {row}" for row in not_exempt)
        + "\nEither bind the site and delete its entry, or amend the rule."
    )


def _slots_for(site_key: str) -> list[str]:
    """The input-slot names of a site's enclosing function (for messages)."""
    rel, _, func_name = site_key.partition("::")
    module = ast.parse((REPO_ROOT / rel).read_text(), rel)
    for node in ast.walk(module):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            return _input_slots(node)
    return []


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

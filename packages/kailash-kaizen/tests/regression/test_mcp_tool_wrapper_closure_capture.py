"""Regression: MCP tool auto-registration was dead -- the wrapper could not register.

`MCPMixin.expose_as_mcp_server` auto-registers agent methods as MCP tools by
wrapping each one. The wrapper bound the method with the default-argument idiom::

    async def tool_wrapper(_bound_method=method, **kwargs): ...

That idiom is the usual way to dodge Python's late-binding-in-a-loop trap, and
in an ordinary closure it is fine. It is wrong for a function whose signature a
framework *introspects to build a published schema*.

WHAT THE DEFECT ACTUALLY IS -- measured by driving the real registration path,
not by inspecting the signature in isolation::

    POST-FIX (**kwargs)                    : REGISTERED OK
    PRE-FIX  (_bound_method=..., **kwargs) : REJECTED ->
        InvalidSignature: Parameter _bound_method ... cannot start with '_'

The pre-fix wrapper could not register AT ALL, so `expose_as_mcp_server` raised
for every auto-generated tool and the feature was dead for every agent. **This
is a FUNCTIONAL repair, not a security fix.**

CORRECTION -- an earlier version of this file claimed `_bound_method` "was
advertised to every client as a tool argument" and that a client passing it
could displace the bound method. **That is refuted.** Registration raises before
any schema is published, so the parameter never reaches a client and there is no
exploitable surface. The claim came from measuring `inspect.signature` on a
MIRROR of the wrapper instead of driving `expose_as_mcp_server` -- an instrument
that could not observe the rejection it needed to see. The tie to #2025 is a
shared ROOT CAUSE (internal closure state in a framework-introspected signature),
NOT shared exploitability.

VERSION-DEPENDENT, and two observations disagree. A reviewer with the standalone
`fastmcp` 2.12.4 importable saw BOTH shapes rejected, on a different rule
(``Functions with **kwargs are not supported as tools``). Here, with the official
FastMCP reached via `kailash_mcp.server` and the standalone module absent, only
the pre-fix shape is rejected and the post-fix shape registers. The fix is right
either way -- it strictly removes one rejection cause -- but under the stack that
reviewer measured, ``**kwargs`` is a SECOND, independent reason auto-registration
cannot work. That is tracked separately; this change does not claim to fix it.

These tests assert the internal name is gone from the signature AND that the two
behaviours the default-arg idiom provided still hold -- correct dispatch and
correct per-iteration binding. A fix dropping either would be worse than the bug.
"""

import asyncio
import inspect

import pytest


def _make_tool_wrapper(bound_method):
    """The post-fix construction, mirrored from ``mcp_mixin.py``.

    Mirrored rather than imported because ``register_as_mcp_server`` needs a live
    FastMCP server to reach the registration loop. The structural test below pins
    this against the real source, so the mirror cannot silently drift from it.
    """

    async def tool_wrapper(**kwargs):
        result = bound_method(**kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return result

    return tool_wrapper


@pytest.mark.regression
def test_wrapper_does_not_advertise_internal_state_as_a_tool_parameter():
    """CONTROL (passes pre- and post-fix): the mirror has no internal parameter.

    Runs against the module-local mirror, so it passes against broken source too
    and is NOT a detector. It documents the intended shape and would catch a
    regression in the mirror itself. The discriminating tests are
    ``test_real_source_binds_via_enclosing_scope_not_a_default_argument`` and
    ``test_pre_fix_wrapper_shape_is_rejected_by_real_registration``.
    """
    wrapper = _make_tool_wrapper(lambda x=1: x)
    params = list(inspect.signature(wrapper).parameters)

    assert params == ["kwargs"], (
        f"tool wrapper advertises {params!r}; anything beyond **kwargs is "
        "published to MCP clients as a callable tool argument"
    )
    assert "_bound_method" not in params


@pytest.mark.regression
def test_client_supplied_bound_method_cannot_displace_the_real_one():
    """A client arg named like the old internal must be data, not control.

    Pre-fix this bound to the named parameter and the wrapper then tried to call
    the client's value. Post-fix it lands in **kwargs and is passed through to
    the method as an ordinary argument.
    """
    seen = {}

    def method(**kwargs):
        seen.update(kwargs)
        return "real-method-ran"

    wrapper = _make_tool_wrapper(method)
    result = asyncio.run(wrapper(_bound_method="attacker-supplied"))

    assert result == "real-method-ran", "the real bound method did not run"
    assert seen == {"_bound_method": "attacker-supplied"}, (
        "the client value must arrive as ordinary data in **kwargs, not as "
        f"control over which callable runs; got {seen!r}"
    )


# --- negative controls: the fix must not break what the idiom provided -------


@pytest.mark.regression
def test_normal_dispatch_and_await_still_work():
    """Sync and async methods both still dispatch and return their value."""

    def sync_method(x):
        return x * 2

    async def async_method(x):
        return x * 3

    assert asyncio.run(_make_tool_wrapper(sync_method)(x=21)) == 42
    assert asyncio.run(_make_tool_wrapper(async_method)(x=14)) == 42


@pytest.mark.regression
def test_each_wrapper_binds_its_own_method_across_a_loop():
    """The late-binding trap the default-arg idiom existed to prevent.

    A naive `async def w(**kw): return method(**kw)` defined directly inside the
    registration loop would close over the LOOP VARIABLE, so every registered
    tool would dispatch to the last method. This is the test that would catch
    that regression -- without it, removing the default arg could silently make
    every MCP tool call the same function.
    """
    methods = [(lambda n=n: (lambda: f"tool-{n}"))() for n in range(3)]
    wrappers = [_make_tool_wrapper(m) for m in methods]

    results = [asyncio.run(w()) for w in wrappers]
    assert results == [
        "tool-0",
        "tool-1",
        "tool-2",
    ], f"wrappers do not bind per-iteration methods: {results!r}"


@pytest.mark.regression
def test_pre_fix_wrapper_shape_is_rejected_by_real_registration():
    """EVIDENCE for the harm claim -- NOT a source-regression detector.

    Pins the FRAMEWORK's behaviour, using probe functions defined here, so it
    passes against both broken and fixed source. It does not red if the source
    regresses; ``test_real_source_binds_via_enclosing_scope_not_a_default_argument``
    is the only test that does.

    It earns its place by substantiating the claim the rest of the file makes.
    The absence of exactly this check is what let the wrong story be told about
    this bug: inspecting ``inspect.signature`` on a mirror shows ``_bound_method``
    present and invites the conclusion that it is published to clients. Driving
    real registration shows it is REJECTED before any schema exists -- a
    different defect (dead feature) with a different severity (no exploitable
    surface). A harm claim with no instrument behind it is how the first version
    of this file overstated its own finding.
    """
    pytest.importorskip("kailash_mcp", reason="MCP server package not installed")
    from kailash_mcp.server import MCPServer

    server = MCPServer("regression-probe")

    async def post_fix(**kwargs):
        return kwargs

    async def pre_fix(_bound_method=None, **kwargs):
        return kwargs

    # POSITIVE: the shipped shape must register.
    server.tool()(post_fix)

    # NEGATIVE: the pre-fix shape must be refused, and the error must name the
    # offending parameter -- otherwise this passes on an unrelated failure.
    with pytest.raises(Exception) as exc:
        server.tool()(pre_fix)
    assert "_bound_method" in str(exc.value), (
        "registration failed for a reason unrelated to the internal parameter; "
        f"this test would then be non-discriminating. Got: {exc.value!r}"
    )


@pytest.mark.regression
def test_real_source_binds_via_enclosing_scope_not_a_default_argument():
    """Structural pin against the actual module, so the mirror cannot drift.

    Asserts the shipped module declares no ``tool_wrapper`` carrying parameters
    beyond ``**kwargs``. Paired with the behavioural tests above rather than
    standing alone: on its own it would pass against a rewrite that merely
    renamed the parameter.

    Parsed via AST, NOT a source grep. A grep for the old idiom also matches
    this module's own explanatory comment quoting it -- a substring scan cannot
    tell code from prose about code, so it reports on the wrong thing. This
    test was first written as a grep and failed in exactly that way.
    """
    import ast

    import kaizen.core.mcp_mixin as mcp_mixin

    tree = ast.parse(inspect.getsource(mcp_mixin))
    wrappers = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "tool_wrapper"
    ]
    assert wrappers, "no tool_wrapper found in mcp_mixin; has it been renamed?"

    for fn in wrappers:
        a = fn.args
        named = [p.arg for p in (a.posonlyargs + a.args + a.kwonlyargs)]
        assert not named, (
            f"tool_wrapper at line {fn.lineno} declares {named!r}; a named "
            "parameter on an MCP-registered wrapper is published to clients as "
            "a tool argument and can be bound by them -- bind via an enclosing "
            "scope instead"
        )
        assert (
            a.kwarg is not None
        ), f"tool_wrapper at line {fn.lineno} cannot forward client arguments"

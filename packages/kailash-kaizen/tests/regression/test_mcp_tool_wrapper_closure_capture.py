"""Regression: MCP tool wrappers published internal state as a tool parameter.

`MCPMixin` auto-registers agent methods as MCP tools by wrapping each one. The
wrapper used the default-argument idiom to bind the method::

    async def tool_wrapper(_bound_method=method, **kwargs): ...

That idiom is the usual way to dodge Python's late-binding-in-a-loop trap, and
in an ordinary closure it is fine. It is wrong for a function whose signature
is *introspected to build a published schema*: an MCP server derives the tool's
advertised parameters from the signature, so `_bound_method` was advertised to
every client as a tool argument. Because it is a NAMED parameter, a client
passing `_bound_method` binds to it directly and never reaches `**kwargs`,
displacing the bound method.

Same class as the FastAPI defect in #2025, where handler default arguments were
treated as caller-writable query parameters and let a caller redirect a proxy to
an arbitrary host. Different framework, identical root cause: internal closure
state placed in a signature that a framework reads as a public contract.

The fix binds through an enclosing scope instead. These tests assert BOTH that
the internal name is gone from the public signature AND that the two behaviours
the default-arg idiom was providing still hold -- correct dispatch, and correct
per-iteration binding. A fix that dropped either would be worse than the defect.
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
    """The headline defect: internal binding must not appear in the signature."""
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

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

SECOND DEFECT, same root cause, fixed here. An earlier version of this file
recorded that a reviewer with `fastmcp` 2.12.4 saw BOTH shapes rejected on a
different rule (``Functions with **kwargs are not supported as tools``) and
concluded it was "tracked separately; this change does not claim to fix it".
That deferral is now closed, because the second rejection is not version-noise
-- it is the SAME defect one layer down. Driving the real path against FastMCP
2.12.4::

    a.expose_as_mcp_server("probe", tools=["greet"])
    -> ValueError: Functions with **kwargs are not supported as tools

Removing ``_bound_method`` from the signature was necessary but not sufficient:
a bare ``**kwargs`` wrapper carries NO signature and NO annotations, and the
server builds the tool's published schema from exactly those. FastMCP refuses to
register a variadic function at all, so ``expose_as_mcp_server`` still raised for
every auto-generated tool and the feature was still dead for every agent.

The repair is ``functools.wraps(bound_method)`` on the wrapper: it copies the
method's signature (via ``__wrapped__``) and its annotations onto the wrapper, so
the tool registers AND advertises the method's REAL parameters. Without it the
published schema would have been empty even where registration succeeded -- a
tool no client could call correctly. Un-publishable methods (variadic, or an
annotation the server cannot render as JSON schema) no longer abort the whole
server: auto-discovered ones warn and are skipped, explicitly requested ones
still raise.

These tests assert the internal name is gone from the signature, that real
registration now succeeds and publishes the method's own parameters, AND that
the two behaviours the default-arg idiom provided still hold -- correct dispatch
and correct per-iteration binding. A fix dropping either would be worse than the
bug.
"""

import asyncio
import functools
import inspect

import pytest


def _make_tool_wrapper(bound_method):
    """The post-fix construction, mirrored from ``mcp_mixin.py``.

    Mirrored rather than imported because ``register_as_mcp_server`` needs a live
    FastMCP server to reach the registration loop. The structural test below pins
    this against the real source, so the mirror cannot silently drift from it.
    """

    @functools.wraps(bound_method)
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
    ``test_expose_as_mcp_server_publishes_the_agent_methods_own_schema``.
    """

    def method(x: int = 1) -> int:
        return x

    wrapper = _make_tool_wrapper(method)

    # DECLARED parameters -- what the wrapper itself accepts. `follow_wrapped`
    # is off because `functools.wraps` makes the default resolve to the wrapped
    # method's signature, which is the *published* view asserted below.
    declared = list(inspect.signature(wrapper, follow_wrapped=False).parameters)
    assert declared == ["kwargs"], (
        f"tool wrapper declares {declared!r}; internal state in the declared "
        "signature is what the original defect published to clients"
    )
    assert "_bound_method" not in declared

    # PUBLISHED parameters -- what the server derives the tool schema from. It
    # must be the METHOD's own signature, not an empty one.
    published = list(inspect.signature(wrapper).parameters)
    assert published == ["x"], (
        f"tool wrapper publishes {published!r}; the schema must carry the "
        "method's real parameters or no client can call the tool correctly"
    )


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
def test_expose_as_mcp_server_publishes_the_agent_methods_own_schema():
    """The detector for the dead-feature defect: drives the REAL path.

    Reds against broken source rather than pinning framework behaviour with
    local probes -- the weakness of the version this replaces, which asserted
    that a bare ``**kwargs`` probe registers. It does not: FastMCP 2.12.4
    refuses variadic functions outright, so that assertion described a shape the
    server rejects, and the shipped wrapper it stood in for was equally
    unregistrable. ``expose_as_mcp_server`` raised for every agent.

    Asserting the PUBLISHED SCHEMA, not just that registration returned, is what
    makes this discriminating twice over: a wrapper that registered but carried
    no signature would advertise an empty schema, and a client would have no way
    to call the tool. The old internal name must be absent from that schema.
    """
    pytest.importorskip("kailash_mcp", reason="MCP server package not installed")
    from kaizen.core.mcp_mixin import MCPMixin

    class _ProbeAgent(MCPMixin):
        agent_id = "regression-probe"

        def greet(self, name: str, excited: bool = False) -> str:
            """Greet someone."""
            return f"hi {name}{'!' if excited else ''}"

    server = _ProbeAgent().expose_as_mcp_server(
        "regression-probe", tools=["greet"], enable_auto_discovery=False
    )

    entry = server.get_tool_by_name("greet")
    assert entry is not None, (
        "expose_as_mcp_server registered no tool for an ordinary agent method; "
        "auto-registration is dead"
    )

    schema = entry["function"].parameters
    assert set(schema["properties"]) == {"name", "excited"}, (
        f"published tool schema is {schema['properties']!r}; it must carry the "
        "method's real parameters, otherwise no client can call the tool"
    )
    assert (
        "_bound_method" not in schema["properties"]
    ), "internal closure state is published to clients as a tool argument"
    assert schema["required"] == ["name"]

    result = asyncio.run(entry["function"].run({"name": "bob", "excited": True}))
    assert result.content[0].text == "hi bob!", "the registered tool did not dispatch"


@pytest.mark.regression
def test_unpublishable_method_does_not_abort_the_whole_server():
    """One un-publishable method must not kill every other tool.

    A variadic method cannot become an MCP tool. Before the fix ANY such method
    on the agent raised out of ``expose_as_mcp_server``, so a single one took
    down the entire server -- the failure mode that made this feature dead.
    Auto-discovery sweeps every public attribute and so always meets one.
    """
    pytest.importorskip("kailash_mcp", reason="MCP server package not installed")
    from kaizen.core.mcp_mixin import MCPMixin

    class _ProbeAgent(MCPMixin):
        agent_id = "regression-probe"

        def greet(self, name: str) -> str:
            """Greet someone."""
            return f"hi {name}"

        def variadic(self, **kwargs):
            """Cannot be expressed as an MCP tool."""
            return kwargs

    agent = _ProbeAgent()

    server = agent.expose_as_mcp_server("regression-probe", enable_auto_discovery=False)
    assert (
        server.get_tool_by_name("greet") is not None
    ), "a publishable method was dropped because a sibling was un-publishable"
    assert server.get_tool_by_name("variadic") is None

    # An EXPLICIT request is a demand, not a sweep: it must fail loudly rather
    # than hand back a server silently missing the tool the caller named.
    with pytest.raises(ValueError, match="variadic"):
        agent.expose_as_mcp_server(
            "regression-probe", tools=["variadic"], enable_auto_discovery=False
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

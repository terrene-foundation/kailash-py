"""Regression: the #1998 projection's own preconditions must be PROVEN, not assumed.

Sibling of ``test_issue_1998_r3_registration_hygiene.py``, which covers the
re-registration defects themselves. This file covers the three places the
projection machinery previously took something on trust.

R3-MED-3 — ``_fastmcp_tool_container`` could not tell a LIVE mapping from a COPY.
    It returned the first ``_tools`` attribute that was a ``dict``. If an
    implementation hands back a defensive copy, every ``pop`` / assignment in
    ``_withhold_tool_from_fastmcp`` and ``_restore_tool_to_fastmcp`` lands on an
    object FastMCP never reads: ``disable_tool`` reports success, the tool stays
    advertised, and every test that inspects the returned mapping still passes
    because the copy faithfully reflects the write. Fail-open here is
    indistinguishable from working, so the container must now PROVE liveness and
    the caller must raise when it cannot.

    Two copy shapes, needing two different proofs:
      * FRESH copy per access — caught by the public read alone
        (``owner._tools is container`` fails on the second access).
      * ONE cached copy, identity-stable — passes the public read; caught only
        by asking whether the mapping is the STORED instance attribute rather
        than something a descriptor computed. ``_CachedCopyFastMCP`` below
        exists specifically to isolate that second proof; without it a
        regression that dropped it would go unnoticed.

    Both proofs are READS. An earlier version wrote a sentinel key and removed
    it in a ``finally``; that was observable from inside the window, so it
    introduced a disclosure on the surface this machinery gates. See
    ``test_proving_liveness_writes_nothing_into_the_live_container``.

R3-HIGH-1 (third site) — ``_restore_tool_to_fastmcp`` overwrote a LIVE entry.
    ``tool()`` drops the park in the same step that replaces a registration, so
    a park co-existing with a live entry means some OTHER path replaced it.
    Writing the parked (older) object back republishes that registration's
    advertised schema and dispatches its wrapper — which closes over ITS
    ``required_permission``. The invariant is held at all three sites that can
    break it; this is the one that holds against a caller the other two never saw.

R3-MED-2 (enumeration) — the projection applied 2 of the 3 fields the view
    decides. The mechanical enumeration below is what stops that shape from
    recurring: a NEW key in ``_public_tool_view``'s output fails the test until
    the author records whether the projection mirrors it and why.

FALSIFYING RESULTS, each observed against the pre-fix code:
  * ``MCPServer("x", ...)`` registering a gated tool against ``_CopyingFastMCP``
    returned normally and ``disable_tool`` returned ``True`` while the real store
    still held the tool (silent non-enforcement).
  * a park re-seeded alongside a live entry was written back over it by
    ``enable_tool``.
  * ``set(_public_tool_view(...))`` contained ``outputSchema`` with no
    corresponding projection.
"""

import pytest
from kailash_mcp.advanced.features import ToolAnnotation
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import MCPError
from kailash_mcp.server import MCPServer

pytestmark = pytest.mark.regression


def _auth_server(name: str) -> MCPServer:
    return MCPServer(
        name,
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )


class _Entry:
    """A registration object shaped enough for the projection to act on."""

    def __init__(self, fn):
        self.fn = fn
        self.parameters = {"type": "object", "properties": {"q": {}}}
        self.description = "live"
        self.output_schema = None


class _FreshCopyFastMCP:
    """``_tools`` builds a NEW dict on every access."""

    def __init__(self):
        self._store = {}

    @property
    def _tools(self):
        return dict(self._store)

    def get_tool(self, name):
        return self._store.get(name)

    def tool(self, *args, **kwargs):
        def decorator(func):
            self._store[func.__name__] = _Entry(func)
            return func

        return decorator


class _CachedCopyFastMCP:
    """``_tools`` is ONE cached snapshot — identity-stable, still not the store.

    The pathological case: ``getattr(owner, "_tools")`` returns the same object
    every time, so an identity re-read cannot distinguish it from the real
    container. Dispatch reads ``_store``, so a write into the snapshot is
    invisible — which only the stored-attribute proof can show.
    """

    def __init__(self):
        self._store = {}
        self._snapshot = {}

    @property
    def _tools(self):
        return self._snapshot

    def get_tool(self, name):
        return self._store.get(name)  # dispatch reads the REAL store

    def tool(self, *args, **kwargs):
        def decorator(func):
            entry = _Entry(func)
            self._store[func.__name__] = entry
            self._snapshot[func.__name__] = entry  # snapshot looks correct
            return func

        return decorator


# ---------------------------------------------------------------------------
# R3-MED-3 — liveness is proven, and failure is loud
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(_FreshCopyFastMCP, id="fresh_copy_per_access"),
        pytest.param(_CachedCopyFastMCP, id="cached_copy_identity_stable"),
    ],
)
def test_gated_registration_refuses_a_container_it_cannot_prove_live(factory):
    """Refuse to register rather than apply the gate to a throwaway object."""
    server = _auth_server(f"r3-live-{factory.__name__}")
    server._mcp = factory()

    with pytest.raises(MCPError, match="tool-disclosure gate"):

        @server.tool(required_permission="admin.write")
        def admin_purge(scope: str) -> str:
            """Purge.

            Args:
                scope: what to purge.
            """
            return "purged"


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(_FreshCopyFastMCP, id="fresh_copy_per_access"),
        pytest.param(_CachedCopyFastMCP, id="cached_copy_identity_stable"),
    ],
)
def test_disable_refuses_a_container_it_cannot_prove_live(factory):
    """A withhold that cannot take effect must raise, never report success."""
    server = MCPServer(f"r3-live-disable-{factory.__name__}")
    server._mcp = factory()

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    with pytest.raises(MCPError, match="tool-disclosure gate"):
        server.disable_tool("echo")

    assert "echo" in server._mcp._store, (
        "CONTROL for the test above: the withhold genuinely did not take "
        "effect, which is exactly why it had to raise"
    )


def test_identity_stable_copy_is_rejected_by_the_stored_attribute_proof():
    """Isolate proof 2: the public read alone accepts the cached copy.

    Without this, an implementation that kept only ``owner._tools is container``
    would still pass every other test in this file — the fresh-copy fixture is
    caught by that read on its own. A cached copy is identity-STABLE, which is
    exactly why the second proof has to ask a different question: is this the
    STORED attribute, or something a descriptor computed?
    """
    server = MCPServer("r3-live-proof2")
    server._mcp = _CachedCopyFastMCP()
    owner = server._mcp
    container = owner._tools

    assert getattr(owner, "_tools", None) is container, (
        "this fixture is identity-STABLE by construction; if that ever stops "
        "holding it no longer isolates the second proof"
    )
    assert server._fastmcp_tool_container_is_live(owner, container) is False, (
        "an identity-stable mapping that dispatch does not read was accepted " "as live"
    )


class _RecordingDict(dict):
    """A container that records every mutation attempted against it."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.mutations = []

    def __setitem__(self, key, value):
        self.mutations.append(("set", key))
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.mutations.append(("del", key))
        super().__delitem__(key)

    def pop(self, key, *default):
        self.mutations.append(("pop", key))
        return super().pop(key, *default)


def test_proving_liveness_writes_nothing_into_the_live_container():
    """The proof must not put anything in the container, even transiently.

    An earlier version wrote a sentinel key and removed it in a ``finally``.
    That was observable: instrumenting a read inside the window showed
    ``['__kailash_fastmcp_liveness_probe__', 'gated']``, so a ``tools/list``
    landing there would have advertised the probe key to an uncredentialed
    caller — a disclosure on the exact surface this machinery gates.

    A window that only MIGHT be raced is not closed, so the proof was changed
    to read-only rather than made faster. This asserts the property directly:
    zero mutations while resolving. It cannot be satisfied by a write that is
    merely cleaned up afterwards.
    """
    server = MCPServer("r3-live-nowrite")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    manager = server._mcp._tool_manager
    recording = _RecordingDict(manager._tools)
    manager._tools = recording
    recording.mutations.clear()

    resolved = server._fastmcp_tool_container()

    assert resolved is recording, "the recording container was not accepted"
    assert recording.mutations == [], (
        "proving liveness mutated the LIVE container; anything enumerating "
        f"tools in that window observes it: {recording.mutations}"
    )
    assert sorted(recording) == ["echo"]


def test_live_container_is_accepted_and_left_untouched():
    """CONTROL: the proof must not reject the real thing, nor pollute it."""
    server = MCPServer("r3-live-control")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    container = server._fastmcp_tool_container()
    assert container is not None, "the real FastMCP container was rejected"
    assert (
        container is server._mcp._tool_manager._tools
    ), "the returned mapping must BE the one FastMCP dispatches from"
    assert sorted(container) == [
        "echo"
    ], f"resolving the container changed its contents: {sorted(container)}"

    server.disable_tool("echo")  # must not raise
    server.enable_tool("echo")  # must not raise
    assert sorted(container) == ["echo"]


# ---------------------------------------------------------------------------
# R3-HIGH-1 third site — restore must not overwrite a live entry
# ---------------------------------------------------------------------------


def test_restore_discards_a_park_that_co_exists_with_a_live_entry():
    """The parked object is from a superseded registration; the live one wins."""
    server = _auth_server("r3-restore-guard")

    @server.tool()
    def widget(payload: str = "v1") -> str:
        """V1 ungated."""
        return "V1-BODY"

    server.disable_tool("widget")
    stale = server._fastmcp_withheld_tools["widget"]

    @server.tool(required_permission="admin.write")
    def widget(scope: str) -> str:  # noqa: F811 — same name ON PURPOSE
        """V2 gated."""
        return "V2-BODY"

    container = server._fastmcp_tool_container()
    live = container["widget"]

    # Simulate a path that replaced the registration WITHOUT clearing the park.
    # ``tool()`` clears it today; this pins the guard that holds when something
    # else does not.
    server._fastmcp_withheld_tools["widget"] = stale
    server.enable_tool("widget")

    assert container["widget"] is live, (
        "enable_tool overwrote the CURRENT registration with a superseded one; "
        "its wrapper closes over the superseded permission set"
    )
    assert (
        "widget" not in server._fastmcp_withheld_tools
    ), "the stale park must be drained, not left to fire on the next enable"


def test_disable_withholds_even_when_a_stale_park_exists():
    """The withhold must key on CONTAINER MEMBERSHIP, never on the park dict.

    ``_withhold_tool_from_fastmcp`` used to early-return when the name was
    already parked. ``tool()`` now drains the park at re-registration, which
    makes that guard unreachable through the ordinary sequence — so the
    sibling file's re-registration tests pass either way and cannot pin this.
    The state that DOES reach it is a park co-existing with a live entry, and
    there the old guard made ``disable_tool`` a silent no-op: it returned True
    while the tool stayed advertised.
    """
    server = _auth_server("r3-withhold-stale-park")

    @server.tool()
    def widget(payload: str = "v1") -> str:
        """V1 ungated."""
        return "V1-BODY"

    server.disable_tool("widget")
    stale = server._fastmcp_withheld_tools["widget"]

    @server.tool(required_permission="admin.write")
    def widget(scope: str) -> str:  # noqa: F811 — same name ON PURPOSE
        """V2 gated."""
        return "V2-BODY"

    container = server._fastmcp_tool_container()
    live = container["widget"]
    server._fastmcp_withheld_tools["widget"] = stale  # the reachable state

    assert server.disable_tool("widget") is True
    assert "widget" not in container, (
        "disable_tool reported success while leaving the tool advertised on "
        "the default transport — the #1998 disclosure, reopened"
    )
    assert server._fastmcp_withheld_tools["widget"] is live, (
        "the park must now hold the CURRENT registration; keeping the stale "
        "one would hand enable_tool a superseded permission closure"
    )


def test_restore_still_reinstates_when_no_live_entry_exists():
    """CONTROL: the guard keys on a LIVE entry, not on refusing every restore."""
    server = MCPServer("r3-restore-control")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    container = server._fastmcp_tool_container()
    original = container["echo"]

    server.disable_tool("echo")
    assert "echo" not in container
    server.enable_tool("echo")

    assert container["echo"] is original


# ---------------------------------------------------------------------------
# R3-MED-2 enumeration — every field the view decides has a recorded disposition
# ---------------------------------------------------------------------------


# Mirrored onto the FastMCP registration by ``_project_tool_onto_fastmcp``.
# view key -> the registration attribute it is written to. Both halves are
# CHECKED against a real registration below, so this table cannot drift into
# describing a projection the code no longer performs.
PROJECTED_ONTO_FASTMCP = {
    "description": "description",
    "inputSchema": "parameters",
    "outputSchema": "output_schema",  # R3-MED-2
}

# Decided by the view but deliberately NOT written onto the registration.
NOT_PROJECTED_WITH_REASON = {
    # The container KEY. It identifies the registration; the projection looks the
    # entry up BY it, so it is equal by construction and cannot be rewritten.
    "name": "the container key — equal by construction",
    # FastMCP derives annotations for NO tool: ``self._mcp.tool()`` is called
    # with no annotations argument, so ``entry.annotations`` is None for gated
    # and ungated alike. There is nothing to SUPPRESS, and writing them would
    # ADD disclosure to gated tools only — the opposite direction from the gate,
    # and an inconsistency with every ungated tool. Advisory hints never gate
    # authorization (see ``_handle_list_tools``), so withholding costs nothing.
    "annotations": "FastMCP derives none for any tool; nothing to suppress",
}


def _enumeration_server() -> MCPServer:
    """A gated and an ungated tool, each declaring every optional view input.

    Both return ``dict[str, int]`` ON PURPOSE: FastMCP derives an output schema
    from the RETURN annotation, so the gated registration genuinely has a result
    shape to suppress. With an un-annotated return there would be nothing to
    clear and the outputSchema assertion below could not fail.
    """
    server = _auth_server("r3-enumeration")
    annotation = ToolAnnotation(is_read_only=True)
    declared = {
        "input_schema": {"type": "object", "properties": {"scope": {}}},
        "output_schema": {"type": "object", "properties": {"rows": {}}},
        "annotations": annotation,
        "description": "Declared.",
    }

    @server.tool(required_permission="admin.write", **declared)
    def gated(scope: str) -> dict[str, int]:
        """Gated."""
        return {}

    @server.tool(**declared)
    def ungated(scope: str) -> dict[str, int]:
        """Ungated."""
        return {}

    return server


def _every_key_the_view_can_emit(server: MCPServer) -> set:
    """Union over both tools — the complete set of fields the view decides."""
    keys = set()
    for name in ("gated", "ungated"):
        view = server._public_tool_view(name, server._tool_registry[name])
        assert view is not None
        keys |= set(view)
    return keys


def test_every_view_field_has_a_projection_disposition():
    """A new advertised field must not be able to skip the default transport.

    R3-MED-2 was exactly this: the view grew ``outputSchema`` and the projection
    silently kept mirroring two fields. Enumerating both sets here converts
    "somebody remembers to update the projection" into a failing test.
    """
    emitted = _every_key_the_view_can_emit(_enumeration_server())
    accounted = set(PROJECTED_ONTO_FASTMCP) | set(NOT_PROJECTED_WITH_REASON)

    assert emitted <= accounted, (
        "_public_tool_view now decides a field with no recorded projection "
        "disposition. Either mirror it in _project_tool_onto_fastmcp and add it "
        "to PROJECTED_ONTO_FASTMCP, or record why it is withheld in "
        f"NOT_PROJECTED_WITH_REASON: {sorted(emitted - accounted)}"
    )
    assert accounted <= emitted, (
        "a field is recorded here that the view no longer emits; drop the stale "
        f"entry: {sorted(accounted - emitted)}"
    )


def test_each_projected_field_actually_reaches_the_registration():
    """Bind the table above to observed behaviour, not to its own prose.

    Without this the enumeration is bookkeeping: it would still pass for a
    projection that dropped a field it claims to mirror — which IS R3-MED-2's
    failure shape, one layer up. Every entry in PROJECTED_ONTO_FASTMCP is
    checked against a real gated registration here.
    """
    server = _enumeration_server()
    entry = server._fastmcp_tool_container()["gated"]
    view = server._public_tool_view("gated", server._tool_registry["gated"])

    for view_key, attr in PROJECTED_ONTO_FASTMCP.items():
        advertised = getattr(entry, attr, None)
        if view_key in view:
            assert advertised == view[view_key], (
                f"the projection claims to mirror {view_key!r} onto "
                f"entry.{attr}, but the registration advertises {advertised!r} "
                f"while the view decided {view[view_key]!r}"
            )
        else:
            assert not advertised, (
                f"the view WITHHOLDS {view_key!r} for this gated tool, but its "
                f"registration still advertises entry.{attr} = {advertised!r} "
                "on the default transport"
            )


# The OTHER axis of the enumeration: fields FastMCP's ``list_tools`` advertises
# that ``_public_tool_view`` does NOT decide. They are safe to leave unprojected
# only because ``self._mcp.tool()`` is called with no arguments, so FastMCP
# derives nothing for them on ANY tool. Attribute name -> advertised field.
INERT_ON_THE_REGISTRATION = {
    "title": "title",
    "annotations": "annotations",
    "icons": "icons",
    "meta": "_meta",
}


@pytest.mark.parametrize("attr", sorted(INERT_ON_THE_REGISTRATION))
def test_unprojected_advertised_fields_are_derived_for_no_tool(attr):
    """The premise the "nothing to suppress" dispositions rest on.

    ``description`` / ``parameters`` / ``output_schema`` are projected. Every
    OTHER field FastMCP puts on the wire is left alone — sound only while
    FastMCP derives none of them. If a future version starts populating one,
    a gated tool would advertise it with the projection never having decided
    anything about it, which is R3-MED-2's exact shape one field over. This
    pin fails at that moment rather than at the next disclosure review.
    """
    server = _auth_server("r3-inert-premise")
    annotation = ToolAnnotation(is_read_only=True)

    @server.tool(required_permission="admin.write", annotations=annotation)
    def gated(scope: str) -> dict[str, int]:
        """Gated."""
        return {}

    @server.tool(annotations=annotation)
    def ungated(scope: str) -> dict[str, int]:
        """Ungated."""
        return {}

    container = server._fastmcp_tool_container()
    for name in ("gated", "ungated"):
        entry = container[name]
        assert hasattr(entry, attr), (
            f"the registration no longer carries {attr!r}; the advertised-field "
            "enumeration is stale and must be re-derived from FastMCP's "
            "list_tools"
        )
        assert getattr(entry, attr) is None, (
            f"FastMCP now derives {attr!r} onto its own registration "
            f"(advertised as {INERT_ON_THE_REGISTRATION[attr]!r}), so the "
            "projection must decide what a GATED tool discloses through it "
            "rather than relying on there being nothing to suppress"
        )

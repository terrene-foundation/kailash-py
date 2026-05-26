# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LegacyInvokeConnector adapter — wraps a bare async callable as Connector.

Per the issue #1035 plan §"Preserve backwards-compat via legacy adapter":
existing legacy connectors that ship as bare ``async def invoke(...)``
callables (not as Connector subclasses) wrap into the new Connector ABC
via :class:`LegacyInvokeConnector`. This test verifies the adapter:

1. Accepts an async callable and per-instance metadata overrides.
2. Refuses non-callable wrapping (typed TypeError).
3. Satisfies the Connector ABC (zero remaining abstracts).
4. Routes invoke() through the wrapped callable verbatim.
5. The 6 new primitive surfaces work via the same auto-installed proxies
   as direct Connector subclasses.
"""

from __future__ import annotations

import uuid

import pytest

from kailash.delegate.audit import DelegateEventType
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    LegacyInvokeConnector,
)
from kailash.delegate.types import DelegateIdentity


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-legacy-adapter",
        role_binding_ref="rb-legacy-adapter",
        genesis_ref="g-legacy-adapter",
        principal_kind="delegate",
    )


# ---------------------------------------------------------------------------
# 1. Construction + ABC satisfaction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_invoke_connector_constructs_with_async_callable() -> None:
    """LegacyInvokeConnector accepts an async callable and constructs cleanly."""

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={"received": dict(input_payload)},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    assert isinstance(adapter, Connector)
    assert adapter.connector_id == "legacy-invoke-adapter"
    assert adapter.connector_kind == "legacy"


@pytest.mark.unit
def test_legacy_invoke_connector_refuses_non_callable() -> None:
    """Non-callable wrapping MUST raise typed TypeError."""
    with pytest.raises(TypeError, match="callable"):
        LegacyInvokeConnector("not-a-callable")  # type: ignore[arg-type]


@pytest.mark.unit
def test_legacy_invoke_connector_satisfies_abc_contract() -> None:
    """LegacyInvokeConnector class has zero remaining abstracts."""
    assert LegacyInvokeConnector.__abstractmethods__ == frozenset()


# ---------------------------------------------------------------------------
# 2. Per-instance metadata overrides
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_invoke_connector_per_instance_metadata_override() -> None:
    """connector_id / connector_kind / requires_capabilities override per-instance."""

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(
        _invoke,
        connector_id="custom-id-42",
        connector_kind="custom-kind",
        requires_capabilities=frozenset({"custom.cap"}),
    )
    assert adapter.connector_id == "custom-id-42"
    assert adapter.connector_kind == "custom-kind"
    assert adapter.requires_capabilities == frozenset({"custom.cap"})


@pytest.mark.unit
def test_legacy_invoke_connector_refuses_empty_connector_id_override() -> None:
    """Empty-string connector_id override MUST raise."""

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    with pytest.raises(TypeError, match="connector_id"):
        LegacyInvokeConnector(_invoke, connector_id="")


@pytest.mark.unit
def test_legacy_invoke_connector_refuses_non_frozenset_capabilities() -> None:
    """Non-frozenset requires_capabilities override MUST raise."""

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    with pytest.raises(TypeError, match="frozenset"):
        LegacyInvokeConnector(
            _invoke, requires_capabilities={"x"}  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 3. invoke() routes through the wrapped callable verbatim
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_routes_invoke_through_callable() -> None:
    """invoke() forwards (input_payload, identity, envelope) to the wrapped callable."""
    invocations: list[dict] = []

    async def _record(input_payload, *, identity, envelope):
        invocations.append(
            {
                "input_payload": dict(input_payload),
                "identity_id": str(identity.delegate_id),
                "envelope_kind": type(envelope).__name__,
            }
        )
        return ConnectorInvocationResult(
            payload={"echo": True},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed="tenant-from-adapter",
            external_side_effect=True,
        )

    adapter = LegacyInvokeConnector(_record)
    identity = _build_identity()
    # envelope arg is opaque at this layer — pass a sentinel
    envelope_sentinel = object()
    result = await adapter.invoke(
        {"a": 1, "b": "two"},
        identity=identity,
        envelope=envelope_sentinel,  # type: ignore[arg-type]
    )
    assert isinstance(result, ConnectorInvocationResult)
    assert result.payload == {"echo": True}
    assert len(invocations) == 1
    assert invocations[0]["input_payload"] == {"a": 1, "b": "two"}
    assert invocations[0]["identity_id"] == str(identity.delegate_id)


# ---------------------------------------------------------------------------
# 4. The 6 newer surfaces (3 accessors + 3 primitives) refuse on legacy
#    invoke()-only connectors via the typed _legacy_unsupported guard.
#    Closes GH #1177 (empty-crypto orphan defaults on authenticate/write/
#    read) + GH #1178 (Principal(tenant_id=None) multi-tenant footgun
#    on authenticate). The prior default-behavior tests are rewritten to
#    assert the typed refusal; the new acceptance tests below repro the
#    issue bodies verbatim.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_authenticate_default_raises_unsupported() -> (
    None
):
    """Default authenticate() on a legacy invoke()-only connector refuses with typed error.

    Closes GH #1178 — the prior default returned
    ``Principal(tenant_id=None)`` which silently slipped through
    tenant-scoped authorization checks. The typed refusal is the
    defense-in-depth fix; legacy connectors MUST authenticate
    implicitly via ``invoke()``.
    """

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    identity = _build_identity()
    with pytest.raises(NotImplementedError, match="authenticate"):
        await adapter.authenticate(identity, None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_write_default_raises_unsupported() -> None:
    """Default write() on a legacy invoke()-only connector refuses with typed error.

    Closes GH #1177 (write half) — the prior default executed the
    action and returned a ``SignedActionEnvelope`` with an EMPTY
    signature that any verifier not explicitly length-checking would
    treat as authenticated. The typed refusal is the defense-in-depth
    fix; legacy connectors MUST dispatch through ``invoke()``.
    """

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    identity = _build_identity()

    async def _action() -> dict:
        return {"written": True, "value": 42}

    with pytest.raises(NotImplementedError, match="write"):
        await adapter.write(
            _action, identity=identity, envelope=None  # type: ignore[arg-type]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_read_default_raises_unsupported() -> None:
    """Default read() on a legacy invoke()-only connector refuses with typed error.

    Closes GH #1177 (read half) — the prior default executed the
    query and returned an ``AttestedReadReceipt`` with an EMPTY
    attestation. The typed refusal is the defense-in-depth fix.
    """

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    identity = _build_identity()

    async def _query() -> str:
        return "read-value"

    with pytest.raises(NotImplementedError, match="read"):
        await adapter.read(
            _query, identity=identity, envelope=None  # type: ignore[arg-type]
        )


@pytest.mark.unit
def test_legacy_invoke_connector_accessor_raises_unsupported() -> None:
    """Auto-installed accessor proxies raise NotImplementedError on access."""

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    with pytest.raises(NotImplementedError, match="revocation"):
        _ = adapter.revocation
    with pytest.raises(NotImplementedError, match="ledger"):
        _ = adapter.ledger
    with pytest.raises(NotImplementedError, match="auth_verifier"):
        _ = adapter.auth_verifier


# ---------------------------------------------------------------------------
# 5. Acceptance tests for GH #1177 + #1178 — verbatim repros from the
#    issue bodies. A direct LegacyInvokeConnector subclass with its own
#    invoke() must STILL refuse the 3 primitive surfaces (the bug was
#    that the inline defaults handled them with empty-crypto / null
#    tenant); a Connector subclass that OVERRIDES write/read/authenticate
#    must continue to dispatch the override (the contract works for
#    new-shape connectors).
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_1177_legacy_only_write_raises_unsupported() -> None:
    """GH #1177 acceptance — legacy subclass with own invoke() refuses .write()."""

    class LegacyOnly(LegacyInvokeConnector):
        connector_id = "legacy"
        connector_kind = "test"
        requires_capabilities: frozenset[str] = frozenset()

        async def invoke(self, input_payload, *, identity, envelope):
            return ConnectorInvocationResult(
                payload={"ok": True},
                audit_events=(),
                tenant_id_observed=None,
                external_side_effect=False,
            )

    # Direct construction (no wrapped callable) — exercise the subclass shape.
    c = LegacyOnly.__new__(LegacyOnly)
    identity = _build_identity()

    async def _action() -> dict:
        return {}

    with pytest.raises(NotImplementedError, match="write"):
        await c.write(_action, identity=identity, envelope=None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_1177_legacy_only_read_raises_unsupported() -> None:
    """GH #1177 acceptance — legacy subclass with own invoke() refuses .read()."""

    class LegacyOnly(LegacyInvokeConnector):
        connector_id = "legacy"
        connector_kind = "test"
        requires_capabilities: frozenset[str] = frozenset()

        async def invoke(self, input_payload, *, identity, envelope):
            return ConnectorInvocationResult(
                payload={"ok": True},
                audit_events=(),
                tenant_id_observed=None,
                external_side_effect=False,
            )

    c = LegacyOnly.__new__(LegacyOnly)
    identity = _build_identity()

    async def _query() -> str:
        return "v"

    with pytest.raises(NotImplementedError, match="read"):
        await c.read(_query, identity=identity, envelope=None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_1178_legacy_only_authenticate_raises_unsupported() -> None:
    """GH #1178 acceptance — legacy subclass with own invoke() refuses .authenticate().

    The prior default returned ``Principal(tenant_id=None)``; the
    refusal closes the multi-tenant footgun the issue called out.
    """

    class LegacyOnly(LegacyInvokeConnector):
        connector_id = "legacy"
        connector_kind = "test"
        requires_capabilities: frozenset[str] = frozenset()

        async def invoke(self, input_payload, *, identity, envelope):
            return ConnectorInvocationResult(
                payload={"ok": True},
                audit_events=(),
                tenant_id_observed=None,
                external_side_effect=False,
            )

    c = LegacyOnly.__new__(LegacyOnly)
    identity = _build_identity()
    with pytest.raises(NotImplementedError, match="authenticate"):
        await c.authenticate(identity, None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_new_shape_subclass_override_returns_real_value() -> None:
    """New-shape sanity — a Connector that OVERRIDES write returns the override.

    The typed-refusal default is only the LEGACY behavior; new-shape
    connectors that implement their own .write() continue to dispatch
    the override (the contract still works for them).
    """
    from kailash.delegate.dispatch import Connector, SignedActionEnvelope

    class NewShape(Connector):
        connector_id = "new-shape"
        connector_kind = "test"
        requires_capabilities: frozenset[str] = frozenset()

        async def invoke(self, input_payload, *, identity, envelope):
            return ConnectorInvocationResult(
                payload={},
                audit_events=(),
                tenant_id_observed=None,
                external_side_effect=False,
            )

        async def write(self, action, *, identity, envelope):
            payload = await action()
            return SignedActionEnvelope(
                action_id=uuid.uuid4(),
                canonical_bytes=b"canon",
                signature=b"real-sig-bytes",
                signer_delegate_id=str(identity.delegate_id),
                payload=payload if isinstance(payload, dict) else {"value": payload},
            )

    conn = NewShape()
    identity = _build_identity()

    async def _action() -> dict:
        return {"written": True}

    env = await conn.write(_action, identity=identity, envelope=None)  # type: ignore[arg-type]
    assert isinstance(env, SignedActionEnvelope)
    assert env.signature == b"real-sig-bytes"
    assert env.payload == {"written": True}

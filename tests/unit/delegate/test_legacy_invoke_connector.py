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
# 4. New-shape primitive surfaces work via auto-installed proxies
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_authenticate_proxy_returns_principal() -> None:
    """Auto-installed authenticate() proxy returns a Principal scoped to the identity."""
    from kailash.delegate.dispatch import Principal

    async def _invoke(input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )

    adapter = LegacyInvokeConnector(_invoke)
    identity = _build_identity()
    p = await adapter.authenticate(identity, None)  # type: ignore[arg-type]
    assert isinstance(p, Principal)
    assert p.delegate_id == str(identity.delegate_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_invoke_connector_write_proxy_synthesizes_envelope() -> None:
    """Auto-installed write() proxy executes the action and synthesizes an envelope."""
    from kailash.delegate.dispatch import SignedActionEnvelope

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

    env = await adapter.write(
        _action, identity=identity, envelope=None  # type: ignore[arg-type]
    )
    assert isinstance(env, SignedActionEnvelope)
    assert env.payload == {"written": True, "value": 42}
    # Legacy proxy produces empty signature — callers MUST treat as unverifiable
    assert env.signature == b""
    assert env.signer_delegate_id == str(identity.delegate_id)


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

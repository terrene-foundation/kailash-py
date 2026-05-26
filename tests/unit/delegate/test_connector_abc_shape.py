# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Connector ABC shape — verify the rs-mirrored member surface (F-17).

Per ``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-
extraction.md:332-385`` (Round-1 F-17), the Python :class:`Connector` ABC
MUST mirror the kailash-rs Connector trait shape: 3 inherent-method
accessors (revocation/ledger/auth_verifier) + 3 required primitives
(authenticate/write/read). The legacy ``invoke()`` method is preserved
for backwards-compat.

**Concrete-defaults design (option c).** ``invoke()`` is the sole
``@abstractmethod``; the 6 newer members (3 accessors + 3 primitives)
ship as concrete defaults on the base class (accessors raise a typed
legacy guard; the primitives provide the legacy-adapter behavior).
A subclass implementing only ``invoke()`` is therefore fully concrete
by inheritance — there is no ``__init_subclass__`` runtime proxy
installation and no ``__abstractmethods__`` mutation, so static type
checkers model legacy invoke()-only subclasses as concrete (no spurious
``reportAbstractUsage``).

This file verifies the structural ABC contract:

1. Connector is abc.ABC; direct instantiation refused.
2. Connector.__abstractmethods__ == {"invoke"} — the sole abstract member.
3. The 6 newer members are concrete defaults (NOT abstract).
4. A subclass implementing only invoke() instantiates successfully by
   inheriting the concrete defaults.
5. A subclass implementing only invoke() exposes the 6 new primitive
   surfaces (accessors raise the typed guard; primitives run the default).
6. A subclass implementing all 6 new primitives directly also constructs.
"""

from __future__ import annotations

import inspect

import pytest

from kailash.delegate.audit import DelegateEventType
from kailash.delegate.dispatch import (
    AttestedReadReceipt,
    Connector,
    ConnectorInvocationResult,
    Principal,
    SignedActionEnvelope,
)

# ---------------------------------------------------------------------------
# 1. Direct instantiation refused
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connector_abc_refuses_direct_instantiation() -> None:
    """Connector is abc.ABC with @abstractmethod — direct construction refused."""
    with pytest.raises(TypeError, match="abstract"):
        Connector()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# 2. __abstractmethods__ == {"invoke"} — invoke is the SOLE abstract member
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connector_abc_has_expected_abstract_members() -> None:
    """Connector.__abstractmethods__ MUST be exactly {"invoke"} (option c).

    ``invoke()`` is the sole abstract member; the 6 newer rs-mirrored
    members (3 accessors + 3 primitives) ship as concrete defaults on the
    base class. Per F-17 the rs trait shape is still mirrored as the member
    surface (see ``test_connector_abc_six_new_members_are_concrete``); only
    the abstractness lives on ``invoke`` so legacy invoke()-only subclasses
    are concrete by inheritance.
    """
    assert Connector.__abstractmethods__ == frozenset({"invoke"}), (
        f"Connector ABC drift: expected {{'invoke'}}, "
        f"got {sorted(Connector.__abstractmethods__)}"
    )


@pytest.mark.unit
def test_connector_abc_six_new_members_are_concrete() -> None:
    """The 6 rs-mirrored members exist as CONCRETE defaults, distinct from invoke.

    Option (c): the 3 accessors (revocation/ledger/auth_verifier) + 3
    primitives (authenticate/write/read) are present on the base class but
    are NOT abstract — a legacy invoke()-only subclass inherits them and is
    fully concrete. ``invoke`` remains the sole abstract member.
    """
    new_members = {
        "revocation",
        "ledger",
        "auth_verifier",
        "authenticate",
        "write",
        "read",
    }
    assert len(new_members) == 6
    assert "invoke" not in new_members
    # Present on the base class …
    assert new_members <= set(dir(Connector))
    # … but NONE of them is abstract (only invoke is).
    assert new_members.isdisjoint(Connector.__abstractmethods__)
    for name in new_members:
        member = inspect.getattr_static(Connector, name)
        # Resolve property fget so the abstractness check sees the callable.
        target = member.fget if isinstance(member, property) else member
        assert not getattr(
            target, "__isabstractmethod__", False
        ), f"{name} MUST be a concrete default, not abstract"


# ---------------------------------------------------------------------------
# 3. Legacy invoke()-only subclass instantiates via auto-installed proxies
# ---------------------------------------------------------------------------


class _LegacyInvokeOnlyConnector(Connector):
    """Legacy connector overriding ONLY invoke() — exercises auto-adapter."""

    connector_id = "legacy-invoke-only"
    connector_kind = "test"
    requires_capabilities = frozenset({"test.invoke"})

    async def invoke(self, input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={"echoed": dict(input_payload)},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed="tenant-legacy",
            external_side_effect=True,
        )


@pytest.mark.unit
def test_legacy_invoke_only_subclass_is_instantiable() -> None:
    """A Connector subclass overriding only invoke() MUST instantiate cleanly.

    Per __init_subclass__ adapter behavior: the 6 new abstracts get
    auto-installed proxies, satisfying the abstract-method contract.
    Without the adapter the subclass would carry 6 unresolved abstracts
    and ABCMeta would refuse instantiation.
    """
    conn = _LegacyInvokeOnlyConnector()
    assert conn.connector_id == "legacy-invoke-only"


@pytest.mark.unit
def test_legacy_invoke_only_subclass_has_no_remaining_abstracts() -> None:
    """Legacy invoke()-only subclass MUST have empty __abstractmethods__."""
    assert _LegacyInvokeOnlyConnector.__abstractmethods__ == frozenset()


# ---------------------------------------------------------------------------
# 4. Legacy subclass exposes the 6 new primitive surfaces (auto-installed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_subclass_exposes_six_new_members_as_attributes() -> None:
    """Auto-installed proxies expose all 6 new members on the subclass."""
    conn = _LegacyInvokeOnlyConnector()
    # The 3 accessors are descriptor-protocol sentinels that raise on
    # access — they exist but reach() unsupported. Verify the attribute
    # bindings EXIST.
    assert hasattr(type(conn), "revocation")
    assert hasattr(type(conn), "ledger")
    assert hasattr(type(conn), "auth_verifier")
    # The 3 primitives are real async methods.
    assert inspect.iscoroutinefunction(conn.authenticate)
    assert inspect.iscoroutinefunction(conn.write)
    assert inspect.iscoroutinefunction(conn.read)


@pytest.mark.unit
def test_legacy_subclass_accessor_access_raises_unsupported() -> None:
    """Auto-installed accessor proxies raise NotImplementedError on access.

    Legacy ``invoke()``-only connectors do not expose RevocationChannel /
    KnowledgeLedger / AuthVerifier surfaces — accessing them surfaces a
    typed refusal (per zero-tolerance.md Rule 3a typed-delegate guards)
    rather than a silent AttributeError.
    """
    conn = _LegacyInvokeOnlyConnector()
    with pytest.raises(NotImplementedError, match="revocation"):
        _ = conn.revocation
    with pytest.raises(NotImplementedError, match="ledger"):
        _ = conn.ledger
    with pytest.raises(NotImplementedError, match="auth_verifier"):
        _ = conn.auth_verifier


# ---------------------------------------------------------------------------
# 5. New-shape subclass: all 6 primitives + invoke implemented directly
# ---------------------------------------------------------------------------


class _AuthVerifierStub:
    def verify_token(self, token: str) -> bool:
        return True


class _RevocationChannelStub:
    def is_revoked(self, delegate_id: str) -> bool:
        return False


class _KnowledgeLedgerStub:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def record(self, event_type: str, payload: dict) -> None:
        self.records.append((event_type, payload))


class _NewShapeConnector(Connector):
    """Full 4-primitive new-shape Connector — exercises the rs-mirrored ABC."""

    connector_id = "new-shape-conn"
    connector_kind = "test"
    requires_capabilities = frozenset({"test.new_shape"})

    def __init__(self) -> None:
        self._revocation = _RevocationChannelStub()
        self._ledger = _KnowledgeLedgerStub()
        self._auth_verifier = _AuthVerifierStub()

    @property
    def revocation(self):
        return self._revocation

    @property
    def ledger(self):
        return self._ledger

    @property
    def auth_verifier(self):
        return self._auth_verifier

    async def authenticate(self, identity, envelope):
        return Principal(
            delegate_id=str(identity.delegate_id),
            tenant_id="tenant-new-shape",
            claims={"shape": "new"},
        )

    async def write(self, action, *, identity, envelope):
        from datetime import datetime, timezone

        payload = await action()
        return SignedActionEnvelope(
            action_id=__import__("uuid").uuid4(),
            canonical_bytes=str(payload).encode("utf-8"),
            signature=b"new-shape-sig",
            signer_delegate_id=str(identity.delegate_id),
            payload=payload if isinstance(payload, dict) else {"value": payload},
        )

    async def read(self, query, *, identity, envelope):
        from datetime import datetime, timezone

        value = await query()
        receipt = AttestedReadReceipt(
            read_id=__import__("uuid").uuid4(),
            canonical_bytes=str(value).encode("utf-8"),
            attestation=b"new-shape-attest",
            attester_delegate_id=str(identity.delegate_id),
            observed_at=datetime.now(timezone.utc),
        )
        return value, receipt

    async def invoke(self, input_payload, *, identity, envelope):
        # New-shape subclass still overrides invoke() (legacy entry point)
        # since the dispatch hot path calls invoke() — the 4-primitive
        # methods are for new-shape callers.
        return ConnectorInvocationResult(
            payload={"new_shape": True},
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )


@pytest.mark.unit
def test_new_shape_subclass_is_instantiable() -> None:
    """New-shape Connector with all 6 primitives MUST instantiate cleanly."""
    conn = _NewShapeConnector()
    assert conn.connector_id == "new-shape-conn"


@pytest.mark.unit
def test_new_shape_subclass_accessors_return_real_objects() -> None:
    """New-shape connector's accessors return real RevocationChannel/Ledger/Auth."""
    conn = _NewShapeConnector()
    assert isinstance(conn.revocation, _RevocationChannelStub)
    assert isinstance(conn.ledger, _KnowledgeLedgerStub)
    assert isinstance(conn.auth_verifier, _AuthVerifierStub)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_new_shape_authenticate_returns_principal() -> None:
    """authenticate() returns a real Principal scoped to the bound identity."""
    import uuid

    from kailash.delegate.types import DelegateIdentity

    conn = _NewShapeConnector()
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-shape-test",
        role_binding_ref="rb-shape-test",
        genesis_ref="g-shape-test",
        principal_kind="delegate",
    )
    # envelope arg is structurally checked at the DispatchSurface boundary,
    # not by the connector primitive — pass None for the unit-level shape
    # test (the new-shape connector's authenticate doesn't inspect the
    # envelope's fields).
    p = await conn.authenticate(identity, None)  # type: ignore[arg-type]
    assert isinstance(p, Principal)
    assert p.delegate_id == str(identity.delegate_id)
    assert p.tenant_id == "tenant-new-shape"


# ---------------------------------------------------------------------------
# 6. Subclass missing invoke() is abstract — instantiation refused
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_subclass_missing_invoke_is_abstract() -> None:
    """Subclass not overriding invoke() MUST be abstract — instantiation refused.

    Option (c): invoke is the sole abstract member, so a subclass that does
    not implement it inherits exactly one unsatisfied abstract ({"invoke"})
    and cannot be instantiated. The 6 newer members are concrete defaults
    and never block instantiation.
    """

    class _Empty(Connector):
        connector_id = "empty"
        connector_kind = "test"

    # invoke is the sole unsatisfied abstract.
    assert _Empty.__abstractmethods__ == frozenset({"invoke"})
    with pytest.raises(TypeError, match="abstract"):
        _Empty()  # type: ignore[abstract]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration tests for ``TenantScopedEventBus`` (issue #1338).

Real in-memory backend, real publish/subscribe round-trips — NO mocking
(per the 3-tier testing rule). Cross-SDK parity with
esperie-enterprise/kailash-rs #1352 (Rust ``kailash.events`` tenant scoping).

Acceptance criteria (#1338):
* A helper-backed tenant-prefixed-topic subscribe/publish pattern for the
  in-memory bus.
* A multi-tenant isolation guarantee using the SDK bus directly: a publish
  on one tenant fans out ONLY within that tenant.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

import kailash
from kailash import DomainEvent, EventBus, Subscription, TenantScopedEventBus
from kailash.events import TenantScopedEventBus as TFromEvents

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_tenant_bus_is_public_surface():
    """from kailash import TenantScopedEventBus works AND it is in __all__."""
    assert hasattr(kailash, "TenantScopedEventBus")
    assert "TenantScopedEventBus" in kailash.__all__
    assert "TenantScopedEventBus" in dir(kailash)
    # Same object from both the top-level namespace and the events package.
    assert kailash.TenantScopedEventBus is TFromEvents
    assert "TenantScopedEventBus" in kailash.events.__all__


def test_tenant_bus_surface_shape():
    """publish/subscribe/subscribe_events mirror EventBus shape."""
    pub = inspect.signature(TenantScopedEventBus.publish)
    assert "event_type" in pub.parameters
    assert "payload" in pub.parameters
    assert pub.parameters["correlation_id"].kind == inspect.Parameter.KEYWORD_ONLY
    assert inspect.iscoroutinefunction(TenantScopedEventBus.publish)

    sub = inspect.signature(TenantScopedEventBus.subscribe)
    assert "event_type" in sub.parameters and "handler" in sub.parameters
    assert not inspect.iscoroutinefunction(TenantScopedEventBus.subscribe)
    assert inspect.iscoroutinefunction(TenantScopedEventBus.close)


# ---------------------------------------------------------------------------
# Core acceptance: multi-tenant isolation on ONE shared bus
# ---------------------------------------------------------------------------


async def test_isolation_publish_fans_out_within_tenant_only():
    """A publish on one tenant reaches ONLY that tenant's subscribers."""
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)
    globex = TenantScopedEventBus("globex", bus)

    acme_seen: list[dict] = []
    globex_seen: list[dict] = []

    async def on_acme(payload):
        acme_seen.append(payload)

    async def on_globex(payload):
        globex_seen.append(payload)

    sa = acme.subscribe("order.created", on_acme)
    sg = globex.subscribe("order.created", on_globex)

    await globex.publish("order.created", {"id": "g1"})
    await acme.publish("order.created", {"id": "a1"})
    await asyncio.sleep(0.02)

    assert acme_seen == [{"id": "a1"}]  # acme NEVER saw globex's event
    assert globex_seen == [{"id": "g1"}]  # globex NEVER saw acme's event

    await sa.unsubscribe()
    await sg.unsubscribe()
    await bus.close()


async def test_same_logical_type_different_tenants_do_not_cross():
    """Three tenants, same logical event_type — zero cross-talk."""
    bus = EventBus()
    tenants = {t: TenantScopedEventBus(t, bus) for t in ("a", "b", "c")}
    seen: dict[str, list] = {t: [] for t in tenants}

    subs = []
    for name, tb in tenants.items():

        async def _h(payload, _n=name):
            seen[_n].append(payload)

        subs.append(tb.subscribe("evt", _h))

    for name, tb in tenants.items():
        await tb.publish("evt", {"from": name})
    await asyncio.sleep(0.03)

    for name in tenants:
        assert seen[name] == [{"from": name}], (name, seen[name])

    for s in subs:
        await s.unsubscribe()
    await bus.close()


async def test_subscribe_returns_subscription_payload_is_original():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)
    seen: list[dict] = []

    async def handler(payload):
        seen.append(payload)

    sub = acme.subscribe("order.created", handler)
    assert isinstance(sub, Subscription)

    original = {"order_id": "o-1", "items": ["x", "y"], "total": 9.5}
    await acme.publish("order.created", original)
    await asyncio.sleep(0.02)
    assert seen == [original]
    assert seen[0]["items"] == ["x", "y"]

    await sub.unsubscribe()
    # after unsubscribe, no more delivery
    await acme.publish("order.created", {"order_id": "o-2"})
    await asyncio.sleep(0.02)
    assert len(seen) == 1
    await bus.close()


# ---------------------------------------------------------------------------
# subscribe_events: full envelope, LOGICAL (un-prefixed) event_type
# ---------------------------------------------------------------------------


async def test_subscribe_events_delivers_logical_event_type():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)
    seen: list[DomainEvent] = []

    async def handler(event: DomainEvent):
        seen.append(event)

    sub = acme.subscribe_events("payment.done", handler)
    await acme.publish(
        "payment.done", {"amt": 5}, correlation_id="trace-9", actor="svc-a"
    )
    await asyncio.sleep(0.02)

    assert len(seen) == 1
    # The subscriber sees the LOGICAL type, not "acme:payment.done".
    assert seen[0].event_type == "payment.done"
    assert seen[0].payload == {"amt": 5}
    assert seen[0].correlation_id == "trace-9"
    assert seen[0].actor == "svc-a"

    await sub.unsubscribe()
    await bus.close()


async def test_subscribe_events_isolated_across_tenants():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)
    globex = TenantScopedEventBus("globex", bus)
    acme_seen: list[DomainEvent] = []

    async def handler(event: DomainEvent):
        acme_seen.append(event)

    sub = acme.subscribe_events("evt", handler)
    await globex.publish("evt", {"x": 1})  # different tenant
    await asyncio.sleep(0.02)
    assert acme_seen == []  # acme's full-envelope subscriber saw nothing

    await acme.publish("evt", {"x": 2})
    await asyncio.sleep(0.02)
    assert len(acme_seen) == 1 and acme_seen[0].payload == {"x": 2}

    await sub.unsubscribe()
    await bus.close()


# ---------------------------------------------------------------------------
# event_type may itself contain the separator; un-prefix is by length
# ---------------------------------------------------------------------------


async def test_event_type_containing_separator_roundtrips():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)  # separator ":"
    seen: list[DomainEvent] = []

    async def handler(event: DomainEvent):
        seen.append(event)

    # event_type itself contains a colon — must survive un-prefixing intact.
    sub = acme.subscribe_events("ns:order:created", handler)
    await acme.publish("ns:order:created", {"k": "v"})
    await asyncio.sleep(0.02)
    assert len(seen) == 1
    assert seen[0].event_type == "ns:order:created"
    await sub.unsubscribe()
    await bus.close()


async def test_custom_separator_isolates_on_own_bus():
    """A non-default separator still isolates tenants (uniform across the bus)."""
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus, separator="/")
    globex = TenantScopedEventBus("globex", bus, separator="/")
    a_seen: list = []
    g_seen: list = []

    async def ha(p):
        a_seen.append(p)

    async def hg(p):
        g_seen.append(p)

    sa = acme.subscribe("evt", ha)
    sg = globex.subscribe("evt", hg)
    await acme.publish("evt", {"sep": "slash"})
    await globex.publish("evt", {"sep": "slash2"})
    await asyncio.sleep(0.02)
    assert a_seen == [{"sep": "slash"}]
    assert g_seen == [{"sep": "slash2"}]
    await sa.unsubscribe()
    await sg.unsubscribe()
    await bus.close()


# ---------------------------------------------------------------------------
# Validation (isolation-integrity guards)
# ---------------------------------------------------------------------------


def test_empty_tenant_id_rejected():
    with pytest.raises(ValueError, match="tenant_id must be a non-empty string"):
        TenantScopedEventBus("")


def test_tenant_id_containing_separator_rejected():
    # The cross-tenant-collision guard: a separator inside the id would make
    # f"{tenant}{sep}{type}" ambiguous.
    with pytest.raises(ValueError, match="must not contain the separator"):
        TenantScopedEventBus("acme:evil")
    # custom separator
    with pytest.raises(ValueError, match="must not contain the separator"):
        TenantScopedEventBus("a/b", separator="/")


def test_empty_separator_rejected():
    with pytest.raises(ValueError, match="separator must be a non-empty string"):
        TenantScopedEventBus("acme", separator="")


# ---------------------------------------------------------------------------
# Uniform-separator-per-bus guard (R2 — closes mixed-separator collision)
# ---------------------------------------------------------------------------


def test_mixed_separator_on_shared_bus_rejected():
    """A second wrapper with a DIFFERENT separator on the same bus is refused."""
    bus = EventBus()
    TenantScopedEventBus("acme", bus, separator=":")  # stamps ":" on the bus
    with pytest.raises(ValueError, match="already tenant-scoped with separator"):
        TenantScopedEventBus("globex", bus, separator="/")


def test_same_separator_on_shared_bus_allowed():
    """Re-wrapping a bus with the SAME separator is fine (the normal case)."""
    bus = EventBus()
    a = TenantScopedEventBus("acme", bus, separator="::")
    b = TenantScopedEventBus("globex", bus, separator="::")
    assert a.bus is b.bus


async def test_mixed_separator_cross_tenant_collision_blocked():
    """Regression: the ('a','::') vs ('a:',':x') prefix-overlap leak is blocked.

    Before the uniform-separator guard, ('a', sep='::') publishing 'xfoo'
    (topic 'a::xfoo') leaked to ('a:', sep=':x') subscribing 'foo'
    (topic 'a::xfoo'). The guard now refuses the second wrapper.
    """
    bus = EventBus()
    TenantScopedEventBus("a", bus, separator="::")
    with pytest.raises(ValueError, match="already tenant-scoped with separator"):
        TenantScopedEventBus("a:", bus, separator=":x")
    await bus.close()


# ---------------------------------------------------------------------------
# Bus-construction kwargs are rejected with a shared bus (R2 — no silent drop)
# ---------------------------------------------------------------------------


def test_bus_construction_kwargs_rejected_with_shared_bus():
    bus = EventBus()
    for kw in (
        {"backend": "memory"},
        {"redis_url": "redis://x"},
        {"max_subscribers": 5},
    ):
        with pytest.raises(ValueError, match="only valid when constructing a new bus"):
            TenantScopedEventBus("acme", bus, **kw)


def test_bus_construction_kwargs_accepted_when_owning():
    """Same kwargs ARE honored when the wrapper constructs its own bus."""
    solo = TenantScopedEventBus("solo", backend="memory", max_subscribers=7)
    assert solo.owns_bus is True
    assert solo.bus.backend_name == "InMemoryEventBackend"


def test_empty_event_type_rejected_on_publish():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)

    async def _run():
        with pytest.raises(ValueError, match="event_type must be a non-empty string"):
            await acme.publish("", {})

    asyncio.run(_run())


def test_empty_event_type_rejected_on_subscribe():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)

    async def _noop(_):
        pass

    with pytest.raises(ValueError, match="event_type must be a non-empty string"):
        acme.subscribe("", _noop)


# ---------------------------------------------------------------------------
# Ownership / lifecycle
# ---------------------------------------------------------------------------


async def test_owns_bus_when_self_constructed():
    solo = TenantScopedEventBus("solo")  # no bus arg → constructs + owns one
    assert solo.owns_bus is True
    assert isinstance(solo.bus, EventBus)
    assert solo.bus.backend_name == "InMemoryEventBackend"
    await solo.close()  # closes the owned bus


async def test_does_not_own_shared_bus():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus)
    assert acme.owns_bus is False
    assert acme.bus is bus

    # close() on the wrapper MUST NOT close the shared bus — it stays usable.
    await acme.close()
    seen: list = []

    async def h(p):
        seen.append(p)

    other = TenantScopedEventBus("globex", bus)
    sub = other.subscribe("evt", h)
    await other.publish("evt", {"still": "alive"})
    await asyncio.sleep(0.02)
    assert seen == [{"still": "alive"}]  # shared bus survived acme.close()
    await sub.unsubscribe()
    await bus.close()


def test_properties_expose_config():
    bus = EventBus()
    acme = TenantScopedEventBus("acme", bus, separator="::")
    assert acme.tenant_id == "acme"
    assert acme.separator == "::"
    assert acme.bus is bus

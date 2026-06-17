# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Multi-tenant event isolation with the Kailash EventBus.

Run:  python examples/eventbus_tenant_isolation.py

A SaaS app serves many tenants from one process and one event bus. Every
tenant must see ONLY its own events — tenant ``acme``'s ``order.created``
must never reach tenant ``globex``'s handlers. ``TenantScopedEventBus``
gives that isolation for free: it prefixes every topic with the tenant id
(``"acme:order.created"`` vs ``"globex:order.created"``), and because the
bus dispatches by exact event_type the two tenants can never cross.

The same pattern works unchanged over the Redis Streams backend
(``EventBus(backend="redis")``) — there, prefixing is the ONLY way to keep
tenants sharing one broker isolated, because every tenant's events land on
its own Redis stream key.
"""

from __future__ import annotations

import asyncio

from kailash import EventBus, TenantScopedEventBus


async def main() -> None:
    # ONE shared transport for the whole process...
    bus = EventBus()  # in-memory default; swap for EventBus(backend="redis")

    # ...one tenant-scoped facade per tenant.
    acme = TenantScopedEventBus("acme", bus)
    globex = TenantScopedEventBus("globex", bus)

    acme_orders: list[dict] = []
    globex_orders: list[dict] = []

    async def on_acme_order(payload: dict) -> None:
        acme_orders.append(payload)
        print(f"  [acme handler]   received {payload}")

    async def on_globex_order(payload: dict) -> None:
        globex_orders.append(payload)
        print(f"  [globex handler] received {payload}")

    acme_sub = acme.subscribe("order.created", on_acme_order)
    globex_sub = globex.subscribe("order.created", on_globex_order)

    print("Publishing one order per tenant on the SAME bus:")
    await acme.publish("order.created", {"order_id": "A-1", "total": 42.0})
    await globex.publish("order.created", {"order_id": "G-1", "total": 99.0})
    await asyncio.sleep(0.05)  # let in-memory handlers drain

    # Isolation guarantee: each tenant saw ONLY its own event.
    assert acme_orders == [{"order_id": "A-1", "total": 42.0}], acme_orders
    assert globex_orders == [{"order_id": "G-1", "total": 99.0}], globex_orders
    print("\nIsolation holds: acme saw 1 order, globex saw 1 order, zero cross-talk.")

    await acme_sub.unsubscribe()
    await globex_sub.unsubscribe()
    await bus.close()


if __name__ == "__main__":
    asyncio.run(main())

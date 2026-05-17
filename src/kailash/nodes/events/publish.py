# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""``EventPublishNode`` — publish a domain event from a workflow step.

Wires the :class:`kailash.EventBus` primitive into the workflow runtime
so a :class:`~kailash.workflow.builder.WorkflowBuilder` step can emit
domain events with ``correlation_id`` trace continuity.

Two ways to supply the bus:

1. Pass a live :class:`~kailash.events.EventBus` instance via the
   ``event_bus`` config key (recommended — one bus shared across the
   process / app).
2. Supply only string params (``backend`` / ``redis_url``); the node
   constructs an :class:`~kailash.events.EventBus` per execution.  Use
   the in-memory backend only when subscribers live in the same process
   and bus instance; otherwise pass a shared instance or use ``redis``.

Example::

    from kailash.workflow.builder import WorkflowBuilder
    from kailash.events import EventBus

    bus = EventBus()
    wf = WorkflowBuilder()
    wf.add_node(
        "EventPublishNode", "emit",
        {
            "event_bus": bus,
            "event_type": "order.created",
            "payload": {"order_id": "o-1"},
            "correlation_id": "trace-42",
        },
    )
"""

from __future__ import annotations

from typing import Any, Optional

from kailash.events import EventBus
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode

__all__ = ["EventPublishNode"]


@register_node()
class EventPublishNode(AsyncNode):
    """Publish a domain event to a :class:`kailash.EventBus`.

    Inputs (via config at ``add_node`` or runtime overrides):

    * ``event_type`` (str, required) — dot-delimited event type.
    * ``payload`` (dict, required) — JSON-serializable event data.
    * ``correlation_id`` (str, optional) — trace id; auto-generated when
      omitted.  Propagates to every subscriber via the event envelope.
    * ``actor`` (str, optional) — id of the entity causing the event.
    * ``event_bus`` (EventBus, optional) — a live bus instance. When
      absent the node builds one from ``backend`` / ``redis_url``.
    * ``backend`` (str, optional) — ``"memory"`` (default) | ``"redis"``.
    * ``redis_url`` (str, optional) — Redis URL for the redis backend.

    Outputs:

    * ``published`` (bool) — ``True`` on successful publish.
    * ``event_type`` (str) — echoed event type.
    * ``correlation_id`` (str) — the (possibly auto-generated) trace id.
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "event_type": NodeParameter(
                name="event_type",
                type=str,
                required=True,
                description="Dot-delimited event type (e.g. 'order.created').",
            ),
            "payload": NodeParameter(
                name="payload",
                type=dict,
                required=True,
                description="JSON-serializable event payload.",
            ),
            "correlation_id": NodeParameter(
                name="correlation_id",
                type=str,
                required=False,
                description="Trace id linking related events; "
                "auto-generated when omitted.",
            ),
            "actor": NodeParameter(
                name="actor",
                type=str,
                required=False,
                description="Optional id of the entity causing the event.",
            ),
            "event_bus": NodeParameter(
                name="event_bus",
                type=object,
                required=False,
                description="A live kailash.events.EventBus instance. "
                "When absent, built from 'backend'/'redis_url'.",
            ),
            "backend": NodeParameter(
                name="backend",
                type=str,
                required=False,
                default="memory",
                description="Backend name when no event_bus is supplied: "
                "'memory' or 'redis'.",
            ),
            "redis_url": NodeParameter(
                name="redis_url",
                type=str,
                required=False,
                description="Redis URL when backend='redis'.",
            ),
            "published": NodeParameter(
                name="published",
                type=bool,
                required=False,
                description="True on successful publish.",
                output=True,
            ),
            "event_type_out": NodeParameter(
                name="event_type_out",
                type=str,
                required=False,
                description="Echoed event type.",
                output=True,
            ),
            "correlation_id_out": NodeParameter(
                name="correlation_id_out",
                type=str,
                required=False,
                description="The (possibly auto-generated) trace id.",
                output=True,
            ),
        }

    async def async_run(self, **inputs: Any) -> dict[str, Any]:
        event_type = inputs.get("event_type", self.config.get("event_type"))
        payload = inputs.get("payload", self.config.get("payload"))
        correlation_id: Optional[str] = inputs.get(
            "correlation_id", self.config.get("correlation_id")
        )
        actor: Optional[str] = inputs.get("actor", self.config.get("actor"))

        if not event_type:
            raise ValueError("EventPublishNode requires 'event_type'")
        if not isinstance(payload, dict):
            raise ValueError(
                "EventPublishNode requires 'payload' to be a dict, "
                f"got {type(payload).__name__}"
            )

        bus = inputs.get("event_bus", self.config.get("event_bus"))
        owns_bus = False
        if bus is None:
            backend = inputs.get("backend", self.config.get("backend", "memory"))
            redis_url = inputs.get("redis_url", self.config.get("redis_url"))
            bus = EventBus(backend=backend, redis_url=redis_url)
            owns_bus = True
        elif not isinstance(bus, EventBus):
            raise ValueError(
                "'event_bus' must be a kailash.events.EventBus instance, "
                f"got {type(bus).__name__}"
            )

        # Generate the correlation_id up-front so it can be both published
        # and returned for downstream trace continuity.
        if correlation_id is None:
            import uuid

            correlation_id = str(uuid.uuid4())

        self.logger.info(
            "event_publish.start event_type=%s correlation_id=%s",
            event_type,
            correlation_id,
        )
        try:
            await bus.publish(
                event_type,
                payload,
                correlation_id=correlation_id,
                actor=actor,
            )
        finally:
            if owns_bus:
                await bus.close()

        self.logger.info(
            "event_publish.ok event_type=%s correlation_id=%s",
            event_type,
            correlation_id,
        )
        return {
            "published": True,
            "event_type_out": event_type,
            "correlation_id_out": correlation_id,
        }

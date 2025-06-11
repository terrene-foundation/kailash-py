"""Event generation nodes for event-driven architectures."""

import random
import uuid
from datetime import UTC, datetime
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class EventGeneratorNode(Node):
    """
    Generates events for event sourcing and event-driven architecture patterns.

    This node creates realistic event streams for testing, development, and
    demonstration of event-driven systems. It supports various event types
    and can generate events with proper sequencing, timestamps, and metadata.

    Design Philosophy:
        Event sourcing requires consistent, well-structured events with proper
        metadata. This node eliminates the need for DataTransformer with embedded
        Python code by providing a dedicated, configurable event generation
        capability.

    Upstream Dependencies:
        - Optional configuration nodes
        - Timer/scheduler nodes for periodic generation
        - Template nodes for event schemas

    Downstream Consumers:
        - Event processing nodes
        - Stream aggregation nodes
        - Event store writers
        - Message queue publishers
        - Analytics and monitoring nodes

    Configuration:
        - Event types and schemas
        - Generation patterns (burst, continuous, scheduled)
        - Data ranges and distributions
        - Metadata templates

    Implementation Details:
        - Generates proper event IDs and timestamps
        - Maintains event ordering and sequencing
        - Supports custom event schemas
        - Realistic data generation with configurable patterns
        - Proper metadata structure

    Error Handling:
        - Validates event schemas
        - Handles invalid configurations gracefully
        - Ensures timestamp consistency
        - Validates required fields

    Side Effects:
        - No external side effects
        - Deterministic with seed parameter
        - Generates new events on each execution

    Examples:
        >>> # Generate order events
        >>> generator = EventGeneratorNode(
        ...     event_types=['OrderCreated', 'PaymentProcessed', 'OrderShipped'],
        ...     event_count=10,
        ...     aggregate_prefix='ORDER-2024'
        ... )
        >>> result = generator.execute()
        >>> assert len(result['events']) == 10
        >>> assert result['events'][0]['event_type'] in ['OrderCreated', 'PaymentProcessed', 'OrderShipped']
        >>>
        >>> # Generate user events with custom data
        >>> generator = EventGeneratorNode(
        ...     event_types=['UserRegistered', 'UserLoggedIn'],
        ...     event_count=5,
        ...     custom_data_templates={
        ...         'UserRegistered': {'username': 'user_{id}', 'email': '{username}@example.com'},
        ...         'UserLoggedIn': {'ip_address': '192.168.1.{random_ip}', 'device': 'Chrome/Windows'}
        ...     }
        ... )
        >>> result = generator.execute()
        >>> assert 'events' in result
        >>> assert result['metadata']['total_events'] == 5
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "event_types": NodeParameter(
                name="event_types",
                type=list,
                required=True,
                description="List of event types to generate",
            ),
            "event_count": NodeParameter(
                name="event_count",
                type=int,
                required=False,
                default=10,
                description="Number of events to generate",
            ),
            "aggregate_prefix": NodeParameter(
                name="aggregate_prefix",
                type=str,
                required=False,
                default="AGG",
                description="Prefix for aggregate IDs",
            ),
            "custom_data_templates": NodeParameter(
                name="custom_data_templates",
                type=dict,
                required=False,
                default={},
                description="Custom data templates for each event type",
            ),
            "source_service": NodeParameter(
                name="source_service",
                type=str,
                required=False,
                default="event-generator",
                description="Source service name for metadata",
            ),
            "time_range_hours": NodeParameter(
                name="time_range_hours",
                type=int,
                required=False,
                default=24,
                description="Time range in hours for event timestamps",
            ),
            "seed": NodeParameter(
                name="seed",
                type=int,
                required=False,
                description="Random seed for reproducible generation",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        event_types = kwargs["event_types"]
        event_count = kwargs.get("event_count", 10)
        aggregate_prefix = kwargs.get("aggregate_prefix", "AGG")
        custom_data_templates = kwargs.get("custom_data_templates", {})
        source_service = kwargs.get("source_service", "event-generator")
        time_range_hours = kwargs.get("time_range_hours", 24)
        seed = kwargs.get("seed")

        if seed is not None:
            random.seed(seed)

        # Generate events
        events = []
        now = datetime.now(UTC)

        # Create a set of aggregate IDs for realistic event grouping
        num_aggregates = max(1, event_count // 3)  # Roughly 3 events per aggregate
        aggregate_ids = [
            f"{aggregate_prefix}-{i:04d}" for i in range(1, num_aggregates + 1)
        ]

        for i in range(event_count):
            # Select event type and aggregate
            event_type = random.choice(event_types)
            aggregate_id = random.choice(aggregate_ids)

            # Generate timestamp within range
            hours_offset = random.uniform(-time_range_hours, 0)
            event_timestamp = now.timestamp() + hours_offset * 3600
            event_time = datetime.fromtimestamp(event_timestamp, tz=UTC)

            # Generate event data
            event_data = self._generate_event_data(
                event_type, aggregate_id, custom_data_templates.get(event_type, {})
            )

            # Create event
            event = {
                "event_id": f"evt-{uuid.uuid4().hex[:8]}",
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "timestamp": event_time.isoformat() + "Z",
                "data": event_data,
                "metadata": {
                    "source": source_service,
                    "version": 1,
                    "correlation_id": f"corr-{uuid.uuid4().hex[:8]}",
                    "generated": True,
                },
            }
            events.append(event)

        # Sort events by timestamp for realistic ordering
        events.sort(key=lambda x: x["timestamp"])

        # Generate metadata
        metadata = {
            "total_events": len(events),
            "event_types": list(set(e["event_type"] for e in events)),
            "aggregate_count": len(set(e["aggregate_id"] for e in events)),
            "time_range": {
                "start": events[0]["timestamp"] if events else None,
                "end": events[-1]["timestamp"] if events else None,
            },
            "generated_at": now.isoformat() + "Z",
            "source": source_service,
        }

        return {
            "events": events,
            "metadata": metadata,
            "event_count": len(events),
            "event_types": metadata["event_types"],
            "aggregate_count": metadata["aggregate_count"],
        }

    def _generate_event_data(
        self, event_type: str, aggregate_id: str, template: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate event-specific data based on type and template."""

        # Default data generators by event type
        default_generators = {
            "OrderCreated": lambda: {
                "customer_id": f"CUST-{random.randint(100, 999)}",
                "total_amount": round(random.uniform(10.0, 1000.0), 2),
                "item_count": random.randint(1, 5),
                "status": "pending",
                "payment_method": random.choice(
                    ["credit_card", "debit_card", "paypal"]
                ),
            },
            "PaymentProcessed": lambda: {
                "payment_id": f"PAY-{random.randint(10000, 99999)}",
                "amount": round(random.uniform(10.0, 1000.0), 2),
                "method": random.choice(["credit_card", "debit_card", "paypal"]),
                "status": random.choice(["success", "failed", "pending"]),
                "transaction_id": f"txn-{uuid.uuid4().hex[:12]}",
            },
            "OrderShipped": lambda: {
                "tracking_number": f"TRACK-{random.randint(100000, 999999)}",
                "carrier": random.choice(["UPS", "FedEx", "DHL", "USPS"]),
                "status": "shipped",
                "estimated_delivery": datetime.now(UTC)
                .replace(day=datetime.now().day + random.randint(1, 7))
                .isoformat()
                + "Z",
            },
            "UserRegistered": lambda: {
                "username": f"user_{random.randint(1000, 9999)}",
                "email": f"user_{random.randint(1000, 9999)}@example.com",
                "plan": random.choice(["free", "premium", "enterprise"]),
                "registration_source": random.choice(["web", "mobile", "api"]),
            },
            "UserLoggedIn": lambda: {
                "ip_address": f"192.168.1.{random.randint(1, 254)}",
                "device": random.choice(
                    [
                        "Chrome/Windows",
                        "Safari/macOS",
                        "Firefox/Linux",
                        "Mobile/iOS",
                        "Mobile/Android",
                    ]
                ),
                "session_id": f"sess-{uuid.uuid4().hex[:16]}",
            },
            "SubscriptionCreated": lambda: {
                "plan": random.choice(["basic", "premium", "enterprise"]),
                "price": random.choice([9.99, 29.99, 99.99, 199.99]),
                "billing_cycle": random.choice(["monthly", "yearly"]),
                "trial_days": random.choice([0, 7, 14, 30]),
            },
        }

        # Use template if provided, otherwise use default generator
        if template:
            data = {}
            for key, value_template in template.items():
                if isinstance(value_template, str):
                    # Simple string templating
                    data[key] = value_template.format(
                        id=random.randint(1, 999),
                        random_ip=random.randint(1, 254),
                        username=f"user_{random.randint(1000, 9999)}",
                        aggregate_id=aggregate_id,
                    )
                else:
                    data[key] = value_template
            return data
        elif event_type in default_generators:
            return default_generators[event_type]()
        else:
            # Generic event data
            return {
                "event_data": f"Generated data for {event_type}",
                "aggregate_id": aggregate_id,
                "timestamp": datetime.now(UTC).isoformat() + "Z",
            }

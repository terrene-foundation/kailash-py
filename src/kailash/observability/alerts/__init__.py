# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reference alert adapters for runtime lifecycle hooks (issue #914).

Each adapter is a thin :class:`TaskEvent` / :class:`JobEvent` consumer that
posts a structured payload to an external alerter. Adapters are intentionally
small — production deployments are encouraged to copy-and-extend them rather
than wrap them in additional layers.

Public API
----------

- :class:`SlackTaskAlertAdapter` — post task lifecycle events to Slack.
- :class:`WebhookTaskAlertAdapter` — post task lifecycle events to any HTTP endpoint.
- :class:`SlackJobAlertAdapter` — post scheduler job events to Slack.
- :class:`WebhookJobAlertAdapter` — post scheduler job events to any HTTP endpoint.

Use as registered handlers::

    from kailash.observability.alerts import SlackTaskAlertAdapter

    adapter = SlackTaskAlertAdapter(webhook_url="https://hooks.slack.com/...")
    worker.on_task_failure(adapter)
"""

from kailash.observability.alerts.slack import (
    SlackJobAlertAdapter,
    SlackTaskAlertAdapter,
)
from kailash.observability.alerts.webhook import (
    WebhookJobAlertAdapter,
    WebhookTaskAlertAdapter,
)

__all__ = [
    "SlackTaskAlertAdapter",
    "WebhookTaskAlertAdapter",
    "SlackJobAlertAdapter",
    "WebhookJobAlertAdapter",
]

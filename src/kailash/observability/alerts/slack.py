# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Slack alert adapters for runtime lifecycle hooks (issue #914).

Posts task / job lifecycle events to a Slack incoming webhook URL using the
attachment color scheme convention: success=good, error=danger, retry=warning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from kailash.runtime.lifecycle_events import JobEvent, TaskEvent

logger = logging.getLogger(__name__)

__all__ = ["SlackTaskAlertAdapter", "SlackJobAlertAdapter"]

_DEFAULT_TIMEOUT_SECONDS = 5.0


def _exception_block(exc: Optional[BaseException]) -> Optional[Dict[str, Any]]:
    if exc is None:
        return None
    return {
        "title": "Exception",
        "value": f"{type(exc).__name__}: {exc}",
        "short": False,
    }


class SlackTaskAlertAdapter:
    """Post :class:`TaskEvent` payloads to a Slack webhook."""

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str = "#alerts",
        username: str = "Kailash Worker",
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.timeout = timeout

    def __call__(self, event: TaskEvent) -> None:
        payload = self._to_payload(event)
        try:
            response = requests.post(
                self.webhook_url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as exc:
            # Per `observability.md` Rule 3a: an alerter that fails MUST NOT
            # crash the lifecycle dispatch. The Worker's dispatcher already
            # catches; we log here for adapter-specific failure detail.
            logger.warning(
                "SlackTaskAlertAdapter POST to %s failed: %s",
                self.webhook_url,
                exc,
            )

    def _to_payload(self, event: TaskEvent) -> Dict[str, Any]:
        # Color is "good" for success (no exception), "danger" otherwise.
        color = "good" if event.exception is None else "danger"
        title = f"Task {event.task_id} {'failed' if event.exception else 'completed'}"
        fields = [
            {
                "title": "Workflow",
                "value": event.workflow_name or "(unnamed)",
                "short": True,
            },
            {"title": "Worker", "value": event.worker_id, "short": True},
            {
                "title": "Attempt",
                "value": f"{event.attempt}/{event.max_attempts}",
                "short": True,
            },
            {
                "title": "Elapsed",
                "value": (
                    f"{event.elapsed_ms:.0f} ms"
                    if event.elapsed_ms is not None
                    else "(prerun)"
                ),
                "short": True,
            },
        ]
        exc_block = _exception_block(event.exception)
        if exc_block:
            fields.append(exc_block)
        return {
            "channel": self.channel,
            "username": self.username,
            "icon_emoji": ":warning:" if event.exception else ":white_check_mark:",
            "attachments": [
                {
                    "color": color,
                    "title": title,
                    "fields": fields,
                    "ts": int(event.timestamp),
                }
            ],
        }


class SlackJobAlertAdapter:
    """Post :class:`JobEvent` payloads to a Slack webhook."""

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str = "#alerts",
        username: str = "Kailash Scheduler",
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.timeout = timeout

    def __call__(self, event: JobEvent) -> None:
        payload = self._to_payload(event)
        try:
            response = requests.post(
                self.webhook_url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "SlackJobAlertAdapter POST to %s failed: %s",
                self.webhook_url,
                exc,
            )

    def _to_payload(self, event: JobEvent) -> Dict[str, Any]:
        color = "good" if event.exception is None else "danger"
        title = (
            f"Schedule {event.schedule_id} "
            f"{'errored' if event.exception else 'fired'}"
        )
        fields = [
            {
                "title": "Schedule",
                "value": event.schedule_name or "(unnamed)",
                "short": True,
            },
            {
                "title": "Fire time",
                "value": (
                    event.scheduled_run_time.isoformat()
                    if event.scheduled_run_time is not None
                    else "(unknown)"
                ),
                "short": True,
            },
        ]
        exc_block = _exception_block(event.exception)
        if exc_block:
            fields.append(exc_block)
        return {
            "channel": self.channel,
            "username": self.username,
            "icon_emoji": ":warning:" if event.exception else ":alarm_clock:",
            "attachments": [
                {
                    "color": color,
                    "title": title,
                    "fields": fields,
                    "ts": int(event.timestamp),
                }
            ],
        }

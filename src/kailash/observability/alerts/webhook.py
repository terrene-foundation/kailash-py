# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Generic webhook alert adapters for runtime lifecycle hooks (issue #914).

A Discord webhook URL works as-is with :class:`WebhookTaskAlertAdapter` /
:class:`WebhookJobAlertAdapter` because Discord accepts the same JSON shape
under the ``content`` key. For Discord-specific embed formatting, copy this
adapter and customize ``_to_payload``.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

import requests

from kailash.runtime.lifecycle_events import JobEvent, TaskEvent

logger = logging.getLogger(__name__)

__all__ = ["WebhookTaskAlertAdapter", "WebhookJobAlertAdapter"]

_DEFAULT_TIMEOUT_SECONDS = 5.0


def _serialize_exception(exc: Optional[BaseException]) -> Optional[Dict[str, str]]:
    if exc is None:
        return None
    return {"type": type(exc).__name__, "message": str(exc)}


class WebhookTaskAlertAdapter:
    """Post :class:`TaskEvent` payloads to an HTTP endpoint as JSON."""

    def __init__(
        self,
        webhook_url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self.timeout = timeout

    def __call__(self, event: TaskEvent) -> None:
        payload = self._to_payload(event)
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            # Per `observability.md` Rule 3a: an alerter that fails MUST NOT
            # crash the lifecycle dispatch. The Worker's dispatcher already
            # catches; we log here for adapter-specific failure detail.
            logger.warning(
                "WebhookTaskAlertAdapter POST to %s failed: %s",
                self.webhook_url,
                exc,
            )

    @staticmethod
    def _to_payload(event: TaskEvent) -> Dict[str, Any]:
        data = asdict(event)
        # asdict cannot serialize BaseException; replace with a typed dict.
        data["exception"] = _serialize_exception(event.exception)
        return data


class WebhookJobAlertAdapter:
    """Post :class:`JobEvent` payloads to an HTTP endpoint as JSON."""

    def __init__(
        self,
        webhook_url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self.timeout = timeout

    def __call__(self, event: JobEvent) -> None:
        payload = self._to_payload(event)
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "WebhookJobAlertAdapter POST to %s failed: %s",
                self.webhook_url,
                exc,
            )

    @staticmethod
    def _to_payload(event: JobEvent) -> Dict[str, Any]:
        return {
            "schedule_id": event.schedule_id,
            "schedule_name": event.schedule_name,
            "scheduled_run_time": (
                event.scheduled_run_time.isoformat()
                if event.scheduled_run_time is not None
                else None
            ),
            "exception": _serialize_exception(event.exception),
            "timestamp": event.timestamp,
        }

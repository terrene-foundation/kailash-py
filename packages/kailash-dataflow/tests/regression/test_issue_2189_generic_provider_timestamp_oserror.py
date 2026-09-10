# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: the DEFAULT ``generic`` webhook provider must not crash on a
finite-but-out-of-range ``X-Webhook-Timestamp``.

Bug history. #2189 fixed the Stripe and Slack verifiers, which guarded the
timestamp parse with ``math.isfinite`` but converted OUTSIDE the guard, so an
attacker-supplied ``t=1e300`` raised ``OverflowError`` past
``WebhookReceiver.handle_webhook``'s documented ``{"accepted": ..., "reason":
...}`` contract and skipped ``metrics.record_webhook``.

That fix stopped one operand short on the ``generic`` path, which is the
DEFAULT ``WebhookConfig.provider``. Its handler caught ``(ValueError,
OverflowError)`` only -- and ``datetime.fromtimestamp`` does not raise one type
for out-of-range input. Measured on CPython 3.13 / macOS:

    1e300  -> OverflowError: timestamp out of range for platform time_t
    1e18   -> OSError: [Errno 84] Value too large to be stored in data type

So ``1e18`` reproduced the ORIGINAL #2189 defect on the default provider after
#2189 was declared fixed. ``OSError`` is now part of the caught set.

Discrimination. ``test_generic_provider_rejects_out_of_range_timestamp``
FAILS against the unfixed source for the ``1e18`` case (it raises rather than
returning). The two companion tests are controls: without them the fix could
have been "reject every timestamp" and the first test would still pass.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import types
from datetime import datetime, timezone

import pytest

from dataflow.fabric.config import WebhookConfig
from dataflow.fabric.webhooks import WebhookReceiver

_SECRET = "regression-2189-secret"
_SECRET_ENV = "DATAFLOW_TEST_WEBHOOK_SECRET_2189"
_BODY = b'{"event": "ping"}'


def _receiver() -> WebhookReceiver:
    config = WebhookConfig(path="/hooks/x", secret_env=_SECRET_ENV, provider="generic")
    source = types.SimpleNamespace(webhook=config)
    return WebhookReceiver(sources={"src": {"config": source}})


def _valid_signature() -> str:
    return hmac.new(_SECRET.encode("utf-8"), _BODY, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The crash sits AFTER the secret lookup, so the env var must be set.

    Without it ``handle_webhook`` returns "Server configuration error" before
    reaching the timestamp branch, and the test would pass vacuously.
    """
    monkeypatch.setenv(_SECRET_ENV, _SECRET)


@pytest.mark.regression
@pytest.mark.parametrize(
    "timestamp",
    [
        "1e300",  # OverflowError on CPython/macOS -- caught before this fix
        "1e18",  # OSError [Errno 84]  -- NOT caught before this fix
        "-1e300",  # negative out-of-range
        "1e17",  # OSError, one order of magnitude down
    ],
)
async def test_generic_provider_rejects_out_of_range_timestamp(
    timestamp: str,
) -> None:
    """A finite-but-unconvertible timestamp is a REJECTION, never an exception.

    Every value here passes ``math.isfinite`` -- that is the whole point: the
    original guard admitted them and the conversion then raised.
    """
    assert math.isfinite(float(timestamp)), "fixture value must pass the isfinite guard"

    result = await _receiver().handle_webhook(
        "src",
        {
            "X-Webhook-Signature": _valid_signature(),
            "X-Webhook-Timestamp": timestamp,
        },
        _BODY,
    )

    assert result == {"accepted": False, "reason": "Invalid timestamp format"}


@pytest.mark.regression
async def test_out_of_range_timestamp_is_counted_by_the_metric() -> None:
    """The rejection must be VISIBLE.

    The second half of #2189: an escaping exception skipped
    ``metrics.record_webhook`` entirely, so a hostile delivery disappeared from
    ``fabric_webhook_received_total`` rather than being counted as rejected.
    """
    from dataflow.fabric import metrics as metrics_module

    metrics = metrics_module.get_fabric_metrics()
    recorded: list[tuple[str, bool]] = []
    original = metrics.record_webhook
    metrics.record_webhook = lambda source, accepted: recorded.append(  # type: ignore[method-assign]
        (source, accepted)
    )
    try:
        await _receiver().handle_webhook(
            "src",
            {
                "X-Webhook-Signature": _valid_signature(),
                "X-Webhook-Timestamp": "1e18",
            },
            _BODY,
        )
    finally:
        metrics.record_webhook = original  # type: ignore[method-assign]

    assert recorded == [("src", False)]


@pytest.mark.regression
async def test_control_a_well_formed_timestamp_is_still_accepted() -> None:
    """Control: the fix must not have turned the branch into a blanket reject.

    Returns the OPPOSITE verdict from the tests above, so a "reject
    everything" implementation fails here.
    """
    result = await _receiver().handle_webhook(
        "src",
        {
            "X-Webhook-Signature": _valid_signature(),
            "X-Webhook-Timestamp": datetime.now(timezone.utc).isoformat(),
        },
        _BODY,
    )

    assert result["accepted"] is True, result


@pytest.mark.regression
async def test_control_a_bad_signature_is_still_rejected_for_the_right_reason() -> None:
    """Control: rejections must still be attributed to their real cause.

    Guards against a fix that collapses every failure into "Invalid timestamp
    format" and so appears to pass the out-of-range cases for the wrong reason.
    """
    result = await _receiver().handle_webhook(
        "src",
        {
            "X-Webhook-Signature": "0" * 64,
            "X-Webhook-Timestamp": datetime.now(timezone.utc).isoformat(),
        },
        _BODY,
    )

    assert result["accepted"] is False
    assert result["reason"] != "Invalid timestamp format", result

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the per-endpoint rate-limit map MUST be bounded in BOTH levels.

``Nexus.endpoint``'s in-memory limiter keys ``request_counts`` by client IP,
each holding a dict of minute-bucket counters. The cleanup evicted stale minute
buckets for the IP CURRENTLY in flight, and nothing ever evicted the outer
``client_ip`` key -- so every IP the endpoint had ever seen retained an entry
for the process lifetime. The comment ``# Cleanup old entries (prevent memory
leak)`` was true of the inner dict and false of the outer one.

On a directly-exposed endpoint, an attacker rotating source addresses (trivial
over IPv6) grows that map without bound.

Instrument note: the bound is asserted by driving the registered wrapper
directly with synthetic ``Request`` objects and reading the closure cell that
holds ``request_counts``. That is structural rather than behavioural, and
deliberately so -- map size has no HTTP-observable surface, and the alternative
(inferring eviction from a victim IP's counter resetting) would assert the
fail-open side effect rather than the property under test. The synthetic
requests exercise the real wrapper, including the real cleanup path.
"""

from collections import defaultdict

import pytest
from fastapi import Request
from nexus import Nexus
from nexus.core import _MAX_RATE_LIMIT_TRACKED_CLIENTS


def _request_counts_of(wrapper) -> defaultdict:
    """Return the ``request_counts`` map captured in the wrapper's closure."""
    for cell in wrapper.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:  # pragma: no cover - empty cell
            continue
        # The only defaultdict in this closure is the per-IP counter map.
        if isinstance(value, defaultdict):
            return value
    raise AssertionError(
        "could not locate request_counts in the wrapper closure; the limiter's "
        "internal structure changed and this test needs updating"
    )


def _synthetic_request(ip: str) -> Request:
    """A real Starlette/FastAPI Request carrying a chosen client address."""
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/probe-bound",
            "raw_path": b"/probe-bound",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "headers": [],
            "client": (ip, 51234),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_client_ip_map_stays_bounded_under_address_rotation():
    """Distinct client IPs MUST NOT grow the counter map without bound.

    Falsifying result: before the fix the map held one entry per distinct IP
    forever, so this reached ``rotations`` entries instead of the cap.
    """
    app = Nexus(
        api_port=8251,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    @app.endpoint("/probe-bound", methods=["GET"], rate_limit=1000)
    async def probe(request: Request):
        return {"ok": True}

    try:
        counts = _request_counts_of(probe)
        rotations = _MAX_RATE_LIMIT_TRACKED_CLIENTS + 500

        for i in range(rotations):
            await probe(
                request=_synthetic_request(
                    f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"
                )
            )

        assert len(counts) <= _MAX_RATE_LIMIT_TRACKED_CLIENTS, (
            f"counter map grew to {len(counts)} entries for {rotations} distinct "
            f"client IPs; cap is {_MAX_RATE_LIMIT_TRACKED_CLIENTS}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_bounding_does_not_break_enforcement_for_a_steady_client():
    """The eviction MUST NOT drop the counter of a continuously-active client.

    Guards the over-broad fix (evicting indiscriminately, or evicting the
    in-flight client): a single steady IP must still hit its limit.
    """
    app = Nexus(
        api_port=8252,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    @app.endpoint("/probe-steady", methods=["GET"], rate_limit=5)
    async def probe(request: Request):
        return {"ok": True}

    try:
        from fastapi import HTTPException

        steady = _synthetic_request("192.0.2.7")
        statuses = []
        for _ in range(9):
            try:
                await probe(request=steady)
                statuses.append(200)
            except HTTPException as exc:
                statuses.append(exc.status_code)

        assert 429 in statuses, f"steady client was never limited: {statuses}"
        assert statuses[0] == 200, f"first request should pass, got {statuses[0]}"
    finally:
        if app._running:
            app.stop()

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

import gc
import time
from typing import MutableMapping

import pytest
from fastapi import Request
from nexus import Nexus
from nexus.core import _MAX_RATE_LIMIT_TRACKED_CLIENTS


def _request_counts_of(wrapper) -> MutableMapping:
    """Return the ``request_counts`` map captured in the wrapper's closure."""
    for cell in wrapper.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:  # pragma: no cover - empty cell
            continue
        # The only mapping in this closure is the per-IP counter map. Matched
        # on `dict` rather than a concrete subclass so the probe survives the
        # limiter switching its container (defaultdict -> OrderedDict).
        if isinstance(value, dict):
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
async def test_eviction_cost_per_request_does_not_explode_at_the_cap():
    """Reaching the cap MUST NOT make every subsequent request expensive.

    The sibling test above asserts only that the map stays bounded, and it
    passes at ANY per-request cost. The first bounding fix paid for the bound
    with a full scan plus a full sort of the map on EVERY new client once the
    cap was reached -- not amortised, per request, forever. Measured at
    2.5 us/request below the cap and 17,660 us/request at it: 17.66 ms of
    synchronous CPU inside an ``async def`` with no await point, which blocks
    the event loop for the whole process, every endpoint. Rotating source
    addresses (trivial over IPv6) is all it takes to hold it there.

    The bound is expressed as a SELF-NORMALIZING RATIO of two measurements
    taken in the same run on the same machine, not as an absolute wall-clock
    threshold: an absolute threshold has to be set loose enough for the
    slowest CI runner, which is exactly loose enough to hide the regression,
    and it ratchets upward every time it flakes.

    The garbage collector is held off across BOTH measurement windows, and
    only across those. A full map keeps ~10k live container objects, so a
    generational pass costs far more at the cap than below it -- real, but a
    cost of the BOUND itself, not of the eviction path this test is about.
    Leaving it in measured a property nobody is asserting: the ratio came out
    at 1x running the file alone and 389x under the full suite, with the same
    fixed code. Suspending it symmetrically is what makes the two windows
    comparable.

    Falsifying result: before the fix the ratio measures in the thousands
    (5867x, 8142.6 us vs 1.4 us per request, measured under this instrument).
    """
    app = Nexus(
        api_port=8253,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    @app.endpoint("/probe-cost", methods=["GET"], rate_limit=1000)
    async def probe(request: Request):
        return {"ok": True}

    def _ip(i: int) -> str:
        return f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"

    async def drive(start: int, stop: int) -> None:
        for i in range(start, stop):
            await probe(request=_synthetic_request(_ip(i)))

    async def measure(start: int, stop: int) -> float:
        """Wall time for ``stop - start`` new clients, with the GC held off."""
        gc.collect()
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            started = time.perf_counter()
            await drive(start, stop)
            return time.perf_counter() - started
        finally:
            if was_enabled:
                gc.enable()

    try:
        counts = _request_counts_of(probe)
        sample = 500

        # Phase 1 -- comfortably below the cap. Warm first so the measured
        # window excludes first-call import/JIT effects.
        await drive(0, 1000)
        below_cap = await measure(1000, 1000 + sample)

        # Phase 2 -- fill exactly to the cap, then measure the same number of
        # NEW clients, each of which now triggers the eviction path.
        await drive(1000 + sample, _MAX_RATE_LIMIT_TRACKED_CLIENTS)
        assert len(counts) == _MAX_RATE_LIMIT_TRACKED_CLIENTS, (
            "expected the map to be exactly full before measuring the "
            f"at-cap cost; it holds {len(counts)}"
        )

        at_cap = await measure(
            _MAX_RATE_LIMIT_TRACKED_CLIENTS,
            _MAX_RATE_LIMIT_TRACKED_CLIENTS + sample,
        )

        ratio = at_cap / below_cap
        assert ratio <= 25, (
            f"per-request cost at the cap is {ratio:.0f}x the below-cap cost "
            f"({at_cap / sample * 1e6:.1f} us vs {below_cap / sample * 1e6:.1f} us "
            "per request). Eviction is not amortised: every new client pays a "
            "full pass over the map. This runs synchronously inside an async "
            "handler, so it blocks the event loop for the entire process."
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

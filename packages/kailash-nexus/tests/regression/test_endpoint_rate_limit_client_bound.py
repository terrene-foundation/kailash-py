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

from collections import OrderedDict
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


#: Ceiling on map entries the eviction path may visit per request at the cap.
#: The amortised implementation visits 0; the scan-and-sort regression visits
#: one per entry (10,000 at the cap). Anything CONSTANT passes, anything
#: PROPORTIONAL to map size fails. The gap is five orders of magnitude, so the
#: exact constant is not load-bearing -- 2 leaves room for an implementation
#: that peeks a neighbour or two without admitting a pass.
_MAX_ENTRIES_VISITED_PER_REQUEST = 2


class _TraversalCountingMap(OrderedDict):
    """``OrderedDict`` that counts entries yielded by traversal.

    O(1) map operations -- ``get``, ``__setitem__``, ``__delitem__``,
    ``move_to_end``, ``popitem``, ``len`` -- do NOT go through ``__iter__``
    and are therefore not counted. Anything that WALKS the map (``for k in
    m``, ``.items()``, ``.keys()``, ``.values()``, ``max(m, ...)``,
    ``sorted(m)``) yields through the counting generator, so the tally IS the
    number of entries the caller examined.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entries_visited = 0

    def _counted(self, iterator):
        for item in iterator:
            self.entries_visited += 1
            yield item

    def __iter__(self):
        return self._counted(super().__iter__())

    def keys(self):
        return self._counted(super().keys())

    def values(self):
        return self._counted(super().values())

    def items(self):
        return self._counted(super().items())


def _install_traversal_counter(wrapper) -> _TraversalCountingMap:
    """Swap the wrapper's ``request_counts`` for a traversal-counting map.

    Writes the closure cell in place (CPython 3.7+ permits this), so the code
    under test is the REAL wrapper running its REAL eviction -- only the
    container is instrumented.
    """
    for cell in wrapper.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:  # pragma: no cover - empty cell
            continue
        if isinstance(value, dict):
            counting = _TraversalCountingMap(value)
            cell.cell_contents = counting
            return counting
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

    Instrument: entries VISITED, not microseconds
    ---------------------------------------------
    This measures the property directly -- how many map entries the eviction
    path walks per request -- by swapping ``request_counts`` for an
    ``OrderedDict`` subclass that counts elements yielded by iteration.

    The amortised implementation touches the map only through ``get`` /
    ``__setitem__`` / ``move_to_end`` / ``popitem(last=False)``, none of which
    traverse it: **0 entries visited per request.** The un-amortised one takes
    ``max()`` over every entry's buckets and then ``sorted()`` over all of
    them, to delete exactly one: **one visit per entry per request**, which at
    a 10,000-entry cap is 10,000.

    That is a five-orders-of-magnitude separation with nothing in between, and
    it is a pure function of the algorithm -- unaffected by machine load, CPU
    frequency, GC, log level, or how many sibling suites share the host.

    This replaces a wall-clock ratio (at-cap us/request over below-cap
    us/request, bounded at 25x). That ratio was the right SHAPE -- self
    normalizing, per ``rules/testing.md`` -- but its denominator was ~4 us, so
    a single scheduler preemption on a box running ~10 concurrent unrelated
    suites moved it enough to fail: observed 28.1x while passing 3/3 in
    isolation and passing in two full-suite runs of the same code. Raising 25
    was BLOCKED (``rules/testing.md`` -- a threshold bump is how an O(n^2)
    regression gets buried); smoothing it further would only have suppressed
    the noise. Counting removes it.

    Falsifying result: with the un-amortised eviction restored, this
    instrument measures **10,001.0 entries visited per request** -- verified,
    not predicted, by patching the eviction back to the scan-and-sort form in
    a scratch worktree and running this exact test against it::

        AssertionError: the eviction path visits 10001.0 map entries per
        request at the cap (limit 2; ...)
        assert 10001.0 <= 2

    (10,000 for the pass plus the one entry the in-flight client added.) The
    bound below sits 5,000x under that, so the verdict does not depend on
    where in the gap the constant is placed.
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

    try:
        counts = _install_traversal_counter(probe)

        # Fill exactly to the cap. Every request past this point evicts.
        await drive(0, _MAX_RATE_LIMIT_TRACKED_CLIENTS)
        assert len(counts) == _MAX_RATE_LIMIT_TRACKED_CLIENTS, (
            "expected the map to be exactly full before measuring the "
            f"at-cap cost; it holds {len(counts)}"
        )

        # Measure ONLY the at-cap window: each of these is a brand-new client
        # arriving at a full map, so each one takes the eviction path.
        measured = 500
        counts.entries_visited = 0
        await drive(
            _MAX_RATE_LIMIT_TRACKED_CLIENTS, _MAX_RATE_LIMIT_TRACKED_CLIENTS + measured
        )
        per_request = counts.entries_visited / measured

        assert per_request <= _MAX_ENTRIES_VISITED_PER_REQUEST, (
            f"the eviction path visits {per_request:.1f} map entries per "
            f"request at the cap (limit {_MAX_ENTRIES_VISITED_PER_REQUEST}; "
            f"the amortised implementation visits 0, and a full pass over a "
            f"{_MAX_RATE_LIMIT_TRACKED_CLIENTS}-entry map visits "
            f"{_MAX_RATE_LIMIT_TRACKED_CLIENTS}). Eviction is not amortised: "
            "every new client pays a pass proportional to the map. This runs "
            "synchronously inside an async handler with no await point, so it "
            "blocks the event loop for the entire process."
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

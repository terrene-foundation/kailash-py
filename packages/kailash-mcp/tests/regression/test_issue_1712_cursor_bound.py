# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for #1712 - ``CursorManager`` unbounded-store DoS (L4).

Wave 2 routed tools / prompts / resource-templates list pagination through the
shared ``CursorManager._cursors`` store, widening a client's ability to mint
cursors. The store was an unbounded ``dict`` with no size cap, so a client
minting cursors across those list types could grow server memory without
limit (a remote DoS).

The fix bounds the store with FIFO eviction (``_MAX_CURSORS``), mirroring
``MCPServer._MAX_SEEN_REQUEST_IDS``. These behavioral pins construct a real
``CursorManager`` (no mocking, per ``rules/testing.md`` Tier 2), mint real
cursors, and assert the store stays bounded AND that recent cursors still
round-trip.
"""

import pytest

from kailash_mcp.advanced.subscriptions import CursorManager


@pytest.mark.regression
def test_cursor_store_stays_bounded_on_overflow():
    """Minting far more than the cap keeps the store at exactly the cap."""
    cm = CursorManager()
    cm._MAX_CURSORS = 5  # small cap so the test is fast and explicit

    minted = [cm.generate_cursor() for _ in range(50)]

    # The store never exceeds the cap despite 50 mints.
    assert len(cm._cursors) == 5
    # The 5 MOST-RECENT cursors survive; the rest were FIFO-evicted.
    for cursor in minted[-5:]:
        assert cm.is_valid(cursor) is True
    for cursor in minted[:-5]:
        assert cm.is_valid(cursor) is False


@pytest.mark.regression
def test_cursor_fifo_evicts_oldest_first():
    """The OLDEST cursor is evicted first when the cap is exceeded."""
    cm = CursorManager()
    cm._MAX_CURSORS = 3

    first = cm.generate_cursor()
    second = cm.generate_cursor()
    third = cm.generate_cursor()

    # At the cap — all three still valid.
    assert cm.is_valid(first) is True

    # One more mint overflows: the oldest (`first`) is evicted, the rest stay.
    fourth = cm.generate_cursor()
    assert cm.is_valid(first) is False
    assert cm.is_valid(second) is True
    assert cm.is_valid(third) is True
    assert cm.is_valid(fourth) is True
    assert len(cm._cursors) == 3


@pytest.mark.regression
def test_recent_cursor_round_trips_under_bound():
    """A valid recent position cursor still resolves after the store bounds.

    Bounding the store MUST NOT break the common case: a cursor minted for a
    list position still resolves to that position while it is recent.
    """
    cm = CursorManager()
    cm._MAX_CURSORS = 4

    items = ["a", "b", "c", "d", "e"]
    cursor = cm.create_cursor_for_position(items, position=2)

    # Mint more cursors (but stay at/under the cap window around this one).
    for _ in range(2):
        cm.generate_cursor()

    # The position cursor is still recent, so it round-trips correctly.
    assert cm.is_valid(cursor) is True
    assert cm.get_cursor_position(cursor) == 2


@pytest.mark.regression
def test_default_cap_bounds_store():
    """The default ``_MAX_CURSORS`` bounds the store without an override."""
    cm = CursorManager()
    cap = cm._MAX_CURSORS

    for _ in range(cap + 100):
        cm.generate_cursor()

    assert len(cm._cursors) == cap

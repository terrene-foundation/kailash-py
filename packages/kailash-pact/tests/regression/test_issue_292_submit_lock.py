# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression: #292 — PactEngine lacks threading.Lock — concurrent submit() race.

Before fix: Two concurrent submit() calls could both read the same
remaining budget and both proceed, overspending the budget.

After fix: PactEngine.submit() acquires an asyncio.Lock, making
check-remaining → execute → record-cost atomic.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pact.engine import PactEngine


FIXTURES_DIR = Path(__file__).parent.parent / "unit" / "governance" / "fixtures"


@pytest.fixture
def minimal_yaml_path() -> Path:
    return FIXTURES_DIR / "minimal-org.yaml"


@pytest.mark.regression
class TestIssue292SubmitLock:
    """PactEngine.submit() must serialize concurrent calls."""

    def test_submit_lock_exists(self, minimal_yaml_path: Path) -> None:
        """PactEngine must have an asyncio.Lock for submit serialization."""
        engine = PactEngine(org=str(minimal_yaml_path))
        assert hasattr(engine, "_submit_lock")
        assert isinstance(engine._submit_lock, asyncio.Lock)

    async def test_concurrent_submits_serialized(self, minimal_yaml_path: Path) -> None:
        """Two concurrent submits must not interleave (lock held)."""
        engine = PactEngine(org=str(minimal_yaml_path), budget_usd=100.0)

        call_order: list[str] = []

        original_submit_locked = engine._submit_locked

        async def tracking_submit(
            objective: str, role: str, context: Any = None
        ) -> Any:
            call_order.append(f"start:{objective}")
            result = await original_submit_locked(objective, role, context)
            call_order.append(f"end:{objective}")
            return result

        engine._submit_locked = tracking_submit  # type: ignore[assignment]

        # Launch two concurrent submits
        results = await asyncio.gather(
            engine.submit("task_A", role="r-dev"),
            engine.submit("task_B", role="r-dev"),
        )

        # Both should complete (even without kaizen-agents)
        assert len(results) == 2

        # The lock ensures A completes before B starts (or vice versa)
        # — no interleaving like start:A, start:B, end:A, end:B
        assert call_order[0].startswith("start:")
        first_task = call_order[0].split(":")[1]
        assert call_order[1] == f"end:{first_task}"

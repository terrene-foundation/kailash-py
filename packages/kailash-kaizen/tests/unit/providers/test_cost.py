# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for SPEC-02 cost tracking.

Covers:
- ``ModelPricing`` frozen dataclass.
- ``CostConfig`` enabled/disabled toggle.
- ``CostTracker`` accumulation, thread safety, reset, and record cap.
"""

from __future__ import annotations

import threading

from kaizen.providers.cost import CostConfig, CostTracker, ModelPricing


class TestModelPricing:
    """ModelPricing is a frozen dataclass with per-1k-token costs."""

    def test_defaults_are_zero(self):
        p = ModelPricing()
        assert p.prompt_cost_per_1k == 0.0
        assert p.completion_cost_per_1k == 0.0

    def test_frozen(self):
        p = ModelPricing(prompt_cost_per_1k=0.03, completion_cost_per_1k=0.06)
        try:
            p.prompt_cost_per_1k = 0.05  # type: ignore[misc]
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass  # expected — frozen dataclass

    def test_custom_values(self):
        p = ModelPricing(prompt_cost_per_1k=0.015, completion_cost_per_1k=0.06)
        assert p.prompt_cost_per_1k == 0.015
        assert p.completion_cost_per_1k == 0.06


class TestCostConfig:
    """CostConfig gates tracking and holds model pricing."""

    def test_defaults(self):
        c = CostConfig()
        assert c.enabled is True
        assert c.pricing == {}

    def test_disabled(self):
        c = CostConfig(enabled=False)
        assert c.enabled is False

    def test_pricing_dict(self):
        c = CostConfig(
            pricing={
                "gpt-4o": ModelPricing(
                    prompt_cost_per_1k=0.005, completion_cost_per_1k=0.015
                ),
            }
        )
        assert "gpt-4o" in c.pricing


class TestCostTracker:
    """CostTracker accumulates token costs thread-safely."""

    def _make_tracker(self) -> CostTracker:
        config = CostConfig(
            pricing={
                "gpt-4o": ModelPricing(
                    prompt_cost_per_1k=0.005,
                    completion_cost_per_1k=0.015,
                ),
                "claude-3-5-sonnet": ModelPricing(
                    prompt_cost_per_1k=0.003,
                    completion_cost_per_1k=0.015,
                ),
            }
        )
        return CostTracker(config=config)

    def test_initial_state_is_zero(self):
        t = self._make_tracker()
        assert t.total_cost_usd == 0.0
        assert t.total_prompt_tokens == 0
        assert t.total_completion_tokens == 0
        assert t.records == []

    def test_record_returns_incremental_cost(self):
        t = self._make_tracker()
        cost = t.record("gpt-4o", prompt_tokens=1000, completion_tokens=500)
        # 1000 * 0.005/1000 + 500 * 0.015/1000 = 0.005 + 0.0075 = 0.0125
        assert abs(cost - 0.0125) < 1e-9

    def test_accumulates_across_calls(self):
        t = self._make_tracker()
        t.record("gpt-4o", prompt_tokens=1000, completion_tokens=0)
        t.record("gpt-4o", prompt_tokens=1000, completion_tokens=0)
        assert t.total_prompt_tokens == 2000
        assert abs(t.total_cost_usd - 0.01) < 1e-9

    def test_unknown_model_uses_zero_pricing(self):
        t = self._make_tracker()
        cost = t.record("unknown-model", prompt_tokens=1000, completion_tokens=1000)
        assert cost == 0.0
        # Tokens still counted even with zero pricing.
        assert t.total_prompt_tokens == 1000
        assert t.total_completion_tokens == 1000

    def test_disabled_tracking_returns_zero(self):
        t = CostTracker(config=CostConfig(enabled=False))
        cost = t.record("gpt-4o", prompt_tokens=1000, completion_tokens=500)
        assert cost == 0.0
        assert t.total_cost_usd == 0.0
        assert t.total_prompt_tokens == 0

    def test_records_list(self):
        t = self._make_tracker()
        t.record("gpt-4o", prompt_tokens=100, completion_tokens=50)
        t.record("claude-3-5-sonnet", prompt_tokens=200, completion_tokens=100)
        records = t.records
        assert len(records) == 2
        assert records[0]["model"] == "gpt-4o"
        assert records[1]["model"] == "claude-3-5-sonnet"
        assert all("cost_usd" in r for r in records)

    def test_reset_clears_state(self):
        t = self._make_tracker()
        t.record("gpt-4o", prompt_tokens=1000, completion_tokens=500)
        assert t.total_cost_usd > 0

        t.reset()
        assert t.total_cost_usd == 0.0
        assert t.total_prompt_tokens == 0
        assert t.total_completion_tokens == 0
        assert t.records == []

    def test_records_capped_at_maxlen(self):
        t = self._make_tracker()
        for i in range(10_050):
            t.record("gpt-4o", prompt_tokens=1, completion_tokens=0)
        # deque maxlen is 10000
        assert len(t.records) == 10_000

    def test_thread_safety(self):
        """Concurrent recording does not corrupt totals."""
        t = self._make_tracker()
        n_threads = 8
        calls_per_thread = 500

        def _worker():
            for _ in range(calls_per_thread):
                t.record("gpt-4o", prompt_tokens=10, completion_tokens=5)

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        expected_prompt = n_threads * calls_per_thread * 10
        expected_completion = n_threads * calls_per_thread * 5
        assert t.total_prompt_tokens == expected_prompt
        assert t.total_completion_tokens == expected_completion

    def test_default_config_when_none(self):
        t = CostTracker(config=None)
        cost = t.record("any-model", prompt_tokens=100, completion_tokens=50)
        assert cost == 0.0  # no pricing configured
        assert t.total_prompt_tokens == 100

"""Regression tests for #1708 Wave 4 (kaizen observability).

Two gaps closed:

1. ``kaizen.production.metrics.MetricsCollector``'s request-duration
   "histogram" was count/sum-only fake data — it never emitted ``le=``
   bucket boundaries, so ``histogram_quantile()`` (p95/p99) could never be
   computed over it. Replaced with a REAL ``prometheus_client.Histogram``
   (the same pattern already proven in
   ``kaizen.core.autonomy.hooks.builtin.metrics_hook.MetricsHook``) with
   explicit second-scale buckets.

2. LLM token + cost usage was ABSENT from every metric surface — only the
   ``cost_update`` EVENT STREAM carried it (``StreamingExecutor`` /
   ``CostUpdateEvent``), invisible to Prometheus/Grafana/alerting. Added
   ``kaizen_llm_prompt_tokens_total`` / ``kaizen_llm_completion_tokens_total``
   / ``kaizen_llm_cost_microdollars_total`` counters, wired at the SAME
   ``cost_update`` emission points inside ``StreamingExecutor`` (both the
   primary agent call and each subagent call), with BOUNDED ``model``/
   ``provider`` labels (overflow -> "_other").

These tests drive the REAL emission path end-to-end (no mocking of the
metrics collector or the Prometheus registry) and assert against the real
``prometheus_client`` registry / ``export_prometheus()`` text — per
testing.md's Tier 2 "NO mocking" contract and probe-driven-verification.md
(structural/behavioral assertions, not regex-over-prose).
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from prometheus_client.parser import text_string_to_metric_families

from kaizen.execution.streaming_executor import StreamingExecutor
from kaizen.production.metrics import (
    MetricsCollector,
    _bound_model_label,
    _bound_provider_label,
)


class _Agent:
    """Minimal agent stub satisfying StreamingExecutor's sync-agent contract.

    Not a mock of the metrics/Prometheus surface under test — it only
    stands in for a Kaizen agent's ``run()`` return shape so the REAL
    StreamingExecutor -> MetricsCollector -> prometheus_client path runs
    unmodified end-to-end (`testing.md` Tier 2 "NO mocking" applies to the
    metrics path, not to a throwaway agent double).
    """

    def __init__(self, name: str, agent_id: str, result: Dict[str, Any]):
        self.name = name
        self.agent_id = agent_id
        self._result = result

    def run(self, **kwargs) -> Dict[str, Any]:
        return self._result


def _families_by_name(prom_text: str) -> Dict[str, Any]:
    """Parse real Prometheus exposition text into a name -> family map.

    NOTE: ``prometheus_client.parser`` strips the trailing ``_total`` from
    Counter family names (upstream Prometheus convention — matches
    ``Counter().describe()``/``CollectorRegistry.collect()`` shape), so a
    Counter declared as ``kaizen_llm_prompt_tokens_total`` parses back as
    family name ``kaizen_llm_prompt_tokens``. Look families up WITHOUT the
    ``_total`` suffix.
    """
    return {fam.name: fam for fam in text_string_to_metric_families(prom_text)}


def _sample_value(family, expected_labels: Dict[str, str]) -> float | None:
    """Return the value of the ``_total``-suffixed counter sample matching
    ``expected_labels`` — NOT the sibling ``_created`` gauge sample every
    ``prometheus_client`` Counter also emits under the same labels."""
    for sample in family.samples:
        if sample.name.endswith("_created"):
            continue
        if all(sample.labels.get(k) == v for k, v in expected_labels.items()):
            return sample.value
    return None


# ===========================================================================
# Deliverable 1 — real bucketed histogram (replaces the count/sum fake)
# ===========================================================================


class TestRealDurationHistogram:
    """MetricsCollector's duration histogram is a REAL prometheus_client
    Histogram with explicit second-scale buckets — not a count/sum fake."""

    @pytest.mark.regression
    @pytest.mark.observability
    def test_export_contains_real_le_buckets(self):
        """The exported text has ``_bucket{...,le="..."}`` lines — the shape
        a fake count/sum-only histogram can never produce."""
        collector = MetricsCollector()
        collector.track_duration("qa_agent", 0.03)
        collector.track_duration("qa_agent", 0.6)
        collector.track_duration("qa_agent", 4.2)

        text = collector.export_prometheus()
        families = _families_by_name(text)

        assert "kaizen_request_duration_seconds" in families
        histogram = families["kaizen_request_duration_seconds"]
        assert histogram.type == "histogram"

        bucket_samples = [s for s in histogram.samples if s.name.endswith("_bucket")]
        assert bucket_samples, "histogram export must include _bucket samples"

        # Explicit second-scale buckets (not the default prometheus_client
        # 10s-ceiling buckets) — le=30.0 and le=60.0 MUST be present.
        le_values = {s.labels["le"] for s in bucket_samples}
        assert "30.0" in le_values
        assert "60.0" in le_values
        assert "+Inf" in le_values

        # Cumulative counts: le=0.05 sees only the 0.03s observation;
        # le=1.0 sees the 0.03s + 0.6s observations; le=+Inf sees all 3.
        def bucket_count(le: str) -> float:
            return _sample_value(histogram, {"agent_type": "qa_agent", "le": le})

        assert bucket_count("0.05") == 1.0
        assert bucket_count("1.0") == 2.0
        assert bucket_count("+Inf") == 3.0

        # Real _sum / _count series (the part the old fake DID emit too —
        # what it never emitted is the _bucket lines asserted above).
        count_sample = next(
            s
            for s in histogram.samples
            if s.name == "kaizen_request_duration_seconds_count"
        )
        sum_sample = next(
            s
            for s in histogram.samples
            if s.name == "kaizen_request_duration_seconds_sum"
        )
        assert count_sample.value == 3.0
        assert sum_sample.value == pytest.approx(0.03 + 0.6 + 4.2)

    @pytest.mark.regression
    @pytest.mark.observability
    def test_get_duration_stats_unaffected_by_real_histogram_swap(self):
        """The public get_duration_stats() contract (count/sum/min/max/avg)
        still works after swapping the backing store to a real Histogram."""
        collector = MetricsCollector()
        collector.track_duration("qa_agent", 0.5)
        collector.track_duration("qa_agent", 1.5)

        stats = collector.get_duration_stats("qa_agent")
        assert stats["count"] == 2
        assert stats["sum"] == 2.0
        assert stats["min"] == 0.5
        assert stats["max"] == 1.5
        assert stats["avg"] == 1.0


# ===========================================================================
# Deliverable 2 — LLM token + cost counters, reached via the real
# cost_update emission path (StreamingExecutor), not called directly
# ===========================================================================


class TestLlmTokenCostCountersEndToEnd:
    """Feed a real completion/cost event through StreamingExecutor's real
    emission path and assert the counters land in the real registry."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    @pytest.mark.observability
    async def test_primary_agent_cost_update_increments_bounded_counters(self):
        agent = _Agent(
            name="QaAgent",
            agent_id="agent-primary-001",
            result={
                "answer": "The capital of France is Paris.",
                "prompt_tokens": 120,
                "completion_tokens": 45,
                "model": "gpt-4o-2026-01-01",
                "provider": "openai",
                "cost_usd": 0.0034,
            },
        )
        executor = StreamingExecutor()

        events = [e async for e in executor.execute_with_events(agent=agent, task="q")]
        assert len(events) > 0  # real emission path ran to completion

        text = executor.metrics_collector.export_prometheus()
        families = _families_by_name(text)

        # Bounded labels: "gpt-4o-2026-01-01" -> family "openai" (per
        # kaizen.providers.registry._MODEL_PREFIX_MAP), provider "openai"
        # stays "openai" (canonical provider registry entry) — never the
        # raw per-release model string as a label value.
        prompt_family = families["kaizen_llm_prompt_tokens"]
        completion_family = families["kaizen_llm_completion_tokens"]
        cost_family = families["kaizen_llm_cost_microdollars"]

        bounded_labels = {"model": "openai", "provider": "openai"}
        assert _sample_value(prompt_family, bounded_labels) == 120.0
        assert _sample_value(completion_family, bounded_labels) == 45.0
        # cost_usd=0.0034 USD -> 3400 microdollars (integer counter).
        assert _sample_value(cost_family, bounded_labels) == 3400.0

        # The raw per-release model string never appears as a label value.
        assert 'model="gpt-4o-2026-01-01"' not in text
        # No prompt/completion TEXT ever reaches a label (security.md +
        # observability.md — no secrets/PII/prompt content in labels).
        assert "Paris" not in text
        assert "capital of France" not in text

    @pytest.mark.asyncio
    @pytest.mark.regression
    @pytest.mark.observability
    async def test_unknown_model_and_provider_bucket_to_other(self):
        """Bounded labels: arbitrary/unrecognized model+provider strings
        collapse to "_other" instead of becoming unbounded label values."""
        agent = _Agent(
            name="QaAgent",
            agent_id="agent-primary-002",
            result={
                "answer": "ok",
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "model": "some-bespoke-finetuned-checkpoint-v42",
                "provider": "self-hosted-triton-cluster",
                "cost_usd": 0.0001,
            },
        )
        executor = StreamingExecutor()
        _ = [e async for e in executor.execute_with_events(agent=agent, task="q")]

        text = executor.metrics_collector.export_prometheus()
        families = _families_by_name(text)

        other_labels = {"model": "_other", "provider": "_other"}
        assert _sample_value(families["kaizen_llm_prompt_tokens"], other_labels) == 7.0
        assert (
            _sample_value(families["kaizen_llm_completion_tokens"], other_labels) == 3.0
        )

        # The unbounded raw strings never became label values.
        assert "some-bespoke-finetuned-checkpoint-v42" not in text
        assert "self-hosted-triton-cluster" not in text

    @pytest.mark.asyncio
    @pytest.mark.regression
    @pytest.mark.observability
    async def test_subagent_cost_update_increments_without_double_counting(self):
        """Each subagent's cost_update emission records its OWN delta;
        summed with the primary call's usage it must equal the running
        total the event stream reports — no double counting."""
        agent = _Agent(
            name="OrchestratorAgent",
            agent_id="agent-primary-003",
            result={
                "answer": "done",
                "tokens_used": 60,  # 50 prompt + 10 completion (primary call)
                "prompt_tokens": 50,
                "completion_tokens": 10,
                "model": "claude-sonnet-4-5",
                "provider": "anthropic",
                "cost_usd": 0.001,
                "subagent_calls": [
                    {
                        "subagent_id": "sub-1",
                        "name": "ResearchAgent",
                        "tokens_used": 200,
                        "prompt_tokens": 150,
                        "completion_tokens": 50,
                        "model": "gemini-2.5-pro",
                        "provider": "google",
                        "cost_usd": 0.002,
                    }
                ],
            },
        )
        executor = StreamingExecutor()
        events = [e async for e in executor.execute_with_events(agent=agent, task="q")]

        from kaizen.execution.events import CompletedEvent

        completed = [e for e in events if isinstance(e, CompletedEvent)][0]
        # Event-stream total (unchanged behavior) — the SAME data must now
        # also reach the real Prometheus counters below.
        assert completed.total_tokens == 260  # 50+10 primary + 200 subagent
        assert completed.total_cost_usd == pytest.approx(0.003)

        text = executor.metrics_collector.export_prometheus()
        families = _families_by_name(text)
        prompt_family = families["kaizen_llm_prompt_tokens"]
        completion_family = families["kaizen_llm_completion_tokens"]
        cost_family = families["kaizen_llm_cost_microdollars"]

        # Primary (anthropic-family) + subagent (google-family) recorded
        # under DISTINCT bounded label pairs — summing them equals the
        # event stream's running total with no double counting.
        primary_labels = {"model": "anthropic", "provider": "anthropic"}
        subagent_labels = {"model": "google", "provider": "google"}

        assert _sample_value(prompt_family, primary_labels) == 50.0
        assert _sample_value(prompt_family, subagent_labels) == 150.0
        assert _sample_value(completion_family, primary_labels) == 10.0
        assert _sample_value(completion_family, subagent_labels) == 50.0
        assert _sample_value(cost_family, primary_labels) == 1000.0  # 0.001 USD
        assert _sample_value(cost_family, subagent_labels) == 2000.0  # 0.002 USD

        total_prompt = _sample_value(prompt_family, primary_labels) + _sample_value(
            prompt_family, subagent_labels
        )
        total_completion = _sample_value(
            completion_family, primary_labels
        ) + _sample_value(completion_family, subagent_labels)
        assert total_prompt + total_completion == completed.total_tokens

    @pytest.mark.regression
    @pytest.mark.observability
    def test_track_llm_usage_bounded_label_helpers_direct(self):
        """Direct unit-level pin of the bounded-label helpers (fast,
        deterministic — complements the end-to-end tests above)."""
        assert _bound_model_label("gpt-4o") == "openai"
        assert _bound_model_label("claude-sonnet-4-5") == "anthropic"
        assert _bound_model_label("gemini-2.5-pro") == "google"
        assert _bound_model_label("mistral-large-latest") == "ollama"
        assert _bound_model_label("") == "_other"
        assert _bound_model_label("something-nobody-has-heard-of") == "_other"

        assert _bound_provider_label("openai") == "openai"
        assert _bound_provider_label("OpenAI") == "openai"  # case-insensitive
        assert _bound_provider_label("") == "_other"
        assert _bound_provider_label("a-provider-that-does-not-exist") == "_other"

    @pytest.mark.regression
    @pytest.mark.observability
    def test_zero_usage_does_not_create_spurious_series(self):
        """track_llm_usage with all-zero usage MUST NOT increment counters
        (no fabricated zero-cost/zero-token series polluting the export)."""
        collector = MetricsCollector()
        collector.track_llm_usage(model="gpt-4o", provider="openai")

        text = collector.export_prometheus()
        families = _families_by_name(text)
        # The metric families exist (declared at construction) but carry
        # no samples for this (unused) label pair.
        prompt_family = families["kaizen_llm_prompt_tokens"]
        assert (
            _sample_value(prompt_family, {"model": "openai", "provider": "openai"})
            is None
        )

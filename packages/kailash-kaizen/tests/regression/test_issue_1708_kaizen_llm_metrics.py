"""Regression tests for #1708 Wave 4 (kaizen observability) + Wave 4 G1 fix.

Three gaps closed:

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

3. (Wave 4 G1) The real histogram + the 3 LLM counters above were each
   registered on a PRIVATE per-``MetricsCollector``-instance
   ``CollectorRegistry`` -- reachable only via the ``metrics_collector``
   property, with NO production ``/metrics`` endpoint ever scraping it (the
   existing kaizen FastAPI ``/metrics`` scrapes a DIFFERENT ``MetricsHook``
   registry). Fixed by registering all 4 instruments as MODULE-LEVEL lazy
   singletons on the process-wide ``prometheus_client.REGISTRY`` (mirroring
   ``kailash.core.monitoring.connection_metrics._get_acquire_wait_histogram``,
   including its dual-import duplicate-registration adopt-guard), so ANY
   co-hosted core/Nexus ``/metrics`` (``generate_latest()`` with no registry
   argument) folds them in with zero additional wiring. The ``agent_type``
   label on the duration histogram is ALSO now bounded via a thread-safe
   top-N admission bucketer (``_bound_agent_type_label`` /
   ``_TopNLabelBucketer``) -- unlike ``model``/``provider`` (bounded against
   a closed enum), ``agent_type`` has no fixed set of valid values, so the
   first N distinct values seen are admitted verbatim and every value after
   the cap collapses to ``_other``.

These tests drive the REAL emission path end-to-end (no mocking of the
metrics collector or the Prometheus registry) and assert against the real
``prometheus_client`` registry / ``export_prometheus()`` text / a direct
``prometheus_client.generate_latest(prometheus_client.REGISTRY)`` call --
per testing.md's Tier 2 "NO mocking" contract and probe-driven-verification.md
(structural/behavioral assertions, not regex-over-prose).

Because the Wave-4-G1 fix makes these instruments GLOBAL (process-wide,
shared across every ``MetricsCollector``/``StreamingExecutor`` instance),
tests exercising the DEFAULT (production) construction path use either (a)
DELTA assertions (value-after minus value-before the action, immune to
whatever other tests in this file already recorded against the same bounded
label pair) or (b) a fresh, per-test-unique ``agent_type`` string (immune to
cross-test bucket-count pollution). ``TestRealDurationHistogram`` keeps the
pre-G1-fix hermetic-registry construction (an explicit ``CollectorRegistry()``
override) since its purpose is pinning bucket SHAPE, not registry reach --
reach is proven separately by ``TestGlobalRegistryReach``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Dict

import prometheus_client
import pytest
from prometheus_client import CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families

from kaizen.execution.streaming_executor import StreamingExecutor
from kaizen.production.metrics import (
    MetricsCollector,
    _bound_agent_type_label,
    _bound_model_label,
    _bound_provider_label,
    _TopNLabelBucketer,
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


def _sample_value_or_zero(family, expected_labels: Dict[str, str]) -> float:
    """Same as ``_sample_value`` but returns 0.0 instead of None.

    Used for delta (before/after) assertions against the GLOBAL registry,
    where "never observed yet" and "observed with value 0" are the same
    starting point for a subtraction.
    """
    value = _sample_value(family, expected_labels)
    return 0.0 if value is None else value


class _EmptyFamily:
    """Stand-in for a metric family that doesn't exist YET in the global
    registry (its lazy module-level singleton hasn't been constructed by
    any ``MetricsCollector()`` call in this process yet — e.g. when a
    "before" snapshot is taken as the very first touch of the registry).
    ``.samples`` is empty so ``_sample_value`` naturally returns ``None``
    and ``_sample_value_or_zero`` naturally returns ``0.0`` — the correct
    baseline for a delta assertion."""

    samples: list = []


def _global_families() -> Dict[str, Any]:
    """Parse ``prometheus_client.generate_latest(prometheus_client.REGISTRY)``.

    This is the literal call a co-hosted core/Nexus ``/metrics`` endpoint
    makes (``generate_latest()`` with no registry argument defaults to the
    same global ``REGISTRY``) — used directly (not through
    ``MetricsCollector.export_prometheus()``) so the reach assertions prove
    the metrics are visible to ANY independent reader of the global
    registry, not just the originating collector instance.

    Returns a ``defaultdict`` so looking up a family that hasn't been
    lazily registered yet (see ``_EmptyFamily`` above) returns an empty
    family instead of raising ``KeyError`` — the correct "not observed
    yet" baseline for delta (before/after) assertions.
    """
    text = prometheus_client.generate_latest(prometheus_client.REGISTRY).decode("utf-8")
    families = _families_by_name(text)
    return defaultdict(_EmptyFamily, families)


# ===========================================================================
# Deliverable 1 — real bucketed histogram shape (replaces the count/sum fake)
# ===========================================================================


class TestRealDurationHistogram:
    """MetricsCollector's duration histogram is a REAL prometheus_client
    Histogram with explicit second-scale buckets — not a count/sum fake.

    Uses an explicit hermetic ``CollectorRegistry()`` override (the
    escape hatch ``MetricsCollector(registry=...)`` preserves for test
    isolation) so bucket-count assertions can pin EXACT values without
    coupling to the Wave-4-G1 global-registry reach fix, which is proven
    separately by ``TestGlobalRegistryReach`` below.
    """

    @pytest.mark.regression
    @pytest.mark.observability
    def test_export_contains_real_le_buckets(self):
        """The exported text has ``_bucket{...,le="..."}`` lines — the shape
        a fake count/sum-only histogram can never produce."""
        collector = MetricsCollector(registry=CollectorRegistry())
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
        collector = MetricsCollector(registry=CollectorRegistry())
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
# cost_update emission path (StreamingExecutor), not called directly.
# Delta-based: the DEFAULT (registry=None) construction now binds every
# MetricsCollector to the SHARED global registry (Wave 4 G1), so absolute
# equality would break the moment another test in this file (or another
# StreamingExecutor instance) increments the same bounded label pair.
# ===========================================================================


class TestLlmTokenCostCountersEndToEnd:
    """Feed a real completion/cost event through StreamingExecutor's real
    emission path and assert the counters' DELTA lands in the real
    (now-global) registry."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    @pytest.mark.observability
    async def test_primary_agent_cost_update_increments_bounded_counters(self):
        bounded_labels = {"model": "openai", "provider": "openai"}
        before = _global_families()
        before_prompt = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], bounded_labels
        )
        before_completion = _sample_value_or_zero(
            before["kaizen_llm_completion_tokens"], bounded_labels
        )
        before_cost = _sample_value_or_zero(
            before["kaizen_llm_cost_microdollars"], bounded_labels
        )

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

        after = _global_families()
        text = prometheus_client.generate_latest(prometheus_client.REGISTRY).decode(
            "utf-8"
        )

        # Bounded labels: "gpt-4o-2026-01-01" -> family "openai" (per
        # kaizen.providers.registry._MODEL_PREFIX_MAP), provider "openai"
        # stays "openai" (canonical provider registry entry) — never the
        # raw per-release model string as a label value.
        after_prompt = _sample_value_or_zero(
            after["kaizen_llm_prompt_tokens"], bounded_labels
        )
        after_completion = _sample_value_or_zero(
            after["kaizen_llm_completion_tokens"], bounded_labels
        )
        after_cost = _sample_value_or_zero(
            after["kaizen_llm_cost_microdollars"], bounded_labels
        )

        assert after_prompt - before_prompt == 120.0
        assert after_completion - before_completion == 45.0
        # cost_usd=0.0034 USD -> 3400 microdollars (integer counter).
        assert after_cost - before_cost == 3400.0

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
        other_labels = {"model": "_other", "provider": "_other"}
        before = _global_families()
        before_prompt = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], other_labels
        )
        before_completion = _sample_value_or_zero(
            before["kaizen_llm_completion_tokens"], other_labels
        )

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

        after = _global_families()
        text = prometheus_client.generate_latest(prometheus_client.REGISTRY).decode(
            "utf-8"
        )
        after_prompt = _sample_value_or_zero(
            after["kaizen_llm_prompt_tokens"], other_labels
        )
        after_completion = _sample_value_or_zero(
            after["kaizen_llm_completion_tokens"], other_labels
        )

        assert after_prompt - before_prompt == 7.0
        assert after_completion - before_completion == 3.0

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
        primary_labels = {"model": "anthropic", "provider": "anthropic"}
        subagent_labels = {"model": "google", "provider": "google"}

        before = _global_families()
        before_prompt_primary = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], primary_labels
        )
        before_prompt_subagent = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], subagent_labels
        )
        before_completion_primary = _sample_value_or_zero(
            before["kaizen_llm_completion_tokens"], primary_labels
        )
        before_completion_subagent = _sample_value_or_zero(
            before["kaizen_llm_completion_tokens"], subagent_labels
        )
        before_cost_primary = _sample_value_or_zero(
            before["kaizen_llm_cost_microdollars"], primary_labels
        )
        before_cost_subagent = _sample_value_or_zero(
            before["kaizen_llm_cost_microdollars"], subagent_labels
        )

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
        # also reach the real (global) Prometheus counters below.
        assert completed.total_tokens == 260  # 50+10 primary + 200 subagent
        assert completed.total_cost_usd == pytest.approx(0.003)

        after = _global_families()
        after_prompt_primary = _sample_value_or_zero(
            after["kaizen_llm_prompt_tokens"], primary_labels
        )
        after_prompt_subagent = _sample_value_or_zero(
            after["kaizen_llm_prompt_tokens"], subagent_labels
        )
        after_completion_primary = _sample_value_or_zero(
            after["kaizen_llm_completion_tokens"], primary_labels
        )
        after_completion_subagent = _sample_value_or_zero(
            after["kaizen_llm_completion_tokens"], subagent_labels
        )
        after_cost_primary = _sample_value_or_zero(
            after["kaizen_llm_cost_microdollars"], primary_labels
        )
        after_cost_subagent = _sample_value_or_zero(
            after["kaizen_llm_cost_microdollars"], subagent_labels
        )

        # Primary (anthropic-family) + subagent (google-family) recorded
        # under DISTINCT bounded label pairs — summing the DELTAS equals
        # the event stream's running total with no double counting.
        delta_prompt_primary = after_prompt_primary - before_prompt_primary
        delta_prompt_subagent = after_prompt_subagent - before_prompt_subagent
        delta_completion_primary = after_completion_primary - before_completion_primary
        delta_completion_subagent = (
            after_completion_subagent - before_completion_subagent
        )
        delta_cost_primary = after_cost_primary - before_cost_primary
        delta_cost_subagent = after_cost_subagent - before_cost_subagent

        assert delta_prompt_primary == 50.0
        assert delta_prompt_subagent == 150.0
        assert delta_completion_primary == 10.0
        assert delta_completion_subagent == 50.0
        assert delta_cost_primary == 1000.0  # 0.001 USD
        assert delta_cost_subagent == 2000.0  # 0.002 USD

        total_prompt = delta_prompt_primary + delta_prompt_subagent
        total_completion = delta_completion_primary + delta_completion_subagent
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
    def test_zero_usage_does_not_increment_counters(self):
        """track_llm_usage with all-zero usage MUST NOT increment counters
        (no fabricated zero-cost/zero-token series polluting the export) --
        asserted as a zero DELTA against the shared global registry."""
        bounded_labels = {"model": "openai", "provider": "openai"}
        before = _global_families()
        before_prompt = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], bounded_labels
        )

        collector = MetricsCollector()
        collector.track_llm_usage(model="gpt-4o", provider="openai")

        after = _global_families()
        after_prompt = _sample_value_or_zero(
            after["kaizen_llm_prompt_tokens"], bounded_labels
        )
        assert after_prompt - before_prompt == 0.0


# ===========================================================================
# Deliverable 3 (Wave 4 G1) — the 3 LLM counters + the real duration
# histogram REACH prometheus_client.generate_latest() over the GLOBAL
# registry: what a co-hosted core/Nexus /metrics scrape actually emits.
# ===========================================================================


class TestGlobalRegistryReach:
    """Prove the scrape-wiring fix: production (registry=None) construction
    binds to prometheus_client.REGISTRY, so a completely independent reader
    calling generate_latest(REGISTRY) — the same call a co-hosted /metrics
    endpoint makes — observes the metrics with NO wiring beyond
    constructing a MetricsCollector / StreamingExecutor."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    @pytest.mark.observability
    async def test_llm_counters_and_histogram_appear_in_generate_latest_over_global_registry(
        self,
    ):
        bounded_labels = {"model": "openai", "provider": "openai"}
        before = _global_families()
        before_prompt = _sample_value_or_zero(
            before["kaizen_llm_prompt_tokens"], bounded_labels
        )
        before_completion = _sample_value_or_zero(
            before["kaizen_llm_completion_tokens"], bounded_labels
        )
        before_cost = _sample_value_or_zero(
            before["kaizen_llm_cost_microdollars"], bounded_labels
        )

        # Real completion/cost event through the real emission path — no
        # LLM call, no mocking of the metrics path (`_Agent` only stands in
        # for the agent's run() return shape, per the class docstring above).
        agent = _Agent(
            name="ReachAgent",
            agent_id="agent-reach-001",
            result={
                "answer": "reach check",
                "prompt_tokens": 11,
                "completion_tokens": 4,
                "model": "gpt-4o",
                "provider": "openai",
                "cost_usd": 0.0005,
            },
        )
        executor = StreamingExecutor()
        events = [e async for e in executor.execute_with_events(agent=agent, task="q")]
        assert len(events) > 0

        # Independent call — NOT executor.metrics_collector.export_prometheus()
        # — the literal generate_latest(REGISTRY) a co-hosted /metrics
        # endpoint makes with no registry argument.
        families = _global_families()

        assert "kaizen_llm_prompt_tokens" in families
        assert "kaizen_llm_completion_tokens" in families
        assert "kaizen_llm_cost_microdollars" in families
        assert "kaizen_request_duration_seconds" in families
        assert families["kaizen_request_duration_seconds"].type == "histogram"

        after_prompt = _sample_value_or_zero(
            families["kaizen_llm_prompt_tokens"], bounded_labels
        )
        after_completion = _sample_value_or_zero(
            families["kaizen_llm_completion_tokens"], bounded_labels
        )
        after_cost = _sample_value_or_zero(
            families["kaizen_llm_cost_microdollars"], bounded_labels
        )

        assert after_prompt - before_prompt == 11.0
        assert after_completion - before_completion == 4.0
        assert after_cost - before_cost == 500.0  # 0.0005 USD -> 500 microdollars

    @pytest.mark.regression
    @pytest.mark.observability
    def test_duration_histogram_reaches_generate_latest_over_global_registry(self):
        """MetricsCollector.track_duration (the histogram's real emission
        path — RED-metric duration tracking has no cost_update/
        StreamingExecutor call site) reaches the SAME global registry.

        Uses a fresh, per-test-unique agent_type so bucket counts are
        exact (never observed before by any other test in this process).
        """
        agent_type = f"reach-{uuid.uuid4().hex[:10]}"
        collector = MetricsCollector()  # production default: global registry
        collector.track_duration(agent_type, 0.42)

        families = _global_families()
        histogram = families["kaizen_request_duration_seconds"]
        assert histogram.type == "histogram"

        # First-ever observation for this unique agent_type: buckets below
        # 0.42 are 0, buckets >= 0.5 (and +Inf) are 1.
        assert _sample_value(histogram, {"agent_type": agent_type, "le": "0.25"}) == 0.0
        assert _sample_value(histogram, {"agent_type": agent_type, "le": "0.5"}) == 1.0
        assert _sample_value(histogram, {"agent_type": agent_type, "le": "+Inf"}) == 1.0


# ===========================================================================
# Deliverable 4 (Wave 4 G1) — agent_type is BOUNDED via a top-N admission
# bucketer (no closed enum exists for it, unlike model/provider).
# ===========================================================================


class TestAgentTypeBucketing:
    """agent_type has no closed enum — the first N distinct values seen
    are admitted verbatim; every value seen after the cap collapses to
    "_other" so the EXPORTED Prometheus label cardinality stays bounded."""

    @pytest.mark.regression
    @pytest.mark.observability
    def test_bucketer_admits_first_n_then_collapses_overflow_to_other(self):
        """Direct behavioral pin of _TopNLabelBucketer — isolated instance,
        no shared/global state, fully deterministic."""
        bucketer = _TopNLabelBucketer(max_values=5)

        admitted = [bucketer.bucket(f"agent-{i}") for i in range(5)]
        assert admitted == [f"agent-{i}" for i in range(5)]
        assert bucketer.admitted_count == 5

        # >N distinct values collapse to _other.
        assert bucketer.bucket("agent-5") == "_other"
        assert bucketer.bucket("agent-6") == "_other"
        assert bucketer.bucket("agent-999") == "_other"
        # Overflow never grows the admitted set.
        assert bucketer.admitted_count == 5

        # Already-admitted values keep resolving verbatim (not evicted by
        # the overflow attempts above).
        assert bucketer.bucket("agent-0") == "agent-0"
        assert bucketer.bucket("agent-4") == "agent-4"

    @pytest.mark.regression
    @pytest.mark.observability
    def test_bucketer_bounds_empty_and_whitespace_to_other(self):
        bucketer = _TopNLabelBucketer(max_values=5)
        assert bucketer.bucket("") == "_other"
        assert bucketer.bucket("   ") == "_other"
        # Neither counts against the admission cap.
        assert bucketer.admitted_count == 0

    @pytest.mark.regression
    @pytest.mark.observability
    def test_module_level_bound_agent_type_label_helper_routes_to_bucketer(
        self, monkeypatch
    ):
        """_bound_agent_type_label is the production entry point every
        Histogram.observe() call routes through — pin its overflow
        behavior with a monkeypatched small-cap bucketer so the assertion
        is deterministic regardless of how many OTHER agent_type values
        this process has already admitted via the real shared bucketer."""
        import kaizen.production.metrics as metrics_module

        fresh_bucketer = _TopNLabelBucketer(max_values=2)
        monkeypatch.setattr(metrics_module, "_AGENT_TYPE_BUCKETER", fresh_bucketer)

        assert metrics_module._bound_agent_type_label("alpha") == "alpha"
        assert metrics_module._bound_agent_type_label("beta") == "beta"
        # Cap reached -- overflow collapses.
        assert metrics_module._bound_agent_type_label("gamma") == "_other"
        assert metrics_module._bound_agent_type_label("delta") == "_other"

    @pytest.mark.regression
    @pytest.mark.observability
    def test_overflow_bounds_the_real_exported_histogram_label(self, monkeypatch):
        """End-to-end: overflow agent_type values collapse to "_other" on
        the REAL exported Prometheus histogram label -- not just the
        bucketer helper in isolation."""
        import kaizen.production.metrics as metrics_module

        fresh_bucketer = _TopNLabelBucketer(max_values=2)
        monkeypatch.setattr(metrics_module, "_AGENT_TYPE_BUCKETER", fresh_bucketer)

        suffix = uuid.uuid4().hex[:8]
        admitted_1 = f"bound-alpha-{suffix}"
        admitted_2 = f"bound-beta-{suffix}"
        overflow_1 = f"bound-gamma-{suffix}"
        overflow_2 = f"bound-delta-{suffix}"

        collector = metrics_module.MetricsCollector()  # global registry, default
        collector.track_duration(admitted_1, 0.1)
        collector.track_duration(admitted_2, 0.2)
        collector.track_duration(overflow_1, 0.3)  # -> _other
        collector.track_duration(overflow_2, 0.4)  # -> _other

        families = _global_families()
        histogram = families["kaizen_request_duration_seconds"]

        assert _sample_value(histogram, {"agent_type": admitted_1, "le": "+Inf"}) == 1.0
        assert _sample_value(histogram, {"agent_type": admitted_2, "le": "+Inf"}) == 1.0
        # The overflow agent_type strings NEVER became label values --
        # their observations landed under "_other" instead.
        assert (
            _sample_value(histogram, {"agent_type": overflow_1, "le": "+Inf"}) is None
        )
        assert (
            _sample_value(histogram, {"agent_type": overflow_2, "le": "+Inf"}) is None
        )
        assert f'agent_type="{overflow_1}"' not in prometheus_client.generate_latest(
            prometheus_client.REGISTRY
        ).decode("utf-8")
        assert f'agent_type="{overflow_2}"' not in prometheus_client.generate_latest(
            prometheus_client.REGISTRY
        ).decode("utf-8")

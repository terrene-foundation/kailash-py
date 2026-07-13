"""Metrics collection for production monitoring.

Provides RED metrics (Rate, Errors, Duration) and custom business metrics
with Prometheus integration.

The request-duration histogram is a REAL ``prometheus_client.Histogram``
with explicit second-scale ``le=`` buckets (matching the pattern already
proven in ``kaizen.core.autonomy.hooks.builtin.metrics_hook.MetricsHook``) —
it replaces an earlier count/sum-only fake that could never back a
``histogram_quantile()`` p95/p99 query (#1708 Wave 4).

LLM token + cost counters (``kaizen_llm_prompt_tokens_total`` /
``kaizen_llm_completion_tokens_total`` / ``kaizen_llm_cost_microdollars_total``)
are also REAL Prometheus counters with BOUNDED ``model``/``provider`` labels —
unrecognized values collapse to ``_other`` (never a raw caller string, never
prompt/completion text) to keep cardinality bounded (#1708 Wave 4).
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from prometheus_client import CollectorRegistry
from prometheus_client import Counter as PromCounter
from prometheus_client import Histogram as PromHistogram
from prometheus_client import generate_latest

from kaizen.providers.registry import _MODEL_PREFIX_MAP, PROVIDERS

# 1 USD = 1,000,000 microdollars (cross-module convention — see
# kaizen.cost.tracker._MICRODOLLARS_PER_USD / kaizen.providers.cost) — kept as
# an integer counter so Prometheus never accumulates float-precision drift.
_MICRODOLLARS_PER_USD = 1_000_000

# Bounded label sentinel — any caller-supplied model/provider string that
# doesn't match a known, finite set collapses here instead of becoming an
# unbounded Prometheus label value.
_OTHER_LABEL = "_other"

# Explicit second-scale buckets for LLM/agent request duration (seconds).
# Default prometheus_client buckets top out at 10s with coarse low-end
# granularity; agent calls span sub-100ms tool invocations through
# multi-minute autonomous cycles, so the boundaries are widened to 60s.
_DEFAULT_DURATION_BUCKETS: Sequence[float] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
    30.0,
    60.0,
)

# Canonical bounded provider enum — reuses the SAME registry the provider
# resolver uses (kaizen.providers.registry.PROVIDERS) so this module carries
# no parallel provider-name list.
_BOUNDED_PROVIDERS = frozenset(PROVIDERS.keys())


def _bound_provider_label(provider: str) -> str:
    """Bound the ``provider`` label to the canonical provider registry.

    Unknown/arbitrary provider strings collapse to ``_other`` to keep
    Prometheus label cardinality bounded (`observability.md` bucketing
    discipline) — never pass a raw caller-supplied string through as a
    label value.
    """
    if not provider:
        return _OTHER_LABEL
    normalized = provider.strip().lower()
    return normalized if normalized in _BOUNDED_PROVIDERS else _OTHER_LABEL


def _bound_model_label(model: str) -> str:
    """Bound the ``model`` label to a known model-family prefix.

    Reuses the canonical model-prefix -> provider-family table from
    ``kaizen.providers.registry`` (the same structural mapping the provider
    resolver uses) so this module carries no parallel model-family list.
    Arbitrary/unknown model strings — and raw per-release model identifiers
    that would otherwise be unbounded cardinality — collapse to ``_other``.
    """
    if not model:
        return _OTHER_LABEL
    normalized = model.strip().lower()
    for prefixes, family in _MODEL_PREFIX_MAP:
        if normalized.startswith(prefixes):
            return family
    return _OTHER_LABEL


@dataclass
class MetricValue:
    """Container for a metric value with metadata."""

    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._lock = threading.Lock()
        self._values: Dict[str, float] = defaultdict(float)

    def inc(self, labels: Optional[Dict[str, str]] = None, amount: float = 1.0):
        """Increment counter."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] += amount

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class Histogram:
    """Thread-safe REAL Prometheus histogram for tracking distributions.

    Wraps ``prometheus_client.Histogram`` with explicit second-scale
    ``le=`` bucket boundaries — a real ``_bucket``/``_sum``/``_count``
    export that ``histogram_quantile()`` can compute p95/p99 over. This
    replaces the earlier fake implementation that only ever emitted
    ``_count``/``_sum`` (no buckets), which cannot back any percentile
    query (#1708 Wave 4 — see module docstring).

    Labels are BOUNDED to ``agent_type`` at the Prometheus-export layer to
    keep cardinality bounded. Any additional caller-supplied labels are
    retained ONLY in an in-memory, per-process sample list so
    ``get_stats()`` can still report min/max/avg (Prometheus histograms do
    not track those natively) — they are never exported as Prometheus
    label values.
    """

    def __init__(
        self,
        name: str,
        description: str,
        buckets: Sequence[float] = _DEFAULT_DURATION_BUCKETS,
        registry: Optional[CollectorRegistry] = None,
    ):
        self.name = name
        self.description = description
        self._registry = registry if registry is not None else CollectorRegistry()
        self._histogram = PromHistogram(
            name,
            description,
            ["agent_type"],
            registry=self._registry,
            buckets=tuple(buckets),
        )
        self._lock = threading.Lock()
        # Bounded per-label-key raw samples, retained ONLY for the in-memory
        # min/max/avg stats surface (get_stats) — never exported to
        # Prometheus (that surface is the real bucketed histogram above).
        self._observations: Dict[str, List[float]] = defaultdict(list)

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Record an observation on the real histogram + in-memory stats."""
        labels = labels or {}
        agent_type = labels.get("agent_type", "")
        self._histogram.labels(agent_type=agent_type).observe(value)

        key = self._label_key(labels)
        with self._lock:
            self._observations[key].append(value)

    def get_stats(self, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get in-memory statistics (count/sum/min/max/avg) for observations."""
        key = self._label_key(labels or {})
        with self._lock:
            values = list(self._observations.get(key, []))
            if not values:
                return {"count": 0, "sum": 0.0}

            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }

    def export_prometheus_text(self) -> str:
        """Export the REAL bucketed histogram in Prometheus text format.

        Includes ``_bucket{le=...}``, ``_sum``, and ``_count`` series —
        the shape ``histogram_quantile()`` requires.
        """
        return generate_latest(self._registry).decode("utf-8")

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class Gauge:
    """Thread-safe gauge metric for values that go up and down."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._lock = threading.Lock()
        self._values: Dict[str, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Set gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class MetricsCollector:
    """Production metrics collector with Prometheus support.

    Implements RED metrics (Rate, Errors, Duration) and supports
    custom business metrics.

    Example:
        >>> metrics = MetricsCollector()
        >>> metrics.track_request("qa_agent", "success")
        >>> metrics.track_duration("qa_agent", 0.5)
        >>> stats = metrics.get_duration_stats("qa_agent")
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics collector.

        Args:
            registry: Prometheus registry backing the REAL histogram + LLM
                token/cost counters (creates a new one if None — matches
                the ``MetricsHook`` convention in
                ``kaizen.core.autonomy.hooks.builtin.metrics_hook``).
        """
        # Shared registry for every REAL prometheus_client metric this
        # collector owns (the duration histogram + the LLM token/cost
        # counters). Exposed publicly so callers can scrape/inspect it
        # directly, same as MetricsHook.registry.
        self.registry = registry if registry is not None else CollectorRegistry()

        # RED metrics
        self._request_counter = Counter(
            "kaizen_requests_total", "Total number of requests"
        )
        self._error_counter = Counter("kaizen_errors_total", "Total number of errors")
        self._duration_histogram = Histogram(
            "kaizen_request_duration_seconds",
            "Request duration in seconds",
            registry=self.registry,
        )

        # LLM token + cost counters (#1708 Wave 4). Labels are BOUNDED —
        # see _bound_model_label / _bound_provider_label — never a raw
        # caller-supplied string, never prompt/completion text.
        self._llm_prompt_tokens_counter = PromCounter(
            "kaizen_llm_prompt_tokens_total",
            "Total LLM prompt (input) tokens consumed, by bounded model "
            "family and provider",
            ["model", "provider"],
            registry=self.registry,
        )
        self._llm_completion_tokens_counter = PromCounter(
            "kaizen_llm_completion_tokens_total",
            "Total LLM completion (output) tokens consumed, by bounded "
            "model family and provider",
            ["model", "provider"],
            registry=self.registry,
        )
        self._llm_cost_microdollars_counter = PromCounter(
            "kaizen_llm_cost_microdollars_total",
            "Total LLM spend in microdollars (1 USD = 1,000,000 "
            "microdollars), by bounded model family and provider",
            ["model", "provider"],
            registry=self.registry,
        )

        # Custom metrics
        self._gauges: Dict[str, Gauge] = {}
        self._counters: Dict[str, Counter] = {}

    def track_llm_usage(
        self,
        model: str = "",
        provider: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record LLM token usage and cost for a completed call.

        This is the counterpart to the ``cost_update`` execution event
        (``kaizen.execution.events.CostUpdateEvent`` /
        ``kaizen.execution.streaming_executor.StreamingExecutor``) — call
        it at the same point a ``cost_update`` event is emitted so token +
        cost visibility reaches the real Prometheus registry, not just the
        event stream (#1708 Wave 4).

        Args:
            model: Model name for this call. Bounded to a known model
                family prefix (e.g. "gpt-4o" -> "openai"); unrecognized
                values collapse to "_other".
            provider: Provider name for this call. Bounded to the
                canonical provider registry; unrecognized values collapse
                to "_other".
            prompt_tokens: Prompt (input) tokens consumed by this call.
            completion_tokens: Completion (output) tokens consumed by
                this call.
            cost_usd: Cost of this call in USD. Converted to an integer
                microdollar count (1 USD = 1,000,000 microdollars) so the
                Prometheus counter never accumulates float-precision
                drift.
        """
        bounded_model = _bound_model_label(model)
        bounded_provider = _bound_provider_label(provider)

        if prompt_tokens:
            self._llm_prompt_tokens_counter.labels(
                model=bounded_model, provider=bounded_provider
            ).inc(prompt_tokens)

        if completion_tokens:
            self._llm_completion_tokens_counter.labels(
                model=bounded_model, provider=bounded_provider
            ).inc(completion_tokens)

        if cost_usd:
            microdollars = round(cost_usd * _MICRODOLLARS_PER_USD)
            if microdollars:
                self._llm_cost_microdollars_counter.labels(
                    model=bounded_model, provider=bounded_provider
                ).inc(microdollars)

    def track_request(
        self, agent_type: str, status: str, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track a request.

        Args:
            agent_type: Type of agent (e.g., "qa_agent")
            status: Request status (e.g., "success", "error")
            labels: Additional labels for the metric
        """
        metric_labels = {"agent_type": agent_type, "status": status}
        if labels:
            metric_labels.update(labels)

        self._request_counter.inc(labels=metric_labels)

    def track_error(
        self, agent_type: str, error_type: str, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track an error.

        Args:
            agent_type: Type of agent
            error_type: Type of error (e.g., "timeout", "validation")
            labels: Additional labels
        """
        metric_labels = {"agent_type": agent_type, "error_type": error_type}
        if labels:
            metric_labels.update(labels)

        self._error_counter.inc(labels=metric_labels)

    def track_duration(
        self, agent_type: str, duration: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track request duration.

        Args:
            agent_type: Type of agent
            duration: Duration in seconds
            labels: Additional labels
        """
        metric_labels = {"agent_type": agent_type}
        if labels:
            metric_labels.update(labels)

        self._duration_histogram.observe(duration, labels=metric_labels)

    def get_request_count(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """Get request count.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Total request count (sum across all statuses if no status specified)
        """
        # If no specific labels, sum all requests for this agent type
        if labels is None:
            total = 0.0
            for label_key, value in self._request_counter._values.items():
                if f"agent_type={agent_type}" in label_key:
                    total += value
            return total

        # Otherwise, get specific label combination
        metric_labels = {"agent_type": agent_type}
        metric_labels.update(labels)
        return self._request_counter.get(labels=metric_labels)

    def get_error_count(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """Get error count.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Total error count (sum across all error types if no type specified)
        """
        # If no specific labels, sum all errors for this agent type
        if labels is None:
            total = 0.0
            for label_key, value in self._error_counter._values.items():
                if f"agent_type={agent_type}" in label_key:
                    total += value
            return total

        # Otherwise, get specific label combination
        metric_labels = {"agent_type": agent_type}
        metric_labels.update(labels)
        return self._error_counter.get(labels=metric_labels)

    def get_duration_stats(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """Get duration statistics.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Dict with count, sum, min, max, avg
        """
        metric_labels = {"agent_type": agent_type}
        if labels:
            metric_labels.update(labels)

        return self._duration_histogram.get_stats(labels=metric_labels)

    def define_gauge(self, name: str, description: str) -> None:
        """Define a custom gauge metric.

        Args:
            name: Metric name
            description: Metric description
        """
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, description)

    def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Set gauge value.

        Args:
            name: Metric name
            value: Metric value
            labels: Additional labels
        """
        if name not in self._gauges:
            raise ValueError(f"Gauge {name} not defined. Call define_gauge() first.")

        self._gauges[name].set(value, labels=labels)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value.

        Args:
            name: Metric name
            labels: Additional labels

        Returns:
            Current gauge value
        """
        if name not in self._gauges:
            raise ValueError(f"Gauge {name} not defined")

        return self._gauges[name].get(labels=labels)

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format.

        The request-duration histogram and the LLM token/cost counters are
        REAL ``prometheus_client`` metrics registered on ``self.registry``,
        so this section is produced by ``generate_latest()`` — the same
        exposition path Prometheus/OTel scrapers already trust — including
        real ``_bucket{le=...}`` lines for the histogram (#1708 Wave 4).
        The hand-rolled request/error counters and custom gauges (not part
        of this fix) are appended after it unchanged.

        Returns:
            Metrics in Prometheus exposition format
        """
        lines = [generate_latest(self.registry).decode("utf-8").rstrip("\n")]

        # Export request counter
        lines.append(
            f"# HELP {self._request_counter.name} {self._request_counter.description}"
        )
        lines.append(f"# TYPE {self._request_counter.name} counter")
        for labels_key, value in self._request_counter._values.items():
            if labels_key:
                lines.append(f"{self._request_counter.name}{{{labels_key}}} {value}")
            else:
                lines.append(f"{self._request_counter.name} {value}")

        # Export error counter
        lines.append(
            f"# HELP {self._error_counter.name} {self._error_counter.description}"
        )
        lines.append(f"# TYPE {self._error_counter.name} counter")
        for labels_key, value in self._error_counter._values.items():
            if labels_key:
                lines.append(f"{self._error_counter.name}{{{labels_key}}} {value}")
            else:
                lines.append(f"{self._error_counter.name} {value}")

        # Export gauges
        for gauge in self._gauges.values():
            lines.append(f"# HELP {gauge.name} {gauge.description}")
            lines.append(f"# TYPE {gauge.name} gauge")
            for labels_key, value in gauge._values.items():
                if labels_key:
                    lines.append(f"{gauge.name}{{{labels_key}}} {value}")
                else:
                    lines.append(f"{gauge.name} {value}")

        return "\n".join(lines) + "\n"

    @property
    def request_rate(self) -> Counter:
        """Get request rate counter."""
        return self._request_counter

    @property
    def error_rate(self) -> Counter:
        """Get error rate counter."""
        return self._error_counter

    @property
    def request_duration(self) -> Histogram:
        """Get request duration histogram."""
        return self._duration_histogram

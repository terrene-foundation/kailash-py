"""Regression: a LABELLED histogram's percentile series must be scrapeable.

``MetricsCollector.export()`` built each percentile line by appending the
suffix to the COMPOSED key from ``_metric_key`` -- which already carries the
label block -- emitting::

    test_histogram{latency="test"}_p50 110.0

In Prometheus exposition format the suffix belongs to the metric NAME, before
the labels, so the reference parser rejects that line with
``Invalid value: '_p50'``. Every labelled histogram's p50/p95/p99 was
therefore unscrapeable, while:

* counters and gauges were unaffected -- they append no suffix, so their
  composed key is already well-formed; and
* UNLABELLED histograms were unaffected -- with no label block, appending to
  the key and appending to the name are the same string.

That combination is why it stayed hidden: the only broken case is
"histogram AND labels", and a substring check for ``test_histogram`` passes
on the malformed line because the name is still a prefix of it.

The oracle here is ``prometheus_client``'s own parser, NOT a substring check.
A substring assertion would pass on a line that still fails to scrape --
which is exactly how the defect survived. Asserting the text PARSES, and that
the parsed family carries the right name and labels, is the only assertion
that discriminates.
"""

import pytest
from kaizen.core.autonomy.observability.metrics import MetricsCollector
from prometheus_client.parser import text_string_to_metric_families

pytestmark = pytest.mark.regression


def _parse(text: str):
    """Parse exposition text, returning {name: [labelsets]}.

    Raises whatever the parser raises -- a malformed line must surface as a
    failure here, not be swallowed into an empty result.
    """
    return {
        family.name: [sample.labels for sample in family.samples]
        for family in text_string_to_metric_families(text + "\n")
    }


@pytest.mark.asyncio
async def test_labelled_histogram_percentiles_are_scrapeable():
    """The defect case: histogram + labels."""
    collector = MetricsCollector()
    for value in (100.0, 110.0, 120.0):
        collector.histogram("latency_ms", value, {"route": "/execute"})

    text = await collector.export()
    families = _parse(text)

    for quantile in ("p50", "p95", "p99"):
        name = f"latency_ms_{quantile}"
        assert name in families, (
            f"{name} is absent from the parsed export; the suffix must attach "
            f"to the metric NAME, before the label block: {text!r}"
        )
        assert families[name] == [{"route": "/execute"}], (
            f"{name} lost or mangled its labels on the way to the wire: "
            f"{families[name]!r}"
        )


@pytest.mark.asyncio
async def test_unlabelled_histogram_percentiles_still_scrapeable():
    """The path that already worked and must not regress.

    With no labels there is no block to misplace, so this case passed both
    before and after the fix. It is here so a future change that reworks key
    composition cannot fix the labelled case by breaking this one.
    """
    collector = MetricsCollector()
    for value in (100.0, 110.0, 120.0):
        collector.histogram("latency_ms", value)

    families = _parse(await collector.export())

    for quantile in ("p50", "p95", "p99"):
        name = f"latency_ms_{quantile}"
        assert name in families, f"{name} absent from the unlabelled export"
        assert families[name] == [
            {}
        ], f"{name} gained labels it was never given: {families[name]!r}"


@pytest.mark.asyncio
async def test_labelled_counters_and_gauges_remain_scrapeable():
    """Counters and gauges share the key builder; changing the histogram path
    must not disturb them. They were correct before the fix precisely because
    they append no suffix."""
    collector = MetricsCollector()
    collector.counter("requests_total", 5.0, {"route": "/execute"})
    collector.gauge("inflight", 3.0, {"route": "/execute"})

    families = _parse(await collector.export())

    assert families.get("requests_total") == [{"route": "/execute"}], families
    assert families.get("inflight") == [{"route": "/execute"}], families


@pytest.mark.asyncio
async def test_whole_export_parses_with_every_metric_type_labelled():
    """End-to-end: one export carrying all three types, all labelled.

    A per-type test can pass while the concatenated document does not, since
    the parser reads the text as a whole.
    """
    collector = MetricsCollector()
    collector.counter("requests_total", 5.0, {"route": "/execute"})
    collector.gauge("inflight", 3.0, {"route": "/execute"})
    for value in (100.0, 110.0, 120.0):
        collector.histogram("latency_ms", value, {"route": "/execute"})

    families = _parse(await collector.export())

    assert {
        "requests_total",
        "inflight",
        "latency_ms_p50",
        "latency_ms_p95",
        "latency_ms_p99",
    } <= set(families), f"missing families in a mixed export: {sorted(families)}"

"""Regression: top-N label bucketers bound their internal counts working set.

Issue #1708 G1 (LOW, from the Round-2 code-review): the metric *label*
cardinality is bounded to ``top_n + "_other"``, but the internal ``_counts``
dict admitted one entry per distinct name for process lifetime -- an
unbounded-memory vector under the exact adversarial input the label bound
targets (``name=f"etl-{customer_id}"`` per request). Both bucketers now cap the
tracked working set at ``max(top_n * 10, top_n + 1000)``; a brand-new name past
the cap buckets to ``_other`` without being tracked.

These tests assert BOTH invariants survive a flood: (1) internal memory stays
bounded, (2) the metric label bound still holds.
"""

import pytest

from kailash.runtime.metrics import _WorkflowNameBucketer
from kailash.observability.ml import _TenantBucketer


@pytest.mark.regression
def test_workflow_name_bucketer_counts_dict_is_bounded_under_flood():
    b = _WorkflowNameBucketer(top_n=5)
    cap = b._max_tracked
    labels = set()
    # Flood with 50x the working-set cap of distinct never-repeated names.
    for i in range(cap * 50):
        labels.add(b.bucket(f"wf-{i}"))
    # (1) internal memory bounded -- never exceeds the working-set cap.
    assert len(b._counts) <= cap
    # (2) metric label cardinality still bounded to top_n admitted + "_other".
    assert len(labels) <= b._top_n + 1
    assert "_other" in labels


@pytest.mark.regression
def test_tenant_bucketer_counts_dict_is_bounded_under_flood():
    b = _TenantBucketer(top_n=5)
    cap = b._max_tracked
    labels = set()
    for i in range(cap * 50):
        labels.add(b.bucket(f"tenant-{i}"))
    assert len(b._counts) <= cap
    assert len(labels) <= b._top_n + 1
    assert "_other" in labels


@pytest.mark.regression
def test_bucketer_still_admits_top_n_then_buckets_overflow():
    """The memory bound must not change the small-N admit/overflow behaviour."""
    b = _WorkflowNameBucketer(top_n=2)
    assert b.bucket("etl-a") == "etl-a"
    assert b.bucket("etl-b") == "etl-b"
    # third distinct name overflows -> _other (admitted set already full at 2)
    assert b.bucket("etl-c") == "_other"
    # already-admitted names keep returning verbatim
    assert b.bucket("etl-a") == "etl-a"

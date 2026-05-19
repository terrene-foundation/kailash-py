"""Regression: latent ``kaizen.nodes.rag.federated`` crashes on malformed input.

F8 shard B5 surfaced nine crash sites across the three federated RAG node
classes via behavioral coverage — six in ``run()`` paths, three in the
``FederatedRAGNode`` ``_create_workflow()`` codegen templates. Per the
B1-B4 two-path lesson, both the ``run()`` paths and the ``code=`` codegen
templates were grepped for each pattern and fixed in the same shard.

Defect 1 — EdgeRAGNode.run() None-query crash.
  ``run()`` did ``kwargs.get("query", "")`` then ``query.encode()`` for the
  cache key. The ``""`` default applies ONLY to a MISSING key; an explicit
  ``query=None`` returned ``None`` and ``.encode()`` raised AttributeError.
  Fix: ``kwargs.get("query") or ""``.

Defect 2 — EdgeRAGNode._edge_optimized_retrieval None-content crash.
  ``doc.get("content", "").lower()`` — a present-but-None content bypassed
  the "" default and ``.lower()`` raised AttributeError.
  Fix: ``(doc.get("content") or "").lower()``.

Defect 3 — EdgeRAGNode._edge_optimized_retrieval non-dict element crash.
  The retrieval loop iterated ``local_data`` calling ``doc.get(...)``. A
  non-dict element (local_data is arbitrary user input) raised AttributeError
  ('str' object has no attribute 'get').
  Fix: ``isinstance(doc, dict)`` skip.

Defect 4 — EdgeRAGNode._generate_edge_response None-content slice crash.
  The 'small'/'medium' model branches did
  ``results[0]["document"].get("content", "")[:100]`` — a present-but-None
  content bypassed the default and ``None[:100]`` raised TypeError.
  Fix: ``(... .get("content") or "")[:N]``.

Defect 5 — CrossSiloRAGNode.run() None-query crash.
  ``run()`` did ``kwargs.get("query", "")`` then the audit trail hashed
  ``query.encode()``. An explicit ``query=None`` raised AttributeError.
  Fix: ``kwargs.get("query") or ""``.

Defect 6 — CrossSiloRAGNode.run() None-access_permissions crash.
  ``run()`` did ``kwargs.get("access_permissions", [])`` then
  ``_validate_cross_silo_access`` did ``all(perm in permissions ...)``. An
  explicit ``access_permissions=None`` raised TypeError ('NoneType' is not
  iterable).
  Fix: ``kwargs.get("access_permissions") or []``.

Defect 7 — result_aggregator codegen None-content crash.
  The aggregator's weighted_average grouping did ``result["content"][:50]``
  as a dict key. A present-but-None content raised TypeError ('NoneType' is
  not subscriptable).
  Fix: coerce a None content to "" at the result-intake loop.

Defect 8 — result_aggregator codegen non-dict result-element crash.
  The aggregator's intake loop did ``result.copy()`` on every element of a
  node's results list. A non-dict element (results are peer-supplied data)
  raised AttributeError ('str' object has no attribute 'copy').
  Fix: ``isinstance(result, dict)`` skip at the intake loop.

Defect 9 — cache_coordinator codegen None-content crash.
  ``hashlib.sha256(result["content"].encode())`` raised AttributeError on a
  present-but-None content.
  Fix: ``(result.get("content") or "").encode()``.

Defects 1-6 are ``run()``-path defects; defects 7-9 are
``_create_workflow()`` codegen-template defects.

All tests are behavioral — they call ``run()`` or exec the real rendered
codegen template against malformed input and assert success / typed outputs,
not source-grep.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime

import pytest

from kaizen.nodes.rag.federated import CrossSiloRAGNode, EdgeRAGNode, FederatedRAGNode

pytestmark = pytest.mark.regression


_EDGE_KEYS = {"results", "resource_usage", "sync_recommendations", "edge_metadata"}
_CROSS_SILO_DENIED_KEY = "error"


def _exec_codegen_fn(node_id, fn_name, extra_ns=None):
    """exec a FederatedRAGNode codegen template and return its function.

    The codegen functions build a local ``result`` dict but never ``return``
    it; this helper appends ``return result`` so the function logic is
    behaviorally observable. The code= string is read off the built workflow
    via ``get_node(id).code`` — ``WorkflowBuilder.build()`` consumes the
    ``code`` config kwarg into the PythonCodeNode's ``.code`` attribute.
    """
    workflow = FederatedRAGNode()._create_workflow()  # type: ignore[attr-defined]
    code = workflow.get_node(node_id).code
    namespace: dict = {
        "datetime": datetime,
        "hashlib": hashlib,
        "random": random,
    }
    if extra_ns:
        namespace.update(extra_ns)
    exec(code + "\n    return result\n", namespace)
    return namespace[fn_name]


# --------------------------------------------------------------------------
# Defect 1 — EdgeRAGNode.run() None query
# --------------------------------------------------------------------------


def test_issue_f8b5_edge_none_query_does_not_crash():
    """Defect 1: ``query=None`` must not raise AttributeError.

    Pre-fix ``query.encode()`` for the cache key raised 'NoneType' object has
    no attribute 'encode' — the kwargs.get default applies only to MISSING
    keys.
    """
    result = EdgeRAGNode().run(query=None, local_data=[{"content": "x"}])
    assert set(result.keys()) == _EDGE_KEYS


def test_issue_f8b5_edge_missing_query_kwarg_does_not_crash():
    """Defect 1 sibling: an absent query kwarg defaults to '' cleanly."""
    result = EdgeRAGNode().run(local_data=[{"content": "x"}])
    assert set(result.keys()) == _EDGE_KEYS


# --------------------------------------------------------------------------
# Defect 2 — EdgeRAGNode._edge_optimized_retrieval None content
# --------------------------------------------------------------------------


def test_issue_f8b5_edge_none_content_does_not_crash():
    """Defect 2: a present-but-None document content must not crash retrieval.

    Pre-fix ``doc.get("content", "").lower()`` raised 'NoneType' object has no
    attribute 'lower'.
    """
    result = EdgeRAGNode().run(query="q", local_data=[{"content": None}])
    assert set(result.keys()) == _EDGE_KEYS


# --------------------------------------------------------------------------
# Defect 3 — EdgeRAGNode._edge_optimized_retrieval non-dict element
# --------------------------------------------------------------------------


def test_issue_f8b5_edge_non_dict_document_element_is_skipped():
    """Defect 3: a non-dict local_data element must be skipped, not crashed on.

    Pre-fix ``doc.get(...)`` raised 'str' object has no attribute 'get'.
    local_data is arbitrary user input.
    """
    result = EdgeRAGNode().run(
        query="valve", local_data=["bare-string", {"content": "valve log"}, 99]
    )
    assert result["edge_metadata"]["local_data_size"] == 3


def test_issue_f8b5_edge_all_non_dict_documents_does_not_crash():
    """Defect 3 edge: an all-non-dict local_data yields a zero-score result."""
    result = EdgeRAGNode().run(query="q", local_data=[1, 2, 3])
    assert result["results"][0]["score"] == 0


# --------------------------------------------------------------------------
# Defect 4 — EdgeRAGNode._generate_edge_response None-content slice
# --------------------------------------------------------------------------


def test_issue_f8b5_edge_small_model_none_content_does_not_crash():
    """Defect 4: a present-but-None content must not crash the 'small' model's
    ``[:100]`` content slice.

    Pre-fix this raised TypeError ('NoneType' object is not subscriptable).
    The retrieval scoring matches the second doc; the top result's document
    has the None content the response builder then slices.
    """
    result = EdgeRAGNode(model_size="small").run(
        query="sensor data",
        local_data=[{"content": None}, {"content": "sensor data reading"}],
    )
    assert set(result.keys()) == _EDGE_KEYS


def test_issue_f8b5_edge_medium_model_none_content_does_not_crash():
    """Defect 4 sibling: the 'medium' model's ``[:200]`` slice list
    comprehension must also survive a present-but-None content."""
    result = EdgeRAGNode(model_size="medium").run(
        query="sensor data",
        local_data=[{"content": None}, {"content": "sensor data reading"}],
    )
    assert set(result.keys()) == _EDGE_KEYS


# --------------------------------------------------------------------------
# Defect 5 — CrossSiloRAGNode.run() None query
# --------------------------------------------------------------------------


def test_issue_f8b5_cross_silo_none_query_does_not_crash():
    """Defect 5: ``query=None`` must not crash the audit-trail query.encode().

    Pre-fix the audit hash ``hashlib.sha256(query.encode())`` raised
    'NoneType' object has no attribute 'encode'.
    """
    result = CrossSiloRAGNode(silos=["org_a"]).run(
        query=None,
        requester_org="org_a",
        access_permissions=["read_aggregated"],
    )
    # Access is granted (org_a in federation, adequate permissions) — the
    # structured success result is returned, audit hash computed over "".
    assert "silo_results" in result


# --------------------------------------------------------------------------
# Defect 6 — CrossSiloRAGNode.run() None access_permissions
# --------------------------------------------------------------------------


def test_issue_f8b5_cross_silo_none_access_permissions_does_not_crash():
    """Defect 6: ``access_permissions=None`` must not crash ``perm in None``.

    Pre-fix ``_validate_cross_silo_access`` did
    ``all(perm in permissions for perm in required)`` — a None permissions
    raised TypeError (argument of type 'NoneType' is not iterable).
    """
    result = CrossSiloRAGNode(silos=["org_a"]).run(
        query="q", requester_org="org_a", access_permissions=None
    )
    # None coerces to [] — the required read_aggregated permission is absent,
    # so access is correctly denied (not crashed).
    assert result[_CROSS_SILO_DENIED_KEY] == "Access denied"
    assert result["reason"] == "Insufficient permissions"


def test_issue_f8b5_cross_silo_missing_access_permissions_kwarg_does_not_crash():
    """Defect 6 sibling: an absent access_permissions kwarg defaults to []."""
    result = CrossSiloRAGNode(silos=["org_a"]).run(query="q", requester_org="org_a")
    assert result[_CROSS_SILO_DENIED_KEY] == "Access denied"


# --------------------------------------------------------------------------
# Defect 7 — result_aggregator codegen None content
# --------------------------------------------------------------------------


def _aggregator_responses(*, none_content=False, non_dict_result=False):
    """Build a federated_responses dict for the result_aggregator codegen."""
    h_a: list = [{"content": "protocol A", "score": 0.9}]
    if none_content:
        h_a = [{"content": None, "score": 0.9}]
    if non_dict_result:
        h_a = ["bare-string", {"content": "protocol A", "score": 0.9}]
    return {
        "query_id": "q1",
        "node_responses": [
            {
                "node_id": "hospital_a",
                "results": h_a,
                "metadata": {
                    "response_time": 1.0,
                    "result_count": len(h_a),
                    "cache_hit": False,
                },
            },
            {
                "node_id": "hospital_b",
                "results": [{"content": "protocol B", "score": 0.8}],
                "metadata": {
                    "response_time": 1.5,
                    "result_count": 1,
                    "cache_hit": False,
                },
            },
        ],
        "failed_nodes": [],
        "statistics": {
            "total_nodes": 2,
            "successful_nodes": 2,
            "failed_nodes": 0,
            "minimum_requirement_met": True,
            "avg_response_time": 1.25,
        },
    }


def test_issue_f8b5_aggregator_none_content_does_not_crash():
    """Defect 7: a present-but-None content must not crash the [:50] key.

    Pre-fix ``content_key = result["content"][:50]`` raised TypeError
    ('NoneType' object is not subscriptable).
    """
    fn = _exec_codegen_fn("result_aggregator", "aggregate_federated_results")
    out = fn(_aggregator_responses(none_content=True))
    assert out["aggregated_results"]["total_raw_results"] == 2


# --------------------------------------------------------------------------
# Defect 8 — result_aggregator codegen non-dict result element
# --------------------------------------------------------------------------


def test_issue_f8b5_aggregator_non_dict_result_element_is_skipped():
    """Defect 8: a non-dict element in a node's results list must be skipped.

    Pre-fix ``result.copy()`` raised AttributeError ('str' object has no
    attribute 'copy'). A node's results list is peer-supplied data.
    """
    fn = _exec_codegen_fn("result_aggregator", "aggregate_federated_results")
    out = fn(_aggregator_responses(non_dict_result=True))
    # The bare string is skipped; the two dict results aggregate cleanly.
    assert out["aggregated_results"]["total_raw_results"] == 2


# --------------------------------------------------------------------------
# Defect 9 — cache_coordinator codegen None content
# --------------------------------------------------------------------------


def test_issue_f8b5_cache_coordinator_none_content_does_not_crash():
    """Defect 9: a present-but-None content must not crash the content_hash.

    Pre-fix ``hashlib.sha256(result["content"].encode())`` raised
    AttributeError ('NoneType' object has no attribute 'encode').
    """
    fn = _exec_codegen_fn("cache_coordinator", "coordinate_caching")
    aggregated = {"results": [{"content": None, "score": 0.95, "node_agreement": 0.9}]}
    out = fn(aggregated, {"query_id": "q1"})
    assert out["cache_coordination"]["candidates_identified"] == 1

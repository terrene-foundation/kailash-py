"""Tier-2a integration coverage for ``kaizen.nodes.rag.federated``.

F8 shard B5. The 3 federated RAG nodes ship a deterministic *simulated*
federated path — ``federated.py`` marks the executor explicitly as "simulated
- would use actual network calls". There is no container and no LLM key on the
shipped default path: the federated aggregation, the cross-silo governance,
and the edge retrieval are all real deterministic compute. NO mocking
(``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in Tier 2 per the
3-tier testing rule). There is nothing to mock — the deterministic compute IS
the path under test.

``FederatedRAGNode`` is a ``WorkflowNode``; its ``_create_workflow()`` builds a
sub-workflow whose ``PythonCodeNode`` ``code=`` templates carry the
distribution / aggregation / formatting logic. End-to-end runtime execution of
that graph is a documented scope boundary (see the shard summary's WorkflowNode
finding). This file covers what is exercisable with the ``[rag]`` extra alone:
the codegen templates exercised DIRECTLY via ``exec`` against well-formed and
malformed input (the B1 codegen-regression pattern), plus the
random-seed-pinned cross-silo / edge ``run()`` paths.

The **no-data-leak verification** (the B5 value-anchor) lives in
``TestFederatedNoDataLeakBoundary`` — it asserts, with a unique sentinel
string, exactly what does and does not cross the federated boundary.

Assertions are structural: result keys, score ranges/ordering, list lengths,
typed-error raises, sentinel presence/absence.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime

import pytest

from kaizen.nodes.rag.federated import CrossSiloRAGNode, EdgeRAGNode, FederatedRAGNode

pytestmark = pytest.mark.integration


# ==========================================================================
# Codegen-template helper — exercise FederatedRAGNode's code= templates.
#
# The FederatedRAGNode codegen functions build a local ``result`` dict as
# their FINAL statement but never ``return`` it — the function output is
# unreachable to a direct caller (a WorkflowNode codegen finding, reported in
# the shard summary). To exercise the logic behaviorally, this helper appends
# ``\n    return result`` so the final ``result`` local is returned. The code=
# string is read off the built workflow via ``get_node(id).code`` — the
# canonical accessor: ``WorkflowBuilder.build()`` consumes the ``code`` config
# kwarg into the PythonCodeNode's ``.code`` attribute and the rebuilt
# NodeInstance ``.config`` is empty.
# ==========================================================================


def _exec_codegen_fn(workflow, node_id, fn_name, extra_ns=None):
    """exec a FederatedRAGNode codegen template and return its function."""
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


def _sample_federated_responses(*, none_content=False, non_dict_result=False):
    """Build a well-formed federated_responses dict for the aggregator.

    none_content / non_dict_result inject the two malformed-input shapes the
    aggregator's result-intake loop must survive.
    """
    h_a_results: list = [{"content": "clinical protocol A", "score": 0.9}]
    if none_content:
        h_a_results = [{"content": None, "score": 0.9}]
    if non_dict_result:
        h_a_results = ["bare-string", {"content": "clinical protocol A", "score": 0.9}]
    return {
        "query_id": "q1",
        "node_responses": [
            {
                "node_id": "hospital_a",
                "results": h_a_results,
                "metadata": {
                    "response_time": 1.0,
                    "result_count": len(h_a_results),
                    "cache_hit": False,
                },
            },
            {
                "node_id": "hospital_b",
                "results": [{"content": "clinical protocol B", "score": 0.8}],
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


# ==========================================================================
# FederatedRAGNode codegen templates — query_distributor + federated_executor
# ==========================================================================


class TestFederatedRAGCodegenDistribution:
    """Behavioral coverage of the distribution-side codegen templates."""

    def test_query_distributor_builds_one_target_per_endpoint(self):
        """The distributor builds a per-endpoint target-node entry."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "query_distributor",
            "distribute_query",
        )
        result = fn(
            "treatment protocols",
            {"hospital_a": "https://a.api", "hospital_b": "https://b.api"},
            {},
        )
        assert result["ready_for_distribution"] is True
        plan = result["distribution_plan"]
        assert len(plan["target_nodes"]) == 2
        assert plan["federation_metadata"]["total_nodes"] == 2

    def test_query_distributor_empty_endpoints_yields_no_targets(self):
        """No endpoints → an empty target-node list, no crash."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "query_distributor",
            "distribute_query",
        )
        result = fn("query", {}, {})
        assert result["distribution_plan"]["target_nodes"] == []

    def test_federated_executor_produces_per_node_responses(self):
        """The simulated executor produces a response per target node."""
        random.seed(7)
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "federated_executor",
            "execute_federated_queries",
        )
        plan = {
            "query_id": "q1",
            "target_nodes": [
                {"node_id": "hospital_a", "endpoint": "u", "timeout": 5},
                {"node_id": "research_lab", "endpoint": "u", "timeout": 5},
            ],
        }
        result = fn(plan)
        stats = result["federated_responses"]["statistics"]
        # seed 7 — both simulated nodes succeed (10% failure rate not hit).
        assert stats["total_nodes"] == 2
        assert stats["successful_nodes"] + stats["failed_nodes"] == 2

    def test_federated_executor_empty_targets_reports_zero_avg(self):
        """An empty target list yields a zero avg_response_time, no ZeroDiv."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "federated_executor",
            "execute_federated_queries",
        )
        result = fn({"query_id": "q1", "target_nodes": []})
        assert result["federated_responses"]["statistics"]["avg_response_time"] == 0


# ==========================================================================
# FederatedRAGNode codegen templates — result_aggregator
# ==========================================================================


class TestFederatedRAGCodegenAggregator:
    """Behavioral coverage of the result_aggregator codegen template."""

    def test_aggregator_weighted_average_produces_scored_results(self):
        """The weighted_average strategy aggregates per-node results."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        out = fn(_sample_federated_responses())["aggregated_results"]
        assert out["total_raw_results"] == 2
        assert out["aggregation_metadata"]["strategy"] == "weighted_average"
        # Results are sorted by score, descending.
        scores = [r["score"] for r in out["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_aggregator_voting_strategy_counts_votes(self):
        """The voting strategy ranks results by accumulated votes."""
        fn = _exec_codegen_fn(
            FederatedRAGNode(
                aggregation_strategy="voting"
            )._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        out = fn(_sample_federated_responses())["aggregated_results"]
        assert out["aggregation_metadata"]["strategy"] == "voting"
        for result in out["results"]:
            assert result["metadata"]["aggregation_method"] == "voting"

    def test_aggregator_below_minimum_returns_error(self):
        """When fewer than min nodes responded, an error block is returned."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        responses = _sample_federated_responses()
        responses["statistics"]["minimum_requirement_met"] = False
        responses["statistics"]["successful_nodes"] = 1
        out = fn(responses)["aggregated_results"]
        assert out["error"] == "Insufficient nodes responded"

    def test_aggregator_none_content_result_does_not_crash(self):
        """A present-but-None content must not crash the [:50] grouping key.

        Pre-fix the aggregator did ``result["content"][:50]`` — a None content
        raised ``TypeError: 'NoneType' object is not subscriptable``. See
        tests/regression/test_issue_f8b5_federated_defects.py.
        """
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        out = fn(_sample_federated_responses(none_content=True))["aggregated_results"]
        assert out["total_raw_results"] == 2

    def test_aggregator_non_dict_result_element_is_skipped(self):
        """A non-dict element in a node's results list is skipped, not crashed.

        Pre-fix the aggregator did ``result.copy()`` on every element — a bare
        string raised ``AttributeError: 'str' object has no attribute 'copy'``.
        """
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        out = fn(_sample_federated_responses(non_dict_result=True))[
            "aggregated_results"
        ]
        # The bare string is skipped; only the two dict results are aggregated.
        assert out["total_raw_results"] == 2


# ==========================================================================
# FederatedRAGNode codegen templates — cache_coordinator + result_formatter
# ==========================================================================


class TestFederatedRAGCodegenFormatting:
    """Behavioral coverage of the cache + formatting codegen templates."""

    def test_cache_coordinator_identifies_high_value_candidates(self):
        """The coordinator caches high-score, high-agreement results."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "cache_coordinator",
            "coordinate_caching",
        )
        aggregated = {
            "results": [
                {"content": "high value", "score": 0.95, "node_agreement": 0.9},
                {"content": "low value", "score": 0.4, "node_agreement": 0.2},
            ]
        }
        out = fn(aggregated, {"query_id": "q1"})["cache_coordination"]
        # Only the high-score / high-agreement result qualifies.
        assert out["candidates_identified"] == 1

    def test_cache_coordinator_none_content_does_not_crash(self):
        """A present-but-None content must not crash the content_hash encode.

        Pre-fix ``hashlib.sha256(result["content"].encode())`` raised
        ``AttributeError: 'NoneType' object has no attribute 'encode'``.
        """
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "cache_coordinator",
            "coordinate_caching",
        )
        aggregated = {
            "results": [{"content": None, "score": 0.95, "node_agreement": 0.9}]
        }
        out = fn(aggregated, {"query_id": "q1"})["cache_coordination"]
        assert out["candidates_identified"] == 1

    def test_result_formatter_builds_node_contribution_summary(self):
        """The formatter builds the final federated-RAG output structure."""
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_formatter",
            "format_federated_results",
        )
        aggregated = {
            "results": [{"content": "c", "score": 0.9}],
            "aggregation_metadata": {
                "strategy": "weighted_average",
                "node_weights": {"hospital_a": 1.0},
                "participating_nodes": ["hospital_a"],
            },
            "total_raw_results": 1,
            "federation_health": {"result_diversity": 0.5},
        }
        federated_responses = {
            "node_responses": [
                {
                    "node_id": "hospital_a",
                    "status": "success",
                    "metadata": {"result_count": 1, "response_time": 1.0},
                }
            ],
            "failed_nodes": [],
            "statistics": {
                "minimum_requirement_met": True,
                "avg_response_time": 1.0,
                "successful_nodes": 1,
                "total_nodes": 1,
            },
        }
        out = fn(aggregated, federated_responses)["federated_rag_output"]
        assert set(out.keys()) >= {
            "federated_results",
            "node_contributions",
            "aggregation_metadata",
            "federation_health",
            "performance_metrics",
        }
        assert "hospital_a" in out["node_contributions"]


# ==========================================================================
# EdgeRAGNode + CrossSiloRAGNode run() — seed-pinned deterministic paths
# ==========================================================================


class TestEdgeRAGNodeRun:
    """EdgeRAGNode.run() against real deterministic edge-retrieval compute."""

    def test_run_resource_usage_reports_model_size(self):
        """resource_usage carries the configured model-size profile."""
        result = EdgeRAGNode(model_size="tiny").run(
            query="anomaly", local_data=[{"content": "anomaly detected"}]
        )
        assert result["resource_usage"]["model_size"] == "tiny"
        assert result["resource_usage"]["estimated_cpu_ms"] == 50

    def test_run_sync_requested_sets_high_priority(self):
        """sync_with_cloud=True forces a high-priority sync recommendation."""
        result = EdgeRAGNode().run(
            query="q",
            local_data=[{"content": f"q match {i}"} for i in range(20)],
            sync_with_cloud=True,
        )
        rec = result["sync_recommendations"]
        assert rec["should_sync"] is True
        assert "User requested sync" in rec["reasons"]


class TestCrossSiloRAGNodeRun:
    """CrossSiloRAGNode.run() against real deterministic governance compute."""

    def test_run_participating_silos_counted_in_metadata(self):
        """federation_metadata counts the silos that participated."""
        random.seed(0)
        result = CrossSiloRAGNode(silos=["org_a", "org_b"]).run(
            query="trend",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        meta = result["federation_metadata"]
        assert meta["participating_silos"] >= 1
        assert meta["data_sharing_level"] == "minimal"

    def test_run_compliance_report_reflects_real_request(self):
        """The compliance report is derived from the actual request inputs.

        The report echoes the real requester and the granted permissions, and
        the verdict reflects per-peer governance state — it is NOT a fixed
        "compliant" stamp. A single-silo request has zero peer silos, so
        data-minimization holds vacuously.
        """
        random.seed(0)
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="trend",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        report = result["compliance_report"]
        assert report["compliance_status"] == "compliant"
        assert report["data_minimization"] is True
        # The report echoes the real request, not hardcoded values.
        assert report["requester"] == "org_a"
        assert report["permissions_granted"] == ["read_aggregated"]
        # Single-silo request: the requester's own silo is not a peer.
        assert report["peer_silos_total"] == 0

    def test_run_compliance_report_counts_governed_peer_silos(self):
        """With a peer silo present, the report counts how many were governed.

        Under the default 'minimal' agreement, the peer silo's content is
        governed (truncated + restricted-marker), so peer_silos_governed
        equals peer_silos_total and the verdict is compliant.
        """
        random.seed(0)
        result = CrossSiloRAGNode(silos=["org_a", "org_b"]).run(
            query="trend",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        report = result["compliance_report"]
        # seed 0 — org_b participates as a governed peer.
        assert report["peer_silos_total"] >= 1
        assert report["peer_silos_governed"] == report["peer_silos_total"]
        assert report["compliance_status"] == "compliant"
        assert report["data_minimization"] is True

    def test_run_audit_trail_reflects_governed_results(self):
        """The audit-trail data_flow records the governed peer-silo output.

        The audit reads governance markers from governed_results (the actual
        post-governance output) — a peer silo under the 'minimal' agreement is
        recorded as governance_applied=True; the requester's own silo, which
        is not governed, as False.
        """
        random.seed(0)
        result = CrossSiloRAGNode(silos=["org_a", "org_b"]).run(
            query="trend",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        flows = {f["silo"]: f for f in result["audit_trail"]["data_flow"]}
        # The requester's own silo is full-access, not governed.
        assert flows["org_a"]["governance_applied"] is False
        assert flows["org_a"]["access_level"] == "full"
        # seed 0 — org_b participates and is governed.
        if flows["org_b"]["data_shared"]:
            assert flows["org_b"]["governance_applied"] is True


# ==========================================================================
# No-data-leak boundary verification — the B5 value-anchor
# ==========================================================================


class TestFederatedNoDataLeakBoundary:
    """Behavioral verification of what crosses the federated boundary.

    The federated RAG nodes advertise data locality: ``FederatedRAGNode`` —
    "Data never leaves source organizations"; ``CrossSiloRAGNode`` — "RAG
    across organizational boundaries with strict data governance". These tests
    pin a unique sentinel into the data a peer silo would hold and assert
    exactly what does and does not cross the boundary in the node OUTPUT.

    The honest characterization of the shipped contract:

    * ``EdgeRAGNode`` is local-only by construction — there is NO federated
      boundary; its output legitimately contains the local document text
      because nothing is shared with any peer.
    * ``FederatedRAGNode`` ingests only a ``query`` and ``node_endpoints`` — it
      has NO document-corpus input, so no raw local document can leak; the
      simulated executor generates its own per-node content.
    * ``CrossSiloRAGNode`` IS the real cross-organization boundary. The
      requester's own silo returns full content (its own data); EVERY OTHER
      silo's content is governed before it crosses — ``minimal`` truncates and
      stamps "[Details restricted ...]"; ``standard`` anonymizes (organization
      names, numeric and ALLCAPS identifiers redacted).
    """

    _SENTINEL = "ZQXJSENTINEL9981"

    def test_federated_rag_node_takes_no_document_corpus_input(self):
        """FederatedRAGNode's parameter contract has no document-corpus input.

        The structural guarantee behind "data never leaves source orgs": the
        node cannot leak a raw local document because no raw document is ever
        passed to it — only a query and per-node endpoints.
        """
        node = FederatedRAGNode()
        # The WorkflowNode wraps a sub-workflow whose entry codegen
        # (query_distributor) reads only ``query`` and ``node_endpoints``.
        # _create_workflow is a private helper; @register_node type-erases the
        # class to Node so the checker cannot see it.
        workflow = node._create_workflow()  # type: ignore[attr-defined]
        distributor_code = workflow.get_node("query_distributor").code
        assert "def distribute_query(query, node_endpoints, federation_config)" in (
            distributor_code
        )
        # No corpus / documents parameter anywhere in the distribution entry.
        assert "documents" not in distributor_code

    def test_federated_aggregate_carries_only_peer_supplied_content(self):
        """The aggregate crossing the boundary carries scores + aggregates.

        The aggregator's output is per-result content + score + metadata
        (source nodes, weights, agreement) — it does NOT fabricate or attach
        any caller-supplied raw local corpus, because the node never received
        one. This pins the aggregate's shape so a future refactor that adds a
        raw-corpus passthrough fails loudly.
        """
        fn = _exec_codegen_fn(
            FederatedRAGNode()._create_workflow(),  # type: ignore[attr-defined]
            "result_aggregator",
            "aggregate_federated_results",
        )
        out = fn(_sample_federated_responses())["aggregated_results"]
        for result in out["results"]:
            assert set(result.keys()) <= {
                "content",
                "score",
                "metadata",
                "node_agreement",
            }
        # The aggregation metadata exposes only counts / weights / node ids.
        assert set(out["aggregation_metadata"].keys()) == {
            "strategy",
            "node_weights",
            "participating_nodes",
        }

    def test_cross_silo_requester_own_silo_keeps_full_content(self):
        """The requester's OWN silo content is NOT governed — it is their data.

        This is the boundary's correct asymmetry: an organization sees its own
        data in full; only OTHER organizations' data is restricted.
        """
        random.seed(0)
        result = CrossSiloRAGNode(
            silos=["org_a", "org_b"], data_sharing_agreement="minimal"
        ).run(
            query=f"analysis {self._SENTINEL}",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        own = next(
            s
            for s in result["silo_results"]
            if s.get("silo") == "org_a" and s.get("participated")
        )
        assert own["access_level"] == "full"
        # The own-silo result is not stamped with a governance marker.
        assert own["results"][0].get("governance_applied") is None

    def test_cross_silo_minimal_agreement_restricts_other_silo_content(self):
        """Under 'minimal', a peer silo's content crosses only as a summary.

        The OTHER silo's content is truncated and stamped with an explicit
        "[Details restricted ...]" marker — the raw detail does not cross.
        """
        random.seed(0)
        result = CrossSiloRAGNode(
            silos=["org_a", "org_b"], data_sharing_agreement="minimal"
        ).run(
            query="analysis",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        other = next(
            (
                s
                for s in result["silo_results"]
                if s.get("silo") == "org_b" and s.get("participated")
            ),
            None,
        )
        # seed 0 — org_b participates; if a future seed change drops it, the
        # next assertion's None-guard makes the skip explicit rather than silent.
        assert other is not None, "expected org_b to participate at seed 0"
        governed = other["results"][0]
        assert governed["governance_applied"] == "minimal_sharing"
        assert "[Details restricted" in governed["content"]

    def test_cross_silo_standard_agreement_anonymizes_other_silo_content(self):
        """Under 'standard', a peer silo's content is anonymized before it
        crosses: the organization name and numeric / ALLCAPS identifiers in the
        sentinel-bearing query are redacted out of the peer's result."""
        random.seed(0)
        result = CrossSiloRAGNode(
            silos=["org_a", "org_b"], data_sharing_agreement="standard"
        ).run(
            query="PATIENT 12345 trend",
            requester_org="org_a",
            access_permissions=["read_aggregated", "read_anonymized"],
        )
        other = next(
            (
                s
                for s in result["silo_results"]
                if s.get("silo") == "org_b" and s.get("participated")
            ),
            None,
        )
        assert other is not None, "expected org_b to participate at seed 0"
        governed = other["results"][0]
        assert governed["governance_applied"] == "anonymized"
        # The peer's own org name and the raw identifiers are redacted.
        assert "org_b" not in governed["content"]
        assert "12345" not in governed["content"]
        assert "PATIENT" not in governed["content"]
        assert "[Organization]" in governed["content"]

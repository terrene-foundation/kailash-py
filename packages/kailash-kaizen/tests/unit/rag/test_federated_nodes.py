"""Tier-1 unit coverage for the 3 ``kaizen.nodes.rag.federated`` nodes.

F8 shard B5. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable" — and for federated RAG specifically the **no-data-leak claim**:
the nodes advertise that raw documents stay local and only aggregates cross
the boundary.

``EdgeRAGNode`` and ``CrossSiloRAGNode`` are ``kailash.nodes.base.Node``
subclasses with a direct ``run()``. Their default code path is deterministic
simulated compute — ``federated.py`` marks the federated executor explicitly
as "simulated - would use actual network calls". There is NO LLM key and NO
network call on the shipped default path; ``run()`` computes its result with
deterministic keyword / governance logic. These tests exercise that real path:
no mocking of the aggregation / governance core (there is nothing to mock).

``FederatedRAGNode`` is a ``WorkflowNode``; its ``run()`` executes a
sub-workflow built by ``_create_workflow()``. Tier-1 covers its construction
and the graph SHAPE (node count, parameter contract, conditional cache node);
the ``code=`` PythonCodeNode templates are exercised directly in the Tier-2a
file.

One test per documented behavior; assertions are structural (output keys,
score ranges/ordering, list lengths, typed raises).
"""

from __future__ import annotations

import pytest

from kaizen.nodes.rag.federated import CrossSiloRAGNode, EdgeRAGNode, FederatedRAGNode

pytestmark = pytest.mark.unit


# ==========================================================================
# EdgeRAGNode
# ==========================================================================

# The top-level keys EdgeRAGNode.run() always returns.
_EDGE_KEYS = {"results", "resource_usage", "sync_recommendations", "edge_metadata"}


class TestEdgeRAGNode:
    """run() golden path + documented edge cases for EdgeRAGNode."""

    def test_get_parameters_declares_query_and_local_data_required(self):
        """query and local_data are the two required run-time inputs."""
        params = EdgeRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["local_data"].required is True
        assert params["sync_with_cloud"].required is False

    def test_run_golden_path_returns_documented_keys(self):
        """run() returns the four documented top-level keys."""
        result = EdgeRAGNode().run(
            query="sensor anomaly",
            local_data=[{"content": "sensor anomaly detected near valve"}],
        )
        assert set(result.keys()) == _EDGE_KEYS
        assert result["edge_metadata"]["local_data_size"] == 1

    def test_run_keyword_match_scores_relevant_document(self):
        """A document sharing query words scores above zero and is retrieved."""
        result = EdgeRAGNode(model_size="tiny").run(
            query="valve pressure",
            local_data=[
                {"content": "valve pressure exceeded threshold"},
                {"content": "completely unrelated text"},
            ],
        )
        # tiny model reports the count of matched results in the answer text.
        assert "Found 1 relevant results" in result["results"][0]["content"]
        assert result["results"][0]["score"] > 0

    def test_run_small_model_summarizes_top_document(self):
        """The 'small' model echoes the top document's content in the answer."""
        result = EdgeRAGNode(model_size="small").run(
            query="valve pressure",
            local_data=[{"content": "valve pressure exceeded threshold"}],
        )
        assert "Based on local data" in result["results"][0]["content"]

    def test_run_no_matching_documents_returns_zero_score(self):
        """A query matching no document yields a zero-score fallback result."""
        result = EdgeRAGNode().run(
            query="quantum tunnelling",
            local_data=[{"content": "valve pressure log"}],
        )
        assert result["results"][0]["score"] == 0

    def test_run_empty_local_data_returns_zero_score_result(self):
        """An empty corpus yields exactly one zero-score fallback result."""
        result = EdgeRAGNode().run(query="anything", local_data=[])
        assert len(result["results"]) == 1
        assert result["results"][0]["score"] == 0

    def test_run_caches_result_and_returns_it_on_repeat_query(self):
        """A repeated identical query returns the cached result object."""
        node = EdgeRAGNode()
        first = node.run(query="q", local_data=[{"content": "q match"}])
        second = node.run(query="q", local_data=[{"content": "different text"}])
        # The second call is a cache hit — same object, local_data ignored.
        assert first is second

    def test_run_performance_power_mode_bypasses_cache(self):
        """power_mode='performance' skips the cache read on every call."""
        node = EdgeRAGNode(power_mode="performance")
        first = node.run(query="q", local_data=[{"content": "q"}])
        second = node.run(query="q", local_data=[{"content": "q"}])
        assert first is not second

    def test_run_small_local_corpus_recommends_cloud_sync(self):
        """Fewer than 10 local documents triggers a high-priority sync rec."""
        result = EdgeRAGNode().run(query="q", local_data=[{"content": "q"}])
        rec = result["sync_recommendations"]
        assert rec["should_sync"] is True
        assert rec["sync_priority"] == "high"
        assert "Insufficient local data" in rec["reasons"]

    # ---- documented edge cases ------------------------------------------

    def test_run_missing_query_kwarg_defaults_cleanly(self):
        """An absent query kwarg defaults to '' without crashing."""
        result = EdgeRAGNode().run(local_data=[{"content": "x"}])
        assert set(result.keys()) == _EDGE_KEYS

    def test_run_missing_local_data_kwarg_defaults_to_empty(self):
        """An absent local_data kwarg defaults to [] without crashing."""
        result = EdgeRAGNode().run(query="anything")
        assert result["edge_metadata"]["local_data_size"] == 0

    def test_run_none_query_does_not_crash(self):
        """An explicit query=None must not crash query.encode() / .lower()."""
        result = EdgeRAGNode().run(query=None, local_data=[{"content": "x"}])
        assert set(result.keys()) == _EDGE_KEYS

    def test_run_none_content_document_does_not_crash(self):
        """A document with content present-but-None must not crash retrieval."""
        result = EdgeRAGNode().run(query="q", local_data=[{"content": None}])
        assert set(result.keys()) == _EDGE_KEYS

    def test_run_non_dict_document_element_is_skipped(self):
        """A non-dict local_data element is skipped, not crashed on."""
        result = EdgeRAGNode().run(
            query="valve", local_data=["bare-string", {"content": "valve log"}]
        )
        assert result["edge_metadata"]["local_data_size"] == 2

    def test_run_unicode_query_is_handled(self):
        """A unicode query is handled by the keyword-matching path."""
        result = EdgeRAGNode().run(
            query="温度センサー", local_data=[{"content": "温度センサー alarm"}]
        )
        assert set(result.keys()) == _EDGE_KEYS


# ==========================================================================
# CrossSiloRAGNode
# ==========================================================================

# The top-level keys CrossSiloRAGNode.run() returns on the access-granted path.
_CROSS_SILO_KEYS = {
    "silo_results",
    "audit_trail",
    "compliance_report",
    "federation_metadata",
}


class TestCrossSiloRAGNode:
    """run() golden path + access-control + governance edge cases."""

    def test_get_parameters_declares_required_inputs(self):
        """query, requester_org and access_permissions are required."""
        params = CrossSiloRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["requester_org"].required is True
        assert params["access_permissions"].required is True
        assert params["purpose"].required is False

    def test_run_granted_access_returns_documented_keys(self):
        """An in-federation requester with adequate permissions gets results."""
        result = CrossSiloRAGNode(silos=["org_a", "org_b"]).run(
            query="industry trend analysis",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert set(result.keys()) == _CROSS_SILO_KEYS
        assert result["federation_metadata"]["governance_applied"] is True

    def test_run_non_federation_requester_is_denied(self):
        """A requester outside the silo set is denied with a typed reason."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="q",
            requester_org="outsider",
            access_permissions=["read_aggregated"],
        )
        assert result["error"] == "Access denied"
        assert result["reason"] == "Organization not part of federation"

    def test_run_insufficient_permissions_is_denied(self):
        """A 'standard' agreement needs read_anonymized; absent → denied."""
        result = CrossSiloRAGNode(
            silos=["org_a"], data_sharing_agreement="standard"
        ).run(
            query="q",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert result["error"] == "Access denied"
        assert result["reason"] == "Insufficient permissions"

    def test_run_disallowed_purpose_is_denied(self):
        """A purpose outside the governance allow-list is denied."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="q",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
            purpose="exfiltration",
        )
        assert result["error"] == "Access denied"
        assert "not allowed" in result["reason"]

    def test_run_minimal_audit_mode_omits_full_trail(self):
        """audit_mode='minimal' returns the deferred-audit sentinel string."""
        result = CrossSiloRAGNode(silos=["org_a"], audit_mode="minimal").run(
            query="q",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert result["audit_trail"] == "Audit available on request"

    def test_run_standard_audit_mode_returns_structured_trail(self):
        """The default audit mode returns a structured audit-trail dict."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="q",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        audit = result["audit_trail"]
        assert isinstance(audit, dict)
        assert set(audit.keys()) >= {
            "timestamp",
            "query_hash",
            "requester",
            "federation_activity",
            "data_flow",
        }

    # ---- documented edge cases ------------------------------------------

    def test_run_missing_access_permissions_kwarg_denies_cleanly(self):
        """An absent access_permissions kwarg defaults to [] → denied."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(query="q", requester_org="org_a")
        assert result["error"] == "Access denied"

    def test_run_none_access_permissions_denies_cleanly(self):
        """An explicit access_permissions=None must not crash `perm in None`."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="q", requester_org="org_a", access_permissions=None
        )
        assert result["error"] == "Access denied"

    def test_run_none_query_does_not_crash_audit_hash(self):
        """An explicit query=None must not crash the audit-trail query.encode()."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query=None,
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert set(result.keys()) == _CROSS_SILO_KEYS

    def test_run_empty_silos_yields_no_participating_silos(self):
        """An empty silo set denies the requester (not in federation)."""
        result = CrossSiloRAGNode(silos=[]).run(
            query="q",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert result["error"] == "Access denied"

    def test_run_unicode_query_is_handled(self):
        """A unicode query flows through the access + governance path."""
        result = CrossSiloRAGNode(silos=["org_a"]).run(
            query="産業動向の分析",
            requester_org="org_a",
            access_permissions=["read_aggregated"],
        )
        assert set(result.keys()) == _CROSS_SILO_KEYS


# ==========================================================================
# FederatedRAGNode — WorkflowNode construction + graph shape
# ==========================================================================


class TestFederatedRAGNode:
    """Construction + the shape of the workflow ``_create_workflow()`` builds.

    FederatedRAGNode is a WorkflowNode; the codegen ``code=`` templates are
    exercised behaviorally in the Tier-2a integration file. Tier-1 covers the
    construction contract and the conditional graph shape.
    """

    def test_constructs_with_defaults(self):
        """The node constructs with documented default configuration."""
        node = FederatedRAGNode()
        assert node.aggregation_strategy == "weighted_average"
        assert node.min_participating_nodes == 2
        assert node.federation_nodes == []
        assert node.enable_caching is True

    def test_constructor_config_overrides_apply(self):
        """Constructor kwargs override the federation configuration."""
        node = FederatedRAGNode(
            federation_nodes=["hospital_a", "hospital_b", "research_lab"],
            aggregation_strategy="voting",
            min_participating_nodes=3,
            enable_caching=False,
        )
        assert node.federation_nodes == ["hospital_a", "hospital_b", "research_lab"]
        assert node.aggregation_strategy == "voting"
        assert node.min_participating_nodes == 3
        assert node.enable_caching is False

    def test_workflow_has_five_nodes_when_caching_enabled(self):
        """With caching on, the workflow has the cache_coordinator node."""
        # _create_workflow is a private helper; type-erased by @register_node.
        workflow = FederatedRAGNode()._create_workflow()  # type: ignore[attr-defined]
        assert set(workflow.nodes) == {
            "query_distributor",
            "federated_executor",
            "result_aggregator",
            "cache_coordinator",
            "result_formatter",
        }

    def test_workflow_omits_cache_coordinator_when_caching_disabled(self):
        """With caching off, the cache_coordinator node is not built."""
        workflow = FederatedRAGNode(
            enable_caching=False
        )._create_workflow()  # type: ignore[attr-defined]
        assert set(workflow.nodes) == {
            "query_distributor",
            "federated_executor",
            "result_aggregator",
            "result_formatter",
        }

    def test_min_participating_nodes_interpolated_into_executor_codegen(self):
        """min_participating_nodes is interpolated into the executor template."""
        workflow = FederatedRAGNode(
            min_participating_nodes=4
        )._create_workflow()  # type: ignore[attr-defined]
        code = workflow.get_node("federated_executor").code
        assert "successful_nodes >= 4" in code

    def test_aggregation_strategy_interpolated_into_aggregator_codegen(self):
        """aggregation_strategy is interpolated into the aggregator template."""
        workflow = FederatedRAGNode(
            aggregation_strategy="voting"
        )._create_workflow()  # type: ignore[attr-defined]
        code = workflow.get_node("result_aggregator").code
        assert '"voting" == "voting"' in code

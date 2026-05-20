"""Tier 1 unit coverage — ``kaizen.nodes.rag.conversational``.

F8 shard B9b. The 2 classes under test (ConversationalRAGNode,
ConversationMemoryNode) are the documented multi-turn / long-term-memory
RAG surface.

Tier 1 scope:

- Construction with default + custom kwargs across both classes.
- ``get_parameters()`` contract for ConversationMemoryNode (Node subclass).
- The inner workflow GRAPH SHAPE produced by
  ``ConversationalRAGNode._create_workflow`` across optional-branch
  permutations (coreference_resolution, topic_tracking,
  enable_summarization).
- The deterministic ``run()`` paths on ConversationMemoryNode
  (store / retrieve / update / forget / unknown).
- ``create_session`` deterministic + Optional-user_id paths.

The Tier-2a aiosqlite round-trip + real LocalRuntime end-to-end coverage
lives in `tests/integration/rag/test_conversational_nodes.py` per the
3-tier strategy.
"""

from __future__ import annotations

from collections import deque

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.conversational import (
    ConversationalRAGNode,
    ConversationMemoryNode,
)

pytestmark = pytest.mark.unit


def _build(node: ConversationalRAGNode) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure."""
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# Construction floor — both classes
# ==========================================================================


class TestBothConstruct:
    def test_conversational_rag_constructs_default(self):
        node = ConversationalRAGNode()
        assert node is not None
        assert node.metadata.name == "conversational_rag"
        assert node.max_context_turns == 10  # type: ignore[attr-defined]
        assert node.enable_summarization is True  # type: ignore[attr-defined]
        assert node.personalization_enabled is True  # type: ignore[attr-defined]
        assert node.coreference_resolution is True  # type: ignore[attr-defined]
        assert node.topic_tracking is True  # type: ignore[attr-defined]
        # Fresh session store starts empty.
        assert node.sessions == {}  # type: ignore[attr-defined]

    def test_conversational_rag_constructs_with_custom_kwargs(self):
        node = ConversationalRAGNode(
            name="custom_conv",
            max_context_turns=5,
            enable_summarization=False,
            personalization_enabled=False,
            coreference_resolution=False,
            topic_tracking=False,
        )
        assert node.metadata.name == "custom_conv"
        assert node.max_context_turns == 5  # type: ignore[attr-defined]
        assert node.enable_summarization is False  # type: ignore[attr-defined]
        assert node.personalization_enabled is False  # type: ignore[attr-defined]
        assert node.coreference_resolution is False  # type: ignore[attr-defined]
        assert node.topic_tracking is False  # type: ignore[attr-defined]

    def test_conversation_memory_constructs_default(self):
        node = ConversationMemoryNode()
        assert node is not None
        assert node.metadata.name == "conversation_memory"
        assert node.memory_types == [  # type: ignore[attr-defined]
            "episodic",
            "semantic",
            "preferences",
        ]
        assert node.retention_policy == "adaptive"  # type: ignore[attr-defined]
        assert node.max_memories_per_user == 1000  # type: ignore[attr-defined]

    def test_conversation_memory_constructs_with_custom_kwargs(self):
        node = ConversationMemoryNode(
            name="custom_memory",
            memory_types=["episodic"],
            retention_policy="permanent",
            max_memories_per_user=100,
        )
        assert node.metadata.name == "custom_memory"
        assert node.memory_types == ["episodic"]  # type: ignore[attr-defined]
        assert node.retention_policy == "permanent"  # type: ignore[attr-defined]
        assert node.max_memories_per_user == 100  # type: ignore[attr-defined]


# ==========================================================================
# get_parameters() contract — ConversationMemoryNode
# ==========================================================================


class TestConversationMemoryParameters:
    def test_required_parameters(self):
        params = ConversationMemoryNode().get_parameters()
        assert params["operation"].required is True
        assert params["operation"].type is str
        assert params["user_id"].required is True
        assert params["user_id"].type is str

    def test_optional_parameters_with_defaults(self):
        params = ConversationMemoryNode().get_parameters()
        assert params["name"].required is False
        assert params["memory_types"].required is False
        assert params["retention_policy"].required is False
        assert params["retention_policy"].default == "adaptive"
        assert params["max_memories_per_user"].required is False
        assert params["max_memories_per_user"].default == 1000
        assert params["data"].required is False
        assert params["context"].required is False

    def test_get_parameters_returns_all_documented_keys(self):
        params = ConversationMemoryNode().get_parameters()
        assert set(params.keys()) == {
            "name",
            "memory_types",
            "retention_policy",
            "max_memories_per_user",
            "operation",
            "user_id",
            "data",
            "context",
        }


# ==========================================================================
# ConversationalRAGNode inner workflow — graph shape
# ==========================================================================


class TestConversationalRAGGraphShape:
    """The _create_workflow graph wires the documented pipeline shape."""

    def test_default_graph_includes_all_optional_nodes(self):
        """With every flag True (defaults), all 7 nodes are wired."""
        wf = _build(ConversationalRAGNode())
        assert set(wf.nodes.keys()) == {
            "context_loader",
            "coreference_resolver",
            "topic_tracker",
            "context_retriever",
            "response_generator",
            "context_summarizer",
            "session_updater",
            "result_formatter",
        }

    def test_coreference_off_omits_coreference_resolver_node(self):
        wf = _build(ConversationalRAGNode(coreference_resolution=False))
        assert "coreference_resolver" not in wf.nodes
        coreference_edges = [
            c
            for c in wf.connections
            if c.target_node == "coreference_resolver"
            or c.source_node == "coreference_resolver"
        ]
        assert coreference_edges == []

    def test_topic_tracking_off_omits_topic_tracker_node(self):
        wf = _build(ConversationalRAGNode(topic_tracking=False))
        assert "topic_tracker" not in wf.nodes
        topic_edges = [
            c
            for c in wf.connections
            if c.target_node == "topic_tracker" or c.source_node == "topic_tracker"
        ]
        assert topic_edges == []

    def test_summarization_off_omits_summarizer_node(self):
        wf = _build(ConversationalRAGNode(enable_summarization=False))
        assert "context_summarizer" not in wf.nodes
        summarizer_edges = [
            c
            for c in wf.connections
            if c.target_node == "context_summarizer"
            or c.source_node == "context_summarizer"
        ]
        assert summarizer_edges == []

    def test_minimal_graph_with_all_optional_flags_off(self):
        """With every optional flag False, only the 5 mandatory nodes remain."""
        wf = _build(
            ConversationalRAGNode(
                coreference_resolution=False,
                topic_tracking=False,
                enable_summarization=False,
            )
        )
        assert set(wf.nodes.keys()) == {
            "context_loader",
            "context_retriever",
            "response_generator",
            "session_updater",
            "result_formatter",
        }

    def test_context_loader_feeds_context_retriever(self):
        wf = _build(ConversationalRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "context_loader"
            and c.target_node == "context_retriever"
        ]
        assert len(edges) >= 1
        # The session_context output flows into context_retriever.session_context.
        ports = {(e.source_output, e.target_input) for e in edges}
        assert ("session_context", "session_context") in ports

    def test_result_formatter_is_final_sink(self):
        """result_formatter has no outbound edges; it is the final sink."""
        wf = _build(ConversationalRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_formatter"]
        assert outbound == []
        inbound = [c for c in wf.connections if c.target_node == "result_formatter"]
        assert len(inbound) >= 4  # session_updater + response_gen + topic + retrieval

    def test_max_context_turns_baked_into_context_loader_code(self):
        """The max_context_turns kwarg is interpolated into the loader code."""
        wf = _build(ConversationalRAGNode(max_context_turns=3))
        loader = wf.get_node("context_loader")
        assert loader is not None
        code = loader.config.get("code", "")
        # The recent_turns slice uses session["turns"][-3:].
        assert 'session["turns"][-3:]' in code


# ==========================================================================
# ConversationalRAGNode.create_session() — deterministic paths
# ==========================================================================


class TestCreateSession:
    def test_create_session_default_returns_documented_shape(self):
        node = ConversationalRAGNode()
        out = node.create_session()
        assert "session_id" in out
        assert out["created"] is True
        assert out["expires_in"] == 3600
        # The session is registered in the in-memory store.
        assert out["session_id"] in node.sessions  # type: ignore[attr-defined]

    def test_create_session_with_user_id(self):
        node = ConversationalRAGNode()
        out = node.create_session(user_id="alice")
        session = node.sessions[out["session_id"]]  # type: ignore[attr-defined]
        assert session["user_id"] == "alice"
        assert session["turns"] == []
        assert session["current_topic"] is None
        assert session["metrics"]["turn_count"] == 0

    def test_create_session_distinct_ids_for_same_user_at_different_timestamps(self):
        """The sha256 hash includes datetime.now().isoformat() — different calls → different ids."""
        import time

        node = ConversationalRAGNode()
        out_a = node.create_session(user_id="alice")
        time.sleep(0.01)  # ensure isoformat() differs in the microsecond field
        out_b = node.create_session(user_id="alice")
        assert out_a["session_id"] != out_b["session_id"]


# ==========================================================================
# ConversationMemoryNode.run() deterministic paths
# ==========================================================================


class TestConversationMemoryRun:
    """The Node-subclass run() dispatches across store/retrieve/update/forget."""

    def test_run_store_episodic_returns_count(self):
        node = ConversationMemoryNode()
        out = node.run(
            operation="store",
            user_id="u1",
            data={
                "conversation_id": "c1",
                "conversation": {
                    "summary": "hello",
                    "topics": ["python"],
                    "sentiment": "neutral",
                    "importance": 0.5,
                },
            },
        )
        assert out["storage_status"] == "success"
        assert out["stored"]["episodic"] == 1
        assert out["total_memories"]["episodic"] == 1

    def test_run_store_then_retrieve_episodic(self):
        """A stored episode with a topic is retrievable when the context shares the topic."""
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="u2",
            data={
                "conversation_id": "c1",
                "conversation": {
                    "summary": "discussed transformers",
                    "topics": ["transformers"],
                    "sentiment": "positive",
                    "importance": 0.8,
                },
            },
        )
        out = node.run(
            operation="retrieve",
            user_id="u2",
            context="transformers attention mechanism",
        )
        relevant = out["relevant_memories"]
        # At least one episodic memory was matched on the "transformers" topic.
        episodic_matches = [m for m in relevant if m["type"] == "episodic"]
        assert len(episodic_matches) >= 1
        assert "transformers" in episodic_matches[0]["content"]["topics"]

    def test_run_retrieve_empty_when_no_memories(self):
        node = ConversationMemoryNode()
        out = node.run(operation="retrieve", user_id="never_seen", context="anything")
        assert out["relevant_memories"] == []
        assert out["memory_summary"] == "No memories found"
        assert out["personalization_hints"] == {}

    def test_run_store_semantic_fact(self):
        node = ConversationMemoryNode()
        out = node.run(
            operation="store",
            user_id="u3",
            data={
                "facts": [
                    {
                        "key": "favorite_language",
                        "value": "python",
                        "confidence": 0.9,
                        "source": "conversation",
                    }
                ]
            },
        )
        assert out["stored"]["semantic"] == 1
        assert out["total_memories"]["semantic"] == 1

    def test_run_store_then_retrieve_semantic(self):
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="u4",
            data={
                "facts": [
                    {
                        "key": "favorite_language",
                        "value": "rust",
                        "confidence": 0.95,
                    }
                ]
            },
        )
        out = node.run(
            operation="retrieve",
            user_id="u4",
            context="favorite_language preference",
        )
        semantic = [m for m in out["relevant_memories"] if m["type"] == "semantic"]
        assert len(semantic) >= 1
        assert semantic[0]["content"]["value"] == "rust"

    def test_run_store_preferences(self):
        node = ConversationMemoryNode()
        out = node.run(
            operation="store",
            user_id="u5",
            data={"preferences": {"style": "concise", "topic": "ml"}},
        )
        # The preferences dict has 2 keys; stored counts each one.
        assert out["stored"]["preferences"] == 2
        assert out["total_memories"]["preferences"] == 2

    def test_run_update_existing_fact(self):
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="u6",
            data={"facts": [{"key": "language", "value": "python", "confidence": 0.5}]},
        )
        out = node.run(
            operation="update",
            user_id="u6",
            data={
                "facts_update": [
                    {"key": "language", "updates": {"value": "rust", "confidence": 0.9}}
                ]
            },
        )
        assert out["update_status"] == "success"
        assert out["updated"]["semantic"] == 1

    def test_run_update_unknown_user_returns_error(self):
        node = ConversationMemoryNode()
        out = node.run(operation="update", user_id="ghost", data={})
        assert out["error"] == "No memories found for user"

    def test_run_forget_all_wipes_user(self):
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="u7",
            data={
                "conversation_id": "c1",
                "conversation": {"summary": "x", "topics": ["a"], "importance": 0.5},
            },
        )
        out = node.run(operation="forget", user_id="u7", data={"forget_all": True})
        assert out["forgotten"] == "all"
        assert out["status"] == "complete"
        # Subsequent retrieve sees no memories.
        retrieve_out = node.run(operation="retrieve", user_id="u7", context="x")
        assert retrieve_out["relevant_memories"] == []

    def test_run_forget_specific_types(self):
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="u8",
            data={
                "facts": [{"key": "k1", "value": "v1"}],
                "preferences": {"p1": "v1"},
            },
        )
        out = node.run(
            operation="forget",
            user_id="u8",
            data={"forget_types": ["semantic"]},
        )
        assert out["forget_status"] == "success"
        assert out["forgotten"]["semantic"] >= 1

    def test_run_unknown_operation_returns_error(self):
        node = ConversationMemoryNode()
        out = node.run(operation="invalid_op", user_id="u9")
        assert "error" in out
        assert "invalid_op" in out["error"]


# ==========================================================================
# ConversationMemoryNode private-helper sanity (deterministic, no LLM)
# ==========================================================================


class TestConversationMemoryHelpers:
    def test_extract_frequent_topics_empty(self):
        node = ConversationMemoryNode()
        # Deque is empty → empty topic list.
        out = node._extract_frequent_topics(deque())  # type: ignore[attr-defined]
        assert out == []

    def test_extract_frequent_topics_orders_by_frequency(self):
        node = ConversationMemoryNode()
        episodes = deque(
            [
                {"topics": ["a", "b"]},
                {"topics": ["a", "c"]},
                {"topics": ["a"]},
                {"topics": ["b"]},
            ]
        )
        out = node._extract_frequent_topics(episodes)  # type: ignore[attr-defined]
        # 'a' appears 3x; 'b' 2x; 'c' 1x.
        assert out[0] == "a"
        assert "b" in out

    def test_infer_interaction_style_empty(self):
        node = ConversationMemoryNode()
        out = node._infer_interaction_style(deque())  # type: ignore[attr-defined]
        assert out["style"] == "unknown"
        assert out["confidence"] == 0

    def test_infer_interaction_style_detailed_for_high_importance(self):
        node = ConversationMemoryNode()
        episodes = deque(
            [{"importance": 0.9}, {"importance": 0.8}, {"importance": 0.85}]
        )
        out = node._infer_interaction_style(episodes)  # type: ignore[attr-defined]
        assert out["style"] == "detailed"

    def test_infer_interaction_style_concise_for_low_importance(self):
        node = ConversationMemoryNode()
        episodes = deque(
            [{"importance": 0.1}, {"importance": 0.2}, {"importance": 0.15}]
        )
        out = node._infer_interaction_style(episodes)  # type: ignore[attr-defined]
        assert out["style"] == "concise"


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_two_classes():
    """The module exports exactly the 2 documented classes."""
    from kaizen.nodes.rag import conversational

    assert set(conversational.__all__) == {
        "ConversationalRAGNode",
        "ConversationMemoryNode",
    }

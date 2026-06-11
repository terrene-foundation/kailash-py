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
        """With every flag True (defaults), all nodes are wired — including the
        L3-fix messages-composer for each LLM stage (response/coreference/
        summary), which render retrieved docs + history + query into the valid
        LLMAgentNode `messages` port."""
        wf = _build(ConversationalRAGNode())
        assert set(wf.nodes.keys()) == {
            "context_loader",
            "coreference_resolver",
            "coreference_messages_composer",
            "topic_tracker",
            "context_retriever",
            "response_generator",
            "response_messages_composer",
            "context_summarizer",
            "summary_messages_composer",
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
        """With every optional flag False, the mandatory nodes remain — plus the
        always-present response messages-composer (the response_generator LLM
        stage always needs grounded `messages`). The coreference/summary
        composers are gated to their optional flags and are absent here."""
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
            "response_messages_composer",
            "session_updater",
            "result_formatter",
        }
        # The optional composers track their optional LLM stages.
        assert "coreference_messages_composer" not in wf.nodes
        assert "summary_messages_composer" not in wf.nodes

    def test_context_loader_feeds_context_retriever(self):
        wf = _build(ConversationalRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "context_loader"
            and c.target_node == "context_retriever"
        ]
        assert len(edges) >= 1
        # F9 #1117 wiring fix: a PythonCodeNode publishes a SINGLE `result`
        # port (carrying its whole module-scope `result` dict); the nested
        # "session_context" key is NOT an individual port. The edge MUST read
        # `result` (the prior `session_context` source port never existed, so
        # the downstream input silently bound to nothing).
        ports = {(e.source_output, e.target_input) for e in edges}
        assert ("result", "session_context") in ports

    def test_pythoncode_producer_edges_read_result_port(self):
        """Every edge sourced from a PythonCodeNode codegen stage MUST read the
        `result` port — the only port a PythonCodeNode publishes. Reading a
        non-existent nested-key port (the F9 #1117 wiring bug) silently binds
        nothing downstream."""
        wf = _build(ConversationalRAGNode())
        pycode_sources = {
            "context_loader",
            "topic_tracker",
            "context_retriever",
            "session_updater",
        }
        offenders = [
            (c.source_node, c.source_output)
            for c in wf.connections
            if c.source_node in pycode_sources and c.source_output != "result"
        ]
        assert (
            offenders == []
        ), f"PythonCodeNode edges not reading `result`: {offenders}"

    def test_result_formatter_is_final_sink(self):
        """result_formatter has no outbound edges; it is the final sink."""
        wf = _build(ConversationalRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_formatter"]
        assert outbound == []
        inbound = [c for c in wf.connections if c.target_node == "result_formatter"]
        assert len(inbound) >= 4  # session_updater + response_gen + topic + retrieval

    def test_max_context_turns_controls_context_loader_sliding_window(self):
        """The max_context_turns kwarg controls the sliding-window slice the
        context_loader applies.

        S6a: the context_loader stage is now a ``PythonCodeNode.from_function``
        node (the inline ``code=`` codegen with the interpolated
        ``session["turns"][-{N}:]`` slice was lifted to the module-level
        ``_load_conversation_context`` function, with ``max_context_turns`` bound
        at workflow-construction time through a closure). This test preserves the
        ORIGINAL intent BEHAVIORALLY (per ``rules/testing.md`` § Behavioral
        Regression Tests Over Source-Grep): it (a) asserts the production node is
        a ``from_function`` ``PythonCodeNode`` (no ``code=`` config), AND (b)
        calls the lifted function directly with a pre-seeded session of 5 turns
        and ``max_context_turns=3``, asserting the returned ``recent_turns`` slice
        honors the window."""
        wf = _build(ConversationalRAGNode(max_context_turns=3))
        loader = wf.get_node("context_loader")
        assert loader is not None
        # The lifted node is a from_function PythonCodeNode — no `code=` config.
        assert type(loader).__name__ == "PythonCodeNode"
        assert loader.config.get("code") is None

        # Behavioral: the lifted function applies the sliding-window slice.
        from kaizen.nodes.rag.conversational import _load_conversation_context

        store = {
            "s1": {
                "id": "s1",
                "turns": [{"query": f"q{i}", "response": f"r{i}"} for i in range(5)],
                "summary": "",
                "current_topic": None,
                "user_preferences": {},
                "metrics": {
                    "turn_count": 5,
                    "topics_discussed": [],
                    "avg_response_length": 0,
                },
            }
        }
        out = _load_conversation_context(
            session_id="s1", sessions_store=store, max_context_turns=3
        )
        recent = out["session_context"]["recent_turns"]
        # The window keeps the LAST 3 of the 5 seeded turns.
        assert len(recent) == 3
        assert [t["query"] for t in recent] == ["q2", "q3", "q4"]


# ==========================================================================
# ConversationalRAGNode.create_session() — deterministic paths
# ==========================================================================


class TestCreateSession:
    def test_create_session_default_returns_documented_shape(self):
        node = ConversationalRAGNode()
        out = node.create_session()  # type: ignore[attr-defined]
        assert "session_id" in out
        assert out["created"] is True
        assert out["expires_in"] == 3600
        # The session is registered in the in-memory store.
        assert out["session_id"] in node.sessions  # type: ignore[attr-defined]

    def test_create_session_with_user_id(self):
        node = ConversationalRAGNode()
        out = node.create_session(user_id="alice")  # type: ignore[attr-defined]
        session = node.sessions[out["session_id"]]  # type: ignore[attr-defined]
        assert session["user_id"] == "alice"
        assert session["turns"] == []
        assert session["current_topic"] is None
        assert session["metrics"]["turn_count"] == 0

    def test_create_session_distinct_ids_for_same_user(self):
        """session_id is a CSPRNG token (secrets.token_hex(16)) — two calls for the
        same user produce different, unguessable ids (no timestamp dependence)."""
        node = ConversationalRAGNode()
        out_a = node.create_session(user_id="alice")  # type: ignore[attr-defined]
        out_b = node.create_session(user_id="alice")  # type: ignore[attr-defined]
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


# ==========================================================================
# F31-FU2 Shard B — direct-call Tier-1 coverage of the 3 pure composer
# `from_function` targets in ``conversational.py``. These render the OpenAI
# chat `messages` list for each LLM stage — pure data rendering (the permitted
# output-formatting exception per rules/agent-reasoning.md), NOT agent
# decision-making. Called DIRECTLY (no LocalRuntime, no mocking — pure funcs).
#
# NOTE: conversational has NO `from_function` PARSERS — the consumers read
# `.get("content")` inline inside the `code=` PythonCodeNode bodies (genuinely
# correct; there is nothing to cover at the parser layer). Only the 3 composers
# are direct-callable module-level functions, so ONLY they are covered here.
# Each composer asserts VALID interpolation + EMPTY/None well-formedness; the
# EMPTY assertion uses the composer's OWN honest placeholder (read source).
# ==========================================================================


from kaizen.nodes.rag.conversational import (
    compose_coreference_messages,
    compose_response_messages,
    compose_summary_messages,
)


def _assert_messages_shape(result):
    """Assert the composer return is a well-formed OpenAI chat ``messages`` list."""
    assert isinstance(result, dict)
    assert "messages" in result
    msgs = result["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    for m in msgs:
        assert isinstance(m, dict)
        assert "role" in m and "content" in m
    return msgs


class TestComposeResponseMessages:
    def test_compose_response_valid_renders_docs_history_query(self):
        contextual_retrieval = {
            "contextual_retrieval": {
                "documents": [{"content": "BERT is a transformer model"}],
                "enhanced_query": "What is BERT?",
            }
        }
        conversation_context = {
            "session_context": {
                "context_text": "User: hi\nAssistant: hello\n",
            }
        }
        msgs = _assert_messages_shape(
            compose_response_messages(
                contextual_retrieval=contextual_retrieval,
                conversation_context=conversation_context,
                query="What is BERT?",
            )
        )
        content = msgs[0]["content"]
        assert "What is BERT?" in content
        # Retrieved docs + history are grounded into the response messages.
        assert "BERT is a transformer model" in content
        assert "User: hi" in content

    def test_compose_response_recovers_query_from_enhanced_query(self):
        # No explicit `query` -> the composer recovers it from the retriever's
        # enhanced_query (an in-graph source embedding the original question).
        contextual_retrieval = {
            "contextual_retrieval": {
                "documents": [],
                "enhanced_query": "transformers context: explain attention",
            }
        }
        msgs = _assert_messages_shape(
            compose_response_messages(
                contextual_retrieval=contextual_retrieval,
                conversation_context=None,
                query="",
            )
        )
        assert "explain attention" in msgs[0]["content"]

    def test_compose_response_all_empty_returns_wellformed(self):
        # query="", no retrieval, no history -> still a valid messages shape.
        msgs = _assert_messages_shape(
            compose_response_messages(
                contextual_retrieval=None,
                conversation_context=None,
                query="",
            )
        )
        # The composer always appends the "Current question:" block (empty body).
        assert "Current question:" in msgs[0]["content"]


class TestComposeCoreferenceMessages:
    def test_compose_coreference_valid_renders_query_and_history(self):
        conversation_context = {
            "session_context": {
                "context_text": "User: tell me about transformers\nAssistant: ok\n",
            }
        }
        msgs = _assert_messages_shape(
            compose_coreference_messages(
                current_query="How does its attention work?",
                conversation_context=conversation_context,
            )
        )
        content = msgs[0]["content"]
        assert "How does its attention work?" in content
        # The conversation history (the antecedent source) is rendered.
        assert "tell me about transformers" in content

    def test_compose_coreference_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(
            compose_coreference_messages(current_query="", conversation_context=None)
        )
        # Always appends the "Query to resolve:" block (empty body), no crash.
        assert "Query to resolve:" in msgs[0]["content"]


class TestComposeSummaryMessages:
    def test_compose_summary_valid_renders_history(self):
        conversation_context = {
            "session_context": {
                "context_text": "User: explain BERT\nAssistant: BERT is...\n",
            }
        }
        msgs = _assert_messages_shape(
            compose_summary_messages(conversation_context=conversation_context)
        )
        assert "explain BERT" in msgs[0]["content"]

    def test_compose_summary_empty_returns_wellformed(self):
        # No history -> explicit empty-history note (honest, non-empty messages).
        msgs = _assert_messages_shape(
            compose_summary_messages(conversation_context=None)
        )
        assert "No conversation history yet." in msgs[0]["content"]


# ==========================================================================
# S6a Shard — direct-call Tier-1 coverage of the 5 COMPUTE-stage
# `from_function` targets lifted from the inline `code=` codegen blocks in
# ``conversational.py``. These are pure data computations (the permitted
# tool-fetch / data-transform shape per rules/agent-reasoning.md — no agent
# decision-making). Called DIRECTLY (no LocalRuntime, no mocking — pure funcs)
# per the one-direct-test-per-variant Tier-1 mandate. A from_function node
# publishes its `return` value on the flat `result` port, so the returned dict
# is exactly what the node publishes downstream.
#
# `_load_conversation_context` is covered above by
# ``test_max_context_turns_controls_context_loader_sliding_window`` (sliding
# window) — the remaining four lifted functions are covered here.
# ==========================================================================


from kaizen.nodes.rag.conversational import (
    _format_conversational_result,
    _load_conversation_context,
    _retrieve_with_context,
    _track_conversation_topic,
    _update_session,
)


class TestLiftedComputeFunctions:
    def test_load_conversation_context_creates_session_when_absent(self):
        """An absent session is seeded; the returned shape carries the
        documented session_context keys + an empty recent_turns window."""
        store: dict = {}
        out = _load_conversation_context(
            session_id="brand_new", sessions_store=store, max_context_turns=10
        )
        sc = out["session_context"]
        assert sc["session_id"] == "brand_new"
        assert sc["recent_turns"] == []
        assert sc["turn_count"] == 0
        assert sc["context_text"] == ""
        # The seeded session is now in the per-run store.
        assert "brand_new" in store

    def test_track_conversation_topic_identifies_transformer_topic(self):
        """A transformer-keyword query yields the 'transformers' topic on the
        flat result's topic_analysis. session_context is the whole
        {"session_context": ...} wrapper the function unwraps internally."""
        out = _track_conversation_topic(
            current_query="explain self-attention in the encoder",
            session_context={"session_context": {"current_topic": None}},
        )
        ta = out["topic_analysis"]
        assert ta["current_topic"] == "transformers"
        assert ta["topic_changed"] is False  # first topic = new_conversation
        assert ta["transition_type"] == "new_conversation"
        assert "transformers" in ta["identified_topics"]
        assert ta["confidence"] == 0.8

    def test_track_conversation_topic_no_keyword_yields_general(self):
        """A query with no topic keyword falls back to 'general' (honest
        default, not fabricated)."""
        out = _track_conversation_topic(
            current_query="hello there",
            session_context={"session_context": {"current_topic": None}},
        )
        ta = out["topic_analysis"]
        assert ta["current_topic"] == "general"
        assert ta["identified_topics"] == []
        assert ta["confidence"] == 0.3

    def test_retrieve_with_context_scores_and_enhances_query(self):
        """The retriever ranks docs by query-term overlap and surfaces the
        enhanced_query on the flat result's contextual_retrieval. topic_info is
        passed through WITHOUT unwrap (already {"topic_analysis": ...})."""
        docs = [
            {"content": "transformer attention mechanism explained"},
            {"content": "unrelated cooking recipe"},
        ]
        out = _retrieve_with_context(
            query="attention mechanism",
            documents=docs,
            session_context={"session_context": {"context_text": ""}},
            topic_info={"topic_analysis": {"current_topic": "transformers"}},
        )
        cr = out["contextual_retrieval"]
        # The topic prefix is folded into the enhanced query.
        assert cr["enhanced_query"].startswith("transformers context:")
        assert len(cr["documents"]) == 2
        # The transformer doc outranks the cooking doc.
        assert cr["documents"][0]["content"].startswith("transformer attention")

    def test_retrieve_with_context_resolved_query_overrides_raw(self):
        """A resolved_query dict (the coreference_resolver `response` port value,
        keyed by "content") overrides the raw query string."""
        out = _retrieve_with_context(
            query="how does it work",
            documents=[{"content": "bert masked language model"}],
            session_context={"session_context": {"context_text": ""}},
            topic_info=None,
            resolved_query={"content": "how does bert work"},
        )
        cr = out["contextual_retrieval"]
        # The resolved query ("bert") drives scoring, not the raw "it".
        assert "bert" in cr["enhanced_query"]

    def test_retrieve_with_context_empty_documents_honest_zero_influence(self):
        """No documents → empty results + honest zero context_influence."""
        out = _retrieve_with_context(
            query="anything",
            documents=[],
            session_context={"session_context": {"context_text": ""}},
        )
        cr = out["contextual_retrieval"]
        assert cr["documents"] == []
        assert cr["scores"] == []
        assert cr["context_influence"] == 0

    def test_update_session_records_turn_and_metrics(self):
        """A new turn is appended; the returned session_update reflects the
        recorded turn + derived (non-fabricated) coherence metrics. response is
        the LLMAgentNode `response` port value keyed by "content"."""
        store: dict = {}
        out = _update_session(
            session_id="s_up",
            query="what is bert",
            response={"content": "BERT is a bidirectional model."},
            topic_info={"topic_analysis": {"current_topic": "bert"}},
            summary=None,
            sessions_store=store,
            max_context_turns=10,
        )
        su = out["session_update"]
        assert su["session_id"] == "s_up"
        assert su["turn_added"] == 1
        assert su["total_turns"] == 1
        assert su["current_topic"] == "bert"
        # Single-topic conversation → coherence 1.0 (derived from topic count).
        assert su["conversation_metrics"]["coherence_score"] == 1.0

    def test_update_session_applies_summary_when_provided(self):
        """A summary dict (context_summarizer `response` port, keyed by
        "content") updates the session summary."""
        store: dict = {}
        _update_session(
            session_id="s_sum",
            query="q",
            response={"content": "r"},
            summary={"content": "A concise conversation summary."},
            sessions_store=store,
            max_context_turns=10,
        )
        assert store["s_sum"]["summary"] == "A concise conversation summary."

    def test_format_conversational_result_publishes_documented_shape(self):
        """The terminal formatter unwraps each producer's nested key and
        publishes the documented conversational_response. The config flags are
        passed explicitly (the closure binds them at construction time)."""
        out = _format_conversational_result(
            response={"content": "the answer"},
            session_update={
                "session_update": {
                    "session_id": "sid",
                    "turn_added": 2,
                    "total_turns": 2,
                    "conversation_metrics": {"topic_diversity": 0.5},
                }
            },
            topic_info={"topic_analysis": {"current_topic": "gpt"}},
            contextual_retrieval={"contextual_retrieval": {"context_influence": 0.7}},
            max_context_turns=8,
            enable_summarization=False,
            coreference_resolution=True,
            personalization_enabled=False,
        )
        cr = out["conversational_response"]
        assert cr["response"] == "the answer"
        assert cr["session_state"]["session_id"] == "sid"
        assert cr["session_state"]["total_turns"] == 2
        # Config flags interpolated through the explicit params (the #1123 fix).
        assert cr["session_state"]["context_window"] == 8
        assert cr["session_state"]["summary_available"] is False
        assert cr["topic_info"]["current_topic"] == "gpt"
        assert cr["conversation_metrics"]["retrieval_context_influence"] == 0.7
        assert cr["metadata"]["coreference_resolution"] is True
        assert cr["metadata"]["personalization"] is False
        assert cr["metadata"]["context_enhanced_retrieval"] is True

    def test_format_conversational_result_handles_all_empty_inputs(self):
        """All-None inputs (a False optional-branch with nothing wired) still
        publish a well-formed conversational_response (honest empty defaults)."""
        out = _format_conversational_result()
        cr = out["conversational_response"]
        assert cr["response"] == ""
        assert cr["session_state"]["session_id"] is None
        assert cr["topic_info"]["transition_type"] == "continuation"
        assert "metadata" in cr

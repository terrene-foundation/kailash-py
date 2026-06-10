"""Tier-2a integration coverage — ``kaizen.nodes.rag.conversational``.

F8 shard B9b. The 2 classes under test (ConversationalRAGNode,
ConversationMemoryNode) carry the multi-turn conversation +
long-term-memory contracts.

Value-anchor (F8 plan §B B9b row): "**metric correctness + real storage
read-back**". This file lifts the **real-storage-read-back** half:

- ``ConversationMemoryNode`` exposes a per-user in-memory store accessed
  through its ``run(operation=...)`` dispatch surface. Tier-2a exercises
  every write (`store`, `update`, `forget`) through the documented API
  AND verifies the effect with a subsequent read (`retrieve`) — per
  `rules/testing.md` § "State Persistence Verification (Tiers 2-3)":
  "Every write MUST be verified with a read-back".
- A separate `AsyncSQLitePool` round-trip test demonstrates real aiosqlite
  persistence via the kailash SDK pool (the framework's pool primitive
  per `rules/patterns.md` § "SQLite Connection Management") to honor the
  brief's "real aiosqlite round-trip" mandate. The pool uses URI
  shared-cache memory mode so the test is hermetic (no on-disk files).
- ``ConversationalRAGNode`` workflow construction + `create_session`
  exercised through real Python execution paths.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in
Tier 2/3 per ``rules/testing.md``).
"""

from __future__ import annotations

import json
import uuid

import pytest
from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

# Register LLMAgentNode (string-referenced inside ConversationalRAGNode's
# workflow) so the end-to-end execution test can resolve it from the registry.
import kaizen.nodes.ai.llm_agent  # noqa: F401
from kaizen.nodes.rag.conversational import (
    ConversationalRAGNode,
    ConversationMemoryNode,
)

pytestmark = pytest.mark.integration


def _build(node: ConversationalRAGNode) -> Workflow:
    """Past the ``@register_node`` Node-type erasure — see B7/B8/B9a precedent."""
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# ConversationMemoryNode — multi-call read-back through the documented API
# ==========================================================================


class TestMemoryReadBackPersistence:
    """Every write through `run(operation=...)` MUST survive a subsequent read.

    Per `rules/testing.md` § "State Persistence Verification": call
    create/update, then call get/list, assert the value. The
    ConversationMemoryNode's in-memory store is the persistence layer for
    this Node-subclass; the read-back verifies the write's effect is
    durable across the operation-dispatch boundary.
    """

    def test_episodic_write_survives_retrieve_read_back(self):
        """Store an episodic memory → retrieve it on its topic → assert it's there."""
        node = ConversationMemoryNode()
        # WRITE: store an episodic memory with a unique topic.
        unique_topic = f"topic_{uuid.uuid4().hex[:8]}"
        store_out = node.run(
            operation="store",
            user_id="readback_user_1",
            data={
                "conversation_id": "rb_conv_1",
                "conversation": {
                    "summary": "test persistence summary",
                    "topics": [unique_topic],
                    "sentiment": "neutral",
                    "importance": 0.7,
                },
            },
        )
        assert store_out["storage_status"] == "success"
        # READ-BACK: retrieve on the unique topic — the episode MUST be there.
        retrieve_out = node.run(
            operation="retrieve",
            user_id="readback_user_1",
            context=unique_topic,
        )
        relevant = retrieve_out["relevant_memories"]
        episodic = [m for m in relevant if m["type"] == "episodic"]
        # The unique topic guarantees the read targets the specific episode.
        assert len(episodic) >= 1
        assert unique_topic in episodic[0]["content"]["topics"]
        assert episodic[0]["content"]["summary"] == "test persistence summary"

    def test_semantic_write_survives_retrieve_read_back(self):
        """Store a semantic fact → retrieve on the fact key → assert value matches."""
        node = ConversationMemoryNode()
        unique_key = f"fact_{uuid.uuid4().hex[:8]}"
        node.run(
            operation="store",
            user_id="readback_user_2",
            data={
                "facts": [
                    {
                        "key": unique_key,
                        "value": "persistent_fact_value",
                        "confidence": 0.92,
                    }
                ]
            },
        )
        retrieve_out = node.run(
            operation="retrieve",
            user_id="readback_user_2",
            context=unique_key,
        )
        semantic = [
            m for m in retrieve_out["relevant_memories"] if m["type"] == "semantic"
        ]
        assert len(semantic) >= 1
        # The value carried by the stored fact is the one returned.
        assert semantic[0]["content"]["value"] == "persistent_fact_value"
        assert semantic[0]["content"]["key"] == unique_key

    def test_update_write_survives_subsequent_retrieve(self):
        """Update a fact → retrieve → assert the updated value is the one read."""
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="readback_user_3",
            data={"facts": [{"key": "language", "value": "python", "confidence": 0.5}]},
        )
        # UPDATE the fact's value to "rust".
        node.run(
            operation="update",
            user_id="readback_user_3",
            data={
                "facts_update": [
                    {"key": "language", "updates": {"value": "rust", "confidence": 0.9}}
                ]
            },
        )
        retrieve_out = node.run(
            operation="retrieve",
            user_id="readback_user_3",
            context="language",
        )
        semantic = [
            m for m in retrieve_out["relevant_memories"] if m["type"] == "semantic"
        ]
        assert len(semantic) >= 1
        # READ-BACK confirms the update landed.
        assert semantic[0]["content"]["value"] == "rust"
        assert semantic[0]["content"]["confidence"] == 0.9

    def test_forget_all_clears_user_then_retrieve_empty(self):
        """Forget-all clears the user → retrieve sees no memories."""
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="readback_user_4",
            data={
                "conversation_id": "c1",
                "conversation": {
                    "summary": "x",
                    "topics": ["doomed"],
                    "importance": 0.5,
                },
            },
        )
        # Confirm the write before forget.
        before = node.run(
            operation="retrieve", user_id="readback_user_4", context="doomed"
        )
        assert len(before["relevant_memories"]) >= 1
        # FORGET ALL.
        node.run(
            operation="forget",
            user_id="readback_user_4",
            data={"forget_all": True},
        )
        # READ-BACK confirms the user's slate is wiped.
        after = node.run(
            operation="retrieve", user_id="readback_user_4", context="doomed"
        )
        assert after["relevant_memories"] == []
        assert after["memory_summary"] == "No memories found"

    def test_preferences_write_survives_retrieve_read_back(self):
        """Store preferences → retrieve → assert the preferences are in personalization_hints."""
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="readback_user_5",
            data={
                "preferences": {
                    "explanation_style": "detailed",
                    "response_length": "long",
                }
            },
        )
        # Read-back via retrieve — preferences live in personalization_hints.
        retrieve_out = node.run(
            operation="retrieve",
            user_id="readback_user_5",
            context="anything",
        )
        prefs = retrieve_out["personalization_hints"]["preferences"]
        assert prefs["explanation_style"] == "detailed"
        assert prefs["response_length"] == "long"

    def test_multi_user_isolation_writes_dont_bleed(self):
        """User A's writes are not visible to user B's reads — isolation contract."""
        node = ConversationMemoryNode()
        node.run(
            operation="store",
            user_id="user_alpha",
            data={
                "facts": [
                    {"key": "secret_alpha", "value": "alpha_value", "confidence": 0.9}
                ]
            },
        )
        # User B retrieves on user A's key — MUST return no memories for B.
        out = node.run(
            operation="retrieve",
            user_id="user_beta",
            context="secret_alpha",
        )
        # Beta has no memories — None of alpha's facts leak.
        assert out["relevant_memories"] == []


# ==========================================================================
# Real aiosqlite round-trip via AsyncSQLitePool (framework pool primitive)
# ==========================================================================


class TestAiosqliteRoundTripViaPool:
    """Real aiosqlite persistence round-trip via the kailash SDK pool.

    Per the F8 B9b value-anchor mandate, real aiosqlite round-trip MUST
    verify state survives a serialized boundary. We serialize the
    ConversationMemoryNode's user-memory state into a real aiosqlite
    table through `AsyncSQLitePool` (the framework's pool primitive per
    `rules/patterns.md` § "SQLite Connection Management"), then read it
    back through a SECOND acquire — proving the write reached the DB.

    Uses URI shared-cache memory mode (`file:memdb_<test>?mode=memory&
    cache=shared`) so the test is hermetic — no on-disk files.

    Schema-defense: the conversation_memory table is created via a
    static DDL string. The user_id is parameter-bound ($1); the table
    name is a hardcoded literal so no dialect.quote_identifier is needed
    per `rules/dataflow-identifier-safety.md` § "Hardcoded Identifier
    Lists" (the table name is static, never user-influenced).
    """

    @pytest.mark.asyncio
    async def test_aiosqlite_round_trip_via_pool(self):
        """Write → close acquire → re-acquire → read back the same bytes."""
        # Unique URI per test instance so concurrent tests don't share state.
        db_uri = f"file:memdb_b9b_{uuid.uuid4().hex[:8]}?mode=memory&cache=shared"
        config = SQLitePoolConfig(
            db_path=db_uri,
            max_read_connections=2,
            uri=True,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()
        try:
            # Build a real ConversationMemoryNode + populate it.
            node = ConversationMemoryNode()
            node.run(
                operation="store",
                user_id="aiosqlite_user_1",
                data={
                    "facts": [
                        {
                            "key": "favorite_lang",
                            "value": "python",
                            "confidence": 0.95,
                        }
                    ],
                    "preferences": {"style": "concise"},
                },
            )
            # Serialize the user's memory slice via the documented retrieve.
            user_state = node.run(
                operation="retrieve",
                user_id="aiosqlite_user_1",
                context="favorite_lang",
            )

            # WRITE through the pool's writer connection. The table name is
            # a static literal (no dynamic identifier).
            async with pool.acquire_write() as conn:
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS conversation_memory ("
                    "user_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)"
                )
                await conn.execute(
                    "INSERT INTO conversation_memory (user_id, state_json) "
                    "VALUES (?, ?)",
                    ("aiosqlite_user_1", json.dumps(user_state)),
                )
                await conn.commit()

            # READ-BACK through a SECOND acquire — proves the write
            # reached the DB (not a coincidental in-process reference).
            # Memory-DB mode is single-connection; the writer acquire is
            # also the reader path.
            async with pool.acquire_write() as conn:
                cursor = await conn.execute(
                    "SELECT state_json FROM conversation_memory WHERE user_id = ?",
                    ("aiosqlite_user_1",),
                )
                row = await cursor.fetchone()
                await cursor.close()

            assert row is not None, "read-back row missing — write did not persist"
            persisted = json.loads(row["state_json"])
            # The persisted state carries the documented retrieve shape.
            assert "relevant_memories" in persisted
            assert "memory_summary" in persisted
            assert "personalization_hints" in persisted
            # The personalization_hints.preferences carries the stored style.
            assert (
                persisted["personalization_hints"]["preferences"]["style"] == "concise"
            )
        finally:
            await pool.close()


# ==========================================================================
# ConversationalRAGNode — workflow construction under real interpreter
# ==========================================================================


class TestConversationalWorkflowConstruction:
    """ConversationalRAGNode constructs cleanly under all optional permutations.

    The node is a WorkflowNode; constructor invokes _create_workflow().
    A successful construction proves the workflow graph compiles AND the
    PEP-562 codegen templates parse as Python without raising NameError
    (the B9a R4 LEAK failure mode).
    """

    def test_construct_with_all_optional_flags_true(self):
        node = ConversationalRAGNode(
            coreference_resolution=True,
            topic_tracking=True,
            enable_summarization=True,
        )
        wf = _build(node)
        # All 8 core nodes + 3 L3-fix messages-composers (response/coreference/
        # summary) = 11.
        assert len(wf.nodes) == 11

    def test_construct_with_all_optional_flags_false(self):
        """Minimal config: 5 mandatory nodes + the always-present response
        messages-composer = 6."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=False,
            enable_summarization=False,
        )
        wf = _build(node)
        assert len(wf.nodes) == 6

    def test_construct_topic_only_yields_7_nodes(self):
        """Only topic_tracking on: 5 mandatory + topic_tracker + the response
        messages-composer = 7."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=True,
            enable_summarization=False,
        )
        wf = _build(node)
        assert "topic_tracker" in wf.nodes
        assert "coreference_resolver" not in wf.nodes
        assert "context_summarizer" not in wf.nodes
        # Optional composers gated to their stages; response composer always on.
        assert "coreference_messages_composer" not in wf.nodes
        assert "summary_messages_composer" not in wf.nodes
        assert "response_messages_composer" in wf.nodes
        assert len(wf.nodes) == 7

    def test_create_session_persists_session_state(self):
        """A created session is reachable on the node's sessions store."""
        node = ConversationalRAGNode()
        out = node.create_session(user_id="alice_user")  # type: ignore[attr-defined]
        # READ-BACK: the session is reachable on the in-memory store.
        sid = out["session_id"]
        assert sid in node.sessions  # type: ignore[attr-defined]
        session = node.sessions[sid]  # type: ignore[attr-defined]
        assert session["user_id"] == "alice_user"
        assert session["turns"] == []


# ==========================================================================
# ConversationalRAGNode — F9 #1117/#1123 end-to-end publishing contract
# ==========================================================================


class TestConversationalRAGEndToEndPublishing:
    """The full ConversationalRAGNode workflow MUST publish a non-empty
    ``conversational_response`` under real ``LocalRuntime``.

    F9 #1117/#1123 regression: four codegen stages (context_loader,
    topic_tracker, context_retriever, session_updater) defined an inner
    function that bound ``result`` function-locally but never called it at
    module scope, AND the terminal result_formatter's config code was NOT an
    f-string yet interpolated ``{self.*}`` config flags (literal set-literals
    of an undefined ``self`` → NameError). Net: the WorkflowNode CONSTRUCTED
    but PUBLISHED NOTHING. This Tier-2 test executes the whole workflow
    against the real runtime (mock LLM provider — Tier-2 deterministic
    adapter, no @patch/MagicMock) and asserts the documented output keys.
    """

    @staticmethod
    def _run(node: ConversationalRAGNode, query: str, docs: list) -> dict:
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sid = f"sess_{uuid.uuid4().hex[:8]}"
        params = {
            "context_loader": {"session_id": sid},
            "topic_tracker": {"current_query": query},
            "context_retriever": {"query": query, "documents": docs},
            "coreference_resolver": {"provider": "mock", "model": "mock-model"},
            "response_generator": {"provider": "mock", "model": "mock-model"},
            "context_summarizer": {"provider": "mock", "model": "mock-model"},
            "session_updater": {"session_id": sid, "query": query},
        }
        with LocalRuntime() as rt:
            results, _ = rt.execute(wf, parameters=params)
        return results

    @pytest.mark.parametrize(
        "cfg",
        [
            dict(
                coreference_resolution=True,
                topic_tracking=True,
                enable_summarization=True,
            ),
            dict(
                coreference_resolution=False,
                topic_tracking=False,
                enable_summarization=False,
            ),
            dict(
                coreference_resolution=False,
                topic_tracking=True,
                enable_summarization=False,
            ),
            dict(
                coreference_resolution=True,
                topic_tracking=False,
                enable_summarization=True,
            ),
        ],
    )
    def test_workflow_publishes_conversational_response(self, cfg):
        """Every optional-flag permutation publishes the documented output."""
        node = ConversationalRAGNode(**cfg)
        query = "What is transformer architecture and how does its attention work?"
        docs = [
            {
                "content": "The transformer architecture uses self-attention "
                "across encoder and decoder layers."
            },
            {"content": "BERT is a bidirectional masked language model."},
        ]
        results = self._run(node, query, docs)

        rf = results.get("result_formatter")
        # The terminal node MUST NOT have errored (pre-fix: NameError on the
        # literal {self.*} set-literal).
        assert isinstance(rf, dict), f"no result_formatter output: {results}"
        assert not rf.get("failed"), f"result_formatter failed: {rf.get('error')}"

        # The terminal node publishes its module-scope `result` carrying the
        # WorkflowNode's documented `conversational_response`.
        published = rf["result"]["conversational_response"]

        # Documented output keys (per the class docstring Returns section).
        for key in (
            "response",
            "session_state",
            "topic_info",
            "conversation_metrics",
            "metadata",
        ):
            assert key in published, f"{key} missing for cfg={cfg}"

        # Real, non-empty response text (mock LLM returns deterministic prose).
        assert isinstance(published["response"], str)
        assert published["response"], f"empty response for cfg={cfg}"

        # The session_state reflects the turn that was actually recorded.
        ss = published["session_state"]
        assert ss["total_turns"] == 1
        assert ss["turn_number"] == 1
        # @register_node erases ConversationalRAGNode→Node for static checkers.
        assert ss["context_window"] == node.max_context_turns  # type: ignore[attr-defined]
        assert ss["summary_available"] is node.enable_summarization  # type: ignore[attr-defined]

        # metadata flags interpolated correctly (the #1123 f-string fix).
        meta = published["metadata"]
        assert meta["coreference_resolution"] is node.coreference_resolution  # type: ignore[attr-defined]
        assert meta["personalization"] is node.personalization_enabled  # type: ignore[attr-defined]
        assert meta["context_enhanced_retrieval"] is True

    def test_broken_nodes_publish_result_port(self):
        """Each previously-broken codegen stage publishes its `result` port
        carrying the documented nested key (not nothing)."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=True,
            enable_summarization=False,
        )
        query = "Tell me about transformer training and optimization."
        docs = [{"content": "Training uses learning rate schedules and batches."}]
        results = self._run(node, query, docs)

        # context_loader → result.session_context
        assert "session_context" in results["context_loader"]["result"]
        # topic_tracker → result.topic_analysis
        assert "topic_analysis" in results["topic_tracker"]["result"]
        # context_retriever → result.contextual_retrieval (with real docs)
        cr = results["context_retriever"]["result"]["contextual_retrieval"]
        assert "documents" in cr and "scores" in cr
        # session_updater → result.session_update (real turn recorded)
        su = results["session_updater"]["result"]["session_update"]
        assert su["total_turns"] == 1


class TestConversationalRAGContextReachesLLM:
    """L3 contract: retrieved documents + the user query MUST reach the
    ``response_generator`` LLM stage via a well-formed ``messages`` list.

    Pre-fix the LLM stages consumed context ONLY via the non-existent
    ``retrieval_results`` / ``conversation_context`` ports (LLMAgentNode reads
    context EXCLUSIVELY through ``messages``), so the retrieved docs were
    silently dropped and the model answered from system_prompt alone. The fix
    inserts a ``PythonCodeNode.from_function`` messages-composer upstream of
    each LLM stage that embeds the retrieved docs + history + query into an
    OpenAI-format ``messages`` list wired to the VALID ``messages`` port.

    This suite proves, under the real ``LocalRuntime``, that the composer
    publishes a ``messages`` list embedding the retrieved doc text + the user
    query, and that the composer feeds the LLM stage's ``messages`` input. The
    composer's output is a real workflow port — a structural probe, no LLM
    judgment, no graph surgery, no ``unittest.mock``.
    """

    # A grep-able sentinel embedded in the retrieved doc. Distinct enough that
    # it cannot collide with system-prompt text or query tokens.
    DOC_SENTINEL = "SENTINEL_TOKEN_42"
    DOC_TEXT = (
        "Self-attention lets every token attend to every other token in the "
        f"{DOC_SENTINEL} transformer sequence."
    )

    @staticmethod
    def _run(node, query, docs):
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sid = f"sess_{uuid.uuid4().hex[:8]}"
        params = {
            # MED-2: supply `current_query` as a TOP-LEVEL workflow input so it
            # reaches coreference_messages_composer ONLY via the production
            # delivery path — the parameter-injector auto-distribute block
            # (src/kailash/runtime/parameter_injector.py:428-449), which fans a
            # top-level param to every node whose get_parameters() advertises it
            # (the composer fn declares `current_query`). NOT via node-keyed
            # injection (params["coreference_messages_composer"]={...}), which
            # would deliver the query regardless of the production wiring (a
            # false-green guard). The load-bearing production elements this test
            # guards are therefore (a) the composer fn declaring `current_query`
            # and (b) the composer→coreference_resolver.messages edge — each
            # independently red/green-proven. (There is no add_workflow_inputs
            # mapping; it was removed as dead code.) A top-level `current_query`
            # with no consumer (coreference OFF) is simply unused — it does NOT
            # trigger the absent-node misrouting that node-keyed params for
            # absent node_ids hit (verified across all cfg permutations).
            "current_query": query,
            "context_loader": {"session_id": sid},
            "topic_tracker": {"current_query": query},
            "context_retriever": {"query": query, "documents": docs},
            "coreference_resolver": {"provider": "mock", "model": "mock-model"},
            "response_generator": {"provider": "mock", "model": "mock-model"},
            "context_summarizer": {"provider": "mock", "model": "mock-model"},
            "session_updater": {"session_id": sid, "query": query},
        }
        with LocalRuntime() as rt:
            results, _ = rt.execute(wf, parameters=params)
        return results

    def test_response_messages_composer_embeds_docs_and_query(self):
        """The composer feeding response_generator publishes a well-formed
        ``messages`` list embedding the retrieved doc text + the user query.

        RED pre-fix: no ``response_messages_composer`` node exists (the LLM
        stage was fed phantom ``retrieval_results`` / ``conversation_context``
        ports). GREEN post-fix: the composer publishes the grounded messages.
        """
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=True,
            enable_summarization=False,
        )
        query = "How does the transformer attention mechanism work?"
        docs = [
            {"content": self.DOC_TEXT},
            {"content": "BERT is a bidirectional masked language model."},
        ]
        results = self._run(node, query, docs)

        # The composer node MUST exist and MUST have published a result.
        comp = results.get("response_messages_composer")
        assert isinstance(comp, dict), (
            "response_messages_composer node missing — the LLM stage's context "
            f"inputs are still wired to phantom ports (L3 defect). keys={list(results)}"
        )
        messages = comp["result"]["messages"]

        # Well-formed OpenAI-format messages list.
        assert isinstance(messages, list) and messages, f"empty messages: {comp}"
        for m in messages:
            assert (
                isinstance(m, dict) and "role" in m and "content" in m
            ), f"malformed message (not OpenAI {{role,content}} shape): {m!r}"

        blob = "\n".join(str(m.get("content", "")) for m in messages)
        # Load-bearing L3 assertion: the retrieved doc text reached the LLM.
        assert self.DOC_SENTINEL in blob, (
            "retrieved document content did NOT reach the LLM stage's messages "
            f"— the model would answer from system_prompt alone. messages={blob!r}"
        )
        # The user query MUST also be embedded.
        assert (
            "attention mechanism" in blob
        ), f"user query did NOT reach the LLM stage's messages: {blob!r}"

    def test_composer_wired_to_response_generator_messages_port(self):
        """Structural: the composer's ``messages`` output connects to the
        ``response_generator`` ``messages`` input (the VALID LLMAgentNode port),
        NOT a phantom ``retrieval_results`` / ``conversation_context`` port.
        """
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=True,
            enable_summarization=False,
        )
        wf = node._create_workflow()  # type: ignore[attr-defined]
        feeders = [c for c in wf.connections if c.target_node == "response_generator"]
        assert feeders, "response_generator has no inbound connections"

        # No connection may target the phantom (silently-dropped) ports.
        phantom = {"retrieval_results", "conversation_context"}
        bad = [c for c in feeders if c.target_input in phantom]
        assert not bad, (
            "response_generator still fed via phantom ports "
            f"{[c.target_input for c in bad]} — LLMAgentNode drops these silently."
        )

        # The composer MUST feed the valid `messages` port.
        msg_feeders = [
            c
            for c in feeders
            if c.target_input == "messages"
            and c.source_node == "response_messages_composer"
        ]
        assert msg_feeders, (
            "response_messages_composer is not wired to response_generator's "
            f"`messages` port. feeders={[(c.source_node, c.target_input) for c in feeders]}"
        )

    def test_coreference_composer_embeds_the_user_query(self):
        """MED-1: the coreference_messages_composer MUST embed the actual user
        query in its published ``messages`` — the pronoun-resolver's entire job
        is resolving pronouns in the user's query, so an empty query makes the
        stage useless.

        Exercises the PRODUCTION delivery path: the user query is supplied as a
        TOP-LEVEL ``current_query`` workflow input (NOT node-keyed injection),
        so it reaches the composer only because the composer declares
        ``current_query`` as a parameter the runtime injector delivers — the
        same path a real ``WorkflowNode`` caller uses. RED pre-MED-1: the
        coreference stage was fed the phantom ``context`` port (no composer);
        the resolver received raw context_loader output, never a ``messages``
        list with the query. GREEN post-fix: the composer renders the query
        into the resolver's ``messages`` port.
        """
        node = ConversationalRAGNode(
            coreference_resolution=True,
            topic_tracking=True,
            enable_summarization=False,
        )
        # A grep-able query sentinel distinct from the doc sentinel.
        query = "How does its QUERY_SENTINEL_99 attention mechanism work?"
        docs = [{"content": self.DOC_TEXT}]

        # Structural guard (load-bearing): the composer MUST feed the resolver's
        # VALID `messages` port, NOT the phantom `context` port the pre-MED-1
        # wiring used. Removing the composer→messages edge (the production
        # wiring) regresses this assertion to RED.
        wf = node._create_workflow()  # type: ignore[attr-defined]
        feeders = [c for c in wf.connections if c.target_node == "coreference_resolver"]
        assert feeders, "coreference_resolver has no inbound connections"
        phantom = {"context", "conversation_context", "retrieval_results"}
        bad = [c for c in feeders if c.target_input in phantom]
        assert not bad, (
            "coreference_resolver still fed via phantom ports "
            f"{[c.target_input for c in bad]} — LLMAgentNode drops these silently."
        )
        msg_feeders = [
            c
            for c in feeders
            if c.target_input == "messages"
            and c.source_node == "coreference_messages_composer"
        ]
        assert msg_feeders, (
            "coreference_messages_composer is not wired to coreference_resolver's "
            f"`messages` port. feeders={[(c.source_node, c.target_input) for c in feeders]}"
        )

        # Behavioral guard: the actual user query reaches the resolver's
        # composed messages via the production top-level-input delivery path.
        results = self._run(node, query, docs)
        comp = results.get("coreference_messages_composer")
        assert isinstance(comp, dict), (
            "coreference_messages_composer node missing — coreference path not "
            f"wired. keys={list(results)}"
        )
        messages = comp["result"]["messages"]
        assert isinstance(messages, list) and messages, f"empty messages: {comp}"
        for m in messages:
            assert (
                isinstance(m, dict) and "role" in m and "content" in m
            ), f"malformed message (not OpenAI {{role,content}} shape): {m!r}"

        blob = "\n".join(str(m.get("content", "")) for m in messages)
        # Load-bearing MED-1 assertion: the actual user query reached the
        # pronoun-resolver (pre-fix this was the empty "Query to resolve:\n").
        assert "QUERY_SENTINEL_99" in blob, (
            "user query did NOT reach the coreference_resolver's messages — the "
            f"pronoun-resolver received an empty query. messages={blob!r}"
        )

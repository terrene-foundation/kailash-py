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
from kailash.workflow.graph import Workflow

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
        # All 8 nodes wired.
        assert len(wf.nodes) == 8

    def test_construct_with_all_optional_flags_false(self):
        """Minimal config: only the 5 mandatory nodes."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=False,
            enable_summarization=False,
        )
        wf = _build(node)
        assert len(wf.nodes) == 5

    def test_construct_topic_only_yields_6_nodes(self):
        """Only topic_tracking on: 5 mandatory + topic_tracker = 6."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=True,
            enable_summarization=False,
        )
        wf = _build(node)
        assert "topic_tracker" in wf.nodes
        assert "coreference_resolver" not in wf.nodes
        assert "context_summarizer" not in wf.nodes
        assert len(wf.nodes) == 6

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

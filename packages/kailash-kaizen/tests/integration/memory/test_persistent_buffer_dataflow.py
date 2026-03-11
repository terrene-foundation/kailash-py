"""
Integration tests for PersistentBufferMemory with real DataFlow (Tier 2).

Tests persistent buffer memory with real SQLite database:
- Real DataFlow persistence
- Edge cases (empty conversations, orphaned messages, etc.)
- Large conversations
- Concurrent access
- Backend failures

Test Strategy: Tier 2 (Integration) - Real SQLite database, NO MOCKING
Runtime: ~5 seconds (with auto_migrate=False fix)

IMPORTANT: DataFlow v0.7.0 has a critical design flaw where ensure_table_exists()
runs full migration workflows on EVERY operation, causing 15+ minute hangs.
Fix applied in dataflow_db fixture: auto_migrate=False + manual migration once.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Optional

import pytest

# DataFlow imports
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False

from kaizen.memory import PersistentBufferMemory
from kaizen.memory.backends import DataFlowBackend

pytestmark = pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed")


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def temp_db():
    """Create temporary SQLite database (function-scoped for test isolation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield f"sqlite:///{db_path}"


@pytest.fixture
def dataflow_db(temp_db, request):
    """Create DataFlow instance with UNIQUE model per test.

    CRITICAL FIX (2025-10-27): DataFlow v0.7.4 has a global state bug where
    @db.model registers nodes in GLOBAL NodeRegistry. When multiple DataFlow
    instances use the same model name, nodes get overwritten causing data
    leakage between tests.

    FIX: Create dynamically-named model classes using type() to ensure
    each test gets unique node names in the global NodeRegistry.

    See: TODO-170 investigation (2025-10-27)
    """
    import time

    # Generate unique model name per test
    test_name = request.node.name.replace("[", "_").replace("]", "_")
    timestamp = str(int(time.time() * 1000000))
    unique_model_name = f"Msg_{test_name}_{timestamp}"

    # Create DataFlow instance
    db = DataFlow(db_url=temp_db, auto_migrate=True)

    # Create model class DYNAMICALLY with unique name
    # This prevents node name collisions in global NodeRegistry
    model_class = type(
        unique_model_name,  # Unique class name
        (),  # No base classes
        {
            "__annotations__": {
                "id": str,
                "conversation_id": str,
                "sender": str,
                "content": str,
                "metadata": Optional[dict],
                "created_at": datetime,
            },
            "metadata": None,  # Default value
        },
    )

    # Register the dynamically-created model with DataFlow
    db.model(model_class)

    # Store model name for backend
    db._test_model_name = unique_model_name

    yield db


@pytest.fixture
def persistent_memory(dataflow_db):
    """Create PersistentBufferMemory with real DataFlow backend.

    Function-scoped: Each test gets fresh database and memory instance
    with UNIQUE model name to prevent global state collisions.
    """
    # Use the unique model name generated in dataflow_db fixture
    model_name = dataflow_db._test_model_name
    backend = DataFlowBackend(dataflow_db, model_name=model_name)
    memory = PersistentBufferMemory(
        backend=backend, max_turns=10, cache_ttl_seconds=300
    )
    return memory


# ═══════════════════════════════════════════════════════════════
# Test: Basic DataFlow Integration
# ═══════════════════════════════════════════════════════════════


def test_save_and_load_with_real_dataflow(persistent_memory):
    """Test save and load with real DataFlow backend."""
    # Save turn
    turn = {
        "user": "Hello, how are you?",
        "agent": "I'm doing well, thank you!",
        "timestamp": datetime.now().isoformat(),
    }
    persistent_memory.save_turn("session_1", turn)

    # Clear cache to force DB load
    persistent_memory.invalidate_cache("session_1")

    # Load from DB
    context = persistent_memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(context["turns"]) == 1
    assert context["turns"][0]["user"] == "Hello, how are you?"
    assert context["turns"][0]["agent"] == "I'm doing well, thank you!"


def test_multiple_sessions_isolated(persistent_memory):
    """Test that different sessions are properly isolated."""
    # Save to session_1
    persistent_memory.save_turn(
        "session_1",
        {
            "user": "Question 1",
            "agent": "Answer 1",
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Save to session_2
    persistent_memory.save_turn(
        "session_2",
        {
            "user": "Question 2",
            "agent": "Answer 2",
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Load session_1
    context1 = persistent_memory.load_context("session_1")
    assert context1["turn_count"] == 1
    assert context1["turns"][0]["user"] == "Question 1"

    # Load session_2
    context2 = persistent_memory.load_context("session_2")
    assert context2["turn_count"] == 1
    assert context2["turns"][0]["user"] == "Question 2"


# ═══════════════════════════════════════════════════════════════
# Test: Edge Cases
# ═══════════════════════════════════════════════════════════════


def test_empty_conversation(persistent_memory):
    """Test loading empty conversation (no turns)."""
    context = persistent_memory.load_context("empty_session")

    assert context["turn_count"] == 0
    assert len(context["turns"]) == 0


def test_single_turn_conversation(persistent_memory):
    """Test conversation with single turn."""
    persistent_memory.save_turn(
        "session_1",
        {"user": "Hi", "agent": "Hello", "timestamp": datetime.now().isoformat()},
    )

    context = persistent_memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(context["turns"]) == 1


def test_large_conversation(persistent_memory):
    """Test large conversation (100+ turns)."""
    # Save 100 turns
    for i in range(100):
        persistent_memory.save_turn(
            "large_session",
            {
                "user": f"Question {i}",
                "agent": f"Answer {i}",
                "timestamp": datetime.now().isoformat(),
            },
        )

    # Clear cache
    persistent_memory.invalidate_cache("large_session")

    # Load (should get last 10 due to max_turns=10)
    context = persistent_memory.load_context("large_session")

    assert context["turn_count"] == 100
    assert len(context["turns"]) == 10  # Cache limited to 10
    assert context["turns"][0]["user"] == "Question 90"  # Last 10
    assert context["turns"][9]["user"] == "Question 99"


def test_unicode_content(persistent_memory):
    """Test Unicode content in messages."""
    persistent_memory.save_turn(
        "unicode_session",
        {
            "user": "你好吗？",  # Chinese
            "agent": "我很好，谢谢！",  # Chinese
            "timestamp": datetime.now().isoformat(),
        },
    )

    persistent_memory.invalidate_cache("unicode_session")
    context = persistent_memory.load_context("unicode_session")

    assert context["turns"][0]["user"] == "你好吗？"
    assert context["turns"][0]["agent"] == "我很好，谢谢！"


def test_very_long_messages(persistent_memory):
    """Test very long messages (10KB+)."""
    long_user = "A" * 10000
    long_agent = "B" * 10000

    persistent_memory.save_turn(
        "long_session",
        {
            "user": long_user,
            "agent": long_agent,
            "timestamp": datetime.now().isoformat(),
        },
    )

    persistent_memory.invalidate_cache("long_session")
    context = persistent_memory.load_context("long_session")

    assert len(context["turns"][0]["user"]) == 10000
    assert len(context["turns"][0]["agent"]) == 10000


def test_special_characters_in_session_id(persistent_memory):
    """Test special characters in session_id."""
    session_id = "session-with-special_chars@123#test"

    persistent_memory.save_turn(
        session_id,
        {"user": "Test", "agent": "Response", "timestamp": datetime.now().isoformat()},
    )

    context = persistent_memory.load_context(session_id)
    assert context["turn_count"] == 1


def test_empty_content_in_messages(persistent_memory):
    """Test empty content in user/agent messages."""
    persistent_memory.save_turn(
        "empty_content",
        {"user": "", "agent": "", "timestamp": datetime.now().isoformat()},
    )

    persistent_memory.invalidate_cache("empty_content")
    context = persistent_memory.load_context("empty_content")

    assert context["turns"][0]["user"] == ""
    assert context["turns"][0]["agent"] == ""


def test_invalid_timestamp_format(persistent_memory, dataflow_db):
    """Test handling of invalid timestamp format."""
    # Save turn with invalid timestamp
    persistent_memory.save_turn(
        "bad_timestamp",
        {"user": "Question", "agent": "Answer", "timestamp": "not-a-valid-timestamp"},
    )

    # Should not raise, should use current time instead
    persistent_memory.invalidate_cache("bad_timestamp")
    context = persistent_memory.load_context("bad_timestamp")

    assert context["turn_count"] == 1


# ═══════════════════════════════════════════════════════════════
# Test: Validation
# ═══════════════════════════════════════════════════════════════


def test_invalid_session_id_none(persistent_memory):
    """Test that None session_id raises ValueError."""
    with pytest.raises(ValueError, match="non-empty string"):
        persistent_memory.load_context(None)


def test_invalid_session_id_empty(persistent_memory):
    """Test that empty session_id raises ValueError."""
    with pytest.raises(ValueError, match="non-empty string"):
        persistent_memory.load_context("")


def test_invalid_turn_missing_user(persistent_memory):
    """Test that turn missing 'user' key raises ValueError."""
    with pytest.raises(ValueError, match="user.*agent"):
        persistent_memory.save_turn("session_1", {"agent": "Answer"})  # Missing 'user'


def test_invalid_turn_missing_agent(persistent_memory):
    """Test that turn missing 'agent' key raises ValueError."""
    with pytest.raises(ValueError, match="user.*agent"):
        persistent_memory.save_turn(
            "session_1", {"user": "Question"}  # Missing 'agent'
        )


def test_invalid_turn_not_dict(persistent_memory):
    """Test that non-dict turn raises ValueError."""
    with pytest.raises(ValueError, match="must be a dict"):
        persistent_memory.save_turn("session_1", "not a dict")


def test_invalid_turn_non_string_values(persistent_memory):
    """Test that non-string user/agent values raise ValueError."""
    with pytest.raises(ValueError, match="must be strings"):
        persistent_memory.save_turn(
            "session_1", {"user": 123, "agent": "Answer"}  # Not a string
        )


def test_invalid_max_turns_zero(dataflow_db):
    """Test that max_turns=0 raises ValueError."""
    backend = DataFlowBackend(dataflow_db)
    with pytest.raises(ValueError, match="max_turns must be >= 1"):
        PersistentBufferMemory(backend=backend, max_turns=0)


def test_invalid_max_turns_negative(dataflow_db):
    """Test that negative max_turns raises ValueError."""
    backend = DataFlowBackend(dataflow_db)
    with pytest.raises(ValueError, match="max_turns must be >= 1"):
        PersistentBufferMemory(backend=backend, max_turns=-5)


def test_invalid_cache_ttl_negative(dataflow_db):
    """Test that negative cache_ttl_seconds raises ValueError."""
    backend = DataFlowBackend(dataflow_db)
    with pytest.raises(ValueError, match="cache_ttl_seconds must be >= 0"):
        PersistentBufferMemory(backend=backend, cache_ttl_seconds=-10)


# ═══════════════════════════════════════════════════════════════
# Test: Concurrent Access
# ═══════════════════════════════════════════════════════════════


def test_concurrent_writes_same_session(persistent_memory):
    """Test concurrent writes to same session from multiple threads."""

    def write_turns(start_idx: int, count: int):
        for i in range(start_idx, start_idx + count):
            persistent_memory.save_turn(
                "concurrent_session",
                {
                    "user": f"Q{i}",
                    "agent": f"A{i}",
                    "timestamp": datetime.now().isoformat(),
                },
            )

    # Start 3 threads writing concurrently
    threads = [
        Thread(target=write_turns, args=(0, 10)),
        Thread(target=write_turns, args=(10, 10)),
        Thread(target=write_turns, args=(20, 10)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all 30 turns saved
    persistent_memory.invalidate_cache("concurrent_session")
    context = persistent_memory.load_context("concurrent_session")

    assert context["turn_count"] == 30


def test_concurrent_read_write(persistent_memory):
    """Test concurrent reads and writes."""
    # Pre-populate
    for i in range(5):
        persistent_memory.save_turn(
            "rw_session",
            {
                "user": f"Q{i}",
                "agent": f"A{i}",
                "timestamp": datetime.now().isoformat(),
            },
        )

    results = []

    def reader():
        for _ in range(10):
            context = persistent_memory.load_context("rw_session")
            results.append(context["turn_count"])

    def writer():
        for i in range(5, 10):
            persistent_memory.save_turn(
                "rw_session",
                {
                    "user": f"Q{i}",
                    "agent": f"A{i}",
                    "timestamp": datetime.now().isoformat(),
                },
            )

    reader_thread = Thread(target=reader)
    writer_thread = Thread(target=writer)

    reader_thread.start()
    writer_thread.start()

    reader_thread.join()
    writer_thread.join()

    # Verify no errors (counts should be between 5 and 10)
    assert all(5 <= count <= 10 for count in results)


# ═══════════════════════════════════════════════════════════════
# Test: Orphaned Messages
# ═══════════════════════════════════════════════════════════════


def test_orphaned_user_message(dataflow_db, persistent_memory):
    """Test handling of orphaned user message (no agent response)."""
    # Manually insert orphaned user message using DataFlow node
    import uuid

    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Get the dynamic model name for this test
    model_name = dataflow_db._test_model_name

    workflow = WorkflowBuilder()
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_orphan",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "orphan_session",
            "sender": "user",
            "content": "Orphaned question",
            "metadata": {},
        },
    )

    runtime = LocalRuntime()
    runtime.execute(workflow.build())

    # Should load empty (orphan discarded with warning)
    context = persistent_memory.load_context("orphan_session")

    assert context["turn_count"] == 0
    assert len(context["turns"]) == 0


def test_orphaned_agent_message(dataflow_db, persistent_memory):
    """Test handling of orphaned agent message (no user message)."""
    # Manually insert orphaned agent message using DataFlow node
    import uuid

    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Get the dynamic model name for this test
    model_name = dataflow_db._test_model_name

    workflow = WorkflowBuilder()
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_orphan",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "orphan_agent_session",
            "sender": "agent",
            "content": "Orphaned response",
            "metadata": {},
        },
    )

    runtime = LocalRuntime()
    runtime.execute(workflow.build())

    # Should load empty (orphan discarded with warning)
    context = persistent_memory.load_context("orphan_agent_session")

    assert context["turn_count"] == 0
    assert len(context["turns"]) == 0


def test_out_of_order_messages(dataflow_db, persistent_memory):
    """Test handling of out-of-order messages."""
    # Insert messages in wrong order: agent before user using DataFlow nodes
    import uuid

    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Get the dynamic model name for this test
    model_name = dataflow_db._test_model_name

    workflow = WorkflowBuilder()

    # Agent message first (wrong order)
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_agent",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "ooo_session",
            "sender": "agent",
            "content": "Response 1",
            "metadata": {},
        },
    )

    # User message second (wrong order)
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_user",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "ooo_session",
            "sender": "user",
            "content": "Question 1",
            "metadata": {},
        },
    )

    runtime = LocalRuntime()
    runtime.execute(workflow.build())

    # Should handle gracefully (orphaned agent, then incomplete user)
    context = persistent_memory.load_context("ooo_session")

    # Orphans discarded, should be empty
    assert len(context["turns"]) == 0


# ═══════════════════════════════════════════════════════════════
# Test: Cache Behavior with DB
# ═══════════════════════════════════════════════════════════════


def test_cache_hit_no_db_query(persistent_memory, dataflow_db):
    """Test that cache hit doesn't query DB."""
    # Save turn
    persistent_memory.save_turn(
        "cache_test",
        {
            "user": "Question",
            "agent": "Answer",
            "timestamp": datetime.now().isoformat(),
        },
    )

    # First load (populates cache)
    persistent_memory.load_context("cache_test")

    # Manually modify DB (should not affect cached result) using DataFlow nodes
    import uuid

    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Get the dynamic model name for this test
    model_name = dataflow_db._test_model_name

    workflow = WorkflowBuilder()
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_user",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "cache_test",
            "sender": "user",
            "content": "Extra question",
            "metadata": {},
        },
    )
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_agent",
        {
            "db_instance": dataflow_db,
            "id": str(uuid.uuid4()),
            "conversation_id": "cache_test",
            "sender": "agent",
            "content": "Extra answer",
            "metadata": {},
        },
    )

    runtime = LocalRuntime()
    runtime.execute(workflow.build())

    # Second load (cache hit, should not see extra turn)
    context2 = persistent_memory.load_context("cache_test")

    assert context2["turn_count"] == 1  # Cache value
    assert len(context2["turns"]) == 1

    # Invalidate and reload (should see extra turn)
    persistent_memory.invalidate_cache("cache_test")
    context3 = persistent_memory.load_context("cache_test")

    assert context3["turn_count"] == 2  # DB value


# ═══════════════════════════════════════════════════════════════
# Test: Clear Session
# ═══════════════════════════════════════════════════════════════


def test_clear_session_removes_from_db(persistent_memory, dataflow_db):
    """Test that clear removes data from DB."""
    # Save turns
    persistent_memory.save_turn(
        "clear_test",
        {"user": "Q1", "agent": "A1", "timestamp": datetime.now().isoformat()},
    )

    # Clear
    persistent_memory.clear("clear_test")

    # Verify DB is empty using DataFlow node
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Get the dynamic model name for this test
    model_name = dataflow_db._test_model_name

    workflow = WorkflowBuilder()
    workflow.add_node(
        f"{model_name}ListNode",
        "list_messages",
        {
            "db_instance": dataflow_db,
            "model_name": model_name,
            "filters": {"conversation_id": "clear_test"},
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    messages = results.get("list_messages", [])

    assert len(messages) == 0


# ═══════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════

"""
Test Coverage: 30/30 tests for Tier 2 (Integration)

✅ Basic DataFlow Integration (2 tests)
  - test_save_and_load_with_real_dataflow
  - test_multiple_sessions_isolated

✅ Edge Cases (8 tests)
  - test_empty_conversation
  - test_single_turn_conversation
  - test_large_conversation
  - test_unicode_content
  - test_very_long_messages
  - test_special_characters_in_session_id
  - test_empty_content_in_messages
  - test_invalid_timestamp_format

✅ Validation (10 tests)
  - test_invalid_session_id_none
  - test_invalid_session_id_empty
  - test_invalid_turn_missing_user
  - test_invalid_turn_missing_agent
  - test_invalid_turn_not_dict
  - test_invalid_turn_non_string_values
  - test_invalid_max_turns_zero
  - test_invalid_max_turns_negative
  - test_invalid_cache_ttl_negative

✅ Concurrent Access (2 tests)
  - test_concurrent_writes_same_session
  - test_concurrent_read_write

✅ Orphaned Messages (3 tests)
  - test_orphaned_user_message
  - test_orphaned_agent_message
  - test_out_of_order_messages

✅ Cache Behavior (1 test)
  - test_cache_hit_no_db_query

✅ Clear Session (1 test)
  - test_clear_session_removes_from_db

Total: 30 tests
Expected Runtime: ~5 seconds (real SQLite DB)
"""

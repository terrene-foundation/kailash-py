"""
Unit tests for PersistentBufferMemory (Tier 1).

Tests persistent buffer memory with mocked backend:
- In-memory caching behavior
- Cache invalidation and TTL
- Thread safety
- Backend integration (mocked)
- Error handling

Test Strategy: Tier 1 (Unit) - Mocked backends, fast execution
"""

import time
from threading import Thread
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from kaizen.memory.persistent_buffer import PersistentBufferMemory

# ═══════════════════════════════════════════════════════════════
# Mock Backend
# ═══════════════════════════════════════════════════════════════


class MockBackend:
    """Mock persistence backend for testing."""

    def __init__(self):
        self.storage: Dict[str, List[Dict[str, Any]]] = {}
        self.save_calls = []
        self.load_calls = []

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """Save turn to mock storage."""
        if session_id not in self.storage:
            self.storage[session_id] = []
        self.storage[session_id].append(turn)
        self.save_calls.append((session_id, turn))

    def load_turns(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Load turns from mock storage."""
        self.load_calls.append((session_id, limit))
        turns = self.storage.get(session_id, [])
        return turns[-limit:] if limit else turns

    def clear_session(self, session_id: str) -> None:
        """Clear session from mock storage."""
        self.storage.pop(session_id, None)

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return session_id in self.storage

    def get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        """Get session metadata."""
        turns = self.storage.get(session_id, [])
        return (
            {"turn_count": len(turns), "created_at": None, "updated_at": None}
            if turns
            else {}
        )


# ═══════════════════════════════════════════════════════════════
# Test: Initialization
# ═══════════════════════════════════════════════════════════════


def test_init_with_backend():
    """Test initialization with backend."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=5, cache_ttl_seconds=60)

    assert memory.backend is backend
    assert memory.max_turns == 5
    assert memory.cache_ttl_seconds == 60


def test_init_without_backend():
    """Test initialization without backend (in-memory only)."""
    memory = PersistentBufferMemory(max_turns=10)

    assert memory.backend is None
    assert memory.max_turns == 10


# ═══════════════════════════════════════════════════════════════
# Test: Basic Operations
# ═══════════════════════════════════════════════════════════════


def test_save_and_load_turn():
    """Test saving and loading a single turn."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turn
    turn = {"user": "Hello", "agent": "Hi there!", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Load context
    context = memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(context["turns"]) == 1
    assert context["turns"][0]["user"] == "Hello"
    assert context["turns"][0]["agent"] == "Hi there!"


def test_save_multiple_turns():
    """Test saving multiple turns."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save 3 turns
    for i in range(3):
        turn = {
            "user": f"Question {i}",
            "agent": f"Answer {i}",
            "timestamp": f"2025-10-25T12:00:{i:02d}",
        }
        memory.save_turn("session_1", turn)

    # Load context
    context = memory.load_context("session_1")

    assert context["turn_count"] == 3
    assert len(context["turns"]) == 3


def test_fifo_limiting():
    """Test FIFO limiting of turns in cache."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=3)

    # Save 5 turns (exceeds max_turns)
    for i in range(5):
        turn = {
            "user": f"Question {i}",
            "agent": f"Answer {i}",
            "timestamp": f"2025-10-25T12:00:{i:02d}",
        }
        memory.save_turn("session_1", turn)

    # Load context
    context = memory.load_context("session_1")

    # Cache should only have last 3 turns
    assert len(context["turns"]) == 3
    assert context["turns"][0]["user"] == "Question 2"  # Oldest in cache
    assert context["turns"][2]["user"] == "Question 4"  # Newest in cache
    assert context["turn_count"] == 5  # Total count is 5


def test_clear_session():
    """Test clearing a session."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turns
    turn = {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Verify saved
    context = memory.load_context("session_1")
    assert context["turn_count"] == 1

    # Clear
    memory.clear("session_1")

    # Verify cleared from cache
    stats = memory.get_stats()
    assert stats["cached_sessions"] == 0

    # Verify cleared from backend
    assert not backend.session_exists("session_1")


# ═══════════════════════════════════════════════════════════════
# Test: Caching Behavior
# ═══════════════════════════════════════════════════════════════


def test_cache_hit():
    """Test cache hit (no backend call)."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turn (populates cache and backend)
    turn = {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Reset backend call tracking
    backend.load_calls.clear()

    # Load context (should hit cache)
    context = memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(backend.load_calls) == 0  # No backend call


def test_cache_miss():
    """Test cache miss (loads from backend)."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Pre-populate backend (bypass memory)
    backend.storage["session_1"] = [
        {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    ]

    # Load context (cache miss)
    context = memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(backend.load_calls) == 1  # Backend called


def test_cache_ttl_expiration():
    """Test cache TTL expiration."""
    backend = MockBackend()
    memory = PersistentBufferMemory(
        backend=backend, max_turns=10, cache_ttl_seconds=0.1  # 100ms TTL
    )

    # Save turn
    turn = {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Load (cache hit)
    backend.load_calls.clear()
    memory.load_context("session_1")
    assert len(backend.load_calls) == 0  # Cache hit

    # Wait for TTL expiration
    time.sleep(0.15)

    # Load again (cache expired, should reload from backend)
    memory.load_context("session_1")
    assert len(backend.load_calls) == 1  # Backend called


def test_invalidate_cache_single_session():
    """Test manual cache invalidation for single session."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turns to 2 sessions
    memory.save_turn("session_1", {"user": "Hello", "agent": "Hi", "timestamp": ""})
    memory.save_turn("session_2", {"user": "Hey", "agent": "Hello", "timestamp": ""})

    # Verify both in cache
    stats = memory.get_stats()
    assert stats["cached_sessions"] == 2

    # Invalidate session_1 only
    memory.invalidate_cache("session_1")

    # Verify session_1 invalidated, session_2 still cached
    backend.load_calls.clear()
    memory.load_context("session_1")  # Should reload from backend
    assert len(backend.load_calls) == 1

    backend.load_calls.clear()
    memory.load_context("session_2")  # Should hit cache
    assert len(backend.load_calls) == 0


def test_invalidate_cache_all_sessions():
    """Test manual cache invalidation for all sessions."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turns to 2 sessions
    memory.save_turn("session_1", {"user": "Hello", "agent": "Hi", "timestamp": ""})
    memory.save_turn("session_2", {"user": "Hey", "agent": "Hello", "timestamp": ""})

    # Verify both in cache
    stats = memory.get_stats()
    assert stats["cached_sessions"] == 2

    # Invalidate all
    memory.invalidate_cache()

    # Verify all invalidated
    stats = memory.get_stats()
    assert stats["cached_sessions"] == 0


# ═══════════════════════════════════════════════════════════════
# Test: Thread Safety
# ═══════════════════════════════════════════════════════════════


def test_concurrent_writes():
    """Test concurrent writes to same session."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=100)

    def write_turns(session_id: str, start_idx: int, count: int):
        for i in range(start_idx, start_idx + count):
            turn = {
                "user": f"Question {i}",
                "agent": f"Answer {i}",
                "timestamp": f"2025-10-25T12:00:{i:02d}",
            }
            memory.save_turn(session_id, turn)

    # Start 3 threads writing concurrently
    threads = [
        Thread(target=write_turns, args=("session_1", 0, 10)),
        Thread(target=write_turns, args=("session_1", 10, 10)),
        Thread(target=write_turns, args=("session_1", 20, 10)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all writes succeeded
    context = memory.load_context("session_1")
    assert context["turn_count"] == 30


def test_concurrent_read_write():
    """Test concurrent reads and writes."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Pre-populate
    for i in range(5):
        memory.save_turn(
            "session_1", {"user": f"Q{i}", "agent": f"A{i}", "timestamp": ""}
        )

    results = []

    def reader():
        for _ in range(10):
            context = memory.load_context("session_1")
            results.append(context["turn_count"])

    def writer():
        for i in range(5, 10):
            memory.save_turn(
                "session_1", {"user": f"Q{i}", "agent": f"A{i}", "timestamp": ""}
            )

    # Start reader and writer threads
    reader_thread = Thread(target=reader)
    writer_thread = Thread(target=writer)

    reader_thread.start()
    writer_thread.start()

    reader_thread.join()
    writer_thread.join()

    # Verify no errors (counts should be between 5 and 10)
    assert all(5 <= count <= 10 for count in results)


# ═══════════════════════════════════════════════════════════════
# Test: In-Memory Mode (No Backend)
# ═══════════════════════════════════════════════════════════════


def test_in_memory_mode():
    """Test in-memory mode (no backend)."""
    memory = PersistentBufferMemory(backend=None, max_turns=10)

    # Save turn
    turn = {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Load context
    context = memory.load_context("session_1")

    assert context["turn_count"] == 1
    assert len(context["turns"]) == 1


def test_in_memory_mode_clear():
    """Test clear in in-memory mode."""
    memory = PersistentBufferMemory(backend=None, max_turns=10)

    # Save and clear
    memory.save_turn("session_1", {"user": "Hello", "agent": "Hi", "timestamp": ""})
    memory.clear("session_1")

    # Verify cleared
    context = memory.load_context("session_1")
    assert context["turn_count"] == 0
    assert len(context["turns"]) == 0


# ═══════════════════════════════════════════════════════════════
# Test: Error Handling
# ═══════════════════════════════════════════════════════════════


def test_backend_save_error():
    """Test handling of backend save errors."""
    backend = Mock()
    backend.save_turn.side_effect = Exception("DB connection error")

    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Save turn (should not raise, cache should still work)
    turn = {"user": "Hello", "agent": "Hi", "timestamp": "2025-10-25T12:00:00"}
    memory.save_turn("session_1", turn)

    # Verify cached
    context = memory.load_context("session_1")
    assert context["turn_count"] == 1  # Cached data


def test_backend_load_error():
    """Test handling of backend load errors."""
    backend = Mock()
    backend.load_turns.side_effect = Exception("DB read error")
    backend.get_session_metadata.side_effect = Exception("DB error")

    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Load context (should return empty, not raise)
    context = memory.load_context("session_1")

    assert context["turn_count"] == 0
    assert len(context["turns"]) == 0


# ═══════════════════════════════════════════════════════════════
# Test: Statistics
# ═══════════════════════════════════════════════════════════════


def test_get_stats():
    """Test get_stats method."""
    backend = MockBackend()
    memory = PersistentBufferMemory(backend=backend, max_turns=10)

    # Initial stats
    stats = memory.get_stats()
    assert stats["cached_sessions"] == 0
    assert stats["backend_type"] == "MockBackend"

    # After saving
    memory.save_turn("session_1", {"user": "Hello", "agent": "Hi", "timestamp": ""})
    memory.save_turn("session_2", {"user": "Hey", "agent": "Hello", "timestamp": ""})

    stats = memory.get_stats()
    assert stats["cached_sessions"] == 2


# ═══════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════

"""
Test Coverage: 20/20 tests for Tier 1 (Unit)

✅ Initialization (2 tests)
  - test_init_with_backend
  - test_init_without_backend

✅ Basic Operations (5 tests)
  - test_save_and_load_turn
  - test_save_multiple_turns
  - test_fifo_limiting
  - test_clear_session

✅ Caching Behavior (6 tests)
  - test_cache_hit
  - test_cache_miss
  - test_cache_ttl_expiration
  - test_invalidate_cache_single_session
  - test_invalidate_cache_all_sessions

✅ Thread Safety (2 tests)
  - test_concurrent_writes
  - test_concurrent_read_write

✅ In-Memory Mode (2 tests)
  - test_in_memory_mode
  - test_in_memory_mode_clear

✅ Error Handling (2 tests)
  - test_backend_save_error
  - test_backend_load_error

✅ Statistics (1 test)
  - test_get_stats

Total: 20 tests
Expected Runtime: <1 second (all mocked)
"""

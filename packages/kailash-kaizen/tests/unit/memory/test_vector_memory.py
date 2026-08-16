"""
Unit tests for VectorMemory - semantic search over conversation history.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, uses mock embedder
- Tests semantic search retrieval
- Tests top_k parameter
- Tests custom embedder injection
"""

from typing import List

import pytest


class TestVectorMemoryBasics:
    """Test basic VectorMemory functionality."""

    def test_vector_memory_instantiation(self):
        """Test VectorMemory can be instantiated."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)
        assert memory is not None
        assert isinstance(memory, VectorMemory)

    def test_vector_memory_with_top_k(self):
        """Test VectorMemory can be instantiated with top_k."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(top_k=3, embedding_fn=hash_embedder_for_tests)
        assert memory.top_k == 3

    def test_vector_memory_default_top_k(self):
        """Test VectorMemory defaults to 5 for top_k."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)
        assert memory.top_k == 5

    def test_empty_vector_memory_loads_empty_context(self):
        """Test loading context from empty vector memory returns empty structure."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)
        context = memory.load_context("session1")

        assert isinstance(context, dict)
        assert "relevant_turns" in context
        assert "all_turns" in context
        assert context["relevant_turns"] == []
        assert context["all_turns"] == []


class TestVectorMemorySaving:
    """Test saving turns to vector memory."""

    def test_save_single_turn(self):
        """Test saving a single conversation turn."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)
        turn = {
            "user": "Hello",
            "agent": "Hi there!",
            "timestamp": "2025-10-02T10:00:00",
        }

        memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 1
        assert context["all_turns"][0]["user"] == "Hello"

    def test_save_multiple_turns(self):
        """Test saving multiple turns to vector store."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        turns = [
            {"user": "Hello", "agent": "Hi!"},
            {"user": "How are you?", "agent": "Good!"},
            {"user": "Great!", "agent": "Indeed!"},
        ]

        for turn in turns:
            memory.save_turn("session1", turn)

        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 3

    def test_turns_stored_with_embeddings(self):
        """Test that turns are embedded when saved."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        memory.save_turn(
            "session1", {"user": "Machine learning is cool", "agent": "Yes!"}
        )

        # Should have created embeddings internally
        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 1


class TestVectorMemorySemanticSearch:
    """Test semantic search functionality."""

    def test_search_with_query_returns_relevant_turns(self):
        """Test that semantic search returns relevant turns."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(top_k=2, embedding_fn=hash_embedder_for_tests)

        # Add diverse turns
        memory.save_turn(
            "session1", {"user": "Python programming", "agent": "Great language"}
        )
        memory.save_turn(
            "session1", {"user": "Machine learning", "agent": "AI is cool"}
        )
        memory.save_turn("session1", {"user": "What's for dinner?", "agent": "Pizza"})

        # Search for programming-related content
        context = memory.load_context("session1", query="coding in Python")

        # Should return relevant turns (implementation specific)
        assert "relevant_turns" in context
        assert len(context["relevant_turns"]) <= 2  # top_k=2

    def test_search_without_query_returns_empty_relevant(self):
        """Test that load_context without query doesn't do semantic search."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        memory.save_turn("session1", {"user": "Hello", "agent": "Hi"})

        # Load without query
        context = memory.load_context("session1")

        assert context["relevant_turns"] == []
        assert len(context["all_turns"]) == 1

    def test_top_k_limits_results(self):
        """Test that top_k parameter limits search results."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(top_k=2, embedding_fn=hash_embedder_for_tests)

        # Add 5 turns
        for i in range(5):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        # Search should return at most top_k results
        context = memory.load_context("session1", query="Message")

        assert len(context["relevant_turns"]) <= 2

    def test_custom_embedder_injection(self):
        """Test that custom embedder can be injected."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        def custom_embedder(text: str) -> List[float]:
            # Simple custom embedder - length-based vector
            return [float(len(text)), float(text.count(" "))]

        memory = VectorMemory(embedding_fn=custom_embedder)

        memory.save_turn("session1", {"user": "Short", "agent": "Ok"})
        memory.save_turn(
            "session1", {"user": "This is a longer message", "agent": "I see"}
        )

        context = memory.load_context("session1", query="medium length text")

        # Should have used custom embedder
        assert len(context["all_turns"]) == 2


class TestVectorMemorySessionIsolation:
    """Test that sessions are properly isolated."""

    def test_multiple_sessions_isolated(self):
        """Test that different sessions maintain separate vector stores."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        # Session 1
        memory.save_turn("session1", {"user": "Python", "agent": "Response 1"})
        memory.save_turn("session1", {"user": "Java", "agent": "Response 2"})

        # Session 2
        memory.save_turn("session2", {"user": "JavaScript", "agent": "Response A"})

        # Verify isolation
        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert len(context1["all_turns"]) == 2
        assert len(context2["all_turns"]) == 1
        assert "Python" in context1["all_turns"][0]["user"]
        assert "JavaScript" in context2["all_turns"][0]["user"]

    def test_clear_only_affects_target_session(self):
        """Test that clearing one session doesn't affect others."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        memory.save_turn("session1", {"user": "S1", "agent": "R1"})
        memory.save_turn("session2", {"user": "S2", "agent": "R2"})

        # Clear session1
        memory.clear("session1")

        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert len(context1["all_turns"]) == 0
        assert len(context2["all_turns"]) == 1


class TestVectorMemoryClear:
    """Test VectorMemory clear functionality."""

    def test_clear_removes_all_turns(self):
        """Test that clear removes all conversation history and embeddings."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        # Add multiple turns
        for i in range(5):
            memory.save_turn(
                "session1", {"user": f"Message {i}", "agent": f"Response {i}"}
            )

        # Verify turns exist
        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 5

        # Clear
        memory.clear("session1")

        # Verify empty
        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 0
        assert len(context["relevant_turns"]) == 0

    def test_clear_nonexistent_session_no_error(self):
        """Test clearing nonexistent session doesn't raise error."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)
        memory.clear("nonexistent_session")

        context = memory.load_context("nonexistent_session")
        assert len(context["all_turns"]) == 0

    def test_turns_can_be_added_after_clear(self):
        """Test that new turns can be added after clearing."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        # Add, clear, add again
        memory.save_turn("session1", {"user": "Before", "agent": "Response"})
        memory.clear("session1")
        memory.save_turn("session1", {"user": "After clear", "agent": "Response"})

        context = memory.load_context("session1")
        assert len(context["all_turns"]) == 1
        assert context["all_turns"][0]["user"] == "After clear"


class TestVectorMemoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_query_string(self):
        """Test that empty query string doesn't trigger search."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        memory.save_turn("session1", {"user": "Hello", "agent": "Hi"})

        # Empty query should not trigger search
        context = memory.load_context("session1", query="")

        assert context["relevant_turns"] == []
        assert len(context["all_turns"]) == 1

    def test_search_returns_metadata(self):
        """Test that search results include full turn metadata."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        turn = {
            "user": "Python",
            "agent": "Great!",
            "timestamp": "2025-10-02T10:00:00",
            "metadata": {"custom": "data"},
        }

        memory.save_turn("session1", turn)

        context = memory.load_context("session1", query="Python programming")

        # If relevant_turns returned, should include all metadata
        if context["relevant_turns"]:
            assert "metadata" in context["relevant_turns"][0]

    def test_load_context_format_consistency(self):
        """Test that load_context always returns consistent format."""
        from kaizen.memory.vector import VectorMemory, hash_embedder_for_tests

        memory = VectorMemory(embedding_fn=hash_embedder_for_tests)

        # Empty session
        context1 = memory.load_context("empty_session")
        assert "relevant_turns" in context1
        assert "all_turns" in context1

        # Session with data
        memory.save_turn("session2", {"user": "Hello", "agent": "Hi"})
        context2 = memory.load_context("session2")
        assert "relevant_turns" in context2
        assert "all_turns" in context2

        # With query
        context3 = memory.load_context("session2", query="greeting")
        assert "relevant_turns" in context3
        assert "all_turns" in context3


class TestEmbeddingFnIsRequired:
    """#2174: the default path MUST NOT silently produce hash-derived vectors.

    ``embedding_fn`` used to default to ``VectorMemory._default_embedder``, an
    MD5-derived pseudo-embedder. Callers who omitted it got vectors of the
    correct shape with no semantic signal, so similarity search returned
    ranked results over hash noise — no raise, no log, nothing observable from
    the outside (``zero-tolerance.md`` Rule 2).
    """

    def test_omitting_embedding_fn_raises(self):
        from kaizen.config.providers import ConfigurationError
        from kaizen.memory.vector import VectorMemory

        with pytest.raises(ConfigurationError) as exc:
            VectorMemory()

        # The error must name the wiring, not merely complain.
        msg = str(exc.value)
        assert "embedding_fn" in msg
        assert "hash_embedder_for_tests" in msg

    def test_explicit_none_raises(self):
        """`embedding_fn=None` is the documented old spelling of the default."""
        from kaizen.config.providers import ConfigurationError
        from kaizen.memory.vector import VectorMemory

        with pytest.raises(ConfigurationError):
            VectorMemory(embedding_fn=None, top_k=5)

    def test_no_hash_embedder_attribute_survives_on_the_class(self):
        """The old default must not remain reachable as an instance method.

        Guards the regression where the raise is added but `_default_embedder`
        stays on the class, so a caller (or a merge) can re-wire it.
        """
        from kaizen.memory.vector import VectorMemory

        assert not hasattr(VectorMemory, "_default_embedder")

    def test_supplied_embedder_is_the_one_used(self):
        """A real embedder must be called; nothing may substitute for it."""
        from kaizen.memory.vector import VectorMemory

        calls = []

        def tracking_embedder(text):
            calls.append(text)
            # Deliberately unlike the hash embedder's 128-dim 0/1 output.
            return [0.5, 0.25, 0.125]

        memory = VectorMemory(embedding_fn=tracking_embedder)
        memory.save_turn("s1", {"user": "hello", "agent": "hi"})

        assert calls, "supplied embedding_fn was never called"
        stored = memory._stores["s1"]["embeddings"][0]
        assert stored == [0.5, 0.25, 0.125]

    def test_hash_embedder_for_tests_is_explicitly_named_and_shaped(self):
        """The stand-in stays available for tests, under an unmistakable name."""
        from kaizen.memory.vector import hash_embedder_for_tests

        vec = hash_embedder_for_tests("hello")
        assert len(vec) == 128
        assert all(v in (0.0, 1.0) for v in vec)
        # Deterministic, which is the only property tests may rely on.
        assert hash_embedder_for_tests("hello") == vec

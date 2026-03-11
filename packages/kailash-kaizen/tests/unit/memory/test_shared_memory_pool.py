"""
Tests for SharedMemoryPool - Shared insight storage for multi-agent collaboration.

This module tests the SharedMemoryPool class which provides a shared insight
storage mechanism for multiple agents to collaborate by reading and writing
insights to a common pool.

Test Coverage:
- Basic operations (write, read_all, clear)
- Insight validation (required fields)
- Statistics (insight count, agent count, tag distribution)
- Timestamp auto-generation
- Thread-safety (concurrent writes)
- Empty pool behavior

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 2: Shared Memory)
"""

from datetime import datetime
from threading import Thread

import pytest


class TestSharedMemoryPoolBasics:
    """Test basic SharedMemoryPool operations."""

    def test_empty_pool_read_all_returns_empty_list(self):
        """Test that reading from an empty pool returns an empty list."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insights = pool.read_all()

        assert insights == []

    def test_write_single_insight(self):
        """Test writing a single insight to the pool."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "analyzer",
            "content": "Customer complaint detected",
            "tags": ["customer", "complaint"],
            "importance": 0.9,
            "segment": "analysis",
            "timestamp": datetime.now().isoformat(),
        }

        pool.write_insight(insight)
        insights = pool.read_all()

        assert len(insights) == 1
        assert insights[0]["agent_id"] == "analyzer"
        assert insights[0]["content"] == "Customer complaint detected"

    def test_write_multiple_insights(self):
        """Test writing multiple insights to the pool."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Write 5 insights
        for i in range(5):
            insight = {
                "agent_id": f"agent_{i}",
                "content": f"Insight {i}",
                "tags": ["test"],
                "importance": 0.5 + (i * 0.1),
                "segment": "analysis",
            }
            pool.write_insight(insight)

        insights = pool.read_all()
        assert len(insights) == 5

    def test_read_all_returns_copy_not_reference(self):
        """Test that read_all returns a copy, not a reference to internal list."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "Test",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
        }
        pool.write_insight(insight)

        insights1 = pool.read_all()
        insights2 = pool.read_all()

        # Modify first result
        insights1.append({"agent_id": "fake"})

        # Second result should be unchanged
        assert len(insights2) == 1

    def test_clear_removes_all_insights(self):
        """Test that clear() removes all insights from the pool."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Add insights
        for i in range(3):
            pool.write_insight(
                {
                    "agent_id": f"agent_{i}",
                    "content": f"Insight {i}",
                    "tags": ["test"],
                    "importance": 0.5,
                    "segment": "test",
                }
            )

        assert len(pool.read_all()) == 3

        # Clear
        pool.clear()

        assert len(pool.read_all()) == 0


class TestSharedMemoryPoolValidation:
    """Test insight validation and auto-generation."""

    def test_insight_requires_agent_id(self):
        """Test that insights must have an agent_id."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "content": "Missing agent_id",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
        }

        with pytest.raises(ValueError, match="agent_id"):
            pool.write_insight(insight)

    def test_insight_requires_content(self):
        """Test that insights must have content."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
        }

        with pytest.raises(ValueError, match="content"):
            pool.write_insight(insight)

    def test_insight_requires_tags(self):
        """Test that insights must have tags."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "Missing tags",
            "importance": 0.5,
            "segment": "test",
        }

        with pytest.raises(ValueError, match="tags"):
            pool.write_insight(insight)

    def test_insight_requires_importance(self):
        """Test that insights must have importance."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "Missing importance",
            "tags": ["test"],
            "segment": "test",
        }

        with pytest.raises(ValueError, match="importance"):
            pool.write_insight(insight)

    def test_insight_requires_segment(self):
        """Test that insights must have segment."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "Missing segment",
            "tags": ["test"],
            "importance": 0.5,
        }

        with pytest.raises(ValueError, match="segment"):
            pool.write_insight(insight)

    def test_importance_must_be_between_0_and_1(self):
        """Test that importance must be in [0.0, 1.0] range."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Test too high
        insight_high = {
            "agent_id": "test",
            "content": "Test",
            "tags": ["test"],
            "importance": 1.5,
            "segment": "test",
        }

        with pytest.raises(ValueError, match="importance.*0.*1"):
            pool.write_insight(insight_high)

        # Test too low
        insight_low = {
            "agent_id": "test",
            "content": "Test",
            "tags": ["test"],
            "importance": -0.1,
            "segment": "test",
        }

        with pytest.raises(ValueError, match="importance.*0.*1"):
            pool.write_insight(insight_low)

    def test_timestamp_auto_generated_if_missing(self):
        """Test that timestamp is auto-generated if not provided."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "No timestamp",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
        }

        before = datetime.now()
        pool.write_insight(insight)
        after = datetime.now()

        insights = pool.read_all()
        assert len(insights) == 1
        assert "timestamp" in insights[0]

        # Parse timestamp and check it's between before and after
        ts = datetime.fromisoformat(insights[0]["timestamp"])
        assert before <= ts <= after

    def test_timestamp_preserved_if_provided(self):
        """Test that provided timestamp is preserved."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        custom_time = "2025-10-02T10:00:00"
        insight = {
            "agent_id": "test",
            "content": "Custom timestamp",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
            "timestamp": custom_time,
        }

        pool.write_insight(insight)
        insights = pool.read_all()

        assert insights[0]["timestamp"] == custom_time

    def test_metadata_optional_and_preserved(self):
        """Test that metadata field is optional but preserved if provided."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Without metadata
        insight1 = {
            "agent_id": "test1",
            "content": "No metadata",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
        }
        pool.write_insight(insight1)

        # With metadata
        insight2 = {
            "agent_id": "test2",
            "content": "With metadata",
            "tags": ["test"],
            "importance": 0.5,
            "segment": "test",
            "metadata": {"source": "api", "user_id": "123"},
        }
        pool.write_insight(insight2)

        insights = pool.read_all()
        assert len(insights) == 2
        assert "metadata" not in insights[0] or insights[0].get("metadata") == {}
        assert insights[1]["metadata"]["source"] == "api"


class TestSharedMemoryPoolStatistics:
    """Test pool statistics and reporting."""

    def test_get_stats_empty_pool(self):
        """Test statistics for an empty pool."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        stats = pool.get_stats()

        assert stats["insight_count"] == 0
        assert stats["agent_count"] == 0
        assert stats["tag_distribution"] == {}

    def test_get_stats_single_insight(self):
        """Test statistics with a single insight."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        pool.write_insight(
            {
                "agent_id": "analyzer",
                "content": "Test",
                "tags": ["customer", "complaint"],
                "importance": 0.9,
                "segment": "analysis",
            }
        )

        stats = pool.get_stats()

        assert stats["insight_count"] == 1
        assert stats["agent_count"] == 1
        assert stats["tag_distribution"]["customer"] == 1
        assert stats["tag_distribution"]["complaint"] == 1

    def test_get_stats_multiple_insights(self):
        """Test statistics with multiple insights from different agents."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Agent 1: 2 insights
        pool.write_insight(
            {
                "agent_id": "analyzer",
                "content": "Insight 1",
                "tags": ["customer", "complaint"],
                "importance": 0.9,
                "segment": "analysis",
            }
        )
        pool.write_insight(
            {
                "agent_id": "analyzer",
                "content": "Insight 2",
                "tags": ["customer"],
                "importance": 0.8,
                "segment": "analysis",
            }
        )

        # Agent 2: 1 insight
        pool.write_insight(
            {
                "agent_id": "responder",
                "content": "Insight 3",
                "tags": ["solution", "customer"],
                "importance": 0.7,
                "segment": "planning",
            }
        )

        stats = pool.get_stats()

        assert stats["insight_count"] == 3
        assert stats["agent_count"] == 2  # 2 unique agents
        assert stats["tag_distribution"]["customer"] == 3
        assert stats["tag_distribution"]["complaint"] == 1
        assert stats["tag_distribution"]["solution"] == 1

    def test_get_stats_segment_distribution(self):
        """Test that stats include segment distribution."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        pool.write_insight(
            {
                "agent_id": "agent1",
                "content": "Analysis 1",
                "tags": ["test"],
                "importance": 0.5,
                "segment": "analysis",
            }
        )
        pool.write_insight(
            {
                "agent_id": "agent2",
                "content": "Analysis 2",
                "tags": ["test"],
                "importance": 0.5,
                "segment": "analysis",
            }
        )
        pool.write_insight(
            {
                "agent_id": "agent3",
                "content": "Planning 1",
                "tags": ["test"],
                "importance": 0.5,
                "segment": "planning",
            }
        )

        stats = pool.get_stats()

        assert "segment_distribution" in stats
        assert stats["segment_distribution"]["analysis"] == 2
        assert stats["segment_distribution"]["planning"] == 1


class TestSharedMemoryPoolThreadSafety:
    """Test thread-safety for concurrent agent writes."""

    def test_concurrent_writes_from_multiple_agents(self):
        """Test that multiple agents can write concurrently without data loss."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        def write_insights(agent_id: str, count: int):
            """Write multiple insights from a single agent."""
            for i in range(count):
                pool.write_insight(
                    {
                        "agent_id": agent_id,
                        "content": f"Insight {i} from {agent_id}",
                        "tags": ["concurrent"],
                        "importance": 0.5,
                        "segment": "test",
                    }
                )

        # Create 5 threads, each writing 10 insights
        threads = []
        for i in range(5):
            thread = Thread(target=write_insights, args=(f"agent_{i}", 10))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have 50 total insights (5 agents * 10 insights)
        insights = pool.read_all()
        assert len(insights) == 50

        # Check that all agents are represented
        stats = pool.get_stats()
        assert stats["agent_count"] == 5

    def test_concurrent_read_and_write(self):
        """Test that reads and writes can happen concurrently."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        results = []

        def write_insights():
            """Write insights continuously."""
            for i in range(20):
                pool.write_insight(
                    {
                        "agent_id": "writer",
                        "content": f"Insight {i}",
                        "tags": ["test"],
                        "importance": 0.5,
                        "segment": "test",
                    }
                )

        def read_insights():
            """Read insights continuously and store counts."""
            for _ in range(10):
                insights = pool.read_all()
                results.append(len(insights))

        # Start writer and reader threads
        writer = Thread(target=write_insights)
        reader = Thread(target=read_insights)

        writer.start()
        reader.start()

        writer.join()
        reader.join()

        # Should have recorded some reads
        assert len(results) > 0
        # Final count should be 20
        final_insights = pool.read_all()
        assert len(final_insights) == 20


class TestSharedMemoryPoolEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_tags_list_is_valid(self):
        """Test that empty tags list is allowed (but not recommended)."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        insight = {
            "agent_id": "test",
            "content": "No tags",
            "tags": [],
            "importance": 0.5,
            "segment": "test",
        }

        # Should not raise (tags key exists, even if empty)
        pool.write_insight(insight)
        insights = pool.read_all()
        assert len(insights) == 1

    def test_importance_boundary_values(self):
        """Test that importance=0.0 and importance=1.0 are valid."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()

        # Test 0.0
        pool.write_insight(
            {
                "agent_id": "test1",
                "content": "Zero importance",
                "tags": ["test"],
                "importance": 0.0,
                "segment": "test",
            }
        )

        # Test 1.0
        pool.write_insight(
            {
                "agent_id": "test2",
                "content": "Max importance",
                "tags": ["test"],
                "importance": 1.0,
                "segment": "test",
            }
        )

        insights = pool.read_all()
        assert len(insights) == 2

    def test_very_long_content(self):
        """Test that very long content is handled correctly."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        long_content = "A" * 10000  # 10k characters

        pool.write_insight(
            {
                "agent_id": "test",
                "content": long_content,
                "tags": ["long"],
                "importance": 0.5,
                "segment": "test",
            }
        )

        insights = pool.read_all()
        assert len(insights[0]["content"]) == 10000

    def test_special_characters_in_content(self):
        """Test that special characters in content are preserved."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        pool = SharedMemoryPool()
        special_content = (
            "Test with\nnewlines\tand\ttabs and 'quotes' and \"double quotes\""
        )

        pool.write_insight(
            {
                "agent_id": "test",
                "content": special_content,
                "tags": ["special"],
                "importance": 0.5,
                "segment": "test",
            }
        )

        insights = pool.read_all()
        assert insights[0]["content"] == special_content

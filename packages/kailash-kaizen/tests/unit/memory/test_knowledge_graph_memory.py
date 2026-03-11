"""
Unit tests for KnowledgeGraphMemory - entity extraction and relationship graph.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, uses mock entity extractor
- Tests entity extraction from conversation
- Tests relationship tracking
- Tests entity mention counting
- Tests custom extractor injection
"""

from typing import Any, Dict


class TestKnowledgeGraphMemoryBasics:
    """Test basic KnowledgeGraphMemory functionality."""

    def test_knowledge_graph_memory_instantiation(self):
        """Test KnowledgeGraphMemory can be instantiated."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()
        assert memory is not None
        assert isinstance(memory, KnowledgeGraphMemory)

    def test_empty_graph_loads_empty_context(self):
        """Test loading context from empty graph returns empty structure."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()
        context = memory.load_context("session1")

        assert isinstance(context, dict)
        assert "entities" in context
        assert "relationships" in context
        assert context["entities"] == {}
        assert context["relationships"] == []


class TestKnowledgeGraphEntityExtraction:
    """Test entity extraction functionality."""

    def test_save_turn_extracts_entities(self):
        """Test that saving a turn extracts entities."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # Turn with capitalized words (entities in mock extractor)
        memory.save_turn(
            "session1", {"user": "Alice met Bob in Paris", "agent": "That's nice!"}
        )

        context = memory.load_context("session1")
        entities = context["entities"]

        # Mock extractor extracts capitalized words
        assert "Alice" in entities
        assert "Bob" in entities
        assert "Paris" in entities

    def test_entity_mention_count_increments(self):
        """Test that entity mentions are counted across turns."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # First mention
        memory.save_turn("session1", {"user": "Alice is great", "agent": "Yes"})

        # Second mention
        memory.save_turn(
            "session1", {"user": "Alice is working on Python", "agent": "Cool"}
        )

        context = memory.load_context("session1")
        alice_entity = context["entities"]["Alice"]

        assert alice_entity["mentions"] == 2

    def test_multiple_entities_in_single_turn(self):
        """Test extracting multiple entities from a single turn."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        memory.save_turn("session1", {"user": "Alice Bob Charlie Diana", "agent": "Ok"})

        context = memory.load_context("session1")
        entities = context["entities"]

        assert len(entities) >= 4
        assert "Alice" in entities
        assert "Bob" in entities
        assert "Charlie" in entities
        assert "Diana" in entities

    def test_entity_type_preserved(self):
        """Test that entity type is preserved from extractor."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        memory.save_turn(
            "session1", {"user": "John works at Microsoft", "agent": "Great"}
        )

        context = memory.load_context("session1")

        # Check entity has type field (from mock extractor)
        if "John" in context["entities"]:
            assert "type" in context["entities"]["John"]


class TestKnowledgeGraphRelationships:
    """Test relationship extraction and tracking."""

    def test_relationships_extracted(self):
        """Test that relationships are extracted from conversation."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        def custom_extractor(text: str) -> Dict[str, Any]:
            """Extractor that returns relationships."""
            entities = {
                w: {"type": "ENTITY", "mentions": 1}
                for w in text.split()
                if w.istitle()
            }

            # Simple relationship extraction
            relationships = []
            if "Alice" in text and "Bob" in text:
                relationships.append(("Alice", "knows", "Bob"))

            return {"entities": entities, "relationships": relationships}

        memory = KnowledgeGraphMemory(entity_extractor=custom_extractor)

        memory.save_turn("session1", {"user": "Alice knows Bob", "agent": "Ok"})

        context = memory.load_context("session1")
        relationships = context["relationships"]

        assert len(relationships) > 0
        assert ("Alice", "knows", "Bob") in relationships

    def test_relationships_accumulate_across_turns(self):
        """Test that relationships accumulate over multiple turns."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        def custom_extractor(text: str) -> Dict[str, Any]:
            entities = {
                w: {"type": "ENTITY", "mentions": 1}
                for w in text.split()
                if w.istitle()
            }

            relationships = []
            if "Alice" in text and "Bob" in text:
                relationships.append(("Alice", "knows", "Bob"))
            if "Charlie" in text and "Diana" in text:
                relationships.append(("Charlie", "knows", "Diana"))

            return {"entities": entities, "relationships": relationships}

        memory = KnowledgeGraphMemory(entity_extractor=custom_extractor)

        memory.save_turn("session1", {"user": "Alice knows Bob", "agent": "Ok"})

        memory.save_turn("session1", {"user": "Charlie knows Diana", "agent": "Great"})

        context = memory.load_context("session1")
        relationships = context["relationships"]

        assert len(relationships) == 2
        assert ("Alice", "knows", "Bob") in relationships
        assert ("Charlie", "knows", "Diana") in relationships


class TestKnowledgeGraphCustomExtractor:
    """Test custom entity extractor injection."""

    def test_custom_extractor_used(self):
        """Test that custom extractor is used for entity extraction."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        def custom_extractor(text: str) -> Dict[str, Any]:
            # Extract email addresses as entities
            words = text.split()
            entities = {}
            for word in words:
                if "@" in word:
                    entities[word] = {"type": "EMAIL", "mentions": 1}

            return {"entities": entities, "relationships": []}

        memory = KnowledgeGraphMemory(entity_extractor=custom_extractor)

        memory.save_turn(
            "session1", {"user": "Contact alice@example.com", "agent": "Ok"}
        )

        context = memory.load_context("session1")
        entities = context["entities"]

        assert "alice@example.com" in entities
        assert entities["alice@example.com"]["type"] == "EMAIL"

    def test_default_extractor_extracts_capitalized_words(self):
        """Test that default extractor extracts capitalized words."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        memory.save_turn("session1", {"user": "Python is a Language", "agent": "Yes"})

        context = memory.load_context("session1")
        entities = context["entities"]

        # Default extractor should extract capitalized words
        assert "Python" in entities
        assert "Language" in entities


class TestKnowledgeGraphSessionIsolation:
    """Test that sessions are properly isolated."""

    def test_multiple_sessions_isolated(self):
        """Test that different sessions maintain separate graphs."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # Session 1
        memory.save_turn("session1", {"user": "Alice met Bob", "agent": "Ok"})

        # Session 2
        memory.save_turn("session2", {"user": "Charlie met Diana", "agent": "Great"})

        # Verify isolation
        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert "Alice" in context1["entities"]
        assert "Alice" not in context2["entities"]
        assert "Charlie" in context2["entities"]
        assert "Charlie" not in context1["entities"]

    def test_clear_only_affects_target_session(self):
        """Test that clearing one session doesn't affect others."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        memory.save_turn("session1", {"user": "Alice", "agent": "Hi"})
        memory.save_turn("session2", {"user": "Bob", "agent": "Hello"})

        # Clear session1
        memory.clear("session1")

        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert len(context1["entities"]) == 0
        assert len(context2["entities"]) > 0


class TestKnowledgeGraphClear:
    """Test KnowledgeGraphMemory clear functionality."""

    def test_clear_removes_entities_and_relationships(self):
        """Test that clear removes all graph data."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # Add entities
        for i in range(5):
            memory.save_turn("session1", {"user": f"Person{i} is here", "agent": "Ok"})

        # Verify data exists
        context = memory.load_context("session1")
        assert len(context["entities"]) > 0

        # Clear
        memory.clear("session1")

        # Verify empty
        context = memory.load_context("session1")
        assert len(context["entities"]) == 0
        assert len(context["relationships"]) == 0

    def test_clear_nonexistent_session_no_error(self):
        """Test clearing nonexistent session doesn't raise error."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()
        memory.clear("nonexistent_session")

        context = memory.load_context("nonexistent_session")
        assert len(context["entities"]) == 0

    def test_entities_can_be_added_after_clear(self):
        """Test that new entities can be added after clearing."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # Add, clear, add again
        memory.save_turn("session1", {"user": "Alice", "agent": "Hi"})
        memory.clear("session1")
        memory.save_turn("session1", {"user": "Bob", "agent": "Hello"})

        context = memory.load_context("session1")
        assert "Bob" in context["entities"]
        assert "Alice" not in context["entities"]


class TestKnowledgeGraphEdgeCases:
    """Test edge cases and error conditions."""

    def test_no_entities_in_turn(self):
        """Test handling turn with no extractable entities."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        memory.save_turn("session1", {"user": "hello there", "agent": "hi"})

        context = memory.load_context("session1")
        # Should work, just no entities extracted
        assert isinstance(context["entities"], dict)

    def test_entity_metadata_preserved(self):
        """Test that entity metadata from extractor is preserved."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        def custom_extractor(text: str) -> Dict[str, Any]:
            entities = {}
            if "Alice" in text:
                entities["Alice"] = {
                    "type": "PERSON",
                    "mentions": 1,
                    "metadata": {"age": 30, "role": "developer"},
                }
            return {"entities": entities, "relationships": []}

        memory = KnowledgeGraphMemory(entity_extractor=custom_extractor)

        memory.save_turn("session1", {"user": "Alice is working", "agent": "Ok"})

        context = memory.load_context("session1")
        alice = context["entities"]["Alice"]

        assert alice["metadata"]["age"] == 30
        assert alice["metadata"]["role"] == "developer"

    def test_load_context_format_consistency(self):
        """Test that load_context always returns consistent format."""
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory

        memory = KnowledgeGraphMemory()

        # Empty session
        context1 = memory.load_context("empty_session")
        assert "entities" in context1
        assert "relationships" in context1

        # Session with data
        memory.save_turn("session2", {"user": "Alice", "agent": "Hi"})
        context2 = memory.load_context("session2")
        assert "entities" in context2
        assert "relationships" in context2

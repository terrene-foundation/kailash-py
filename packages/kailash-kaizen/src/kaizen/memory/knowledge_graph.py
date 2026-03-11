"""
KnowledgeGraphMemory: Entity extraction and relationship graph.

This memory implementation builds a knowledge graph from conversation by
extracting entities (people, places, things) and relationships between them.

Example:
    >>> from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
    >>> memory = KnowledgeGraphMemory()
    >>> memory.save_turn("session1", {
    ...     "user": "Alice met Bob in Paris",
    ...     "agent": "That's interesting!"
    ... })
    >>> context = memory.load_context("session1")
    >>> print(context["entities"].keys())
    dict_keys(['Alice', 'Bob', 'Paris'])

Note: This is a Kaizen-owned implementation, inspired by LangChain's
ConversationKGMemory but NOT integrated with LangChain.
"""

from typing import Any, Callable, Dict, Optional

from kaizen.memory.conversation_base import KaizenMemory


class KnowledgeGraphMemory(KaizenMemory):
    """
    Entity extraction and relationship graph for conversation memory.

    Maintains a knowledge graph of entities and relationships extracted
    from conversation history. Entities are tracked with mention counts
    and metadata, while relationships capture connections between entities.

    Attributes:
        entity_extractor: Function to extract entities and relationships from text
        _graphs: Internal storage mapping session_id -> graph data
    """

    def __init__(
        self, entity_extractor: Optional[Callable[[str], Dict[str, Any]]] = None
    ):
        """
        Initialize KnowledgeGraphMemory.

        Args:
            entity_extractor: Optional custom entity extraction function that
                             takes text and returns a dict with:
                             - "entities": Dict[str, Dict] mapping entity names to attributes
                             - "relationships": List[Tuple[str, str, str]] of (entity1, relation, entity2)
                             If None, uses default mock extractor.
        """
        self.entity_extractor = entity_extractor or self._default_extractor
        self._graphs: Dict[str, Dict[str, Any]] = {}

    def _default_extractor(self, text: str) -> Dict[str, Any]:
        """
        Default mock entity extractor for testing.

        In production, this would use actual NER (Named Entity Recognition) like:
        - spaCy: nlp(text).ents
        - HuggingFace NER models
        - OpenAI function calling for entity extraction

        For testing, we extract capitalized words as entities.

        Args:
            text: Text to extract entities from

        Returns:
            Dictionary with "entities" and "relationships"
        """
        words = text.split()

        # Extract capitalized words as entities
        entities = {}
        for word in words:
            # Simple heuristic: capitalized words are entities
            # Remove punctuation
            clean_word = word.strip(".,!?;:")
            if clean_word and clean_word[0].isupper() and len(clean_word) > 1:
                if clean_word not in entities:
                    entities[clean_word] = {"type": "ENTITY", "mentions": 1}

        # No relationship extraction in default mock
        # (would require more sophisticated NLP)
        return {"entities": entities, "relationships": []}

    def load_context(self, session_id: str) -> Dict[str, Any]:
        """
        Load knowledge graph context for a specific session.

        Args:
            session_id: Unique identifier for the conversation session

        Returns:
            Dictionary with:
                - "entities": Dict mapping entity names to attributes (type, mentions, etc.)
                - "relationships": List of tuples (entity1, relation, entity2)
        """
        graph = self._graphs.get(session_id, {"entities": {}, "relationships": []})

        return {
            "entities": graph.get("entities", {}),
            "relationships": graph.get("relationships", []),
        }

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a conversation turn and extract entities/relationships.

        Entities are merged into the graph with mention counts incremented.
        Relationships are appended to the relationship list.

        Args:
            session_id: Unique identifier for the conversation session
            turn: Dictionary containing conversation turn data
        """
        # Initialize graph if it doesn't exist
        if session_id not in self._graphs:
            self._graphs[session_id] = {"entities": {}, "relationships": []}

        # Extract entities and relationships from turn
        turn_text = f"{turn.get('user', '')} {turn.get('agent', '')}"
        extracted = self.entity_extractor(turn_text)

        # Merge entities into graph
        for entity_name, entity_attrs in extracted.get("entities", {}).items():
            if entity_name in self._graphs[session_id]["entities"]:
                # Entity already exists - increment mention count
                self._graphs[session_id]["entities"][entity_name]["mentions"] += 1

                # Merge any new attributes (preserve existing)
                for key, value in entity_attrs.items():
                    if key != "mentions":  # Don't overwrite mention count
                        if key not in self._graphs[session_id]["entities"][entity_name]:
                            self._graphs[session_id]["entities"][entity_name][
                                key
                            ] = value
            else:
                # New entity - add to graph
                self._graphs[session_id]["entities"][entity_name] = entity_attrs

        # Add relationships to graph
        for relationship in extracted.get("relationships", []):
            self._graphs[session_id]["relationships"].append(relationship)

    def clear(self, session_id: str) -> None:
        """
        Clear all knowledge graph data for a specific session.

        Removes all entities and relationships.

        Args:
            session_id: Unique identifier for the conversation session
        """
        if session_id in self._graphs:
            del self._graphs[session_id]

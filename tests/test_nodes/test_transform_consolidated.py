"""Consolidated tests for transform processor nodes."""

from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode,
    ContextFormatterNode,
    QueryTextWrapperNode,
)
from kailash.nodes.transform.processors import DataTransformer, Filter, Map, Sort
from kailash.sdk_exceptions import NodeExecutionError


class TestTransformNodes:
    """Consolidated tests for all transform nodes."""

    def test_filter_operations(self):
        """Test Filter node with various operations."""
        # Basic numeric filtering
        node = Filter(data=[1, 2, 3, 4, 5], operator=">", value=3)
        result = node.execute()
        assert result["filtered_data"] == [4, 5]

        # Field-based filtering
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        node = Filter(data=data, field="age", operator=">", value=27)
        result = node.execute()
        assert len(result["filtered_data"]) == 1

        # Edge cases
        node = Filter(data=[], operator=">", value=5)
        assert node.execute()["filtered_data"] == []

        # Test invalid operator - Filter returns False for all items on error
        result = Filter(data=[1, 2], operator="invalid", value=1).execute()
        assert (
            result["filtered_data"] == []
        )  # All items filtered out due to invalid operator

    def test_map_operations(self):
        """Test Map node with various operations."""
        # Simple multiplication
        node = Map(data=[1, 2, 3], operation="multiply", value=2)
        result = node.execute()
        assert result["mapped_data"] == [2, 4, 6]

        # String operations
        node = Map(data=["hello", "world"], operation="upper")
        result = node.execute()
        assert result["mapped_data"] == ["HELLO", "WORLD"]

        # Field operations
        data = [{"price": 10}, {"price": 20}]
        node = Map(data=data, field="price", operation="multiply", value=1.1)
        result = node.execute()
        assert len(result["mapped_data"]) == 2

    def test_sort_operations(self):
        """Test Sort node with various operations."""
        # Basic sorting
        node = Sort(data=[3, 1, 4, 1, 5], ascending=True)
        result = node.execute()
        assert result["sorted_data"] == [1, 1, 3, 4, 5]

        # Field-based sorting
        data = [{"name": "Charlie", "age": 35}, {"name": "Alice", "age": 30}]
        node = Sort(data=data, field="age", ascending=True)
        result = node.execute()
        assert result["sorted_data"][0]["name"] == "Alice"

    def test_data_transformer(self):
        """Test DataTransformer node."""
        data = [{"name": "Alice", "score": 85}, {"name": "Bob", "score": 92}]

        # Test with simple transformation - filter scores > 90
        transformer = DataTransformer(
            transformations=["[item for item in result if item['score'] > 90]"]
        )
        result = transformer.execute(data=data)
        assert len(result["result"]) == 1
        assert result["result"][0]["name"] == "Bob"

    def test_hierarchical_chunker(self):
        """Test HierarchicalChunkerNode."""
        documents = [
            {
                "id": "doc1",
                "title": "Test Document",
                "content": "This is a test document. It has multiple sentences. Each sentence should be chunked appropriately.",
            }
        ]

        node = HierarchicalChunkerNode(chunk_size=50, overlap=10)
        result = node.execute(documents=documents)

        assert "chunks" in result
        assert len(result["chunks"]) > 0
        assert isinstance(result["chunks"], list)
        assert result["chunks"][0]["document_id"] == "doc1"

    def test_formatters(self):
        """Test formatting nodes."""
        # Test chunk text extractor
        chunks = [
            {"content": "First chunk", "metadata": {"source": "doc1"}},
            {"content": "Second chunk", "metadata": {"source": "doc1"}},
        ]

        extractor = ChunkTextExtractorNode()
        result = extractor.execute(chunks=chunks)
        assert "input_texts" in result
        assert len(result["input_texts"]) == 2
        assert result["input_texts"][0] == "First chunk"

        # Test query wrapper
        wrapper = QueryTextWrapperNode()
        result = wrapper.execute(query="What is AI?")
        assert "input_texts" in result
        assert len(result["input_texts"]) == 1
        assert result["input_texts"][0] == "What is AI?"

        # Test context formatter
        relevant_chunks = [
            {"content": "context 1", "document_title": "Doc1", "relevance_score": 0.95},
            {"content": "context 2", "document_title": "Doc2", "relevance_score": 0.85},
        ]
        formatter = ContextFormatterNode()
        result = formatter.execute(query="test query", relevant_chunks=relevant_chunks)
        assert "formatted_prompt" in result
        assert "messages" in result
        assert "context" in result

    def test_edge_cases_and_errors(self):
        """Test edge cases and error conditions across transform nodes."""
        # Empty data handling
        assert Filter(data=[], operator=">", value=1).execute()["filtered_data"] == []
        assert Map(data=[], operation="upper").execute()["mapped_data"] == []
        assert Sort(data=[], ascending=True).execute()["sorted_data"] == []

        # Invalid operations - Map raises NodeExecutionError which wraps ValueError
        try:
            Map(data=[1, 2], operation="invalid_op").execute()
            assert False, "Should have raised an exception"
        except (ValueError, NodeExecutionError):
            pass  # Either exception is acceptable

        # Empty documents handling in hierarchical chunker
        chunker = HierarchicalChunkerNode(chunk_size=10)
        result = chunker.execute(documents=[])
        assert result["chunks"] == []

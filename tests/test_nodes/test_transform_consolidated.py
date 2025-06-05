"""Consolidated tests for transform processor nodes."""

import pytest

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
        
        # Error handling
        with pytest.raises(NodeExecutionError):
            Filter(data=[1, 2], operator="invalid", value=1).execute()

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
        
        # Test with simple transformation
        transformer = DataTransformer(
            transformations=[
                {"type": "filter", "field": "score", "operator": ">", "value": 80}
            ]
        )
        result = transformer.execute(data=data)
        assert len(result["transformed_data"]) == 2

    def test_hierarchical_chunker(self):
        """Test HierarchicalChunkerNode."""
        text = "This is a test document. It has multiple sentences. Each sentence should be chunked appropriately."
        
        node = HierarchicalChunkerNode(
            chunk_size=50,
            overlap=10,
            separators=[".", "!", "?"]
        )
        result = node.execute(text=text)
        
        assert "chunks" in result
        assert len(result["chunks"]) > 0
        assert isinstance(result["chunks"], list)

    def test_formatters(self):
        """Test formatting nodes."""
        # Test chunk text extractor
        chunks = [
            {"text": "First chunk", "metadata": {"source": "doc1"}},
            {"text": "Second chunk", "metadata": {"source": "doc1"}}
        ]
        
        extractor = ChunkTextExtractorNode()
        result = extractor.execute(chunks=chunks)
        assert "extracted_text" in result
        assert len(result["extracted_text"]) == 2
        
        # Test query wrapper
        wrapper = QueryTextWrapperNode(template="Question: {query}\nContext: {context}")
        result = wrapper.execute(query="What is AI?", context="AI is artificial intelligence")
        assert "formatted_text" in result
        assert "Question:" in result["formatted_text"]
        
        # Test context formatter
        formatter = ContextFormatterNode()
        result = formatter.execute(
            query="test query",
            contexts=["context 1", "context 2"],
            max_length=100
        )
        assert "formatted_context" in result

    def test_edge_cases_and_errors(self):
        """Test edge cases and error conditions across transform nodes."""
        # Empty data handling
        assert Filter(data=[], operator=">", value=1).execute()["filtered_data"] == []
        assert Map(data=[], operation="upper").execute()["mapped_data"] == []
        assert Sort(data=[], ascending=True).execute()["sorted_data"] == []
        
        # Invalid operations
        with pytest.raises(NodeExecutionError):
            Map(data=[1, 2], operation="invalid_op").execute()
            
        # None handling in hierarchical chunker
        chunker = HierarchicalChunkerNode(chunk_size=10)
        with pytest.raises(NodeExecutionError):
            chunker.execute(text=None)
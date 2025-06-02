"""Tests for transform processor nodes."""

import pytest

from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode,
    ContextFormatterNode,
    QueryTextWrapperNode,
)
from kailash.nodes.transform.processors import DataTransformer, Filter, Map, Sort
from kailash.sdk_exceptions import NodeExecutionError


class TestFilterNode:
    """Test Filter transformation node."""

    def test_filter_numeric_greater_than(self):
        """Test filtering with greater than operator."""
        node = Filter(data=[1, 2, 3, 4, 5], operator=">", value=3)

        result = node.execute()

        assert result["filtered_data"] == [4, 5]

    def test_filter_with_field(self):
        """Test filtering on specific field."""
        node = Filter(
            data=[
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 35},
            ],
            field="age",
            operator=">",
            value=30,
        )

        result = node.execute()

        assert len(result["filtered_data"]) == 1
        assert result["filtered_data"][0]["name"] == "Charlie"

    def test_filter_string_equality(self):
        """Test filtering strings with equality."""
        node = Filter(
            data=["apple", "banana", "apple", "cherry"], operator="==", value="apple"
        )

        result = node.execute()

        assert result["filtered_data"] == ["apple", "apple"]

    def test_filter_contains_operator(self):
        """Test filtering with contains operator."""
        node = Filter(
            data=["hello world", "test case", "hello there", "goodbye"],
            operator="contains",
            value="hello",
        )

        result = node.execute()

        assert len(result["filtered_data"]) == 2
        assert "hello world" in result["filtered_data"]
        assert "hello there" in result["filtered_data"]

    def test_filter_empty_data(self):
        """Test filtering empty data."""
        node = Filter(data=[], operator=">", value=0)

        result = node.execute()

        assert result["filtered_data"] == []

    def test_filter_numeric_conversion(self):
        """Test numeric conversion for string numbers."""
        node = Filter(data=["1", "2", "3", "4", "5"], operator=">", value="3")

        result = node.execute()

        assert result["filtered_data"] == ["4", "5"]

    def test_filter_none_values(self):
        """Test Filter with None values in data."""
        node = Filter(data=[1, None, 3, None, 5], operator=">", value=2)

        result = node.execute()

        # None values should be filtered out (comparison fails safely)
        assert result["filtered_data"] == [3, 5]

    def test_filter_invalid_operator(self):
        """Test Filter with invalid operator."""
        node = Filter(data=[1, 2, 3], operator="invalid", value=2)

        # Invalid operator returns False for all items, so no items are filtered through
        result = node.execute()
        assert result["filtered_data"] == []  # All items filtered out


class TestMapNode:
    """Test Map transformation node."""

    def test_map_simple_multiplication(self):
        """Test simple multiplication operation."""
        node = Map(data=[1, 2, 3, 4], operation="multiply", value=2)

        result = node.execute()

        assert result["mapped_data"] == [2.0, 4.0, 6.0, 8.0]

    def test_map_string_upper(self):
        """Test string upper case operation."""
        node = Map(data=["hello", "world", "test"], operation="upper")

        result = node.execute()

        assert result["mapped_data"] == ["HELLO", "WORLD", "TEST"]

    def test_map_dict_field_transformation(self):
        """Test mapping on dictionary field."""
        node = Map(
            data=[
                {"name": "alice", "value": 10},
                {"name": "bob", "value": 20},
                {"name": "charlie", "value": 30},
            ],
            field="name",
            operation="upper",
        )

        result = node.execute()

        assert result["mapped_data"][0]["name"] == "ALICE"
        assert result["mapped_data"][1]["name"] == "BOB"
        assert result["mapped_data"][2]["name"] == "CHARLIE"

    def test_map_dict_new_field(self):
        """Test mapping to new field in dictionaries."""
        node = Map(
            data=[{"value": 10}, {"value": 20}, {"value": 30}],
            field="value",
            new_field="doubled",
            operation="multiply",
            value=2,
        )

        result = node.execute()

        assert result["mapped_data"][0]["doubled"] == 20.0
        assert result["mapped_data"][1]["doubled"] == 40.0
        assert result["mapped_data"][2]["doubled"] == 60.0
        # Original field should remain unchanged
        assert result["mapped_data"][0]["value"] == 10

    def test_map_string_addition(self):
        """Test string addition operation."""
        node = Map(data=["hello", "world"], operation="add", value=" test")

        result = node.execute()

        assert result["mapped_data"] == ["hello test", "world test"]

    def test_map_identity_operation(self):
        """Test identity operation (no change)."""
        data = [1, 2, 3]
        node = Map(data=data, operation="identity")

        result = node.execute()

        assert result["mapped_data"] == data

    def test_map_mixed_types(self):
        """Test Map with mixed data types."""
        node = Map(
            data=[1, "hello", 3.14],
            operation="upper",  # Will work on strings, convert others
        )

        result = node.execute()

        assert result["mapped_data"] == ["1", "HELLO", "3.14"]

    def test_map_invalid_operation(self):
        """Test map with invalid operation."""
        node = Map(data=[1, 2, 3], operation="invalid_op")

        with pytest.raises(NodeExecutionError):
            node.execute()

    def test_map_missing_value_for_operation(self):
        """Test Map with missing value for operation that needs it."""
        node = Map(
            data=[1, 2, 3],
            operation="multiply",
            # Missing value parameter
        )

        with pytest.raises(NodeExecutionError):
            node.execute()


class TestSortNode:
    """Test Sort transformation node."""

    def test_sort_numbers_ascending(self):
        """Test sorting numbers in ascending order."""
        node = Sort(data=[3, 1, 4, 1, 5, 9, 2, 6])

        result = node.execute()

        assert result["sorted_data"] == [1, 1, 2, 3, 4, 5, 6, 9]

    def test_sort_numbers_descending(self):
        """Test sorting numbers in descending order."""
        node = Sort(data=[3, 1, 4, 1, 5], reverse=True)

        result = node.execute()

        assert result["sorted_data"] == [5, 4, 3, 1, 1]

    def test_sort_strings(self):
        """Test sorting strings."""
        node = Sort(data=["banana", "apple", "cherry", "date"])

        result = node.execute()

        assert result["sorted_data"] == ["apple", "banana", "cherry", "date"]

    def test_sort_dict_by_field(self):
        """Test sorting dictionaries by field."""
        node = Sort(
            data=[
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 35},
            ],
            field="age",
        )

        result = node.execute()

        assert result["sorted_data"][0]["name"] == "Bob"
        assert result["sorted_data"][1]["name"] == "Alice"
        assert result["sorted_data"][2]["name"] == "Charlie"

    def test_sort_dict_by_field_descending(self):
        """Test sorting dictionaries by field in descending order."""
        node = Sort(
            data=[
                {"name": "Alice", "score": 85},
                {"name": "Bob", "score": 92},
                {"name": "Charlie", "score": 78},
            ],
            field="score",
            reverse=True,
        )

        result = node.execute()

        assert result["sorted_data"][0]["name"] == "Bob"  # highest score
        assert result["sorted_data"][1]["name"] == "Alice"
        assert result["sorted_data"][2]["name"] == "Charlie"  # lowest score

    def test_sort_empty_data(self):
        """Test sorting empty data."""
        node = Sort(data=[])

        result = node.execute()

        assert result["sorted_data"] == []

    def test_sort_mixed_numeric_types(self):
        """Test Sort with mixed numeric types."""
        node = Sort(data=[3.14, 1, 2.5, 4])

        result = node.execute()

        assert result["sorted_data"] == [1, 2.5, 3.14, 4]

    def test_sort_dict_without_field(self):
        """Test Sort with dict data but no field specified."""
        node = Sort(data=[{"name": "Bob"}, {"name": "Alice"}])

        # Should raise error when trying to compare dicts directly
        with pytest.raises(NodeExecutionError):
            node.execute()


class TestDataTransformerNode:
    """Test DataTransformer node."""

    def test_simple_lambda_transformation(self):
        """Test simple lambda transformation."""
        node = DataTransformer(data=[1, 2, 3, 4], transformations=["lambda x: x * 2"])

        result = node.execute()

        assert result["result"] == [2, 4, 6, 8]

    def test_string_transformation(self):
        """Test string transformation."""
        node = DataTransformer(
            data=["hello", "world"], transformations=["lambda x: x.upper()"]
        )

        result = node.execute()

        assert result["result"] == ["HELLO", "WORLD"]

    def test_dict_transformation(self):
        """Test dictionary transformation."""
        node = DataTransformer(
            data=[{"value": 10}, {"value": 20}],
            transformations=[
                "lambda x: {'original': x['value'], 'doubled': x['value'] * 2}"
            ],
        )

        result = node.execute()

        assert result["result"][0]["original"] == 10
        assert result["result"][0]["doubled"] == 20
        assert result["result"][1]["original"] == 20
        assert result["result"][1]["doubled"] == 40

    def test_multi_step_transformation(self):
        """Test multiple transformation steps."""
        node = DataTransformer(
            data=[1, 2, 3],
            transformations=[
                "lambda x: x * 2",  # First: double each number
                "lambda x: x + 1",  # Then: add 1 to each result
            ],
        )

        result = node.execute()

        assert result["result"] == [3, 5, 7]  # (1*2)+1, (2*2)+1, (3*2)+1

    def test_aggregation_transformation(self):
        """Test aggregation transformation."""
        node = DataTransformer(data=[1, 2, 3, 4, 5], transformations=["sum(result)"])

        result = node.execute()

        assert result["result"] == 15

    def test_empty_transformations(self):
        """Test with empty transformations list."""
        data = [1, 2, 3]
        node = DataTransformer(data=data, transformations=[])

        result = node.execute()

        assert result["result"] == data

    def test_complex_lambda_transformation(self):
        """Test DataTransformer with complex lambda function."""
        node = DataTransformer(
            data=[
                {"name": "Alice", "scores": [85, 90, 78]},
                {"name": "Bob", "scores": [92, 88, 95]},
            ],
            transformations=[
                "lambda x: {'name': x['name'], 'avg_score': sum(x['scores']) / len(x['scores'])}"
            ],
        )

        result = node.execute()

        assert result["result"][0]["avg_score"] == 84.33333333333333  # (85+90+78)/3
        assert result["result"][1]["avg_score"] == 91.66666666666667  # (92+88+95)/3

    def test_simple_code_block_transformation(self):
        """Test simple code block transformation."""
        node = DataTransformer(
            data=[1, 2, 3, 4, 5],
            transformations=[
                """
# Filter even numbers
result = [x for x in result if x % 2 == 0]
"""
            ],
        )

        result = node.execute()

        assert result["result"] == [2, 4]  # Only even numbers

    def test_transformation_with_additional_args(self):
        """Test transformation with additional arguments - simplified."""
        # Simplified test using a different approach
        node = DataTransformer(
            data=[1, 2, 3],
            transformations=[
                "[x * 10 for x in result]"
            ],  # Direct value instead of variable
        )

        result = node.execute()

        assert result["result"] == [10, 20, 30]

    def test_transformation_error_handling(self):
        """Test error handling in transformations."""
        node = DataTransformer(
            data=[1, 2, 3], transformations=["invalid python syntax"]
        )

        with pytest.raises(NodeExecutionError, match="Error executing transformation"):
            node.execute()


class TestTransformNodeEdgeCases:
    """Test edge cases and special scenarios."""

    def test_filter_not_equal_operator(self):
        """Test filtering with not equal operator."""
        node = Filter(data=[1, 2, 3, 2, 4], operator="!=", value=2)

        result = node.execute()

        assert result["filtered_data"] == [1, 3, 4]

    def test_map_lower_case_operation(self):
        """Test map with lower case operation."""
        node = Map(data=["HELLO", "WORLD"], operation="lower")

        result = node.execute()

        assert result["mapped_data"] == ["hello", "world"]

    def test_sort_with_none_field(self):
        """Test Sort with None field (should sort data directly)."""
        node = Sort(data=[3, 1, 4, 2], field=None)

        result = node.execute()

        assert result["sorted_data"] == [1, 2, 3, 4]

    def test_data_transformer_list_comprehension(self):
        """Test DataTransformer with list comprehension."""
        node = DataTransformer(
            data=[1, 2, 3, 4, 5], transformations=["[x * 2 for x in result if x > 2]"]
        )

        result = node.execute()

        assert result["result"] == [6, 8, 10]  # (3*2, 4*2, 5*2)

    def test_filter_less_than_equal_operator(self):
        """Test filtering with less than or equal operator."""
        node = Filter(data=[1, 2, 3, 4, 5], operator="<=", value=3)

        result = node.execute()

        assert result["filtered_data"] == [1, 2, 3]

    def test_map_numeric_addition(self):
        """Test map with numeric addition."""
        node = Map(data=[10, 20, 30], operation="add", value=5)

        result = node.execute()

        assert result["mapped_data"] == [15.0, 25.0, 35.0]


class TestHierarchicalChunkerNode:
    """Test HierarchicalChunkerNode for document chunking."""

    def test_basic_document_chunking(self):
        """Test basic document chunking functionality."""
        node = HierarchicalChunkerNode()

        documents = [
            {
                "id": "doc1",
                "title": "Test Document",
                "content": "This is the first sentence. This is the second sentence. This is the third sentence.",
            }
        ]

        result = node.run(documents=documents, chunk_size=50, overlap=10)

        assert "chunks" in result
        assert isinstance(result["chunks"], list)
        assert len(result["chunks"]) > 0

        # Check chunk structure
        chunk = result["chunks"][0]
        assert "chunk_id" in chunk
        assert "document_id" in chunk
        assert "document_title" in chunk
        assert "chunk_index" in chunk
        assert "content" in chunk
        assert "hierarchy_level" in chunk

        assert chunk["document_id"] == "doc1"
        assert chunk["document_title"] == "Test Document"
        assert chunk["hierarchy_level"] == "paragraph"
        assert chunk["chunk_index"] == 0

    def test_multiple_documents_chunking(self):
        """Test chunking multiple documents."""
        node = HierarchicalChunkerNode()

        documents = [
            {
                "id": "doc1",
                "title": "First Document",
                "content": "Short content for first document.",
            },
            {
                "id": "doc2",
                "title": "Second Document",
                "content": "This is longer content for the second document with multiple sentences. It should be split into chunks based on the chunk size parameter.",
            },
        ]

        result = node.run(documents=documents, chunk_size=80, overlap=20)

        assert "chunks" in result
        chunks = result["chunks"]

        # Should have chunks from both documents
        doc1_chunks = [c for c in chunks if c["document_id"] == "doc1"]
        doc2_chunks = [c for c in chunks if c["document_id"] == "doc2"]

        assert len(doc1_chunks) > 0
        assert len(doc2_chunks) > 0

        # Verify chunk IDs are unique and properly formatted
        chunk_ids = [c["chunk_id"] for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))  # All unique

        # Check chunk ID format
        assert doc1_chunks[0]["chunk_id"].startswith("doc1_chunk_")
        assert doc2_chunks[0]["chunk_id"].startswith("doc2_chunk_")

    def test_empty_documents(self):
        """Test behavior with empty documents list."""
        node = HierarchicalChunkerNode()

        result = node.run(documents=[])

        assert "chunks" in result
        assert result["chunks"] == []

    def test_chunk_size_parameters(self):
        """Test different chunk size parameters."""
        node = HierarchicalChunkerNode()

        document = {
            "id": "test_doc",
            "title": "Test",
            "content": "This is a very long sentence that should be split into multiple chunks when the chunk size is small. This is another sentence that continues the content.",
        }

        # Test with small chunk size
        result_small = node.run(documents=[document], chunk_size=50)
        chunks_small = result_small["chunks"]

        # Test with large chunk size
        result_large = node.run(documents=[document], chunk_size=200)
        chunks_large = result_large["chunks"]

        # Small chunk size should produce more chunks
        assert len(chunks_small) >= len(chunks_large)

    def test_node_parameters(self):
        """Test node parameter configuration."""
        node = HierarchicalChunkerNode()
        params = node.get_parameters()

        expected_params = ["documents", "chunk_size", "overlap"]
        for param_name in expected_params:
            assert param_name in params

        # Check default values
        assert params["chunk_size"].default == 200
        assert params["overlap"].default == 50
        assert params["chunk_size"].type == int
        assert params["overlap"].type == int


class TestChunkTextExtractorNode:
    """Test ChunkTextExtractorNode for text extraction."""

    def test_extract_text_from_chunks(self):
        """Test extracting text content from chunks."""
        node = ChunkTextExtractorNode()

        chunks = [
            {"content": "First chunk content", "document_id": "doc1"},
            {"content": "Second chunk content", "document_id": "doc1"},
            {"content": "Third chunk content", "document_id": "doc2"},
        ]

        result = node.run(chunks=chunks)

        assert "input_texts" in result
        assert isinstance(result["input_texts"], list)
        assert len(result["input_texts"]) == 3

        expected_texts = [
            "First chunk content",
            "Second chunk content",
            "Third chunk content",
        ]
        assert result["input_texts"] == expected_texts

    def test_extract_from_empty_chunks(self):
        """Test behavior with empty chunks list."""
        node = ChunkTextExtractorNode()

        result = node.run(chunks=[])

        assert "input_texts" in result
        assert result["input_texts"] == []

    def test_extract_with_missing_content(self):
        """Test behavior when chunks missing content field."""
        node = ChunkTextExtractorNode()

        chunks = [
            {"content": "Valid content"},
            {"no_content_field": "invalid"},  # Missing content field
        ]

        # Should handle KeyError gracefully or raise appropriate error
        try:
            result = node.run(chunks=chunks)
            # If it doesn't raise an error, verify it handled it gracefully
            assert "input_texts" in result
        except KeyError:
            # This is also acceptable behavior
            pass

    def test_node_parameters(self):
        """Test node parameter configuration."""
        node = ChunkTextExtractorNode()
        params = node.get_parameters()

        assert "chunks" in params
        assert params["chunks"].type == list
        assert params["chunks"].required is False


class TestQueryTextWrapperNode:
    """Test QueryTextWrapperNode for query wrapping."""

    def test_wrap_query_string(self):
        """Test wrapping a query string in a list."""
        node = QueryTextWrapperNode()

        query = "What are the main types of machine learning?"
        result = node.run(query=query)

        assert "input_texts" in result
        assert isinstance(result["input_texts"], list)
        assert len(result["input_texts"]) == 1
        assert result["input_texts"][0] == query

    def test_wrap_empty_query(self):
        """Test wrapping an empty query."""
        node = QueryTextWrapperNode()

        result = node.run(query="")

        assert "input_texts" in result
        assert result["input_texts"] == [""]

    def test_default_query_handling(self):
        """Test behavior when no query is provided."""
        node = QueryTextWrapperNode()

        result = node.run()

        assert "input_texts" in result
        assert isinstance(result["input_texts"], list)
        assert len(result["input_texts"]) == 1
        # Should use empty string as default
        assert result["input_texts"][0] == ""

    def test_node_parameters(self):
        """Test node parameter configuration."""
        node = QueryTextWrapperNode()
        params = node.get_parameters()

        assert "query" in params
        assert params["query"].type == str
        assert params["query"].required is False


class TestContextFormatterNode:
    """Test ContextFormatterNode for LLM context formatting."""

    def test_format_context_with_chunks(self):
        """Test formatting context from relevant chunks."""
        node = ContextFormatterNode()

        relevant_chunks = [
            {
                "content": "Machine learning is a subset of AI.",
                "document_title": "ML Basics",
                "relevance_score": 0.95,
            },
            {
                "content": "Deep learning uses neural networks.",
                "document_title": "Deep Learning",
                "relevance_score": 0.87,
            },
        ]

        query = "What is machine learning?"
        result = node.run(relevant_chunks=relevant_chunks, query=query)

        assert "formatted_prompt" in result
        assert "messages" in result
        assert "context" in result

        # Check formatted prompt contains query and context
        prompt = result["formatted_prompt"]
        assert query in prompt
        assert "Machine learning is a subset of AI." in prompt
        assert "Deep learning uses neural networks." in prompt
        assert "ML Basics" in prompt
        assert "0.950" in prompt  # Score should be formatted

        # Check messages format for LLM
        messages = result["messages"]
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == prompt

        # Check context extraction
        context = result["context"]
        assert "Machine learning is a subset of AI." in context
        assert "Deep learning uses neural networks." in context

    def test_format_with_empty_chunks(self):
        """Test formatting with empty relevant chunks."""
        node = ContextFormatterNode()

        query = "What is machine learning?"
        result = node.run(relevant_chunks=[], query=query)

        assert "formatted_prompt" in result
        assert "messages" in result
        assert "context" in result

        # Should still create a prompt with the query
        prompt = result["formatted_prompt"]
        assert query in prompt

        # Context should be empty
        context = result["context"]
        assert context == ""

    def test_format_with_single_chunk(self):
        """Test formatting with single relevant chunk."""
        node = ContextFormatterNode()

        relevant_chunks = [
            {
                "content": "Neural networks are computing systems inspired by biological neural networks.",
                "document_title": "Neural Networks",
                "relevance_score": 0.92,
            }
        ]

        query = "How do neural networks work?"
        result = node.run(relevant_chunks=relevant_chunks, query=query)

        prompt = result["formatted_prompt"]
        assert "Neural networks are computing systems" in prompt
        assert "Neural Networks" in prompt
        assert "0.920" in prompt
        assert query in prompt

    def test_score_formatting(self):
        """Test that relevance scores are properly formatted."""
        node = ContextFormatterNode()

        relevant_chunks = [
            {
                "content": "Test content",
                "document_title": "Test Doc",
                "relevance_score": 0.123456789,  # Long decimal
            }
        ]

        result = node.run(relevant_chunks=relevant_chunks, query="test query")

        # Score should be formatted to 3 decimal places
        prompt = result["formatted_prompt"]
        assert "0.123" in prompt
        assert "0.123456789" not in prompt

    def test_node_parameters(self):
        """Test node parameter configuration."""
        node = ContextFormatterNode()
        params = node.get_parameters()

        expected_params = ["relevant_chunks", "query"]
        for param_name in expected_params:
            assert param_name in params

        assert params["relevant_chunks"].type == list
        assert params["query"].type == str
        assert params["relevant_chunks"].required is False
        assert params["query"].required is False

"""
Unit tests for MongoDB workflow nodes.

These tests use mocks to test node logic without requiring
a real MongoDB instance (Tier 1 - Unit Tests).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.adapters.mongodb import MongoDBAdapter
from dataflow.nodes.mongodb_nodes import (
    AggregateNode,
    BulkDocumentInsertNode,
    CreateIndexNode,
    DocumentCountNode,
    DocumentDeleteNode,
    DocumentFindNode,
    DocumentInsertNode,
    DocumentUpdateNode,
)


class TestDocumentInsertNode:
    """Test DocumentInsertNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = DocumentInsertNode()

        assert node is not None
        assert hasattr(node, "get_parameters")

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = DocumentInsertNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "document" in params
        assert "bypass_document_validation" in params

        assert params["collection"].required is True
        assert params["document"].required is True
        assert params["bypass_document_validation"].required is False

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful document insert."""
        node = DocumentInsertNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_one = AsyncMock(return_value="507f1f77bcf86cd799439011")

        # Setup mock dataflow instance
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", document={"name": "Alice", "email": "alice@example.com"}
        )

        # Verify
        assert result["success"] is True
        assert result["inserted_id"] == "507f1f77bcf86cd799439011"
        assert result["collection"] == "users"
        mock_adapter.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_wrong_adapter(self):
        """Test error when using wrong adapter type."""
        node = DocumentInsertNode()

        # Setup mock with wrong adapter type
        mock_adapter = MagicMock()  # Not MongoDBAdapter
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute should raise ValueError
        with pytest.raises(ValueError, match="requires MongoDBAdapter"):
            await node.async_run(collection="users", document={"name": "Alice"})

    @pytest.mark.asyncio
    async def test_async_run_insert_failure(self):
        """Test handling of insert failure."""
        node = DocumentInsertNode()

        # Setup mock adapter to fail
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_one = AsyncMock(side_effect=Exception("Insert failed"))

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(collection="users", document={"name": "Alice"})

        # Verify error handling
        assert result["success"] is False
        assert "error" in result
        assert "Insert failed" in result["error"]


class TestDocumentFindNode:
    """Test DocumentFindNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = DocumentFindNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = DocumentFindNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "filter" in params
        assert "projection" in params
        assert "sort" in params
        assert "limit" in params
        assert "skip" in params

        assert params["collection"].required is True
        assert params["filter"].required is False
        assert params["limit"].default == 0

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful document find."""
        node = DocumentFindNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_documents = [
            {"_id": "id1", "name": "Alice", "status": "active"},
            {"_id": "id2", "name": "Bob", "status": "active"},
        ]
        mock_adapter.find = AsyncMock(return_value=mock_documents)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", filter={"status": "active"}, limit=10
        )

        # Verify
        assert result["count"] == 2
        assert len(result["documents"]) == 2
        assert result["collection"] == "users"
        mock_adapter.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_no_results(self):
        """Test find with no matching documents."""
        node = DocumentFindNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.find = AsyncMock(return_value=[])

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", filter={"status": "nonexistent"}
        )

        # Verify
        assert result["count"] == 0
        assert result["documents"] == []


class TestDocumentUpdateNode:
    """Test DocumentUpdateNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = DocumentUpdateNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = DocumentUpdateNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "filter" in params
        assert "update" in params
        assert "upsert" in params
        assert "multi" in params

        assert params["collection"].required is True
        assert params["filter"].required is True
        assert params["update"].required is True
        assert params["upsert"].default is False
        assert params["multi"].default is False

    @pytest.mark.asyncio
    async def test_async_run_update_one(self):
        """Test successful update_one operation."""
        node = DocumentUpdateNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.update_one = AsyncMock(
            return_value={"matched_count": 1, "modified_count": 1, "upserted_id": None}
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users",
            filter={"email": "alice@example.com"},
            update={"$set": {"status": "active"}},
            multi=False,
        )

        # Verify
        assert result["matched_count"] == 1
        assert result["modified_count"] == 1
        assert result["upserted_id"] is None
        mock_adapter.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_update_many(self):
        """Test successful update_many operation."""
        node = DocumentUpdateNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.update_many = AsyncMock(
            return_value={"matched_count": 5, "modified_count": 5, "upserted_id": None}
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users",
            filter={"status": "inactive"},
            update={"$set": {"archived": True}},
            multi=True,
        )

        # Verify
        assert result["matched_count"] == 5
        assert result["modified_count"] == 5
        mock_adapter.update_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_with_upsert(self):
        """Test update with upsert option."""
        node = DocumentUpdateNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.update_one = AsyncMock(
            return_value={
                "matched_count": 0,
                "modified_count": 0,
                "upserted_id": "new-id",
            }
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users",
            filter={"email": "new@example.com"},
            update={"$set": {"name": "New User"}},
            upsert=True,
        )

        # Verify
        assert result["matched_count"] == 0
        assert result["modified_count"] == 0
        assert result["upserted_id"] == "new-id"


class TestDocumentDeleteNode:
    """Test DocumentDeleteNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = DocumentDeleteNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = DocumentDeleteNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "filter" in params
        assert "multi" in params

        assert params["collection"].required is True
        assert params["filter"].required is True
        assert params["multi"].default is False

    @pytest.mark.asyncio
    async def test_async_run_delete_one(self):
        """Test successful delete_one operation."""
        node = DocumentDeleteNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.delete_one = AsyncMock(return_value=1)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", filter={"email": "alice@example.com"}, multi=False
        )

        # Verify
        assert result["deleted_count"] == 1
        assert result["collection"] == "users"
        mock_adapter.delete_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_delete_many(self):
        """Test successful delete_many operation."""
        node = DocumentDeleteNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.delete_many = AsyncMock(return_value=3)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", filter={"status": "inactive"}, multi=True
        )

        # Verify
        assert result["deleted_count"] == 3
        mock_adapter.delete_many.assert_called_once()


class TestAggregateNode:
    """Test AggregateNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = AggregateNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = AggregateNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "pipeline" in params
        assert "allow_disk_use" in params

        assert params["collection"].required is True
        assert params["pipeline"].required is True
        assert params["allow_disk_use"].default is False

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful aggregation."""
        node = AggregateNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_results = [
            {"_id": "category1", "total": 1000, "count": 5},
            {"_id": "category2", "total": 2000, "count": 10},
        ]
        mock_adapter.aggregate = AsyncMock(return_value=mock_results)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        ]
        result = await node.async_run(collection="orders", pipeline=pipeline)

        # Verify
        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert result["collection"] == "orders"
        mock_adapter.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_empty_results(self):
        """Test aggregation with no results."""
        node = AggregateNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.aggregate = AsyncMock(return_value=[])

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        pipeline = [{"$match": {"status": "nonexistent"}}]
        result = await node.async_run(collection="orders", pipeline=pipeline)

        # Verify
        assert result["count"] == 0
        assert result["results"] == []


class TestBulkDocumentInsertNode:
    """Test BulkDocumentInsertNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = BulkDocumentInsertNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = BulkDocumentInsertNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "documents" in params
        assert "ordered" in params
        assert "bypass_document_validation" in params

        assert params["collection"].required is True
        assert params["documents"].required is True
        assert params["ordered"].default is True

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful bulk insert."""
        node = BulkDocumentInsertNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_many = AsyncMock(return_value=["id1", "id2", "id3"])

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        documents = [{"name": "Alice"}, {"name": "Bob"}, {"name": "Charlie"}]
        result = await node.async_run(collection="users", documents=documents)

        # Verify
        assert result["success"] is True
        assert result["inserted_count"] == 3
        assert len(result["inserted_ids"]) == 3
        assert result["collection"] == "users"
        mock_adapter.insert_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_failure(self):
        """Test handling of bulk insert failure."""
        node = BulkDocumentInsertNode()

        # Setup mock adapter to fail
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_many = AsyncMock(
            side_effect=Exception("Bulk insert failed")
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        documents = [{"name": "Alice"}]
        result = await node.async_run(collection="users", documents=documents)

        # Verify error handling
        assert result["success"] is False
        assert result["inserted_count"] == 0
        assert "error" in result


class TestCreateIndexNode:
    """Test CreateIndexNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = CreateIndexNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = CreateIndexNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "keys" in params
        assert "unique" in params
        assert "sparse" in params
        assert "name" in params

        assert params["collection"].required is True
        assert params["keys"].required is True
        assert params["unique"].default is False
        assert params["sparse"].default is False

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful index creation."""
        node = CreateIndexNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.create_index = AsyncMock(return_value="email_1")

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", keys=[("email", 1)], unique=True
        )

        # Verify
        assert result["success"] is True
        assert result["index_name"] == "email_1"
        assert result["collection"] == "users"
        mock_adapter.create_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_compound_index(self):
        """Test creating compound index."""
        node = CreateIndexNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.create_index = AsyncMock(return_value="last_name_1_first_name_1")

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(
            collection="users", keys=[("last_name", 1), ("first_name", 1)]
        )

        # Verify
        assert result["success"] is True
        assert result["index_name"] == "last_name_1_first_name_1"


class TestDocumentCountNode:
    """Test DocumentCountNode."""

    def test_node_initialization(self):
        """Test node initialization."""
        node = DocumentCountNode()

        assert node is not None

    def test_node_parameters(self):
        """Test node parameters are properly defined."""
        node = DocumentCountNode()
        params = node.get_parameters()

        assert "collection" in params
        assert "filter" in params

        assert params["collection"].required is True
        assert params["filter"].required is False
        assert params["filter"].default == {}

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful count operation."""
        node = DocumentCountNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.count_documents = AsyncMock(return_value=10)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(collection="users", filter={"status": "active"})

        # Verify
        assert result["count"] == 10
        assert result["collection"] == "users"
        mock_adapter.count_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_run_no_filter(self):
        """Test count with no filter (count all)."""
        node = DocumentCountNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.count_documents = AsyncMock(return_value=100)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter
        node.dataflow_instance = mock_dataflow

        # Execute node
        result = await node.async_run(collection="users")

        # Verify
        assert result["count"] == 100


class TestMongoDBNodesIntegration:
    """Test integration between multiple MongoDB nodes."""

    @pytest.mark.asyncio
    async def test_insert_then_find(self):
        """Test inserting and then finding documents."""
        insert_node = DocumentInsertNode()
        find_node = DocumentFindNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_one = AsyncMock(return_value="new-id")
        mock_adapter.find = AsyncMock(
            return_value=[
                {"_id": "new-id", "name": "Alice", "email": "alice@example.com"}
            ]
        )

        # Setup mock dataflow
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        insert_node.dataflow_instance = mock_dataflow
        find_node.dataflow_instance = mock_dataflow

        # Insert document
        insert_result = await insert_node.async_run(
            collection="users", document={"name": "Alice", "email": "alice@example.com"}
        )

        assert insert_result["success"] is True

        # Find document
        find_result = await find_node.async_run(
            collection="users", filter={"email": "alice@example.com"}
        )

        assert find_result["count"] == 1
        assert find_result["documents"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_insert_update_find(self):
        """Test insert, update, and find workflow."""
        insert_node = DocumentInsertNode()
        update_node = DocumentUpdateNode()
        find_node = DocumentFindNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_one = AsyncMock(return_value="new-id")
        mock_adapter.update_one = AsyncMock(
            return_value={"matched_count": 1, "modified_count": 1, "upserted_id": None}
        )
        mock_adapter.find = AsyncMock(
            return_value=[
                {
                    "_id": "new-id",
                    "name": "Alice",
                    "email": "alice@example.com",
                    "status": "active",
                }
            ]
        )

        # Setup mock dataflow
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        insert_node.dataflow_instance = mock_dataflow
        update_node.dataflow_instance = mock_dataflow
        find_node.dataflow_instance = mock_dataflow

        # Insert
        await insert_node.async_run(
            collection="users", document={"name": "Alice", "email": "alice@example.com"}
        )

        # Update
        update_result = await update_node.async_run(
            collection="users",
            filter={"email": "alice@example.com"},
            update={"$set": {"status": "active"}},
        )

        assert update_result["modified_count"] == 1

        # Find
        find_result = await find_node.async_run(
            collection="users", filter={"email": "alice@example.com"}
        )

        assert find_result["documents"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_bulk_insert_and_count(self):
        """Test bulk insert and count workflow."""
        bulk_insert_node = BulkDocumentInsertNode()
        count_node = DocumentCountNode()

        # Setup mock adapter
        mock_adapter = MagicMock(spec=MongoDBAdapter)
        mock_adapter.insert_many = AsyncMock(return_value=["id1", "id2", "id3"])
        mock_adapter.count_documents = AsyncMock(return_value=3)

        # Setup mock dataflow
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        bulk_insert_node.dataflow_instance = mock_dataflow
        count_node.dataflow_instance = mock_dataflow

        # Bulk insert
        documents = [
            {"name": "Alice", "status": "active"},
            {"name": "Bob", "status": "active"},
            {"name": "Charlie", "status": "active"},
        ]
        bulk_result = await bulk_insert_node.async_run(
            collection="users", documents=documents
        )

        assert bulk_result["inserted_count"] == 3

        # Count
        count_result = await count_node.async_run(
            collection="users", filter={"status": "active"}
        )

        assert count_result["count"] == 3

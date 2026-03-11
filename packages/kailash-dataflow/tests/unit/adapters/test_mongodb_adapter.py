"""
Unit tests for MongoDBAdapter.

These tests use mocks to test adapter logic without requiring
a real MongoDB instance (Tier 1 - Unit Tests).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.adapters.mongodb import MongoDBAdapter


class TestMongoDBAdapterInitialization:
    """Test MongoDB adapter initialization and properties."""

    def test_adapter_initialization(self):
        """Test basic adapter initialization."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.connection_string == "mongodb://localhost:27017/testdb"
        assert adapter.database_name is None
        assert adapter._connected is False
        assert adapter._client is None
        assert adapter._db is None

    def test_adapter_initialization_with_database_name(self):
        """Test adapter initialization with explicit database name."""
        adapter = MongoDBAdapter("mongodb://localhost:27017", database_name="testdb")

        assert adapter.database_name == "testdb"

    def test_adapter_initialization_with_options(self):
        """Test adapter initialization with client options."""
        adapter = MongoDBAdapter(
            "mongodb://localhost:27017/testdb",
            maxPoolSize=50,
            minPoolSize=5,
            serverSelectionTimeoutMS=5000,
        )

        assert adapter.client_options["maxPoolSize"] == 50
        assert adapter.client_options["minPoolSize"] == 5
        assert adapter.client_options["serverSelectionTimeoutMS"] == 5000

    def test_adapter_type_property(self):
        """Test adapter_type property returns 'document'."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.adapter_type == "document"

    def test_database_type_property(self):
        """Test database_type property returns 'mongodb'."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.database_type == "mongodb"


class TestMongoDBAdapterFeatureDetection:
    """Test MongoDB adapter feature detection."""

    def test_supports_documents_feature(self):
        """Test support for documents feature."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("documents") is True

    def test_supports_flexible_schema_feature(self):
        """Test support for flexible schema."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("flexible_schema") is True

    def test_supports_aggregation_feature(self):
        """Test support for aggregation pipelines."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("aggregation") is True

    def test_supports_text_search_feature(self):
        """Test support for full-text search."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("text_search") is True

    def test_supports_geospatial_feature(self):
        """Test support for geospatial queries."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("geospatial") is True

    def test_supports_transactions_feature(self):
        """Test support for transactions."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("transactions") is True

    def test_supports_change_streams_feature(self):
        """Test support for change streams."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("change_streams") is True

    def test_supports_gridfs_feature(self):
        """Test support for GridFS."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("gridfs") is True

    def test_does_not_support_unknown_feature(self):
        """Test unknown feature returns False."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        assert adapter.supports_feature("unknown_feature") is False
        assert adapter.supports_feature("sql") is False


class TestMongoDBAdapterConnection:
    """Test MongoDB adapter connection management (with mocks)."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        with patch("dataflow.adapters.mongodb.AsyncIOMotorClient") as mock_client_class:
            # Setup mock
            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(return_value={"ok": 1})
            mock_client_class.return_value = mock_client

            # Connect
            await adapter.connect()

            # Verify
            assert adapter._connected is True
            assert adapter._client == mock_client
            assert adapter._db == mock_client["testdb"]
            mock_client.admin.command.assert_called_once_with("ping")

    @pytest.mark.asyncio
    async def test_connect_with_database_name_parameter(self):
        """Test connection with explicit database name."""
        adapter = MongoDBAdapter("mongodb://localhost:27017", database_name="mydb")

        with patch("dataflow.adapters.mongodb.AsyncIOMotorClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(return_value={"ok": 1})
            mock_client_class.return_value = mock_client

            await adapter.connect()

            assert adapter._db == mock_client["mydb"]

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test connection failure handling."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        with patch("dataflow.adapters.mongodb.AsyncIOMotorClient") as mock_client_class:
            # Setup mock to fail
            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(
                side_effect=Exception("Connection failed")
            )
            mock_client_class.return_value = mock_client

            # Connect should raise
            with pytest.raises(ConnectionError, match="MongoDB connection failed"):
                await adapter.connect()

            assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connecting when already connected."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")
        adapter._connected = True

        # Connect should return early without error
        await adapter.connect()

        # No client should be created
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        """Test successful disconnection."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_client = MagicMock()
        adapter._connected = True
        adapter._client = mock_client
        adapter._db = MagicMock()

        # Disconnect
        await adapter.disconnect()

        # Verify
        assert adapter._connected is False
        assert adapter._client is None
        assert adapter._db is None
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        """Test disconnecting when not connected."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Disconnect should return early without error
        await adapter.disconnect()

        assert adapter._connected is False


class TestMongoDBAdapterHealthCheck:
    """Test MongoDB adapter health check (with mocks)."""

    @pytest.mark.asyncio
    async def test_health_check_connected(self):
        """Test health check when connected."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.name = "testdb"
        mock_db.command = AsyncMock(
            return_value={"dataSize": 1024, "storageSize": 2048, "indexes": 5}
        )
        mock_db.list_collection_names = AsyncMock(
            return_value=["users", "products", "orders"]
        )

        adapter._connected = True
        adapter._client = mock_client
        adapter._db = mock_db

        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_client.server_info = AsyncMock(return_value={"version": "6.0.0"})

        # Health check
        result = await adapter.health_check()

        # Verify
        assert result["connected"] is True
        assert result["database"] == "testdb"
        assert result["server_version"] == "6.0.0"
        assert result["collections_count"] == 3
        assert result["data_size"] == 1024
        assert result["storage_size"] == 2048
        assert result["indexes"] == 5

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self):
        """Test health check when not connected."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        result = await adapter.health_check()

        assert result["connected"] is False
        assert result["database"] is None
        assert "error" in result

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure handling."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state but failing health check
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.name = "testdb"
        mock_client.admin.command = AsyncMock(
            side_effect=Exception("Health check failed")
        )

        adapter._connected = True
        adapter._client = mock_client
        adapter._db = mock_db

        # Health check
        result = await adapter.health_check()

        # Verify
        assert result["connected"] is False
        assert result["database"] == "testdb"
        assert "error" in result


class TestMongoDBAdapterDocumentOperations:
    """Test MongoDB adapter document operations (with mocks)."""

    @pytest.mark.asyncio
    async def test_insert_one_success(self):
        """Test successful single document insert."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "507f1f77bcf86cd799439011"

        mock_collection.insert_one = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Insert
        result_id = await adapter.insert_one(
            "users", {"name": "Alice", "email": "alice@example.com"}
        )

        # Verify
        assert result_id == "507f1f77bcf86cd799439011"
        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_one_empty_document(self):
        """Test insert with empty document."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")
        adapter._connected = True
        adapter._db = MagicMock()

        with pytest.raises(ValueError, match="Document cannot be empty"):
            await adapter.insert_one("users", {})

    @pytest.mark.asyncio
    async def test_insert_one_not_connected(self):
        """Test insert when not connected."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        with pytest.raises(ConnectionError, match="Not connected to MongoDB"):
            await adapter.insert_one("users", {"name": "Alice"})

    @pytest.mark.asyncio
    async def test_insert_many_success(self):
        """Test successful bulk insert."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3"]

        mock_collection.insert_many = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Insert
        documents = [{"name": "Alice"}, {"name": "Bob"}, {"name": "Charlie"}]
        result_ids = await adapter.insert_many("users", documents)

        # Verify
        assert len(result_ids) == 3
        assert result_ids == ["id1", "id2", "id3"]
        mock_collection.insert_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_one_success(self):
        """Test successful find_one operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_document = {"_id": "id1", "name": "Alice", "email": "alice@example.com"}

        mock_collection.find_one = AsyncMock(return_value=mock_document)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Find
        result = await adapter.find_one("users", {"email": "alice@example.com"})

        # Verify
        assert result == mock_document
        mock_collection.find_one.assert_called_once_with({"email": "alice@example.com"})

    @pytest.mark.asyncio
    async def test_find_one_not_found(self):
        """Test find_one when document not found."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Find
        result = await adapter.find_one("users", {"email": "nonexistent@example.com"})

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_find_success(self):
        """Test successful find operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_documents = [
            {"_id": "id1", "name": "Alice", "status": "active"},
            {"_id": "id2", "name": "Bob", "status": "active"},
        ]

        mock_cursor.to_list = AsyncMock(return_value=mock_documents)
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)

        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Find
        results = await adapter.find(
            "users", filter={"status": "active"}, sort=[("name", 1)], limit=10, skip=0
        )

        # Verify
        assert len(results) == 2
        assert results == mock_documents

    @pytest.mark.asyncio
    async def test_update_one_success(self):
        """Test successful update_one operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_id = None

        mock_collection.update_one = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Update
        result = await adapter.update_one(
            "users", {"email": "alice@example.com"}, {"$set": {"status": "active"}}
        )

        # Verify
        assert result["matched_count"] == 1
        assert result["modified_count"] == 1
        assert result["upserted_id"] is None

    @pytest.mark.asyncio
    async def test_update_many_success(self):
        """Test successful update_many operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 5
        mock_result.modified_count = 5
        mock_result.upserted_id = None

        mock_collection.update_many = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Update
        result = await adapter.update_many(
            "users", {"status": "inactive"}, {"$set": {"archived": True}}
        )

        # Verify
        assert result["matched_count"] == 5
        assert result["modified_count"] == 5

    @pytest.mark.asyncio
    async def test_delete_one_success(self):
        """Test successful delete_one operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 1

        mock_collection.delete_one = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Delete
        count = await adapter.delete_one("users", {"email": "alice@example.com"})

        # Verify
        assert count == 1

    @pytest.mark.asyncio
    async def test_delete_many_success(self):
        """Test successful delete_many operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 3

        mock_collection.delete_many = AsyncMock(return_value=mock_result)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Delete
        count = await adapter.delete_many("users", {"status": "inactive"})

        # Verify
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_documents_success(self):
        """Test successful count_documents operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=10)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Count
        count = await adapter.count_documents("users", {"status": "active"})

        # Verify
        assert count == 10

    @pytest.mark.asyncio
    async def test_aggregate_success(self):
        """Test successful aggregate operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_results = [
            {"_id": "category1", "total": 1000, "count": 5},
            {"_id": "category2", "total": 2000, "count": 10},
        ]
        mock_cursor.to_list = AsyncMock(return_value=mock_results)

        mock_collection.aggregate = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Aggregate
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        ]
        results = await adapter.aggregate("orders", pipeline)

        # Verify
        assert len(results) == 2
        assert results == mock_results


class TestMongoDBAdapterIndexOperations:
    """Test MongoDB adapter index operations (with mocks)."""

    @pytest.mark.asyncio
    async def test_create_index_success(self):
        """Test successful index creation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.create_index = AsyncMock(return_value="email_1")
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Create index
        index_name = await adapter.create_index("users", [("email", 1)], unique=True)

        # Verify
        assert index_name == "email_1"

    @pytest.mark.asyncio
    async def test_list_indexes_success(self):
        """Test successful list indexes operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_indexes = [
            {"name": "_id_", "key": {"_id": 1}},
            {"name": "email_1", "key": {"email": 1}, "unique": True},
        ]
        mock_cursor.to_list = AsyncMock(return_value=mock_indexes)

        mock_collection.list_indexes = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # List indexes
        indexes = await adapter.list_indexes("users")

        # Verify
        assert len(indexes) == 2
        assert indexes == mock_indexes

    @pytest.mark.asyncio
    async def test_drop_index_success(self):
        """Test successful drop index operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.drop_index = AsyncMock()
        mock_db.__getitem__.return_value = mock_collection

        adapter._connected = True
        adapter._db = mock_db

        # Drop index
        await adapter.drop_index("users", "email_1")

        # Verify
        mock_collection.drop_index.assert_called_once_with("email_1")


class TestMongoDBAdapterCollectionOperations:
    """Test MongoDB adapter collection operations (with mocks)."""

    @pytest.mark.asyncio
    async def test_create_collection_success(self):
        """Test successful collection creation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_db.create_collection = AsyncMock()

        adapter._connected = True
        adapter._db = mock_db

        # Create collection
        await adapter.create_collection("new_collection")

        # Verify
        mock_db.create_collection.assert_called_once_with("new_collection")

    @pytest.mark.asyncio
    async def test_drop_collection_success(self):
        """Test successful collection drop."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_db.drop_collection = AsyncMock()

        adapter._connected = True
        adapter._db = mock_db

        # Drop collection
        await adapter.drop_collection("old_collection")

        # Verify
        mock_db.drop_collection.assert_called_once_with("old_collection")

    @pytest.mark.asyncio
    async def test_list_collections_success(self):
        """Test successful list collections operation."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_db.list_collection_names = AsyncMock(
            return_value=["users", "products", "orders"]
        )

        adapter._connected = True
        adapter._db = mock_db

        # List collections
        collections = await adapter.list_collections()

        # Verify
        assert len(collections) == 3
        assert "users" in collections
        assert "products" in collections
        assert "orders" in collections

    @pytest.mark.asyncio
    async def test_collection_exists_true(self):
        """Test collection_exists when collection exists."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_db.list_collection_names = AsyncMock(
            return_value=["users", "products", "orders"]
        )

        adapter._connected = True
        adapter._db = mock_db

        # Check existence
        exists = await adapter.collection_exists("users")

        # Verify
        assert exists is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self):
        """Test collection_exists when collection doesn't exist."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        # Setup connected state
        mock_db = MagicMock()
        mock_db.list_collection_names = AsyncMock(
            return_value=["users", "products", "orders"]
        )

        adapter._connected = True
        adapter._db = mock_db

        # Check existence
        exists = await adapter.collection_exists("nonexistent")

        # Verify
        assert exists is False


class TestMongoDBAdapterUtilityMethods:
    """Test MongoDB adapter utility methods."""

    def test_sanitize_connection_string_with_password(self):
        """Test connection string sanitization."""
        adapter = MongoDBAdapter("mongodb://user:password123@localhost:27017/testdb")

        sanitized = adapter._sanitize_connection_string(
            "mongodb://user:password123@localhost:27017/testdb"
        )

        assert "password123" not in sanitized
        assert "***" in sanitized

    def test_sanitize_connection_string_without_password(self):
        """Test connection string sanitization without password."""
        adapter = MongoDBAdapter("mongodb://localhost:27017/testdb")

        sanitized = adapter._sanitize_connection_string(
            "mongodb://localhost:27017/testdb"
        )

        assert sanitized == "mongodb://localhost:27017/testdb"

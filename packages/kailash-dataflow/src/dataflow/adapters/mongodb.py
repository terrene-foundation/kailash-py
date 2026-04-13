"""
MongoDB Adapter for DataFlow.

Provides document database operations using Motor async driver.

Motor is imported lazily inside :meth:`MongoDBAdapter.connect` so that
merely importing :mod:`dataflow` (e.g. ``from dataflow import DataFlow``)
does not require motor/pymongo to be installed. The adapter raises a
descriptive ``ImportError`` at connect time if motor is missing.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from dataflow.adapters.base_adapter import BaseAdapter

# Motor types are runtime-only — see ``connect()`` for the lazy import.
# The class attributes ``_client`` and ``_db`` are typed as ``Any`` so
# CodeQL's static analysis does not flag a TYPE_CHECKING-block import
# as unused (the alternative — string forward references inside an
# ``if TYPE_CHECKING:`` block — generates a ``py/unused-import`` false
# positive because CodeQL does not parse string annotations).
# The runtime types are ``motor.motor_asyncio.AsyncIOMotorClient`` and
# ``motor.motor_asyncio.AsyncIOMotorDatabase`` respectively; see the
# docstrings on the attributes for documentation.

logger = logging.getLogger(__name__)


class MongoDBAdapter(BaseAdapter):
    """MongoDB document database adapter using Motor async driver.

    Key Differences from SQL Adapters:
    - Document-based, not relational
    - Flexible schema (schemaless)
    - No SQL queries (MongoDB query language)
    - Aggregation pipelines instead of JOINs
    - Different indexing strategies

    Example:
        >>> adapter = MongoDBAdapter("mongodb://localhost:27017/mydb")
        >>> await adapter.connect()
        >>> result_id = await adapter.insert_one("users", {"name": "Alice"})
        >>> documents = await adapter.find("users", {"name": "Alice"})
    """

    def __init__(
        self, connection_string: str, database_name: Optional[str] = None, **kwargs
    ):
        """
        Initialize MongoDB adapter.

        Args:
            connection_string: MongoDB connection string
                - mongodb://localhost:27017/mydb (standalone)
                - mongodb://user:pass@localhost:27017/mydb?authSource=admin
                - mongodb+srv://cluster.mongodb.net/mydb (Atlas)
            database_name: Database name (optional, can be in connection string)
            **kwargs: Additional Motor client options
                - maxPoolSize: Maximum connection pool size (default: 100)
                - minPoolSize: Minimum connection pool size (default: 10)
                - serverSelectionTimeoutMS: Timeout for server selection
                - connectTimeoutMS: Timeout for connection attempts
                - retryWrites: Enable retryable writes (default: True)
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.client_options = kwargs

        # Runtime type: motor.motor_asyncio.AsyncIOMotorClient (typed
        # as Any to avoid CodeQL's TYPE_CHECKING-block false positive).
        self._client: Optional[Any] = None
        # Runtime type: motor.motor_asyncio.AsyncIOMotorDatabase.
        self._db: Optional[Any] = None
        self._connected = False

        logger.info(
            f"MongoDBAdapter initialized with connection string: {self._sanitize_connection_string(connection_string)}"
        )

    @property
    def adapter_type(self) -> str:
        """Get adapter type category.

        Returns:
            str: "document" (not "sql")
        """
        return "document"

    @property
    def source_type(self) -> str:
        """Get specific source type identifier.

        Returns:
            str: "mongodb"
        """
        return "mongodb"

    async def connect(self) -> None:
        """Establish MongoDB connection.

        Creates Motor client and connects to database.
        Verifies connection with ping command.

        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            logger.warning("Already connected to MongoDB")
            return

        try:
            # Lazy import — motor/pymongo are optional for projects
            # that don't use MongoDB. A descriptive ImportError here
            # is better than a top-level ModuleNotFoundError every
            # time `from dataflow import DataFlow` runs.
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
            except ImportError as exc:
                raise ImportError(
                    "MongoDB support requires the 'motor' driver. "
                    "Install it with: pip install motor pymongo"
                ) from exc

            # Create Motor client
            self._client = AsyncIOMotorClient(
                self.connection_string, **self.client_options
            )

            # Extract database name from connection string or use provided name
            if self.database_name:
                db_name = self.database_name
            else:
                # Parse database name from connection string
                # mongodb://localhost:27017/mydb -> mydb
                from urllib.parse import urlparse

                from kailash.utils.url_credentials import (
                    preencode_password_special_chars,
                )

                parsed = urlparse(
                    preencode_password_special_chars(self.connection_string)
                )
                db_name = parsed.path.lstrip("/")
                if not db_name:
                    raise ValueError(
                        "Database name must be provided either in connection string or database_name parameter"
                    )

            self._db = self._client[db_name]

            # Verify connection
            await self._client.admin.command("ping")

            self._connected = True
            logger.info(
                "mongodb.connected_to_mongodb_database", extra={"db_name": db_name}
            )

        except Exception as e:
            logger.error(
                "mongodb.failed_to_connect_to_mongodb", extra={"error": str(e)}
            )
            raise ConnectionError(f"MongoDB connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Close MongoDB connection.

        Closes Motor client and releases resources.
        """
        if not self._connected:
            logger.warning("Not connected to MongoDB")
            return

        try:
            if self._client:
                self._client.close()

            self._connected = False
            self._client = None
            self._db = None

            logger.info("Disconnected from MongoDB")

        except Exception as e:
            logger.error(
                "mongodb.error_disconnecting_from_mongodb", extra={"error": str(e)}
            )
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Check MongoDB connection and server status.

        Returns:
            dict: Health status information including:
                - connected: Whether connection is active
                - database: Database name
                - server_info: Server version and stats
                - collections: Number of collections

        Raises:
            Exception: If health check fails
        """
        if not self._connected or self._client is None:
            return {"connected": False, "database": None, "error": "Not connected"}

        try:
            # Ping server
            await self._client.admin.command("ping")

            # Get server info
            server_info = await self._client.server_info()

            # Get database stats
            stats = await self._db.command("dbStats")

            # List collections
            collection_names = await self._db.list_collection_names()

            return {
                "connected": True,
                "database": self._db.name,
                "server_version": server_info.get("version"),
                "collections_count": len(collection_names),
                "data_size": stats.get("dataSize", 0),
                "storage_size": stats.get("storageSize", 0),
                "indexes": stats.get("indexes", 0),
            }

        except Exception as e:
            logger.error("mongodb.health_check_failed", extra={"error": str(e)})
            return {
                "connected": False,
                "database": self._db.name if self._db else None,
                "error": str(e),
            }

    def supports_feature(self, feature: str) -> bool:
        """Check if MongoDB supports a specific feature.

        Supported features:
        - "documents": Document operations
        - "flexible_schema": Schemaless operations
        - "aggregation": Aggregation pipelines
        - "text_search": Full-text search
        - "geospatial": Geospatial queries
        - "transactions": Multi-document transactions (replica sets only)
        - "change_streams": Real-time data changes
        - "gridfs": Large file storage

        Args:
            feature: Feature name to check

        Returns:
            bool: True if feature is supported
        """
        mongodb_features = {
            "documents",
            "flexible_schema",
            "aggregation",
            "text_search",
            "geospatial",
            "transactions",
            "change_streams",
            "gridfs",
        }
        return feature in mongodb_features

    # ==================== Document Operations ====================

    async def insert_one(self, collection: str, document: dict, **options) -> str:
        """Insert single document into collection.

        Args:
            collection: Collection name
            document: Document to insert
            **options: Additional insert options
                - bypass_document_validation: Skip validation

        Returns:
            str: Inserted document ID

        Raises:
            ValueError: If document is empty
            Exception: If insert fails
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not document:
            raise ValueError("Document cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.insert_one(document, **options)

            inserted_id = str(result.inserted_id)
            logger.debug(
                "mongodb.inserted_document_with_id_into",
                extra={"inserted_id": inserted_id, "collection": collection},
            )

            return inserted_id

        except Exception as e:
            logger.error(
                "mongodb.failed_to_insert_document_into",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def insert_many(
        self, collection: str, documents: List[dict], **options
    ) -> List[str]:
        """Bulk insert documents into collection.

        Args:
            collection: Collection name
            documents: List of documents to insert
            **options: Additional insert options
                - ordered: Insert in order (default: True)
                - bypass_document_validation: Skip validation

        Returns:
            list[str]: List of inserted document IDs

        Raises:
            ValueError: If documents list is empty
            Exception: If insert fails
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not documents:
            raise ValueError("Documents list cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.insert_many(documents, **options)

            inserted_ids = [str(oid) for oid in result.inserted_ids]
            logger.info(
                "mongodb.inserted_documents_into",
                extra={"count": len(inserted_ids), "collection": collection},
            )

            return inserted_ids

        except Exception as e:
            logger.error(
                "mongodb.failed_to_bulk_insert_into",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def find_one(
        self, collection: str, filter: dict, **options
    ) -> Optional[dict]:
        """Find single document by filter.

        Args:
            collection: Collection name
            filter: Query filter (MongoDB query language)
            **options: Additional find options
                - projection: Fields to include/exclude
                - sort: Sort specification

        Returns:
            dict or None: Found document or None

        Example:
            >>> doc = await adapter.find_one("users", {"email": "alice@example.com"})
            >>> doc = await adapter.find_one("users", {"age": {"$gte": 18}})
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            coll = self._db[collection]
            document = await coll.find_one(filter, **options)

            if document:
                logger.debug(
                    "mongodb.found_document_in", extra={"collection": collection}
                )
            else:
                logger.debug(
                    "mongodb.no_document_found_in_matching_filter",
                    extra={"collection": collection},
                )

            return document

        except Exception as e:
            logger.error(
                "mongodb.failed_to_find_document_in",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def find(
        self,
        collection: str,
        filter: Optional[dict] = None,
        projection: Optional[dict] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: int = 0,
        skip: int = 0,
        **options,
    ) -> List[dict]:
        """Find multiple documents with pagination.

        Args:
            collection: Collection name
            filter: Query filter (default: {})
            projection: Fields to include/exclude
            sort: Sort specification as list of (field, direction) tuples
                  Direction: 1 for ascending, -1 for descending
            limit: Maximum number of documents to return (0 = no limit)
            skip: Number of documents to skip
            **options: Additional find options

        Returns:
            list[dict]: List of found documents

        Example:
            >>> docs = await adapter.find("users", {"status": "active"}, limit=10)
            >>> docs = await adapter.find("users",
            ...     {"age": {"$gte": 18}},
            ...     sort=[("name", 1), ("created_at", -1)]
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        filter = filter or {}

        try:
            coll = self._db[collection]
            cursor = coll.find(filter, projection=projection, **options)

            if sort:
                cursor = cursor.sort(sort)

            if skip > 0:
                cursor = cursor.skip(skip)

            if limit > 0:
                cursor = cursor.limit(limit)

            documents = await cursor.to_list(length=None)

            logger.debug(
                "mongodb.found_documents_in",
                extra={"count": len(documents), "collection": collection},
            )

            return documents

        except Exception as e:
            logger.error(
                "mongodb.failed_to_find_documents_in",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def update_one(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
        **options,
    ) -> dict:
        """Update single document.

        Args:
            collection: Collection name
            filter: Query filter to find document
            update: Update operations (must use update operators like $set)
            upsert: Create document if not found (default: False)
            **options: Additional update options

        Returns:
            dict: Update result with:
                - matched_count: Number of documents matched
                - modified_count: Number of documents modified
                - upserted_id: ID of upserted document (if upsert=True)

        Example:
            >>> result = await adapter.update_one(
            ...     "users",
            ...     {"email": "alice@example.com"},
            ...     {"$set": {"status": "active"}}
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not filter:
            raise ValueError("Filter cannot be empty")

        if not update:
            raise ValueError("Update cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.update_one(filter, update, upsert=upsert, **options)

            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            }

        except Exception as e:
            logger.error(
                "mongodb.failed_to_update_document_in",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def update_many(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
        **options,
    ) -> dict:
        """Update multiple documents.

        Args:
            collection: Collection name
            filter: Query filter to find documents
            update: Update operations (must use update operators like $set)
            upsert: Create document if not found (default: False)
            **options: Additional update options

        Returns:
            dict: Update result with:
                - matched_count: Number of documents matched
                - modified_count: Number of documents modified
                - upserted_id: ID of upserted document (if upsert=True)

        Example:
            >>> result = await adapter.update_many(
            ...     "users",
            ...     {"status": "inactive"},
            ...     {"$set": {"archived": True}}
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not filter:
            raise ValueError("Filter cannot be empty")

        if not update:
            raise ValueError("Update cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.update_many(filter, update, upsert=upsert, **options)

            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            }

        except Exception as e:
            logger.error(
                "mongodb.failed_to_update_documents_in",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def delete_one(self, collection: str, filter: dict, **options) -> int:
        """Delete single document.

        Args:
            collection: Collection name
            filter: Query filter to find document
            **options: Additional delete options

        Returns:
            int: Number of documents deleted (0 or 1)

        Example:
            >>> count = await adapter.delete_one(
            ...     "users",
            ...     {"email": "alice@example.com"}
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not filter:
            raise ValueError("Filter cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.delete_one(filter, **options)

            logger.debug(
                f"Deleted {result.deleted_count} document(s) from {collection}"
            )

            return result.deleted_count

        except Exception as e:
            logger.error(
                "mongodb.failed_to_delete_document_from",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def delete_many(self, collection: str, filter: dict, **options) -> int:
        """Delete multiple documents.

        Args:
            collection: Collection name
            filter: Query filter to find documents
            **options: Additional delete options

        Returns:
            int: Number of documents deleted

        Example:
            >>> count = await adapter.delete_many(
            ...     "users",
            ...     {"status": "inactive"}
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not filter:
            raise ValueError("Filter cannot be empty")

        try:
            coll = self._db[collection]
            result = await coll.delete_many(filter, **options)

            logger.info(
                "mongodb.deleted_document_s_from",
                extra={"deleted_count": result.deleted_count, "collection": collection},
            )

            return result.deleted_count

        except Exception as e:
            logger.error(
                "mongodb.failed_to_delete_documents_from",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def count_documents(
        self, collection: str, filter: Optional[dict] = None, **options
    ) -> int:
        """Count documents matching filter.

        Args:
            collection: Collection name
            filter: Query filter (default: {})
            **options: Additional count options
                - limit: Maximum count
                - skip: Number to skip

        Returns:
            int: Number of documents matching filter

        Example:
            >>> count = await adapter.count_documents("users", {"status": "active"})
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        filter = filter or {}

        try:
            coll = self._db[collection]
            count = await coll.count_documents(filter, **options)

            logger.debug(
                "mongodb.counted_documents_in",
                extra={"count": count, "collection": collection},
            )

            return count

        except Exception as e:
            logger.error(
                "mongodb.failed_to_count_documents_in",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def aggregate(
        self, collection: str, pipeline: List[dict], **options
    ) -> List[dict]:
        """Execute aggregation pipeline.

        Args:
            collection: Collection name
            pipeline: Aggregation pipeline stages
            **options: Additional aggregation options
                - allowDiskUse: Allow using disk for large operations

        Returns:
            list[dict]: Aggregation results

        Example:
            >>> results = await adapter.aggregate("orders", [
            ...     {"$match": {"status": "completed"}},
            ...     {"$group": {"_id": "$user_id", "total": {"$sum": "$amount"}}},
            ...     {"$sort": {"total": -1}},
            ...     {"$limit": 10}
            ... ])
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not pipeline:
            raise ValueError("Pipeline cannot be empty")

        try:
            coll = self._db[collection]
            cursor = coll.aggregate(pipeline, **options)
            results = await cursor.to_list(length=None)

            logger.debug(
                "mongodb.aggregation_on_returned_results",
                extra={"collection": collection, "count": len(results)},
            )

            return results

        except Exception as e:
            logger.error(
                "mongodb.failed_to_execute_aggregation_on",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    # ==================== Index Management ====================

    async def create_index(
        self,
        collection: str,
        keys: List[Tuple[str, int]],
        unique: bool = False,
        sparse: bool = False,
        name: Optional[str] = None,
        **options,
    ) -> str:
        """Create index on collection.

        Args:
            collection: Collection name
            keys: Index keys as list of (field, direction) tuples
                  Direction: 1 for ascending, -1 for descending
            unique: Create unique index (default: False)
            sparse: Create sparse index (default: False)
            name: Index name (default: auto-generated)
            **options: Additional index options

        Returns:
            str: Index name

        Example:
            >>> index_name = await adapter.create_index(
            ...     "users",
            ...     [("email", 1)],
            ...     unique=True
            ... )
            >>> index_name = await adapter.create_index(
            ...     "users",
            ...     [("last_name", 1), ("first_name", 1)]
            ... )
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        if not keys:
            raise ValueError("Keys cannot be empty")

        try:
            coll = self._db[collection]
            index_name = await coll.create_index(
                keys, unique=unique, sparse=sparse, name=name, **options
            )

            logger.info(
                "mongodb.created_index_on",
                extra={"index_name": index_name, "collection": collection},
            )

            return index_name

        except Exception as e:
            logger.error(
                "mongodb.failed_to_create_index_on",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def list_indexes(self, collection: str) -> List[dict]:
        """List all indexes on collection.

        Args:
            collection: Collection name

        Returns:
            list[dict]: List of index specifications

        Example:
            >>> indexes = await adapter.list_indexes("users")
            >>> for index in indexes:
            ...     print(f"{index['name']}: {index['key']}")
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            coll = self._db[collection]
            cursor = coll.list_indexes()
            indexes = await cursor.to_list(length=None)

            logger.debug(
                "mongodb.listed_indexes_on",
                extra={"count": len(indexes), "collection": collection},
            )

            return indexes

        except Exception as e:
            logger.error(
                "mongodb.failed_to_list_indexes_on",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def drop_index(self, collection: str, index_name: str) -> None:
        """Drop specific index.

        Args:
            collection: Collection name
            index_name: Name of index to drop

        Example:
            >>> await adapter.drop_index("users", "email_1")
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            coll = self._db[collection]
            await coll.drop_index(index_name)

            logger.info(
                "mongodb.dropped_index_from",
                extra={"index_name": index_name, "collection": collection},
            )

        except Exception as e:
            logger.error(
                "mongodb.failed_to_drop_index_from",
                extra={
                    "index_name": index_name,
                    "collection": collection,
                    "error": str(e),
                },
            )
            raise

    # ==================== Collection Management ====================

    async def create_collection(self, collection: str, **options) -> None:
        """Create collection with optional validation schema.

        Args:
            collection: Collection name
            **options: Collection options
                - validator: JSON schema for document validation
                - validationLevel: "strict" or "moderate"
                - validationAction: "error" or "warn"

        Example:
            >>> await adapter.create_collection("users", validator={
            ...     "$jsonSchema": {
            ...         "bsonType": "object",
            ...         "required": ["name", "email"],
            ...         "properties": {
            ...             "name": {"bsonType": "string"},
            ...             "email": {"bsonType": "string"}
            ...         }
            ...     }
            ... })
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            await self._db.create_collection(collection, **options)

            logger.info("mongodb.created_collection", extra={"collection": collection})

        except Exception as e:
            logger.error(
                "mongodb.failed_to_create_collection",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def drop_collection(self, collection: str) -> None:
        """Drop collection.

        Args:
            collection: Collection name

        Example:
            >>> await adapter.drop_collection("temp_data")
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            await self._db.drop_collection(collection)

            logger.info("mongodb.dropped_collection", extra={"collection": collection})

        except Exception as e:
            logger.error(
                "mongodb.failed_to_drop_collection",
                extra={"collection": collection, "error": str(e)},
            )
            raise

    async def list_collections(self) -> List[str]:
        """List all collections in database.

        Returns:
            list[str]: List of collection names

        Example:
            >>> collections = await adapter.list_collections()
            >>> print(f"Found {len(collections)} collections")
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection_names = await self._db.list_collection_names()

            logger.debug(
                "mongodb.listed_collections", extra={"count": len(collection_names)}
            )

            return collection_names

        except Exception as e:
            logger.error("mongodb.failed_to_list_collections", extra={"error": str(e)})
            raise

    async def collection_exists(self, collection: str) -> bool:
        """Check if collection exists.

        Args:
            collection: Collection name

        Returns:
            bool: True if collection exists

        Example:
            >>> if await adapter.collection_exists("users"):
            ...     print("Users collection exists")
        """
        if not self._connected or self._db is None:
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection_names = await self._db.list_collection_names()
            exists = collection in collection_names

            logger.debug(
                "mongodb.collection_exists",
                extra={"collection": collection, "exists": exists},
            )

            return exists

        except Exception as e:
            logger.error(
                "mongodb.failed_to_check_collection_existence", extra={"error": str(e)}
            )
            raise

    # ==================== Utility Methods ====================

    def _sanitize_connection_string(self, connection_string: str) -> str:
        """Sanitize connection string for logging (hide password).

        Args:
            connection_string: Original connection string

        Returns:
            str: Sanitized connection string
        """
        # Delegates to the canonical URL masker so that passwords
        # containing encoded "@" (%40) and other special characters
        # are handled via urlparse, not a fragile str.replace.
        try:
            from dataflow.utils.masking import mask_url

            return mask_url(connection_string)

        except Exception:
            return "mongodb://***"

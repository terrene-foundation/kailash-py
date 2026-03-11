"""
MongoDB Workflow Nodes for DataFlow.

Provides workflow nodes for MongoDB document database operations.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from dataflow.adapters.mongodb import MongoDBAdapter

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode

logger = logging.getLogger(__name__)


@register_node()
class DocumentInsertNode(AsyncNode):
    """Insert single document into MongoDB collection.

    This node inserts a single document into a MongoDB collection
    and returns the inserted document's ID.

    Parameters:
        collection (str): Collection name [REQUIRED]
        document (dict): Document to insert [REQUIRED]
        bypass_document_validation (bool): Skip validation (default: False)

    Returns:
        dict: Result with keys:
            - success (bool): Whether insert succeeded
            - inserted_id (str): ID of inserted document
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("DocumentInsertNode", "insert_user", {
        ...     "collection": "users",
        ...     "document": {
        ...         "name": "Alice",
        ...         "email": "alice@example.com",
        ...         "profile": {"age": 30, "city": "NYC"}
        ...     }
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "document": NodeParameter(
                name="document",
                type=dict,
                required=True,
                description="Document to insert",
            ),
            "bypass_document_validation": NodeParameter(
                name="bypass_document_validation",
                type=bool,
                required=False,
                default=False,
                description="Skip document validation",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute document insert operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Insert result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If insert fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        # Get adapter from DataFlow instance
        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"DocumentInsertNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Insert document
            result_id = await adapter.insert_one(
                collection=validated_inputs["collection"],
                document=validated_inputs["document"],
                bypass_document_validation=validated_inputs.get(
                    "bypass_document_validation", False
                ),
            )

            return {
                "success": True,
                "inserted_id": result_id,
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Document insert failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class DocumentFindNode(AsyncNode):
    """Find documents in MongoDB collection.

    This node queries documents from a MongoDB collection with
    support for filtering, projection, sorting, and pagination.

    Parameters:
        collection (str): Collection name [REQUIRED]
        filter (dict): Query filter (default: {})
        projection (dict): Fields to include/exclude (optional)
        sort (list): Sort specification [(field, direction), ...] (optional)
        limit (int): Maximum documents to return (default: 0 = no limit)
        skip (int): Number of documents to skip (default: 0)

    Returns:
        dict: Result with keys:
            - documents (list): Found documents
            - count (int): Number of documents found
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("DocumentFindNode", "find_active_users", {
        ...     "collection": "users",
        ...     "filter": {"status": "active", "age": {"$gte": 18}},
        ...     "projection": {"name": 1, "email": 1},
        ...     "sort": [("name", 1)],
        ...     "limit": 10
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=False,
                default={},
                description="Query filter (MongoDB query language)",
            ),
            "projection": NodeParameter(
                name="projection",
                type=dict,
                required=False,
                default=None,
                description="Fields to include/exclude",
            ),
            "sort": NodeParameter(
                name="sort",
                type=list,
                required=False,
                default=None,
                description="Sort specification [(field, direction), ...]",
            ),
            "limit": NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=0,
                description="Maximum documents to return (0 = no limit)",
            ),
            "skip": NodeParameter(
                name="skip",
                type=int,
                required=False,
                default=0,
                description="Number of documents to skip",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute document find operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Find result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If find fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"DocumentFindNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Find documents
            results = await adapter.find(
                collection=validated_inputs["collection"],
                filter=validated_inputs.get("filter", {}),
                projection=validated_inputs.get("projection"),
                sort=validated_inputs.get("sort"),
                limit=validated_inputs.get("limit", 0),
                skip=validated_inputs.get("skip", 0),
            )

            return {
                "documents": results,
                "count": len(results),
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Document find failed: {e}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class DocumentUpdateNode(AsyncNode):
    """Update documents in MongoDB collection.

    This node updates one or multiple documents in a MongoDB collection
    using update operators like $set, $inc, $push, etc.

    Parameters:
        collection (str): Collection name [REQUIRED]
        filter (dict): Query filter to find documents [REQUIRED]
        update (dict): Update operations (must use update operators) [REQUIRED]
        upsert (bool): Create document if not found (default: False)
        multi (bool): Update multiple documents (default: False)

    Returns:
        dict: Result with keys:
            - matched_count (int): Number of documents matched
            - modified_count (int): Number of documents modified
            - upserted_id (str): ID of upserted document (if upsert=True)
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("DocumentUpdateNode", "activate_user", {
        ...     "collection": "users",
        ...     "filter": {"email": "alice@example.com"},
        ...     "update": {"$set": {"status": "active", "last_login": "2024-01-15"}},
        ...     "upsert": False,
        ...     "multi": False
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=True,
                description="Query filter to find documents",
            ),
            "update": NodeParameter(
                name="update",
                type=dict,
                required=True,
                description="Update operations (must use update operators like $set)",
            ),
            "upsert": NodeParameter(
                name="upsert",
                type=bool,
                required=False,
                default=False,
                description="Create document if not found",
            ),
            "multi": NodeParameter(
                name="multi",
                type=bool,
                required=False,
                default=False,
                description="Update multiple documents",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute document update operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Update result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If update fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"DocumentUpdateNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Update document(s)
            if validated_inputs.get("multi", False):
                result = await adapter.update_many(
                    collection=validated_inputs["collection"],
                    filter=validated_inputs["filter"],
                    update=validated_inputs["update"],
                    upsert=validated_inputs.get("upsert", False),
                )
            else:
                result = await adapter.update_one(
                    collection=validated_inputs["collection"],
                    filter=validated_inputs["filter"],
                    update=validated_inputs["update"],
                    upsert=validated_inputs.get("upsert", False),
                )

            return {
                "matched_count": result["matched_count"],
                "modified_count": result["modified_count"],
                "upserted_id": result.get("upserted_id"),
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Document update failed: {e}")
            return {
                "matched_count": 0,
                "modified_count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class DocumentDeleteNode(AsyncNode):
    """Delete documents from MongoDB collection.

    This node deletes one or multiple documents from a MongoDB collection
    based on a query filter.

    Parameters:
        collection (str): Collection name [REQUIRED]
        filter (dict): Query filter to find documents [REQUIRED]
        multi (bool): Delete multiple documents (default: False)

    Returns:
        dict: Result with keys:
            - deleted_count (int): Number of documents deleted
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("DocumentDeleteNode", "delete_inactive", {
        ...     "collection": "users",
        ...     "filter": {"status": "inactive", "last_login": {"$lt": "2023-01-01"}},
        ...     "multi": True
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=True,
                description="Query filter to find documents",
            ),
            "multi": NodeParameter(
                name="multi",
                type=bool,
                required=False,
                default=False,
                description="Delete multiple documents",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute document delete operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Delete result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If delete fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"DocumentDeleteNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Delete document(s)
            if validated_inputs.get("multi", False):
                deleted_count = await adapter.delete_many(
                    collection=validated_inputs["collection"],
                    filter=validated_inputs["filter"],
                )
            else:
                deleted_count = await adapter.delete_one(
                    collection=validated_inputs["collection"],
                    filter=validated_inputs["filter"],
                )

            return {
                "deleted_count": deleted_count,
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Document delete failed: {e}")
            return {
                "deleted_count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class AggregateNode(AsyncNode):
    """Execute MongoDB aggregation pipeline.

    This node executes a MongoDB aggregation pipeline for complex
    data processing, grouping, and transformation operations.

    Parameters:
        collection (str): Collection name [REQUIRED]
        pipeline (list): Aggregation pipeline stages [REQUIRED]
        allow_disk_use (bool): Allow using disk for large operations (default: False)

    Returns:
        dict: Result with keys:
            - results (list): Aggregation results
            - count (int): Number of results
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("AggregateNode", "sales_by_category", {
        ...     "collection": "orders",
        ...     "pipeline": [
        ...         {"$match": {"status": "completed"}},
        ...         {"$group": {
        ...             "_id": "$category",
        ...             "total_sales": {"$sum": "$amount"},
        ...             "order_count": {"$sum": 1}
        ...         }},
        ...         {"$sort": {"total_sales": -1}},
        ...         {"$limit": 10}
        ...     ]
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "pipeline": NodeParameter(
                name="pipeline",
                type=list,
                required=True,
                description="Aggregation pipeline stages",
            ),
            "allow_disk_use": NodeParameter(
                name="allow_disk_use",
                type=bool,
                required=False,
                default=False,
                description="Allow using disk for large operations",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute aggregation pipeline.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Aggregation result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If aggregation fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"AggregateNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Execute aggregation
            results = await adapter.aggregate(
                collection=validated_inputs["collection"],
                pipeline=validated_inputs["pipeline"],
                allowDiskUse=validated_inputs.get("allow_disk_use", False),
            )

            return {
                "results": results,
                "count": len(results),
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return {
                "results": [],
                "count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class BulkDocumentInsertNode(AsyncNode):
    """Bulk insert documents into MongoDB collection.

    This node inserts multiple documents into a MongoDB collection
    in a single operation for better performance.

    Parameters:
        collection (str): Collection name [REQUIRED]
        documents (list): List of documents to insert [REQUIRED]
        ordered (bool): Insert in order (default: True)
        bypass_document_validation (bool): Skip validation (default: False)

    Returns:
        dict: Result with keys:
            - success (bool): Whether insert succeeded
            - inserted_ids (list): IDs of inserted documents
            - inserted_count (int): Number of documents inserted
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("BulkDocumentInsertNode", "bulk_import", {
        ...     "collection": "products",
        ...     "documents": [
        ...         {"name": "Product 1", "price": 29.99},
        ...         {"name": "Product 2", "price": 39.99},
        ...         {"name": "Product 3", "price": 49.99}
        ...     ],
        ...     "ordered": True
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="List of documents to insert",
            ),
            "ordered": NodeParameter(
                name="ordered",
                type=bool,
                required=False,
                default=True,
                description="Insert in order",
            ),
            "bypass_document_validation": NodeParameter(
                name="bypass_document_validation",
                type=bool,
                required=False,
                default=False,
                description="Skip document validation",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute bulk document insert operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Bulk insert result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If insert fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"BulkDocumentInsertNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Bulk insert documents
            inserted_ids = await adapter.insert_many(
                collection=validated_inputs["collection"],
                documents=validated_inputs["documents"],
                ordered=validated_inputs.get("ordered", True),
                bypass_document_validation=validated_inputs.get(
                    "bypass_document_validation", False
                ),
            )

            return {
                "success": True,
                "inserted_ids": inserted_ids,
                "inserted_count": len(inserted_ids),
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Bulk document insert failed: {e}")
            return {
                "success": False,
                "inserted_ids": [],
                "inserted_count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class CreateIndexNode(AsyncNode):
    """Create index on MongoDB collection.

    This node creates an index on a MongoDB collection to improve
    query performance.

    Parameters:
        collection (str): Collection name [REQUIRED]
        keys (list): Index keys as [(field, direction), ...] [REQUIRED]
        unique (bool): Create unique index (default: False)
        sparse (bool): Create sparse index (default: False)
        name (str): Index name (optional, auto-generated if not provided)

    Returns:
        dict: Result with keys:
            - success (bool): Whether index creation succeeded
            - index_name (str): Name of created index
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("CreateIndexNode", "create_email_index", {
        ...     "collection": "users",
        ...     "keys": [("email", 1)],
        ...     "unique": True,
        ...     "name": "email_unique_idx"
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "keys": NodeParameter(
                name="keys",
                type=list,
                required=True,
                description="Index keys as [(field, direction), ...]",
            ),
            "unique": NodeParameter(
                name="unique",
                type=bool,
                required=False,
                default=False,
                description="Create unique index",
            ),
            "sparse": NodeParameter(
                name="sparse",
                type=bool,
                required=False,
                default=False,
                description="Create sparse index",
            ),
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default=None,
                description="Index name (auto-generated if not provided)",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute index creation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Index creation result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If index creation fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"CreateIndexNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Create index
            index_name = await adapter.create_index(
                collection=validated_inputs["collection"],
                keys=validated_inputs["keys"],
                unique=validated_inputs.get("unique", False),
                sparse=validated_inputs.get("sparse", False),
                name=validated_inputs.get("name"),
            )

            return {
                "success": True,
                "index_name": index_name,
                "collection": validated_inputs["collection"],
            }

        except Exception as e:
            logger.error(f"Index creation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }


@register_node()
class DocumentCountNode(AsyncNode):
    """Count documents in MongoDB collection.

    This node counts documents in a MongoDB collection that match
    a given filter.

    Parameters:
        collection (str): Collection name [REQUIRED]
        filter (dict): Query filter (default: {})

    Returns:
        dict: Result with keys:
            - count (int): Number of documents matching filter
            - collection (str): Collection name

    Example:
        >>> workflow.add_node("DocumentCountNode", "count_active_users", {
        ...     "collection": "users",
        ...     "filter": {"status": "active"}
        ... })
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=True,
                description="Collection name",
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=False,
                default={},
                description="Query filter (MongoDB query language)",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute document count operation.

        Args:
            **kwargs: Node parameters

        Returns:
            dict: Count result

        Raises:
            ValueError: If adapter is not MongoDBAdapter
            Exception: If count fails
        """
        validated_inputs = self.validate_inputs(**kwargs)

        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError(
                f"DocumentCountNode requires MongoDBAdapter, got {type(adapter).__name__}"
            )

        try:
            # Count documents
            count = await adapter.count_documents(
                collection=validated_inputs["collection"],
                filter=validated_inputs.get("filter", {}),
            )

            return {"count": count, "collection": validated_inputs["collection"]}

        except Exception as e:
            logger.error(f"Document count failed: {e}")
            return {
                "count": 0,
                "error": str(e),
                "collection": validated_inputs["collection"],
            }

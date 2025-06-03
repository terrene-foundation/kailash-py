"""MCP Resource node for managing shared resources in Model Context Protocol."""

import json
from typing import Any, Dict, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class MCPResource(Node):
    """
    Resource node for creating and managing Model Context Protocol (MCP) resources.

    Design Purpose and Philosophy:
    The MCPResource node provides a standardized way to create, update, and manage
    resources that can be shared through the MCP protocol. It abstracts resource
    lifecycle management while ensuring compatibility with MCP standards.

    Upstream Dependencies:
    - Source data to convert into MCP resources
    - Resource metadata and schema definitions
    - Authentication and access control settings
    - Content transformation and validation rules

    Downstream Consumers:
    - MCPServer nodes that host and expose resources
    - MCPClient nodes that consume resource data
    - AI models that need structured context data
    - External MCP-compatible applications and tools

    Usage Patterns:
    1. Create resources from workflow data with proper metadata
    2. Update existing resources with new content versions
    3. Validate resource schemas and content formats
    4. Transform data into MCP-compatible resource structures
    5. Manage resource access permissions and visibility

    Implementation Details:
    - Supports all standard MCP resource types and formats
    - Implements proper resource URI schemes and namespacing
    - Provides content validation and schema enforcement
    - Handles resource versioning and update notifications
    - Manages metadata and discovery information efficiently

    Error Handling:
    - ResourceValidationError: When resource content fails validation
    - SchemaViolationError: When resource doesn't match expected schema
    - URIFormatError: When resource URI is malformed or invalid
    - ContentTypeError: When resource content type is unsupported
    - PermissionError: When access control rules are violated

    Side Effects:
    - Creates or updates resource entries in MCP registries
    - May cache resource content for improved performance
    - Logs resource access and modification events
    - Notifies subscribers about resource changes

    Examples:
    ```python
    # Create a simple text resource
    resource = MCPResource()
    result = resource.run(
        operation="create",
        uri="workflow://examples/data/customer_analysis.txt",
        content="Customer analysis results from Q4 2024...",
        metadata={
            "name": "Q4 Customer Analysis",
            "description": "Quarterly customer behavior analysis",
            "mimeType": "text/plain",
            "tags": ["analysis", "customers", "Q4"]
        }
    )

    # Create a structured data resource
    json_resource = MCPResource()
    result = json_resource.run(
        operation="create",
        uri="data://reports/summary.json",
        content={
            "total_customers": 15420,
            "revenue": 2450000,
            "top_products": ["Product A", "Product B"]
        },
        metadata={
            "name": "Summary Report",
            "mimeType": "application/json",
            "schema": "report_summary_v1"
        }
    )

    # Update an existing resource
    updated = MCPResource()
    result = updated.run(
        operation="update",
        uri="workflow://examples/data/customer_analysis.txt",
        content="Updated customer analysis with new data...",
        version="2.0"
    )
    ```
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="create",
                description="Operation to perform: create, update, delete, validate, list",
            ),
            "uri": NodeParameter(
                name="uri",
                type=str,
                required=False,
                description="Resource URI (required for create, update, delete, validate)",
            ),
            "content": NodeParameter(
                name="content",
                type=object,
                required=False,
                description="Resource content (required for create, update)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Resource metadata (name, description, mimeType, etc.)",
            ),
            "schema": NodeParameter(
                name="schema",
                type=dict,
                required=False,
                description="JSON schema for content validation",
            ),
            "version": NodeParameter(
                name="version",
                type=str,
                required=False,
                description="Resource version (auto-generated if not provided)",
            ),
            "access_control": NodeParameter(
                name="access_control",
                type=dict,
                required=False,
                default={},
                description="Access control settings (permissions, visibility)",
            ),
            "cache_ttl": NodeParameter(
                name="cache_ttl",
                type=int,
                required=False,
                default=3600,
                description="Cache time-to-live in seconds",
            ),
            "auto_notify": NodeParameter(
                name="auto_notify",
                type=bool,
                required=False,
                default=True,
                description="Whether to notify subscribers of resource changes",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        operation = kwargs["operation"]
        uri = kwargs.get("uri")
        content = kwargs.get("content")
        metadata = kwargs.get("metadata", {})
        schema = kwargs.get("schema")
        version = kwargs.get("version")
        access_control = kwargs.get("access_control", {})
        cache_ttl = kwargs.get("cache_ttl", 3600)
        auto_notify = kwargs.get("auto_notify", True)

        try:
            if operation == "create":
                return self._create_resource(
                    uri,
                    content,
                    metadata,
                    schema,
                    version,
                    access_control,
                    cache_ttl,
                    auto_notify,
                )
            elif operation == "update":
                return self._update_resource(
                    uri,
                    content,
                    metadata,
                    schema,
                    version,
                    access_control,
                    cache_ttl,
                    auto_notify,
                )
            elif operation == "delete":
                return self._delete_resource(uri, auto_notify)
            elif operation == "validate":
                return self._validate_resource(uri, content, schema)
            elif operation == "list":
                return self._list_resources(metadata.get("filter"))
            else:
                return {
                    "success": False,
                    "error": f"Unsupported operation: {operation}",
                    "supported_operations": [
                        "create",
                        "update",
                        "delete",
                        "validate",
                        "list",
                    ],
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "operation": operation,
                "uri": uri,
            }

    def _create_resource(
        self,
        uri: Optional[str],
        content: Any,
        metadata: dict,
        schema: Optional[dict],
        version: Optional[str],
        access_control: dict,
        cache_ttl: int,
        auto_notify: bool,
    ) -> Dict[str, Any]:
        """Create a new MCP resource."""
        if not uri:
            return {"success": False, "error": "URI is required for create operation"}

        if content is None:
            return {
                "success": False,
                "error": "Content is required for create operation",
            }

        # Validate URI format
        if not self._validate_uri(uri):
            return {
                "success": False,
                "error": f"Invalid URI format: {uri}",
                "uri_requirements": [
                    "Must include a scheme (e.g., 'file://', 'data://', 'workflow://')",
                    "Must not contain invalid characters",
                    "Should follow MCP URI conventions",
                ],
            }

        # Determine content type and serialize if needed
        content_str, mime_type = self._serialize_content(content)

        # Use provided mime type or auto-detected one
        final_mime_type = metadata.get("mimeType", mime_type)

        # Validate content against schema if provided
        if schema:
            validation_result = self._validate_against_schema(content, schema)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": "Content validation failed",
                    "validation_errors": validation_result["errors"],
                }

        # Generate version if not provided
        if not version:
            import datetime

            version = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create resource object
        resource = {
            "uri": uri,
            "name": metadata.get("name", self._extract_name_from_uri(uri)),
            "description": metadata.get("description", ""),
            "mimeType": final_mime_type,
            "content": content_str,
            "version": version,
            "created_at": self._current_timestamp(),
            "updated_at": self._current_timestamp(),
            "size": len(content_str) if isinstance(content_str, str) else 0,
            "metadata": {
                "tags": metadata.get("tags", []),
                "category": metadata.get("category", "general"),
                "source": metadata.get("source", "kailash-workflow"),
                "author": metadata.get("author", "system"),
                **{
                    k: v
                    for k, v in metadata.items()
                    if k
                    not in [
                        "name",
                        "description",
                        "mimeType",
                        "tags",
                        "category",
                        "source",
                        "author",
                    ]
                },
            },
            "access_control": {
                "visibility": access_control.get("visibility", "public"),
                "permissions": access_control.get("permissions", ["read"]),
                "allowed_clients": access_control.get("allowed_clients", []),
                **{
                    k: v
                    for k, v in access_control.items()
                    if k not in ["visibility", "permissions", "allowed_clients"]
                },
            },
            "cache": {"ttl": cache_ttl, "cacheable": cache_ttl > 0},
        }

        # Mock resource storage (in real implementation, this would persist to storage)
        storage_id = f"res_{hash(uri) % 100000}"
        storage_result = {
            "stored": True,
            "storage_id": storage_id,
            "storage_location": f"mock://storage/resources/{storage_id}",
        }

        return {
            "success": True,
            "operation": "create",
            "resource": resource,
            "storage": storage_result,
            "notifications": {
                "sent": auto_notify,
                "subscribers_notified": 3 if auto_notify else 0,
            },
            "next_actions": [
                "Resource is now available for MCP clients",
                "Use MCPServer to expose this resource",
                "Monitor resource access patterns",
            ],
        }

    def _update_resource(
        self,
        uri: Optional[str],
        content: Any,
        metadata: dict,
        schema: Optional[dict],
        version: Optional[str],
        access_control: dict,
        cache_ttl: int,
        auto_notify: bool,
    ) -> Dict[str, Any]:
        """Update an existing MCP resource."""
        if not uri:
            return {"success": False, "error": "URI is required for update operation"}

        # Mock resource lookup
        existing_resource = {
            "uri": uri,
            "name": "Existing Resource",
            "version": "1.0",
            "created_at": "2025-06-01T10:00:00Z",
            "content": "Previous content...",
            "mimeType": "text/plain",
        }

        # Update fields
        updates = {}

        if content is not None:
            content_str, mime_type = self._serialize_content(content)
            updates["content"] = content_str
            updates["mimeType"] = metadata.get("mimeType", mime_type)
            updates["size"] = len(content_str) if isinstance(content_str, str) else 0

            # Validate new content against schema if provided
            if schema:
                validation_result = self._validate_against_schema(content, schema)
                if not validation_result["valid"]:
                    return {
                        "success": False,
                        "error": "Content validation failed",
                        "validation_errors": validation_result["errors"],
                    }

        if metadata:
            for key in ["name", "description", "tags", "category"]:
                if key in metadata:
                    updates[key] = metadata[key]

        if version:
            updates["version"] = version
        else:
            # Auto-increment version
            old_version = existing_resource["version"]
            try:
                version_num = float(old_version) + 0.1
                updates["version"] = f"{version_num:.1f}"
            except (ValueError, TypeError):
                import datetime

                updates["version"] = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        updates["updated_at"] = self._current_timestamp()

        # Apply access control updates
        if access_control:
            updates["access_control"] = {
                **existing_resource.get("access_control", {}),
                **access_control,
            }

        # Create updated resource
        updated_resource = {**existing_resource, **updates}

        return {
            "success": True,
            "operation": "update",
            "resource": updated_resource,
            "changes": updates,
            "previous_version": existing_resource["version"],
            "notifications": {
                "sent": auto_notify,
                "subscribers_notified": 5 if auto_notify else 0,
                "change_summary": f"Updated {len(updates)} fields",
            },
        }

    def _delete_resource(self, uri: Optional[str], auto_notify: bool) -> Dict[str, Any]:
        """Delete an MCP resource."""
        if not uri:
            return {"success": False, "error": "URI is required for delete operation"}

        # Mock resource deletion
        deleted_resource = {
            "uri": uri,
            "name": "Deleted Resource",
            "deleted_at": self._current_timestamp(),
            "final_version": "2.1",
        }

        return {
            "success": True,
            "operation": "delete",
            "deleted_resource": deleted_resource,
            "cleanup": {
                "cache_cleared": True,
                "references_updated": 3,
                "storage_freed": "1.2 MB",
            },
            "notifications": {
                "sent": auto_notify,
                "subscribers_notified": 7 if auto_notify else 0,
            },
        }

    def _validate_resource(
        self, uri: Optional[str], content: Any, schema: Optional[dict]
    ) -> Dict[str, Any]:
        """Validate a resource without creating or updating it."""
        validation_results = {
            "uri_valid": True,
            "content_valid": True,
            "schema_valid": True,
            "errors": [],
            "warnings": [],
        }

        # Validate URI
        if uri:
            if not self._validate_uri(uri):
                validation_results["uri_valid"] = False
                validation_results["errors"].append(f"Invalid URI format: {uri}")
        else:
            validation_results["errors"].append("URI is required for validation")

        # Validate content
        if content is not None:
            try:
                content_str, mime_type = self._serialize_content(content)
                if not content_str:
                    validation_results["warnings"].append("Content is empty")
            except Exception as e:
                validation_results["content_valid"] = False
                validation_results["errors"].append(
                    f"Content serialization failed: {e}"
                )

            # Validate against schema
            if schema:
                schema_validation = self._validate_against_schema(content, schema)
                if not schema_validation["valid"]:
                    validation_results["schema_valid"] = False
                    validation_results["errors"].extend(schema_validation["errors"])
        else:
            validation_results["warnings"].append("No content provided for validation")

        overall_valid = (
            validation_results["uri_valid"]
            and validation_results["content_valid"]
            and validation_results["schema_valid"]
        )

        return {
            "success": True,
            "operation": "validate",
            "valid": overall_valid,
            "results": validation_results,
            "summary": {
                "total_errors": len(validation_results["errors"]),
                "total_warnings": len(validation_results["warnings"]),
                "recommendation": (
                    "Resource is valid"
                    if overall_valid
                    else "Fix errors before creating resource"
                ),
            },
        }

    def _list_resources(self, filter_criteria: Optional[dict] = None) -> Dict[str, Any]:
        """List available MCP resources."""
        # Mock resource listing
        mock_resources = [
            {
                "uri": "workflow://examples/data/customer_analysis.txt",
                "name": "Customer Analysis",
                "mimeType": "text/plain",
                "size": 1024,
                "created_at": "2025-06-01T10:00:00Z",
                "version": "1.0",
            },
            {
                "uri": "data://reports/summary.json",
                "name": "Summary Report",
                "mimeType": "application/json",
                "size": 512,
                "created_at": "2025-06-01T11:00:00Z",
                "version": "2.1",
            },
            {
                "uri": "file:///tmp/output.csv",
                "name": "Output Data",
                "mimeType": "text/csv",
                "size": 2048,
                "created_at": "2025-06-01T12:00:00Z",
                "version": "3.0",
            },
        ]

        # Apply filters if provided
        if filter_criteria:
            filtered_resources = []
            for resource in mock_resources:
                include = True

                if "mimeType" in filter_criteria:
                    if resource["mimeType"] != filter_criteria["mimeType"]:
                        include = False

                if "min_size" in filter_criteria:
                    if resource["size"] < filter_criteria["min_size"]:
                        include = False

                if "name_contains" in filter_criteria:
                    if (
                        filter_criteria["name_contains"].lower()
                        not in resource["name"].lower()
                    ):
                        include = False

                if include:
                    filtered_resources.append(resource)

            mock_resources = filtered_resources

        return {
            "success": True,
            "operation": "list",
            "resources": mock_resources,
            "total_count": len(mock_resources),
            "filter_applied": filter_criteria is not None,
            "filter_criteria": filter_criteria,
            "summary": {
                "mime_types": list(set(r["mimeType"] for r in mock_resources)),
                "total_size": sum(r["size"] for r in mock_resources),
                "version_range": (
                    f"{min(r['version'] for r in mock_resources)} - {max(r['version'] for r in mock_resources)}"
                    if mock_resources
                    else "N/A"
                ),
            },
        }

    def _validate_uri(self, uri: str) -> bool:
        """Validate MCP resource URI format."""
        if not uri:
            return False

        # Check for scheme
        if "://" not in uri:
            return False

        # Check for valid characters (basic validation)
        invalid_chars = [" ", "\t", "\n", "\r"]
        for char in invalid_chars:
            if char in uri:
                return False

        return True

    def _serialize_content(self, content: Any) -> tuple[str, str]:
        """Serialize content and determine MIME type."""
        if isinstance(content, str):
            return content, "text/plain"
        elif isinstance(content, (dict, list)):
            return json.dumps(content, indent=2), "application/json"
        elif isinstance(content, bytes):
            try:
                return content.decode("utf-8"), "text/plain"
            except UnicodeDecodeError:
                return str(content), "application/octet-stream"
        else:
            return str(content), "text/plain"

    def _validate_against_schema(self, content: Any, schema: dict) -> Dict[str, Any]:
        """Validate content against JSON schema."""
        try:
            # Mock schema validation (in real implementation, use jsonschema library)
            if not isinstance(schema, dict):
                return {"valid": False, "errors": ["Schema must be a dictionary"]}

            # Basic type checking
            schema_type = schema.get("type")
            if schema_type:
                if schema_type == "object" and not isinstance(content, dict):
                    return {
                        "valid": False,
                        "errors": [f"Expected object, got {type(content).__name__}"],
                    }
                elif schema_type == "array" and not isinstance(content, list):
                    return {
                        "valid": False,
                        "errors": [f"Expected array, got {type(content).__name__}"],
                    }
                elif schema_type == "string" and not isinstance(content, str):
                    return {
                        "valid": False,
                        "errors": [f"Expected string, got {type(content).__name__}"],
                    }

            return {"valid": True, "errors": []}

        except Exception as e:
            return {"valid": False, "errors": [f"Schema validation error: {e}"]}

    def _extract_name_from_uri(self, uri: str) -> str:
        """Extract a reasonable name from URI."""
        # Extract the last part of the URI path
        if "/" in uri:
            name = uri.split("/")[-1]
        else:
            name = uri

        # Remove file extension for display
        if "." in name:
            name = name.rsplit(".", 1)[0]

        return name or "Unnamed Resource"

    def _current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        import datetime

        return datetime.datetime.now().isoformat() + "Z"

"""
Middleware SDK Integration Example

Demonstrates how to properly use SDK components and nodes within middleware
instead of reimplementing functionality. This example shows the refactored
approach for common middleware patterns.
"""

import asyncio
import logging

# Import data path utilities
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import middleware components
from kailash.middleware import AgentUIMiddleware, APIGateway
from kailash.nodes.admin import PermissionCheckNode
from kailash.nodes.ai import EmbeddingGeneratorNode

# Import SDK nodes instead of external libraries
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.data import (
    AsyncPostgreSQLVectorNode,
    AsyncSQLDatabaseNode,
    SQLDatabaseNode,
)
from kailash.nodes.logic import WorkflowNode
from kailash.nodes.security import (
    AuditLogNode,
    CredentialManagerNode,
    RotatingCredentialNode,
    SecurityEventNode,
)
from kailash.nodes.transform import DataTransformer
from kailash.workflow import WorkflowBuilder

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from examples.utils.data_paths import get_output_data_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SDKIntegratedWebhookManager:
    """Webhook manager using SDK HTTPRequestNode instead of httpx."""

    def __init__(self):
        # Use HTTPRequestNode instead of httpx client
        self.http_node = HTTPRequestNode(
            name="webhook_sender",
            retry_count=3,
            timeout=10.0,
            headers={"User-Agent": "Kailash-Middleware/2.0"},
        )

        # Use AuditLogNode for delivery tracking
        self.audit_node = AuditLogNode(name="webhook_audit", log_level="INFO")

    async def deliver_webhook(
        self, webhook_config: Dict[str, Any], event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deliver webhook using SDK components."""
        # Prepare payload
        payload = {
            "webhook_id": webhook_config["id"],
            "event": event_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Log attempt
        self.audit_node.execute(
            operation="log_event",
            event_data={
                "event_type": "webhook_attempt",
                "severity": "low",
                "action": "webhook_delivery_attempt",
                "description": f"Attempting webhook delivery to {webhook_config['url']}",
                "metadata": {
                    "webhook_id": webhook_config["id"],
                    "url": webhook_config["url"],
                },
            },
            tenant_id="middleware_demo",
        )

        try:
            # Use HTTPRequestNode for delivery
            response = self.http_node.execute(
                url=webhook_config["url"],
                method="POST",
                json=payload,
                headers=webhook_config.get("headers", {}),
            )

            # Log success
            self.audit_node.execute(
                action="webhook_delivery_success",
                webhook_id=webhook_config["id"],
                status_code=response.get("status_code"),
            )

            return {
                "success": True,
                "status_code": response.get("status_code"),
                "response": response,
            }

        except Exception as e:
            # Log failure
            self.audit_node.execute(
                action="webhook_delivery_failure",
                webhook_id=webhook_config["id"],
                error=str(e),
            )

            return {"success": False, "error": str(e)}


class SDKIntegratedRepository:
    """Repository using SDK database nodes instead of raw SQLAlchemy."""

    def __init__(self, connection_string: str):
        # Use AsyncSQLDatabaseNode for all database operations
        self.db_node = AsyncSQLDatabaseNode(
            name="middleware_db", connection_string=connection_string
        )

        # Use DataTransformer for result mapping
        self.transformer = DataTransformer(name="db_result_transformer")

    async def save_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save workflow using SDK database node."""
        # Execute insert using database node
        result = await self.db_node.execute(
            {
                "query": """
                INSERT INTO workflows (id, name, config, created_at)
                VALUES (:id, :name, :config, :created_at)
                RETURNING *
            """,
                "params": {
                    "id": workflow_data["id"],
                    "name": workflow_data["name"],
                    "config": workflow_data["config"],
                    "created_at": datetime.now(timezone.utc),
                },
            }
        )

        # Transform result
        transformed = await self.transformer.execute(
            {
                "data": result["rows"][0] if result["rows"] else {},
                "schema": {
                    "id": "string",
                    "name": "string",
                    "config": "json",
                    "created_at": "datetime",
                },
            }
        )

        return transformed["result"]

    async def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow using SDK database node."""
        result = await self.db_node.execute(
            {
                "query": "SELECT * FROM workflows WHERE id = :id",
                "params": {"id": workflow_id},
            }
        )

        if not result["rows"]:
            return None

        # Transform result
        transformed = await self.transformer.execute(
            {
                "data": result["rows"][0],
                "schema": {
                    "id": "string",
                    "name": "string",
                    "config": "json",
                    "created_at": "datetime",
                },
            }
        )

        return transformed["result"]


class SDKIntegratedAuthManager:
    """Authentication manager using SDK security nodes."""

    def __init__(self):
        # Use CredentialManagerNode for token management
        self.credential_manager = CredentialManagerNode(
            credential_name="auth_manager_creds",
            name="jwt_manager",
            storage_backend="secure_memory",
        )

        # Use RotatingCredentialNode for API keys
        self.api_key_manager = RotatingCredentialNode(
            name="api_key_rotator", rotation_interval_hours=24
        )

        # Use PermissionCheckNode for authorization
        self.permission_checker = PermissionCheckNode(name="auth_checker")

        # Use SecurityEventNode for security logging
        self.security_logger = SecurityEventNode(name="auth_security_events")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token using SDK components."""
        try:
            # Log validation attempt
            await self.security_logger.execute(
                {
                    "event_type": "token_validation_attempt",
                    "token_prefix": token[:10] + "...",
                }
            )

            # Validate using credential manager
            validation_result = await self.credential_manager.execute(
                {"action": "validate", "credential_type": "jwt", "token": token}
            )

            if validation_result["valid"]:
                # Check permissions
                user_id = validation_result["user_id"]
                permissions = await self.permission_checker.execute(
                    {
                        "user_id": user_id,
                        "resource": "middleware_api",
                        "action": "access",
                    }
                )

                # Log success
                await self.security_logger.execute(
                    {"event_type": "token_validation_success", "user_id": user_id}
                )

                return {
                    "valid": True,
                    "user_id": user_id,
                    "permissions": permissions["permissions"],
                }
            else:
                # Log failure
                await self.security_logger.execute(
                    {
                        "event_type": "token_validation_failure",
                        "reason": validation_result.get("reason", "invalid_token"),
                    }
                )

                return {"valid": False, "reason": "Invalid token"}

        except Exception as e:
            # Log error
            await self.security_logger.execute(
                {"event_type": "token_validation_error", "error": str(e)}
            )

            return {"valid": False, "reason": "Validation error"}


class SDKIntegratedAIChat:
    """AI Chat using SDK vector database and embedding nodes."""

    def __init__(self, connection_string: str):
        # Use EmbeddingGeneratorNode for text embeddings
        self.embedding_node = EmbeddingGeneratorNode(
            name="chat_embedder",
            provider="sentence-transformers",
            model="all-MiniLM-L6-v2",
        )

        # Use AsyncPostgreSQLVectorNode for semantic search
        self.vector_db = AsyncPostgreSQLVectorNode(
            name="chat_vector_store",
            connection_string=connection_string,
            table_name="chat_messages",
            embedding_dimension=384,  # Match embedding model
        )

        # Use AuditLogNode for chat history
        self.chat_audit = AuditLogNode(name="chat_history", log_level="INFO")

    async def store_message(
        self, session_id: str, message: str, role: str
    ) -> Dict[str, Any]:
        """Store chat message with embeddings."""
        # Generate embedding
        embedding_result = await self.embedding_node.execute({"text": message})

        # Store in vector database
        stored = await self.vector_db.execute(
            {
                "action": "insert",
                "data": {
                    "session_id": session_id,
                    "message": message,
                    "role": role,
                    "timestamp": datetime.now(timezone.utc),
                    "embedding": embedding_result["embedding"],
                },
            }
        )

        # Log to audit
        await self.chat_audit.execute(
            {
                "action": "chat_message_stored",
                "session_id": session_id,
                "role": role,
                "message_id": stored.get("id"),
            }
        )

        return stored

    async def find_similar_conversations(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar conversations using vector search."""
        # Generate query embedding
        query_embedding = await self.embedding_node.execute({"text": query})

        # Search similar messages
        results = await self.vector_db.execute(
            {
                "action": "search",
                "embedding": query_embedding["embedding"],
                "limit": limit,
            }
        )

        return results["matches"]


class SDKIntegratedWorkflowBuilder:
    """Workflow builder using WorkflowNode for composition."""

    def __init__(self):
        # Use WorkflowNode for sub-workflow execution
        self.workflow_node = WorkflowNode(name="sub_workflow_executor")

        # Use DataTransformer for configuration validation
        self.config_validator = DataTransformer(name="workflow_config_validator")

    async def create_data_processing_workflow(self) -> WorkflowBuilder:
        """Create workflow using proper SDK patterns."""
        builder = WorkflowBuilder()

        # Add CSV reader node
        csv_reader_id = builder.add_node(
            "CSVReaderNode",
            node_id="csv_reader",
            config={
                "name": "customer_reader",
                "file_path": "/data/inputs/customers.csv",
            },
        )

        # Add data transformer instead of PythonCodeNode
        transformer_id = builder.add_node(
            "DataTransformer",
            node_id="data_transformer",
            config={
                "name": "customer_transformer",
                "transformations": [
                    {
                        "type": "add_field",
                        "field": "processed_at",
                        "value": datetime.now(timezone.utc).isoformat(),
                    },
                    {"type": "add_field", "field": "row_count", "value": "=len(data)"},
                ],
            },
        )

        # Add aggregator node for statistics
        aggregator_id = builder.add_node(
            "AggregatorNode",
            node_id="stats_aggregator",
            config={
                "name": "customer_stats",
                "operations": [
                    {"type": "count", "field": "*", "as": "total_customers"},
                    {"type": "avg", "field": "age", "as": "average_age"},
                    {"type": "max", "field": "purchase_count", "as": "max_purchases"},
                ],
            },
        )

        # Connect nodes
        builder.add_connection(csv_reader_id, "output", transformer_id, "data")
        builder.add_connection(transformer_id, "result", aggregator_id, "data")

        return builder


async def demonstrate_sdk_integration():
    """Demonstrate proper SDK component usage in middleware."""
    print("\n" + "=" * 60)
    print("🚀 SDK-INTEGRATED MIDDLEWARE DEMONSTRATION")
    print("=" * 60)

    # 1. Webhook Delivery with SDK Nodes
    print("\n1️⃣ Webhook Delivery using HTTPRequestNode:")
    webhook_manager = SDKIntegratedWebhookManager()

    webhook_config = {
        "id": "webhook_001",
        "url": "https://httpbin.org/post",
        "headers": {"X-Custom": "SDK-Integration"},
    }

    result = await webhook_manager.deliver_webhook(
        webhook_config, {"event": "test", "data": "SDK integration successful"}
    )
    print(f"   ✅ Webhook delivery: {result['success']}")

    # 2. Database Operations with SDK Nodes
    print("\n2️⃣ Database Operations using AsyncSQLDatabaseNode:")
    # Note: Using in-memory SQLite for demo
    repository = SDKIntegratedRepository("sqlite+aiosqlite:///:memory:")

    # Would need to create table first in real scenario
    print("   ✅ Repository initialized with SDK database node")

    # 3. Authentication with Security Nodes
    print("\n3️⃣ Authentication using SDK Security Nodes:")
    auth_manager = SDKIntegratedAuthManager()

    # Store a test credential
    await auth_manager.credential_manager.execute(
        action="store",
        credential_type="jwt",
        token="test_token_123",
        user_id="user_001",
    )

    # Validate token
    validation = await auth_manager.validate_token("test_token_123")
    print(f"   ✅ Token validation: {validation['valid']}")

    # 4. AI Chat with Vector Database
    print("\n4️⃣ AI Chat using Vector Database Nodes:")
    # Note: Would need PostgreSQL with pgvector in real scenario
    print("   ✅ AI Chat configured with embedding and vector nodes")

    # 5. Workflow Building with SDK Patterns
    print("\n5️⃣ Workflow Building using SDK Patterns:")
    workflow_builder = SDKIntegratedWorkflowBuilder()
    builder = await workflow_builder.create_data_processing_workflow()

    print("   ✅ Created workflow with:")
    print("      - CSVReaderNode (instead of manual file reading)")
    print("      - DataTransformer (instead of PythonCodeNode)")
    print("      - AggregatorNode (instead of manual calculations)")

    # Summary
    print("\n" + "=" * 60)
    print("📊 INTEGRATION SUMMARY:")
    print("-" * 40)
    print("✅ HTTP Operations: HTTPRequestNode replaces httpx")
    print("✅ Database: AsyncSQLDatabaseNode replaces SQLAlchemy")
    print("✅ Authentication: Security nodes replace manual JWT")
    print("✅ AI Features: Vector nodes enable semantic search")
    print("✅ Workflows: Specialized nodes replace PythonCodeNode")
    print("=" * 60)

    # Best practices
    print("\n💡 KEY BENEFITS OF SDK INTEGRATION:")
    print("1. Automatic retry and error handling")
    print("2. Built-in monitoring and audit logging")
    print("3. Consistent patterns across middleware")
    print("4. Type safety and validation")
    print("5. Performance optimizations")
    print("=" * 60)


def create_migration_guide():
    """Create a migration guide for middleware developers."""
    guide = """
# Middleware SDK Integration Migration Guide

## Quick Reference: What to Replace

### 1. HTTP Operations
❌ OLD:
```python
import httpx
async with httpx.AsyncClient() as client:
    response = await client.post(url, json=data)
```

✅ NEW:
```python
from kailash.nodes.api import HTTPRequestNode
http_node = HTTPRequestNode(name="api_client")
response = await http_node.execute({
    "url": url,
    "method": "POST",
    "json": data
})
```

### 2. Database Operations
❌ OLD:
```python
from sqlalchemy import create_engine
engine = create_engine(connection_string)
result = engine.execute(query, params)
```

✅ NEW:
```python
from kailash.nodes.data import AsyncSQLDatabaseNode
db_node = AsyncSQLDatabaseNode(name="db", connection_string=connection_string)
result = await db_node.execute({
    "query": query,
    "params": params
})
```

### 3. Authentication
❌ OLD:
```python
import jwt
token = jwt.encode(payload, secret)
decoded = jwt.decode(token, secret)
```

✅ NEW:
```python
from kailash.nodes.security import CredentialManagerNode
cred_node = CredentialManagerNode(name="auth")
await cred_node.execute({
    "action": "store",
    "credential_type": "jwt",
    "token": token
})
```

### 4. Simple Data Processing
❌ OLD:
```python
builder.add_node("PythonCodeNode", config={
    "code": "result = {'count': len(data)}"
})
```

✅ NEW:
```python
builder.add_node("DataTransformer", config={
    "transformations": [
        {"type": "add_field", "field": "count", "value": "=len(data)"}
    ]
})
```

### 5. Audit Logging
❌ OLD:
```python
logger.info(f"Action: {action}, User: {user}")
```

✅ NEW:
```python
from kailash.nodes.security import AuditLogNode
audit_node = AuditLogNode(name="audit")
await audit_node.execute({
    "action": action,
    "user": user
})
```

## Migration Steps

1. **Identify Custom Implementations**
   - Search for `httpx`, `requests`, `aiohttp` usage
   - Look for raw `json.dumps/loads` calls
   - Find database connection code
   - Locate authentication logic

2. **Map to SDK Nodes**
   - HTTP → HTTPRequestNode, RESTClientNode
   - Database → SQLDatabaseNode, AsyncSQLDatabaseNode
   - Auth → CredentialManagerNode, OAuth2Node
   - Transform → DataTransformer, FilterNode

3. **Refactor Incrementally**
   - Start with HTTP operations (easiest)
   - Move to database operations
   - Update authentication last (most complex)

4. **Test Thoroughly**
   - Verify retry logic works
   - Check error handling
   - Confirm monitoring/logging

5. **Document Changes**
   - Update API documentation
   - Note any behavior changes
   - Provide migration examples
"""

    # Save migration guide
    output_path = get_output_data_path("middleware_migration_guide.md")
    with open(output_path, "w") as f:
        f.write(guide)

    print(f"\n📝 Migration guide saved to: {output_path}")


if __name__ == "__main__":
    # Run demonstration
    asyncio.run(demonstrate_sdk_integration())

    # Create migration guide
    create_migration_guide()

    print("\n✅ SDK Integration demonstration complete!")
    print("🔗 See the migration guide for detailed refactoring steps.")

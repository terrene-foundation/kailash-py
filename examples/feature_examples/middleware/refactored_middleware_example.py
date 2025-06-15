"""
Refactored Middleware Example

Demonstrates the middleware layer after refactoring to use SDK components:
- HTTPRequestNode for webhook delivery instead of httpx
- SDK security nodes for authentication instead of manual JWT
- Database repositories using SDK database nodes
- Vector database for AI chat history
- Audit logging with SDK nodes instead of Python logging
- Data transformation with SDK nodes instead of manual JSON handling

This example shows how the refactoring improves consistency and leverages
SDK features throughout the middleware layer.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

# Import refactored middleware components
from kailash.middleware import (
    AgentUIMiddleware,
    AIChatMiddleware,
    RealtimeMiddleware,
    create_gateway,
)
from kailash.middleware.auth import MiddlewareAuthManager
from kailash.middleware.database.repositories import (
    MiddlewareExecutionRepository,
    MiddlewareUserRepository,
    MiddlewareWorkflowRepository,
)
from kailash.workflow.builder import WorkflowBuilder

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RefactoredMiddlewareDemo:
    """Demonstration of refactored middleware using SDK components."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///middleware_demo.db"):
        self.database_url = database_url
        self.gateway = None
        self.auth_manager = None
        self.repositories = {}

    async def setup_infrastructure(self):
        """Set up the refactored middleware infrastructure."""
        logger.info("🚀 Setting up refactored middleware with SDK components...")

        # 1. Initialize repositories using SDK database nodes
        logger.info("📊 Initializing database repositories with SDK nodes...")
        self.repositories = {
            "workflows": MiddlewareWorkflowRepository(self.database_url),
            "executions": MiddlewareExecutionRepository(self.database_url),
            "users": MiddlewareUserRepository(self.database_url),
        }

        # 2. Initialize auth manager using SDK security nodes
        logger.info("🔐 Setting up authentication with SDK security nodes...")
        self.auth_manager = MiddlewareAuthManager(
            token_expiry_hours=24,
            enable_api_keys=True,
            enable_audit=True,
            database_url=self.database_url,
        )

        # 3. Create gateway with all SDK integrations using convenience function
        logger.info("🌐 Creating API gateway with SDK components...")
        self.gateway = create_gateway(
            title="Refactored Kailash Gateway",
            description="Middleware using SDK components throughout",
            version="2.0.0",
            cors_origins=["http://localhost:3000"],
            enable_docs=True,
            enable_auth=True,
            database_url=self.database_url,
        )

        # 4. Initialize AI chat with vector database
        logger.info("🤖 Setting up AI chat with vector database...")
        # Note: In production, use PostgreSQL with pgvector
        self.ai_chat = AIChatMiddleware(
            self.gateway.agent_ui,
            vector_db_url=None,  # Would be PostgreSQL URL in production
            enable_semantic_search=False,  # Disabled for demo
        )

        logger.info("✅ Infrastructure setup complete!")

    async def demonstrate_auth_flow(self):
        """Demonstrate authentication using SDK security nodes."""
        print("\n" + "=" * 60)
        print("🔐 AUTHENTICATION DEMONSTRATION")
        print("=" * 60)

        # Create a test user
        user_data = {
            "username": "demo_user",
            "email": "demo@example.com",
            "full_name": "Demo User",
        }

        try:
            user = await self.repositories["users"].create(user_data)
            print(f"✅ Created user: {user['username']}")

            # Generate JWT token using SDK nodes
            token = await self.auth_manager.create_token(
                user_id=user["id"],
                permissions=["read", "write", "execute"],
                metadata={"role": "developer"},
            )
            print(f"✅ Generated JWT token (first 20 chars): {token[:20]}...")

            # Validate token
            token_data = await self.auth_manager.validate_token(token)
            print(f"✅ Token validated for user: {token_data['user_id']}")

            # Create API key using rotating credentials
            api_key_result = await self.auth_manager.create_api_key(
                user_id=user["id"],
                key_name="demo_api_key",
                permissions=["api.read", "api.write"],
            )
            print(f"✅ Created API key: {api_key_result['key_id']}")

        except Exception as e:
            logger.error(f"Auth demonstration failed: {e}")

    async def demonstrate_workflow_persistence(self):
        """Demonstrate workflow persistence using SDK database nodes."""
        print("\n" + "=" * 60)
        print("💾 WORKFLOW PERSISTENCE DEMONSTRATION")
        print("=" * 60)

        # Create a workflow
        workflow_data = {
            "name": "Data Processing Pipeline",
            "description": "Refactored workflow using SDK nodes",
            "config": {
                "nodes": [
                    {
                        "id": "csv_reader",
                        "type": "CSVReaderNode",
                        "config": {"file_path": "/data/inputs/customers.csv"},
                    },
                    {
                        "id": "transformer",
                        "type": "DataTransformer",
                        "config": {
                            "transformations": [
                                {"type": "filter", "condition": "age > 18"},
                                {
                                    "type": "add_field",
                                    "field": "processed_at",
                                    "value": "now()",
                                },
                            ]
                        },
                    },
                ],
                "connections": [
                    {
                        "from": "csv_reader",
                        "from_output": "output",
                        "to": "transformer",
                        "to_input": "data",
                    }
                ],
            },
            "created_by": "demo_user",
        }

        try:
            # Save workflow using repository (which uses SDK database nodes)
            workflow = await self.repositories["workflows"].create(workflow_data)
            print(f"✅ Saved workflow: {workflow['id']}")

            # Retrieve workflow
            retrieved = await self.repositories["workflows"].get(workflow["id"])
            print(f"✅ Retrieved workflow: {retrieved['name']}")

            # List workflows
            workflows = await self.repositories["workflows"].list(limit=10)
            print(f"✅ Found {len(workflows)} workflows in database")

        except Exception as e:
            logger.error(f"Persistence demonstration failed: {e}")

    async def demonstrate_webhook_delivery(self):
        """Demonstrate webhook delivery using HTTPRequestNode."""
        print("\n" + "=" * 60)
        print("🔗 WEBHOOK DELIVERY DEMONSTRATION")
        print("=" * 60)

        # The RealtimeMiddleware now uses HTTPRequestNode internally
        realtime = self.gateway.realtime

        # Register a webhook (will use HTTPRequestNode for delivery)
        webhook_id = "demo_webhook"

        try:
            realtime.register_webhook(
                webhook_id=webhook_id,
                url="https://httpbin.org/post",
                event_types=["workflow.completed"],
                headers={"X-Custom": "SDK-Refactored"},
            )
            print("✅ Registered webhook using SDK components")

            # The webhook manager now uses:
            # - HTTPRequestNode for HTTP delivery (with retry logic)
            # - AuditLogNode for delivery tracking
            # - SecurityEventNode for failure logging

            print("✅ Webhook will be delivered using HTTPRequestNode with:")
            print("   - Automatic retry logic")
            print("   - Connection pooling")
            print("   - Monitoring integration")
            print("   - Audit logging")

        except Exception as e:
            logger.error(f"Webhook demonstration failed: {e}")

    async def demonstrate_data_transformation(self):
        """Demonstrate data transformation using SDK nodes."""
        print("\n" + "=" * 60)
        print("🔄 DATA TRANSFORMATION DEMONSTRATION")
        print("=" * 60)

        # The gateway now uses DataTransformer nodes internally
        # for all JSON operations instead of manual json.dumps/loads

        # Create a session to see transformation in action
        session_id = await self.gateway.agent_ui.create_session(
            user_id="demo_user", metadata={"source": "refactored_demo"}
        )

        print(f"✅ Created session: {session_id}")
        print("   - Session data transformed using DataTransformer node")
        print("   - Automatic timestamp addition")
        print("   - Schema validation")
        print("   - Type safety")

        # The API responses are now transformed using SDK nodes
        # providing consistent formatting and validation

    async def demonstrate_complete_flow(self):
        """Demonstrate a complete flow using all refactored components."""
        print("\n" + "=" * 60)
        print("🎯 COMPLETE REFACTORED FLOW DEMONSTRATION")
        print("=" * 60)

        try:
            # 1. Authenticate user
            user = await self.repositories["users"].get_by_username("demo_user")
            if not user:
                user = await self.repositories["users"].create(
                    {"username": "demo_user", "email": "demo@example.com"}
                )

            token = await self.auth_manager.create_token(user["id"])
            print(f"✅ Authenticated user: {user['username']}")

            # 2. Create session with persistence
            session_id = await self.gateway.agent_ui.create_session(
                user_id=user["id"], metadata={"demo": True}
            )
            print(f"✅ Created persistent session: {session_id}")

            # 3. Create workflow using SDK patterns
            builder = WorkflowBuilder()

            # Using DataTransformer instead of PythonCodeNode
            reader_id = builder.add_node(
                "CSVReaderNode",
                node_id="reader",
                config={"name": "reader", "file_path": "/data/inputs/test.csv"},
            )

            transformer_id = builder.add_node(
                "DataTransformer",
                node_id="transformer",
                config={
                    "name": "transformer",
                    "transformations": [
                        {"type": "add_field", "field": "timestamp", "value": "now()"},
                        {
                            "type": "add_field",
                            "field": "session_id",
                            "value": session_id,
                        },
                    ],
                },
            )

            builder.add_connection(reader_id, "output", transformer_id, "data")

            # Register workflow
            workflow_id = "refactored_demo_workflow"
            await self.gateway.agent_ui.register_workflow(
                workflow_id, builder, session_id
            )
            print(f"✅ Registered workflow: {workflow_id}")

            # 4. Execute with full SDK integration
            execution_id = await self.gateway.agent_ui.execute_workflow(
                session_id=session_id, workflow_id=workflow_id, inputs={"test": True}
            )
            print(f"✅ Started execution: {execution_id}")

            # The execution now:
            # - Persists to database using SDK nodes
            # - Logs with AuditLogNode
            # - Tracks security events with SecurityEventNode
            # - Transforms data with DataTransformer
            # - Delivers webhooks with HTTPRequestNode

            await asyncio.sleep(2)  # Wait for execution

            # 5. Check execution status from database
            if self.gateway.agent_ui.enable_persistence:
                execution = await self.repositories["executions"].get(execution_id)
                if execution:
                    print(f"✅ Execution persisted with status: {execution['status']}")

        except Exception as e:
            logger.error(f"Complete flow failed: {e}")

    async def show_benefits_summary(self):
        """Show the benefits of the refactoring."""
        print("\n" + "=" * 60)
        print("💡 REFACTORING BENEFITS SUMMARY")
        print("=" * 60)

        benefits = {
            "HTTPRequestNode vs httpx": [
                "✅ Automatic retry with exponential backoff",
                "✅ Connection pooling and reuse",
                "✅ Built-in timeout handling",
                "✅ Integrated monitoring and metrics",
            ],
            "SDK Security Nodes vs Manual JWT": [
                "✅ Secure credential storage",
                "✅ Automatic token rotation",
                "✅ Comprehensive audit logging",
                "✅ Security event tracking",
            ],
            "SDK Database Nodes vs Raw SQL": [
                "✅ Connection pooling",
                "✅ Automatic retry on failures",
                "✅ Query parameter sanitization",
                "✅ Result transformation",
            ],
            "Vector Database for AI Chat": [
                "✅ Semantic search capabilities",
                "✅ Conversation similarity matching",
                "✅ Scalable chat history storage",
                "✅ Context-aware responses",
            ],
            "DataTransformer vs json.dumps": [
                "✅ Schema validation",
                "✅ Type safety",
                "✅ Consistent formatting",
                "✅ Automatic field addition",
            ],
        }

        for category, items in benefits.items():
            print(f"\n{category}:")
            for item in items:
                print(f"  {item}")

        print("\n" + "=" * 60)

    async def run_complete_demo(self):
        """Run the complete refactored middleware demonstration."""
        print("\n" + "=" * 60)
        print("🌟 REFACTORED MIDDLEWARE DEMONSTRATION")
        print("=" * 60)
        print("Showing how SDK components improve the middleware layer")
        print("=" * 60)

        try:
            # Setup
            await self.setup_infrastructure()

            # Run demonstrations
            await self.demonstrate_auth_flow()
            await self.demonstrate_workflow_persistence()
            await self.demonstrate_webhook_delivery()
            await self.demonstrate_data_transformation()
            await self.demonstrate_complete_flow()
            await self.show_benefits_summary()

            print("\n✅ Refactored middleware demonstration complete!")
            print(
                "🎉 All components now use SDK nodes for better reliability and features"
            )

        except Exception as e:
            logger.error(f"Demo failed: {e}")
            raise


async def compare_before_and_after():
    """Show before and after comparison of middleware code."""
    print("\n" + "=" * 60)
    print("📊 BEFORE AND AFTER COMPARISON")
    print("=" * 60)

    comparisons = [
        {
            "feature": "Webhook Delivery",
            "before": """
# Before: Using httpx directly
async with httpx.AsyncClient() as client:
    response = await client.post(url, json=payload, timeout=10)
    if response.status_code >= 400:
        # Manual retry logic needed
        for attempt in range(3):
            # Complex retry implementation
""",
            "after": """
# After: Using HTTPRequestNode
response = await self.http_node.execute({
    "url": url,
    "method": "POST",
    "json": payload
})
# Automatic retry, pooling, monitoring included!
""",
        },
        {
            "feature": "Authentication",
            "before": """
# Before: Manual JWT handling
import jwt
token = jwt.encode(payload, secret, algorithm="HS256")
try:
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
except jwt.ExpiredTokenError:
    # Manual error handling
""",
            "after": """
# After: Using SDK security nodes
token = await self.credential_manager.execute({
    "action": "create",
    "payload": payload
})
# Automatic expiry, rotation, audit logging!
""",
        },
        {
            "feature": "Database Operations",
            "before": """
# Before: Raw SQL with manual connection
conn = await asyncpg.connect(database_url)
try:
    result = await conn.fetch("SELECT * FROM workflows WHERE id = $1", id)
finally:
    await conn.close()
""",
            "after": """
# After: Using SDK database nodes
result = await self.db_node.execute({
    "query": "SELECT * FROM workflows WHERE id = :id",
    "params": {"id": id}
})
# Connection pooling, retry, monitoring included!
""",
        },
    ]

    for comp in comparisons:
        print(f"\n### {comp['feature']} ###")
        print("\n❌ BEFORE (Manual Implementation):")
        print(comp["before"])
        print("\n✅ AFTER (Using SDK Nodes):")
        print(comp["after"])

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Show comparison first
    asyncio.run(compare_before_and_after())

    # Run the demonstration
    demo = RefactoredMiddlewareDemo()
    asyncio.run(demo.run_complete_demo())

    print("\n🚀 The middleware has been successfully refactored to use SDK components!")
    print("📚 This improves reliability, reduces code complexity, and adds features.")

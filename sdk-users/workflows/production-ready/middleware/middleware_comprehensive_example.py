"""
Comprehensive Kailash Middleware Example

Demonstrates the complete middleware layer capabilities including:
- Agent-UI communication
- Real-time event streaming
- Dynamic workflow creation
- AI chat integration
- Schema generation
- Multi-transport support

This example shows how to set up a complete middleware server that
supports frontend applications with full real-time capabilities.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

# Import middleware components
from kailash.middleware import (
    AgentUIMiddleware,
    AIChatMiddleware,
    APIGateway,
    EventStream,
    RealtimeMiddleware,
    create_gateway,
)

# Import Kailash core components
from kailash.workflow.builder import WorkflowBuilder

# No longer needed - using WorkflowBuilder.add_node() with string types


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MiddlewareDemo:
    """Demonstration of Kailash Middleware capabilities."""

    def __init__(self):
        self.gateway = None
        self.agent_ui = None
        self.realtime = None
        self.ai_chat = None

    async def setup_middleware(self):
        """Set up the complete middleware stack."""
        logger.info("🚀 Setting up Kailash Middleware...")

        # Create gateway with enhanced configuration
        self.gateway = create_gateway(
            title="Kailash Middleware Demo",
            description="Complete middleware demonstration with all features",
            version="1.0.0",
            cors_origins=["http://localhost:3000", "http://localhost:8080"],
            enable_docs=True,
            max_sessions=100,
        )

        # Get middleware components
        self.agent_ui = self.gateway.agent_ui
        self.realtime = self.gateway.realtime

        # Initialize AI chat
        self.ai_chat = AIChatMiddleware(self.agent_ui)

        # Add AI chat routes to gateway
        self._add_chat_routes()

        logger.info("✅ Middleware setup complete")

    def _add_chat_routes(self):
        """Add AI chat routes to the gateway."""

        @self.gateway.app.post("/api/chat/sessions")
        async def start_chat_session(session_id: str, user_id: str = None):
            """Start a new AI chat session."""
            chat_session_id = await self.ai_chat.start_chat_session(session_id, user_id)
            return {"chat_session_id": chat_session_id}

        @self.gateway.app.post("/api/chat/message")
        async def send_chat_message(
            session_id: str, message: str, context: Dict[str, Any] = None
        ):
            """Send message to AI chat."""
            response = await self.ai_chat.send_message(session_id, message, context)
            return response

        @self.gateway.app.get("/api/chat/history/{session_id}")
        async def get_chat_history(session_id: str, limit: int = 50):
            """Get chat history for a session."""
            history = self.ai_chat.get_chat_history(session_id, limit)
            return {"history": history}

    async def create_sample_workflows(self):
        """Create sample workflows to demonstrate capabilities."""
        logger.info("📊 Creating sample workflows...")

        # 1. Data Processing Workflow
        data_workflow = self._create_data_processing_workflow()
        await self.agent_ui.register_workflow(
            "data_processing", data_workflow, make_shared=True
        )

        # 2. AI Analysis Workflow
        ai_workflow = self._create_ai_analysis_workflow()
        await self.agent_ui.register_workflow(
            "ai_analysis", ai_workflow, make_shared=True
        )

        # 3. Dynamic Workflow via Chat
        await self._create_workflow_via_chat()

        logger.info("✅ Sample workflows created")

    def _create_data_processing_workflow(self) -> WorkflowBuilder:
        """Create a data processing workflow."""
        builder = WorkflowBuilder()

        # CSV Reader
        reader_id = builder.add_node(
            "CSVReaderNode",
            node_id="csv_reader",
            config={"name": "csv_reader", "file_path": "/data/inputs/customers.csv"},
        )

        # Data processor
        processor_id = builder.add_node(
            "PythonCodeNode",
            node_id="data_processor",
            config={
                "name": "data_processor",
                "code": """
# Process incoming data
result = {
    "total_rows": len(input_data) if isinstance(input_data, list) else 1,
    "processed_at": datetime.now().isoformat(),
    "summary": "Data processed successfully"
}
""",
            },
        )

        # Connect nodes
        builder.add_connection(reader_id, "output", processor_id, "input")

        return builder

    def _create_ai_analysis_workflow(self) -> WorkflowBuilder:
        """Create an AI analysis workflow."""
        builder = WorkflowBuilder()

        # Data input
        data_input_id = builder.add_node(
            "PythonCodeNode",
            node_id="data_input",
            config={
                "name": "data_input",
                "code": """
# Prepare data for analysis
data = input_data.get('text', 'Sample text for analysis')
result = {'text': data, 'ready_for_analysis': True}
""",
            },
        )

        # AI Analyzer (if LLM is available)
        try:
            ai_analyzer_id = builder.add_node(
                "LLMAgentNode",
                node_id="ai_analyzer",
                config={
                    "name": "ai_analyzer",
                    "provider": "ollama",
                    "model": "llama3.2:3b",
                    "temperature": 0.3,
                },
            )
            builder.add_connection(data_input_id, "result", ai_analyzer_id, "messages")
        except Exception as e:
            logger.warning(f"LLM not available, using fallback: {e}")

            # Fallback analyzer
            fallback_id = builder.add_node(
                "PythonCodeNode",
                node_id="fallback_analyzer",
                config={
                    "name": "fallback_analyzer",
                    "code": """
# Fallback analysis when LLM is not available
text = input_data.get('text', '')
result = {
    'analysis': f'Analyzed text with {len(text)} characters',
    'sentiment': 'neutral',
    'key_topics': ['general'],
    'confidence': 0.8,
    'method': 'fallback_analysis'
}
""",
                },
            )
            builder.add_connection(data_input_id, "result", fallback_id, "input_data")

        return builder

    async def _create_workflow_via_chat(self):
        """Demonstrate creating workflow via AI chat."""
        try:
            # Start chat session
            session_id = await self.agent_ui.create_session(user_id="demo_user")
            await self.ai_chat.start_chat_session(session_id)

            # Ask AI to create a workflow
            chat_response = await self.ai_chat.send_message(
                session_id,
                "Create a simple workflow that reads a CSV file and counts the rows",
                context={"available_data": ["/data/inputs/customers.csv"]},
            )

            # If workflow was generated, create it
            if chat_response.get("workflow_config"):
                workflow_config = chat_response["workflow_config"]
                workflow_id = await self.agent_ui.create_dynamic_workflow(
                    session_id=session_id,
                    workflow_config=workflow_config,
                    workflow_id="ai_generated_workflow",
                )
                logger.info(f"✅ AI generated workflow: {workflow_id}")

        except Exception as e:
            logger.warning(f"Could not create workflow via chat: {e}")

    async def demonstrate_real_time_features(self):
        """Demonstrate real-time communication features."""
        logger.info("🔄 Demonstrating real-time features...")

        # Create a session for demo
        session_id = await self.agent_ui.create_session(user_id="realtime_demo")

        # Set up event subscription
        events_received = []

        async def event_handler(event):
            events_received.append(event.to_dict())
            logger.info(f"📢 Event received: {event.type}")

        await self.agent_ui.subscribe_to_events(
            "demo_subscriber", event_handler, session_id=session_id
        )

        # Execute a workflow to generate events
        try:
            execution_id = await self.agent_ui.execute_workflow(
                session_id=session_id,
                workflow_id="data_processing",
                inputs={"file_path": "/data/inputs/customers.csv"},
            )

            # Wait a bit for execution
            await asyncio.sleep(2)

            logger.info(f"✅ Generated {len(events_received)} real-time events")

        except Exception as e:
            logger.warning(f"Workflow execution demo failed: {e}")

    async def demonstrate_schema_generation(self):
        """Demonstrate dynamic schema generation."""
        logger.info("📋 Demonstrating schema generation...")

        # Get available node schemas
        from kailash.nodes.base import NodeRegistry

        available_nodes = NodeRegistry.list_nodes()

        # Generate schemas for a few key nodes
        key_nodes = ["CSVReaderNode", "PythonCodeNode", "LLMAgentNode"]
        schemas_generated = 0

        for node_name in key_nodes:
            if node_name in available_nodes:
                node_class = available_nodes[node_name]
                schema = self.gateway.schema_registry.get_node_schema(node_class)

                logger.info(
                    f"📄 Generated schema for {node_name}: {len(schema.get('parameters', []))} parameters"
                )
                schemas_generated += 1

        logger.info(f"✅ Generated {schemas_generated} node schemas")

    async def demonstrate_webhook_integration(self):
        """Demonstrate webhook integration."""
        logger.info("🔗 Setting up webhook demo...")

        # Register a webhook (points to a test endpoint)
        webhook_id = "demo_webhook"

        try:
            self.realtime.register_webhook(
                webhook_id=webhook_id,
                url="https://httpbin.org/post",  # Test endpoint
                event_types=["workflow.completed", "workflow.failed"],
                headers={"X-Demo": "Kailash-Middleware"},
            )

            logger.info(f"✅ Registered webhook: {webhook_id}")

        except Exception as e:
            logger.warning(f"Webhook registration failed: {e}")

    async def run_comprehensive_demo(self):
        """Run the complete middleware demonstration."""
        print("\n" + "=" * 60)
        print("🌟 KAILASH MIDDLEWARE COMPREHENSIVE DEMO")
        print("=" * 60)

        try:
            # Setup
            await self.setup_middleware()

            # Create sample workflows
            await self.create_sample_workflows()

            # Demonstrate features
            await self.demonstrate_real_time_features()
            await self.demonstrate_schema_generation()
            await self.demonstrate_webhook_integration()

            # Print statistics
            await self._print_statistics()

            print("\n" + "=" * 60)
            print("🎉 DEMO COMPLETE - Middleware ready for frontend integration!")
            print("=" * 60)
            print("📡 API Gateway: http://localhost:8000")
            print("📚 API Docs: http://localhost:8000/docs")
            print("🔌 WebSocket: ws://localhost:8000/ws")
            print("📡 SSE: http://localhost:8000/events")
            print("=" * 60)

            # Note: In a real deployment, you would start the server here
            logger.info("🚀 Middleware server configured and ready!")
            logger.info("📡 Would start server at: http://0.0.0.0:8000")
            logger.info("📚 API docs would be at: http://0.0.0.0:8000/docs")
            logger.info("🔌 WebSocket would be at: ws://0.0.0.0:8000/ws")

        except Exception as e:
            logger.error(f"Demo failed: {e}")
            raise

    async def _print_statistics(self):
        """Print comprehensive statistics."""
        print("\n📊 MIDDLEWARE STATISTICS:")
        print("-" * 40)

        # Agent UI stats
        agent_stats = self.agent_ui.get_stats()
        print(f"Active Sessions: {agent_stats['active_sessions']}")
        print(f"Workflows Executed: {agent_stats['workflows_executed']}")
        print(f"Events Emitted: {agent_stats['events_emitted']}")

        # Real-time stats
        realtime_stats = self.realtime.get_stats()
        print(f"Events Processed: {realtime_stats['events_processed']}")
        print(
            f"Latency Avg: {realtime_stats.get('latency_stats', {}).get('avg_ms', 'N/A')}ms"
        )

        # Schema stats
        schema_stats = self.gateway.schema_registry.get_stats()
        print(f"Schemas Generated: {schema_stats['schemas_generated']}")
        print(f"Cache Hit Rate: {schema_stats['cache_hit_rate']:.2%}")

        # AI Chat stats (if available)
        if hasattr(self, "ai_chat"):
            chat_stats = self.ai_chat.get_stats()
            print(f"Chat Conversations: {chat_stats['conversations_started']}")
            print(f"Workflows Generated by AI: {chat_stats['workflows_generated']}")


def create_simple_middleware_server():
    """Create a simple middleware server for quick testing."""
    print("🚀 Creating simple middleware server...")

    # Create gateway with minimal configuration
    gateway = create_gateway(
        title="Simple Kailash Middleware",
        cors_origins=["*"],  # Allow all origins for testing
        enable_docs=True,
    )

    # Create a basic workflow
    builder = WorkflowBuilder()

    hello_node_id = builder.add_node(
        "PythonCodeNode",
        node_id="hello_world",
        config={
            "name": "hello_world",
            "code": """
# Simple hello world example
message = input_data.get('name', 'World')
result = {'greeting': f'Hello, {message}!', 'timestamp': '${datetime.now(timezone.utc).isoformat()}'}
""",
        },
    )

    # Register the workflow
    asyncio.create_task(
        gateway.agent_ui.register_workflow("hello_world", builder, make_shared=True)
    )

    print("✅ Simple server ready!")
    print("📡 Server: http://localhost:8000")
    print("📚 Docs: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws")

    # Run the server
    gateway.execute(port=8000)


async def test_middleware_components():
    """Test individual middleware components."""
    print("🧪 Testing middleware components...")

    # Test AgentUIMiddleware
    agent_ui = AgentUIMiddleware()
    session_id = await agent_ui.create_session(user_id="test_user")
    print(f"✅ Created session: {session_id}")

    # Test RealtimeMiddleware
    realtime = RealtimeMiddleware(agent_ui)
    print("✅ Real-time middleware initialized")

    # Test AIChatMiddleware
    ai_chat = AIChatMiddleware(agent_ui)
    await ai_chat.start_chat_session(session_id)

    chat_response = await ai_chat.send_message(
        session_id, "Hello! Can you help me create a simple workflow?"
    )
    print(f"✅ AI Chat response: {chat_response['message'][:100]}...")

    # Print stats
    print(f"📊 Agent UI Stats: {agent_ui.get_stats()}")
    print(f"📊 Real-time Stats: {realtime.get_stats()}")
    print(f"📊 AI Chat Stats: {ai_chat.get_stats()}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "simple":
            # Run simple server
            create_simple_middleware_server()
        elif sys.argv[1] == "test":
            # Test components
            asyncio.execute(test_middleware_components())
    else:
        # Run comprehensive demo
        demo = MiddlewareDemo()
        asyncio.execute(demo.run_comprehensive_demo())


"""
Usage Examples:

1. Full Demo:
   python middleware_comprehensive_example.py

2. Simple Server:
   python middleware_comprehensive_example.py simple

3. Component Testing:
   python middleware_comprehensive_example.py test

Frontend Integration Examples:

1. WebSocket Connection:
   const ws = new WebSocket('ws://localhost:8000/ws?session_id=my_session');
   ws.onmessage = (event) => console.log('Event:', JSON.parse(event.data));

2. REST API Usage:
   // Create session
   const session = await fetch('http://localhost:8000/api/sessions', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({user_id: 'frontend_user'})
   });

   // Execute workflow
   const execution = await fetch('http://localhost:8000/api/executions', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({
       workflow_id: 'hello_world',
       inputs: {name: 'Frontend User'}
     })
   });

3. Server-Sent Events:
   const eventSource = new EventSource('http://localhost:8000/events?session_id=my_session');
   eventSource.onmessage = (event) => console.log('SSE Event:', event.data);

4. AI Chat Integration:
   const chatResponse = await fetch('http://localhost:8000/api/chat/message', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({
       session_id: 'my_session',
       message: 'Create a workflow that processes customer data'
     })
   });
"""

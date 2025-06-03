"""Example: Multi-Workflow API Gateway with MCP Integration.

This example demonstrates how to run multiple workflows through a single
API gateway, providing unified access and management.

Features demonstrated:
- Multiple workflow registration
- Unified routing with prefixes
- MCP server integration
- Health monitoring
- WebSocket support
- Workflow orchestration
"""

import asyncio
import logging

from kailash.api.gateway import WorkflowAPIGateway, WorkflowOrchestrator
from kailash.nodes.api import RESTClientNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.logic import ConditionalNode
from kailash.nodes.transform import DataTransformer
from kailash.workflow import Workflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sales_workflow() -> Workflow:
    """Create a sales data processing workflow."""
    workflow = Workflow("sales_pipeline")

    # Read customer data
    reader = CSVReaderNode()
    workflow.add_node("read_customers", reader)

    # Filter high-value customers
    filter_node = ConditionalNode(
        condition=lambda row: float(row.get("total_purchases", 0)) > 1000
    )
    workflow.add_node("filter_high_value", filter_node)

    # Transform data
    transformer = DataTransformer(
        transform_fn=lambda df: df.assign(
            customer_segment="high_value", discount_eligible=True
        )
    )
    workflow.add_node("add_segment", transformer)

    # Write results
    writer = CSVWriterNode()
    workflow.add_node("write_results", writer)

    # Connect nodes
    workflow.add_edge("read_customers", "filter_high_value")
    workflow.add_edge("filter_high_value", "add_segment")
    workflow.add_edge("add_segment", "write_results")

    return workflow


def create_analytics_workflow() -> Workflow:
    """Create an analytics workflow."""
    workflow = Workflow("analytics_pipeline")

    # Read metrics data
    reader = CSVReaderNode()
    workflow.add_node("read_metrics", reader)

    # Aggregate data
    aggregator = DataTransformer(
        transform_fn=lambda df: df.groupby("category")
        .agg({"value": ["sum", "mean", "count"]})
        .reset_index()
    )
    workflow.add_node("aggregate", aggregator)

    # Write summary
    writer = CSVWriterNode()
    workflow.add_node("write_summary", writer)

    # Connect nodes
    workflow.add_edge("read_metrics", "aggregate")
    workflow.add_edge("aggregate", "write_summary")

    return workflow


def create_integration_workflow() -> Workflow:
    """Create an external API integration workflow."""
    workflow = Workflow("integration_pipeline")

    # Call external API
    api_client = RESTClientNode(
        base_url="https://api.example.com",
        default_headers={"Accept": "application/json"},
    )
    workflow.add_node("fetch_data", api_client)

    # Transform response
    transformer = DataTransformer(
        transform_fn=lambda data: {
            "processed": True,
            "item_count": len(data.get("items", [])),
            "timestamp": data.get("timestamp"),
        }
    )
    workflow.add_node("process_response", transformer)

    # Connect nodes
    workflow.add_edge("fetch_data", "process_response")

    return workflow


async def demonstrate_gateway():
    """Demonstrate the multi-workflow gateway."""

    # Create gateway
    gateway = WorkflowAPIGateway(
        title="Enterprise Workflow Gateway",
        description="Unified API for all company workflows",
        version="2.0.0",
        max_workers=20,
        cors_origins=["http://localhost:3000", "https://app.example.com"],
    )

    # Register workflows
    logger.info("Registering workflows...")

    gateway.register_workflow(
        "sales",
        create_sales_workflow(),
        description="Process sales data and identify high-value customers",
        tags=["sales", "customers", "segmentation"],
    )

    gateway.register_workflow(
        "analytics",
        create_analytics_workflow(),
        description="Aggregate and analyze metrics data",
        tags=["analytics", "metrics", "reporting"],
    )

    gateway.register_workflow(
        "integration",
        create_integration_workflow(),
        description="Integrate with external APIs",
        tags=["integration", "api", "external"],
    )

    # Demonstrate workflow orchestration
    orchestrator = WorkflowOrchestrator(gateway)

    # Create a workflow chain
    orchestrator.create_chain(
        "customer_analysis", ["sales", "analytics"]  # First process sales, then analyze
    )

    # Print available endpoints
    print("\n=== Available Endpoints ===")
    print("Gateway Root: http://localhost:8000/")
    print("List Workflows: http://localhost:8000/workflows")
    print("Health Check: http://localhost:8000/health")
    print("WebSocket: ws://localhost:8000/ws")

    print("\n=== Workflow Endpoints ===")
    for name in gateway.workflows:
        print(f"\n{name.upper()} Workflow:")
        print(f"  - Execute: http://localhost:8000/{name}/execute")
        print(f"  - Info: http://localhost:8000/{name}/workflow/info")
        print(f"  - Health: http://localhost:8000/{name}/health")
        print(f"  - Docs: http://localhost:8000/{name}/docs")

    print("\n=== Example API Calls ===")
    print("# Execute sales workflow")
    print("curl -X POST http://localhost:8000/sales/execute \\")
    print("  -H 'Content-Type: application/json' \\")
    print('  -d \'{"file_path": "customers.csv"}\'')

    print("\n# Get analytics workflow info")
    print("curl http://localhost:8000/analytics/workflow/info")

    print("\n# List all workflows")
    print("curl http://localhost:8000/workflows")

    return gateway


def demonstrate_deployment_patterns():
    """Show different deployment patterns."""

    print("\n=== Deployment Patterns ===")

    print("\n1. Single Gateway (Recommended for most cases):")
    print(
        """
    from kailash.api.gateway import WorkflowAPIGateway
    
    gateway = WorkflowAPIGateway()
    gateway.register_workflow("workflow1", workflow1)
    gateway.register_workflow("workflow2", workflow2)
    gateway.run(port=8000)
    """
    )

    print("\n2. With External Services:")
    print(
        """
    # Some workflows run in the gateway
    gateway.register_workflow("light_workflow", light_wf)
    
    # Heavy workflows run separately
    gateway.proxy_workflow(
        "ml_pipeline",
        "http://ml-service:8080",
        health_check="/health"
    )
    """
    )

    print("\n3. With MCP Integration:")
    print(
        """
    from kailash.api.mcp_integration import MCPIntegration
    
    # Add MCP tools to workflows
    mcp = MCPIntegration("company_tools")
    gateway.register_mcp_server("tools", mcp)
    
    # Workflows can now use MCP tools
    workflow.use_mcp_tool("tools", "database_query")
    """
    )

    print("\n4. With Load Balancing:")
    print(
        """
    # Run multiple gateway instances
    # Use nginx/haproxy for load balancing
    
    upstream kailash_gateway {
        server gateway1:8000;
        server gateway2:8000;
        server gateway3:8000;
    }
    """
    )

    print("\n5. Kubernetes Deployment:")
    print(
        """
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: kailash-gateway
    spec:
      replicas: 3
      template:
        spec:
          containers:
          - name: gateway
            image: company/kailash-gateway:latest
            ports:
            - containerPort: 8000
    """
    )


if __name__ == "__main__":
    # Create and demonstrate gateway
    gateway = asyncio.run(demonstrate_gateway())

    # Show deployment patterns
    demonstrate_deployment_patterns()

    print("\n=== Starting Gateway Server ===")
    print("Access the gateway at: http://localhost:8000")
    print("Interactive API docs: http://localhost:8000/docs")
    print("Press Ctrl+C to stop")

    # Run the server
    gateway.run(port=8000, reload=True)

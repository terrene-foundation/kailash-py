"""Complex Multi-Workflow Gateway Example with MCP Integration.

This example demonstrates an advanced gateway setup with:
1. Multiple interconnected workflows
2. MCP server integration for AI-powered tools
3. Workflow orchestration and chaining
4. Real-time monitoring capabilities
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from kailash.api.gateway import WorkflowAPIGateway, WorkflowOrchestrator
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.workflow import Workflow

# Setup paths
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def create_mcp_server() -> MCPIntegration:
    """Create an MCP server with various AI-powered tools."""
    mcp = MCPIntegration(
        "ai_tools",
        "AI-powered tools for data analysis and processing",
        capabilities=["tools", "resources", "context"],
    )

    # Add sentiment analysis tool
    def analyze_sentiment(text: str, **kwargs) -> Dict[str, Any]:
        """Analyze sentiment of text (simulated)."""
        # In real implementation, this would call an AI model
        words = text.lower().split()
        positive_words = ["good", "great", "excellent", "amazing", "love", "best"]
        negative_words = ["bad", "terrible", "awful", "hate", "worst", "poor"]

        pos_count = sum(1 for word in words if word in positive_words)
        neg_count = sum(1 for word in words if word in negative_words)

        if pos_count > neg_count:
            sentiment = "positive"
            score = 0.7 + (pos_count / len(words)) * 0.3
        elif neg_count > pos_count:
            sentiment = "negative"
            score = 0.3 - (neg_count / len(words)) * 0.3
        else:
            sentiment = "neutral"
            score = 0.5

        return {
            "text": text,
            "sentiment": sentiment,
            "score": round(score, 2),
            "confidence": 0.85,
        }

    mcp.add_tool(
        "sentiment_analysis",
        analyze_sentiment,
        "Analyze sentiment of text",
        {"text": {"type": "string", "required": True}},
    )

    # Add data enrichment tool
    def enrich_data(
        data: Dict[str, Any], fields: List[str], **kwargs
    ) -> Dict[str, Any]:
        """Enrich data with additional information (simulated)."""
        enriched = data.copy()

        for field in fields:
            if field == "category":
                # Simulate category assignment
                if "value" in data:
                    value = float(data.get("value", 0))
                    enriched["category"] = (
                        "high" if value > 100 else "medium" if value > 50 else "low"
                    )
            elif field == "risk_score":
                # Simulate risk calculation
                enriched["risk_score"] = round(hash(str(data)) % 100 / 100, 2)
            elif field == "timestamp":
                enriched["timestamp"] = datetime.now().isoformat()

        return enriched

    mcp.add_tool(
        "enrich_data",
        enrich_data,
        "Enrich data with additional fields",
        {
            "data": {"type": "object", "required": True},
            "fields": {"type": "array", "items": {"type": "string"}, "required": True},
        },
    )

    # Add intelligent routing tool
    async def smart_route(data: Any, rules: Dict[str, Any], **kwargs) -> str:
        """Intelligently route data based on rules (simulated)."""
        # In real implementation, this could use ML for routing decisions
        if isinstance(data, dict):
            value = data.get("value", 0)
            priority = data.get("priority", "normal")

            if priority == "urgent" or value > 1000:
                return "express"
            elif value > 100:
                return "standard"
            else:
                return "basic"

        return "default"

    mcp.add_tool(
        "smart_route",
        smart_route,
        "Intelligently route data based on content",
        {
            "data": {"type": "any", "required": True},
            "rules": {"type": "object", "required": False},
        },
    )

    # Add resources
    mcp.add_resource(
        "knowledge_base", "internal://kb/main", "Company knowledge base for context"
    )

    mcp.add_resource(
        "templates", "internal://templates", "Processing templates and patterns"
    )

    return mcp


def create_customer_analysis_workflow(mcp_server_name: str) -> Workflow:
    """Create a customer analysis workflow using MCP tools."""
    workflow = Workflow("customer_analysis")

    # Read customer data
    reader = CSVReaderNode()
    workflow.add_node("read_customers", reader)

    # Enrich with MCP tool
    enrichment_node = MCPToolNode(
        mcp_server=mcp_server_name,
        tool_name="enrich_data",
        parameter_mapping={"customer_data": "data"},
    )
    workflow.add_node("enrich_customer", enrichment_node)

    # Analyze sentiment from customer feedback
    sentiment_node = MCPToolNode(
        mcp_server=mcp_server_name,
        tool_name="sentiment_analysis",
        parameter_mapping={"feedback": "text"},
    )
    workflow.add_node("analyze_sentiment", sentiment_node)

    # Smart routing based on analysis
    routing_node = MCPToolNode(mcp_server=mcp_server_name, tool_name="smart_route")
    workflow.add_node("route_customer", routing_node)

    # Process based on route
    switch = SwitchNode(
        condition=lambda x: x.get("route", "default"),
        outputs=["express", "standard", "basic", "default"],
    )
    workflow.add_node("switch_process", switch)

    # Different processing paths
    express_process = PythonCodeNode(
        code="""
output = {
    'customer_id': input_data.get('customer_id'),
    'process_type': 'express',
    'priority': 'high',
    'sla': '24h'
}
"""
    )
    workflow.add_node("express_process", express_process)

    standard_process = PythonCodeNode(
        code="""
output = {
    'customer_id': input_data.get('customer_id'),
    'process_type': 'standard',
    'priority': 'normal',
    'sla': '48h'
}
"""
    )
    workflow.add_node("standard_process", standard_process)

    # Merge results
    merge = MergeNode()
    workflow.add_node("merge_results", merge)

    # Write results
    writer = CSVWriterNode()
    workflow.add_node("save_analysis", writer)

    # Connect nodes
    workflow.add_edge("read_customers", "enrich_customer")
    workflow.add_edge("enrich_customer", "analyze_sentiment")
    workflow.add_edge("analyze_sentiment", "route_customer")
    workflow.add_edge("route_customer", "switch_process")

    workflow.add_edge("switch_process", "express_process", "express")
    workflow.add_edge("switch_process", "standard_process", "standard")

    workflow.add_edge("express_process", "merge_results")
    workflow.add_edge("standard_process", "merge_results")

    workflow.add_edge("merge_results", "save_analysis")

    return workflow


def create_order_processing_workflow() -> Workflow:
    """Create an order processing workflow."""
    workflow = Workflow("order_processing")

    # Validate order
    validator = PythonCodeNode(
        code="""
import json

order = input_data
errors = []

# Validate required fields
required_fields = ['order_id', 'customer_id', 'items', 'total']
for field in required_fields:
    if field not in order:
        errors.append(f"Missing required field: {field}")

# Validate items
if 'items' in order and isinstance(order['items'], list):
    for item in order['items']:
        if 'quantity' not in item or item['quantity'] <= 0:
            errors.append(f"Invalid quantity for item: {item.get('name', 'unknown')}")

output = {
    'order': order,
    'valid': len(errors) == 0,
    'errors': errors,
    'validation_timestamp': datetime.now().isoformat()
}
"""
    )
    workflow.add_node("validate_order", validator)

    # Check inventory
    inventory_check = PythonCodeNode(
        code="""
order = input_data['order']
items_available = True

# Simulate inventory check
for item in order.get('items', []):
    # In real implementation, this would check actual inventory
    stock = hash(item.get('sku', '')) % 100
    if stock < item.get('quantity', 0):
        items_available = False
        break

output = {
    'order': order,
    'inventory_available': items_available,
    'estimated_ship_date': '2024-12-15' if items_available else None
}
"""
    )
    workflow.add_node("check_inventory", inventory_check)

    # Process payment
    payment_processor = PythonCodeNode(
        code="""
order = input_data['order']
# Simulate payment processing
payment_success = hash(order.get('order_id', '')) % 10 > 2  # 80% success rate

output = {
    'order_id': order.get('order_id'),
    'payment_status': 'approved' if payment_success else 'declined',
    'transaction_id': f"TXN-{hash(order.get('order_id', '')) % 1000000}",
    'amount': order.get('total', 0)
}
"""
    )
    workflow.add_node("process_payment", payment_processor)

    # Connect nodes
    workflow.add_edge("validate_order", "check_inventory")
    workflow.add_edge("check_inventory", "process_payment")

    return workflow


def create_reporting_workflow() -> Workflow:
    """Create a comprehensive reporting workflow."""
    workflow = Workflow("reporting")

    # Aggregate data from multiple sources
    aggregator = PythonCodeNode(
        code="""
import pandas as pd
from datetime import datetime

# Simulate data aggregation
report_data = {
    'report_id': f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    'generated_at': datetime.now().isoformat(),
    'metrics': {
        'total_customers': 1543,
        'active_customers': 892,
        'total_orders': 3421,
        'revenue': 285420.50,
        'avg_order_value': 83.45
    },
    'trends': {
        'customer_growth': '+12.5%',
        'revenue_growth': '+18.3%',
        'order_volume': '+15.7%'
    },
    'alerts': [
        'High value customer churn rate increased by 5%',
        'Inventory levels low for top 3 products'
    ]
}

output = report_data
"""
    )
    workflow.add_node("aggregate_data", aggregator)

    # Generate visualizations
    viz_generator = PythonCodeNode(
        code="""
report = input_data

# Generate chart data
charts = {
    'revenue_trend': {
        'type': 'line',
        'data': [
            {'month': 'Jan', 'value': 230000},
            {'month': 'Feb', 'value': 245000},
            {'month': 'Mar', 'value': 285420}
        ]
    },
    'customer_segments': {
        'type': 'pie',
        'data': [
            {'segment': 'Premium', 'count': 156},
            {'segment': 'Standard', 'count': 543},
            {'segment': 'Basic', 'count': 844}
        ]
    }
}

output = {
    **report,
    'visualizations': charts
}
"""
    )
    workflow.add_node("generate_viz", viz_generator)

    # Connect nodes
    workflow.add_edge("aggregate_data", "generate_viz")

    return workflow


def main():
    """Run the complex gateway example."""
    print("=== Complex Multi-Workflow Gateway with MCP Integration ===\n")

    # Create MCP server
    print("Setting up MCP server...")
    mcp_server = create_mcp_server()
    print(f"✓ Created MCP server 'ai_tools' with {len(mcp_server.tools)} tools\n")

    # Create gateway
    gateway = WorkflowAPIGateway(
        title="Enterprise Workflow Platform",
        description="Advanced workflow orchestration with AI integration",
        version="2.0.0",
        max_workers=20,
        cors_origins=["http://localhost:3000", "https://app.company.com"],
    )

    # Register MCP server
    gateway.register_mcp_server("ai_tools", mcp_server)

    # Register workflows
    print("Registering workflows...")

    # Customer analysis with MCP
    customer_workflow = create_customer_analysis_workflow("ai_tools")
    # Set MCP integration for nodes that need it
    for node_name, node in customer_workflow.nodes.items():
        if isinstance(node, MCPToolNode):
            node.set_mcp_integration(mcp_server)

    gateway.register_workflow(
        "customers",
        customer_workflow,
        description="AI-powered customer analysis and routing",
        tags=["customers", "ai", "analytics"],
    )

    gateway.register_workflow(
        "orders",
        create_order_processing_workflow(),
        description="Order validation and processing",
        tags=["orders", "payments", "inventory"],
    )

    gateway.register_workflow(
        "reports",
        create_reporting_workflow(),
        description="Comprehensive business reporting",
        tags=["reporting", "analytics", "dashboards"],
    )

    print("✓ Registered 3 workflows\n")

    # Create orchestrator for workflow chaining
    orchestrator = WorkflowOrchestrator(gateway)

    # Define workflow chains
    orchestrator.create_chain(
        "full_customer_journey", ["customers", "orders", "reports"]
    )

    print("✓ Created workflow orchestration chains\n")

    # Display comprehensive information
    print("Platform Overview:")
    print("-" * 60)
    print("MCP Tools Available:")
    for tool in mcp_server.list_tools():
        print(f"  - {tool['name']}: {tool['description']}")
    print()

    print("Registered Workflows:")
    for name, reg in gateway.workflows.items():
        print(f"  - {name}: {reg.description}")
        print(f"    Tags: {', '.join(reg.tags)}")
    print()

    print("API Endpoints:")
    print("-" * 60)
    print("Platform Info:      http://localhost:8000/")
    print("All Workflows:      http://localhost:8000/workflows")
    print("Health Status:      http://localhost:8000/health")
    print("WebSocket:          ws://localhost:8000/ws")
    print()

    # Example complex workflow execution
    print("Example: AI-Powered Customer Analysis")
    print("-" * 60)
    print("curl -X POST http://localhost:8000/customers/execute \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -d '{")
    print('    "read_customers": {')
    print(f'      "file_path": "{DATA_DIR}/customers.csv"')
    print("    },")
    print('    "enrich_customer": {')
    print('      "fields": ["category", "risk_score", "timestamp"]')
    print("    },")
    print('    "save_analysis": {')
    print(f'      "file_path": "{OUTPUT_DIR}/customer_analysis.csv"')
    print("    }")
    print("  }'")
    print()

    # Example orchestrated workflow
    print("Example: Full Customer Journey (Orchestrated)")
    print("-" * 60)
    print("# This would execute multiple workflows in sequence:")
    print("# 1. Analyze customer → 2. Process their order → 3. Generate report")
    print()
    print("curl -X POST http://localhost:8000/orchestrate/full_customer_journey \\")
    print("  -H 'Content-Type: application/json' \\")
    print('  -d \'{"customer_id": "CUST-12345"}\'')

    return gateway, mcp_server


if __name__ == "__main__":
    gateway, mcp_server = main()

    print("\n\nGateway Configuration Complete!")
    print("=" * 60)
    print("The gateway is configured with:")
    print(f"  - {len(gateway.workflows)} workflows")
    print(f"  - {len(mcp_server.tools)} MCP tools")
    print("  - WebSocket support for real-time updates")
    print("  - Workflow orchestration capabilities")
    print()
    print("To start the server, run: gateway.run(port=8000)")
    print()
    print("Access the interactive API documentation at:")
    print("http://localhost:8000/docs (Gateway)")
    print("http://localhost:8000/customers/docs (Customer Workflow)")
    print("http://localhost:8000/orders/docs (Order Workflow)")
    print("http://localhost:8000/reports/docs (Reporting Workflow)")

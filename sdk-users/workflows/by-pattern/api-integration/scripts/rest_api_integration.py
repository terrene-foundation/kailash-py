#!/usr/bin/env python3
"""
REST API Integration with Kailash SDK
====================================

This script demonstrates production-ready REST API integration patterns:
1. Authentication and authorization
2. Rate limiting and retry logic
3. Pagination handling
4. Error recovery
5. Response transformation

Key Features:
- Uses RESTClientNode for all API operations
- Implements rate limiting with RateLimitedAPINode
- Handles various authentication methods
- Production-ready error handling
"""

import asyncio

from kailash import Workflow
from kailash.nodes.api import RateLimitedAPINode, RESTClientNode, WebhookNode
from kailash.nodes.api.rate_limiting import RateLimitConfig
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime import AsyncLocalRuntime


def create_api_integration_workflow() -> Workflow:
    """Create a comprehensive REST API integration workflow."""
    workflow = Workflow(name="api_integration")

    # Customer API with authentication
    customer_api = RESTClientNode(name="customer_api")
    workflow.add_node(customer_api)

    # Orders API with rate limiting
    rate_limit_config = RateLimitConfig(
        max_requests=100,
        time_window=60,  # 100 requests per minute
        strategy="token_bucket",
        burst_limit=10,
    )

    orders_api_base = RESTClientNode(name="orders_api_base")
    orders_api = RateLimitedAPINode(
        wrapped_node=orders_api_base,
        rate_limit_config=rate_limit_config,
        name="orders_api",
    )
    workflow.add_node(orders_api)

    # Transform customer data
    customer_transformer = DataTransformer(name="customer_transformer")
    workflow.add_node(customer_transformer)
    workflow.connect(customer_api.id, customer_transformer.id, mapping={"data": "data"})

    # Filter active customers
    active_filter = FilterNode(name="active_customers")
    workflow.add_node(active_filter)
    workflow.connect(
        customer_transformer.id, active_filter.id, mapping={"result": "data"}
    )

    # Enrich with order data
    order_enricher = DataTransformer(name="order_enricher")
    workflow.add_node(order_enricher)
    workflow.connect(
        active_filter.id, order_enricher.id, mapping={"filtered_data": "customers"}
    )
    workflow.connect(orders_api.id, order_enricher.id, mapping={"data": "orders"})

    # Status-based routing
    status_router = SwitchNode(name="status_router")
    workflow.add_node(status_router)
    workflow.connect(order_enricher.id, status_router.id, mapping={"result": "input"})

    # Webhook for high-value customers
    webhook_notifier = WebhookNode(
        name="slack_notifier", url="https://hooks.slack.com/services/YOUR/WEBHOOK"
    )
    workflow.add_node(webhook_notifier)
    workflow.connect(status_router.id, webhook_notifier.id, output_key="high_value")

    # Standard processing
    standard_processor = DataTransformer(name="standard_processor")
    workflow.add_node(standard_processor)
    workflow.connect(status_router.id, standard_processor.id, output_key="standard")

    # Merge results
    result_merger = MergeNode(name="result_merger")
    workflow.add_node(result_merger)
    workflow.connect(
        webhook_notifier.id, result_merger.id, mapping={"response": "notifications"}
    )
    workflow.connect(
        standard_processor.id, result_merger.id, mapping={"result": "processed"}
    )

    return workflow


async def run_api_integration():
    """Execute the API integration workflow."""
    workflow = create_api_integration_workflow()
    runtime = AsyncLocalRuntime()

    # Define runtime parameters
    parameters = {
        "customer_api": {
            "base_url": "https://api.example.com/v1",
            "resource": "customers",
            "method": "GET",
            "auth_type": "bearer",
            "auth_token": "your-api-token",
            "query_params": {"page": 1, "per_page": 50, "status": "active"},
            "paginate": True,
            "pagination_params": {
                "type": "page",
                "page_param": "page",
                "limit_param": "per_page",
                "items_path": "data",
                "total_path": "meta.total",
            },
        },
        "orders_api": {
            "base_url": "https://api.example.com/v1",
            "resource": "orders",
            "method": "GET",
            "auth_type": "api_key",
            "auth_token": "your-api-key",
            "api_key_header": "X-API-Key",
            "query_params": {"date_from": "2024-01-01", "status": "completed"},
            "respect_rate_limits": True,
            "wait_on_rate_limit": True,
        },
        "customer_transformer": {
            "transformations": [
                # Standardize customer data
                """
result = []
for customer in data:
    transformed = {
        'id': customer.get('customer_id') or customer.get('id'),
        'name': customer.get('full_name') or f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        'email': customer.get('email'),
        'status': customer.get('status', 'unknown'),
        'created_at': customer.get('created_at'),
        'lifetime_value': float(customer.get('total_spent', 0))
    }
    result.append(transformed)
"""
            ]
        },
        "active_customers": {"field": "status", "operator": "==", "value": "active"},
        "order_enricher": {
            "transformations": [
                # Enrich customers with order data
                """
# Create order lookup by customer
from collections import defaultdict
order_map = defaultdict(list)
for order in orders:
    order_map[order['customer_id']].append(order)

# Enrich each customer
result = []
for customer in customers:
    customer_orders = order_map.get(customer['id'], [])
    enriched = {
        **customer,
        'order_count': len(customer_orders),
        'recent_order_date': max((o['date'] for o in customer_orders), default=None),
        'total_order_value': sum(float(o.get('total', 0)) for o in customer_orders),
        'is_high_value': customer['lifetime_value'] > 1000 or len(customer_orders) > 10
    }
    result.append(enriched)
"""
            ]
        },
        "status_router": {
            "condition_field": "is_high_value",
            "routes": {"True": "high_value", "False": "standard"},
        },
        "slack_notifier": {
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "transform_payload": True,
            "payload_template": {
                "text": "🎯 High-value customer detected!",
                "attachments": [
                    {
                        "color": "good",
                        "fields": [
                            {"title": "Customer", "value": "{{ name }}", "short": True},
                            {
                                "title": "Orders",
                                "value": "{{ order_count }}",
                                "short": True,
                            },
                            {
                                "title": "Total Value",
                                "value": "${{ total_order_value }}",
                                "short": True,
                            },
                        ],
                    }
                ],
            },
        },
        "standard_processor": {
            "transformations": [
                # Standard processing for regular customers
                "lambda customers: [{'customer_id': c['id'], 'status': 'processed', 'segment': 'standard'} for c in customers]"
            ]
        },
        "result_merger": {"merge_strategy": "combine", "output_format": "structured"},
    }

    try:
        print("Starting API integration workflow...")
        result = await runtime.execute(workflow, parameters=parameters)
        print("API integration completed successfully!")
        return result
    except Exception as e:
        print(f"API integration failed: {str(e)}")
        raise


def create_github_api_workflow() -> Workflow:
    """Create a GitHub API integration workflow."""
    workflow = Workflow(name="github_integration")

    # Get repository info
    repo_api = RESTClientNode(name="repo_info")
    workflow.add_node(repo_api)

    # Get repository issues
    issues_api = RESTClientNode(name="issues_api")
    workflow.add_node(issues_api)

    # Filter open issues
    open_issues = FilterNode(name="open_issues")
    workflow.add_node(open_issues)
    workflow.connect(issues_api.id, open_issues.id, mapping={"data": "data"})

    # Get pull requests
    prs_api = RESTClientNode(name="prs_api")
    workflow.add_node(prs_api)

    # Transform and merge data
    stats_calculator = DataTransformer(name="repo_stats")
    workflow.add_node(stats_calculator)
    workflow.connect(repo_api.id, stats_calculator.id, mapping={"data": "repo"})
    workflow.connect(
        open_issues.id, stats_calculator.id, mapping={"filtered_data": "issues"}
    )
    workflow.connect(prs_api.id, stats_calculator.id, mapping={"data": "pull_requests"})

    return workflow


def main():
    """Main entry point."""
    import os

    # Check for demo mode
    if os.getenv("DEMO_MODE", "true").lower() == "true":
        print("Running in demo mode with mock endpoints...")
        # In demo mode, we'll use mock data

        # Create mock workflow
        from kailash import Workflow
        from kailash.nodes.data import ConstantNode

        demo_workflow = Workflow(name="api_demo")

        # Mock customer data
        mock_customers = ConstantNode(
            name="mock_customers",
            value=[
                {
                    "id": "C001",
                    "name": "Alice Corp",
                    "email": "alice@corp.com",
                    "status": "active",
                    "total_spent": "5000",
                },
                {
                    "id": "C002",
                    "name": "Bob Inc",
                    "email": "bob@inc.com",
                    "status": "active",
                    "total_spent": "800",
                },
                {
                    "id": "C003",
                    "name": "Charlie LLC",
                    "email": "charlie@llc.com",
                    "status": "inactive",
                    "total_spent": "0",
                },
            ],
        )
        demo_workflow.add_node(mock_customers)

        # Mock order data
        mock_orders = ConstantNode(
            name="mock_orders",
            value=[
                {
                    "order_id": "O001",
                    "customer_id": "C001",
                    "date": "2024-02-15",
                    "total": "1500",
                },
                {
                    "order_id": "O002",
                    "customer_id": "C001",
                    "date": "2024-02-20",
                    "total": "2000",
                },
                {
                    "order_id": "O003",
                    "customer_id": "C002",
                    "date": "2024-02-10",
                    "total": "800",
                },
            ],
        )
        demo_workflow.add_node(mock_orders)

        print("Demo workflow created with mock data")
    else:
        # Production mode
        asyncio.execute(run_api_integration())


if __name__ == "__main__":
    main()

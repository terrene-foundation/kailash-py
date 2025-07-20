# DataFlow + Nexus Integration

Integrate DataFlow with Nexus to create unified multi-channel platforms with automatic API, CLI, and MCP interfaces.

## Overview

The DataFlow + Nexus integration provides:
- **Automatic API Generation**: REST endpoints for all DataFlow models
- **CLI Commands**: Command-line interface for database operations
- **MCP Tools**: AI agents can perform database operations
- **WebSocket Support**: Real-time database change notifications
- **Unified Sessions**: Cross-channel state synchronization

## Quick Start

### Basic Integration

```python
from dataflow import DataFlow
from nexus import Nexus

# Initialize DataFlow
db = DataFlow()

@db.model
class Product:
    name: str
    price: float
    stock: int = 0
    active: bool = True

@db.model
class Order:
    customer_id: int
    product_id: int
    quantity: int
    total: float
    status: str = "pending"

# Create Nexus with DataFlow integration
nexus = Nexus(
    title="E-commerce Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    dataflow_integration=db  # Auto-generates all interfaces
)
```

This automatically creates:
- REST API endpoints for Products and Orders
- CLI commands for all CRUD operations
- MCP tools for AI agents
- WebSocket subscriptions for real-time updates

## API Generation

### Automatic REST Endpoints

Every DataFlow model gets these REST endpoints:

```python
# Product endpoints (automatically generated)
GET    /api/products           # List products
POST   /api/products           # Create product
GET    /api/products/{id}      # Get product
PUT    /api/products/{id}      # Update product
DELETE /api/products/{id}      # Delete product
POST   /api/products/bulk      # Bulk operations
GET    /api/products/aggregate # Aggregations

# With query parameters
GET /api/products?active=true&sort=-price&limit=20
GET /api/products?name__contains=phone&price__gte=100
```

### Advanced API Configuration

```python
nexus = Nexus(
    title="Advanced E-commerce API",
    dataflow_config={
        "integration": db,
        "auto_generate_endpoints": True,

        # API customization
        "api_prefix": "/api/v1",
        "expose_bulk_operations": True,
        "expose_aggregations": True,
        "expose_transactions": True,

        # Security
        "require_authentication": True,
        "rate_limiting": {
            "default": 1000,  # per hour
            "bulk_operations": 100
        },

        # Real-time features
        "websocket_enabled": True,
        "change_notifications": True
    }
)
```

### Custom API Endpoints

Add custom business logic endpoints:

```python
from kailash.workflow.builder import WorkflowBuilder

# Custom endpoint for order processing
@nexus.api_endpoint("/api/orders/{order_id}/process", methods=["POST"])
def process_order(order_id: int):
    workflow = WorkflowBuilder()

    # Get order details
    workflow.add_node("OrderReadNode", "order", {"id": order_id})

    # Check product stock
    workflow.add_node("ProductReadNode", "product", {
        "id": "$order.product_id"
    })

    # Update stock
    workflow.add_node("ProductUpdateNode", "update_stock", {
        "id": "$order.product_id",
        "stock": {"$dec": "$order.quantity"}
    })

    # Update order status
    workflow.add_node("OrderUpdateNode", "complete", {
        "id": order_id,
        "status": "completed"
    })

    return nexus.execute_workflow(workflow)
```

## CLI Integration

### Automatic CLI Commands

Every model gets CLI commands:

```bash
# Product commands (automatically generated)
nexus products create --name "iPhone 15" --price 999.99 --stock 100
nexus products list --active true --sort -price --limit 10
nexus products get 123
nexus products update 123 --stock 150
nexus products delete 123

# Bulk operations
nexus products bulk-create --file products.json
nexus products bulk-update --filter '{"category": "phones"}' --set '{"on_sale": true}'

# Aggregations
nexus products aggregate --group-by category --sum price --avg stock
```

### CLI Configuration

```python
nexus = Nexus(
    title="E-commerce CLI",
    dataflow_config={
        "integration": db,
        "auto_generate_cli_commands": True,

        # CLI customization
        "cli_command_prefix": "shop",  # e.g., "shop products list"
        "enable_interactive_mode": True,
        "enable_output_formats": ["json", "table", "csv"],

        # Advanced features
        "enable_query_builder": True,  # Interactive query building
        "enable_data_import": True,    # Import from CSV/JSON
        "enable_data_export": True     # Export to various formats
    }
)
```

### Interactive Query Builder

```bash
# Interactive mode
nexus query
> select products
> where price > 100 and active = true
> sort by -created_at
> limit 20
> execute

# Or as one command
nexus query "products where price > 100 order by -price limit 10"
```

## MCP Integration

### AI Agent Database Access

Enable AI agents to perform database operations:

```python
nexus = Nexus(
    title="AI-Powered E-commerce",
    enable_mcp=True,
    dataflow_config={
        "integration": db,
        "auto_generate_mcp_tools": True,

        # MCP tool configuration
        "mcp_tool_prefix": "database",
        "expose_to_agents": {
            "read_operations": True,
            "write_operations": True,
            "bulk_operations": True,
            "analytics": True
        },

        # Safety controls
        "require_confirmation": ["delete", "bulk_delete"],
        "max_records_per_operation": 1000,
        "audit_agent_actions": True
    }
)
```

### Agent Usage Examples

AI agents can now:

```python
# Agent performs database operations
agent_request = """
Find all products that are low on stock (less than 10 units)
and create a purchase order for each one to restock to 100 units.
"""

# Agent automatically:
# 1. Uses database.products.list tool with filter {"stock": {"$lt": 10}}
# 2. For each product, uses database.purchase_orders.create tool
# 3. Updates product stock levels
```

## Real-Time Features

### WebSocket Subscriptions

Enable real-time database updates:

```python
# Client-side subscription
const ws = new WebSocket('ws://localhost:8000/ws');

// Subscribe to product changes
ws.send(JSON.stringify({
    action: 'subscribe',
    model: 'products',
    filter: { active: true },
    events: ['create', 'update', 'delete']
}));

// Receive real-time updates
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`Product ${data.event}:`, data.record);
};
```

### Server-Side Configuration

```python
nexus = Nexus(
    title="Real-Time E-commerce",
    dataflow_config={
        "integration": db,
        "websocket_config": {
            "enabled": True,
            "allow_subscriptions": True,
            "max_subscriptions_per_client": 10,
            "heartbeat_interval": 30,

            # Change detection
            "change_detection_method": "database_triggers",  # or "polling"
            "notification_batch_size": 100,
            "notification_delay_ms": 100
        }
    }
)
```

## Transaction Support

### Multi-Model Transactions

Execute complex transactions across models:

```python
@nexus.api_endpoint("/api/checkout", methods=["POST"])
def checkout(order_data: dict):
    workflow = WorkflowBuilder()

    # Start transaction
    workflow.add_node("TransactionStartNode", "txn", {
        "isolation_level": "READ_COMMITTED"
    })

    # Create order
    workflow.add_node("OrderCreateNode", "order", {
        "customer_id": order_data["customer_id"],
        "items": order_data["items"],
        "total": order_data["total"]
    })

    # Update inventory for each item
    for item in order_data["items"]:
        workflow.add_node(f"ProductUpdateNode", f"stock_{item['product_id']}", {
            "id": item["product_id"],
            "stock": {"$dec": item["quantity"]},
            "transaction_id": "$txn.id"
        })

    # Process payment
    workflow.add_node("PaymentProcessNode", "payment", {
        "amount": order_data["total"],
        "method": order_data["payment_method"],
        "transaction_id": "$txn.id"
    })

    # Commit or rollback
    workflow.add_node("TransactionCommitNode", "commit", {
        "transaction_id": "$txn.id",
        "rollback_on_error": True
    })

    return nexus.execute_workflow(workflow)
```

## Analytics Integration

### Built-in Analytics Endpoints

```python
# Automatic analytics endpoints
GET /api/analytics/products/sales-by-category
GET /api/analytics/orders/revenue-by-month
GET /api/analytics/customers/lifetime-value

# Custom analytics
@nexus.api_endpoint("/api/analytics/dashboard")
def analytics_dashboard():
    workflow = WorkflowBuilder()

    # Multiple aggregations in parallel
    workflow.add_node("ProductAggregateNode", "inventory", {
        "group_by": ["category"],
        "aggregate": {
            "total_value": {"$sum": {"$multiply": ["price", "stock"]}},
            "low_stock_count": {"$sum": {"$case": [
                {"$lt": ["stock", 10]}, 1, 0
            ]}}
        }
    })

    workflow.add_node("OrderAggregateNode", "revenue", {
        "filter": {"status": "completed"},
        "group_by": [{"$date_trunc": ["day", "created_at"]}],
        "aggregate": {
            "daily_revenue": {"$sum": "total"},
            "order_count": {"$count": "*"}
        }
    })

    return nexus.execute_workflow(workflow)
```

## Multi-Tenant Support

### Tenant-Aware Integration

```python
# Multi-tenant DataFlow
db = DataFlow(multi_tenant=True)

@db.model
class Product:
    name: str
    price: float
    __dataflow__ = {'multi_tenant': True}

# Tenant-aware Nexus
nexus = Nexus(
    title="Multi-Tenant E-commerce",
    dataflow_config={
        "integration": db,
        "multi_tenant": {
            "enabled": True,
            "tenant_identification": "header",  # X-Tenant-ID
            "tenant_isolation": "strict",
            "cross_tenant_operations": ["admin_only"]
        }
    }
)

# Requests automatically filtered by tenant
# GET /api/products (with X-Tenant-ID: acme)
# Only returns products for tenant "acme"
```

## Performance Optimization

### Caching Integration

```python
nexus = Nexus(
    title="High-Performance E-commerce",
    dataflow_config={
        "integration": db,
        "caching": {
            "enabled": True,
            "backend": "redis",
            "default_ttl": 300,  # 5 minutes

            # Cache strategies
            "cache_strategies": {
                "products": {
                    "list": {"ttl": 600, "key_pattern": "products:*"},
                    "get": {"ttl": 3600, "key_pattern": "product:{id}"}
                },
                "orders": {
                    "list": {"ttl": 60},  # Shorter TTL for orders
                    "aggregate": {"ttl": 300}
                }
            },

            # Auto-invalidation
            "invalidation_events": {
                "product_update": ["products:*", "product:{id}"],
                "product_create": ["products:*"],
                "order_create": ["orders:*", "analytics:*"]
            }
        }
    }
)
```

## Monitoring & Observability

### Integrated Monitoring

```python
nexus = Nexus(
    title="Observable E-commerce",
    dataflow_config={
        "integration": db,
        "monitoring": {
            "enabled": True,
            "metrics_endpoint": "/metrics",

            # Track database metrics
            "database_metrics": {
                "query_time": True,
                "connection_pool": True,
                "cache_hit_rate": True,
                "slow_queries": {"threshold": 100}  # ms
            },

            # Track API metrics
            "api_metrics": {
                "request_rate": True,
                "response_time": True,
                "error_rate": True,
                "endpoint_breakdown": True
            },

            # Alerts
            "alerts": {
                "high_error_rate": {"threshold": 5, "window": 300},
                "slow_response": {"threshold": 1000, "window": 60}
            }
        }
    }
)
```

## Complete Example

### Full E-commerce Platform

```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Initialize DataFlow with models
db = DataFlow(
    database_url="postgresql://localhost/ecommerce",
    multi_tenant=True
)

@db.model
class Customer:
    email: str
    name: str
    tier: str = "standard"  # standard, premium, vip
    __dataflow__ = {
        'multi_tenant': True,
        'soft_delete': True,
        'audit_log': True
    }

@db.model
class Product:
    sku: str
    name: str
    price: float
    stock: int = 0
    category: str
    __dataflow__ = {
        'multi_tenant': True,
        'versioned': True,
        'cache': True
    }
    __indexes__ = [
        {"fields": ["sku"], "unique": True},
        {"fields": ["category", "price"]}
    ]

@db.model
class Order:
    customer_id: int
    items: list  # [{product_id, quantity, price}]
    total: float
    status: str = "pending"
    __dataflow__ = {
        'multi_tenant': True,
        'audit_log': True,
        'workflow_events': ['status_change']
    }

# Create unified platform
nexus = Nexus(
    title="Enterprise E-commerce Platform",

    # Enable all channels
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    channels_synced=True,

    # DataFlow integration
    dataflow_config={
        "integration": db,
        "auto_generate_endpoints": True,
        "auto_generate_cli_commands": True,
        "auto_generate_mcp_tools": True,

        # Features
        "expose_bulk_operations": True,
        "expose_analytics": True,
        "expose_transactions": True,
        "websocket_enabled": True,

        # Performance
        "caching": {"enabled": True, "backend": "redis"},
        "connection_pooling": {"size": 20, "overflow": 10},

        # Security
        "authentication_required": True,
        "rate_limiting": {"default": 10000},
        "audit_all_operations": True
    },

    # Authentication
    auth_config={
        "providers": ["oauth2", "api_key"],
        "rbac_enabled": True,
        "mfa_available": True
    },

    # Monitoring
    monitoring_config={
        "prometheus_enabled": True,
        "opentelemetry_enabled": True,
        "custom_metrics": True
    }
)

# Add custom business logic
@nexus.workflow("process_vip_order")
def process_vip_order(order_data: dict):
    workflow = WorkflowBuilder()

    # Check customer tier
    workflow.add_node("CustomerReadNode", "customer", {
        "id": order_data["customer_id"]
    })

    # Apply VIP benefits
    workflow.add_node("ConditionalNode", "check_vip", {
        "condition": "$customer.tier == 'vip'",
        "true_branch": "apply_discount",
        "false_branch": "standard_processing"
    })

    # VIP discount
    workflow.add_node("CalculateDiscountNode", "apply_discount", {
        "base_total": order_data["total"],
        "discount_percent": 10,
        "free_shipping": True
    })

    # Create order with benefits
    workflow.add_node("OrderCreateNode", "create_order", {
        **order_data,
        "total": "$apply_discount.final_total",
        "benefits_applied": "$apply_discount.benefits"
    })

    return workflow

# Platform is now accessible via:
# - REST API: http://localhost:8000/api/
# - CLI: nexus --help
# - MCP: Available to AI agents
# - WebSocket: ws://localhost:8000/ws
```

## Best Practices

### 1. Design for Scale

```python
# Optimize for high traffic
nexus = Nexus(
    dataflow_config={
        "integration": db,
        "connection_pooling": {
            "size": 50,
            "overflow": 25,
            "recycle": 3600
        },
        "caching": {
            "enabled": True,
            "aggressive_caching": True,
            "preload_common_queries": True
        },
        "async_operations": True
    }
)
```

### 2. Security First

```python
# Secure by default
nexus = Nexus(
    dataflow_config={
        "integration": db,
        "security": {
            "require_authentication": True,
            "encrypt_sensitive_fields": True,
            "audit_all_operations": True,
            "rate_limiting": {"enabled": True},
            "sql_injection_protection": True
        }
    }
)
```

### 3. Monitor Everything

```python
# Comprehensive observability
nexus = Nexus(
    dataflow_config={
        "integration": db,
        "monitoring": {
            "track_all_queries": True,
            "slow_query_log": True,
            "performance_metrics": True,
            "error_tracking": True,
            "usage_analytics": True
        }
    }
)
```

---

**Next**: See [Gateway Integration](gateway.md) for REST API gateway patterns.

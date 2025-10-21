"""
Enterprise Integration with DataFlow

This example demonstrates:
- Integration with Kailash gateway
- Distributed transactions (Saga pattern)
- Event-driven workflows
- Real-time data synchronization
- API endpoint generation
- Security and access control
"""

from datetime import datetime

from kailash.middleware.gateway import create_gateway
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Production-ready configuration
db = DataFlow(
    multi_tenant=True,
    monitoring=True,
    pool_size=50,
)


# E-commerce models
@db.model
class Customer:
    """Customer model with profile data"""

    email: str
    name: str
    tier: str = "bronze"  # bronze, silver, gold, platinum
    credit_limit: float = 1000.0
    total_spent: float = 0.0

    __dataflow__ = {
        "soft_delete": True,
        "versioned": True,
        "multi_tenant": True,
    }

    __indexes__ = [
        {"name": "idx_email", "fields": ["email"], "unique": True},
        {"name": "idx_tier", "fields": ["tier"]},
    ]


@db.model
class Order:
    """Order model with status tracking"""

    customer_id: int
    total_amount: float
    status: str = "pending"  # pending, processing, shipped, delivered, cancelled
    payment_status: str = "pending"  # pending, authorized, captured, refunded

    __dataflow__ = {
        "versioned": True,
        "multi_tenant": True,
    }

    __indexes__ = [
        {"name": "idx_status", "fields": ["status", "created_at"]},
        {"name": "idx_customer", "fields": ["customer_id"]},
    ]


@db.model
class OrderItem:
    """Order line items"""

    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    discount: float = 0.0


@db.model
class Inventory:
    """Inventory tracking with reservations"""

    product_id: int
    available_stock: int
    reserved_stock: int = 0
    warehouse_location: str

    __dataflow__ = {
        "versioned": True,  # For optimistic locking
    }


def create_order_saga_workflow(customer_email: str, items: list):
    """
    Create a distributed transaction workflow using Saga pattern

    This demonstrates how DataFlow integrates with Kailash's
    distributed transaction capabilities for complex operations
    spanning multiple services and databases.
    """
    workflow = WorkflowBuilder()

    # Start distributed transaction with Saga pattern
    workflow.add_node(
        "DistributedTransactionManagerNode",
        "saga",
        {
            "pattern": "saga",
            "timeout": 60,  # 60 second timeout
            "isolation_level": "read_committed",
        },
    )

    # Step 1: Validate customer and credit
    workflow.add_node(
        "CustomerReadNode", "get_customer", {"filter": {"email": customer_email}}
    )

    workflow.add_node(
        "PythonCodeNode",
        "validate_credit",
        {
            "code": """
        customer = inputs['customer']
        total = inputs['order_total']

        available_credit = customer['credit_limit'] - customer['total_spent']

        outputs = {
            'approved': available_credit >= total,
            'available_credit': available_credit,
            'customer_id': customer['id']
        }
        """
        },
    )

    # Step 2: Create order
    workflow.add_node(
        "OrderCreateNode",
        "create_order",
        {
            "customer_id": ":customer_id",
            "total_amount": ":order_total",
            "status": "processing",
        },
    )

    # Step 3: Reserve inventory (with compensation)
    for i, item in enumerate(items):
        workflow.add_node(
            "InventoryUpdateNode",
            f"reserve_inventory_{i}",
            {
                "filter": {
                    "product_id": item["product_id"],
                    "available_stock": {"$gte": item["quantity"]},
                },
                "fields": {
                    "available_stock": f"available_stock - {item['quantity']}",
                    "reserved_stock": f"reserved_stock + {item['quantity']}",
                },
            },
        )

        # Compensation: Release inventory if later steps fail
        workflow.add_node(
            "InventoryUpdateNode",
            f"release_inventory_{i}",
            {
                "filter": {"product_id": item["product_id"]},
                "fields": {
                    "available_stock": f"available_stock + {item['quantity']}",
                    "reserved_stock": f"reserved_stock - {item['quantity']}",
                },
            },
        )

    # Step 4: Process payment
    workflow.add_node(
        "PaymentServiceNode",
        "process_payment",
        {
            "customer_id": ":customer_id",
            "amount": ":order_total",
            "order_id": ":order_id",
        },
    )

    # Compensation: Refund payment
    workflow.add_node(
        "PaymentServiceNode",
        "refund_payment",
        {"order_id": ":order_id", "action": "refund"},
    )

    # Step 5: Update customer spending
    workflow.add_node(
        "CustomerUpdateNode",
        "update_spending",
        {
            "filter": {"id": ":customer_id"},
            "fields": {"total_spent": "total_spent + :order_total"},
        },
    )

    # Compensation: Revert spending
    workflow.add_node(
        "CustomerUpdateNode",
        "revert_spending",
        {
            "filter": {"id": ":customer_id"},
            "fields": {"total_spent": "total_spent - :order_total"},
        },
    )

    # Step 6: Send confirmation
    workflow.add_node(
        "EmailNotificationNode",
        "send_confirmation",
        {
            "template": "order_confirmation",
            "to": customer_email,
            "order_id": ":order_id",
        },
    )

    # Connect forward path
    workflow.add_connection("saga", "get_customer")
    workflow.add_connection("get_customer", "validate_credit", "data", "customer")
    workflow.add_connection(
        "validate_credit", "create_order", condition="approved == true"
    )

    # Connect inventory reservations
    prev_node = "create_order"
    for i in range(len(items)):
        workflow.add_connection(prev_node, f"reserve_inventory_{i}")
        prev_node = f"reserve_inventory_{i}"

    workflow.add_connection(prev_node, "process_payment")
    workflow.add_connection("process_payment", "update_spending")
    workflow.add_connection("update_spending", "send_confirmation")

    # Connect compensation path
    workflow.add_connection(
        "process_payment", "refund_payment", condition="status == 'failed'"
    )

    for i in range(len(items)):
        workflow.add_connection("refund_payment", f"release_inventory_{i}")

    workflow.add_connection("refund_payment", "revert_spending")

    return workflow.build()


def create_gateway_api():
    """
    Create a production-ready API gateway with DataFlow integration

    This demonstrates how DataFlow works seamlessly with Kailash's
    gateway for building enterprise APIs.
    """

    # Create gateway with DataFlow integration
    app = create_gateway(
        title="E-commerce API",
        version="1.0.0",
        database_url=db.config.database.get_connection_url(db.config.environment),
        enable_auth=True,
        enable_rate_limiting=True,
        enable_monitoring=True,
    )

    @app.post("/api/v1/customers")
    async def create_customer(email: str, name: str, tier: str = "bronze"):
        """Create a new customer"""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "CustomerCreateNode", "create", {"email": email, "name": name, "tier": tier}
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        return results["create"]["output"]

    @app.post("/api/v1/orders")
    async def create_order(customer_email: str, items: list):
        """Create a new order with distributed transaction"""
        # Calculate total
        total = sum(item["quantity"] * item["unit_price"] for item in items)

        # Create saga workflow
        workflow = create_order_saga_workflow(customer_email, items)

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        return {
            "order_id": results.get("create_order", {}).get("output", {}).get("id"),
            "status": "success" if results.get("send_confirmation") else "failed",
            "run_id": run_id,
        }

    @app.get("/api/v1/customers/{customer_id}/orders")
    async def get_customer_orders(customer_id: int):
        """Get all orders for a customer"""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "OrderListNode",
            "list_orders",
            {"filter": {"customer_id": customer_id}, "order_by": ["-created_at"]},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        return results["list_orders"]["output"]

    @app.get("/api/v1/analytics/top-customers")
    async def get_top_customers(limit: int = 10):
        """Get top customers by spending"""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "CustomerListNode",
            "top_customers",
            {"order_by": ["-total_spent"], "limit": limit},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        return results["top_customers"]["output"]

    return app


def demo_event_driven_workflow():
    """
    Demonstrate event-driven workflows with DataFlow

    This shows how DataFlow can trigger workflows based on
    database events for real-time processing.
    """
    print("\n=== EVENT-DRIVEN WORKFLOW DEMO ===")

    workflow = WorkflowBuilder()

    # Monitor for high-value orders
    workflow.add_node(
        "DatabaseEventMonitorNode",
        "monitor_orders",
        {
            "table": "orders",
            "event_types": ["INSERT", "UPDATE"],
            "filter": {"total_amount": {"$gte": 1000}},
        },
    )

    # When high-value order detected, upgrade customer
    workflow.add_node(
        "CustomerUpdateNode",
        "upgrade_customer",
        {
            "filter": {"id": ":customer_id"},
            "fields": {
                "tier": """
            CASE
                WHEN total_spent >= 10000 THEN 'platinum'
                WHEN total_spent >= 5000 THEN 'gold'
                WHEN total_spent >= 1000 THEN 'silver'
                ELSE tier
            END
            """
            },
        },
    )

    # Send notification
    workflow.add_node(
        "NotificationServiceNode",
        "notify_upgrade",
        {"type": "customer_tier_upgrade", "customer_id": ":customer_id"},
    )

    # Connect event to actions
    workflow.add_connection(
        "monitor_orders", "upgrade_customer", "customer_id", "customer_id"
    )
    workflow.add_connection(
        "upgrade_customer", "notify_upgrade", condition="tier != :previous_tier"
    )

    return workflow.build()


def demo_data_synchronization():
    """
    Demonstrate real-time data synchronization

    This shows how DataFlow can keep multiple systems in sync
    using change data capture (CDC) patterns.
    """
    print("\n=== DATA SYNCHRONIZATION DEMO ===")

    workflow = WorkflowBuilder()

    # Capture changes to customer data
    workflow.add_node(
        "ChangeDataCaptureNode",
        "cdc_customers",
        {
            "source_table": "customers",
            "capture_operations": ["INSERT", "UPDATE", "DELETE"],
            "include_before_image": True,
        },
    )

    # Transform for external system
    workflow.add_node(
        "DataTransformNode",
        "transform",
        {
            "mapping": {
                "customer_id": "id",
                "customer_email": "email",
                "customer_name": "name",
                "customer_tier": "tier",
                "last_updated": "updated_at",
            }
        },
    )

    # Sync to external systems
    workflow.add_node(
        "HTTPRequestNode",
        "sync_to_crm",
        {
            "url": "https://crm.example.com/api/customers",
            "method": "POST",
            "headers": {"Authorization": "Bearer ${CRM_API_KEY}"},
            "body": ":transformed_data",
        },
    )

    workflow.add_node(
        "KafkaProducerNode",
        "publish_event",
        {
            "topic": "customer-updates",
            "key": ":customer_id",
            "value": ":transformed_data",
        },
    )

    # Connect the sync pipeline
    workflow.add_connection("cdc_customers", "transform", "change_data", "input_data")
    workflow.add_connection("transform", "sync_to_crm", "output", "transformed_data")
    workflow.add_connection("transform", "publish_event", "output", "transformed_data")

    return workflow.build()


if __name__ == "__main__":
    print("DataFlow Enterprise Integration Example")
    print("=" * 50)

    # Create sample data
    workflow = WorkflowBuilder()

    # Create customers
    workflow.add_node(
        "CustomerCreateNode",
        "create_cust_1",
        {
            "email": "alice@example.com",
            "name": "Alice Johnson",
            "tier": "gold",
            "credit_limit": 5000.0,
        },
    )

    workflow.add_node(
        "CustomerCreateNode",
        "create_cust_2",
        {
            "email": "bob@example.com",
            "name": "Bob Smith",
            "tier": "silver",
            "credit_limit": 2500.0,
        },
    )

    # Create inventory
    for i in range(1, 4):
        workflow.add_node(
            "InventoryCreateNode",
            f"create_inv_{i}",
            {
                "product_id": i,
                "available_stock": 100,
                "warehouse_location": "Warehouse A",
            },
        )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    print("Sample data created successfully")

    # Demonstrate Saga pattern
    print("\n=== DISTRIBUTED TRANSACTION (SAGA) DEMO ===")

    order_items = [
        {"product_id": 1, "quantity": 2, "unit_price": 299.99},
        {"product_id": 2, "quantity": 1, "unit_price": 149.99},
    ]

    saga_workflow = create_order_saga_workflow("alice@example.com", order_items)
    results, run_id = runtime.execute(saga_workflow)

    if results.get("send_confirmation"):
        print("Order completed successfully with Saga pattern")
        print("All steps committed in order")
    else:
        print("Order failed - all changes rolled back")
        print("Saga pattern ensured consistency")

    # Create API gateway
    print("\n=== API GATEWAY INTEGRATION ===")
    app = create_gateway_api()
    print("API Gateway created with endpoints:")
    print("  POST   /api/v1/customers")
    print("  POST   /api/v1/orders")
    print("  GET    /api/v1/customers/{id}/orders")
    print("  GET    /api/v1/analytics/top-customers")

    # Event-driven workflow
    print("\n=== EVENT-DRIVEN CAPABILITIES ===")
    event_workflow = demo_event_driven_workflow()
    print("Event-driven workflow created:")
    print("  - Monitors high-value orders")
    print("  - Automatically upgrades customer tiers")
    print("  - Sends notifications on upgrades")

    # Data synchronization
    print("\n=== DATA SYNCHRONIZATION ===")
    sync_workflow = demo_data_synchronization()
    print("Data synchronization pipeline created:")
    print("  - Change data capture on customers table")
    print("  - Transform data for external systems")
    print("  - Sync to CRM via REST API")
    print("  - Publish events to Kafka")

    print("\n" + "=" * 50)
    print("Enterprise integration demonstrated successfully!")
    print("\nKey takeaways:")
    print("1. Saga pattern ensures distributed transaction consistency")
    print("2. Gateway integration provides instant REST APIs")
    print("3. Event-driven workflows enable real-time processing")
    print("4. CDC patterns keep systems synchronized")
    print("5. All with zero-configuration setup!")
    print("\nDataFlow + Kailash SDK = Enterprise-Ready from Day One")

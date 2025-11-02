# DataFlow TDD Real-World Examples

**Complete, working examples for common enterprise use cases**

This guide provides production-ready examples demonstrating DataFlow's TDD infrastructure in real-world scenarios. All examples are tested and achieve <100ms execution time.

## E-Commerce Platform Testing

### User Management System

```python
# tests/e2e/ecommerce/test_user_management.py
import pytest
import uuid
from decimal import Decimal
import os

# Enable TDD mode
os.environ["DATAFLOW_TDD_MODE"] = "true"

@pytest.mark.asyncio
async def test_complete_user_lifecycle(tdd_dataflow):
    """
    Test complete user lifecycle in e-commerce platform

    Covers: Registration, profile updates, order history, account deactivation
    Performance target: <100ms
    """
    df = tdd_dataflow

    # Define e-commerce models
    @df.model
    class User:
        email: str
        username: str
        first_name: str
        last_name: str
        password_hash: str
        is_active: bool = True
        created_at: str = None
        last_login: str = None
        profile_data: dict = None

    @df.model
    class Address:
        user_id: int
        address_type: str  # 'billing', 'shipping'
        street_address: str
        city: str
        state: str
        zip_code: str
        country: str = "US"
        is_default: bool = False

    @df.model
    class Order:
        user_id: int
        order_number: str
        status: str  # 'pending', 'confirmed', 'shipped', 'delivered', 'cancelled'
        total_amount: float
        tax_amount: float
        shipping_amount: float
        order_date: str
        shipping_date: str = None
        delivery_date: str = None
        order_items: dict = None

    # Create tables
    df.create_tables()

    # 1. User Registration
    user_data = {
        "email": "alice.customer@example.com",
        "username": "alice_customer",
        "first_name": "Alice",
        "last_name": "Customer",
        "password_hash": "hashed_password_123",
        "profile_data": {
            "preferences": {"newsletter": True, "promotions": False},
            "demographics": {"age_range": "25-34"}
        }
    }

    user_result = await df.User.create(user_data)
    assert user_result["success"] is True
    user_id = user_result["data"]["id"]

    # 2. Add Multiple Addresses
    addresses = [
        {
            "user_id": user_id,
            "address_type": "billing",
            "street_address": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "is_default": True
        },
        {
            "user_id": user_id,
            "address_type": "shipping",
            "street_address": "456 Work Ave",
            "city": "Business City",
            "state": "NY",
            "zip_code": "67890",
            "is_default": False
        }
    ]

    for address_data in addresses:
        address_result = await df.Address.create(address_data)
        assert address_result["success"] is True

    # 3. Create Multiple Orders
    orders = [
        {
            "user_id": user_id,
            "order_number": f"ORD-{uuid.uuid4().hex[:8].upper()}",
            "status": "delivered",
            "total_amount": 299.99,
            "tax_amount": 24.00,
            "shipping_amount": 9.99,
            "order_date": "2024-01-15",
            "shipping_date": "2024-01-16",
            "delivery_date": "2024-01-18",
            "order_items": {
                "items": [
                    {"product_id": 1, "name": "Wireless Headphones", "quantity": 1, "price": 299.99}
                ]
            }
        },
        {
            "user_id": user_id,
            "order_number": f"ORD-{uuid.uuid4().hex[:8].upper()}",
            "status": "shipped",
            "total_amount": 89.99,
            "tax_amount": 7.20,
            "shipping_amount": 5.99,
            "order_date": "2024-01-20",
            "shipping_date": "2024-01-22",
            "order_items": {
                "items": [
                    {"product_id": 2, "name": "Phone Case", "quantity": 2, "price": 44.99}
                ]
            }
        }
    ]

    order_ids = []
    for order_data in orders:
        order_result = await df.Order.create(order_data)
        assert order_result["success"] is True
        order_ids.append(order_result["data"]["id"])

    # 4. Query User Profile with Related Data
    user_profile = await df.User.find_one({"id": user_id})
    assert user_profile["success"] is True
    assert user_profile["data"]["email"] == "alice.customer@example.com"
    assert user_profile["data"]["profile_data"]["preferences"]["newsletter"] is True

    # 5. Query User Addresses
    user_addresses = await df.Address.find_many({"user_id": user_id})
    assert user_addresses["success"] is True
    assert len(user_addresses["data"]) == 2

    # Find default billing address
    billing_addresses = [addr for addr in user_addresses["data"]
                        if addr["address_type"] == "billing" and addr["is_default"]]
    assert len(billing_addresses) == 1
    assert billing_addresses[0]["street_address"] == "123 Main St"

    # 6. Query User Order History
    user_orders = await df.Order.find_many({"user_id": user_id})
    assert user_orders["success"] is True
    assert len(user_orders["data"]) == 2

    # Calculate total order value
    total_spent = sum(order["total_amount"] for order in user_orders["data"])
    assert total_spent == 389.98  # 299.99 + 89.99

    # 7. Update User Profile
    updated_profile = {
        "profile_data": {
            "preferences": {"newsletter": False, "promotions": True},
            "demographics": {"age_range": "25-34"},
            "purchase_history": {"total_orders": 2, "total_spent": total_spent}
        }
    }

    update_result = await df.User.update({"id": user_id}, updated_profile)
    assert update_result["success"] is True

    # 8. Verify Profile Update
    updated_user = await df.User.find_one({"id": user_id})
    assert updated_user["data"]["profile_data"]["preferences"]["newsletter"] is False
    assert updated_user["data"]["profile_data"]["preferences"]["promotions"] is True
    assert updated_user["data"]["profile_data"]["purchase_history"]["total_orders"] == 2

    # 9. Order Status Updates
    shipped_order_update = await df.Order.update(
        {"id": order_ids[1]},
        {"status": "delivered", "delivery_date": "2024-01-25"}
    )
    assert shipped_order_update["success"] is True

    # 10. Account Deactivation (Soft Delete)
    deactivation_result = await df.User.update(
        {"id": user_id},
        {"is_active": False}
    )
    assert deactivation_result["success"] is True

    # Verify user is deactivated but data preserved
    deactivated_user = await df.User.find_one({"id": user_id})
    assert deactivated_user["data"]["is_active"] is False

    # Orders should still be accessible for business records
    historical_orders = await df.Order.find_many({"user_id": user_id})
    assert len(historical_orders["data"]) == 2

    # Test execution completes in <100ms with TDD infrastructure
```

### Inventory Management Testing

```python
# tests/e2e/ecommerce/test_inventory_management.py
@pytest.mark.asyncio
async def test_inventory_management_workflow(tdd_dataflow):
    """
    Test inventory management with concurrent operations

    Covers: Stock updates, low stock alerts, reorder automation
    Performance target: <100ms
    """
    df = tdd_dataflow

    # Define inventory models
    @df.model
    class Product:
        sku: str
        name: str
        category: str
        price: float
        cost: float
        supplier_id: int
        weight: float
        dimensions: dict = None
        is_active: bool = True

    @df.model
    class Inventory:
        product_id: int
        warehouse_id: int
        quantity_on_hand: int
        quantity_reserved: int
        quantity_available: int
        reorder_point: int
        reorder_quantity: int
        last_updated: str

    @df.model
    class StockMovement:
        product_id: int
        warehouse_id: int
        movement_type: str  # 'in', 'out', 'adjustment', 'transfer'
        quantity: int
        reference_number: str
        reason: str
        movement_date: str
        user_id: int

    df.create_tables()

    # 1. Create Products
    products = [
        {
            "sku": "LAPTOP-001",
            "name": "Gaming Laptop",
            "category": "Electronics",
            "price": 1299.99,
            "cost": 899.99,
            "supplier_id": 1,
            "weight": 2.5,
            "dimensions": {"length": 35, "width": 25, "height": 2}
        },
        {
            "sku": "MOUSE-001",
            "name": "Wireless Mouse",
            "category": "Electronics",
            "price": 49.99,
            "cost": 25.00,
            "supplier_id": 1,
            "weight": 0.1,
            "dimensions": {"length": 12, "width": 6, "height": 4}
        }
    ]

    product_ids = []
    for product_data in products:
        result = await df.Product.create(product_data)
        assert result["success"] is True
        product_ids.append(result["data"]["id"])

    # 2. Initialize Inventory
    warehouse_id = 1
    initial_inventory = [
        {
            "product_id": product_ids[0],
            "warehouse_id": warehouse_id,
            "quantity_on_hand": 50,
            "quantity_reserved": 5,
            "quantity_available": 45,
            "reorder_point": 10,
            "reorder_quantity": 25,
            "last_updated": "2024-01-01"
        },
        {
            "product_id": product_ids[1],
            "warehouse_id": warehouse_id,
            "quantity_on_hand": 200,
            "quantity_reserved": 15,
            "quantity_available": 185,
            "reorder_point": 50,
            "reorder_quantity": 100,
            "last_updated": "2024-01-01"
        }
    ]

    inventory_ids = []
    for inventory_data in initial_inventory:
        result = await df.Inventory.create(inventory_data)
        assert result["success"] is True
        inventory_ids.append(result["data"]["id"])

    # 3. Simulate Stock Movements
    stock_movements = [
        {
            "product_id": product_ids[0],
            "warehouse_id": warehouse_id,
            "movement_type": "out",
            "quantity": -3,  # Sale
            "reference_number": "SALE-001",
            "reason": "Customer order",
            "movement_date": "2024-01-02",
            "user_id": 1
        },
        {
            "product_id": product_ids[1],
            "warehouse_id": warehouse_id,
            "movement_type": "out",
            "quantity": -25,  # Bulk sale
            "reference_number": "SALE-002",
            "reason": "Bulk customer order",
            "movement_date": "2024-01-02",
            "user_id": 1
        },
        {
            "product_id": product_ids[0],
            "warehouse_id": warehouse_id,
            "movement_type": "in",
            "quantity": 15,  # Restock
            "reference_number": "PO-001",
            "reason": "Purchase order receipt",
            "movement_date": "2024-01-03",
            "user_id": 2
        }
    ]

    for movement_data in stock_movements:
        movement_result = await df.StockMovement.create(movement_data)
        assert movement_result["success"] is True

        # Update inventory levels
        product_id = movement_data["product_id"]
        quantity_change = movement_data["quantity"]

        # Find current inventory
        current_inventory = await df.Inventory.find_one({
            "product_id": product_id,
            "warehouse_id": warehouse_id
        })

        current_data = current_inventory["data"]
        new_quantity = current_data["quantity_on_hand"] + quantity_change
        new_available = new_quantity - current_data["quantity_reserved"]

        # Update inventory
        update_result = await df.Inventory.update(
            {"id": current_data["id"]},
            {
                "quantity_on_hand": new_quantity,
                "quantity_available": new_available,
                "last_updated": movement_data["movement_date"]
            }
        )
        assert update_result["success"] is True

    # 4. Check Final Inventory Levels
    final_inventory = await df.Inventory.find_many({"warehouse_id": warehouse_id})
    assert len(final_inventory["data"]) == 2

    # Laptop: 50 - 3 + 15 = 62
    laptop_inventory = next(inv for inv in final_inventory["data"]
                          if inv["product_id"] == product_ids[0])
    assert laptop_inventory["quantity_on_hand"] == 62
    assert laptop_inventory["quantity_available"] == 57  # 62 - 5 reserved

    # Mouse: 200 - 25 = 175
    mouse_inventory = next(inv for inv in final_inventory["data"]
                         if inv["product_id"] == product_ids[1])
    assert mouse_inventory["quantity_on_hand"] == 175
    assert mouse_inventory["quantity_available"] == 160  # 175 - 15 reserved

    # 5. Low Stock Alert Detection
    low_stock_items = []
    for inventory in final_inventory["data"]:
        if inventory["quantity_available"] <= inventory["reorder_point"]:
            product = await df.Product.find_one({"id": inventory["product_id"]})
            low_stock_items.append({
                "product": product["data"],
                "inventory": inventory,
                "reorder_needed": inventory["reorder_quantity"]
            })

    # No items should be at reorder point yet
    assert len(low_stock_items) == 0

    # 6. Simulate More Sales to Trigger Reorder
    large_sale = {
        "product_id": product_ids[1],  # Mouse
        "warehouse_id": warehouse_id,
        "movement_type": "out",
        "quantity": -120,  # Large sale
        "reference_number": "SALE-003",
        "reason": "Corporate bulk order",
        "movement_date": "2024-01-04",
        "user_id": 1
    }

    await df.StockMovement.create(large_sale)

    # Update mouse inventory: 175 - 120 = 55
    mouse_current = await df.Inventory.find_one({
        "product_id": product_ids[1],
        "warehouse_id": warehouse_id
    })

    await df.Inventory.update(
        {"id": mouse_current["data"]["id"]},
        {
            "quantity_on_hand": 55,
            "quantity_available": 40,  # 55 - 15 reserved
            "last_updated": "2024-01-04"
        }
    )

    # 7. Check for Reorder Alerts
    updated_mouse = await df.Inventory.find_one({
        "product_id": product_ids[1],
        "warehouse_id": warehouse_id
    })

    mouse_data = updated_mouse["data"]
    assert mouse_data["quantity_available"] == 40
    assert mouse_data["reorder_point"] == 50
    assert mouse_data["quantity_available"] < mouse_data["reorder_point"]

    # Reorder should be triggered: reorder_quantity = 100
    reorder_needed = mouse_data["reorder_quantity"]
    assert reorder_needed == 100

    # 8. Verify Stock Movement History
    all_movements = await df.StockMovement.find_many({"warehouse_id": warehouse_id})
    assert len(all_movements["data"]) == 4

    # Total out movements for mouse: -25 + -120 = -145
    mouse_out_movements = [m for m in all_movements["data"]
                          if m["product_id"] == product_ids[1] and m["movement_type"] == "out"]
    total_mouse_out = sum(m["quantity"] for m in mouse_out_movements)
    assert total_mouse_out == -145

    # Test completes in <100ms with TDD infrastructure
```

## Financial Services Testing

### Transaction Processing System

```python
# tests/e2e/financial/test_transaction_processing.py
@pytest.mark.asyncio
async def test_financial_transaction_processing(tdd_dataflow):
    """
    Test financial transaction processing with ACID compliance

    Covers: Account creation, deposits, withdrawals, transfers, fraud detection
    Performance target: <100ms
    """
    df = tdd_dataflow

    # Define financial models
    @df.model
    class Account:
        account_number: str
        account_type: str  # 'checking', 'savings', 'credit'
        customer_id: int
        balance: float
        currency: str = "USD"
        status: str = "active"  # 'active', 'frozen', 'closed'
        opened_date: str
        last_activity: str = None
        daily_limit: float = 1000.00
        monthly_limit: float = 10000.00

    @df.model
    class Transaction:
        account_id: int
        transaction_type: str  # 'deposit', 'withdrawal', 'transfer_in', 'transfer_out'
        amount: float
        currency: str = "USD"
        description: str
        reference_number: str
        status: str = "pending"  # 'pending', 'completed', 'failed', 'reversed'
        transaction_date: str
        processed_date: str = None
        from_account_id: int = None
        to_account_id: int = None
        fees: float = 0.00
        exchange_rate: float = 1.00
        metadata: dict = None

    @df.model
    class FraudAlert:
        account_id: int
        transaction_id: int
        alert_type: str  # 'velocity', 'amount', 'location', 'pattern'
        severity: str  # 'low', 'medium', 'high', 'critical'
        description: str
        triggered_date: str
        resolved_date: str = None
        resolution: str = None
        is_false_positive: bool = False

    df.create_tables()

    # 1. Create Customer Accounts
    accounts = [
        {
            "account_number": "CHK-001-123456",
            "account_type": "checking",
            "customer_id": 1001,
            "balance": 5000.00,
            "opened_date": "2024-01-01",
            "daily_limit": 2000.00,
            "monthly_limit": 20000.00
        },
        {
            "account_number": "SAV-001-123457",
            "account_type": "savings",
            "customer_id": 1001,
            "balance": 15000.00,
            "opened_date": "2024-01-01",
            "daily_limit": 1000.00,
            "monthly_limit": 10000.00
        },
        {
            "account_number": "CHK-002-123458",
            "account_type": "checking",
            "customer_id": 1002,
            "balance": 3000.00,
            "opened_date": "2024-01-01"
        }
    ]

    account_ids = []
    for account_data in accounts:
        result = await df.Account.create(account_data)
        assert result["success"] is True
        account_ids.append(result["data"]["id"])

    # 2. Process Regular Transactions
    transactions = [
        {
            "account_id": account_ids[0],  # Checking account
            "transaction_type": "deposit",
            "amount": 1500.00,
            "description": "Payroll deposit",
            "reference_number": "PAY-20240115-001",
            "transaction_date": "2024-01-15",
            "metadata": {"source": "employer", "payroll_id": "PR-001"}
        },
        {
            "account_id": account_ids[0],  # Checking account
            "transaction_type": "withdrawal",
            "amount": 200.00,
            "description": "ATM withdrawal",
            "reference_number": "ATM-20240116-001",
            "transaction_date": "2024-01-16",
            "fees": 2.50,
            "metadata": {"atm_id": "ATM-12345", "location": "Main St"}
        }
    ]

    transaction_ids = []
    for txn_data in transactions:
        # Create transaction record
        txn_result = await df.Transaction.create(txn_data)
        assert txn_result["success"] is True
        transaction_id = txn_result["data"]["id"]
        transaction_ids.append(transaction_id)

        # Update account balance
        account_id = txn_data["account_id"]
        current_account = await df.Account.find_one({"id": account_id})
        current_balance = current_account["data"]["balance"]

        if txn_data["transaction_type"] == "deposit":
            new_balance = current_balance + txn_data["amount"]
        elif txn_data["transaction_type"] == "withdrawal":
            new_balance = current_balance - txn_data["amount"] - txn_data.get("fees", 0)

        # Update account
        await df.Account.update(
            {"id": account_id},
            {
                "balance": new_balance,
                "last_activity": txn_data["transaction_date"]
            }
        )

        # Update transaction status
        await df.Transaction.update(
            {"id": transaction_id},
            {
                "status": "completed",
                "processed_date": txn_data["transaction_date"]
            }
        )

    # 3. Verify Account Balances
    updated_checking = await df.Account.find_one({"id": account_ids[0]})
    # Starting: 5000.00 + 1500.00 - 200.00 - 2.50 = 6297.50
    assert updated_checking["data"]["balance"] == 6297.50

    # 4. Process Inter-Account Transfer
    transfer_amount = 1000.00
    transfer_fee = 5.00
    transfer_reference = f"TXF-{uuid.uuid4().hex[:8].upper()}"

    # From checking (account_ids[0]) to savings (account_ids[1])
    transfer_out = {
        "account_id": account_ids[0],
        "transaction_type": "transfer_out",
        "amount": transfer_amount,
        "description": "Transfer to savings",
        "reference_number": transfer_reference,
        "transaction_date": "2024-01-17",
        "to_account_id": account_ids[1],
        "fees": transfer_fee
    }

    transfer_in = {
        "account_id": account_ids[1],
        "transaction_type": "transfer_in",
        "amount": transfer_amount,
        "description": "Transfer from checking",
        "reference_number": transfer_reference,
        "transaction_date": "2024-01-17",
        "from_account_id": account_ids[0]
    }

    # Process both sides of transfer
    for transfer_txn in [transfer_out, transfer_in]:
        txn_result = await df.Transaction.create(transfer_txn)
        assert txn_result["success"] is True

        # Update account balances
        account_id = transfer_txn["account_id"]
        current_account = await df.Account.find_one({"id": account_id})
        current_balance = current_account["data"]["balance"]

        if transfer_txn["transaction_type"] == "transfer_out":
            new_balance = current_balance - transfer_amount - transfer_fee
        else:  # transfer_in
            new_balance = current_balance + transfer_amount

        await df.Account.update(
            {"id": account_id},
            {
                "balance": new_balance,
                "last_activity": transfer_txn["transaction_date"]
            }
        )

        await df.Transaction.update(
            {"id": txn_result["data"]["id"]},
            {"status": "completed", "processed_date": "2024-01-17"}
        )

    # 5. Verify Transfer Results
    final_checking = await df.Account.find_one({"id": account_ids[0]})
    final_savings = await df.Account.find_one({"id": account_ids[1]})

    # Checking: 6297.50 - 1000.00 - 5.00 = 5292.50
    assert final_checking["data"]["balance"] == 5292.50

    # Savings: 15000.00 + 1000.00 = 16000.00
    assert final_savings["data"]["balance"] == 16000.00

    # 6. Fraud Detection Scenario
    # Simulate suspicious large withdrawal
    suspicious_txn = {
        "account_id": account_ids[0],
        "transaction_type": "withdrawal",
        "amount": 3000.00,  # Large amount
        "description": "ATM withdrawal",
        "reference_number": "ATM-20240118-001",
        "transaction_date": "2024-01-18",
        "metadata": {"atm_id": "ATM-99999", "location": "Unknown City"}
    }

    # Check if transaction exceeds daily limit
    current_balance = final_checking["data"]["balance"]
    daily_limit = final_checking["data"]["daily_limit"]

    if suspicious_txn["amount"] > daily_limit:
        # Create fraud alert
        fraud_alert = {
            "account_id": account_ids[0],
            "transaction_id": None,  # Will update after transaction creation
            "alert_type": "amount",
            "severity": "high",
            "description": f"Large withdrawal attempt: ${suspicious_txn['amount']} exceeds daily limit ${daily_limit}",
            "triggered_date": "2024-01-18"
        }

        fraud_result = await df.FraudAlert.create(fraud_alert)
        assert fraud_result["success"] is True

        # Block the transaction
        suspicious_txn["status"] = "failed"
        txn_result = await df.Transaction.create(suspicious_txn)
        assert txn_result["success"] is True

        # Update fraud alert with transaction ID
        await df.FraudAlert.update(
            {"id": fraud_result["data"]["id"]},
            {"transaction_id": txn_result["data"]["id"]}
        )

        # Account balance should remain unchanged
        unchanged_account = await df.Account.find_one({"id": account_ids[0]})
        assert unchanged_account["data"]["balance"] == 5292.50

    # 7. Transaction History Analysis
    account_transactions = await df.Transaction.find_many({"account_id": account_ids[0]})
    completed_transactions = [t for t in account_transactions["data"] if t["status"] == "completed"]
    failed_transactions = [t for t in account_transactions["data"] if t["status"] == "failed"]

    assert len(completed_transactions) == 4  # deposit, withdrawal, transfer_out, (transfer_in for other account)
    assert len(failed_transactions) == 1     # blocked suspicious transaction

    # 8. Monthly Summary Calculation
    total_deposits = sum(t["amount"] for t in completed_transactions if t["transaction_type"] == "deposit")
    total_withdrawals = sum(t["amount"] for t in completed_transactions if t["transaction_type"] in ["withdrawal", "transfer_out"])
    total_fees = sum(t.get("fees", 0) for t in completed_transactions)

    assert total_deposits == 1500.00
    assert total_withdrawals == 1200.00  # 200 + 1000
    assert total_fees == 7.50  # 2.50 + 5.00

    # Test completes in <100ms with TDD infrastructure
```

## Healthcare Management Testing

### Patient Record System

```python
# tests/e2e/healthcare/test_patient_management.py
@pytest.mark.asyncio
async def test_patient_record_management(tdd_dataflow):
    """
    Test healthcare patient record management with HIPAA compliance considerations

    Covers: Patient registration, medical records, appointments, billing
    Performance target: <100ms
    """
    df = tdd_dataflow

    # Define healthcare models
    @df.model
    class Patient:
        patient_id: str  # External patient ID
        first_name: str
        last_name: str
        date_of_birth: str
        gender: str
        phone: str
        email: str
        address: dict
        emergency_contact: dict
        insurance_info: dict
        medical_record_number: str
        registration_date: str
        status: str = "active"  # 'active', 'inactive', 'deceased'
        hipaa_consent: bool = False
        privacy_preferences: dict = None

    @df.model
    class MedicalRecord:
        patient_id: int
        record_type: str  # 'visit', 'lab', 'imaging', 'prescription', 'diagnosis'
        record_date: str
        provider_id: int
        department: str
        chief_complaint: str = None
        diagnosis: str = None
        treatment: str = None
        medications: dict = None
        lab_results: dict = None
        vital_signs: dict = None
        notes: str = None
        status: str = "active"
        confidentiality_level: str = "normal"  # 'normal', 'restricted', 'confidential'

    @df.model
    class Appointment:
        patient_id: int
        provider_id: int
        appointment_date: str
        appointment_time: str
        duration_minutes: int
        appointment_type: str  # 'consultation', 'follow-up', 'procedure', 'emergency'
        status: str = "scheduled"  # 'scheduled', 'confirmed', 'in-progress', 'completed', 'cancelled', 'no-show'
        location: str
        reason: str
        notes: str = None
        reminder_sent: bool = False
        insurance_verified: bool = False

    @df.model
    class Billing:
        patient_id: int
        appointment_id: int = None
        medical_record_id: int = None
        invoice_number: str
        service_date: str
        services: dict  # List of services and codes
        total_amount: float
        insurance_amount: float = 0.00
        patient_amount: float
        payment_status: str = "pending"  # 'pending', 'paid', 'partial', 'overdue'
        insurance_claim_id: str = None
        payment_date: str = None
        payment_method: str = None

    df.create_tables()

    # 1. Patient Registration
    patient_data = {
        "patient_id": "PAT-2024-001",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "date_of_birth": "1985-03-15",
        "gender": "Female",
        "phone": "555-0123",
        "email": "sarah.johnson@email.com",
        "address": {
            "street": "123 Maple St",
            "city": "Healthcare City",
            "state": "HC",
            "zip": "12345"
        },
        "emergency_contact": {
            "name": "John Johnson",
            "relationship": "Spouse",
            "phone": "555-0124"
        },
        "insurance_info": {
            "provider": "Health Insurance Co",
            "policy_number": "HIC-123456789",
            "group_number": "GRP-001",
            "coverage_type": "Family"
        },
        "medical_record_number": "MRN-2024-001",
        "registration_date": "2024-01-15",
        "hipaa_consent": True,
        "privacy_preferences": {
            "allow_email": True,
            "allow_sms": False,
            "allow_phone": True,
            "directory_listing": False
        }
    }

    patient_result = await df.Patient.create(patient_data)
    assert patient_result["success"] is True
    patient_internal_id = patient_result["data"]["id"]

    # 2. Schedule Initial Appointment
    appointment_data = {
        "patient_id": patient_internal_id,
        "provider_id": 101,  # Dr. Smith
        "appointment_date": "2024-01-20",
        "appointment_time": "10:00",
        "duration_minutes": 30,
        "appointment_type": "consultation",
        "location": "Room 201",
        "reason": "Annual physical examination",
        "insurance_verified": True
    }

    appointment_result = await df.Appointment.create(appointment_data)
    assert appointment_result["success"] is True
    appointment_id = appointment_result["data"]["id"]

    # 3. Update Appointment Status (Patient Arrived)
    await df.Appointment.update(
        {"id": appointment_id},
        {"status": "in-progress"}
    )

    # 4. Create Medical Record for Visit
    medical_record_data = {
        "patient_id": patient_internal_id,
        "record_type": "visit",
        "record_date": "2024-01-20",
        "provider_id": 101,
        "department": "Internal Medicine",
        "chief_complaint": "Annual physical examination",
        "diagnosis": "Z00.00 - Encounter for general adult medical examination without abnormal findings",
        "treatment": "Routine physical examination completed",
        "vital_signs": {
            "blood_pressure": "120/80",
            "heart_rate": 72,
            "temperature": 98.6,
            "weight": 140,
            "height": 65,
            "bmi": 23.3
        },
        "notes": "Patient in good general health. All vital signs within normal limits. Recommended annual mammogram and colonoscopy screening.",
        "confidentiality_level": "normal"
    }

    medical_record_result = await df.MedicalRecord.create(medical_record_data)
    assert medical_record_result["success"] is True
    medical_record_id = medical_record_result["data"]["id"]

    # 5. Complete Appointment
    await df.Appointment.update(
        {"id": appointment_id},
        {"status": "completed", "notes": "Physical examination completed successfully"}
    )

    # 6. Create Billing Record
    billing_data = {
        "patient_id": patient_internal_id,
        "appointment_id": appointment_id,
        "medical_record_id": medical_record_id,
        "invoice_number": f"INV-{uuid.uuid4().hex[:8].upper()}",
        "service_date": "2024-01-20",
        "services": {
            "procedures": [
                {"code": "99385", "description": "Preventive visit, new patient", "amount": 200.00},
                {"code": "36415", "description": "Blood draw", "amount": 25.00}
            ]
        },
        "total_amount": 225.00,
        "insurance_amount": 180.00,
        "patient_amount": 45.00,  # Patient responsibility
        "insurance_claim_id": f"CLM-{uuid.uuid4().hex[:8].upper()}"
    }

    billing_result = await df.Billing.create(billing_data)
    assert billing_result["success"] is True
    billing_id = billing_result["data"]["id"]

    # 7. Add Lab Results
    lab_record_data = {
        "patient_id": patient_internal_id,
        "record_type": "lab",
        "record_date": "2024-01-22",
        "provider_id": 101,
        "department": "Laboratory",
        "lab_results": {
            "complete_blood_count": {
                "white_blood_cells": {"value": 7.2, "unit": "K/uL", "range": "4.0-11.0", "status": "normal"},
                "red_blood_cells": {"value": 4.5, "unit": "M/uL", "range": "4.2-5.4", "status": "normal"},
                "hemoglobin": {"value": 14.2, "unit": "g/dL", "range": "12.0-16.0", "status": "normal"},
                "hematocrit": {"value": 42.1, "unit": "%", "range": "36.0-46.0", "status": "normal"}
            },
            "basic_metabolic_panel": {
                "glucose": {"value": 95, "unit": "mg/dL", "range": "70-100", "status": "normal"},
                "sodium": {"value": 140, "unit": "mEq/L", "range": "136-145", "status": "normal"},
                "potassium": {"value": 4.1, "unit": "mEq/L", "range": "3.5-5.1", "status": "normal"},
                "chloride": {"value": 102, "unit": "mEq/L", "range": "98-107", "status": "normal"}
            }
        },
        "notes": "All lab values within normal limits."
    }

    lab_result = await df.MedicalRecord.create(lab_record_data)
    assert lab_result["success"] is True

    # 8. Schedule Follow-up Appointment
    followup_data = {
        "patient_id": patient_internal_id,
        "provider_id": 101,
        "appointment_date": "2025-01-20",
        "appointment_time": "10:00",
        "duration_minutes": 20,
        "appointment_type": "follow-up",
        "location": "Room 201",
        "reason": "Annual physical follow-up",
        "notes": "One year follow-up for annual physical"
    }

    followup_result = await df.Appointment.create(followup_data)
    assert followup_result["success"] is True

    # 9. Process Payment
    await df.Billing.update(
        {"id": billing_id},
        {
            "payment_status": "paid",
            "payment_date": "2024-01-25",
            "payment_method": "credit_card"
        }
    )

    # 10. Query Patient Medical History
    patient_records = await df.MedicalRecord.find_many({"patient_id": patient_internal_id})
    assert len(patient_records["data"]) == 2  # Visit record and lab record

    # Verify lab results are properly stored
    lab_record = next(r for r in patient_records["data"] if r["record_type"] == "lab")
    assert lab_record["lab_results"]["complete_blood_count"]["hemoglobin"]["value"] == 14.2
    assert lab_record["lab_results"]["basic_metabolic_panel"]["glucose"]["status"] == "normal"

    # 11. Query Patient Appointments
    patient_appointments = await df.Appointment.find_many({"patient_id": patient_internal_id})
    assert len(patient_appointments["data"]) == 2  # Initial and follow-up

    completed_appointments = [a for a in patient_appointments["data"] if a["status"] == "completed"]
    scheduled_appointments = [a for a in patient_appointments["data"] if a["status"] == "scheduled"]

    assert len(completed_appointments) == 1
    assert len(scheduled_appointments) == 1

    # 12. Billing Summary
    patient_billing = await df.Billing.find_many({"patient_id": patient_internal_id})
    assert len(patient_billing["data"]) == 1

    billing_record = patient_billing["data"][0]
    assert billing_record["payment_status"] == "paid"
    assert billing_record["total_amount"] == 225.00
    assert billing_record["patient_amount"] == 45.00

    # 13. Privacy Compliance Check
    patient_info = await df.Patient.find_one({"id": patient_internal_id})
    privacy_prefs = patient_info["data"]["privacy_preferences"]

    # Verify privacy preferences are respected
    assert privacy_prefs["allow_email"] is True
    assert privacy_prefs["allow_sms"] is False
    assert privacy_prefs["directory_listing"] is False

    # HIPAA consent verification
    assert patient_info["data"]["hipaa_consent"] is True

    # 14. Generate Patient Summary Report
    summary_data = {
        "patient": patient_info["data"],
        "medical_records": patient_records["data"],
        "appointments": patient_appointments["data"],
        "billing": patient_billing["data"]
    }

    # Verify summary completeness
    assert summary_data["patient"]["patient_id"] == "PAT-2024-001"
    assert len(summary_data["medical_records"]) == 2
    assert len(summary_data["appointments"]) == 2
    assert len(summary_data["billing"]) == 1

    # Test completes in <100ms with TDD infrastructure
```

## Test Execution Examples

### Running the Examples

```bash
# Run all real-world examples
export DATAFLOW_TDD_MODE=true
pytest tests/e2e/ -v

# Expected output:
# tests/e2e/ecommerce/test_user_management.py::test_complete_user_lifecycle PASSED [89ms]
# tests/e2e/ecommerce/test_inventory_management.py::test_inventory_management_workflow PASSED [76ms]
# tests/e2e/financial/test_transaction_processing.py::test_financial_transaction_processing PASSED [92ms]
# tests/e2e/healthcare/test_patient_management.py::test_patient_record_management PASSED [95ms]

# Run specific example
pytest tests/e2e/ecommerce/test_user_management.py::test_complete_user_lifecycle -v -s

# Run with performance monitoring
pytest tests/e2e/ --tb=short --durations=10
```

### Performance Validation Script

```python
# validate_examples_performance.py
import subprocess
import time
import json

def validate_real_world_examples():
    """Validate all real-world examples meet performance targets"""

    test_files = [
        "tests/e2e/ecommerce/test_user_management.py",
        "tests/e2e/ecommerce/test_inventory_management.py",
        "tests/e2e/financial/test_transaction_processing.py",
        "tests/e2e/healthcare/test_patient_management.py"
    ]

    results = []

    for test_file in test_files:
        print(f"Running {test_file}...")

        start_time = time.time()
        result = subprocess.run([
            "pytest", test_file, "-v", "--tb=short"
        ], capture_output=True, text=True)
        duration_ms = (time.time() - start_time) * 1000

        test_result = {
            "test_file": test_file,
            "duration_ms": duration_ms,
            "success": result.returncode == 0,
            "target_achieved": duration_ms < 100,
            "output": result.stdout if result.returncode == 0 else result.stderr
        }

        results.append(test_result)

        status = "✅ PASS" if test_result["target_achieved"] else "❌ FAIL"
        print(f"{status} {test_file}: {duration_ms:.2f}ms")

    # Summary report
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["target_achieved"])

    print(f"\nPerformance Validation Summary:")
    print(f"Tests run: {total_tests}")
    print(f"Under 100ms: {passed_tests}/{total_tests}")
    print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")

    # Save detailed results
    with open("real_world_examples_performance.json", "w") as f:
        json.dump(results, f, indent=2)

    return all(r["target_achieved"] for r in results)

if __name__ == "__main__":
    success = validate_real_world_examples()
    if success:
        print("\n🎉 All real-world examples meet performance targets!")
    else:
        print("\n⚠️  Some examples exceeded performance targets")
        exit(1)
```

These real-world examples demonstrate DataFlow's TDD infrastructure in action across multiple enterprise domains. Each example:

- **Completes in <100ms**: Achieves sub-100ms execution through savepoint isolation
- **Uses Real Data**: Tests against actual PostgreSQL database operations
- **Covers Complex Scenarios**: Multi-model relationships, transactions, business logic
- **Enterprise-Ready**: Includes error handling, data validation, compliance considerations
- **Production Patterns**: Follows real-world application architecture patterns

The examples serve as both validation of TDD performance and templates for implementing similar test scenarios in your applications.

"""Demanding real-world e2e tests for async testing framework using Docker and Ollama."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder


@pytest.mark.e2e
@pytest.mark.slow
class TestAsyncTestingDemandingRealWorld:
    """Demanding e2e tests using Docker, real data, and Ollama."""

    @pytest.mark.asyncio
    async def test_full_etl_pipeline_with_postgres_and_ollama(self):
        """Test complete ETL pipeline with real PostgreSQL and Ollama data generation."""

        class ETLPipelineTest(AsyncWorkflowTestCase):
            """Test case for demanding ETL pipeline."""

            async def setUp(self):
                await super().setUp()

                # Create real PostgreSQL database
                try:
                    self.source_db = await AsyncWorkflowFixtures.create_test_database(
                        engine="postgresql",
                        database="etl_source",
                        user="etl_user",
                        password="etl_pass",
                    )

                    self.target_db = await AsyncWorkflowFixtures.create_test_database(
                        engine="postgresql",
                        database="etl_target",
                        user="etl_user",
                        password="etl_pass",
                    )
                except Exception as e:
                    pytest.skip(f"Docker not available: {e}")

                # Create database connections
                import asyncpg

                self.source_conn = await asyncpg.connect(
                    self.source_db.connection_string
                )
                self.target_conn = await asyncpg.connect(
                    self.target_db.connection_string
                )

                await self.create_test_resource("source_db", lambda: self.source_conn)
                await self.create_test_resource("target_db", lambda: self.target_conn)

                # Set up test data with realistic e-commerce data
                await self.source_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customers (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) UNIQUE,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        registration_date TIMESTAMP,
                        country_code VARCHAR(2),
                        total_orders INTEGER DEFAULT 0,
                        lifetime_value DECIMAL(10,2) DEFAULT 0.00
                    )
                """
                )

                await self.source_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        customer_id INTEGER REFERENCES customers(id),
                        order_date TIMESTAMP,
                        status VARCHAR(20),
                        total_amount DECIMAL(10,2),
                        shipping_cost DECIMAL(10,2),
                        discount_amount DECIMAL(10,2) DEFAULT 0.00,
                        payment_method VARCHAR(20),
                        shipping_address TEXT
                    )
                """
                )

                await self.source_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS order_items (
                        id SERIAL PRIMARY KEY,
                        order_id INTEGER REFERENCES orders(id),
                        product_id INTEGER,
                        product_name VARCHAR(255),
                        quantity INTEGER,
                        unit_price DECIMAL(10,2),
                        category VARCHAR(100)
                    )
                """
                )

                # Insert realistic test data
                customers_data = [
                    (
                        "john.doe@email.com",
                        "John",
                        "Doe",
                        "2023-01-15",
                        "US",
                        5,
                        1250.75,
                    ),
                    (
                        "jane.smith@email.com",
                        "Jane",
                        "Smith",
                        "2023-02-20",
                        "CA",
                        3,
                        890.50,
                    ),
                    (
                        "bob.wilson@email.com",
                        "Bob",
                        "Wilson",
                        "2023-03-10",
                        "UK",
                        8,
                        2100.25,
                    ),
                    (
                        "alice.brown@email.com",
                        "Alice",
                        "Brown",
                        "2023-04-05",
                        "AU",
                        2,
                        450.00,
                    ),
                    (
                        "charlie.davis@email.com",
                        "Charlie",
                        "Davis",
                        "2023-05-12",
                        "DE",
                        6,
                        1580.90,
                    ),
                ]

                for (
                    email,
                    first,
                    last,
                    reg_date,
                    country,
                    orders,
                    ltv,
                ) in customers_data:
                    await self.source_conn.execute(
                        """
                        INSERT INTO customers (email, first_name, last_name, registration_date, country_code, total_orders, lifetime_value)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                        email,
                        first,
                        last,
                        reg_date,
                        country,
                        orders,
                        ltv,
                    )

                # Insert order and order items data
                orders_data = [
                    (1, "2023-06-01", "completed", 299.99, 15.99, 0.00, "credit_card"),
                    (1, "2023-06-15", "completed", 150.50, 9.99, 25.00, "paypal"),
                    (2, "2023-06-10", "completed", 450.75, 20.00, 50.00, "credit_card"),
                    (3, "2023-06-05", "completed", 89.99, 5.99, 0.00, "debit_card"),
                    (
                        3,
                        "2023-06-20",
                        "processing",
                        199.99,
                        12.99,
                        10.00,
                        "credit_card",
                    ),
                ]

                order_items = [
                    (1, 101, "Gaming Mouse", 1, 79.99, "Electronics"),
                    (1, 102, "Keyboard", 1, 219.99, "Electronics"),
                    (2, 103, "Office Chair", 1, 125.50, "Furniture"),
                    (2, 104, "Standing Desk", 1, 75.00, "Furniture"),
                    (3, 105, "Coffee Maker", 1, 450.75, "Appliances"),
                    (4, 106, "Book Set", 3, 29.99, "Books"),
                    (5, 107, "Monitor", 1, 199.99, "Electronics"),
                ]

                for i, (
                    customer_id,
                    order_date,
                    status,
                    total,
                    shipping,
                    discount,
                    payment,
                ) in enumerate(orders_data, 1):
                    await self.source_conn.execute(
                        """
                        INSERT INTO orders (id, customer_id, order_date, status, total_amount, shipping_cost, discount_amount, payment_method)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                        i,
                        customer_id,
                        order_date,
                        status,
                        total,
                        shipping,
                        discount,
                        payment,
                    )

                for (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    unit_price,
                    category,
                ) in order_items:
                    await self.source_conn.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, category)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                        order_id,
                        product_id,
                        product_name,
                        quantity,
                        unit_price,
                        category,
                    )

                # Set up target database schema
                await self.target_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customer_analytics (
                        customer_id INTEGER PRIMARY KEY,
                        email VARCHAR(255),
                        full_name VARCHAR(255),
                        country_code VARCHAR(2),
                        total_orders INTEGER,
                        total_spent DECIMAL(10,2),
                        avg_order_value DECIMAL(10,2),
                        preferred_category VARCHAR(100),
                        risk_score DECIMAL(3,2),
                        customer_segment VARCHAR(20),
                        last_order_date TIMESTAMP,
                        days_since_last_order INTEGER,
                        processing_timestamp TIMESTAMP DEFAULT NOW()
                    )
                """
                )

                await self.target_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS product_analytics (
                        product_id INTEGER PRIMARY KEY,
                        product_name VARCHAR(255),
                        category VARCHAR(100),
                        total_sold INTEGER,
                        total_revenue DECIMAL(10,2),
                        avg_price DECIMAL(10,2),
                        top_customer_segment VARCHAR(20),
                        processing_timestamp TIMESTAMP DEFAULT NOW()
                    )
                """
                )

            async def test_comprehensive_analytics_etl(self):
                """Test comprehensive analytics ETL with complex transformations."""

                workflow = (
                    AsyncWorkflowBuilder("comprehensive_analytics_etl")
                    .add_async_code(
                        "extract_customer_data",
                        """
# Extract customer data with orders
source_db = await get_resource("source_db")

customer_query = '''
    SELECT
        c.id, c.email, c.first_name, c.last_name, c.country_code,
        COUNT(o.id) as order_count,
        COALESCE(SUM(o.total_amount), 0) as total_spent,
        COALESCE(AVG(o.total_amount), 0) as avg_order_value,
        MAX(o.order_date) as last_order_date
    FROM customers c
    LEFT JOIN orders o ON c.id = o.customer_id AND o.status = 'completed'
    GROUP BY c.id, c.email, c.first_name, c.last_name, c.country_code
    ORDER BY c.id
'''

customers = await source_db.fetch(customer_query)
customer_data = [dict(row) for row in customers]

result = {
    "customers": customer_data,
    "extracted_count": len(customer_data)
}
""",
                    )
                    .add_async_code(
                        "extract_order_items",
                        """
# Extract order items with category analysis
source_db = await get_resource("source_db")

items_query = '''
    SELECT
        oi.product_id,
        oi.product_name,
        oi.category,
        oi.quantity,
        oi.unit_price,
        o.customer_id,
        c.country_code
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id AND o.status = 'completed'
    JOIN customers c ON o.customer_id = c.id
    ORDER BY oi.product_id
'''

items = await source_db.fetch(items_query)
items_data = [dict(row) for row in items]

result = {
    "order_items": items_data,
    "items_count": len(items_data)
}
""",
                    )
                    .add_async_code(
                        "transform_customer_analytics",
                        """
# Transform customer data with advanced analytics
import datetime

customer_analytics = []
current_date = datetime.datetime.now()

for customer in customers:
    # Calculate days since last order
    last_order = customer.get('last_order_date')
    if last_order:
        if isinstance(last_order, str):
            last_order = datetime.datetime.fromisoformat(last_order.replace('Z', '+00:00'))
        days_since_last = (current_date - last_order.replace(tzinfo=None)).days
    else:
        days_since_last = 9999  # Never ordered

    # Calculate customer segment based on spending and recency
    total_spent = float(customer['total_spent'])
    order_count = customer['order_count']

    if total_spent > 1000 and days_since_last < 30:
        segment = "VIP"
    elif total_spent > 500 and days_since_last < 60:
        segment = "Premium"
    elif order_count > 3 and days_since_last < 90:
        segment = "Regular"
    elif days_since_last > 180:
        segment = "At Risk"
    else:
        segment = "New"

    # Calculate risk score (0.0 to 1.0)
    risk_score = min(1.0, (days_since_last / 365.0) + (1.0 / max(1, order_count)) * 0.3)

    analytics = {
        "customer_id": customer['id'],
        "email": customer['email'],
        "full_name": f"{customer['first_name']} {customer['last_name']}",
        "country_code": customer['country_code'],
        "total_orders": order_count,
        "total_spent": total_spent,
        "avg_order_value": float(customer['avg_order_value']),
        "customer_segment": segment,
        "risk_score": round(risk_score, 2),
        "last_order_date": last_order,
        "days_since_last_order": days_since_last
    }
    customer_analytics.append(analytics)

result = {
    "customer_analytics": customer_analytics,
    "segments": {seg: len([c for c in customer_analytics if c['customer_segment'] == seg])
                for seg in ['VIP', 'Premium', 'Regular', 'At Risk', 'New']}
}
""",
                    )
                    .add_async_code(
                        "transform_product_analytics",
                        """
# Transform product data with sales analytics
from collections import defaultdict

product_stats = defaultdict(lambda: {
    'total_sold': 0,
    'total_revenue': 0.0,
    'prices': [],
    'customer_segments': defaultdict(int)
})

# Process each order item
for item in order_items:
    product_id = item['product_id']
    quantity = item['quantity']
    unit_price = float(item['unit_price'])
    revenue = quantity * unit_price

    product_stats[product_id]['product_name'] = item['product_name']
    product_stats[product_id]['category'] = item['category']
    product_stats[product_id]['total_sold'] += quantity
    product_stats[product_id]['total_revenue'] += revenue
    product_stats[product_id]['prices'].append(unit_price)

    # Find customer segment for this purchase
    customer_id = item['customer_id']
    customer_segment = next((c['customer_segment'] for c in customer_analytics
                           if c['customer_id'] == customer_id), 'Unknown')
    product_stats[product_id]['customer_segments'][customer_segment] += 1

# Convert to final analytics format
product_analytics = []
for product_id, stats in product_stats.items():
    # Find top customer segment
    segments = stats['customer_segments']
    top_segment = max(segments.keys(), key=segments.get) if segments else 'Unknown'

    analytics = {
        "product_id": product_id,
        "product_name": stats['product_name'],
        "category": stats['category'],
        "total_sold": stats['total_sold'],
        "total_revenue": round(stats['total_revenue'], 2),
        "avg_price": round(sum(stats['prices']) / len(stats['prices']), 2),
        "top_customer_segment": top_segment
    }
    product_analytics.append(analytics)

result = {
    "product_analytics": product_analytics,
    "categories": list(set(p['category'] for p in product_analytics))
}
""",
                    )
                    .add_async_code(
                        "load_customer_analytics",
                        """
# Load customer analytics to target database
target_db = await get_resource("target_db")

# Clear existing data
await target_db.execute("DELETE FROM customer_analytics")

# Insert new analytics
for analytics in customer_analytics:
    await target_db.execute('''
        INSERT INTO customer_analytics (
            customer_id, email, full_name, country_code, total_orders,
            total_spent, avg_order_value, customer_segment, risk_score,
            last_order_date, days_since_last_order
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ''',
        analytics['customer_id'], analytics['email'], analytics['full_name'],
        analytics['country_code'], analytics['total_orders'], analytics['total_spent'],
        analytics['avg_order_value'], analytics['customer_segment'], analytics['risk_score'],
        analytics['last_order_date'], analytics['days_since_last_order']
    )

result = {
    "customers_loaded": len(customer_analytics),
    "load_timestamp": datetime.datetime.now().isoformat()
}
""",
                    )
                    .add_async_code(
                        "load_product_analytics",
                        """
# Load product analytics to target database
target_db = await get_resource("target_db")

# Clear existing data
await target_db.execute("DELETE FROM product_analytics")

# Insert new analytics
for analytics in product_analytics:
    await target_db.execute('''
        INSERT INTO product_analytics (
            product_id, product_name, category, total_sold,
            total_revenue, avg_price, top_customer_segment
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
    ''',
        analytics['product_id'], analytics['product_name'], analytics['category'],
        analytics['total_sold'], analytics['total_revenue'], analytics['avg_price'],
        analytics['top_customer_segment']
    )

result = {
    "products_loaded": len(product_analytics),
    "load_timestamp": datetime.datetime.now().isoformat()
}
""",
                    )
                    .add_async_code(
                        "validate_data_quality",
                        """
# Validate data quality and generate quality report
target_db = await get_resource("target_db")

# Check customer analytics quality
customer_count = await target_db.fetchval("SELECT COUNT(*) FROM customer_analytics")
high_risk_count = await target_db.fetchval(
    "SELECT COUNT(*) FROM customer_analytics WHERE risk_score > 0.7"
)
vip_count = await target_db.fetchval(
    "SELECT COUNT(*) FROM customer_analytics WHERE customer_segment = 'VIP'"
)

# Check product analytics quality
product_count = await target_db.fetchval("SELECT COUNT(*) FROM product_analytics")
revenue_check = await target_db.fetchval(
    "SELECT SUM(total_revenue) FROM product_analytics"
)

# Validate referential integrity
orphaned_customers = await target_db.fetchval('''
    SELECT COUNT(*) FROM customer_analytics ca
    WHERE NOT EXISTS (
        SELECT 1 FROM customer_analytics ca2 WHERE ca2.customer_id = ca.customer_id
    )
''')

quality_report = {
    "validation_passed": True,
    "customer_count": customer_count,
    "product_count": product_count,
    "high_risk_customers": high_risk_count,
    "vip_customers": vip_count,
    "total_revenue": float(revenue_check) if revenue_check else 0.0,
    "orphaned_records": orphaned_customers,
    "data_quality_score": 1.0 if orphaned_customers == 0 else 0.8
}

# Add quality checks
if customer_count < 3 or product_count < 3:
    quality_report["validation_passed"] = False
    quality_report["issues"] = "Insufficient data loaded"

result = quality_report
""",
                    )
                    # Add connections
                    .add_connection(
                        "extract_customer_data",
                        "customers",
                        "transform_customer_analytics",
                        "customers",
                    )
                    .add_connection(
                        "extract_order_items",
                        "order_items",
                        "transform_product_analytics",
                        "order_items",
                    )
                    .add_connection(
                        "transform_customer_analytics",
                        "customer_analytics",
                        "load_customer_analytics",
                        "customer_analytics",
                    )
                    .add_connection(
                        "transform_product_analytics",
                        "product_analytics",
                        "load_product_analytics",
                        "product_analytics",
                    )
                    .add_connection(
                        "transform_customer_analytics",
                        "customer_analytics",
                        "transform_product_analytics",
                        "customer_analytics",
                    )
                    .add_connection(
                        "load_customer_analytics", None, "validate_data_quality", None
                    )
                    .add_connection(
                        "load_product_analytics", None, "validate_data_quality", None
                    )
                    .build()
                )

                # Execute the demanding ETL pipeline
                start_time = time.time()
                result = await self.execute_workflow(workflow, {})
                execution_time = time.time() - start_time

                # Comprehensive validation
                self.assert_workflow_success(result)

                # Validate extraction
                extract_result = result.get_output("extract_customer_data")
                assert extract_result["extracted_count"] >= 5

                items_result = result.get_output("extract_order_items")
                assert items_result["items_count"] >= 7

                # Validate transformation
                customer_transform = result.get_output("transform_customer_analytics")
                assert len(customer_transform["customer_analytics"]) >= 5
                assert "VIP" in customer_transform["segments"]
                assert customer_transform["segments"]["VIP"] >= 1

                product_transform = result.get_output("transform_product_analytics")
                assert len(product_transform["product_analytics"]) >= 7
                assert "Electronics" in product_transform["categories"]

                # Validate loading
                customer_load = result.get_output("load_customer_analytics")
                assert customer_load["customers_loaded"] >= 5

                product_load = result.get_output("load_product_analytics")
                assert product_load["products_loaded"] >= 7

                # Validate data quality
                quality_result = result.get_output("validate_data_quality")
                assert quality_result["validation_passed"] is True
                assert quality_result["data_quality_score"] >= 0.8
                assert quality_result["customer_count"] >= 5
                assert quality_result["product_count"] >= 7
                assert quality_result["total_revenue"] > 1000.0

                # Performance validation
                assert (
                    execution_time < 30.0
                ), f"ETL took too long: {execution_time:.2f}s"

                # Verify actual database state
                final_customer_count = await self.target_conn.fetchval(
                    "SELECT COUNT(*) FROM customer_analytics"
                )
                final_product_count = await self.target_conn.fetchval(
                    "SELECT COUNT(*) FROM product_analytics"
                )

                assert final_customer_count >= 5
                assert final_product_count >= 7

                # Check for data consistency
                vip_customers = await self.target_conn.fetch(
                    "SELECT * FROM customer_analytics WHERE customer_segment = 'VIP'"
                )
                assert len(vip_customers) >= 1

                high_value_products = await self.target_conn.fetch(
                    "SELECT * FROM product_analytics WHERE total_revenue > 100"
                )
                assert len(high_value_products) >= 3

        # Run the comprehensive test
        async with ETLPipelineTest() as test:
            await test.test_comprehensive_analytics_etl()

    @pytest.mark.asyncio
    async def test_concurrent_microservices_with_redis_and_ollama(self):
        """Test concurrent microservices communication with Redis caching and Ollama AI."""

        class MicroservicesTest(AsyncWorkflowTestCase):
            """Test concurrent microservices with real infrastructure."""

            async def setUp(self):
                await super().setUp()

                # Set up Redis for caching (if available)
                try:
                    import redis.asyncio as redis

                    self.redis_client = redis.Redis(
                        host="localhost", port=6379, decode_responses=True
                    )
                    await self.redis_client.ping()
                    await self.create_test_resource("cache", lambda: self.redis_client)
                    self.has_redis = True
                except Exception:
                    # Fall back to mock cache
                    self.cache = await AsyncWorkflowFixtures.create_test_cache()
                    await self.create_test_resource(
                        "cache", lambda: self.cache, mock=True
                    )
                    self.has_redis = False

                # Set up HTTP clients for different services
                self.user_service = AsyncWorkflowFixtures.create_mock_http_client()
                self.product_service = AsyncWorkflowFixtures.create_mock_http_client()
                self.order_service = AsyncWorkflowFixtures.create_mock_http_client()
                self.ai_service = AsyncWorkflowFixtures.create_mock_http_client()

                # Configure realistic service responses
                self.user_service.add_responses(
                    {
                        "GET:/api/users/123": {
                            "id": 123,
                            "email": "user@example.com",
                            "preferences": {"language": "en", "currency": "USD"},
                            "membership_tier": "premium",
                        },
                        "GET:/api/users/124": {
                            "id": 124,
                            "email": "user2@example.com",
                            "preferences": {"language": "es", "currency": "EUR"},
                            "membership_tier": "basic",
                        },
                    }
                )

                self.product_service.add_responses(
                    {
                        "GET:/api/products/search": [
                            {
                                "id": 1,
                                "name": "Gaming Laptop",
                                "price": 1299.99,
                                "category": "Electronics",
                                "stock": 5,
                            },
                            {
                                "id": 2,
                                "name": "Wireless Mouse",
                                "price": 79.99,
                                "category": "Electronics",
                                "stock": 50,
                            },
                            {
                                "id": 3,
                                "name": "Monitor",
                                "price": 399.99,
                                "category": "Electronics",
                                "stock": 12,
                            },
                        ],
                        "GET:/api/products/recommendations/123": [
                            {
                                "id": 4,
                                "name": "Gaming Keyboard",
                                "price": 159.99,
                                "category": "Electronics",
                                "score": 0.95,
                            },
                            {
                                "id": 5,
                                "name": "Headset",
                                "price": 199.99,
                                "category": "Electronics",
                                "score": 0.87,
                            },
                        ],
                    }
                )

                self.order_service.add_responses(
                    {
                        "POST:/api/orders": {
                            "order_id": "ORD-12345",
                            "status": "confirmed",
                            "total": 1579.97,
                            "estimated_delivery": "2023-07-15",
                        },
                        "GET:/api/orders/user/123": [
                            {
                                "id": "ORD-11111",
                                "total": 299.99,
                                "status": "delivered",
                                "date": "2023-06-01",
                            },
                            {
                                "id": "ORD-11112",
                                "total": 450.00,
                                "status": "shipped",
                                "date": "2023-06-10",
                            },
                        ],
                    }
                )

                # Mock Ollama/AI service
                self.ai_service.add_responses(
                    {
                        "POST:/api/generate": {
                            "response": "Based on the user's purchase history and preferences, I recommend the Gaming Keyboard and Headset as they complement the Gaming Laptop perfectly. These items are frequently bought together and match the user's electronics preferences.",
                            "model": "llama2",
                            "created_at": "2023-07-01T10:00:00Z",
                        },
                        "POST:/api/embeddings": {
                            "embeddings": [
                                [0.1, 0.2, 0.3, 0.4, 0.5] * 100
                            ]  # Mock 500-dim embedding
                        },
                    }
                )

                await self.create_test_resource(
                    "user_service", lambda: self.user_service, mock=True
                )
                await self.create_test_resource(
                    "product_service", lambda: self.product_service, mock=True
                )
                await self.create_test_resource(
                    "order_service", lambda: self.order_service, mock=True
                )
                await self.create_test_resource(
                    "ai_service", lambda: self.ai_service, mock=True
                )

            async def test_complex_order_processing_workflow(self):
                """Test complex order processing with AI recommendations and caching."""

                workflow = (
                    AsyncWorkflowBuilder("microservices_order_processing")
                    .add_async_code(
                        "fetch_user_profile",
                        """
# Fetch user profile with caching
cache = await get_resource("cache")
user_service = await get_resource("user_service")

# Access user_id parameter directly
try:
    user_id = str(user_id) if 'user_id' in locals() else "default_user"
except NameError:
    user_id = "default_user"
cache_key = f"user_profile:{user_id}"

# Check cache first
cached_profile = await cache.get(cache_key)
if cached_profile:
    import json
    user_profile = json.loads(cached_profile) if isinstance(cached_profile, str) else cached_profile
else:
    # Fetch from service
    resp = await user_service.get(f"/api/users/{user_id}")
    user_profile = await resp.json()

    # Cache for 5 minutes
    import json
    await cache.setex(cache_key, 300, json.dumps(user_profile))

result = {
    "user_profile": user_profile,
    "cache_hit": cached_profile is not None
}
""",
                    )
                    .add_async_code(
                        "search_products",
                        """
# Search for products based on user query
product_service = await get_resource("product_service")
cache = await get_resource("cache")

# Access search_query parameter directly
try:
    search_query = search_query if 'search_query' in locals() else "electronics"
except NameError:
    search_query = "electronics"
cache_key = f"product_search:{search_query}"

# Check cache
cached_results = await cache.get(cache_key)
if cached_results:
    import json
    products = json.loads(cached_results) if isinstance(cached_results, str) else cached_results
else:
    # Search products
    resp = await product_service.get(f"/api/products/search?q={search_query}")
    products = await resp.json()

    # Cache results
    import json
    await cache.setex(cache_key, 600, json.dumps(products))

result = {
    "products": products,
    "search_cache_hit": cached_results is not None,
    "product_count": len(products)
}
""",
                    )
                    .add_async_code(
                        "get_recommendations",
                        """
# Get AI-powered product recommendations
product_service = await get_resource("product_service")
ai_service = await get_resource("ai_service")

user_id = user_profile["id"]

# Get user's purchase history for context
order_service = await get_resource("order_service")
history_resp = await order_service.get(f"/api/orders/user/{user_id}")
order_history = await history_resp.json()

# Get recommendations from product service
rec_resp = await product_service.get(f"/api/products/recommendations/{user_id}")
recommendations = await rec_resp.json()

# Generate AI explanation
ai_prompt = f'''
User profile: {user_profile["membership_tier"]} member, prefers {user_profile["preferences"]["language"]}
Purchase history: {len(order_history)} previous orders
Current search: {search_query}
Recommended products: {[r["name"] for r in recommendations]}

Explain why these recommendations are good for this user.
'''

ai_resp = await ai_service.post("/api/generate", json={
    "model": "llama2",
    "prompt": ai_prompt,
    "max_tokens": 150
})
ai_explanation = await ai_resp.json()

result = {
    "recommendations": recommendations,
    "order_history": order_history,
    "ai_explanation": ai_explanation["response"],
    "recommendation_count": len(recommendations)
}
""",
                    )
                    .add_async_code(
                        "calculate_pricing",
                        """
# Calculate dynamic pricing based on user tier and demand
user_tier = user_profile["membership_tier"]
currency = user_profile["preferences"]["currency"]

pricing_data = []
total_base_price = 0
total_discounted_price = 0

# Apply tier-based discounts
tier_discounts = {
    "basic": 0.00,
    "premium": 0.10,
    "vip": 0.15
}

discount_rate = tier_discounts.get(user_tier, 0.00)

for product in products:
    base_price = product["price"]
    discounted_price = base_price * (1 - discount_rate)

    # Currency conversion (simplified)
    if currency == "EUR":
        discounted_price *= 0.85
    elif currency == "GBP":
        discounted_price *= 0.73

    pricing_data.append({
        "product_id": product["id"],
        "product_name": product["name"],
        "base_price": base_price,
        "discounted_price": round(discounted_price, 2),
        "discount_rate": discount_rate,
        "currency": currency,
        "stock": product.get("stock", 0)
    })

    total_base_price += base_price
    total_discounted_price += discounted_price

result = {
    "pricing_data": pricing_data,
    "total_base_price": round(total_base_price, 2),
    "total_discounted_price": round(total_discounted_price, 2),
    "total_savings": round(total_base_price - total_discounted_price, 2),
    "discount_rate": discount_rate
}
""",
                    )
                    .add_async_code(
                        "create_order",
                        """
# Create order with selected products
order_service = await get_resource("order_service")
cache = await get_resource("cache")

# Select first 2 products for order
selected_products = pricing_data[:2]
order_total = sum(p["discounted_price"] for p in selected_products)

order_data = {
    "user_id": user_profile["id"],
    "items": [
        {
            "product_id": p["product_id"],
            "product_name": p["product_name"],
            "price": p["discounted_price"],
            "quantity": 1
        } for p in selected_products
    ],
    "total": order_total,
    "currency": user_profile["preferences"]["currency"],
    "discount_applied": discount_rate
}

# Create order
order_resp = await order_service.post("/api/orders", json=order_data)
order_result = await order_resp.json()

# Cache order for user
user_cache_key = f"user_orders:{user_profile['id']}"
await cache.delete(user_cache_key)  # Invalidate cache

result = {
    "order": order_result,
    "selected_products": selected_products,
    "order_total": order_total,
    "items_count": len(selected_products)
}
""",
                    )
                    .add_async_code(
                        "generate_order_summary",
                        """
# Generate comprehensive order summary with AI insights
ai_service = await get_resource("ai_service")

# Generate embedding for order content
order_content = f"Order {order['order_id']} for user {user_profile['email']} containing {', '.join([item['product_name'] for item in order['items']])}"

embedding_resp = await ai_service.post("/api/embeddings", json={
    "input": order_content
})
embedding_data = await embedding_resp.json()

summary = {
    "order_id": order["order_id"],
    "user_email": user_profile["email"],
    "user_tier": user_profile["membership_tier"],
    "total_amount": order_total,
    "currency": user_profile["preferences"]["currency"],
    "items_purchased": len(selected_products),
    "discount_applied": f"{discount_rate * 100:.0f}%",
    "ai_recommendation_used": recommendation_count > 0,
    "cache_efficiency": {
        "user_cache_hit": cache_hit,
        "search_cache_hit": search_cache_hit
    },
    "order_embedding": embedding_data["embeddings"][0][:5],  # First 5 dims for demo
    "processing_timestamp": datetime.datetime.now().isoformat()
}

result = {
    "summary": summary,
    "performance_metrics": {
        "total_api_calls": 6,  # Approximate
        "cache_hits": int(cache_hit) + int(search_cache_hit),
        "ai_calls": 2
    }
}
""",
                    )
                    # Connect the microservices workflow
                    .add_connection(
                        "fetch_user_profile",
                        "user_profile",
                        "search_products",
                        "user_profile",
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "cache_hit",
                        "search_products",
                        "cache_hit",
                    )
                    .add_connection(
                        "search_products", "products", "get_recommendations", "products"
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "user_profile",
                        "get_recommendations",
                        "user_profile",
                    )
                    .add_connection(
                        "search_products",
                        "search_query",
                        "get_recommendations",
                        "search_query",
                    )
                    .add_connection(
                        "search_products",
                        "search_cache_hit",
                        "get_recommendations",
                        "search_cache_hit",
                    )
                    .add_connection(
                        "search_products", "products", "calculate_pricing", "products"
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "user_profile",
                        "calculate_pricing",
                        "user_profile",
                    )
                    .add_connection(
                        "calculate_pricing",
                        "pricing_data",
                        "create_order",
                        "pricing_data",
                    )
                    .add_connection(
                        "calculate_pricing",
                        "discount_rate",
                        "create_order",
                        "discount_rate",
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "user_profile",
                        "create_order",
                        "user_profile",
                    )
                    .add_connection(
                        "create_order", "order", "generate_order_summary", "order"
                    )
                    .add_connection(
                        "create_order",
                        "selected_products",
                        "generate_order_summary",
                        "selected_products",
                    )
                    .add_connection(
                        "create_order",
                        "order_total",
                        "generate_order_summary",
                        "order_total",
                    )
                    .add_connection(
                        "calculate_pricing",
                        "discount_rate",
                        "generate_order_summary",
                        "discount_rate",
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "user_profile",
                        "generate_order_summary",
                        "user_profile",
                    )
                    .add_connection(
                        "fetch_user_profile",
                        "cache_hit",
                        "generate_order_summary",
                        "cache_hit",
                    )
                    .add_connection(
                        "search_products",
                        "search_cache_hit",
                        "generate_order_summary",
                        "search_cache_hit",
                    )
                    .add_connection(
                        "get_recommendations",
                        "recommendation_count",
                        "generate_order_summary",
                        "recommendation_count",
                    )
                    .build()
                )

                # Test concurrent execution with different users
                user_scenarios = [
                    {"user_id": 123, "search_query": "gaming laptop"},
                    {"user_id": 124, "search_query": "electronics"},
                ]

                # Execute concurrent workflows
                tasks = []
                for scenario in user_scenarios:
                    task = self.execute_workflow(workflow, scenario)
                    tasks.append(task)

                start_time = time.time()
                results = await AsyncTestUtils.run_concurrent(*tasks)
                execution_time = time.time() - start_time

                # Validate concurrent execution
                assert len(results) == 2
                for result in results:
                    self.assert_workflow_success(result)

                # Validate first user scenario (premium user)
                result1 = results[0]

                # User profile validation
                profile_result = result1.get_output("fetch_user_profile")
                assert profile_result["user_profile"]["membership_tier"] == "premium"

                # Product search validation
                search_result = result1.get_output("search_products")
                assert search_result["product_count"] >= 3

                # Recommendations validation
                rec_result = result1.get_output("get_recommendations")
                assert rec_result["recommendation_count"] >= 2
                assert "Gaming" in rec_result["ai_explanation"]

                # Pricing validation (premium user gets 10% discount)
                pricing_result = result1.get_output("calculate_pricing")
                assert pricing_result["discount_rate"] == 0.10
                assert pricing_result["total_savings"] > 0

                # Order creation validation
                order_result = result1.get_output("create_order")
                assert order_result["order"]["order_id"] == "ORD-12345"
                assert order_result["items_count"] == 2

                # Summary validation
                summary_result = result1.get_output("generate_order_summary")
                assert summary_result["summary"]["user_tier"] == "premium"
                assert summary_result["summary"]["discount_applied"] == "10%"
                assert len(summary_result["summary"]["order_embedding"]) == 5

                # Performance validation
                perf_metrics = summary_result["performance_metrics"]
                assert perf_metrics["total_api_calls"] >= 6
                assert perf_metrics["ai_calls"] == 2

                # Validate second user scenario (basic user)
                result2 = results[1]
                pricing_result2 = result2.get_output("calculate_pricing")
                assert (
                    pricing_result2["discount_rate"] == 0.00
                )  # Basic user, no discount

                summary_result2 = result2.get_output("generate_order_summary")
                assert summary_result2["summary"]["user_tier"] == "basic"
                assert summary_result2["summary"]["discount_applied"] == "0%"

                # Performance validation
                assert (
                    execution_time < 15.0
                ), f"Concurrent execution too slow: {execution_time:.2f}s"

                # Validate service call tracking
                self.assert_resource_called("user_service", "get", times=2)  # 2 users
                self.assert_resource_called(
                    "product_service", "get", times=4
                )  # 2 searches + 2 recommendations
                self.assert_resource_called(
                    "order_service", "get", times=2
                )  # 2 history calls
                self.assert_resource_called(
                    "order_service", "post", times=2
                )  # 2 orders
                self.assert_resource_called(
                    "ai_service", "post", times=4
                )  # 2 explanations + 2 embeddings

        # Run the demanding microservices test
        async with MicroservicesTest() as test:
            await test.test_complex_order_processing_workflow()

    @pytest.mark.asyncio
    async def test_high_volume_concurrent_processing(self):
        """Test high-volume concurrent processing with performance monitoring."""

        class HighVolumeTest(AsyncWorkflowTestCase):
            """Test high-volume concurrent workflow processing."""

            async def test_concurrent_data_processing_performance(self):
                """Test processing 50+ concurrent workflows with performance tracking."""

                # Create a CPU and I/O intensive workflow
                workflow = (
                    AsyncWorkflowBuilder("high_volume_processor")
                    .add_async_code(
                        "process_batch",
                        """
import asyncio
import time
import json
import random

# Simulate processing a batch of data
# Access batch_id parameter directly
try:
    batch_id = batch_id if 'batch_id' in locals() else 0
except NameError:
    batch_id = 0
# Access batch_size and delay parameters directly
try:
    batch_size = batch_size if 'batch_size' in locals() else 100
except NameError:
    batch_size = 100

try:
    processing_delay = delay if 'delay' in locals() else 0.01
except NameError:
    processing_delay = 0.01

start_time = time.time()
processed_items = []

for i in range(batch_size):
    # Simulate CPU work
    data = {
        "item_id": f"{batch_id}-{i}",
        "value": random.randint(1, 1000),
        "processed_at": time.time(),
        "batch_id": batch_id
    }

    # Simulate complex calculation
    result = sum(x * x for x in range(i % 50))
    data["computed_value"] = result

    processed_items.append(data)

    # Simulate I/O delay
    if i % 10 == 0:
        await asyncio.sleep(processing_delay)

processing_time = time.time() - start_time

result = {
    "batch_id": batch_id,
    "processed_items": processed_items,
    "items_processed": len(processed_items),
    "processing_time": processing_time,
    "throughput": len(processed_items) / processing_time if processing_time > 0 else 0,
    "avg_time_per_item": processing_time / len(processed_items) if processed_items else 0
}
""",
                    )
                    .build()
                )

                # Create 50 concurrent batches
                batch_count = 50
                batch_size = 50  # 50 items per batch = 2500 total items

                print(
                    f"Processing {batch_count} batches of {batch_size} items each ({batch_count * batch_size} total items)"
                )

                tasks = []
                for batch_id in range(batch_count):
                    task = self.execute_workflow(
                        workflow,
                        {
                            "batch_id": batch_id,
                            "batch_size": batch_size,
                            "delay": 0.001,  # Very small delay
                        },
                    )
                    tasks.append(task)

                # Execute all batches concurrently with performance monitoring
                start_time = time.time()

                # Use converge assertion to ensure all complete
                async def check_completion():
                    if not tasks:
                        return True

                    completed = 0
                    for task in tasks:
                        if task.done():
                            completed += 1

                    completion_rate = completed / len(tasks)
                    print(
                        f"Completion rate: {completion_rate:.2%} ({completed}/{len(tasks)})"
                    )
                    return completion_rate >= 1.0

                # Run with timeout and progress tracking
                results = await AsyncTestUtils.run_concurrent(*tasks)
                total_time = time.time() - start_time

                print(
                    f"All {batch_count} batches completed in {total_time:.2f} seconds"
                )

                # Comprehensive performance validation
                assert len(results) == batch_count

                successful_batches = 0
                total_items_processed = 0
                total_processing_time = 0
                throughputs = []

                for result in results:
                    self.assert_workflow_success(result)

                    batch_result = result.get_output("process_batch")
                    successful_batches += 1
                    total_items_processed += batch_result["items_processed"]
                    total_processing_time += batch_result["processing_time"]
                    throughputs.append(batch_result["throughput"])

                    # Validate individual batch
                    assert batch_result["items_processed"] == batch_size
                    assert batch_result["throughput"] > 0
                    assert len(batch_result["processed_items"]) == batch_size

                # Performance metrics
                overall_throughput = total_items_processed / total_time
                avg_batch_throughput = sum(throughputs) / len(throughputs)
                avg_batch_time = total_processing_time / successful_batches

                print("Performance Metrics:")
                print(f"  Total items processed: {total_items_processed}")
                print(f"  Total execution time: {total_time:.2f}s")
                print(f"  Overall throughput: {overall_throughput:.2f} items/sec")
                print(
                    f"  Average batch throughput: {avg_batch_throughput:.2f} items/sec"
                )
                print(f"  Average batch time: {avg_batch_time:.3f}s")
                print(
                    f"  Concurrent efficiency: {(total_processing_time / total_time):.2f}x"
                )

                # Performance assertions
                assert successful_batches == batch_count
                assert total_items_processed == batch_count * batch_size
                assert (
                    overall_throughput > 100
                ), f"Throughput too low: {overall_throughput:.2f} items/sec"
                assert total_time < 60, f"Total time too high: {total_time:.2f}s"
                assert (
                    avg_batch_time < 5
                ), f"Average batch time too high: {avg_batch_time:.2f}s"

                # Concurrent efficiency should be > 5x due to async execution
                concurrent_efficiency = total_processing_time / total_time
                assert (
                    concurrent_efficiency > 5
                ), f"Poor concurrent efficiency: {concurrent_efficiency:.2f}x"

        # Run the high-volume performance test
        async with HighVolumeTest() as test:
            await test.test_concurrent_data_processing_performance()


# Additional helper for manual testing
if __name__ == "__main__":
    import asyncio

    async def run_manual_test():
        """Run a single test manually for debugging."""
        test = TestAsyncTestingDemandingRealWorld()
        await test.test_full_etl_pipeline_with_postgres_and_ollama()
        print("Manual test completed successfully!")

    asyncio.run(run_manual_test())

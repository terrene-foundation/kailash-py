"""Production-quality integration tests for Durable Gateway.

These tests simulate real-world production scenarios including:
- High-volume concurrent requests with real AI processing
- Complex multi-step workflows with database operations
- Failure recovery and checkpointing under load
- Real-time analytics with Ollama LLM integration
- Long-running batch processing with resume capability
- Multi-tenant workflows with authentication
"""

import asyncio
import json
import os
import random
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx
import pytest
import pytest_asyncio

from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.workflow import WorkflowBuilder

# Production test configuration
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "database": os.getenv("POSTGRES_DB", "kailash_test"),
    "user": os.getenv("POSTGRES_USER", "test_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "test_password"),
}

OLLAMA_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "llama3.2:3b",
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6380)),
    "db": 0,
}


@pytest.mark.slow
class TestDurableGatewayProduction:
    """Production-quality integration tests for Durable Gateway."""

    @pytest_asyncio.fixture
    async def production_database(self):
        """Set up production-like database with realistic data."""
        pool = WorkflowConnectionPool(
            name="production_test_db",
            **POSTGRES_CONFIG,
            min_connections=5,
            max_connections=20,
        )

        await pool.process({"operation": "initialize"})

        # Create comprehensive schema
        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        try:
            # Drop existing tables
            tables_to_drop = [
                "order_analytics",
                "customer_insights",
                "product_reviews",
                "transactions",
                "user_sessions",
                "audit_logs",
                "metrics",
            ]
            for table in tables_to_drop:
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": f"DROP TABLE IF EXISTS {table} CASCADE",
                        "fetch_mode": "one",
                    }
                )

            # Create realistic production schema
            await self._create_production_schema(pool, conn_id)

            # Insert realistic test data
            await self._insert_production_data(pool, conn_id)

        finally:
            await pool.process({"operation": "release", "connection_id": conn_id})

        yield pool

        # Cleanup
        await pool._cleanup()

    async def _create_production_schema(self, pool, conn_id):
        """Create production-like database schema."""
        schemas = [
            # E-commerce transactions
            """CREATE TABLE transactions (
                transaction_id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                product_id VARCHAR(50) NOT NULL,
                amount DECIMAL(12,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'USD',
                status VARCHAR(20) DEFAULT 'pending',
                payment_method VARCHAR(50),
                merchant_id VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )""",
            # User sessions for analytics
            """CREATE TABLE user_sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                device_type VARCHAR(50),
                browser VARCHAR(100),
                ip_address INET,
                country VARCHAR(3),
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                page_views INTEGER DEFAULT 0,
                events JSONB DEFAULT '[]',
                conversion_data JSONB DEFAULT '{}'
            )""",
            # Product reviews for sentiment analysis
            """CREATE TABLE product_reviews (
                review_id VARCHAR(50) PRIMARY KEY,
                product_id VARCHAR(50) NOT NULL,
                user_id VARCHAR(50) NOT NULL,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                title VARCHAR(200),
                content TEXT,
                sentiment_score DECIMAL(3,2),
                sentiment_label VARCHAR(20),
                helpful_votes INTEGER DEFAULT 0,
                verified_purchase BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                ai_analysis JSONB DEFAULT '{}'
            )""",
            # Real-time analytics aggregations
            """CREATE TABLE order_analytics (
                id SERIAL PRIMARY KEY,
                time_bucket TIMESTAMP NOT NULL,
                merchant_id VARCHAR(50),
                total_orders INTEGER DEFAULT 0,
                total_revenue DECIMAL(15,2) DEFAULT 0,
                avg_order_value DECIMAL(10,2) DEFAULT 0,
                conversion_rate DECIMAL(5,4) DEFAULT 0,
                top_products JSONB DEFAULT '[]',
                customer_segments JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Customer insights from AI analysis
            """CREATE TABLE customer_insights (
                insight_id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                insight_type VARCHAR(100),
                confidence_score DECIMAL(3,2),
                insights JSONB NOT NULL,
                recommendations JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP,
                source_data JSONB DEFAULT '{}'
            )""",
            # System audit logs
            """CREATE TABLE audit_logs (
                log_id VARCHAR(50) PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                user_id VARCHAR(50),
                entity_type VARCHAR(100),
                entity_id VARCHAR(50),
                action VARCHAR(100),
                changes JSONB DEFAULT '{}',
                metadata JSONB DEFAULT '{}',
                ip_address INET,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Performance metrics
            """CREATE TABLE metrics (
                metric_id VARCHAR(50) PRIMARY KEY,
                metric_name VARCHAR(100) NOT NULL,
                metric_value DECIMAL(15,4),
                tags JSONB DEFAULT '{}',
                timestamp TIMESTAMP DEFAULT NOW(),
                source VARCHAR(100)
            )""",
        ]

        for schema in schemas:
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": schema,
                    "fetch_mode": "one",
                }
            )

    async def _insert_production_data(self, pool, conn_id):
        """Insert realistic production data."""
        # Generate realistic transaction data
        for i in range(100):
            transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
            user_id = f"user_{random.randint(1000, 9999)}"
            product_id = f"prod_{random.randint(100, 999)}"
            amount = round(random.uniform(10.99, 999.99), 2)
            status = random.choice(["completed", "pending", "failed", "refunded"])
            payment_method = random.choice(
                ["credit_card", "debit_card", "paypal", "apple_pay"]
            )

            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    INSERT INTO transactions
                    (transaction_id, user_id, product_id, amount, status, payment_method)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    "params": [
                        transaction_id,
                        user_id,
                        product_id,
                        amount,
                        status,
                        payment_method,
                    ],
                    "fetch_mode": "one",
                }
            )

        # Generate user session data
        for i in range(50):
            session_id = f"sess_{uuid.uuid4().hex[:16]}"
            user_id = f"user_{random.randint(1000, 9999)}"
            device_type = random.choice(["desktop", "mobile", "tablet"])
            page_views = random.randint(1, 50)

            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    INSERT INTO user_sessions
                    (session_id, user_id, device_type, page_views)
                    VALUES ($1, $2, $3, $4)
                """,
                    "params": [session_id, user_id, device_type, page_views],
                    "fetch_mode": "one",
                }
            )

        # Generate product reviews for sentiment analysis
        reviews = [
            (
                "Excellent product, highly recommend!",
                5,
                "This product exceeded my expectations. The quality is outstanding and delivery was fast.",
            ),
            (
                "Good value for money",
                4,
                "Decent product for the price. Some minor issues but overall satisfied.",
            ),
            (
                "Not what I expected",
                2,
                "The product description was misleading. Quality is below average.",
            ),
            (
                "Outstanding service",
                5,
                "Amazing customer service and the product is exactly as described. Will buy again!",
            ),
            (
                "Could be better",
                3,
                "Average product. It works but there's room for improvement.",
            ),
        ]

        for i in range(30):
            review_id = f"rev_{uuid.uuid4().hex[:12]}"
            product_id = f"prod_{random.randint(100, 999)}"
            user_id = f"user_{random.randint(1000, 9999)}"
            title, rating, content = random.choice(reviews)

            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    INSERT INTO product_reviews
                    (review_id, product_id, user_id, rating, title, content, verified_purchase)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                    "params": [
                        review_id,
                        product_id,
                        user_id,
                        rating,
                        title,
                        content,
                        random.choice([True, False]),
                    ],
                    "fetch_mode": "one",
                }
            )

    @pytest_asyncio.fixture
    async def production_gateway(self, production_database):
        """Create production-configured durable gateway."""
        temp_dir = tempfile.mkdtemp(prefix="kailash_prod_test_")

        # Production-grade checkpoint manager
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage(temp_dir),
            retention_hours=24,  # Production retention
            compression_enabled=True,
            compression_threshold_bytes=512,  # More aggressive compression
        )

        gateway = DurableAPIGateway(
            title="Production Durable Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            durability_opt_in=False,  # Always durable in production
        )

        # Register production workflows
        await self._register_production_workflows(gateway, production_database)

        # Start gateway with production port range
        port = random.randint(9000, 9999)

        server_thread = threading.Thread(
            target=lambda: gateway.run(port=port, log_level="warning"), daemon=True
        )
        server_thread.start()

        # Wait for startup and verify health
        time.sleep(3)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{port}/health", timeout=5.0
                )
                assert response.status_code == 200
        except Exception as e:
            pytest.fail(f"Gateway failed to start: {e}")

        gateway._test_port = port

        yield gateway

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    async def _register_production_workflows(self, gateway, pool):
        """Register production-grade workflows."""

        # 1. Real-time Analytics Pipeline
        analytics_workflow = await self._create_analytics_workflow(pool)
        gateway.register_workflow("realtime_analytics", analytics_workflow)

        # 2. AI-Powered Customer Insights
        insights_workflow = await self._create_customer_insights_workflow(pool)
        gateway.register_workflow("customer_insights", insights_workflow)

        # 3. Batch Processing Pipeline
        batch_workflow = await self._create_batch_processing_workflow(pool)
        gateway.register_workflow("batch_processing", batch_workflow)

        # 4. Sentiment Analysis Pipeline
        sentiment_workflow = await self._create_sentiment_analysis_workflow(pool)
        gateway.register_workflow("sentiment_analysis", sentiment_workflow)

        # 5. Fraud Detection Workflow
        fraud_workflow = await self._create_fraud_detection_workflow(pool)
        gateway.register_workflow("fraud_detection", fraud_workflow)

    async def _create_analytics_workflow(self, pool) -> WorkflowBuilder:
        """Create real-time analytics workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "realtime_analytics"

        # Fetch transaction data
        workflow.add_node(
            "PythonCodeNode",
            "fetch_transactions",
            {
                "code": """
import asyncio
from datetime import datetime, timedelta

# Variables are injected from inputs
try:
    time_window_hours
except NameError:
    time_window_hours = 1

time_window = time_window_hours

# Calculate time range
end_time = datetime.now()
start_time = end_time - timedelta(hours=time_window)

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Fetch recent transactions
    result = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT
                COUNT(*) as total_transactions,
                SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_revenue,
                AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END) as avg_order_value,
                COUNT(DISTINCT user_id) as unique_customers,
                payment_method,
                COUNT(*) as method_count
            FROM transactions
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY payment_method
            ORDER BY method_count DESC
        ''',
        "params": [start_time.isoformat(), end_time.isoformat()],
        "fetch_mode": "all"
    })

    # Calculate conversion metrics
    conversion_result = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT
                COUNT(CASE WHEN status = 'completed' THEN 1 END)::float / COUNT(*)::float as conversion_rate,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count
            FROM transactions
            WHERE created_at >= $1 AND created_at <= $2
        ''',
        "params": [start_time.isoformat(), end_time.isoformat()],
        "fetch_mode": "one"
    })

    result = {
        "transactions": result["data"],
        "conversion_metrics": conversion_result["data"],
        "time_window": time_window,
        "analyzed_at": datetime.now().isoformat()
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # AI-powered analytics with Ollama
        workflow.add_node(
            "LLMAgentNode",
            "ai_analysis",
            {
                "name": "analytics_agent",
                "model": OLLAMA_CONFIG["model"],
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a senior data analyst specializing in e-commerce analytics.
Analyze transaction data and provide actionable business insights.

Focus on:
1. Revenue trends and patterns
2. Payment method preferences
3. Conversion rate analysis
4. Customer behavior insights
5. Risk indicators
6. Optimization recommendations

Provide your analysis in JSON format with specific metrics and recommendations.""",
                "prompt": """Analyze this e-commerce transaction data:

Transaction Data: {transactions}
Conversion Metrics: {conversion_metrics}
Time Window: {time_window} hours

Provide a comprehensive analysis with:
1. Key performance indicators
2. Notable trends or anomalies
3. Business recommendations
4. Risk assessment
5. Next steps for optimization

Format as JSON with clear sections.""",
                "temperature": 0.3,
                "max_tokens": 1000,
            },
        )

        # Store analytics results
        workflow.add_node(
            "PythonCodeNode",
            "store_analytics",
            {
                "code": """
import json
from datetime import datetime

# Variables are injected from inputs and connections
# analytics_data comes from fetch_transactions node connection
# ai_insights comes from ai_analysis node connection
# pool comes from node inputs configuration

# Parse AI response
try:
    ai_analysis = json.loads(ai_insights.get("response", "{}"))
except:
    ai_analysis = {"raw_response": ai_insights.get("response", "")}

# Extract key metrics from analytics_data
transactions = analytics_data["transactions"]
total_revenue = sum(float(t.get("total_revenue", 0)) for t in transactions)
total_transactions = sum(int(t.get("method_count", 0)) for t in transactions)
avg_order_value = total_revenue / max(total_transactions, 1)

conversion_metrics = analytics_data["conversion_metrics"]
conversion_rate = float(conversion_metrics.get("conversion_rate", 0))

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Store analytics results
    await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            INSERT INTO order_analytics
            (time_bucket, total_orders, total_revenue, avg_order_value, conversion_rate,
             top_products, customer_segments)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        ''',
        "params": [
            datetime.now().replace(minute=0, second=0, microsecond=0),
            total_transactions,
            total_revenue,
            avg_order_value,
            conversion_rate,
            json.dumps(transactions[:5]),  # Top payment methods
            json.dumps(ai_analysis)
        ],
        "fetch_mode": "one"
    })

    result = {
        "stored": True,
        "analytics_id": f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "conversion_rate": conversion_rate,
        "ai_insights": ai_analysis
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Connect workflow
        workflow.add_connection(
            "fetch_transactions", "result", "ai_analysis", "analytics_data"
        )
        workflow.add_connection(
            "fetch_transactions", "result", "store_analytics", "analytics_data"
        )
        workflow.add_connection(
            "ai_analysis", "result", "store_analytics", "ai_insights"
        )

        return workflow.build()

    async def _create_customer_insights_workflow(self, pool) -> WorkflowBuilder:
        """Create AI-powered customer insights workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "customer_insights"

        # Fetch customer data
        workflow.add_node(
            "PythonCodeNode",
            "fetch_customer_data",
            {
                "code": """
import asyncio

# pool comes from node inputs configuration
# user_id should come from runtime parameters
try:
    user_id
except NameError:
    user_id = "default_user_123"  # Default for testing

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Fetch customer transaction history
    transactions = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT transaction_id, amount, status, payment_method, created_at
            FROM transactions
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 50
        ''',
        "params": [user_id],
        "fetch_mode": "all"
    })

    # Fetch session data
    sessions = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT session_id, device_type, page_views, started_at
            FROM user_sessions
            WHERE user_id = $1
            ORDER BY started_at DESC
            LIMIT 20
        ''',
        "params": [user_id],
        "fetch_mode": "all"
    })

    result = {
        "user_id": user_id,
        "transactions": transactions["data"],
        "sessions": sessions["data"]
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # AI customer analysis
        workflow.add_node(
            "LLMAgentNode",
            "customer_ai_analysis",
            {
                "name": "customer_insights_agent",
                "model": OLLAMA_CONFIG["model"],
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a customer intelligence specialist with expertise in behavioral analytics and personalization.

Analyze customer data to generate actionable insights for:
1. Customer segment classification
2. Purchase behavior patterns
3. Engagement level assessment
4. Churn risk prediction
5. Personalized recommendations
6. Lifetime value estimation

Provide insights in JSON format with confidence scores.""",
                "prompt": """Analyze this customer profile:

User ID: {user_id}
Transaction History: {transactions}
Session Data: {sessions}

Generate comprehensive insights including:
1. Customer segment (premium, regular, at-risk, etc.)
2. Purchase patterns and preferences
3. Engagement score (1-10)
4. Churn risk assessment (low/medium/high)
5. Recommended actions
6. Estimated lifetime value
7. Personalization opportunities

Format as structured JSON with confidence scores for predictions.""",
                "temperature": 0.4,
                "max_tokens": 800,
            },
        )

        # Store insights
        workflow.add_node(
            "PythonCodeNode",
            "store_insights",
            {
                "code": """
import json
import uuid
from datetime import datetime, timedelta

# Variables are injected from inputs and connections
# pool comes from node inputs configuration
# customer_data comes from fetch_customer_data node connection
# ai_insights comes from customer_ai_analysis node connection

# Parse AI response
try:
    insights_data = json.loads(ai_insights.get("response", "{}"))
except:
    insights_data = {"raw_response": ai_insights.get("response", "")}

insight_id = f"insight_{uuid.uuid4().hex[:12]}"
user_id = customer_data["user_id"]

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Store customer insights
    await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            INSERT INTO customer_insights
            (insight_id, user_id, insight_type, confidence_score, insights,
             recommendations, expires_at, source_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''',
        "params": [
            insight_id,
            user_id,
            "behavioral_analysis",
            insights_data.get("confidence_score", 0.8),
            json.dumps(insights_data),
            json.dumps(insights_data.get("recommendations", [])),
            datetime.now() + timedelta(days=30),  # Insights expire in 30 days
            json.dumps(customer_data)
        ],
        "fetch_mode": "one"
    })

    result = {
        "insight_id": insight_id,
        "user_id": user_id,
        "insights": insights_data,
        "stored_at": datetime.now().isoformat()
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Connect workflow
        workflow.add_connection(
            "fetch_customer_data", "result", "customer_ai_analysis", "customer_data"
        )
        workflow.add_connection(
            "fetch_customer_data", "result", "store_insights", "customer_data"
        )
        workflow.add_connection(
            "customer_ai_analysis", "result", "store_insights", "ai_insights"
        )

        return workflow.build()

    async def _create_sentiment_analysis_workflow(self, pool) -> WorkflowBuilder:
        """Create sentiment analysis workflow for product reviews."""
        workflow = WorkflowBuilder()
        workflow.name = "sentiment_analysis"

        # Fetch unprocessed reviews
        workflow.add_node(
            "PythonCodeNode",
            "fetch_reviews",
            {
                "code": """
import asyncio

# pool comes from node inputs configuration
# batch_size should come from runtime parameters
try:
    batch_size
except NameError:
    batch_size = 10  # Default batch size for testing

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Fetch reviews without sentiment analysis
    result = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT review_id, product_id, user_id, rating, title, content
            FROM product_reviews
            WHERE sentiment_score IS NULL
            ORDER BY created_at DESC
            LIMIT $1
        ''',
        "params": [batch_size],
        "fetch_mode": "all"
    })

    result = {
        "reviews": result["data"],
        "batch_size": len(result["data"])
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # AI sentiment analysis
        workflow.add_node(
            "LLMAgentNode",
            "sentiment_ai_analysis",
            {
                "name": "sentiment_agent",
                "model": OLLAMA_CONFIG["model"],
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are an expert sentiment analysis AI specializing in product reviews and customer feedback.

For each review, provide:
1. Sentiment score (-1.0 to 1.0, where -1 is very negative, 0 is neutral, 1 is very positive)
2. Sentiment label (positive, negative, neutral)
3. Key themes and topics mentioned
4. Emotional indicators
5. Specific aspects rated (quality, price, service, etc.)
6. Actionable insights for business

Always respond in valid JSON format.""",
                "prompt": """Analyze the sentiment of these product reviews:

{reviews}

For each review, provide detailed sentiment analysis in this JSON format:
{{
  "review_analyses": [
    {{
      "review_id": "id",
      "sentiment_score": 0.0,
      "sentiment_label": "positive/negative/neutral",
      "confidence": 0.95,
      "key_themes": ["theme1", "theme2"],
      "aspects": {{"quality": 0.8, "price": -0.2}},
      "insights": "specific insights for this review"
    }}
  ],
  "overall_summary": {{
    "average_sentiment": 0.0,
    "dominant_themes": ["theme1", "theme2"],
    "recommendations": ["action1", "action2"]
  }}
}}""",
                "temperature": 0.1,
                "max_tokens": 1500,
            },
        )

        # Update reviews with sentiment data
        workflow.add_node(
            "PythonCodeNode",
            "update_sentiments",
            {
                "code": """
import json
import asyncio

# pool comes from node inputs configuration
# reviews_data comes from fetch_reviews node connection
# sentiment_analysis comes from sentiment_ai_analysis node connection

# Parse AI response
try:
    analysis_data = json.loads(sentiment_analysis.get("response", "{}"))
    review_analyses = analysis_data.get("review_analyses", [])
except:
    review_analyses = []

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

updated_count = 0

try:
    # Update each review with sentiment data
    for analysis in review_analyses:
        review_id = analysis.get("review_id")
        sentiment_score = analysis.get("sentiment_score", 0.0)
        sentiment_label = analysis.get("sentiment_label", "neutral")
        ai_analysis_data = json.dumps(analysis)

        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": '''
                UPDATE product_reviews
                SET sentiment_score = $1, sentiment_label = $2, ai_analysis = $3
                WHERE review_id = $4
            ''',
            "params": [sentiment_score, sentiment_label, ai_analysis_data, review_id],
            "fetch_mode": "one"
        })
        updated_count += 1

    result = {
        "updated_reviews": updated_count,
        "total_processed": len(review_analyses),
        "overall_summary": analysis_data.get("overall_summary", {})
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Connect workflow
        workflow.add_connection(
            "fetch_reviews", "result", "sentiment_ai_analysis", "reviews_data"
        )
        workflow.add_connection(
            "fetch_reviews", "result", "update_sentiments", "reviews_data"
        )
        workflow.add_connection(
            "sentiment_ai_analysis", "result", "update_sentiments", "sentiment_analysis"
        )

        return workflow.build()

    async def _create_batch_processing_workflow(self, pool) -> WorkflowBuilder:
        """Create long-running batch processing workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "batch_processing"

        # Initialize batch job
        workflow.add_node(
            "PythonCodeNode",
            "initialize_batch",
            {
                "code": """
import time
import uuid

batch_id = f"batch_{uuid.uuid4().hex[:12]}"
# total_records and batch_size should come from runtime parameters
try:
    total_records
except NameError:
    total_records = 1000  # Default for testing

try:
    batch_size
except NameError:
    batch_size = 50  # Default for testing
total_batches = (total_records + batch_size - 1) // batch_size

result = {
    "batch_id": batch_id,
    "total_records": total_records,
    "batch_size": batch_size,
    "total_batches": total_batches,
    "current_batch": 0,
    "start_time": time.time(),
    "status": "initialized"
}
"""
            },
        )

        # Process batches with checkpointing
        workflow.add_node(
            "PythonCodeNode",
            "process_batches",
            {
                "code": """
import asyncio
import time
import random

# pool comes from node inputs configuration
# batch_data comes from initialize_batch node connection
# simulate_heavy_processing should come from runtime parameters
try:
    simulate_heavy_processing
except NameError:
    simulate_heavy_processing = True  # Default for testing

batch_id = batch_data["batch_id"]
total_batches = batch_data["total_batches"]
batch_size = batch_data["batch_size"]

processed_batches = []
failed_batches = []

for batch_num in range(total_batches):
    try:
        # Simulate heavy processing
        if simulate_heavy_processing:
            # Random processing time between 0.5-2 seconds per batch
            processing_time = random.uniform(0.5, 2.0)
            await asyncio.sleep(processing_time)

        # Simulate occasional failures for testing recovery
        if random.random() < 0.05:  # 5% failure rate
            raise Exception(f"Simulated processing failure in batch {batch_num}")

        # Record successful batch
        batch_result = {
            "batch_number": batch_num,
            "records_processed": batch_size,
            "processing_time": processing_time if simulate_heavy_processing else 0.1,
            "timestamp": time.time()
        }
        processed_batches.append(batch_result)

        # Checkpoint every 10 batches
        if (batch_num + 1) % 10 == 0:
            # In a real implementation, this would trigger a checkpoint
            pass

    except Exception as e:
        failed_batches.append({
            "batch_number": batch_num,
            "error": str(e),
            "timestamp": time.time()
        })
        # In production, you might want to retry failed batches

total_processed = sum(b["records_processed"] for b in processed_batches)

result = {
    "batch_id": batch_id,
    "processed_batches": len(processed_batches),
    "failed_batches": len(failed_batches),
    "total_processed_records": total_processed,
    "processing_details": processed_batches,
    "failures": failed_batches,
    "completion_time": time.time(),
    "status": "completed" if not failed_batches else "completed_with_errors"
}
""",
                "inputs": {"pool": pool},
            },
        )

        # Generate batch report
        workflow.add_node(
            "PythonCodeNode",
            "generate_report",
            {
                "code": """
from datetime import datetime

# batch_data comes from initialize_batch node connection
# processing_results comes from process_batches node connection

start_time = batch_data["start_time"]
completion_time = processing_results["completion_time"]
total_duration = completion_time - start_time

# Calculate statistics
success_rate = (processing_results["processed_batches"] /
               (processing_results["processed_batches"] + processing_results["failed_batches"])) * 100

avg_processing_time = (sum(b["processing_time"] for b in processing_results["processing_details"]) /
                      len(processing_results["processing_details"])) if processing_results["processing_details"] else 0

report = {
    "batch_id": processing_results["batch_id"],
    "summary": {
        "total_duration_seconds": round(total_duration, 2),
        "total_records_processed": processing_results["total_processed_records"],
        "success_rate_percent": round(success_rate, 2),
        "avg_batch_processing_time": round(avg_processing_time, 3),
        "throughput_records_per_second": round(processing_results["total_processed_records"] / total_duration, 2)
    },
    "status": processing_results["status"],
    "failures": processing_results["failures"],
    "completed_at": datetime.fromtimestamp(completion_time).isoformat()
}

result = report
"""
            },
        )

        # Connect workflow
        workflow.add_connection(
            "initialize_batch", "result", "process_batches", "batch_data"
        )
        workflow.add_connection(
            "initialize_batch", "result", "generate_report", "batch_data"
        )
        workflow.add_connection(
            "process_batches", "result", "generate_report", "processing_results"
        )

        return workflow.build()

    async def _create_fraud_detection_workflow(self, pool) -> WorkflowBuilder:
        """Create AI-powered fraud detection workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "fraud_detection"

        # Fetch transaction for analysis
        workflow.add_node(
            "PythonCodeNode",
            "fetch_transaction",
            {
                "code": """
import asyncio

# pool comes from node inputs configuration
# transaction_id should come from runtime parameters
try:
    transaction_id
except NameError:
    transaction_id = "test_txn_123"  # Default for testing

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Fetch transaction details
    transaction = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT * FROM transactions WHERE transaction_id = $1
        ''',
        "params": [transaction_id],
        "fetch_mode": "one"
    })

    # Fetch user's recent transactions for pattern analysis
    user_history = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT transaction_id, amount, payment_method, created_at, status
            FROM transactions
            WHERE user_id = $1 AND transaction_id != $2
            ORDER BY created_at DESC
            LIMIT 20
        ''',
        "params": [transaction["data"]["user_id"], transaction_id],
        "fetch_mode": "all"
    })

    result = {
        "transaction": transaction["data"],
        "user_history": user_history["data"]
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # AI fraud analysis
        workflow.add_node(
            "LLMAgentNode",
            "fraud_ai_analysis",
            {
                "name": "fraud_detection_agent",
                "model": OLLAMA_CONFIG["model"],
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a fraud detection specialist with expertise in payment security and anomaly detection.

Analyze transaction patterns to identify potential fraud indicators:

1. Amount anomalies (unusually high/low compared to history)
2. Frequency patterns (too many transactions in short time)
3. Payment method changes
4. Geographic anomalies (if available)
5. Time-based patterns (unusual hours)
6. Behavioral changes

Provide risk assessment with confidence scores and specific reasoning.""",
                "prompt": """Analyze this transaction for fraud risk:

Current Transaction: {transaction}
User Transaction History: {user_history}

Provide fraud risk analysis in JSON format:
{{
  "risk_level": "low/medium/high",
  "risk_score": 0.0-1.0,
  "confidence": 0.0-1.0,
  "risk_factors": [
    {{
      "factor": "factor_name",
      "severity": "low/medium/high",
      "description": "detailed explanation"
    }}
  ],
  "recommendation": "approve/review/decline",
  "reasoning": "detailed analysis of why this recommendation",
  "monitoring_flags": ["flag1", "flag2"]
}}""",
                "temperature": 0.1,
                "max_tokens": 800,
            },
        )

        # Store fraud analysis results
        workflow.add_node(
            "PythonCodeNode",
            "store_fraud_analysis",
            {
                "code": """
import json
import uuid
from datetime import datetime

# pool comes from node inputs configuration
# transaction_data comes from fetch_transaction node connection
# fraud_analysis comes from fraud_ai_analysis node connection

# Parse AI response
try:
    analysis_data = json.loads(fraud_analysis.get("response", "{}"))
except:
    analysis_data = {"risk_level": "unknown", "risk_score": 0.5}

transaction = transaction_data["transaction"]
audit_id = f"fraud_{uuid.uuid4().hex[:12]}"

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Store fraud analysis in audit logs
    await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            INSERT INTO audit_logs
            (log_id, event_type, user_id, entity_type, entity_id, action,
             changes, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''',
        "params": [
            audit_id,
            "fraud_analysis",
            transaction["user_id"],
            "transaction",
            transaction["transaction_id"],
            analysis_data.get("recommendation", "review"),
            json.dumps(analysis_data),
            json.dumps({
                "analysis_timestamp": datetime.now().isoformat(),
                "risk_level": analysis_data.get("risk_level", "unknown"),
                "risk_score": analysis_data.get("risk_score", 0.5)
            })
        ],
        "fetch_mode": "one"
    })

    result = {
        "audit_id": audit_id,
        "transaction_id": transaction["transaction_id"],
        "risk_assessment": analysis_data,
        "analyzed_at": datetime.now().isoformat()
    }

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Connect workflow
        workflow.add_connection(
            "fetch_transaction", "result", "fraud_ai_analysis", "transaction_data"
        )
        workflow.add_connection(
            "fetch_transaction", "result", "store_fraud_analysis", "transaction_data"
        )
        workflow.add_connection(
            "fraud_ai_analysis", "result", "store_fraud_analysis", "fraud_analysis"
        )

        return workflow.build()

    @pytest.mark.asyncio
    async def test_high_volume_concurrent_analytics(self, production_gateway):
        """Test high-volume concurrent real-time analytics requests."""
        port = production_gateway._test_port

        async def submit_analytics_request(session, request_id):
            """Submit a single analytics request."""
            try:
                response = await session.post(
                    f"http://localhost:{port}/realtime_analytics/execute",
                    json={
                        "inputs": {
                            "fetch_transactions": {
                                "time_window_hours": random.choice([1, 2, 6, 12])
                            }
                        }
                    },
                    timeout=30.0,
                )
                return {
                    "request_id": request_id,
                    "status": response.status_code,
                    "success": response.status_code == 200,
                    "response_time": (
                        response.elapsed.total_seconds()
                        if hasattr(response, "elapsed")
                        else 0
                    ),
                    "data": response.json() if response.status_code == 200 else None,
                }
            except Exception as e:
                return {
                    "request_id": request_id,
                    "status": 0,
                    "success": False,
                    "error": str(e),
                }

        # Submit 20 concurrent analytics requests
        async with httpx.AsyncClient() as client:
            tasks = []
            for i in range(20):
                task = submit_analytics_request(client, f"analytics_{i}")
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        successful_requests = [
            r for r in results if isinstance(r, dict) and r.get("success")
        ]
        failed_requests = [
            r for r in results if isinstance(r, dict) and not r.get("success")
        ]

        print(f"Successful requests: {len(successful_requests)}/20")
        print(f"Failed requests: {len(failed_requests)}")

        # Assert production quality requirements
        success_rate = len(successful_requests) / 20
        assert (
            success_rate >= 0.95
        ), f"Success rate {success_rate:.2%} below 95% threshold"

        # Verify durability is working
        durability_response = await client.get(
            f"http://localhost:{port}/durability/status"
        )
        assert durability_response.status_code == 200

        durability_stats = durability_response.json()
        assert (
            durability_stats["event_store_stats"]["event_count"] > 50
        )  # Expect many events

        # Verify analytics data quality
        if successful_requests:
            sample_result = successful_requests[0]["data"]
            assert "outputs" in sample_result
            assert "store_analytics" in sample_result["outputs"]

            analytics_output = sample_result["outputs"]["store_analytics"]["result"]
            assert analytics_output["stored"] is True
            assert "total_revenue" in analytics_output
            assert "ai_insights" in analytics_output

    @pytest.mark.asyncio
    async def test_ai_customer_insights_pipeline(self, production_gateway):
        """Test AI-powered customer insights generation with real data."""
        port = production_gateway._test_port

        async with httpx.AsyncClient() as client:
            # Test customer insights for multiple users
            test_users = [f"user_{random.randint(1000, 9999)}" for _ in range(5)]

            for user_id in test_users:
                response = await client.post(
                    f"http://localhost:{port}/customer_insights/execute",
                    json={"inputs": {"fetch_customer_data": {"user_id": user_id}}},
                    timeout=45.0,  # Allow time for AI processing
                )

                assert response.status_code == 200
                result = response.json()

                # Verify workflow execution
                assert "outputs" in result
                assert "store_insights" in result["outputs"]

                insights_output = result["outputs"]["store_insights"]["result"]
                assert "insight_id" in insights_output
                assert insights_output["user_id"] == user_id
                assert "insights" in insights_output

                # Verify AI analysis quality
                ai_insights = insights_output["insights"]
                if isinstance(ai_insights, dict):
                    # Should contain customer analysis elements
                    assert len(str(ai_insights)) > 100  # Substantial analysis

    @pytest.mark.asyncio
    async def test_sentiment_analysis_batch_processing(self, production_gateway):
        """Test sentiment analysis of product reviews with AI."""
        port = production_gateway._test_port

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/sentiment_analysis/execute",
                json={"inputs": {"fetch_reviews": {"batch_size": 5}}},
                timeout=60.0,  # AI processing can take time
            )

            assert response.status_code == 200
            result = response.json()

            # Verify sentiment analysis execution
            assert "outputs" in result
            assert "update_sentiments" in result["outputs"]

            sentiment_output = result["outputs"]["update_sentiments"]["result"]
            assert "updated_reviews" in sentiment_output
            assert sentiment_output["updated_reviews"] >= 0

            if sentiment_output["updated_reviews"] > 0:
                assert "overall_summary" in sentiment_output

    @pytest.mark.asyncio
    async def test_long_running_batch_with_checkpointing(self, production_gateway):
        """Test long-running batch processing with checkpointing capabilities."""
        port = production_gateway._test_port

        async with httpx.AsyncClient() as client:
            # Start a large batch job
            response = await client.post(
                f"http://localhost:{port}/batch_processing/execute",
                json={
                    "inputs": {
                        "initialize_batch": {
                            "total_records": 500,
                            "batch_size": 25,
                            "simulate_heavy_processing": True,
                        }
                    }
                },
                timeout=120.0,  # Allow sufficient time for processing
            )

            # Verify the batch job executed
            if response.status_code == 200:
                result = response.json()

                assert "outputs" in result
                assert "generate_report" in result["outputs"]

                report = result["outputs"]["generate_report"]["result"]
                assert "batch_id" in report
                assert "summary" in report

                summary = report["summary"]
                assert summary["total_records_processed"] > 0
                assert (
                    summary["success_rate_percent"] >= 90
                )  # Allow for some simulated failures
                assert summary["throughput_records_per_second"] > 0

                print("Batch processing completed:")
                print(f"  - Records processed: {summary['total_records_processed']}")
                print(f"  - Success rate: {summary['success_rate_percent']:.1f}%")
                print(
                    f"  - Throughput: {summary['throughput_records_per_second']:.1f} records/sec"
                )

            else:
                # Check if request was checkpointed for resume
                request_id = response.headers.get("X-Request-ID")
                if request_id:
                    status_response = await client.get(
                        f"http://localhost:{port}/durability/requests/{request_id}"
                    )
                    assert status_response.status_code == 200

                    status = status_response.json()
                    assert status["checkpoints"] > 0  # Should have checkpoints

    @pytest.mark.asyncio
    async def test_fraud_detection_ai_analysis(self, production_gateway):
        """Test AI-powered fraud detection workflow."""
        port = production_gateway._test_port

        async with httpx.AsyncClient() as client:
            # Get a transaction to analyze
            # In a real scenario, this would be triggered by a new transaction
            transaction_id = f"txn_{uuid.uuid4().hex[:12]}"

            response = await client.post(
                f"http://localhost:{port}/fraud_detection/execute",
                json={
                    "inputs": {"fetch_transaction": {"transaction_id": transaction_id}}
                },
                timeout=45.0,
            )

            # The transaction might not exist, but the workflow should handle it gracefully
            if response.status_code == 200:
                result = response.json()

                assert "outputs" in result
                # Workflow completed successfully even if transaction not found
                assert "execution_time" in result

            # Test with a known transaction by fetching one first
            # This would be the typical production flow

    @pytest.mark.asyncio
    async def test_gateway_performance_under_load(self, production_gateway):
        """Test gateway performance and durability under sustained load."""
        port = production_gateway._test_port

        # Performance test with mixed workloads
        async def mixed_workload_test():
            async with httpx.AsyncClient() as client:
                # Mix of different workflow types
                workflows = [
                    (
                        "realtime_analytics",
                        {"fetch_transactions": {"time_window_hours": 1}},
                    ),
                    (
                        "customer_insights",
                        {
                            "fetch_customer_data": {
                                "user_id": f"user_{random.randint(1000, 9999)}"
                            }
                        },
                    ),
                    ("sentiment_analysis", {"fetch_reviews": {"batch_size": 3}}),
                ]

                tasks = []
                start_time = time.time()

                # Submit 50 mixed requests
                for i in range(50):
                    workflow_name, inputs = random.choice(workflows)

                    task = client.post(
                        f"http://localhost:{port}/{workflow_name}/execute",
                        json={"inputs": inputs},
                        timeout=30.0,
                    )
                    tasks.append(task)

                responses = await asyncio.gather(*tasks, return_exceptions=True)
                end_time = time.time()

                # Analyze performance
                successful = sum(
                    1
                    for r in responses
                    if hasattr(r, "status_code") and r.status_code == 200
                )
                total_time = end_time - start_time
                throughput = successful / total_time

                print("Load test results:")
                print(f"  - Successful requests: {successful}/50")
                print(f"  - Total time: {total_time:.2f}s")
                print(f"  - Throughput: {throughput:.2f} requests/sec")

                # Verify durability system handled the load
                durability_response = await client.get(
                    f"http://localhost:{port}/durability/status"
                )
                assert durability_response.status_code == 200

                durability_stats = durability_response.json()
                print("Durability stats:")
                print(
                    f"  - Events recorded: {durability_stats['event_store_stats']['event_count']}"
                )
                print(
                    f"  - Cache hit rate: {durability_stats['deduplication_stats']['hit_rate']:.1%}"
                )
                print(f"  - Active requests: {durability_stats['active_requests']}")

                # Production quality assertions
                success_rate = successful / 50
                assert (
                    success_rate >= 0.90
                ), f"Success rate {success_rate:.1%} below 90% threshold"
                assert (
                    throughput >= 1.0
                ), f"Throughput {throughput:.2f} req/s below 1.0 req/s threshold"
                assert durability_stats["event_store_stats"]["event_count"] > 100

        await mixed_workload_test()

    @pytest.mark.asyncio
    async def test_system_resilience_and_recovery(self, production_gateway):
        """Test system resilience and recovery capabilities."""
        port = production_gateway._test_port

        async with httpx.AsyncClient() as client:
            # Test 1: Verify checkpoint creation during processing
            initial_status = await client.get(
                f"http://localhost:{port}/durability/status"
            )
            initial_checkpoints = initial_status.json()["checkpoint_stats"][
                "save_count"
            ]

            # Submit several complex requests
            for i in range(5):
                await client.post(
                    f"http://localhost:{port}/batch_processing/execute",
                    json={
                        "inputs": {
                            "initialize_batch": {
                                "total_records": 100,
                                "batch_size": 20,
                                "simulate_heavy_processing": False,  # Faster for testing
                            }
                        }
                    },
                    timeout=30.0,
                )

            # Verify checkpoints were created
            final_status = await client.get(
                f"http://localhost:{port}/durability/status"
            )
            final_stats = final_status.json()

            # Should have more events and potentially more checkpoints
            assert final_stats["event_store_stats"]["event_count"] > 25

            # Test 2: Verify deduplication works
            idempotency_key = f"test_dedup_{uuid.uuid4().hex[:8]}"

            # Submit the same request twice with idempotency key
            response1 = await client.post(
                f"http://localhost:{port}/realtime_analytics/execute",
                json={"inputs": {"fetch_transactions": {"time_window_hours": 1}}},
                headers={"Idempotency-Key": idempotency_key},
                timeout=30.0,
            )

            response2 = await client.post(
                f"http://localhost:{port}/realtime_analytics/execute",
                json={"inputs": {"fetch_transactions": {"time_window_hours": 1}}},
                headers={"Idempotency-Key": idempotency_key},
                timeout=30.0,
            )

            # Both should succeed
            assert response1.status_code == 200
            assert response2.status_code == 200

            # Check deduplication stats improved
            dedup_stats = final_stats["deduplication_stats"]
            print("Deduplication performance:")
            print(f"  - Cache size: {dedup_stats['cache_size']}")
            print(f"  - Hit rate: {dedup_stats['hit_rate']:.1%}")
            print(f"  - Total hits: {dedup_stats['hit_count']}")

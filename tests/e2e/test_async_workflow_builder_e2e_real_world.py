"""
End-to-end tests for AsyncWorkflowBuilder with real infrastructure.

Tests complete real-world scenarios using Docker infrastructure, Ollama,
and actual external services to validate production readiness.
"""

import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
import asyncpg
import pytest
import pytest_asyncio

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from kailash.resources.factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
)
from kailash.resources.registry import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncPatterns, AsyncWorkflowBuilder
from tests.utils.docker_config import DATABASE_CONFIG, OLLAMA_CONFIG, REDIS_CONFIG


@pytest.mark.integration
@pytest.mark.requires_infrastructure
@pytest.mark.requires_ollama
@pytest.mark.slow
class TestAsyncWorkflowBuilderE2ERealWorld:
    """End-to-end tests with real infrastructure and AI integration."""

    @pytest_asyncio.fixture(scope="class")
    async def infrastructure_setup(self):
        if redis is None:
            pytest.skip("Redis package not available")
        """Setup real infrastructure connections for E2E tests."""
        # Test database connection
        db_conn = await asyncpg.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            database=DATABASE_CONFIG["database"],
        )

        # Test Redis connection
        redis_client = redis.Redis(
            host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"], decode_responses=True
        )
        await redis_client.ping()

        # Test Ollama connection
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{OLLAMA_CONFIG['host']}/api/tags") as response:
                    ollama_available = response.status == 200
                    models = (
                        await response.json() if ollama_available else {"models": []}
                    )
            except:
                ollama_available = False
                models = {"models": []}

        infrastructure = {
            "database": db_conn,
            "redis": redis_client,
            "ollama_available": ollama_available,
            "available_models": [m["name"] for m in models.get("models", [])],
        }

        yield infrastructure

        # Cleanup
        await db_conn.close()
        await redis_client.close()

    @pytest_asyncio.fixture
    async def real_resource_registry(self, infrastructure_setup):
        """Create resource registry with real infrastructure connections."""
        registry = ResourceRegistry()

        # Real database pool
        db_factory = DatabasePoolFactory(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            database=DATABASE_CONFIG["database"],
            min_size=2,
            max_size=10,
        )
        registry.register_factory("production_db", db_factory)

        # Real HTTP client
        http_factory = HttpClientFactory(
            timeout=aiohttp.ClientTimeout(total=60), connection_limit=20
        )
        registry.register_factory("http_client", http_factory)

        # Real Redis cache
        cache_factory = CacheFactory(
            backend="redis", host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"]
        )
        registry.register_factory("production_cache", cache_factory)

        return registry

    @pytest.mark.asyncio
    async def test_ai_powered_data_analysis_pipeline(
        self, real_resource_registry, infrastructure_setup
    ):
        """Test: Complete AI-powered data analysis pipeline with Ollama."""

        if not infrastructure_setup["ollama_available"]:
            pytest.skip("Ollama not available for AI testing")

        if not any(
            "llama" in model.lower()
            for model in infrastructure_setup["available_models"]
        ):
            pytest.skip("No suitable LLM model available in Ollama")

        # Select an available model
        available_llm = next(
            (
                model
                for model in infrastructure_setup["available_models"]
                if "llama" in model.lower()
            ),
            (
                infrastructure_setup["available_models"][0]
                if infrastructure_setup["available_models"]
                else None
            ),
        )

        if not available_llm:
            pytest.skip("No LLM models available")

        builder = AsyncWorkflowBuilder(
            "ai_data_analysis_pipeline", resource_registry=real_resource_registry
        )

        # Add all resources
        builder.with_database("production_db", **DATABASE_CONFIG)
        builder.with_http_client("http_client")
        builder.with_cache("production_cache", **REDIS_CONFIG)

        # Step 1: Create and populate analysis dataset
        builder.add_async_code(
            "setup_analysis_data",
            """
            import random
            import json
            from datetime import datetime, timedelta

            db = await get_resource("production_db")

            # Create tables for analysis
            async with db.acquire() as conn:
                # Sales data table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS sales_data (
                        id SERIAL PRIMARY KEY,
                        product_name VARCHAR(100),
                        category VARCHAR(50),
                        sales_amount DECIMAL(10,2),
                        units_sold INTEGER,
                        sale_date DATE,
                        region VARCHAR(50),
                        customer_segment VARCHAR(50),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Clear existing data
                await conn.execute('DELETE FROM sales_data')

                # Generate realistic sales data
                products = [
                    ("Laptop Pro", "Electronics"), ("Office Chair", "Furniture"),
                    ("Coffee Maker", "Appliances"), ("Wireless Headphones", "Electronics"),
                    ("Standing Desk", "Furniture"), ("Smart Watch", "Electronics"),
                    ("Blender", "Appliances"), ("Monitor", "Electronics"),
                    ("Bookshelf", "Furniture"), ("Air Purifier", "Appliances")
                ]

                regions = ["North", "South", "East", "West", "Central"]
                segments = ["Enterprise", "SMB", "Consumer", "Education"]

                # Insert 1000 sales records over the past 90 days
                base_date = datetime.now() - timedelta(days=90)

                for i in range(1000):
                    product_name, category = random.choice(products)

                    # Realistic pricing based on category
                    if category == "Electronics":
                        base_price = random.uniform(200, 2000)
                    elif category == "Furniture":
                        base_price = random.uniform(150, 1200)
                    else:  # Appliances
                        base_price = random.uniform(50, 800)

                    units = random.randint(1, 10)
                    total_amount = base_price * units

                    sale_date = base_date + timedelta(days=random.randint(0, 89))
                    region = random.choice(regions)
                    segment = random.choice(segments)

                    await conn.execute('''
                        INSERT INTO sales_data
                        (product_name, category, sales_amount, units_sold, sale_date, region, customer_segment)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ''', product_name, category, total_amount, units, sale_date, region, segment)

                # Get summary stats
                total_records = await conn.fetchval('SELECT COUNT(*) FROM sales_data')
                total_revenue = await conn.fetchval('SELECT SUM(sales_amount) FROM sales_data')

                result = {
                    "setup_complete": True,
                    "total_records": total_records,
                    "total_revenue": float(total_revenue),
                    "analysis_ready": True,
                    "data_period_days": 90
                }
            """,
        )

        # Step 2: Extract and aggregate data for analysis
        builder.add_async_code(
            "extract_analysis_data",
            """
            db = await get_resource("production_db")

            async with db.acquire() as conn:
                # Sales by category
                category_sales = await conn.fetch('''
                    SELECT category,
                           COUNT(*) as transaction_count,
                           SUM(sales_amount) as total_revenue,
                           SUM(units_sold) as total_units,
                           AVG(sales_amount) as avg_transaction_value
                    FROM sales_data
                    GROUP BY category
                    ORDER BY total_revenue DESC
                ''')

                # Sales by region
                region_sales = await conn.fetch('''
                    SELECT region,
                           COUNT(*) as transaction_count,
                           SUM(sales_amount) as total_revenue,
                           AVG(sales_amount) as avg_transaction_value
                    FROM sales_data
                    GROUP BY region
                    ORDER BY total_revenue DESC
                ''')

                # Monthly trends
                monthly_trends = await conn.fetch('''
                    SELECT DATE_TRUNC('month', sale_date) as month,
                           COUNT(*) as transaction_count,
                           SUM(sales_amount) as total_revenue,
                           SUM(units_sold) as total_units
                    FROM sales_data
                    GROUP BY DATE_TRUNC('month', sale_date)
                    ORDER BY month
                ''')

                # Top products
                top_products = await conn.fetch('''
                    SELECT product_name,
                           COUNT(*) as transaction_count,
                           SUM(sales_amount) as total_revenue,
                           SUM(units_sold) as total_units
                    FROM sales_data
                    GROUP BY product_name
                    ORDER BY total_revenue DESC
                    LIMIT 10
                ''')

                # Customer segment analysis
                segment_analysis = await conn.fetch('''
                    SELECT customer_segment,
                           COUNT(*) as transaction_count,
                           SUM(sales_amount) as total_revenue,
                           AVG(sales_amount) as avg_transaction_value,
                           COUNT(DISTINCT product_name) as unique_products
                    FROM sales_data
                    GROUP BY customer_segment
                    ORDER BY total_revenue DESC
                ''')

                result = {
                    "category_performance": [dict(row) for row in category_sales],
                    "regional_performance": [dict(row) for row in region_sales],
                    "monthly_trends": [dict(row) for row in monthly_trends],
                    "top_products": [dict(row) for row in top_products],
                    "segment_analysis": [dict(row) for row in segment_analysis],
                    "data_extracted_at": time.time()
                }
            """,
        )

        # Step 3: Generate AI-powered insights using Ollama
        builder.add_async_code(
            "generate_ai_insights",
            f"""
            import json

            http = await get_resource("http_client")

            # Prepare data summary for AI analysis
            data_summary = {{
                "total_categories": len(analysis_data["category_performance"]),
                "total_regions": len(analysis_data["regional_performance"]),
                "top_category": analysis_data["category_performance"][0] if analysis_data["category_performance"] else None,
                "top_region": analysis_data["regional_performance"][0] if analysis_data["regional_performance"] else None,
                "top_product": analysis_data["top_products"][0] if analysis_data["top_products"] else None,
                "monthly_trend_count": len(analysis_data["monthly_trends"])
            }}

            # Create analysis prompt
            top_cat = data_summary["top_category"]["category"] if data_summary["top_category"] else "N/A"
            top_cat_rev = data_summary["top_category"]["total_revenue"] if data_summary["top_category"] else 0
            top_reg = data_summary["top_region"]["region"] if data_summary["top_region"] else "N/A"
            top_reg_rev = data_summary["top_region"]["total_revenue"] if data_summary["top_region"] else 0
            top_prod = data_summary["top_product"]["product_name"] if data_summary["top_product"] else "N/A"
            top_prod_units = data_summary["top_product"]["total_units"] if data_summary["top_product"] else 0

            prompt = "Analyze the following sales data and provide business insights:\\n\\n"
            prompt += f"Top Category: {top_cat}\\n"
            prompt += f"Revenue: ${top_cat_rev:,.2f}\\n\\n"
            prompt += f"Top Region: {top_reg}\\n"
            prompt += f"Revenue: ${top_reg_rev:,.2f}\\n\\n"
            prompt += f"Top Product: {top_prod}\\n"
            prompt += f"Units Sold: {top_prod_units}\\n\\n"
            prompt += "Please provide:\\n"
            prompt += "1. Key business insights (2-3 bullet points)\\n"
            prompt += "2. Recommendations for improvement (2-3 bullet points)\\n"
            prompt += "3. Areas of concern or opportunity (1-2 bullet points)\\n\\n"
            prompt += "Keep response concise and business-focused."

            # Call Ollama API
            ollama_request = {{
                "model": "{available_llm}",
                "prompt": prompt,
                "stream": False
            }}

            try:
                async with http.post(
                    "{OLLAMA_CONFIG['host']}/api/generate",
                    json=ollama_request,
                    timeout=60
                ) as response:
                    if response.status == 200:
                        ollama_response = await response.json()
                        ai_insights = ollama_response.get("response", "AI analysis unavailable")
                        ai_success = True
                    else:
                        ai_insights = f"AI service error: HTTP {{response.status}}"
                        ai_success = False
            except Exception as e:
                ai_insights = f"AI service error: {{str(e)}}"
                ai_success = False

            # Parse insights into structured format
            insights_structured = {{
                "ai_analysis": ai_insights,
                "ai_success": ai_success,
                "model_used": "{available_llm}",
                "analysis_timestamp": time.time(),
                "data_summary": data_summary
            }}

            result = {{
                "ai_insights": insights_structured,
                "raw_analysis_data": analysis_data,
                "insight_generation_complete": True
            }}
            """,
        )

        # Step 4: Cache insights and create final report
        AsyncPatterns.cache_aside(
            builder,
            "cache_check_insights",
            "generate_final_report",
            "cache_store_insights",
            """
            # Generate comprehensive business report
            report = {
                "executive_summary": {
                    "report_date": time.time(),
                    "analysis_period": "Last 90 days",
                    "total_revenue": sum(cat["total_revenue"] for cat in insights_data["raw_analysis_data"]["category_performance"]),
                    "total_transactions": sum(cat["transaction_count"] for cat in insights_data["raw_analysis_data"]["category_performance"]),
                    "ai_insights_available": insights_data["ai_insights"]["ai_success"]
                },
                "performance_highlights": {
                    "top_performing_category": insights_data["raw_analysis_data"]["category_performance"][0] if insights_data["raw_analysis_data"]["category_performance"] else None,
                    "top_performing_region": insights_data["raw_analysis_data"]["regional_performance"][0] if insights_data["raw_analysis_data"]["regional_performance"] else None,
                    "best_selling_product": insights_data["raw_analysis_data"]["top_products"][0] if insights_data["raw_analysis_data"]["top_products"] else None
                },
                "ai_analysis": insights_data["ai_insights"]["ai_analysis"] if insights_data["ai_insights"]["ai_success"] else "AI analysis not available",
                "detailed_metrics": {
                    "category_breakdown": insights_data["raw_analysis_data"]["category_performance"],
                    "regional_breakdown": insights_data["raw_analysis_data"]["regional_performance"],
                    "segment_analysis": insights_data["raw_analysis_data"]["segment_analysis"]
                },
                "report_metadata": {
                    "generated_by": "Kailash AsyncWorkflowBuilder",
                    "ai_model": insights_data["ai_insights"]["model_used"],
                    "data_freshness": "Real-time",
                    "report_version": "1.0"
                }
            }

            result = {
                "business_report": report,
                "report_ready": True,
                "cache_recommended": True
            }
            """,
            cache_resource="production_cache",
            cache_key_template="business_report_{report_date}",
            ttl_seconds=3600,  # 1 hour cache
        )

        # Step 5: Store final results and generate alerts
        builder.add_async_code(
            "finalize_and_alert",
            """
            db = await get_resource("production_db")

            # Store report in database
            async with db.acquire() as conn:
                # Create reports table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS business_reports (
                        id SERIAL PRIMARY KEY,
                        report_date TIMESTAMP DEFAULT NOW(),
                        report_data JSONB,
                        ai_insights_included BOOLEAN,
                        total_revenue DECIMAL(15,2),
                        total_transactions INTEGER
                    )
                ''')

                # Insert report
                report_id = await conn.fetchval('''
                    INSERT INTO business_reports
                    (report_data, ai_insights_included, total_revenue, total_transactions)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                ''',
                json.dumps(final_report["business_report"]),
                final_report["business_report"]["executive_summary"]["ai_insights_available"],
                final_report["business_report"]["executive_summary"]["total_revenue"],
                final_report["business_report"]["executive_summary"]["total_transactions"]
                )

                # Generate alerts based on performance
                alerts = []
                exec_summary = final_report["business_report"]["executive_summary"]

                # Revenue threshold alert
                if exec_summary["total_revenue"] < 100000:  # Less than $100k
                    alerts.append({
                        "type": "revenue_low",
                        "severity": "medium",
                        "message": f"Revenue below target: ${exec_summary['total_revenue']:,.2f}"
                    })
                elif exec_summary["total_revenue"] > 500000:  # More than $500k
                    alerts.append({
                        "type": "revenue_high",
                        "severity": "positive",
                        "message": f"Excellent revenue performance: ${exec_summary['total_revenue']:,.2f}"
                    })

                # Transaction volume alert
                if exec_summary["total_transactions"] < 500:
                    alerts.append({
                        "type": "volume_low",
                        "severity": "medium",
                        "message": f"Transaction volume below expected: {exec_summary['total_transactions']}"
                    })

                # AI insights alert
                if not exec_summary["ai_insights_available"]:
                    alerts.append({
                        "type": "ai_unavailable",
                        "severity": "low",
                        "message": "AI insights could not be generated"
                    })

                result = {
                    "report_stored": True,
                    "report_id": report_id,
                    "alerts_generated": alerts,
                    "pipeline_complete": True,
                    "final_summary": {
                        "total_revenue": exec_summary["total_revenue"],
                        "total_transactions": exec_summary["total_transactions"],
                        "ai_enhanced": exec_summary["ai_insights_available"],
                        "alerts_count": len(alerts)
                    }
                }
            """,
        )

        # Connect the complete pipeline
        builder.add_connection(
            "setup_analysis_data", None, "extract_analysis_data", "setup_result"
        )
        builder.add_connection(
            "extract_analysis_data", None, "generate_ai_insights", "analysis_data"
        )
        builder.add_connection(
            "generate_ai_insights", None, "cache_check_insights", "insights_data"
        )
        builder.add_connection(
            "cache_store_insights", None, "finalize_and_alert", "final_report"
        )

        # Build and execute the complete AI pipeline
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=real_resource_registry)

        start_time = time.time()
        result = await runtime.execute_workflow_async(
            workflow, {"report_date": "2024-01-01"}
        )
        end_time = time.time()

        # Comprehensive verification
        assert (
            result["status"] == "success"
        ), f"Pipeline failed: {result.get('error', 'Unknown error')}"

        # Verify each step
        setup_result = result["results"]["setup_analysis_data"]
        assert setup_result["setup_complete"] is True
        assert setup_result["total_records"] == 1000
        assert setup_result["total_revenue"] > 0

        extract_result = result["results"]["extract_analysis_data"]
        assert len(extract_result["category_performance"]) > 0
        assert len(extract_result["regional_performance"]) > 0
        assert len(extract_result["top_products"]) > 0

        ai_result = result["results"]["generate_ai_insights"]
        assert "ai_insights" in ai_result
        # AI might fail, but we should handle it gracefully

        final_result = result["results"]["finalize_and_alert"]
        assert final_result["pipeline_complete"] is True
        assert final_result["report_stored"] is True
        assert "final_summary" in final_result

        # Performance verification
        execution_time = end_time - start_time
        assert execution_time < 120, f"Pipeline too slow: {execution_time:.2f}s"

        # Verify data quality
        assert (
            final_result["final_summary"]["total_revenue"] > 50000
        )  # Reasonable revenue
        assert final_result["final_summary"]["total_transactions"] == 1000

        print(f"✅ AI-powered pipeline completed in {execution_time:.2f}s")
        print(
            f"   Revenue analyzed: ${final_result['final_summary']['total_revenue']:,.2f}"
        )
        print(
            f"   AI insights: {'✓' if final_result['final_summary']['ai_enhanced'] else '✗'}"
        )
        print(f"   Alerts generated: {final_result['final_summary']['alerts_count']}")

    @pytest.mark.asyncio
    async def test_real_time_data_streaming_pipeline(
        self, real_resource_registry, infrastructure_setup
    ):
        """Test: Real-time data streaming and processing pipeline."""

        builder = AsyncWorkflowBuilder(
            "realtime_streaming_pipeline", resource_registry=real_resource_registry
        )

        # Add resources
        builder.with_database("production_db", **DATABASE_CONFIG)
        builder.with_cache("production_cache", **REDIS_CONFIG)
        builder.with_http_client("http_client")

        # Step 1: Setup streaming infrastructure
        builder.add_async_code(
            "setup_streaming",
            """
            import asyncio
            import random
            import json
            from datetime import datetime

            db = await get_resource("production_db")
            cache = await get_resource("production_cache")

            # Create streaming tables
            async with db.acquire() as conn:
                # Events table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS streaming_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(50),
                        user_id VARCHAR(50),
                        session_id VARCHAR(100),
                        event_data JSONB,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Real-time metrics table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS realtime_metrics (
                        id SERIAL PRIMARY KEY,
                        metric_name VARCHAR(100),
                        metric_value DECIMAL(15,4),
                        tags JSONB,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Clear existing data
                await conn.execute('DELETE FROM streaming_events')
                await conn.execute('DELETE FROM realtime_metrics')

            # Initialize Redis streams
            stream_key = "events_stream"
            await cache.delete(stream_key)  # Clear existing stream

            result = {
                "streaming_setup_complete": True,
                "stream_key": stream_key,
                "tables_created": True,
                "ready_for_streaming": True
            }
            """,
        )

        # Step 2: Generate real-time event stream
        builder.add_parallel_map(
            "generate_event_stream",
            """
async def process_item(batch_id):
    import random
    import json
    import uuid
    from datetime import datetime

    cache = await get_resource("production_cache")

    # Event types with different frequencies
    event_types = [
        ("page_view", 0.4),
        ("click", 0.25),
        ("purchase", 0.1),
        ("login", 0.15),
        ("logout", 0.1)
    ]

    events_generated = []

    # Generate 50 events per batch
    for i in range(50):
        # Select event type based on probability
        rand = random.random()
        cumulative = 0
        selected_event = "page_view"

        for event_type, prob in event_types:
            cumulative += prob
            if rand <= cumulative:
                selected_event = event_type
                break

    # Generate realistic event data
    user_id = f"user_{random.randint(1, 1000)}"
    session_id = str(uuid.uuid4())[:8]

    event_data = {
        "timestamp": datetime.now().isoformat(),
        "user_agent": random.choice(["Chrome", "Firefox", "Safari", "Edge"]),
        "platform": random.choice(["web", "mobile", "tablet"]),
        "location": random.choice(["US", "UK", "CA", "AU", "DE"])
    }

    # Add event-specific data
    if selected_event == "page_view":
        event_data["page"] = random.choice(["/home", "/products", "/about", "/contact"])
        event_data["duration"] = random.randint(10, 300)  # seconds
    elif selected_event == "click":
        event_data["element"] = random.choice(["button", "link", "image", "menu"])
        event_data["coordinates"] = {"x": random.randint(0, 1920), "y": random.randint(0, 1080)}
    elif selected_event == "purchase":
        event_data["product_id"] = f"prod_{random.randint(1, 100)}"
        event_data["amount"] = round(random.uniform(10, 500), 2)
        event_data["currency"] = "USD"

    event = {
        "event_type": selected_event,
        "user_id": user_id,
        "session_id": session_id,
        "event_data": event_data
    }

    # Add to Redis stream
    await cache.xadd("events_stream", event)
    events_generated.append(event)

    # Small delay to simulate real-time streaming
    await asyncio.sleep(0.01)

    return {
    "batch_id": batch_id,
    "events_count": len(events_generated),
    "event_types": list(set(e["event_type"] for e in events_generated)),
    "generation_complete": True
    }
            """,
            max_workers=5,
            timeout_per_item=30,
            continue_on_error=True,
        )

        # Step 3: Process streaming data in real-time
        AsyncPatterns.batch_processor(
            builder,
            "process_stream_batches",
            """
            import json
            from collections import defaultdict, Counter

            db = await get_resource("production_db")
            cache = await get_resource("production_cache")

            batch_results = []

            # Process each event batch
            for batch_result in items:
                if not batch_result.get("generation_complete"):
                    continue

                # Read events from Redis stream for this batch
                stream_data = await cache.xread({"events_stream": "0"}, count=100, block=1000)

                events_processed = 0
                event_stats = Counter()
                user_activity = defaultdict(int)
                purchase_total = 0

                # Process stream data
                for stream_name, messages in stream_data:
                    for message_id, fields in messages:
                        event_type = fields.get("event_type", "unknown")
                        user_id = fields.get("user_id", "anonymous")

                        event_stats[event_type] += 1
                        user_activity[user_id] += 1
                        events_processed += 1

                        # Track purchase amounts
                        if event_type == "purchase":
                            event_data = json.loads(fields.get("event_data", "{}"))
                            purchase_total += event_data.get("amount", 0)

                        # Store event in database
                        async with db.acquire() as conn:
                            await conn.execute('''
                                INSERT INTO streaming_events
                                (event_type, user_id, session_id, event_data)
                                VALUES ($1, $2, $3, $4)
                            ''',
                            event_type,
                            user_id,
                            fields.get("session_id"),
                            fields.get("event_data")
                            )

                batch_results.append({
                    "batch_id": batch_result["batch_id"],
                    "events_processed": events_processed,
                    "event_type_distribution": dict(event_stats),
                    "unique_users": len(user_activity),
                    "total_purchase_amount": purchase_total
                })

            # Calculate real-time metrics
            total_events = sum(b["events_processed"] for b in batch_results)
            total_users = len(set(user for batch in batch_results for user in user_activity.keys()))
            total_revenue = sum(b["total_purchase_amount"] for b in batch_results)

            # Store metrics in database
            async with db.acquire() as conn:
                metrics_to_store = [
                    ("events_per_second", total_events / max(1, len(batch_results))),
                    ("active_users", total_users),
                    ("revenue_per_minute", total_revenue),
                    ("conversion_rate", (sum(b["event_type_distribution"].get("purchase", 0) for b in batch_results) / max(1, total_events)) * 100)
                ]

                for metric_name, metric_value in metrics_to_store:
                    await conn.execute('''
                        INSERT INTO realtime_metrics (metric_name, metric_value, tags)
                        VALUES ($1, $2, $3)
                    ''', metric_name, metric_value, json.dumps({"pipeline": "streaming", "timestamp": time.time()}))
            """,
            batch_size=10,
            flush_interval=5.0,
        )

        # Step 4: Real-time analytics and alerting
        builder.add_async_code(
            "realtime_analytics",
            """
            db = await get_resource("production_db")
            cache = await get_resource("production_cache")

            async with db.acquire() as conn:
                # Get recent metrics
                recent_metrics = await conn.fetch('''
                    SELECT metric_name, metric_value, timestamp
                    FROM realtime_metrics
                    WHERE timestamp >= NOW() - INTERVAL '5 minutes'
                    ORDER BY timestamp DESC
                ''')

                # Get event summary
                event_summary = await conn.fetch('''
                    SELECT event_type, COUNT(*) as count
                    FROM streaming_events
                    WHERE timestamp >= NOW() - INTERVAL '5 minutes'
                    GROUP BY event_type
                    ORDER BY count DESC
                ''')

                # Calculate real-time KPIs
                total_events = await conn.fetchval('''
                    SELECT COUNT(*) FROM streaming_events
                    WHERE timestamp >= NOW() - INTERVAL '5 minutes'
                ''')

                unique_users = await conn.fetchval('''
                    SELECT COUNT(DISTINCT user_id) FROM streaming_events
                    WHERE timestamp >= NOW() - INTERVAL '5 minutes'
                ''')

                purchase_revenue = await conn.fetchval('''
                    SELECT COALESCE(SUM((event_data->>'amount')::DECIMAL), 0)
                    FROM streaming_events
                    WHERE event_type = 'purchase'
                    AND timestamp >= NOW() - INTERVAL '5 minutes'
                ''') or 0

                # Generate alerts based on thresholds
                alerts = []

                if total_events < 100:  # Low activity
                    alerts.append({
                        "type": "low_activity",
                        "severity": "warning",
                        "message": f"Low event volume: {total_events} events in last 5 minutes"
                    })

                if unique_users < 10:  # Low user engagement
                    alerts.append({
                        "type": "low_engagement",
                        "severity": "warning",
                        "message": f"Low user engagement: {unique_users} unique users"
                    })

                if purchase_revenue > 1000:  # High revenue spike
                    alerts.append({
                        "type": "revenue_spike",
                        "severity": "positive",
                        "message": f"Revenue spike detected: ${purchase_revenue:.2f} in 5 minutes"
                    })

                # Store analytics in cache for dashboard
                analytics_data = {
                    "timestamp": time.time(),
                    "kpis": {
                        "total_events": total_events,
                        "unique_users": unique_users,
                        "revenue_5min": float(purchase_revenue),
                        "events_per_user": total_events / max(1, unique_users)
                    },
                    "event_distribution": [dict(row) for row in event_summary],
                    "alerts": alerts,
                    "metrics_history": [dict(row) for row in recent_metrics]
                }

                # Cache for real-time dashboard
                await cache.setex("realtime_analytics", 60, json.dumps(analytics_data))

                result = {
                    "analytics_complete": True,
                    "realtime_kpis": analytics_data["kpis"],
                    "alerts_generated": len(alerts),
                    "dashboard_updated": True,
                    "streaming_health": "healthy" if len(alerts) == 0 else "degraded" if any(a["severity"] == "warning" for a in alerts) else "critical"
                }
            """,
        )

        # Connect the streaming pipeline
        builder.add_connection(
            "setup_streaming", None, "generate_event_stream", "stream_config"
        )
        builder.add_connection(
            "generate_event_stream", "results", "process_stream_batches", "items"
        )
        builder.add_connection(
            "process_stream_batches", None, "realtime_analytics", "batch_results"
        )

        # Execute the streaming pipeline
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=real_resource_registry)

        # Generate 10 batches of events (500 events total)
        start_time = time.time()
        result = await runtime.execute_workflow_async(
            workflow, {"batch_count": list(range(10))}
        )
        end_time = time.time()

        # Verify streaming pipeline
        assert result["status"] == "success"

        # Check setup
        setup_result = result["results"]["setup_streaming"]
        assert setup_result["streaming_setup_complete"] is True

        # Check event generation
        generation_result = result["results"]["generate_event_stream"]
        assert "results" in generation_result
        assert (
            generation_result["statistics"]["successful"] >= 8
        )  # Most batches should succeed

        # Check processing
        processing_result = result["results"]["process_stream_batches"]
        assert processing_result["processed_count"] > 0

        # Check analytics
        analytics_result = result["results"]["realtime_analytics"]
        assert analytics_result["analytics_complete"] is True
        assert "realtime_kpis" in analytics_result
        assert (
            analytics_result["realtime_kpis"]["total_events"] > 400
        )  # Should process most events
        assert analytics_result["dashboard_updated"] is True

        # Performance check
        execution_time = end_time - start_time
        assert (
            execution_time < 90
        ), f"Streaming pipeline too slow: {execution_time:.2f}s"

        print(f"✅ Streaming pipeline completed in {execution_time:.2f}s")
        print(
            f"   Events processed: {analytics_result['realtime_kpis']['total_events']}"
        )
        print(f"   Unique users: {analytics_result['realtime_kpis']['unique_users']}")
        print(f"   Revenue: ${analytics_result['realtime_kpis']['revenue_5min']:.2f}")
        print(f"   Health: {analytics_result['streaming_health']}")

    @pytest.mark.asyncio
    async def test_production_deployment_workflow(
        self, real_resource_registry, infrastructure_setup
    ):
        """Test: Production deployment and monitoring workflow."""

        builder = AsyncWorkflowBuilder(
            "production_deployment_pipeline", resource_registry=real_resource_registry
        )

        # Add resources
        builder.with_database("production_db", **DATABASE_CONFIG)
        builder.with_cache("production_cache", **REDIS_CONFIG)
        builder.with_http_client("http_client")

        # Step 1: Pre-deployment health checks
        AsyncPatterns.parallel_fetch(
            builder,
            "pre_deployment_checks",
            {
                "database_health": """
db = await get_resource("production_db")

try:
    async with db.acquire() as conn:
                        # Check database connectivity
                        db_version = await conn.fetchval('SELECT version()')

                        # Check table accessibility
                        table_count = await conn.fetchval('''
                            SELECT COUNT(*) FROM information_schema.tables
                            WHERE table_schema = 'public'
                        ''')

                        # Check recent activity
                        recent_activity = await conn.fetchval('''
                            SELECT COUNT(*) FROM pg_stat_activity
                            WHERE state = 'active'
                        ''')

                        result = {
                            "status": "healthy",
                            "database_version": db_version,
                            "accessible_tables": table_count,
                            "active_connections": recent_activity,
                            "response_time_ms": 50  # Simulated
                        }
                except Exception as e:
                    result = {
                        "status": "unhealthy",
                        "error": str(e),
                        "response_time_ms": 5000
                    }
                """,
                "cache_health": """
cache = await get_resource("production_cache")

                try:
                    # Test cache operations
                    test_key = "health_check_" + str(time.time())
                    await cache.set(test_key, "test_value", ex=10)
                    retrieved_value = await cache.get(test_key)
                    await cache.delete(test_key)

                    # Get cache info
                    cache_info = await cache.info()

                    result = {
                        "status": "healthy" if retrieved_value == "test_value" else "unhealthy",
                        "read_write_success": retrieved_value == "test_value",
                        "memory_usage": cache_info.get("used_memory_human", "unknown"),
                        "connected_clients": cache_info.get("connected_clients", 0),
                        "response_time_ms": 10  # Simulated
                    }
                except Exception as e:
                    result = {
                        "status": "unhealthy",
                        "error": str(e),
                        "response_time_ms": 1000
                    }
                """,
                "external_api_health": """
                http = await get_resource("http_client")

                # Test external dependencies
                health_checks = []

                # Test public API (httpbin for demo)
                try:
                    async with http.get("https://httpbin.org/status/200", timeout=10) as response:
                        health_checks.append({
                            "service": "httpbin_api",
                            "status": "healthy" if response.status == 200 else "unhealthy",
                            "response_code": response.status,
                            "response_time_ms": 200  # Simulated
                        })
                except Exception as e:
                    health_checks.append({
                        "service": "httpbin_api",
                        "status": "unhealthy",
                        "error": str(e),
                        "response_time_ms": 5000
                    })

                # Test another service (JSONPlaceholder for demo)
                try:
                    async with http.get("https://jsonplaceholder.typicode.com/posts/1", timeout=10) as response:
                        health_checks.append({
                            "service": "jsonplaceholder_api",
                            "status": "healthy" if response.status == 200 else "unhealthy",
                            "response_code": response.status,
                            "response_time_ms": 150  # Simulated
                        })
                except Exception as e:
                    health_checks.append({
                        "service": "jsonplaceholder_api",
                        "status": "unhealthy",
                        "error": str(e),
                        "response_time_ms": 5000
                    })

                result = {
                    "external_services": health_checks,
                    "all_healthy": all(check["status"] == "healthy" for check in health_checks),
                    "avg_response_time": sum(check["response_time_ms"] for check in health_checks) / len(health_checks)
                }
                """,
            },
            timeout_per_operation=30.0,
            continue_on_error=True,
        )

        # Step 2: Deployment simulation and validation
        builder.add_async_code(
            "simulate_deployment",
            """
            import uuid
            import random

            # Simulate deployment process
            deployment_id = str(uuid.uuid4())[:8]

            # Check if all health checks passed
            health_results = successful if successful else {}

            deployment_status = "ready"
            blocking_issues = []

            # Validate each service
            if "database_health" in health_results:
                db_health = health_results["database_health"]
                if db_health.get("status") != "healthy":
                    deployment_status = "blocked"
                    blocking_issues.append("Database unhealthy")
            else:
                deployment_status = "blocked"
                blocking_issues.append("Database health check failed")

            if "cache_health" in health_results:
                cache_health = health_results["cache_health"]
                if cache_health.get("status") != "healthy":
                    deployment_status = "blocked"
                    blocking_issues.append("Cache unhealthy")
            else:
                deployment_status = "blocked"
                blocking_issues.append("Cache health check failed")

            if "external_api_health" in health_results:
                api_health = health_results["external_api_health"]
                if not api_health.get("all_healthy", False):
                    deployment_status = "warning"  # Non-blocking but concerning
                    blocking_issues.append("Some external APIs unhealthy")

            # Simulate deployment steps
            deployment_steps = [
                {"step": "backup_current", "status": "completed", "duration_ms": 2000},
                {"step": "run_migrations", "status": "completed", "duration_ms": 1500},
                {"step": "update_application", "status": "completed", "duration_ms": 3000},
                {"step": "run_smoke_tests", "status": "completed", "duration_ms": 5000},
                {"step": "update_load_balancer", "status": "completed", "duration_ms": 1000}
            ]

            # Simulate occasional deployment issues
            if random.random() < 0.1:  # 10% chance of deployment issue
                deployment_steps[-2]["status"] = "failed"
                deployment_steps[-2]["error"] = "Smoke test timeout"
                deployment_status = "failed"

            total_deployment_time = sum(step["duration_ms"] for step in deployment_steps)

            result = {
                "deployment_id": deployment_id,
                "deployment_status": deployment_status,
                "blocking_issues": blocking_issues,
                "deployment_steps": deployment_steps,
                "total_deployment_time_ms": total_deployment_time,
                "health_check_summary": {
                    "database": health_results.get("database_health", {}).get("status", "unknown"),
                    "cache": health_results.get("cache_health", {}).get("status", "unknown"),
                    "external_apis": health_results.get("external_api_health", {}).get("all_healthy", False)
                }
            }
            """,
        )

        # Step 3: Post-deployment monitoring
        AsyncPatterns.circuit_breaker(
            builder,
            "post_deployment_monitoring",
            """
            db = await get_resource("production_db")
            cache = await get_resource("production_cache")

            # Store deployment record
            async with db.acquire() as conn:
                # Create deployments table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS deployments (
                        id SERIAL PRIMARY KEY,
                        deployment_id VARCHAR(50) UNIQUE,
                        status VARCHAR(20),
                        deployment_time_ms INTEGER,
                        health_summary JSONB,
                        deployment_steps JSONB,
                        deployed_at TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Insert deployment record
                await conn.execute('''
                    INSERT INTO deployments
                    (deployment_id, status, deployment_time_ms, health_summary, deployment_steps)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (deployment_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    deployment_time_ms = EXCLUDED.deployment_time_ms
                ''',
                deployment_data["deployment_id"],
                deployment_data["deployment_status"],
                deployment_data["total_deployment_time_ms"],
                json.dumps(deployment_data["health_check_summary"]),
                json.dumps(deployment_data["deployment_steps"])
                )

                # Get deployment history
                recent_deployments = await conn.fetch('''
                    SELECT deployment_id, status, deployed_at
                    FROM deployments
                    ORDER BY deployed_at DESC
                    LIMIT 10
                ''')

                # Calculate success rate
                total_deployments = await conn.fetchval('SELECT COUNT(*) FROM deployments')
                successful_deployments = await conn.fetchval('''
                    SELECT COUNT(*) FROM deployments WHERE status = 'ready'
                ''')

                success_rate = successful_deployments / max(1, total_deployments)

                # Generate monitoring alerts
                alerts = []

                if deployment_data["deployment_status"] == "failed":
                    alerts.append({
                        "type": "deployment_failed",
                        "severity": "critical",
                        "message": f"Deployment {deployment_data['deployment_id']} failed"
                    })
                elif deployment_data["deployment_status"] == "blocked":
                    alerts.append({
                        "type": "deployment_blocked",
                        "severity": "high",
                        "message": f"Deployment blocked: {', '.join(deployment_data['blocking_issues'])}"
                    })
                elif deployment_data["total_deployment_time_ms"] > 15000:  # > 15 seconds
                    alerts.append({
                        "type": "slow_deployment",
                        "severity": "medium",
                        "message": f"Deployment took {deployment_data['total_deployment_time_ms']/1000:.1f}s"
                    })

                if success_rate < 0.8:  # Less than 80% success rate
                    alerts.append({
                        "type": "low_success_rate",
                        "severity": "high",
                        "message": f"Deployment success rate: {success_rate:.1%}"
                    })

                # Cache monitoring data
                monitoring_data = {
                    "current_deployment": deployment_data,
                    "deployment_history": [dict(row) for row in recent_deployments],
                    "success_rate": success_rate,
                    "alerts": alerts,
                    "monitoring_timestamp": time.time()
                }

                await cache.setex("deployment_monitoring", 300, json.dumps(monitoring_data))

                result = {
                    "monitoring_complete": True,
                    "deployment_recorded": True,
                    "success_rate": success_rate,
                    "alerts_generated": len(alerts),
                    "monitoring_status": "healthy" if len(alerts) == 0 else "degraded",
                    "deployment_summary": {
                        "id": deployment_data["deployment_id"],
                        "status": deployment_data["deployment_status"],
                        "duration_seconds": deployment_data["total_deployment_time_ms"] / 1000,
                        "issues": deployment_data["blocking_issues"]
                    }
                }
            """,
            failure_threshold=3,
            reset_timeout=60.0,
        )

        # Connect the deployment pipeline
        builder.add_connection(
            "pre_deployment_checks", "successful", "simulate_deployment", "successful"
        )
        builder.add_connection(
            "pre_deployment_checks", "failed", "simulate_deployment", "failed"
        )
        builder.add_connection(
            "simulate_deployment", None, "post_deployment_monitoring", "deployment_data"
        )

        # Execute the deployment pipeline
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=real_resource_registry)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        end_time = time.time()

        # Verify deployment pipeline
        assert result["status"] == "success"

        # Check health checks
        health_result = result["results"]["pre_deployment_checks"]
        assert "successful" in health_result
        assert len(health_result["successful"]) >= 2  # At least database and cache

        # Check deployment simulation
        deployment_result = result["results"]["simulate_deployment"]
        assert "deployment_id" in deployment_result
        assert "deployment_status" in deployment_result
        assert deployment_result["deployment_status"] in [
            "ready",
            "blocked",
            "warning",
            "failed",
        ]

        # Check monitoring
        monitoring_result = result["results"]["post_deployment_monitoring"]
        assert monitoring_result["monitoring_complete"] is True
        assert monitoring_result["deployment_recorded"] is True
        assert "success_rate" in monitoring_result
        assert "_circuit_breaker_info" in monitoring_result

        # Performance check
        execution_time = end_time - start_time
        assert (
            execution_time < 60
        ), f"Deployment pipeline too slow: {execution_time:.2f}s"

        print(f"✅ Deployment pipeline completed in {execution_time:.2f}s")
        print(f"   Deployment ID: {deployment_result['deployment_id']}")
        print(f"   Status: {deployment_result['deployment_status']}")
        print(f"   Duration: {deployment_result['total_deployment_time_ms']/1000:.1f}s")
        print(f"   Success rate: {monitoring_result['success_rate']:.1%}")
        print(f"   Monitoring: {monitoring_result['monitoring_status']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

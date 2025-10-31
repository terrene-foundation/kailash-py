"""End-to-end tests demonstrating real user workflows with connection pooling."""

import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest
from kailash import Workflow
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.nodes.transform.processors import DataTransformer
from kailash.runtime import LocalRuntime


@pytest.mark.e2e
@pytest.mark.asyncio
class TestConnectionPoolUserFlow:
    """End-to-end tests for real user scenarios."""

    @pytest.fixture
    def db_config(self):
        """Database configuration."""
        return {
            "database_type": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5432)),
            "database": os.getenv("POSTGRES_DB", "kailash_test"),
            "user": os.getenv("POSTGRES_USER", "kailash"),
            "password": os.getenv("POSTGRES_PASSWORD", "kailash123"),
            "min_connections": 3,
            "max_connections": 10,
        }

    async def test_data_analytics_workflow(self, db_config):
        """
        User Story: Data analyst needs to run complex analytics queries
        with optimal connection management and AI-powered insights.
        """
        # Create analytics workflow
        workflow = Workflow("analytics_pipeline", "Analytics Pipeline")

        # Add connection pool
        workflow.add_node("db_pool", WorkflowConnectionPool(), **db_config)

        # Initialize pool
        workflow.add_node(
            "init_pool",
            "PythonCodeNode",
            code="""
result = {"operation": "initialize"}
""",
        )

        # Create sample data
        workflow.add_node(
            "setup_data",
            "PythonCodeNode",
            code="""
            # Prepare operations to create sample data
            return {
                "operations": [
                    {
                        "operation": "acquire",
                        "tag": "setup"
                    },
                    {
                        "operation": "execute",
                        "query": '''
                            CREATE TABLE IF NOT EXISTS sales_data (
                                id SERIAL PRIMARY KEY,
                                product_name VARCHAR(100),
                                category VARCHAR(50),
                                sale_date DATE,
                                quantity INTEGER,
                                price DECIMAL(10, 2),
                                region VARCHAR(50)
                            )
                        '''
                    },
                    {
                        "operation": "execute",
                        "query": '''
                            INSERT INTO sales_data (product_name, category, sale_date, quantity, price, region)
                            SELECT
                                'Product ' || (random() * 100)::int,
                                CASE (random() * 3)::int
                                    WHEN 0 THEN 'Electronics'
                                    WHEN 1 THEN 'Clothing'
                                    ELSE 'Home & Garden'
                                END,
                                CURRENT_DATE - ((random() * 365)::int || ' days')::interval,
                                (random() * 50 + 1)::int,
                                (random() * 500 + 10)::numeric(10,2),
                                CASE (random() * 4)::int
                                    WHEN 0 THEN 'North'
                                    WHEN 1 THEN 'South'
                                    WHEN 2 THEN 'East'
                                    ELSE 'West'
                                END
                            FROM generate_series(1, 1000)
                            ON CONFLICT DO NOTHING
                        '''
                    }
                ]
            }
        """,
        )

        # Execute setup operations
        workflow.add_node(
            "execute_setup",
            "PythonCodeNode",
            code="""
            results = []
            conn_id = None

            for op in inputs["operations"]:
                if op["operation"] == "acquire":
                    result = {"operation": "acquire"}
                    conn_id = op.get("tag", "setup")
                elif op["operation"] == "execute":
                    result = {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": op["query"]
                    }
                results.append(result)

            return {"batch_operations": results, "setup_connection": conn_id}
        """,
        )

        # Run analytics queries in parallel
        workflow.add_node(
            "analytics_queries",
            "PythonCodeNode",
            code="""
            # Define analytics queries
            queries = [
                {
                    "name": "sales_by_category",
                    "query": '''
                        SELECT category,
                               COUNT(*) as transaction_count,
                               SUM(quantity) as total_quantity,
                               SUM(quantity * price) as total_revenue,
                               AVG(price) as avg_price
                        FROM sales_data
                        GROUP BY category
                        ORDER BY total_revenue DESC
                    '''
                },
                {
                    "name": "monthly_trends",
                    "query": '''
                        SELECT DATE_TRUNC('month', sale_date) as month,
                               COUNT(*) as transactions,
                               SUM(quantity * price) as revenue
                        FROM sales_data
                        GROUP BY month
                        ORDER BY month DESC
                        LIMIT 12
                    '''
                },
                {
                    "name": "regional_performance",
                    "query": '''
                        SELECT region,
                               COUNT(DISTINCT product_name) as unique_products,
                               SUM(quantity) as units_sold,
                               SUM(quantity * price) as revenue,
                               AVG(quantity * price) as avg_order_value
                        FROM sales_data
                        GROUP BY region
                        ORDER BY revenue DESC
                    '''
                }
            ]

            return {"queries": queries}
        """,
        )

        # Execute queries with connection pool
        workflow.add_node(
            "execute_analytics",
            "PythonCodeNode",
            code="""
            import asyncio

            # We'll need separate connections for parallel execution
            connection_requests = [
                {"operation": "acquire", "query_name": q["name"]}
                for q in inputs["queries"]
            ]

            return {"connection_requests": connection_requests, "queries": inputs["queries"]}
        """,
        )

        # Process query results
        workflow.add_node(
            "process_results",
            "DataTransformer",
            transformations=[
                {"type": "validate", "schema": "query_results"},
                {"type": "add_field", "field": "timestamp", "value": "now()"},
                {
                    "type": "add_field",
                    "field": "analysis_type",
                    "value": "sales_analytics",
                },
            ],
        )

        # Generate AI insights using Ollama
        workflow.add_node(
            "ai_insights",
            LLMAgentNode(),
            provider="ollama",
            model="llama2",
            temperature=0.7,
            system_prompt="""You are a data analyst expert. Analyze the sales data results
            and provide actionable business insights. Focus on trends, anomalies, and recommendations.""",
            prompt_template="""
            Analyze these sales analytics results:

            Sales by Category:
            {sales_by_category}

            Monthly Trends:
            {monthly_trends}

            Regional Performance:
            {regional_performance}

            Provide:
            1. Key findings
            2. Trend analysis
            3. Business recommendations
            4. Areas of concern
            """,
        )

        # Clean up connections
        workflow.add_node(
            "cleanup",
            "PythonCodeNode",
            code="""
            # Release all connections and get final stats
            return {
                "operation": "stats",
                "cleanup": True
            }
        """,
        )

        # Connect the workflow
        # PythonCodeNode outputs its namespace under 'result' key
        workflow.connect(
            "init_pool", "db_pool"
        )  # Will map result.operation to operation
        workflow.connect("db_pool", "setup_data")
        workflow.connect("setup_data", "execute_setup")

        # Execute with proper runtime
        runtime = LocalRuntime(enable_async=True)

        # Notify pool of workflow start
        pool_node = workflow.get_node("db_pool")
        await pool_node.on_workflow_start("analytics_001", "data_analytics")

        # Execute workflow with parameters to satisfy validation
        params = {"db_pool": {"operation": "initialize"}}
        outputs, error = await runtime.execute_async(workflow, parameters=params)

        # Check for errors
        if error:
            print(f"Workflow error: {error}")
            print(f"Outputs: {outputs}")

        assert error is None

        # Verify results

        # Check pool initialization
        assert outputs["db_pool"]["status"] == "initialized"

        # Clean up
        await pool_node.on_workflow_complete("analytics_001")

        # Drop test table
        cleanup_pool = WorkflowConnectionPool(**db_config)
        await cleanup_pool.process({"operation": "initialize"})
        conn = await cleanup_pool.process({"operation": "acquire"})
        await cleanup_pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": "DROP TABLE IF EXISTS sales_data",
            }
        )
        await cleanup_pool._cleanup()

    async def test_high_concurrency_api_workflow(self, db_config):
        """
        User Story: API backend needs to handle high concurrent requests
        with optimal connection pooling and health monitoring.
        """
        # Simulate API handling multiple concurrent requests
        workflow = Workflow("api_backend", "API Backend")

        # Add connection pool with API-optimized settings
        api_db_config = db_config.copy()
        api_db_config.update(
            {
                "min_connections": 5,
                "max_connections": 20,
                "health_threshold": 60,
                "pre_warm": True,
            }
        )

        workflow.add_node("db_pool", WorkflowConnectionPool(), **api_db_config)

        # Initialize
        workflow.add_node(
            "init",
            "PythonCodeNode",
            code="""
            return {"operation": "initialize"}
        """,
        )

        # Create user table for API
        workflow.add_node(
            "setup_users",
            "PythonCodeNode",
            code="""
            return {
                "acquire_op": {"operation": "acquire"},
                "create_table": {
                    "operation": "execute",
                    "query": '''
                        CREATE TABLE IF NOT EXISTS api_users (
                            id SERIAL PRIMARY KEY,
                            username VARCHAR(50) UNIQUE,
                            email VARCHAR(100) UNIQUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_active TIMESTAMP,
                            request_count INTEGER DEFAULT 0
                        )
                    '''
                },
                "seed_data": {
                    "operation": "execute",
                    "query": '''
                        INSERT INTO api_users (username, email, last_active, request_count)
                        SELECT
                            'user_' || generate_series,
                            'user_' || generate_series || '@example.com',
                            CURRENT_TIMESTAMP - (random() * interval '30 days'),
                            (random() * 1000)::int
                        FROM generate_series(1, 100)
                        ON CONFLICT DO NOTHING
                    '''
                }
            }
        """,
        )

        # Simulate concurrent API requests
        workflow.add_node(
            "simulate_requests",
            "PythonCodeNode",
            code="""
            import random

            # Generate 50 concurrent API requests
            requests = []
            for i in range(50):
                request_type = random.choice(['get_user', 'update_activity', 'get_stats'])
                user_id = random.randint(1, 100)

                if request_type == 'get_user':
                    requests.append({
                        "type": "get_user",
                        "query": f"SELECT * FROM api_users WHERE id = {user_id}"
                    })
                elif request_type == 'update_activity':
                    requests.append({
                        "type": "update_activity",
                        "query": f'''
                            UPDATE api_users
                            SET last_active = CURRENT_TIMESTAMP,
                                request_count = request_count + 1
                            WHERE id = {user_id}
                            RETURNING *
                        '''
                    })
                else:
                    requests.append({
                        "type": "get_stats",
                        "query": '''
                            SELECT
                                COUNT(*) as total_users,
                                SUM(request_count) as total_requests,
                                AVG(request_count) as avg_requests_per_user,
                                COUNT(CASE WHEN last_active > CURRENT_TIMESTAMP - interval '1 hour'
                                      THEN 1 END) as active_last_hour
                            FROM api_users
                        '''
                    })

            return {"api_requests": requests}
        """,
        )

        # Monitor pool performance
        workflow.add_node(
            "monitor_performance",
            "PythonCodeNode",
            code="""
            # Get pool statistics during high load
            return {"operation": "stats"}
        """,
        )

        # AI-powered performance analysis
        workflow.add_node(
            "performance_analysis",
            LLMAgentNode(),
            provider="ollama",
            model="llama2",
            temperature=0.5,
            system_prompt="You are a database performance expert. Analyze connection pool metrics and provide optimization recommendations.",
            prompt_template="""
            Analyze these connection pool performance metrics:

            {pool_stats}

            The pool handled {request_count} concurrent API requests.

            Please provide:
            1. Performance assessment
            2. Bottleneck identification
            3. Optimization recommendations
            4. Capacity planning advice
            """,
        )

        # Connect workflow
        workflow.connect("init", "db_pool")
        workflow.connect("db_pool", "setup_users")
        # More connections would be added for full flow

        # Execute workflow
        runtime = LocalRuntime(enable_async=True)
        pool_node = workflow.get_node("db_pool")

        # Start workflow
        await pool_node.on_workflow_start("api_backend_001", "api_service")

        # Run initial setup
        init_result = await pool_node.process({"operation": "initialize"})
        assert init_result["status"] == "initialized"

        # Simulate high concurrency
        async def simulate_api_request(pool, request_data):
            # Acquire connection
            conn = await pool.process({"operation": "acquire"})

            try:
                # Execute query
                result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn["connection_id"],
                        "query": request_data["query"],
                        "fetch_mode": (
                            "all" if request_data["type"] == "get_stats" else "one"
                        ),
                    }
                )
                return result
            finally:
                # Always release connection
                await pool.process(
                    {"operation": "release", "connection_id": conn["connection_id"]}
                )

        # Create test table first
        setup_conn = await pool_node.process({"operation": "acquire"})
        await pool_node.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS api_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE,
                    email VARCHAR(100) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP,
                    request_count INTEGER DEFAULT 0
                )
            """,
            }
        )

        # Seed data
        await pool_node.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                INSERT INTO api_users (username, email, last_active, request_count)
                SELECT
                    'user_' || generate_series,
                    'user_' || generate_series || '@example.com',
                    CURRENT_TIMESTAMP - (random() * interval '30 days'),
                    (random() * 1000)::int
                FROM generate_series(1, 100)
                ON CONFLICT DO NOTHING
            """,
            }
        )

        await pool_node.process(
            {"operation": "release", "connection_id": setup_conn["connection_id"]}
        )

        # Generate requests
        import random

        requests = []
        for i in range(30):  # Reduced for test speed
            request_type = random.choice(["get_user", "update_activity", "get_stats"])
            user_id = random.randint(1, 100)

            if request_type == "get_user":
                requests.append(
                    {
                        "type": "get_user",
                        "query": f"SELECT * FROM api_users WHERE id = {user_id}",
                    }
                )
            elif request_type == "update_activity":
                requests.append(
                    {
                        "type": "update_activity",
                        "query": f"""
                        UPDATE api_users
                        SET last_active = CURRENT_TIMESTAMP,
                            request_count = request_count + 1
                        WHERE id = {user_id}
                        RETURNING *
                    """,
                    }
                )
            else:
                requests.append(
                    {
                        "type": "get_stats",
                        "query": """
                        SELECT
                            COUNT(*) as total_users,
                            SUM(request_count) as total_requests,
                            AVG(request_count) as avg_requests_per_user,
                            COUNT(CASE WHEN last_active > CURRENT_TIMESTAMP - interval '1 hour'
                                  THEN 1 END) as active_last_hour
                        FROM api_users
                    """,
                    }
                )

        # Execute concurrent requests
        start_time = asyncio.get_event_loop().time()
        tasks = [simulate_api_request(pool_node, req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = asyncio.get_event_loop().time() - start_time

        # Get performance stats
        stats = await pool_node.process({"operation": "stats"})

        # Verify performance
        successful_requests = sum(
            1 for r in results if isinstance(r, dict) and r.get("success")
        )
        assert successful_requests >= len(requests) * 0.95  # At least 95% success rate

        # Check pool efficiency
        assert stats["queries"]["executed"] >= len(requests)
        assert (
            stats["current_state"]["total_connections"]
            <= api_db_config["max_connections"]
        )

        # Average time per request should be reasonable
        avg_time_per_request = elapsed / len(requests)
        assert avg_time_per_request < 0.1  # Less than 100ms per request average

        print("\nAPI Performance Test Results:")
        print(f"- Processed {len(requests)} requests in {elapsed:.2f}s")
        print(f"- Average time per request: {avg_time_per_request*1000:.2f}ms")
        print(f"- Success rate: {successful_requests/len(requests)*100:.1f}%")
        print(f"- Peak connections used: {stats['current_state']['total_connections']}")
        print(
            f"- Average acquisition time: {stats['performance']['avg_acquisition_time_ms']:.2f}ms"
        )

        # Clean up
        cleanup_conn = await pool_node.process({"operation": "acquire"})
        await pool_node.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS api_users",
            }
        )

        await pool_node.on_workflow_complete("api_backend_001")

    async def test_connection_pool_with_failures(self, db_config):
        """
        User Story: System needs to handle database failures gracefully
        with automatic recovery and minimal service disruption.
        """
        # Create resilience testing workflow
        workflow = Workflow("resilience_test", "Resilience Test")

        # Configure pool for resilience testing
        resilient_config = db_config.copy()
        resilient_config.update(
            {
                "min_connections": 3,
                "max_connections": 8,
                "health_threshold": 50,
                "health_check_interval": 5.0,  # More frequent health checks
            }
        )

        pool = WorkflowConnectionPool(**resilient_config)

        # Initialize pool
        await pool.process({"operation": "initialize"})

        # Create test table
        conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS resilience_test (
                    id SERIAL PRIMARY KEY,
                    test_name VARCHAR(100),
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            }
        )

        # Track results
        test_results = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "recovered_connections": 0,
        }

        # Simulate workload with intermittent failures
        async def run_query_with_tracking(query, test_name):
            test_results["total_queries"] += 1

            try:
                # Acquire connection
                conn_result = await pool.process({"operation": "acquire"})
                conn_id = conn_result["connection_id"]

                # Execute query
                result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": query,
                        "params": (test_name,) if test_name else None,
                    }
                )

                if result["success"]:
                    test_results["successful_queries"] += 1
                else:
                    test_results["failed_queries"] += 1

                # Release connection
                release_result = await pool.process(
                    {"operation": "release", "connection_id": conn_id}
                )

                if release_result["status"] == "recycled":
                    test_results["recovered_connections"] += 1

                return result

            except Exception as e:
                test_results["failed_queries"] += 1
                raise

        # Run normal queries
        for i in range(10):
            await run_query_with_tracking(
                "INSERT INTO resilience_test (test_name, status) VALUES (%s, 'success')",
                f"normal_query_{i}",
            )

        # Simulate some failures by using bad queries
        for i in range(5):
            try:
                await run_query_with_tracking("SELECT * FROM nonexistent_table", None)
            except:
                pass  # Expected to fail

        # Continue with normal queries to test recovery
        for i in range(10):
            await run_query_with_tracking(
                "INSERT INTO resilience_test (test_name, status) VALUES (%s, 'recovered')",
                f"recovery_query_{i}",
            )

        # Get final stats
        pool_stats = await pool.process({"operation": "stats"})

        # Verify resilience
        print("\nResilience Test Results:")
        print(f"- Total queries: {test_results['total_queries']}")
        print(f"- Successful: {test_results['successful_queries']}")
        print(f"- Failed: {test_results['failed_queries']}")
        print(f"- Recovered connections: {test_results['recovered_connections']}")
        print(f"- Pool health scores: {pool_stats['current_state']['health_scores']}")

        # Success rate should be good despite failures
        success_rate = (
            test_results["successful_queries"] / test_results["total_queries"]
        )
        assert success_rate > 0.7  # At least 70% success despite failures

        # Pool should have recycled some connections
        assert pool_stats["connections"]["recycled"] > 0

        # Pool should still be operational
        final_query = await run_query_with_tracking(
            "SELECT COUNT(*) as count FROM resilience_test WHERE status = 'recovered'",
            None,
        )
        assert final_query["success"] is True
        assert final_query["data"][0]["count"] >= 5

        # Clean up
        cleanup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS resilience_test",
            }
        )

        await pool._cleanup()

        print("\nResilience test completed successfully!")

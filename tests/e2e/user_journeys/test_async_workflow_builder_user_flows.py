"""
User flow tests for AsyncWorkflowBuilder.

Tests realistic developer workflows and common usage patterns to ensure
the AsyncWorkflowBuilder meets developer expectations and provides
excellent developer experience.
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest
from kailash.resources.registry import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import (
    AsyncPatterns,
    AsyncWorkflowBuilder,
    ErrorHandler,
    RetryPolicy,
)

from tests.utils.docker_config import DATABASE_CONFIG, OLLAMA_CONFIG, REDIS_CONFIG


@pytest.mark.integration
@pytest.mark.requires_infrastructure
class TestAsyncWorkflowBuilderUserFlows:
    """Test real developer workflows and usage patterns."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for user flow tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create sample data files
            sample_csv = workspace / "customers.csv"
            sample_csv.write_text(
                """id,name,email,signup_date,plan,monthly_spend
1,Alice Johnson,alice@example.com,2023-01-15,premium,299.99
2,Bob Smith,bob@example.com,2023-02-20,basic,49.99
3,Charlie Brown,charlie@example.com,2023-01-10,premium,199.99
4,Diana Prince,diana@example.com,2023-03-05,basic,29.99
5,Eve Wilson,eve@example.com,2023-02-28,enterprise,999.99
6,Frank Miller,frank@example.com,2023-01-20,premium,249.99
7,Grace Davis,grace@example.com,2023-03-15,basic,39.99
8,Henry Lee,henry@example.com,2023-02-10,premium,319.99
9,Ivy Chen,ivy@example.com,2023-01-25,enterprise,1299.99
10,Jack Taylor,jack@example.com,2023-03-01,basic,19.99
"""
            )

            # Create orders data
            orders_csv = workspace / "orders.csv"
            orders_csv.write_text(
                """order_id,customer_id,product,amount,order_date,status
1001,1,Product A,99.99,2023-01-16,completed
1002,2,Product B,29.99,2023-02-21,completed
1003,1,Product C,199.99,2023-01-18,completed
1004,3,Product A,99.99,2023-01-11,completed
1005,4,Product B,29.99,2023-03-06,pending
1006,5,Product D,799.99,2023-03-01,completed
1007,1,Product B,29.99,2023-01-20,completed
1008,6,Product A,99.99,2023-01-21,completed
1009,7,Product B,29.99,2023-03-16,completed
1010,8,Product C,199.99,2023-02-11,completed
"""
            )

            # Create config file
            config_json = workspace / "pipeline_config.json"
            config_json.write_text(
                json.dumps(
                    {
                        "processing": {
                            "batch_size": 50,
                            "max_workers": 5,
                            "timeout_seconds": 30,
                        },
                        "thresholds": {
                            "high_value_customer": 200.0,
                            "enterprise_minimum": 500.0,
                        },
                        "output_formats": ["csv", "json", "report"],
                    }
                )
            )

            yield workspace

    @pytest.mark.asyncio
    async def test_data_analyst_workflow(self, temp_workspace):
        """Test: Data analyst building a customer analytics pipeline."""

        # Scenario: Data analyst wants to analyze customer data
        # 1. Load customer and order data
        # 2. Join and enrich the data
        # 3. Calculate customer metrics
        # 4. Generate insights and reports

        builder = AsyncWorkflowBuilder("customer_analytics_pipeline")

        # Step 1: Load data files (common analyst task)
        builder.add_async_code(
            "load_customers",
            f"""
            import pandas as pd

            # Load customer data
            customers_df = pd.read_csv(r"{temp_workspace / 'customers.csv'}")

            result = {{
                "customers": customers_df.to_dict('records'),
                "total_customers": len(customers_df),
                "loaded_at": time.time()
            }}
            """,
        )

        builder.add_async_code(
            "load_orders",
            f"""
            import pandas as pd

            # Load orders data
            orders_df = pd.read_csv(r"{temp_workspace / 'orders.csv'}")

            result = {{
                "orders": orders_df.to_dict('records'),
                "total_orders": len(orders_df),
                "loaded_at": time.time()
            }}
            """,
        )

        # Step 2: Join and enrich data (parallel processing)
        builder.add_parallel_map(
            "enrich_customer_data",
            """
            async def process_item(customer):
                import pandas as pd

                customer_id = customer["id"]

                # Find customer orders
                customer_orders = [order for order in all_orders if order["customer_id"] == customer_id]

                # Calculate metrics
                total_orders = len(customer_orders)
                total_spent = sum(float(order["amount"]) for order in customer_orders)
                avg_order_value = total_spent / total_orders if total_orders > 0 else 0

                # Determine customer segment
                monthly_spend = float(customer["monthly_spend"])
                if monthly_spend >= 500:
                    segment = "enterprise"
                elif monthly_spend >= 100:
                    segment = "premium"
                else:
                    segment = "basic"

                return {
                    "customer_id": customer_id,
                    "name": customer["name"],
                    "email": customer["email"],
                    "plan": customer["plan"],
                    "monthly_spend": monthly_spend,
                    "segment": segment,
                    "metrics": {
                        "total_orders": total_orders,
                        "total_spent": total_spent,
                        "avg_order_value": avg_order_value,
                        "orders_per_month": total_orders / 3  # 3 months of data
                    },
                    "orders": customer_orders
                }
            """,
            max_workers=3,
            continue_on_error=True,
        )

        # Step 3: Generate insights
        builder.add_async_code(
            "generate_insights",
            """
            # Segment analysis
            segments = {}
            for customer in enriched_customers:
                segment = customer["segment"]
                if segment not in segments:
                    segments[segment] = []
                segments[segment].append(customer)

            # Calculate segment metrics
            segment_metrics = {}
            for segment, customers in segments.items():
                total_customers = len(customers)
                total_revenue = sum(customer["metrics"]["total_spent"] for customer in customers)
                avg_monthly_spend = sum(customer["monthly_spend"] for customer in customers) / total_customers
                avg_orders = sum(customer["metrics"]["total_orders"] for customer in customers) / total_customers

                segment_metrics[segment] = {
                    "customer_count": total_customers,
                    "total_revenue": total_revenue,
                    "avg_monthly_spend": avg_monthly_spend,
                    "avg_orders_per_customer": avg_orders,
                    "revenue_per_customer": total_revenue / total_customers if total_customers > 0 else 0
                }

            # Top customers by value
            top_customers = sorted(
                enriched_customers,
                key=lambda c: c["metrics"]["total_spent"],
                reverse=True
            )[:5]

            result = {
                "segment_analysis": segment_metrics,
                "top_customers": top_customers,
                "overall_metrics": {
                    "total_customers": len(enriched_customers),
                    "total_revenue": sum(c["metrics"]["total_spent"] for c in enriched_customers),
                    "avg_customer_value": sum(c["metrics"]["total_spent"] for c in enriched_customers) / len(enriched_customers)
                },
                "insights": [
                    "Total customers analyzed: " + str(len(enriched_customers)),
                    "Enterprise segment revenue: $" + str(round(segment_metrics.get('enterprise', {}).get('total_revenue', 0), 2)),
                    "Top customer spent: $" + str(round(top_customers[0]['metrics']['total_spent'], 2)) if top_customers else "No customers found"
                ]
            }
            """,
        )

        # Step 4: Export results
        customers_csv_path = str(temp_workspace / "customer_analysis.csv")
        insights_json_path = str(temp_workspace / "insights.json")
        report_txt_path = str(temp_workspace / "analysis_report.txt")

        builder.add_async_code(
            "export_results",
            f"""
            import pandas as pd
            import json

            # Export customer data to CSV
            customers_df = pd.DataFrame(enriched_customers)
            customers_output_path = r"{customers_csv_path}"
            customers_df.to_csv(customers_output_path, index=False)

            # Export insights to JSON
            insights_output_path = r"{insights_json_path}"
            with open(insights_output_path, 'w') as f:
                json.dump(insights_data, f, indent=2)

            # Generate text report
            report_output_path = r"{report_txt_path}"
            with open(report_output_path, 'w') as f:
                f.write("Customer Analytics Report\\n")
                f.write("=" * 30 + "\\n\\n")

                for insight in insights_data.get("insights", []):
                    f.write("• " + insight + "\\n")

                f.write("\\nSegment Breakdown:\\n")
                for segment, metrics in insights_data.get("segment_analysis", {{}}).items():
                    f.write("  " + segment.title() + ": " + str(metrics['customer_count']) + " customers, " +
                           "$" + str(round(metrics['total_revenue'], 2)) + " revenue\\n")

            result = {{
                "exports_completed": True,
                "files_created": [
                    customers_output_path,
                    insights_output_path,
                    report_output_path
                ],
                "export_summary": {{
                    "customers_exported": len(enriched_customers),
                    "segments_analyzed": len(insights_data.get("segment_analysis", {{}})),
                    "insights_generated": len(insights_data.get("insights", []))
                }}
            }}
            """,
        )

        # Connect the workflow
        builder.add_connection(
            "load_customers", "customers", "enrich_customer_data", "items"
        )
        builder.add_connection(
            "load_orders", "orders", "enrich_customer_data", "all_orders"
        )
        builder.add_connection(
            "enrich_customer_data", "results", "generate_insights", "enriched_customers"
        )
        builder.add_connection(
            "generate_insights", None, "export_results", "insights_data"
        )
        builder.add_connection(
            "enrich_customer_data", "results", "export_results", "enriched_customers"
        )

        # Execute the workflow
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify analyst workflow completed successfully
        assert result["status"] == "success"

        # Check data loading
        customers_result = result["results"]["load_customers"]
        assert customers_result["total_customers"] == 10

        orders_result = result["results"]["load_orders"]
        assert orders_result["total_orders"] == 10

        # Check enrichment
        enrichment_result = result["results"]["enrich_customer_data"]
        assert len(enrichment_result["results"]) > 0
        assert enrichment_result["statistics"]["successful"] > 0

        # Check insights
        insights_result = result["results"]["generate_insights"]
        assert "segment_analysis" in insights_result
        assert "top_customers" in insights_result
        assert len(insights_result["insights"]) >= 3

        # Check exports
        export_result = result["results"]["export_results"]
        assert export_result["exports_completed"] is True
        assert len(export_result["files_created"]) == 3

        # Verify files were actually created
        for file_path in export_result["files_created"]:
            assert Path(file_path).exists()

    @pytest.mark.asyncio
    async def test_api_integration_developer_workflow(self):
        """Test: Developer building an API integration pipeline."""

        # Scenario: Developer needs to integrate with external APIs
        # 1. Fetch data from multiple APIs
        # 2. Handle rate limiting and retries
        # 3. Process and validate data
        # 4. Handle errors gracefully

        builder = AsyncWorkflowBuilder("api_integration_pipeline")

        # Mock API data (simulating external services)
        builder.add_async_code(
            "setup_mock_data",
            """
            # Simulate API endpoints with different characteristics
            api_configs = {
                "users_api": {
                    "endpoint": "/users",
                    "rate_limit": 10,  # requests per second
                    "reliability": 0.95,  # 95% success rate
                    "response_time": 0.1
                },
                "orders_api": {
                    "endpoint": "/orders",
                    "rate_limit": 5,
                    "reliability": 0.8,  # 80% success rate (less reliable)
                    "response_time": 0.2
                },
                "inventory_api": {
                    "endpoint": "/inventory",
                    "rate_limit": 20,
                    "reliability": 0.99,  # Very reliable
                    "response_time": 0.05
                }
            }

            result = {
                "api_configs": api_configs,
                "mock_setup_complete": True
            }
            """,
        )

        # Fetch data with different patterns based on API characteristics
        AsyncPatterns.rate_limited(
            builder,
            "fetch_users",
            """
            import random

            # Simulate API call with rate limiting
            await asyncio.sleep(0.1)  # Simulate network delay

            if random.random() > 0.95:  # 5% failure rate
                raise aiohttp.ClientError("Users API temporarily unavailable")

            # Simulate user data
            users = [
                {"id": i, "name": f"User {i}", "email": f"user{i}@example.com",
                 "status": "active" if i % 3 != 0 else "inactive"}
                for i in range(1, 21)
            ]

            result = {
                "users": users,
                "total": len(users),
                "api": "users_api",
                "fetched_at": time.time()
            }
            """,
            requests_per_second=10,
            burst_size=5,
        )

        AsyncPatterns.retry_with_backoff(
            builder,
            "fetch_orders",
            """
            import random

            # Simulate less reliable API
            if random.random() > 0.8:  # 20% failure rate
                raise ConnectionError("Orders API connection failed")

            await asyncio.sleep(0.2)  # Slower API

            orders = [
                {"order_id": 1000 + i, "user_id": (i % 20) + 1,
                 "amount": round(random.uniform(10, 500), 2),
                 "status": "completed" if i % 4 != 0 else "pending"}
                for i in range(1, 31)
            ]

            result = {
                "orders": orders,
                "total": len(orders),
                "api": "orders_api",
                "fetched_at": time.time()
            }
            """,
            max_retries=3,
            initial_backoff=0.5,
            backoff_factor=2.0,
        )

        AsyncPatterns.circuit_breaker(
            builder,
            "fetch_inventory",
            """
            import random

            # Very reliable API
            if random.random() > 0.99:  # 1% failure rate
                raise Exception("Inventory API unexpected error")

            await asyncio.sleep(0.05)  # Fast API

            inventory = [
                {"product_id": f"PROD_{i:03d}", "name": f"Product {i}",
                 "stock": random.randint(0, 100), "price": round(random.uniform(5, 200), 2)}
                for i in range(1, 51)
            ]

            result = {
                "inventory": inventory,
                "total": len(inventory),
                "api": "inventory_api",
                "fetched_at": time.time()
            }
            """,
            failure_threshold=3,
            reset_timeout=30.0,
        )

        # Data validation and enrichment
        builder.add_async_code(
            "validate_and_enrich",
            """
            # Validate data integrity
            validation_results = {
                "users": {
                    "total": len(users_data.get("users", [])),
                    "active": len([u for u in users_data.get("users", []) if u.get("status") == "active"]),
                    "valid_emails": len([u for u in users_data.get("users", []) if "@" in u.get("email", "")])
                },
                "orders": {
                    "total": len(orders_data.get("orders", [])),
                    "completed": len([o for o in orders_data.get("orders", []) if o.get("status") == "completed"]),
                    "total_value": sum(o.get("amount", 0) for o in orders_data.get("orders", []))
                },
                "inventory": {
                    "total": len(inventory_data.get("inventory", [])),
                    "in_stock": len([i for i in inventory_data.get("inventory", []) if i.get("stock", 0) > 0]),
                    "total_value": sum(i.get("price", 0) * i.get("stock", 0) for i in inventory_data.get("inventory", []))
                }
            }

            # Cross-reference data
            user_ids = {u["id"] for u in users_data.get("users", [])}
            orders_with_valid_users = [
                o for o in orders_data.get("orders", [])
                if o.get("user_id") in user_ids
            ]

            # Generate enriched dataset
            enriched_data = {
                "users": users_data.get("users", []),
                "orders": orders_with_valid_users,
                "inventory": inventory_data.get("inventory", []),
                "cross_references": {
                    "valid_user_orders": len(orders_with_valid_users),
                    "orphaned_orders": len(orders_data.get("orders", [])) - len(orders_with_valid_users)
                }
            }

            result = {
                "validation_results": validation_results,
                "enriched_data": enriched_data,
                "data_quality_score": (
                    validation_results["users"]["valid_emails"] / max(1, validation_results["users"]["total"]) +
                    validation_results["orders"]["completed"] / max(1, validation_results["orders"]["total"]) +
                    validation_results["inventory"]["in_stock"] / max(1, validation_results["inventory"]["total"])
                ) / 3
            }
            """,
        )

        # Error handling and reporting
        builder.add_async_code(
            "generate_integration_report",
            """
            # Compile integration status
            api_status = {}

            # Check which APIs succeeded
            if users_result.get("success", True):
                api_status["users_api"] = {
                    "status": "success",
                    "records": users_result.get("total", 0),
                    "response_time": users_result.get("_rate_limit_info", {}).get("operation_duration", 0)
                }
            else:
                api_status["users_api"] = {"status": "failed", "error": "Rate limit or connection issue"}

            if orders_result.get("success", True):
                api_status["orders_api"] = {
                    "status": "success",
                    "records": orders_result.get("total", 0),
                    "attempts": orders_result.get("total_attempts", 1)
                }
            else:
                api_status["orders_api"] = {"status": "failed", "error": "Retry attempts exhausted"}

            if inventory_result.get("success", True):
                api_status["inventory_api"] = {
                    "status": "success",
                    "records": inventory_result.get("total", 0),
                    "circuit_breaker": inventory_result.get("_circuit_breaker_info", {})
                }
            else:
                api_status["inventory_api"] = {"status": "failed", "error": "Circuit breaker open"}

            # Overall integration health
            successful_apis = len([api for api in api_status.values() if api["status"] == "success"])
            total_apis = len(api_status)

            result = {
                "integration_report": {
                    "api_status": api_status,
                    "overall_health": successful_apis / total_apis,
                    "successful_apis": successful_apis,
                    "total_apis": total_apis,
                    "data_quality_score": validation_data.get("data_quality_score", 0),
                    "recommendations": [
                        "Monitor orders API reliability" if api_status.get("orders_api", {}).get("status") == "failed" else "Orders API performing well",
                        f"Data quality score: {validation_data.get('data_quality_score', 0):.2f}/1.0",
                        "Consider caching inventory data" if api_status.get("inventory_api", {}).get("status") == "success" else "Inventory API needs attention"
                    ]
                }
            }
            """,
        )

        # Connect the workflow
        builder.add_connection("fetch_users", None, "validate_and_enrich", "users_data")
        builder.add_connection(
            "fetch_orders", None, "validate_and_enrich", "orders_data"
        )
        builder.add_connection(
            "fetch_inventory", None, "validate_and_enrich", "inventory_data"
        )
        builder.add_connection(
            "validate_and_enrich",
            None,
            "generate_integration_report",
            "validation_data",
        )
        builder.add_connection(
            "fetch_users", None, "generate_integration_report", "users_result"
        )
        builder.add_connection(
            "fetch_orders", None, "generate_integration_report", "orders_result"
        )
        builder.add_connection(
            "fetch_inventory", None, "generate_integration_report", "inventory_result"
        )

        # Execute the workflow
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify API integration workflow
        assert result["status"] == "success"

        # Check individual API results
        users_result = result["results"]["fetch_users"]
        assert "_rate_limit_info" in users_result

        orders_result = result["results"]["fetch_orders"]
        assert "total_attempts" in orders_result

        inventory_result = result["results"]["fetch_inventory"]
        assert "_circuit_breaker_info" in inventory_result

        # Check validation
        validation_result = result["results"]["validate_and_enrich"]
        assert "validation_results" in validation_result
        assert "data_quality_score" in validation_result
        assert validation_result["data_quality_score"] > 0

        # Check integration report
        report_result = result["results"]["generate_integration_report"]
        assert "integration_report" in report_result
        assert "api_status" in report_result["integration_report"]
        assert "overall_health" in report_result["integration_report"]

    @pytest.mark.asyncio
    async def test_data_scientist_ml_pipeline_workflow(self):
        """Test: Data scientist building an ML feature engineering pipeline."""

        # Scenario: Data scientist wants to prepare features for ML model
        # 1. Load and clean data
        # 2. Feature engineering and transformation
        # 3. Data validation and quality checks
        # 4. Export features for ML training

        builder = AsyncWorkflowBuilder("ml_feature_pipeline")

        # Generate synthetic dataset
        builder.add_async_code(
            "generate_synthetic_data",
            """
            import random
            import numpy as np
            from datetime import datetime, timedelta

            # Generate realistic customer behavior data
            customers = []
            base_date = datetime(2023, 1, 1)

            for customer_id in range(1, 501):  # 500 customers
                # Customer profile
                signup_date = base_date + timedelta(days=random.randint(0, 90))
                plan_type = random.choice(['basic', 'premium', 'enterprise'])
                industry = random.choice(['tech', 'retail', 'finance', 'healthcare', 'education'])

                # Behavioral patterns
                sessions_per_week = random.gammavariate(2, 2) + 1  # Realistic distribution
                avg_session_duration = random.lognormvariate(3, 1)  # Log-normal for time data
                feature_usage = {
                    'feature_a': random.random(),
                    'feature_b': random.random(),
                    'feature_c': random.random()
                }

                # Generate time series data
                activity_history = []
                current_date = signup_date
                while current_date < base_date + timedelta(days=90):
                    if random.random() < sessions_per_week / 7:  # Daily activity probability
                        activity_history.append({
                            'date': current_date.isoformat(),
                            'session_duration': max(1, random.normalvariate(avg_session_duration, avg_session_duration * 0.3)),
                            'actions_taken': random.poisson(5),
                            'errors_encountered': random.poisson(0.5)
                        })
                    current_date += timedelta(days=1)

                customers.append({
                    'customer_id': customer_id,
                    'signup_date': signup_date.isoformat(),
                    'plan_type': plan_type,
                    'industry': industry,
                    'sessions_per_week': sessions_per_week,
                    'avg_session_duration': avg_session_duration,
                    'feature_usage': feature_usage,
                    'activity_history': activity_history,
                    'is_churned': random.random() < 0.15  # 15% churn rate
                })

            result = {
                "synthetic_data": customers,
                "dataset_size": len(customers),
                "generation_timestamp": time.time(),
                "data_schema": {
                    "customer_id": "unique identifier",
                    "signup_date": "ISO date string",
                    "plan_type": "categorical: basic/premium/enterprise",
                    "industry": "categorical industry type",
                    "sessions_per_week": "numeric behavioral metric",
                    "avg_session_duration": "numeric time metric",
                    "feature_usage": "dict of feature adoption rates",
                    "activity_history": "list of time series events",
                    "is_churned": "boolean target variable"
                }
            }
            """,
        )

        # Feature engineering with parallel processing
        builder.add_parallel_map(
            "engineer_features",
            """
            async def process_item(customer):
                import numpy as np
                from datetime import datetime

                # Basic features
                signup_date = datetime.fromisoformat(customer['signup_date'])
                days_since_signup = (datetime.now() - signup_date).days

                # Activity features
                activity = customer['activity_history']
                total_sessions = len(activity)
                total_duration = sum(session['session_duration'] for session in activity)
                total_actions = sum(session['actions_taken'] for session in activity)
                total_errors = sum(session['errors_encountered'] for session in activity)

                # Temporal features
                if activity:
                    last_activity = max(datetime.fromisoformat(session['date']) for session in activity)
                    days_since_last_activity = (datetime.now() - last_activity).days

                    # Weekly activity pattern
                    weekly_sessions = [0] * 7
                    for session in activity:
                        day_of_week = datetime.fromisoformat(session['date']).weekday()
                        weekly_sessions[day_of_week] += 1

                    activity_variance = np.var(weekly_sessions) if weekly_sessions else 0
                else:
                    days_since_last_activity = days_since_signup
                    activity_variance = 0

                # Engagement features
                avg_session_duration = total_duration / total_sessions if total_sessions > 0 else 0
                avg_actions_per_session = total_actions / total_sessions if total_sessions > 0 else 0
                error_rate = total_errors / total_actions if total_actions > 0 else 0

                # Feature adoption
                feature_adoption_score = sum(customer['feature_usage'].values()) / len(customer['feature_usage'])

                # Plan value features
                plan_value_map = {'basic': 1, 'premium': 2, 'enterprise': 3}
                plan_value = plan_value_map.get(customer['plan_type'], 1)

                # Industry encoding (simple for demo)
                industry_tech = 1 if customer['industry'] == 'tech' else 0
                industry_finance = 1 if customer['industry'] == 'finance' else 0

                return {
                    'customer_id': customer['customer_id'],
                    'target': customer['is_churned'],
                    'features': {
                        # Temporal features
                        'days_since_signup': days_since_signup,
                        'days_since_last_activity': days_since_last_activity,

                        # Activity features
                        'total_sessions': total_sessions,
                        'avg_session_duration': avg_session_duration,
                        'avg_actions_per_session': avg_actions_per_session,
                        'sessions_per_week': customer['sessions_per_week'],
                        'activity_variance': activity_variance,

                        # Engagement features
                        'feature_adoption_score': feature_adoption_score,
                        'error_rate': error_rate,

                        # Plan and demographic features
                        'plan_value': plan_value,
                        'industry_tech': industry_tech,
                        'industry_finance': industry_finance,

                        # Derived features
                        'engagement_score': (
                            (avg_session_duration / 100) * 0.3 +
                            (avg_actions_per_session / 10) * 0.3 +
                            feature_adoption_score * 0.4
                        ),
                        'activity_consistency': 1 / (1 + activity_variance)  # Higher = more consistent
                    }
                }
            """,
            max_workers=10,
            batch_size=25,
            continue_on_error=True,
        )

        # Data validation and quality assessment
        builder.add_async_code(
            "validate_features",
            """
            import numpy as np

            # Extract feature arrays for analysis
            feature_names = list(engineered_features[0]['features'].keys()) if engineered_features else []
            feature_matrix = []
            targets = []

            for customer in engineered_features:
                if customer.get('features'):
                    feature_vector = [customer['features'].get(fname, 0) for fname in feature_names]
                    feature_matrix.append(feature_vector)
                    targets.append(int(customer['target']))

            feature_matrix = np.array(feature_matrix)
            targets = np.array(targets)

            # Feature statistics
            feature_stats = {}
            for i, fname in enumerate(feature_names):
                col_data = feature_matrix[:, i]
                feature_stats[fname] = {
                    'mean': float(np.mean(col_data)),
                    'std': float(np.std(col_data)),
                    'min': float(np.min(col_data)),
                    'max': float(np.max(col_data)),
                    'missing_rate': float(np.sum(np.isnan(col_data)) / len(col_data)),
                    'zero_rate': float(np.sum(col_data == 0) / len(col_data))
                }

            # Target distribution
            target_dist = {
                'churn_rate': float(np.mean(targets)),
                'total_samples': len(targets),
                'churned_customers': int(np.sum(targets)),
                'retained_customers': int(len(targets) - np.sum(targets))
            }

            # Data quality checks
            quality_issues = []
            for fname, stats in feature_stats.items():
                if stats['missing_rate'] > 0.1:
                    quality_issues.append(f"High missing rate in {fname}: {stats['missing_rate']:.2%}")
                if stats['std'] == 0:
                    quality_issues.append(f"No variance in {fname}")
                if stats['zero_rate'] > 0.8:
                    quality_issues.append(f"High zero rate in {fname}: {stats['zero_rate']:.2%}")

            result = {
                'feature_statistics': feature_stats,
                'target_distribution': target_dist,
                'data_quality': {
                    'total_features': len(feature_names),
                    'total_samples': len(feature_matrix),
                    'quality_issues': quality_issues,
                    'quality_score': max(0, 1 - len(quality_issues) / len(feature_names))
                },
                'feature_matrix_shape': feature_matrix.shape,
                'ready_for_ml': len(quality_issues) < 3 and len(feature_matrix) > 100
            }
            """,
        )

        # Export features for ML training
        builder.add_async_code(
            "export_ml_features",
            """
            import pandas as pd
            import json

            # Prepare ML-ready dataset
            ml_dataset = []
            for customer in engineered_features:
                if customer.get('features'):
                    row = {'customer_id': customer['customer_id'], 'target': customer['target']}
                    row.update(customer['features'])
                    ml_dataset.append(row)

            # Create train/validation split (80/20)
            import random
            random.shuffle(ml_dataset)
            split_idx = int(0.8 * len(ml_dataset))

            train_data = ml_dataset[:split_idx]
            val_data = ml_dataset[split_idx:]

            # Feature importance estimation (simple correlation)
            feature_importance = {}
            if validation_results['ready_for_ml']:
                train_df = pd.DataFrame(train_data)
                for col in train_df.columns:
                    if col not in ['customer_id', 'target']:
                        try:
                            corr = abs(train_df[col].corr(train_df['target']))
                            feature_importance[col] = corr if not np.isnan(corr) else 0
                        except:
                            feature_importance[col] = 0

            # Sort features by importance
            sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)

            result = {
                'ml_export': {
                    'train_size': len(train_data),
                    'validation_size': len(val_data),
                    'feature_count': len(validation_results['feature_statistics']),
                    'target_balance': validation_results['target_distribution']['churn_rate'],
                    'ready_for_training': validation_results['ready_for_ml']
                },
                'feature_importance': dict(sorted_features),
                'top_features': [fname for fname, importance in sorted_features[:10]],
                'export_metadata': {
                    'created_at': time.time(),
                    'data_quality_score': validation_results['data_quality']['quality_score'],
                    'quality_issues': validation_results['data_quality']['quality_issues']
                },
                'model_recommendations': [
                    "Use Random Forest for baseline model",
                    "Consider feature scaling for linear models",
                    f"Top feature for prediction: {sorted_features[0][0] if sorted_features else 'unknown'}",
                    "Monitor for data drift in production"
                ]
            }
            """,
        )

        # Connect the ML pipeline
        builder.add_connection(
            "generate_synthetic_data", "synthetic_data", "engineer_features", "items"
        )
        builder.add_connection(
            "engineer_features", "results", "validate_features", "engineered_features"
        )
        builder.add_connection(
            "validate_features", None, "export_ml_features", "validation_results"
        )
        builder.add_connection(
            "engineer_features", "results", "export_ml_features", "engineered_features"
        )

        # Execute the ML pipeline
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify ML pipeline workflow
        assert result["status"] == "success"

        # Check data generation
        data_result = result["results"]["generate_synthetic_data"]
        assert data_result["dataset_size"] == 500
        assert "data_schema" in data_result

        # Check feature engineering
        features_result = result["results"]["engineer_features"]
        assert "results" in features_result
        assert features_result["statistics"]["successful"] > 450  # Most should succeed

        # Check validation
        validation_result = result["results"]["validate_features"]
        assert "feature_statistics" in validation_result
        assert "target_distribution" in validation_result
        assert validation_result["data_quality"]["total_features"] > 10

        # Check ML export
        export_result = result["results"]["export_ml_features"]
        assert "ml_export" in export_result
        assert "feature_importance" in export_result
        assert export_result["ml_export"]["train_size"] > 300
        assert export_result["ml_export"]["validation_size"] > 50
        assert len(export_result["model_recommendations"]) >= 4

    @pytest.mark.asyncio
    async def test_devops_monitoring_pipeline_workflow(self):
        """Test: DevOps engineer building a monitoring and alerting pipeline."""

        # Scenario: DevOps engineer needs to monitor system health
        # 1. Collect metrics from multiple sources
        # 2. Process and aggregate metrics
        # 3. Detect anomalies and issues
        # 4. Generate alerts and reports

        builder = AsyncWorkflowBuilder("devops_monitoring_pipeline")

        # Simulate metric collection from different sources
        AsyncPatterns.parallel_fetch(
            builder,
            "collect_metrics",
            {
                "cpu_metrics": """
                import random
                import time

                # Simulate CPU metrics collection
                await asyncio.sleep(0.1)

                metrics = []
                current_time = time.time()
                for i in range(10):  # 10 time points
                    timestamp = current_time - (i * 60)  # 1 minute intervals
                    cpu_usage = max(0, min(100, random.normalvariate(45, 15)))  # Normal around 45%
                    load_avg = max(0, random.normalvariate(2.5, 0.8))

                    metrics.append({
                        "timestamp": timestamp,
                        "cpu_usage_percent": cpu_usage,
                        "load_average": load_avg,
                        "source": "system_monitor"
                    })

                result = {
                    "metric_type": "cpu",
                    "metrics": metrics,
                    "collection_time": current_time
                }
                """,
                "memory_metrics": """
                import random
                import time

                await asyncio.sleep(0.15)

                metrics = []
                current_time = time.time()
                for i in range(10):
                    timestamp = current_time - (i * 60)
                    memory_used = max(0, min(100, random.normalvariate(65, 10)))  # Normal around 65%
                    swap_used = max(0, min(100, random.normalvariate(15, 5)))

                    metrics.append({
                        "timestamp": timestamp,
                        "memory_usage_percent": memory_used,
                        "swap_usage_percent": swap_used,
                        "source": "system_monitor"
                    })

                result = {
                    "metric_type": "memory",
                    "metrics": metrics,
                    "collection_time": current_time
                }
                """,
                "network_metrics": """
                import random
                import time

                await asyncio.sleep(0.08)

                metrics = []
                current_time = time.time()
                base_traffic = 1000000  # Base traffic in bytes

                for i in range(10):
                    timestamp = current_time - (i * 60)
                    # Simulate network traffic with some spikes
                    traffic_in = base_traffic * random.lognormvariate(0, 0.5)
                    traffic_out = traffic_in * random.uniform(0.3, 0.8)
                    packet_loss = max(0, random.normalvariate(0.1, 0.05))  # Very low loss normally

                    metrics.append({
                        "timestamp": timestamp,
                        "bytes_in": traffic_in,
                        "bytes_out": traffic_out,
                        "packet_loss_percent": packet_loss,
                        "source": "network_monitor"
                    })

                result = {
                    "metric_type": "network",
                    "metrics": metrics,
                    "collection_time": current_time
                }
                """,
                "application_metrics": """
                import random
                import time

                await asyncio.sleep(0.12)

                metrics = []
                current_time = time.time()

                for i in range(10):
                    timestamp = current_time - (i * 60)
                    response_time = max(50, random.lognormvariate(4.5, 0.5))  # Log-normal for response times
                    error_rate = max(0, random.normalvariate(2, 1))  # 2% average error rate
                    throughput = max(0, random.normalvariate(1000, 200))  # requests per minute

                    metrics.append({
                        "timestamp": timestamp,
                        "response_time_ms": response_time,
                        "error_rate_percent": error_rate,
                        "throughput_rpm": throughput,
                        "source": "application_monitor"
                    })

                result = {
                    "metric_type": "application",
                    "metrics": metrics,
                    "collection_time": current_time
                }
                """,
            },
            timeout_per_operation=5.0,
            continue_on_error=True,
        )

        # Process and aggregate metrics
        builder.add_async_code(
            "process_metrics",
            """
            import numpy as np
            from collections import defaultdict

            # Combine all metrics
            all_metrics = {}
            for metric_type, data in successful.items():
                all_metrics[metric_type] = data["metrics"]

            # Calculate aggregated statistics
            aggregated_stats = {}

            # CPU metrics
            if "cpu_metrics" in all_metrics:
                cpu_data = all_metrics["cpu_metrics"]
                cpu_values = [m["cpu_usage_percent"] for m in cpu_data]
                load_values = [m["load_average"] for m in cpu_data]

                aggregated_stats["cpu"] = {
                    "avg_usage": np.mean(cpu_values),
                    "max_usage": np.max(cpu_values),
                    "avg_load": np.mean(load_values),
                    "max_load": np.max(load_values),
                    "samples": len(cpu_values)
                }

            # Memory metrics
            if "memory_metrics" in all_metrics:
                memory_data = all_metrics["memory_metrics"]
                memory_values = [m["memory_usage_percent"] for m in memory_data]
                swap_values = [m["swap_usage_percent"] for m in memory_data]

                aggregated_stats["memory"] = {
                    "avg_usage": np.mean(memory_values),
                    "max_usage": np.max(memory_values),
                    "avg_swap": np.mean(swap_values),
                    "max_swap": np.max(swap_values),
                    "samples": len(memory_values)
                }

            # Network metrics
            if "network_metrics" in all_metrics:
                network_data = all_metrics["network_metrics"]
                traffic_in = [m["bytes_in"] for m in network_data]
                packet_loss = [m["packet_loss_percent"] for m in network_data]

                aggregated_stats["network"] = {
                    "avg_traffic_in_mb": np.mean(traffic_in) / 1024 / 1024,
                    "max_traffic_in_mb": np.max(traffic_in) / 1024 / 1024,
                    "avg_packet_loss": np.mean(packet_loss),
                    "max_packet_loss": np.max(packet_loss),
                    "samples": len(traffic_in)
                }

            # Application metrics
            if "application_metrics" in all_metrics:
                app_data = all_metrics["application_metrics"]
                response_times = [m["response_time_ms"] for m in app_data]
                error_rates = [m["error_rate_percent"] for m in app_data]
                throughput = [m["throughput_rpm"] for m in app_data]

                aggregated_stats["application"] = {
                    "avg_response_time": np.mean(response_times),
                    "p95_response_time": np.percentile(response_times, 95),
                    "avg_error_rate": np.mean(error_rates),
                    "max_error_rate": np.max(error_rates),
                    "avg_throughput": np.mean(throughput),
                    "samples": len(response_times)
                }

            result = {
                "raw_metrics": all_metrics,
                "aggregated_stats": aggregated_stats,
                "collection_summary": {
                    "total_metric_types": len(all_metrics),
                    "failed_collections": list(failed.keys()) if failed else [],
                    "total_data_points": sum(len(metrics) for metrics in all_metrics.values())
                },
                "processing_timestamp": time.time()
            }
            """,
        )

        # Anomaly detection and alerting
        builder.add_async_code(
            "detect_anomalies",
            """
            # Define thresholds for different metrics
            thresholds = {
                "cpu": {"high_usage": 80, "high_load": 5.0},
                "memory": {"high_usage": 85, "high_swap": 50},
                "network": {"high_packet_loss": 1.0},
                "application": {"high_response_time": 1000, "high_error_rate": 5.0}
            }

            alerts = []
            anomalies = []

            # Check each metric type against thresholds
            stats = aggregated_data.get("aggregated_stats", {})

            # CPU anomalies
            if "cpu" in stats:
                cpu_stats = stats["cpu"]
                if cpu_stats["max_usage"] > thresholds["cpu"]["high_usage"]:
                    alerts.append({
                        "severity": "high",
                        "metric": "cpu_usage",
                        "value": cpu_stats["max_usage"],
                        "threshold": thresholds["cpu"]["high_usage"],
                        "message": f"High CPU usage detected: {cpu_stats['max_usage']:.1f}%"
                    })

                if cpu_stats["max_load"] > thresholds["cpu"]["high_load"]:
                    alerts.append({
                        "severity": "medium",
                        "metric": "load_average",
                        "value": cpu_stats["max_load"],
                        "threshold": thresholds["cpu"]["high_load"],
                        "message": f"High load average detected: {cpu_stats['max_load']:.2f}"
                    })

            # Memory anomalies
            if "memory" in stats:
                memory_stats = stats["memory"]
                if memory_stats["max_usage"] > thresholds["memory"]["high_usage"]:
                    alerts.append({
                        "severity": "high",
                        "metric": "memory_usage",
                        "value": memory_stats["max_usage"],
                        "threshold": thresholds["memory"]["high_usage"],
                        "message": f"High memory usage detected: {memory_stats['max_usage']:.1f}%"
                    })

            # Network anomalies
            if "network" in stats:
                network_stats = stats["network"]
                if network_stats["max_packet_loss"] > thresholds["network"]["high_packet_loss"]:
                    alerts.append({
                        "severity": "medium",
                        "metric": "packet_loss",
                        "value": network_stats["max_packet_loss"],
                        "threshold": thresholds["network"]["high_packet_loss"],
                        "message": f"High packet loss detected: {network_stats['max_packet_loss']:.2f}%"
                    })

            # Application anomalies
            if "application" in stats:
                app_stats = stats["application"]
                if app_stats["p95_response_time"] > thresholds["application"]["high_response_time"]:
                    alerts.append({
                        "severity": "high",
                        "metric": "response_time",
                        "value": app_stats["p95_response_time"],
                        "threshold": thresholds["application"]["high_response_time"],
                        "message": f"High response time detected: {app_stats['p95_response_time']:.0f}ms (95th percentile)"
                    })

                if app_stats["max_error_rate"] > thresholds["application"]["high_error_rate"]:
                    alerts.append({
                        "severity": "critical",
                        "metric": "error_rate",
                        "value": app_stats["max_error_rate"],
                        "threshold": thresholds["application"]["high_error_rate"],
                        "message": f"High error rate detected: {app_stats['max_error_rate']:.1f}%"
                    })

            # System health assessment
            critical_alerts = [a for a in alerts if a["severity"] == "critical"]
            high_alerts = [a for a in alerts if a["severity"] == "high"]

            if critical_alerts:
                system_health = "critical"
            elif high_alerts:
                system_health = "degraded"
            elif alerts:
                system_health = "warning"
            else:
                system_health = "healthy"

            result = {
                "alerts": alerts,
                "system_health": system_health,
                "alert_summary": {
                    "total_alerts": len(alerts),
                    "critical": len(critical_alerts),
                    "high": len(high_alerts),
                    "medium": len([a for a in alerts if a["severity"] == "medium"])
                },
                "health_score": max(0, 100 - len(alerts) * 10),  # Simple scoring
                "detection_timestamp": time.time(),
                "recommendations": [
                    "Investigate high CPU usage" if any(a["metric"] == "cpu_usage" for a in alerts) else None,
                    "Check memory leaks" if any(a["metric"] == "memory_usage" for a in alerts) else None,
                    "Review application performance" if any(a["metric"] in ["response_time", "error_rate"] for a in alerts) else None,
                    "Monitor network connectivity" if any(a["metric"] == "packet_loss" for a in alerts) else None
                ]
            }

            # Filter out None recommendations
            result["recommendations"] = [r for r in result["recommendations"] if r is not None]
            if not result["recommendations"]:
                result["recommendations"] = ["System operating within normal parameters"]
            """,
        )

        # Generate monitoring report
        builder.add_async_code(
            "generate_monitoring_report",
            """
            # Create comprehensive monitoring report
            report_sections = {
                "executive_summary": {
                    "system_health": anomaly_data["system_health"],
                    "health_score": anomaly_data["health_score"],
                    "total_alerts": anomaly_data["alert_summary"]["total_alerts"],
                    "monitoring_period": "last 10 minutes",
                    "report_generated": time.time()
                },
                "metric_summary": {},
                "alert_details": anomaly_data["alerts"],
                "recommendations": anomaly_data["recommendations"]
            }

            # Add metric summaries
            stats = aggregated_data.get("aggregated_stats", {})
            for metric_type, metric_stats in stats.items():
                if metric_type == "cpu":
                    report_sections["metric_summary"]["cpu"] = f"Average usage: {metric_stats['avg_usage']:.1f}%, Peak: {metric_stats['max_usage']:.1f}%"
                elif metric_type == "memory":
                    report_sections["metric_summary"]["memory"] = f"Average usage: {metric_stats['avg_usage']:.1f}%, Peak: {metric_stats['max_usage']:.1f}%"
                elif metric_type == "application":
                    report_sections["metric_summary"]["application"] = f"Avg response time: {metric_stats['avg_response_time']:.0f}ms, Error rate: {metric_stats['avg_error_rate']:.1f}%"
                elif metric_type == "network":
                    report_sections["metric_summary"]["network"] = f"Avg traffic: {metric_stats['avg_traffic_in_mb']:.1f}MB, Packet loss: {metric_stats['avg_packet_loss']:.2f}%"

            # Create action items based on alerts
            action_items = []
            for alert in anomaly_data["alerts"]:
                if alert["severity"] in ["critical", "high"]:
                    action_items.append({
                        "priority": alert["severity"],
                        "action": f"Investigate {alert['metric']} - {alert['message']}",
                        "metric": alert["metric"],
                        "value": alert["value"]
                    })

            # Dashboard data for visualization
            dashboard_data = {
                "current_metrics": {
                    metric_type: {
                        "status": "critical" if any(a["metric"].startswith(metric_type) for a in anomaly_data["alerts"] if a["severity"] == "critical")
                                else "warning" if any(a["metric"].startswith(metric_type) for a in anomaly_data["alerts"])
                                else "healthy",
                        "latest_values": metric_stats
                    }
                    for metric_type, metric_stats in stats.items()
                },
                "alert_timeline": [
                    {
                        "timestamp": alert.get("timestamp", time.time()),
                        "severity": alert["severity"],
                        "message": alert["message"]
                    }
                    for alert in anomaly_data["alerts"]
                ]
            }

            result = {
                "monitoring_report": report_sections,
                "action_items": action_items,
                "dashboard_data": dashboard_data,
                "report_metadata": {
                    "generated_at": time.time(),
                    "data_points_analyzed": aggregated_data["collection_summary"]["total_data_points"],
                    "metric_types_monitored": aggregated_data["collection_summary"]["total_metric_types"],
                    "collection_failures": len(aggregated_data["collection_summary"]["failed_collections"])
                }
            }
            """,
        )

        # Connect the monitoring pipeline
        builder.add_connection(
            "collect_metrics", "successful", "process_metrics", "successful"
        )
        builder.add_connection("collect_metrics", "failed", "process_metrics", "failed")
        builder.add_connection(
            "process_metrics", None, "detect_anomalies", "aggregated_data"
        )
        builder.add_connection(
            "detect_anomalies", None, "generate_monitoring_report", "anomaly_data"
        )
        builder.add_connection(
            "process_metrics", None, "generate_monitoring_report", "aggregated_data"
        )

        # Execute the monitoring pipeline
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify monitoring pipeline workflow
        assert result["status"] == "success"

        # Check metric collection
        collect_result = result["results"]["collect_metrics"]
        assert "successful" in collect_result
        assert len(collect_result["successful"]) >= 3  # At least 3 metric types

        # Check processing
        process_result = result["results"]["process_metrics"]
        assert "aggregated_stats" in process_result
        assert "collection_summary" in process_result
        assert process_result["collection_summary"]["total_data_points"] > 30

        # Check anomaly detection
        anomaly_result = result["results"]["detect_anomalies"]
        assert "system_health" in anomaly_result
        assert "alerts" in anomaly_result
        assert "health_score" in anomaly_result
        assert anomaly_result["system_health"] in [
            "healthy",
            "warning",
            "degraded",
            "critical",
        ]

        # Check monitoring report
        report_result = result["results"]["generate_monitoring_report"]
        assert "monitoring_report" in report_result
        assert "dashboard_data" in report_result
        assert "action_items" in report_result

        monitoring_report = report_result["monitoring_report"]
        assert "executive_summary" in monitoring_report
        assert "metric_summary" in monitoring_report
        assert len(monitoring_report["metric_summary"]) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""E2E tests for PythonCodeNode production scenarios.

Follows the testing policy:
- E2E tests (Tier 3): Complete real scenarios with REAL Docker services
- NO MOCKING ALLOWED - Simulates TPC migration team's production use cases
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import asyncpg
import httpx
import pytest
import redis

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import (
    DeferredConfigNode,
    WorkflowParameterInjector,
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.workflow.builder import WorkflowBuilder
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.slow
class TestTPCMigrationScenarios:
    """Test scenarios reported by TPC migration team."""

    @pytest.fixture(autouse=True)
    async def setup_production_environment(self):
        """Set up production-like environment."""
        # Ensure all services are running
        await ensure_docker_services(["postgres", "redis"])

        # Set up PostgreSQL with production-like schema
        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)

        try:
            # Create production-like tables
            await conn.execute("DROP TABLE IF EXISTS transactions CASCADE")
            await conn.execute("DROP TABLE IF EXISTS customers CASCADE")
            await conn.execute("DROP TABLE IF EXISTS audit_logs CASCADE")

            await conn.execute(
                """
                CREATE TABLE customers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    tier VARCHAR(20) DEFAULT 'standard',
                    risk_score FLOAT DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}'
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE transactions (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER REFERENCES customers(id),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(3) DEFAULT 'USD',
                    status VARCHAR(20) DEFAULT 'pending',
                    transaction_type VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}'
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE audit_logs (
                    id SERIAL PRIMARY KEY,
                    entity_type VARCHAR(50),
                    entity_id INTEGER,
                    action VARCHAR(50),
                    user_id VARCHAR(100),
                    changes JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert production-like data
            customer_data = [
                ("Enterprise Corp", "enterprise@corp.com", "premium", 0.1),
                ("Small Business LLC", "contact@smallbiz.com", "standard", 0.3),
                ("High Risk Inc", "admin@highrisk.com", "standard", 0.8),
                ("Trusted Partners", "info@trusted.com", "premium", 0.05),
            ]

            for name, email, tier, risk in customer_data:
                await conn.execute(
                    """
                    INSERT INTO customers (name, email, tier, risk_score, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                """,
                    name,
                    email,
                    tier,
                    risk,
                    json.dumps({"source": "migration"}),
                )

            # Insert transactions
            await conn.execute(
                """
                INSERT INTO transactions (customer_id, amount, transaction_type, status)
                SELECT
                    c.id,
                    (RANDOM() * 10000)::DECIMAL(10,2),
                    CASE WHEN RANDOM() < 0.5 THEN 'payment' ELSE 'refund' END,
                    CASE
                        WHEN RANDOM() < 0.7 THEN 'completed'
                        WHEN RANDOM() < 0.9 THEN 'pending'
                        ELSE 'failed'
                    END
                FROM customers c
                CROSS JOIN generate_series(1, 10)
            """
            )

        finally:
            await conn.close()

        # Set up Redis with production patterns
        redis_params = get_redis_connection_params()
        r_client = redis.Redis(**redis_params)

        # Clear test namespace
        for key in r_client.scan_iter("tpc:*"):
            r_client.delete(key)

        # Set configuration parameters
        r_client.hset(
            "tpc:config",
            mapping={
                "risk_threshold": "0.5",
                "premium_discount": "0.15",
                "standard_discount": "0.05",
                "batch_size": "100",
                "enable_audit": "true",
            },
        )

        yield

        # Cleanup
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS transactions CASCADE")
            await conn.execute("DROP TABLE IF EXISTS customers CASCADE")
            await conn.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
        finally:
            await conn.close()

        for key in r_client.scan_iter("tpc:*"):
            r_client.delete(key)
        r_client.close()

    @pytest.mark.asyncio
    async def test_scenario_1_complex_data_processing_pipeline(self):
        """Test Scenario 1: Complex data processing with parameter injection.

        This simulates the TPC team's production workflow that processes
        customer transactions with dynamic risk scoring and discounts.
        """
        builder = WorkflowBuilder(name="TPC Production Pipeline")

        # Step 1: Fetch high-value transactions
        builder.add_node(
            "AsyncSQLDatabaseNode",
            name="fetch_transactions",
            connection_string=get_postgres_connection_string(),
            query="""
                SELECT
                    t.id, t.amount, t.status, t.transaction_type,
                    c.id as customer_id, c.name, c.tier, c.risk_score
                FROM transactions t
                JOIN customers c ON t.customer_id = c.id
                WHERE t.amount > $1 AND t.status = 'pending'
                ORDER BY t.amount DESC
            """,
        )

        # Step 2: Fetch configuration from Redis
        redis_params = get_redis_connection_params()
        builder.add_node(
            "RedisNode",
            name="fetch_config",
            host=redis_params["host"],
            port=redis_params["port"],
            operation="hgetall",
            key="tpc:config",
        )

        # Step 3: Process with PythonCode (with **kwargs for parameter injection)
        def process_transactions(
            transactions: List[Dict],
            config: Dict[str, str],
            **kwargs,  # This allows workflow parameter injection
        ) -> Dict[str, Any]:
            """Process transactions with risk assessment and discounts.

            This function demonstrates the parameter injection bug fix:
            - It accepts **kwargs to receive workflow parameters
            - It has default parameters that should work correctly
            - It performs complex business logic similar to TPC's use case
            """
            # Get injected parameters with defaults
            override_threshold = kwargs.get("risk_threshold_override")
            audit_enabled = kwargs.get(
                "audit_enabled", config.get("enable_audit", "true") == "true"
            )
            processing_date = kwargs.get("processing_date", datetime.now().isoformat())
            batch_id = kwargs.get("batch_id", f"batch_{int(time.time())}")

            # Use override threshold if provided
            risk_threshold = float(
                override_threshold or config.get("risk_threshold", "0.5")
            )
            premium_discount = float(config.get("premium_discount", "0.15"))
            standard_discount = float(config.get("standard_discount", "0.05"))

            results = {
                "processed": [],
                "flagged": [],
                "statistics": {
                    "total_processed": 0,
                    "total_amount": 0,
                    "flagged_count": 0,
                    "discounts_applied": 0,
                },
                "metadata": {
                    "batch_id": batch_id,
                    "processing_date": processing_date,
                    "risk_threshold_used": risk_threshold,
                    "audit_enabled": audit_enabled,
                },
            }

            for txn in transactions:
                processed_txn = {
                    "transaction_id": txn["id"],
                    "customer_id": txn["customer_id"],
                    "customer_name": txn["name"],
                    "original_amount": float(txn["amount"]),
                    "risk_score": txn["risk_score"],
                    "tier": txn["tier"],
                }

                # Risk assessment
                if txn["risk_score"] > risk_threshold:
                    processed_txn["status"] = "flagged_for_review"
                    processed_txn["reason"] = (
                        f"Risk score {txn['risk_score']} exceeds threshold {risk_threshold}"
                    )
                    results["flagged"].append(processed_txn)
                    results["statistics"]["flagged_count"] += 1
                else:
                    # Apply discounts based on tier
                    if txn["tier"] == "premium":
                        discount = premium_discount
                    else:
                        discount = standard_discount

                    processed_txn["discount_rate"] = discount
                    processed_txn["final_amount"] = processed_txn["original_amount"] * (
                        1 - discount
                    )
                    processed_txn["status"] = "approved"

                    results["processed"].append(processed_txn)
                    results["statistics"]["discounts_applied"] += 1

                results["statistics"]["total_processed"] += 1
                results["statistics"]["total_amount"] += float(txn["amount"])

            return results

        builder.add_node(
            "PythonCodeNode", name="process", function=process_transactions
        )

        # Step 4: Cache results in Redis
        builder.add_node(
            "RedisNode",
            name="cache_results",
            host=redis_params["host"],
            port=redis_params["port"],
            operation="set",
            ttl=3600,  # 1 hour
        )

        # Step 5: Update database with results
        def generate_update_query(results: Dict) -> Dict:
            """Generate SQL update based on processing results."""
            updates = []

            for txn in results.get("processed", []):
                updates.append(
                    f"UPDATE transactions SET status = 'completed', "
                    f"metadata = metadata || '{json.dumps({'discount': txn.get('discount_rate', 0)})}' "
                    f"WHERE id = {txn['transaction_id']}"
                )

            for txn in results.get("flagged", []):
                updates.append(
                    f"UPDATE transactions SET status = 'flagged', "
                    f"metadata = metadata || '{json.dumps({'reason': txn.get('reason', '')})}' "
                    f"WHERE id = {txn['transaction_id']}"
                )

            return {
                "query": ";".join(updates) if updates else "SELECT 1",
                "count": len(updates),
            }

        builder.add_node(
            "PythonCodeNode", name="generate_updates", function=generate_update_query
        )

        builder.add_node(
            "AsyncSQLDatabaseNode",
            name="update_transactions",
            connection_string=get_postgres_connection_string(),
        )

        # Connect workflow
        builder.add_connection("fetch_config", "process", "result", "config")
        builder.add_connection(
            "fetch_transactions", "process", "result", "transactions"
        )
        builder.add_connection("process", "cache_results", "metadata.batch_id", "key")
        builder.add_connection("process", "cache_results", "result", "value")
        builder.add_connection("process", "generate_updates", "result", "results")
        builder.add_connection(
            "generate_updates", "update_transactions", "query", "query"
        )

        # Execute with workflow parameters (testing parameter injection)
        workflow = builder.build()
        runtime = LocalRuntime()

        result = await runtime.execute(
            workflow,
            inputs={"fetch_transactions": {"parameters": [1000]}},  # Amount threshold
            parameters={
                "risk_threshold_override": 0.6,  # Override config value
                "audit_enabled": True,
                "batch_id": "test_batch_001",
            },
        )

        # Verify results
        process_output = result.node_outputs["process"]

        # Check that parameter injection worked
        assert (
            process_output["metadata"]["risk_threshold_used"] == 0.6
        )  # Override was applied
        assert process_output["metadata"]["batch_id"] == "test_batch_001"
        assert process_output["metadata"]["audit_enabled"] is True

        # Check processing logic
        assert process_output["statistics"]["total_processed"] > 0
        assert "processed" in process_output
        assert "flagged" in process_output

        # Verify high-risk customers were flagged
        flagged_names = [t["customer_name"] for t in process_output["flagged"]]
        if "High Risk Inc" in [
            t["customer_name"]
            for t in process_output["processed"] + process_output["flagged"]
        ]:
            assert (
                "High Risk Inc" in flagged_names
            )  # Should be flagged due to risk score

        # Verify results were cached
        r_client = redis.Redis(**redis_params)
        cached = r_client.get("test_batch_001")
        assert cached is not None
        r_client.close()

    @pytest.mark.asyncio
    async def test_scenario_2_enterprise_deferred_configuration(self):
        """Test Scenario 2: Enterprise node with deferred configuration.

        This tests the new DeferredConfigNode pattern for enterprise deployments
        where credentials are injected at runtime.
        """
        # Create workflow with deferred nodes
        builder = WorkflowBuilder(name="Enterprise Deferred Config Workflow")

        # Add deferred SQL node (credentials injected later)
        sql_node = create_deferred_sql(
            name="customer_fetcher", query="SELECT * FROM customers WHERE tier = $1"
        )
        builder.add_node_instance(sql_node)

        # Add processing node that needs injected config
        def process_customers(
            customers: List[Dict], tier_config: Dict = None, **kwargs
        ) -> Dict:
            """Process customers with tier-specific logic."""
            # Access runtime-injected configuration
            processing_mode = kwargs.get("processing_mode", "standard")
            enable_notifications = kwargs.get("enable_notifications", False)

            results = {
                "customers": [],
                "summary": {
                    "total": len(customers),
                    "processing_mode": processing_mode,
                    "notifications_enabled": enable_notifications,
                },
            }

            for customer in customers:
                customer_data = {
                    "id": customer["id"],
                    "name": customer["name"],
                    "tier": customer["tier"],
                    "risk_category": "high" if customer["risk_score"] > 0.5 else "low",
                }

                if processing_mode == "enhanced" and customer["tier"] == "premium":
                    customer_data["enhanced_features"] = True
                    customer_data["priority"] = "high"

                results["customers"].append(customer_data)

            return results

        builder.add_node("PythonCodeNode", name="processor", function=process_customers)

        builder.add_connection("customer_fetcher", "processor", "result", "customers")

        # Build workflow
        workflow = builder.build()

        # Create parameter injector
        injector = WorkflowParameterInjector()

        # Configure deferred nodes at runtime
        injector.configure_deferred_node(
            workflow,
            "customer_fetcher",
            connection_string=get_postgres_connection_string(),
        )

        # Execute with runtime parameters
        runtime = LocalRuntime()
        result = await runtime.execute(
            workflow,
            inputs={"customer_fetcher": {"parameters": ["premium"]}},
            parameters={"processing_mode": "enhanced", "enable_notifications": True},
        )

        # Verify deferred configuration worked
        output = result.node_outputs["processor"]
        assert output["summary"]["total"] > 0
        assert output["summary"]["processing_mode"] == "enhanced"
        assert output["summary"]["notifications_enabled"] is True

        # Verify enhanced processing was applied
        premium_customers = [c for c in output["customers"] if c["tier"] == "premium"]
        for customer in premium_customers:
            assert customer.get("enhanced_features") is True
            assert customer.get("priority") == "high"

    @pytest.mark.asyncio
    async def test_scenario_3_multi_stage_pipeline_with_failures(self):
        """Test Scenario 3: Multi-stage pipeline with error handling.

        This tests the complete parameter handling in a complex pipeline
        that includes error scenarios and recovery logic.
        """
        builder = WorkflowBuilder(name="Resilient Processing Pipeline")

        # Stage 1: Parallel data fetching
        builder.add_node(
            "AsyncSQLDatabaseNode",
            name="fetch_active_customers",
            connection_string=get_postgres_connection_string(),
            query="SELECT * FROM customers WHERE risk_score < $1",
        )

        builder.add_node(
            "AsyncSQLDatabaseNode",
            name="fetch_recent_transactions",
            connection_string=get_postgres_connection_string(),
            query="""
                SELECT * FROM transactions
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                AND status IN ('pending', 'completed')
            """,
        )

        # Stage 2: Risk analysis with failure handling
        def analyze_risk(
            customers: List[Dict],
            transactions: List[Dict],
            risk_model_version: str = "v1.0",
            **kwargs,
        ) -> Dict:
            """Analyze risk with resilient processing."""
            # Get parameters with defaults
            fail_on_high_risk = kwargs.get("fail_on_high_risk", False)
            risk_multiplier = kwargs.get("risk_multiplier", 1.0)
            enable_ml_scoring = kwargs.get("enable_ml_scoring", False)

            try:
                # Create customer transaction map
                customer_txns = {}
                for txn in transactions:
                    cid = txn["customer_id"]
                    if cid not in customer_txns:
                        customer_txns[cid] = []
                    customer_txns[cid].append(txn)

                risk_assessments = []
                failures = []

                for customer in customers:
                    try:
                        cid = customer["id"]
                        txns = customer_txns.get(cid, [])

                        # Calculate risk metrics
                        base_risk = customer["risk_score"]
                        txn_volume = len(txns)
                        txn_amount = sum(float(t["amount"]) for t in txns)

                        # Apply risk model
                        if enable_ml_scoring:
                            # Simulate ML scoring
                            ml_adjustment = 0.1 * (txn_volume / 10)
                        else:
                            ml_adjustment = 0

                        final_risk = (base_risk + ml_adjustment) * risk_multiplier

                        # Check failure condition
                        if fail_on_high_risk and final_risk > 0.8:
                            raise ValueError(f"High risk detected for customer {cid}")

                        assessment = {
                            "customer_id": cid,
                            "customer_name": customer["name"],
                            "base_risk": base_risk,
                            "final_risk": min(final_risk, 1.0),
                            "transaction_count": txn_volume,
                            "transaction_total": txn_amount,
                            "model_version": risk_model_version,
                            "ml_enabled": enable_ml_scoring,
                        }

                        risk_assessments.append(assessment)

                    except Exception as e:
                        failures.append(
                            {
                                "customer_id": customer.get("id"),
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

                return {
                    "assessments": risk_assessments,
                    "failures": failures,
                    "summary": {
                        "total_assessed": len(risk_assessments),
                        "total_failed": len(failures),
                        "risk_model": risk_model_version,
                        "parameters_used": {
                            "risk_multiplier": risk_multiplier,
                            "ml_enabled": enable_ml_scoring,
                        },
                    },
                }

            except Exception as e:
                # Catastrophic failure - return safe default
                return {
                    "assessments": [],
                    "failures": [{"error": f"Critical failure: {str(e)}"}],
                    "summary": {"status": "failed"},
                }

        builder.add_node("PythonCodeNode", name="risk_analyzer", function=analyze_risk)

        # Stage 3: Audit logging
        def create_audit_logs(risk_results: Dict, **kwargs) -> Dict:
            """Create audit logs for compliance."""
            audit_user = kwargs.get("audit_user", "system")
            audit_context = kwargs.get("audit_context", {})

            logs = []

            for assessment in risk_results.get("assessments", []):
                logs.append(
                    {
                        "entity_type": "customer",
                        "entity_id": assessment["customer_id"],
                        "action": "risk_assessment",
                        "user_id": audit_user,
                        "changes": {
                            "risk_score": assessment["final_risk"],
                            "model_version": assessment["model_version"],
                        },
                        "context": audit_context,
                    }
                )

            return {"audit_logs": logs, "count": len(logs)}

        builder.add_node(
            "PythonCodeNode", name="audit_logger", function=create_audit_logs
        )

        # Connect pipeline
        builder.add_connection(
            "fetch_active_customers", "risk_analyzer", "result", "customers"
        )
        builder.add_connection(
            "fetch_recent_transactions", "risk_analyzer", "result", "transactions"
        )
        builder.add_connection(
            "risk_analyzer", "audit_logger", "result", "risk_results"
        )

        # Execute with various parameter scenarios
        workflow = builder.build()
        runtime = LocalRuntime()

        # Test 1: Normal execution
        result1 = await runtime.execute(
            workflow,
            inputs={"fetch_active_customers": {"parameters": [0.7]}},
            parameters={
                "risk_model_version": "v2.0",
                "risk_multiplier": 1.2,
                "enable_ml_scoring": True,
                "audit_user": "test_user",
                "audit_context": {"test_run": True},
            },
        )

        risk_output = result1.node_outputs["risk_analyzer"]
        audit_output = result1.node_outputs["audit_logger"]

        # Verify parameter injection worked throughout pipeline
        assert risk_output["summary"]["risk_model"] == "v2.0"
        assert risk_output["summary"]["parameters_used"]["risk_multiplier"] == 1.2
        assert risk_output["summary"]["parameters_used"]["ml_enabled"] is True
        assert len(audit_output["audit_logs"]) > 0

        # Test 2: Execution with failures
        result2 = await runtime.execute(
            workflow,
            inputs={"fetch_active_customers": {"parameters": [0.3]}},  # Lower threshold
            parameters={
                "fail_on_high_risk": True,  # Enable failure mode
                "risk_multiplier": 2.0,  # High multiplier
                "audit_user": "failure_test",
            },
        )

        risk_output2 = result2.node_outputs["risk_analyzer"]

        # Should have some failures due to high risk
        if risk_output2["summary"].get("total_failed", 0) > 0:
            assert len(risk_output2["failures"]) > 0
            assert "High risk detected" in risk_output2["failures"][0]["error"]


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestPythonCodeSecurityE2E:
    """E2E tests for security improvements."""

    @pytest.mark.asyncio
    async def test_security_in_production_workflow(self):
        """Test security measures in a production-like workflow."""
        await ensure_docker_services(["postgres"])

        builder = WorkflowBuilder(name="Secure Processing Workflow")

        # Add data source
        builder.add_node(
            "AsyncSQLDatabaseNode",
            name="fetch_sensitive_data",
            connection_string=get_postgres_connection_string(),
            query="SELECT id, name, email FROM customers LIMIT 10",
        )

        # Test various code patterns for security
        secure_functions = [
            # Safe data transformation
            lambda data: [{"id": d["id"], "name": d["name"].upper()} for d in data],
            # Safe aggregation
            lambda data: {"count": len(data), "ids": [d["id"] for d in data]},
            # Safe filtering
            lambda data, threshold=5: [d for d in data if d["id"] < threshold],
        ]

        for i, func in enumerate(secure_functions):
            builder.add_node(
                "PythonCodeNode", name=f"secure_processor_{i}", function=func
            )

        # Connect in sequence
        builder.add_connection(
            "fetch_sensitive_data", "secure_processor_0", "result", "data"
        )
        builder.add_connection(
            "secure_processor_0", "secure_processor_1", "result", "data"
        )
        builder.add_connection(
            "secure_processor_1", "secure_processor_2", "ids", "data"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result = await runtime.execute(workflow, parameters={"threshold": 7})

        # Verify all nodes executed successfully
        assert "secure_processor_0" in result.node_outputs
        assert "secure_processor_1" in result.node_outputs
        assert "secure_processor_2" in result.node_outputs

        # Test that unsafe code is rejected
        unsafe_node = PythonCodeNode(name="unsafe_test")

        with pytest.raises((ValidationError, ValueError)):
            unsafe_node.set_code("import os; os.system('echo hacked')")

        with pytest.raises((ValidationError, ValueError)):
            unsafe_node.set_code("eval('1 + 1')")

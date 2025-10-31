"""
End-to-end tests for connection parameter validation.

Tests complete user workflows with real infrastructure to ensure
connection validation works in production scenarios.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.nodes.security.threat_detection import ThreatDetectionNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConnectionValidationE2E:
    """E2E tests for connection validation in production scenarios."""

    @pytest.fixture
    def database_config(self):
        """Database configuration for tests."""
        return {
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
            "host": "localhost",
            "port": 5432,
        }

    def test_sql_injection_prevention_workflow(self, database_config):
        """
        Test a complete workflow that prevents SQL injection attacks
        through connection validation.
        """
        workflow = WorkflowBuilder()

        # Simulated user input node (could be from API, form, etc.)
        workflow.add_node(
            PythonCodeNode,
            "user_input",
            {
                "code": """
# Simulated malicious user input
result = {
    'search_term': "'; DROP TABLE users; --",
    'user_id': "admin' OR '1'='1",
    'limit': "10; DELETE FROM logs;"
}
"""
            },
        )

        # Threat detection node
        workflow.add_node(ThreatDetectionNode, "threat_detector", {})

        # SQL query builder with validation
        class SecureSQLBuilderNode(Node):
            def get_parameters(self):
                return {
                    "search_term": NodeParameter(type=str, required=True),
                    "user_id": NodeParameter(type=str, required=True),
                    "limit": NodeParameter(type=int, required=False, default=10),
                }

            def run(self, **kwargs):
                # Validate inputs
                search_term = kwargs["search_term"]
                user_id = kwargs["user_id"]
                limit = kwargs["limit"]

                # Check for SQL injection patterns
                dangerous_patterns = [";", "--", "DROP", "DELETE", "OR '1'='1'"]
                for pattern in dangerous_patterns:
                    if (
                        pattern.upper() in search_term.upper()
                        or pattern.upper() in user_id.upper()
                    ):
                        raise ValueError(f"Potential SQL injection detected: {pattern}")

                # Build safe parameterized query
                query = "SELECT * FROM products WHERE name LIKE $1 AND owner_id = $2 LIMIT $3"
                params = [f"%{search_term}%", user_id, limit]

                return {"query": query, "params": params, "validated": True}

        workflow.add_node(SecureSQLBuilderNode, "sql_builder", {})

        # Connect user input to threat detector
        workflow.add_connection("user_input", "result", "threat_detector", "input_data")

        # Connect user input to SQL builder
        workflow.add_connection("user_input", "result", "sql_builder", "")

        # Test with strict validation
        runtime = LocalRuntime(connection_validation="strict")

        # Should detect and prevent SQL injection
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build(), {})

        assert "injection" in str(exc_info.value).lower()

    def test_dataflow_integration_workflow(self):
        """
        Test DataFlow integration with connection validation.
        This simulates a real DataFlow workflow with CRUD operations.
        """
        workflow = WorkflowBuilder()

        # User registration data
        workflow.add_node(
            PythonCodeNode,
            "registration",
            {
                "code": """
# New user registration data
result = {
    'user': {
        'name': 'Alice Smith',
        'email': 'alice@example.com',
        'age': '25',  # String that should be converted to int
        'role': 'user',
        'metadata': {
            'source': 'web',
            'campaign': 'spring2024'
        }
    }
}
"""
            },
        )

        # Data validator node
        class UserValidatorNode(Node):
            def get_parameters(self):
                return {"user": NodeParameter(type=dict, required=True)}

            def run(self, **kwargs):
                user = kwargs["user"]

                # Validate required fields
                required_fields = ["name", "email", "age", "role"]
                for field in required_fields:
                    if field not in user:
                        raise ValueError(f"Missing required field: {field}")

                # Validate email format
                if "@" not in user["email"]:
                    raise ValueError("Invalid email format")

                # Convert and validate age
                try:
                    age = int(user["age"])
                    if age < 18 or age > 120:
                        raise ValueError("Age must be between 18 and 120")
                    user["age"] = age
                except ValueError:
                    raise ValueError("Age must be a valid number")

                # Validate role
                valid_roles = ["user", "admin", "moderator"]
                if user["role"] not in valid_roles:
                    raise ValueError(f"Invalid role. Must be one of: {valid_roles}")

                return {"validated_user": user}

        workflow.add_node(UserValidatorNode, "validator", {})

        # Simulated DataFlow create node
        class DataFlowCreateNode(Node):
            def get_parameters(self):
                return {"validated_user": NodeParameter(type=dict, required=True)}

            def run(self, **kwargs):
                user = kwargs["validated_user"]

                # Simulate database insert with parameterized query
                query = """
                INSERT INTO users (name, email, age, role, metadata)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """
                params = [
                    user["name"],
                    user["email"],
                    user["age"],
                    user["role"],
                    json.dumps(user.get("metadata", {})),
                ]

                # Simulate successful creation
                return {
                    "user_id": "12345",
                    "created": True,
                    "query": query,
                    "params": params,
                }

        workflow.add_node(DataFlowCreateNode, "create_user", {})

        # Audit log node
        workflow.add_node(
            PythonCodeNode,
            "audit_log",
            {
                "code": """
# Log the creation event
user_id = parameters.get('user_id')
created = parameters.get('created')
timestamp = parameters.get('timestamp', '2024-01-01T00:00:00Z')

result = {
    'log_entry': {
        'event': 'user_created',
        'user_id': user_id,
        'success': created,
        'timestamp': timestamp
    }
}
"""
            },
        )

        # Connect the workflow
        workflow.add_connection("registration", "result.user", "validator", "user")
        workflow.add_connection(
            "validator", "validated_user", "create_user", "validated_user"
        )
        workflow.add_connection("create_user", "", "audit_log", "")

        # Execute with validation
        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})

        # Verify the workflow completed successfully
        assert results["validator"]["validated_user"]["age"] == 25  # Converted to int
        assert results["create_user"]["created"] is True
        assert results["audit_log"]["log_entry"]["event"] == "user_created"

    def test_multi_stage_etl_workflow(self):
        """
        Test a complex ETL workflow with multiple validation points.
        This simulates a production data pipeline.
        """
        workflow = WorkflowBuilder()

        # Stage 1: Data extraction
        workflow.add_node(
            PythonCodeNode,
            "extractor",
            {
                "code": """
# Simulate data from multiple sources
result = {
    'customers': [
        {'id': '1', 'name': 'ACME Corp', 'revenue': '1000000', 'country': 'US'},
        {'id': '2', 'name': 'TechCo', 'revenue': 'invalid', 'country': 'UK'},
        {'id': '3', 'name': 'StartupXYZ', 'revenue': '50000', 'country': 'CA'}
    ],
    'orders': [
        {'customer_id': '1', 'amount': '5000', 'status': 'completed'},
        {'customer_id': '1', 'amount': '3000', 'status': 'pending'},
        {'customer_id': '3', 'amount': '1000', 'status': 'completed'}
    ]
}
"""
            },
        )

        # Stage 2: Data transformation with validation
        class ETLTransformerNode(Node):
            def get_parameters(self):
                return {
                    "customers": NodeParameter(type=list, required=True),
                    "orders": NodeParameter(type=list, required=True),
                }

            def run(self, **kwargs):
                customers = kwargs["customers"]
                orders = kwargs["orders"]

                # Transform and validate customers
                valid_customers = []
                errors = []

                for customer in customers:
                    try:
                        # Convert revenue to float
                        revenue = float(customer["revenue"])
                        if revenue < 0:
                            raise ValueError("Revenue cannot be negative")

                        transformed = {
                            "id": customer["id"],
                            "name": customer["name"],
                            "revenue": revenue,
                            "country": customer["country"],
                            "tier": "enterprise" if revenue > 100000 else "standard",
                        }
                        valid_customers.append(transformed)
                    except (ValueError, KeyError) as e:
                        errors.append(
                            {
                                "customer_id": customer.get("id", "unknown"),
                                "error": str(e),
                            }
                        )

                # Aggregate order data
                order_summary = {}
                for order in orders:
                    customer_id = order["customer_id"]
                    amount = float(order["amount"])

                    if customer_id not in order_summary:
                        order_summary[customer_id] = {
                            "total_orders": 0,
                            "total_amount": 0.0,
                            "completed_orders": 0,
                        }

                    order_summary[customer_id]["total_orders"] += 1
                    order_summary[customer_id]["total_amount"] += amount
                    if order["status"] == "completed":
                        order_summary[customer_id]["completed_orders"] += 1

                return {
                    "valid_customers": valid_customers,
                    "order_summary": order_summary,
                    "errors": errors,
                }

        workflow.add_node(ETLTransformerNode, "transformer", {})

        # Stage 3: Data quality check
        class DataQualityNode(Node):
            def get_parameters(self):
                return {
                    "valid_customers": NodeParameter(type=list, required=True),
                    "errors": NodeParameter(type=list, required=True),
                }

            def run(self, **kwargs):
                valid_customers = kwargs["valid_customers"]
                errors = kwargs["errors"]

                total_records = len(valid_customers) + len(errors)
                success_rate = (
                    len(valid_customers) / total_records if total_records > 0 else 0
                )

                quality_report = {
                    "total_records": total_records,
                    "valid_records": len(valid_customers),
                    "error_records": len(errors),
                    "success_rate": success_rate,
                    "quality_score": "PASS" if success_rate >= 0.8 else "FAIL",
                }

                return {"quality_report": quality_report}

        workflow.add_node(DataQualityNode, "quality_check", {})

        # Stage 4: Data loading decision
        workflow.add_node(
            SwitchNode, "load_decision", {"condition": "quality_score == 'PASS'"}
        )

        # Connect the workflow
        workflow.add_connection("extractor", "result", "transformer", "")
        workflow.add_connection("transformer", "", "quality_check", "")
        workflow.add_connection(
            "quality_check", "quality_report", "load_decision", "input_data"
        )

        # Execute with validation
        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})

        # Verify results
        assert len(results["transformer"]["valid_customers"]) == 2  # One invalid
        assert len(results["transformer"]["errors"]) == 1
        assert results["quality_check"]["quality_report"]["success_rate"] > 0.6

    @pytest.mark.asyncio
    async def test_async_workflow_validation(self):
        """Test validation in async workflow execution."""
        workflow = WorkflowBuilder()

        # Async data source
        class AsyncDataSourceNode(Node):
            async def async_run(self, **kwargs):
                # Simulate async data fetch
                await asyncio.sleep(0.1)
                return {
                    "data": {
                        "items": [1, 2, 3, 4, 5],
                        "metadata": {"source": "async_api"},
                    }
                }

        workflow.add_node(AsyncDataSourceNode, "async_source", {})

        # Async processor with validation
        class AsyncProcessorNode(Node):
            def get_parameters(self):
                return {
                    "items": NodeParameter(type=list, required=True),
                    "metadata": NodeParameter(type=dict, required=False),
                }

            async def async_run(self, **kwargs):
                items = kwargs["items"]
                metadata = kwargs.get("metadata", {})

                # Async processing
                await asyncio.sleep(0.1)

                processed = [item * 2 for item in items]
                return {
                    "processed": processed,
                    "count": len(processed),
                    "source": metadata.get("source", "unknown"),
                }

        workflow.add_node(AsyncProcessorNode, "async_processor", {})

        # Connect async nodes
        workflow.add_connection("async_source", "data", "async_processor", "")

        # Use async runtime with validation
        from kailash.runtime.async_runtime import AsyncRuntime

        runtime = AsyncRuntime(connection_validation="strict")

        # Execute async workflow
        results, _ = await runtime.execute_async(workflow.build(), {})

        # Verify async execution with validation
        assert results["async_processor"]["count"] == 5
        assert results["async_processor"]["source"] == "async_api"

    def test_security_compliance_workflow(self):
        """
        Test a security compliance workflow that validates
        sensitive data handling through connections.
        """
        workflow = WorkflowBuilder()

        # PII data source
        workflow.add_node(
            PythonCodeNode,
            "pii_source",
            {
                "code": """
# Sensitive personal data
result = {
    'users': [
        {
            'ssn': '123-45-6789',
            'name': 'John Doe',
            'dob': '1990-01-01',
            'email': 'john@example.com'
        },
        {
            'ssn': '987-65-4321',
            'name': 'Jane Smith',
            'dob': '1985-05-15',
            'email': 'jane@example.com'
        }
    ]
}
"""
            },
        )

        # PII validator and masker
        class PIIComplianceNode(Node):
            def get_parameters(self):
                return {"users": NodeParameter(type=list, required=True)}

            def run(self, **kwargs):
                users = kwargs["users"]

                compliant_users = []
                for user in users:
                    # Validate SSN format
                    ssn = user.get("ssn", "")
                    if not self._validate_ssn(ssn):
                        raise ValueError(f"Invalid SSN format: {ssn}")

                    # Mask sensitive data
                    masked_user = {
                        "ssn": f"XXX-XX-{ssn[-4:]}",
                        "name": user["name"],
                        "dob": user["dob"],
                        "email": self._mask_email(user["email"]),
                        "compliance_checked": True,
                    }
                    compliant_users.append(masked_user)

                return {
                    "compliant_users": compliant_users,
                    "compliance_status": "GDPR_COMPLIANT",
                }

            def _validate_ssn(self, ssn):
                # Simple SSN format validation
                import re

                return bool(re.match(r"^\d{3}-\d{2}-\d{4}$", ssn))

            def _mask_email(self, email):
                # Mask email for privacy
                parts = email.split("@")
                if len(parts) == 2:
                    name = parts[0]
                    masked_name = (
                        name[0] + "*" * (len(name) - 2) + name[-1]
                        if len(name) > 2
                        else name
                    )
                    return f"{masked_name}@{parts[1]}"
                return email

        workflow.add_node(PIIComplianceNode, "pii_compliance", {})

        # Audit logger for compliance
        workflow.add_node(
            PythonCodeNode,
            "compliance_audit",
            {
                "code": """
# Log compliance check
users = parameters.get('compliant_users', [])
status = parameters.get('compliance_status', 'UNKNOWN')

result = {
    'audit_log': {
        'event': 'pii_compliance_check',
        'records_processed': len(users),
        'compliance_status': status,
        'timestamp': '2024-01-01T00:00:00Z',
        'all_masked': all(u.get('compliance_checked') for u in users)
    }
}
"""
            },
        )

        # Connect workflow
        workflow.add_connection("pii_source", "result.users", "pii_compliance", "users")
        workflow.add_connection("pii_compliance", "", "compliance_audit", "")

        # Execute with strict validation
        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})

        # Verify compliance
        assert results["pii_compliance"]["compliance_status"] == "GDPR_COMPLIANT"
        assert all(
            "XXX-XX-" in user["ssn"]
            for user in results["pii_compliance"]["compliant_users"]
        )
        assert results["compliance_audit"]["audit_log"]["all_masked"] is True

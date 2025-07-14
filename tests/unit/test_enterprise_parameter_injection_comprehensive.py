"""Comprehensive Enterprise Parameter Injection Validation.

This test suite validates the complete enterprise parameter injection system
with complex real-world scenarios including multi-tenant authentication,
compliance workflows, and real-time parameter injection.
"""

from datetime import datetime
from typing import Any, Dict, List

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.workflow.builder import WorkflowBuilder


class TestEnterpriseParameterInjectionComprehensive:
    """Comprehensive enterprise parameter injection validation."""

    def test_multi_tenant_authentication_workflow(self):
        """Test Test complex multi-tenant authentication with enterprise parameter injection."""

        try:

        # Step 1: Create authentication workflow with enterprise functions
        builder = WorkflowBuilder()

        def validate_tenant_credentials(
            credentials: Dict[str, str], **kwargs
        ) -> Dict[str, Any]:
            """Enterprise authentication with multi-tenant context."""
            # Extract enterprise parameters via **kwargs
            tenant_id = kwargs.get("tenant_id", "default")
            security_level = kwargs.get("security_level", "standard")
            audit_enabled = kwargs.get("audit_enabled", False)
            compliance_mode = kwargs.get("compliance_mode", "basic")
            region = kwargs.get("region", "us-east-1")

            # Simulate enterprise authentication logic
            username = credentials.get("username", "")
            password = credentials.get("password", "")

            # Multi-tenant validation
            if (
                tenant_id == "enterprise_tenant"
                and username == "admin"
                and password == "secure123"
            ):
                return {
                    "authenticated": True,
                    "user_id": f"user_{tenant_id}_001",
                    "tenant_id": tenant_id,
                    "security_level": security_level,
                    "permissions": (
                        ["read", "write", "admin"]
                        if security_level == "enhanced"
                        else ["read"]
                    ),
                    "audit_enabled": audit_enabled,
                    "compliance_mode": compliance_mode,
                    "region": region,
                    "session_token": f"token_{tenant_id}_{region}",
                    "authenticated_at": datetime.now().isoformat(),
                }
            else:
                return {
                    "authenticated": False,
                    "error": "Invalid credentials",
                    "tenant_id": tenant_id,
                    "audit_enabled": audit_enabled,
                    "failed_at": datetime.now().isoformat(),
                }

        builder.add_node(
            "PythonCodeNode", "tenant_auth", {"function": validate_tenant_credentials}
        )

        def generate_enterprise_session(
            auth_result: Dict[str, Any], **kwargs
        ) -> Dict[str, Any]:
            """Generate enterprise session with context injection."""
            # Extract additional enterprise parameters
            session_timeout = kwargs.get("session_timeout", 3600)
            monitoring_enabled = kwargs.get("monitoring_enabled", False)
            data_classification = kwargs.get("data_classification", "internal")

            if not auth_result.get("authenticated"):
                return {"session_created": False, "error": "Authentication failed"}

            return {
                "session_created": True,
                "session_id": f"session_{auth_result['tenant_id']}_{int(datetime.now().timestamp())}",
                "user_id": auth_result["user_id"],
                "tenant_id": auth_result["tenant_id"],
                "expires_at": int(datetime.now().timestamp()) + session_timeout,
                "permissions": auth_result["permissions"],
                "security_context": {
                    "security_level": auth_result["security_level"],
                    "compliance_mode": auth_result["compliance_mode"],
                    "region": auth_result["region"],
                    "data_classification": data_classification,
                },
                "monitoring_enabled": monitoring_enabled,
                "audit_trail": {
                    "authenticated_at": auth_result["authenticated_at"],
                    "session_created_at": datetime.now().isoformat(),
                },
            }

        builder.add_node(
            "PythonCodeNode",
            "session_generator",
            {"function": generate_enterprise_session},
        )

        # Connect the workflow
        builder.add_connection(
            "tenant_auth", "result", "session_generator", "auth_result"
        )

        # Build and execute with complex enterprise parameters
        workflow = builder.build()
        runtime = LocalRuntime(debug=True)

        # ENTERPRISE PARAMETER INJECTION TEST
        enterprise_params = {
            # Node-specific parameters
            "tenant_auth": {
                "credentials": {"username": "admin", "password": "secure123"}
            },
            # Workflow-level enterprise parameters (should be injected into **kwargs)
            "tenant_id": "enterprise_tenant",
            "security_level": "enhanced",
            "audit_enabled": True,
            "compliance_mode": "gdpr",
            "region": "eu-west-1",
            "session_timeout": 7200,
            "monitoring_enabled": True,
            "data_classification": "confidential",
        }

        result = runtime.execute(workflow, parameters=enterprise_params)

        # Unpack result if needed
        if isinstance(result, tuple):
            result = result[0]

        # Validate authentication result received enterprise parameters
        auth_output = result["tenant_auth"]["result"]
        assert auth_output["authenticated"] is True
        assert auth_output["tenant_id"] == "enterprise_tenant"
        assert auth_output["security_level"] == "enhanced"
        assert auth_output["audit_enabled"] is True
        assert auth_output["compliance_mode"] == "gdpr"
        assert auth_output["region"] == "eu-west-1"
        assert auth_output["permissions"] == [
            "read",
            "write",
            "admin",
        ]  # Enhanced security

        # Validate session generator received enterprise parameters
        session_output = result["session_generator"]["result"]
        assert session_output["session_created"] is True
        assert session_output["tenant_id"] == "enterprise_tenant"
        assert session_output["monitoring_enabled"] is True
        assert session_output["security_context"]["security_level"] == "enhanced"
        assert session_output["security_context"]["compliance_mode"] == "gdpr"
        assert session_output["security_context"]["region"] == "eu-west-1"
        assert (
            session_output["security_context"]["data_classification"] == "confidential"
        )

        print(
            "✅ Multi-tenant authentication with enterprise parameter injection: SUCCESS"
        )

    def test_real_time_data_processing_pipeline(self):
        """Test real-time data processing with dynamic enterprise parameter injection."""

        builder = WorkflowBuilder()

        def process_enterprise_data(data_batch: List[Dict], **kwargs) -> Dict[str, Any]:
            """Process data with real-time enterprise context."""
            # Extract real-time enterprise parameters
            processing_mode = kwargs.get("processing_mode", "standard")
            rate_limit_context = kwargs.get("rate_limit_context", {})
            monitoring_context = kwargs.get("monitoring_context", {})
            compliance_rules = kwargs.get("compliance_rules", {})
            tenant_context = kwargs.get("tenant_context", {})
            encryption_key = kwargs.get("encryption_key", "default_key")

            # Simulate enterprise data processing
            processed_items = []
            for item in data_batch:
                processed_item = {
                    "original_id": item.get("id"),
                    "processed_at": datetime.now().isoformat(),
                    "processing_mode": processing_mode,
                    "tenant_id": tenant_context.get("tenant_id", "unknown"),
                    "encrypted": encryption_key != "default_key",
                    "compliance_checked": bool(compliance_rules),
                }

                # Apply rate limiting based on context
                if rate_limit_context.get("max_throughput", 1000) > 500:
                    processed_item["priority"] = "high"
                else:
                    processed_item["priority"] = "standard"

                processed_items.append(processed_item)

            return {
                "processed_count": len(processed_items),
                "processed_items": processed_items,
                "processing_context": {
                    "mode": processing_mode,
                    "rate_limits": rate_limit_context,
                    "monitoring": monitoring_context,
                    "compliance": compliance_rules,
                    "tenant": tenant_context,
                    "security": {"encryption_enabled": encryption_key != "default_key"},
                },
                "performance_metrics": {
                    "throughput": rate_limit_context.get("current_throughput", 0),
                    "latency_ms": monitoring_context.get("avg_latency_ms", 0),
                },
            }

        builder.add_node(
            "PythonCodeNode", "data_processor", {"function": process_enterprise_data}
        )

        # Build workflow
        workflow = builder.build()
        runtime = LocalRuntime(debug=True)

        # REAL-TIME ENTERPRISE PARAMETER INJECTION
        real_time_params = {
            # Node-specific parameters
            "data_processor": {
                "data_batch": [
                    {"id": "item_001", "value": 100},
                    {"id": "item_002", "value": 200},
                    {"id": "item_003", "value": 300},
                ]
            },
            # Real-time workflow-level parameters (enterprise context)
            "processing_mode": "enterprise_enhanced",
            "rate_limit_context": {
                "max_throughput": 1500,
                "current_throughput": 1200,
                "burst_allowed": True,
            },
            "monitoring_context": {
                "avg_latency_ms": 45,
                "error_rate": 0.001,
                "active_connections": 150,
            },
            "compliance_rules": {
                "gdpr_enabled": True,
                "data_retention_days": 90,
                "audit_required": True,
            },
            "tenant_context": {
                "tenant_id": "enterprise_client_001",
                "tier": "premium",
                "region": "eu-central-1",
            },
            "encryption_key": "enterprise_key_2024_rotation_3",
        }

        result = runtime.execute(workflow, parameters=real_time_params)

        # Unpack result if needed
        if isinstance(result, tuple):
            result = result[0]

        # Validate enterprise parameter injection
        output = result["data_processor"]["result"]

        assert output["processed_count"] == 3
        assert output["processing_context"]["mode"] == "enterprise_enhanced"
        assert output["processing_context"]["rate_limits"]["max_throughput"] == 1500
        assert output["processing_context"]["monitoring"]["avg_latency_ms"] == 45
        assert output["processing_context"]["compliance"]["gdpr_enabled"] is True
        assert (
            output["processing_context"]["tenant"]["tenant_id"]
            == "enterprise_client_001"
        )
        assert output["processing_context"]["security"]["encryption_enabled"] is True

        # Validate business logic with enterprise context
        for item in output["processed_items"]:
            assert item["processing_mode"] == "enterprise_enhanced"
            assert item["tenant_id"] == "enterprise_client_001"
            assert item["encrypted"] is True
            assert item["compliance_checked"] is True
            assert item["priority"] == "high"  # Based on rate limit context

        # Validate performance metrics injection
        assert output["performance_metrics"]["throughput"] == 1200
        assert output["performance_metrics"]["latency_ms"] == 45

        print(
            "✅ Real-time data processing with enterprise parameter injection: SUCCESS"
        )

    def test_nested_workflow_parameter_inheritance(self):
        """Test parameter inheritance in nested enterprise workflows."""

        # Create parent workflow
        parent_builder = WorkflowBuilder()

        def parent_orchestrator(config: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            """Parent workflow orchestrator with enterprise context."""
            # Enterprise parameters should be inherited
            global_tenant = kwargs.get("global_tenant_id", "unknown")
            security_context = kwargs.get("security_context", {})
            audit_context = kwargs.get("audit_context", {})

            return {
                "orchestration_result": "parent_processed",
                "global_tenant": global_tenant,
                "security_level": security_context.get("level", "basic"),
                "audit_enabled": audit_context.get("enabled", False),
                "child_config": {"inherit_security": True, "inherit_audit": True},
            }

        parent_builder.add_node(
            "PythonCodeNode", "orchestrator", {"function": parent_orchestrator}
        )

        # Create child workflow
        child_builder = WorkflowBuilder()

        def child_processor(data: List[str], **kwargs) -> Dict[str, Any]:
            """Child workflow processor that should inherit enterprise parameters."""
            # Should inherit parent enterprise parameters
            global_tenant = kwargs.get("global_tenant_id", "unknown")
            security_context = kwargs.get("security_context", {})
            audit_context = kwargs.get("audit_context", {})

            return {
                "child_processing_result": "child_processed",
                "inherited_tenant": global_tenant,
                "inherited_security": security_context.get("level", "basic"),
                "inherited_audit": audit_context.get("enabled", False),
                "processed_data_count": len(data),
            }

        child_builder.add_node(
            "PythonCodeNode", "child_processor", {"function": child_processor}
        )

        # Build workflows
        parent_workflow = parent_builder.build()
        child_workflow = child_builder.build()

        # Test parent workflow with enterprise parameters
        runtime = LocalRuntime(debug=True)

        enterprise_context = {
            # Node-specific
            "orchestrator": {"config": {"workflow_type": "enterprise"}},
            # Enterprise workflow-level parameters
            "global_tenant_id": "enterprise_global_001",
            "security_context": {
                "level": "maximum",
                "encryption_required": True,
                "mfa_enabled": True,
            },
            "audit_context": {
                "enabled": True,
                "compliance_mode": "sox",
                "retention_years": 7,
            },
        }

        parent_result = runtime.execute(parent_workflow, parameters=enterprise_context)
        if isinstance(parent_result, tuple):
            parent_result = parent_result[0]

        # Test child workflow with inherited parameters
        child_context = {
            # Node-specific
            "child_processor": {"data": ["item1", "item2", "item3", "item4"]},
            # Should inherit enterprise parameters from parent context
            "global_tenant_id": "enterprise_global_001",
            "security_context": {
                "level": "maximum",
                "encryption_required": True,
                "mfa_enabled": True,
            },
            "audit_context": {
                "enabled": True,
                "compliance_mode": "sox",
                "retention_years": 7,
            },
        }

        child_result = runtime.execute(child_workflow, parameters=child_context)
        if isinstance(child_result, tuple):
            child_result = child_result[0]

        # Validate parent workflow received enterprise parameters
        parent_output = parent_result["orchestrator"]["result"]
        assert parent_output["global_tenant"] == "enterprise_global_001"
        assert parent_output["security_level"] == "maximum"
        assert parent_output["audit_enabled"] is True

        # Validate child workflow inherited enterprise parameters
        child_output = child_result["child_processor"]["result"]
        assert child_output["inherited_tenant"] == "enterprise_global_001"
        assert child_output["inherited_security"] == "maximum"
        assert child_output["inherited_audit"] is True
        assert child_output["processed_data_count"] == 4

        print("✅ Nested workflow parameter inheritance: SUCCESS")

    def test_enterprise_parameter_validation_and_debugging(self):
        """Test enterprise parameter validation and debugging capabilities."""

        builder = WorkflowBuilder()

        def enterprise_validator(input_data: str, **kwargs) -> Dict[str, Any]:
            """Function that validates enterprise parameter injection."""
            received_params = list(kwargs.keys())

            return {
                "input_processed": input_data,
                "received_enterprise_params": received_params,
                "param_values": {k: v for k, v in kwargs.items()},
                "validation_successful": len(received_params) > 0,
            }

        builder.add_node(
            "PythonCodeNode", "validator", {"function": enterprise_validator}
        )

        workflow = builder.build()
        runtime = LocalRuntime(debug=True)

        # Test with comprehensive enterprise parameters
        comprehensive_params = {
            # Node-specific
            "validator": {"input_data": "test_enterprise_validation"},
            # Comprehensive enterprise parameters
            "tenant_id": "validation_tenant",
            "user_context": {"user_id": "validator_user", "role": "admin"},
            "security_context": {"level": "high", "mfa": True},
            "audit_context": {"enabled": True, "level": "detailed"},
            "monitoring_context": {"metrics_enabled": True, "tracing": True},
            "compliance_context": {"gdpr": True, "sox": True, "hipaa": False},
            "performance_context": {
                "cache_enabled": True,
                "optimization": "aggressive",
            },
            "business_context": {"priority": "high", "sla": "premium"},
            "technical_context": {
                "api_version": "v2",
                "feature_flags": {"new_ui": True},
            },
        }

        result = runtime.execute(workflow, parameters=comprehensive_params)
        if isinstance(result, tuple):
            result = result[0]

        output = result["validator"]["result"]

        # Validate all enterprise parameters were injected
        expected_params = {
            "tenant_id",
            "user_context",
            "security_context",
            "audit_context",
            "monitoring_context",
            "compliance_context",
            "performance_context",
            "business_context",
            "technical_context",
        }

        received_params = set(output["received_enterprise_params"])
        assert expected_params.issubset(
            received_params
        ), f"Missing params: {expected_params - received_params}"

        # Validate parameter values were correctly injected
        param_values = output["param_values"]
        assert param_values["tenant_id"] == "validation_tenant"
        assert param_values["user_context"]["user_id"] == "validator_user"
        assert param_values["security_context"]["level"] == "high"
        assert param_values["audit_context"]["enabled"] is True
        assert param_values["compliance_context"]["gdpr"] is True

        print("✅ Enterprise parameter validation and debugging: SUCCESS")
        except ImportError:
            pytest.skip("Required modules not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

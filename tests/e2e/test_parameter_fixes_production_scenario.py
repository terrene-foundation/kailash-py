"""End-to-end test for parameter fixes in production-like scenario.

This test simulates the TPC migration team's production workflow that was
failing due to the parameter handling bugs documented in TODO-092.
"""

import asyncio

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import (
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.workflow import WorkflowBuilder


class TestProductionParameterScenario:
    """Test parameter fixes in production-like TPC migration scenario."""

    def test_tpc_migration_workflow_scenario(self):
        """Test the complete TPC migration workflow that was failing."""

        # This simulates the TPC team's actual workflow
        workflow = WorkflowBuilder()

        # 1. Data extraction with configurable parameters (Issue #1: Default params bug)
        def extract_user_data(
            source_id, batch_size=100, include_inactive=False, **extraction_opts
        ):
            """Extract user data with configurable batch processing."""
            # Simulate data extraction
            base_users = [
                {"id": i, "name": f"User{i}", "active": i % 3 != 0}
                for i in range(1, source_id * 10 + 1)
            ]

            # Apply batch size
            if batch_size and batch_size > 0:
                base_users = base_users[:batch_size]

            # Filter by active status
            if not include_inactive:
                base_users = [u for u in base_users if u["active"]]

            # Apply any extra extraction options
            metadata = {
                "source_id": source_id,
                "batch_size": batch_size,
                "include_inactive": include_inactive,
                "total_extracted": len(base_users),
                "extraction_options": extraction_opts,
            }

            return {"users": base_users, "metadata": metadata}

        extraction_node = PythonCodeNode.from_function(
            extract_user_data, name="extractor"
        )
        workflow.add_node(extraction_node, "data_extraction")

        # 2. Data transformation with flexible parameters (Issue #2: **kwargs support)
        def transform_user_data(users, metadata, **transform_opts):
            """Transform user data with flexible options."""
            transformed_users = []

            for user in users:
                transformed = user.copy()

                # Apply transformations based on options
                if transform_opts.get("add_full_name"):
                    transformed["full_name"] = f"{user['name']} (ID: {user['id']})"

                if transform_opts.get("normalize_names"):
                    transformed["name"] = (
                        user["name"].lower().replace("user", "migrated_user_")
                    )

                if transform_opts.get("add_migration_timestamp"):
                    import time

                    transformed["migrated_at"] = int(time.time())

                # Add any custom fields from transform options
                custom_fields = {
                    k: v for k, v in transform_opts.items() if k.startswith("custom_")
                }
                transformed.update(custom_fields)

                transformed_users.append(transformed)

            return {
                "transformed_users": transformed_users,
                "transform_metadata": {
                    "original_count": len(users),
                    "transformed_count": len(transformed_users),
                    "options_applied": list(transform_opts.keys()),
                    "source_metadata": metadata,
                },
            }

        transform_node = PythonCodeNode.from_function(
            transform_user_data, name="transformer"
        )
        workflow.add_node(transform_node, "data_transformation")

        # 3. Security validation (Issue #3: Security model consistency)
        def validate_data_security(
            transformed_users, transform_metadata, **security_opts
        ):
            """Validate data meets security requirements."""
            issues = []
            safe_users = []

            security_config = {
                "max_users_per_batch": security_opts.get("max_users_per_batch", 1000),
                "require_full_name": security_opts.get("require_full_name", False),
                "block_test_data": security_opts.get("block_test_data", True),
                "audit_logging": security_opts.get("audit_logging", True),
            }

            for user in transformed_users:
                # Security checks
                is_safe = True

                if (
                    security_config["block_test_data"]
                    and "test" in user.get("name", "").lower()
                ):
                    issues.append(f"Test data detected in user {user['id']}")
                    is_safe = False

                if security_config["require_full_name"] and not user.get("full_name"):
                    issues.append(f"Missing full_name for user {user['id']}")
                    is_safe = False

                if is_safe:
                    safe_users.append(user)

            # Batch size validation
            if len(safe_users) > security_config["max_users_per_batch"]:
                issues.append(
                    f"Batch size {len(safe_users)} exceeds limit {security_config['max_users_per_batch']}"
                )
                safe_users = safe_users[: security_config["max_users_per_batch"]]

            return {
                "validated_users": safe_users,
                "security_issues": issues,
                "security_summary": {
                    "total_issues": len(issues),
                    "users_validated": len(safe_users),
                    "users_rejected": len(transformed_users) - len(safe_users),
                    "security_config": security_config,
                },
            }

        security_node = PythonCodeNode.from_function(
            validate_data_security, name="security_validator"
        )
        workflow.add_node(security_node, "security_validation")

        # 4. Deferred database connection (Issue #5: Enterprise node timing)
        database_node = create_deferred_sql(name="migration_db")
        workflow.add_node(database_node, "database_storage")

        # 5. Migration result aggregation
        workflow.add_node(
            "PythonCodeNode",
            "result_aggregator",
            {
                "code": """
# Aggregate migration results
if 'validated_data' in locals() and validated_data:
    result = {
        "migration_success": True,
        "users_migrated": len(validated_data["validated_users"]),
        "security_issues": len(validated_data["security_issues"]),
        "batch_metadata": validated_data.get("security_summary", {}),
        "processing_summary": {
            "extraction_completed": True,
            "transformation_completed": True,
            "security_validation_completed": True,
            "database_ready": False  # Would be True if DB connection worked
        }
    }
else:
    result = {
        "migration_success": False,
        "error": "No validated data received"
    }
"""
            },
        )

        # Connect the workflow (simulating TPC team's pipeline)
        workflow.add_connection(
            "data_extraction", "result", "data_transformation", "extraction_result"
        )
        workflow.add_connection(
            "data_transformation",
            "result.transformed_users",
            "security_validation",
            "transformed_users",
        )
        workflow.add_connection(
            "data_transformation",
            "result.transform_metadata",
            "security_validation",
            "transform_metadata",
        )
        workflow.add_connection(
            "security_validation", "result", "result_aggregator", "validated_data"
        )

        # Build workflow
        wf = workflow.build()
        runtime = LocalRuntime()

        # Execute the TPC migration scenario that was previously failing
        result = runtime.execute_workflow(
            wf,
            inputs={
                "data_extraction": {
                    "source_id": 3,  # Small dataset for testing
                    "batch_size": 50,
                    "include_inactive": False,
                    # These extra parameters should now work (Issue #2 fix)
                    "data_source": "legacy_system",
                    "migration_id": "TPC-2024-001",
                    "priority": "high",
                },
                "data_transformation": {
                    # These flexible transformation options should now work
                    "add_full_name": True,
                    "normalize_names": True,
                    "add_migration_timestamp": True,
                    "custom_migration_batch": "TPC-BATCH-1",
                    "custom_team_id": "TPC-MIGRATION-TEAM",
                },
                "security_validation": {
                    "max_users_per_batch": 100,
                    "require_full_name": True,
                    "block_test_data": True,
                    "audit_logging": True,
                    "compliance_level": "enterprise",
                },
            },
        )

        # Validate the complete workflow succeeded
        assert "result_aggregator" in result
        final_result = result["result_aggregator"]["result"]

        # The migration should now succeed
        assert final_result["migration_success"] is True
        assert final_result["users_migrated"] > 0
        assert final_result["processing_summary"]["extraction_completed"] is True
        assert final_result["processing_summary"]["transformation_completed"] is True
        assert (
            final_result["processing_summary"]["security_validation_completed"] is True
        )

        # Verify extraction worked with default parameters (Issue #1 fix)
        extraction_result = result["data_extraction"]["result"]
        assert extraction_result["metadata"]["batch_size"] == 50
        assert extraction_result["metadata"]["include_inactive"] is False
        assert "migration_id" in extraction_result["metadata"]["extraction_options"]

        # Verify transformation accepted flexible parameters (Issue #2 fix)
        transform_result = result["data_transformation"]["result"]
        assert (
            "add_full_name" in transform_result["transform_metadata"]["options_applied"]
        )
        assert (
            "custom_migration_batch"
            in transform_result["transform_metadata"]["options_applied"]
        )

        # Verify security validation worked (Issue #3 fix)
        security_result = result["security_validation"]["result"]
        assert security_result["security_summary"]["users_validated"] > 0
        assert (
            security_result["security_summary"]["total_issues"] == 0
        )  # No security issues

    def test_parameter_injection_timing_issue(self):
        """Test the specific timing issue with enterprise nodes that TPC team encountered."""

        # This reproduces the exact issue where OAuth2Node needed runtime parameters
        workflow = WorkflowBuilder()

        # 1. Configuration provider (simulates runtime parameter source)
        def provide_auth_config(environment, **config_opts):
            """Provide authentication configuration based on environment."""
            configs = {
                "dev": {
                    "token_url": "https://dev-auth.example.com/token",
                    "client_id": "dev_client_123",
                    "scope": "read write",
                },
                "staging": {
                    "token_url": "https://staging-auth.example.com/token",
                    "client_id": "staging_client_456",
                    "scope": "read write admin",
                },
                "production": {
                    "token_url": "https://prod-auth.example.com/token",
                    "client_id": "prod_client_789",
                    "scope": "read write admin audit",
                },
            }

            base_config = configs.get(environment, configs["dev"])

            # Apply any configuration overrides
            for key, value in config_opts.items():
                if key.startswith("auth_"):
                    auth_key = key[5:]  # Remove "auth_" prefix
                    base_config[auth_key] = value

            return {
                "auth_config": base_config,
                "environment": environment,
                "config_source": "dynamic_provider",
            }

        config_node = PythonCodeNode.from_function(
            provide_auth_config, name="config_provider"
        )
        workflow.add_node(config_node, "config_provider")

        # 2. Deferred OAuth2 node (Issue #5: Should accept runtime config)
        oauth_node = create_deferred_oauth2(name="dynamic_oauth")
        workflow.add_node(oauth_node, "oauth_authentication")

        # 3. API call simulation that uses the auth
        def make_authenticated_api_call(auth_headers, config_info, **call_opts):
            """Simulate making an API call with dynamic authentication."""
            # In real scenario, this would make actual API calls
            # Here we simulate the behavior

            call_config = {
                "endpoint": call_opts.get("api_endpoint", "/api/v1/users"),
                "method": call_opts.get("http_method", "GET"),
                "timeout": call_opts.get("timeout_seconds", 30),
            }

            # Simulate API response based on auth
            if auth_headers and "Authorization" in auth_headers:
                api_response = {
                    "status": "success",
                    "data": [{"id": 1, "name": "User 1"}, {"id": 2, "name": "User 2"}],
                    "auth_used": auth_headers.get("Authorization", "").split(" ")[0],
                    "environment": config_info.get("environment", "unknown"),
                }
            else:
                api_response = {
                    "status": "error",
                    "error": "No authentication provided",
                }

            return {
                "api_response": api_response,
                "call_config": call_config,
                "auth_validated": bool(auth_headers),
            }

        api_node = PythonCodeNode.from_function(
            make_authenticated_api_call, name="api_caller"
        )
        workflow.add_node(api_node, "api_call")

        # Connect with parameter passing (this was the failing part)
        workflow.add_connection(
            "config_provider",
            "result.auth_config",
            "oauth_authentication",
            "runtime_config",
        )
        workflow.add_connection(
            "oauth_authentication", "headers", "api_call", "auth_headers"
        )
        workflow.add_connection("config_provider", "result", "api_call", "config_info")

        # Build workflow
        wf = workflow.build()

        # Verify workflow builds successfully (this was failing before)
        assert wf is not None

        # Verify OAuth node has correct parameter structure for deferred config
        oauth_params = oauth_node.get_parameters()
        assert "token_url" in oauth_params
        assert "client_id" in oauth_params
        assert oauth_params["token_url"].required is True

    def test_complex_parameter_inheritance_scenario(self):
        """Test complex parameter inheritance that enterprise customers need."""

        workflow = WorkflowBuilder()

        # Base configuration with inheritance
        def create_base_config(tenant_id, deployment_type="standard", **overrides):
            """Create base configuration that can be inherited."""
            base_configs = {
                "standard": {
                    "max_batch_size": 100,
                    "timeout_seconds": 30,
                    "retry_attempts": 3,
                    "log_level": "info",
                },
                "enterprise": {
                    "max_batch_size": 1000,
                    "timeout_seconds": 60,
                    "retry_attempts": 5,
                    "log_level": "debug",
                    "encryption_enabled": True,
                    "audit_logging": True,
                },
                "premium": {
                    "max_batch_size": 5000,
                    "timeout_seconds": 120,
                    "retry_attempts": 10,
                    "log_level": "trace",
                    "encryption_enabled": True,
                    "audit_logging": True,
                    "priority_processing": True,
                    "dedicated_resources": True,
                },
            }

            config = base_configs.get(deployment_type, base_configs["standard"]).copy()
            config.update(overrides)
            config["tenant_id"] = tenant_id
            config["deployment_type"] = deployment_type

            return {
                "inherited_config": config,
                "config_source": f"{deployment_type}_template",
                "tenant_info": {"id": tenant_id, "type": deployment_type},
            }

        base_config_node = PythonCodeNode.from_function(
            create_base_config, name="base_config"
        )
        workflow.add_node(base_config_node, "base_configuration")

        # Specialized processor that inherits and extends config
        def process_with_inheritance(
            data,
            inherited_config,
            tenant_info,
            # These parameters can override inherited ones
            custom_batch_size=None,
            custom_timeout=None,
            enable_debugging=False,
            **processing_opts,
        ):
            """Process data using inherited configuration with overrides."""

            # Start with inherited config
            effective_config = inherited_config.copy()

            # Apply parameter overrides
            if custom_batch_size is not None:
                effective_config["max_batch_size"] = custom_batch_size

            if custom_timeout is not None:
                effective_config["timeout_seconds"] = custom_timeout

            if enable_debugging:
                effective_config["log_level"] = "debug"
                effective_config["detailed_logging"] = True

            # Apply any additional processing options
            for key, value in processing_opts.items():
                if key.startswith("config_"):
                    config_key = key[7:]  # Remove "config_" prefix
                    effective_config[config_key] = value

            # Simulate processing based on effective config
            batch_size = effective_config["max_batch_size"]
            processed_batches = []

            for i in range(0, len(data), batch_size):
                batch = data[i : i + batch_size]
                processed_batch = {
                    "batch_id": len(processed_batches) + 1,
                    "items": batch,
                    "size": len(batch),
                    "tenant_id": tenant_info["id"],
                    "processing_config": effective_config,
                }
                processed_batches.append(processed_batch)

            return {
                "processed_batches": processed_batches,
                "effective_config": effective_config,
                "inheritance_applied": True,
                "total_items": len(data),
                "total_batches": len(processed_batches),
            }

        processor_node = PythonCodeNode.from_function(
            process_with_inheritance, name="inherited_processor"
        )
        workflow.add_node(processor_node, "data_processor")

        # Connect inheritance flow
        workflow.add_connection(
            "base_configuration",
            "result.inherited_config",
            "data_processor",
            "inherited_config",
        )
        workflow.add_connection(
            "base_configuration", "result.tenant_info", "data_processor", "tenant_info"
        )

        # Build and test
        wf = workflow.build()
        runtime = LocalRuntime()

        # Test with enterprise deployment and parameter overrides
        test_data = list(range(1, 251))  # 250 items

        result = runtime.execute_workflow(
            wf,
            inputs={
                "base_configuration": {
                    "tenant_id": "TENANT-001",
                    "deployment_type": "enterprise",
                    # Override some base config
                    "custom_encryption_key": "enterprise-key-123",
                    "region": "us-east-1",
                },
                "data_processor": {
                    "data": test_data,
                    # Parameter overrides (these should work with the fixes)
                    "custom_batch_size": 75,  # Override inherited batch size
                    "enable_debugging": True,
                    # Additional processing options
                    "config_special_handling": True,
                    "processing_priority": "high",
                    "compliance_mode": "strict",
                },
            },
        )

        # Validate inheritance and parameter override worked
        processor_result = result["data_processor"]["result"]

        assert processor_result["inheritance_applied"] is True
        assert processor_result["total_items"] == 250

        # Check that parameter override worked
        effective_config = processor_result["effective_config"]
        assert effective_config["max_batch_size"] == 75  # Overridden
        assert (
            effective_config["log_level"] == "debug"
        )  # Enterprise + debugging override
        assert effective_config["special_handling"] is True  # From processing_opts

        # Check batching worked correctly with override
        assert (
            len(processor_result["processed_batches"]) == 4
        )  # 250 / 75 = 3.33 -> 4 batches

        # Verify enterprise features were inherited
        assert effective_config["encryption_enabled"] is True
        assert effective_config["audit_logging"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

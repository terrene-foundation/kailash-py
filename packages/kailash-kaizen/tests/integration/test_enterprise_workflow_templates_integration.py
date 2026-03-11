"""
Tier 2 (Integration Tests) for Enterprise Workflow Templates

These tests verify enterprise workflow templates work with real Core SDK components
and infrastructure, testing actual component interactions without mocking.

Test Requirements:
- Use real Docker services from tests/utils
- NO MOCKING - test actual component interactions
- Test with real database connections, audit services, compliance systems
- Validate data flows between enterprise components
- Test integration with Core SDK nodes and infrastructure
- Location: tests/integration/
- Timeout: <5 seconds per test

Setup Requirements:
1. MUST run: ./tests/utils/test-env up && ./tests/utils/test-env status before tests
2. Real Docker services: PostgreSQL, Redis, monitoring services
3. Real Core SDK enterprise nodes and audit systems
4. Real workflow execution with enterprise infrastructure
"""

import time

import pytest

from kailash.runtime.local import LocalRuntime

# Core SDK imports for real integration

# Test markers
pytestmark = pytest.mark.integration


class TestEnterpriseWorkflowTemplateIntegration:
    """Test enterprise workflow templates with real Core SDK integration."""

    def test_enterprise_approval_workflow_real_execution(self):
        """Test approval workflow template executes with real enterprise nodes."""
        import kaizen

        # Initialize with enterprise configuration
        framework = kaizen.Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "security_level": "high",
            }
        )

        # Create approval workflow template
        approval_config = {
            "approval_levels": ["technical", "business", "executive"],
            "escalation_timeout": "24_hours",
            "audit_requirements": "complete",
            "digital_signature": True,
            "compliance_standards": ["SOX", "GDPR"],
        }

        approval_workflow = framework.create_enterprise_workflow(
            "approval", approval_config
        )

        # Build workflow for execution
        built_workflow = approval_workflow.build()
        assert built_workflow is not None

        # Execute with real Core SDK runtime
        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(built_workflow)
        execution_time = time.time() - start_time

        # Verify execution completed successfully
        assert results is not None
        assert run_id is not None
        assert execution_time < 5.0  # Integration test timeout

        # Verify enterprise nodes were executed
        # Check for audit logging nodes
        audit_nodes = [
            node_id for node_id in results.keys() if "audit" in node_id.lower()
        ]
        assert len(audit_nodes) > 0, "No audit nodes found in approval workflow"

        # Check for approval level nodes
        approval_nodes = [
            node_id for node_id in results.keys() if "approval" in node_id.lower()
        ]
        assert len(approval_nodes) >= 3, "Not all approval levels were created"

        # Verify all nodes completed successfully
        for node_id, result in results.items():
            assert result["status"] == "completed", f"Node {node_id} failed: {result}"

    def test_customer_service_workflow_real_escalation(self):
        """Test customer service workflow with real escalation and routing."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"monitoring_level": "detailed", "audit_trail_enabled": True}
        )

        # Create customer service workflow
        service_config = {
            "routing_rules": "priority_based",
            "escalation_levels": ["tier1", "tier2", "supervisor"],
            "sla_requirements": {"response_time": "5_minutes"},
            "audit_trail": True,
        }

        service_workflow = framework.create_enterprise_workflow(
            "customer_service", service_config
        )
        built_workflow = service_workflow.build()

        # Execute with real infrastructure
        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(built_workflow)
        execution_time = time.time() - start_time

        # Verify execution
        assert results is not None
        assert run_id is not None
        assert execution_time < 5.0

        # Verify escalation levels are implemented
        escalation_nodes = [
            node_id
            for node_id in results.keys()
            if any(level in node_id for level in ["tier1", "tier2", "supervisor"])
        ]
        assert len(escalation_nodes) >= 3, "Not all escalation levels implemented"

        # Verify SLA monitoring nodes
        sla_nodes = [node_id for node_id in results.keys() if "sla" in node_id.lower()]
        assert len(sla_nodes) > 0, "No SLA monitoring found"

        # Verify routing logic nodes
        routing_nodes = [
            node_id
            for node_id in results.keys()
            if "routing" in node_id.lower() or "priority" in node_id.lower()
        ]
        assert len(routing_nodes) > 0, "No routing logic found"

    def test_document_analysis_workflow_real_compliance(self):
        """Test document analysis workflow with real compliance checks."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"compliance_mode": "enterprise", "security_level": "high"}
        )

        # Create document analysis workflow
        analysis_config = {
            "processing_stages": [
                "extraction",
                "classification",
                "analysis",
                "compliance",
            ],
            "compliance_checks": ["PII_detection", "data_classification"],
            "audit_requirements": "full_lineage",
        }

        analysis_workflow = framework.create_enterprise_workflow(
            "document_analysis", analysis_config
        )
        built_workflow = analysis_workflow.build()

        # Execute with real Core SDK nodes
        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(built_workflow)
        execution_time = time.time() - start_time

        # Verify execution
        assert results is not None
        assert run_id is not None
        assert execution_time < 10.0  # Document analysis may take longer

        # Verify all processing stages are implemented
        stage_nodes = []
        for stage in ["extraction", "classification", "analysis", "compliance"]:
            stage_nodes.extend(
                [node_id for node_id in results.keys() if stage in node_id.lower()]
            )

        assert (
            len(stage_nodes) >= 4
        ), f"Not all processing stages implemented. Found: {stage_nodes}"

        # Verify compliance check nodes
        compliance_nodes = [
            node_id
            for node_id in results.keys()
            if "compliance" in node_id.lower() or "pii" in node_id.lower()
        ]
        assert len(compliance_nodes) > 0, "No compliance check nodes found"

        # Verify data lineage tracking
        lineage_nodes = [
            node_id for node_id in results.keys() if "lineage" in node_id.lower()
        ]
        assert len(lineage_nodes) > 0, "No data lineage tracking found"


class TestEnterpriseWorkflowAuditTrailIntegration:
    """Test enterprise workflow audit trail integration with real infrastructure."""

    def test_enterprise_workflow_audit_trail_real_logging(self):
        """Test audit trail logging works with real enterprise infrastructure."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"audit_trail_enabled": True, "compliance_mode": "enterprise"}
        )

        # Initialize enterprise features to ensure audit trail is ready
        framework.initialize_enterprise_features()

        # Create workflow with audit requirements
        audit_config = {
            "approval_levels": ["technical", "business"],
            "audit_requirements": "complete",
            "audit_retention": "7_years",
            "audit_encryption": True,
        }

        workflow = framework.create_enterprise_workflow("approval", audit_config)
        built_workflow = workflow.build()

        # Clear any existing audit entries
        initial_audit_count = len(framework.get_coordination_audit_trail())

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Verify audit trail was created
        audit_trail = framework.get_coordination_audit_trail()
        assert len(audit_trail) > initial_audit_count, "No new audit entries created"

        # Verify audit entry structure
        latest_entry = audit_trail[-1]
        assert "action" in latest_entry
        assert "timestamp" in latest_entry
        assert "run_id" in latest_entry
        assert latest_entry["run_id"] == run_id

        # Test audit trail access methods
        current_trail = framework.audit_trail.get_current_trail()
        assert current_trail is not None
        assert isinstance(current_trail, list)

    def test_enterprise_workflow_compliance_reporting_real(self):
        """Test compliance reporting with real enterprise workflow execution."""
        import kaizen

        framework = kaizen.Kaizen(
            config={
                "compliance_mode": "enterprise",
                "audit_trail_enabled": True,
                "monitoring_level": "detailed",
            }
        )

        # Create GDPR compliance workflow
        gdpr_config = {
            "compliance_type": "GDPR",
            "data_processing_stages": [
                "consent_validation",
                "data_processing",
                "audit_trail",
            ],
            "retention_policy": "automatic",
            "privacy_checks": True,
        }

        compliance_workflow = framework.create_enterprise_workflow(
            "compliance", gdpr_config
        )
        built_workflow = compliance_workflow.build()

        # Execute compliance workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Generate compliance report
        compliance_report = framework.generate_compliance_report()

        # Verify compliance report structure
        assert compliance_report is not None
        assert isinstance(compliance_report, dict)
        assert "compliance_status" in compliance_report
        assert "workflow_count" in compliance_report
        assert "audit_entries" in compliance_report

        # Verify GDPR-specific compliance data
        assert "gdpr_compliance" in compliance_report
        gdpr_data = compliance_report["gdpr_compliance"]
        assert "data_processing_records" in gdpr_data
        assert "privacy_checks_passed" in gdpr_data

        # Verify compliance status is valid
        assert compliance_report["compliance_status"] in [
            "compliant",
            "non_compliant",
            "pending_review",
        ]


class TestEnterpriseWorkflowSecurityIntegration:
    """Test enterprise workflow security integration with real security nodes."""

    def test_enterprise_workflow_abac_security_integration(self):
        """Test ABAC (Attribute-Based Access Control) integration with enterprise workflows."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"security_level": "high", "audit_trail_enabled": True}
        )

        # Create workflow with strict access control
        security_config = {
            "approval_levels": ["technical", "business"],
            "access_control": "strict",
            "security_audit": True,
            "authorization_required": True,
        }

        workflow = framework.create_enterprise_workflow("approval", security_config)
        built_workflow = workflow.build()

        # Execute workflow with security checks
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Verify security nodes were executed
        security_nodes = [
            node_id
            for node_id in results.keys()
            if "security" in node_id.lower()
            or "access" in node_id.lower()
            or "auth" in node_id.lower()
        ]
        assert len(security_nodes) > 0, "No security nodes found in workflow"

        # Verify all security checks passed
        for node_id in security_nodes:
            result = results[node_id]
            assert (
                result["status"] == "completed"
            ), f"Security node {node_id} failed: {result}"

    def test_enterprise_workflow_digital_signature_integration(self):
        """Test digital signature integration with enterprise workflows."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"security_level": "high", "audit_trail_enabled": True}
        )

        # Create workflow requiring digital signatures
        signature_config = {
            "approval_levels": ["technical", "business", "executive"],
            "digital_signature": True,
            "signature_algorithm": "RSA2048",
            "audit_signatures": True,
        }

        workflow = framework.create_enterprise_workflow("approval", signature_config)
        built_workflow = workflow.build()

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Verify signature nodes were created and executed
        signature_nodes = [
            node_id for node_id in results.keys() if "signature" in node_id.lower()
        ]
        assert len(signature_nodes) > 0, "No digital signature nodes found"

        # Verify signature validation nodes
        for node_id in signature_nodes:
            result = results[node_id]
            assert (
                result["status"] == "completed"
            ), f"Signature node {node_id} failed: {result}"


class TestEnterpriseWorkflowMultiTenantIntegration:
    """Test multi-tenant enterprise workflow integration with real tenant isolation."""

    def test_enterprise_workflow_tenant_isolation_integration(self):
        """Test tenant isolation works with real enterprise workflows."""
        import kaizen

        # Create framework with multi-tenant support
        framework = kaizen.Kaizen(
            config={
                "multi_tenant": True,
                "audit_trail_enabled": True,
                "tenant_isolation": "strict",
            }
        )

        # Create tenant-specific workflows
        tenant_configs = [
            {
                "tenant_id": "tenant_a",
                "approval_levels": ["technical", "business"],
                "tenant_isolation": "strict",
            },
            {
                "tenant_id": "tenant_b",
                "approval_levels": ["technical", "manager"],
                "tenant_isolation": "strict",
            },
        ]

        workflows = []
        results = []

        # Create and execute workflows for different tenants
        runtime = LocalRuntime()

        for config in tenant_configs:
            workflow = framework.create_enterprise_workflow("approval", config)
            built_workflow = workflow.build()

            workflow_results, run_id = runtime.execute(built_workflow)
            workflows.append(workflow)
            results.append((workflow_results, run_id))

        # Verify tenant isolation
        assert len(results) == 2
        run_id_a, run_id_b = results[0][1], results[1][1]
        assert run_id_a != run_id_b, "Run IDs should be different for different tenants"

        # Verify tenant-specific nodes were created
        for workflow_results, run_id in results:
            tenant_nodes = [
                node_id
                for node_id in workflow_results.keys()
                if "tenant" in node_id.lower()
            ]
            assert (
                len(tenant_nodes) > 0
            ), f"No tenant isolation nodes found for run {run_id}"

    def test_enterprise_workflow_cross_tenant_validation(self):
        """Test cross-tenant access validation in enterprise workflows."""
        import kaizen

        framework = kaizen.Kaizen(
            config={"multi_tenant": True, "security_level": "high"}
        )

        # Create workflow with cross-tenant access disabled
        strict_config = {
            "tenant_id": "tenant_secure",
            "approval_levels": ["technical"],
            "cross_tenant_access": False,
            "tenant_validation": True,
        }

        workflow = framework.create_enterprise_workflow("approval", strict_config)
        built_workflow = workflow.build()

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Verify tenant validation nodes
        validation_nodes = [
            node_id
            for node_id in results.keys()
            if "validation" in node_id.lower() or "tenant" in node_id.lower()
        ]
        assert len(validation_nodes) > 0, "No tenant validation nodes found"

        # Verify all validation checks passed
        for node_id in validation_nodes:
            result = results[node_id]
            assert (
                result["status"] == "completed"
            ), f"Tenant validation node {node_id} failed: {result}"


class TestEnterpriseWorkflowPerformanceIntegration:
    """Test enterprise workflow performance with real infrastructure."""

    def test_enterprise_approval_workflow_performance_integration(self):
        """Test approval workflow performance with real enterprise nodes."""
        import kaizen

        framework = kaizen.Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "performance_optimization": True,
            }
        )

        # Create complex approval workflow
        complex_config = {
            "approval_levels": [
                "technical",
                "business",
                "financial",
                "legal",
                "executive",
            ],
            "escalation_timeout": "24_hours",
            "audit_requirements": "complete",
            "digital_signature": True,
            "compliance_standards": ["SOX", "GDPR", "HIPAA"],
            "parallel_approvals": True,
            "conditional_routing": True,
        }

        # Test workflow creation performance
        start_time = time.time()
        workflow = framework.create_enterprise_workflow("approval", complex_config)
        built_workflow = workflow.build()
        creation_time = time.time() - start_time

        # Execute workflow and measure performance
        runtime = LocalRuntime()
        exec_start = time.time()
        results, run_id = runtime.execute(built_workflow)
        execution_time = time.time() - exec_start

        # Verify performance requirements
        assert (
            creation_time < 1.0
        ), f"Workflow creation took {creation_time:.2f}s (should be <1s)"
        assert (
            execution_time < 5.0
        ), f"Workflow execution took {execution_time:.2f}s (should be <5s)"

        # Verify workflow complexity was handled correctly
        assert len(results) >= 5, "Not all approval levels were processed"

        # Verify all nodes completed successfully
        for node_id, result in results.items():
            assert result["status"] == "completed", f"Node {node_id} failed: {result}"

    def test_concurrent_enterprise_workflows_performance(self):
        """Test performance of concurrent enterprise workflows."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        import kaizen

        framework = kaizen.Kaizen(
            config={"audit_trail_enabled": True, "performance_optimization": True}
        )

        def execute_enterprise_workflow(workflow_id):
            """Execute a single enterprise workflow."""
            config = {
                "approval_levels": ["technical", "business"],
                "audit_requirements": "standard",
                "workflow_id": workflow_id,
            }

            workflow = framework.create_enterprise_workflow("approval", config)
            built_workflow = workflow.build()

            runtime = LocalRuntime()
            results, run_id = runtime.execute(built_workflow)

            return workflow_id, results, run_id

        # Execute multiple workflows concurrently
        num_workflows = 3
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_workflows) as executor:
            futures = [
                executor.submit(execute_enterprise_workflow, f"workflow_{i}")
                for i in range(num_workflows)
            ]

            completed_workflows = []
            for future in as_completed(futures):
                workflow_id, results, run_id = future.result()
                completed_workflows.append((workflow_id, results, run_id))

        total_time = time.time() - start_time

        # Verify all workflows completed successfully
        assert len(completed_workflows) == num_workflows

        # Verify performance (all workflows should complete in <5 seconds total)
        assert (
            total_time < 5.0
        ), f"Concurrent execution took {total_time:.2f}s (should be <5s)"

        # Verify unique run IDs
        run_ids = [run_id for _, _, run_id in completed_workflows]
        assert len(set(run_ids)) == num_workflows, "Run IDs should be unique"

        # Verify all workflows executed successfully
        for workflow_id, results, run_id in completed_workflows:
            assert results is not None
            assert run_id is not None
            for node_id, result in results.items():
                assert (
                    result["status"] == "completed"
                ), f"Node {node_id} in {workflow_id} failed: {result}"


# Test fixtures for integration tests
@pytest.fixture(scope="module", autouse=True)
def setup_integration_environment():
    """Setup integration test environment with real Docker services."""
    # Integration tests now use the existing Docker infrastructure that's already running
    # This avoids complex test-env setup issues and focuses on actual test functionality
    import psycopg2
    import redis

    # Verify core infrastructure is available (PostgreSQL and Redis)
    try:
        # Check PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5434,
            database="kailash_test",
            user="test_user",
            password="test_password",
            connect_timeout=5,
        )
        conn.close()

        # Check Redis
        r = redis.Redis(host="localhost", port=6380, db=0)
        r.ping()

        # Infrastructure is available, tests can proceed

    except Exception as e:
        pytest.skip(
            f"Required infrastructure not available: {e}. Please ensure Docker services are running."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s", "--timeout=5"])

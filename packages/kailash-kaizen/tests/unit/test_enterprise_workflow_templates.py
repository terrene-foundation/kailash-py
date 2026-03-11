"""
Tier 1 (Unit Tests) for Enterprise Workflow Templates

These tests verify enterprise workflow template creation and configuration at the unit level,
focusing on individual components without external dependencies.

Test Requirements:
- Fast execution (<1 second per test)
- No external dependencies (databases, APIs, files)
- Can use mocks for external services only
- Test all public methods and edge cases
- Focus on individual template functionality
- Location: tests/unit/

Test Coverage:
1. Enterprise workflow template creation and validation
2. Approval workflow template generation with multi-level stages
3. Customer service workflow routing and escalation logic
4. Document analysis pipeline template creation
5. Enterprise configuration validation and error handling
6. Template parameter validation and defaults
7. Enterprise audit trail configuration
8. Compliance workflow template validation
"""

import time
from unittest.mock import patch

# Import framework components
import pytest
from kaizen.core.framework import Kaizen

# Test markers
pytestmark = pytest.mark.unit


class TestEnterpriseWorkflowTemplateCreation:
    """Test core enterprise workflow template creation functionality."""

    def test_create_enterprise_workflow_approval_template(self):
        """Test approval workflow template creation with multi-level approval stages."""
        # Initialize framework
        framework = Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "security_level": "high",
                "transparency_enabled": True,
            }
        )

        # Test approval workflow template creation
        approval_config = {
            "approval_levels": ["technical", "business", "executive"],
            "escalation_timeout": "24_hours",
            "audit_requirements": "complete",
            "digital_signature": True,
            "compliance_standards": ["SOX", "GDPR"],
        }

        # This should create an enterprise approval workflow template
        approval_workflow = framework.create_enterprise_workflow(
            "approval", approval_config
        )

        # Verify workflow template structure
        assert approval_workflow is not None
        assert hasattr(approval_workflow, "template_type")
        assert approval_workflow.template_type == "approval"
        assert hasattr(approval_workflow, "config")

        # Verify essential config elements are present
        for key, value in approval_config.items():
            assert approval_workflow.config[key] == value

        # Verify approval levels are configured
        assert len(approval_workflow.approval_levels) == 3
        assert approval_workflow.approval_levels == [
            "technical",
            "business",
            "executive",
        ]

        # Verify enterprise features
        assert approval_workflow.audit_requirements == "complete"
        assert approval_workflow.digital_signature is True
        assert approval_workflow.compliance_standards == ["SOX", "GDPR"]

        # Verify escalation configuration
        assert approval_workflow.escalation_timeout == "24_hours"

        # Verify workflow can be built for execution
        built_workflow = approval_workflow.build()
        assert built_workflow is not None

    def test_create_enterprise_workflow_customer_service_template(self):
        """Test customer service workflow template creation with routing and escalation."""
        framework = Kaizen(
            config={"audit_trail_enabled": True, "monitoring_level": "detailed"}
        )

        # Test customer service workflow template creation
        service_config = {
            "routing_rules": "priority_based",
            "escalation_levels": ["tier1", "tier2", "supervisor"],
            "sla_requirements": {"response_time": "5_minutes"},
            "audit_trail": True,
        }

        service_workflow = framework.create_enterprise_workflow(
            "customer_service", service_config
        )

        # Verify workflow template structure
        assert service_workflow is not None
        assert service_workflow.template_type == "customer_service"

        # Verify essential config elements are present
        for key, value in service_config.items():
            assert service_workflow.config[key] == value

        # Verify routing configuration
        assert service_workflow.routing_rules == "priority_based"

        # Verify escalation levels
        assert len(service_workflow.escalation_levels) == 3
        assert service_workflow.escalation_levels == ["tier1", "tier2", "supervisor"]

        # Verify SLA requirements
        assert service_workflow.sla_requirements["response_time"] == "5_minutes"

        # Verify audit trail is enabled
        assert service_workflow.audit_trail_enabled is True

        # Verify workflow can be built
        built_workflow = service_workflow.build()
        assert built_workflow is not None

    def test_create_enterprise_workflow_document_analysis_template(self):
        """Test document analysis workflow template creation with compliance checks."""
        framework = Kaizen(
            config={
                "compliance_mode": "enterprise",
                "security_level": "high",
                "transparency_enabled": True,
                "audit_trail_enabled": True,
            }
        )

        # Test document analysis workflow template creation
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

        # Verify workflow template structure
        assert analysis_workflow is not None
        assert analysis_workflow.template_type == "document_analysis"

        # Verify essential config elements are present
        for key, value in analysis_config.items():
            assert analysis_workflow.config[key] == value

        # Verify processing stages
        assert len(analysis_workflow.processing_stages) == 4
        assert analysis_workflow.processing_stages == [
            "extraction",
            "classification",
            "analysis",
            "compliance",
        ]

        # Verify compliance checks
        assert len(analysis_workflow.compliance_checks) == 2
        assert analysis_workflow.compliance_checks == [
            "PII_detection",
            "data_classification",
        ]

        # Verify audit requirements
        assert analysis_workflow.audit_requirements == "full_lineage"

        # Verify workflow can be built
        built_workflow = analysis_workflow.build()
        assert built_workflow is not None

    def test_create_enterprise_workflow_invalid_template_type(self):
        """Test error handling for invalid enterprise workflow template types."""
        framework = Kaizen()

        # Test invalid template type
        with pytest.raises(
            ValueError, match="Unknown enterprise workflow template type"
        ):
            framework.create_enterprise_workflow("invalid_template", {})

    def test_create_enterprise_workflow_missing_config(self):
        """Test error handling for missing required configuration parameters."""
        framework = Kaizen()

        # Test approval workflow without required config
        with pytest.raises(ValueError, match="Missing required configuration"):
            framework.create_enterprise_workflow("approval", {})

        # Test customer service workflow without required config
        with pytest.raises(ValueError, match="Missing required configuration"):
            framework.create_enterprise_workflow("customer_service", {})

    def test_create_enterprise_workflow_invalid_config_values(self):
        """Test error handling for invalid configuration values."""
        framework = Kaizen()

        # Test invalid approval levels
        invalid_config = {
            "approval_levels": [],  # Empty approval levels should fail
            "escalation_timeout": "24_hours",
            "audit_requirements": "complete",
        }

        with pytest.raises(ValueError, match="approval_levels cannot be empty"):
            framework.create_enterprise_workflow("approval", invalid_config)

        # Test invalid escalation timeout
        invalid_timeout_config = {
            "approval_levels": ["technical"],
            "escalation_timeout": "invalid_timeout",
            "audit_requirements": "complete",
        }

        with pytest.raises(ValueError, match="Invalid escalation_timeout format"):
            framework.create_enterprise_workflow("approval", invalid_timeout_config)


class TestEnterpriseWorkflowTemplateConfiguration:
    """Test enterprise workflow template configuration and validation."""

    def test_enterprise_workflow_default_configuration(self):
        """Test enterprise workflow templates apply sensible defaults."""
        framework = Kaizen(
            config={"compliance_mode": "enterprise", "transparency_enabled": True}
        )

        # Test approval workflow with minimal config
        minimal_config = {"approval_levels": ["technical", "business"]}

        workflow = framework.create_enterprise_workflow("approval", minimal_config)

        # Verify defaults are applied
        assert workflow.escalation_timeout == "24_hours"  # Default timeout
        assert workflow.audit_requirements == "standard"  # Default audit level
        assert workflow.digital_signature is False  # Default signature setting
        assert workflow.compliance_standards == []  # Default empty standards

    def test_enterprise_workflow_configuration_validation(self):
        """Test configuration parameter validation for enterprise workflows."""
        framework = Kaizen()

        # Test valid compliance standards
        valid_config = {
            "approval_levels": ["technical"],
            "compliance_standards": ["SOX", "GDPR", "HIPAA"],
        }

        workflow = framework.create_enterprise_workflow("approval", valid_config)
        assert workflow.compliance_standards == ["SOX", "GDPR", "HIPAA"]

        # Test invalid compliance standards
        invalid_config = {
            "approval_levels": ["technical"],
            "compliance_standards": ["INVALID_STANDARD"],
        }

        with pytest.raises(ValueError, match="Invalid compliance standard"):
            framework.create_enterprise_workflow("approval", invalid_config)

    def test_enterprise_workflow_audit_configuration(self):
        """Test audit trail configuration for enterprise workflows."""
        framework = Kaizen(config={"audit_trail_enabled": True})

        # Test complete audit configuration
        audit_config = {
            "approval_levels": ["technical"],
            "audit_requirements": "complete",
            "audit_retention": "7_years",
            "audit_encryption": True,
        }

        workflow = framework.create_enterprise_workflow("approval", audit_config)

        # Verify audit configuration
        assert workflow.audit_requirements == "complete"
        assert workflow.audit_retention == "7_years"
        assert workflow.audit_encryption is True

        # Verify audit trail is properly initialized
        assert hasattr(workflow, "audit_trail")
        assert workflow.audit_trail is not None

    def test_enterprise_workflow_security_configuration(self):
        """Test security configuration for enterprise workflows."""
        framework = Kaizen(
            config={"security_level": "high", "audit_trail_enabled": True}
        )

        # Test high security configuration
        security_config = {
            "approval_levels": ["technical", "business"],
            "digital_signature": True,
            "encryption_required": True,
            "access_control": "strict",
            "security_audit": True,
        }

        workflow = framework.create_enterprise_workflow("approval", security_config)

        # Verify security settings
        assert workflow.digital_signature is True
        assert workflow.encryption_required is True
        assert workflow.access_control == "strict"
        assert workflow.security_audit is True


class TestEnterpriseWorkflowTemplateTypes:
    """Test different types of enterprise workflow templates."""

    def test_compliance_workflow_template(self):
        """Test compliance-specific workflow template creation."""
        framework = Kaizen(
            config={"compliance_mode": "enterprise", "transparency_enabled": True}
        )

        # Test GDPR compliance workflow
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

        # Verify compliance workflow structure
        assert compliance_workflow.template_type == "compliance"
        assert compliance_workflow.compliance_type == "GDPR"
        assert len(compliance_workflow.data_processing_stages) == 3
        assert compliance_workflow.privacy_checks is True

        # Test SOX compliance workflow
        sox_config = {
            "compliance_type": "SOX",
            "financial_controls": [
                "segregation_of_duties",
                "authorization",
                "audit_trail",
            ],
            "reporting_requirements": "quarterly",
            "audit_trail": True,
        }

        sox_workflow = framework.create_enterprise_workflow("compliance", sox_config)
        assert sox_workflow.compliance_type == "SOX"
        assert len(sox_workflow.financial_controls) == 3
        assert sox_workflow.reporting_requirements == "quarterly"

    def test_multi_tenant_workflow_template(self):
        """Test multi-tenant workflow template with tenant isolation."""
        framework = Kaizen(config={"multi_tenant": True})

        # Test multi-tenant workflow configuration
        tenant_config = {
            "approval_levels": ["technical", "business"],
            "tenant_isolation": "strict",
            "cross_tenant_access": False,
            "tenant_specific_rules": True,
        }

        tenant_workflow = framework.create_enterprise_workflow(
            "approval", tenant_config
        )

        # Verify tenant isolation settings
        assert tenant_workflow.tenant_isolation == "strict"
        assert tenant_workflow.cross_tenant_access is False
        assert tenant_workflow.tenant_specific_rules is True

        # Verify tenant workflow can be built
        built_workflow = tenant_workflow.build()
        assert built_workflow is not None

    def test_resource_allocation_workflow_template(self):
        """Test resource allocation workflow template creation."""
        framework = Kaizen(config={"resource_management": True})

        # Test resource allocation workflow
        resource_config = {
            "allocation_strategy": "dynamic",
            "resource_types": ["compute", "storage", "network"],
            "optimization_enabled": True,
            "cost_tracking": True,
        }

        resource_workflow = framework.create_enterprise_workflow(
            "resource_allocation", resource_config
        )

        # Verify resource allocation settings
        assert resource_workflow.template_type == "resource_allocation"
        assert resource_workflow.allocation_strategy == "dynamic"
        assert len(resource_workflow.resource_types) == 3
        assert resource_workflow.optimization_enabled is True
        assert resource_workflow.cost_tracking is True


class TestEnterpriseWorkflowTemplateIntegration:
    """Test enterprise workflow template integration with existing framework components."""

    def test_enterprise_workflow_with_agent_integration(self):
        """Test enterprise workflows integrate with existing agent system."""
        framework = Kaizen()

        # Create agent for enterprise workflow
        approval_agent = framework.create_agent(
            agent_id="approval_agent",
            config={
                "role": "approval_coordinator",
                "capabilities": ["workflow_management", "audit_logging"],
            },
        )

        # Create enterprise workflow for the agent
        workflow_config = {
            "approval_levels": ["technical", "business"],
            "audit_requirements": "complete",
        }

        enterprise_workflow = framework.create_enterprise_workflow(
            "approval", workflow_config
        )

        # Verify integration
        assert approval_agent is not None
        assert enterprise_workflow is not None

        # Test agent can execute enterprise workflow
        built_workflow = enterprise_workflow.build()
        assert built_workflow is not None

        # Verify the workflow contains proper enterprise nodes
        # (This will be validated in implementation)
        assert hasattr(enterprise_workflow, "_workflow_nodes")

    def test_enterprise_workflow_audit_trail_integration(self):
        """Test enterprise workflows integrate with audit trail system."""
        framework = Kaizen(config={"audit_trail_enabled": True})

        # Create workflow with audit requirements
        audit_config = {
            "approval_levels": ["technical"],
            "audit_requirements": "complete",
            "audit_retention": "7_years",
        }

        workflow = framework.create_enterprise_workflow("approval", audit_config)

        # Verify audit trail integration
        assert hasattr(workflow, "audit_trail")
        assert workflow.audit_trail is not None

        # Test audit trail access
        audit_trail = framework.audit_trail.get_current_trail()
        assert audit_trail is not None
        assert isinstance(audit_trail, list)

    def test_enterprise_workflow_compliance_reporting(self):
        """Test enterprise workflows support compliance reporting."""
        framework = Kaizen(
            config={
                "compliance_mode": "enterprise",
                "audit_trail_enabled": True,
                "transparency_enabled": True,
            }
        )

        # Create compliance workflow
        compliance_config = {
            "compliance_type": "GDPR",
            "data_processing_stages": ["consent", "processing", "storage"],
            "reporting_enabled": True,
        }

        workflow = framework.create_enterprise_workflow("compliance", compliance_config)

        # Verify compliance reporting capability
        assert workflow.reporting_enabled is True

        # Test compliance report generation
        compliance_report = framework.generate_compliance_report()
        assert compliance_report is not None
        assert isinstance(compliance_report, dict)
        assert "compliance_status" in compliance_report
        assert "workflow_count" in compliance_report


class TestEnterpriseWorkflowTemplatePerformance:
    """Test performance requirements for enterprise workflow templates."""

    def test_enterprise_workflow_creation_performance(self):
        """Test enterprise workflow creation meets performance requirements (<1000ms)."""
        framework = Kaizen()

        # Test approval workflow creation performance
        approval_config = {
            "approval_levels": ["technical", "business", "executive", "board"],
            "escalation_timeout": "24_hours",
            "audit_requirements": "complete",
            "digital_signature": True,
            "compliance_standards": ["SOX", "GDPR", "HIPAA"],
        }

        start_time = time.time()
        workflow = framework.create_enterprise_workflow("approval", approval_config)
        creation_time = time.time() - start_time

        # Verify performance requirement (<1000ms for complex workflows)
        assert creation_time < 1.0
        assert workflow is not None

    def test_multiple_enterprise_workflow_creation_performance(self):
        """Test creating multiple enterprise workflows maintains performance."""
        framework = Kaizen(config={"performance_optimization": True})

        # Create multiple different enterprise workflows
        workflow_configs = [
            ("approval", {"approval_levels": ["technical", "business"]}),
            (
                "customer_service",
                {
                    "routing_rules": "priority_based",
                    "escalation_levels": ["tier1", "tier2"],
                },
            ),
            (
                "document_analysis",
                {
                    "processing_stages": ["extraction", "analysis"],
                    "compliance_checks": ["PII_detection"],
                },
            ),
            (
                "compliance",
                {
                    "compliance_type": "GDPR",
                    "data_processing_stages": ["consent", "processing"],
                },
            ),
            (
                "resource_allocation",
                {"allocation_strategy": "dynamic", "resource_types": ["compute"]},
            ),
        ]

        start_time = time.time()
        workflows = []

        for template_type, config in workflow_configs:
            workflow = framework.create_enterprise_workflow(template_type, config)
            workflows.append(workflow)

        total_time = time.time() - start_time

        # Verify all workflows created successfully
        assert len(workflows) == 5
        for workflow in workflows:
            assert workflow is not None

        # Verify performance (all 5 workflows in <5 seconds)
        assert total_time < 5.0

        # Verify average time per workflow
        avg_time = total_time / len(workflows)
        assert avg_time < 1.0


# Test fixtures and utilities
@pytest.fixture
def enterprise_framework():
    """Provide enterprise-configured Kaizen framework for tests."""
    return Kaizen(
        config={
            "audit_trail_enabled": True,
            "compliance_mode": "enterprise",
            "security_level": "high",
            "monitoring_level": "detailed",
            "multi_tenant": True,
            "transparency_enabled": True,
        }
    )


@pytest.fixture
def mock_enterprise_nodes():
    """Mock enterprise nodes for unit testing."""
    with (
        patch("kailash.nodes.enterprise.EnterpriseAuditLoggerNode") as mock_audit,
        patch("kailash.nodes.admin.EnterpriseAuditLogNode") as mock_admin_audit,
        patch("kailash.nodes.compliance.GDPRComplianceNode") as mock_gdpr,
        patch("kailash.nodes.security.ABACEvaluatorNode") as mock_abac,
    ):

        # Configure mocks
        mock_audit.return_value.get_parameters.return_value = {}
        mock_admin_audit.return_value.get_parameters.return_value = {}
        mock_gdpr.return_value.get_parameters.return_value = {}
        mock_abac.return_value.get_parameters.return_value = {}

        yield {
            "audit": mock_audit,
            "admin_audit": mock_admin_audit,
            "gdpr": mock_gdpr,
            "abac": mock_abac,
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s", "--timeout=1"])

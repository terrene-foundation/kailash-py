"""
Tests for compliance-monitoring enterprise workflow example.

This test suite validates:
1. Individual agent behavior (PolicyParserAgent, ComplianceCheckerAgent, ViolationAnalyzerAgent, AuditReporterAgent)
2. Workflow integration and multi-agent collaboration
3. Shared memory usage for compliance monitoring pipeline
4. Real-world compliance monitoring scenarios

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load compliance-monitoring example
_compliance_module = import_example_module(
    "examples/3-enterprise-workflows/compliance-monitoring"
)
PolicyParserAgent = _compliance_module.PolicyParserAgent
ComplianceCheckerAgent = _compliance_module.ComplianceCheckerAgent
ViolationAnalyzerAgent = _compliance_module.ViolationAnalyzerAgent
AuditReporterAgent = _compliance_module.AuditReporterAgent
ComplianceConfig = _compliance_module.ComplianceConfig
compliance_monitoring_workflow = _compliance_module.compliance_monitoring_workflow
batch_compliance_monitoring = _compliance_module.batch_compliance_monitoring


class TestComplianceMonitoringAgents:
    """Test individual agent behavior."""

    def test_policy_parser_agent_parses_policies(self):
        """Test PolicyParserAgent parses compliance policies.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = ComplianceConfig(llm_provider="mock")
        agent = PolicyParserAgent(config)

        policies = {
            "GDPR": "EU data protection regulation",
            "HIPAA": "Healthcare privacy standards",
            "SOX": "Financial reporting requirements",
        }

        result = agent.parse_policies(policies)

        # Structure test only - content depends on provider
        assert result is not None
        assert "parsed_policies" in result
        assert "rules" in result
        # rules may be empty list with mock provider
        assert isinstance(result["rules"], list)

    def test_compliance_checker_agent_checks_compliance(self):
        """Test ComplianceCheckerAgent checks data against policies."""

        config = ComplianceConfig(llm_provider="mock")
        agent = ComplianceCheckerAgent(config)

        data = {
            "user_data": {"email": "test@example.com", "age": 25},
            "access_logs": ["2024-01-01: User accessed records"],
        }

        rules = [
            {"rule_id": "R1", "description": "Data encryption required"},
            {"rule_id": "R2", "description": "Access logging required"},
        ]

        result = agent.check_compliance(data, rules)

        assert result is not None
        assert "compliance_status" in result
        assert "violations" in result
        assert "passed_checks" in result

    def test_violation_analyzer_agent_analyzes_violations(self):
        """Test ViolationAnalyzerAgent analyzes compliance violations."""

        config = ComplianceConfig(llm_provider="mock")
        agent = ViolationAnalyzerAgent(config)

        violations = [
            {"rule_id": "R1", "severity": "high", "description": "Unencrypted data"},
            {"rule_id": "R2", "severity": "medium", "description": "Missing audit log"},
        ]

        result = agent.analyze_violations(violations)

        assert result is not None
        assert "analysis" in result
        assert "risk_assessment" in result
        assert "recommendations" in result

    def test_audit_reporter_agent_generates_report(self):
        """Test AuditReporterAgent generates audit report."""

        config = ComplianceConfig(llm_provider="mock")
        agent = AuditReporterAgent(config)

        audit_data = {
            "compliance_status": "partial",
            "violations": [{"rule_id": "R1", "severity": "high"}],
            "analysis": {"risk_level": "high"},
        }

        result = agent.generate_report(audit_data)

        assert result is not None
        assert "report" in result
        assert "summary" in result


class TestComplianceMonitoringWorkflow:
    """Test complete compliance monitoring workflow."""

    def test_single_compliance_check(self):
        """Test performing a single compliance check."""

        config = ComplianceConfig(llm_provider="mock")

        check_spec = {
            "system": "user_database",
            "policies": {"GDPR": "Data protection rules"},
            "data": {"users": [{"email": "test@example.com"}]},
        }

        result = compliance_monitoring_workflow(check_spec, config)

        assert result is not None
        assert "parsed_policies" in result
        assert "compliance_check" in result
        assert "violation_analysis" in result
        assert "audit_report" in result

    def test_batch_compliance_checks(self):
        """Test performing multiple compliance checks."""

        config = ComplianceConfig(llm_provider="mock")

        check_specs = [
            {"system": "db1", "policies": {"GDPR": "rules"}, "data": {}},
            {"system": "db2", "policies": {"HIPAA": "rules"}, "data": {}},
            {"system": "api", "policies": {"SOX": "rules"}, "data": {}},
        ]

        results = batch_compliance_monitoring(check_specs, config)

        assert results is not None
        assert len(results) == 3
        assert all("audit_report" in r for r in results)

    def test_scheduled_compliance_monitoring(self):
        """Test scheduled compliance monitoring."""

        config = ComplianceConfig(llm_provider="mock", schedule="daily")

        check_spec = {
            "system": "production_db",
            "policies": {"GDPR": "Data protection"},
        }

        result = compliance_monitoring_workflow(check_spec, config)

        assert result is not None


class TestSharedMemoryIntegration:
    """Test shared memory usage in compliance monitoring pipeline."""

    def test_parser_writes_to_shared_memory(self):
        """Test PolicyParserAgent writes parsed policies to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = ComplianceConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = PolicyParserAgent(config, shared_pool, "parser")

        policies = {"GDPR": "Data protection"}
        agent.parse_policies(policies)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="checker", tags=["parsed_policies"], segments=["pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "parser"

    def test_checker_reads_from_shared_memory(self):
        """Test ComplianceCheckerAgent reads parsed policies from shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = ComplianceConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        parser = PolicyParserAgent(config, shared_pool, "parser")
        ComplianceCheckerAgent(config, shared_pool, "checker")

        # Parser writes
        policies = {"GDPR": "Data protection"}
        parser.parse_policies(policies)

        # Checker reads
        insights = shared_pool.read_relevant(
            agent_id="checker", tags=["parsed_policies"], segments=["pipeline"]
        )

        assert len(insights) > 0

    def test_pipeline_coordination_via_shared_memory(self):
        """Test full pipeline coordination via shared memory."""

        config = ComplianceConfig(llm_provider="mock")

        check_spec = {"system": "test_system", "policies": {"GDPR": "rules"}}

        result = compliance_monitoring_workflow(check_spec, config)

        # All stages should complete
        assert "parsed_policies" in result
        assert "compliance_check" in result
        assert "violation_analysis" in result
        assert "audit_report" in result


class TestEnterpriseFeatures:
    """Test enterprise-specific features."""

    def test_multi_policy_compliance(self):
        """Test checking compliance against multiple policies.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = ComplianceConfig(llm_provider="mock")
        agent = PolicyParserAgent(config)

        policies = {
            "GDPR": "EU data protection",
            "HIPAA": "Healthcare privacy",
            "SOX": "Financial reporting",
            "PCI-DSS": "Payment card security",
        }

        result = agent.parse_policies(policies)

        # Structure test only - parsed_policies may be empty dict with mock provider
        assert isinstance(result["parsed_policies"], dict)

    def test_severity_levels(self):
        """Test violation severity level handling."""

        config = ComplianceConfig(llm_provider="mock")
        agent = ViolationAnalyzerAgent(config)

        violations = [
            {"rule_id": "R1", "severity": "critical"},
            {"rule_id": "R2", "severity": "high"},
            {"rule_id": "R3", "severity": "medium"},
            {"rule_id": "R4", "severity": "low"},
        ]

        result = agent.analyze_violations(violations)

        assert "risk_assessment" in result

    def test_audit_trail(self):
        """Test audit trail generation."""

        config = ComplianceConfig(llm_provider="mock", audit_trail=True)
        agent = AuditReporterAgent(config)

        audit_data = {"compliance_status": "compliant", "violations": []}

        result = agent.generate_report(audit_data)

        assert "report" in result

    def test_error_handling_missing_policies(self):
        """Test error handling for missing policies."""

        config = ComplianceConfig(llm_provider="mock")

        # Missing policies
        check_spec = {"system": "test"}  # Missing policies

        result = compliance_monitoring_workflow(check_spec, config)

        # Should handle gracefully
        assert result is not None


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = ComplianceConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.severity_threshold == "medium"

    def test_custom_config(self):
        """Test custom configuration."""

        config = ComplianceConfig(
            llm_provider="openai",
            model="gpt-4",
            severity_threshold="high",
            schedule="daily",
            audit_trail=True,
            alert_emails=["compliance@example.com"],
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.severity_threshold == "high"
        assert config.audit_trail is True

    def test_alert_config(self):
        """Test alert configuration."""

        config = ComplianceConfig(
            llm_provider="mock",
            alert_emails=["admin@example.com", "security@example.com"],
            severity_threshold="critical",
        )

        assert len(config.alert_emails) == 2
        assert config.severity_threshold == "critical"

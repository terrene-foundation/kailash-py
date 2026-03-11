"""
Compliance Monitoring Enterprise Workflow

This example demonstrates automated compliance checking using multi-agent collaboration.

Agents:
1. PolicyParserAgent - Parses compliance policies and extracts rules
2. ComplianceCheckerAgent - Checks data/systems against compliance rules
3. ViolationAnalyzerAgent - Analyzes violations and assesses risk
4. AuditReporterAgent - Generates compliance audit reports

Use Cases:
- GDPR compliance monitoring
- HIPAA compliance checking
- SOX financial compliance
- PCI-DSS payment security
- Custom regulatory compliance

Architecture Pattern: Sequential Pipeline with Shared Memory
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class ComplianceConfig:
    """Configuration for compliance monitoring workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    severity_threshold: str = "medium"  # "low", "medium", "high", "critical"
    schedule: Optional[str] = None  # "daily", "weekly", "monthly"
    audit_trail: bool = False
    alert_emails: List[str] = field(default_factory=list)


# ===== Signatures =====


class PolicyParsingSignature(Signature):
    """Signature for policy parsing."""

    policies: str = InputField(description="Compliance policies as JSON")

    parsed_policies: str = OutputField(description="Parsed policies as JSON")
    rules: str = OutputField(description="Extracted compliance rules as JSON")


class ComplianceCheckingSignature(Signature):
    """Signature for compliance checking."""

    data: str = InputField(description="Data to check as JSON")
    rules: str = InputField(description="Compliance rules as JSON")

    compliance_status: str = OutputField(description="Overall compliance status")
    violations: str = OutputField(description="Detected violations as JSON")
    passed_checks: str = OutputField(description="Passed checks as JSON")


class ViolationAnalysisSignature(Signature):
    """Signature for violation analysis."""

    violations: str = InputField(description="Violations to analyze as JSON")

    analysis: str = OutputField(description="Violation analysis")
    risk_assessment: str = OutputField(description="Risk assessment")
    recommendations: str = OutputField(description="Remediation recommendations")


class AuditReportingSignature(Signature):
    """Signature for audit reporting."""

    audit_data: str = InputField(description="Complete audit data as JSON")

    report: str = OutputField(description="Audit report content")
    summary: str = OutputField(description="Executive summary")


# ===== Agents =====


class PolicyParserAgent(BaseAgent):
    """Agent for parsing compliance policies."""

    def __init__(
        self,
        config: ComplianceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "parser",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=PolicyParsingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.compliance_config = config

    def parse_policies(self, policies: Dict[str, Any]) -> Dict[str, Any]:
        """Parse compliance policies and extract rules."""
        # Run agent
        result = self.run(policies=json.dumps(policies))

        # Extract outputs
        parsed_policies_raw = result.get("parsed_policies", "{}")
        if isinstance(parsed_policies_raw, str):
            try:
                parsed_policies = (
                    json.loads(parsed_policies_raw) if parsed_policies_raw else {}
                )
            except:
                parsed_policies = {"raw": parsed_policies_raw}
        else:
            parsed_policies = (
                parsed_policies_raw if isinstance(parsed_policies_raw, dict) else {}
            )

        rules_raw = result.get("rules", "[]")
        if isinstance(rules_raw, str):
            try:
                rules = json.loads(rules_raw) if rules_raw else []
            except:
                rules = [{"rule": rules_raw}]
        else:
            rules = (
                rules_raw
                if isinstance(rules_raw, list)
                else [rules_raw] if rules_raw else []
            )

        parse_result = {"parsed_policies": parsed_policies, "rules": rules}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=parse_result,  # Auto-serialized
            tags=["parsed_policies", "pipeline"],
            importance=0.9,
            segment="pipeline",
        )

        return parse_result


class ComplianceCheckerAgent(BaseAgent):
    """Agent for checking compliance against rules."""

    def __init__(
        self,
        config: ComplianceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "checker",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ComplianceCheckingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.compliance_config = config

    def check_compliance(
        self, data: Dict[str, Any], rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check data against compliance rules."""
        # Run agent
        result = self.run(data=json.dumps(data), rules=json.dumps(rules))

        # Extract outputs
        compliance_status = result.get("compliance_status", "unknown")

        # UX Improvement: One-line extraction

        violations = self.extract_list(result, "violations", default=[])

        # UX Improvement: One-line extraction

        passed_checks = self.extract_list(result, "passed_checks", default=[])

        check_result = {
            "compliance_status": compliance_status,
            "violations": violations,
            "passed_checks": passed_checks,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=check_result,  # Auto-serialized
            tags=["compliance_check", "pipeline"],
            importance=1.0,
            segment="pipeline",
        )

        return check_result


class ViolationAnalyzerAgent(BaseAgent):
    """Agent for analyzing compliance violations."""

    def __init__(
        self,
        config: ComplianceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "analyzer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ViolationAnalysisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.compliance_config = config

    def analyze_violations(self, violations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze violations and assess risk."""
        # Run agent
        result = self.run(violations=json.dumps(violations))

        # Extract outputs
        analysis = result.get("analysis", "No analysis available")
        risk_assessment = result.get("risk_assessment", "Unknown risk")
        recommendations = result.get("recommendations", "No recommendations")

        analysis_result = {
            "analysis": analysis,
            "risk_assessment": risk_assessment,
            "recommendations": recommendations,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=analysis_result,  # Auto-serialized
            tags=["violation_analysis", "pipeline"],
            importance=0.95,
            segment="pipeline",
        )

        return analysis_result


class AuditReporterAgent(BaseAgent):
    """Agent for generating audit reports."""

    def __init__(
        self,
        config: ComplianceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "reporter",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AuditReportingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.compliance_config = config

    def generate_report(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate compliance audit report."""
        # Run agent
        result = self.run(audit_data=json.dumps(audit_data))

        # Extract outputs
        report = result.get("report", "Report not generated")
        summary = result.get("summary", "No summary available")

        report_result = {"report": report, "summary": summary}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=report_result,  # Auto-serialized
            tags=["audit_report", "pipeline"],
            importance=1.0,
            segment="pipeline",
        )

        return report_result


# ===== Workflow Functions =====


def compliance_monitoring_workflow(
    check_spec: Dict[str, Any], config: Optional[ComplianceConfig] = None
) -> Dict[str, Any]:
    """
    Execute compliance monitoring workflow.

    Args:
        check_spec: Compliance check specification with 'system', 'policies', 'data'
        config: Configuration for compliance monitoring

    Returns:
        Complete compliance check with policies, violations, analysis, and report
    """
    if config is None:
        config = ComplianceConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    parser = PolicyParserAgent(config, shared_pool, "parser")
    checker = ComplianceCheckerAgent(config, shared_pool, "checker")
    analyzer = ViolationAnalyzerAgent(config, shared_pool, "analyzer")
    reporter = AuditReporterAgent(config, shared_pool, "reporter")

    # Execute pipeline
    # Stage 1: Parse policies
    policies = check_spec.get("policies", {})
    parsed = parser.parse_policies(policies)

    # Stage 2: Check compliance
    data = check_spec.get("data", {})
    compliance_check = checker.check_compliance(data, parsed["rules"])

    # Stage 3: Analyze violations
    violation_analysis = analyzer.analyze_violations(compliance_check["violations"])

    # Stage 4: Generate audit report
    audit_data = {
        "system": check_spec.get("system", "unknown"),
        "compliance_status": compliance_check["compliance_status"],
        "violations": compliance_check["violations"],
        "passed_checks": compliance_check["passed_checks"],
        "analysis": violation_analysis["analysis"],
        "risk_assessment": violation_analysis["risk_assessment"],
        "recommendations": violation_analysis["recommendations"],
    }

    audit_report = reporter.generate_report(audit_data)

    return {
        "system": check_spec.get("system", "unknown"),
        "parsed_policies": parsed,
        "compliance_check": compliance_check,
        "violation_analysis": violation_analysis,
        "audit_report": audit_report,
    }


def batch_compliance_monitoring(
    check_specs: List[Dict[str, Any]], config: Optional[ComplianceConfig] = None
) -> List[Dict[str, Any]]:
    """
    Execute batch compliance monitoring on multiple systems.

    Args:
        check_specs: List of compliance check specifications
        config: Configuration for compliance monitoring

    Returns:
        List of complete compliance checks
    """
    if config is None:
        config = ComplianceConfig()

    results = []

    # Process each check
    for spec in check_specs:
        result = compliance_monitoring_workflow(spec, config)
        results.append(result)

    return results


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = ComplianceConfig(llm_provider="mock")

    # Single compliance check
    check_spec = {
        "system": "user_database",
        "policies": {
            "GDPR": "EU data protection regulation - requires encryption and access logging",
            "HIPAA": "Healthcare privacy standards - requires audit trails",
        },
        "data": {
            "user_records": ["email", "name", "age"],
            "encryption": True,
            "access_logs": True,
        },
    }

    print("=== Single Compliance Check ===")
    result = compliance_monitoring_workflow(check_spec, config)
    print(f"System: {result['system']}")
    print(f"Compliance Status: {result['compliance_check']['compliance_status']}")
    print(f"Violations: {len(result['compliance_check']['violations'])}")
    print(f"Risk Assessment: {result['violation_analysis']['risk_assessment'][:50]}...")

    # Batch compliance monitoring
    check_specs = [
        {"system": "db1", "policies": {"GDPR": "Data protection"}, "data": {}},
        {"system": "db2", "policies": {"HIPAA": "Healthcare privacy"}, "data": {}},
        {"system": "api", "policies": {"SOX": "Financial reporting"}, "data": {}},
    ]

    print("\n=== Batch Compliance Monitoring ===")
    results = batch_compliance_monitoring(check_specs, config)
    print(f"Checked {len(results)} systems")
    for i, result in enumerate(results, 1):
        print(
            f"{i}. {result['system']}: {result['compliance_check']['compliance_status']}"
        )

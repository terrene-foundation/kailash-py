# Compliance Monitoring Enterprise Workflow

**Category**: Enterprise Workflows
**Pattern**: Multi-Agent Sequential Pipeline
**Complexity**: Intermediate
**Use Cases**: GDPR compliance, HIPAA healthcare privacy, SOX financial reporting, PCI-DSS payment security, custom regulatory compliance

## Overview

This example demonstrates automated compliance monitoring using four specialized agents that collaborate through SharedMemoryPool to parse policies, check compliance, analyze violations, and generate audit reports.

### Key Features

- **Multi-policy support** - Monitor GDPR, HIPAA, SOX, PCI-DSS, and custom policies
- **Automated checking** - Check data/systems against compliance rules automatically
- **Violation analysis** - Analyze violations with risk assessment
- **Audit reporting** - Generate comprehensive audit reports
- **Severity tracking** - Track violations by severity (critical, high, medium, low)
- **Scheduled monitoring** - Support for daily, weekly, monthly checks

## Architecture

```
Compliance Specification
     |
     v
┌─────────────────────┐
│ PolicyParserAgent   │ - Parses policies and extracts rules
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["parsed_policies", "pipeline"]
           │
           v
┌─────────────────────┐
│ComplianceCheckerAgent│ - Checks data against rules
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["compliance_check", "pipeline"]
           │
           v
┌─────────────────────┐
│ViolationAnalyzerAgent│ - Analyzes violations and assesses risk
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["violation_analysis", "pipeline"]
           │
           v
┌─────────────────────┐
│ AuditReporterAgent  │ - Generates audit reports
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["audit_report", "pipeline"]
           │
           v
   Final Audit Report
```

## Agents

### 1. PolicyParserAgent

**Signature**: `PolicyParsingSignature`
- **Inputs**: `policies` (str) - Compliance policies as JSON
- **Outputs**:
  - `parsed_policies` (str) - Parsed policies as JSON
  - `rules` (str) - Extracted compliance rules as JSON

**Responsibilities**:
- Parse compliance policies (GDPR, HIPAA, SOX, etc.)
- Extract specific compliance rules
- Write parsed policies to SharedMemoryPool

**SharedMemory Tags**: `["parsed_policies", "pipeline"]`, segment: `"pipeline"`

### 2. ComplianceCheckerAgent

**Signature**: `ComplianceCheckingSignature`
- **Inputs**:
  - `data` (str) - Data to check as JSON
  - `rules` (str) - Compliance rules as JSON
- **Outputs**:
  - `compliance_status` (str) - Overall compliance status
  - `violations` (str) - Detected violations as JSON
  - `passed_checks` (str) - Passed checks as JSON

**Responsibilities**:
- Check data against compliance rules
- Detect violations
- Track passed checks
- Write results to SharedMemoryPool

**SharedMemory Tags**: `["compliance_check", "pipeline"]`, segment: `"pipeline"`

### 3. ViolationAnalyzerAgent

**Signature**: `ViolationAnalysisSignature`
- **Inputs**: `violations` (str) - Violations to analyze as JSON
- **Outputs**:
  - `analysis` (str) - Violation analysis
  - `risk_assessment` (str) - Risk assessment
  - `recommendations` (str) - Remediation recommendations

**Responsibilities**:
- Analyze compliance violations
- Assess risk levels (critical, high, medium, low)
- Provide remediation recommendations
- Write analysis to SharedMemoryPool

**SharedMemory Tags**: `["violation_analysis", "pipeline"]`, segment: `"pipeline"`

### 4. AuditReporterAgent

**Signature**: `AuditReportingSignature`
- **Inputs**: `audit_data` (str) - Complete audit data as JSON
- **Outputs**:
  - `report` (str) - Audit report content
  - `summary` (str) - Executive summary

**Responsibilities**:
- Generate compliance audit reports
- Create executive summaries
- Write reports to SharedMemoryPool

**SharedMemory Tags**: `["audit_report", "pipeline"]`, segment: `"pipeline"`

## Quick Start

### 1. Basic Usage

```python
from workflow import compliance_monitoring_workflow, ComplianceConfig

config = ComplianceConfig(llm_provider="mock")

check_spec = {
    "system": "user_database",
    "policies": {
        "GDPR": "EU data protection regulation"
    },
    "data": {
        "encryption": True,
        "access_logs": True
    }
}

result = compliance_monitoring_workflow(check_spec, config)
print(f"Compliance Status: {result['compliance_check']['compliance_status']}")
```

### 2. Custom Configuration

```python
config = ComplianceConfig(
    llm_provider="openai",
    model="gpt-4",
    severity_threshold="high",  # "low", "medium", "high", "critical"
    schedule="daily",
    audit_trail=True,
    alert_emails=["compliance@example.com"]
)
```

### 3. Batch Compliance Monitoring

```python
from workflow import batch_compliance_monitoring

check_specs = [
    {"system": "db1", "policies": {"GDPR": "Data protection"}, "data": {}},
    {"system": "db2", "policies": {"HIPAA": "Healthcare privacy"}, "data": {}},
    {"system": "api", "policies": {"SOX": "Financial reporting"}, "data": {}}
]

results = batch_compliance_monitoring(check_specs, config)
print(f"Checked {len(results)} systems")
```

## Configuration

### ComplianceConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "mock" | LLM provider (mock, openai, anthropic) |
| `model` | str | "gpt-3.5-turbo" | Model name |
| `severity_threshold` | str | "medium" | Alert threshold: low, medium, high, critical |
| `schedule` | str | None | Schedule: daily, weekly, monthly |
| `audit_trail` | bool | False | Enable audit trail logging |
| `alert_emails` | List[str] | [] | Email recipients for alerts |

## Use Cases

### 1. GDPR Compliance

Monitor EU data protection compliance with encryption and access logging checks.

### 2. HIPAA Healthcare Privacy

Ensure healthcare data privacy with audit trails and access controls.

### 3. SOX Financial Reporting

Monitor financial reporting compliance with data integrity checks.

### 4. PCI-DSS Payment Security

Verify payment card data security with encryption and tokenization checks.

### 5. Custom Regulatory Compliance

Define custom policies for industry-specific regulations.

## Testing

```bash
# Run all tests
pytest tests/unit/examples/test_compliance_monitoring.py -v

# Run specific test class
pytest tests/unit/examples/test_compliance_monitoring.py::TestComplianceMonitoringAgents -v
```

**Test Coverage**: 17 tests, 100% passing

## Related Examples

- **document-analysis** - Multi-agent document processing
- **data-reporting** - Automated report generation
- **simple-qa** - Basic question answering

## Implementation Notes

- **Phase**: 5E.2 (Enterprise Workflow Examples)
- **Created**: 2025-10-02
- **Tests**: 17/17 passing
- **TDD**: Tests written first, implementation second

## Author

Kaizen Framework Team

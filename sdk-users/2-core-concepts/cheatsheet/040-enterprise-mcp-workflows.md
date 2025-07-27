# Enterprise MCP Workflows - Production-Ready Patterns

**Version**: v0.6.3 | **Quick Access**: Multi-tenant, SSO, compliance, audit workflows

## 🎯 Quick Reference

**When to use**: Enterprise applications requiring multi-tenancy, compliance, SSO authentication, audit trails
**Key nodes**: TenantAssignmentNode, MCPServiceDiscoveryNode, EnterpriseMLCPExecutorNode, EnterpriseAuditLoggerNode
**Authentication**: SSO + MFA flows with audit trails
**Compliance**: HIPAA, SOX, GDPR, PCI-DSS ready

## 🏗️ Enterprise Node Components

### TenantAssignmentNode - Smart Tenant Assignment
```python
from kailash.nodes.enterprise import TenantAssignmentNode

# Intelligent tenant assignment with compliance
workflow.add_node("TenantAssignmentNode", "assign_tenant", {})

# Connect SSO authentication outputs
workflow.add_connection("sso_login", "user_id", "assign_tenant", "user_id")
workflow.add_connection("mfa_challenge", "verified", "assign_tenant", "verified")

# Outputs: tenant, user_context, assignment_timestamp
```

### MCPServiceDiscoveryNode - Compliance-Aware Discovery
```python
from kailash.nodes.enterprise import MCPServiceDiscoveryNode

# Service discovery with compliance filtering
workflow.add_node("MCPServiceDiscoveryNode", "discover_services", {})

# Connect tenant context
workflow.add_connection("assign_tenant", "tenant", "discover_services", "tenant")
workflow.add_connection("assign_tenant", "user_context", "discover_services", "user_context")

# Outputs: discovered_services, service_count, compliance_filters
```

### EnterpriseMLCPExecutorNode - Resilient MCP Execution
```python
from kailash.nodes.enterprise import EnterpriseMLCPExecutorNode

# MCP execution with circuit breakers and audit trails
workflow.add_node("EnterpriseMLCPExecutorNode", "mcp_executor", {
    "circuit_breaker_enabled": True,
    "success_rate_threshold": 0.8
})

# Connect AI agent tool requests
workflow.add_connection("ai_analyst", "response", "mcp_executor", "tool_request")

# Outputs: success, data, execution_time_ms, circuit_state, execution_results
```

### EnterpriseAuditLoggerNode - Comprehensive Compliance Logging
```python
from kailash.nodes.enterprise import EnterpriseAuditLoggerNode

# Full compliance audit logging
workflow.add_node("EnterpriseAuditLoggerNode", "audit_logger", {
    "audit_level": "detailed"  # basic, detailed, full
})

# Connect execution results and user context
workflow.add_connection("mcp_executor", "execution_results", "audit_logger", "execution_results")
workflow.add_connection("assign_tenant", "user_context", "audit_logger", "user_context")

# Outputs: audit_entry, audit_id, compliance_status, risk_assessment
```

## 🏥 Healthcare HIPAA Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.auth import SSOAuthenticationNode, MultiFactorAuthNode
from kailash.nodes.enterprise import (
    TenantAssignmentNode, MCPServiceDiscoveryNode,
    EnterpriseMLCPExecutorNode, EnterpriseAuditLoggerNode
)

# Healthcare compliance workflow
healthcare_workflow = WorkflowBuilder()

# Step 1: SSO Authentication (Azure AD/Okta)
healthcare_workflow.add_node("SSOAuthenticationNode", "sso_login", {
    "providers": {
        "azure_ad": {
            "tenant_id": "healthcare-tenant",
            "client_id": "healthcare-app",
            "scopes": ["User.Read", "Directory.Read.All"]
        }
    }
})

# Step 2: Multi-Factor Authentication
healthcare_workflow.add_node("MultiFactorAuthNode", "mfa_challenge", {
    "methods": ["totp", "push"],
    "session_lifetime": 3600
})

# Step 3: HIPAA-compliant tenant assignment
healthcare_workflow.add_node("TenantAssignmentNode", "assign_tenant", {})

# Step 4: Service discovery with HIPAA filtering
healthcare_workflow.add_node("MCPServiceDiscoveryNode", "discover_services", {})

# Step 5: AI-powered patient analytics
healthcare_workflow.add_node("LLMAgentNode", "patient_analyst", {
    "model": "gpt-4",
    "system_prompt": """You are a HIPAA-compliant healthcare analyst.
    Analyze patient data while maintaining strict privacy controls.
    Only access necessary information and log all activities."""
})

# Step 6: HIPAA-compliant MCP execution
healthcare_workflow.add_node("EnterpriseMLCPExecutorNode", "mcp_executor", {
    "circuit_breaker_enabled": True,
    "success_rate_threshold": 0.9  # Higher threshold for healthcare
})

# Step 7: HIPAA audit logging
healthcare_workflow.add_node("EnterpriseAuditLoggerNode", "audit_logger", {
    "audit_level": "full"  # Full logging for HIPAA compliance
})

# Connect components
healthcare_workflow.add_connection("sso_login", "attributes", "mfa_challenge", "user_data")
healthcare_workflow.add_connection("sso_login", "user_id", "assign_tenant", "user_id")
healthcare_workflow.add_connection("mfa_challenge", "verified", "assign_tenant", "verified")
healthcare_workflow.add_connection("assign_tenant", "tenant", "discover_services", "tenant")
healthcare_workflow.add_connection("assign_tenant", "user_context", "discover_services", "user_context")
healthcare_workflow.add_connection("discover_services", "discovered_services", "patient_analyst", "available_tools")
healthcare_workflow.add_connection("patient_analyst", "response", "mcp_executor", "tool_request")
healthcare_workflow.add_connection("mcp_executor", "execution_results", "audit_logger", "execution_results")
healthcare_workflow.add_connection("assign_tenant", "user_context", "audit_logger", "user_context")

# Execute with HIPAA-compliant parameters
healthcare_wf = healthcare_workflow.build()
results, run_id = await runtime.execute_async(healthcare_wf, parameters={
    "sso_login": {
        "action": "validate",
        "provider": "azure_ad",
        "request_data": {
            "username": "doctor.smith@healthcare.com",
            "token": "azure-ad-token"
        }
    },
    "mfa_challenge": {
        "action": "verify",
        "user_id": "doctor.smith",
        "method": "totp",
        "totp_code": "123456"
    },
    "patient_analyst": {
        "prompt": "Analyze patient satisfaction trends for Q4 while maintaining HIPAA compliance"
    }
})

# Access HIPAA audit trail
audit_entry = results["audit_logger"]["audit_entry"]
print(f"HIPAA Audit ID: {audit_entry['audit_id']}")
print(f"Data Classification: {audit_entry['security']['data_classification']}")
print(f"Compliance Status: {audit_entry['compliance']['data_residency_compliant']}")
```

## 🏦 Finance SOX Workflow

```python
# Finance SOX compliance workflow
finance_workflow = WorkflowBuilder()

# Enhanced authentication for financial data
finance_workflow.add_node("SSOAuthenticationNode", "sso_login", {
    "providers": {
        "okta": {
            "domain": "finance.okta.com",
            "client_id": "finance-client",
            "redirect_uri": "https://finance.app/auth"
        }
    }
})

finance_workflow.add_node("MultiFactorAuthNode", "mfa_challenge", {
    "methods": ["totp", "hardware_key"],  # Hardware keys for finance
    "session_lifetime": 1800,  # Shorter sessions for finance
    "risk_assessment": True
})

# SOX-compliant tenant assignment
finance_workflow.add_node("TenantAssignmentNode", "assign_tenant", {})

# Financial service discovery
finance_workflow.add_node("MCPServiceDiscoveryNode", "discover_services", {})

# SOX-compliant financial analysis
finance_workflow.add_node("LLMAgentNode", "financial_analyst", {
    "model": "gpt-4",
    "system_prompt": """You are a SOX-compliant financial analyst.
    Maintain audit trails for all financial data access.
    Ensure segregation of duties and proper authorization."""
})

# SOX-compliant MCP execution with enhanced circuit breaker
finance_workflow.add_node("EnterpriseMLCPExecutorNode", "mcp_executor", {
    "circuit_breaker_enabled": True,
    "success_rate_threshold": 0.95,  # Very high threshold for finance
})

# SOX audit logging with full detail
finance_workflow.add_node("EnterpriseAuditLoggerNode", "audit_logger", {
    "audit_level": "full"
})

# Connections (same pattern as healthcare)
# ... [connection setup similar to healthcare] ...

# Execute with SOX parameters
results, run_id = await runtime.execute_async(finance_workflow.build(), parameters={
    "sso_login": {
        "action": "validate",
        "provider": "okta",
        "request_data": {
            "username": "analyst.jones@finance.com",
            "token": "okta-token"
        }
    },
    "financial_analyst": {
        "prompt": "Analyze Q4 transaction patterns for SOX compliance reporting"
    }
})
```

## 🌐 Multi-Tenant Isolation

```python
# Multi-tenant workflow with strict isolation
multi_tenant_workflow = WorkflowBuilder()

# Database with tenant isolation
multi_tenant_workflow.add_node("AsyncSQLDatabaseNode", "tenant_db", {
    "connection_string": "postgresql://localhost:5434/multi_tenant_test",
    "query": "SELECT * FROM tenant_data WHERE tenant_id = :tenant_id",
    "isolation_strategy": "strict"
})

# Connect tenant context for data isolation
multi_tenant_workflow.add_connection("assign_tenant", "user_context", "tenant_db", "isolation_context")

# Validate tenant boundaries
tenant_data = results["tenant_db"]["result"]
assert tenant_data["tenant_id"] == expected_tenant_id
```

## 🔒 Advanced Security Patterns

### Circuit Breaker with Custom Thresholds
```python
# Enhanced circuit breaker configuration
workflow.add_node("EnterpriseMLCPExecutorNode", "mcp_executor", {
    "circuit_breaker_enabled": True,
    "success_rate_threshold": 0.8,
    "failure_threshold": 5,  # Open after 5 failures
    "recovery_timeout": 30,  # 30 seconds before retry
    "half_open_max_calls": 3  # Test with 3 calls in half-open
})
```

### Risk-Based Audit Logging
```python
# Risk assessment in audit logging
workflow.add_node("EnterpriseAuditLoggerNode", "audit_logger", {
    "audit_level": "detailed",
    "risk_threshold": 0.7,  # Flag high-risk operations
    "compliance_zones": ["sox", "pci_dss"],
    "alert_on_high_risk": True
})

# Access risk assessment
audit_result = results["audit_logger"]["audit_entry"]
risk_level = audit_result["risk_assessment"]["risk_level"]
if risk_level == "high":
    # Trigger additional security measures
    send_security_alert(audit_result)
```

## 📊 Compliance Reporting

### HIPAA Compliance Report
```python
# Generate HIPAA compliance report
def generate_hipaa_report(audit_entries):
    """Generate HIPAA compliance report from audit entries."""
    report = {
        "report_date": datetime.utcnow().isoformat(),
        "compliance_status": "compliant",
        "total_operations": len(audit_entries),
        "data_classifications": {},
        "access_violations": [],
        "encryption_status": "all_encrypted"
    }

    for entry in audit_entries:
        # Check data classification
        data_class = entry["security"]["data_classification"]
        report["data_classifications"][data_class] = \
            report["data_classifications"].get(data_class, 0) + 1

        # Check for violations
        if not entry["compliance"]["data_residency_compliant"]:
            report["access_violations"].append(entry["audit_id"])

    return report

# Usage
audit_entries = [results[node]["audit_entry"] for node in ["audit_logger"]]
hipaa_report = generate_hipaa_report(audit_entries)
```

## ⚡ Performance Optimization

### Async Enterprise Workflow
```python
from kailash.runtime.local import LocalRuntime

# Use async runtime for better performance
runtime = LocalRuntime()

# Parallel execution where possible
results, run_id = await runtime.execute_async(workflow, parameters={
    # ... parameters
})

# Performance metrics
execution_time = results.get("execution_metadata", {}).get("total_time_ms", 0)
print(f"Enterprise workflow completed in {execution_time}ms")
```

### Connection Optimization
```python
# Optimize parameter connections for better performance
workflow.add_connection("assign_tenant", "tenant", "discover_services", "tenant")
workflow.add_connection("assign_tenant", "user_context", "discover_services", "user_context")

# Use dot notation for nested outputs
workflow.add_connection("mcp_executor", "execution_results", "audit_logger", "execution_results")
```

## 🧪 Testing Enterprise Workflows

```python
import pytest
from tests.utils.docker_config import ensure_docker_services

@pytest.mark.e2e
@pytest.mark.requires_docker
class TestEnterpriseWorkflows:

    async def test_healthcare_hipaa_workflow(self):
        """Test complete HIPAA-compliant healthcare workflow."""
        # Ensure Docker services (PostgreSQL, Redis)
        await ensure_docker_services()

        # Execute workflow
        results, run_id = await runtime.execute_async(healthcare_wf, parameters={
            "sso_login": {
                "action": "validate",
                "provider": "azure_ad",
                "request_data": {
                    "username": "doctor.test@healthcare.com",
                    "token": "test-token"
                }
            }
        })

        # Validate HIPAA compliance
        assert results["assign_tenant"]["tenant"]["id"] == "healthcare-corp"
        assert results["audit_logger"]["compliance_status"] == "compliant"

        # Verify audit trail
        audit_entry = results["audit_logger"]["audit_entry"]
        assert audit_entry["compliance"]["data_residency_compliant"] is True
        assert audit_entry["security"]["data_classification"] == "confidential"
```

## 🚨 Common Patterns

### Error Handling
```python
# Enterprise error handling
try:
    results, run_id = await runtime.execute_async(enterprise_wf, parameters=params)
except RuntimeExecutionError as e:
    if "circuit_breaker" in str(e):
        # Handle circuit breaker failure
        log_circuit_breaker_event(e)
    elif "compliance" in str(e):
        # Handle compliance violation
        alert_compliance_team(e)
    else:
        # General error handling
        log_enterprise_error(e)
```

### Session Management
```python
# Enterprise session management
session_context = {
    "user_id": "user123",
    "tenant_id": "healthcare-corp",
    "session_id": f"session-{int(time.time())}",
    "compliance_zones": ["hipaa", "gdpr"],
    "data_residency": "us-east-1"
}

# Pass session context to audit logger
workflow.add_connection("assign_tenant", "user_context", "audit_logger", "user_context")
```

## 📚 Related Guides

- **[Enterprise Patterns](../enterprise/)** - Advanced enterprise features
- **[Security Configuration](008-security-configuration.md)** - Security setup
- **[Testing Guide](../developer/14-async-testing-framework-guide.md)** - Enterprise testing patterns
- **[Node Selection Guide](../nodes/node-selection-guide.md)** - Choose the right enterprise nodes
- **[Production Deployment](../developer/04-production.md)** - Deploy enterprise workflows

---

**Next**: [Advanced Integration Patterns](038-integration-mastery.md) | **Core**: [README](README.md)

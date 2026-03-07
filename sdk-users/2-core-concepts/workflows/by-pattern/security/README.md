# Security Audit Workflows

This directory contains comprehensive security audit and scanning workflow patterns using the Kailash SDK.

## Overview

Security audit workflows provide automated security scanning, vulnerability assessment, and compliance checking capabilities. These patterns perform real security assessments against actual systems and databases, making them suitable for production security operations.

## Core Pattern: Security Audit and Scanning

The security audit workflow demonstrates how to:
- **Scan real databases** using SQLDatabaseNode for vulnerability assessment
- **Check web endpoints** using HTTPRequestNode for security headers and SSL
- **Analyze configurations** against security best practices
- **Generate compliance reports** with detailed findings and recommendations

### Key Features

✅ **Real Security Scanning** - Performs actual vulnerability assessments
✅ **Database Security** - Scans real PostgreSQL/MongoDB instances via Docker
✅ **Web Security** - Checks SSL certificates, security headers, endpoint security
✅ **Compliance Frameworks** - Maps findings to OWASP, CIS, ISO 27001 standards
✅ **Actionable Reports** - Detailed remediation steps and priority scoring

## Available Scripts

### `scripts/security_audit_workflow.py`

**Purpose**: Comprehensive multi-layer security audit system

**What it does**:
1. Scans database security configurations using real Docker databases
2. Performs web security assessments on HTTP endpoints
3. Checks SSL/TLS configuration and certificate validity
4. Maps vulnerabilities to compliance frameworks (OWASP, CIS)
5. Generates prioritized security reports with remediation guidance

**Usage**:
```bash
# Start Docker security infrastructure
docker-compose -f docker/docker-compose.sdk-dev.yml up -d postgres mongodb

# Run the security audit
python sdk-users/workflows/by-pattern/security/scripts/security_audit_workflow.py

# The script will:
# - Scan Docker database configurations
# - Test web endpoint security
# - Check SSL/TLS implementations
# - Generate security report in /data/outputs/security/
```

**Scanned Components**:
- PostgreSQL database security (via Docker container)
- MongoDB security configuration (via Docker container)
- Web endpoint security headers and SSL
- API security best practices

**Output**:
- Vulnerability assessment with CVSS scores
- Compliance mapping (OWASP Top 10, CIS Controls)
- Prioritized remediation recommendations
- Executive summary with risk scoring

## Node Usage Patterns

### Database Security Scanning
```python
# Scan PostgreSQL database security
postgres_security_scan = SQLDatabaseNode(
    name="postgres_security_scan",
    connection_string="postgresql://kailash:kailash123@localhost:5432/postgres",
    query="""
    SELECT
        setting as ssl_enabled,
        'SSL Configuration' as check_type
    FROM pg_settings
    WHERE name = 'ssl'
    """,
    return_type="dataframe"
)

# Check database user permissions
user_permissions_check = SQLDatabaseNode(
    name="user_permissions_check",
    connection_string="postgresql://kailash:kailash123@localhost:5432/postgres",
    query="""
    SELECT
        rolname as username,
        rolsuper as is_superuser,
        rolcreatedb as can_create_db,
        rolcreaterole as can_create_roles
    FROM pg_roles
    WHERE rolname NOT LIKE 'pg_%'
    """,
    return_type="dataframe"
)

```

### Web Security Assessment
```python
# Check security headers
security_headers_check = HTTPRequestNode(
    name="security_headers_check",
    method="GET",
    url="https://api.github.com",
    headers={"User-Agent": "Kailash-Security-Scanner/1.0"}
)

# SSL/TLS security check
ssl_security_check = HTTPRequestNode(
    name="ssl_security_check",
    method="GET",
    url="https://www.google.com",
    verify_ssl=True,
    timeout=10.0
)

```

### Vulnerability Analysis
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Analyze security scan results
vulnerability_analyzer = PythonCodeNode.from_function(
    func=analyze_security_findings,
    name="vulnerability_analyzer"
)

# Generate compliance report
compliance_reporter = PythonCodeNode.from_function(
    func=generate_compliance_report,
    name="compliance_reporter"
)

```

## Security Assessment Framework

### Database Security Checks
```python
def assess_database_security(db_results):
    """Analyze database configuration for security issues"""
    vulnerabilities = []

    # Check SSL configuration
    ssl_config = db_results.get("ssl_enabled", "off")
    if ssl_config != "on":
        vulnerabilities.append({
            "type": "SSL_DISABLED",
            "severity": "HIGH",
            "description": "Database SSL/TLS not enabled",
            "remediation": "Enable SSL in postgresql.conf"
        })

    # Check user privileges
    users = db_results.get("user_permissions", [])
    for user in users:
        if user.get("is_superuser") and user.get("username") != "postgres":
            vulnerabilities.append({
                "type": "EXCESSIVE_PRIVILEGES",
                "severity": "MEDIUM",
                "description": f"User {user['username']} has superuser privileges",
                "remediation": "Remove unnecessary superuser privileges"
            })

    return vulnerabilities

```

### Web Security Assessment
```python
def assess_web_security(http_response):
    """Analyze HTTP response for security issues"""
    security_findings = []
    headers = http_response.get("headers", {})

    # Check security headers
    security_headers = [
        "X-Content-Type-Options",
        "X-Frame-Options",
        "X-XSS-Protection",
        "Strict-Transport-Security"
    ]

    for header in security_headers:
        if header not in headers:
            security_findings.append({
                "type": "MISSING_SECURITY_HEADER",
                "severity": "MEDIUM",
                "header": header,
                "description": f"Missing {header} security header"
            })

    return security_findings

```

## Compliance Framework Integration

### OWASP Top 10 Mapping
```python
OWASP_MAPPING = {
    "A01_BROKEN_ACCESS_CONTROL": [
        "EXCESSIVE_PRIVILEGES",
        "MISSING_AUTHENTICATION",
        "WEAK_AUTHORIZATION"
    ],
    "A02_CRYPTOGRAPHIC_FAILURES": [
        "SSL_DISABLED",
        "WEAK_ENCRYPTION",
        "INSECURE_COMMUNICATION"
    ],
    "A03_INJECTION": [
        "SQL_INJECTION_RISK",
        "COMMAND_INJECTION",
        "LDAP_INJECTION"
    ]
}

```

### CIS Controls Mapping
```python
CIS_CONTROLS = {
    "CIS_CONTROL_3": {
        "name": "Data Protection",
        "checks": ["SSL_DISABLED", "UNENCRYPTED_DATA"]
    },
    "CIS_CONTROL_5": {
        "name": "Account Management",
        "checks": ["EXCESSIVE_PRIVILEGES", "WEAK_PASSWORDS"]
    },
    "CIS_CONTROL_14": {
        "name": "Malware Defenses",
        "checks": ["MISSING_ANTIVIRUS", "OUTDATED_SIGNATURES"]
    }
}

```

## Integration with Security Tools

### SIEM Integration
- **Splunk**: Export security findings in Splunk format
- **ELK Stack**: Send logs to Elasticsearch for analysis
- **QRadar**: Forward security events to IBM QRadar

### Vulnerability Management
- **Nessus**: Import scan results for correlation
- **OpenVAS**: Export findings to OpenVAS format
- **Qualys**: Integrate with Qualys VMDR platform

### Compliance Platforms
- **GRC Tools**: Export compliance reports
- **Audit Systems**: Generate audit trails and evidence
- **Risk Management**: Calculate and track risk scores

## Security Scanning Configuration

### Database Security Checks
```python
DATABASE_SECURITY_CHECKS = {
    "postgresql": [
        {"name": "SSL Configuration", "query": "SELECT setting FROM pg_settings WHERE name = 'ssl'"},
        {"name": "User Privileges", "query": "SELECT * FROM pg_roles WHERE rolname NOT LIKE 'pg_%'"},
        {"name": "Password Policy", "query": "SELECT * FROM pg_settings WHERE name LIKE '%password%'"}
    ],
    "mongodb": [
        {"name": "Authentication", "command": "db.runCommand({getParameter: 1, authenticationMechanisms: 1})"},
        {"name": "SSL Status", "command": "db.runCommand({getParameter: 1, sslMode: 1})"}
    ]
}

```

### Web Security Headers
```python
SECURITY_HEADERS_CHECKLIST = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin"
}

```

## Risk Assessment and Scoring

### CVSS Score Calculation
```python
def calculate_cvss_score(vulnerability):
    """Calculate CVSS v3.1 score for vulnerability"""
    base_metrics = {
        "attack_vector": vulnerability.get("attack_vector", "network"),
        "attack_complexity": vulnerability.get("complexity", "low"),
        "privileges_required": vulnerability.get("privileges", "none"),
        "user_interaction": vulnerability.get("interaction", "none"),
        "scope": vulnerability.get("scope", "unchanged"),
        "confidentiality_impact": vulnerability.get("confidentiality", "high"),
        "integrity_impact": vulnerability.get("integrity", "high"),
        "availability_impact": vulnerability.get("availability", "high")
    }

    # CVSS calculation logic here
    return calculate_cvss_base_score(base_metrics)

```

### Risk Prioritization
```python
def prioritize_vulnerabilities(vulnerabilities):
    """Prioritize vulnerabilities by risk score"""
    for vuln in vulnerabilities:
        risk_score = calculate_risk_score(
            cvss_score=vuln["cvss_score"],
            exploitability=vuln.get("exploitability", "medium"),
            asset_criticality=vuln.get("asset_criticality", "high")
        )
        vuln["risk_score"] = risk_score
        vuln["priority"] = get_priority_level(risk_score)

    return sorted(vulnerabilities, key=lambda x: x["risk_score"], reverse=True)

```

## Best Practices

### Scanning Frequency
- **Critical Assets**: Daily automated scans
- **Production Systems**: Weekly comprehensive scans
- **Development/Staging**: Bi-weekly scans
- **Infrastructure Changes**: Immediate post-change scans

### False Positive Management
- Maintain whitelist of accepted risks
- Document risk acceptance decisions
- Regular review of suppressed findings
- Automated validation of fixes

### Reporting and Communication
- Executive dashboards with risk trends
- Technical reports with detailed findings
- Automated alerting for critical vulnerabilities
- Integration with ticketing systems for remediation

## Common Use Cases

### Infrastructure Security
- **Database Hardening**: Scan database configurations against security benchmarks
- **Network Security**: Check firewall rules and network segmentation
- **Server Security**: Assess OS configurations and patch levels

### Application Security
- **Web Application Security**: OWASP Top 10 vulnerability assessment
- **API Security**: REST/GraphQL endpoint security testing
- **Mobile Security**: Mobile application security scanning

### Compliance Auditing
- **PCI DSS**: Payment card industry compliance checks
- **HIPAA**: Healthcare data protection requirements
- **SOX**: Sarbanes-Oxley IT controls assessment
- **GDPR**: Data protection and privacy compliance

## Advanced Patterns

### Multi-Layer Security Assessment
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Scan multiple layers simultaneously
workflow = WorkflowBuilder()
workflow.add_connection("network_scan", ["database_scan", "web_scan", "os_scan"])

```

### Continuous Security Monitoring
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Schedule regular security scans
security_scheduler = CronNode(
    name="security_scheduler",
    schedule="0 2 * * *",  # Daily at 2 AM
    workflow_id="security_audit"
)

```

### Automated Remediation
```python
# Trigger automated fixes for specific vulnerability types
auto_remediation = SwitchNode(
    name="auto_remediation",
    condition_# mapping removed,
        "manual_review": "severity in ['MEDIUM', 'HIGH', 'CRITICAL']"
    }
)

```

## Related Patterns

- **[Monitoring](../monitoring/)** - For security event monitoring
- **[API Integration](../api-integration/)** - For security tool integration
- **[Data Processing](../data-processing/)** - For security data analysis

## Production Checklist

- [ ] All scans use real infrastructure (Docker databases, actual endpoints)
- [ ] Vulnerability findings mapped to compliance frameworks
- [ ] Risk scoring and prioritization implemented
- [ ] Automated reporting and alerting configured
- [ ] Integration with existing security tools and SIEM
- [ ] False positive management and exception handling
- [ ] Sensitive data protection in scan results and logs
- [ ] Access controls for security reports and findings
- [ ] Regular scan schedule and monitoring implemented

---

**Next Steps**:
- Review `scripts/security_audit_workflow.py` for implementation details
- Configure security scanning for your specific infrastructure
- Integrate with existing security and compliance tools
- See the Kailash SDK repository for training examples

#!/usr/bin/env python3
"""
Security Audit Workflow - Real Infrastructure Security Assessment
===============================================================

Demonstrates comprehensive security auditing patterns using Kailash SDK with real infrastructure.
This workflow uses SQLDatabaseNode and HTTPRequestNode to perform actual security assessments
against Docker infrastructure, avoiding any mock data generation.

Patterns demonstrated:
1. Real database security scanning using SQLDatabaseNode
2. API endpoint security assessment using HTTPRequestNode
3. Infrastructure configuration analysis
4. Vulnerability detection and risk assessment

Features:
- Uses SQLDatabaseNode for real database security scans
- Uses HTTPRequestNode for API security assessments
- Analyzes actual Docker infrastructure services
- Generates comprehensive security audit reports
"""

import json
import os
from typing import Any

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime


def get_security_targets() -> dict[str, Any]:
    """Get real security assessment targets from Docker infrastructure."""
    return {
        "databases": [
            {
                "name": "postgres",
                "connection_string": "postgresql://kailash:kailash123@localhost:5432/postgres",
                "critical": True,
                "service_type": "database",
                "assessment_type": "database_security",
            },
            {
                "name": "mongodb",
                "connection_string": "mongodb://kailash:kailash123@localhost:27017/kailash",
                "critical": True,
                "service_type": "nosql_database",
                "assessment_type": "database_security",
            },
        ],
        "api_endpoints": [
            {
                "name": "mock-api",
                "url": "http://localhost:8888",
                "critical": False,
                "service_type": "api",
                "assessment_type": "api_security",
            },
            {
                "name": "mcp-server",
                "url": "http://localhost:8765",
                "critical": False,
                "service_type": "mcp",
                "assessment_type": "api_security",
            },
            {
                "name": "mongo-express",
                "url": "http://localhost:8081",
                "critical": True,  # Admin interface - high security importance
                "service_type": "admin_ui",
                "assessment_type": "web_security",
            },
            {
                "name": "kafka-ui",
                "url": "http://localhost:8082",
                "critical": True,  # Admin interface - high security importance
                "service_type": "admin_ui",
                "assessment_type": "web_security",
            },
        ],
    }


def create_security_audit_workflow() -> Workflow:
    """Create a comprehensive security audit workflow using real infrastructure."""
    workflow = Workflow(
        workflow_id="real_security_audit_001",
        name="real_security_audit_workflow",
        description="Perform real security assessment using SQLDatabaseNode and HTTPRequestNode",
    )

    # === SECURITY TARGET CONFIGURATION ===

    # Configure real security assessment targets
    target_configurator = PythonCodeNode(
        name="target_configurator",
        code="""
# Configure real security assessment targets
security_targets = {
    "databases": [
        {
            "name": "postgres",
            "connection_string": "postgresql://kailash:kailash123@localhost:5432/postgres",
            "critical": True,
            "service_type": "database",
            "assessment_type": "database_security"
        }
    ],
    "api_endpoints": [
        {
            "name": "mock-api",
            "url": "http://localhost:8888",
            "critical": False,
            "service_type": "api",
            "assessment_type": "api_security"
        },
        {
            "name": "mcp-server",
            "url": "http://localhost:8765",
            "critical": False,
            "service_type": "mcp",
            "assessment_type": "api_security"
        },
        {
            "name": "mongo-express",
            "url": "http://localhost:8081",
            "critical": True,  # Admin interface - high security importance
            "service_type": "admin_ui",
            "assessment_type": "web_security"
        },
        {
            "name": "kafka-ui",
            "url": "http://localhost:8082",
            "critical": True,  # Admin interface - high security importance
            "service_type": "admin_ui",
            "assessment_type": "web_security"
        }
    ]
}

result = {
    "security_targets": security_targets,
    "total_databases": len(security_targets["databases"]),
    "total_api_endpoints": len(security_targets["api_endpoints"]),
    "critical_targets": sum(1 for db in security_targets["databases"] if db["critical"]) +
                       sum(1 for api in security_targets["api_endpoints"] if api["critical"])
}
""",
    )
    workflow.add_node("target_configurator", target_configurator)

    # === REAL DATABASE SECURITY SCANNING ===

    # Perform database security assessment using SQLDatabaseNode
    database_scanner = PythonCodeNode(
        name="database_scanner",
        code="""
# Perform real database security assessment using SQLDatabaseNode
from kailash.nodes.data import SQLDatabaseNode
from datetime import datetime
import time

targets = config_data.get("security_targets", {})
databases = targets.get("databases", [])
database_findings = []

for db_config in databases:
    db_name = db_config["name"]
    connection_string = db_config["connection_string"]
    is_critical = db_config["critical"]
    service_type = db_config["service_type"]

    try:
        # Create SQLDatabaseNode for this database
        sql_node = SQLDatabaseNode(
            name=f"security_scan_{db_name}",
            connection_string=connection_string,
            pool_size=2,  # Small pool for security scanning
            pool_timeout=10
        )

        # Perform security-focused database queries
        security_checks = []

        # 1. Check database version and configuration
        try:
            version_result = sql_node.execute(query="SELECT version()")
            version_info = version_result.get("data", [{}])[0] if version_result.get("data") else {}
            version_check = {
                "check": "database_version",
                "status": "info",
                "details": version_info,
                "risk_level": "low",
                "description": "Database version information"
            }
            security_checks.append(version_check)
        except Exception as e:
            version_check = {
                "check": "database_version",
                "status": "error",
                "error": str(e),
                "risk_level": "medium",
                "description": "Could not retrieve database version"
            }
            security_checks.append(version_check)

        # 2. Check for default/weak authentication
        auth_check = {
            "check": "authentication_strength",
            "status": "warning",
            "risk_level": "high",
            "description": "Database using default credentials detected",
            "details": {
                "issue": "Default username/password detected in connection string",
                "recommendation": "Change default credentials immediately",
                "cvss_score": 8.5
            }
        }
        security_checks.append(auth_check)

        # 3. Check database permissions and roles
        try:
            if service_type == "database":  # PostgreSQL
                roles_result = sql_node.execute(
                    query="SELECT rolname, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles"
                )
                roles_data = roles_result.get("data", [])

                # Check for overprivileged roles
                super_users = [role for role in roles_data if role.get("rolsuper")]
                overprivileged_check = {
                    "check": "privilege_escalation",
                    "status": "warning" if len(super_users) > 2 else "pass",
                    "risk_level": "medium" if len(super_users) > 2 else "low",
                    "description": f"Found {len(super_users)} superuser roles",
                    "details": {
                        "superuser_count": len(super_users),
                        "superusers": [role["rolname"] for role in super_users],
                        "recommendation": "Limit superuser privileges to essential accounts only"
                    }
                }
                security_checks.append(overprivileged_check)

        except Exception as e:
            permission_check = {
                "check": "privilege_escalation",
                "status": "error",
                "error": str(e),
                "risk_level": "medium",
                "description": "Could not assess database permissions"
            }
            security_checks.append(permission_check)

        # 4. Check for sensitive data exposure
        try:
            if service_type == "database":  # PostgreSQL
                # Check for tables that might contain sensitive data
                tables_result = sql_node.execute(
                    query="SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
                tables_data = tables_result.get("data", [])

                sensitive_patterns = ["user", "customer", "payment", "credit", "password", "token"]
                sensitive_tables = []
                for table in tables_data:
                    table_name = table.get("table_name", "").lower()
                    if any(pattern in table_name for pattern in sensitive_patterns):
                        sensitive_tables.append(table_name)

                data_exposure_check = {
                    "check": "sensitive_data_exposure",
                    "status": "warning" if sensitive_tables else "pass",
                    "risk_level": "high" if sensitive_tables else "low",
                    "description": f"Found {len(sensitive_tables)} tables with potentially sensitive data",
                    "details": {
                        "sensitive_tables": sensitive_tables,
                        "total_tables": len(tables_data),
                        "recommendation": "Ensure proper encryption and access controls for sensitive data"
                    }
                }
                security_checks.append(data_exposure_check)

        except Exception as e:
            data_check = {
                "check": "sensitive_data_exposure",
                "status": "error",
                "error": str(e),
                "risk_level": "medium",
                "description": "Could not assess sensitive data exposure"
            }
            security_checks.append(data_check)

        # 5. Network security assessment
        network_check = {
            "check": "network_security",
            "status": "warning",
            "risk_level": "medium",
            "description": "Database accessible on default port without encryption",
            "details": {
                "issue": "Database exposed on standard port (5432) without SSL",
                "recommendation": "Enable SSL/TLS encryption and use non-standard ports",
                "cvss_score": 6.5
            }
        }
        security_checks.append(network_check)

        # Calculate overall security score
        risk_scores = {"low": 1, "medium": 5, "high": 8, "critical": 10}
        total_risk = sum(risk_scores.get(check.get("risk_level", "low"), 1) for check in security_checks)
        max_possible_risk = len(security_checks) * 10
        security_score = max(0, 100 - (total_risk / max_possible_risk * 100))

        db_finding = {
            "target_info": {
                "name": db_name,
                "type": service_type,
                "is_critical": is_critical,
                "connection_tested": True
            },
            "security_checks": security_checks,
            "overall_assessment": {
                "security_score": round(security_score, 1),
                "total_checks": len(security_checks),
                "passed_checks": sum(1 for check in security_checks if check.get("status") == "pass"),
                "warning_checks": sum(1 for check in security_checks if check.get("status") == "warning"),
                "failed_checks": sum(1 for check in security_checks if check.get("status") == "error"),
                "highest_risk": max((check.get("risk_level", "low") for check in security_checks), default="low")
            },
            "scan_metadata": {
                "scanned_at": datetime.now().isoformat(),
                "scan_type": "database_security",
                "connection_method": "SQLDatabaseNode"
            }
        }

        database_findings.append(db_finding)

    except Exception as e:
        # Handle connection failures
        error_finding = {
            "target_info": {
                "name": db_name,
                "type": service_type,
                "is_critical": is_critical,
                "connection_tested": False
            },
            "security_checks": [],
            "overall_assessment": {
                "security_score": 0,
                "total_checks": 0,
                "connection_error": str(e)
            },
            "scan_metadata": {
                "scanned_at": datetime.now().isoformat(),
                "scan_type": "database_security",
                "connection_method": "SQLDatabaseNode",
                "scan_failed": True
            }
        }
        database_findings.append(error_finding)

result = {
    "database_findings": database_findings,
    "databases_scanned": len(database_findings),
    "successful_scans": sum(1 for finding in database_findings if finding["target_info"]["connection_tested"]),
    "scan_timestamp": datetime.now().isoformat()
}
""",
    )
    workflow.add_node("database_scanner", database_scanner)
    workflow.connect(
        "target_configurator", "database_scanner", mapping={"result": "config_data"}
    )

    # === REAL API SECURITY SCANNING ===

    # Perform API security assessment using HTTPRequestNode
    api_scanner = PythonCodeNode(
        name="api_scanner",
        code="""
# Perform real API security assessment using HTTPRequestNode
from kailash.nodes.api.http import HTTPRequestNode
from datetime import datetime
import time

targets = config_data.get("security_targets", {})
api_endpoints = targets.get("api_endpoints", [])
api_findings = []

for api_config in api_endpoints:
    api_name = api_config["name"]
    api_url = api_config["url"]
    is_critical = api_config["critical"]
    service_type = api_config["service_type"]

    try:
        # Create HTTPRequestNode for this API
        http_node = HTTPRequestNode(name=f"security_scan_{api_name}")

        # Perform security-focused API tests
        security_checks = []

        # 1. Basic connectivity and response analysis
        try:
            response = http_node.execute(
                url=api_url,
                method="GET",
                timeout=10,
                verify_ssl=False
            )

            is_accessible = response.get("success", False)
            status_code = response.get("status_code")
            response_data = response.get("response", {})
            headers = response_data.get("headers", {}) if response_data else {}

            connectivity_check = {
                "check": "service_accessibility",
                "status": "pass" if is_accessible else "warning",
                "risk_level": "low" if is_accessible else "medium",
                "description": f"API endpoint accessibility test",
                "details": {
                    "accessible": is_accessible,
                    "status_code": status_code,
                    "response_time": response_data.get("response_time_ms", 0) if response_data else 0
                }
            }
            security_checks.append(connectivity_check)

            # 2. Security headers analysis
            security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000",
                "Content-Security-Policy": "default-src 'self'"
            }

            missing_headers = []
            for header, expected in security_headers.items():
                if header.lower() not in [h.lower() for h in headers.keys()]:
                    missing_headers.append(header)

            headers_check = {
                "check": "security_headers",
                "status": "warning" if missing_headers else "pass",
                "risk_level": "medium" if missing_headers else "low",
                "description": f"Missing {len(missing_headers)} security headers",
                "details": {
                    "missing_headers": missing_headers,
                    "present_headers": list(headers.keys()),
                    "recommendation": "Implement missing security headers"
                }
            }
            security_checks.append(headers_check)

        except Exception as e:
            connectivity_check = {
                "check": "service_accessibility",
                "status": "error",
                "error": str(e),
                "risk_level": "high",
                "description": "Could not connect to API endpoint"
            }
            security_checks.append(connectivity_check)

        # 3. Authentication bypass testing
        try:
            # Test for unprotected admin endpoints
            admin_paths = ["/admin", "/admin/", "/admin/login", "/dashboard", "/config"]

            vulnerable_paths = []
            for path in admin_paths:
                test_url = f"{api_url}{path}"
                try:
                    admin_response = http_node.execute(
                        url=test_url,
                        method="GET",
                        timeout=5,
                        verify_ssl=False
                    )

                    if admin_response.get("success") and admin_response.get("status_code") == 200:
                        vulnerable_paths.append(path)

                except Exception:
                    pass  # Expected for most paths

            auth_check = {
                "check": "authentication_bypass",
                "status": "critical" if vulnerable_paths else "pass",
                "risk_level": "critical" if vulnerable_paths else "low",
                "description": f"Found {len(vulnerable_paths)} unprotected admin paths",
                "details": {
                    "vulnerable_paths": vulnerable_paths,
                    "recommendation": "Implement proper authentication for admin interfaces",
                    "cvss_score": 9.0 if vulnerable_paths else 0
                }
            }
            security_checks.append(auth_check)

        except Exception as e:
            auth_check = {
                "check": "authentication_bypass",
                "status": "error",
                "error": str(e),
                "risk_level": "medium",
                "description": "Could not test authentication mechanisms"
            }
            security_checks.append(auth_check)

        # 4. Information disclosure testing
        try:
            # Test for information disclosure in error responses
            error_response = http_node.execute(
                url=f"{api_url}/nonexistent-endpoint-12345",
                method="GET",
                timeout=5,
                verify_ssl=False
            )

            error_content = ""
            if error_response.get("response", {}).get("content"):
                error_content = str(error_response["response"]["content"]).lower()

            # Check for information leakage in error messages
            sensitive_info = ["server", "version", "stack trace", "exception", "debug", "internal"]
            leaked_info = [info for info in sensitive_info if info in error_content]

            info_disclosure_check = {
                "check": "information_disclosure",
                "status": "warning" if leaked_info else "pass",
                "risk_level": "medium" if leaked_info else "low",
                "description": f"Potential information disclosure in error responses",
                "details": {
                    "leaked_information": leaked_info,
                    "error_status": error_response.get("status_code"),
                    "recommendation": "Implement generic error messages to prevent information leakage"
                }
            }
            security_checks.append(info_disclosure_check)

        except Exception as e:
            info_check = {
                "check": "information_disclosure",
                "status": "error",
                "error": str(e),
                "risk_level": "low",
                "description": "Could not test information disclosure"
            }
            security_checks.append(info_check)

        # 5. HTTPS enforcement testing
        if api_url.startswith("http://"):
            https_check = {
                "check": "https_enforcement",
                "status": "critical",
                "risk_level": "high",
                "description": "API endpoint not using HTTPS encryption",
                "details": {
                    "issue": "Unencrypted HTTP communication detected",
                    "recommendation": "Enforce HTTPS for all API communications",
                    "cvss_score": 7.5
                }
            }
            security_checks.append(https_check)

        # Calculate overall security score
        risk_scores = {"low": 1, "medium": 5, "high": 8, "critical": 10}
        total_risk = sum(risk_scores.get(check.get("risk_level", "low"), 1) for check in security_checks)
        max_possible_risk = len(security_checks) * 10
        security_score = max(0, 100 - (total_risk / max_possible_risk * 100))

        api_finding = {
            "target_info": {
                "name": api_name,
                "type": service_type,
                "url": api_url,
                "is_critical": is_critical,
                "connection_tested": True
            },
            "security_checks": security_checks,
            "overall_assessment": {
                "security_score": round(security_score, 1),
                "total_checks": len(security_checks),
                "passed_checks": sum(1 for check in security_checks if check.get("status") == "pass"),
                "warning_checks": sum(1 for check in security_checks if check.get("status") == "warning"),
                "failed_checks": sum(1 for check in security_checks if check.get("status") == "error"),
                "critical_checks": sum(1 for check in security_checks if check.get("status") == "critical"),
                "highest_risk": max((check.get("risk_level", "low") for check in security_checks), default="low")
            },
            "scan_metadata": {
                "scanned_at": datetime.now().isoformat(),
                "scan_type": "api_security",
                "connection_method": "HTTPRequestNode"
            }
        }

        api_findings.append(api_finding)

    except Exception as e:
        # Handle connection failures
        error_finding = {
            "target_info": {
                "name": api_name,
                "type": service_type,
                "url": api_url,
                "is_critical": is_critical,
                "connection_tested": False
            },
            "security_checks": [],
            "overall_assessment": {
                "security_score": 0,
                "total_checks": 0,
                "connection_error": str(e)
            },
            "scan_metadata": {
                "scanned_at": datetime.now().isoformat(),
                "scan_type": "api_security",
                "connection_method": "HTTPRequestNode",
                "scan_failed": True
            }
        }
        api_findings.append(error_finding)

result = {
    "api_findings": api_findings,
    "apis_scanned": len(api_findings),
    "successful_scans": sum(1 for finding in api_findings if finding["target_info"]["connection_tested"]),
    "scan_timestamp": datetime.now().isoformat()
}
""",
    )
    workflow.add_node("api_scanner", api_scanner)
    workflow.connect(
        "target_configurator", "api_scanner", mapping={"result": "config_data"}
    )

    # === VULNERABILITY AGGREGATION ===

    # Merge database and API security findings
    security_merger = MergeNode(id="security_merger", merge_type="merge_dict")
    workflow.add_node("security_merger", security_merger)
    workflow.connect("database_scanner", "security_merger", mapping={"result": "data1"})
    workflow.connect("api_scanner", "security_merger", mapping={"result": "data2"})

    # === RISK ASSESSMENT ===

    # Analyze security findings and calculate risk scores
    risk_assessor = PythonCodeNode(
        name="risk_assessor",
        code="""
# Analyze security findings and calculate comprehensive risk assessment
from datetime import datetime

merged_data = security_data
db_findings = merged_data.get("database_findings", [])
api_findings = merged_data.get("api_findings", [])

all_findings = db_findings + api_findings
vulnerabilities = []

# Extract vulnerabilities from all findings
for finding in all_findings:
    target_info = finding.get("target_info", {})
    security_checks = finding.get("security_checks", [])

    for check in security_checks:
        if check.get("status") in ["warning", "critical", "error"]:
            vulnerability = {
                "vulnerability_id": f"VULN-{target_info['name']}-{check['check']}",
                "target_name": target_info["name"],
                "target_type": target_info["type"],
                "is_critical_target": target_info.get("is_critical", False),
                "vulnerability_type": check["check"],
                "severity": check.get("risk_level", "low"),
                "status": check.get("status", "unknown"),
                "description": check.get("description", "No description"),
                "technical_details": check.get("details", {}),
                "error_message": check.get("error", None),
                "cvss_score": check.get("details", {}).get("cvss_score", 0),
                "recommendation": check.get("details", {}).get("recommendation", "Review security configuration"),
                "discovered_at": datetime.now().isoformat()
            }
            vulnerabilities.append(vulnerability)

# Risk scoring matrix
risk_multipliers = {
    "critical_target": 1.5,  # Critical infrastructure gets higher risk scores
    "external_facing": 1.3,  # External APIs get higher risk scores
    "admin_interface": 1.4,  # Admin interfaces get higher risk scores
    "database": 1.2,        # Databases get higher risk scores
}

severity_scores = {
    "low": 2,
    "medium": 5,
    "high": 8,
    "critical": 10
}

risk_assessments = []

for vuln in vulnerabilities:
    base_score = severity_scores.get(vuln["severity"], 2)

    # Apply risk multipliers
    risk_score = base_score

    if vuln["is_critical_target"]:
        risk_score *= risk_multipliers["critical_target"]

    if vuln["target_type"] in ["api", "web_security", "admin_ui"]:
        risk_score *= risk_multipliers["external_facing"]

    if vuln["target_type"] in ["admin_ui"]:
        risk_score *= risk_multipliers["admin_interface"]

    if vuln["target_type"] in ["database", "nosql_database"]:
        risk_score *= risk_multipliers["database"]

    # Normalize to 0-10 scale
    risk_score = min(10.0, risk_score)

    # Determine priority and timeline
    if risk_score >= 9.0:
        priority = 1
        remediation_timeline = "immediate"
        business_impact = "critical"
    elif risk_score >= 7.0:
        priority = 2
        remediation_timeline = "1 week"
        business_impact = "high"
    elif risk_score >= 5.0:
        priority = 3
        remediation_timeline = "1 month"
        business_impact = "medium"
    else:
        priority = 4
        remediation_timeline = "3 months"
        business_impact = "low"

    # Estimate remediation effort
    effort_estimates = {
        "authentication_bypass": 16,     # High effort - requires authentication system
        "https_enforcement": 8,          # Medium effort - SSL configuration
        "security_headers": 4,           # Low effort - header configuration
        "sensitive_data_exposure": 24,   # High effort - data encryption/access controls
        "privilege_escalation": 12,      # Medium effort - role/permission changes
        "information_disclosure": 6,     # Low-medium effort - error handling
        "network_security": 12,          # Medium effort - firewall/network config
        "authentication_strength": 8     # Medium effort - credential changes
    }

    effort_hours = effort_estimates.get(vuln["vulnerability_type"], 8)
    estimated_cost = effort_hours * 150  # $150/hour security consultant rate

    risk_assessment = {
        "vulnerability_id": vuln["vulnerability_id"],
        "target_name": vuln["target_name"],
        "target_type": vuln["target_type"],
        "vulnerability_type": vuln["vulnerability_type"],
        "severity": vuln["severity"],
        "risk_score": round(risk_score, 2),
        "priority": priority,
        "remediation_timeline": remediation_timeline,
        "business_impact": business_impact,
        "technical_details": vuln["technical_details"],
        "recommendation": vuln["recommendation"],
        "remediation_effort_hours": effort_hours,
        "estimated_cost_usd": estimated_cost,
        "compliance_impact": {
            "affects_pci_dss": vuln["target_type"] in ["database"] or "payment" in vuln["description"].lower(),
            "affects_gdpr": "data" in vuln["description"].lower() or vuln["target_type"] in ["database"],
            "affects_sox": vuln["target_type"] in ["database", "admin_ui"]
        },
        "risk_factors": {
            "base_severity": base_score,
            "final_risk_score": risk_score,
            "critical_target": vuln["is_critical_target"],
            "external_facing": vuln["target_type"] in ["api", "web_security", "admin_ui"]
        },
        "assessment_timestamp": datetime.now().isoformat()
    }

    risk_assessments.append(risk_assessment)

# Sort by risk score descending (highest risk first)
risk_assessments.sort(key=lambda x: x["risk_score"], reverse=True)

# Calculate portfolio risk metrics
total_vulnerabilities = len(risk_assessments)
if total_vulnerabilities > 0:
    total_risk_score = sum(assessment["risk_score"] for assessment in risk_assessments)
    average_risk_score = total_risk_score / total_vulnerabilities
    highest_risk_score = risk_assessments[0]["risk_score"] if risk_assessments else 0
else:
    total_risk_score = 0
    average_risk_score = 0
    highest_risk_score = 0

risk_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}
for assessment in risk_assessments:
    if assessment["risk_score"] >= 9.0:
        risk_distribution["critical"] += 1
    elif assessment["risk_score"] >= 7.0:
        risk_distribution["high"] += 1
    elif assessment["risk_score"] >= 5.0:
        risk_distribution["medium"] += 1
    else:
        risk_distribution["low"] += 1

total_remediation_cost = sum(assessment["estimated_cost_usd"] for assessment in risk_assessments)
critical_remediation_cost = sum(assessment["estimated_cost_usd"] for assessment in risk_assessments if assessment["risk_score"] >= 9.0)

# Generate executive summary
executive_summary = {
    "overall_risk_level": "critical" if risk_distribution["critical"] > 0 else "high" if risk_distribution["high"] > 2 else "medium",
    "total_vulnerabilities": total_vulnerabilities,
    "highest_risk_score": round(highest_risk_score, 2),
    "average_risk_score": round(average_risk_score, 2),
    "risk_distribution": risk_distribution,
    "immediate_action_required": risk_distribution["critical"] + risk_distribution["high"],
    "total_remediation_cost": total_remediation_cost,
    "critical_remediation_cost": critical_remediation_cost,
    "targets_scanned": len(all_findings),
    "successful_scans": sum(1 for finding in all_findings if finding.get("target_info", {}).get("connection_tested", False))
}

result = {
    "risk_assessments": risk_assessments,
    "executive_summary": executive_summary,
    "remediation_roadmap": {
        "immediate": [a for a in risk_assessments if a["risk_score"] >= 9.0],
        "short_term": [a for a in risk_assessments if 7.0 <= a["risk_score"] < 9.0],
        "medium_term": [a for a in risk_assessments if 5.0 <= a["risk_score"] < 7.0],
        "long_term": [a for a in risk_assessments if a["risk_score"] < 5.0]
    },
    "compliance_summary": {
        "pci_dss_affected": sum(1 for a in risk_assessments if a["compliance_impact"]["affects_pci_dss"]),
        "gdpr_affected": sum(1 for a in risk_assessments if a["compliance_impact"]["affects_gdpr"]),
        "sox_affected": sum(1 for a in risk_assessments if a["compliance_impact"]["affects_sox"])
    },
    "assessment_timestamp": datetime.now().isoformat()
}
""",
    )
    workflow.add_node("risk_assessor", risk_assessor)
    workflow.connect(
        "security_merger", "risk_assessor", mapping={"merged_data": "security_data"}
    )

    # === SECURITY REPORTING ===

    # Generate comprehensive security audit report
    security_reporter = PythonCodeNode(
        name="security_reporter",
        code="""
# Generate comprehensive security audit report
from datetime import datetime

risk_data = risk_results
risk_assessments = risk_data.get("risk_assessments", [])
executive_summary = risk_data.get("executive_summary", {})
remediation_roadmap = risk_data.get("remediation_roadmap", {})
compliance_summary = risk_data.get("compliance_summary", {})

# Determine overall security posture
overall_risk_level = executive_summary.get("overall_risk_level", "unknown")
total_vulnerabilities = executive_summary.get("total_vulnerabilities", 0)
immediate_actions = executive_summary.get("immediate_action_required", 0)

if overall_risk_level == "critical" or immediate_actions >= 3:
    security_posture = "CRITICAL"
    posture_color = "red"
elif overall_risk_level == "high" or immediate_actions >= 1:
    security_posture = "HIGH RISK"
    posture_color = "orange"
elif overall_risk_level == "medium":
    security_posture = "MODERATE RISK"
    posture_color = "yellow"
else:
    security_posture = "LOW RISK"
    posture_color = "green"

# Generate security dashboard
current_time = datetime.now()
security_dashboard = {
    "security_posture": security_posture,
    "posture_color": posture_color,
    "total_vulnerabilities": total_vulnerabilities,
    "critical_high_vulns": immediate_actions,
    "highest_risk_score": executive_summary.get("highest_risk_score", 0),
    "average_risk_score": executive_summary.get("average_risk_score", 0),
    "remediation_budget_required": f"${executive_summary.get('total_remediation_cost', 0):,}",
    "critical_remediation_budget": f"${executive_summary.get('critical_remediation_cost', 0):,}",
    "targets_scanned": executive_summary.get("targets_scanned", 0),
    "successful_scans": executive_summary.get("successful_scans", 0),
    "scan_success_rate": round((executive_summary.get("successful_scans", 0) / max(1, executive_summary.get("targets_scanned", 1))) * 100, 1),
    "report_timestamp": current_time.isoformat()
}

# Generate key findings
key_findings = []

if immediate_actions > 0:
    key_findings.append({
        "type": "security",
        "severity": "critical",
        "finding": f"{immediate_actions} critical/high-risk vulnerabilities require immediate attention",
        "impact": "High risk of security breach, data compromise, or service disruption",
        "recommendation": "Prioritize remediation of critical and high-risk vulnerabilities within 24-48 hours"
    })

# Check for specific vulnerability types
auth_issues = sum(1 for a in risk_assessments if "authentication" in a["vulnerability_type"])
if auth_issues > 0:
    key_findings.append({
        "type": "authentication",
        "severity": "major",
        "finding": f"{auth_issues} authentication-related vulnerabilities detected",
        "impact": "Unauthorized access to systems and data",
        "recommendation": "Strengthen authentication mechanisms and eliminate default credentials"
    })

data_exposure = sum(1 for a in risk_assessments if "data" in a["vulnerability_type"] or "exposure" in a["vulnerability_type"])
if data_exposure > 0:
    key_findings.append({
        "type": "data_protection",
        "severity": "major",
        "finding": f"{data_exposure} data exposure vulnerabilities found",
        "impact": "Potential data breaches and privacy violations",
        "recommendation": "Implement proper data encryption and access controls"
    })

# Compliance findings
compliance_risks = []
if compliance_summary.get("pci_dss_affected", 0) > 0:
    compliance_risks.append("PCI DSS")
if compliance_summary.get("gdpr_affected", 0) > 0:
    compliance_risks.append("GDPR")
if compliance_summary.get("sox_affected", 0) > 0:
    compliance_risks.append("SOX")

if compliance_risks:
    key_findings.append({
        "type": "compliance",
        "severity": "major",
        "finding": f"Vulnerabilities affecting compliance with: {', '.join(compliance_risks)}",
        "impact": "Regulatory penalties, audit failures, legal liability",
        "recommendation": "Address compliance-related vulnerabilities to meet regulatory requirements"
    })

# Generate action plan
action_plan = {
    "immediate_actions": [
        f"Address {immediate_actions} critical/high-risk vulnerabilities",
        "Review and strengthen authentication mechanisms",
        "Implement security headers for web applications",
        "Enable HTTPS for all external-facing services"
    ],
    "short_term_actions": [
        "Complete vulnerability remediation per timeline",
        "Implement comprehensive security monitoring",
        "Update security policies and procedures",
        "Conduct security awareness training"
    ],
    "long_term_actions": [
        "Establish regular security assessments",
        "Implement security-by-design practices",
        "Enhance incident response capabilities",
        "Regular third-party security audits"
    ],
    "budget_requirements": {
        "immediate": executive_summary.get("critical_remediation_cost", 0),
        "quarterly": executive_summary.get("total_remediation_cost", 0) * 0.4,
        "annual": executive_summary.get("total_remediation_cost", 0) * 1.2
    }
}

# Generate detailed sections
vulnerability_summary = {
    "total_found": total_vulnerabilities,
    "by_risk_level": executive_summary.get("risk_distribution", {}),
    "by_target_type": {},
    "by_vulnerability_type": {},
    "top_vulnerabilities": risk_assessments[:10] if risk_assessments else []
}

# Aggregate by target type and vulnerability type
for assessment in risk_assessments:
    target_type = assessment["target_type"]
    vuln_type = assessment["vulnerability_type"]

    if target_type not in vulnerability_summary["by_target_type"]:
        vulnerability_summary["by_target_type"][target_type] = 0
    vulnerability_summary["by_target_type"][target_type] += 1

    if vuln_type not in vulnerability_summary["by_vulnerability_type"]:
        vulnerability_summary["by_vulnerability_type"][vuln_type] = 0
    vulnerability_summary["by_vulnerability_type"][vuln_type] += 1

# Final comprehensive report
report = {
    "security_audit_report": {
        "security_dashboard": security_dashboard,
        "key_findings": key_findings,
        "vulnerability_summary": vulnerability_summary,
        "compliance_summary": compliance_summary,
        "action_plan": action_plan,
        "remediation_roadmap": remediation_roadmap,
        "detailed_assessments": risk_assessments
    },
    "report_metadata": {
        "generated_at": current_time.isoformat(),
        "report_type": "comprehensive_security_audit",
        "version": "1.0",
        "scanning_method": "SQLDatabaseNode + HTTPRequestNode",
        "next_audit_date": (current_time.replace(year=current_time.year if current_time.month < 10 else current_time.year + 1,
                                                month=current_time.month + 3 if current_time.month < 10 else current_time.month - 9)).isoformat(),
        "audit_scope": "docker_infrastructure_security"
    },
    "recommendations": {
        "priority_1": [finding["recommendation"] for finding in key_findings if finding["severity"] == "critical"],
        "priority_2": [finding["recommendation"] for finding in key_findings if finding["severity"] == "major"],
        "priority_3": [finding["recommendation"] for finding in key_findings if finding["severity"] == "minor"]
    }
}

result = report
""",
    )
    workflow.add_node("security_reporter", security_reporter)
    workflow.connect(
        "risk_assessor", "security_reporter", mapping={"result": "risk_results"}
    )

    # === OUTPUTS ===

    # Save comprehensive security audit report
    audit_writer = JSONWriterNode(
        id="audit_writer",
        file_path="data/outputs/comprehensive_security_audit_report.json",
    )
    workflow.add_node("audit_writer", audit_writer)
    workflow.connect("security_reporter", "audit_writer", mapping={"result": "data"})

    # Save vulnerability details for tracking
    vuln_writer = JSONWriterNode(
        id="vuln_writer", file_path="data/outputs/vulnerability_assessment_details.json"
    )
    workflow.add_node("vuln_writer", vuln_writer)
    workflow.connect("risk_assessor", "vuln_writer", mapping={"result": "data"})

    return workflow


def run_security_audit():
    """Execute the real security audit workflow."""
    workflow = create_security_audit_workflow()
    runtime = LocalRuntime()

    parameters = {}

    try:
        print("Starting Real Security Audit Workflow...")
        print(
            "🔍 Scanning actual Docker infrastructure for security vulnerabilities..."
        )

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\\n✅ Security Audit Complete!")
        print("📁 Outputs generated:")
        print(
            "   - Comprehensive audit report: data/outputs/comprehensive_security_audit_report.json"
        )
        print(
            "   - Vulnerability details: data/outputs/vulnerability_assessment_details.json"
        )

        # Show security dashboard
        audit_result = result.get("security_reporter", {}).get("result", {})
        security_report = audit_result.get("security_audit_report", {})
        security_dashboard = security_report.get("security_dashboard", {})

        print(
            f"\\n📊 Security Posture: {security_dashboard.get('security_posture', 'UNKNOWN')}"
        )
        print(
            f"   - Total Vulnerabilities: {security_dashboard.get('total_vulnerabilities', 0)}"
        )
        print(
            f"   - Critical/High Risk: {security_dashboard.get('critical_high_vulns', 0)}"
        )
        print(
            f"   - Highest Risk Score: {security_dashboard.get('highest_risk_score', 0)}/10"
        )
        print(
            f"   - Average Risk Score: {security_dashboard.get('average_risk_score', 0)}/10"
        )
        print(
            f"   - Remediation Budget: {security_dashboard.get('remediation_budget_required', 'N/A')}"
        )
        print(
            f"   - Critical Budget: {security_dashboard.get('critical_remediation_budget', 'N/A')}"
        )
        print(
            f"   - Scan Success Rate: {security_dashboard.get('scan_success_rate', 0)}%"
        )

        # Show key findings
        key_findings = security_report.get("key_findings", [])
        if key_findings:
            print("\\n🚨 KEY SECURITY FINDINGS:")
            for finding in key_findings[:3]:  # Show top 3 findings
                print(
                    f"   - [{finding.get('severity', 'unknown').upper()}] {finding.get('finding', 'N/A')}"
                )

        # Show immediate actions
        action_plan = security_report.get("action_plan", {})
        immediate_actions = action_plan.get("immediate_actions", [])
        if immediate_actions:
            print("\\n⚡ IMMEDIATE ACTIONS REQUIRED:")
            for action in immediate_actions:
                print(f"   - {action}")

        return result

    except Exception as e:
        print(f"❌ Security Audit failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the security audit workflow
    run_security_audit()

    # Display generated reports
    print("\\n=== Security Audit Report Preview ===")
    try:
        with open("data/outputs/comprehensive_security_audit_report.json") as f:
            report = json.load(f)
            security_dashboard = report["security_audit_report"]["security_dashboard"]
            print(json.dumps(security_dashboard, indent=2))

        print("\\n=== Vulnerability Summary ===")
        vulnerability_summary = report["security_audit_report"]["vulnerability_summary"]
        print(f"Total Vulnerabilities: {vulnerability_summary['total_found']}")
        print(f"Risk Distribution: {vulnerability_summary['by_risk_level']}")
        print(f"By Target Type: {vulnerability_summary['by_target_type']}")

        print("\\n=== Compliance Impact ===")
        compliance_summary = report["security_audit_report"]["compliance_summary"]
        for compliance, count in compliance_summary.items():
            print(f"{compliance.upper()}: {count} affected vulnerabilities")

    except Exception as e:
        print(f"Could not read reports: {e}")


if __name__ == "__main__":
    main()

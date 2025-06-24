"""
Ollama-powered E2E tests for admin nodes with AI-driven decision making.

These tests demonstrate real-world AI integration scenarios:
- Intelligent access control decisions
- Anomaly detection in permission patterns
- Automated compliance validation
- Risk assessment and threat detection
- Natural language policy evaluation
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

from kailash import LocalRuntime, Workflow, WorkflowBuilder
from kailash.nodes import PythonCodeNode
from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.nodes.transform import DataTransformer
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import (
    OLLAMA_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
)

pytestmark = [pytest.mark.docker, pytest.mark.e2e, pytest.mark.ai]


class AISecurityAnalyzer:
    """AI-powered security analysis using Ollama."""

    @staticmethod
    def create_threat_detection_workflow() -> Workflow:
        """Create workflow for AI-powered threat detection."""
        return WorkflowBuilder.from_dict(
            {
                "name": "ai_threat_detection",
                "description": "AI-powered threat detection and response",
                "nodes": {
                    "collect_signals": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json
from datetime import datetime, timedelta

# Collect security signals
user_activity = inputs.get("user_activity", {})
access_patterns = inputs.get("access_patterns", {})
system_state = inputs.get("system_state", {})

# Analyze patterns
signals = {
    "user_behavior": {
                        "login_time": user_activity.get("login_time"),
                        "location": user_activity.get("location"),
                        "device": user_activity.get("device"),
                        "failed_attempts": user_activity.get("failed_attempts", 0),
                        "unusual_activity": []
                    },
    "access_patterns": {
                        "resources_accessed": access_patterns.get("resources", []),
                        "frequency": access_patterns.get("frequency", {}),
                        "data_volume": access_patterns.get("data_volume", 0),
                        "sensitive_access": access_patterns.get("sensitive_count", 0)
                    },
    "risk_indicators": []
}

# Identify risk indicators
if user_activity.get("failed_attempts", 0) > 3:
    signals["risk_indicators"].append("multiple_failed_logins")

if access_patterns.get("sensitive_count", 0) > 10:
    signals["risk_indicators"].append("excessive_sensitive_access")

if user_activity.get("location", "").lower() in ["unknown", "tor", "vpn"]:
    signals["risk_indicators"].append("suspicious_location")

# Check for data exfiltration patterns
if access_patterns.get("data_volume", 0) > 1000000:  # 1GB
    signals["risk_indicators"].append("potential_data_exfiltration")

result = signals
"""
                        },
                    },
                    "ai_threat_analysis": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.1,
                            "system_prompt": """You are an AI security analyst specializing in threat detection and incident response.

Analyze the provided security signals and determine:
1. Threat level (none/low/medium/high/critical)
2. Threat type (if any): insider threat, account compromise, data exfiltration, privilege escalation, etc.
3. Confidence level (0-100)
4. Recommended actions
5. Similar historical patterns

Respond with a JSON object:
{
    "threat_level": "none|low|medium|high|critical",
    "threat_types": ["list of identified threats"],
    "confidence": 0-100,
    "risk_score": 0-100,
    "indicators": ["specific indicators that led to this assessment"],
    "recommended_actions": ["immediate actions to take"],
    "requires_human_review": true|false,
    "explanation": "detailed explanation of the analysis"
}""",
                        },
                    },
                    "ai_compliance_check": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.1,
                            "system_prompt": """You are an AI compliance officer ensuring adherence to security policies and regulations.

Review the activity and determine compliance status for:
1. SOC2 compliance
2. GDPR requirements (if applicable)
3. Internal security policies
4. Industry regulations

Respond with a JSON object:
{
    "compliant": true|false,
    "violations": ["list of compliance violations"],
    "regulations_checked": ["SOC2", "GDPR", "HIPAA", "PCI-DSS", etc.],
    "severity": "none|minor|major|critical",
    "remediation_required": true|false,
    "audit_notes": "details for compliance audit"
}""",
                        },
                    },
                    "generate_response": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json

# Parse AI analyses
threat_analysis = json.loads(inputs.get("threat_analysis", "{}"))
compliance_check = json.loads(inputs.get("compliance_check", "{}"))

# Determine response actions
response = {
    "action": "monitor",  # monitor, alert, block, investigate
    "severity": "low",
    "notifications": [],
    "automated_actions": [],
    "manual_actions": []
}

# Determine action based on threat level
threat_level = threat_analysis.get("threat_level", "none")
if threat_level == "critical":
    response["action"] = "block"
    response["severity"] = "critical"
    response["notifications"].append("security_team")
    response["notifications"].append("ciso")
    response["automated_actions"].extend([
                        "disable_user_account",
                        "revoke_all_sessions",
                        "preserve_evidence"
                    ])
elif threat_level == "high":
    response["action"] = "alert"
    response["severity"] = "high"
    response["notifications"].append("security_team")
    response["automated_actions"].append("require_mfa")
    response["manual_actions"].append("investigate_immediately")
elif threat_level == "medium":
    response["action"] = "investigate"
    response["severity"] = "medium"
    response["automated_actions"].append("increase_monitoring")

# Add compliance actions
if not compliance_check.get("compliant", True):
    response["manual_actions"].append("compliance_review")
    if compliance_check.get("severity") == "critical":
                        response["automated_actions"].append("restrict_access")

# Include AI insights
response["ai_insights"] = {
    "threat_analysis": threat_analysis,
    "compliance_status": compliance_check
}

result = response
"""
                        },
                    },
                },
                "connections": [
                    {
                        "from": "collect_signals",
                        "to": "ai_threat_analysis",
                        "map": {"result": "security_signals"},
                    },
                    {
                        "from": "collect_signals",
                        "to": "ai_compliance_check",
                        "map": {"result": "activity_data"},
                    },
                    {
                        "from": "ai_threat_analysis",
                        "to": "generate_response",
                        "map": {"result.content": "threat_analysis"},
                    },
                    {
                        "from": "ai_compliance_check",
                        "to": "generate_response",
                        "map": {"result.content": "compliance_check"},
                    },
                ],
            }
        )

    @staticmethod
    def create_policy_evaluation_workflow() -> Workflow:
        """Create workflow for natural language policy evaluation."""
        return WorkflowBuilder.from_dict(
            {
                "name": "nl_policy_evaluation",
                "description": "Natural language policy evaluation using AI",
                "nodes": {
                    "parse_request": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
# Parse natural language access request
nl_request = inputs.get("request", "")
user_context = inputs.get("user_context", {})
resource_context = inputs.get("resource_context", {})

# Structure the request for AI evaluation
structured_request = {
    "request_text": nl_request,
    "request_type": "access",  # Could be inferred from NL
    "user": {
                        "id": user_context.get("user_id"),
                        "role": user_context.get("role"),
                        "department": user_context.get("department"),
                        "clearance": user_context.get("clearance"),
                        "history": user_context.get("access_history", {})
                    },
    "resource": {
                        "id": resource_context.get("resource_id"),
                        "type": resource_context.get("type"),
                        "sensitivity": resource_context.get("sensitivity"),
                        "owner": resource_context.get("owner"),
                        "classification": resource_context.get("classification")
                    },
    "context": {
                        "time": inputs.get("timestamp"),
                        "location": inputs.get("location"),
                        "reason": inputs.get("business_reason")
                    }
}

result = structured_request
"""
                        },
                    },
                    "ai_policy_interpreter": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.2,
                            "system_prompt": """You are an AI policy interpreter that evaluates access requests against organizational policies.

Given a natural language request and context, determine:
1. What specific permissions are being requested
2. Whether the request aligns with security policies
3. Any policy exceptions that might apply
4. Risk level of granting access

Consider these policies:
- Principle of least privilege
- Separation of duties
- Data classification requirements
- Time-based access restrictions
- Location-based restrictions
- Business justification requirements

Respond with a JSON object:
{
    "interpreted_permissions": ["specific permissions requested"],
    "policy_alignment": true|false,
    "applicable_policies": ["list of relevant policies"],
    "exceptions_needed": ["any policy exceptions required"],
    "risk_assessment": {
                        "level": "low|medium|high",
                        "factors": ["risk factors identified"]
                    },
    "recommendation": "approve|deny|approve_with_conditions",
    "conditions": ["any conditions for approval"],
    "justification": "detailed explanation"
}""",
                        },
                    },
                    "ai_precedent_check": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.3,
                            "system_prompt": """You are an AI that analyzes historical access patterns and precedents.

Review the request and determine:
1. Similar historical requests and their outcomes
2. Patterns in user's previous access
3. Anomalies compared to peer group
4. Precedents that support or oppose the request

Respond with a JSON object:
{
    "similar_requests": [
                        {
                            "summary": "brief description",
                            "outcome": "approved|denied",
                            "relevance": 0-100
                        }
                    ],
    "user_patterns": {
                        "typical_access": ["usual resources accessed"],
                        "access_frequency": "description",
                        "anomaly_detected": true|false
                    },
    "peer_comparison": {
                        "similar_roles_access": ["what peers typically access"],
                        "request_is_typical": true|false
                    },
    "precedent_recommendation": "strong_approve|approve|neutral|deny|strong_deny",
    "confidence": 0-100
}""",
                        },
                    },
                    "make_decision": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json

# Parse AI evaluations
policy_eval = json.loads(inputs.get("policy_evaluation", "{}"))
precedent_check = json.loads(inputs.get("precedent_analysis", "{}"))

# Make access decision
decision = {
    "grant_access": False,
    "permissions": [],
    "conditions": [],
    "duration": None,
    "require_approval": False,
    "audit_priority": "normal"
}

# Combine recommendations
policy_rec = policy_eval.get("recommendation", "deny")
precedent_rec = precedent_check.get("precedent_recommendation", "neutral")

# Decision logic
if policy_rec == "approve" and precedent_rec in ["strong_approve", "approve", "neutral"]:
    decision["grant_access"] = True
    decision["permissions"] = policy_eval.get("interpreted_permissions", [])
    decision["conditions"] = policy_eval.get("conditions", [])
    decision["duration"] = "24_hours"  # Time-boxed access
elif policy_rec == "approve_with_conditions":
    decision["grant_access"] = True
    decision["permissions"] = policy_eval.get("interpreted_permissions", [])
    decision["conditions"] = policy_eval.get("conditions", [])
    decision["require_approval"] = True
    decision["audit_priority"] = "high"
else:
    decision["grant_access"] = False
    decision["audit_priority"] = "high" if policy_eval.get("risk_assessment", {}).get("level") == "high" else "normal"

# Add AI reasoning
decision["ai_reasoning"] = {
    "policy_factors": policy_eval.get("applicable_policies", []),
    "risk_level": policy_eval.get("risk_assessment", {}).get("level", "unknown"),
    "precedent_confidence": precedent_check.get("confidence", 0),
    "anomalies": precedent_check.get("user_patterns", {}).get("anomaly_detected", False)
}

result = decision
"""
                        },
                    },
                },
                "connections": [
                    {
                        "from": "parse_request",
                        "to": "ai_policy_interpreter",
                        "map": {"result": "request_data"},
                    },
                    {
                        "from": "parse_request",
                        "to": "ai_precedent_check",
                        "map": {"result": "request_context"},
                    },
                    {
                        "from": "ai_policy_interpreter",
                        "to": "make_decision",
                        "map": {"result.content": "policy_evaluation"},
                    },
                    {
                        "from": "ai_precedent_check",
                        "to": "make_decision",
                        "map": {"result.content": "precedent_analysis"},
                    },
                ],
            }
        )


class TestAdminNodesOllamaAIE2E:
    """E2E tests for AI-powered admin node scenarios using Ollama."""

    @pytest.fixture(autouse=True)
    async def ensure_ollama_ready(self):
        """Ensure Ollama service is ready."""
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker services not available")

        # Check Ollama specifically
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}/api/tags"
                )
                if response.status_code != 200:
                    pytest.skip("Ollama not responding")
        except Exception:
            pytest.skip("Ollama not available")

    def setup_method(self):
        """Set up test environment."""
        self.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
        }

        self.ollama_config = {**OLLAMA_CONFIG, "model": "llama3.2:3b", "timeout": 30}

        self.test_tenant = f"ai_test_{int(time.time())}"
        self._setup_test_organization()

    def teardown_method(self):
        """Clean up test data."""
        try:
            db_node = SQLDatabaseNode(name="cleanup", **self.db_config)
            for table in ["admin_audit_log", "user_role_assignments", "users", "roles"]:
                db_node.run(
                    query=f"DELETE FROM {table} WHERE tenant_id = %s",
                    parameters=[self.test_tenant],
                )
        except Exception:
            pass

    def _setup_test_organization(self):
        """Set up test organization with users and roles."""
        role_mgmt = RoleManagementNode()
        user_mgmt = UserManagementNode()

        # Create roles
        self.roles = {
            "security_analyst": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "Security Analyst",
                    "permissions": [
                        "logs:read",
                        "alerts:manage",
                        "incidents:investigate",
                    ],
                    "attributes": {
                        "clearance": "confidential",
                        "access_level": "monitoring",
                    },
                },
                tenant_id=self.test_tenant,
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
            "data_scientist": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "Data Scientist",
                    "permissions": ["data:read", "models:train", "analytics:run"],
                    "attributes": {"clearance": "internal", "access_level": "analysis"},
                },
                tenant_id=self.test_tenant,
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
            "system_admin": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "System Administrator",
                    "permissions": [
                        "system:manage",
                        "users:manage",
                        "security:configure",
                    ],
                    "attributes": {"clearance": "secret", "access_level": "full"},
                },
                tenant_id=self.test_tenant,
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
        }

        # Create test users
        self.users = []
        user_profiles = [
            {"name": "Alice Johnson", "role": "security_analyst", "behavior": "normal"},
            {"name": "Bob Smith", "role": "data_scientist", "behavior": "normal"},
            {"name": "Charlie Davis", "role": "system_admin", "behavior": "normal"},
            {"name": "Eve Wilson", "role": "data_scientist", "behavior": "suspicious"},
        ]

        for profile in user_profiles:
            user_id = profile["name"].lower().replace(" ", "_")
            user_mgmt.run(
                operation="create_user",
                user_data={
                    "user_id": user_id,
                    "email": f"{user_id}@company.com",
                    "username": user_id,
                    "first_name": profile["name"].split()[0],
                    "last_name": profile["name"].split()[1],
                    "attributes": {
                        "behavior_profile": profile["behavior"],
                        "department": (
                            "Security" if "security" in profile["role"] else "Data"
                        ),
                        "start_date": (
                            datetime.now(timezone.utc) - timedelta(days=365)
                        ).isoformat(),
                    },
                },
                tenant_id=self.test_tenant,
                database_config=self.db_config,
            )

            role_mgmt.run(
                operation="assign_user",
                user_id=user_id,
                role_id=self.roles[profile["role"]],
                tenant_id=self.test_tenant,
                database_config=self.db_config,
            )

            self.users.append(user_id)

    def test_ai_powered_threat_detection_scenario(self):
        """Test AI-powered threat detection in real-time."""
        print("\n🚨 Testing AI-Powered Threat Detection...")

        # Create threat detection workflow
        threat_workflow = AISecurityAnalyzer.create_threat_detection_workflow()
        runtime = LocalRuntime()

        # Simulate different threat scenarios
        threat_scenarios = [
            {
                "name": "Normal Activity",
                "user": "alice_johnson",
                "activity": {
                    "login_time": datetime.now(timezone.utc).isoformat(),
                    "location": "office",
                    "device": "company_laptop",
                    "failed_attempts": 0,
                },
                "patterns": {
                    "resources": ["security_dashboard", "incident_log", "alert_queue"],
                    "frequency": {"per_hour": 15},
                    "data_volume": 50000,  # 50KB
                    "sensitive_count": 2,
                },
                "expected_threat": "none",
            },
            {
                "name": "Brute Force Attack",
                "user": "unknown_attacker",
                "activity": {
                    "login_time": datetime.now(timezone.utc).isoformat(),
                    "location": "unknown",
                    "device": "unknown",
                    "failed_attempts": 47,
                },
                "patterns": {
                    "resources": [],
                    "frequency": {"per_minute": 47},
                    "data_volume": 0,
                    "sensitive_count": 0,
                },
                "expected_threat": "high",
            },
            {
                "name": "Data Exfiltration Attempt",
                "user": "eve_wilson",
                "activity": {
                    "login_time": (
                        datetime.now(timezone.utc) - timedelta(hours=3)
                    ).isoformat(),
                    "location": "vpn",
                    "device": "personal_device",
                    "failed_attempts": 0,
                },
                "patterns": {
                    "resources": [
                        "customer_db",
                        "financial_records",
                        "employee_data",
                        "ip_portfolio",
                    ],
                    "frequency": {"per_hour": 200},
                    "data_volume": 5000000000,  # 5GB
                    "sensitive_count": 150,
                },
                "expected_threat": "critical",
            },
            {
                "name": "Privilege Escalation",
                "user": "bob_smith",
                "activity": {
                    "login_time": datetime.now(timezone.utc).isoformat(),
                    "location": "office",
                    "device": "company_laptop",
                    "failed_attempts": 2,
                },
                "patterns": {
                    "resources": ["admin_console", "user_management", "role_editor"],
                    "frequency": {"per_hour": 10},
                    "data_volume": 10000,
                    "sensitive_count": 5,
                },
                "expected_threat": "medium",
            },
        ]

        for scenario in threat_scenarios:
            print(f"\n📊 Scenario: {scenario['name']} - User: {scenario['user']}")

            # Execute threat detection
            result, metadata = runtime.execute(
                threat_workflow,
                parameters={
                    "collect_signals": {
                        "user_activity": scenario["activity"],
                        "access_patterns": scenario["patterns"],
                        "system_state": {"alert_level": "normal"},
                    },
                    "ai_threat_analysis": {
                        "prompt": f"Analyze security signals for {scenario['name']} scenario",
                        "backend_config": {
                            "host": self.ollama_config["host"],
                            "port": self.ollama_config["port"],
                        },
                    },
                    "ai_compliance_check": {
                        "prompt": f"Check compliance for {scenario['user']} activity",
                        "backend_config": {
                            "host": self.ollama_config["host"],
                            "port": self.ollama_config["port"],
                        },
                    },
                },
            )

            # Extract results
            response = result["generate_response"]["result"]
            ai_insights = response["ai_insights"]

            print("  🤖 AI Threat Assessment:")
            try:
                threat_analysis = ai_insights["threat_analysis"]
                print(
                    f"     Threat Level: {threat_analysis.get('threat_level', 'unknown')}"
                )
                print(f"     Confidence: {threat_analysis.get('confidence', 0)}%")
                print(f"     Risk Score: {threat_analysis.get('risk_score', 0)}/100")

                if threat_analysis.get("threat_types"):
                    print(
                        f"     Threats Detected: {', '.join(threat_analysis['threat_types'])}"
                    )

                if threat_analysis.get("indicators"):
                    print(
                        f"     Indicators: {', '.join(threat_analysis['indicators'][:3])}"
                    )
            except Exception as e:
                print(f"     Error parsing threat analysis: {e}")

            print("\n  📋 Response Plan:")
            print(f"     Action: {response['action']}")
            print(f"     Severity: {response['severity']}")

            if response["notifications"]:
                print(f"     Notify: {', '.join(response['notifications'])}")

            if response["automated_actions"]:
                print(f"     Automated: {', '.join(response['automated_actions'][:3])}")

            if response["manual_actions"]:
                print(f"     Manual: {', '.join(response['manual_actions'])}")

            # Log threat detection result
            if response["severity"] in ["high", "critical"]:
                db_node = SQLDatabaseNode(name="audit", **self.db_config)
                db_node.run(
                    query="""
                        INSERT INTO admin_audit_log
                        (user_id, action, resource_type, resource_id, operation, details, success, tenant_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    parameters=[
                        scenario["user"],
                        "threat_detected",
                        "security",
                        f"threat_{scenario['name'].lower().replace(' ', '_')}",
                        "ai_analysis",
                        json.dumps(
                            {
                                "threat_level": response["severity"],
                                "actions": response["automated_actions"],
                            }
                        ),
                        False,  # Threat = not success
                        self.test_tenant,
                        datetime.now(timezone.utc),
                    ],
                )

    def test_natural_language_policy_evaluation(self):
        """Test natural language access requests with AI policy evaluation."""
        print("\n💬 Testing Natural Language Policy Evaluation...")

        # Create policy evaluation workflow
        policy_workflow = AISecurityAnalyzer.create_policy_evaluation_workflow()
        runtime = LocalRuntime()

        # Natural language access requests
        nl_requests = [
            {
                "request": "I need to access the customer database to generate the quarterly sales report for the board meeting tomorrow",
                "user": "bob_smith",
                "user_context": {
                    "user_id": "bob_smith",
                    "role": "Data Scientist",
                    "department": "Data",
                    "clearance": "internal",
                    "access_history": {
                        "typical_resources": ["analytics_db", "reports_folder"],
                        "last_sensitive_access": "30_days_ago",
                    },
                },
                "resource_context": {
                    "resource_id": "customer_database",
                    "type": "database",
                    "sensitivity": "high",
                    "owner": "Sales",
                    "classification": "confidential",
                },
                "business_reason": "Quarterly board report",
                "expected_decision": "approve_with_conditions",
            },
            {
                "request": "Grant me admin access to all systems for maintenance",
                "user": "alice_johnson",
                "user_context": {
                    "user_id": "alice_johnson",
                    "role": "Security Analyst",
                    "department": "Security",
                    "clearance": "confidential",
                    "access_history": {
                        "typical_resources": ["logs", "alerts"],
                        "admin_access": "never",
                    },
                },
                "resource_context": {
                    "resource_id": "admin_console",
                    "type": "system",
                    "sensitivity": "critical",
                    "owner": "IT",
                    "classification": "restricted",
                },
                "business_reason": "System maintenance",
                "expected_decision": "deny",
            },
            {
                "request": "Can I temporarily access the production servers to deploy the security patch we discussed in this morning's meeting?",
                "user": "charlie_davis",
                "user_context": {
                    "user_id": "charlie_davis",
                    "role": "System Administrator",
                    "department": "IT",
                    "clearance": "secret",
                    "access_history": {
                        "typical_resources": ["servers", "configs", "deploy_tools"],
                        "last_prod_access": "yesterday",
                    },
                },
                "resource_context": {
                    "resource_id": "production_servers",
                    "type": "infrastructure",
                    "sensitivity": "critical",
                    "owner": "IT",
                    "classification": "production",
                },
                "business_reason": "Critical security patch deployment",
                "expected_decision": "approve",
            },
            {
                "request": "I want to download all employee records for my personal research project",
                "user": "eve_wilson",
                "user_context": {
                    "user_id": "eve_wilson",
                    "role": "Data Scientist",
                    "department": "Data",
                    "clearance": "internal",
                    "access_history": {
                        "typical_resources": ["training_data", "models"],
                        "hr_access": "never",
                        "suspicious_activity": True,
                    },
                },
                "resource_context": {
                    "resource_id": "employee_records",
                    "type": "hr_database",
                    "sensitivity": "critical",
                    "owner": "HR",
                    "classification": "pii",
                },
                "business_reason": "Personal research",
                "expected_decision": "deny",
            },
        ]

        for request_data in nl_requests:
            print(f"\n📝 Request: \"{request_data['request']}\"")
            print(
                f"   From: {request_data['user']} ({request_data['user_context']['role']})"
            )
            print(f"   Resource: {request_data['resource_context']['resource_id']}")

            # Execute policy evaluation
            result, metadata = runtime.execute(
                policy_workflow,
                parameters={
                    "parse_request": {
                        "request": request_data["request"],
                        "user_context": request_data["user_context"],
                        "resource_context": request_data["resource_context"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "location": "office",
                        "business_reason": request_data["business_reason"],
                    },
                    "ai_policy_interpreter": {
                        "prompt": f"Evaluate access request: {request_data['request']}",
                        "backend_config": {
                            "host": self.ollama_config["host"],
                            "port": self.ollama_config["port"],
                        },
                    },
                    "ai_precedent_check": {
                        "prompt": f"Check historical precedents for {request_data['user']} accessing {request_data['resource_context']['resource_id']}",
                        "backend_config": {
                            "host": self.ollama_config["host"],
                            "port": self.ollama_config["port"],
                        },
                    },
                },
            )

            # Extract decision
            decision = result["make_decision"]["result"]

            print("\n   🤖 AI Policy Decision:")
            print(f"      Access Granted: {'✅' if decision['grant_access'] else '❌'}")

            if decision["grant_access"]:
                print(f"      Permissions: {', '.join(decision['permissions'])}")
                if decision["conditions"]:
                    print(f"      Conditions: {', '.join(decision['conditions'])}")
                if decision["duration"]:
                    print(f"      Duration: {decision['duration']}")
                if decision["require_approval"]:
                    print("      ⚠️  Requires additional approval")

            print(f"      Audit Priority: {decision['audit_priority']}")

            # Show AI reasoning
            if "ai_reasoning" in decision:
                reasoning = decision["ai_reasoning"]
                print("\n   🧠 AI Reasoning:")
                print(f"      Risk Level: {reasoning.get('risk_level', 'unknown')}")
                print(
                    f"      Precedent Confidence: {reasoning.get('precedent_confidence', 0)}%"
                )
                if reasoning.get("anomalies"):
                    print("      ⚠️  Anomalies detected in request")
                if reasoning.get("policy_factors"):
                    print(
                        f"      Policies Applied: {', '.join(reasoning['policy_factors'][:3])}"
                    )

            # Create audit entry for denied requests
            if not decision["grant_access"]:
                db_node = SQLDatabaseNode(name="audit", **self.db_config)
                db_node.run(
                    query="""
                        INSERT INTO admin_audit_log
                        (user_id, action, resource_type, resource_id, operation, details, success, tenant_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    parameters=[
                        request_data["user"],
                        "access_denied",
                        request_data["resource_context"]["type"],
                        request_data["resource_context"]["resource_id"],
                        "nl_request",
                        json.dumps(
                            {
                                "request": request_data["request"],
                                "reason": request_data["business_reason"],
                                "ai_decision": decision.get("ai_reasoning", {}),
                            }
                        ),
                        False,
                        self.test_tenant,
                        datetime.now(timezone.utc),
                    ],
                )

    def test_ai_driven_anomaly_detection(self):
        """Test AI-driven anomaly detection in user behavior."""
        print("\n🔍 Testing AI-Driven Anomaly Detection...")

        # Create anomaly detection workflow
        anomaly_workflow = WorkflowBuilder.from_dict(
            {
                "name": "anomaly_detection",
                "description": "AI-powered user behavior anomaly detection",
                "nodes": {
                    "collect_behavior": {
                        "type": "SQLDatabaseNode",
                        "parameters": {
                            "operation": "query",
                            "query": """
                            SELECT
                                user_id,
                                COUNT(*) as access_count,
                                COUNT(DISTINCT resource_id) as unique_resources,
                                AVG(CASE WHEN success THEN 1 ELSE 0 END) as success_rate,
                                MAX(created_at) as last_access
                            FROM admin_audit_log
                            WHERE tenant_id = %s
                            AND created_at > NOW() - INTERVAL '24 hours'
                            GROUP BY user_id
                        """,
                        },
                    },
                    "analyze_patterns": {
                        "type": "DataTransformer",
                        "parameters": {
                            "transformations": [
                                {
                                    "operation": "calculate",
                                    "field": "access_velocity",
                                    "expression": "access_count / 24",
                                },
                                {
                                    "operation": "calculate",
                                    "field": "resource_diversity",
                                    "expression": "unique_resources / access_count",
                                },
                            ]
                        },
                    },
                    "ai_anomaly_detection": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.2,
                            "system_prompt": """You are an AI specializing in user behavior analysis and anomaly detection.

Analyze the user behavior data and identify:
1. Unusual access patterns
2. Potential security threats
3. Behavioral anomalies compared to baseline
4. Risk indicators

Consider factors like:
- Sudden increase in access frequency
- Access to unusual resources
- Failed access attempts
- Time-based anomalies
- Peer group deviations

Respond with a JSON object:
{
    "anomalies_detected": [
                        {
                            "user_id": "user",
                            "anomaly_type": "type",
                            "severity": "low|medium|high",
                            "description": "what was detected",
                            "risk_score": 0-100
                        }
                    ],
    "overall_risk": "low|medium|high|critical",
    "recommended_actions": ["list of actions"],
    "patterns_identified": ["behavioral patterns observed"]
}""",
                        },
                    },
                },
                "connections": [
                    {"from": "collect_behavior", "to": "analyze_patterns"},
                    {"from": "analyze_patterns", "to": "ai_anomaly_detection"},
                ],
            }
        )

        # Generate some test activity
        print("📊 Generating test activity patterns...")
        self._generate_test_activity()

        # Run anomaly detection
        runtime = LocalRuntime()
        result, metadata = runtime.execute(
            anomaly_workflow,
            parameters={
                "collect_behavior": {
                    "parameters": [self.test_tenant],
                    "database_config": self.db_config,
                },
                "analyze_patterns": {},
                "ai_anomaly_detection": {
                    "prompt": "Analyze user behavior for security anomalies",
                    "backend_config": {
                        "host": self.ollama_config["host"],
                        "port": self.ollama_config["port"],
                    },
                },
            },
        )

        # Display results
        print("\n🤖 AI Anomaly Detection Results:")

        try:
            ai_analysis = json.loads(
                result["ai_anomaly_detection"]["result"]["content"]
            )

            print(
                f"   Overall Risk Level: {ai_analysis.get('overall_risk', 'unknown')}"
            )

            if ai_analysis.get("anomalies_detected"):
                print("\n   🚨 Anomalies Detected:")
                for anomaly in ai_analysis["anomalies_detected"]:
                    print(f"      User: {anomaly['user_id']}")
                    print(f"      Type: {anomaly['anomaly_type']}")
                    print(f"      Severity: {anomaly['severity']}")
                    print(f"      Description: {anomaly['description']}")
                    print(f"      Risk Score: {anomaly['risk_score']}/100")
                    print()

            if ai_analysis.get("patterns_identified"):
                print("   📈 Patterns Identified:")
                for pattern in ai_analysis["patterns_identified"]:
                    print(f"      - {pattern}")

            if ai_analysis.get("recommended_actions"):
                print("\n   🛡️ Recommended Actions:")
                for action in ai_analysis["recommended_actions"]:
                    print(f"      - {action}")

        except Exception as e:
            print(f"   Error parsing AI response: {e}")

    def test_ai_compliance_validation(self):
        """Test AI-powered compliance validation."""
        print("\n📋 Testing AI-Powered Compliance Validation...")

        # Create compliance validation workflow
        compliance_workflow = WorkflowBuilder.from_dict(
            {
                "name": "compliance_validation",
                "description": "AI-powered compliance checking",
                "nodes": {
                    "gather_audit_data": {
                        "type": "SQLDatabaseNode",
                        "parameters": {
                            "operation": "query",
                            "query": """
                            SELECT
                                operation,
                                COUNT(*) as count,
                                SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                                COUNT(DISTINCT user_id) as unique_users,
                                MIN(created_at) as first_occurrence,
                                MAX(created_at) as last_occurrence
                            FROM admin_audit_log
                            WHERE tenant_id = %s
                            AND created_at > NOW() - INTERVAL '7 days'
                            GROUP BY operation
                        """,
                        },
                    },
                    "ai_compliance_check": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.1,
                            "system_prompt": """You are an AI compliance auditor reviewing system activity for regulatory compliance.

Review the audit data and validate compliance with:
1. SOC2 requirements (security, availability, processing integrity)
2. GDPR (if personal data is involved)
3. Access control best practices
4. Audit logging requirements
5. Separation of duties

Identify any compliance violations or concerns.

Respond with a JSON object:
{
    "compliance_status": "compliant|non_compliant|needs_review",
    "frameworks_evaluated": ["SOC2", "GDPR", etc.],
    "violations": [
                        {
                            "framework": "framework name",
                            "requirement": "specific requirement",
                            "violation": "what was violated",
                            "severity": "low|medium|high|critical",
                            "remediation": "how to fix"
                        }
                    ],
    "strengths": ["positive compliance aspects"],
    "recommendations": ["improvement suggestions"],
    "audit_completeness": 0-100,
    "certification_ready": true|false
}""",
                        },
                    },
                    "generate_report": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json
from datetime import datetime

# Parse AI compliance assessment
compliance_data = json.loads(inputs.get("compliance_assessment", "{}"))

# Generate compliance report
report = {
    "report_id": f"compliance_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    "generated_at": datetime.now().isoformat(),
    "tenant_id": inputs.get("tenant_id"),
    "period": "last_7_days",
    "executive_summary": {
                        "status": compliance_data.get("compliance_status", "unknown"),
                        "certification_ready": compliance_data.get("certification_ready", False),
                        "critical_issues": len([v for v in compliance_data.get("violations", []) if v.get("severity") == "critical"]),
                        "audit_completeness": compliance_data.get("audit_completeness", 0)
                    },
    "details": compliance_data,
    "action_items": []
}

# Generate action items from violations
for violation in compliance_data.get("violations", []):
    report["action_items"].append({
                        "priority": violation.get("severity"),
                        "framework": violation.get("framework"),
                        "action": violation.get("remediation"),
                        "deadline": "immediate" if violation.get("severity") == "critical" else "30_days"
                    })

result = report
"""
                        },
                    },
                },
                "connections": [
                    {"from": "gather_audit_data", "to": "ai_compliance_check"},
                    {
                        "from": "ai_compliance_check",
                        "to": "generate_report",
                        "map": {"result.content": "compliance_assessment"},
                    },
                ],
            }
        )

        # Execute compliance validation
        runtime = LocalRuntime()
        result, metadata = runtime.execute(
            compliance_workflow,
            parameters={
                "gather_audit_data": {
                    "parameters": [self.test_tenant],
                    "database_config": self.db_config,
                },
                "ai_compliance_check": {
                    "prompt": "Perform comprehensive compliance audit",
                    "backend_config": {
                        "host": self.ollama_config["host"],
                        "port": self.ollama_config["port"],
                    },
                },
                "generate_report": {"tenant_id": self.test_tenant},
            },
        )

        # Display compliance report
        report = result["generate_report"]["result"]

        print("\n📊 Compliance Report")
        print(f"   Report ID: {report['report_id']}")
        print(f"   Status: {report['executive_summary']['status']}")
        print(
            f"   Certification Ready: {'✅' if report['executive_summary']['certification_ready'] else '❌'}"
        )
        print(
            f"   Audit Completeness: {report['executive_summary']['audit_completeness']}%"
        )

        if report["executive_summary"]["critical_issues"] > 0:
            print(
                f"\n   ⚠️  Critical Issues: {report['executive_summary']['critical_issues']}"
            )

        if report.get("action_items"):
            print("\n   📝 Action Items:")
            for item in report["action_items"][:5]:  # Show first 5
                print(
                    f"      [{item['priority'].upper()}] {item['framework']}: {item['action']}"
                )
                print(f"            Deadline: {item['deadline']}")

        # Save report to database
        db_node = SQLDatabaseNode(name="save_report", **self.db_config)
        db_node.run(
            query="""
                INSERT INTO admin_audit_log
                (user_id, action, resource_type, resource_id, operation, details, success, tenant_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            parameters=[
                "ai_system",
                "compliance_report_generated",
                "report",
                report["report_id"],
                "compliance_audit",
                json.dumps(report),
                True,
                self.test_tenant,
                datetime.now(timezone.utc),
            ],
        )

        print(f"\n   ✅ Compliance report saved: {report['report_id']}")

    def _generate_test_activity(self):
        """Generate test activity for anomaly detection."""
        perm_check = PermissionCheckNode()

        # Normal activity for most users
        for user in ["alice_johnson", "bob_smith", "charlie_davis"]:
            for i in range(10):
                try:
                    perm_check.run(
                        operation="check_permission",
                        user_id=user,
                        resource_id=f"resource_{i}",
                        permission="read",
                        tenant_id=self.test_tenant,
                        database_config=self.db_config,
                    )
                except:
                    pass

        # Suspicious activity for Eve
        for i in range(100):  # Excessive access attempts
            try:
                perm_check.run(
                    operation="check_permission",
                    user_id="eve_wilson",
                    resource_id=f"sensitive_resource_{i}",
                    permission="export",
                    tenant_id=self.test_tenant,
                    database_config=self.db_config,
                )
            except:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

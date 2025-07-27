# Enterprise Security Nodes Guide

*Comprehensive security framework with AI-powered threat detection, ABAC permissions, and multi-factor authentication*

## Overview

The Enterprise Security Nodes provide production-ready security capabilities including AI-powered threat detection, advanced ABAC (Attribute-Based Access Control) permission evaluation, multi-factor authentication, and behavior analysis. These nodes are designed for enterprise environments requiring sophisticated security controls.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of security concepts (RBAC, ABAC, MFA)
- Familiarity with threat detection principles

## Core Security Nodes

### ThreatDetectionNode

AI-powered threat detection with real-time analysis and automated response.

```python
from kailash.nodes.security.threat_detection import ThreatDetectionNode

# Basic threat detection setup
threat_detector = ThreatDetectionNode(
    name="threat_detector",
    detection_rules=["brute_force", "privilege_escalation", "data_exfiltration"],
    ai_model="ollama:llama3.2:3b",
    response_actions=["alert", "block_ip", "quarantine_user"],
    real_time=True,
    severity_threshold="medium"
)

# Process security events
security_events = [
    {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True, "timestamp": "2024-01-01T10:00:00Z"},
    {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True, "timestamp": "2024-01-01T10:00:05Z"},
    {"type": "login", "user": "admin", "ip": "192.168.1.100", "failed": True, "timestamp": "2024-01-01T10:00:10Z"},
    {"type": "file_access", "user": "admin", "file": "/etc/passwd", "timestamp": "2024-01-01T10:00:15Z"}
]

result = threat_detector.run(events=security_events)
print(f"Detected {len(result['threats'])} threats with confidence scores")
```

### Advanced Threat Detection

```python
# Production threat detection with comprehensive rules
threat_detector = ThreatDetectionNode(
    name="advanced_threat_detector",
    detection_rules=[
        "brute_force",
        "privilege_escalation",
        "data_exfiltration",
        "lateral_movement",
        "anomalous_access",
        "insider_threat"
    ],

    # AI configuration
    ai_model="ollama:llama3.2:7b",

    # Response configuration
    response_actions=[
        "alert_soc",
        "block_ip",
        "quarantine_user",
        "escalate_to_admin",
        "lock_account"
    ],

    # Performance settings
    real_time=True,
    severity_threshold="high",
    response_time_target_ms=100
)

# Handle real-time threat detection
@threat_detector.on_threat_detected
async def handle_threat(threat_info):
    """Handle detected threat with automated response."""
    threat_level = threat_info["severity"]

    if threat_level == "critical":
        # Immediate response
        await threat_detector.execute_response("block_ip", threat_info["source_ip"])
        await threat_detector.execute_response("alert_soc", threat_info)
    elif threat_level == "high":
        # Escalated monitoring
        await threat_detector.execute_response("escalate_to_admin", threat_info)

    # Always log the threat
    await threat_detector.log_threat(threat_info)
```

## ABAC Permission Evaluation

Advanced attribute-based access control with AI-powered policy reasoning.

### ABACPermissionEvaluatorNode

```python
from kailash.nodes.security.abac_evaluator import ABACPermissionEvaluatorNode, ABACPolicy, ABACContext

# Initialize ABAC evaluator
abac_evaluator = ABACPermissionEvaluatorNode(
    policies=[
        ABACPolicy(
            id="admin_access",
            name="Admin Full Access",
            effect="allow",
            conditions={
                "user.role": {"equals": "admin"},
                "resource.type": {"not_equals": "classified"},
                "environment.time": {"within_hours": [8, 18]}
            },
            priority=100
        ),
        ABACPolicy(
            id="data_scientist_access",
            name="Data Scientist Limited Access",
            effect="allow",
            conditions={
                "user.department": {"equals": "data_science"},
                "resource.classification": {"in": ["public", "internal"]},
                "action.type": {"equals": "read"}
            },
            priority=50
        )
    ],

    # AI-powered policy reasoning
    enable_ai_reasoning=True,
    ai_model="ollama:llama3.2:3b",

    # Performance optimization
    enable_caching=True,
    cache_ttl=300,  # 5 minutes
    target_response_time_ms=15,

    # Audit and monitoring
    enable_audit_logging=True,
    log_all_decisions=True
)

# Evaluate permission request
user_context = ABACContext(
    user_attributes={
        "id": "user123",
        "role": "data_scientist",
        "department": "data_science",
        "clearance_level": 3,
        "groups": ["analytics", "research"]
    },
    resource_attributes={
        "id": "dataset456",
        "type": "dataset",
        "classification": "internal",
        "owner": "data_team",
        "sensitive": False
    },
    environment_attributes={
        "time": "14:30",
        "location": "office",
        "network": "corporate",
        "device_type": "laptop"
    },
    action_attributes={
        "type": "read",
        "method": "query",
        "scope": "limited"
    }
)

decision = abac_evaluator.run(context=user_context)
print(f"Access decision: {decision['decision']} (confidence: {decision['confidence']})")
```

### ABAC with Complex Policies

```python
# Advanced ABAC policies with 16 operators
complex_policies = [
    ABACPolicy(
        id="dynamic_access",
        name="Dynamic Resource Access",
        effect="allow",
        conditions={
            # Equality operators
            "user.role": {"equals": "analyst"},
            "resource.department": {"not_equals": "hr"},

            # Set operators
            "user.groups": {"contains": "analysts"},
            "resource.tags": {"intersects": ["public", "research"]},
            "action.permissions": {"subset_of": ["read", "query"]},

            # Numeric operators
            "user.clearance_level": {"greater_than": 2},
            "resource.sensitivity_score": {"less_than_or_equal": 5},
            "environment.risk_score": {"between": [1, 3]},

            # String operators
            "user.email": {"starts_with": "analyst@"},
            "resource.path": {"ends_with": ".csv"},
            "resource.description": {"contains": "analytics"},

            # Temporal operators
            "environment.time": {"within_hours": [9, 17]},
            "user.last_login": {"within_days": 7},

            # Advanced operators
            "user.attributes": {"matches_pattern": r"^[a-zA-Z]+@company\.com$"},
            "resource.metadata": {"satisfies_expression": "sensitivity < 5 AND public = true"},
            "environment.context": {"custom_function": "check_geolocation"}
        },
        priority=75
    )
]

# Real-time permission checking
result = abac_evaluator.run(
    context=user_context,
    request_id="req_12345",
    trace_decision=True  # Enable decision tracing for audit
)

if result["decision"] == "allow":
    print(f"Access granted: {result['reason']}")
    # Log successful access
    await audit_logger.log_access_granted(user_context, result)
else:
    print(f"Access denied: {result['reason']}")
    # Log denied access and potentially alert
    await audit_logger.log_access_denied(user_context, result)
```

## Multi-Factor Authentication

Enterprise MFA with TOTP, SMS, email, and backup codes.

### MultiFactorAuthNode

```python
from datetime import timedelta
from kailash.nodes.auth.mfa import MultiFactorAuthNode

# Initialize MFA node
mfa_node = MultiFactorAuthNode(
    name="mfa_enforcer",
    methods=["totp", "sms", "email", "backup_codes"],
    default_method="totp",
    backup_codes_count=10,

    # TOTP configuration
    issuer="MyCompany",
    totp_period=30,

    # SMS configuration
    sms_provider={"provider": "twilio", "template": "Your verification code is: {code}"},

    # Email configuration
    email_provider={"provider": "smtp", "template": "verification_email.html"},

    # Security settings
    rate_limit_attempts=3,
    rate_limit_window=300,  # 5 minutes
    session_timeout=timedelta(minutes=15)
)

# Setup MFA for user
mfa_setup = mfa_node.run(
    action="setup",
    user_id="user123",
    primary_method="totp",
    backup_methods=["sms", "backup_codes"],
    phone="+1234567890",
    email="user@company.com"
)

print(f"MFA setup complete. QR code: {mfa_setup['qr_code_url']}")
print(f"Backup codes: {mfa_setup['backup_codes']}")
```

### MFA Verification Workflow

```python
# Verify MFA during authentication
verification_result = mfa_node.run(
    action="verify",
    user_id="user123",
    method="totp",
    code="123456",
    context={
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0...",
        "location": "office",
        "device_fingerprint": "abc123"
    }
)

if verification_result["success"]:
    print("MFA verification successful")
    # Set authentication session
    session_token = verification_result["session_token"]
else:
    print(f"MFA verification failed: {verification_result['reason']}")
    attempts_remaining = verification_result["attempts_remaining"]

    if attempts_remaining == 0:
        print("Account locked due to too many failed attempts")

# Handle backup code verification
backup_verification = mfa_node.run(
    action="verify_backup",
    user_id="user123",
    backup_code="abc-def-ghi",
    context={"emergency_access": True}
)

# Manage MFA settings
mfa_status = mfa_node.run(
    action="status",
    user_id="user123"
)

print(f"MFA enabled: {mfa_status['enabled']}")
print(f"Active methods: {mfa_status['active_methods']}")
print(f"Backup codes remaining: {mfa_status['backup_codes_remaining']}")
```

## Behavior Analysis

AI-powered user behavior analysis for anomaly detection.

### BehaviorAnalysisNode

```python
from datetime import timedelta
from kailash.nodes.security.behavior_analysis import BehaviorAnalysisNode

# Initialize behavior analysis
behavior_analyzer = BehaviorAnalysisNode(
    name="behavior_monitor",

    # AI configuration
    ai_model="ollama:llama3.2:7b",
    baseline_period=timedelta(days=30),
    anomaly_threshold=0.8,  # Anomaly detection threshold (0-1)

    # Learning settings
    learning_enabled=True,
    ai_analysis=True,

    # Storage settings
    max_profile_history=10000
)

# Analyze user behavior
user_activity = {
    "user_id": "user123",
    "login_time": "02:30",  # Unusual time
    "location": "remote",   # Different from usual office
    "data_access": [
        {"resource": "customer_database", "action": "bulk_download"},
        {"resource": "financial_reports", "action": "export"}
    ],
    "network_activity": {
        "unusual_destinations": ["external_server.com"],
        "data_volume": "500MB"  # Much higher than usual
    }
}

analysis_result = behavior_analyzer.run(
    activity=user_activity,
    baseline_comparison=True,
    generate_risk_score=True
)

print(f"Risk score: {analysis_result['risk_score']}/10")
print(f"Anomalies detected: {analysis_result['anomalies']}")
print(f"Recommended actions: {analysis_result['recommended_actions']}")
```

## Security Event Integration

Integrate security nodes with event logging and monitoring.

### Comprehensive Security Workflow

```python
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode
from kailash.workflow.builder import WorkflowBuilder

# Create security monitoring workflow
security_workflow = WorkflowBuilder()

# Add security nodes
security_workflow.add_node("ThreatDetectionNode", "threat_detector", {
    "detection_rules": ["brute_force", "privilege_escalation"],
    "ai_model": "ollama:llama3.2:3b",
    "real_time": True
})

security_workflow.add_node("ABACPermissionEvaluatorNode", "abac_evaluator", {
    "enable_ai_reasoning": True,
    "enable_caching": True,
    "target_response_time_ms": 15
})

security_workflow.add_node("MultiFactorAuthNode", "mfa_verifier", {
    "supported_methods": ["totp", "sms"],
    "require_multiple_factors": True
})

security_workflow.add_node("BehaviorAnalysisNode", "behavior_analyzer", {
    "analysis_types": ["login_patterns", "access_patterns"],
    "real_time_analysis": True
})

security_workflow.add_node("AuditLogNode", "audit_logger", {
    "log_level": "detailed",
    "retention_days": 365,
    "enable_real_time_alerts": True
})

# Connect security pipeline
security_workflow.add_connection("threat_detector", "audit_logger", "threat_detector.threats", "audit_logger.security_events")
security_workflow.add_connection("abac_evaluator", "audit_logger", "abac_evaluator.decisions", "audit_logger.access_decisions")
security_workflow.add_connection("behavior_analyzer", "threat_detector", "behavior_analyzer.anomalies", "threat_detector.behavioral_indicators")

# Execute security workflow
security_result = security_runtime.execute(workflow.build(), {
    "security_events": security_events,
    "permission_requests": permission_requests,
    "user_activities": user_activities
})
```

## Production Security Patterns

### Defense in Depth

```python
# Multi-layered security approach
class EnterpriseSecurityFramework:
    def __init__(self):
        # Layer 1: Threat Detection
        self.threat_detector = ThreatDetectionNode(
            name="enterprise_threat_detector",
            detection_rules=["brute_force", "privilege_escalation", "data_exfiltration"],
            ai_model="ollama:llama3.2:7b",
            real_time=True
        )

        # Layer 2: Access Control
        self.security_workflow.add_node("ABACPermissionEvaluatorNode", "enterprise_abac", {
            "enable_ai_reasoning": True,
            "strict_mode": True
        })

        # Layer 3: Authentication
        self.security_workflow.add_node("MultiFactorAuthNode", "enterprise_mfa", {
            "methods": ["totp", "sms", "backup_codes"],
            "default_method": "totp"
        })

        # Layer 4: Behavior Monitoring
        self.behavior_monitor = BehaviorAnalysisNode(
            name="enterprise_behavior_monitor",
            anomaly_threshold=0.85,  # Strict threshold
            learning_enabled=True,
            ai_analysis=True
        )

    async def security_check(self, request):
        """Comprehensive security validation."""
        # Step 1: Threat detection
        threat_result = await self.threat_detector.execute(request["events"])
        if threat_result["threat_level"] == "critical":
            return {"access": "denied", "reason": "Active threat detected"}

        # Step 2: Permission evaluation
        permission_result = await self.abac_evaluator.execute(request["context"])
        if not permission_result["decision"]:
            return {"access": "denied", "reason": "Insufficient permissions"}

        # Step 3: MFA verification
        if request.get("requires_mfa"):
            mfa_result = await self.mfa_enforcer.execute(request["mfa_data"])
            if not mfa_result["success"]:
                return {"access": "denied", "reason": "MFA verification failed"}

        # Step 4: Behavior analysis
        behavior_result = await self.behavior_monitor.execute(request["user_activity"])
        if behavior_result["risk_score"] > 8:
            return {"access": "conditional", "reason": "High risk behavior detected",
                   "additional_requirements": ["additional_verification"]}

        return {"access": "granted", "security_score": behavior_result["risk_score"]}
```

### Security Monitoring Dashboard

```python
# Real-time security monitoring
class SecurityMonitoringDashboard:
    def __init__(self, security_framework):
        self.security = security_framework
        self.metrics = {}

    async def real_time_monitoring(self):
        """Continuous security monitoring."""
        while True:
            # Collect security metrics
            threat_metrics = await self.security.threat_detector.get_metrics()
            access_metrics = await self.security.abac_evaluator.get_metrics()
            auth_metrics = await self.security.mfa_enforcer.get_metrics()
            behavior_metrics = await self.security.behavior_monitor.get_metrics()

            # Update dashboard
            self.metrics.update({
                "threats_detected": threat_metrics["total_threats"],
                "threat_severity": threat_metrics["avg_severity"],
                "access_requests": access_metrics["total_requests"],
                "access_denied_rate": access_metrics["denial_rate"],
                "mfa_success_rate": auth_metrics["success_rate"],
                "behavioral_anomalies": behavior_metrics["anomaly_count"],
                "overall_risk_score": self.calculate_overall_risk()
            })

            # Alert on critical conditions
            if self.metrics["overall_risk_score"] > 8:
                await self.send_critical_alert()

            await asyncio.sleep(60)  # Update every minute

    def calculate_overall_risk(self):
        """Calculate composite risk score."""
        weights = {
            "threat_severity": 0.3,
            "access_denied_rate": 0.2,
            "mfa_failure_rate": 0.2,
            "behavioral_anomalies": 0.3
        }

        risk_score = 0
        for metric, weight in weights.items():
            if metric in self.metrics:
                risk_score += self.metrics[metric] * weight

        return min(risk_score, 10)  # Cap at 10
```

## Best Practices

### 1. Security Configuration

```python
# Production security configuration
ENTERPRISE_SECURITY_CONFIG = {
    "threat_detection": {
        "ai_model": "ollama:llama3.2:7b",  # Use larger model for better accuracy
        "confidence_threshold": 0.8,       # High confidence threshold
        "response_time_ms": 50,            # Fast response requirement
        "enable_threat_intel": True
    },

    "abac_evaluation": {
        "enable_ai_reasoning": True,
        "cache_ttl": 300,                  # 5 minute cache
        "strict_mode": True,               # Fail-safe defaults
        "audit_all_decisions": True
    },

    "mfa_enforcement": {
        "require_for_admin": True,
        "require_for_sensitive": True,
        "backup_codes_required": True,
        "session_timeout": 3600            # 1 hour
    },

    "behavior_analysis": {
        "baseline_period": 30,             # 30 days
        "anomaly_threshold": 2.0,          # 2 standard deviations
        "continuous_learning": True,
        "real_time_alerts": True
    }
}
```

### 2. Integration Patterns

```python
# Integrate with existing security infrastructure
def integrate_with_siem(security_nodes):
    """Integrate security nodes with SIEM system."""

    @security_nodes.threat_detector.on_threat
    async def forward_to_siem(threat):
        await siem_client.send_event({
            "source": "kailash_threat_detection",
            "severity": threat["severity"],
            "description": threat["description"],
            "timestamp": threat["timestamp"],
            "indicators": threat["indicators"]
        })

    @security_nodes.abac_evaluator.on_access_denied
    async def log_access_denial(denial):
        await siem_client.send_event({
            "source": "kailash_access_control",
            "event_type": "access_denied",
            "user": denial["user_id"],
            "resource": denial["resource"],
            "reason": denial["reason"]
        })
```

### 3. Performance Optimization

```python
# Optimize security node performance
async def optimize_security_performance():
    """Implement performance optimizations."""

    # Use caching for frequent permission checks
    abac_cache = {}

    # Batch process security events
    event_batch = []

    # Implement circuit breakers for external dependencies
    threat_intel_circuit_breaker = CircuitBreaker(
        failure_threshold=5,
        timeout=30
    )

    # Use async processing for non-blocking security checks
    async def parallel_security_check(request):
        tasks = [
            threat_detector.process_async(request),
            abac_evaluator.process_async(request),
            behavior_analyzer.process_async(request)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return combine_security_results(results)
```

## Related Guides

**Prerequisites:**
- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server setup

**Next Steps:**
- [Durable Gateway Guide](29-durable-gateway-guide.md) - Gateway durability
- [MCP Advanced Features Guide](27-mcp-advanced-features-guide.md) - Advanced patterns

---

**Implement enterprise-grade security with AI-powered threat detection and advanced access control!**

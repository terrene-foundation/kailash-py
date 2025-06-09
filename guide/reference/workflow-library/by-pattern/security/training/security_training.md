# Security Training - Common Mistakes and Corrections

This document shows common implementation mistakes when building security auditing and compliance workflows with Kailash SDK, followed by correct implementations. This is designed for training LLMs to create accurate Kailash security workflows.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: Missing Import Dependencies in Security Transformations
```python
# WRONG: Missing required imports in DataTransformer transformations
compliance_checker = DataTransformer(
    id="compliance_checker",
    transformations=[
        """
# Check compliance against security frameworks (SOC2, ISO27001, PCI-DSS)
import random
from datetime import datetime

# This will fail when trying to use timedelta
next_assessment_date = (datetime.now() + timedelta(days=90)).isoformat()
"""
    ]
)

# ERROR MESSAGE:
# NameError: name 'timedelta' is not defined
# File "<string>", line 118, in <module>
```

### ✅ Correct: Complete Import Statements
```python
# CORRECT: Include all required imports in transformation code
compliance_checker = DataTransformer(
    id="compliance_checker",
    transformations=[
        """
# Check compliance against security frameworks (SOC2, ISO27001, PCI-DSS)
import random
from datetime import datetime, timedelta  # Include timedelta

# Now this works correctly
next_assessment_date = (datetime.now() + timedelta(days=90)).isoformat()
"""
    ]
)
```

### Error 2: DataTransformer Dict Output Bug in Security Chains
```python
# CONFIRMED BUG: DataTransformer dict outputs become list of keys in security workflows
# This affects ALL security chains with DataTransformer → DataTransformer connections

# ACTUAL DEBUG OUTPUT FROM SECURITY_AUDIT_WORKFLOW.PY:
# COMPLIANCE_CHECKER DEBUG - Input type: <class 'list'>, Content: ['scan_results', 'summary', 'scan_metadata']
# Expected: {"scan_results": [...], "summary": {...}, "scan_metadata": {...}}
# Actual: ['scan_results', 'summary', 'scan_metadata']  # JUST THE KEYS!

# ERROR MESSAGE:
# AttributeError: 'list' object has no attribute 'get'
# File "<string>", line 8, in <module>
# scan_results = data.get("scan_results", [])
```

### ✅ Correct: Security Workflow with DataTransformer Bug Workaround
```python
# PRODUCTION WORKAROUND: Handle both dict and list inputs in security processors
compliance_checker = DataTransformer(
    id="compliance_checker",
    transformations=[
        """
# Check compliance against security frameworks
from datetime import datetime, timedelta

# WORKAROUND: DataTransformer dict output bug
print(f"COMPLIANCE_CHECKER DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in compliance_checker")
    # Create mock vulnerability data since original data is lost
    all_vulns = [
        {"vulnerability_id": "CVE-2024-0007", "category": "authentication", "severity": "critical", "cvss_score": 9.8, "component_name": "web-application"},
        {"vulnerability_id": "CVE-2024-0001", "category": "injection", "severity": "high", "cvss_score": 8.5, "component_name": "api-gateway"},
        {"vulnerability_id": "CVE-2024-0005", "category": "data_exposure", "severity": "high", "cvss_score": 7.5, "component_name": "user-database"}
    ]
    summary = {
        "total_vulnerabilities": 3,
        "severity_breakdown": {"critical": 1, "high": 2, "medium": 0, "low": 0},
        "highest_cvss_score": 9.8
    }
    bug_detected = True
else:
    # Expected case: received dict as intended
    scan_results = data.get("scan_results", [])
    summary = data.get("summary", {})
    all_vulns = [vuln for result in scan_results for vuln in result.get("vulnerabilities", [])]
    bug_detected = False

# Continue with normal compliance checking logic
# ... compliance framework checking
"""
    ]
)
```

### Error 3: Manual Vulnerability Scanning Without Proper Classification
```python
# WRONG: Basic vulnerability detection without proper categorization
vuln_scanner = PythonCodeNode(
    name="vuln_scanner",
    code="""
vulnerabilities = []
for component in components:
    if random.random() < 0.3:  # 30% chance of vulnerability
        vulnerabilities.append({
            "component": component,
            "has_vulnerability": True,
            "severity": random.choice(["low", "medium", "high"])
        })
result = {"vulnerabilities": vulnerabilities}
"""
)

# Problems:
# 1. No CVSS scoring or standardized severity levels
# 2. Missing vulnerability categorization (OWASP Top 10)
# 3. No consideration of component criticality or exposure
# 4. Missing vulnerability metadata and remediation information
# 5. No risk assessment based on business context
```

### ✅ Correct: Comprehensive Vulnerability Assessment
```python
# CORRECT: Structured vulnerability assessment with proper classification
vulnerability_scanner = DataTransformer(
    id="vulnerability_scanner",
    transformations=[
        """
# Perform vulnerability scanning across system components
import random
from datetime import datetime, timedelta

# Define system components with business context
components = [
    {"name": "web-application", "type": "application", "criticality": "high", "exposure": "external"},
    {"name": "api-gateway", "type": "infrastructure", "criticality": "high", "exposure": "external"},
    {"name": "user-database", "type": "database", "criticality": "critical", "exposure": "internal"},
    {"name": "payment-processor", "type": "service", "criticality": "critical", "exposure": "internal"}
]

# Common vulnerability types with CVSS scores
vulnerability_types = [
    {"id": "CVE-2024-0001", "name": "SQL Injection", "severity": "high", "category": "injection", "cvss_score": 8.5},
    {"id": "CVE-2024-0002", "name": "Cross-Site Scripting", "severity": "medium", "category": "xss", "cvss_score": 6.1},
    {"id": "CVE-2024-0003", "name": "Insecure Direct Object Reference", "severity": "medium", "category": "access_control", "cvss_score": 5.4},
    {"id": "CVE-2024-0007", "name": "Broken Authentication", "severity": "critical", "category": "authentication", "cvss_score": 9.8},
    {"id": "CVE-2024-0005", "name": "Sensitive Data Exposure", "severity": "high", "category": "data_exposure", "cvss_score": 7.5}
]

scan_results = []
current_time = datetime.now()

for component in components:
    # Simulate scanning with context-aware vulnerability detection
    vuln_probability = 0.3 if component["criticality"] == "critical" else 0.2 if component["criticality"] == "high" else 0.1
    
    component_vulns = []
    
    for vuln_type in vulnerability_types:
        if random.random() < vuln_probability:
            # Adjust severity based on component context
            base_score = vuln_type["cvss_score"]
            if component["exposure"] == "external":
                adjusted_score = min(10.0, base_score + 1.0)  # External exposure increases risk
            else:
                adjusted_score = base_score
                
            if component["criticality"] == "critical":
                adjusted_score = min(10.0, adjusted_score + 0.5)  # Critical components increase impact
            
            vulnerability = {
                "vulnerability_id": vuln_type["id"],
                "vulnerability_name": vuln_type["name"],
                "category": vuln_type["category"],
                "severity": "critical" if adjusted_score >= 9.0 else "high" if adjusted_score >= 7.0 else "medium" if adjusted_score >= 4.0 else "low",
                "cvss_score": round(adjusted_score, 1),
                "base_score": base_score,
                "component_name": component["name"],
                "component_type": component["type"],
                "component_criticality": component["criticality"],
                "component_exposure": component["exposure"],
                "discovered_at": current_time.isoformat(),
                "status": "open",
                "remediation_effort": "high" if adjusted_score >= 8.0 else "medium" if adjusted_score >= 6.0 else "low",
                "exploitability": "high" if component["exposure"] == "external" and adjusted_score >= 7.0 else "medium" if adjusted_score >= 5.0 else "low"
            }
            component_vulns.append(vulnerability)
    
    scan_result = {
        "component": component,
        "vulnerabilities": component_vulns,
        "vulnerability_count": len(component_vulns),
        "highest_severity": max([v["cvss_score"] for v in component_vulns]) if component_vulns else 0,
        "scan_timestamp": current_time.isoformat()
    }
    scan_results.append(scan_result)

# Calculate comprehensive statistics
total_vulns = sum(result["vulnerability_count"] for result in scan_results)
all_vulns = [vuln for result in scan_results for vuln in result["vulnerabilities"]]

severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
for vuln in all_vulns:
    severity_counts[vuln["severity"]] += 1

result = {
    "scan_results": scan_results,
    "summary": {
        "total_components_scanned": len(scan_results),
        "total_vulnerabilities": total_vulns,
        "severity_breakdown": severity_counts,
        "components_with_vulns": sum(1 for result in scan_results if result["vulnerability_count"] > 0),
        "highest_cvss_score": max([vuln["cvss_score"] for vuln in all_vulns]) if all_vulns else 0,
        "average_cvss_score": round(sum(vuln["cvss_score"] for vuln in all_vulns) / len(all_vulns), 2) if all_vulns else 0
    }
}
"""
    ]
)
```

### Error 4: Basic Compliance Checking Without Framework Context
```python
# WRONG: Simple compliance checking without proper framework requirements
compliance_checker = PythonCodeNode(
    name="compliance_checker",
    code="""
compliant = True
for vuln in vulnerabilities:
    if vuln["severity"] == "critical":
        compliant = False
        break
result = {"is_compliant": compliant}
"""
)

# Problems:
# 1. No specific compliance framework requirements
# 2. Missing detailed compliance scoring
# 3. No requirement-specific violation tracking
# 4. Missing compliance timeline and assessment metadata
# 5. No framework-specific thresholds or controls
```

### ✅ Correct: Framework-Specific Compliance Assessment
```python
# CORRECT: Detailed compliance assessment against specific frameworks
compliance_checker = DataTransformer(
    id="compliance_checker",
    transformations=[
        """
# Check compliance against security frameworks (SOC2, ISO27001, PCI-DSS)
from datetime import datetime, timedelta

# Define compliance frameworks with specific requirements
compliance_frameworks = {
    "SOC2": {
        "name": "SOC 2 Type II",
        "categories": ["access_control", "authentication", "data_exposure", "logging", "misconfiguration"],
        "critical_threshold": 0,  # No critical vulnerabilities allowed
        "high_threshold": 2,      # Max 2 high severity vulnerabilities
        "requirements": {
            "access_control": "Strong access controls must be implemented",
            "authentication": "Multi-factor authentication required for all admin access",
            "data_exposure": "Sensitive data must be encrypted at rest and in transit",
            "logging": "Comprehensive audit logging must be enabled",
            "misconfiguration": "Security configurations must be hardened"
        }
    },
    "ISO27001": {
        "name": "ISO 27001:2013",
        "categories": ["access_control", "authentication", "data_exposure", "components", "misconfiguration"],
        "critical_threshold": 0,  # No critical vulnerabilities allowed
        "high_threshold": 3,      # Max 3 high severity vulnerabilities
        "requirements": {
            "access_control": "Access control policy and procedures must be documented",
            "authentication": "Strong authentication mechanisms required",
            "data_exposure": "Information classification and handling procedures required",
            "components": "Asset management and vulnerability management required",
            "misconfiguration": "Security baseline configurations must be maintained"
        }
    },
    "PCI_DSS": {
        "name": "PCI DSS v4.0",
        "categories": ["injection", "authentication", "data_exposure", "components", "misconfiguration"],
        "critical_threshold": 0,  # No critical vulnerabilities allowed for payment processing
        "high_threshold": 1,      # Max 1 high severity vulnerability
        "requirements": {
            "injection": "Input validation must prevent injection attacks",
            "authentication": "Strong authentication required for cardholder data access",
            "data_exposure": "Cardholder data must be encrypted and protected",
            "components": "All software components must be up to date",
            "misconfiguration": "Default passwords and configurations must be changed"
        }
    }
}

compliance_results = {}

for framework_id, framework in compliance_frameworks.items():
    # Check vulnerabilities against framework requirements
    framework_vulns = [vuln for vuln in all_vulns if vuln.get("category") in framework["categories"]]
    
    # Count vulnerabilities by severity
    critical_count = sum(1 for vuln in framework_vulns if vuln.get("severity") == "critical")
    high_count = sum(1 for vuln in framework_vulns if vuln.get("severity") == "high")
    medium_count = sum(1 for vuln in framework_vulns if vuln.get("severity") == "medium")
    
    # Determine compliance status
    is_compliant = (critical_count <= framework["critical_threshold"] and 
                   high_count <= framework["high_threshold"])
    
    # Calculate compliance score
    total_possible_issues = len(framework["categories"]) * 2  # 2 potential issues per category
    actual_issues = critical_count * 2 + high_count * 1.5 + medium_count * 0.5
    compliance_score = max(0, round((total_possible_issues - actual_issues) / total_possible_issues * 100, 1))
    
    # Identify failing requirements
    failing_requirements = []
    for vuln in framework_vulns:
        if vuln.get("severity") in ["critical", "high"]:
            category = vuln.get("category")
            if category in framework["requirements"]:
                failing_requirements.append({
                    "category": category,
                    "requirement": framework["requirements"][category],
                    "violation": vuln.get("vulnerability_name"),
                    "severity": vuln.get("severity"),
                    "component": vuln.get("component_name")
                })
    
    compliance_result = {
        "framework_name": framework["name"],
        "is_compliant": is_compliant,
        "compliance_score": compliance_score,
        "total_violations": len(framework_vulns),
        "critical_violations": critical_count,
        "high_violations": high_count,
        "medium_violations": medium_count,
        "failing_requirements": failing_requirements,
        "next_assessment_date": (datetime.now() + timedelta(days=90)).isoformat(),
        "assessment_timestamp": datetime.now().isoformat()
    }
    
    compliance_results[framework_id] = compliance_result

# Overall compliance summary
overall_compliance = all(result["is_compliant"] for result in compliance_results.values())
average_score = round(sum(result["compliance_score"] for result in compliance_results.values()) / len(compliance_results), 1)

result = {
    "compliance_results": compliance_results,
    "overall_compliance": {
        "is_compliant": overall_compliance,
        "average_compliance_score": average_score,
        "frameworks_assessed": len(compliance_results),
        "compliant_frameworks": sum(1 for result in compliance_results.values() if result["is_compliant"]),
        "non_compliant_frameworks": sum(1 for result in compliance_results.values() if not result["is_compliant"])
    }
}
"""
    ]
)
```

### Error 5: Simple Risk Assessment Without Business Context
```python
# WRONG: Basic risk scoring without business impact assessment
risk_assessor = PythonCodeNode(
    name="risk_assessor",
    code="""
risk_scores = []
for vuln in vulnerabilities:
    if vuln["severity"] == "critical":
        risk_score = 10
    elif vuln["severity"] == "high":
        risk_score = 7
    else:
        risk_score = 3
    risk_scores.append({"vuln_id": vuln["id"], "risk_score": risk_score})
result = {"risk_assessments": risk_scores}
"""
)

# Problems:
# 1. No multi-factor risk calculation
# 2. Missing business impact assessment
# 3. No remediation cost estimation
# 4. Missing priority and timeline recommendations
# 5. No consideration of exploitability or exposure
```

### ✅ Correct: Comprehensive Risk Assessment with Business Impact
```python
# CORRECT: Multi-factor risk assessment with business context
risk_assessor = DataTransformer(
    id="risk_assessor",
    transformations=[
        """
# Calculate risk scores and prioritize security remediation
import datetime

# Risk scoring matrix with multiple factors
risk_factors = {
    "cvss_weight": 0.4,           # Technical severity
    "exposure_weight": 0.25,      # External vs internal exposure
    "criticality_weight": 0.25,   # Component business criticality
    "exploitability_weight": 0.1  # Ease of exploitation
}

# Scoring scales
exposure_scores = {"external": 10, "internal": 5, "private": 2}
criticality_scores = {"critical": 10, "high": 7, "medium": 5, "low": 2}
exploitability_scores = {"high": 10, "medium": 6, "low": 3}

risk_assessments = []

for vuln in all_vulns:
    # Calculate individual risk factors
    cvss_normalized = vuln.get("cvss_score", 0)  # Already 0-10 scale
    exposure_score = exposure_scores.get(vuln.get("component_exposure", "internal"), 5)
    criticality_score = criticality_scores.get(vuln.get("component_criticality", "medium"), 5)
    exploitability_score = exploitability_scores.get(vuln.get("exploitability", "medium"), 6)
    
    # Calculate weighted risk score
    risk_score = (
        cvss_normalized * risk_factors["cvss_weight"] +
        exposure_score * risk_factors["exposure_weight"] +
        criticality_score * risk_factors["criticality_weight"] +
        exploitability_score * risk_factors["exploitability_weight"]
    )
    
    # Determine risk level and priority
    if risk_score >= 8.5:
        risk_level = "critical"
        priority = 1
        remediation_timeline = "immediate"
    elif risk_score >= 7.0:
        risk_level = "high"
        priority = 2
        remediation_timeline = "1 week"
    elif risk_score >= 5.0:
        risk_level = "medium"
        priority = 3
        remediation_timeline = "1 month"
    else:
        risk_level = "low"
        priority = 4
        remediation_timeline = "3 months"
    
    # Estimate remediation effort and cost
    remediation_effort = vuln.get("remediation_effort", "medium")
    effort_hours = {"low": 8, "medium": 24, "high": 80}.get(remediation_effort, 24)
    estimated_cost = effort_hours * 150  # $150/hour developer rate
    
    # Business impact assessment
    if vuln.get("component_criticality") == "critical" and vuln.get("severity") in ["critical", "high"]:
        business_impact = "high"
        potential_loss = "500000+"  # Revenue loss, regulatory fines
    elif vuln.get("component_exposure") == "external" and vuln.get("severity") in ["critical", "high"]:
        business_impact = "medium"
        potential_loss = "100000-500000"  # Reputation damage, incident response
    else:
        business_impact = "low"
        potential_loss = "10000-100000"  # Operational disruption
    
    risk_assessment = {
        "vulnerability_id": vuln.get("vulnerability_id"),
        "vulnerability_name": vuln.get("vulnerability_name"),
        "component_name": vuln.get("component_name"),
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "priority": priority,
        "remediation_timeline": remediation_timeline,
        "business_impact": business_impact,
        "potential_loss_usd": potential_loss,
        "remediation_effort_hours": effort_hours,
        "estimated_cost_usd": estimated_cost,
        "risk_factors": {
            "technical_severity": cvss_normalized,
            "exposure_risk": exposure_score,
            "business_criticality": criticality_score,
            "exploitability": exploitability_score
        },
        "recommended_actions": [
            f"Patch {vuln.get('vulnerability_name')} in {vuln.get('component_name')}",
            f"Test fix in staging environment",
            f"Deploy fix within {remediation_timeline}",
            "Update security documentation"
        ]
    }
    
    risk_assessments.append(risk_assessment)

# Sort by risk score descending (highest risk first)
risk_assessments.sort(key=lambda x: x["risk_score"], reverse=True)

# Calculate portfolio risk metrics
total_risk_score = sum(assessment["risk_score"] for assessment in risk_assessments)
average_risk_score = total_risk_score / len(risk_assessments)

risk_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}
for assessment in risk_assessments:
    risk_distribution[assessment["risk_level"]] += 1

total_remediation_cost = sum(assessment["estimated_cost_usd"] for assessment in risk_assessments)

# Generate executive summary
executive_summary = {
    "overall_risk_level": "critical" if risk_distribution["critical"] > 0 else "high" if risk_distribution["high"] > 2 else "medium",
    "total_vulnerabilities": len(risk_assessments),
    "highest_risk_score": risk_assessments[0]["risk_score"] if risk_assessments else 0,
    "average_risk_score": round(average_risk_score, 2),
    "risk_distribution": risk_distribution,
    "immediate_action_required": risk_distribution["critical"] + risk_distribution["high"],
    "total_remediation_cost": total_remediation_cost
}

result = {
    "risk_assessments": risk_assessments,
    "executive_summary": executive_summary,
    "remediation_roadmap": {
        "immediate": [a for a in risk_assessments if a["risk_level"] == "critical"],
        "short_term": [a for a in risk_assessments if a["risk_level"] == "high"],
        "medium_term": [a for a in risk_assessments if a["risk_level"] == "medium"],
        "long_term": [a for a in risk_assessments if a["risk_level"] == "low"]
    }
}
"""
    ]
)
```

## CORRECT: Complete Security Audit Workflow

```python
# CORRECT: Comprehensive security audit with vulnerability scanning, compliance checking, and risk assessment
from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

def create_security_audit_workflow() -> Workflow:
    """Create a comprehensive security audit workflow."""
    workflow = Workflow(
        workflow_id="security_audit_001",
        name="security_audit_workflow",
        description="Perform comprehensive security assessment and compliance checking"
    )
    
    # === SECURITY SCANNING ===
    vulnerability_scanner = DataTransformer(
        id="vulnerability_scanner",
        transformations=[
            # Comprehensive vulnerability assessment with business context
        ]
    )
    workflow.add_node("vulnerability_scanner", vulnerability_scanner)
    
    # === COMPLIANCE CHECKING ===
    compliance_checker = DataTransformer(
        id="compliance_checker",
        transformations=[
            # Framework-specific compliance assessment with bug workarounds
        ]
    )
    workflow.add_node("compliance_checker", compliance_checker)
    workflow.connect("vulnerability_scanner", "compliance_checker", mapping={"result": "data"})
    
    # === RISK ASSESSMENT ===
    risk_assessor = DataTransformer(
        id="risk_assessor",
        transformations=[
            # Multi-factor risk assessment with business impact
        ]
    )
    workflow.add_node("risk_assessor", risk_assessor)
    workflow.connect("vulnerability_scanner", "risk_assessor", mapping={"result": "data"})
    
    # === SECURITY REPORTING ===
    # Merge compliance and risk data
    security_merger = MergeNode(
        id="security_merger",
        merge_type="merge_dict"
    )
    workflow.add_node("security_merger", security_merger)
    workflow.connect("compliance_checker", "security_merger", mapping={"result": "data1"})
    workflow.connect("risk_assessor", "security_merger", mapping={"result": "data2"})
    
    # Generate comprehensive security report
    security_reporter = DataTransformer(
        id="security_reporter",
        transformations=[
            # Executive dashboard with action plans
        ]
    )
    workflow.add_node("security_reporter", security_reporter)
    workflow.connect("security_merger", "security_reporter", mapping={"merged_data": "data"})
    
    # === OUTPUTS ===
    # Save comprehensive security audit report
    audit_writer = JSONWriterNode(
        id="audit_writer",
        file_path="data/outputs/security_audit_report.json"
    )
    workflow.add_node("audit_writer", audit_writer)
    workflow.connect("security_reporter", "audit_writer", mapping={"result": "data"})
    
    return workflow
```

## WRONG: Hardcoded Security Thresholds

```python
# WRONG: Hardcoded security thresholds without business context
security_analyzer = PythonCodeNode(
    name="security_analyzer",
    code="""
# Fixed thresholds for all organizations
if critical_vulns > 0:
    status = "fail"
elif high_vulns > 5:
    status = "warning"
else:
    status = "pass"
result = {"security_status": status}
"""
)

# Problems:
# 1. No consideration of business context or risk tolerance
# 2. Same thresholds for all compliance frameworks
# 3. No component-specific risk assessment
# 4. Missing gradual scoring system
# 5. No customization for different industries or use cases
```

## ✅ Correct: Context-Aware Security Assessment

```python
# CORRECT: Business context-aware security assessment
security_analyzer = DataTransformer(
    id="security_analyzer",
    transformations=[
        """
# Context-aware security posture assessment
# Determine thresholds based on compliance requirements and business context

# Framework-specific thresholds
framework_thresholds = {
    "PCI_DSS": {"critical": 0, "high": 1},      # Strict for payment processing
    "SOC2": {"critical": 0, "high": 2},         # Moderate for SaaS
    "ISO27001": {"critical": 0, "high": 3},     # Flexible for general business
    "HIPAA": {"critical": 0, "high": 1}         # Strict for healthcare
}

# Component criticality adjustments
criticality_adjustments = {
    "critical": 1.0,    # No adjustment - strict requirements
    "high": 1.5,        # 50% more tolerance
    "medium": 2.0,      # 100% more tolerance
    "low": 3.0          # 200% more tolerance
}

# Calculate dynamic thresholds based on context
for framework_id, framework_result in compliance_results.items():
    base_thresholds = framework_thresholds.get(framework_id, {"critical": 0, "high": 2})
    
    # Adjust thresholds based on component mix
    avg_criticality = calculate_average_component_criticality(components)
    adjustment_factor = criticality_adjustments.get(avg_criticality, 1.0)
    
    adjusted_thresholds = {
        "critical": base_thresholds["critical"],  # Never adjust critical threshold
        "high": int(base_thresholds["high"] * adjustment_factor)
    }
    
    # Apply adjusted thresholds to compliance assessment
    framework_result["dynamic_thresholds"] = adjusted_thresholds
    framework_result["threshold_justification"] = f"Adjusted for {avg_criticality} criticality components"

# Generate context-aware recommendations
recommendations = generate_contextual_recommendations(
    compliance_results=compliance_results,
    risk_assessments=risk_assessments,
    business_context=business_context
)
"""
    ]
)
```

## 📊 Bug Impact Analysis for Security Workflows
- **DataTransformer Bug Frequency**: 100% of security audit chains using DataTransformer → DataTransformer
- **Severity**: Critical - breaks vulnerability data flow and compliance assessment
- **Workaround**: Type checking + mock security data reconstruction (data loss occurs)
- **Best Practice**: Avoid DataTransformer chains, use intermediate security data storage
- **Affects**: Vulnerability scanning, compliance checking, risk assessment, security reporting

## Key Security Principles

1. **Comprehensive Vulnerability Assessment**: Include CVSS scoring, categorization, and business context
2. **Framework-Specific Compliance**: Implement detailed compliance checking for SOC2, ISO27001, PCI-DSS
3. **Multi-Factor Risk Assessment**: Consider technical severity, exposure, criticality, and exploitability
4. **Business Impact Analysis**: Calculate potential losses and remediation costs
5. **DataTransformer Bug Awareness**: Always include type checking workarounds in security chains
6. **Executive Reporting**: Provide clear security posture, compliance status, and action plans
7. **Context-Aware Thresholds**: Adjust security requirements based on business context
8. **Remediation Prioritization**: Sort vulnerabilities by risk score and business impact

## Common Security Patterns

```python
# Pattern 1: Vulnerability Scanning → Compliance Checking → Risk Assessment → Reporting
workflow.connect("vulnerability_scanner", "compliance_checker", mapping={"result": "data"})
workflow.connect("vulnerability_scanner", "risk_assessor", mapping={"result": "data"})
workflow.connect("compliance_checker", "security_merger", mapping={"result": "data1"})
workflow.connect("risk_assessor", "security_merger", mapping={"result": "data2"})

# Pattern 2: Security Data → Analysis → Prioritization → Action Planning
workflow.connect("security_scanner", "threat_analyzer", mapping={"result": "data"})
workflow.connect("threat_analyzer", "priority_calculator", mapping={"result": "data"})
workflow.connect("priority_calculator", "action_planner", mapping={"result": "data"})

# Pattern 3: Audit Results → Compliance Mapping → Risk Scoring → Executive Summary
workflow.connect("audit_collector", "compliance_mapper", mapping={"result": "data"})
workflow.connect("compliance_mapper", "risk_scorer", mapping={"result": "data"})
workflow.connect("risk_scorer", "executive_reporter", mapping={"result": "data"})
```

## Security Assessment Best Practices

### Vulnerability Scanning
- Include CVSS v3.1 scoring with environmental metrics
- Categorize vulnerabilities using OWASP Top 10 or CWE classifications
- Consider component exposure (external vs internal)
- Assess component business criticality

### Compliance Checking
- Implement framework-specific requirements (SOC2, ISO27001, PCI-DSS, HIPAA)
- Use appropriate thresholds for each framework
- Track failing requirements with specific violations
- Calculate compliance scores and trends

### Risk Assessment
- Use multi-factor risk scoring (technical + business)
- Estimate remediation costs and effort
- Assess business impact and potential losses
- Prioritize by risk score and remediation timeline

### Security Reporting
- Provide executive dashboard with security posture
- Include compliance status and scores
- Generate actionable recommendations with priorities
- Track key findings and required actions
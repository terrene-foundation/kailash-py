# Enterprise Compliance Framework

This directory contains comprehensive compliance frameworks for SOC2, HIPAA, and ISO27001 standards, providing automated controls, policies, and audit capabilities for the Kailash platform.

## 🏗️ Compliance Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Compliance Framework                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │     SOC2     │  │    HIPAA     │  │   ISO27001   │        │
│  │   Controls   │  │  Safeguards  │  │   Controls   │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
│  ┌────────────────────────┴────────────────────────┐          │
│  │            Policy Management Engine              │          │
│  ├─────────────────────────────────────────────────┤          │
│  │ • Access Control      • Data Protection         │          │
│  │ • Audit Logging       • Incident Response       │          │
│  │ • Risk Assessment     • Business Continuity     │          │
│  └─────────────────────────────────────────────────┘          │
│                           │                                     │
│  ┌────────────────────────┴────────────────────────┐          │
│  │           Automated Controls & Monitoring        │          │
│  ├─────────────────────────────────────────────────┤          │
│  │ • OPA Policies        • Security Scanning       │          │
│  │ • Compliance Reports • Continuous Monitoring    │          │
│  │ • Evidence Collection • Alert Management        │          │
│  └─────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

```
compliance/
├── README.md                    # This file
├── soc2/                       # SOC2 Type II controls
│   ├── controls/               # Individual control implementations
│   ├── policies/               # SOC2-specific policies
│   ├── procedures/             # Operating procedures
│   └── evidence/               # Evidence collection
├── hipaa/                      # HIPAA compliance
│   ├── safeguards/             # Administrative, physical, technical
│   ├── policies/               # HIPAA-specific policies
│   ├── procedures/             # Security procedures
│   └── breach-response/        # Incident response
├── iso27001/                   # ISO27001:2013 controls
│   ├── controls/               # Annex A controls
│   ├── policies/               # Information security policies
│   ├── procedures/             # Management procedures
│   └── risk-management/        # Risk assessment framework
├── policies/                   # Common policies across frameworks
│   ├── access-control.yaml     # Identity and access management
│   ├── data-protection.yaml    # Data classification and handling
│   ├── incident-response.yaml  # Security incident procedures
│   └── business-continuity.yaml
├── controls/                   # Automated control implementations
│   ├── opa-policies/           # Open Policy Agent rules
│   ├── kubernetes/             # K8s security policies
│   ├── monitoring/             # Compliance monitoring
│   └── scanning/               # Automated scanning
└── audits/                     # Audit and assessment tools
    ├── automation/             # Automated audit scripts
    ├── reports/                # Report templates
    └── evidence/               # Evidence collection tools
```

## 🎯 Compliance Standards

### SOC2 Type II
**Trust Service Criteria**:
- **Security**: Protection against unauthorized access
- **Availability**: System availability for operation and use
- **Processing Integrity**: Complete, valid, accurate processing
- **Confidentiality**: Information designated as confidential
- **Privacy**: Personal information collection, use, retention

### HIPAA
**Safeguards**:
- **Administrative**: Policies and procedures
- **Physical**: Facility access controls
- **Technical**: Access control, audit controls, integrity

### ISO27001:2013
**Control Categories**:
- **A.5-18**: 114 security controls across 14 domains
- Information security policies
- Organization of information security
- Human resource security
- Asset management

## 🚀 Quick Start

### Deploy Compliance Controls

1. **Apply OPA Policies**:
   ```bash
   kubectl apply -f deployment/compliance/controls/opa-policies/
   ```

2. **Deploy Monitoring Stack**:
   ```bash
   kubectl apply -k deployment/compliance/controls/monitoring/
   ```

3. **Configure Audit Logging**:
   ```bash
   kubectl apply -f deployment/compliance/controls/kubernetes/audit-policy.yaml
   ```

### Generate Compliance Report

```bash
# Run comprehensive compliance scan
./deployment/compliance/audits/automation/compliance-scan.sh

# Generate SOC2 report
./deployment/compliance/soc2/generate-report.sh

# Generate HIPAA assessment
./deployment/compliance/hipaa/assess-compliance.sh
```

## 🔧 Control Implementation

### Access Control (Common Control)

**Policy Definition**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: access-control-policy
data:
  policy.yaml: |
    # Multi-factor authentication required
    mfa_required: true
    
    # Role-based access control
    rbac_enabled: true
    
    # Privileged access management
    pam_required: true
    
    # Access review frequency
    access_review_days: 90
```

**OPA Policy Implementation**:
```rego
package kubernetes.admission

# Deny pods without security context
deny[msg] {
    input.request.kind.kind == "Pod"
    input.request.object.spec.securityContext.runAsNonRoot != true
    msg := "Pods must run as non-root user"
}

# Require network policies
deny[msg] {
    input.request.kind.kind == "Namespace"
    not has_network_policy(input.request.object.metadata.name)
    msg := "Namespaces must have network policies"
}
```

### Data Protection (HIPAA/GDPR)

**Encryption Requirements**:
```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: data-protection
spec:
  # Require encrypted storage
  volumes:
    - persistentVolumeClaim
    - secret
    - configMap
  
  # Security context requirements
  runAsUser:
    rule: MustRunAsNonRoot
  
  # Host network restrictions
  hostNetwork: false
  hostPorts:
    - min: 0
      max: 0
```

## 📊 Monitoring & Alerting

### Compliance Metrics

**Prometheus Metrics**:
```yaml
# compliance_control_status
compliance_control_status{framework="soc2",control="CC6.1",status="compliant"} 1

# audit_log_events_total
audit_log_events_total{source="kubernetes",action="create"} 1543

# access_violations_total
access_violations_total{type="unauthorized_access",severity="high"} 0
```

**Grafana Dashboard**:
```json
{
  "dashboard": {
    "title": "Compliance Dashboard",
    "panels": [
      {
        "title": "SOC2 Control Status",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(compliance_control_status{framework=\"soc2\"})"
          }
        ]
      }
    ]
  }
}
```

## 🔒 Security Controls

### Kubernetes Security Policies

**Pod Security Standards**:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

**Network Policies**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: compliance-isolation
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              compliance-zone: "trusted"
```

### Container Security

**Falco Rules for Compliance**:
```yaml
- rule: Unauthorized Process in Container
  desc: Detect unauthorized process execution
  condition: >
    spawned_process and container and
    not proc.name in (allowed_processes)
  output: >
    Unauthorized process started in container
    (user=%user.name command=%proc.cmdline container=%container.name)
  priority: WARNING
  tags: [compliance, process, soc2]
```

## 📋 Audit & Evidence Collection

### Automated Evidence Collection

**Audit Log Analysis**:
```bash
#!/bin/bash
# collect-audit-evidence.sh

# Collect Kubernetes audit logs
kubectl logs -n kube-system -l component=kube-apiserver > audit-logs.json

# Analyze access patterns
jq '.items[] | select(.verb=="create" or .verb=="delete")' audit-logs.json > access-events.json

# Generate compliance report
python3 scripts/generate-compliance-report.py \
  --audit-logs audit-logs.json \
  --framework soc2 \
  --output compliance-report.pdf
```

**Continuous Compliance Monitoring**:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: compliance-monitor
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: compliance-scanner
            image: compliance-scanner:latest
            command:
            - /bin/sh
            - -c
            - |
              # Run compliance checks
              ./scan-soc2-controls.sh
              ./scan-hipaa-safeguards.sh
              ./scan-iso27001-controls.sh
              
              # Upload results
              aws s3 cp results/ s3://compliance-evidence/ --recursive
```

## 🎯 Framework-Specific Implementation

### SOC2 Implementation

**Trust Service Criteria Mapping**:
```yaml
# Security (CC6.0)
CC6.1: "Logical and physical access controls"
  - kubernetes_rbac_enabled: true
  - multi_factor_auth: required
  - privileged_access_logging: enabled

CC6.2: "Transmission and disposal of information"
  - encryption_in_transit: "TLS 1.2+"
  - encryption_at_rest: "AES-256"
  - data_disposal_policy: "NIST 800-88"

CC6.3: "System access controls"
  - authentication_mechanisms: ["MFA", "SSO"]
  - authorization_model: "RBAC"
  - session_management: "secure"
```

### HIPAA Implementation

**Technical Safeguards**:
```yaml
# Access Control (164.312(a))
access_control:
  unique_user_identification: true
  emergency_access_procedure: enabled
  automatic_logoff: "15_minutes"
  encryption_decryption: "AES-256"

# Audit Controls (164.312(b))
audit_controls:
  hardware_software_systems: monitored
  access_attempts: logged
  information_access: tracked

# Integrity (164.312(c))
integrity:
  phi_alteration_destruction: protected
  audit_trail: comprehensive
```

### ISO27001 Implementation

**Annex A Controls**:
```yaml
# A.9 Access Control
A.9.1.1: "Access control policy"
  policy_document: "access-control-policy.md"
  approval_date: "2024-01-01"
  review_frequency: "annual"

A.9.2.1: "User registration and de-registration"
  user_lifecycle_management: automated
  access_review_period: "quarterly"
  deprovisioning: "immediate"

# A.12 Operations Security
A.12.6.1: "Management of technical vulnerabilities"
  vulnerability_scanning: "continuous"
  patch_management: "automated"
  risk_assessment: "quarterly"
```

## 🔍 Compliance Validation

### Automated Testing

**Control Testing Framework**:
```python
# compliance_tests.py
import pytest
from compliance_framework import SOC2, HIPAA, ISO27001

class TestSOC2Compliance:
    def test_cc6_1_access_controls(self):
        """Test logical access controls are implemented"""
        assert check_rbac_enabled()
        assert check_mfa_required()
        assert check_privileged_access_logging()
    
    def test_cc6_2_data_protection(self):
        """Test data transmission and disposal controls"""
        assert check_encryption_in_transit()
        assert check_encryption_at_rest()
        assert check_data_disposal_policy()

class TestHIPAACompliance:
    def test_administrative_safeguards(self):
        """Test HIPAA administrative safeguards"""
        assert check_security_officer_assigned()
        assert check_workforce_training_completed()
        assert check_incident_response_procedures()
    
    def test_technical_safeguards(self):
        """Test HIPAA technical safeguards"""
        assert check_access_control_implementation()
        assert check_audit_controls_enabled()
        assert check_integrity_controls_active()
```

### Evidence Automation

**Automated Evidence Collection**:
```bash
#!/bin/bash
# evidence-collector.sh

echo "Collecting compliance evidence..."

# System configuration evidence
kubectl get all --all-namespaces -o yaml > system-config.yaml

# Security policy evidence
kubectl get networkpolicies --all-namespaces -o yaml > network-policies.yaml

# RBAC evidence
kubectl get roles,rolebindings,clusterroles,clusterrolebindings -o yaml > rbac-config.yaml

# Audit log evidence
kubectl logs -n kube-system -l component=kube-apiserver --tail=10000 > audit-logs.txt

# Generate evidence package
tar -czf compliance-evidence-$(date +%Y%m%d).tar.gz *.yaml *.txt

echo "Evidence collected: compliance-evidence-$(date +%Y%m%d).tar.gz"
```

## 📈 Reporting & Documentation

### Compliance Dashboards

**Real-time Compliance Status**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: compliance-dashboard
data:
  dashboard.json: |
    {
      "dashboard": {
        "title": "Enterprise Compliance Dashboard",
        "panels": [
          {
            "title": "SOC2 Control Status",
            "type": "stat",
            "fieldConfig": {
              "defaults": {
                "color": {
                  "mode": "thresholds"
                },
                "thresholds": {
                  "steps": [
                    {"color": "red", "value": 0},
                    {"color": "yellow", "value": 80},
                    {"color": "green", "value": 95}
                  ]
                }
              }
            }
          }
        ]
      }
    }
```

### Automated Reports

**Monthly Compliance Report**:
```python
# generate_compliance_report.py
from datetime import datetime
from compliance_framework import ComplianceReporter

def generate_monthly_report():
    reporter = ComplianceReporter()
    
    # SOC2 status
    soc2_status = reporter.get_soc2_status()
    
    # HIPAA status
    hipaa_status = reporter.get_hipaa_status()
    
    # ISO27001 status
    iso_status = reporter.get_iso27001_status()
    
    # Generate PDF report
    report = reporter.create_report(
        frameworks=[soc2_status, hipaa_status, iso_status],
        period=datetime.now().strftime("%Y-%m"),
        template="monthly-compliance-report.html"
    )
    
    return report
```

## 🚀 Deployment Instructions

### Prerequisites

1. **Kubernetes cluster** with RBAC enabled
2. **OPA Gatekeeper** installed
3. **Falco** for runtime security
4. **Prometheus** for monitoring

### Installation

```bash
# 1. Deploy OPA policies
kubectl apply -f deployment/compliance/controls/opa-policies/

# 2. Configure audit logging
kubectl apply -f deployment/compliance/controls/kubernetes/

# 3. Deploy compliance monitoring
kubectl apply -k deployment/compliance/controls/monitoring/

# 4. Setup evidence collection
kubectl create -f deployment/compliance/audits/automation/cronjobs.yaml

# 5. Verify deployment
kubectl get all -n compliance-system
```

### Validation

```bash
# Run compliance tests
pytest deployment/compliance/tests/

# Generate initial report
./deployment/compliance/audits/automation/compliance-scan.sh

# Check control status
kubectl get constrainttemplates
kubectl get constraints
```

This comprehensive compliance framework provides enterprise-grade controls and automated compliance monitoring for SOC2, HIPAA, and ISO27001 standards!
# Enterprise Compliance Patterns

*Regulatory compliance, audit trails, data governance, and policy enforcement patterns*

## 🏛️ Overview

This guide covers compliance implementation patterns for Kailash SDK enterprise applications, including GDPR, HIPAA, SOX, PCI-DSS compliance, audit trails, data retention policies, and automated compliance monitoring.

## 📋 GDPR Compliance

### Data Privacy Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.compliance import GDPRComplianceNode, DataRetentionPolicyNode
from kailash.nodes.security import CredentialManagerNode, AuditLogNode

# GDPR compliance workflow
gdpr_workflow = WorkflowBuilder()

# GDPR compliance checks
gdpr_workflow.add_node("GDPRComplianceNode", "gdpr_validator", {
    "compliance_checks": [
        "consent_verification",
        "data_minimization",
        "purpose_limitation",
        "access_rights",
        "erasure_rights",
        "portability_rights"
    ],
    "retention_policy": {
        "personal_data": 365,  # days
        "sensitive_data": 180,
        "marketing_data": 90
    },
    "encryption_required": True,
    "audit_trail": True
})

# Data retention management
gdpr_workflow.add_node("DataRetentionPolicyNode", "retention_manager", {
    "policies": [
        {
            "data_type": "user_profiles",
            "retention_days": 365,
            "deletion_method": "hard_delete",
            "archive_before_delete": True
        },
        {
            "data_type": "transaction_logs",
            "retention_days": 2555,  # 7 years
            "deletion_method": "anonymize",
            "compliance": "financial_regulations"
        },
        {
            "data_type": "access_logs",
            "retention_days": 90,
            "deletion_method": "soft_delete"
        }
    ],
    "automated_cleanup": True,
    "cleanup_schedule": "0 2 * * *"  # 2 AM daily
})

# Consent management using PythonCodeNode
gdpr_workflow.add_node("PythonCodeNode", "consent_manager", {
    "code": """
from datetime import datetime, timedelta
import json

# Verify user consent
def verify_consent(user_id, purpose):
    # Check consent database
    consent_record = consent_db.get(user_id, {}).get(purpose)

    if not consent_record:
        return {
            "valid": False,
            "reason": "no_consent_recorded"
        }

    # Check if consent is still valid
    consent_date = datetime.fromisoformat(consent_record['date'])
    if datetime.now() - consent_date > timedelta(days=365):
        return {
            "valid": False,
            "reason": "consent_expired",
            "expired_date": consent_date.isoformat()
        }

    # Check if consent covers requested purpose
    if purpose not in consent_record['purposes']:
        return {
            "valid": False,
            "reason": "purpose_not_covered"
        }

    return {
        "valid": True,
        "consent_date": consent_date.isoformat(),
        "purposes": consent_record['purposes'],
        "withdrawal_method": consent_record.get('withdrawal_method')
    }

# Process data subject request
def process_dsr(request_type, user_id):
    timestamp = datetime.now().isoformat()

    if request_type == "access":
        # Gather all user data
        user_data = {
            "profile": get_user_profile(user_id),
            "transactions": get_user_transactions(user_id),
            "consents": get_user_consents(user_id),
            "generated_at": timestamp
        }
        return {"status": "completed", "data": user_data}

    elif request_type == "erasure":
        # Right to be forgotten
        deletion_plan = {
            "user_profiles": "delete",
            "transactions": "anonymize",
            "logs": "redact_pii",
            "backups": "schedule_deletion"
        }
        return {"status": "scheduled", "plan": deletion_plan, "eta": "48_hours"}

    elif request_type == "portability":
        # Export data in portable format
        export_data = gather_portable_data(user_id)
        return {
            "status": "ready",
            "format": "json",
            "data": export_data,
            "download_link": f"/api/gdpr/download/{user_id}"
        }

result = {
    "consent_check": verify_consent(user_id, requested_purpose),
    "dsr_status": process_dsr(request_type, user_id) if request_type else None,
    "compliance_timestamp": datetime.now().isoformat()
}
"""
})

# Audit all GDPR operations
gdpr_workflow.add_node("AuditLogNode", "gdpr_audit", {
    "log_categories": ["gdpr", "privacy", "consent", "data_requests"],
    "retention_days": 2555,  # 7 years for compliance
    "immutable": True,
    "encryption": "aes-256-gcm"
})
```

### Data Anonymization Pipeline

```python
# Data anonymization workflow
anonymization_workflow = WorkflowBuilder()

# PII detection
anonymization_workflow.add_node("PythonCodeNode", "pii_detector", {
    "code": """
import re
import hashlib
from typing import Dict, List, Any

# PII patterns
PII_PATTERNS = {
    'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}',
    'phone': r'\\+?1?\\d{9,15}',
    'ssn': r'\\d{3}-\\d{2}-\\d{4}',
    'credit_card': r'\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}',
    'ip_address': r'\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b'
}

def detect_pii(data: Dict[str, Any]) -> Dict[str, List[str]]:
    pii_found = {}

    for field, value in data.items():
        if isinstance(value, str):
            for pii_type, pattern in PII_PATTERNS.items():
                if re.search(pattern, value):
                    if field not in pii_found:
                        pii_found[field] = []
                    pii_found[field].append(pii_type)
        elif isinstance(value, dict):
            nested_pii = detect_pii(value)
            for k, v in nested_pii.items():
                pii_found[f"{field}.{k}"] = v

    return pii_found

def anonymize_data(data: Dict[str, Any], pii_fields: Dict[str, List[str]]) -> Dict[str, Any]:
    anonymized = data.copy()

    for field_path, pii_types in pii_fields.items():
        # Navigate nested fields
        fields = field_path.split('.')
        target = anonymized
        for field in fields[:-1]:
            target = target[field]

        # Anonymize based on PII type
        original_value = target[fields[-1]]
        if 'email' in pii_types:
            # Keep domain but hash local part
            local, domain = original_value.split('@')
            hashed = hashlib.sha256(local.encode()).hexdigest()[:8]
            target[fields[-1]] = f"{hashed}@{domain}"
        elif 'phone' in pii_types:
            # Keep country code, anonymize rest
            target[fields[-1]] = re.sub(r'\\d', 'X', original_value[-7:])
        elif 'ssn' in pii_types or 'credit_card' in pii_types:
            # Full hash
            target[fields[-1]] = hashlib.sha256(original_value.encode()).hexdigest()[:12]
        elif 'ip_address' in pii_types:
            # Zero out last octet
            parts = original_value.split('.')
            parts[-1] = '0'
            target[fields[-1]] = '.'.join(parts)

    return anonymized

# Process data
pii_detected = detect_pii(input_data)
anonymized_data = anonymize_data(input_data, pii_detected)

result = {
    "pii_detected": pii_detected,
    "anonymized_data": anonymized_data,
    "anonymization_method": "deterministic_hashing",
    "reversible": False
}
"""
})
```

## 🏥 HIPAA Compliance

### Healthcare Data Protection

```python
# HIPAA compliance workflow
hipaa_workflow = WorkflowBuilder()

# PHI encryption and access control
hipaa_workflow.add_node("PythonCodeNode", "phi_protector", {
    "code": """
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
from datetime import datetime

# Generate encryption key from master key
def derive_key(master_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
    return key

# Encrypt PHI data
def encrypt_phi(data: dict, master_key: str) -> dict:
    salt = os.urandom(16)
    key = derive_key(master_key, salt)
    f = Fernet(key)

    encrypted_data = {}
    phi_fields = ['patient_name', 'ssn', 'medical_record_number', 'diagnosis', 'treatment']

    for field, value in data.items():
        if field in phi_fields and value:
            encrypted_value = f.encrypt(json.dumps(value).encode())
            encrypted_data[field] = {
                'encrypted': base64.b64encode(encrypted_value).decode(),
                'salt': base64.b64encode(salt).decode(),
                'algorithm': 'AES-256-GCM',
                'encrypted_at': datetime.now().isoformat()
            }
        else:
            encrypted_data[field] = value

    return encrypted_data

# Access control check
def check_phi_access(user_role: str, resource_type: str, access_type: str) -> dict:
    # HIPAA minimum necessary standard
    access_matrix = {
        'physician': {
            'patient_records': ['read', 'write'],
            'treatment_plans': ['read', 'write'],
            'billing': ['read']
        },
        'nurse': {
            'patient_records': ['read'],
            'treatment_plans': ['read', 'update'],
            'billing': []
        },
        'billing_staff': {
            'patient_records': ['read_limited'],
            'treatment_plans': [],
            'billing': ['read', 'write']
        },
        'admin': {
            'patient_records': ['read_metadata'],
            'treatment_plans': ['read_metadata'],
            'billing': ['read']
        }
    }

    allowed_actions = access_matrix.get(user_role, {}).get(resource_type, [])
    is_allowed = access_type in allowed_actions

    # Log access attempt
    access_log = {
        'timestamp': datetime.now().isoformat(),
        'user_role': user_role,
        'resource_type': resource_type,
        'access_type': access_type,
        'allowed': is_allowed,
        'hipaa_rule': 'minimum_necessary'
    }

    return {
        'allowed': is_allowed,
        'reason': 'role_based_access' if is_allowed else 'insufficient_privileges',
        'log': access_log
    }

# Process PHI with encryption and access control
encrypted_phi = encrypt_phi(patient_data, master_key)
access_decision = check_phi_access(user_role, resource_type, requested_access)

result = {
    'encrypted_data': encrypted_phi if access_decision['allowed'] else None,
    'access_decision': access_decision,
    'compliance_checks': {
        'encryption': True,
        'access_control': True,
        'audit_trail': True,
        'minimum_necessary': True
    }
}
"""
})

# HIPAA audit trail
hipaa_workflow.add_node("AuditLogNode", "hipaa_audit", {
    "log_categories": ["phi_access", "hipaa_compliance", "security_events"],
    "retention_days": 2190,  # 6 years per HIPAA
    "immutable": True,
    "encryption": "aes-256-gcm",
    "include_fields": [
        "user_id",
        "access_time",
        "resource_accessed",
        "action_taken",
        "ip_address",
        "access_reason"
    ]
})

# Breach detection and notification
hipaa_workflow.add_node("ThreatDetectionNode", "breach_detector", {
    "detection_rules": [
        {
            "name": "unauthorized_phi_access",
            "pattern": "access_denied_repeated",
            "threshold": 3,
            "window": 300,
            "severity": "critical"
        },
        {
            "name": "bulk_data_export",
            "pattern": "large_data_transfer",
            "threshold": 1000,  # records
            "severity": "high"
        },
        {
            "name": "after_hours_access",
            "pattern": "non_business_hours",
            "severity": "medium"
        }
    ],
    "breach_response": ["notify_privacy_officer", "lock_account", "preserve_evidence"]
})
```

## 💳 PCI-DSS Compliance

### Payment Card Data Protection

```python
# PCI-DSS compliance workflow
pci_workflow = WorkflowBuilder()

# Credit card tokenization
pci_workflow.add_node("PythonCodeNode", "card_tokenizer", {
    "code": """
import hashlib
import hmac
from datetime import datetime
import re

class PCITokenizer:
    def __init__(self, master_key: str):
        self.master_key = master_key.encode()

    def tokenize_card(self, card_number: str) -> dict:
        # Validate card number
        card_number = re.sub(r'\\s|-', '', card_number)
        if not self.validate_card_number(card_number):
            raise ValueError("Invalid card number")

        # Generate token
        token = self.generate_token(card_number)

        # Store mapping securely (in practice, use HSM)
        token_mapping = {
            'token': token,
            'first_six': card_number[:6],
            'last_four': card_number[-4:],
            'card_type': self.detect_card_type(card_number),
            'created_at': datetime.now().isoformat(),
            'expires_at': None  # Set based on business rules
        }

        return token_mapping

    def generate_token(self, card_number: str) -> str:
        # Generate format-preserving token
        h = hmac.new(self.master_key, card_number.encode(), hashlib.sha256)
        token_bytes = h.digest()

        # Convert to numeric token preserving length
        token_int = int.from_bytes(token_bytes[:8], 'big')
        token = str(token_int)[:len(card_number)].zfill(len(card_number))

        return token

    def validate_card_number(self, card_number: str) -> bool:
        # Luhn algorithm
        def luhn_checksum(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]
            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10

        return luhn_checksum(card_number) == 0

    def detect_card_type(self, card_number: str) -> str:
        patterns = {
            'visa': r'^4[0-9]{12}(?:[0-9]{3})?$',
            'mastercard': r'^5[1-5][0-9]{14}$',
            'amex': r'^3[47][0-9]{13}$',
            'discover': r'^6(?:011|5[0-9]{2})[0-9]{12}$'
        }

        for card_type, pattern in patterns.items():
            if re.match(pattern, card_number):
                return card_type
        return 'unknown'

# Process payment data
tokenizer = PCITokenizer(tokenization_key)

# Never store raw card data
if 'card_number' in payment_data:
    token_info = tokenizer.tokenize_card(payment_data['card_number'])
    # Replace card number with token
    payment_data['payment_token'] = token_info['token']
    payment_data['card_last_four'] = token_info['last_four']
    payment_data['card_type'] = token_info['card_type']
    del payment_data['card_number']  # Remove sensitive data

result = {
    'tokenized': True,
    'payment_data': payment_data,
    'pci_compliance': {
        'encryption': 'tokenization',
        'storage': 'token_vault',
        'transmission': 'tls_1_3',
        'access_control': 'role_based'
    }
}
"""
})

# Network segmentation check
pci_workflow.add_node("PythonCodeNode", "network_validator", {
    "code": """
import ipaddress
from typing import Dict, List

# Define PCI network zones
PCI_ZONES = {
    'cardholder_data_environment': {
        'networks': [ipaddress.ip_network('10.1.0.0/16')],
        'allowed_services': ['payment_processor', 'token_vault'],
        'security_level': 'critical'
    },
    'dmz': {
        'networks': [ipaddress.ip_network('10.2.0.0/16')],
        'allowed_services': ['web_server', 'api_gateway'],
        'security_level': 'high'
    },
    'internal': {
        'networks': [ipaddress.ip_network('10.3.0.0/16')],
        'allowed_services': ['application_server', 'database'],
        'security_level': 'medium'
    },
    'management': {
        'networks': [ipaddress.ip_network('10.4.0.0/16')],
        'allowed_services': ['monitoring', 'logging'],
        'security_level': 'high'
    }
}

def validate_network_segmentation(source_ip: str, dest_ip: str, service: str) -> Dict:
    source_addr = ipaddress.ip_address(source_ip)
    dest_addr = ipaddress.ip_address(dest_ip)

    source_zone = None
    dest_zone = None

    # Identify zones
    for zone_name, zone_config in PCI_ZONES.items():
        for network in zone_config['networks']:
            if source_addr in network:
                source_zone = zone_name
            if dest_addr in network:
                dest_zone = zone_name

    # Check if communication is allowed
    allowed = False
    reason = "unknown"

    if source_zone == 'cardholder_data_environment':
        # CDE can only communicate with specific services
        if dest_zone == 'dmz' and service == 'payment_processor':
            allowed = True
            reason = "authorized_payment_processing"
        else:
            allowed = False
            reason = "cde_isolation_policy"
    elif source_zone == 'dmz' and dest_zone == 'internal':
        # DMZ to internal allowed for specific services
        if service in ['api_gateway', 'web_application']:
            allowed = True
            reason = "dmz_to_internal_allowed"

    return {
        'allowed': allowed,
        'source_zone': source_zone,
        'dest_zone': dest_zone,
        'reason': reason,
        'pci_requirement': '1.3.1',
        'log_required': True
    }

# Validate network communication
validation_result = validate_network_segmentation(
    request_source_ip,
    request_dest_ip,
    request_service
)

result = validation_result
"""
})
```

## 📊 SOX Compliance

### Financial Controls and Audit

```python
# SOX compliance workflow
sox_workflow = WorkflowBuilder()

# Financial data integrity checks
sox_workflow.add_node("PythonCodeNode", "financial_controls", {
    "code": """
import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json

class SOXFinancialControls:
    def __init__(self):
        self.control_log = []

    def validate_transaction(self, transaction: dict) -> dict:
        validations = {
            'segregation_of_duties': self.check_segregation_of_duties(transaction),
            'authorization_limits': self.check_authorization_limits(transaction),
            'data_integrity': self.verify_data_integrity(transaction),
            'audit_trail': self.create_audit_trail(transaction)
        }

        all_valid = all(v['valid'] for v in validations.values())

        return {
            'valid': all_valid,
            'validations': validations,
            'control_id': self.generate_control_id(transaction)
        }

    def check_segregation_of_duties(self, transaction: dict) -> dict:
        # Ensure creator and approver are different
        creator = transaction.get('created_by')
        approver = transaction.get('approved_by')

        if creator == approver:
            return {
                'valid': False,
                'control': 'segregation_of_duties',
                'reason': 'same_person_created_and_approved'
            }

        # Check if both have appropriate roles
        creator_role = transaction.get('creator_role')
        approver_role = transaction.get('approver_role')

        valid_combinations = {
            ('accountant', 'manager'),
            ('analyst', 'director'),
            ('manager', 'executive')
        }

        if (creator_role, approver_role) not in valid_combinations:
            return {
                'valid': False,
                'control': 'segregation_of_duties',
                'reason': 'invalid_role_combination'
            }

        return {'valid': True, 'control': 'segregation_of_duties'}

    def check_authorization_limits(self, transaction: dict) -> dict:
        amount = Decimal(str(transaction.get('amount', 0)))
        approver_role = transaction.get('approver_role')

        limits = {
            'accountant': Decimal('10000'),
            'manager': Decimal('50000'),
            'director': Decimal('250000'),
            'executive': Decimal('1000000')
        }

        approver_limit = limits.get(approver_role, Decimal('0'))

        if amount > approver_limit:
            return {
                'valid': False,
                'control': 'authorization_limits',
                'reason': f'amount_exceeds_limit',
                'amount': str(amount),
                'limit': str(approver_limit)
            }

        return {'valid': True, 'control': 'authorization_limits'}

    def verify_data_integrity(self, transaction: dict) -> dict:
        # Calculate transaction hash
        tx_data = {
            'id': transaction['id'],
            'amount': str(transaction['amount']),
            'date': transaction['date'],
            'account_debit': transaction['account_debit'],
            'account_credit': transaction['account_credit']
        }

        calculated_hash = hashlib.sha256(
            json.dumps(tx_data, sort_keys=True).encode()
        ).hexdigest()

        stored_hash = transaction.get('integrity_hash')

        if stored_hash and calculated_hash != stored_hash:
            return {
                'valid': False,
                'control': 'data_integrity',
                'reason': 'hash_mismatch',
                'potential_tampering': True
            }

        return {
            'valid': True,
            'control': 'data_integrity',
            'hash': calculated_hash
        }

    def create_audit_trail(self, transaction: dict) -> dict:
        audit_entry = {
            'transaction_id': transaction['id'],
            'timestamp': datetime.now().isoformat(),
            'action': 'validate_transaction',
            'user': transaction.get('current_user'),
            'ip_address': transaction.get('ip_address'),
            'changes': transaction.get('changes', []),
            'sox_controls_applied': [
                'segregation_of_duties',
                'authorization_limits',
                'data_integrity'
            ]
        }

        self.control_log.append(audit_entry)

        return {
            'valid': True,
            'control': 'audit_trail',
            'entry_id': len(self.control_log) - 1
        }

    def generate_control_id(self, transaction: dict) -> str:
        return f"SOX-{datetime.now().strftime('%Y%m%d')}-{transaction['id']}"

# Apply SOX controls
controls = SOXFinancialControls()
validation_result = controls.validate_transaction(financial_transaction)

result = {
    'validation': validation_result,
    'sox_compliant': validation_result['valid'],
    'remediation_required': not validation_result['valid'],
    'audit_log': controls.control_log
}
"""
})

# Change management controls
sox_workflow.add_node("PythonCodeNode", "change_management", {
    "code": """
from datetime import datetime
import json

# IT change management for SOX compliance
class ChangeManagement:
    def __init__(self):
        self.change_log = []

    def validate_change_request(self, change_request: dict) -> dict:
        validations = []

        # Required fields check
        required_fields = [
            'change_id', 'description', 'risk_level',
            'business_justification', 'rollback_plan',
            'testing_evidence', 'approvals'
        ]

        for field in required_fields:
            if field not in change_request or not change_request[field]:
                validations.append({
                    'check': f'required_field_{field}',
                    'passed': False,
                    'reason': f'{field} is missing or empty'
                })
            else:
                validations.append({
                    'check': f'required_field_{field}',
                    'passed': True
                })

        # Risk-based approval requirements
        risk_level = change_request.get('risk_level', 'high')
        required_approvals = {
            'low': ['team_lead'],
            'medium': ['team_lead', 'manager'],
            'high': ['team_lead', 'manager', 'director'],
            'critical': ['team_lead', 'manager', 'director', 'ciso']
        }

        actual_approvals = [a['role'] for a in change_request.get('approvals', [])]
        needed_approvals = required_approvals.get(risk_level, [])

        missing_approvals = set(needed_approvals) - set(actual_approvals)
        if missing_approvals:
            validations.append({
                'check': 'approval_requirements',
                'passed': False,
                'reason': f'Missing approvals from: {missing_approvals}'
            })
        else:
            validations.append({
                'check': 'approval_requirements',
                'passed': True
            })

        # Testing evidence validation
        testing_evidence = change_request.get('testing_evidence', {})
        if risk_level in ['high', 'critical']:
            required_tests = ['unit_tests', 'integration_tests', 'security_scan']
            for test in required_tests:
                if test not in testing_evidence or not testing_evidence[test]['passed']:
                    validations.append({
                        'check': f'testing_{test}',
                        'passed': False,
                        'reason': f'{test} not passed or missing'
                    })

        all_passed = all(v['passed'] for v in validations)

        # Log the change request
        self.change_log.append({
            'change_id': change_request['change_id'],
            'timestamp': datetime.now().isoformat(),
            'validation_result': all_passed,
            'validations': validations,
            'sox_section': '404'
        })

        return {
            'approved': all_passed,
            'validations': validations,
            'change_log_id': len(self.change_log) - 1,
            'sox_requirements_met': all_passed
        }

# Process change request
cm = ChangeManagement()
change_validation = cm.validate_change_request(it_change_request)

result = {
    'change_approved': change_validation['approved'],
    'validation_details': change_validation,
    'sox_404_compliant': change_validation['sox_requirements_met'],
    'audit_trail': cm.change_log
}
"""
})
```

## 🔍 Compliance Monitoring

### Automated Compliance Checks

```python
# Comprehensive compliance monitoring
monitoring_workflow = WorkflowBuilder()

# Multi-regulation compliance scanner
monitoring_workflow.add_node("PythonCodeNode", "compliance_scanner", {
    "code": """
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

class ComplianceScanner:
    def __init__(self):
        self.regulations = ['GDPR', 'HIPAA', 'PCI-DSS', 'SOX']
        self.scan_results = []

    def scan_system(self, system_config: dict) -> dict:
        results = {}

        for regulation in self.regulations:
            if regulation == 'GDPR':
                results['GDPR'] = self.scan_gdpr(system_config)
            elif regulation == 'HIPAA':
                results['HIPAA'] = self.scan_hipaa(system_config)
            elif regulation == 'PCI-DSS':
                results['PCI-DSS'] = self.scan_pci(system_config)
            elif regulation == 'SOX':
                results['SOX'] = self.scan_sox(system_config)

        # Calculate overall compliance score
        total_checks = sum(r['total_checks'] for r in results.values())
        passed_checks = sum(r['passed_checks'] for r in results.values())
        compliance_score = (passed_checks / total_checks * 100) if total_checks > 0 else 0

        scan_result = {
            'scan_id': f"SCAN-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'timestamp': datetime.now().isoformat(),
            'regulations': results,
            'overall_score': round(compliance_score, 2),
            'status': 'compliant' if compliance_score >= 95 else 'non_compliant',
            'critical_issues': self.extract_critical_issues(results)
        }

        self.scan_results.append(scan_result)
        return scan_result

    def scan_gdpr(self, config: dict) -> dict:
        checks = {
            'data_encryption': config.get('encryption', {}).get('at_rest', False),
            'consent_management': config.get('consent_system', False),
            'data_retention_policy': config.get('retention_policy', False),
            'right_to_erasure': config.get('data_deletion_api', False),
            'data_portability': config.get('export_api', False),
            'privacy_by_design': config.get('privacy_settings', {}).get('default', 'opt_in') == 'opt_in',
            'dpo_appointed': config.get('data_protection_officer', False),
            'impact_assessments': config.get('dpia_completed', False)
        }

        passed = sum(checks.values())
        issues = [k for k, v in checks.items() if not v]

        return {
            'total_checks': len(checks),
            'passed_checks': passed,
            'compliance_percentage': (passed / len(checks) * 100),
            'failed_checks': issues,
            'severity': 'critical' if len(issues) > 3 else 'medium'
        }

    def scan_hipaa(self, config: dict) -> dict:
        checks = {
            'phi_encryption': config.get('phi_encryption', False),
            'access_controls': config.get('role_based_access', False),
            'audit_logging': config.get('audit_trail', False),
            'minimum_necessary': config.get('data_minimization', False),
            'business_associates': config.get('baa_agreements', False),
            'incident_response': config.get('breach_notification', False),
            'physical_safeguards': config.get('physical_security', False),
            'workforce_training': config.get('hipaa_training', False)
        }

        passed = sum(checks.values())
        issues = [k for k, v in checks.items() if not v]

        return {
            'total_checks': len(checks),
            'passed_checks': passed,
            'compliance_percentage': (passed / len(checks) * 100),
            'failed_checks': issues,
            'severity': 'critical' if 'phi_encryption' in issues else 'high'
        }

    def scan_pci(self, config: dict) -> dict:
        checks = {
            'network_segmentation': config.get('network_zones', False),
            'cardholder_encryption': config.get('card_tokenization', False),
            'secure_development': config.get('secure_sdlc', False),
            'vulnerability_scanning': config.get('vuln_scans', False),
            'access_restriction': config.get('need_to_know_access', False),
            'monitoring_logging': config.get('security_monitoring', False),
            'security_testing': config.get('penetration_testing', False),
            'incident_response': config.get('ir_plan', False),
            'vendor_management': config.get('vendor_assessments', False),
            'security_policies': config.get('security_documentation', False)
        }

        passed = sum(checks.values())
        issues = [k for k, v in checks.items() if not v]

        return {
            'total_checks': len(checks),
            'passed_checks': passed,
            'compliance_percentage': (passed / len(checks) * 100),
            'failed_checks': issues,
            'severity': 'critical' if 'cardholder_encryption' in issues else 'high'
        }

    def scan_sox(self, config: dict) -> dict:
        checks = {
            'financial_controls': config.get('internal_controls', False),
            'segregation_duties': config.get('role_separation', False),
            'change_management': config.get('change_control', False),
            'access_reviews': config.get('periodic_access_review', False),
            'data_integrity': config.get('transaction_validation', False),
            'audit_trail': config.get('comprehensive_logging', False),
            'management_assessment': config.get('control_testing', False),
            'documentation': config.get('process_documentation', False)
        }

        passed = sum(checks.values())
        issues = [k for k, v in checks.items() if not v]

        return {
            'total_checks': len(checks),
            'passed_checks': passed,
            'compliance_percentage': (passed / len(checks) * 100),
            'failed_checks': issues,
            'severity': 'high' if len(issues) > 2 else 'medium'
        }

    def extract_critical_issues(self, results: dict) -> List[dict]:
        critical_issues = []

        for regulation, result in results.items():
            if result['severity'] in ['critical', 'high']:
                for issue in result['failed_checks']:
                    critical_issues.append({
                        'regulation': regulation,
                        'issue': issue,
                        'severity': result['severity'],
                        'remediation_priority': 'immediate' if result['severity'] == 'critical' else 'high'
                    })

        return critical_issues

# Run compliance scan
scanner = ComplianceScanner()
scan_results = scanner.scan_system(system_configuration)

result = {
    'compliance_scan': scan_results,
    'remediation_required': scan_results['status'] != 'compliant',
    'next_scan_due': (datetime.now() + timedelta(days=30)).isoformat()
}
"""
})

# Compliance reporting
monitoring_workflow.add_node("PythonCodeNode", "compliance_reporter", {
    "code": """
from datetime import datetime
import json

def generate_compliance_report(scan_results: dict) -> dict:
    report = {
        'report_id': f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'generated_at': datetime.now().isoformat(),
        'reporting_period': {
            'start': datetime.now().replace(day=1).isoformat(),
            'end': datetime.now().isoformat()
        },
        'executive_summary': {
            'overall_compliance_score': scan_results['overall_score'],
            'status': scan_results['status'],
            'critical_issues_count': len(scan_results['critical_issues']),
            'regulations_covered': list(scan_results['regulations'].keys())
        },
        'detailed_findings': {}
    }

    # Add detailed findings for each regulation
    for regulation, results in scan_results['regulations'].items():
        report['detailed_findings'][regulation] = {
            'compliance_percentage': results['compliance_percentage'],
            'passed_controls': results['passed_checks'],
            'total_controls': results['total_checks'],
            'gaps_identified': results['failed_checks'],
            'risk_level': results['severity'],
            'recommendations': generate_recommendations(regulation, results['failed_checks'])
        }

    # Add remediation plan
    report['remediation_plan'] = {
        'immediate_actions': [
            issue for issue in scan_results['critical_issues']
            if issue['remediation_priority'] == 'immediate'
        ],
        'short_term_actions': [
            issue for issue in scan_results['critical_issues']
            if issue['remediation_priority'] == 'high'
        ],
        'estimated_completion': '30_days'
    }

    # Add attestation section
    report['attestation'] = {
        'prepared_by': 'compliance_team',
        'reviewed_by': 'chief_compliance_officer',
        'approved_by': None,  # Requires manual approval
        'certification_statement': 'This report accurately reflects the compliance status as of the date generated.'
    }

    return report

def generate_recommendations(regulation: str, gaps: List[str]) -> List[dict]:
    recommendations = []

    recommendation_map = {
        'GDPR': {
            'data_encryption': {
                'action': 'Implement AES-256 encryption for all personal data at rest',
                'priority': 'critical',
                'estimated_effort': '2_weeks'
            },
            'consent_management': {
                'action': 'Deploy consent management platform with granular controls',
                'priority': 'high',
                'estimated_effort': '4_weeks'
            }
        },
        'HIPAA': {
            'phi_encryption': {
                'action': 'Enable end-to-end encryption for all PHI data',
                'priority': 'critical',
                'estimated_effort': '3_weeks'
            },
            'audit_logging': {
                'action': 'Implement comprehensive audit trail for PHI access',
                'priority': 'high',
                'estimated_effort': '2_weeks'
            }
        }
    }

    for gap in gaps:
        if regulation in recommendation_map and gap in recommendation_map[regulation]:
            recommendations.append(recommendation_map[regulation][gap])
        else:
            recommendations.append({
                'action': f'Address {gap} to meet {regulation} requirements',
                'priority': 'medium',
                'estimated_effort': 'tbd'
            })

    return recommendations

# Generate compliance report
compliance_report = generate_compliance_report(scan_results)

result = {
    'report': compliance_report,
    'distribution_list': ['cco@company.com', 'ciso@company.com', 'cfo@company.com'],
    'next_report_due': '2024-02-01'
}
"""
})
```

## 📚 Compliance Best Practices

### Essential Compliance Patterns
- [ ] **Data Privacy**: GDPR compliance with consent management
- [ ] **Healthcare**: HIPAA safeguards for PHI protection
- [ ] **Payment Security**: PCI-DSS tokenization and segmentation
- [ ] **Financial Controls**: SOX compliance for financial integrity
- [ ] **Audit Trails**: Immutable logging for all regulations
- [ ] **Access Controls**: Role-based permissions with least privilege
- [ ] **Data Retention**: Automated policies per regulation
- [ ] **Incident Response**: Breach notification procedures
- [ ] **Compliance Monitoring**: Automated scanning and reporting
- [ ] **Documentation**: Maintain evidence for audits

### Compliance Implementation Checklist
- **Risk Assessment**: Identify applicable regulations
- **Gap Analysis**: Compare current state vs requirements
- **Control Implementation**: Deploy technical controls
- **Policy Development**: Create compliance policies
- **Training Program**: Educate staff on requirements
- **Monitoring Setup**: Continuous compliance checking
- **Audit Preparation**: Maintain documentation
- **Incident Response**: Test breach procedures
- **Third-Party Management**: Vendor compliance verification
- **Regular Reviews**: Quarterly compliance assessments

### Related Enterprise Guides
- **[Security Patterns](security-patterns.md)** - Authentication and authorization
- **[Gateway Patterns](gateway-patterns.md)** - API gateway and integration
- **[Production Patterns](production-patterns.md)** - Deployment and scaling
- **[Middleware Patterns](middleware-patterns.md)** - Advanced middleware setup

---

**Ready for compliance?** Start with a compliance scan, implement critical controls, then establish continuous monitoring and regular audits.

# Security & Authentication Patterns

**Complete guide to security workflows** - From authentication flows to enterprise compliance with GDPR, HIPAA, and SOX.

## 📋 Pattern Overview

Security workflows provide:
- **Authentication & Authorization**: User verification and access control
- **Data Protection**: Encryption, PII handling, privacy compliance
- **Audit & Compliance**: Security logging, regulatory requirements
- **Threat Detection**: Anomaly detection, incident response
- **Secure Communication**: TLS, encryption, secure data transfer

## 🚀 Quick Start Examples

### 30-Second JWT Authentication
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.api import RestClientNode
from kailash.runtime.local import LocalRuntime

# JWT authentication workflow
workflow = WorkflowBuilder()

# Token validator
workflow.add_node("PythonCodeNode", "token_validator", {}):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.validation_errors = []

    def validate_token(self, token, required_claims=None):
        """Validate JWT token with comprehensive security checks."""

        if not token:
            return {
                "valid": False,
                "error": "No token provided",
                "security_event": "missing_token"
            }

        try:
            # Decode and validate token
            decoded_token = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "require_exp": True,
                    "require_iat": True
                }
            )

            # Validate required claims
            if required_claims:
                missing_claims = [claim for claim in required_claims
                                if claim not in decoded_token]
                if missing_claims:
                    return {
                        "valid": False,
                        "error": f"Missing required claims: {missing_claims}",
                        "security_event": "invalid_claims"
                    }

            # Additional security validations
            security_checks = self.perform_security_checks(decoded_token)

            return {
                "valid": True,
                "user_id": decoded_token.get("sub"),
                "username": decoded_token.get("username"),
                "roles": decoded_token.get("roles", []),
                "permissions": decoded_token.get("permissions", []),
                "expires_at": decoded_token.get("exp"),
                "issued_at": decoded_token.get("iat"),
                "security_checks": security_checks,
                "decoded_claims": decoded_token
            }

        except jwt.ExpiredSignatureError:
            return {
                "valid": False,
                "error": "Token has expired",
                "security_event": "expired_token"
            }
        except jwt.InvalidTokenError as e:
            return {
                "valid": False,
                "error": f"Invalid token: {str(e)}",
                "security_event": "invalid_token"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Token validation error: {str(e)}",
                "security_event": "validation_error"
            }

    def perform_security_checks(self, decoded_token):
        """Perform additional security validations."""

        checks = {
            "token_age_valid": True,
            "issuer_valid": True,
            "audience_valid": True,
            "scope_valid": True
        }

        # Check token age (not too old even if not expired)
        if "iat" in decoded_token:
            token_age = datetime.datetime.utcnow().timestamp() - decoded_token["iat"]
            if token_age > 86400:  # 24 hours
                checks["token_age_valid"] = False

        # Validate issuer if present
        if "iss" in decoded_token:
            expected_issuer = "your-auth-service"
            checks["issuer_valid"] = decoded_token["iss"] == expected_issuer

        # Validate audience if present
        if "aud" in decoded_token:
            expected_audience = "your-api"
            checks["audience_valid"] = decoded_token["aud"] == expected_audience

        return checks

# Validate incoming token
validator = JWTTokenValidator(secret_key="your-secret-key")
validation_result = validator.validate_token(
    auth_token,
    required_claims=["sub", "username", "roles"]
)

result = validation_result
'''
))

workflow.add_connection("token_validator", "user_authorizer", "result", "auth_data")

# Execute with token
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "token_validator": {
        "auth_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    }
})

```

## 🔐 Advanced Authentication Patterns

### Multi-Factor Authentication (MFA) Workflow
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

workflow = WorkflowBuilder()

# MFA orchestrator
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.mfa_methods = {
            'totp': self.validate_totp,
            'sms': self.validate_sms,
            'email': self.validate_email,
            'push': self.validate_push_notification,
            'backup_codes': self.validate_backup_code
        }
        self.session_cache = {}

    def initiate_mfa_flow(self, user_data, mfa_preferences):
        """Initiate multi-factor authentication flow."""

        user_id = user_data.get("user_id")
        if not user_id:
            return {"error": "Invalid user data"}

        # Determine required MFA methods based on risk score
        risk_score = self.calculate_risk_score(user_data)
        required_factors = self.determine_required_factors(risk_score, mfa_preferences)

        # Generate session for MFA flow
        mfa_session = {
            "session_id": secrets.token_urlsafe(32),
            "user_id": user_id,
            "risk_score": risk_score,
            "required_factors": required_factors,
            "completed_factors": [],
            "attempts": 0,
            "max_attempts": 3,
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }

        self.session_cache[mfa_session["session_id"]] = mfa_session

        # Prepare challenges for each required factor
        challenges = {}
        for factor in required_factors:
            challenges[factor] = self.prepare_challenge(factor, user_data)

        return {
            "mfa_session_id": mfa_session["session_id"],
            "required_factors": required_factors,
            "challenges": challenges,
            "risk_level": self.get_risk_level(risk_score),
            "expires_at": mfa_session["expires_at"]
        }

    def calculate_risk_score(self, user_data):
        """Calculate authentication risk score."""

        risk_factors = {
            "new_device": 15,
            "new_location": 20,
            "suspicious_activity": 25,
            "high_privilege_user": 10,
            "off_hours_access": 5,
            "failed_attempts": 30
        }

        total_risk = 0

        # Check for risk indicators
        if user_data.get("device_fingerprint") not in user_data.get("known_devices", []):
            total_risk += risk_factors["new_device"]

        if user_data.get("ip_location") != user_data.get("usual_location"):
            total_risk += risk_factors["new_location"]

        if user_data.get("roles", []) and any(role in ["admin", "supervisor"] for role in user_data["roles"]):
            total_risk += risk_factors["high_privilege_user"]

        # Time-based risk
        current_hour = datetime.utcnow().hour
        if current_hour < 6 or current_hour > 22:  # Outside business hours
            total_risk += risk_factors["off_hours_access"]

        return min(100, total_risk)  # Cap at 100

    def determine_required_factors(self, risk_score, preferences):
        """Determine required MFA factors based on risk."""

        factors = []

        # Always require at least one factor
        if "totp" in preferences:
            factors.append("totp")
        elif "sms" in preferences:
            factors.append("sms")
        else:
            factors.append("email")  # Fallback

        # High risk requires additional factors
        if risk_score >= 50:
            if "push" in preferences:
                factors.append("push")
            else:
                factors.append("email")

        # Very high risk requires three factors
        if risk_score >= 75:
            if "sms" not in factors and "sms" in preferences:
                factors.append("sms")

        return list(set(factors))  # Remove duplicates

    def prepare_challenge(self, factor_type, user_data):
        """Prepare challenge for specific MFA factor."""

        if factor_type == "totp":
            return {
                "type": "totp",
                "instruction": "Enter the 6-digit code from your authenticator app",
                "setup_required": not user_data.get("totp_secret")
            }

        elif factor_type == "sms":
            # Generate and send SMS code
            sms_code = f"{secrets.randbelow(900000) + 100000:06d}"
            phone = user_data.get("phone_number", "")[-4:]  # Mask phone number
            return {
                "type": "sms",
                "instruction": f"Enter the code sent to ***-***-{phone}",
                "code_sent": True,
                "challenge_data": hashlib.sha256(sms_code.encode()).hexdigest()  # Store hash
            }

        elif factor_type == "email":
            # Generate and send email code
            email_code = f"{secrets.randbelow(900000) + 100000:06d}"
            email = user_data.get("email", "")
            masked_email = email[:2] + "***@" + email.split("@")[1] if "@" in email else "***"
            return {
                "type": "email",
                "instruction": f"Enter the code sent to {masked_email}",
                "code_sent": True,
                "challenge_data": hashlib.sha256(email_code.encode()).hexdigest()
            }

        elif factor_type == "push":
            return {
                "type": "push",
                "instruction": "Approve the push notification on your registered device",
                "push_sent": True,
                "challenge_id": secrets.token_urlsafe(16)
            }

        return {"type": factor_type, "instruction": "Complete authentication"}

    def validate_mfa_response(self, session_id, factor_type, response_data):
        """Validate MFA response."""

        if session_id not in self.session_cache:
            return {
                "valid": False,
                "error": "Invalid or expired MFA session",
                "security_event": "invalid_mfa_session"
            }

        session = self.session_cache[session_id]

        # Check session expiry
        if datetime.utcnow() > datetime.fromisoformat(session["expires_at"]):
            del self.session_cache[session_id]
            return {
                "valid": False,
                "error": "MFA session expired",
                "security_event": "mfa_session_expired"
            }

        # Check attempt limits
        session["attempts"] += 1
        if session["attempts"] > session["max_attempts"]:
            del self.session_cache[session_id]
            return {
                "valid": False,
                "error": "Too many failed attempts",
                "security_event": "mfa_max_attempts_exceeded"
            }

        # Validate the specific factor
        if factor_type not in self.mfa_methods:
            return {
                "valid": False,
                "error": f"Unsupported MFA method: {factor_type}",
                "security_event": "unsupported_mfa_method"
            }

        validation_result = self.mfa_methods[factor_type](response_data, session)

        if validation_result["valid"]:
            # Mark factor as completed
            if factor_type not in session["completed_factors"]:
                session["completed_factors"].append(factor_type)

            # Check if all required factors are completed
            all_completed = all(factor in session["completed_factors"]
                              for factor in session["required_factors"])

            if all_completed:
                # MFA flow complete
                del self.session_cache[session_id]
                return {
                    "valid": True,
                    "mfa_completed": True,
                    "user_id": session["user_id"],
                    "risk_score": session["risk_score"],
                    "factors_used": session["completed_factors"]
                }
            else:
                # More factors required
                remaining_factors = [f for f in session["required_factors"]
                                   if f not in session["completed_factors"]]
                return {
                    "valid": True,
                    "mfa_completed": False,
                    "remaining_factors": remaining_factors,
                    "completed_factors": session["completed_factors"]
                }

        return validation_result

    def validate_totp(self, response_data, session):
        """Validate TOTP code."""

        code = response_data.get("code", "")
        if not code or len(code) != 6:
            return {
                "valid": False,
                "error": "Invalid TOTP code format",
                "security_event": "invalid_totp_format"
            }

        # In production, get TOTP secret from secure user storage
        totp_secret = "JBSWY3DPEHPK3PXP"  # Example secret
        totp = pyotp.TOTP(totp_secret)

        # Verify with time window tolerance
        if totp.verify(code, valid_window=1):
            return {
                "valid": True,
                "factor_type": "totp",
                "verified_at": datetime.utcnow().isoformat()
            }

        return {
            "valid": False,
            "error": "Invalid TOTP code",
            "security_event": "invalid_totp_code"
        }

    def validate_sms(self, response_data, session):
        """Validate SMS code."""

        code = response_data.get("code", "")
        expected_hash = response_data.get("challenge_data", "")

        if hashlib.sha256(code.encode()).hexdigest() == expected_hash:
            return {
                "valid": True,
                "factor_type": "sms",
                "verified_at": datetime.utcnow().isoformat()
            }

        return {
            "valid": False,
            "error": "Invalid SMS code",
            "security_event": "invalid_sms_code"
        }

    def validate_email(self, response_data, session):
        """Validate email code."""

        code = response_data.get("code", "")
        expected_hash = response_data.get("challenge_data", "")

        if hashlib.sha256(code.encode()).hexdigest() == expected_hash:
            return {
                "valid": True,
                "factor_type": "email",
                "verified_at": datetime.utcnow().isoformat()
            }

        return {
            "valid": False,
            "error": "Invalid email code",
            "security_event": "invalid_email_code"
        }

    def validate_push_notification(self, response_data, session):
        """Validate push notification response."""

        approved = response_data.get("approved", False)
        challenge_id = response_data.get("challenge_id", "")

        if approved and challenge_id:
            return {
                "valid": True,
                "factor_type": "push",
                "verified_at": datetime.utcnow().isoformat()
            }

        return {
            "valid": False,
            "error": "Push notification not approved",
            "security_event": "push_notification_denied"
        }

    def validate_backup_code(self, response_data, session):
        """Validate backup recovery code."""

        code = response_data.get("backup_code", "")
        # In production, check against stored backup codes
        # and mark as used to prevent reuse

        return {
            "valid": False,
            "error": "Backup code validation not implemented",
            "security_event": "backup_code_attempted"
        }

    def get_risk_level(self, risk_score):
        """Convert risk score to level."""
        if risk_score >= 75:
            return "HIGH"
        elif risk_score >= 50:
            return "MEDIUM"
        elif risk_score >= 25:
            return "LOW"
        else:
            return "MINIMAL"

# Initialize MFA flow
mfa_system = MultiFactorAuthenticator()
mfa_result = mfa_system.initiate_mfa_flow(user_data, mfa_preferences)

result = mfa_result
'''
))

```

## 🛡️ Data Privacy & Protection Patterns

### GDPR/HIPAA Compliance Workflow
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

workflow = WorkflowBuilder()

# Data privacy processor
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.encryption_key = encryption_key or Fernet.generate_key()
        self.cipher_suite = Fernet(self.encryption_key)

        # PII patterns for detection
        self.pii_patterns = {
            'ssn': r'\\b\\d{3}-?\\d{2}-?\\d{4}\\b',
            'credit_card': r'\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b',
            'email': r'\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b',
            'phone': r'\\b\\d{3}[-.\\s]?\\d{3}[-.\\s]?\\d{4}\\b',
            'passport': r'\\b[A-Z]{1,2}\\d{6,9}\\b',
            'medical_record': r'\\b(MRN|mrn)\\s*:?\\s*\\d+\\b',
            'iban': r'\\b[A-Z]{2}\\d{2}[A-Z0-9]{4}\\d{7}([A-Z0-9]?){0,16}\\b'
        }

        self.processing_purposes = {
            'analytics': 'Data analysis and business intelligence',
            'marketing': 'Marketing communications and campaigns',
            'support': 'Customer support and service delivery',
            'legal': 'Legal compliance and regulatory requirements',
            'security': 'Security monitoring and fraud prevention'
        }

    def process_data_request(self, data, processing_purpose, consent_data, retention_policy):
        """Process data according to privacy regulations."""

        # Validate consent and legal basis
        consent_validation = self.validate_consent(consent_data, processing_purpose)
        if not consent_validation['valid']:
            return {
                "error": "Invalid consent for data processing",
                "consent_validation": consent_validation,
                "data_processed": False
            }

        # Detect and classify PII
        pii_detection = self.detect_pii(data)

        # Apply data minimization
        minimized_data = self.apply_data_minimization(data, processing_purpose)

        # Apply anonymization/pseudonymization if required
        privacy_enhanced_data = self.apply_privacy_enhancement(
            minimized_data,
            pii_detection,
            processing_purpose
        )

        # Set retention period
        retention_info = self.set_retention_period(retention_policy, processing_purpose)

        # Create processing record for audit
        processing_record = self.create_processing_record(
            data,
            processing_purpose,
            consent_data,
            pii_detection,
            retention_info
        )

        return {
            "processed_data": privacy_enhanced_data,
            "pii_detection": pii_detection,
            "consent_validation": consent_validation,
            "retention_info": retention_info,
            "processing_record": processing_record,
            "compliance_status": "GDPR_HIPAA_COMPLIANT",
            "data_processed": True
        }

    def validate_consent(self, consent_data, processing_purpose):
        """Validate GDPR consent requirements."""

        required_elements = [
            'consent_given',
            'consent_timestamp',
            'data_subject_id',
            'processing_purposes',
            'consent_method'
        ]

        # Check all required elements are present
        missing_elements = [elem for elem in required_elements
                          if elem not in consent_data]

        if missing_elements:
            return {
                "valid": False,
                "error": f"Missing consent elements: {missing_elements}",
                "compliance_issue": "incomplete_consent"
            }

        # Validate consent is for current purpose
        if processing_purpose not in consent_data.get('processing_purposes', []):
            return {
                "valid": False,
                "error": f"No consent for purpose: {processing_purpose}",
                "compliance_issue": "purpose_not_consented"
            }

        # Check consent is not expired (GDPR doesn't specify, but best practice)
        consent_date = datetime.fromisoformat(consent_data['consent_timestamp'])
        if datetime.utcnow() - consent_date > timedelta(days=365*2):  # 2 years
            return {
                "valid": False,
                "error": "Consent may be stale (>2 years old)",
                "compliance_issue": "stale_consent"
            }

        # Validate consent was freely given (not pre-checked, etc.)
        if consent_data.get('consent_method') == 'pre_checked':
            return {
                "valid": False,
                "error": "Consent cannot be pre-checked under GDPR",
                "compliance_issue": "invalid_consent_method"
            }

        return {
            "valid": True,
            "consent_verified": True,
            "legal_basis": "consent",
            "purpose_approved": processing_purpose
        }

    def detect_pii(self, data):
        """Detect personally identifiable information."""

        if isinstance(data, dict):
            text_data = str(data)
        else:
            text_data = str(data)

        detected_pii = {}
        pii_count = 0

        for pii_type, pattern in self.pii_patterns.items():
            matches = re.findall(pattern, text_data, re.IGNORECASE)
            if matches:
                detected_pii[pii_type] = {
                    'count': len(matches),
                    'samples': matches[:3],  # Store max 3 samples
                    'risk_level': self.assess_pii_risk(pii_type)
                }
                pii_count += len(matches)

        return {
            "pii_detected": pii_count > 0,
            "total_pii_instances": pii_count,
            "pii_types": detected_pii,
            "risk_assessment": self.assess_overall_risk(detected_pii),
            "requires_special_handling": pii_count > 0
        }

    def assess_pii_risk(self, pii_type):
        """Assess risk level for specific PII type."""

        high_risk = ['ssn', 'credit_card', 'passport', 'medical_record']
        medium_risk = ['email', 'phone', 'iban']

        if pii_type in high_risk:
            return 'HIGH'
        elif pii_type in medium_risk:
            return 'MEDIUM'
        else:
            return 'LOW'

    def assess_overall_risk(self, detected_pii):
        """Assess overall privacy risk."""

        if not detected_pii:
            return 'MINIMAL'

        high_risk_count = sum(1 for pii_info in detected_pii.values()
                            if pii_info['risk_level'] == 'HIGH')
        medium_risk_count = sum(1 for pii_info in detected_pii.values()
                              if pii_info['risk_level'] == 'MEDIUM')

        if high_risk_count > 0:
            return 'HIGH'
        elif medium_risk_count > 2:
            return 'HIGH'
        elif medium_risk_count > 0:
            return 'MEDIUM'
        else:
            return 'LOW'

    def apply_data_minimization(self, data, processing_purpose):
        """Apply GDPR data minimization principle."""

        # Define which fields are necessary for each purpose
        purpose_field_mapping = {
            'analytics': ['user_id', 'timestamp', 'action', 'category'],
            'marketing': ['user_id', 'email', 'preferences', 'segments'],
            'support': ['user_id', 'issue', 'contact_info', 'history'],
            'legal': ['user_id', 'legal_basis', 'consent', 'retention'],
            'security': ['user_id', 'ip_address', 'session', 'security_events']
        }

        if isinstance(data, dict):
            allowed_fields = purpose_field_mapping.get(processing_purpose, list(data.keys()))
            minimized_data = {k: v for k, v in data.items() if k in allowed_fields}

            return {
                "minimized_data": minimized_data,
                "removed_fields": list(set(data.keys()) - set(allowed_fields)),
                "data_reduction_percentage":
                    round((1 - len(minimized_data) / len(data)) * 100, 2) if data else 0
            }

        return {"minimized_data": data, "removed_fields": [], "data_reduction_percentage": 0}

    def apply_privacy_enhancement(self, data, pii_detection, processing_purpose):
        """Apply anonymization/pseudonymization techniques."""

        if not pii_detection['pii_detected']:
            return {
                "enhanced_data": data,
                "enhancement_applied": "none",
                "privacy_level": "standard"
            }

        risk_level = pii_detection['risk_assessment']

        if risk_level == 'HIGH':
            # Apply strong anonymization
            enhanced_data = self.anonymize_data(data['minimized_data'])
            return {
                "enhanced_data": enhanced_data,
                "enhancement_applied": "anonymization",
                "privacy_level": "high",
                "reversible": False
            }

        elif risk_level in ['MEDIUM', 'LOW']:
            # Apply pseudonymization (reversible with key)
            enhanced_data = self.pseudonymize_data(data['minimized_data'])
            return {
                "enhanced_data": enhanced_data,
                "enhancement_applied": "pseudonymization",
                "privacy_level": "medium",
                "reversible": True
            }

        return {
            "enhanced_data": data,
            "enhancement_applied": "none",
            "privacy_level": "standard"
        }

    def anonymize_data(self, data):
        """Apply irreversible anonymization."""

        anonymized = {}

        for key, value in data.items():
            if isinstance(value, str):
                # Replace PII with hashed values
                for pii_type, pattern in self.pii_patterns.items():
                    value = re.sub(pattern, f"[ANONYMIZED_{pii_type.upper()}]", value, flags=re.IGNORECASE)
                anonymized[key] = value
            else:
                anonymized[key] = value

        return anonymized

    def pseudonymize_data(self, data):
        """Apply reversible pseudonymization."""

        pseudonymized = {}

        for key, value in data.items():
            if isinstance(value, str) and self.contains_pii(value):
                # Encrypt PII data (reversible with key)
                encrypted_value = self.cipher_suite.encrypt(value.encode()).decode()
                pseudonymized[key] = f"ENCRYPTED:{encrypted_value}"
            else:
                pseudonymized[key] = value

        return pseudonymized

    def contains_pii(self, text):
        """Check if text contains PII."""

        for pattern in self.pii_patterns.values():
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def set_retention_period(self, retention_policy, processing_purpose):
        """Set data retention period according to policy."""

        # Default retention periods by purpose (in days)
        default_retention = {
            'analytics': 1095,  # 3 years
            'marketing': 730,   # 2 years
            'support': 2555,    # 7 years
            'legal': 2555,      # 7 years
            'security': 1095    # 3 years
        }

        retention_days = retention_policy.get(
            processing_purpose,
            default_retention.get(processing_purpose, 365)
        )

        deletion_date = datetime.utcnow() + timedelta(days=retention_days)

        return {
            "retention_period_days": retention_days,
            "deletion_scheduled": deletion_date.isoformat(),
            "retention_basis": f"Purpose: {processing_purpose}",
            "auto_deletion_enabled": True
        }

    def create_processing_record(self, data, processing_purpose, consent_data, pii_detection, retention_info):
        """Create audit record for data processing."""

        return {
            "record_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().isoformat(),
            "data_subject_id": consent_data.get('data_subject_id'),
            "processing_purpose": processing_purpose,
            "legal_basis": "consent",
            "data_categories": list(pii_detection['pii_types'].keys()) if pii_detection['pii_detected'] else [],
            "data_volume": len(str(data)),
            "privacy_enhancement": "applied" if pii_detection['pii_detected'] else "none",
            "retention_period": retention_info['retention_period_days'],
            "compliance_frameworks": ["GDPR", "HIPAA"],
            "processing_location": "EU",
            "data_controller": "Your Organization",
            "audit_trail": {
                "consent_verified": True,
                "data_minimization_applied": True,
                "privacy_impact_assessed": True,
                "security_measures_applied": True
            }
        }

# Process data with privacy compliance
processor = PrivacyComplianceProcessor()

# Sample consent data
consent_data = {
    "consent_given": True,
    "consent_timestamp": "2024-01-01T10:00:00Z",
    "data_subject_id": "user_123",
    "processing_purposes": ["analytics", "support"],
    "consent_method": "explicit_checkbox"
}

# Sample retention policy
retention_policy = {
    "analytics": 365,  # 1 year for analytics
    "support": 2555    # 7 years for support
}

privacy_result = processor.process_data_request(
    user_data,
    processing_purpose,
    consent_data,
    retention_policy
)

result = privacy_result
'''
))

```

## 🔒 Access Control & Authorization

### Role-Based Access Control (RBAC)
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

workflow = WorkflowBuilder()

# RBAC engine
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.roles_hierarchy = {
            'admin': ['manager', 'user', 'viewer'],
            'manager': ['user', 'viewer'],
            'user': ['viewer'],
            'viewer': []
        }

        self.permissions_registry = {
            # User management permissions
            'users.create': ['admin'],
            'users.read': ['admin', 'manager', 'user'],
            'users.update': ['admin', 'manager'],
            'users.delete': ['admin'],

            # Data permissions
            'data.read': ['admin', 'manager', 'user', 'viewer'],
            'data.write': ['admin', 'manager', 'user'],
            'data.delete': ['admin', 'manager'],
            'data.export': ['admin', 'manager'],

            # System permissions
            'system.configure': ['admin'],
            'system.monitor': ['admin', 'manager'],
            'system.backup': ['admin'],

            # Report permissions
            'reports.view': ['admin', 'manager', 'user', 'viewer'],
            'reports.create': ['admin', 'manager', 'user'],
            'reports.share': ['admin', 'manager'],
            'reports.admin': ['admin']
        }

        self.resource_policies = {}
        self.session_cache = {}

    def authorize_request(self, user_info, requested_permission, resource_context=None):
        """Authorize user request against RBAC policies."""

        # Basic validation
        if not user_info or not requested_permission:
            return {
                "authorized": False,
                "reason": "Invalid authorization request",
                "security_event": "invalid_auth_request"
            }

        # Check if user is active
        if not user_info.get("active", True):
            return {
                "authorized": False,
                "reason": "User account is inactive",
                "security_event": "inactive_user_access_attempt"
            }

        # Get user roles
        user_roles = user_info.get("roles", [])
        if not user_roles:
            return {
                "authorized": False,
                "reason": "User has no assigned roles",
                "security_event": "no_roles_assigned"
            }

        # Check role-based permissions
        role_authorization = self.check_role_permissions(user_roles, requested_permission)

        if not role_authorization["authorized"]:
            return role_authorization

        # Check resource-specific policies
        resource_authorization = self.check_resource_policies(
            user_info, requested_permission, resource_context
        )

        if not resource_authorization["authorized"]:
            return resource_authorization

        # Check time-based restrictions
        time_authorization = self.check_temporal_restrictions(user_info, requested_permission)

        if not time_authorization["authorized"]:
            return time_authorization

        # Check additional security constraints
        security_check = self.perform_security_checks(user_info, requested_permission)

        # Log successful authorization
        self.log_authorization_event(user_info, requested_permission, True, resource_context)

        return {
            "authorized": True,
            "granted_permission": requested_permission,
            "authorization_basis": role_authorization["basis"],
            "user_id": user_info.get("user_id"),
            "session_id": user_info.get("session_id"),
            "authorized_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
            "security_checks": security_check
        }

    def check_role_permissions(self, user_roles, requested_permission):
        """Check if any user role has the requested permission."""

        # Get all effective roles (including inherited)
        effective_roles = set()
        for role in user_roles:
            effective_roles.add(role)
            effective_roles.update(self.roles_hierarchy.get(role, []))

        # Check if permission is granted to any effective role
        authorized_roles = self.permissions_registry.get(requested_permission, [])

        for role in effective_roles:
            if role in authorized_roles:
                return {
                    "authorized": True,
                    "basis": f"Role '{role}' has permission '{requested_permission}'",
                    "authorizing_role": role,
                    "all_effective_roles": list(effective_roles)
                }

        # Log failed authorization attempt
        self.log_authorization_event(
            {"roles": user_roles}, requested_permission, False, None,
            f"No role in {list(effective_roles)} has permission '{requested_permission}'"
        )

        return {
            "authorized": False,
            "reason": f"None of user roles {user_roles} have permission '{requested_permission}'",
            "required_roles": authorized_roles,
            "user_roles": user_roles,
            "security_event": "insufficient_role_permissions"
        }

    def check_resource_policies(self, user_info, permission, resource_context):
        """Check resource-specific access policies."""

        if not resource_context:
            return {"authorized": True, "basis": "No resource restrictions"}

        resource_type = resource_context.get("resource_type")
        resource_id = resource_context.get("resource_id")

        # Check data ownership policies
        if resource_type == "user_data":
            return self.check_data_ownership_policy(user_info, resource_context)

        # Check departmental access policies
        if resource_type == "department_data":
            return self.check_department_policy(user_info, resource_context)

        # Check project-based access
        if resource_type == "project":
            return self.check_project_access_policy(user_info, resource_context)

        # Check confidentiality level restrictions
        if "confidentiality_level" in resource_context:
            return self.check_confidentiality_policy(user_info, resource_context)

        return {"authorized": True, "basis": "No specific resource restrictions"}

    def check_data_ownership_policy(self, user_info, resource_context):
        """Check if user can access their own data or has admin privileges."""

        resource_owner = resource_context.get("owner_id")
        user_id = user_info.get("user_id")
        user_roles = user_info.get("roles", [])

        # Users can always access their own data
        if resource_owner == user_id:
            return {
                "authorized": True,
                "basis": "Data ownership - user accessing own data"
            }

        # Admins and managers can access any user data
        if any(role in ['admin', 'manager'] for role in user_roles):
            return {
                "authorized": True,
                "basis": f"Administrative access - user has {user_roles} role(s)"
            }

        return {
            "authorized": False,
            "reason": "User cannot access other users' data",
            "security_event": "unauthorized_data_access_attempt"
        }

    def check_department_policy(self, user_info, resource_context):
        """Check departmental access restrictions."""

        user_department = user_info.get("department")
        resource_department = resource_context.get("department")
        user_roles = user_info.get("roles", [])

        # Same department access
        if user_department == resource_department:
            return {
                "authorized": True,
                "basis": f"Same department access - {user_department}"
            }

        # Cross-department access for admin/manager
        if any(role in ['admin', 'manager'] for role in user_roles):
            return {
                "authorized": True,
                "basis": f"Cross-department access - {user_roles} role(s)"
            }

        return {
            "authorized": False,
            "reason": f"User department '{user_department}' cannot access '{resource_department}' data",
            "security_event": "cross_department_access_denied"
        }

    def check_project_access_policy(self, user_info, resource_context):
        """Check project-based access control."""

        user_projects = user_info.get("assigned_projects", [])
        required_project = resource_context.get("project_id")
        user_roles = user_info.get("roles", [])

        # Check project assignment
        if required_project in user_projects:
            return {
                "authorized": True,
                "basis": f"Project assignment - user assigned to project {required_project}"
            }

        # Admin override
        if 'admin' in user_roles:
            return {
                "authorized": True,
                "basis": "Administrative override for project access"
            }

        return {
            "authorized": False,
            "reason": f"User not assigned to project {required_project}",
            "security_event": "unauthorized_project_access"
        }

    def check_confidentiality_policy(self, user_info, resource_context):
        """Check access based on data confidentiality level."""

        clearance_levels = {
            'public': 0,
            'internal': 1,
            'confidential': 2,
            'restricted': 3,
            'top_secret': 4
        }

        user_clearance = user_info.get("security_clearance", "public")
        resource_level = resource_context.get("confidentiality_level", "public")

        user_level = clearance_levels.get(user_clearance, 0)
        required_level = clearance_levels.get(resource_level, 0)

        if user_level >= required_level:
            return {
                "authorized": True,
                "basis": f"Security clearance sufficient - {user_clearance} >= {resource_level}"
            }

        return {
            "authorized": False,
            "reason": f"Insufficient security clearance - need {resource_level}, have {user_clearance}",
            "security_event": "insufficient_security_clearance"
        }

    def check_temporal_restrictions(self, user_info, permission):
        """Check time-based access restrictions."""

        current_time = datetime.utcnow()
        current_hour = current_time.hour
        current_day = current_time.weekday()  # Monday = 0

        # Check business hours restrictions for sensitive operations
        sensitive_permissions = ['users.delete', 'system.configure', 'data.delete']

        if permission in sensitive_permissions:
            # Business hours: 9 AM to 6 PM, Monday to Friday
            if current_day >= 5 or current_hour < 9 or current_hour >= 18:
                # Allow admin override
                if 'admin' in user_info.get("roles", []):
                    return {
                        "authorized": True,
                        "basis": "Admin override for off-hours sensitive operation"
                    }

                return {
                    "authorized": False,
                    "reason": "Sensitive operation restricted to business hours (9 AM - 6 PM, Mon-Fri)",
                    "security_event": "off_hours_sensitive_operation_blocked"
                }

        # Check session expiry
        session_start = user_info.get("session_start")
        if session_start:
            session_start_time = datetime.fromisoformat(session_start)
            session_duration = current_time - session_start_time

            if session_duration > timedelta(hours=8):  # 8 hour session limit
                return {
                    "authorized": False,
                    "reason": "Session expired - maximum duration exceeded",
                    "security_event": "expired_session_access_attempt"
                }

        return {"authorized": True, "basis": "No temporal restrictions violated"}

    def perform_security_checks(self, user_info, permission):
        """Perform additional security validations."""

        checks = {
            "account_locked": False,
            "password_expired": False,
            "mfa_verified": True,
            "suspicious_activity": False,
            "concurrent_sessions": False
        }

        # Check account status
        if user_info.get("account_locked", False):
            checks["account_locked"] = True

        # Check password expiry
        password_changed = user_info.get("password_last_changed")
        if password_changed:
            password_age = datetime.utcnow() - datetime.fromisoformat(password_changed)
            if password_age > timedelta(days=90):  # 90-day password policy
                checks["password_expired"] = True

        # Check MFA for sensitive operations
        sensitive_ops = ['users.delete', 'system.configure', 'data.export']
        if permission in sensitive_ops:
            if not user_info.get("mfa_verified", False):
                checks["mfa_verified"] = False

        return checks

    def log_authorization_event(self, user_info, permission, authorized, resource_context, reason=None):
        """Log authorization events for audit."""

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_info.get("user_id", "unknown"),
            "permission": permission,
            "authorized": authorized,
            "resource_context": resource_context,
            "reason": reason,
            "user_roles": user_info.get("roles", []),
            "session_id": user_info.get("session_id"),
            "ip_address": user_info.get("ip_address"),
            "user_agent": user_info.get("user_agent")
        }

        # In production, send to security audit system
        print(f"RBAC_AUDIT: {json.dumps(event)}")

# Authorize user request
rbac_engine = RBACAuthorizationEngine()

# Sample resource context
resource_context = {
    "resource_type": "user_data",
    "resource_id": "user_456",
    "owner_id": "user_456",
    "confidentiality_level": "confidential"
}

authorization_result = rbac_engine.authorize_request(
    user_info,
    requested_permission,
    resource_context
)

result = authorization_result
'''
))

```

## 🔍 Security Audit & Compliance

### Comprehensive Audit Trail System
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

workflow = WorkflowBuilder()

# Audit system
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.audit_categories = {
            'authentication': 'User authentication events',
            'authorization': 'Access control decisions',
            'data_access': 'Data read/write operations',
            'system_changes': 'System configuration changes',
            'security_events': 'Security-related incidents',
            'compliance': 'Regulatory compliance events'
        }

        self.severity_levels = {
            'critical': 1,
            'high': 2,
            'medium': 3,
            'low': 4,
            'info': 5
        }

        self.compliance_frameworks = {
            'SOX': 'Sarbanes-Oxley compliance',
            'GDPR': 'General Data Protection Regulation',
            'HIPAA': 'Health Insurance Portability and Accountability Act',
            'PCI_DSS': 'Payment Card Industry Data Security Standard',
            'ISO_27001': 'Information Security Management'
        }

    def create_audit_entry(self, event_data, category, severity='medium'):
        """Create comprehensive audit entry."""

        # Generate unique audit ID
        audit_id = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}{json.dumps(event_data)}".encode()
        ).hexdigest()[:16]

        # Create base audit entry
        audit_entry = {
            "audit_id": audit_id,
            "timestamp": datetime.utcnow().isoformat(),
            "category": category,
            "severity": severity,
            "severity_level": self.severity_levels.get(severity, 3),
            "event_data": event_data,
            "compliance_tags": self.determine_compliance_tags(category, event_data),
            "audit_metadata": self.create_audit_metadata(event_data)
        }

        # Add category-specific fields
        if category == 'authentication':
            audit_entry.update(self.enhance_auth_audit(event_data))
        elif category == 'authorization':
            audit_entry.update(self.enhance_authz_audit(event_data))
        elif category == 'data_access':
            audit_entry.update(self.enhance_data_audit(event_data))
        elif category == 'system_changes':
            audit_entry.update(self.enhance_system_audit(event_data))
        elif category == 'security_events':
            audit_entry.update(self.enhance_security_audit(event_data))

        # Calculate risk score
        audit_entry["risk_score"] = self.calculate_risk_score(audit_entry)

        # Add retention policy
        audit_entry["retention_policy"] = self.determine_retention_policy(category, severity)

        return audit_entry

    def determine_compliance_tags(self, category, event_data):
        """Determine which compliance frameworks apply."""

        tags = []

        # SOX compliance for financial systems
        if any(term in str(event_data).lower() for term in ['financial', 'accounting', 'revenue']):
            tags.append('SOX')

        # GDPR for personal data
        if any(term in str(event_data).lower() for term in ['personal', 'pii', 'gdpr', 'privacy']):
            tags.append('GDPR')

        # HIPAA for health data
        if any(term in str(event_data).lower() for term in ['medical', 'health', 'patient', 'hipaa']):
            tags.append('HIPAA')

        # PCI DSS for payment data
        if any(term in str(event_data).lower() for term in ['payment', 'card', 'transaction']):
            tags.append('PCI_DSS')

        # ISO 27001 for security events
        if category in ['security_events', 'system_changes']:
            tags.append('ISO_27001')

        return tags

    def create_audit_metadata(self, event_data):
        """Create audit metadata for integrity verification."""

        return {
            "audit_version": "1.0",
            "data_integrity_hash": hashlib.sha256(json.dumps(event_data, sort_keys=True).encode()).hexdigest(),
            "audit_system": "Kailash Security Audit System",
            "audit_location": "Primary Data Center",
            "immutable": True,
            "chain_verified": True
        }

    def enhance_auth_audit(self, event_data):
        """Enhance authentication audit events."""

        return {
            "auth_method": event_data.get("auth_method", "unknown"),
            "success": event_data.get("success", False),
            "failure_reason": event_data.get("failure_reason"),
            "source_ip": event_data.get("source_ip"),
            "user_agent": event_data.get("user_agent"),
            "session_id": event_data.get("session_id"),
            "mfa_used": event_data.get("mfa_used", False),
            "risk_indicators": self.identify_auth_risk_indicators(event_data)
        }

    def enhance_authz_audit(self, event_data):
        """Enhance authorization audit events."""

        return {
            "requested_resource": event_data.get("requested_resource"),
            "permission_granted": event_data.get("permission_granted", False),
            "user_roles": event_data.get("user_roles", []),
            "authorization_basis": event_data.get("authorization_basis"),
            "resource_sensitivity": self.assess_resource_sensitivity(event_data),
            "access_context": event_data.get("access_context", {})
        }

    def enhance_data_audit(self, event_data):
        """Enhance data access audit events."""

        return {
            "data_type": event_data.get("data_type"),
            "operation": event_data.get("operation", "read"),
            "records_affected": event_data.get("records_affected", 0),
            "data_classification": event_data.get("data_classification", "internal"),
            "export_attempted": event_data.get("operation") == "export",
            "data_retention_impact": self.assess_retention_impact(event_data)
        }

    def enhance_system_audit(self, event_data):
        """Enhance system change audit events."""

        return {
            "system_component": event_data.get("system_component"),
            "change_type": event_data.get("change_type", "modification"),
            "change_approved": event_data.get("change_approved", False),
            "approval_id": event_data.get("approval_id"),
            "rollback_possible": event_data.get("rollback_possible", True),
            "impact_assessment": self.assess_change_impact(event_data)
        }

    def enhance_security_audit(self, event_data):
        """Enhance security event audit entries."""

        return {
            "threat_type": event_data.get("threat_type", "unknown"),
            "threat_level": event_data.get("threat_level", "medium"),
            "attack_vector": event_data.get("attack_vector"),
            "indicators_of_compromise": event_data.get("ioc", []),
            "incident_id": event_data.get("incident_id"),
            "response_required": self.determine_response_required(event_data),
            "affected_systems": event_data.get("affected_systems", [])
        }

    def identify_auth_risk_indicators(self, event_data):
        """Identify authentication risk indicators."""

        indicators = []

        # Multiple failed attempts
        if event_data.get("failed_attempts", 0) > 3:
            indicators.append("multiple_failed_attempts")

        # Unusual location
        if event_data.get("location_risk", "low") == "high":
            indicators.append("unusual_location")

        # Off-hours access
        current_hour = datetime.utcnow().hour
        if current_hour < 6 or current_hour > 22:
            indicators.append("off_hours_access")

        # New device
        if event_data.get("device_known", True) is False:
            indicators.append("new_device")

        return indicators

    def assess_resource_sensitivity(self, event_data):
        """Assess sensitivity level of accessed resource."""

        resource = str(event_data.get("requested_resource", "")).lower()

        if any(term in resource for term in ['admin', 'config', 'system']):
            return "high"
        elif any(term in resource for term in ['user', 'profile', 'settings']):
            return "medium"
        else:
            return "low"

    def assess_retention_impact(self, event_data):
        """Assess data retention policy impact."""

        operation = event_data.get("operation", "read")
        data_type = event_data.get("data_type", "")

        impact = {
            "retention_affected": operation in ["delete", "purge"],
            "compliance_retention_required": "personal" in data_type.lower(),
            "legal_hold_impact": operation == "delete" and "legal" in data_type.lower()
        }

        return impact

    def assess_change_impact(self, event_data):
        """Assess impact of system changes."""

        component = event_data.get("system_component", "").lower()
        change_type = event_data.get("change_type", "").lower()

        impact = {
            "business_impact": "high" if "production" in component else "low",
            "security_impact": "high" if "security" in component else "medium",
            "availability_impact": "high" if change_type in ["outage", "restart"] else "low",
            "requires_approval": "security" in component or "production" in component
        }

        return impact

    def determine_response_required(self, event_data):
        """Determine if incident response is required."""

        threat_level = event_data.get("threat_level", "medium")
        threat_type = event_data.get("threat_type", "").lower()

        high_priority_threats = ["malware", "breach", "intrusion", "ransomware"]

        return {
            "immediate_response": threat_level == "critical" or threat_type in high_priority_threats,
            "escalation_required": threat_level in ["critical", "high"],
            "notification_required": True,
            "containment_required": threat_type in high_priority_threats
        }

    def calculate_risk_score(self, audit_entry):
        """Calculate overall risk score for audit event."""

        base_score = self.severity_levels.get(audit_entry["severity"], 3)

        # Adjust based on category
        if audit_entry["category"] == "security_events":
            base_score -= 1  # Higher risk
        elif audit_entry["category"] == "authentication":
            if not audit_entry.get("success", True):
                base_score -= 1

        # Adjust based on compliance requirements
        if audit_entry.get("compliance_tags"):
            base_score -= 0.5  # Compliance events are higher risk

        # Normalize to 1-10 scale
        risk_score = max(1, min(10, 11 - base_score))

        return round(risk_score, 1)

    def determine_retention_policy(self, category, severity):
        """Determine audit log retention policy."""

        # Base retention periods (in years)
        base_retention = {
            'authentication': 1,
            'authorization': 2,
            'data_access': 3,
            'system_changes': 5,
            'security_events': 7,
            'compliance': 7
        }

        retention_years = base_retention.get(category, 1)

        # Extend for high severity events
        if severity in ['critical', 'high']:
            retention_years += 2

        return {
            "retention_years": retention_years,
            "auto_archive_after_months": 12,
            "requires_legal_review": severity == 'critical',
            "immutable_period_months": 6
        }

    def generate_compliance_report(self, audit_entries, framework, time_period_days=30):
        """Generate compliance report for specific framework."""

        # Filter entries by compliance framework
        relevant_entries = [
            entry for entry in audit_entries
            if framework in entry.get("compliance_tags", [])
        ]

        # Analyze by categories
        category_analysis = {}
        for category in self.audit_categories:
            category_entries = [e for e in relevant_entries if e["category"] == category]
            category_analysis[category] = {
                "total_events": len(category_entries),
                "critical_events": len([e for e in category_entries if e["severity"] == "critical"]),
                "high_risk_events": len([e for e in category_entries if e["risk_score"] >= 8]),
                "compliance_violations": len([e for e in category_entries if e["risk_score"] >= 9])
            }

        # Overall compliance metrics
        total_events = len(relevant_entries)
        violations = len([e for e in relevant_entries if e["risk_score"] >= 9])
        compliance_score = max(0, 100 - (violations / total_events * 100)) if total_events > 0 else 100

        return {
            "framework": framework,
            "report_period_days": time_period_days,
            "report_generated": datetime.utcnow().isoformat(),
            "overall_metrics": {
                "total_audit_events": total_events,
                "compliance_violations": violations,
                "compliance_score": round(compliance_score, 1),
                "average_risk_score": round(sum(e["risk_score"] for e in relevant_entries) / total_events, 1) if total_events > 0 else 0
            },
            "category_analysis": category_analysis,
            "recommendations": self.generate_compliance_recommendations(framework, category_analysis, compliance_score)
        }

    def generate_compliance_recommendations(self, framework, category_analysis, compliance_score):
        """Generate compliance improvement recommendations."""

        recommendations = []

        if compliance_score < 90:
            recommendations.append(f"Overall {framework} compliance score of {compliance_score}% needs improvement")

        for category, metrics in category_analysis.items():
            if metrics["compliance_violations"] > 0:
                recommendations.append(f"Address {metrics['compliance_violations']} compliance violations in {category}")

            if metrics["critical_events"] > 5:
                recommendations.append(f"High volume of critical events in {category} - review procedures")

        # Framework-specific recommendations
        if framework == "GDPR":
            recommendations.extend([
                "Implement automated PII detection and protection",
                "Review data retention policies for compliance",
                "Ensure consent management procedures are followed"
            ])
        elif framework == "SOX":
            recommendations.extend([
                "Strengthen financial system access controls",
                "Implement segregation of duties for financial processes",
                "Enhance change management for financial systems"
            ])
        elif framework == "HIPAA":
            recommendations.extend([
                "Implement comprehensive PHI access logging",
                "Review minimum necessary access policies",
                "Strengthen encryption for health data"
            ])

        return recommendations[:10]  # Top 10 recommendations

# Create audit system and process events
audit_system = SecurityAuditSystem()

# Sample audit events
sample_events = [
    {
        "user_id": "user_123",
        "auth_method": "password",
        "success": False,
        "failure_reason": "invalid_password",
        "source_ip": "192.168.1.100",
        "failed_attempts": 4
    }
]

# Create audit entries
audit_entries = []
for event in sample_events:
    audit_entry = audit_system.create_audit_entry(event, "authentication", "high")
    audit_entries.append(audit_entry)

# Generate compliance report
compliance_report = audit_system.generate_compliance_report(audit_entries, "GDPR", 30)

result = {
    "audit_entries": audit_entries,
    "compliance_report": compliance_report,
    "audit_system_status": "operational"
}
'''
))

```

## 🔗 Security Best Practices

### Production Security Checklist
- [ ] **Authentication**: Multi-factor authentication for all privileged accounts
- [ ] **Authorization**: Principle of least privilege with regular access reviews
- [ ] **Encryption**: Data encrypted in transit and at rest
- [ ] **Audit Logging**: Comprehensive audit trails for all security events
- [ ] **Incident Response**: Automated threat detection and response procedures
- [ ] **Compliance**: Regular compliance audits and vulnerability assessments
- [ ] **Key Management**: Secure key rotation and hardware security modules
- [ ] **Network Security**: Network segmentation and intrusion detection
- [ ] **Backup & Recovery**: Secure backup procedures with disaster recovery testing
- [ ] **Security Training**: Regular security awareness training for all users

### Security Integration Patterns
1. **Zero Trust Architecture**: Never trust, always verify
2. **Defense in Depth**: Multiple layers of security controls
3. **Continuous Monitoring**: Real-time security monitoring and alerting
4. **DevSecOps**: Security integrated throughout development lifecycle
5. **Risk-Based Security**: Security controls based on risk assessment

---

*This comprehensive security guide covers enterprise-grade security patterns from authentication to compliance. Use these patterns to build secure, auditable systems that meet regulatory requirements.*

"""Compliance validation system for Kaizen AI framework."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ComplianceValidator(ABC):
    """Base class for compliance validators."""

    @abstractmethod
    def validate(self, control_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a specific compliance control.

        Args:
            control_id: Control identifier (e.g., "CC6.1" for SOC2)
            config: System configuration to validate

        Returns:
            Validation result with compliant status and violations
        """
        pass


class SOC2Validator(ComplianceValidator):
    """SOC2 Trust Service Criteria validator."""

    def __init__(self):
        """Initialize SOC2 validator."""
        # SOC2 control definitions
        self.controls = {
            "CC6.1": {
                "name": "Logical and Physical Access Controls",
                "description": "Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users whose access is administered by the entity.",
                "checks": ["mfa_enabled", "password_policy", "rbac_enabled"],
            },
            "CC6.2": {
                "name": "Prior to Issuing System Credentials",
                "description": "The entity authorizes, modifies, or removes access to data, software, functions, and other protected information assets based on roles, responsibilities, or the system design and changes.",
                "checks": ["rbac_enabled", "principle_of_least_privilege"],
            },
            "CC6.7": {
                "name": "Restricted Access to Data",
                "description": "The entity restricts the transmission, movement, and removal of information to authorized internal and external users and processes, and protects it during transmission, movement, or removal.",
                "checks": ["encryption_enabled", "audit_logging"],
            },
        }

    def validate(self, control_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate SOC2 control."""
        if control_id not in self.controls:
            raise ValueError(f"Unknown control ID: {control_id}")

        control = self.controls[control_id]
        violations = []

        # CC6.1: Logical Access Controls
        if control_id == "CC6.1":
            auth_config = config.get("authentication", {})
            authz_config = config.get("authorization", {})

            # Check MFA
            if not auth_config.get("mfa_enabled", False):
                violations.append(
                    {
                        "check": "mfa_enabled",
                        "description": "Multi-factor authentication (MFA) must be enabled",
                        "severity": "high",
                    }
                )

            # Check password policy
            password_policy = auth_config.get("password_policy", {})
            if password_policy.get("min_length", 0) < 12:
                violations.append(
                    {
                        "check": "password_policy",
                        "description": "Password minimum length must be at least 12 characters",
                        "severity": "high",
                    }
                )

            if not password_policy.get("require_special_chars", False):
                violations.append(
                    {
                        "check": "password_policy",
                        "description": "Password policy must require special characters",
                        "severity": "medium",
                    }
                )

            # Check RBAC
            if not authz_config.get("rbac_enabled", False):
                violations.append(
                    {
                        "check": "rbac_enabled",
                        "description": "Role-based access control (RBAC) must be enabled",
                        "severity": "high",
                    }
                )

        # CC6.2: Authorization based on roles
        elif control_id == "CC6.2":
            authz_config = config.get("authorization", {})

            if not authz_config.get("rbac_enabled", False):
                violations.append(
                    {
                        "check": "rbac_enabled",
                        "description": "RBAC must be enabled for role-based authorization",
                        "severity": "high",
                    }
                )

            if not authz_config.get("principle_of_least_privilege", False):
                violations.append(
                    {
                        "check": "principle_of_least_privilege",
                        "description": "Principle of least privilege must be enforced",
                        "severity": "high",
                    }
                )

        # CC6.7: Data protection and encryption
        elif control_id == "CC6.7":
            audit_config = config.get("audit", {})
            encryption_config = config.get("encryption", {})

            if not audit_config.get("logging_enabled", False):
                violations.append(
                    {
                        "check": "audit_logging",
                        "description": "Audit logging must be enabled for data access",
                        "severity": "high",
                    }
                )

            if not encryption_config.get("data_at_rest", False):
                violations.append(
                    {
                        "check": "encryption_at_rest",
                        "description": "Data at rest must be encrypted",
                        "severity": "critical",
                    }
                )

            if not encryption_config.get("data_in_transit", False):
                violations.append(
                    {
                        "check": "encryption_in_transit",
                        "description": "Data in transit must be encrypted",
                        "severity": "critical",
                    }
                )

        return {
            "control_id": control_id,
            "control_name": control["name"],
            "compliant": len(violations) == 0,
            "violations": violations,
            "timestamp": datetime.now(timezone.utc),
        }


class GDPRValidator(ComplianceValidator):
    """GDPR (General Data Protection Regulation) validator."""

    def __init__(self):
        """Initialize GDPR validator."""
        self.articles = {
            "Art5": {
                "name": "Principles relating to processing of personal data",
                "description": "Personal data shall be processed lawfully, fairly and transparently; collected for specified, explicit and legitimate purposes.",
                "checks": [
                    "lawful_basis",
                    "purpose_limitation",
                    "data_minimization",
                    "accuracy",
                    "storage_limitation",
                ],
            },
            "Art17": {
                "name": "Right to erasure ('right to be forgotten')",
                "description": "The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay.",
                "checks": ["erasure_supported", "erasure_timeframe"],
            },
            "Art25": {
                "name": "Data protection by design and by default",
                "description": "The controller shall implement appropriate technical and organisational measures for ensuring that, by default, only personal data necessary is processed.",
                "checks": ["data_minimization", "pseudonymization", "encryption"],
            },
            "Art32": {
                "name": "Security of processing",
                "description": "The controller and processor shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk.",
                "checks": [
                    "encryption",
                    "pseudonymization",
                    "confidentiality",
                    "integrity",
                    "availability",
                ],
            },
        }

    def validate(self, article: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate GDPR article."""
        if article not in self.articles:
            raise ValueError(f"Unknown GDPR article: {article}")

        article_def = self.articles[article]
        violations = []

        # Art5: Data processing principles
        if article == "Art5":
            data_proc = config.get("data_processing", {})

            if not data_proc.get("lawful_basis"):
                violations.append(
                    {
                        "check": "lawful_basis",
                        "description": "Must have lawful basis for data processing (consent, contract, legal obligation, etc.)",
                        "severity": "critical",
                    }
                )

            if not data_proc.get("purpose_specified", False):
                violations.append(
                    {
                        "check": "purpose_limitation",
                        "description": "Purpose of data processing must be specified",
                        "severity": "high",
                    }
                )

            if not data_proc.get("data_minimization", False):
                violations.append(
                    {
                        "check": "data_minimization",
                        "description": "Data minimization principle must be applied",
                        "severity": "high",
                    }
                )

        # Art17: Right to erasure
        elif article == "Art17":
            rights = config.get("data_subject_rights", {})

            if not rights.get("erasure_supported", False):
                violations.append(
                    {
                        "check": "erasure_supported",
                        "description": "Right to erasure (RTBF) must be supported",
                        "severity": "critical",
                    }
                )

            timeframe = rights.get("erasure_timeframe_days", 999)
            if timeframe > 30:
                violations.append(
                    {
                        "check": "erasure_timeframe",
                        "description": "Erasure must be completed within 30 days",
                        "severity": "high",
                    }
                )

        # Art25: Privacy by design
        elif article == "Art25":
            privacy = config.get("privacy", {})

            if not privacy.get("data_minimization", False):
                violations.append(
                    {
                        "check": "data_minimization",
                        "description": "Data minimization must be implemented by design",
                        "severity": "high",
                    }
                )

            if not privacy.get("pseudonymization", False):
                violations.append(
                    {
                        "check": "pseudonymization",
                        "description": "Pseudonymization should be implemented where appropriate",
                        "severity": "medium",
                    }
                )

            if not privacy.get("encryption_by_default", False):
                violations.append(
                    {
                        "check": "encryption_by_default",
                        "description": "Encryption by default must be implemented",
                        "severity": "high",
                    }
                )

        # Art32: Security of processing
        elif article == "Art32":
            security = config.get("security", {})

            if not security.get("encryption", False):
                violations.append(
                    {
                        "check": "encryption",
                        "description": "Encryption must be implemented for data protection",
                        "severity": "critical",
                    }
                )

            if not security.get("confidentiality", False):
                violations.append(
                    {
                        "check": "confidentiality",
                        "description": "Confidentiality measures must be in place",
                        "severity": "high",
                    }
                )

            if not security.get("integrity", False):
                violations.append(
                    {
                        "check": "integrity",
                        "description": "Data integrity measures must be in place",
                        "severity": "high",
                    }
                )

            if not security.get("regular_testing", False):
                violations.append(
                    {
                        "check": "regular_testing",
                        "description": "Regular testing and evaluation of security measures required",
                        "severity": "medium",
                    }
                )

        return {
            "article": article,
            "article_name": article_def["name"],
            "compliant": len(violations) == 0,
            "violations": violations,
            "timestamp": datetime.now(timezone.utc),
        }


class ComplianceEngine:
    """Compliance validation engine."""

    def __init__(self):
        """Initialize compliance engine."""
        self.validators: Dict[str, ComplianceValidator] = {}

    def register_validator(self, standard: str, validator: ComplianceValidator):
        """Register a compliance validator."""
        self.validators[standard] = validator

    def get_validator(self, standard: str) -> Optional[ComplianceValidator]:
        """Get a registered validator."""
        return self.validators.get(standard)

    def list_validators(self) -> List[str]:
        """List all registered validators."""
        return list(self.validators.keys())

    def run_compliance_check(
        self, standard: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run full compliance check for a standard."""
        if standard not in self.validators:
            raise ValueError(f"No validator registered for standard: {standard}")

        validator = self.validators[standard]
        results = []

        # Get all controls/articles
        if standard == "soc2" and isinstance(validator, SOC2Validator):
            control_ids = validator.controls.keys()
        elif standard == "gdpr" and isinstance(validator, GDPRValidator):
            control_ids = validator.articles.keys()
        else:
            return {}

        # Run validation for each control
        for control_id in control_ids:
            result = validator.validate(control_id, config)
            results.append(result)

        total_violations = sum(len(r["violations"]) for r in results)
        overall_compliant = all(r["compliant"] for r in results)

        return {
            "timestamp": datetime.now(timezone.utc),
            "standard": standard,
            "overall_compliant": overall_compliant,
            "controls_checked": len(results),
            "total_violations": total_violations,
            "results": results,
        }

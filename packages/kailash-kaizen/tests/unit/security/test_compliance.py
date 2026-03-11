"""Tier 1 unit tests for compliance validation system."""

from kaizen.security.compliance import ComplianceValidator, SOC2Validator


class TestComplianceFramework:
    """Test suite for compliance validation framework."""

    def test_compliance_validator_registration(self):
        """Test 4.1a: Register and retrieve compliance validators."""
        from kaizen.security.compliance import ComplianceEngine

        engine = ComplianceEngine()

        # Register SOC2 validator
        soc2_validator = SOC2Validator()
        engine.register_validator("soc2", soc2_validator)

        # Retrieve validator
        retrieved = engine.get_validator("soc2")
        assert retrieved is soc2_validator

        # List all validators
        validators = engine.list_validators()
        assert "soc2" in validators

    def test_soc2_access_control_validation(self):
        """Test 4.1b: Validate SOC2 access control requirements."""
        validator = SOC2Validator()

        # Valid configuration: MFA enabled, RBAC configured
        valid_config = {
            "authentication": {
                "mfa_enabled": True,
                "password_policy": {"min_length": 12, "require_special_chars": True},
            },
            "authorization": {
                "rbac_enabled": True,
                "principle_of_least_privilege": True,
            },
        }

        result = validator.validate(
            "CC6.1", valid_config
        )  # CC6.1: Logical Access Controls

        assert result["compliant"] is True
        assert result["control_id"] == "CC6.1"
        assert "violations" in result
        assert len(result["violations"]) == 0

    def test_soc2_violation_detection(self):
        """Test 4.1c: Detect SOC2 compliance violations."""
        validator = SOC2Validator()

        # Invalid configuration: MFA disabled, weak password
        invalid_config = {
            "authentication": {
                "mfa_enabled": False,  # Violation!
                "password_policy": {
                    "min_length": 6,  # Too short!
                    "require_special_chars": False,  # Missing!
                },
            },
            "authorization": {"rbac_enabled": False},  # Violation!
        }

        result = validator.validate("CC6.1", invalid_config)

        assert result["compliant"] is False
        assert len(result["violations"]) > 0

        # Verify violation details
        violation_descriptions = [v["description"] for v in result["violations"]]
        assert any(
            "MFA" in desc or "multi-factor" in desc.lower()
            for desc in violation_descriptions
        )
        assert any("password" in desc.lower() for desc in violation_descriptions)

    def test_compliance_reporting(self):
        """Test 4.1d: Generate compliance status report."""
        from kaizen.security.compliance import ComplianceEngine

        engine = ComplianceEngine()
        soc2_validator = SOC2Validator()
        engine.register_validator("soc2", soc2_validator)

        # Run compliance checks
        config = {
            "authentication": {
                "mfa_enabled": True,
                "password_policy": {"min_length": 12, "require_special_chars": True},
            },
            "authorization": {
                "rbac_enabled": True,
                "principle_of_least_privilege": True,
            },
            "audit": {"logging_enabled": True, "retention_days": 365},
        }

        report = engine.run_compliance_check("soc2", config)

        assert "timestamp" in report
        assert "standard" in report
        assert report["standard"] == "soc2"
        assert "overall_compliant" in report
        assert "controls_checked" in report
        assert "total_violations" in report

    def test_multiple_controls_validation(self):
        """Test 4.1e: Validate multiple SOC2 controls."""
        validator = SOC2Validator()

        config = {
            "authentication": {
                "mfa_enabled": True,
                "password_policy": {"min_length": 12, "require_special_chars": True},
            },
            "authorization": {
                "rbac_enabled": True,
                "principle_of_least_privilege": True,
            },
            "audit": {
                "logging_enabled": True,
                "retention_days": 365,
                "immutable_logs": True,
            },
            "encryption": {
                "data_at_rest": True,
                "data_in_transit": True,
                "algorithm": "AES-256-GCM",
            },
        }

        # Validate multiple controls
        results = []
        for control_id in ["CC6.1", "CC6.2", "CC6.7"]:
            result = validator.validate(control_id, config)
            results.append(result)

        # All controls should pass
        assert all(r["compliant"] for r in results)
        assert len(results) == 3

    def test_gdpr_validator_registration(self):
        """Test 4.2a: Register GDPR validator."""
        from kaizen.security.compliance import GDPRValidator

        validator = GDPRValidator()

        # Verify it's a ComplianceValidator
        assert isinstance(validator, ComplianceValidator)

        # Verify GDPR articles defined
        assert "Art5" in validator.articles  # Data processing principles
        assert "Art17" in validator.articles  # Right to erasure
        assert "Art25" in validator.articles  # Privacy by design
        assert "Art32" in validator.articles  # Security of processing

    def test_gdpr_data_processing_principles(self):
        """Test 4.2b: Validate GDPR Article 5 (data processing principles)."""
        from kaizen.security.compliance import GDPRValidator

        validator = GDPRValidator()

        # Valid configuration: meets GDPR principles
        valid_config = {
            "data_processing": {
                "lawful_basis": "consent",  # Lawfulness
                "purpose_specified": True,  # Purpose limitation
                "data_minimization": True,  # Data minimization
                "accuracy_maintained": True,  # Accuracy
                "storage_limitation": True,  # Storage limitation
                "integrity_confidentiality": True,  # Integrity and confidentiality
            }
        }

        result = validator.validate("Art5", valid_config)

        assert result["compliant"] is True
        assert result["article"] == "Art5"
        assert len(result["violations"]) == 0

    def test_gdpr_right_to_erasure(self):
        """Test 4.2c: Validate GDPR Article 17 (right to erasure/RTBF)."""
        from kaizen.security.compliance import GDPRValidator

        validator = GDPRValidator()

        # Valid configuration: supports right to erasure
        valid_config = {
            "data_subject_rights": {
                "erasure_supported": True,
                "erasure_timeframe_days": 30,  # Must be within reasonable timeframe
                "automated_deletion": True,
                "deletion_verification": True,
            }
        }

        result = validator.validate("Art17", valid_config)

        assert result["compliant"] is True
        assert len(result["violations"]) == 0

        # Invalid configuration: doesn't support erasure
        invalid_config = {
            "data_subject_rights": {
                "erasure_supported": False,  # Violation!
                "erasure_timeframe_days": 90,  # Too long!
            }
        }

        result = validator.validate("Art17", invalid_config)

        assert result["compliant"] is False
        assert len(result["violations"]) > 0

    def test_gdpr_privacy_by_design(self):
        """Test 4.2d: Validate GDPR Article 25 (privacy by design)."""
        from kaizen.security.compliance import GDPRValidator

        validator = GDPRValidator()

        # Valid configuration: privacy by design
        valid_config = {
            "privacy": {
                "data_minimization": True,
                "pseudonymization": True,
                "encryption_by_default": True,
                "privacy_impact_assessment": True,
            }
        }

        result = validator.validate("Art25", valid_config)

        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_gdpr_security_of_processing(self):
        """Test 4.2e: Validate GDPR Article 32 (security of processing)."""
        from kaizen.security.compliance import GDPRValidator

        validator = GDPRValidator()

        # Valid configuration: appropriate security measures
        valid_config = {
            "security": {
                "encryption": True,
                "pseudonymization": True,
                "confidentiality": True,
                "integrity": True,
                "availability": True,
                "resilience": True,
                "regular_testing": True,
                "incident_response_plan": True,
            }
        }

        result = validator.validate("Art32", valid_config)

        assert result["compliant"] is True
        assert len(result["violations"]) == 0

        # Invalid: missing key security measures
        invalid_config = {
            "security": {
                "encryption": False,  # Violation!
                "regular_testing": False,  # Violation!
            }
        }

        result = validator.validate("Art32", invalid_config)

        assert result["compliant"] is False
        assert len(result["violations"]) >= 2

    def test_gdpr_comprehensive_check(self):
        """Test 4.2f: Run comprehensive GDPR compliance check."""
        from kaizen.security.compliance import ComplianceEngine, GDPRValidator

        engine = ComplianceEngine()
        gdpr_validator = GDPRValidator()
        engine.register_validator("gdpr", gdpr_validator)

        # Comprehensive GDPR-compliant configuration
        config = {
            "data_processing": {
                "lawful_basis": "consent",
                "purpose_specified": True,
                "data_minimization": True,
                "accuracy_maintained": True,
                "storage_limitation": True,
                "integrity_confidentiality": True,
            },
            "data_subject_rights": {
                "erasure_supported": True,
                "erasure_timeframe_days": 30,
                "automated_deletion": True,
                "deletion_verification": True,
            },
            "privacy": {
                "data_minimization": True,
                "pseudonymization": True,
                "encryption_by_default": True,
                "privacy_impact_assessment": True,
            },
            "security": {
                "encryption": True,
                "pseudonymization": True,
                "confidentiality": True,
                "integrity": True,
                "availability": True,
                "resilience": True,
                "regular_testing": True,
                "incident_response_plan": True,
            },
        }

        report = engine.run_compliance_check("gdpr", config)

        assert report["standard"] == "gdpr"
        assert report["overall_compliant"] is True
        assert report["controls_checked"] >= 4  # At least Art5, Art17, Art25, Art32
        assert report["total_violations"] == 0

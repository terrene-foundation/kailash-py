"""
Unit tests for the connection contract system.

Tests the basic contract functionality including:
- ConnectionContract creation and validation
- SecurityPolicy enforcement
- ContractRegistry functionality
- ContractValidator behavior
"""

import pytest
from kailash.workflow.contracts import (
    ConnectionContract,
    ContractRegistry,
    ContractValidator,
    SecurityPolicy,
    get_contract_registry,
)


class TestConnectionContract:
    """Test ConnectionContract functionality."""

    def test_basic_contract_creation(self):
        """Test creating a basic contract."""
        contract = ConnectionContract(
            name="test_contract",
            description="A test contract",
            source_schema={"type": "string"},
            target_schema={"type": "string"},
        )

        assert contract.name == "test_contract"
        assert contract.description == "A test contract"
        assert contract.source_schema == {"type": "string"}
        assert contract.target_schema == {"type": "string"}
        assert contract.audit_level == "normal"

    def test_contract_with_security_policies(self):
        """Test contract with security policies."""
        contract = ConnectionContract(
            name="secure_contract",
            security_policies=[SecurityPolicy.NO_PII, SecurityPolicy.NO_SQL],
        )

        assert SecurityPolicy.NO_PII in contract.security_policies
        assert SecurityPolicy.NO_SQL in contract.security_policies

    def test_contract_source_validation(self):
        """Test source data validation."""
        contract = ConnectionContract(
            name="string_contract", source_schema={"type": "string"}
        )

        # Valid string
        is_valid, error = contract.validate_source("test_string")
        assert is_valid
        assert error is None

        # Invalid type
        is_valid, error = contract.validate_source(123)
        assert not is_valid
        assert "Source validation failed" in error

    def test_contract_target_validation(self):
        """Test target data validation."""
        contract = ConnectionContract(
            name="number_contract", target_schema={"type": "number"}
        )

        # Valid number
        is_valid, error = contract.validate_target(42)
        assert is_valid
        assert error is None

        # Invalid type
        is_valid, error = contract.validate_target("not_a_number")
        assert not is_valid
        assert "Target validation failed" in error

    def test_security_policy_enforcement(self):
        """Test security policy checking."""
        contract = ConnectionContract(
            name="no_sql_contract", security_policies=[SecurityPolicy.NO_SQL]
        )

        # Safe data
        is_compliant, violation = contract.check_security_policies("safe data")
        assert is_compliant
        assert violation is None

        # SQL injection attempt
        is_compliant, violation = contract.check_security_policies(
            "SELECT * FROM users"
        )
        assert not is_compliant
        assert "SQL pattern detected" in violation

    def test_pii_detection(self):
        """Test PII policy enforcement."""
        contract = ConnectionContract(
            name="no_pii_contract", security_policies=[SecurityPolicy.NO_PII]
        )

        # Safe data
        is_compliant, violation = contract.check_security_policies("normal user data")
        assert is_compliant

        # PII data
        is_compliant, violation = contract.check_security_policies("SSN: 123-45-6789")
        assert not is_compliant
        assert "PII detected" in violation

    def test_credentials_detection(self):
        """Test credentials policy enforcement."""
        contract = ConnectionContract(
            name="no_creds_contract", security_policies=[SecurityPolicy.NO_CREDENTIALS]
        )

        # Safe data
        is_compliant, violation = contract.check_security_policies("user information")
        assert is_compliant

        # Credential data
        is_compliant, violation = contract.check_security_policies(
            "password: secret123"
        )
        assert not is_compliant
        assert "Credential detected" in violation

    def test_contract_serialization(self):
        """Test contract to/from dict conversion."""
        original = ConnectionContract(
            name="serializable_contract",
            description="Test serialization",
            source_schema={"type": "object"},
            security_policies=[SecurityPolicy.NO_PII],
            audit_level="detailed",
        )

        # Convert to dict
        contract_dict = original.to_dict()

        assert contract_dict["name"] == "serializable_contract"
        assert contract_dict["description"] == "Test serialization"
        assert contract_dict["source_schema"] == {"type": "object"}
        assert "no_pii" in contract_dict["security_policies"]
        assert contract_dict["audit_level"] == "detailed"

        # Convert back from dict
        restored = ConnectionContract.from_dict(contract_dict)

        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.source_schema == original.source_schema
        assert restored.security_policies == original.security_policies
        assert restored.audit_level == original.audit_level


class TestContractRegistry:
    """Test ContractRegistry functionality."""

    def test_predefined_contracts(self):
        """Test that predefined contracts are available."""
        registry = ContractRegistry()

        contracts = registry.list_contracts()

        # Check common predefined contracts
        assert "string_data" in contracts
        assert "numeric_data" in contracts
        assert "file_path" in contracts
        assert "sql_query" in contracts
        assert "user_data" in contracts

    def test_register_custom_contract(self):
        """Test registering custom contracts."""
        registry = ContractRegistry()

        custom_contract = ConnectionContract(
            name="custom_test", description="Custom test contract"
        )

        registry.register(custom_contract)

        retrieved = registry.get("custom_test")
        assert retrieved is not None
        assert retrieved.name == "custom_test"
        assert retrieved.description == "Custom test contract"

    def test_create_from_schema(self):
        """Test creating contract from schema."""
        registry = ContractRegistry()

        schema = {"type": "array", "items": {"type": "string"}}
        security_policies = [SecurityPolicy.NO_SQL]

        contract = registry.create_from_schema(
            "array_contract", schema, security_policies
        )

        assert contract.name == "array_contract"
        assert contract.source_schema == schema
        assert contract.target_schema == schema
        assert SecurityPolicy.NO_SQL in contract.security_policies

        # Should be registered automatically
        retrieved = registry.get("array_contract")
        assert retrieved is not None

    def test_global_registry_singleton(self):
        """Test that global registry is singleton."""
        registry1 = get_contract_registry()
        registry2 = get_contract_registry()

        assert registry1 is registry2

        # Add contract to one, should be visible in other
        test_contract = ConnectionContract(name="singleton_test")
        registry1.register(test_contract)

        retrieved = registry2.get("singleton_test")
        assert retrieved is not None
        assert retrieved.name == "singleton_test"


class TestContractValidator:
    """Test ContractValidator functionality."""

    def test_validate_connection_success(self):
        """Test successful connection validation."""
        validator = ContractValidator()

        contract = ConnectionContract(
            name="string_validation",
            source_schema={"type": "string"},
            target_schema={"type": "string"},
        )

        source_data = "test_source"
        target_data = "test_target"

        is_valid, errors = validator.validate_connection(
            contract, source_data, target_data
        )

        assert is_valid
        assert len(errors) == 0

    def test_validate_connection_failure(self):
        """Test connection validation with failures."""
        validator = ContractValidator()

        contract = ConnectionContract(
            name="number_validation",
            source_schema={"type": "number"},
            target_schema={"type": "number"},
            security_policies=[SecurityPolicy.NO_SQL],
        )

        source_data = "SELECT * FROM users"  # Invalid: string instead of number + SQL
        target_data = "not_a_number"  # Invalid: string instead of number

        is_valid, errors = validator.validate_connection(
            contract, source_data, target_data
        )

        assert not is_valid
        assert len(errors) > 0

        # Should have source validation, target validation, and security errors
        error_text = " ".join(errors)
        assert "Source validation" in error_text
        assert "Target validation" in error_text
        assert "Security policy violation" in error_text

    def test_validate_with_contract_name(self):
        """Test validation using contract name."""
        validator = ContractValidator()

        # Use predefined contract by name
        is_valid, errors = validator.validate_connection(
            "string_data", "valid_string", "another_string"
        )

        assert is_valid
        assert len(errors) == 0

    def test_validate_unknown_contract_name(self):
        """Test validation with unknown contract name."""
        validator = ContractValidator()

        is_valid, errors = validator.validate_connection(
            "unknown_contract", "data", "data"
        )

        assert not is_valid
        assert len(errors) == 1
        assert "Contract 'unknown_contract' not found" in errors[0]

    def test_suggest_contract(self):
        """Test contract suggestion based on data."""
        validator = ContractValidator()

        # String data
        suggestion = validator.suggest_contract("test string")
        assert suggestion == "string_data"

        # Numeric data
        suggestion = validator.suggest_contract(42)
        assert suggestion == "numeric_data"

        # File path
        suggestion = validator.suggest_contract("/path/to/file.txt")
        assert suggestion == "file_path"

        # SQL query
        suggestion = validator.suggest_contract("SELECT id FROM users")
        assert suggestion == "sql_query"

        # User object
        suggestion = validator.suggest_contract({"id": "123", "name": "Test"})
        assert suggestion == "user_data"

        # Unknown data
        suggestion = validator.suggest_contract([1, 2, 3])
        assert suggestion is None


class TestSecurityPolicies:
    """Test SecurityPolicy enum and behaviors."""

    def test_all_security_policies_exist(self):
        """Test that all expected security policies are defined."""
        expected_policies = [
            SecurityPolicy.NONE,
            SecurityPolicy.NO_PII,
            SecurityPolicy.NO_CREDENTIALS,
            SecurityPolicy.NO_SQL,
            SecurityPolicy.SANITIZED,
            SecurityPolicy.ENCRYPTED,
        ]

        for policy in expected_policies:
            assert policy.value is not None

    def test_security_policy_values(self):
        """Test security policy string values."""
        assert SecurityPolicy.NONE.value == "none"
        assert SecurityPolicy.NO_PII.value == "no_pii"
        assert SecurityPolicy.NO_CREDENTIALS.value == "no_credentials"
        assert SecurityPolicy.NO_SQL.value == "no_sql"
        assert SecurityPolicy.SANITIZED.value == "sanitized"
        assert SecurityPolicy.ENCRYPTED.value == "encrypted"

"""
Connection Contract System for Kailash Workflows

Provides contract-based validation for workflow connections using JSON Schema.
Contracts define the expected data format, constraints, and security policies
for data flowing between nodes.

Design Goals:
1. Declarative validation using JSON Schema
2. Reusable contract definitions
3. Security policy enforcement
4. Backward compatibility with existing workflows
5. Clear contract violation messages
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import jsonschema
from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaError
from kailash.sdk_exceptions import WorkflowValidationError


class SecurityPolicy(Enum):
    """Security policies that can be applied to connections."""

    NONE = "none"
    """No special security policy"""

    NO_PII = "no_pii"
    """No personally identifiable information allowed"""

    NO_CREDENTIALS = "no_credentials"
    """No passwords, tokens, or keys allowed"""

    NO_SQL = "no_sql"
    """No SQL queries allowed (prevents injection)"""

    SANITIZED = "sanitized"
    """Data must be sanitized/escaped"""

    ENCRYPTED = "encrypted"
    """Data must be encrypted in transit"""


@dataclass
class ConnectionContract:
    """
    Defines a contract for data flowing through a connection.

    A contract specifies:
    - JSON Schema for data validation
    - Security policies to enforce
    - Transformation rules (optional)
    - Audit requirements
    """

    name: str
    """Human-readable name for the contract"""

    description: str = ""
    """Description of what this contract validates"""

    source_schema: Optional[Dict[str, Any]] = None
    """JSON Schema for validating source node output"""

    target_schema: Optional[Dict[str, Any]] = None
    """JSON Schema for validating target node input"""

    security_policies: List[SecurityPolicy] = field(default_factory=list)
    """Security policies to enforce on this connection"""

    transformations: Optional[Dict[str, Any]] = None
    """Optional transformations to apply (e.g., type coercion rules)"""

    audit_level: str = "normal"
    """Audit level: 'none', 'normal', 'detailed'"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata for the contract"""

    def __post_init__(self):
        """Validate contract after initialization."""
        # Validate schemas if provided
        if self.source_schema:
            try:
                Draft7Validator.check_schema(self.source_schema)
            except Exception as e:
                raise ValueError(f"Invalid source schema: {e}")

        if self.target_schema:
            try:
                Draft7Validator.check_schema(self.target_schema)
            except Exception as e:
                raise ValueError(f"Invalid target schema: {e}")

    def validate_source(self, data: Any) -> tuple[bool, Optional[str]]:
        """
        Validate data against source schema.

        Args:
            data: Data to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.source_schema:
            return True, None

        try:
            validator = Draft7Validator(self.source_schema)
            validator.validate(data)
            return True, None
        except JsonSchemaError as e:
            return False, f"Source validation failed: {e.message}"

    def validate_target(self, data: Any) -> tuple[bool, Optional[str]]:
        """
        Validate data against target schema.

        Args:
            data: Data to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.target_schema:
            return True, None

        try:
            validator = Draft7Validator(self.target_schema)
            validator.validate(data)
            return True, None
        except JsonSchemaError as e:
            return False, f"Target validation failed: {e.message}"

    def check_security_policies(self, data: Any) -> tuple[bool, Optional[str]]:
        """
        Check if data complies with security policies.

        Args:
            data: Data to check

        Returns:
            Tuple of (is_compliant, violation_message)
        """
        data_str = str(data).lower() if data is not None else ""

        for policy in self.security_policies:
            if policy == SecurityPolicy.NO_PII:
                # Simple PII detection (should be more sophisticated in production)
                pii_patterns = ["ssn", "social security", "credit card", "passport"]
                for pattern in pii_patterns:
                    if pattern in data_str:
                        return False, f"PII detected: {pattern}"

            elif policy == SecurityPolicy.NO_CREDENTIALS:
                cred_patterns = [
                    "password",
                    "token",
                    "api_key",
                    "secret",
                    "private_key",
                ]
                for pattern in cred_patterns:
                    if pattern in data_str:
                        return False, f"Credential detected: {pattern}"

            elif policy == SecurityPolicy.NO_SQL:
                sql_patterns = [
                    "select ",
                    "insert ",
                    "update ",
                    "delete ",
                    "drop ",
                    "union ",
                ]
                for pattern in sql_patterns:
                    if pattern in data_str:
                        return False, f"SQL pattern detected: {pattern}"

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        """Convert contract to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "source_schema": self.source_schema,
            "target_schema": self.target_schema,
            "security_policies": [p.value for p in self.security_policies],
            "transformations": self.transformations,
            "audit_level": self.audit_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionContract":
        """Create contract from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            source_schema=data.get("source_schema"),
            target_schema=data.get("target_schema"),
            security_policies=[
                SecurityPolicy(p) for p in data.get("security_policies", [])
            ],
            transformations=data.get("transformations"),
            audit_level=data.get("audit_level", "normal"),
            metadata=data.get("metadata", {}),
        )


class ContractRegistry:
    """Registry for reusable connection contracts."""

    def __init__(self):
        self._contracts: Dict[str, ConnectionContract] = {}
        self._initialize_common_contracts()

    def _initialize_common_contracts(self):
        """Initialize commonly used contracts."""
        # String data contract
        self.register(
            ConnectionContract(
                name="string_data",
                description="Basic string data contract",
                source_schema={"type": "string"},
                target_schema={"type": "string"},
            )
        )

        # Numeric data contract
        self.register(
            ConnectionContract(
                name="numeric_data",
                description="Numeric data contract",
                source_schema={"type": "number"},
                target_schema={"type": "number"},
            )
        )

        # File path contract
        self.register(
            ConnectionContract(
                name="file_path",
                description="File path validation",
                source_schema={
                    "type": "string",
                    "pattern": "^[^\\0]+$",  # No null bytes
                },
                target_schema={"type": "string", "pattern": "^[^\\0]+$"},
                security_policies=[SecurityPolicy.NO_SQL],
            )
        )

        # SQL query contract
        self.register(
            ConnectionContract(
                name="sql_query",
                description="SQL query with injection protection",
                source_schema={"type": "string"},
                target_schema={"type": "string"},
                security_policies=[SecurityPolicy.SANITIZED],
            )
        )

        # User data contract
        self.register(
            ConnectionContract(
                name="user_data",
                description="User data with PII protection",
                source_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                    },
                    "required": ["id"],
                },
                target_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                    },
                },
                security_policies=[SecurityPolicy.NO_CREDENTIALS],
                audit_level="detailed",
            )
        )

    def register(self, contract: ConnectionContract) -> None:
        """Register a contract in the registry."""
        self._contracts[contract.name] = contract

    def get(self, name: str) -> Optional[ConnectionContract]:
        """Get a contract by name."""
        return self._contracts.get(name)

    def list_contracts(self) -> List[str]:
        """List all available contract names."""
        return list(self._contracts.keys())

    def create_from_schema(
        self,
        name: str,
        schema: Dict[str, Any],
        security_policies: Optional[List[SecurityPolicy]] = None,
    ) -> ConnectionContract:
        """Create and register a contract from a JSON schema."""
        contract = ConnectionContract(
            name=name,
            source_schema=schema,
            target_schema=schema,
            security_policies=security_policies or [],
        )
        self.register(contract)
        return contract


class ContractValidator:
    """Validates data against connection contracts."""

    def __init__(self, registry: Optional[ContractRegistry] = None):
        self.registry = registry or ContractRegistry()

    def validate_connection(
        self,
        contract: Union[str, ConnectionContract],
        source_data: Any,
        target_data: Any,
    ) -> tuple[bool, List[str]]:
        """
        Validate a connection against a contract.

        Args:
            contract: Contract name or instance
            source_data: Data from source node
            target_data: Data for target node

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        # Resolve contract
        if isinstance(contract, str):
            contract_obj = self.registry.get(contract)
            if not contract_obj:
                return False, [f"Contract '{contract}' not found"]
            contract = contract_obj

        errors = []

        # Validate source
        valid, error = contract.validate_source(source_data)
        if not valid:
            errors.append(f"Source validation: {error}")

        # Validate target
        valid, error = contract.validate_target(target_data)
        if not valid:
            errors.append(f"Target validation: {error}")

        # Check security policies on both source and target
        for data, label in [(source_data, "source"), (target_data, "target")]:
            compliant, violation = contract.check_security_policies(data)
            if not compliant:
                errors.append(f"Security policy violation ({label}): {violation}")

        return len(errors) == 0, errors

    def suggest_contract(self, data: Any) -> Optional[str]:
        """
        Suggest a suitable contract based on data type.

        Args:
            data: Sample data

        Returns:
            Suggested contract name or None
        """
        if isinstance(data, str):
            # Check for specific string patterns
            if "@" in data and "." in data:
                return "email_data"
            elif "/" in data or "\\" in data:
                return "file_path"
            elif any(sql in data.lower() for sql in ["select", "insert", "update"]):
                return "sql_query"
            else:
                return "string_data"

        elif isinstance(data, (int, float)):
            return "numeric_data"

        elif isinstance(data, dict):
            if "id" in data or "name" in data:
                return "user_data"

        return None


# Global contract registry instance
_global_registry = None


def get_contract_registry() -> ContractRegistry:
    """Get the global contract registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ContractRegistry()
    return _global_registry

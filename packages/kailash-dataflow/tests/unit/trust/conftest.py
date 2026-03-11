#!/usr/bin/env python3
"""
Fixtures for DataFlow Trust Unit Tests (CARE-019).

Provides standardized mock objects and test data for trust-related testing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# === Mock Constraint Types (mirrors Kaizen's ConstraintType) ===


class MockConstraintType(Enum):
    """Mock constraint types for testing without Kaizen dependency."""

    RESOURCE_LIMIT = "resource_limit"
    TIME_WINDOW = "time_window"
    DATA_SCOPE = "data_scope"
    ACTION_RESTRICTION = "action_restriction"
    AUDIT_REQUIREMENT = "audit_requirement"


@dataclass
class MockConstraint:
    """Mock constraint for testing."""

    id: str
    constraint_type: MockConstraintType
    value: Any
    source: str
    priority: int = 0


@dataclass
class MockHumanOrigin:
    """Mock human origin for testing."""

    human_id: str
    authorization_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "human_id": self.human_id,
            "authorization_time": self.authorization_time.isoformat(),
        }


@dataclass
class MockRuntimeTrustContext:
    """Mock RuntimeTrustContext for testing."""

    trace_id: str
    human_origin: Optional[MockHumanOrigin] = None
    delegation_chain: List[str] = field(default_factory=list)
    delegation_depth: int = 0
    constraints: Dict[str, Any] = field(default_factory=dict)
    verification_mode: str = "enforcing"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "trace_id": self.trace_id,
            "human_origin": (
                self.human_origin.to_dict() if self.human_origin else None
            ),
            "delegation_chain": self.delegation_chain,
            "delegation_depth": self.delegation_depth,
            "constraints": self.constraints,
            "verification_mode": self.verification_mode,
        }


# === Fixtures ===


@pytest.fixture
def mock_trust_verifier():
    """Create mock TrustVerifier for unit tests."""
    verifier = MagicMock()
    verifier.verify_workflow_access = AsyncMock(
        return_value=MagicMock(allowed=True, reason="Test access granted")
    )
    verifier.verify_resource_access = AsyncMock(
        return_value=MagicMock(allowed=True, reason="Test resource access granted")
    )
    return verifier


@pytest.fixture
def mock_trust_operations():
    """Create mock TrustOperations for unit tests."""
    ops = MagicMock()
    ops.get_agent_constraints = AsyncMock(return_value=[])
    ops.verify = AsyncMock(
        return_value=MagicMock(valid=True, reason=None, violations=[])
    )
    return ops


@pytest.fixture
def mock_audit_generator():
    """Create mock RuntimeAuditGenerator for unit tests."""
    generator = MagicMock()
    generator.resource_accessed = AsyncMock(return_value=MagicMock(event_id="evt-123"))
    generator.workflow_started = AsyncMock(return_value=MagicMock(event_id="evt-124"))
    generator.workflow_completed = AsyncMock(return_value=MagicMock(event_id="evt-125"))
    return generator


@pytest.fixture
def sample_constraints():
    """Create sample constraints for testing."""
    return [
        MockConstraint(
            id="con-001",
            constraint_type=MockConstraintType.DATA_SCOPE,
            value="department:finance",
            source="capability:cap-001",
        ),
        MockConstraint(
            id="con-002",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="delegation:del-001",
        ),
        MockConstraint(
            id="con-003",
            constraint_type=MockConstraintType.TIME_WINDOW,
            value="last_30_days",
            source="capability:cap-002",
        ),
        MockConstraint(
            id="con-004",
            constraint_type=MockConstraintType.RESOURCE_LIMIT,
            value="row_limit:1000",
            source="capability:cap-003",
        ),
        MockConstraint(
            id="con-005",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="no_pii",
            source="capability:cap-004",
        ),
    ]


@pytest.fixture
def sample_columns_with_pii():
    """Sample column names that include PII columns."""
    return [
        "id",
        "name",
        "email",
        "ssn",  # PII
        "social_security_number",  # PII
        "dob",  # PII
        "date_of_birth",  # PII
        "tax_id",  # PII
        "passport_number",  # PII
        "drivers_license",  # PII
        "department",
        "salary",  # Sensitive
        "password",  # Sensitive
        "api_key",  # Sensitive
        "created_at",
    ]


@pytest.fixture
def sample_columns_without_pii():
    """Sample column names without PII."""
    return [
        "id",
        "name",
        "email",
        "department",
        "created_at",
        "updated_at",
        "status",
        "category",
    ]


@pytest.fixture
def sample_trust_context():
    """Create sample RuntimeTrustContext for testing."""
    return MockRuntimeTrustContext(
        trace_id="trace-test-123",
        human_origin=MockHumanOrigin(human_id="alice@corp.com"),
        delegation_chain=["pseudo:alice@corp.com", "agent-001"],
        delegation_depth=1,
        constraints={"max_tokens": 1000},
        verification_mode="enforcing",
    )


@pytest.fixture
def mock_dataflow_instance():
    """Create mock DataFlow instance for testing."""
    df = MagicMock()
    df.get_models = MagicMock(return_value=["User", "Transaction", "Order"])
    df.execute = AsyncMock(return_value={"data": []})
    return df

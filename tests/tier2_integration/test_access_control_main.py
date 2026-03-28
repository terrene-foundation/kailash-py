"""Unit tests for main access_control.py module."""

import os
import sys
from datetime import UTC, datetime, time, timezone
from unittest.mock import Mock, patch

import pytest

# Import directly from the original access_control.py file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "access_control_main",
    os.path.join(os.path.dirname(__file__), "../../src/kailash/access_control.py"),
)
access_control_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access_control_main)

# Import from the main module
AccessControlManager = access_control_main.AccessControlManager
AccessDecision = access_control_main.AccessDecision
ConditionEvaluator = access_control_main.ConditionEvaluator
NodePermission = access_control_main.NodePermission
PermissionEffect = access_control_main.PermissionEffect
PermissionRule = access_control_main.PermissionRule
UserContext = access_control_main.UserContext
WorkflowPermission = access_control_main.WorkflowPermission
get_access_control_manager = access_control_main.get_access_control_manager
set_access_control_manager = access_control_main.set_access_control_manager


class TestUserContext:
    """Test UserContext dataclass."""

    def test_user_context_creation_minimal(self):
        """Test creating UserContext with minimal required fields."""
        user = UserContext(
            user_id="user123", tenant_id="tenant001", email="user@example.com"
        )

        assert user.user_id == "user123"
        assert user.tenant_id == "tenant001"
        assert user.email == "user@example.com"
        assert user.roles == []
        assert user.permissions == []
        assert user.attributes == {}
        assert user.session_id is None
        assert user.ip_address is None

    def test_user_context_creation_full(self):
        """Test creating UserContext with all fields."""
        user = UserContext(
            user_id="user123",
            tenant_id="tenant001",
            email="user@example.com",
            roles=["admin", "analyst"],
            permissions=["read", "write"],
            attributes={"department": "engineering"},
            session_id="session123",
            ip_address="192.168.1.1",
        )

        assert user.user_id == "user123"
        assert user.tenant_id == "tenant001"
        assert user.email == "user@example.com"
        assert user.roles == ["admin", "analyst"]
        assert user.permissions == ["read", "write"]
        assert user.attributes == {"department": "engineering"}
        assert user.session_id == "session123"
        assert user.ip_address == "192.168.1.1"

    def test_user_context_default_factory(self):
        """Test that default factory creates separate instances."""
        user1 = UserContext("u1", "t1", "e1@test.com")
        user2 = UserContext("u2", "t2", "e2@test.com")

        user1.roles.append("admin")
        assert user2.roles == []  # Should not be affected


class TestPermissionRule:
    """Test PermissionRule dataclass."""

    def test_permission_rule_creation_minimal(self):
        """Test creating PermissionRule with minimal required fields."""
        rule = PermissionRule(
            id="rule1",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
        )

        assert rule.id == "rule1"
        assert rule.resource_type == "node"
        assert rule.resource_id == "test_node"
        assert rule.permission == NodePermission.EXECUTE
        assert rule.effect == PermissionEffect.ALLOW
        assert rule.user_id is None
        assert rule.role is None
        assert rule.tenant_id is None
        assert rule.conditions == {}
        assert isinstance(rule.created_at, datetime)
        assert rule.created_by is None
        assert rule.expires_at is None
        assert rule.priority == 0

    def test_permission_rule_creation_full(self):
        """Test creating PermissionRule with all fields."""
        expires = datetime.now(UTC)
        created = datetime.now(UTC)

        rule = PermissionRule(
            id="rule1",
            resource_type="workflow",
            resource_id="test_workflow",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.DENY,
            user_id="user123",
            role="admin",
            tenant_id="tenant001",
            conditions={"time_range": {"start": "09:00", "end": "17:00"}},
            created_at=created,
            created_by="admin",
            expires_at=expires,
            priority=100,
        )

        assert rule.id == "rule1"
        assert rule.resource_type == "workflow"
        assert rule.resource_id == "test_workflow"
        assert rule.permission == WorkflowPermission.EXECUTE
        assert rule.effect == PermissionEffect.DENY
        assert rule.user_id == "user123"
        assert rule.role == "admin"
        assert rule.tenant_id == "tenant001"
        assert rule.conditions == {"time_range": {"start": "09:00", "end": "17:00"}}
        assert rule.created_at == created
        assert rule.created_by == "admin"
        assert rule.expires_at == expires
        assert rule.priority == 100


class TestAccessDecision:
    """Test AccessDecision dataclass."""

    def test_access_decision_creation_minimal(self):
        """Test creating AccessDecision with minimal fields."""
        decision = AccessDecision(allowed=True, reason="User has required role")

        assert decision.allowed is True
        assert decision.reason == "User has required role"
        assert decision.applied_rules == []
        assert decision.conditions_met == {}
        assert decision.masked_fields == []
        assert decision.redirect_node is None

    def test_access_decision_creation_full(self):
        """Test creating AccessDecision with all fields."""
        rule = PermissionRule(
            id="rule1",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
        )

        decision = AccessDecision(
            allowed=False,
            reason="Access denied by policy",
            applied_rules=[rule],
            conditions_met={"time_check": True, "ip_check": False},
            masked_fields=["ssn", "email"],
            redirect_node="alternative_node",
        )

        assert decision.allowed is False
        assert decision.reason == "Access denied by policy"
        assert decision.applied_rules == [rule]
        assert decision.conditions_met == {"time_check": True, "ip_check": False}
        assert decision.masked_fields == ["ssn", "email"]
        assert decision.redirect_node == "alternative_node"


class TestConditionEvaluator:
    """Test ConditionEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create ConditionEvaluator instance."""
        return ConditionEvaluator()

    @pytest.fixture
    def sample_context(self):
        """Create sample context for testing."""
        user = UserContext(
            user_id="user123",
            tenant_id="tenant001",
            email="user@example.com",
            attributes={"department": "engineering"},
            ip_address="192.168.1.100",
        )
        return {"user": user, "data": {"status": "active", "priority": "high"}}

    def test_evaluator_initialization(self, evaluator):
        """Test evaluator initializes with correct evaluators."""
        expected_evaluators = {
            "time_range",
            "data_contains",
            "user_attribute",
            "ip_range",
            "custom",
        }
        assert set(evaluator.evaluators.keys()) == expected_evaluators

    @patch("datetime.datetime")
    def test_eval_time_range_within_range(self, mock_datetime, evaluator):
        """Test time range evaluation when current time is within range."""
        # Mock current time to 14:30
        mock_datetime.now.return_value.time.return_value = time(14, 30)

        condition_value = {"start": "09:00", "end": "17:00"}
        context = {}

        result = evaluator._eval_time_range(condition_value, context)
        assert result is True

    @patch("datetime.datetime")
    def test_eval_time_range_outside_range(self, mock_datetime, evaluator):
        """Test time range evaluation when current time is outside range."""
        # Mock current time to 20:00
        mock_datetime.now.return_value.time.return_value = time(20, 0)

        condition_value = {"start": "09:00", "end": "17:00"}
        context = {}

        result = evaluator._eval_time_range(condition_value, context)
        assert result is False

    def test_eval_time_range_default_values(self, evaluator):
        """Test time range evaluation with default start/end values."""
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value.time.return_value = time(12, 0)

            # Empty condition should use defaults (00:00-23:59)
            condition_value = {}
            context = {}

            result = evaluator._eval_time_range(condition_value, context)
            assert result is True

    def test_eval_data_contains_match(self, evaluator, sample_context):
        """Test data contains evaluation with matching value."""
        condition_value = {"field": "status", "value": "active"}

        result = evaluator._eval_data_contains(condition_value, sample_context)
        assert result is True

    def test_eval_data_contains_no_match(self, evaluator, sample_context):
        """Test data contains evaluation with non-matching value."""
        condition_value = {"field": "status", "value": "inactive"}

        result = evaluator._eval_data_contains(condition_value, sample_context)
        assert result is False

    def test_eval_data_contains_missing_field(self, evaluator, sample_context):
        """Test data contains evaluation with missing field."""
        condition_value = {"field": "nonexistent", "value": "test"}

        result = evaluator._eval_data_contains(condition_value, sample_context)
        assert result is False

    def test_eval_user_attribute_match(self, evaluator, sample_context):
        """Test user attribute evaluation with matching attribute."""
        condition_value = {"attribute": "department", "value": "engineering"}

        result = evaluator._eval_user_attribute(condition_value, sample_context)
        assert result is True

    def test_eval_user_attribute_no_match(self, evaluator, sample_context):
        """Test user attribute evaluation with non-matching attribute."""
        condition_value = {"attribute": "department", "value": "sales"}

        result = evaluator._eval_user_attribute(condition_value, sample_context)
        assert result is False

    def test_eval_user_attribute_no_user(self, evaluator):
        """Test user attribute evaluation with no user in context."""
        condition_value = {"attribute": "department", "value": "engineering"}
        context = {}

        result = evaluator._eval_user_attribute(condition_value, context)
        assert result is False

    def test_eval_ip_range_allowed(self, evaluator):
        """Test IP range evaluation with allowed IP."""
        condition_value = {"allowed": ["192.168.1.100", "10.0.0.1"]}
        context = {"user": {"ip_address": "192.168.1.100"}}

        result = evaluator._eval_ip_range(condition_value, context)
        assert result is True

    def test_eval_ip_range_not_allowed(self, evaluator):
        """Test IP range evaluation with non-allowed IP."""
        condition_value = {"allowed": ["10.0.0.1", "172.16.0.1"]}
        context = {"user": {"ip_address": "192.168.1.100"}}

        result = evaluator._eval_ip_range(condition_value, context)
        assert result is False

    def test_eval_ip_range_no_user_ip(self, evaluator):
        """Test IP range evaluation with no user IP."""
        condition_value = {"allowed": ["192.168.1.100"]}
        context = {"user": {}}  # No IP

        result = evaluator._eval_ip_range(condition_value, context)
        assert result is False

    def test_eval_custom_always_true(self, evaluator):
        """Test custom evaluation (simplified implementation)."""
        condition_value = {"function": "custom_check"}
        context = {}

        result = evaluator._eval_custom(condition_value, context)
        assert result is True

    def test_evaluate_known_condition(self, evaluator):
        """Test evaluate method with known condition type."""
        mock_eval = Mock(return_value=True)
        evaluator.evaluators["time_range"] = mock_eval

        condition_value = {"start": "09:00", "end": "17:00"}
        context = {}

        result = evaluator.evaluate("time_range", condition_value, context)

        assert result is True
        mock_eval.assert_called_once_with(condition_value, context)

    def test_evaluate_unknown_condition(self, evaluator):
        """Test evaluate method with unknown condition type."""
        condition_value = {"test": "value"}
        context = {}

        result = evaluator.evaluate("unknown_type", condition_value, context)
        assert result is False

    def test_evaluate_exception_handling(self, evaluator):
        """Test evaluate method handles exceptions gracefully."""
        with patch.object(
            evaluator, "_eval_time_range", side_effect=Exception("Test error")
        ):
            condition_value = {"start": "invalid"}
            context = {}

            result = evaluator.evaluate("time_range", condition_value, context)
            assert result is False


class TestAccessControlManager:
    """Test AccessControlManager class."""

    @pytest.fixture
    def manager(self):
        """Create AccessControlManager instance."""
        return AccessControlManager(enabled=True)

    @pytest.fixture
    def disabled_manager(self):
        """Create disabled AccessControlManager instance."""
        return AccessControlManager(enabled=False)

    @pytest.fixture
    def sample_user(self):
        """Create sample user for testing."""
        return UserContext(
            user_id="user123",
            tenant_id="tenant001",
            email="user@example.com",
            roles=["analyst"],
            ip_address="192.168.1.100",
        )

    @pytest.fixture
    def sample_rule_allow(self):
        """Create sample allow rule."""
        return PermissionRule(
            id="allow_analyst_execute",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        )

    @pytest.fixture
    def sample_rule_deny(self):
        """Create sample deny rule."""
        return PermissionRule(
            id="deny_all_sensitive",
            resource_type="node",
            resource_id="sensitive_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.DENY,
            priority=100,  # Higher priority
        )

    def test_manager_initialization_enabled(self):
        """Test manager initialization with access control enabled."""
        manager = AccessControlManager(enabled=True)

        assert manager.enabled is True
        assert manager.rules == []
        assert isinstance(manager.condition_evaluator, ConditionEvaluator)

    def test_manager_initialization_disabled(self):
        """Test manager initialization with access control disabled."""
        manager = AccessControlManager(enabled=False)

        assert manager.enabled is False
        assert manager.rules == []

    def test_add_rule(self, manager, sample_rule_allow):
        """Test adding a permission rule."""
        manager.add_rule(sample_rule_allow)

        assert len(manager.rules) == 1
        assert manager.rules[0] == sample_rule_allow

    def test_add_multiple_rules_sorted_by_priority(
        self, manager, sample_rule_allow, sample_rule_deny
    ):
        """Test that rules are maintained in order when added."""
        # Add lower priority rule first
        manager.add_rule(sample_rule_allow)  # priority 0
        manager.add_rule(sample_rule_deny)  # priority 100

        # Rules are stored in the order they were added
        assert len(manager.rules) == 2
        assert manager.rules[0] == sample_rule_allow  # First added
        assert manager.rules[1] == sample_rule_deny  # Second added

    def test_remove_rule(self, manager, sample_rule_allow):
        """Test removing a permission rule."""
        manager.add_rule(sample_rule_allow)
        assert len(manager.rules) == 1

        manager.remove_rule("allow_analyst_execute")
        assert len(manager.rules) == 0

    def test_remove_nonexistent_rule(self, manager):
        """Test removing a non-existent rule."""
        # Should not raise an exception
        manager.remove_rule("nonexistent_rule")
        assert len(manager.rules) == 0

    def test_check_workflow_access_disabled(self, disabled_manager, sample_user):
        """Test workflow access check when access control is disabled."""
        decision = disabled_manager.check_workflow_access(
            sample_user, "test_workflow", WorkflowPermission.EXECUTE
        )

        assert decision.allowed is True
        assert "Access control disabled" in decision.reason

    def test_check_workflow_access_no_rules(self, manager, sample_user):
        """Test workflow access check with no matching rules."""
        decision = manager.check_workflow_access(
            sample_user, "test_workflow", WorkflowPermission.EXECUTE
        )

        assert decision.allowed is False
        assert "No matching rules" in decision.reason

    def test_check_workflow_access_allow_rule(self, manager, sample_user):
        """Test workflow access check with allow rule."""
        rule = PermissionRule(
            id="allow_analyst_workflow",
            resource_type="workflow",
            resource_id="test_workflow",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        )
        manager.add_rule(rule)

        decision = manager.check_workflow_access(
            sample_user, "test_workflow", WorkflowPermission.EXECUTE
        )

        assert decision.allowed is True
        assert rule in decision.applied_rules

    def test_check_workflow_access_deny_rule(self, manager, sample_user):
        """Test workflow access check with deny rule."""
        rule = PermissionRule(
            id="deny_analyst_workflow",
            resource_type="workflow",
            resource_id="test_workflow",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.DENY,
            role="analyst",
        )
        manager.add_rule(rule)

        decision = manager.check_workflow_access(
            sample_user, "test_workflow", WorkflowPermission.EXECUTE
        )

        assert decision.allowed is False
        assert rule in decision.applied_rules

    def test_check_node_access_disabled(self, disabled_manager, sample_user):
        """Test node access check when access control is disabled."""
        decision = disabled_manager.check_node_access(
            sample_user, "test_node", NodePermission.EXECUTE
        )

        assert decision.allowed is True
        assert "Access control disabled" in decision.reason

    def test_check_node_access_allow(self, manager, sample_user, sample_rule_allow):
        """Test node access check with allow rule."""
        manager.add_rule(sample_rule_allow)

        decision = manager.check_node_access(
            sample_user, "test_node", NodePermission.EXECUTE
        )

        assert decision.allowed is True
        assert sample_rule_allow in decision.applied_rules

    def test_check_node_access_deny(self, manager, sample_user, sample_rule_deny):
        """Test node access check with deny rule."""
        manager.add_rule(sample_rule_deny)

        decision = manager.check_node_access(
            sample_user, "sensitive_node", NodePermission.EXECUTE
        )

        assert decision.allowed is False
        assert sample_rule_deny in decision.applied_rules

    def test_check_node_access_with_conditions(self, manager, sample_user):
        """Test node access check with conditional rule."""
        rule = PermissionRule(
            id="conditional_allow",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.CONDITIONAL,
            role="analyst",
            conditions={"time_range": {"start": "09:00", "end": "17:00"}},
        )
        manager.add_rule(rule)

        with patch.object(manager.condition_evaluator, "evaluate", return_value=True):
            decision = manager.check_node_access(
                sample_user, "test_node", NodePermission.EXECUTE
            )

            assert decision.allowed is True

    def test_get_accessible_nodes_disabled(self, disabled_manager, sample_user):
        """Test get accessible nodes when access control is disabled."""
        nodes = ["node1", "node2", "node3"]
        accessible = disabled_manager.get_accessible_nodes(
            sample_user, nodes, NodePermission.EXECUTE
        )

        assert accessible == nodes

    def test_get_accessible_nodes_with_rules(self, manager, sample_user):
        """Test get accessible nodes with permission rules."""
        # Allow access to node1
        rule1 = PermissionRule(
            id="allow_node1",
            resource_type="node",
            resource_id="node1",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        )
        # Deny access to node2
        rule2 = PermissionRule(
            id="deny_node2",
            resource_type="node",
            resource_id="node2",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.DENY,
            role="analyst",
        )

        manager.add_rule(rule1)
        manager.add_rule(rule2)

        nodes = ["node1", "node2", "node3"]
        accessible = manager.get_accessible_nodes(
            sample_user, nodes, NodePermission.EXECUTE
        )

        # Only node1 should be accessible (allowed), node3 has no rules (denied by default)
        assert accessible == ["node1"]

    def test_get_permission_based_route_no_alternatives(self, manager, sample_user):
        """Test permission-based routing with no alternatives."""
        route = manager.get_permission_based_route(
            sample_user, "test_node", NodePermission.EXECUTE
        )

        assert route is None

    def test_get_permission_based_route_with_alternatives(self, manager, sample_user):
        """Test permission-based routing with alternative node."""
        # Deny primary node but provide alternative
        rule = PermissionRule(
            id="deny_with_redirect",
            resource_type="node",
            resource_id="restricted_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.DENY,
            role="analyst",
        )
        manager.add_rule(rule)

        alternatives = {"restricted_node": "public_node"}
        route = manager.get_permission_based_route(
            sample_user, "restricted_node", NodePermission.EXECUTE, alternatives
        )

        assert route == "public_node"

    def test_mask_node_output_no_rules(self, manager, sample_user):
        """Test output masking with no masking rules."""
        output_data = {"name": "John", "ssn": "123-45-6789"}

        masked = manager.mask_node_output(sample_user, "test_node", output_data)

        assert masked == output_data

    def test_mask_node_output_with_masking(self, manager, sample_user):
        """Test output masking with masking rules."""
        # Create rule that masks output
        rule = PermissionRule(
            id="mask_sensitive",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.MASK_OUTPUT,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        )
        manager.add_rule(rule)

        output_data = {
            "name": "John",
            "ssn": "123-45-6789",
            "email": "john@example.com",
        }

        # Mock the decision to include masked fields
        with patch.object(manager, "_evaluate_rules") as mock_eval:
            mock_decision = AccessDecision(
                allowed=True, reason="Masking applied", masked_fields=["ssn", "email"]
            )
            mock_eval.return_value = mock_decision

            masked = manager.mask_node_output(sample_user, "test_node", output_data)

            assert masked["name"] == "John"
            assert masked["ssn"] == "***MASKED***"
            assert masked["email"] == "***MASKED***"

    def test_rule_applies_to_user_by_user_id(self, manager, sample_user):
        """Test rule application by specific user ID."""
        rule = PermissionRule(
            id="user_specific",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            user_id="user123",
        )

        assert manager._rule_applies_to_user(rule, sample_user) is True

    def test_rule_applies_to_user_by_role(self, manager, sample_user):
        """Test rule application by user role."""
        rule = PermissionRule(
            id="role_specific",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        )

        assert manager._rule_applies_to_user(rule, sample_user) is True

    def test_rule_applies_to_user_by_tenant(self, manager, sample_user):
        """Test rule application by tenant ID."""
        rule = PermissionRule(
            id="tenant_specific",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            tenant_id="tenant001",
        )

        assert manager._rule_applies_to_user(rule, sample_user) is True

    def test_rule_does_not_apply_wrong_user(self, manager, sample_user):
        """Test rule does not apply to wrong user."""
        rule = PermissionRule(
            id="other_user",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            user_id="other_user",
        )

        assert manager._rule_applies_to_user(rule, sample_user) is False

    def test_rule_does_not_apply_wrong_role(self, manager, sample_user):
        """Test rule does not apply to user without role."""
        rule = PermissionRule(
            id="admin_only",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )

        assert manager._rule_applies_to_user(rule, sample_user) is False

    def test_audit_log_called(self, manager, sample_user):
        """Test that audit logging is called during access checks."""
        with patch.object(manager, "_audit_log") as mock_audit:
            manager.check_node_access(sample_user, "test_node", NodePermission.EXECUTE)

            mock_audit.assert_called_once()


class TestGlobalAccessControlManager:
    """Test global access control manager functions."""

    def test_get_access_control_manager_default(self):
        """Test getting default access control manager."""
        manager = get_access_control_manager()

        assert isinstance(manager, AccessControlManager)
        assert manager.enabled is False  # Default is disabled

    def test_set_and_get_access_control_manager(self):
        """Test setting and getting custom access control manager."""
        custom_manager = AccessControlManager(enabled=True)

        set_access_control_manager(custom_manager)
        retrieved_manager = get_access_control_manager()

        assert retrieved_manager is custom_manager
        assert retrieved_manager.enabled is True

        # Reset to default for other tests
        set_access_control_manager(AccessControlManager(enabled=False))

#!/usr/bin/env python3
"""Demonstration of Attribute-Based Access Control (ABAC) in Kailash SDK.

This example shows how to use the enhanced access control system with
attribute-based permissions, including:
- Department hierarchy matching
- Security clearance levels
- Geographic region restrictions
- Time-based access
- Attribute-based data masking
"""

import asyncio
from datetime import datetime

from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    create_attribute_condition,
    create_complex_condition,
)
from kailash.access_control_abac import (
    AttributeCondition,
    AttributeExpression,
    AttributeMaskingRule,
    AttributeOperator,
    LogicalOperator,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.workflow import Workflow


@register_node()
class SensitiveDataNode(Node):
    """Node that outputs sensitive data for testing ABAC."""

    def define_parameters(self) -> list[NodeParameter]:
        return [
            NodeParameter(
                name="data_type", type="str", required=False, default="financial"
            )
        ]

    def run(self, **inputs) -> dict:
        """Generate sensitive test data."""
        return {
            "result": {
                "employee_id": "EMP12345",
                "name": "John Doe",
                "salary": 95000,
                "ssn": "123-45-6789",
                "department": "engineering.backend",
                "performance_rating": "excellent",
                "stock_options": 50000,
                "medical_records": {
                    "blood_type": "O+",
                    "conditions": ["none"],
                    "insurance_id": "INS98765",
                },
            }
        }


def create_abac_rules():
    """Create example ABAC rules demonstrating various patterns."""
    rules = []

    # Rule 1: Department hierarchy - engineering can access engineering data
    rules.append(
        PermissionRule(
            id="eng_dept_access",
            resource_type="node",
            resource_id="sensitive_data",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
            conditions={
                "type": "department_hierarchy",
                "value": {"department": "engineering", "include_children": True},
            },
        )
    )

    # Rule 2: Security clearance - secret or above for financial data
    rules.append(
        PermissionRule(
            id="financial_clearance",
            resource_type="node",
            resource_id="financial_data",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions={
                "type": "security_clearance",
                "value": {"minimum_clearance": "secret"},
            },
        )
    )

    # Rule 3: Complex condition - department AND region AND time
    rules.append(
        PermissionRule(
            id="regional_time_access",
            resource_type="node",
            resource_id="regional_data",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions=create_complex_condition(
                "and",
                [
                    create_attribute_condition(
                        "user.attributes.department", "hierarchical_match", "sales"
                    ),
                    create_attribute_condition(
                        "user.attributes.region", "in", ["us-west", "us-east"]
                    ),
                    {
                        "type": "time_of_day",
                        "value": {"start": "08:00", "end": "18:00"},
                    },
                ],
            ),
        )
    )

    # Rule 4: Attribute expression with NOT logic
    rules.append(
        PermissionRule(
            id="non_contractor_access",
            resource_type="node",
            resource_id="internal_systems",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions=create_complex_condition(
                "not",
                [
                    create_attribute_condition(
                        "user.attributes.employee_type", "equals", "contractor"
                    )
                ],
            ),
        )
    )

    # Rule 5: Multiple attributes with OR
    rules.append(
        PermissionRule(
            id="executive_or_hr_access",
            resource_type="node",
            resource_id="compensation_data",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
            conditions=create_complex_condition(
                "or",
                [
                    create_attribute_condition(
                        "user.attributes.department", "equals", "hr"
                    ),
                    create_attribute_condition(
                        "user.attributes.job_level", "greater_or_equal", "director"
                    ),
                ],
            ),
        )
    )

    return rules


def create_masking_rules():
    """Create attribute-based data masking rules."""
    rules = []

    # Mask SSN for non-HR users
    rules.append(
        AttributeMaskingRule(
            field_path="ssn",
            mask_type="redact",
            condition=AttributeExpression(
                operator=LogicalOperator.NOT,
                conditions=[
                    AttributeCondition(
                        attribute_path="user.attributes.department",
                        operator=AttributeOperator.EQUALS,
                        value="hr",
                    )
                ],
            ),
        )
    )

    # Partially mask salary for non-managers
    rules.append(
        AttributeMaskingRule(
            field_path="salary",
            mask_type="partial",
            condition=AttributeExpression(
                operator=LogicalOperator.NOT,
                conditions=[
                    AttributeCondition(
                        attribute_path="user.attributes.is_manager",
                        operator=AttributeOperator.EQUALS,
                        value=True,
                    )
                ],
            ),
        )
    )

    # Replace medical records for non-medical staff
    rules.append(
        AttributeMaskingRule(
            field_path="medical_records",
            mask_type="replace",
            mask_value={"status": "restricted"},
            condition=AttributeExpression(
                operator=LogicalOperator.NOT,
                conditions=[
                    AttributeCondition(
                        attribute_path="user.attributes.department",
                        operator=AttributeOperator.IN,
                        value=["medical", "hr"],
                    )
                ],
            ),
        )
    )

    return rules


def create_test_users():
    """Create test users with different attributes."""
    users = []

    # Engineering manager with secret clearance
    users.append(
        UserContext(
            user_id="eng_mgr_001",
            tenant_id="acme_corp",
            email="alice@acme.com",
            roles=["engineer", "manager"],
            attributes={
                "department": "engineering.backend.api",
                "security_clearance": "secret",
                "region": "us-west",
                "employee_type": "full_time",
                "job_level": "manager",
                "is_manager": True,
            },
        )
    )

    # HR specialist
    users.append(
        UserContext(
            user_id="hr_spec_001",
            tenant_id="acme_corp",
            email="bob@acme.com",
            roles=["hr_specialist"],
            attributes={
                "department": "hr",
                "security_clearance": "confidential",
                "region": "us-east",
                "employee_type": "full_time",
                "job_level": "specialist",
                "is_manager": False,
            },
        )
    )

    # Sales contractor
    users.append(
        UserContext(
            user_id="sales_cont_001",
            tenant_id="acme_corp",
            email="charlie@acme.com",
            roles=["sales"],
            attributes={
                "department": "sales.west",
                "security_clearance": "public",
                "region": "us-west",
                "employee_type": "contractor",
                "job_level": "associate",
                "is_manager": False,
            },
        )
    )

    # Executive with top secret clearance
    users.append(
        UserContext(
            user_id="exec_001",
            tenant_id="acme_corp",
            email="diana@acme.com",
            roles=["executive"],
            attributes={
                "department": "executive",
                "security_clearance": "top_secret",
                "region": "global",
                "employee_type": "full_time",
                "job_level": "cto",
                "is_manager": True,
            },
        )
    )

    return users


async def demonstrate_abac():
    """Run ABAC demonstration."""
    print("=== Kailash SDK ABAC Demonstration ===\n")

    # Create access control manager
    acm = AccessControlManager(strategy="abac")

    # Add ABAC rules
    print("1. Setting up ABAC rules...")
    for rule in create_abac_rules():
        acm.add_rule(rule)
        print(f"   Added rule: {rule.id}")

    # Add masking rules
    print("\n2. Setting up data masking rules...")
    for rule in create_masking_rules():
        acm.add_masking_rule("sensitive_data", rule)
        print(f"   Added masking rule for field: {rule.field_path}")

    # Create test workflow
    print("\n3. Creating test workflow...")
    workflow = Workflow(name="abac_test_workflow")
    workflow.add_node("sensitive_data", SensitiveDataNode())

    # Test with different users
    print("\n4. Testing access with different users...\n")
    users = create_test_users()

    for user in users:
        print(f"Testing user: {user.email}")
        print(f"  Department: {user.attributes.get('department')}")
        print(f"  Clearance: {user.attributes.get('security_clearance')}")
        print(f"  Employee Type: {user.attributes.get('employee_type')}")

        # Check node access
        decision = acm.check_node_access(
            user, "sensitive_data", NodePermission.READ_OUTPUT
        )
        print(f"  Can read sensitive data: {decision.allowed}")

        if decision.allowed:
            # Create runtime with access control
            runtime = AccessControlledRuntime(
                access_control_manager=acm, user_context=user
            )

            # Execute workflow
            results = runtime.execute(workflow)

            # Get node output
            if "sensitive_data" in results:
                raw_data = results["sensitive_data"]["result"]

                # Apply masking
                masked_data = acm.apply_data_masking(user, "sensitive_data", raw_data)

                print("  Data received:")
                for key, value in masked_data.items():
                    if isinstance(value, dict):
                        print(f"    {key}: {value}")
                    else:
                        print(f"    {key}: {value}")

        print()

    # Demonstrate permission analysis
    print("5. Permission Analysis for Engineering Manager:")
    eng_manager = users[0]

    # Export applicable rules
    applicable_rules = acm.export_rules_for_user(eng_manager)
    print(f"   Rules that could apply: {len(applicable_rules)}")
    for rule in applicable_rules[:3]:  # Show first 3
        print(f"   - {rule['id']}: {rule['permission']} on {rule['resource_id']}")

    # Get effective permissions
    print("\n6. Effective Permissions on 'sensitive_data' node:")
    permissions = acm.get_user_effective_permissions(
        eng_manager, "node", "sensitive_data"
    )
    for perm, allowed in permissions.items():
        print(f"   {perm}: {'✓' if allowed else '✗'}")

    print("\n=== ABAC Demonstration Complete ===")


if __name__ == "__main__":
    asyncio.run(demonstrate_abac())

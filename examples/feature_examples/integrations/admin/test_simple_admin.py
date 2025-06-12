#!/usr/bin/env python3
"""
Simple test to verify admin nodes can be imported and created.
"""

print("Testing admin node imports...")

try:
    # Test basic imports
    from kailash.nodes.base import Node
    print("✅ Base node imported")
    
    # Import admin module step by step
    import kailash.nodes.admin
    print("✅ Admin module imported")
    
    # Try importing individual nodes
    from kailash.nodes.admin.user_management import UserManagementNode
    print("✅ UserManagementNode imported")
    
    from kailash.nodes.admin.role_management import RoleManagementNode
    print("✅ RoleManagementNode imported")
    
    from kailash.nodes.admin.permission_check import PermissionCheckNode
    print("✅ PermissionCheckNode imported")
    
    from kailash.nodes.admin.audit_log import AuditLogNode
    print("✅ AuditLogNode imported")
    
    from kailash.nodes.admin.security_event import SecurityEventNode
    print("✅ SecurityEventNode imported")
    
    # Test creating a simple node
    user_node = UserManagementNode(
        name="test_user",
        operation="create",
        user_data={
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User"
        }
    )
    print("✅ UserManagementNode created successfully")
    
    # Check node parameters
    params = user_node.get_parameters()
    print(f"✅ Node has {len(params)} parameters")
    
    print("\n🎉 All admin nodes imported and created successfully!")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
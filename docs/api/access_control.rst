.. _api_access_control:


Access Control
==============

The access control module provides comprehensive security and permission management for
workflows.

.. automodule:: kailash.access_control
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Access Control Manager
----------------------

.. autoclass:: kailash.access_control.AccessControlManager
   :members:
   :undoc-members:
   :show-inheritance:

User Context
------------

.. autoclass:: kailash.access_control.UserContext
   :members:
   :undoc-members:
   :show-inheritance:

Permission Rules
----------------

.. autoclass:: kailash.access_control.PermissionRule
   :members:
   :undoc-members:
   :show-inheritance:

Access Decisions
----------------

.. autoclass:: kailash.access_control.AccessDecision
   :members:
   :undoc-members:
   :show-inheritance:

Enumerations
------------

.. autoclass:: kailash.access_control.WorkflowPermission
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kailash.access_control.NodePermission
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kailash.access_control.PermissionEffect
   :members:
   :undoc-members:
   :show-inheritance:

Access Controlled Runtime
-------------------------

.. automodule:: kailash.runtime.access_controlled
   :members:
   :undoc-members:
   :show-inheritance:

Base Nodes with ACL
-------------------

.. automodule:: kailash.nodes.base_with_acl
   :members:
   :undoc-members:
   :show-inheritance:

Examples
--------

Basic RBAC Setup
~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.access_control import (
       UserContext, PermissionRule, NodePermission,
       WorkflowPermission, PermissionEffect, get_access_control_manager
   )
   from kailash.runtime.access_controlled import AccessControlledRuntime

   # Create user context
   user = UserContext(
       user_id="john_doe",
       tenant_id="acme_corp",
       email="john@acme.com",
       roles=["analyst", "viewer"]
   )

   # Configure access control
   acm = get_access_control_manager()
   acm.enabled = True

   # Add permission rules
   acm.add_rule(PermissionRule(
       id="allow_analysts_execute",
       resource_type="workflow",
       resource_id="customer_analytics",
       permission=WorkflowPermission.EXECUTE,
       effect=PermissionEffect.ALLOW,
       role="analyst"
   ))

   # Use secure runtime
   runtime = AccessControlledRuntime(user_context=user)
   result, run_id = runtime.execute(workflow)

Multi-Tenant Isolation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create tenant-specific rules
   tenant_rule = PermissionRule(
       id="tenant_isolation",
       resource_type="node",
       resource_id="sensitive_data",
       permission=NodePermission.READ_OUTPUT,
       effect=PermissionEffect.ALLOW,
       tenant_id="acme_corp"  # Only ACME users can access
   )

   acm.add_rule(tenant_rule)

   # Users from other tenants will be denied access
   other_user = UserContext(
       user_id="jane_smith",
       tenant_id="other_corp",
       email="jane@other.com",
       roles=["admin"]
   )

   # This will be denied due to tenant mismatch
   runtime = AccessControlledRuntime(user_context=other_user)

Data Masking
~~~~~~~~~~~~

.. code-block:: python

   from kailash.nodes.base_with_acl import add_access_control
   from kailash.nodes.data.readers import CSVReaderNode

   # Create secure data reader with field masking
   secure_reader = add_access_control(
       CSVReaderNode(file_path="customers.csv"),
       enable_access_control=True,
       required_permission=NodePermission.READ_OUTPUT,
       mask_output_fields=["ssn", "phone"]  # Mask for non-admin users
   )

   workflow.add_node("secure_data", secure_reader)

Permission-Based Routing
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Different processing based on user permissions
   admin_processor = PythonCodeNode.from_function(
       lambda data: {"result": process_all_data(data)},
       name="admin_processor"
   )

   viewer_processor = PythonCodeNode.from_function(
       lambda data: {"result": process_summary_data(data)},
       name="viewer_processor"
   )

   # Configure different permissions for each path
   acm.add_rule(PermissionRule(
       id="admin_full_access",
       resource_type="node",
       resource_id="admin_processor",
       permission=NodePermission.EXECUTE,
       effect=PermissionEffect.ALLOW,
       role="admin"
   ))

   acm.add_rule(PermissionRule(
       id="viewer_limited_access",
       resource_type="node",
       resource_id="viewer_processor",
       permission=NodePermission.EXECUTE,
       effect=PermissionEffect.ALLOW,
       role="viewer"
   ))

   # Runtime will automatically route based on user permissions
   workflow.add_node("admin_path", admin_processor)
   workflow.add_node("viewer_path", viewer_processor)

.. _security:


Security
========

This document outlines security considerations and best practices when using the
Kailash Python SDK.

Security Features
-----------------

The Kailash Python SDK includes several security features to protect your workflows:

1. **Sandboxed Code Execution**

   The ``PythonCodeNode`` executes user code in a restricted environment:

   - Limited namespace access
   - No access to system modules by default
   - Configurable allowed imports
   - Execution timeouts (implemented)
   - Memory limits (implemented on Unix systems)
   - AST-based code safety validation
   - Input sanitization

2. **Input Validation**

   All nodes validate inputs before execution:

   - Type checking with Pydantic
   - Path traversal prevention
   - SQL injection protection in database nodes
   - XSS prevention in web-related nodes

3. **Secure Credential Handling**

   - Support for environment variables
   - No hardcoded credentials in code
   - Integration with secret managers (planned)

4. **Production Security Framework**

   The SDK includes a comprehensive security framework (``kailash.security``):

   - Configurable security policies with ``SecurityConfig``
   - Path traversal prevention for all file operations
   - Command injection detection and validation
   - Secure file operations with ``safe_open()``
   - SecurityMixin for node-level security integration
   - Comprehensive audit logging

5. **Access Control and RBAC**

   The SDK provides comprehensive access control capabilities
   (``kailash.access_control``):

   - Role-based access control (RBAC) with user contexts
   - Multi-tenant isolation with complete data separation
   - Node-level and workflow-level permissions
   - Field-level data masking for sensitive information
   - Permission-based conditional routing
   - JWT authentication support
   - Comprehensive audit logging for compliance
   - Backward compatibility with existing workflows

Security Best Practices
-----------------------

File Operations
~~~~~~~~~~~~~~~

When using file I/O nodes:

- **Validate Paths**: Always validate file paths to prevent directory traversal
- **Check Permissions**: Ensure proper file permissions
- **Limit Access**: Restrict file access to specific directories

.. code-block:: python

   # Good: Restricted to specific directory
   import os
   from pathlib import Path

   safe_dir = Path("/app/data").resolve()
   file_path = (safe_dir / user_input).resolve()

   if not str(file_path).startswith(str(safe_dir)):
       raise ValueError("Invalid file path")

Code Execution
~~~~~~~~~~~~~~

When using ``PythonCodeNode``:

- **Review Code**: Always review code before execution
- **Limit Imports**: Restrict available modules
- **Set Timeouts**: Use execution timeouts
- **Monitor Resources**: Track CPU and memory usage

.. code-block:: python

   from kailash.nodes.code import PythonCodeNode

   # Configure with restrictions
   node = PythonCodeNode(
       code="# user code here",
       allowed_imports=["math", "json"],  # Limit imports
       timeout=30,  # 30 second timeout (when implemented)
       max_memory_mb=512  # Memory limit (when implemented)
   )

API Integration
~~~~~~~~~~~~~~~

When integrating with external APIs:

- **Use HTTPS**: Always use encrypted connections
- **Validate Certificates**: Don't disable SSL verification
- **Secure Storage**: Store API keys securely
- **Rate Limiting**: Implement rate limiting
- **Input Sanitization**: Sanitize data before sending

.. code-block:: python

   import os
   from kailash.nodes.api import HTTPRequestNode

   # Good: Using environment variables
   api_node = HTTPRequestNode(
       url="https://api.example.com/data",
       headers={
           "Authorization": f"Bearer {os.getenv('API_TOKEN')}"
       },
       verify_ssl=True  # Always verify SSL
   )

Access Control
~~~~~~~~~~~~~~

When implementing access control in workflows:

- **Define Clear Roles**: Create specific roles with minimal required permissions
- **Implement Tenant Isolation**: Ensure complete data separation between tenants
- **Use Field Masking**: Protect sensitive data with role-based masking
- **Enable Audit Logging**: Track all access attempts for compliance
- **Test Permissions**: Validate access control rules before deployment

.. code-block:: python

   from kailash.access_control import (
       UserContext, PermissionRule, NodePermission,
       WorkflowPermission, PermissionEffect, get_access_control_manager
   )
   from kailash.runtime.access_controlled import AccessControlledRuntime

   # Define user context with roles
   user = UserContext(
       user_id="analyst_001",
       tenant_id="company_abc",
       email="analyst@company.com",
       roles=["analyst", "viewer"]
   )

   # Configure access control manager
   acm = get_access_control_manager()
   acm.enabled = True

   # Add permission rules
   acm.add_rule(PermissionRule(
       id="analysts_can_read",
       resource_type="node",
       resource_id="customer_data",
       permission=NodePermission.READ_OUTPUT,
       effect=PermissionEffect.ALLOW,
       role="analyst"
   ))

   # Use secure runtime
   runtime = AccessControlledRuntime(user_context=user)
   results, run_id = runtime.execute(workflow)

Multi-Tenant Security
~~~~~~~~~~~~~~~~~~~~~

For multi-tenant deployments:

- **Tenant Isolation**: Implement strict tenant boundaries
- **Data Segregation**: Ensure no cross-tenant data leakage
- **Resource Quotas**: Limit per-tenant resource usage
- **Audit Trails**: Maintain separate audit logs per tenant

.. code-block:: python

   # Tenant-specific permission rule
   tenant_rule = PermissionRule(
       id="tenant_isolation",
       resource_type="workflow",
       resource_id="analytics_workflow",
       permission=WorkflowPermission.EXECUTE,
       effect=PermissionEffect.ALLOW,
       tenant_id="tenant_123"  # Only this tenant can access
   )

   acm.add_rule(tenant_rule)

Known Security Considerations
-----------------------------

1. **Python Code Execution**

   The ``PythonCodeNode`` allows arbitrary code execution. While we provide
   sandboxing, it's not foolproof. For production use:

   - Run in isolated containers
   - Use separate service accounts
   - Monitor resource usage
   - Implement network isolation

2. **File System Access**

   File I/O nodes have access to the file system. To mitigate risks:

   - Run with minimal permissions
   - Use chroot or containers
   - Implement quota limits
   - Monitor file operations

3. **Network Access**

   API nodes can make external requests. Consider:

   - Network segmentation
   - Egress filtering
   - DNS filtering
   - Proxy configuration

Reporting Security Issues
-------------------------

If you discover a security vulnerability:

1. **Do NOT** open a public issue
2. Email security@terrene.foundation with:

   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

3. We will respond within 48 hours
4. We will work on a fix and coordinate disclosure

Security Roadmap
----------------

Planned security enhancements:

- ✅ Basic input validation
- ✅ Path traversal prevention
- ✅ Execution timeouts for PythonCodeNode
- ✅ Memory limits for code execution
- ✅ Comprehensive security framework
- ✅ Audit logging
- ✅ SecurityMixin for node-level security
- ⏳ Enhanced sandboxing with PyPy sandbox
- ⏳ Integration with secret managers
- ✅ Role-based access control
- ⏳ Workflow signing and verification

Compliance
----------

The Kailash Python SDK is designed to help meet common compliance requirements:

- **GDPR**: Data processing nodes support data anonymization
- **HIPAA**: Supports encryption for data at rest and in transit
- **SOC 2**: Comprehensive audit logging capabilities
- **PCI DSS**: No credit card data processing in core SDK

For specific compliance needs, please contact compliance@terrene.foundation.

Additional Resources
--------------------

- `OWASP Python Security <https://owasp.org/www-project-python-security/>`_
- `Python Security Best Practices <https://python.readthedocs.io/en/latest/library/security_warnings.html>`_
- `CWE Top 25 <https://cwe.mitre.org/top25/>`_

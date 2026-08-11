"""Kailash server implementations.

This module provides server classes for hosting Kailash workflows with
different feature sets:

- WorkflowServer: Basic multi-workflow hosting
- DurableWorkflowServer: Adds request durability and checkpointing
- EnterpriseWorkflowServer: Full enterprise features (recommended default)

Example:
    >>> from kailash.middleware.auth import MiddlewareAuthManager
    >>> from kailash.servers import EnterpriseWorkflowServer
    >>>
    >>> # Enterprise-ready server with all features
    >>> server = EnterpriseWorkflowServer(
    ...     title="My Application",
    ...     auth_manager=MiddlewareAuthManager(secret_key=...),
    ... )
    >>>
    >>> server.register_workflow("data_pipeline", workflow)
    >>> server.run(port=8000)

Note:
    The example above previously passed ``enable_auth=True``. That kwarg was
    never a parameter of any server in this package -- it landed in
    ``**kwargs`` and was discarded, so the documented security control did
    nothing (the shape ``zero-tolerance.md`` Rule 3c names). ``auth_manager=``
    is the real control; :meth:`WorkflowServer.proxy_workflow` consumes it and
    refuses to register an unauthenticated proxy route without it (#2025).
"""

from ..utils.proxy_guard import (
    DEFAULT_ALLOWED_METHODS,
    PROXY_SUPPORTED_METHODS,
    ProxyAuthNotConfiguredError,
)
from .durable_workflow_server import DurableWorkflowServer
from .enterprise_workflow_server import EnterpriseWorkflowServer
from .workflow_server import WorkflowServer

# Recommended default for production
__all__ = [
    "WorkflowServer",
    "DurableWorkflowServer",
    "EnterpriseWorkflowServer",
    "ProxyAuthNotConfiguredError",
    "DEFAULT_ALLOWED_METHODS",
    "PROXY_SUPPORTED_METHODS",
]

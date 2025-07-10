"""Kailash server implementations.

This module provides server classes for hosting Kailash workflows with
different feature sets:

- WorkflowServer: Basic multi-workflow hosting
- DurableWorkflowServer: Adds request durability and checkpointing
- EnterpriseWorkflowServer: Full enterprise features (recommended default)

Example:
    >>> from kailash.servers import EnterpriseWorkflowServer
    >>>
    >>> # Enterprise-ready server with all features
    >>> server = EnterpriseWorkflowServer(
    ...     title="My Application",
    ...     enable_auth=True
    ... )
    >>>
    >>> server.register_workflow("data_pipeline", workflow)
    >>> server.run(port=8000)
"""

from .durable_workflow_server import DurableWorkflowServer
from .enterprise_workflow_server import EnterpriseWorkflowServer
from .workflow_server import WorkflowServer

# Recommended default for production
__all__ = [
    "WorkflowServer",
    "DurableWorkflowServer",
    "EnterpriseWorkflowServer",
]

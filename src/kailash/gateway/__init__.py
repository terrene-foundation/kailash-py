"""Enhanced Gateway Integration for Kailash SDK.

This module provides:
- Resource reference support in JSON API
- Secret management with encryption
- Enhanced client SDK for async workflows
- Production-ready gateway for complex deployments
"""

from .api import WorkflowRequestModel, WorkflowResponseModel, create_gateway_app
from .enhanced_gateway import (
    EnhancedDurableAPIGateway,
    WorkflowNotFoundError,
    WorkflowRequest,
    WorkflowResponse,
)
from .resource_resolver import ResourceReference, ResourceResolver
from .security import SecretBackend, SecretManager, SecretNotFoundError

__all__ = [
    "EnhancedDurableAPIGateway",
    "WorkflowRequest",
    "WorkflowResponse",
    "WorkflowNotFoundError",
    "ResourceReference",
    "ResourceResolver",
    "SecretManager",
    "SecretBackend",
    "SecretNotFoundError",
    "create_gateway_app",
    "WorkflowRequestModel",
    "WorkflowResponseModel",
]

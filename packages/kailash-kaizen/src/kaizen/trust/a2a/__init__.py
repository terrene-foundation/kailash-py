"""
A2A HTTP Service Module.

Implements the A2A (Agent-to-Agent) protocol with EATP trust extensions
for secure inter-agent communication.

Key Components:
- A2AService: FastAPI-based HTTP service
- AgentCardGenerator: Generate Agent Cards with trust extensions
- JsonRpcHandler: JSON-RPC 2.0 compliant request handling
- A2AAuthenticator: JWT-based authentication with trust verification

Example:
    >>> from kaizen.trust.a2a import A2AService, create_a2a_app
    >>>
    >>> # Create service
    >>> service = A2AService(
    ...     trust_operations=trust_ops,
    ...     agent_id="agent-001",
    ...     agent_name="My Agent",
    ...     agent_version="1.0.0",
    ...     private_key=private_key,
    ...     capabilities=["analyze", "report"],
    ... )
    >>> app = service.create_app()
    >>>
    >>> # Or use convenience function
    >>> app = create_a2a_app(
    ...     trust_operations=trust_ops,
    ...     agent_id="agent-001",
    ...     agent_name="My Agent",
    ...     agent_version="1.0.0",
    ...     private_key=private_key,
    ... )
"""

from kaizen.trust.a2a.agent_card import AgentCardCache, AgentCardGenerator
from kaizen.trust.a2a.auth import A2AAuthenticator, extract_token_from_header
from kaizen.trust.a2a.exceptions import (
    A2AError,
    A2AServiceError,
    AgentCardError,
    AuthenticationError,
    AuthorizationError,
    DelegationError,
    InvalidTokenError,
    JsonRpcInternalError,
    JsonRpcInvalidParamsError,
    JsonRpcInvalidRequestError,
    JsonRpcMethodNotFoundError,
    JsonRpcParseError,
    TokenExpiredError,
    TrustVerificationError,
)
from kaizen.trust.a2a.jsonrpc import A2AMethodHandlers, JsonRpcHandler
from kaizen.trust.a2a.models import (
    A2AToken,
    AgentCapability,
    AgentCard,
    AuditQueryRequest,
    AuditQueryResponse,
    DelegationRequest,
    DelegationResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    TrustExtensions,
    VerificationRequest,
    VerificationResponse,
)
from kaizen.trust.a2a.service import A2AService, create_a2a_app

__all__ = [
    # Service
    "A2AService",
    "create_a2a_app",
    # Agent Card
    "AgentCardGenerator",
    "AgentCardCache",
    "AgentCard",
    "AgentCapability",
    "TrustExtensions",
    # JSON-RPC
    "JsonRpcHandler",
    "A2AMethodHandlers",
    "JsonRpcRequest",
    "JsonRpcResponse",
    # Authentication
    "A2AAuthenticator",
    "extract_token_from_header",
    "A2AToken",
    # Request/Response Models
    "VerificationRequest",
    "VerificationResponse",
    "DelegationRequest",
    "DelegationResponse",
    "AuditQueryRequest",
    "AuditQueryResponse",
    # Exceptions
    "A2AError",
    "A2AServiceError",
    "JsonRpcParseError",
    "JsonRpcInvalidRequestError",
    "JsonRpcMethodNotFoundError",
    "JsonRpcInvalidParamsError",
    "JsonRpcInternalError",
    "TrustVerificationError",
    "AuthenticationError",
    "AuthorizationError",
    "DelegationError",
    "AgentCardError",
    "TokenExpiredError",
    "InvalidTokenError",
]

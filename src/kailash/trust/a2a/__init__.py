# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

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
    >>> from kailash.trust.a2a import A2AService, create_a2a_app
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

from typing import TYPE_CHECKING

from kailash.trust.a2a.agent_card import AgentCardCache, AgentCardGenerator
from kailash.trust.a2a.auth import (
    A2AAuthenticator,
    CallerIdentity,
    TokenVerifier,
    extract_token_from_header,
)
from kailash.trust.a2a.authorization import A2AAuthorizer
from kailash.trust.a2a.exceptions import (
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
from kailash.trust.a2a.jsonrpc import A2AMethodHandlers, JsonRpcHandler
from kailash.trust.a2a.models import (
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

if TYPE_CHECKING:  # pragma: no cover - import-time only for type checkers
    # Declared here so `__all__`, Sphinx autodoc, pyright and CodeQL all resolve
    # these names, while the runtime import stays lazy below
    # (orphan-detection.md Rule 6b).
    from kailash.trust.a2a.service import A2AService, create_a2a_app

#: Symbols served lazily because importing them requires `nexus`, which is NOT
#: in the `[trust]` extra that gates this package.
_LAZY_SERVICE_EXPORTS = frozenset({"A2AService", "create_a2a_app"})


def __getattr__(name: str):
    """Import the Nexus-backed HTTP service on first access, not at import time.

    `service.py` imports `nexus` at module scope, but `nexus` ships in the
    `[nexus]` extra while this package is gated by `[trust]`. Importing it
    eagerly meant `pip install kailash[trust]` followed by
    `import kailash.trust.a2a` raised `ModuleNotFoundError: No module named
    'nexus'` — for EVERY symbol in the package, including the ones with no HTTP
    dependency at all (`A2AAuthenticator`, `JsonRpcHandler`, `CallerIdentity`).

    That is the `dependencies.md` module-scope-import rule: an unconditional
    import of a sibling this package does not declare. It went unnoticed
    because a monorepo dev environment has `nexus` editable-installed, so it
    only ever failed on a clean install.

    Raising here — at the point of use — turns it into an actionable error
    naming the missing extra, instead of making the whole package unimportable.
    """
    if name in _LAZY_SERVICE_EXPORTS:
        try:
            from kailash.trust.a2a import service as _service
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"kailash.trust.a2a.{name} requires the HTTP service layer, "
                f"which needs the 'nexus' package: pip install 'kailash[nexus]'. "
                f"The rest of kailash.trust.a2a (authentication, authorization, "
                f"JSON-RPC) works without it. Original error: {exc}"
            ) from exc
        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "CallerIdentity",
    "TokenVerifier",
    "A2AAuthorizer",
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

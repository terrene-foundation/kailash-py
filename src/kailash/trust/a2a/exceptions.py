# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A HTTP Service Exceptions.

Custom exceptions for A2A protocol operations including JSON-RPC errors
and authentication failures.
"""

from typing import Any, Dict, Optional


class A2AError(Exception):
    """Base exception for A2A operations."""

    def __init__(
        self, message: str, code: int = -32000, data: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.data = data or {}
        super().__init__(message)


class A2AServiceError(A2AError):
    """Error in A2A service operations."""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=-32000, data=data)


# JSON-RPC 2.0 Standard Error Codes (-32700 to -32600)
class JsonRpcParseError(A2AError):
    """Invalid JSON was received."""

    def __init__(
        self, message: str = "Parse error", data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code=-32700, data=data)


class JsonRpcInvalidRequestError(A2AError):
    """The JSON sent is not a valid Request object."""

    def __init__(
        self, message: str = "Invalid Request", data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code=-32600, data=data)


class JsonRpcMethodNotFoundError(A2AError):
    """The method does not exist / is not available."""

    def __init__(self, method: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(f"Method not found: {method}", code=-32601, data=data)


class JsonRpcInvalidParamsError(A2AError):
    """Invalid method parameter(s)."""

    def __init__(
        self, message: str = "Invalid params", data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code=-32602, data=data)


class JsonRpcInternalError(A2AError):
    """Internal JSON-RPC error."""

    def __init__(
        self, message: str = "Internal error", data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code=-32603, data=data)


# EATP-Specific Error Codes (-40001 to -40099)
class TrustVerificationError(A2AError):
    """Trust verification failed for agent."""

    def __init__(
        self, agent_id: str, reason: str, data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Trust verification failed for {agent_id}: {reason}",
            code=-40001,
            data={"agent_id": agent_id, "reason": reason, **(data or {})},
        )


class AuthenticationError(A2AError):
    """Authentication failed."""

    def __init__(
        self,
        message: str = "Authentication failed",
        data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=-40002, data=data)


class AuthorizationError(A2AError):
    """Authorization failed - insufficient capabilities."""

    def __init__(self, required_capability: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(
            f"Authorization failed: missing capability '{required_capability}'",
            code=-40003,
            data={"required_capability": required_capability, **(data or {})},
        )


class DelegationError(A2AError):
    """Delegation operation failed."""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=-40004, data=data)


class AgentCardError(A2AError):
    """Error generating or serving Agent Card."""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=-40005, data=data)


class TokenExpiredError(AuthenticationError):
    """JWT token has expired."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        super().__init__("Token expired", data)


class InvalidTokenError(AuthenticationError):
    """JWT token is invalid."""

    def __init__(
        self, reason: str = "Invalid token", data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(reason, data)

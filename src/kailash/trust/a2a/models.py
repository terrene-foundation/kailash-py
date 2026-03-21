# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A Protocol Models.

Data models for A2A HTTP service including Agent Card, JSON-RPC
messages, and authentication tokens.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class A2AVersion(str, Enum):
    """Supported A2A protocol versions."""

    V1_0 = "1.0"


@dataclass
class AgentCapability:
    """
    Agent capability as exposed in Agent Card.

    Represents a specific capability the agent can perform,
    optionally with constraints.
    """

    name: str
    description: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"name": self.name}
        if self.description:
            result["description"] = self.description
        if self.constraints:
            result["constraints"] = self.constraints
        return result


@dataclass
class TrustExtensions:
    """
    EATP trust extensions for Agent Card.

    Provides trust chain information for verifiable agent identity.
    """

    trust_chain_hash: str
    genesis_authority_id: str
    genesis_authority_type: str
    verification_endpoint: Optional[str] = None
    delegation_endpoint: Optional[str] = None
    capabilities_attested: Optional[List[str]] = None
    constraints: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "trust_chain_hash": self.trust_chain_hash,
            "genesis_authority_id": self.genesis_authority_id,
            "genesis_authority_type": self.genesis_authority_type,
        }
        if self.verification_endpoint:
            result["verification_endpoint"] = self.verification_endpoint
        if self.delegation_endpoint:
            result["delegation_endpoint"] = self.delegation_endpoint
        if self.capabilities_attested:
            result["capabilities_attested"] = self.capabilities_attested
        if self.constraints:
            result["constraints"] = self.constraints
        return result


@dataclass
class AgentCard:
    """
    A2A Agent Card with EATP trust extensions.

    The Agent Card is the public identity of an agent, served at
    /.well-known/agent.json according to the A2A specification.
    """

    # Required A2A fields
    agent_id: str
    name: str
    version: str

    # Optional A2A fields
    description: Optional[str] = None
    capabilities: List[AgentCapability] = field(default_factory=list)
    protocols: List[str] = field(default_factory=lambda: ["a2a/1.0"])
    endpoint: Optional[str] = None
    public_key: Optional[str] = None

    # EATP trust extensions
    trust: Optional[TrustExtensions] = None

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for HTTP response."""
        result = {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "protocols": self.protocols,
            # Always include capabilities (empty list if none)
            "capabilities": [c.to_dict() for c in self.capabilities],
        }

        if self.description:
            result["description"] = self.description
        if self.endpoint:
            result["endpoint"] = self.endpoint
        if self.public_key:
            result["public_key"] = self.public_key
        if self.trust:
            result["trust"] = self.trust.to_dict()
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            result["updated_at"] = self.updated_at.isoformat()

        return result

    def compute_etag(self) -> str:
        """Compute ETag for caching based on content hash."""
        import hashlib
        import json

        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class JsonRpcRequest:
    """
    JSON-RPC 2.0 Request object.

    All A2A method calls use JSON-RPC 2.0 format.
    """

    method: str
    id: Optional[Union[str, int]] = None
    params: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JsonRpcRequest":
        """Parse JSON-RPC request from dict."""
        return cls(
            method=data.get("method", ""),
            id=data.get("id"),
            params=data.get("params"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.params is not None:
            result["params"] = self.params
        return result


@dataclass
class JsonRpcResponse:
    """
    JSON-RPC 2.0 Response object.

    Successful responses contain 'result', error responses contain 'error'.
    """

    id: Optional[Union[str, int]]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    @classmethod
    def success(cls, id: Optional[Union[str, int]], result: Any) -> "JsonRpcResponse":
        """Create successful response."""
        return cls(id=id, result=result)

    @classmethod
    def create_error(
        cls,
        id: Optional[Union[str, int]],
        code: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> "JsonRpcResponse":
        """Create error response."""
        error_obj: Dict[str, Any] = {"code": code, "message": message}
        if data:
            error_obj["data"] = data
        return cls(id=id, error=error_obj)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            result["error"] = self.error
        else:
            result["result"] = self.result
        return result


@dataclass
class A2AToken:
    """
    JWT token claims for A2A authentication.

    Tokens are signed with the agent's trust key and include
    trust chain information for verification.
    """

    # Standard JWT claims
    sub: str  # agent_id
    iss: str  # issuing agent_id
    aud: str  # target agent_id
    exp: datetime
    iat: datetime
    jti: str  # unique token ID

    # EATP claims
    authority_id: str
    trust_chain_hash: str
    capabilities: List[str] = field(default_factory=list)
    constraints: Optional[Dict[str, Any]] = None

    def to_claims(self) -> Dict[str, Any]:
        """Convert to JWT claims dict."""
        claims = {
            "sub": self.sub,
            "iss": self.iss,
            "aud": self.aud,
            "exp": int(self.exp.timestamp()),
            "iat": int(self.iat.timestamp()),
            "jti": self.jti,
            "authority_id": self.authority_id,
            "trust_chain_hash": self.trust_chain_hash,
            "capabilities": self.capabilities,
        }
        if self.constraints:
            claims["constraints"] = self.constraints
        return claims

    @classmethod
    def from_claims(cls, claims: Dict[str, Any]) -> "A2AToken":
        """Parse token from JWT claims."""
        return cls(
            sub=claims["sub"],
            iss=claims["iss"],
            aud=claims["aud"],
            exp=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(claims["iat"], tz=timezone.utc),
            jti=claims["jti"],
            authority_id=claims["authority_id"],
            trust_chain_hash=claims["trust_chain_hash"],
            capabilities=claims.get("capabilities", []),
            constraints=claims.get("constraints"),
        )


@dataclass
class VerificationRequest:
    """Request to verify an agent's trust chain."""

    agent_id: str
    verification_level: str = "STANDARD"  # QUICK, STANDARD, FULL


@dataclass
class VerificationResponse:
    """Response from trust verification."""

    valid: bool
    agent_id: str
    verification_level: str
    errors: List[str] = field(default_factory=list)
    trust_chain_summary: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "valid": self.valid,
            "agent_id": self.agent_id,
            "verification_level": self.verification_level,
            "errors": self.errors,
        }
        if self.trust_chain_summary:
            result["trust_chain_summary"] = self.trust_chain_summary
        if self.latency_ms is not None:
            result["latency_ms"] = self.latency_ms
        return result


@dataclass
class DelegationRequest:
    """Request to delegate capabilities to another agent."""

    delegatee_agent_id: str
    task_id: str
    capabilities: List[str]
    constraints: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


@dataclass
class DelegationResponse:
    """Response from delegation operation."""

    delegation_id: str
    delegator_agent_id: str
    delegatee_agent_id: str
    task_id: str
    capabilities_delegated: List[str]
    constraints: Dict[str, Any]
    delegated_at: datetime
    expires_at: Optional[datetime]
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "delegation_id": self.delegation_id,
            "delegator_agent_id": self.delegator_agent_id,
            "delegatee_agent_id": self.delegatee_agent_id,
            "task_id": self.task_id,
            "capabilities_delegated": self.capabilities_delegated,
            "constraints": self.constraints,
            "delegated_at": self.delegated_at.isoformat(),
            "signature": self.signature,
        }
        if self.expires_at:
            result["expires_at"] = self.expires_at.isoformat()
        return result


@dataclass
class AuditQueryRequest:
    """Request to query audit trail."""

    agent_id: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    action_type: Optional[str] = None
    resource_uri: Optional[str] = None
    limit: int = 100
    offset: int = 0


@dataclass
class AuditQueryResponse:
    """Response from audit query."""

    agent_id: str
    total_count: int
    actions: List[Dict[str, Any]]
    delegation_chain: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "agent_id": self.agent_id,
            "total_count": self.total_count,
            "actions": self.actions,
        }
        if self.delegation_chain:
            result["delegation_chain"] = self.delegation_chain
        return result

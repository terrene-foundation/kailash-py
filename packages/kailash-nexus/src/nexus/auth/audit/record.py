"""Audit record dataclass (TODO-310F).

Defines AuditRecord for structured audit logging of API requests.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


@dataclass
class AuditRecord:
    """Structured audit record for API requests.

    Captures comprehensive information about each API request for
    compliance, debugging, and security analysis.
    """

    timestamp: datetime
    request_id: str
    method: str
    path: str
    status_code: int
    user_id: Optional[str]
    tenant_id: Optional[str]
    ip_address: str
    user_agent: str
    duration_ms: float
    request_body_size: int
    response_body_size: int
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        ip_address: str,
        user_agent: str = "",
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        request_body_size: int = 0,
        response_body_size: int = 0,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "AuditRecord":
        """Factory method to create an audit record with auto-generated fields."""
        return cls(
            timestamp=datetime.now(timezone.utc),
            request_id=str(uuid4()),
            method=method,
            path=path,
            status_code=status_code,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=duration_ms,
            request_body_size=request_body_size,
            response_body_size=response_body_size,
            error=error,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary with ISO timestamp."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "duration_ms": self.duration_ms,
            "request_body_size": self.request_body_size,
            "response_body_size": self.response_body_size,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditRecord":
        """Deserialize from dictionary."""
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            if timestamp.endswith("Z"):
                timestamp = timestamp[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            timestamp=timestamp,
            request_id=data["request_id"],
            method=data["method"],
            path=data["path"],
            status_code=data["status_code"],
            user_id=data.get("user_id"),
            tenant_id=data.get("tenant_id"),
            ip_address=data["ip_address"],
            user_agent=data.get("user_agent", ""),
            duration_ms=data["duration_ms"],
            request_body_size=data.get("request_body_size", 0),
            response_body_size=data.get("response_body_size", 0),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

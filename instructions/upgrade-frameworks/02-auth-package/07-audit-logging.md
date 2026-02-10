# Audit Logging Specification

## Overview

This specification defines a comprehensive audit logging system for Nexus that records every API request with structured metadata for compliance and debugging. It supports multiple storage backends (structured logging, DataFlow, custom) with PII filtering and configurable exclusions.

## Evidence from Real Projects

| Project                | File             | Lines | Key Features                                         |
| ---------------------- | ---------------- | ----- | ---------------------------------------------------- |
| kaizen.trust           | `audit_store.py` | 1087  | Append-only, cryptographic signatures, chain linking |
| dataflow.trust         | `audit.py`       | 676   | Signed records, Ed25519 signatures, hash chains      |
| kailash.runtime.trust  | `audit.py`       | 640   | Runtime audit generation, EATP compliance            |
| kailash.nodes.security | `audit_log.py`   | 104   | Structured logging node                              |

## Architecture

### Component Hierarchy

```
nexus.auth.audit
    AuditConfig               # Configuration dataclass
    AuditRecord               # Audit record dataclass
    AuditBackend (ABC)        # Abstract backend interface
        LoggingBackend        # JSON structured logging
        DataFlowBackend       # Database storage via DataFlow
        CustomBackend         # User-provided callable
    AuditMiddleware           # FastAPI middleware
    PIIFilter                 # PII redaction utility
```

### File Structure

```
apps/kailash-nexus/src/nexus/auth/
    __init__.py                 # Re-export AuditConfig
    audit/
        __init__.py             # Re-export all components
        config.py               # AuditConfig dataclass
        record.py               # AuditRecord dataclass
        backends/
            __init__.py
            base.py             # AuditBackend ABC
            logging.py          # LoggingBackend (structured JSON)
            dataflow.py         # DataFlowBackend
            custom.py           # CustomBackend wrapper
        middleware.py           # AuditMiddleware
        pii_filter.py           # PIIFilter utility
```

## Audit Record Schema

### AuditRecord

**Location:** `nexus/auth/audit/record.py`

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

@dataclass
class AuditRecord:
    """Structured audit record for API requests.

    Captures comprehensive information about each API request for
    compliance, debugging, and security analysis.

    Attributes:
        timestamp: When the request was received (UTC)
        request_id: Unique identifier for this request (UUID)
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: Request path (e.g., "/api/users/123")
        status_code: HTTP response status code
        user_id: Authenticated user ID (if available)
        tenant_id: Tenant ID from context (if available)
        ip_address: Client IP address
        user_agent: Client User-Agent header
        duration_ms: Request duration in milliseconds
        request_body_size: Request body size in bytes
        response_body_size: Response body size in bytes
        error: Error message if status_code >= 400
        metadata: Additional context (headers, query params, etc.)

    Example:
        >>> record = AuditRecord(
        ...     timestamp=datetime.now(timezone.utc),
        ...     request_id="550e8400-e29b-41d4-a716-446655440000",
        ...     method="POST",
        ...     path="/api/users",
        ...     status_code=201,
        ...     user_id="user-123",
        ...     tenant_id="tenant-456",
        ...     ip_address="192.168.1.100",
        ...     user_agent="Mozilla/5.0...",
        ...     duration_ms=45.2,
        ...     request_body_size=256,
        ...     response_body_size=512,
        ...     error=None,
        ...     metadata={"action": "create_user"},
        ... )
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
        """Factory method to create an audit record.

        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            duration_ms: Request duration
            ip_address: Client IP
            user_agent: Client User-Agent
            user_id: Authenticated user ID (optional)
            tenant_id: Tenant ID (optional)
            request_body_size: Request size in bytes
            response_body_size: Response size in bytes
            error: Error message (optional)
            metadata: Additional context (optional)

        Returns:
            New AuditRecord instance
        """
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
        """Serialize to dictionary.

        Returns:
            Dictionary representation with ISO timestamp
        """
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
        """Serialize to JSON string.

        Returns:
            JSON string representation
        """
        import json
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditRecord":
        """Deserialize from dictionary.

        Args:
            data: Dictionary with record fields

        Returns:
            AuditRecord instance
        """
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
```

## Configuration

### AuditConfig

**Location:** `nexus/auth/audit/config.py`

```python
from dataclasses import dataclass, field
from typing import Callable, List, Literal, Optional

@dataclass
class AuditConfig:
    """Configuration for audit logging.

    Attributes:
        enabled: Whether audit logging is enabled (default: True)
        backend: Storage backend - "logging", "dataflow", or custom callable
        log_request_body: Whether to log request bodies (default: False)
        log_response_body: Whether to log response bodies (default: False)
        exclude_paths: Paths to exclude from audit logging
        exclude_methods: HTTP methods to exclude (default: ["OPTIONS"])
        redact_headers: Header names to redact (default: auth-related)
        redact_fields: Field names to redact in bodies (default: sensitive fields)
        max_body_log_size: Maximum body size to log in bytes (default: 10KB)
        include_query_params: Whether to include query params in metadata
        include_request_headers: Whether to include request headers in metadata

    Example:
        >>> config = AuditConfig(
        ...     enabled=True,
        ...     backend="logging",
        ...     log_request_body=False,
        ...     log_response_body=False,
        ...     exclude_paths=["/health", "/metrics"],
        ...     exclude_methods=["OPTIONS"],
        ...     redact_headers=["Authorization", "Cookie", "X-API-Key"],
        ...     redact_fields=["password", "secret", "token", "credit_card"],
        ... )
    """

    enabled: bool = True

    # Backend configuration
    backend: Literal["logging", "dataflow"] | Callable = "logging"
    dataflow_model_name: str = "AuditRecord"  # For dataflow backend
    log_level: str = "INFO"  # For logging backend

    # What to log
    log_request_body: bool = False  # Privacy - don't log bodies by default
    log_response_body: bool = False
    max_body_log_size: int = 10 * 1024  # 10KB max
    include_query_params: bool = True
    include_request_headers: bool = False

    # Exclusions
    exclude_paths: List[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs", "/openapi.json"]
    )
    exclude_methods: List[str] = field(default_factory=lambda: ["OPTIONS"])

    # PII filtering
    redact_headers: List[str] = field(
        default_factory=lambda: [
            "Authorization",
            "Cookie",
            "Set-Cookie",
            "X-API-Key",
            "X-Auth-Token",
            "X-Session-ID",
        ]
    )
    redact_fields: List[str] = field(
        default_factory=lambda: [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credit_card",
            "card_number",
            "cvv",
            "ssn",
            "social_security",
            "access_token",
            "refresh_token",
        ]
    )
    redact_replacement: str = "[REDACTED]"

    def __post_init__(self):
        """Validate configuration."""
        if self.max_body_log_size < 0:
            raise ValueError("max_body_log_size cannot be negative")
```

## PII Filtering

### PIIFilter

**Location:** `nexus/auth/audit/pii_filter.py`

```python
import re
from typing import Any, Dict, List, Set

class PIIFilter:
    """Filters PII from audit data.

    Provides methods to redact sensitive information from headers,
    bodies, and other data structures before logging.

    Example:
        >>> filter = PIIFilter(
        ...     redact_fields=["password", "token"],
        ...     redact_headers=["Authorization"],
        ... )
        >>> clean_headers = filter.redact_headers({"Authorization": "Bearer xyz"})
        >>> # {"Authorization": "[REDACTED]"}
    """

    def __init__(
        self,
        redact_fields: List[str],
        redact_headers: List[str],
        replacement: str = "[REDACTED]",
    ):
        """Initialize PII filter.

        Args:
            redact_fields: Field names to redact (case-insensitive)
            redact_headers: Header names to redact (case-insensitive)
            replacement: Replacement string for redacted values
        """
        self._redact_fields: Set[str] = {f.lower() for f in redact_fields}
        self._redact_headers: Set[str] = {h.lower() for h in redact_headers}
        self._replacement = replacement

        # Common PII patterns
        self._patterns = [
            (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "EMAIL"),
            (re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"), "SSN"),
            (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "CARD"),
        ]

    def redact_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Redact sensitive headers.

        Args:
            headers: Dictionary of header name -> value

        Returns:
            Headers with sensitive values redacted
        """
        result = {}
        for name, value in headers.items():
            if name.lower() in self._redact_headers:
                result[name] = self._replacement
            else:
                result[name] = value
        return result

    def redact_body(self, body: Any) -> Any:
        """Recursively redact sensitive fields from body.

        Args:
            body: Request/response body (dict, list, or primitive)

        Returns:
            Body with sensitive fields redacted
        """
        if isinstance(body, dict):
            return {
                k: self._replacement if k.lower() in self._redact_fields else self.redact_body(v)
                for k, v in body.items()
            }
        elif isinstance(body, list):
            return [self.redact_body(item) for item in body]
        elif isinstance(body, str):
            return self._redact_patterns(body)
        else:
            return body

    def _redact_patterns(self, text: str) -> str:
        """Redact common PII patterns from text.

        Args:
            text: Text to scan for PII patterns

        Returns:
            Text with patterns redacted
        """
        result = text
        for pattern, label in self._patterns:
            result = pattern.sub(f"[{label}_REDACTED]", result)
        return result

    def redact_query_params(self, params: Dict[str, str]) -> Dict[str, str]:
        """Redact sensitive query parameters.

        Args:
            params: Dictionary of parameter name -> value

        Returns:
            Parameters with sensitive values redacted
        """
        result = {}
        for name, value in params.items():
            if name.lower() in self._redact_fields:
                result[name] = self._replacement
            else:
                result[name] = value
        return result
```

## Backend Interface

### AuditBackend (ABC)

**Location:** `nexus/auth/audit/backends/base.py`

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from ..record import AuditRecord

class AuditBackend(ABC):
    """Abstract interface for audit storage backends.

    All backends must implement store() for writing records.
    Query methods are optional (raise NotImplementedError if not supported).
    """

    @abstractmethod
    async def store(self, record: AuditRecord) -> None:
        """Store an audit record.

        Args:
            record: AuditRecord to store

        Raises:
            AuditStorageError: If storage fails
        """
        pass

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        path_pattern: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """Query audit records (optional).

        Args:
            start_time: Filter by start time
            end_time: Filter by end time
            user_id: Filter by user ID
            tenant_id: Filter by tenant ID
            path_pattern: Filter by path pattern (glob)
            status_code: Filter by status code
            limit: Maximum records to return
            offset: Pagination offset

        Returns:
            List of matching AuditRecords

        Raises:
            NotImplementedError: If query not supported
        """
        raise NotImplementedError("Query not supported by this backend")

    async def close(self) -> None:
        """Clean up resources."""
        pass
```

### LoggingBackend

**Location:** `nexus/auth/audit/backends/logging.py`

```python
import json
import logging
from typing import Optional

from ..record import AuditRecord
from .base import AuditBackend

class LoggingBackend(AuditBackend):
    """Structured JSON logging backend.

    Writes audit records as JSON to Python's logging system.
    Default backend - requires no additional infrastructure.

    Example:
        >>> backend = LoggingBackend(
        ...     logger_name="nexus.audit",
        ...     log_level="INFO",
        ... )
        >>> await backend.store(record)
        # Logs: {"timestamp": "...", "method": "POST", ...}
    """

    def __init__(
        self,
        logger_name: str = "nexus.audit",
        log_level: str = "INFO",
    ):
        """Initialize logging backend.

        Args:
            logger_name: Logger name (default: "nexus.audit")
            log_level: Log level (default: "INFO")
        """
        self._logger = logging.getLogger(logger_name)
        self._level = getattr(logging, log_level.upper(), logging.INFO)

    async def store(self, record: AuditRecord) -> None:
        """Store record by logging as JSON.

        Args:
            record: AuditRecord to log
        """
        # Format as single-line JSON for log aggregation
        log_data = record.to_dict()

        # Log at appropriate level based on status code
        if record.status_code >= 500:
            self._logger.error(json.dumps(log_data))
        elif record.status_code >= 400:
            self._logger.warning(json.dumps(log_data))
        else:
            self._logger.log(self._level, json.dumps(log_data))
```

### DataFlowBackend

**Location:** `nexus/auth/audit/backends/dataflow.py`

```python
import logging
from datetime import datetime
from typing import Any, List, Optional

from ..record import AuditRecord
from .base import AuditBackend

logger = logging.getLogger(__name__)

class DataFlowBackend(AuditBackend):
    """DataFlow database backend for audit records.

    Stores audit records in a database table via DataFlow.
    Supports querying for compliance and debugging.

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("postgresql://...")
        >>> backend = DataFlowBackend(dataflow=db, model_name="AuditRecord")
        >>> await backend.initialize()
        >>> await backend.store(record)
    """

    def __init__(
        self,
        dataflow: Any,  # DataFlow instance
        model_name: str = "AuditRecord",
    ):
        """Initialize DataFlow backend.

        Args:
            dataflow: DataFlow instance
            model_name: Name of the audit model (default: "AuditRecord")
        """
        self._db = dataflow
        self._model_name = model_name
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the audit model in DataFlow.

        Creates the AuditRecord model if it doesn't exist.
        """
        if self._initialized:
            return

        # Define model dynamically if not already defined
        # This allows the backend to work without pre-defined models

        try:
            # Check if model already exists
            self._db.get_model(self._model_name)
        except Exception:
            # Model doesn't exist - define it
            # Note: In practice, the model should be pre-defined
            logger.warning(
                f"Audit model '{self._model_name}' not found. "
                "Please define the model in your DataFlow instance."
            )

        self._initialized = True

    async def store(self, record: AuditRecord) -> None:
        """Store audit record in database.

        Args:
            record: AuditRecord to store
        """
        if not self._initialized:
            await self.initialize()

        try:
            await self._db.create(
                self._model_name,
                record.to_dict(),
            )
        except Exception as e:
            # Never let audit storage failures break the application
            logger.error(f"Failed to store audit record: {e}")

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        path_pattern: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """Query audit records from database.

        Args:
            start_time: Filter by start time
            end_time: Filter by end time
            user_id: Filter by user ID
            tenant_id: Filter by tenant ID
            path_pattern: Filter by path pattern
            status_code: Filter by status code
            limit: Maximum records
            offset: Pagination offset

        Returns:
            List of matching AuditRecords
        """
        if not self._initialized:
            await self.initialize()

        # Build filter
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status_code:
            filters["status_code"] = status_code

        # Note: Time range and path pattern filtering may need
        # DataFlow-specific operators

        try:
            records = await self._db.list(
                self._model_name,
                filter=filters,
                limit=limit,
                offset=offset,
                order_by=["-timestamp"],
            )

            # Apply post-filters for fields DataFlow doesn't support directly
            result = []
            for record_data in records:
                record = AuditRecord.from_dict(record_data)

                # Time range filter
                if start_time and record.timestamp < start_time:
                    continue
                if end_time and record.timestamp > end_time:
                    continue

                # Path pattern filter (simple glob)
                if path_pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(record.path, path_pattern):
                        continue

                result.append(record)

            return result

        except Exception as e:
            logger.error(f"Failed to query audit records: {e}")
            return []

    async def close(self) -> None:
        """Close database connection."""
        pass  # DataFlow manages its own connections
```

### CustomBackend

**Location:** `nexus/auth/audit/backends/custom.py`

```python
from typing import Awaitable, Callable, Union

from ..record import AuditRecord
from .base import AuditBackend

# Type for custom store function
StoreCallable = Union[
    Callable[[AuditRecord], None],
    Callable[[AuditRecord], Awaitable[None]],
]

class CustomBackend(AuditBackend):
    """Custom backend wrapper for user-provided callable.

    Wraps a user-provided function as an audit backend.

    Example:
        >>> async def my_store(record: AuditRecord):
        ...     # Send to external service
        ...     await send_to_splunk(record.to_dict())
        >>>
        >>> backend = CustomBackend(store_func=my_store)
        >>> await backend.store(record)
    """

    def __init__(self, store_func: StoreCallable):
        """Initialize custom backend.

        Args:
            store_func: Callable that accepts AuditRecord
        """
        self._store_func = store_func

    async def store(self, record: AuditRecord) -> None:
        """Store record using custom function.

        Args:
            record: AuditRecord to store
        """
        import asyncio
        import inspect

        if asyncio.iscoroutinefunction(self._store_func):
            await self._store_func(record)
        else:
            self._store_func(record)
```

## Middleware

**Location:** `nexus/auth/audit/middleware.py`

```python
import fnmatch
import logging
import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .backends.base import AuditBackend
from .backends.logging import LoggingBackend
from .backends.dataflow import DataFlowBackend
from .backends.custom import CustomBackend
from .config import AuditConfig
from .pii_filter import PIIFilter
from .record import AuditRecord

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for audit logging.

    Records every API request with structured metadata for
    compliance and debugging.

    Middleware behavior:
    1. Check if path/method is excluded
    2. Record request start time
    3. Extract request metadata (IP, user agent, body size)
    4. Process request
    5. Record response metadata (status, body size, duration)
    6. Apply PII filtering
    7. Store audit record via backend

    Example:
        >>> from fastapi import FastAPI
        >>> from nexus.auth import AuditConfig
        >>> from nexus.auth.audit import AuditMiddleware
        >>>
        >>> app = FastAPI()
        >>> config = AuditConfig(
        ...     backend="logging",
        ...     exclude_paths=["/health"],
        ... )
        >>> app.add_middleware(AuditMiddleware, config=config)
    """

    def __init__(
        self,
        app,
        config: AuditConfig,
        dataflow: Optional[Any] = None,
    ):
        """Initialize audit middleware.

        Args:
            app: FastAPI/Starlette application
            config: Audit configuration
            dataflow: DataFlow instance (required if backend="dataflow")
        """
        super().__init__(app)
        self.config = config
        self._backend: Optional[AuditBackend] = None
        self._pii_filter = PIIFilter(
            redact_fields=config.redact_fields,
            redact_headers=config.redact_headers,
            replacement=config.redact_replacement,
        )
        self._dataflow = dataflow
        self._initialized = False

    async def _ensure_backend(self) -> None:
        """Lazily initialize backend on first request."""
        if self._initialized:
            return

        if callable(self.config.backend) and not isinstance(self.config.backend, str):
            # Custom callable backend
            self._backend = CustomBackend(store_func=self.config.backend)

        elif self.config.backend == "dataflow":
            if not self._dataflow:
                raise ValueError(
                    "DataFlow instance required when backend='dataflow'"
                )
            self._backend = DataFlowBackend(
                dataflow=self._dataflow,
                model_name=self.config.dataflow_model_name,
            )
            await self._backend.initialize()

        else:  # "logging" or default
            self._backend = LoggingBackend(
                logger_name="nexus.audit",
                log_level=self.config.log_level,
            )

        self._initialized = True

    def _is_excluded(self, request: Request) -> bool:
        """Check if request should be excluded from audit.

        Args:
            request: FastAPI request

        Returns:
            True if excluded
        """
        # Check method
        if request.method in self.config.exclude_methods:
            return True

        # Check path
        path = request.url.path
        for pattern in self.config.exclude_paths:
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address.

        Handles proxies via X-Forwarded-For header.

        Args:
            request: FastAPI request

        Returns:
            Client IP address
        """
        # Check for proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # First IP in the chain is the client
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Direct connection
        if request.client:
            return request.client.host

        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with audit logging."""
        if not self.config.enabled:
            return await call_next(request)

        # Check exclusions
        if self._is_excluded(request):
            return await call_next(request)

        await self._ensure_backend()

        # Start timing
        start_time = time.time()

        # Extract request metadata
        request_body_size = 0
        if request.headers.get("content-length"):
            request_body_size = int(request.headers.get("content-length", 0))

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Extract response metadata
        response_body_size = 0
        if response.headers.get("content-length"):
            response_body_size = int(response.headers.get("content-length", 0))

        # Extract user/tenant from request state
        user_id = getattr(request.state, "user_id", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Build metadata
        metadata = {}

        if self.config.include_query_params:
            query_params = dict(request.query_params)
            if query_params:
                metadata["query_params"] = self._pii_filter.redact_query_params(
                    query_params
                )

        if self.config.include_request_headers:
            headers = dict(request.headers)
            metadata["request_headers"] = self._pii_filter.redact_headers(headers)

        # Extract error message for 4xx/5xx responses
        error = None
        if response.status_code >= 400:
            # Try to get error from response body
            # Note: This is tricky with streaming responses
            error = f"HTTP {response.status_code}"

        # Create audit record
        record = AuditRecord.create(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            ip_address=self._get_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
            user_id=user_id,
            tenant_id=tenant_id,
            request_body_size=request_body_size,
            response_body_size=response_body_size,
            error=error,
            metadata=metadata,
        )

        # Store asynchronously (don't block response)
        try:
            await self._backend.store(record)
        except Exception as e:
            # Never let audit failures break the application
            logger.error(f"Failed to store audit record: {e}")

        return response
```

## Integration with Nexus

### Nexus Configuration

```python
from nexus import Nexus
from nexus.auth import AuditConfig

app = Nexus(
    audit=AuditConfig(
        enabled=True,
        backend="logging",
        log_request_body=False,
        log_response_body=False,
        exclude_paths=["/health", "/metrics"],
        exclude_methods=["OPTIONS"],
        redact_headers=["Authorization", "Cookie", "X-API-Key"],
        redact_fields=["password", "secret", "token", "credit_card"],
    ),
)
```

### DataFlow Backend Configuration

```python
from dataflow import DataFlow
from nexus import Nexus
from nexus.auth import AuditConfig

# Define audit model
db = DataFlow("postgresql://...")

@db.model
class AuditRecord:
    id: str
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
    error: Optional[str]
    metadata: dict  # JSONB in PostgreSQL

app = Nexus(
    audit=AuditConfig(
        backend="dataflow",
        dataflow_model_name="AuditRecord",
    ),
    dataflow=db,
)
```

### Custom Backend Configuration

```python
from nexus import Nexus
from nexus.auth import AuditConfig
from nexus.auth.audit import AuditRecord

async def send_to_splunk(record: AuditRecord):
    """Custom audit storage to Splunk."""
    async with aiohttp.ClientSession() as session:
        await session.post(
            "https://splunk.example.com/services/collector",
            json={"event": record.to_dict()},
            headers={"Authorization": f"Splunk {SPLUNK_TOKEN}"},
        )

app = Nexus(
    audit=AuditConfig(
        backend=send_to_splunk,  # Custom callable
    ),
)
```

## Testing Requirements

### Tier 1: Unit Tests (Mocking Allowed)

**Location:** `tests/unit/auth/audit/`

```python
# test_config.py
def test_config_defaults():
    """Test default configuration values."""
    config = AuditConfig()
    assert config.enabled is True
    assert config.backend == "logging"
    assert config.log_request_body is False
    assert config.log_response_body is False
    assert "password" in config.redact_fields
    assert "Authorization" in config.redact_headers

# test_record.py
def test_record_create():
    """Test AuditRecord factory method."""
    record = AuditRecord.create(
        method="POST",
        path="/api/users",
        status_code=201,
        duration_ms=45.2,
        ip_address="192.168.1.1",
    )

    assert record.method == "POST"
    assert record.path == "/api/users"
    assert record.status_code == 201
    assert record.request_id  # UUID generated
    assert record.timestamp  # Timestamp set

def test_record_to_dict():
    """Test serialization to dictionary."""
    record = AuditRecord.create(
        method="GET",
        path="/api/data",
        status_code=200,
        duration_ms=10.5,
        ip_address="10.0.0.1",
    )

    data = record.to_dict()
    assert data["method"] == "GET"
    assert "timestamp" in data  # ISO format

def test_record_from_dict():
    """Test deserialization from dictionary."""
    data = {
        "timestamp": "2024-01-15T10:30:00+00:00",
        "request_id": "abc-123",
        "method": "POST",
        "path": "/api/test",
        "status_code": 200,
        "ip_address": "127.0.0.1",
        "user_agent": "test",
        "duration_ms": 50.0,
    }

    record = AuditRecord.from_dict(data)
    assert record.method == "POST"
    assert record.request_id == "abc-123"

# test_pii_filter.py
def test_pii_filter_headers():
    """Test header redaction."""
    filter = PIIFilter(
        redact_fields=["password"],
        redact_headers=["Authorization"],
    )

    headers = {
        "Authorization": "Bearer secret-token",
        "Content-Type": "application/json",
    }

    result = filter.redact_headers(headers)
    assert result["Authorization"] == "[REDACTED]"
    assert result["Content-Type"] == "application/json"

def test_pii_filter_body():
    """Test body field redaction."""
    filter = PIIFilter(
        redact_fields=["password", "secret"],
        redact_headers=[],
    )

    body = {
        "username": "alice",
        "password": "super-secret",
        "nested": {
            "secret": "also-secret",
            "public": "visible",
        },
    }

    result = filter.redact_body(body)
    assert result["username"] == "alice"
    assert result["password"] == "[REDACTED]"
    assert result["nested"]["secret"] == "[REDACTED]"
    assert result["nested"]["public"] == "visible"

# test_logging_backend.py
@pytest.mark.asyncio
async def test_logging_backend_stores_record(caplog):
    """Test logging backend writes to logger."""
    backend = LoggingBackend(logger_name="test.audit", log_level="INFO")

    record = AuditRecord.create(
        method="GET",
        path="/api/test",
        status_code=200,
        duration_ms=10.0,
        ip_address="127.0.0.1",
    )

    with caplog.at_level(logging.INFO, logger="test.audit"):
        await backend.store(record)

    assert len(caplog.records) == 1
    assert "/api/test" in caplog.records[0].message

@pytest.mark.asyncio
async def test_logging_backend_error_level_for_5xx(caplog):
    """Test 5xx responses logged at ERROR level."""
    backend = LoggingBackend(logger_name="test.audit")

    record = AuditRecord.create(
        method="GET",
        path="/api/error",
        status_code=500,
        duration_ms=100.0,
        ip_address="127.0.0.1",
    )

    with caplog.at_level(logging.ERROR, logger="test.audit"):
        await backend.store(record)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
```

### Tier 2: Integration Tests (NO MOCKING - Real Infrastructure)

**Location:** `tests/integration/auth/audit/`

```python
# test_dataflow_backend_integration.py
@pytest.fixture
async def db():
    """Create DataFlow instance with real database."""
    db = DataFlow("sqlite:///:memory:")

    @db.model
    class AuditRecord:
        id: str
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
        error: Optional[str]
        metadata: dict

    await db.initialize()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_dataflow_backend_stores_and_queries(db):
    """Test DataFlow backend (NO MOCKING)."""
    backend = DataFlowBackend(dataflow=db)
    await backend.initialize()

    # Store record
    record = AuditRecord.create(
        method="POST",
        path="/api/users",
        status_code=201,
        duration_ms=45.0,
        ip_address="192.168.1.1",
        user_id="user-123",
    )

    await backend.store(record)

    # Query records
    results = await backend.query(user_id="user-123")
    assert len(results) == 1
    assert results[0].path == "/api/users"

# test_middleware_integration.py
@pytest.fixture
def test_client_with_audit():
    """Create test client with audit middleware."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    config = AuditConfig(
        backend="logging",
        exclude_paths=["/health"],
    )
    app.add_middleware(AuditMiddleware, config=config)

    @app.get("/api/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return TestClient(app)

def test_middleware_logs_requests(test_client_with_audit, caplog):
    """Test middleware logs requests (NO MOCKING)."""
    with caplog.at_level(logging.INFO, logger="nexus.audit"):
        response = test_client_with_audit.get("/api/test")

    assert response.status_code == 200

    # Check audit log was created
    audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
    assert len(audit_logs) == 1
    assert "/api/test" in audit_logs[0].message

def test_middleware_excludes_health_endpoint(test_client_with_audit, caplog):
    """Test excluded paths not logged (NO MOCKING)."""
    with caplog.at_level(logging.INFO, logger="nexus.audit"):
        response = test_client_with_audit.get("/health")

    assert response.status_code == 200

    # Check no audit log for excluded path
    audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
    assert len(audit_logs) == 0

def test_pii_redaction_in_middleware(test_client_with_audit, caplog):
    """Test PII is redacted (NO MOCKING)."""
    with caplog.at_level(logging.INFO, logger="nexus.audit"):
        response = test_client_with_audit.get(
            "/api/test?password=secret&name=alice"
        )

    assert response.status_code == 200

    # Check password was redacted
    log_message = caplog.records[0].message
    assert "secret" not in log_message
    assert "[REDACTED]" in log_message or "password" not in log_message
```

### Tier 3: E2E Tests (NO MOCKING - Full Stack)

**Location:** `tests/e2e/auth/audit/`

```python
# test_audit_e2e.py
@pytest.mark.asyncio
async def test_full_audit_trail():
    """Test complete audit trail for request lifecycle (NO MOCKING)."""
    import aiohttp

    base_url = "http://localhost:8000"

    async with aiohttp.ClientSession() as session:
        # Make authenticated request
        token = create_test_jwt({"user_id": "user-123", "org_id": "tenant-456"})

        async with session.post(
            f"{base_url}/api/users",
            json={"name": "Alice"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            assert resp.status == 201

    # Query audit logs (assuming DataFlow backend)
    audit_records = await query_audit_logs(user_id="user-123")

    assert len(audit_records) >= 1
    record = audit_records[0]
    assert record.method == "POST"
    assert record.path == "/api/users"
    assert record.user_id == "user-123"
    assert record.tenant_id == "tenant-456"
```

## Performance Considerations

### Async Storage

Audit records are stored asynchronously to avoid blocking request processing:

```python
# In middleware
try:
    await self._backend.store(record)
except Exception as e:
    # Log but don't fail the request
    logger.error(f"Audit storage failed: {e}")
```

### Batching (Future Enhancement)

For high-traffic applications, consider batching:

```python
class BatchingBackend(AuditBackend):
    """Backend that batches records for efficiency."""

    def __init__(self, inner_backend: AuditBackend, batch_size: int = 100):
        self._inner = inner_backend
        self._batch: List[AuditRecord] = []
        self._batch_size = batch_size
        self._lock = asyncio.Lock()

    async def store(self, record: AuditRecord) -> None:
        async with self._lock:
            self._batch.append(record)
            if len(self._batch) >= self._batch_size:
                await self._flush()

    async def _flush(self) -> None:
        batch = self._batch
        self._batch = []
        for record in batch:
            await self._inner.store(record)
```

## Migration Path

### From Custom Implementations

```python
# Before: Custom audit middleware
from myapp.middleware import AuditMiddleware as CustomAuditMiddleware

app.add_middleware(CustomAuditMiddleware, log_level="INFO")

# After: Nexus audit logging
from nexus.auth import AuditConfig
from nexus.auth.audit import AuditMiddleware

app.add_middleware(
    AuditMiddleware,
    config=AuditConfig(backend="logging"),
)
```

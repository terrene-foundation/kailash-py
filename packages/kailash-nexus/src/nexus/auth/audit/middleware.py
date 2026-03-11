"""Audit logging middleware (TODO-310F).

FastAPI middleware that records every API request with structured
metadata for compliance and debugging.
"""

import fnmatch
import logging
import time
from typing import Any, Callable, Optional

from fastapi import Request, Response
from nexus.auth.audit.backends.base import AuditBackend
from nexus.auth.audit.backends.custom import CustomBackend
from nexus.auth.audit.backends.dataflow import DataFlowBackend
from nexus.auth.audit.backends.logging import LoggingBackend
from nexus.auth.audit.config import AuditConfig
from nexus.auth.audit.pii_filter import PIIFilter
from nexus.auth.audit.record import AuditRecord
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for audit logging.

    Records every API request with structured metadata.
    Supports multiple backends with failure isolation.
    """

    def __init__(
        self,
        app: Any,
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
            self._backend = CustomBackend(store_func=self.config.backend)
        elif self.config.backend == "dataflow":
            if not self._dataflow:
                raise ValueError("DataFlow instance required when backend='dataflow'")
            self._backend = DataFlowBackend(
                dataflow=self._dataflow,
                model_name=self.config.dataflow_model_name,
            )
            await self._backend.initialize()
        else:
            self._backend = LoggingBackend(
                logger_name="nexus.audit",
                log_level=self.config.log_level,
            )

        self._initialized = True

    def _is_excluded(self, request: Request) -> bool:
        """Check if request should be excluded from audit."""
        if request.method in self.config.exclude_methods:
            return True

        path = request.url.path
        for pattern in self.config.exclude_paths:
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address.

        SECURITY: Only trusts proxy headers (X-Forwarded-For, X-Real-IP)
        when trust_proxy_headers is enabled in config. Without this,
        attackers can forge IP addresses to bypass rate limiting or
        poison audit logs.
        """
        if self.config.trust_proxy_headers:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()

            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip

        if request.client:
            return request.client.host

        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with audit logging."""
        if not self.config.enabled:
            return await call_next(request)

        if self._is_excluded(request):
            return await call_next(request)

        await self._ensure_backend()

        start_time = time.time()

        request_body_size = 0
        content_length = request.headers.get("content-length")
        if content_length:
            request_body_size = int(content_length)

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        response_body_size = 0
        resp_content_length = response.headers.get("content-length")
        if resp_content_length:
            response_body_size = int(resp_content_length)

        # Read from AuthenticatedUser object set by JWT middleware
        user = getattr(request.state, "user", None)
        user_id = getattr(user, "user_id", None) if user else None
        tenant_id = getattr(request.state, "tenant_id", None) or (
            getattr(user, "tenant_id", None) if user else None
        )

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

        error = None
        if response.status_code >= 400:
            error = f"HTTP {response.status_code}"

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

        try:
            await self._backend.store(record)
        except Exception as e:
            # Never let audit failures break the application
            logger.error(f"Failed to store audit record: {e}")

        return response

"""Enhanced client for interacting with Kailash gateway.

This module provides async and sync clients for the Enhanced Gateway API
with support for resource references and convenient helper methods.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import aiohttp

from ..gateway.resource_resolver import ResourceReference

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result from workflow execution."""

    request_id: str
    workflow_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None

    @property
    def is_success(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def is_running(self) -> bool:
        return self.status in ["pending", "running"]


class KailashClient:
    """Enhanced client for interacting with Kailash gateway."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure HTTP session exists."""
        if not self._session:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)

    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def execute_workflow(
        self,
        workflow_id: str,
        inputs: Dict[str, Any],
        resources: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        wait: bool = True,
        poll_interval: float = 1.0,
        max_wait: float = 300.0,
    ) -> WorkflowResult:
        """Execute workflow with resource support."""
        await self._ensure_session()

        # Prepare request
        request_data = {
            "inputs": inputs,
            "resources": resources or {},
            "context": context or {},
        }

        # Execute workflow
        async with self._session.post(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/execute", json=request_data
        ) as response:
            response.raise_for_status()
            result_data = await response.json()

        result = WorkflowResult(**result_data)

        # Wait for completion if requested
        if wait and result.is_running:
            result = await self.wait_for_completion(
                workflow_id,
                result.request_id,
                poll_interval=poll_interval,
                max_wait=max_wait,
            )

        return result

    async def wait_for_completion(
        self,
        workflow_id: str,
        request_id: str,
        poll_interval: float = 1.0,
        max_wait: float = 300.0,
    ) -> WorkflowResult:
        """Wait for workflow completion."""
        await self._ensure_session()

        elapsed = 0.0
        while elapsed < max_wait:
            # Get status
            result = await self.get_workflow_status(workflow_id, request_id)

            if not result.is_running:
                return result

            # Wait before next poll
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout
        raise TimeoutError(f"Workflow did not complete within {max_wait} seconds")

    async def get_workflow_status(
        self, workflow_id: str, request_id: str
    ) -> WorkflowResult:
        """Get workflow execution status."""
        await self._ensure_session()

        async with self._session.get(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/status/{request_id}"
        ) as response:
            response.raise_for_status()
            result_data = await response.json()

        return WorkflowResult(**result_data)

    async def list_workflows(self) -> Dict[str, Any]:
        """List available workflows."""
        await self._ensure_session()

        async with self._session.get(f"{self.base_url}/api/v1/workflows") as response:
            response.raise_for_status()
            return await response.json()

    async def get_workflow_details(self, workflow_id: str) -> Dict[str, Any]:
        """Get details of a specific workflow."""
        await self._ensure_session()

        async with self._session.get(
            f"{self.base_url}/api/v1/workflows/{workflow_id}"
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def health_check(self) -> Dict[str, Any]:
        """Check gateway health."""
        await self._ensure_session()

        async with self._session.get(f"{self.base_url}/api/v1/health") as response:
            response.raise_for_status()
            return await response.json()

    async def list_resources(self) -> List[str]:
        """List available resources."""
        await self._ensure_session()

        async with self._session.get(f"{self.base_url}/api/v1/resources") as response:
            response.raise_for_status()
            return await response.json()

    # Resource reference helpers
    def ref(self, resource_name: str) -> str:
        """Create reference to registered resource."""
        return f"@{resource_name}"

    def database(
        self,
        host: str,
        database: str,
        port: int = 5432,
        credentials_ref: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create database resource reference."""
        config = {"host": host, "port": port, "database": database, **kwargs}

        return {
            "type": "database",
            "config": config,
            "credentials_ref": credentials_ref,
        }

    def http_client(
        self,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        credentials_ref: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create HTTP client resource reference."""
        config = {**kwargs}
        if base_url:
            config["base_url"] = base_url
        if headers:
            config["headers"] = headers

        return {
            "type": "http_client",
            "config": config,
            "credentials_ref": credentials_ref,
        }

    def cache(
        self,
        host: str = "localhost",
        port: int = 6379,
        credentials_ref: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create cache resource reference."""
        config = {"host": host, "port": port, **kwargs}

        return {"type": "cache", "config": config, "credentials_ref": credentials_ref}


# Synchronous wrapper for convenience
class SyncKailashClient:
    """Synchronous wrapper for KailashClient."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.async_client = KailashClient(base_url, api_key)

    def execute_workflow(
        self, workflow_id: str, inputs: Dict[str, Any], **kwargs
    ) -> WorkflowResult:
        """Execute workflow synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.async_client.execute_workflow(workflow_id, inputs, **kwargs)
            )
        finally:
            loop.close()

    def list_workflows(self) -> Dict[str, Any]:
        """List workflows synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.async_client.list_workflows())
        finally:
            loop.close()

    def get_workflow_details(self, workflow_id: str) -> Dict[str, Any]:
        """Get workflow details synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.async_client.get_workflow_details(workflow_id)
            )
        finally:
            loop.close()

    def health_check(self) -> Dict[str, Any]:
        """Check health synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.async_client.health_check())
        finally:
            loop.close()

    def list_resources(self) -> List[str]:
        """List resources synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.async_client.list_resources())
        finally:
            loop.close()

    # Delegate resource helpers
    def __getattr__(self, name):
        return getattr(self.async_client, name)

from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Deploy client — register agent manifests locally or remotely.

Supports two deployment modes:

- **Local**: Persists the manifest as JSON in a ``LocalRegistry`` directory.
- **Remote**: POSTs the manifest to a CARE Platform API endpoint.

Example::

    from kaizen.deploy.client import deploy, deploy_local

    # Local deployment (no server required)
    result = deploy_local({"name": "my-agent", "module": "m", "class_name": "C"})

    # Remote deployment (CARE Platform)
    result = deploy(manifest, target_url="https://care.example.com", api_key="...")
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from kaizen.deploy.registry import LocalRegistry

logger = logging.getLogger(__name__)

__all__ = ["deploy", "deploy_local", "DeployResult", "DeployError", "DeployAuthError"]


# -----------------------------------------------------------------------
# Error hierarchy
# -----------------------------------------------------------------------


class DeployError(Exception):
    """Base error for deployment failures.

    Attributes:
        details: Structured error context (status codes, URLs, etc.).
    """

    def __init__(self, message: str, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class DeployAuthError(DeployError):
    """Raised when the remote endpoint returns 401 or 403."""

    pass


# -----------------------------------------------------------------------
# Result dataclass
# -----------------------------------------------------------------------


@dataclass
class DeployResult:
    """Structured result from a deploy operation.

    Attributes:
        agent_name: Name of the deployed agent.
        status: Deployment status (e.g. ``"registered"``).
        mode: ``"local"`` or ``"remote"``.
        governance_match: Whether the agent's governance constraints
            matched the platform policy (remote only, ``None`` for local).
        details: Additional context from the deployment.
    """

    agent_name: str = ""
    status: str = ""
    mode: str = ""  # "local" or "remote"
    governance_match: Optional[bool] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        result: Dict[str, Any] = {
            "agent_name": self.agent_name,
            "status": self.status,
            "mode": self.mode,
            "details": self.details,
        }
        if self.governance_match is not None:
            result["governance_match"] = self.governance_match
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeployResult:
        """Deserialize from a plain dict (inverse of ``to_dict``)."""
        return cls(
            agent_name=data.get("agent_name", ""),
            status=data.get("status", ""),
            mode=data.get("mode", ""),
            governance_match=data.get("governance_match"),
            details=data.get("details", {}),
        )


# -----------------------------------------------------------------------
# Deploy functions
# -----------------------------------------------------------------------


def deploy_local(
    manifest_dict: Dict[str, Any],
    registry_dir: Optional[str] = None,
) -> DeployResult:
    """Deploy an agent manifest to the local file-based registry.

    Args:
        manifest_dict: Agent manifest data (must contain ``"name"``).
        registry_dir: Path to the registry directory.  If ``None``,
            defaults to ``~/.kaizen/registry/``.

    Returns:
        ``DeployResult`` with ``mode="local"``.
    """
    registry = LocalRegistry(registry_dir=registry_dir)
    result = registry.register(manifest_dict)
    return DeployResult(
        agent_name=result["agent_name"],
        status=result["status"],
        mode="local",
        details=result,
    )


def deploy(
    manifest_dict: Dict[str, Any],
    target_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 30,
    registry_dir: Optional[str] = None,
) -> DeployResult:
    """Deploy an agent manifest.

    If *target_url* is ``None``, deploys to the local file-based registry.
    If *target_url* is provided, POSTs to the remote CARE Platform API
    at ``{target_url}/api/v1/agents``.

    Args:
        manifest_dict: Agent manifest data.
        target_url: Remote CARE Platform URL, or ``None`` for local.
        api_key: Bearer token for remote authentication.
        timeout: HTTP timeout in seconds (default 30).
        registry_dir: Local registry dir (only used when *target_url* is ``None``).

    Returns:
        ``DeployResult`` describing the outcome.

    Raises:
        DeployAuthError: On HTTP 401 or 403 from the remote endpoint.
        DeployError: On any other HTTP or connection error.
    """
    if target_url is None:
        return deploy_local(manifest_dict, registry_dir=registry_dir)

    # --- Remote deployment ---
    url = f"{target_url.rstrip('/')}/api/v1/agents"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = json.dumps(manifest_dict).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    logger.info("Deploying agent %r to %s", manifest_dict.get("name", "?"), url)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            return DeployResult(
                agent_name=manifest_dict.get("name", ""),
                status=resp_data.get("status", "registered"),
                mode="remote",
                governance_match=resp_data.get("governance_match"),
                details=resp_data,
            )
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise DeployAuthError(
                f"Authentication failed: HTTP {exc.code}",
                details={"status_code": exc.code, "url": url},
            ) from exc
        raise DeployError(
            f"Deploy failed: HTTP {exc.code}",
            details={"status_code": exc.code, "url": url},
        ) from exc
    except urllib.error.URLError as exc:
        raise DeployError(
            f"Connection failed: {exc.reason}",
            details={"url": url, "reason": str(exc.reason)},
        ) from exc

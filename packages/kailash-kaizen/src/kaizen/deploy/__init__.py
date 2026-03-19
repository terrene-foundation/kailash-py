from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Agent deployment — introspection, local registry, and remote deploy client.

This module provides:

- ``introspect_agent(module, class_name)`` — extract runtime metadata from a
  Kaizen agent class without instantiating it.
- ``LocalRegistry`` — file-based agent registry (default ``~/.kaizen/registry/``).
- ``deploy()`` / ``deploy_local()`` — deploy an agent manifest to a local or
  remote CARE Platform registry.
- ``DeployResult`` — structured result from a deploy operation.

Example usage::

    from kaizen.deploy import introspect_agent, deploy_local

    info = introspect_agent("agents.market_analyzer", "MarketAnalyzer")
    result = deploy_local(info)
    print(result.status)  # "registered"
"""

from kaizen.deploy.client import (
    DeployAuthError,
    DeployError,
    DeployResult,
    deploy,
    deploy_local,
)
from kaizen.deploy.introspect import introspect_agent
from kaizen.deploy.registry import LocalRegistry

__all__ = [
    "introspect_agent",
    "deploy",
    "deploy_local",
    "DeployResult",
    "DeployError",
    "DeployAuthError",
    "LocalRegistry",
]

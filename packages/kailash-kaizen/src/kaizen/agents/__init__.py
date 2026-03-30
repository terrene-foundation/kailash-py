# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Proxy module: kaizen.agents -> kaizen_agents.agents.registry

Provides backward-compatible import path for agent registration functions.
The canonical implementation lives in kaizen_agents.agents.registry.

Also registers sys.modules aliases so that mock.patch targets like
``kaizen.agents.multi_modal.transcription_agent.WhisperProcessor``
resolve to the real kaizen_agents module (where the name is looked up
at runtime).
"""

import sys

from kaizen_agents.agents.registry import (
    AgentRegistration,
    AgentTypeRegistration,
    create_agent_from_type,
    get_agent_type_registration,
    get_agent_types_by_category,
    get_agent_types_by_tag,
    is_agent_type_registered,
    list_agent_type_names,
    list_agent_types,
    register_agent,
    register_agent_type,
)

# Trigger built-in agent registration so queries work immediately
try:
    from kaizen_agents.agents import register_builtin as _register_builtin  # noqa: F401
except ImportError:
    pass

# Alias submodules so mock.patch("kaizen.agents.multi_modal...") resolves
# to the real kaizen_agents.agents.multi_modal module (same object).
import kaizen_agents.agents.multi_modal as _mm  # noqa: E402
import kaizen_agents.agents.multi_modal.transcription_agent as _ta  # noqa: E402

sys.modules.setdefault("kaizen.agents.multi_modal", _mm)
sys.modules.setdefault("kaizen.agents.multi_modal.transcription_agent", _ta)

__all__ = [
    "register_agent",
    "register_agent_type",
    "get_agent_type_registration",
    "is_agent_type_registered",
    "list_agent_type_names",
    "list_agent_types",
    "get_agent_types_by_tag",
    "get_agent_types_by_category",
    "create_agent_from_type",
    "AgentRegistration",
    "AgentTypeRegistration",
]

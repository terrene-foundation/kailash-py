# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["HandlerDef", "HandlerParam", "HandlerRegistry"]


@dataclass
class HandlerParam:
    """Parameter definition for a handler function."""

    name: str
    param_type: str = "string"  # string, integer, float, bool, object, array, file
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class HandlerDef:
    """Transport-agnostic handler definition.

    All handlers (both workflow-backed and function-backed) are stored as
    HandlerDef instances. Transports read these to build their dispatch layer.
    """

    name: str
    func: Optional[Callable] = None
    params: List[HandlerParam] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class HandlerRegistry:
    """Central registry for all handlers and workflows.

    Stores HandlerDef instances for function-based handlers and Workflow
    objects for workflow-based registrations. Transports and internal
    Nexus code read from this registry.

    Optionally accepts an EventBus to publish HANDLER_REGISTERED events.
    """

    def __init__(self, event_bus=None):
        self._handlers: Dict[str, HandlerDef] = {}
        self._workflows: Dict[str, Any] = {}  # name -> Workflow object
        self._handler_funcs: Dict[str, Dict[str, Any]] = {}  # compat dict
        self._event_bus = event_bus

    def register_workflow(self, name: str, workflow) -> None:
        """Register a workflow by name."""
        self._workflows[name] = workflow

    def register_handler(
        self,
        name: str,
        func: Callable,
        *,
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        workflow=None,
    ) -> HandlerDef:
        """Register a function-based handler.

        Args:
            name: Handler name (unique).
            func: The handler function.
            description: Human-readable description.
            tags: Categorization tags.
            metadata: Arbitrary metadata dict.
            workflow: The generated workflow for this handler (stored for
                backward compatibility with core.py internals).

        Returns:
            The created HandlerDef.

        Raises:
            ValueError: If name already registered as handler.
        """
        if name in self._handler_funcs:
            raise ValueError(
                f"Handler '{name}' is already registered. "
                f"Use a different name or unregister the existing handler first."
            )

        params = self._extract_params(func)
        handler_def = HandlerDef(
            name=name,
            func=func,
            params=params,
            description=description or getattr(func, "__doc__", "") or "",
            tags=tags or [],
            metadata=metadata or {},
        )
        self._handlers[name] = handler_def
        self._handler_funcs[name] = {
            "handler": func,
            "description": handler_def.description,
            "tags": handler_def.tags,
            "workflow": workflow,
        }

        if self._event_bus is not None:
            self._event_bus.publish_handler_registered(name, handler_def)

        return handler_def

    def get_handler(self, name: str) -> Optional[HandlerDef]:
        """Get a handler definition by name."""
        return self._handlers.get(name)

    def get_workflow(self, name: str):
        """Get a workflow by name. Returns None if not found."""
        return self._workflows.get(name)

    def list_handlers(self) -> List[HandlerDef]:
        """Return all registered handler definitions."""
        return list(self._handlers.values())

    def list_workflows(self) -> Dict[str, Any]:
        """Return dict of name -> workflow (backward compat)."""
        return dict(self._workflows)

    @property
    def workflow_count(self) -> int:
        return len(self._workflows)

    @property
    def handler_count(self) -> int:
        return len(self._handlers)

    @staticmethod
    def _extract_params(func: Callable) -> List[HandlerParam]:
        """Extract HandlerParam list from function signature."""
        from nexus.files import NexusFile

        params = []
        sig = inspect.signature(func)
        type_map = {
            str: "string",
            int: "integer",
            float: "float",
            bool: "bool",
            dict: "object",
            list: "array",
            NexusFile: "file",
        }
        for pname, p in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            annotation = p.annotation
            param_type = type_map.get(annotation, "string")
            required = p.default is inspect.Parameter.empty
            default = None if required else p.default
            params.append(
                HandlerParam(
                    name=pname,
                    param_type=param_type,
                    required=required,
                    default=default,
                )
            )
        return params

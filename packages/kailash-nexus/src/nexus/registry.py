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
        self._workflow_metadata: Dict[str, Dict[str, Any]] = {}  # name -> metadata
        self._handler_funcs: Dict[str, Dict[str, Any]] = {}  # compat dict
        self._event_bus = event_bus

    # 64 KiB is the soft cap on caller-supplied workflow metadata. The
    # metadata dict is stored on the Workflow object and in the registry
    # but is not currently rendered in any hot path; the cap is a
    # defensive bound against resource exhaustion via oversized or
    # non-JSON-serializable inputs. Raise at registration time so the
    # failure is attributed to the caller that supplied it.
    _METADATA_MAX_BYTES = 64 * 1024

    def register_workflow(
        self,
        name: str,
        workflow,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a workflow by name with optional metadata.

        Args:
            name: Workflow identifier.
            workflow: Workflow instance.
            metadata: Arbitrary metadata dict (version, author, tags,
                etc.). Must be JSON-serializable and fit within
                ``_METADATA_MAX_BYTES``.

        Raises:
            ValueError: If ``metadata`` is not JSON-serializable or
                exceeds the size cap.
        """
        if metadata is not None:
            import json

            try:
                encoded = json.dumps(metadata)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Workflow '{name}' metadata is not JSON-serializable: {exc}"
                ) from exc
            if len(encoded.encode("utf-8")) > self._METADATA_MAX_BYTES:
                raise ValueError(
                    f"Workflow '{name}' metadata exceeds "
                    f"{self._METADATA_MAX_BYTES} bytes"
                )
        self._workflows[name] = workflow
        if metadata is not None:
            # Store a SHALLOW copy so caller-side top-level mutations
            # after register() returns cannot retroactively change what
            # the registry holds (``metadata["version"] = "X"`` is
            # contained). Nested structures are still shared references:
            # ``metadata["tags"].append(...)`` WILL be observed by the
            # registry. Callers that need full isolation must pass a
            # deep-copied metadata dict themselves — deep-copy by
            # default would break legitimate non-JSON sentinel values
            # and the size-cap validator already ensures the metadata
            # is JSON-shaped for the common case.
            self._workflow_metadata[name] = dict(metadata)

    def get_workflow_metadata(self, name: str) -> Dict[str, Any]:
        """Get metadata for a registered workflow. Returns empty dict if none."""
        return self._workflow_metadata.get(name, {})

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

        if not callable(func):
            raise ValueError(
                f"Handler '{name}': func must be callable, "
                f"got {type(func).__name__}"
            )

        import inspect

        sig = inspect.signature(func)
        if not sig.parameters:
            raise ValueError(
                f"Handler '{name}': function must accept at least one parameter "
                f"(request or **kwargs)"
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

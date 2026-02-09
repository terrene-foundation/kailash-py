"""Handler node for executing arbitrary async/sync functions in workflows.

This module provides HandlerNode, which wraps user-defined functions as
workflow nodes. It bridges the gap between Nexus handler functions and
the Core SDK workflow execution engine, allowing developers to register
async functions directly as multi-channel workflows without PythonCodeNode
sandbox restrictions.

Key Features:
- Automatic parameter derivation from function signatures
- Support for both async and sync handlers
- Type annotation mapping to NodeParameter entries
- Seamless integration with WorkflowBuilder

Usage:
    from kailash.nodes.handler import HandlerNode, make_handler_workflow

    async def greet(name: str, greeting: str = "Hello") -> dict:
        return {"message": f"{greeting}, {name}!"}

    # Use directly as a node
    node = HandlerNode(handler=greet)

    # Or build a complete workflow
    workflow = make_handler_workflow(greet, "greet_handler")
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from kailash.nodes.base import NodeMetadata, NodeParameter
from kailash.nodes.base_async import AsyncNode

if TYPE_CHECKING:
    from kailash.workflow.workflow import Workflow

logger = logging.getLogger(__name__)

# Mapping from Python types to NodeParameter-compatible types
_TYPE_MAP: Dict[type, type] = {
    str: str,
    int: int,
    float: float,
    bool: bool,
    dict: dict,
    list: list,
}


def _derive_params_from_signature(
    func: Callable,
) -> Dict[str, NodeParameter]:
    """Inspect a function's signature and derive NodeParameter entries.

    Maps Python type annotations to NodeParameter definitions. Handles:
    - Required vs optional parameters (based on defaults)
    - Basic types (str, int, float, bool, dict, list)
    - Optional[T] detection (defaults to not required)
    - Complex annotations default to str with a debug log

    Args:
        func: The function to inspect.

    Returns:
        Dictionary mapping parameter names to NodeParameter instances.
    """
    sig = inspect.signature(func)
    params: Dict[str, NodeParameter] = {}

    for name, param in sig.parameters.items():
        # Skip **kwargs and *args
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        annotation = param.annotation
        has_default = param.default is not inspect.Parameter.empty
        default_value = param.default if has_default else None

        # Resolve the parameter type
        param_type = str  # fallback
        required = not has_default

        if annotation is inspect.Parameter.empty:
            # No annotation - default to str
            param_type = str
        else:
            # Check for Optional[T] (Union[T, None])
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())

            if origin is type(None):
                param_type = str
                required = False
            elif _is_optional_type(annotation):
                # Optional[T] -> extract T
                inner_types = [a for a in args if a is not type(None)]
                if inner_types:
                    param_type = _TYPE_MAP.get(inner_types[0], str)
                else:
                    param_type = str
                required = False
            elif annotation in _TYPE_MAP:
                param_type = _TYPE_MAP[annotation]
            else:
                # Complex type (Union, Literal, Annotated, custom classes)
                logger.debug(
                    f"Complex annotation '{annotation}' for parameter '{name}' "
                    f"in handler '{func.__name__}' defaulting to str"
                )
                param_type = str

        params[name] = NodeParameter(
            name=name,
            type=param_type,
            required=required,
            default=default_value,
            description=f"Parameter '{name}' from handler '{func.__name__}'",
        )

    return params


def _is_optional_type(annotation: Any) -> bool:
    """Check if an annotation is Optional[T] (i.e. Union[T, None])."""
    import typing

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # typing.Union with NoneType as one of the args
    if origin is typing.Union and type(None) in args:
        return True

    return False


class HandlerNode(AsyncNode):
    """Workflow node that wraps an arbitrary async or sync function.

    HandlerNode allows developers to use plain Python functions as workflow
    nodes, bypassing the PythonCodeNode sandbox. This is the foundation for
    Nexus's @app.handler() decorator.

    The handler function's signature is inspected at construction time to
    derive NodeParameter entries automatically. At execution time, only
    parameters matching the handler's signature are forwarded.

    Important MRO Note:
        Instance attributes (_handler, _handler_params) MUST be set BEFORE
        calling super().__init__() because Node.__init__() calls
        get_parameters() during initialization.

    Args:
        handler: The async or sync function to wrap.
        params: Optional explicit parameter definitions. If not provided,
            parameters are derived from the handler's signature.
        **kwargs: Additional configuration passed to AsyncNode.

    Example:
        async def process_data(data: dict, threshold: float = 0.5) -> dict:
            filtered = {k: v for k, v in data.items() if v > threshold}
            return {"filtered": filtered, "count": len(filtered)}

        node = HandlerNode(handler=process_data)
        result = await node.execute_async(data={"a": 1, "b": 0.3}, threshold=0.5)
    """

    def __init__(
        self,
        handler: Callable,
        params: Optional[Dict[str, NodeParameter]] = None,
        **kwargs,
    ):
        if not callable(handler):
            raise TypeError(f"handler must be callable, got {type(handler).__name__}")

        # CRITICAL: Set instance attrs BEFORE super().__init__()
        # Node.__init__() calls get_parameters() which needs these
        self._handler = handler
        self._handler_params = (
            params if params is not None else _derive_params_from_signature(handler)
        )

        # Set up metadata if not provided
        if "metadata" not in kwargs and not isinstance(
            kwargs.get("metadata"), NodeMetadata
        ):
            func_name = getattr(handler, "__name__", "handler")
            kwargs["metadata"] = NodeMetadata(
                name=f"HandlerNode:{func_name}",
                description=getattr(handler, "__doc__", "")
                or f"Handler for {func_name}",
                tags={"handler", "custom"},
            )

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Return parameter definitions derived from the handler signature."""
        return self._handler_params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute the wrapped handler function.

        Filters kwargs to only include parameters that match the handler's
        signature, then calls the handler. Sync handlers are run in an
        executor to avoid blocking the event loop.

        Args:
            **kwargs: Runtime inputs (superset of handler parameters).

        Returns:
            Dictionary of results. If the handler returns a dict, it is
            returned directly. Otherwise, the return value is wrapped as
            {"result": <value>}.
        """
        # Filter kwargs to only handler signature params
        sig = inspect.signature(self._handler)
        handler_params = set(sig.parameters.keys())

        # Check if handler accepts **kwargs
        accepts_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

        if accepts_var_keyword:
            filtered_kwargs = kwargs
        else:
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in handler_params}

        # Execute handler
        if asyncio.iscoroutinefunction(self._handler):
            result = await self._handler(**filtered_kwargs)
        else:
            # Run sync handler in executor to avoid blocking
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: self._handler(**filtered_kwargs)
            )

        # Normalize return value
        if isinstance(result, dict):
            return result
        return {"result": result}


def make_handler_workflow(
    handler: Callable,
    node_id: str = "handler",
    input_mapping: Optional[Dict[str, str]] = None,
) -> "Workflow":
    """Build a single-node workflow from a handler function.

    Creates a WorkflowBuilder with a HandlerNode instance and configures
    workflow-level input mappings so runtime inputs flow to the handler.

    Args:
        handler: The async or sync function to wrap.
        node_id: The node ID within the workflow (default: "handler").
        input_mapping: Optional mapping of workflow input names to handler
            parameter names. If not provided, identity mapping is used
            (each parameter maps to itself).

    Returns:
        A built Workflow instance ready for runtime execution.

    Example:
        async def summarize(text: str, max_length: int = 100) -> dict:
            return {"summary": text[:max_length]}

        workflow = make_handler_workflow(summarize, "summarizer")
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"text": "Hello world", "max_length": 50}
        )
    """
    from kailash.workflow.builder import WorkflowBuilder

    node = HandlerNode(handler=handler)
    params = _derive_params_from_signature(handler)

    builder = WorkflowBuilder()
    builder.add_node_instance(node, node_id)

    # Build identity input mapping if not provided
    if input_mapping is None:
        input_mapping = {name: name for name in params}

    builder.add_workflow_inputs(node_id, input_mapping)

    func_name = getattr(handler, "__name__", "handler")
    return builder.build(name=f"handler_workflow:{func_name}")

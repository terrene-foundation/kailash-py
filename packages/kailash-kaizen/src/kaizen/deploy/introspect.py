from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Runtime agent introspection.

Extracts metadata from a Kaizen agent class (or any class with
compatible attributes) without instantiating it.  The result dict
is compatible with ``AgentManifest.from_introspection()``.

Security note
-------------
``introspect_agent()`` uses ``importlib.import_module()`` which executes
module-level code.  Do **NOT** expose this function to untrusted callers.
It is intended for CLI and Python API use only — **NOT** safe for MCP
exposure (RT-07).
"""

import importlib
import inspect
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["introspect_agent"]


def introspect_agent(module: str, class_name: str) -> Dict[str, Any]:
    """Extract metadata from a Kaizen agent class at runtime.

    Imports the specified *module* and reads attributes from the class
    named *class_name*.  Recognized attributes:

    - ``signature`` — class whose docstring becomes the description and
      whose ``__annotations__`` are split into input/output schemas.
    - ``tools`` — list of tool identifiers.
    - ``capabilities`` — list of capability tags.
    - ``supported_models`` — list of LLM model identifiers.

    If no ``signature`` attribute is present, the class's own docstring
    is used as the description.

    Args:
        module: Dotted module path (e.g. ``"agents.market_analyzer"``).
        class_name: Class name within the module (e.g. ``"MarketAnalyzer"``).

    Returns:
        Dict compatible with ``AgentManifest.from_introspection()``.

    Raises:
        ModuleNotFoundError: If *module* cannot be imported.
        AttributeError: If *class_name* does not exist in the module.
    """
    mod = importlib.import_module(module)
    cls = getattr(mod, class_name)

    result: Dict[str, Any] = {
        "name": class_name,
        "module": module,
        "class_name": class_name,
        "description": "",
        "capabilities": [],
        "tools": [],
        "supported_models": [],
    }

    # --- Signature introspection ----------------------------------------
    signature_cls = getattr(cls, "signature", None)
    if signature_cls is not None:
        doc = inspect.getdoc(signature_cls)
        if doc:
            result["description"] = doc

        # Extract input/output schema from signature annotations.
        # Convention: fields with a default value on the signature class
        # are considered *inputs*; fields without a default are *outputs*.
        # Route through the shared helper so PEP 649/749 lazy annotations
        # on Python 3.14+ resolve the same way they do everywhere else in
        # the SDK — the helper docstring promises a single-point handler
        # for 3.13/3.14 differences, and this call site honours that.
        from kailash.utils.annotations import get_class_annotations

        hints: Dict[str, Any] = get_class_annotations(signature_cls)

        input_schema: Dict[str, str] = {}
        output_schema: Dict[str, str] = {}

        for field_name, field_type in hints.items():
            if field_name.startswith("_"):
                continue
            type_name = (
                field_type.__name__
                if hasattr(field_type, "__name__")
                else str(field_type)
            )
            if hasattr(signature_cls, field_name):
                input_schema[field_name] = type_name
            else:
                output_schema[field_name] = type_name

        result["input_schema"] = input_schema
        result["output_schema"] = output_schema
    else:
        doc = inspect.getdoc(cls)
        if doc:
            result["description"] = doc

    # --- Tools ----------------------------------------------------------
    tools = getattr(cls, "tools", [])
    if isinstance(tools, (list, tuple)):
        result["tools"] = list(tools)

    # --- Capabilities ---------------------------------------------------
    capabilities = getattr(cls, "capabilities", [])
    if isinstance(capabilities, (list, tuple)):
        result["capabilities"] = list(capabilities)

    # --- Supported models -----------------------------------------------
    models = getattr(cls, "supported_models", [])
    if isinstance(models, (list, tuple)):
        result["supported_models"] = list(models)

    logger.debug(
        "Introspected %s.%s: %d tools, %d capabilities",
        module,
        class_name,
        len(result["tools"]),
        len(result["capabilities"]),
    )

    return result

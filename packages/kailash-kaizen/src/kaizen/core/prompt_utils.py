"""
Shared prompt generation utilities for Kaizen agents.

This module is the single source of truth for signature-based prompt generation.
Both BaseAgent._generate_system_prompt() and WorkflowGenerator._generate_system_prompt()
delegate to these functions to avoid prompt logic duplication.

Functions:
    generate_prompt_from_signature: Build a system prompt from a Signature's fields.
    json_prompt_suffix: Return JSON format instructions for providers that require it.
"""

from __future__ import annotations

import json as json_module
from typing import Any, Dict, List, Optional


def generate_prompt_from_signature(signature: Any) -> str:
    """Generate a system prompt from a Signature's description and fields.

    This extracts the shared prompt-building logic that was previously duplicated
    in BaseAgent._generate_system_prompt() and WorkflowGenerator._generate_system_prompt().

    The generated prompt includes:
    1. Signature description (from docstring) or name-based fallback
    2. Input/output field name listing
    3. Input/output field descriptions (when available)

    It does NOT include:
    - MCP tool documentation (BaseAgent adds this separately)
    - JSON formatting instructions (use json_prompt_suffix() separately)

    Args:
        signature: A Kaizen Signature instance. Must have at least ``description``
            or ``name`` attributes.  Optionally exposes ``input_fields``,
            ``output_fields``, ``inputs``, and ``outputs``.

    Returns:
        The assembled prompt string.  Never empty -- falls back to
        ``"You are a helpful AI assistant."`` when the signature carries
        no description or name.
    """
    if signature is None:
        return "You are a helpful AI assistant."

    prompt_parts: List[str] = []

    # ------------------------------------------------------------------
    # 1. Description (docstring) or name-based fallback
    # ------------------------------------------------------------------
    if hasattr(signature, "description") and signature.description:
        prompt_parts.append(signature.description)
    elif hasattr(signature, "name") and signature.name:
        prompt_parts.append(f"Task: {signature.name}")
    else:
        prompt_parts.append("You are a helpful AI assistant.")

    # ------------------------------------------------------------------
    # 2. Input / output field name listing
    # ------------------------------------------------------------------
    input_names: List[str] = []
    output_names: List[str] = []

    # Prefer input_fields dict (class-based signatures).
    # Fall back to inputs property (programmatic signatures where input_fields is empty).
    if hasattr(signature, "input_fields") and signature.input_fields:
        input_names = list(signature.input_fields.keys())
    elif hasattr(signature, "inputs") and signature.inputs:
        input_names = list(signature.inputs)

    if hasattr(signature, "output_fields") and signature.output_fields:
        output_names = list(signature.output_fields.keys())
    elif hasattr(signature, "outputs") and signature.outputs:
        raw_outputs = signature.outputs
        if isinstance(raw_outputs, list):
            output_names = [str(o) for o in raw_outputs]
        else:
            output_names = [str(raw_outputs)]

    if input_names:
        prompt_parts.append(f"\nInputs: {', '.join(input_names)}")
    if output_names:
        prompt_parts.append(f"Outputs: {', '.join(output_names)}")

    # ------------------------------------------------------------------
    # 3. Field descriptions (richer context for the LLM)
    # ------------------------------------------------------------------
    if hasattr(signature, "input_fields") and signature.input_fields:
        field_descs: List[str] = []
        for field_name, field_def in signature.input_fields.items():
            if isinstance(field_def, dict) and field_def.get("desc"):
                field_descs.append(f"  - {field_name}: {field_def['desc']}")
        if field_descs:
            prompt_parts.append("\nInput Field Descriptions:")
            prompt_parts.extend(field_descs)

    if hasattr(signature, "output_fields") and signature.output_fields:
        field_descs = []
        for field_name, field_def in signature.output_fields.items():
            if isinstance(field_def, dict) and field_def.get("desc"):
                field_type = field_def.get("type", str)
                type_name = (
                    field_type.__name__
                    if hasattr(field_type, "__name__")
                    else str(field_type)
                )
                field_descs.append(
                    f"  - {field_name} ({type_name}): {field_def['desc']}"
                )
        if field_descs:
            prompt_parts.append("\nOutput Field Descriptions:")
            prompt_parts.extend(field_descs)

    return "\n".join(prompt_parts)


def json_prompt_suffix(output_fields: Optional[Dict[str, Any]] = None) -> str:
    """Return JSON format instructions for providers that need explicit guidance.

    Some providers (e.g. Azure with ``response_format: {"type": "json_object"}``)
    require the word "JSON" to appear in the prompt.  This helper builds the
    instruction block that was previously inlined in
    ``WorkflowGenerator._generate_system_prompt()``.

    When OpenAI strict-mode structured outputs (``json_schema``) are in use,
    callers should **not** append this suffix because the provider API enforces
    the schema automatically.

    Args:
        output_fields: The signature's ``output_fields`` dict.  Each value is
            expected to be a dict with at least a ``"type"`` key.  When *None*
            or empty, a generic JSON instruction is returned.

    Returns:
        A multi-line string starting with ``\\n---`` that instructs the LLM to
        respond with a JSON object.
    """
    parts: List[str] = []
    parts.append("\n---")
    parts.append(
        "\nIMPORTANT: You must respond with a valid JSON object containing exactly these fields:"
    )

    if output_fields:
        json_example: Dict[str, Any] = {}
        for field_name, field_def in output_fields.items():
            field_type = (
                field_def.get("type", str) if isinstance(field_def, dict) else str
            )
            if field_type == str:
                json_example[field_name] = f"<your {field_name} here>"
            elif field_type == float:
                json_example[field_name] = 0.0
            elif field_type == int:
                json_example[field_name] = 0
            elif field_type == bool:
                json_example[field_name] = False
            elif field_type == list:
                json_example[field_name] = []
            elif field_type == dict:
                json_example[field_name] = {}
            else:
                json_example[field_name] = f"<{field_name}>"

        parts.append(
            f"\nExpected JSON format:\n```json\n{json_module.dumps(json_example, indent=2)}\n```"
        )

    parts.append("\nDo not include any explanation or text outside the JSON object.")

    return "\n".join(parts)

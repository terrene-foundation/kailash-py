"""
Typed output-field extraction mixin for BaseAgent.

Extracts the four type-safe result accessors from ``base_agent.py`` --
``extract_list``, ``extract_dict``, ``extract_float`` and ``extract_str``.

An LLM returns a signature's output fields as whatever the model felt like
emitting: the declared list may arrive as a JSON string, the declared float as
``"0.82"``, the declared dict as ``"{}"``. These helpers coerce each field to
its declared type and fall back to a caller-supplied default rather than
raising, so a malformed field degrades one value instead of the whole agent
run.

Extracted from ``base_agent.py`` rather than inlined there: that module carries
two line-count guards (``tests/regression/test_loc_invariants.py`` and
``tests/unit/core/test_base_agent_slimming.py``) protecting it against
re-inlined helper code, and these accessors are generic dict coercion with no
dependency on ``BaseAgent`` state -- no ``self`` attribute is read by any of
them.

Uses duck typing -- the host class need provide nothing.

Copyright 2026 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

__all__ = ["OutputExtractionMixin"]


class OutputExtractionMixin:
    """Mixin providing type-safe output-field extraction for BaseAgent.

    Every method is a pure function of its arguments; the mixin holds no state
    and reads none from the host class.
    """

    def extract_list(
        self, result: Dict[str, Any], field_name: str, default: Optional[List] = None
    ) -> List:
        """Extract a list field from result with type safety."""
        if default is None:
            default = []

        field_value = result.get(field_name, default)

        if isinstance(field_value, list):
            return field_value

        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, list) else default
            except Exception:
                return default

        return default

    def extract_dict(
        self, result: Dict[str, Any], field_name: str, default: Optional[Dict] = None
    ) -> Dict:
        """Extract a dict field from result with type safety."""
        if default is None:
            default = {}

        field_value = result.get(field_name, default)

        if isinstance(field_value, dict):
            return field_value

        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, dict) else default
            except Exception:
                return default

        return default

    def extract_float(
        self, result: Dict[str, Any], field_name: str, default: float = 0.0
    ) -> float:
        """Extract a float field from result with type safety."""
        field_value = result.get(field_name, default)

        if isinstance(field_value, (int, float)):
            return float(field_value)

        if isinstance(field_value, str):
            try:
                return float(field_value)
            except Exception:
                return default

        return default

    def extract_str(
        self, result: Dict[str, Any], field_name: str, default: str = ""
    ) -> str:
        """Extract a string field from result with type safety."""
        field_value = result.get(field_name, default)
        return str(field_value) if field_value is not None else default

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Two consumer-facing breaks: the declared floor, and the gated-tool schema.

FINDING A — THE VERSION FLOOR IS PART OF THE CODE, NOT PACKAGING TRIVIA.
``kaizen-agents`` imports symbols from ``kailash-kaizen`` at MODULE scope, so a
symbol that post-dates the declared floor is not a degraded feature — it is an
``ImportError`` on ``import kaizen_agents`` for every user who upgrades one
package without the other. The floor is therefore an executable claim, and this
file makes it one: it re-derives every module-scope ``kaizen.*`` import from
source and asserts each resolves, so a future cross-package import cannot land
without someone confronting the floor.

The trap it closes is specific. It is NOT enough to check that the MODULE exists
at the floor — ``kaizen.core.tool_formatters`` predates 2.36.0 while
``normalize_tool_input_schema`` (added below, for Finding B) does not. Only a
SYMBOL-level check catches that, and the module-level version of this sweep
would have passed while shipping the break.

FINDING B — ``.get(key, default)`` DOES NOT FIRE ON A PRESENT-BUT-EMPTY VALUE.
A permission-gated MCP tool advertises ``inputSchema: {}``. Every converter read
it as ``tool.get("inputSchema", {})``, whose default fires only when the key is
ABSENT — so the empty dict flowed through untouched. Anthropic's
``InputSchemaTyped`` declares ``type: Required[Literal["object"]]``, so
``input_schema: {}`` is REJECTED; and even where an empty schema is accepted the
model loses every argument name for that tool.

This is the documented configuration, not an edge case: the pattern
``required_permission=f"tools.{tool_name}"`` in the MCP architecture docs gates
EVERY tool.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re

import pytest

pytestmark = pytest.mark.regression

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_SRC = _HERE.parents[2] / "src"
_PYPROJECT = _HERE.parents[2] / "pyproject.toml"


# ---------------------------------------------------------------------------
# Finding A — the declared floor must cover every module-scope kaizen import
# ---------------------------------------------------------------------------
def _module_scope_kaizen_imports() -> set[tuple[str, str]]:
    """Every (module, symbol) imported from `kaizen.*` at MODULE scope.

    Module scope only: a function-local import is lazy, so it degrades at call
    time rather than breaking `import kaizen_agents`. `kaizen_agents.*` is a
    DIFFERENT distribution and is excluded.
    """
    pairs: set[tuple[str, str]] = set()
    for path in _AGENTS_SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - defensive
            continue
        for node in tree.body:  # top level ONLY
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                and (node.module == "kaizen" or node.module.startswith("kaizen."))
            ):
                for alias in node.names:
                    pairs.add((node.module, alias.name))
    return pairs


class TestDeclaredFloorCoversEveryCrossPackageImport:
    def test_the_sweep_is_not_vacuous(self) -> None:
        """The enumeration must find something, or every claim below is empty."""
        pairs = _module_scope_kaizen_imports()
        assert len(pairs) >= 50, (
            f"only {len(pairs)} module-scope kaizen imports found; the AST walk "
            "is not reaching the tree and the resolution claim below would pass "
            "vacuously"
        )

    def test_every_module_scope_symbol_resolves(self) -> None:
        """The installed kailash-kaizen actually provides every symbol.

        Catches the SHAPE of the bug at head: a module-scope import of a symbol
        the depended-on package does not export.
        """
        missing = []
        for module, symbol in sorted(_module_scope_kaizen_imports()):
            try:
                mod = importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001 - reporting, not control flow
                missing.append(f"{module} (module import failed: {exc!r})")
                continue
            if not hasattr(mod, symbol):
                missing.append(f"{module}.{symbol}")
        assert missing == [], (
            "kaizen-agents imports these at MODULE scope but the installed "
            f"kailash-kaizen does not provide them: {missing}. Every one is an "
            "ImportError at `import kaizen_agents`."
        )

    def test_floor_is_at_least_the_version_that_carries_the_new_symbols(
        self,
    ) -> None:
        """The three symbols below landed while kailash-kaizen read 2.45.0.

        2.45.0's own release artifact may therefore PREDATE them, which makes
        2.46.0 the first version guaranteed to carry all three.
        """
        text = _PYPROJECT.read_text(encoding="utf-8")
        m = re.search(r'"kailash-kaizen>=(\d+)\.(\d+)\.(\d+)"', text)
        assert m, "no kailash-kaizen floor declared in kaizen-agents/pyproject.toml"
        floor = tuple(int(g) for g in m.groups())
        assert floor >= (2, 46, 0), (
            f"declared floor {floor} predates the module-scope symbols "
            "kaizen-agents now imports (kaizen.utils.credential_scrub, "
            "kaizen.llm.reasoning.ReasoningDegradedError, "
            "kaizen.core.tool_formatters.normalize_tool_input_schema). Users "
            "who upgrade kaizen-agents alone break at import."
        )

    @pytest.mark.parametrize(
        ("module", "symbol"),
        [
            ("kaizen.utils.credential_scrub", "scrub_local_error"),
            ("kaizen.utils.credential_scrub", "scrub_remote_error"),
            ("kaizen.llm.reasoning", "ReasoningDegradedError"),
            ("kaizen.core.tool_formatters", "normalize_tool_input_schema"),
        ],
    )
    def test_the_specific_post_floor_symbols_exist(
        self, module: str, symbol: str
    ) -> None:
        """Named explicitly so the floor's rationale stays checkable.

        If one of these is ever removed from kailash-kaizen, this reds here
        rather than at a consumer's first import.
        """
        assert hasattr(importlib.import_module(module), symbol)


# ---------------------------------------------------------------------------
# Finding B — a gated tool's empty inputSchema must never reach a provider
# ---------------------------------------------------------------------------
#: What a permission-GATED MCP tool advertises: the key is PRESENT and EMPTY.
GATED_TOOL = {"name": "search_docs", "description": "gated", "inputSchema": {}}

#: An ordinary tool, for the control direction.
FULL_TOOL = {
    "name": "search_docs",
    "description": "ordinary",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}


def _converters():
    from kaizen.core.tool_formatters import (
        convert_mcp_to_anthropic_tools,
        convert_mcp_to_openai_tools,
    )
    from kaizen_agents.runtime_adapters.tool_mapping.mcp import MCPToolMapper

    return {
        "anthropic": lambda t: convert_mcp_to_anthropic_tools([t])[0]["input_schema"],
        "openai": lambda t: convert_mcp_to_openai_tools([t])[0]["function"][
            "parameters"
        ],
        "kaizen_mcp_mapper": lambda t: MCPToolMapper._from_mcp_tool(t)["function"][
            "parameters"
        ],
    }


class TestGatedToolSchemaIsValidForEveryConverter:
    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_gated_tool_emits_a_valid_object_schema(self, name: str) -> None:
        schema = _converters()[name](GATED_TOOL)
        assert schema.get("type") == "object", (
            f"{name} emitted {schema!r} for a permission-gated tool. Anthropic's "
            "InputSchemaTyped declares type: Required[Literal['object']], so an "
            "empty schema is rejected outright; and any provider that accepts it "
            "leaves the model with no argument names at all."
        )
        assert "properties" in schema

    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_ordinary_tool_schema_is_passed_through_unchanged(self, name: str) -> None:
        """CONTROL. Normalization must not rewrite a real schema.

        A fix that stamped `{"type": "object", "properties": {}}` over every
        tool would pass the assertion above while destroying every real tool's
        parameters.
        """
        assert _converters()[name](FULL_TOOL) == FULL_TOOL["inputSchema"]

    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_absent_key_still_handled(self, name: str) -> None:
        """The pre-existing `.get(..., {})` case must not regress."""
        schema = _converters()[name]({"name": "x", "description": "d"})
        assert schema.get("type") == "object"

    def test_schema_with_properties_but_no_type_is_completed(self) -> None:
        """JSON Schema leaves a missing `type` unconstrained; the tool APIs
        all mean `object` in this position."""
        from kaizen.core.tool_formatters import normalize_tool_input_schema

        out = normalize_tool_input_schema({"properties": {"q": {"type": "string"}}})
        assert out["type"] == "object"
        assert out["properties"] == {"q": {"type": "string"}}

    def test_normalizer_does_not_mutate_its_argument(self) -> None:
        """The caller's dict is shared with the MCP client's tool cache."""
        from kaizen.core.tool_formatters import normalize_tool_input_schema

        original = {"properties": {"q": {"type": "string"}}}
        snapshot = {"properties": {"q": {"type": "string"}}}
        normalize_tool_input_schema(original)
        assert original == snapshot

    def test_every_converter_shares_one_normalizer(self) -> None:
        """Three converters that 'must agree' is the defect; one is the fix.

        Pins that no converter grew a private copy of the empty-schema rule.
        """
        import kaizen.core.tool_formatters as tf
        import kaizen_agents.runtime_adapters.tool_mapping.mcp as mcp_map

        assert mcp_map.normalize_tool_input_schema is tf.normalize_tool_input_schema

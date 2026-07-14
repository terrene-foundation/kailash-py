"""
Regression tests for the 5 review fixes applied when rescuing the
uncommitted ``kaizen.manifest`` module (issue #1735).

SELF-CONTAINED: mirrors ``tests/unit/test_manifest.py`` — pre-seeds
``sys.modules["kaizen"]`` with a placeholder so that ``kaizen.manifest.*``
resolves without triggering the full ``kaizen/__init__.py`` import chain
(which pulls in ``kailash.nodes.base`` and fails on a pre-existing import
error unrelated to this module).

Each test class below maps 1:1 to one of the 5 fixes:

    1. ManifestError(Exception) -> ManifestError(ValueError)
    2. agent.py::_escape_toml_string control-byte escaping
    3. agent.py/app.py::_parse_toml_bytes array-of-tables guard
    4. app.py budget parsing non-numeric guard
    5. agent.py/app.py::from_dict list-field type-confusion guard
"""

from __future__ import annotations

import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Bypass kaizen/__init__.py — seed a minimal placeholder in sys.modules
# so that ``kaizen.manifest`` can be imported without triggering the full
# kaizen init chain.
# ---------------------------------------------------------------------------
if "kaizen" not in sys.modules:
    _placeholder = types.ModuleType("kaizen")
    _placeholder.__path__ = [  # type: ignore[attr-defined]
        str(
            __import__("pathlib").Path(__file__).resolve().parents[2] / "src" / "kaizen"
        )
    ]
    _placeholder.__package__ = "kaizen"
    sys.modules["kaizen"] = _placeholder

from kaizen.manifest.agent import AgentManifest  # noqa: E402
from kaizen.manifest.app import AppManifest  # noqa: E402
from kaizen.manifest.errors import (  # noqa: E402
    ManifestError,
    ManifestParseError,
    ManifestValidationError,
)


# ---------------------------------------------------------------------------
# Fix 1 — ManifestError(Exception) -> ManifestError(ValueError)
# ---------------------------------------------------------------------------
class TestManifestErrorIsValueError:
    """The MCP catalog server's ``_dispatch_tool`` only forwards real error
    messages to the client for ``(ValueError, KeyError, TypeError)``; every
    ManifestError subclass MUST be a ValueError so malformed-manifest
    submissions surface the real validation message instead of an opaque
    "Internal tool error".
    """

    def test_manifest_error_is_value_error_subclass(self):
        assert issubclass(ManifestError, ValueError)

    def test_manifest_parse_error_is_value_error_subclass(self):
        assert issubclass(ManifestParseError, ValueError)

    def test_manifest_validation_error_is_value_error_subclass(self):
        assert issubclass(ManifestValidationError, ValueError)

    def test_malformed_manifest_raises_value_error_with_real_message(self):
        """A malformed manifest through the public parsing API raises a
        ValueError-subclass exception carrying the module's real
        validation message (not swallowed/generic)."""
        bad_toml = "this is [not valid toml"
        with pytest.raises(ValueError) as exc_info:
            AgentManifest.from_toml_str(bad_toml)
        assert isinstance(exc_info.value, ManifestParseError)
        assert "Invalid TOML" in str(exc_info.value)

    def test_missing_required_field_raises_value_error_with_real_message(self):
        toml_str = """\
[agent]
module = "kaizen.agents.x"
class_name = "X"
"""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest.from_toml_str(toml_str)
        assert isinstance(exc_info.value, ManifestValidationError)
        assert "name" in str(exc_info.value)

    def test_mcp_catalog_server_relays_real_message_not_internal_error(self):
        """End-to-end through the MCP catalog server's deploy_agent tool:
        a malformed manifest_toml MUST surface the real ManifestError
        message via ``_dispatch_tool``'s ``(ValueError, KeyError,
        TypeError)`` relay path, NOT the sanitized "Internal tool error"
        fallback reserved for unexpected exceptions.
        """
        import json
        import os

        # Bypass the same broken kailash.nodes.base import chain the MCP
        # catalog server tests work around.
        _src_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), os.pardir, "..", "src")
        )
        if _src_dir not in sys.path:
            sys.path.insert(0, _src_dir)

        from kaizen.mcp.catalog_server.server import CatalogMCPServer

        server = CatalogMCPServer()
        server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            }
        )
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "deploy_agent",
                    "arguments": {"manifest_toml": "[agent]\nname = "},
                },
            }
        )
        result = json.loads(resp["result"]["content"][0]["text"])
        assert resp["result"]["isError"] is True
        assert result["error"] != "Internal tool error"
        assert "Invalid TOML" in result["error"]


# ---------------------------------------------------------------------------
# Fix 2 — _escape_toml_string control-byte escaping
# ---------------------------------------------------------------------------
class TestControlByteRoundTrip:
    def test_control_byte_in_name_round_trips(self):
        raw_name = "name\x00with\x01control\x1fbytes"
        manifest = AgentManifest(
            name=raw_name, module="kaizen.agents.x", class_name="X"
        )
        toml_output = manifest.to_toml()
        restored = AgentManifest.from_toml_str(toml_output)
        assert restored.name == raw_name

    def test_control_byte_in_description_round_trips(self):
        raw_description = "line1\x02line2\x1fline3"
        manifest = AgentManifest(
            name="bot",
            module="kaizen.agents.bot",
            class_name="Bot",
            description=raw_description,
        )
        toml_output = manifest.to_toml()
        restored = AgentManifest.from_toml_str(toml_output)
        assert restored.description == raw_description

    def test_control_byte_in_capability_list_item_round_trips(self):
        raw_cap = "cap\x07withbell"
        manifest = AgentManifest(
            name="bot",
            module="kaizen.agents.bot",
            class_name="Bot",
            capabilities=[raw_cap, "normal-cap"],
        )
        toml_output = manifest.to_toml()
        restored = AgentManifest.from_toml_str(toml_output)
        assert restored.capabilities == [raw_cap, "normal-cap"]

    def test_escaped_output_contains_no_raw_control_bytes(self):
        """The serialized TOML string itself MUST NOT contain the raw
        control byte (only the escaped \\uXXXX form) — otherwise the
        output is not valid TOML in the first place."""
        manifest = AgentManifest(name="name\x00null", module="m", class_name="C")
        toml_output = manifest.to_toml()
        assert "\x00" not in toml_output
        assert "\\u0000" in toml_output


# ---------------------------------------------------------------------------
# Fix 3 — array-of-tables ([[agent]] / [[application]]) guard
# ---------------------------------------------------------------------------
class TestArrayOfTablesRaisesParseError:
    def test_agent_array_of_tables_raises_manifest_parse_error(self):
        toml_str = """\
[[agent]]
name = "bot-a"
module = "kaizen.agents.a"
class_name = "A"

[[agent]]
name = "bot-b"
module = "kaizen.agents.b"
class_name = "B"
"""
        with pytest.raises(ManifestParseError):
            AgentManifest.from_toml_str(toml_str)

    def test_agent_array_of_tables_does_not_raise_attribute_error(self):
        toml_str = """\
[[agent]]
name = "bot-a"
module = "kaizen.agents.a"
class_name = "A"
"""
        try:
            AgentManifest.from_toml_str(toml_str)
        except AttributeError:
            pytest.fail(
                "from_toml_str raised a raw AttributeError instead of "
                "ManifestParseError for [[agent]] array-of-tables input"
            )
        except ManifestParseError:
            pass  # expected

    def test_application_array_of_tables_raises_manifest_parse_error(self):
        toml_str = """\
[[application]]
name = "app-a"
owner = "alex@example.com"
"""
        with pytest.raises(ManifestParseError):
            AppManifest.from_toml_str(toml_str)

    def test_application_array_of_tables_does_not_raise_attribute_error(self):
        toml_str = """\
[[application]]
name = "app-a"
owner = "alex@example.com"
"""
        try:
            AppManifest.from_toml_str(toml_str)
        except AttributeError:
            pytest.fail(
                "from_toml_str raised a raw AttributeError instead of "
                "ManifestParseError for [[application]] array-of-tables input"
            )
        except ManifestParseError:
            pass  # expected


# ---------------------------------------------------------------------------
# Fix 4 — non-numeric budget raises ManifestValidationError
# ---------------------------------------------------------------------------
class TestNonNumericBudgetRaises:
    def test_non_numeric_budget_raises_manifest_validation_error(self):
        toml_str = """\
[application]
name = "budget-test"
owner = "bob@example.com"

[application.budget]
monthly = "free"
"""
        with pytest.raises(ManifestValidationError, match="monthly"):
            AppManifest.from_toml_str(toml_str)

    def test_non_numeric_budget_does_not_raise_raw_invalid_operation(self):
        toml_str = """\
[application]
name = "budget-test"
owner = "bob@example.com"

[application.budget]
monthly = "free"
"""
        import decimal

        try:
            AppManifest.from_toml_str(toml_str)
        except decimal.InvalidOperation:
            pytest.fail(
                "from_toml_str raised a raw decimal.InvalidOperation "
                "instead of ManifestValidationError for non-numeric budget"
            )
        except ManifestValidationError:
            pass  # expected

    def test_numeric_budget_still_works(self):
        """Regression guard: the fix must not break the happy path."""
        toml_str = """\
[application]
name = "budget-test"
owner = "bob@example.com"

[application.budget]
monthly = 250
"""
        manifest = AppManifest.from_toml_str(toml_str)
        assert manifest.budget_monthly_microdollars == 250_000_000


# ---------------------------------------------------------------------------
# Fix 5 — should-be-list fields raise on str (type-confusion), not
# silently char-split
# ---------------------------------------------------------------------------
class TestListFieldTypeConfusionRaises:
    def test_capabilities_string_raises_not_char_split(self):
        with pytest.raises(ManifestValidationError, match="capabilities"):
            AgentManifest.from_dict(
                {
                    "name": "bot",
                    "module": "kaizen.agents.bot",
                    "class_name": "Bot",
                    "capabilities": "pii",
                }
            )

    def test_tools_string_raises(self):
        with pytest.raises(ManifestValidationError, match="tools"):
            AgentManifest.from_dict(
                {
                    "name": "bot",
                    "module": "kaizen.agents.bot",
                    "class_name": "Bot",
                    "tools": "scanner",
                }
            )

    def test_supported_models_string_raises(self):
        with pytest.raises(ManifestValidationError, match="supported_models"):
            AgentManifest.from_dict(
                {
                    "name": "bot",
                    "module": "kaizen.agents.bot",
                    "class_name": "Bot",
                    "supported_models": "gpt-4",
                }
            )

    def test_agents_requested_string_raises(self):
        with pytest.raises(ManifestValidationError, match="agents_requested"):
            AppManifest.from_dict(
                {
                    "name": "app",
                    "owner": "bob@example.com",
                    "agents_requested": "doc-classifier",
                }
            )

    def test_capabilities_dict_raises(self):
        """Non-list, non-string types are also rejected (not just str)."""
        with pytest.raises(ManifestValidationError, match="capabilities"):
            AgentManifest.from_dict(
                {
                    "name": "bot",
                    "module": "kaizen.agents.bot",
                    "class_name": "Bot",
                    "capabilities": {"pii": True},
                }
            )

    def test_capabilities_list_still_works(self):
        """Regression guard: the fix must not break the happy path."""
        manifest = AgentManifest.from_dict(
            {
                "name": "bot",
                "module": "kaizen.agents.bot",
                "class_name": "Bot",
                "capabilities": ["pii-detection", "classification"],
            }
        )
        assert manifest.capabilities == ["pii-detection", "classification"]

    def test_capabilities_tuple_coerced_to_list(self):
        """A tuple is a legitimate list-like input and MUST still coerce
        (not raise) — only str/bytes/non-sequence types are rejected."""
        manifest = AgentManifest.from_dict(
            {
                "name": "bot",
                "module": "kaizen.agents.bot",
                "class_name": "Bot",
                "capabilities": ("pii-detection", "classification"),
            }
        )
        assert manifest.capabilities == ["pii-detection", "classification"]

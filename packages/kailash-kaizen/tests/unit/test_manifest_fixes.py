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
from kaizen.manifest.governance import GovernanceManifest  # noqa: E402
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

    def test_governance_data_access_needed_string_raises(self):
        # Fix #5 extended to GovernanceManifest.from_dict (same char-split class)
        with pytest.raises(ManifestValidationError, match="data_access_needed"):
            GovernanceManifest.from_dict({"data_access_needed": "pii"})

    def test_governance_data_access_needed_list_still_works(self):
        g = GovernanceManifest.from_dict({"data_access_needed": ["pii", "logs"]})
        assert g.data_access_needed == ["pii", "logs"]

    # Fix #5 extended to the TOML-parse + introspection paths — the PRODUCTION
    # path (deployment.py -> from_toml_str) goes through these, NOT from_dict.
    def test_from_toml_str_capabilities_string_raises(self):
        with pytest.raises(ManifestValidationError, match="capabilities"):
            AgentManifest.from_toml_str(
                '[agent]\nname="a"\nmodule="m"\nclass_name="C"\n'
                'capabilities="pii-detection"\n'
            )

    def test_from_introspection_capabilities_string_raises(self):
        with pytest.raises(ManifestValidationError, match="capabilities"):
            AgentManifest.from_introspection(
                {"name": "a", "module": "m", "class_name": "C", "capabilities": "pii"}
            )

    def test_app_from_toml_str_agents_string_raises(self):
        with pytest.raises(ManifestValidationError, match="agents_requested"):
            AppManifest.from_toml_str(
                '[application]\nname="x"\n'
                '[application.agents_requested]\nagents="single"\n'
            )


# ===========================================================================
# Security review findings (4) + governance-error consistency
# ===========================================================================


def _agent_toml_with_budget(budget_literal: str) -> str:
    """Build an agent manifest whose [governance] declares a raw budget
    literal (unquoted → parsed as a TOML number)."""
    return (
        '[agent]\nname="x"\nmodule="m"\nclass_name="C"\n'
        "[governance]\n"
        'purpose="p"\n'
        'risk_level="low"\n'
        'suggested_posture="supervised"\n'
        f"max_budget_microdollars = {budget_literal}\n"
    )


# ---------------------------------------------------------------------------
# Finding 1 (HIGH) — non-finite governance budget (inf/nan) is rejected
# ---------------------------------------------------------------------------
class TestGovernanceBudgetRejectsNonFinite:
    def test_inf_budget_raises_validation_error(self):
        with pytest.raises(ManifestValidationError):
            AgentManifest.from_toml_str(_agent_toml_with_budget("inf"))

    def test_nan_budget_raises_validation_error(self):
        with pytest.raises(ManifestValidationError):
            AgentManifest.from_toml_str(_agent_toml_with_budget("nan"))

    def test_negative_inf_budget_raises_validation_error(self):
        with pytest.raises(ManifestValidationError):
            AgentManifest.from_toml_str(_agent_toml_with_budget("-inf"))

    def test_direct_construction_inf_raises(self):
        with pytest.raises(ManifestValidationError):
            GovernanceManifest(max_budget_microdollars=float("inf"))

    def test_direct_construction_nan_raises(self):
        with pytest.raises(ManifestValidationError):
            GovernanceManifest(max_budget_microdollars=float("nan"))

    def test_error_message_does_not_echo_unbounded_value(self):
        """The message MUST NOT echo 'inf'/'nan' back (an attacker-supplied
        non-finite value should not appear in the forwarded error)."""
        with pytest.raises(ManifestValidationError) as exc_info:
            GovernanceManifest(max_budget_microdollars=float("inf"))
        msg = str(exc_info.value).lower()
        assert "inf" not in msg
        assert "nan" not in msg

    def test_finite_budget_still_accepted(self):
        manifest = AgentManifest.from_toml_str(_agent_toml_with_budget("5000000"))
        assert manifest.governance is not None
        assert manifest.governance.max_budget_microdollars == 5_000_000

    def test_negative_finite_budget_still_rejected(self):
        with pytest.raises(ManifestValidationError):
            GovernanceManifest(max_budget_microdollars=-100)


# ---------------------------------------------------------------------------
# Finding 2 (MEDIUM) — attacker-controlled field values are length-bounded
# in forwarded error messages (no error-payload amplification)
# ---------------------------------------------------------------------------
class TestErrorMessagesAreLengthBounded:
    def test_coerce_list_field_huge_value_message_is_bounded(self):
        huge = "p" * 100_000
        with pytest.raises(ManifestValidationError) as exc_info:
            AgentManifest.from_dict(
                {
                    "name": "b",
                    "module": "m",
                    "class_name": "C",
                    "capabilities": huge,
                }
            )
        msg = str(exc_info.value)
        # Bounded: the 100KB payload MUST NOT be echoed verbatim.
        assert len(msg) < 400
        assert len(msg) < len(huge)
        assert huge not in msg

    def test_manifest_version_huge_value_message_is_bounded(self):
        huge = "9" * 100_000
        with pytest.raises(ManifestValidationError) as exc_info:
            AgentManifest(manifest_version=huge, name="b", module="m", class_name="C")
        msg = str(exc_info.value)
        assert len(msg) < 400
        assert huge not in msg

    def test_governance_risk_level_huge_value_message_is_bounded(self):
        huge = "z" * 100_000
        with pytest.raises(ManifestValidationError) as exc_info:
            GovernanceManifest(risk_level=huge)
        msg = str(exc_info.value)
        assert len(msg) < 400
        assert huge not in msg

    def test_registry_invalid_name_message_is_bounded(self):
        from kaizen.mcp.catalog_server.registry import _validate_name

        huge = "!" * 100_000  # fails the name regex
        with pytest.raises(ValueError) as exc_info:
            _validate_name(huge)
        msg = str(exc_info.value)
        assert len(msg) < 400
        assert huge not in msg

    def test_safe_repr_truncates_and_marks(self):
        from kaizen.manifest._coerce import safe_repr

        out = safe_repr("a" * 5000, max_len=200)
        assert len(out) <= 200
        assert out.endswith("…(truncated)")

    def test_safe_repr_short_value_unchanged(self):
        from kaizen.manifest._coerce import safe_repr

        assert safe_repr("small") == "'small'"


# ---------------------------------------------------------------------------
# Finding 3 (LOW) — non-finite app budget raises ManifestValidationError,
# not a raw OverflowError
# ---------------------------------------------------------------------------
class TestAppBudgetOverflow:
    def _app_toml(self, budget_literal: str) -> str:
        return (
            '[application]\nname="a"\nowner="o@example.com"\n'
            f"[application.budget]\nmonthly = {budget_literal}\n"
        )

    def test_inf_app_budget_raises_validation_error(self):
        with pytest.raises(ManifestValidationError, match="monthly"):
            AppManifest.from_toml_str(self._app_toml("inf"))

    def test_inf_app_budget_does_not_raise_raw_overflow_error(self):
        try:
            AppManifest.from_toml_str(self._app_toml("inf"))
        except OverflowError:
            pytest.fail(
                "from_toml_str raised a raw OverflowError instead of "
                "ManifestValidationError for an inf budget"
            )
        except ManifestValidationError:
            pass  # expected

    def test_nan_app_budget_raises_validation_error(self):
        with pytest.raises(ManifestValidationError, match="monthly"):
            AppManifest.from_toml_str(self._app_toml("nan"))


# ---------------------------------------------------------------------------
# Finding 4 (LOW, documentation) — loader path-handling security warning
# ---------------------------------------------------------------------------
class TestLoaderDocumentsPathTraversalRisk:
    def test_module_docstring_warns_about_path_containment(self):
        import kaizen.manifest.loader as loader_mod

        doc = (loader_mod.__doc__ or "").lower()
        assert "traversal" in doc or "containment" in doc or "allowlist" in doc

    def test_load_manifest_docstring_warns(self):
        from kaizen.manifest.loader import load_manifest

        doc = (load_manifest.__doc__ or "").lower()
        assert "containment" in doc or "allowlist" in doc

    def test_load_app_manifest_docstring_warns(self):
        from kaizen.manifest.loader import load_app_manifest

        doc = (load_app_manifest.__doc__ or "").lower()
        assert "containment" in doc or "allowlist" in doc


# ---------------------------------------------------------------------------
# Consistency — governance risk_level/suggested_posture raise
# ManifestValidationError (aligned with the rest of the module), which is a
# ValueError subclass so existing pytest.raises(ValueError) still passes.
# ---------------------------------------------------------------------------
class TestGovernanceErrorConsistency:
    def test_invalid_risk_level_raises_manifest_validation_error(self):
        with pytest.raises(ManifestValidationError, match="risk_level"):
            GovernanceManifest(risk_level="extreme")

    def test_invalid_posture_raises_manifest_validation_error(self):
        with pytest.raises(ManifestValidationError, match="suggested_posture"):
            GovernanceManifest(suggested_posture="autonomous")

    def test_governance_errors_are_still_value_errors(self):
        # Backward-compat: existing callers catching ValueError still work.
        with pytest.raises(ValueError):
            GovernanceManifest(risk_level="extreme")
        with pytest.raises(ValueError):
            GovernanceManifest(suggested_posture="autonomous")

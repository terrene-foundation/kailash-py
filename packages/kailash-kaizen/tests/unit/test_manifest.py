"""
Unit tests for kaizen.manifest — Agent, App, and Governance manifest models.

SELF-CONTAINED: Only imports from kaizen.manifest submodules, NOT from
kaizen core.  We pre-seed sys.modules["kaizen"] with a placeholder so
that ``kaizen.manifest.*`` resolves without triggering kaizen/__init__.py
(which pulls in kailash.nodes.base and fails on the pre-existing import error).
"""

from __future__ import annotations

import importlib
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

# Now we can safely import manifest submodules without kaizen/__init__.py
from kaizen.manifest.agent import AgentManifest  # noqa: E402
from kaizen.manifest.app import AppManifest  # noqa: E402
from kaizen.manifest.errors import (  # noqa: E402
    ManifestError,
    ManifestParseError,
    ManifestValidationError,
)
from kaizen.manifest.governance import GovernanceManifest  # noqa: E402
from kaizen.manifest.loader import load_app_manifest, load_manifest  # noqa: E402


# ---------------------------------------------------------------------------
# Sample TOML content for tests
# ---------------------------------------------------------------------------

FULL_AGENT_TOML = """\
[agent]
manifest_version = "1.0"
name = "doc-classifier"
module = "kaizen.agents.doc_classifier"
class_name = "DocClassifierAgent"
description = "Classifies documents by type and sensitivity"
capabilities = ["document-classification", "pii-detection"]
tools = ["file-reader", "regex-scanner"]
supported_models = ["gpt-4", "claude-3-opus"]

[governance]
purpose = "Classify inbound legal documents"
risk_level = "high"
data_access_needed = ["documents", "user_metadata"]
suggested_posture = "supervised"
max_budget_microdollars = 5000000
"""

MINIMAL_AGENT_TOML = """\
[agent]
name = "simple-bot"
module = "kaizen.agents.simple"
class_name = "SimpleBot"
"""

FULL_APP_TOML = """\
[application]
name = "contract-review-tool"
description = "Contract review pipeline"
owner = "alex@example.com"
org_unit = "legal-ops"
duration = "6 months"
justification = "Automate contract review for legal team"

[application.agents_requested]
agents = ["doc-classifier", "pii-redactor"]

[application.budget]
monthly = 500
"""


# ---------------------------------------------------------------------------
# Test 1: AgentManifest from full TOML string
# ---------------------------------------------------------------------------
class TestAgentManifestFromValidTomlStr:
    def test_parses_all_fields(self):
        manifest = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        assert manifest.name == "doc-classifier"
        assert manifest.module == "kaizen.agents.doc_classifier"
        assert manifest.class_name == "DocClassifierAgent"
        assert manifest.description == "Classifies documents by type and sensitivity"
        assert manifest.manifest_version == "1.0"
        assert manifest.capabilities == ["document-classification", "pii-detection"]
        assert manifest.tools == ["file-reader", "regex-scanner"]
        assert manifest.supported_models == ["gpt-4", "claude-3-opus"]

    def test_parses_governance_section(self):
        manifest = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        assert manifest.governance is not None
        assert manifest.governance.purpose == "Classify inbound legal documents"
        assert manifest.governance.risk_level == "high"
        assert manifest.governance.data_access_needed == ["documents", "user_metadata"]
        assert manifest.governance.suggested_posture == "supervised"
        assert manifest.governance.max_budget_microdollars == 5000000


# ---------------------------------------------------------------------------
# Test 2: AgentManifest minimal — only required fields
# ---------------------------------------------------------------------------
class TestAgentManifestMinimal:
    def test_minimal_required_fields(self):
        manifest = AgentManifest.from_toml_str(MINIMAL_AGENT_TOML)
        assert manifest.name == "simple-bot"
        assert manifest.module == "kaizen.agents.simple"
        assert manifest.class_name == "SimpleBot"
        assert manifest.manifest_version == "1.0"  # default
        assert manifest.capabilities == []
        assert manifest.tools == []
        assert manifest.supported_models == []
        assert manifest.governance is None


# ---------------------------------------------------------------------------
# Test 3: AgentManifest rejects missing name
# ---------------------------------------------------------------------------
class TestAgentManifestRejectsMissingName:
    def test_empty_name_raises(self):
        with pytest.raises(ManifestValidationError, match="name"):
            AgentManifest(
                name="",
                module="kaizen.agents.x",
                class_name="X",
            )

    def test_no_name_in_toml_raises(self):
        toml_str = """\
[agent]
module = "kaizen.agents.x"
class_name = "X"
"""
        with pytest.raises(ManifestValidationError, match="name"):
            AgentManifest.from_toml_str(toml_str)


# ---------------------------------------------------------------------------
# Test 4: AgentManifest rejects unknown version
# ---------------------------------------------------------------------------
class TestAgentManifestRejectsUnknownVersion:
    def test_version_2_raises(self):
        with pytest.raises(ManifestValidationError, match="manifest_version"):
            AgentManifest(
                manifest_version="2.0",
                name="bot",
                module="kaizen.agents.bot",
                class_name="Bot",
            )

    def test_empty_version_raises(self):
        with pytest.raises(ManifestValidationError, match="manifest_version"):
            AgentManifest(
                manifest_version="",
                name="bot",
                module="kaizen.agents.bot",
                class_name="Bot",
            )


# ---------------------------------------------------------------------------
# Test 5: GovernanceManifest valid construction
# ---------------------------------------------------------------------------
class TestGovernanceManifestValid:
    def test_defaults(self):
        g = GovernanceManifest()
        assert g.risk_level == "medium"
        assert g.suggested_posture == "supervised"
        assert g.max_budget_microdollars is None

    def test_all_fields(self):
        g = GovernanceManifest(
            purpose="Review contracts",
            risk_level="critical",
            data_access_needed=["contracts"],
            suggested_posture="delegated",
            max_budget_microdollars=1_000_000,
        )
        assert g.purpose == "Review contracts"
        assert g.risk_level == "critical"
        assert g.suggested_posture == "delegated"


# ---------------------------------------------------------------------------
# Test 6: GovernanceManifest rejects invalid risk_level
# ---------------------------------------------------------------------------
class TestGovernanceManifestRejectsInvalidRiskLevel:
    def test_invalid_risk_level(self):
        with pytest.raises(ValueError, match="risk_level"):
            GovernanceManifest(risk_level="extreme")


# ---------------------------------------------------------------------------
# Test 7: GovernanceManifest rejects invalid posture
# ---------------------------------------------------------------------------
class TestGovernanceManifestRejectsInvalidPosture:
    def test_invalid_posture(self):
        with pytest.raises(ValueError, match="suggested_posture"):
            GovernanceManifest(suggested_posture="autonomous")


# ---------------------------------------------------------------------------
# Test 8: AppManifest from valid TOML string
# ---------------------------------------------------------------------------
class TestAppManifestFromValidTomlStr:
    def test_parses_all_fields(self):
        manifest = AppManifest.from_toml_str(FULL_APP_TOML)
        assert manifest.name == "contract-review-tool"
        assert manifest.description == "Contract review pipeline"
        assert manifest.owner == "alex@example.com"
        assert manifest.org_unit == "legal-ops"
        assert manifest.duration == "6 months"
        assert manifest.agents_requested == ["doc-classifier", "pii-redactor"]
        assert manifest.justification == "Automate contract review for legal team"


# ---------------------------------------------------------------------------
# Test 9: AppManifest budget conversion (float -> microdollars)
# ---------------------------------------------------------------------------
class TestAppManifestBudgetConversion:
    def test_budget_float_to_microdollars(self):
        manifest = AppManifest.from_toml_str(FULL_APP_TOML)
        assert manifest.budget_monthly_microdollars == 500_000_000

    def test_budget_decimal_precision(self):
        toml_str = """\
[application]
name = "precision-test"
owner = "bob@example.com"

[application.budget]
monthly = 0.01
"""
        manifest = AppManifest.from_toml_str(toml_str)
        assert manifest.budget_monthly_microdollars == 10_000

    def test_no_budget_section(self):
        toml_str = """\
[application]
name = "no-budget"
owner = "bob@example.com"
"""
        manifest = AppManifest.from_toml_str(toml_str)
        assert manifest.budget_monthly_microdollars is None


# ---------------------------------------------------------------------------
# Test 10: to_dict / from_dict roundtrip — Agent
# ---------------------------------------------------------------------------
class TestToDictFromDictRoundtripAgent:
    def test_roundtrip(self):
        original = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        d = original.to_dict()
        restored = AgentManifest.from_dict(d)
        assert restored.name == original.name
        assert restored.module == original.module
        assert restored.class_name == original.class_name
        assert restored.capabilities == original.capabilities
        assert restored.tools == original.tools
        assert restored.supported_models == original.supported_models
        assert restored.manifest_version == original.manifest_version
        assert restored.governance is not None
        assert restored.governance.risk_level == original.governance.risk_level
        assert restored.governance.purpose == original.governance.purpose


# ---------------------------------------------------------------------------
# Test 11: to_dict / from_dict roundtrip — App
# ---------------------------------------------------------------------------
class TestToDictFromDictRoundtripApp:
    def test_roundtrip(self):
        original = AppManifest.from_toml_str(FULL_APP_TOML)
        d = original.to_dict()
        restored = AppManifest.from_dict(d)
        assert restored.name == original.name
        assert restored.owner == original.owner
        assert restored.agents_requested == original.agents_requested
        assert (
            restored.budget_monthly_microdollars == original.budget_monthly_microdollars
        )
        assert restored.justification == original.justification


# ---------------------------------------------------------------------------
# Test 12: to_toml / from_toml_str roundtrip — Agent
# ---------------------------------------------------------------------------
class TestToTomlFromTomlStrRoundtrip:
    def test_roundtrip(self):
        original = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        toml_output = original.to_toml()
        restored = AgentManifest.from_toml_str(toml_output)
        assert restored.name == original.name
        assert restored.module == original.module
        assert restored.class_name == original.class_name
        assert restored.capabilities == original.capabilities
        assert restored.tools == original.tools
        assert restored.supported_models == original.supported_models
        assert restored.manifest_version == original.manifest_version

    def test_roundtrip_with_governance(self):
        original = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        toml_output = original.to_toml()
        restored = AgentManifest.from_toml_str(toml_output)
        assert restored.governance is not None
        assert restored.governance.risk_level == original.governance.risk_level
        assert restored.governance.purpose == original.governance.purpose
        assert (
            restored.governance.max_budget_microdollars
            == original.governance.max_budget_microdollars
        )


# ---------------------------------------------------------------------------
# Test 13: to_agent_card — A2A compatible format
# ---------------------------------------------------------------------------
class TestToAgentCard:
    def test_agent_card_format(self):
        manifest = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        card = manifest.to_agent_card()
        assert card["name"] == "doc-classifier"
        assert card["description"] == "Classifies documents by type and sensitivity"
        assert "capabilities" in card
        assert "document-classification" in card["capabilities"]
        assert "pii-detection" in card["capabilities"]
        assert card["version"] == "1.0"

    def test_agent_card_has_governance(self):
        manifest = AgentManifest.from_toml_str(FULL_AGENT_TOML)
        card = manifest.to_agent_card()
        assert "governance" in card
        assert card["governance"]["risk_level"] == "high"
        assert card["governance"]["suggested_posture"] == "supervised"


# ---------------------------------------------------------------------------
# Test 14: malformed TOML raises ManifestParseError
# ---------------------------------------------------------------------------
class TestMalformedTomlRaisesParseError:
    def test_invalid_toml_syntax(self):
        bad_toml = "this is [not valid toml"
        with pytest.raises(ManifestParseError):
            AgentManifest.from_toml_str(bad_toml)


# ---------------------------------------------------------------------------
# Test 15: empty string TOML raises ManifestParseError
# ---------------------------------------------------------------------------
class TestEmptyStringTomlRaisesParseError:
    def test_empty_string(self):
        with pytest.raises((ManifestParseError, ManifestValidationError)):
            AgentManifest.from_toml_str("")

    def test_whitespace_only(self):
        with pytest.raises((ManifestParseError, ManifestValidationError)):
            AgentManifest.from_toml_str("   \n\n  ")


# ---------------------------------------------------------------------------
# Test 16: load_manifest rejects non-.toml files
# ---------------------------------------------------------------------------
class TestLoadManifestRejectsNonToml:
    def test_json_rejected(self):
        with pytest.raises(ManifestParseError, match=".toml"):
            load_manifest("/tmp/agent.json")

    def test_yaml_rejected(self):
        with pytest.raises(ManifestParseError, match=".toml"):
            load_manifest("/tmp/agent.yaml")

    def test_app_json_rejected(self):
        with pytest.raises(ManifestParseError, match=".toml"):
            load_app_manifest("/tmp/app.json")


# ---------------------------------------------------------------------------
# Test 17: from_introspection — create manifest from introspection dict
# ---------------------------------------------------------------------------
class TestFromIntrospection:
    def test_basic_introspection(self):
        info = {
            "name": "introspected-agent",
            "module": "kaizen.agents.introspected",
            "class_name": "IntrospectedAgent",
            "description": "Auto-discovered agent",
            "capabilities": ["text-generation"],
            "tools": ["search"],
            "supported_models": ["gpt-4"],
        }
        manifest = AgentManifest.from_introspection(info)
        assert manifest.name == "introspected-agent"
        assert manifest.module == "kaizen.agents.introspected"
        assert manifest.class_name == "IntrospectedAgent"
        assert manifest.description == "Auto-discovered agent"
        assert manifest.capabilities == ["text-generation"]
        assert manifest.tools == ["search"]

    def test_introspection_missing_required_raises(self):
        info = {"description": "no name or module"}
        with pytest.raises(ManifestValidationError, match="name"):
            AgentManifest.from_introspection(info)


# ---------------------------------------------------------------------------
# Test: AgentManifest from_toml with file path (using tmp_path)
# ---------------------------------------------------------------------------
class TestAgentManifestFromTomlFile:
    def test_from_toml_file(self, tmp_path):
        toml_file = tmp_path / "agent.toml"
        toml_file.write_text(FULL_AGENT_TOML)
        manifest = AgentManifest.from_toml(str(toml_file))
        assert manifest.name == "doc-classifier"
        assert manifest.governance is not None

    def test_nonexistent_file_raises(self):
        with pytest.raises(ManifestParseError):
            AgentManifest.from_toml("/nonexistent/path/agent.toml")


# ---------------------------------------------------------------------------
# Test: AppManifest from_toml with file path (using tmp_path)
# ---------------------------------------------------------------------------
class TestAppManifestFromTomlFile:
    def test_from_toml_file(self, tmp_path):
        toml_file = tmp_path / "app.toml"
        toml_file.write_text(FULL_APP_TOML)
        manifest = AppManifest.from_toml(str(toml_file))
        assert manifest.name == "contract-review-tool"
        assert manifest.budget_monthly_microdollars == 500_000_000

    def test_nonexistent_file_raises(self):
        with pytest.raises(ManifestParseError):
            AppManifest.from_toml("/nonexistent/path/app.toml")


# ---------------------------------------------------------------------------
# Test: load_manifest and load_app_manifest with real files
# ---------------------------------------------------------------------------
class TestLoaderWithRealFiles:
    def test_load_manifest(self, tmp_path):
        toml_file = tmp_path / "agent.toml"
        toml_file.write_text(FULL_AGENT_TOML)
        manifest = load_manifest(str(toml_file))
        assert manifest.name == "doc-classifier"

    def test_load_app_manifest(self, tmp_path):
        toml_file = tmp_path / "app.toml"
        toml_file.write_text(FULL_APP_TOML)
        manifest = load_app_manifest(str(toml_file))
        assert manifest.name == "contract-review-tool"


# ---------------------------------------------------------------------------
# Test: GovernanceManifest rejects negative budget
# ---------------------------------------------------------------------------
class TestGovernanceManifestRejectsNegativeBudget:
    def test_negative_budget(self):
        with pytest.raises(ValueError, match="max_budget_microdollars"):
            GovernanceManifest(max_budget_microdollars=-100)


# ---------------------------------------------------------------------------
# Test: AgentManifest rejects missing module and class_name
# ---------------------------------------------------------------------------
class TestAgentManifestRejectsMissingModuleAndClass:
    def test_empty_module_raises(self):
        with pytest.raises(ManifestValidationError, match="module"):
            AgentManifest(name="bot", module="", class_name="Bot")

    def test_empty_class_name_raises(self):
        with pytest.raises(ManifestValidationError, match="class_name"):
            AgentManifest(name="bot", module="kaizen.agents.bot", class_name="")


# ---------------------------------------------------------------------------
# Test: Error hierarchy
# ---------------------------------------------------------------------------
class TestErrorHierarchy:
    def test_parse_error_is_manifest_error(self):
        assert issubclass(ManifestParseError, ManifestError)

    def test_validation_error_is_manifest_error(self):
        assert issubclass(ManifestValidationError, ManifestError)

    def test_manifest_error_has_details(self):
        err = ManifestError("test", details={"key": "val"})
        assert err.details == {"key": "val"}

    def test_manifest_error_default_details(self):
        err = ManifestError("test")
        assert err.details == {}

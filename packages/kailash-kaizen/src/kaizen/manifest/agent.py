from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AgentManifest — declarative agent identity and capabilities.

Parsed from ``[agent]`` + ``[governance]`` sections of a TOML manifest
file.  Supports round-trip serialization (``to_toml`` / ``from_toml_str``)
and conversion to the A2A Agent Card format (``to_agent_card``).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.manifest._coerce import coerce_list_field, safe_repr
from kaizen.manifest.errors import ManifestParseError, ManifestValidationError
from kaizen.manifest.governance import GovernanceManifest

logger = logging.getLogger(__name__)

__all__ = ["AgentManifest"]

_SUPPORTED_VERSIONS = frozenset({"1.0"})


def _escape_toml_string(s: str) -> str:
    """Escape special characters for TOML basic string values.

    Escapes the standard TOML basic-string escapes (backslash, double
    quote, newline, carriage return, tab) plus every remaining C0 control
    byte (``\\x00``-``\\x1f``) not already covered by one of those, using
    TOML's ``\\uXXXX`` escape form.  Without this, a control byte embedded
    in a name/description/list item (e.g. from untrusted introspection
    data) would be written into the TOML output unescaped, producing a
    file that either fails to round-trip through ``from_toml_str`` or —
    worse — is misparsed by a downstream TOML consumer.
    """
    result = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    escaped_chars = []
    for ch in result:
        codepoint = ord(ch)
        if codepoint < 0x20 and ch not in ("\n", "\r", "\t"):
            escaped_chars.append(f"\\u{codepoint:04x}")
        else:
            escaped_chars.append(ch)
    return "".join(escaped_chars)


def _load_tomllib():
    """Return the tomllib module (stdlib 3.11+ or tomli fallback)."""
    try:
        import tomllib

        return tomllib
    except ModuleNotFoundError:
        pass
    try:
        import tomli as tomllib  # type: ignore[no-redef]

        return tomllib
    except ModuleNotFoundError:
        raise ImportError(
            "TOML parsing requires Python 3.11+ (tomllib) or the 'tomli' "
            "package.  Install with: pip install tomli"
        )


@dataclass
class AgentManifest:
    """Declarative manifest for a Kaizen agent.

    Attributes:
        manifest_version: Schema version — must be ``"1.0"`` (RT-12).
        name: Unique agent identifier (required, non-empty).
        module: Python module path (required, non-empty).
        class_name: Agent class name inside *module* (required, non-empty).
        description: Human-readable summary.
        capabilities: List of capability tags (e.g. ``["pii-detection"]``).
        tools: Tool identifiers the agent may invoke.
        supported_models: LLM model identifiers the agent can work with.
        governance: Optional governance constraints.
    """

    name: str = ""
    module: str = ""
    class_name: str = ""
    manifest_version: str = "1.0"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    supported_models: List[str] = field(default_factory=list)
    governance: Optional[GovernanceManifest] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        errors: Dict[str, str] = {}
        if not self.name or not self.name.strip():
            errors["name"] = "name must be a non-empty string"
        if not self.module or not self.module.strip():
            errors["module"] = "module must be a non-empty string"
        if not self.class_name or not self.class_name.strip():
            errors["class_name"] = "class_name must be a non-empty string"
        if self.manifest_version not in _SUPPORTED_VERSIONS:
            errors["manifest_version"] = (
                f"manifest_version must be one of {sorted(_SUPPORTED_VERSIONS)}, "
                f"got {safe_repr(self.manifest_version)}"
            )
        if errors:
            # Use the first error key for the message so pytest.raises(match=...)
            # can locate the relevant field name.
            first_key = next(iter(errors))
            raise ManifestValidationError(
                f"AgentManifest validation failed: {errors[first_key]}",
                details=errors,
            )

    # ------------------------------------------------------------------
    # Dict serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        result: Dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "name": self.name,
            "module": self.module,
            "class_name": self.class_name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "supported_models": list(self.supported_models),
        }
        if self.governance is not None:
            result["governance"] = self.governance.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentManifest:
        """Deserialize from a plain dict (inverse of ``to_dict``)."""
        governance = None
        if "governance" in data and data["governance"] is not None:
            governance = GovernanceManifest.from_dict(data["governance"])
        return cls(
            manifest_version=data.get("manifest_version", "1.0"),
            name=data.get("name", ""),
            module=data.get("module", ""),
            class_name=data.get("class_name", ""),
            description=data.get("description", ""),
            capabilities=coerce_list_field(
                data.get("capabilities", []), "capabilities"
            ),
            tools=coerce_list_field(data.get("tools", []), "tools"),
            supported_models=coerce_list_field(
                data.get("supported_models", []), "supported_models"
            ),
            governance=governance,
        )

    # ------------------------------------------------------------------
    # TOML serialization
    # ------------------------------------------------------------------
    def to_toml(self) -> str:
        """Serialize to a TOML string (hand-formatted, no toml library needed)."""
        lines: List[str] = ["[agent]"]
        lines.append(
            f'manifest_version = "{_escape_toml_string(self.manifest_version)}"'
        )
        lines.append(f'name = "{_escape_toml_string(self.name)}"')
        lines.append(f'module = "{_escape_toml_string(self.module)}"')
        lines.append(f'class_name = "{_escape_toml_string(self.class_name)}"')
        if self.description:
            lines.append(f'description = "{_escape_toml_string(self.description)}"')
        if self.capabilities:
            cap_items = ", ".join(
                f'"{_escape_toml_string(c)}"' for c in self.capabilities
            )
            lines.append(f"capabilities = [{cap_items}]")
        if self.tools:
            tool_items = ", ".join(f'"{_escape_toml_string(t)}"' for t in self.tools)
            lines.append(f"tools = [{tool_items}]")
        if self.supported_models:
            model_items = ", ".join(
                f'"{_escape_toml_string(m)}"' for m in self.supported_models
            )
            lines.append(f"supported_models = [{model_items}]")

        if self.governance is not None:
            lines.append("")
            lines.append("[governance]")
            g = self.governance
            lines.append(f'purpose = "{_escape_toml_string(g.purpose)}"')
            lines.append(f'risk_level = "{_escape_toml_string(g.risk_level)}"')
            if g.data_access_needed:
                da_items = ", ".join(
                    f'"{_escape_toml_string(d)}"' for d in g.data_access_needed
                )
                lines.append(f"data_access_needed = [{da_items}]")
            else:
                lines.append("data_access_needed = []")
            lines.append(
                f'suggested_posture = "{_escape_toml_string(g.suggested_posture)}"'
            )
            if g.max_budget_microdollars is not None:
                lines.append(f"max_budget_microdollars = {g.max_budget_microdollars}")

        lines.append("")  # trailing newline
        return "\n".join(lines)

    @classmethod
    def from_toml(cls, path: str) -> AgentManifest:
        """Parse an AgentManifest from a TOML file on disk.

        Raises:
            ManifestParseError: If the file cannot be read or parsed.
        """
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except FileNotFoundError as exc:
            raise ManifestParseError(
                f"Manifest file not found: {path}",
                details={"path": path},
            ) from exc
        except OSError as exc:
            raise ManifestParseError(
                f"Cannot read manifest file: {path}: {exc}",
                details={"path": path},
            ) from exc

        return cls._parse_toml_bytes(raw, source=path)

    @classmethod
    def from_toml_str(cls, content: str) -> AgentManifest:
        """Parse an AgentManifest from an in-memory TOML string.

        Raises:
            ManifestParseError: If the string is not valid TOML.
            ManifestValidationError: If required fields are missing.
        """
        return cls._parse_toml_bytes(content.encode("utf-8"), source="<string>")

    @classmethod
    def _parse_toml_bytes(cls, raw: bytes, *, source: str = "<bytes>") -> AgentManifest:
        """Internal: parse raw TOML bytes into an AgentManifest."""
        tomllib = _load_tomllib()
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ManifestParseError(
                f"Invalid TOML in {source}: {exc}",
                details={"source": source},
            ) from exc

        agent_section = data.get("agent", {})
        if not agent_section:
            # No [agent] section — try top-level for very minimal files,
            # but normally we require it.  Raise clear error.
            raise ManifestValidationError(
                f"Missing [agent] section in manifest ({source})",
                details={"source": source, "name": ""},
            )
        if not isinstance(agent_section, dict):
            # A legal-but-wrong array-of-tables declaration (``[[agent]]``)
            # parses [agent] to a list, not a dict.  Without this guard,
            # ``agent_section.get(...)`` below raises a raw AttributeError
            # instead of the documented ManifestParseError.
            raise ManifestParseError(
                f"Invalid [agent] section in manifest ({source}): expected a "
                f"table (did you use [[agent]] — array of tables — instead of "
                f"[agent]?), got {type(agent_section).__name__}",
                details={"source": source},
            )

        governance = None
        gov_data = data.get("governance", agent_section.get("governance"))
        if gov_data and isinstance(gov_data, dict):
            governance = GovernanceManifest.from_dict(gov_data)

        return cls(
            manifest_version=str(agent_section.get("manifest_version", "1.0")),
            name=agent_section.get("name", ""),
            module=agent_section.get("module", ""),
            class_name=agent_section.get("class_name", agent_section.get("class", "")),
            description=agent_section.get("description", ""),
            capabilities=coerce_list_field(
                agent_section.get("capabilities", []), "capabilities"
            ),
            tools=coerce_list_field(agent_section.get("tools", []), "tools"),
            supported_models=coerce_list_field(
                agent_section.get("supported_models", []), "supported_models"
            ),
            governance=governance,
        )

    # ------------------------------------------------------------------
    # A2A Agent Card
    # ------------------------------------------------------------------
    def to_agent_card(self) -> Dict[str, Any]:
        """Convert this manifest to an A2A-compatible Agent Card dict.

        The returned dict follows the A2A Agent Card structure with
        optional governance extensions.
        """
        card: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "version": self.manifest_version,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "supported_models": list(self.supported_models),
            "protocols": ["a2a/1.0", "kaizen-manifest/1.0"],
            "module": self.module,
            "class_name": self.class_name,
        }
        if self.governance is not None:
            card["governance"] = self.governance.to_dict()
        return card

    # ------------------------------------------------------------------
    # Introspection factory
    # ------------------------------------------------------------------
    @classmethod
    def from_introspection(cls, info: Dict[str, Any]) -> AgentManifest:
        """Create an AgentManifest from a runtime introspection dict.

        The *info* dict is expected to contain at minimum ``name``,
        ``module``, and ``class_name``.

        Raises:
            ManifestValidationError: If required keys are missing.
        """
        governance = None
        if "governance" in info and isinstance(info["governance"], dict):
            governance = GovernanceManifest.from_dict(info["governance"])

        return cls(
            name=info.get("name", ""),
            module=info.get("module", ""),
            class_name=info.get("class_name", ""),
            description=info.get("description", ""),
            capabilities=coerce_list_field(
                info.get("capabilities", []), "capabilities"
            ),
            tools=coerce_list_field(info.get("tools", []), "tools"),
            supported_models=coerce_list_field(
                info.get("supported_models", []), "supported_models"
            ),
            governance=governance,
        )

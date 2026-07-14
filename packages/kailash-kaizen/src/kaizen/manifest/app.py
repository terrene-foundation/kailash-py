from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AppManifest — application-level manifest for multi-agent deployments.

Parsed from ``[application]`` sections of a TOML manifest file.
Budget values in TOML are expressed as floats (dollars) and converted
to integer microdollars (1 dollar = 1,000,000 microdollars) using
``Decimal`` for precision.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from kaizen.manifest._coerce import coerce_list_field
from kaizen.manifest.errors import ManifestParseError, ManifestValidationError

logger = logging.getLogger(__name__)

__all__ = ["AppManifest"]


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
class AppManifest:
    """Application manifest declaring agents requested and budget.

    Attributes:
        name: Application identifier (required, non-empty).
        description: Human-readable summary.
        owner: Contact email or identifier for the application owner.
        org_unit: Organizational unit (optional).
        duration: Requested deployment duration (optional, e.g. "6 months").
        agents_requested: Agent identifiers this application needs.
        budget_monthly_microdollars: Monthly budget in microdollars (optional).
        justification: Why these agents are needed.
    """

    name: str = ""
    description: str = ""
    owner: str = ""
    org_unit: Optional[str] = None
    duration: Optional[str] = None
    agents_requested: List[str] = field(default_factory=list)
    budget_monthly_microdollars: Optional[int] = None
    justification: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ManifestValidationError(
                "AppManifest validation failed: name must be a non-empty string",
                details={"name": "name must be a non-empty string"},
            )

    # ------------------------------------------------------------------
    # Dict serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        result: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "agents_requested": list(self.agents_requested),
            "justification": self.justification,
        }
        if self.org_unit is not None:
            result["org_unit"] = self.org_unit
        if self.duration is not None:
            result["duration"] = self.duration
        if self.budget_monthly_microdollars is not None:
            result["budget_monthly_microdollars"] = self.budget_monthly_microdollars
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppManifest:
        """Deserialize from a plain dict (inverse of ``to_dict``)."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            owner=data.get("owner", ""),
            org_unit=data.get("org_unit"),
            duration=data.get("duration"),
            agents_requested=coerce_list_field(
                data.get("agents_requested", []), "agents_requested"
            ),
            budget_monthly_microdollars=data.get("budget_monthly_microdollars"),
            justification=data.get("justification", ""),
        )

    # ------------------------------------------------------------------
    # TOML parsing
    # ------------------------------------------------------------------
    @classmethod
    def from_toml(cls, path: str) -> AppManifest:
        """Parse an AppManifest from a TOML file on disk.

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
    def from_toml_str(cls, content: str) -> AppManifest:
        """Parse an AppManifest from an in-memory TOML string.

        Raises:
            ManifestParseError: If the string is not valid TOML.
            ManifestValidationError: If required fields are missing.
        """
        return cls._parse_toml_bytes(content.encode("utf-8"), source="<string>")

    @classmethod
    def _parse_toml_bytes(cls, raw: bytes, *, source: str = "<bytes>") -> AppManifest:
        """Internal: parse raw TOML bytes into an AppManifest."""
        tomllib = _load_tomllib()
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ManifestParseError(
                f"Invalid TOML in {source}: {exc}",
                details={"source": source},
            ) from exc

        app_section = data.get("application", {})
        if not app_section:
            raise ManifestValidationError(
                f"Missing [application] section in manifest ({source})",
                details={"source": source, "name": ""},
            )
        if not isinstance(app_section, dict):
            # A legal-but-wrong array-of-tables declaration
            # (``[[application]]``) parses [application] to a list, not a
            # dict.  Without this guard, ``app_section.get(...)`` below
            # raises a raw AttributeError instead of the documented
            # ManifestParseError.
            raise ManifestParseError(
                f"Invalid [application] section in manifest ({source}): "
                f"expected a table (did you use [[application]] — array of "
                f"tables — instead of [application]?), got "
                f"{type(app_section).__name__}",
                details={"source": source},
            )

        # Extract agents_requested from nested section
        agents_req_section = app_section.get("agents_requested", {})
        agents_requested: List[str] = []
        if isinstance(agents_req_section, dict):
            agents_requested = coerce_list_field(
                agents_req_section.get("agents", []), "agents_requested"
            )
        elif isinstance(agents_req_section, list):
            agents_requested = list(agents_req_section)

        # Extract justification — may live in agents_requested subsection or top-level
        justification = ""
        if (
            isinstance(agents_req_section, dict)
            and "justification" in agents_req_section
        ):
            justification = str(agents_req_section["justification"])
        elif "justification" in app_section:
            justification = str(app_section["justification"])

        # Budget: convert float dollars -> integer microdollars
        budget_monthly_microdollars: Optional[int] = None
        budget_section = app_section.get("budget", {})
        if isinstance(budget_section, dict) and "monthly" in budget_section:
            monthly_raw = budget_section["monthly"]
            try:
                budget_monthly_microdollars = int(Decimal(str(monthly_raw)) * 1_000_000)
            except (InvalidOperation, ValueError) as exc:
                raise ManifestValidationError(
                    f"Invalid [application.budget].monthly value in manifest "
                    f"({source}): expected a number, got {monthly_raw!r}",
                    details={"source": source, "monthly": repr(monthly_raw)},
                ) from exc

        return cls(
            name=app_section.get("name", ""),
            description=app_section.get("description", ""),
            owner=app_section.get("owner", ""),
            org_unit=app_section.get("org_unit"),
            duration=app_section.get("duration"),
            agents_requested=agents_requested,
            budget_monthly_microdollars=budget_monthly_microdollars,
            justification=justification,
        )

# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""YAML organization definition loader -- parses unified YAML into PACT structures.

Loads a unified YAML org definition and returns all the components needed
to construct a GovernanceEngine: org definition (departments, teams, roles),
clearances, envelopes, bridges, and KSPs.

The YAML format is designed for human authoring -- it uses short keys
(``heads`` instead of ``is_primary_for_unit``, ``reports_to`` instead of
``reports_to_role_id``) and groups all governance config in a single file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.compilation import RoleDefinition

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigurationError",
    "ClearanceSpec",
    "EnvelopeSpec",
    "BridgeSpec",
    "KspSpec",
    "LoadedOrg",
    "load_org_yaml",
]

# Valid clearance level strings
_VALID_CLEARANCE_LEVELS = frozenset(
    {"public", "restricted", "confidential", "secret", "top_secret"}
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigurationError(Exception):
    """Raised when a YAML org definition is invalid or has broken references."""

    pass


# ---------------------------------------------------------------------------
# Intermediate spec dataclasses (returned to caller for engine construction)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClearanceSpec:
    """A clearance specification from the YAML file.

    Contains the raw role ID and clearance parameters before address
    resolution (which happens at GovernanceEngine construction time).
    """

    role_id: str
    level: str  # e.g. "confidential", "secret"
    compartments: list[str] = field(default_factory=list)
    nda_signed: bool = False


@dataclass(frozen=True)
class EnvelopeSpec:
    """An envelope specification from the YAML file.

    Contains raw role IDs and constraint parameters before address
    resolution.
    """

    target: str  # role_id of the target role
    defined_by: str  # role_id of the defining (supervisor) role
    financial: dict[str, Any] | None = None
    operational: dict[str, Any] | None = None
    temporal: dict[str, Any] | None = None
    data_access: dict[str, Any] | None = None
    communication: dict[str, Any] | None = None


@dataclass(frozen=True)
class BridgeSpec:
    """A bridge specification from the YAML file."""

    id: str
    role_a: str  # role_id
    role_b: str  # role_id
    bridge_type: str  # "standing", "scoped", "ad_hoc"
    max_classification: str  # e.g. "confidential"
    bilateral: bool = True


@dataclass(frozen=True)
class KspSpec:
    """A Knowledge Share Policy specification from the YAML file."""

    id: str
    source: str  # department/team ID
    target: str  # department/team ID
    max_classification: str  # e.g. "restricted"


@dataclass(frozen=True)
class LoadedOrg:
    """Result of loading a YAML org definition.

    Contains the OrgDefinition (ready for compilation) plus all governance
    specifications (clearances, envelopes, bridges, KSPs) that need to be
    applied after compilation resolves positional addresses.
    """

    org_definition: OrgDefinition
    clearances: list[ClearanceSpec] = field(default_factory=list)
    envelopes: list[EnvelopeSpec] = field(default_factory=list)
    bridges: list[BridgeSpec] = field(default_factory=list)
    ksps: list[KspSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_org_yaml(path: str | Path) -> LoadedOrg:
    """Load a unified YAML org definition.

    The YAML format supports:
    - ``org_id``, ``name`` (required)
    - ``departments`` (list of ``{id, name}``)
    - ``teams`` (list of ``{id, name}``)
    - ``roles`` (list of ``{id, name, reports_to?, heads?, agent?}``)
    - ``clearances`` (list of ``{role, level, compartments?, nda_signed?}``)
    - ``envelopes`` (list of ``{target, defined_by, financial?, operational?, ...}``)
    - ``bridges`` (list of ``{id, role_a, role_b, type, max_classification, bilateral?}``)
    - ``ksps`` (list of ``{id, source, target, max_classification}``)

    Args:
        path: Path to the YAML file.

    Returns:
        A LoadedOrg containing the OrgDefinition and all governance specs.

    Raises:
        ConfigurationError: If the YAML is invalid, required fields are
            missing, or references are broken.
    """
    path = Path(path)

    # --- Read and parse YAML ---
    if not path.exists():
        raise ConfigurationError(
            f"YAML org definition file not found: '{path}'. "
            f"Ensure the file exists and the path is correct."
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            f"Failed to read YAML org definition from '{path}': {exc}"
        ) from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Failed to parse YAML from '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"YAML org definition must be a mapping (dict), got {type(data).__name__}. "
            f"Ensure the file is not empty and starts with key-value pairs."
        )

    # --- Validate required top-level fields ---
    _require_field(data, "org_id", path)
    _require_field(data, "name", path)

    org_id: str = data["org_id"]
    name: str = data["name"]

    # --- Parse departments ---
    raw_depts = data.get("departments", [])
    if not isinstance(raw_depts, list):
        raise ConfigurationError(
            f"'departments' must be a list, got {type(raw_depts).__name__} in '{path}'"
        )
    departments = _parse_departments(raw_depts, path)

    # --- Parse teams ---
    raw_teams = data.get("teams", [])
    if not isinstance(raw_teams, list):
        raise ConfigurationError(
            f"'teams' must be a list, got {type(raw_teams).__name__} in '{path}'"
        )
    teams = _parse_teams(raw_teams, path)

    # --- Build lookup indexes for reference validation ---
    dept_ids = {d.department_id for d in departments}
    team_ids = {t.id for t in teams}
    all_unit_ids = dept_ids | team_ids

    # --- Parse roles ---
    raw_roles = data.get("roles", [])
    if not isinstance(raw_roles, list):
        raise ConfigurationError(
            f"'roles' must be a list, got {type(raw_roles).__name__} in '{path}'"
        )
    roles = _parse_roles(raw_roles, all_unit_ids, path)

    # --- Validate role references ---
    role_ids = {r.role_id for r in roles}
    _validate_role_references(roles, role_ids, path)

    # --- Parse clearances ---
    raw_clearances = data.get("clearances", [])
    if not isinstance(raw_clearances, list):
        raise ConfigurationError(
            f"'clearances' must be a list, got {type(raw_clearances).__name__} in '{path}'"
        )
    clearances = _parse_clearances(raw_clearances, role_ids, path)

    # --- Parse envelopes ---
    raw_envelopes = data.get("envelopes", [])
    if not isinstance(raw_envelopes, list):
        raise ConfigurationError(
            f"'envelopes' must be a list, got {type(raw_envelopes).__name__} in '{path}'"
        )
    envelopes = _parse_envelopes(raw_envelopes, role_ids, path)

    # --- Parse bridges ---
    raw_bridges = data.get("bridges", [])
    if not isinstance(raw_bridges, list):
        raise ConfigurationError(
            f"'bridges' must be a list, got {type(raw_bridges).__name__} in '{path}'"
        )
    bridges = _parse_bridges(raw_bridges, role_ids, path)

    # --- Parse KSPs ---
    raw_ksps = data.get("ksps", [])
    if not isinstance(raw_ksps, list):
        raise ConfigurationError(
            f"'ksps' must be a list, got {type(raw_ksps).__name__} in '{path}'"
        )
    ksps = _parse_ksps(raw_ksps, all_unit_ids, path)

    # --- Build OrgDefinition ---
    org_def = OrgDefinition(
        org_id=org_id,
        name=name,
        departments=departments,
        teams=teams,
        roles=roles,
    )

    logger.info(
        "Loaded YAML org definition '%s' from '%s': "
        "%d departments, %d teams, %d roles, "
        "%d clearances, %d envelopes, %d bridges, %d KSPs",
        org_id,
        path,
        len(departments),
        len(teams),
        len(roles),
        len(clearances),
        len(envelopes),
        len(bridges),
        len(ksps),
    )

    return LoadedOrg(
        org_definition=org_def,
        clearances=clearances,
        envelopes=envelopes,
        bridges=bridges,
        ksps=ksps,
    )


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------


def _require_field(data: dict[str, Any], field_name: str, path: Path) -> None:
    """Raise ConfigurationError if a required field is missing."""
    if field_name not in data:
        raise ConfigurationError(
            f"Required field '{field_name}' is missing from YAML org definition in '{path}'. "
            f"Available top-level keys: {sorted(data.keys())}"
        )


def _parse_departments(raw: list[Any], path: Path) -> list[DepartmentConfig]:
    """Parse department entries from YAML."""
    departments: list[DepartmentConfig] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Department entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )
        dept_id = entry.get("id")
        if not dept_id:
            raise ConfigurationError(
                f"Department entry {i} is missing required 'id' field in '{path}'"
            )
        dept_name = entry.get("name", dept_id)
        departments.append(DepartmentConfig(department_id=dept_id, name=dept_name))
    return departments


def _parse_teams(raw: list[Any], path: Path) -> list[TeamConfig]:
    """Parse team entries from YAML."""
    teams: list[TeamConfig] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Team entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )
        team_id = entry.get("id")
        if not team_id:
            raise ConfigurationError(f"Team entry {i} is missing required 'id' field in '{path}'")
        team_name = entry.get("name", team_id)
        # Use a placeholder workspace since YAML teams don't require one
        teams.append(TeamConfig(id=team_id, name=team_name, workspace=f"ws-{team_id}"))
    return teams


def _parse_roles(
    raw: list[Any],
    all_unit_ids: set[str],
    path: Path,
) -> list[RoleDefinition]:
    """Parse role entries from YAML into RoleDefinition objects."""
    roles: list[RoleDefinition] = []
    seen_ids: set[str] = set()

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Role entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )

        role_id = entry.get("id")
        if not role_id:
            raise ConfigurationError(f"Role entry {i} is missing required 'id' field in '{path}'")

        # Check for duplicate role IDs
        if role_id in seen_ids:
            raise ConfigurationError(
                f"Duplicate role ID '{role_id}' in YAML org definition at '{path}'. "
                f"Each role must have a unique ID."
            )
        seen_ids.add(role_id)

        role_name = entry.get("name", role_id)
        reports_to = entry.get("reports_to")
        heads = entry.get("heads")
        agent_id = entry.get("agent")

        # Validate heads reference
        if heads is not None and heads not in all_unit_ids:
            raise ConfigurationError(
                f"Role '{role_id}' references unit '{heads}' via 'heads' field, "
                f"but '{heads}' was not found in departments or teams. "
                f"Available units: {sorted(all_unit_ids)}. "
                f"In YAML file '{path}'."
            )

        roles.append(
            RoleDefinition(
                role_id=role_id,
                name=role_name,
                reports_to_role_id=reports_to,
                is_primary_for_unit=heads,
                agent_id=agent_id,
            )
        )

    return roles


def _validate_role_references(
    roles: list[RoleDefinition],
    role_ids: set[str],
    path: Path,
) -> None:
    """Validate that all role cross-references are valid."""
    for role in roles:
        if role.reports_to_role_id is not None and role.reports_to_role_id not in role_ids:
            raise ConfigurationError(
                f"Role '{role.role_id}' has reports_to='{role.reports_to_role_id}', "
                f"but '{role.reports_to_role_id}' was not found in the role definitions. "
                f"Available role IDs: {sorted(role_ids)}. "
                f"In YAML file '{path}'."
            )


def _parse_clearances(
    raw: list[Any],
    role_ids: set[str],
    path: Path,
) -> list[ClearanceSpec]:
    """Parse clearance entries from YAML."""
    clearances: list[ClearanceSpec] = []

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Clearance entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )

        role_id = entry.get("role")
        if not role_id:
            raise ConfigurationError(
                f"Clearance entry {i} is missing required 'role' field in '{path}'"
            )

        if role_id not in role_ids:
            raise ConfigurationError(
                f"Clearance entry {i} references role '{role_id}' which was not found "
                f"in the role definitions. Available role IDs: {sorted(role_ids)}. "
                f"In YAML file '{path}'."
            )

        level = entry.get("level")
        if not level:
            raise ConfigurationError(
                f"Clearance entry {i} for role '{role_id}' is missing required 'level' field "
                f"in '{path}'"
            )

        if level not in _VALID_CLEARANCE_LEVELS:
            raise ConfigurationError(
                f"Clearance entry {i} for role '{role_id}' has invalid level '{level}'. "
                f"Valid levels: {sorted(_VALID_CLEARANCE_LEVELS)}. "
                f"In YAML file '{path}'."
            )

        compartments = entry.get("compartments", [])
        if not isinstance(compartments, list):
            raise ConfigurationError(
                f"Clearance entry {i} for role '{role_id}': 'compartments' must be a list, "
                f"got {type(compartments).__name__}. In YAML file '{path}'."
            )

        nda_signed = entry.get("nda_signed", False)

        clearances.append(
            ClearanceSpec(
                role_id=role_id,
                level=level,
                compartments=compartments,
                nda_signed=bool(nda_signed),
            )
        )

    return clearances


def _parse_envelopes(
    raw: list[Any],
    role_ids: set[str],
    path: Path,
) -> list[EnvelopeSpec]:
    """Parse envelope entries from YAML."""
    envelopes: list[EnvelopeSpec] = []

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Envelope entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )

        target = entry.get("target")
        if not target:
            raise ConfigurationError(
                f"Envelope entry {i} is missing required 'target' field in '{path}'"
            )

        defined_by = entry.get("defined_by")
        if not defined_by:
            raise ConfigurationError(
                f"Envelope entry {i} is missing required 'defined_by' field in '{path}'"
            )

        envelopes.append(
            EnvelopeSpec(
                target=target,
                defined_by=defined_by,
                financial=entry.get("financial"),
                operational=entry.get("operational"),
                temporal=entry.get("temporal"),
                data_access=entry.get("data_access"),
                communication=entry.get("communication"),
            )
        )

    return envelopes


def _parse_bridges(
    raw: list[Any],
    role_ids: set[str],
    path: Path,
) -> list[BridgeSpec]:
    """Parse bridge entries from YAML."""
    bridges: list[BridgeSpec] = []

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Bridge entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )

        bridge_id = entry.get("id")
        if not bridge_id:
            raise ConfigurationError(f"Bridge entry {i} is missing required 'id' field in '{path}'")

        role_a = entry.get("role_a")
        role_b = entry.get("role_b")
        bridge_type = entry.get("type")
        max_classification = entry.get("max_classification")

        if not role_a:
            raise ConfigurationError(
                f"Bridge '{bridge_id}' is missing required 'role_a' field in '{path}'"
            )
        if not role_b:
            raise ConfigurationError(
                f"Bridge '{bridge_id}' is missing required 'role_b' field in '{path}'"
            )
        if not bridge_type:
            raise ConfigurationError(
                f"Bridge '{bridge_id}' is missing required 'type' field in '{path}'"
            )
        if not max_classification:
            raise ConfigurationError(
                f"Bridge '{bridge_id}' is missing required 'max_classification' field in '{path}'"
            )

        bilateral = entry.get("bilateral", True)

        bridges.append(
            BridgeSpec(
                id=bridge_id,
                role_a=role_a,
                role_b=role_b,
                bridge_type=bridge_type,
                max_classification=max_classification,
                bilateral=bool(bilateral),
            )
        )

    return bridges


def _parse_ksps(
    raw: list[Any],
    all_unit_ids: set[str],
    path: Path,
) -> list[KspSpec]:
    """Parse KSP entries from YAML."""
    ksps: list[KspSpec] = []

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"KSP entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )

        ksp_id = entry.get("id")
        if not ksp_id:
            raise ConfigurationError(f"KSP entry {i} is missing required 'id' field in '{path}'")

        source = entry.get("source")
        target = entry.get("target")
        max_classification = entry.get("max_classification")

        if not source:
            raise ConfigurationError(
                f"KSP '{ksp_id}' is missing required 'source' field in '{path}'"
            )
        if not target:
            raise ConfigurationError(
                f"KSP '{ksp_id}' is missing required 'target' field in '{path}'"
            )
        if not max_classification:
            raise ConfigurationError(
                f"KSP '{ksp_id}' is missing required 'max_classification' field in '{path}'"
            )

        ksps.append(
            KspSpec(
                id=ksp_id,
                source=source,
                target=target,
                max_classification=max_classification,
            )
        )

    return ksps

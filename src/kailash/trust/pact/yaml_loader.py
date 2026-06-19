# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
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

from kailash.trust.pact.compilation import RoleDefinition
from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigurationError",
    "ClearanceSpec",
    "EnvelopeSpec",
    "BridgeSpec",
    "KspSpec",
    "LoadedOrg",
    "load_org_yaml",
    "load_org_from_dict",
]

# Valid clearance level strings
_VALID_CLEARANCE_LEVELS = frozenset(
    {"public", "restricted", "confidential", "secret", "top_secret"}
)


def _is_valid_level(value: Any) -> bool:
    """True iff ``value`` is a string naming a valid clearance level.

    The ``isinstance`` guard short-circuits BEFORE the ``in`` membership test, so
    an unhashable YAML value (a list / dict at a clearance-level position) yields
    a fail-closed ``ConfigurationError`` at the call site rather than a raw
    ``TypeError: unhashable type``. All clearance-level validation in this loader
    routes through here so every level field fails closed with the same helpful
    message.
    """
    return isinstance(value, str) and value in _VALID_CLEARANCE_LEVELS


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigurationError(PactError):
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

    Beyond the five CARE dimension dicts, an envelope may carry two top-level
    governance fields that map directly onto
    :class:`~kailash.trust.pact.config.ConstraintEnvelopeConfig`. Both are
    carried VERBATIM and coerced/validated when the envelope is resolved
    (see :func:`kailash.trust.pact.yaml_resolvers.resolve_envelope`); omitting
    either leaves the runtime config default in place.

    Attributes:
        confidentiality_clearance: Raw clearance-level string (e.g.
            ``"restricted"``) capping the maximum data classification this
            envelope's agent may access; ``None`` leaves the config default
            (``PUBLIC``).
        max_delegation_depth: Positive integer capping how many levels deep
            trust may be delegated; ``None`` leaves the config default
            (``None`` = unlimited).
    """

    target: str  # role_id of the target role
    defined_by: str  # role_id of the defining (supervisor) role
    financial: dict[str, Any] | None = None
    operational: dict[str, Any] | None = None
    temporal: dict[str, Any] | None = None
    data_access: dict[str, Any] | None = None
    communication: dict[str, Any] | None = None
    gradient_thresholds: dict[str, Any] | None = None
    confidentiality_clearance: str | None = None
    max_delegation_depth: int | None = None


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
    """A Knowledge Share Policy specification from the YAML file.

    Beyond the source/target addressing and the ``max_classification``
    ceiling, a KSP may carry NARROWING scope filters that mirror the runtime
    :class:`~kailash.trust.pact.access.KnowledgeSharePolicy` (see its
    docstring for the enforcement semantics). Each scope field is a narrowing
    filter: an empty collection (or ``None``) means "no narrowing on this
    dimension" and preserves the policy's broad grant; a non-empty value
    requires the item to satisfy that dimension.

    Scope-field values are carried VERBATIM as the YAML author wrote them
    (the same deferred-conversion convention the loader already uses for
    ``max_classification``, which it keeps as a raw level string). Parse-time
    validation is limited to shape (list / mapping / string) plus
    classification-domain membership for the clearance-level fields; the
    semantic fail-closed checks (``..`` path-traversal rejection, condition
    key validity, raw-string -> ``ConfidentialityLevel`` conversion, and raw
    dept/team id -> resolved unit address) remain owned by
    ``KnowledgeSharePolicy`` and the engine-application layer.

    Attributes:
        id: Unique policy identifier.
        source: Department/team ID sharing knowledge (raw, pre-resolution).
        target: Department/team ID receiving access (raw, pre-resolution).
        max_classification: Maximum classification level shared (raw level
            string, e.g. ``"restricted"``).
        compartments: Compartment names the item's compartments must be a
            subset of (empty = no compartment narrowing).
        shared_paths: Path-prefix patterns the item path must match
            (empty = no path narrowing).
        shared_types: Knowledge-type names the item type must be a member of
            (empty = no type narrowing).
        shared_classifications: Classification-level strings the item
            classification must be a member of (empty = ceiling-only).
        min_clearance: Recipient clearance floor as a raw level string, or
            ``None`` for no floor.
        conditions: Request-context conditions (e.g. ``time_window`` /
            ``environment``) carried verbatim; validated at access time.
    """

    id: str
    source: str  # department/team ID
    target: str  # department/team ID
    max_classification: str  # e.g. "restricted"
    compartments: tuple[str, ...] = ()
    shared_paths: tuple[str, ...] = ()
    shared_types: tuple[str, ...] = ()
    shared_classifications: tuple[str, ...] = ()
    min_clearance: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)


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
    - ``envelopes`` (list of ``{target, defined_by, financial?, operational?,
      temporal?, data_access?, communication?, gradient_thresholds?,
      confidentiality_clearance?, max_delegation_depth?}``) -- the optional
      ``confidentiality_clearance`` (clearance-level string) caps the data
      classification the envelope's agent may access; ``max_delegation_depth``
      (positive int) caps delegation depth. Both default to the
      ``ConstraintEnvelopeConfig`` defaults (``PUBLIC`` / unlimited) when omitted.
    - ``bridges`` (list of ``{id, role_a, role_b, type, max_classification, bilateral?}``)
    - ``ksps`` (list of ``{id, source, target, max_classification,
      compartments?, shared_paths?, shared_types?, shared_classifications?,
      min_clearance?, conditions?}``) -- the optional scope fields are
      NARROWING filters mirroring ``KnowledgeSharePolicy``: an empty
      collection or ``null`` means no narrowing on that dimension and
      preserves the broad grant.

    Args:
        path: str | Path to the YAML file.

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

    return _loaded_org_from_data(data, path)


def load_org_from_dict(data: Any, source: str = "<in-memory dict>") -> LoadedOrg:
    """Load a unified org definition from an already-parsed mapping.

    Identical parse + reference-validation semantics as :func:`load_org_yaml`,
    but reads from a Python ``dict`` instead of a YAML file. This is the entry
    point engines use when an org is supplied as a raw dict, so the dict path
    parses (and the caller can apply) the SAME four governance-spec lists the
    file path does -- closing the gap where dict-sourced orgs silently dropped
    ``clearances`` / ``envelopes`` / ``bridges`` / ``ksps``.

    Args:
        data: The org-definition mapping (same shape as a parsed YAML file).
        source: A label used in error messages (defaults to a synthetic tag).

    Returns:
        A LoadedOrg containing the OrgDefinition and all governance specs.

    Raises:
        ConfigurationError: If the mapping is invalid, required fields are
            missing, or references are broken.
    """
    return _loaded_org_from_data(data, source)


def _loaded_org_from_data(data: Any, source: str | Path) -> LoadedOrg:
    """Parse a unified org-definition mapping into a LoadedOrg.

    Shared core for :func:`load_org_yaml` (file path) and
    :func:`load_org_from_dict` (dict path); ``source`` is the path or label
    used in error messages. ``data`` is validated to be a mapping here so the
    single guard serves both the file (``yaml.safe_load`` output) and dict
    entry points.
    """
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"org definition must be a mapping (dict), got {type(data).__name__}. "
            f"Ensure the source is not empty and starts with key-value pairs. "
            f"In '{source}'."
        )

    # --- Validate required top-level fields ---
    _require_field(data, "org_id", source)
    _require_field(data, "name", source)

    org_id: str = data["org_id"]
    name: str = data["name"]

    # --- Parse departments ---
    raw_depts = data.get("departments", [])
    if not isinstance(raw_depts, list):
        raise ConfigurationError(
            f"'departments' must be a list, got {type(raw_depts).__name__} in '{source}'"
        )
    departments = _parse_departments(raw_depts, source)

    # --- Parse teams ---
    raw_teams = data.get("teams", [])
    if not isinstance(raw_teams, list):
        raise ConfigurationError(
            f"'teams' must be a list, got {type(raw_teams).__name__} in '{source}'"
        )
    teams = _parse_teams(raw_teams, source)

    # --- Build lookup indexes for reference validation ---
    dept_ids = {d.department_id for d in departments}
    team_ids = {t.id for t in teams}
    all_unit_ids = dept_ids | team_ids

    # --- Parse roles ---
    raw_roles = data.get("roles", [])
    if not isinstance(raw_roles, list):
        raise ConfigurationError(
            f"'roles' must be a list, got {type(raw_roles).__name__} in '{source}'"
        )
    roles = _parse_roles(raw_roles, all_unit_ids, source)

    # --- Validate role references ---
    role_ids = {r.role_id for r in roles}
    _validate_role_references(roles, role_ids, source)

    # --- Parse clearances ---
    raw_clearances = data.get("clearances", [])
    if not isinstance(raw_clearances, list):
        raise ConfigurationError(
            f"'clearances' must be a list, got {type(raw_clearances).__name__} in '{source}'"
        )
    clearances = _parse_clearances(raw_clearances, role_ids, source)

    # --- Parse envelopes ---
    raw_envelopes = data.get("envelopes", [])
    if not isinstance(raw_envelopes, list):
        raise ConfigurationError(
            f"'envelopes' must be a list, got {type(raw_envelopes).__name__} in '{source}'"
        )
    envelopes = _parse_envelopes(raw_envelopes, role_ids, source)

    # --- Parse bridges ---
    raw_bridges = data.get("bridges", [])
    if not isinstance(raw_bridges, list):
        raise ConfigurationError(
            f"'bridges' must be a list, got {type(raw_bridges).__name__} in '{source}'"
        )
    bridges = _parse_bridges(raw_bridges, role_ids, source)

    # --- Parse KSPs ---
    raw_ksps = data.get("ksps", [])
    if not isinstance(raw_ksps, list):
        raise ConfigurationError(
            f"'ksps' must be a list, got {type(raw_ksps).__name__} in '{source}'"
        )
    ksps = _parse_ksps(raw_ksps, all_unit_ids, source)

    # --- Build OrgDefinition ---
    org_def = OrgDefinition(
        org_id=org_id,
        name=name,
        departments=departments,
        teams=teams,
        roles=roles,
    )

    logger.info(
        "Loaded org definition '%s' from '%s': "
        "%d departments, %d teams, %d roles, "
        "%d clearances, %d envelopes, %d bridges, %d KSPs",
        org_id,
        source,
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


def _require_field(data: dict[str, Any], field_name: str, path: str | Path) -> None:
    """Raise ConfigurationError if a required field is missing."""
    if field_name not in data:
        raise ConfigurationError(
            f"Required field '{field_name}' is missing from YAML org definition in '{path}'. "
            f"Available top-level keys: {sorted(data.keys())}"
        )


def _parse_departments(raw: list[Any], path: str | Path) -> list[DepartmentConfig]:
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


def _parse_teams(raw: list[Any], path: str | Path) -> list[TeamConfig]:
    """Parse team entries from YAML."""
    teams: list[TeamConfig] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Team entry {i} must be a mapping, got {type(entry).__name__} in '{path}'"
            )
        team_id = entry.get("id")
        if not team_id:
            raise ConfigurationError(
                f"Team entry {i} is missing required 'id' field in '{path}'"
            )
        team_name = entry.get("name", team_id)
        # Use a placeholder workspace since YAML teams don't require one
        teams.append(TeamConfig(id=team_id, name=team_name, workspace=f"ws-{team_id}"))
    return teams


def _parse_roles(
    raw: list[Any],
    all_unit_ids: set[str],
    path: str | Path,
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
            raise ConfigurationError(
                f"Role entry {i} is missing required 'id' field in '{path}'"
            )

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
    path: str | Path,
) -> None:
    """Validate that all role cross-references are valid."""
    for role in roles:
        if (
            role.reports_to_role_id is not None
            and role.reports_to_role_id not in role_ids
        ):
            raise ConfigurationError(
                f"Role '{role.role_id}' has reports_to='{role.reports_to_role_id}', "
                f"but '{role.reports_to_role_id}' was not found in the role definitions. "
                f"Available role IDs: {sorted(role_ids)}. "
                f"In YAML file '{path}'."
            )


def _parse_clearances(
    raw: list[Any],
    role_ids: set[str],
    path: str | Path,
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

        if not _is_valid_level(level):
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
    path: str | Path,
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

        # --- Optional top-level governance fields (map onto
        # ConstraintEnvelopeConfig). Carried VERBATIM; Pydantic coerces the
        # clearance string -> ConfidentialityLevel and re-checks the gt=0
        # delegation-depth bound at resolve time. Parse-time validation is
        # fail-closed (a malformed value raises rather than silently
        # defaulting the authored control). ---
        confidentiality_clearance = entry.get("confidentiality_clearance")
        if confidentiality_clearance is not None and not _is_valid_level(
            confidentiality_clearance
        ):
            raise ConfigurationError(
                f"Envelope entry {i} (target '{target}') has invalid "
                f"confidentiality_clearance '{confidentiality_clearance}'. "
                f"Valid levels: {sorted(_VALID_CLEARANCE_LEVELS)}. "
                f"In YAML file '{path}'."
            )

        max_delegation_depth = entry.get("max_delegation_depth")
        if max_delegation_depth is not None and (
            isinstance(max_delegation_depth, bool)
            or not isinstance(max_delegation_depth, int)
            or max_delegation_depth <= 0
        ):
            raise ConfigurationError(
                f"Envelope entry {i} (target '{target}'): 'max_delegation_depth' "
                f"must be a positive integer, got {max_delegation_depth!r}. "
                f"In YAML file '{path}'."
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
                gradient_thresholds=entry.get("gradient_thresholds"),
                confidentiality_clearance=confidentiality_clearance,
                max_delegation_depth=max_delegation_depth,
            )
        )

    return envelopes


def _parse_bridges(
    raw: list[Any],
    role_ids: set[str],
    path: str | Path,
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
            raise ConfigurationError(
                f"Bridge entry {i} is missing required 'id' field in '{path}'"
            )

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


def _ksp_str_tuple(
    entry: dict[str, Any], key: str, ksp_id: str, path: str | Path
) -> tuple[str, ...]:
    """Validate an optional KSP scope field as a list of strings -> tuple.

    Shape validation only (list-of-str). The empty default preserves the
    broad grant (no narrowing on this dimension). Semantic checks live in
    ``KnowledgeSharePolicy``.
    """
    val = entry.get(key, [])
    if not isinstance(val, list):
        raise ConfigurationError(
            f"KSP '{ksp_id}': '{key}' must be a list, got "
            f"{type(val).__name__}. In YAML file '{path}'."
        )
    if not all(isinstance(x, str) for x in val):
        raise ConfigurationError(
            f"KSP '{ksp_id}': '{key}' entries must all be strings. "
            f"In YAML file '{path}'."
        )
    return tuple(val)


def _parse_ksps(
    raw: list[Any],
    all_unit_ids: set[str],
    path: str | Path,
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
            raise ConfigurationError(
                f"KSP entry {i} is missing required 'id' field in '{path}'"
            )

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

        # --- Optional narrowing scope fields (backward-compatible: every
        # field defaults to empty/None = no narrowing on that dimension).
        # Values are carried VERBATIM; the semantic fail-closed checks
        # ('..' path traversal, condition-key validity, raw level string ->
        # ConfidentialityLevel, raw id -> resolved address) are owned by
        # KnowledgeSharePolicy and the engine-application layer, NOT here. ---
        compartments = _ksp_str_tuple(entry, "compartments", ksp_id, path)
        shared_paths = _ksp_str_tuple(entry, "shared_paths", ksp_id, path)
        shared_types = _ksp_str_tuple(entry, "shared_types", ksp_id, path)
        shared_classifications = _ksp_str_tuple(
            entry, "shared_classifications", ksp_id, path
        )
        for level in shared_classifications:
            if not _is_valid_level(level):
                raise ConfigurationError(
                    f"KSP '{ksp_id}': invalid shared_classification '{level}'. "
                    f"Valid levels: {sorted(_VALID_CLEARANCE_LEVELS)}. "
                    f"In YAML file '{path}'."
                )

        min_clearance = entry.get("min_clearance")
        if min_clearance is not None and not _is_valid_level(min_clearance):
            raise ConfigurationError(
                f"KSP '{ksp_id}': invalid min_clearance '{min_clearance}'. "
                f"Valid levels: {sorted(_VALID_CLEARANCE_LEVELS)}. "
                f"In YAML file '{path}'."
            )

        conditions = entry.get("conditions", {})
        if not isinstance(conditions, dict):
            raise ConfigurationError(
                f"KSP '{ksp_id}': 'conditions' must be a mapping, got "
                f"{type(conditions).__name__}. In YAML file '{path}'."
            )

        ksps.append(
            KspSpec(
                id=ksp_id,
                source=source,
                target=target,
                max_classification=max_classification,
                compartments=compartments,
                shared_paths=shared_paths,
                shared_types=shared_types,
                shared_classifications=shared_classifications,
                min_clearance=min_clearance,
                conditions=conditions,
            )
        )

    return ksps

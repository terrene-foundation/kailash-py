# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Governance configuration schema — Pydantic models for PACT configuration.

Defines how organizations describe their structure, teams, agents, constraint
envelopes, and workspace layout in YAML configuration files.

Types imported from kailash.trust:
    - TrustPosture (aliased as TrustPostureLevel for backward compatibility)
    - ConfidentialityLevel

Types defined locally (PACT-specific):
    - VerificationLevel (AUTO_APPROVED, FLAGGED, HELD, BLOCKED)
    - All Pydantic config models (ConstraintEnvelopeConfig, PactConfig, etc.)
    - OrgDefinition and validation helpers
"""

from __future__ import annotations

import enum
import logging
import math
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kailash.trust import ConfidentialityLevel, TrustPosture

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatible alias: TrustPostureLevel -> TrustPosture
# ---------------------------------------------------------------------------
TrustPostureLevel = TrustPosture

# ---------------------------------------------------------------------------
# Confidentiality ordering
# ---------------------------------------------------------------------------

CONFIDENTIALITY_ORDER: dict[ConfidentialityLevel, int] = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}

# Backward-compatible alias
_CONFIDENTIALITY_ORDER = CONFIDENTIALITY_ORDER


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConstraintDimension(str, Enum):
    """The five CARE constraint dimensions."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    TEMPORAL = "temporal"
    DATA_ACCESS = "data_access"
    COMMUNICATION = "communication"


class VerificationLevel(str, Enum):
    """Verification gradient levels for agent actions.

    This is the PACT-specific enum (AUTO_APPROVED, FLAGGED, HELD, BLOCKED).
    NOT the same as kailash.trust's VerificationLevel (QUICK, STANDARD, FULL).
    """

    AUTO_APPROVED = "AUTO_APPROVED"
    FLAGGED = "FLAGGED"
    HELD = "HELD"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Constraint Envelope Config
# ---------------------------------------------------------------------------


class FinancialConstraintConfig(BaseModel):
    """Financial dimension of a constraint envelope."""

    model_config = ConfigDict(frozen=True)

    max_spend_usd: float = Field(
        default=0.0, ge=0, description="Maximum USD spend allowed"
    )
    api_cost_budget_usd: float | None = Field(
        default=None, ge=0, description="LLM API cost budget (per billing period)"
    )
    requires_approval_above_usd: float | None = Field(
        default=None, ge=0, description="Threshold requiring human approval"
    )
    reasoning_required: bool = Field(
        default=False,
        description="When True, any action touching this dimension must include a reasoning trace",
    )

    @field_validator(
        "max_spend_usd", "api_cost_budget_usd", "requires_approval_above_usd"
    )
    @classmethod
    def reject_non_finite(cls, v: float | None, info: Any) -> float | None:
        """Reject NaN and Inf values -- they bypass numeric comparisons.

        Security-critical: NaN < X is always False, Inf > X is always False
        for finite X. Both silently bypass budget checks and tightening
        validation. Per trust-plane-security.md rule 3.
        """
        if v is not None and not math.isfinite(v):
            raise ValueError(
                f"{info.field_name} must be finite, got {v!r}. "
                f"NaN/Inf values bypass governance checks."
            )
        return v


class OperationalConstraintConfig(BaseModel):
    """Operational dimension of a constraint envelope."""

    model_config = ConfigDict(frozen=True)

    allowed_actions: list[str] = Field(
        default_factory=list, description="Actions this agent may perform"
    )
    blocked_actions: list[str] = Field(
        default_factory=list, description="Actions explicitly blocked"
    )
    max_actions_per_day: int | None = Field(
        default=None, gt=0, description="Daily action rate limit"
    )
    max_actions_per_hour: int | None = Field(
        default=None,
        gt=0,
        description="Hourly action rate limit (per-agent sliding window)",
    )
    rate_limit_window_type: str = Field(
        default="fixed",
        description="Rate limit window type: 'fixed' (calendar-based) or 'rolling' (sliding window)",
    )
    reasoning_required: bool = Field(
        default=False,
        description="When True, any action touching this dimension must include a reasoning trace",
    )

    @field_validator("rate_limit_window_type")
    @classmethod
    def validate_rate_limit_window_type(cls, v: str) -> str:
        if v not in ("fixed", "rolling"):
            msg = f"rate_limit_window_type must be 'fixed' or 'rolling', got '{v}'"
            raise ValueError(msg)
        return v


class TemporalConstraintConfig(BaseModel):
    """Temporal dimension of a constraint envelope."""

    model_config = ConfigDict(frozen=True)

    active_hours_start: str | None = Field(
        default=None, description="Start of active window (HH:MM, 24h)"
    )
    active_hours_end: str | None = Field(
        default=None, description="End of active window (HH:MM, 24h)"
    )
    timezone: str = Field(default="UTC", description="Timezone for active hours")
    blackout_periods: list[str] = Field(
        default_factory=list, description="Periods when agent must not operate"
    )
    reasoning_required: bool = Field(
        default=False,
        description="When True, any action touching this dimension must include a reasoning trace",
    )

    @field_validator("active_hours_start", "active_hours_end")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2:
            msg = f"Time must be HH:MM format, got '{v}'"
            raise ValueError(msg)
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            msg = f"Invalid time '{v}': hours 0-23, minutes 0-59"
            raise ValueError(msg)
        return v


class DataAccessConstraintConfig(BaseModel):
    """Data access dimension of a constraint envelope."""

    model_config = ConfigDict(frozen=True)

    read_paths: list[str] = Field(
        default_factory=list, description="Paths/resources agent may read"
    )
    write_paths: list[str] = Field(
        default_factory=list, description="Paths/resources agent may write"
    )
    blocked_data_types: list[str] = Field(
        default_factory=list,
        description="Data types agent must never access (e.g., 'pii', 'financial_records')",
    )
    reasoning_required: bool = Field(
        default=False,
        description="When True, any action touching this dimension must include a reasoning trace",
    )


class CommunicationConstraintConfig(BaseModel):
    """Communication dimension of a constraint envelope."""

    model_config = ConfigDict(frozen=True)

    internal_only: bool = Field(
        default=False, description="Agent restricted to internal channels"
    )
    allowed_channels: list[str] = Field(
        default_factory=list, description="Channels agent may communicate through"
    )
    external_requires_approval: bool = Field(
        default=True, description="External communication requires human approval"
    )
    reasoning_required: bool = Field(
        default=False,
        description="When True, any action touching this dimension must include a reasoning trace",
    )


class ConstraintEnvelopeConfig(BaseModel):
    """A complete constraint envelope across all five CARE dimensions.

    Now includes confidentiality_clearance (M15/1501) -- the maximum
    confidentiality level of data this envelope's agent may access.

    M23/2301: financial is Optional -- not all agents handle money. When None,
    the financial dimension is skipped during evaluation (no zero-spend default
    that blocks everything).

    M23/2302: max_delegation_depth controls how many levels deep trust can be
    delegated. expires_at is a config-level expiry (distinct from the envelope
    object's runtime expiry).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Unique identifier for this envelope")
    description: str = Field(default="", description="Human-readable description")
    confidentiality_clearance: ConfidentialityLevel = Field(
        default=ConfidentialityLevel.PUBLIC,
        description=(
            "Maximum confidentiality level of data this envelope may access. "
            "Data classified above this level will be denied."
        ),
    )
    financial: FinancialConstraintConfig | None = Field(
        default=None,
        description=(
            "Financial constraint config. None means the agent has no financial "
            "capability -- the financial dimension is skipped during evaluation."
        ),
    )
    operational: OperationalConstraintConfig = Field(
        default_factory=OperationalConstraintConfig
    )
    temporal: TemporalConstraintConfig = Field(default_factory=TemporalConstraintConfig)
    data_access: DataAccessConstraintConfig = Field(
        default_factory=DataAccessConstraintConfig
    )
    communication: CommunicationConstraintConfig = Field(
        default_factory=CommunicationConstraintConfig
    )
    max_delegation_depth: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum delegation depth -- how many levels deep trust can be delegated. "
            "None means unlimited."
        ),
    )
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "Config-level expiry timestamp. When set, the constraint envelope config "
            "itself expires at this time, independent of the runtime envelope expiry."
        ),
    )


# ---------------------------------------------------------------------------
# Verification Gradient Config
# ---------------------------------------------------------------------------


class GradientRuleConfig(BaseModel):
    """A single verification gradient rule -- maps action patterns to verification levels."""

    pattern: str = Field(description="Action pattern to match (glob or regex)")
    level: VerificationLevel = Field(
        description="Verification level for matching actions"
    )
    reason: str = Field(default="", description="Why this level applies")


class VerificationGradientConfig(BaseModel):
    """Verification gradient rules for an agent or team."""

    rules: list[GradientRuleConfig] = Field(
        default_factory=list,
        description="Ordered list of gradient rules (first match wins)",
    )
    default_level: VerificationLevel = Field(
        default=VerificationLevel.HELD, description="Default level when no rule matches"
    )


# ---------------------------------------------------------------------------
# Agent Config
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Configuration for a single agent in a team."""

    id: str = Field(description="Unique agent identifier")
    name: str = Field(description="Human-readable agent name")
    role: str = Field(description="Agent's role description")
    constraint_envelope: str = Field(
        description="ID of the constraint envelope governing this agent"
    )
    initial_posture: TrustPostureLevel = Field(
        default=TrustPostureLevel.SUPERVISED,
        description="Starting trust posture",
    )
    capabilities: list[str] = Field(
        default_factory=list, description="Specific capabilities this agent has"
    )
    llm_backend: str | None = Field(
        default=None, description="LLM backend override (uses team default if None)"
    )
    verification_gradient: VerificationGradientConfig | None = Field(
        default=None,
        description="Agent-specific gradient rules (overrides team default)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional agent-specific metadata"
    )


# ---------------------------------------------------------------------------
# Workspace Config
# ---------------------------------------------------------------------------


class WorkspaceConfig(BaseModel):
    """Configuration for a workspace (knowledge base for an agent team)."""

    id: str = Field(description="Unique workspace identifier")
    path: str = Field(description="Filesystem path to workspace directory")
    description: str = Field(default="", description="Purpose of this workspace")
    knowledge_base_paths: list[str] = Field(
        default_factory=lambda: ["briefs/", "01-analysis/", "02-plans/"],
        description="Subdirectories constituting the knowledge base",
    )

    @field_validator("path")
    @classmethod
    def validate_path_not_empty(cls, v: str) -> str:
        if not v.strip():
            msg = "Workspace path must not be empty"
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# Team Config
# ---------------------------------------------------------------------------


class TeamConfig(BaseModel):
    """Configuration for an agent team."""

    id: str = Field(description="Unique team identifier")
    name: str = Field(description="Human-readable team name")
    workspace: str = Field(description="ID of the workspace this team operates in")
    team_lead: str | None = Field(default=None, description="ID of the team lead agent")
    agents: list[str] = Field(
        default_factory=list, description="IDs of agents in this team"
    )
    default_llm_backend: str = Field(
        default="anthropic", description="Default LLM backend for team agents"
    )
    verification_gradient: VerificationGradientConfig | None = Field(
        default=None, description="Team-level default gradient rules"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional team-specific metadata"
    )


# ---------------------------------------------------------------------------
# Department Config
# ---------------------------------------------------------------------------


class DepartmentConfig(BaseModel):
    """Configuration for a department -- an intermediate grouping between org and team.

    Departments enable 3-level monotonic constraint tightening:
    org envelope >= department envelope >= team envelope >= agent envelope.

    Each department groups related teams under a single constraint envelope
    that is tighter than the org-level envelope but looser than individual
    team envelopes.
    """

    model_config = ConfigDict(frozen=True)

    department_id: str = Field(description="Unique department identifier")
    name: str = Field(description="Human-readable department name")
    description: str = Field(default="", description="Optional department description")
    teams: list[str] = Field(
        default_factory=list, description="Team IDs belonging to this department"
    )
    head_agent_id: str | None = Field(
        default=None,
        description="Department head agent -- must be an agent in one of the department's teams",
    )
    envelope: ConstraintEnvelopeConfig | None = Field(
        default=None,
        description=(
            "Department-level constraint envelope. Must be tighter than the org "
            "envelope and looser than or equal to team envelopes."
        ),
    )


# ---------------------------------------------------------------------------
# Genesis Config
# ---------------------------------------------------------------------------


class GenesisConfig(BaseModel):
    """Configuration for the EATP genesis record (root of trust)."""

    authority: str = Field(
        description="Authority identifier (e.g., 'terrene.foundation')"
    )
    authority_name: str = Field(description="Human-readable authority name")
    policy_reference: str = Field(
        default="", description="URI or path to the governance policy document"
    )


# ---------------------------------------------------------------------------
# PACT Config (Top Level)
# ---------------------------------------------------------------------------


class PactConfig(BaseModel):
    """Top-level PACT configuration.

    This is the root object that contains all platform configuration --
    genesis, teams, agents, constraint envelopes, workspaces, and gradient rules.
    """

    name: str = Field(description="Organization name")
    version: str = Field(default="1.0", description="Config schema version")
    genesis: GenesisConfig = Field(description="EATP genesis (root of trust)")
    default_posture: TrustPostureLevel = Field(
        default=TrustPostureLevel.SUPERVISED,
        description="Default trust posture for new agents",
    )
    constraint_envelopes: list[ConstraintEnvelopeConfig] = Field(
        default_factory=list, description="All constraint envelope definitions"
    )
    agents: list[AgentConfig] = Field(
        default_factory=list, description="All agent definitions"
    )
    teams: list[TeamConfig] = Field(
        default_factory=list, description="All team definitions"
    )
    workspaces: list[WorkspaceConfig] = Field(
        default_factory=list, description="All workspace definitions"
    )

    def get_envelope(self, envelope_id: str) -> ConstraintEnvelopeConfig | None:
        """Look up a constraint envelope by ID."""
        for envelope in self.constraint_envelopes:
            if envelope.id == envelope_id:
                return envelope
        return None

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        """Look up an agent by ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_team(self, team_id: str) -> TeamConfig | None:
        """Look up a team by ID."""
        for team in self.teams:
            if team.id == team_id:
                return team
        return None

    def get_workspace(self, workspace_id: str) -> WorkspaceConfig | None:
        """Look up a workspace by ID."""
        for workspace in self.workspaces:
            if workspace.id == workspace_id:
                return workspace
        return None

    @field_validator("constraint_envelopes")
    @classmethod
    def validate_unique_envelope_ids(
        cls,
        v: list[ConstraintEnvelopeConfig],
    ) -> list[ConstraintEnvelopeConfig]:
        ids = [e.id for e in v]
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            msg = f"Duplicate constraint envelope IDs: {set(dupes)}"
            raise ValueError(msg)
        return v

    @field_validator("agents")
    @classmethod
    def validate_unique_agent_ids(cls, v: list[AgentConfig]) -> list[AgentConfig]:
        ids = [a.id for a in v]
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            msg = f"Duplicate agent IDs: {set(dupes)}"
            raise ValueError(msg)
        return v

    @field_validator("teams")
    @classmethod
    def validate_unique_team_ids(cls, v: list[TeamConfig]) -> list[TeamConfig]:
        ids = [t.id for t in v]
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            msg = f"Duplicate team IDs: {set(dupes)}"
            raise ValueError(msg)
        return v


# Backward-compatible alias (PlatformConfig was renamed to PactConfig)
PlatformConfig = PactConfig


# ---------------------------------------------------------------------------
# Org Validation Helpers
# ---------------------------------------------------------------------------


class ValidationSeverity(str, enum.Enum):
    """Severity level for org validation results."""

    ERROR = "error"
    WARNING = "warning"


class ValidationResult(BaseModel):
    """A single validation finding with severity, message, and error code."""

    severity: ValidationSeverity
    message: str
    code: str

    @property
    def is_error(self) -> bool:
        """Whether this result is a blocking error."""
        return self.severity == ValidationSeverity.ERROR


# ---------------------------------------------------------------------------
# OrgDefinition
# ---------------------------------------------------------------------------


class OrgDefinition(BaseModel):
    """Complete organization definition.

    Contains all agents, teams, envelopes, workspaces, and departments for an
    organization.  Provides validation to ensure internal consistency (no dangling
    references, no duplicate IDs) and monotonic constraint tightening across four
    levels: org -> department -> team -> agent.
    """

    org_id: str = Field(description="Unique organization identifier")
    name: str = Field(description="Human-readable organization name")
    authority_id: str = Field(default="", description="Genesis authority identifier")
    org_envelope: ConstraintEnvelopeConfig | None = Field(
        default=None,
        description=(
            "Organization-level constraint envelope. When set, department and "
            "team envelopes are validated as monotonic tightenings of this envelope."
        ),
    )
    departments: list[DepartmentConfig] = Field(
        default_factory=list,
        description="All department definitions (intermediate grouping between org and team)",
    )
    teams: list[TeamConfig] = Field(
        default_factory=list, description="All team definitions"
    )
    agents: list[AgentConfig] = Field(
        default_factory=list, description="All agent definitions"
    )
    envelopes: list[ConstraintEnvelopeConfig] = Field(
        default_factory=list, description="All constraint envelope definitions"
    )
    workspaces: list[WorkspaceConfig] = Field(
        default_factory=list, description="All workspace definitions"
    )
    roles: list = Field(
        default_factory=list,
        description="All role definitions (first-class PACT nodes, list of RoleDefinition)",
    )

    def get_team_agents(self, team_id: str) -> list[AgentConfig]:
        """Get all agents in a team.

        Args:
            team_id: The team to look up.

        Returns:
            List of AgentConfig for agents assigned to the team.

        Raises:
            ValueError: If the team_id is not found in this organization.
        """
        team = None
        for t in self.teams:
            if t.id == team_id:
                team = t
                break
        if team is None:
            raise ValueError(
                f"Team '{team_id}' not found in organization '{self.org_id}'. "
                f"Available teams: {[t.id for t in self.teams]}"
            )

        agent_index = {a.id: a for a in self.agents}
        return [agent_index[aid] for aid in team.agents if aid in agent_index]

    def validate_org(self) -> tuple[bool, list[str]]:
        """Validate org definition for internal consistency.

        Checks:
        - No duplicate IDs across agents, teams, envelopes, workspaces, departments
        - All agent envelope references resolve to defined envelopes
        - All team workspace references resolve to defined workspaces
        - All department team references resolve to defined teams
        - No team appears in multiple departments
        - Department head agent must be in one of the department's teams

        Returns:
            (True, []) if valid, (False, [list of error messages]) otherwise.
        """
        errors: list[str] = []

        # Check duplicate agent IDs
        agent_ids = [a.id for a in self.agents]
        seen_agents: set[str] = set()
        for aid in agent_ids:
            if aid in seen_agents:
                errors.append(f"Duplicate agent ID: '{aid}'")
            seen_agents.add(aid)

        # Check duplicate team IDs
        team_ids = [t.id for t in self.teams]
        seen_teams: set[str] = set()
        for tid in team_ids:
            if tid in seen_teams:
                errors.append(f"Duplicate team ID: '{tid}'")
            seen_teams.add(tid)

        # Check duplicate envelope IDs
        envelope_ids = [e.id for e in self.envelopes]
        seen_envelopes: set[str] = set()
        for eid in envelope_ids:
            if eid in seen_envelopes:
                errors.append(f"Duplicate envelope ID: '{eid}'")
            seen_envelopes.add(eid)

        # Check duplicate workspace IDs
        workspace_ids = [w.id for w in self.workspaces]
        seen_workspaces: set[str] = set()
        for wid in workspace_ids:
            if wid in seen_workspaces:
                errors.append(f"Duplicate workspace ID: '{wid}'")
            seen_workspaces.add(wid)

        # Check duplicate department IDs
        seen_depts: set[str] = set()
        for dept in self.departments:
            if dept.department_id in seen_depts:
                errors.append(f"Duplicate department ID: '{dept.department_id}'")
            seen_depts.add(dept.department_id)

        # Check all agent envelope references resolve
        envelope_id_set = set(envelope_ids)
        for agent in self.agents:
            if agent.constraint_envelope not in envelope_id_set:
                errors.append(
                    f"Agent '{agent.id}' references envelope '{agent.constraint_envelope}' "
                    f"which does not exist. Available envelopes: {sorted(envelope_id_set)}"
                )

        # Check all team workspace references resolve
        workspace_id_set = set(workspace_ids)
        for team in self.teams:
            if team.workspace not in workspace_id_set:
                errors.append(
                    f"Team '{team.id}' references workspace '{team.workspace}' "
                    f"which does not exist. Available workspaces: {sorted(workspace_id_set)}"
                )

        # Department validation
        team_id_set = set(team_ids)

        # Build team -> agents mapping for head validation
        team_agent_map: dict[str, list[str]] = {}
        for team in self.teams:
            team_agent_map[team.id] = list(team.agents)

        # Track which teams belong to which departments
        team_to_dept: dict[str, list[str]] = {}
        for dept in self.departments:
            # Check department team references resolve
            for team_ref in dept.teams:
                if team_ref not in team_id_set:
                    errors.append(
                        f"Department '{dept.department_id}' references team '{team_ref}' "
                        f"which does not exist. Available teams: {sorted(team_id_set)}"
                    )
                team_to_dept.setdefault(team_ref, []).append(dept.department_id)

            # Check department head is in one of the department's teams
            if dept.head_agent_id is not None:
                dept_agent_ids: set[str] = set()
                for team_ref in dept.teams:
                    if team_ref in team_agent_map:
                        dept_agent_ids.update(team_agent_map[team_ref])
                if dept.head_agent_id not in dept_agent_ids:
                    errors.append(
                        f"Department '{dept.department_id}' head agent "
                        f"'{dept.head_agent_id}' is not in any of the department's "
                        f"teams ({dept.teams}). The head must be an agent in one of "
                        f"the department's teams."
                    )

        # Check no team appears in multiple departments
        for team_ref, dept_list in team_to_dept.items():
            if len(dept_list) > 1:
                errors.append(
                    f"Team '{team_ref}' appears in multiple departments: "
                    f"{sorted(dept_list)}. A team can only belong to one department."
                )

        return (len(errors) == 0, errors)

    def validate_org_detailed(self) -> list[ValidationResult]:
        """Validate org definition with detailed results including severity levels.

        Returns a list of ValidationResult objects with ERROR or WARNING severity.
        ERRORs are structural issues that prevent building (duplicate IDs, dangling refs).
        WARNINGs are coverage gaps that allow building with notification.

        Returns:
            List of ValidationResult findings (empty means fully valid).
        """
        results: list[ValidationResult] = []

        # --- Structural checks (ERROR severity) ---

        # Duplicate agent IDs
        seen_agents: set[str] = set()
        for a in self.agents:
            if a.id in seen_agents:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate agent ID: '{a.id}'",
                        code="ERR_DUPLICATE_AGENT",
                    )
                )
            seen_agents.add(a.id)

        # Duplicate team IDs
        seen_teams: set[str] = set()
        for t in self.teams:
            if t.id in seen_teams:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate team ID: '{t.id}'",
                        code="ERR_DUPLICATE_TEAM",
                    )
                )
            seen_teams.add(t.id)

        # Duplicate envelope IDs
        seen_envelopes: set[str] = set()
        for e in self.envelopes:
            if e.id in seen_envelopes:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate envelope ID: '{e.id}'",
                        code="ERR_DUPLICATE_ENVELOPE",
                    )
                )
            seen_envelopes.add(e.id)

        # Duplicate workspace IDs
        seen_workspaces: set[str] = set()
        for w in self.workspaces:
            if w.id in seen_workspaces:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate workspace ID: '{w.id}'",
                        code="ERR_DUPLICATE_WORKSPACE",
                    )
                )
            seen_workspaces.add(w.id)

        # Envelope references
        envelope_ids = {e.id for e in self.envelopes}
        for agent in self.agents:
            if agent.constraint_envelope not in envelope_ids:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Agent '{agent.id}' references envelope "
                            f"'{agent.constraint_envelope}' which does not exist"
                        ),
                        code="ERR_DANGLING_ENVELOPE_REF",
                    )
                )

        # Workspace references
        workspace_ids = {w.id for w in self.workspaces}
        for team in self.teams:
            if team.workspace not in workspace_ids:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Team '{team.id}' references workspace "
                            f"'{team.workspace}' which does not exist"
                        ),
                        code="ERR_DANGLING_WORKSPACE_REF",
                    )
                )

        # --- Department structural checks (M39/6021) ---
        team_id_set = {t.id for t in self.teams}
        team_agent_map_d: dict[str, list[str]] = {}
        for team in self.teams:
            team_agent_map_d[team.id] = list(team.agents)

        # Duplicate department IDs
        seen_dept_ids: set[str] = set()
        for dept in self.departments:
            if dept.department_id in seen_dept_ids:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Duplicate department ID: '{dept.department_id}'",
                        code="ERR_DUPLICATE_DEPARTMENT",
                    )
                )
            seen_dept_ids.add(dept.department_id)

        # Department team references
        team_to_dept_map: dict[str, list[str]] = {}
        for dept in self.departments:
            for team_ref in dept.teams:
                if team_ref not in team_id_set:
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Department '{dept.department_id}' references team "
                                f"'{team_ref}' which does not exist"
                            ),
                            code="ERR_DANGLING_DEPT_TEAM_REF",
                        )
                    )
                team_to_dept_map.setdefault(team_ref, []).append(dept.department_id)

        # Team in multiple departments
        for team_ref, dept_list in team_to_dept_map.items():
            if len(dept_list) > 1:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Team '{team_ref}' appears in multiple departments: "
                            f"{sorted(dept_list)}"
                        ),
                        code="TEAM_IN_MULTIPLE_DEPARTMENTS",
                    )
                )

        # Department head must be in department's teams
        for dept in self.departments:
            if dept.head_agent_id is not None:
                dept_agent_ids_set: set[str] = set()
                for team_ref in dept.teams:
                    if team_ref in team_agent_map_d:
                        dept_agent_ids_set.update(team_agent_map_d[team_ref])
                if dept.head_agent_id not in dept_agent_ids_set:
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Department '{dept.department_id}' head agent "
                                f"'{dept.head_agent_id}' is not in any of the "
                                f"department's teams ({dept.teams})"
                            ),
                            code="ERR_DEPT_HEAD_NOT_IN_TEAMS",
                        )
                    )

        # --- Capability-envelope alignment (5029) ---
        envelope_index = {e.id: e for e in self.envelopes}
        for agent in self.agents:
            env = envelope_index.get(agent.constraint_envelope)
            if env and env.operational and env.operational.allowed_actions:
                allowed = set(env.operational.allowed_actions)
                for cap in getattr(agent, "capabilities", []) or []:
                    if cap not in allowed:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Agent '{agent.id}' has capability '{cap}' "
                                    f"not in envelope '{env.id}' allowed_actions"
                                ),
                                code="CAP_NOT_IN_ENVELOPE",
                            )
                        )

        # --- Team lead superset check (5031) ---
        for team in self.teams:
            team_agents = [a for a in self.agents if a.id in team.agents]
            leads = [
                a
                for a in team_agents
                if "lead" in a.id.lower() or "lead" in (a.role or "").lower()
            ]
            non_leads = [a for a in team_agents if a not in leads]
            for lead in leads:
                lead_caps = set(getattr(lead, "capabilities", []) or [])
                for member in non_leads:
                    member_caps = set(getattr(member, "capabilities", []) or [])
                    missing = member_caps - lead_caps
                    if missing:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Team lead '{lead.id}' missing capabilities "
                                    f"held by '{member.id}': {sorted(missing)}"
                                ),
                                code="LEAD_MISSING_CAPABILITY",
                            )
                        )

        # --- Gradient coverage (5032) ---
        # Build team gradient lookup for fallback
        agent_to_team: dict[str, TeamConfig] = {}
        for team in self.teams:
            for aid in team.agents:
                agent_to_team[aid] = team

        for agent in self.agents:
            gradient = getattr(agent, "verification_gradient", None)
            # Fall back to team gradient if agent has none
            if not gradient or not gradient.rules:
                team = agent_to_team.get(agent.id)
                if team:
                    gradient = getattr(team, "verification_gradient", None)
            if gradient and gradient.rules:
                rule_patterns = [r.pattern for r in gradient.rules]
                for cap in getattr(agent, "capabilities", []) or []:
                    covered = any(
                        cap == pattern
                        or pattern == "*"
                        or (pattern.endswith("*") and cap.startswith(pattern[:-1]))
                        for pattern in rule_patterns
                    )
                    if not covered:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.WARNING,
                                message=(
                                    f"Agent '{agent.id}' capability '{cap}' "
                                    f"has no matching gradient rule"
                                ),
                                code="GRADIENT_UNCOVERED_CAPABILITY",
                            )
                        )

        # --- Helper: glob-aware path containment ---
        def _path_covered_by(child: str, parent_paths: set[str]) -> bool:
            for p in parent_paths:
                if child == p:
                    return True
                if p.endswith("*") and child.startswith(p[:-1]):
                    return True
            return False

        # --- Monotonic constraint tightening (5030) ---
        agent_index = {a.id: a for a in self.agents}
        for team in self.teams:
            lead_id = team.team_lead
            if not lead_id or lead_id not in agent_index:
                continue
            lead_agent = agent_index[lead_id]
            lead_env = envelope_index.get(lead_agent.constraint_envelope)
            if not lead_env:
                continue

            for member_id in team.agents:
                if member_id == lead_id or member_id not in agent_index:
                    continue
                member_agent = agent_index[member_id]
                sub_env = envelope_index.get(member_agent.constraint_envelope)
                if not sub_env:
                    continue

                # Financial tightening
                if (
                    lead_env.financial
                    and sub_env.financial
                    and lead_env.financial.max_spend_usd is not None
                    and sub_env.financial.max_spend_usd is not None
                    and sub_env.financial.max_spend_usd
                    > lead_env.financial.max_spend_usd
                ):
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"Agent '{member_id}' financial limit "
                                f"(${sub_env.financial.max_spend_usd}) exceeds "
                                f"lead '{lead_id}' (${lead_env.financial.max_spend_usd})"
                            ),
                            code="FINANCIAL_TIGHTENING",
                        )
                    )

                # Operational tightening -- allowed actions
                if lead_env.operational and sub_env.operational:
                    lead_actions = set(lead_env.operational.allowed_actions or [])
                    sub_actions = set(sub_env.operational.allowed_actions or [])
                    if lead_actions and sub_actions:
                        extra = sub_actions - lead_actions
                        if extra:
                            results.append(
                                ValidationResult(
                                    severity=ValidationSeverity.ERROR,
                                    message=(
                                        f"Agent '{member_id}' has actions {sorted(extra)} "
                                        f"not in lead '{lead_id}' envelope"
                                    ),
                                    code="OPERATIONAL_TIGHTENING",
                                )
                            )

                    # Operational tightening -- rate limit
                    lead_rate = lead_env.operational.max_actions_per_day
                    sub_rate = sub_env.operational.max_actions_per_day
                    if lead_rate and sub_rate and sub_rate > lead_rate:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Agent '{member_id}' rate limit ({sub_rate}/day) "
                                    f"exceeds lead '{lead_id}' ({lead_rate}/day)"
                                ),
                                code="OPERATIONAL_TIGHTENING",
                            )
                        )

                # Communication tightening
                if lead_env.communication and sub_env.communication:
                    if (
                        lead_env.communication.internal_only
                        and not sub_env.communication.internal_only
                    ):
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Agent '{member_id}' allows external communication "
                                    f"but lead '{lead_id}' is internal-only"
                                ),
                                code="COMMUNICATION_TIGHTENING",
                            )
                        )

                # Temporal tightening (5033)
                if lead_env.temporal and sub_env.temporal:
                    if (
                        lead_env.temporal.active_hours_start
                        and sub_env.temporal.active_hours_start
                        and sub_env.temporal.active_hours_start
                        < lead_env.temporal.active_hours_start
                    ):
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Agent '{member_id}' starts at "
                                    f"{sub_env.temporal.active_hours_start} "
                                    f"before lead '{lead_id}' "
                                    f"({lead_env.temporal.active_hours_start})"
                                ),
                                code="TEMPORAL_TIGHTENING",
                            )
                        )
                    if (
                        lead_env.temporal.active_hours_end
                        and sub_env.temporal.active_hours_end
                        and sub_env.temporal.active_hours_end
                        > lead_env.temporal.active_hours_end
                    ):
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Agent '{member_id}' ends at "
                                    f"{sub_env.temporal.active_hours_end} "
                                    f"after lead '{lead_id}' "
                                    f"({lead_env.temporal.active_hours_end})"
                                ),
                                code="TEMPORAL_TIGHTENING",
                            )
                        )

                # Data access tightening (5033) -- glob-aware path containment
                if lead_env.data_access and sub_env.data_access:
                    lead_read = set(lead_env.data_access.read_paths or [])
                    sub_read = set(sub_env.data_access.read_paths or [])
                    if lead_read and sub_read:
                        uncovered = [
                            p for p in sub_read if not _path_covered_by(p, lead_read)
                        ]
                        if uncovered:
                            results.append(
                                ValidationResult(
                                    severity=ValidationSeverity.ERROR,
                                    message=(
                                        f"Agent '{member_id}' has read paths "
                                        f"{sorted(uncovered)} outside lead "
                                        f"'{lead_id}' scope"
                                    ),
                                    code="DATA_ACCESS_TIGHTENING",
                                )
                            )

                    lead_write = set(lead_env.data_access.write_paths or [])
                    sub_write = set(sub_env.data_access.write_paths or [])
                    if lead_write and sub_write:
                        uncovered = [
                            p for p in sub_write if not _path_covered_by(p, lead_write)
                        ]
                        if uncovered:
                            results.append(
                                ValidationResult(
                                    severity=ValidationSeverity.ERROR,
                                    message=(
                                        f"Agent '{member_id}' has write paths "
                                        f"{sorted(uncovered)} outside lead "
                                        f"'{lead_id}' scope"
                                    ),
                                    code="DATA_ACCESS_TIGHTENING",
                                )
                            )

        # --- 3-Level Monotonic Tightening (M39/6022) ---
        # Checks: org -> department -> team (for teams in departments)

        # Build lookup: team_id -> department (if any)
        team_dept_lookup: dict[str, DepartmentConfig] = {}
        for dept in self.departments:
            for tid in dept.teams:
                team_dept_lookup[tid] = dept

        def _check_envelope_tightening(
            child_env: ConstraintEnvelopeConfig,
            parent_env: ConstraintEnvelopeConfig,
            child_label: str,
            parent_label: str,
            code: str,
        ) -> None:
            """Check that child_env is tighter than or equal to parent_env."""
            # Financial tightening
            if (
                parent_env.financial
                and child_env.financial
                and parent_env.financial.max_spend_usd is not None
                and child_env.financial.max_spend_usd is not None
                and child_env.financial.max_spend_usd
                > parent_env.financial.max_spend_usd
            ):
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"{child_label} financial limit "
                            f"(${child_env.financial.max_spend_usd}) exceeds "
                            f"{parent_label} (${parent_env.financial.max_spend_usd})"
                        ),
                        code=code,
                    )
                )

            # Operational tightening -- allowed actions
            if parent_env.operational and child_env.operational:
                parent_actions = set(parent_env.operational.allowed_actions or [])
                child_actions = set(child_env.operational.allowed_actions or [])
                if parent_actions and child_actions:
                    extra = child_actions - parent_actions
                    if extra:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"{child_label} has actions {sorted(extra)} "
                                    f"not in {parent_label} envelope"
                                ),
                                code=code,
                            )
                        )

                # Operational tightening -- rate limit
                parent_rate = parent_env.operational.max_actions_per_day
                child_rate = child_env.operational.max_actions_per_day
                if parent_rate and child_rate and child_rate > parent_rate:
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"{child_label} rate limit ({child_rate}/day) "
                                f"exceeds {parent_label} ({parent_rate}/day)"
                            ),
                            code=code,
                        )
                    )

            # Communication tightening
            if parent_env.communication and child_env.communication:
                if (
                    parent_env.communication.internal_only
                    and not child_env.communication.internal_only
                ):
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"{child_label} allows external communication "
                                f"but {parent_label} is internal-only"
                            ),
                            code=code,
                        )
                    )

            # Temporal tightening
            if parent_env.temporal and child_env.temporal:
                if (
                    parent_env.temporal.active_hours_start
                    and child_env.temporal.active_hours_start
                    and child_env.temporal.active_hours_start
                    < parent_env.temporal.active_hours_start
                ):
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"{child_label} starts at "
                                f"{child_env.temporal.active_hours_start} "
                                f"before {parent_label} "
                                f"({parent_env.temporal.active_hours_start})"
                            ),
                            code=code,
                        )
                    )
                if (
                    parent_env.temporal.active_hours_end
                    and child_env.temporal.active_hours_end
                    and child_env.temporal.active_hours_end
                    > parent_env.temporal.active_hours_end
                ):
                    results.append(
                        ValidationResult(
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"{child_label} ends at "
                                f"{child_env.temporal.active_hours_end} "
                                f"after {parent_label} "
                                f"({parent_env.temporal.active_hours_end})"
                            ),
                            code=code,
                        )
                    )

            # Data access tightening
            if parent_env.data_access and child_env.data_access:
                parent_read = set(parent_env.data_access.read_paths or [])
                child_read = set(child_env.data_access.read_paths or [])
                if parent_read and child_read:
                    uncovered = [
                        p for p in child_read if not _path_covered_by(p, parent_read)
                    ]
                    if uncovered:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"{child_label} has read paths "
                                    f"{sorted(uncovered)} outside "
                                    f"{parent_label} scope"
                                ),
                                code=code,
                            )
                        )
                parent_write = set(parent_env.data_access.write_paths or [])
                child_write = set(child_env.data_access.write_paths or [])
                if parent_write and child_write:
                    uncovered = [
                        p for p in child_write if not _path_covered_by(p, parent_write)
                    ]
                    if uncovered:
                        results.append(
                            ValidationResult(
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"{child_label} has write paths "
                                    f"{sorted(uncovered)} outside "
                                    f"{parent_label} scope"
                                ),
                                code=code,
                            )
                        )

        # Check org -> department tightening
        if self.org_envelope:
            for dept in self.departments:
                if dept.envelope is not None:
                    _check_envelope_tightening(
                        child_env=dept.envelope,
                        parent_env=self.org_envelope,
                        child_label=f"Department '{dept.department_id}'",
                        parent_label=f"org '{self.org_id}'",
                        code="DEPT_ORG_TIGHTENING",
                    )

        # Check department -> team tightening
        for team in self.teams:
            dept = team_dept_lookup.get(team.id)
            if dept is None or dept.envelope is None:
                continue
            lead_id = team.team_lead
            if lead_id and lead_id in agent_index:
                lead_agent = agent_index[lead_id]
                lead_env = envelope_index.get(lead_agent.constraint_envelope)
                if lead_env:
                    _check_envelope_tightening(
                        child_env=lead_env,
                        parent_env=dept.envelope,
                        child_label=f"Team '{team.id}'",
                        parent_label=f"department '{dept.department_id}'",
                        code="TEAM_DEPT_TIGHTENING",
                    )

        # --- Multi-team validation (5034) ---
        agent_team_map: dict[str, list[str]] = {}
        for team in self.teams:
            for agent_id in team.agents:
                agent_team_map.setdefault(agent_id, []).append(team.id)

        for agent_id, team_list in agent_team_map.items():
            if len(team_list) > 1:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Agent '{agent_id}' appears in multiple teams: "
                            f"{sorted(team_list)}"
                        ),
                        code="AGENT_IN_MULTIPLE_TEAMS",
                    )
                )

        # Workspace path conflicts
        ws_paths: dict[str, list[str]] = {}
        for ws in self.workspaces:
            ws_paths.setdefault(ws.path, []).append(ws.id)

        for path, ws_ids in ws_paths.items():
            if len(ws_ids) > 1:
                results.append(
                    ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"Workspace path '{path}' used by multiple workspaces: "
                            f"{sorted(ws_ids)}"
                        ),
                        code="CONFLICTING_WORKSPACE_PATHS",
                    )
                )

        return results


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Imported from kailash.trust
    "ConfidentialityLevel",
    "TrustPosture",
    "TrustPostureLevel",
    # Constants
    "CONFIDENTIALITY_ORDER",
    "_CONFIDENTIALITY_ORDER",
    # Enums
    "ConstraintDimension",
    "VerificationLevel",
    # Constraint configs
    "FinancialConstraintConfig",
    "OperationalConstraintConfig",
    "TemporalConstraintConfig",
    "DataAccessConstraintConfig",
    "CommunicationConstraintConfig",
    "ConstraintEnvelopeConfig",
    # Verification gradient
    "GradientRuleConfig",
    "VerificationGradientConfig",
    # Agent / workspace / team / department
    "AgentConfig",
    "WorkspaceConfig",
    "TeamConfig",
    "DepartmentConfig",
    # Genesis / top-level
    "GenesisConfig",
    "PactConfig",
    "PlatformConfig",
    # Org definition & validation
    "ValidationSeverity",
    "ValidationResult",
    "OrgDefinition",
]

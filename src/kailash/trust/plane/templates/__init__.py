# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Constraint template ecosystem for TrustPlane.

Pre-built, tested constraint envelopes for common domains.
Each template provides a complete constraint envelope with all
five EATP dimensions configured.

Templates:
- governance: Documentation, constitution, policy work
- software: Software development with CI/CD protection
- research: Research and analysis projects
"""

from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    FinancialConstraints,
    OperationalConstraints,
    TemporalConstraints,
)

# Template registry
_TEMPLATES: dict[str, dict] = {}


def _register(name: str, description: str, detail: str, envelope_factory):
    """Register a constraint template.

    Args:
        name: Template identifier.
        description: One-line summary shown in ``attest template list``.
        detail: Multi-line Markdown explanation shown by ``attest template describe``.
        envelope_factory: Callable returning a ``ConstraintEnvelope``.
    """
    _TEMPLATES[name] = {
        "name": name,
        "description": description,
        "detail": detail,
        "factory": envelope_factory,
    }


def list_templates() -> list[dict[str, str]]:
    """List all available templates."""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in _TEMPLATES.values()
    ]


def get_template(name: str, author: str = "") -> ConstraintEnvelope:
    """Get a constraint envelope from a template.

    Args:
        name: Template name
        author: Author to sign the envelope

    Returns:
        ConstraintEnvelope configured per the template

    Raises:
        KeyError: If template not found
    """
    if name not in _TEMPLATES:
        raise KeyError(
            f"Template '{name}' not found. Available: {', '.join(_TEMPLATES.keys())}"
        )
    envelope = _TEMPLATES[name]["factory"]()
    if author:
        envelope.signed_by = author
    return envelope


def describe_template(name: str) -> str:
    """Return a detailed Markdown explanation of a template's constraints.

    Args:
        name: Template identifier.

    Returns:
        Multi-line Markdown string describing every constraint dimension.

    Raises:
        KeyError: If template not found.
    """
    if name not in _TEMPLATES:
        raise KeyError(
            f"Template '{name}' not found. Available: {', '.join(_TEMPLATES.keys())}"
        )
    tmpl = _TEMPLATES[name]
    envelope = tmpl["factory"]()

    lines: list[str] = []
    lines.append(f"# Template: {name}")
    lines.append("")
    lines.append(tmpl["description"])
    lines.append("")
    lines.append(tmpl["detail"])
    lines.append("")
    lines.append("## Constraint Dimensions")
    lines.append("")

    # Operational
    op = envelope.operational
    lines.append("### Operational")
    if op.allowed_actions:
        lines.append(f"- Allowed actions: {', '.join(op.allowed_actions)}")
    if op.blocked_actions:
        lines.append(f"- Blocked actions: {', '.join(op.blocked_actions)}")
    lines.append("")

    # Data Access
    da = envelope.data_access
    lines.append("### Data Access")
    if da.read_paths:
        lines.append(f"- Read paths: {', '.join(da.read_paths)}")
    if da.write_paths:
        lines.append(f"- Write paths: {', '.join(da.write_paths)}")
    if da.blocked_paths:
        lines.append(f"- Blocked paths: {', '.join(da.blocked_paths)}")
    if da.blocked_patterns:
        lines.append(f"- Blocked patterns: {', '.join(da.blocked_patterns)}")
    lines.append("")

    # Financial
    fin = envelope.financial
    lines.append("### Financial")
    if fin.max_cost_per_session is not None:
        lines.append(f"- Max cost per session: ${fin.max_cost_per_session:.2f}")
    if fin.max_cost_per_action is not None:
        lines.append(f"- Max cost per action: ${fin.max_cost_per_action:.2f}")
    lines.append(
        f"- Budget tracking: {'enabled' if fin.budget_tracking else 'disabled'}"
    )
    lines.append("")

    # Temporal
    temp = envelope.temporal
    lines.append("### Temporal")
    if temp.max_session_hours is not None:
        lines.append(f"- Max session length: {temp.max_session_hours} hours")
    else:
        lines.append("- Max session length: unlimited")
    if temp.allowed_hours is not None:
        lines.append(
            f"- Allowed hours: {temp.allowed_hours[0]}:00-{temp.allowed_hours[1]}:00"
        )
    if temp.cooldown_minutes > 0:
        lines.append(f"- Cooldown between sessions: {temp.cooldown_minutes} minutes")
    lines.append("")

    # Communication
    comm = envelope.communication
    lines.append("### Communication")
    if comm.allowed_channels:
        lines.append(f"- Allowed channels: {', '.join(comm.allowed_channels)}")
    if comm.blocked_channels:
        lines.append(f"- Blocked channels: {', '.join(comm.blocked_channels)}")
    if comm.requires_review:
        lines.append(f"- Requires review: {', '.join(comm.requires_review)}")
    lines.append("")

    return "\n".join(lines)


# --- Governance Template ---


def _governance_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=[
                "draft_content",
                "cross_reference",
                "format_output",
                "review_document",
                "create_analysis",
            ],
            blocked_actions=[
                "modify_constitution",
                "publish_externally",
                "delete_source_document",
                "modify_compliance_records",
            ],
        ),
        data_access=DataAccessConstraints(
            read_paths=["docs/", "workspaces/"],
            write_paths=["workspaces/"],
            blocked_paths=["docs/06-operations/constitution/"],
            blocked_patterns=["*.key", "*.env", "credentials*"],
        ),
        financial=FinancialConstraints(budget_tracking=True),
        temporal=TemporalConstraints(max_session_hours=4.0),
        communication=CommunicationConstraints(
            allowed_channels=["internal_review"],
            blocked_channels=["external_publication", "social_media"],
            requires_review=["partnership_communications"],
        ),
    )


_register(
    "governance",
    "Governance, documentation, and policy work. "
    "Protects constitution and compliance records.",
    "Designed for organizations managing policy documents, constitutions, "
    "and compliance frameworks. AI assistants can draft, review, and "
    "cross-reference documents but cannot modify foundational governance "
    "artifacts (constitutions, compliance records) or publish externally "
    "without human approval. Sessions are limited to 4 hours to encourage "
    "regular human checkpoints. Budget tracking is enabled to monitor "
    "AI usage costs across governance activities.",
    _governance_envelope,
)


# --- Software Development Template ---


def _software_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=[
                "write_code",
                "run_tests",
                "create_pr",
                "review_code",
                "format_code",
            ],
            blocked_actions=[
                "merge_to_main",
                "modify_ci_cd",
                "access_production",
                "delete_branch",
            ],
        ),
        data_access=DataAccessConstraints(
            read_paths=["src/", "tests/", "docs/"],
            write_paths=["src/", "tests/"],
            blocked_paths=[".env", "secrets/", "production/"],
            blocked_patterns=["*.key", "*.pem", "credentials*"],
        ),
        financial=FinancialConstraints(
            max_cost_per_session=10.0,
            max_cost_per_action=1.0,
            budget_tracking=True,
        ),
        temporal=TemporalConstraints(max_session_hours=8.0),
        communication=CommunicationConstraints(
            allowed_channels=["github_pr", "slack_dev"],
            blocked_channels=["external_api", "production_deploy"],
            requires_review=["github_merge"],
        ),
    )


_register(
    "software",
    "Software development with CI/CD protection. "
    "Blocks production access and force operations.",
    "Designed for software engineering teams using AI coding assistants. "
    "AI can write code, run tests, create PRs, and review code, but "
    "cannot merge to main, modify CI/CD pipelines, access production "
    "systems, or delete branches. Secrets (.env, .key, .pem, credentials) "
    "are blocked from read and write. Cost limits are set at $10/session "
    "and $1/action. Sessions are limited to 8 hours. Communication is "
    "scoped to GitHub PRs and Slack dev channels; production deploys "
    "require human action.",
    _software_envelope,
)


# --- Research Template ---


def _research_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=[
                "create_analysis",
                "draft_content",
                "cross_reference",
                "compute_statistics",
                "generate_visualization",
            ],
            blocked_actions=[
                "delete_raw_data",
                "modify_source_data",
                "publish_findings",
            ],
        ),
        data_access=DataAccessConstraints(
            read_paths=["data/", "literature/", "analysis/"],
            write_paths=["analysis/", "outputs/", "drafts/"],
            blocked_paths=["data/raw/"],
            blocked_patterns=["*.private", "participant_*"],
        ),
        financial=FinancialConstraints(budget_tracking=False),
        temporal=TemporalConstraints(),  # No session limit
        communication=CommunicationConstraints(
            blocked_channels=["publication_submission"],
            requires_review=["conference_abstract", "journal_submission"],
        ),
    )


_register(
    "research",
    "Research and analysis projects. "
    "Protects raw data and requires publication review.",
    "Designed for academic and industry research projects. AI can create "
    "analyses, draft content, cross-reference literature, compute "
    "statistics, and generate visualizations, but cannot delete or modify "
    "raw source data or publish findings without review. Private data "
    "files and participant identifiers are blocked. No session time limit "
    "is imposed (research often requires long exploratory sessions). "
    "Publication submissions and conference abstracts require explicit "
    "human review before sending.",
    _research_envelope,
)


# --- Data Pipeline Template ---


def _data_pipeline_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=[
                "read_data",
                "transform_data",
                "write_output",
                "run_pipeline",
                "create_analysis",
                "validate_schema",
            ],
            blocked_actions=[
                "delete_source_data",
                "modify_production_pipeline",
                "grant_access",
                "export_credentials",
            ],
        ),
        data_access=DataAccessConstraints(
            read_paths=["data/", "pipelines/", "configs/"],
            write_paths=["outputs/", "staging/", "logs/"],
            blocked_paths=["data/production/", "credentials/"],
            blocked_patterns=["*.key", "*.pem", "*.env", "credentials*"],
        ),
        financial=FinancialConstraints(
            max_cost_per_session=25.0,
            budget_tracking=True,
        ),
        temporal=TemporalConstraints(max_session_hours=12.0),
        communication=CommunicationConstraints(
            allowed_channels=["pipeline_alerts", "data_team"],
            blocked_channels=["external_api"],
            requires_review=["production_deploy", "schema_migration"],
        ),
    )


_register(
    "data-pipeline",
    "Data pipeline and ETL workflows. Protects source data and production pipelines.",
    "Designed for data engineering teams building ETL/ELT pipelines. AI "
    "can read, transform, and output data, run pipeline jobs, and validate "
    "schemas, but cannot delete source data, modify production pipelines, "
    "or export credentials. Production data directories and credential "
    "files are blocked. Cost is capped at $25/session (data processing "
    "can be compute-intensive). Sessions can run up to 12 hours for long "
    "batch jobs. Schema migrations and production deployments require "
    "human review.",
    _data_pipeline_envelope,
)


# --- Minimal Template ---


def _minimal_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=[],
            blocked_actions=[],
        ),
        data_access=DataAccessConstraints(
            blocked_patterns=["*.key", "*.pem", "*.env"],
        ),
        financial=FinancialConstraints(budget_tracking=False),
        temporal=TemporalConstraints(),
        communication=CommunicationConstraints(),
    )


_register(
    "minimal",
    "Minimal constraints for exploration. Only blocks credential file patterns.",
    "A near-empty constraint envelope for teams that want to start "
    "with observation rather than enforcement. The only constraints "
    "applied are blocking access to common credential file patterns "
    "(*.key, *.pem, *.env). No operational restrictions, no cost "
    "limits, no session time limits, and no communication restrictions. "
    "Ideal as a starting point — use 'attest diagnose' after a few "
    "sessions to see what constraints would be useful, then switch "
    "to a domain-specific template.",
    _minimal_envelope,
)

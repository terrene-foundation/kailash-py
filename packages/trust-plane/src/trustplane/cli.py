# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane CLI — EATP-powered trust environment for collaborative work.

Usage:
    attest init --name "My Project" --author "Jane Doe"
    attest decide --type scope --decision "Focus on X" --rationale "Because Y"
    attest milestone --version v0.1 --description "First draft" --file paper.md
    attest verify
    attest status
    attest decisions
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click

from trustplane._locking import atomic_write, safe_read_json, validate_tenant_id
from trustplane.migrate import migrate_project
from trustplane.models import (
    DecisionRecord,
    ReviewRequirement,
    _decision_type_value,
    _parse_decision_type,
)
from trustplane.project import TrustProject


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _load_project(trust_dir: str) -> TrustProject:
    """Load project with clean error handling."""
    try:
        return _run(TrustProject.load(trust_dir))
    except FileNotFoundError:
        click.echo(
            f"No project found at {trust_dir}. Run 'attest init' first.", err=True
        )
        sys.exit(1)


def _resolve_tenant_dir(trust_dir: str, tenant_id: str | None) -> str:
    """Resolve the trust directory for a given tenant.

    When a tenant is specified, the trust directory becomes a subdirectory
    of the base trust directory scoped to that tenant. This provides
    filesystem-level isolation between tenants.

    Args:
        trust_dir: Base trust plane directory.
        tenant_id: Optional tenant identifier. If None, returns the base
            trust directory unchanged (backward-compatible default).

    Returns:
        The resolved trust directory path.

    Raises:
        click.BadParameter: If the tenant ID is invalid.
    """
    if tenant_id is None:
        return trust_dir
    try:
        validate_tenant_id(tenant_id)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="'--tenant'")
    return str(Path(trust_dir) / tenant_id)


@click.group(invoke_without_command=True)
@click.option(
    "--dir",
    "trust_dir",
    default="./trust-plane",
    type=click.Path(),
    help="Trust plane directory (default: ./trust-plane)",
)
@click.option(
    "--tenant",
    "tenant_id",
    default=None,
    type=str,
    help="Tenant ID for multi-tenancy (scopes to .trust-plane/<tenant>/)",
)
@click.pass_context
def main(ctx, trust_dir, tenant_id):
    """TrustPlane — EATP-powered trust environment for collaborative work.

    Cryptographic attestation for decisions, milestones, and verification
    in human-AI collaborative projects.
    """
    ctx.ensure_object(dict)
    ctx.obj["base_trust_dir"] = trust_dir
    ctx.obj["tenant_id"] = tenant_id
    ctx.obj["trust_dir"] = _resolve_tenant_dir(trust_dir, tenant_id)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.option("--name", required=True, help="Project name")
@click.option("--author", required=True, help="Author name (the human authority)")
@click.option(
    "--constraint",
    multiple=True,
    help="Project constraints (repeatable)",
)
@click.pass_context
def init(ctx, name, author, constraint):
    """Initialize a new TrustPlane project with EATP Genesis Record."""
    trust_dir = ctx.obj["trust_dir"]
    manifest_path = Path(trust_dir) / "manifest.json"
    if manifest_path.exists():
        click.echo(f"Project already exists at {trust_dir}", err=True)
        sys.exit(1)

    project = _run(
        TrustProject.create(
            trust_dir=trust_dir,
            project_name=name,
            author=author,
            constraints=list(constraint),
        )
    )
    click.echo(f"Initialized project: {project.manifest.project_name}")
    click.echo(f"  Project ID: {project.manifest.project_id}")
    click.echo(f"  Genesis:    {project.manifest.genesis_id}")
    click.echo(f"  Trust dir:  {trust_dir}")


# Domain -> template name mapping for quickstart
_DOMAIN_TEMPLATE_MAP = {
    "web-app": "software",
    "data-pipeline": "data-pipeline",
    "research": "research",
    "custom": "minimal",
}


@main.command()
@click.option("--project-name", default=None, help="Project name")
@click.option("--author", default=None, help="Author name or organization")
@click.option(
    "--domain",
    default=None,
    type=click.Choice(["web-app", "data-pipeline", "research", "custom"]),
    help="Project domain",
)
@click.option(
    "--mode",
    "qs_mode",
    default=None,
    type=click.Choice(["shadow-first", "full-governance", "exploring"]),
    help="Setup mode",
)
@click.pass_context
def quickstart(ctx, project_name, author, domain, qs_mode):
    """Interactive setup wizard for new TrustPlane projects.

    Walks you through project setup with sensible defaults.
    Can also be run non-interactively with CLI flags.

    \b
    Examples:
        attest quickstart
        attest quickstart --project-name "My App" --author "Alice" --domain web-app --mode shadow-first
    """
    from trustplane.templates import get_template

    trust_dir = ctx.obj["trust_dir"]

    # Interactive prompts for missing values
    if project_name is None:
        project_name = click.prompt("Project name")
    if author is None:
        author = click.prompt("Author name / organization")
    if domain is None:
        domain = click.prompt(
            "Domain",
            type=click.Choice(["web-app", "data-pipeline", "research", "custom"]),
        )
    if qs_mode is None:
        qs_mode = click.prompt(
            "Mode",
            type=click.Choice(["shadow-first", "full-governance", "exploring"]),
        )

    # Validate project name is non-empty
    if not project_name.strip():
        click.echo("Project name cannot be empty.", err=True)
        sys.exit(1)
    if not author.strip():
        click.echo("Author cannot be empty.", err=True)
        sys.exit(1)

    trust_path = Path(trust_dir)
    manifest_path = trust_path / "manifest.json"
    if manifest_path.exists():
        click.echo(f"Project already exists at {trust_dir}", err=True)
        sys.exit(1)

    template_name = _DOMAIN_TEMPLATE_MAP[domain]

    if qs_mode == "shadow-first":
        # Create minimal .trust-plane directory and start shadow observer
        trust_path.mkdir(parents=True, exist_ok=True)

        # Write a minimal config for shadow mode
        from trustplane.config import TrustPlaneConfig

        config = TrustPlaneConfig(enforcement_mode="shadow")
        config.write(trust_path)

        # Initialize a project with shadow enforcement mode
        envelope = get_template(template_name, author=author)
        project = _run(
            TrustProject.create(
                trust_dir=trust_dir,
                project_name=project_name,
                author=author,
                constraint_envelope=envelope,
            )
        )

        click.echo(f"Initialized shadow-first project: {project.manifest.project_name}")
        click.echo(f"  Project ID: {project.manifest.project_id}")
        click.echo(f"  Template:   {template_name}")
        click.echo(f"  Mode:       shadow (observe only, no enforcement)")
        click.echo(f"  Trust dir:  {trust_dir}")
        click.echo()
        click.echo("Shadow mode is now active. AI actions will be observed")
        click.echo("and recorded, but never blocked.")
        click.echo()
        click.echo("Next steps:")
        click.echo("  attest shadow --report          # View shadow observations")
        click.echo("  attest diagnose                 # Analyze constraint quality")
        click.echo(
            "  attest enforce strict            # Switch to enforcement when ready"
        )

    elif qs_mode == "full-governance":
        # Create full project with domain template applied
        envelope = get_template(template_name, author=author)
        project = _run(
            TrustProject.create(
                trust_dir=trust_dir,
                project_name=project_name,
                author=author,
                constraint_envelope=envelope,
            )
        )

        # Write config file
        from trustplane.config import TrustPlaneConfig

        config = TrustPlaneConfig(enforcement_mode="strict")
        config.write(trust_path)

        # Also persist the constraint envelope as a standalone file
        project._write_json("constraint-envelope.json", envelope.to_dict())

        click.echo(
            f"Initialized full-governance project: {project.manifest.project_name}"
        )
        click.echo(f"  Project ID: {project.manifest.project_id}")
        click.echo(f"  Template:   {template_name}")
        click.echo(f"  Mode:       strict (constraints enforced)")
        click.echo(f"  Trust dir:  {trust_dir}")
        click.echo()
        click.echo("Constraint enforcement is active. Actions violating the")
        click.echo(f"'{template_name}' template will be held or blocked.")
        click.echo()
        click.echo("Next steps:")
        click.echo("  attest status                   # View project status")
        click.echo("  attest template describe " + template_name)
        click.echo("  attest decide --type scope --decision '...' --rationale '...'")

    elif qs_mode == "exploring":
        # Create project with minimal constraints
        envelope = get_template("minimal", author=author)
        project = _run(
            TrustProject.create(
                trust_dir=trust_dir,
                project_name=project_name,
                author=author,
                constraint_envelope=envelope,
            )
        )

        # Write config for shadow mode (exploring = observe, don't block)
        from trustplane.config import TrustPlaneConfig

        config = TrustPlaneConfig(enforcement_mode="shadow")
        config.write(trust_path)

        click.echo(f"Initialized exploration project: {project.manifest.project_name}")
        click.echo(f"  Project ID: {project.manifest.project_id}")
        click.echo(f"  Template:   minimal (credential patterns only)")
        click.echo(f"  Mode:       shadow (observe only)")
        click.echo(f"  Trust dir:  {trust_dir}")
        click.echo()
        click.echo("Getting started:")
        click.echo("  1. Work normally with your AI assistant")
        click.echo("  2. Run 'attest shadow --report' to see what happened")
        click.echo("  3. Run 'attest diagnose' to get constraint recommendations")
        click.echo("  4. Run 'attest template list' to see domain templates")
        click.echo(
            "  5. Run 'attest template apply <name>' when ready for real constraints"
        )


@main.command()
@click.option(
    "--type",
    "decision_type",
    required=True,
    help="Decision category (built-in: scope, argument, literature, design, policy, technical, ... or any custom string)",
)
@click.option("--decision", required=True, help="What was decided")
@click.option("--rationale", required=True, help="Why this choice was made")
@click.option(
    "--alternative", multiple=True, help="Alternatives considered (repeatable)"
)
@click.option("--risk", multiple=True, help="Known risks (repeatable)")
@click.option(
    "--grade",
    type=click.Choice([g.value for g in ReviewRequirement]),
    default="standard",
    help="Review requirement (default: standard)",
)
@click.option(
    "--confidence",
    type=click.FloatRange(0.0, 1.0),
    default=0.8,
    help="Confidence level 0.0-1.0 (default: 0.8)",
)
@click.option("--author", default="human", help="Decision author (default: human)")
@click.pass_context
def decide(
    ctx,
    decision_type,
    decision,
    rationale,
    alternative,
    risk,
    grade,
    confidence,
    author,
):
    """Record a decision with EATP audit trail."""
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    record = DecisionRecord(
        decision_type=_parse_decision_type(decision_type),
        decision=decision,
        rationale=rationale,
        alternatives=list(alternative),
        risks=list(risk),
        review_requirement=ReviewRequirement(grade),
        confidence=confidence,
        author=author,
    )

    decision_id = _run(project.record_decision(record))
    click.echo(f"Recorded decision: {decision_id}")
    click.echo(f"  Type:       {decision_type}")
    click.echo(f"  Grade:      {grade}")
    click.echo(f"  Confidence: {confidence}")


@main.command()
@click.option("--version", required=True, help="Version string (e.g., v0.1)")
@click.option("--description", required=True, help="What this milestone represents")
@click.option(
    "--file", "file_path", default="", help="File to hash for tamper detection"
)
@click.pass_context
def milestone(ctx, version, description, file_path):
    """Record a milestone with EATP audit trail."""
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    milestone_id = _run(project.record_milestone(version, description, file_path))
    click.echo(f"Recorded milestone: {milestone_id}")
    click.echo(f"  Version: {version}")


@main.command()
@click.pass_context
def verify(ctx):
    """Verify the project's EATP trust chain integrity."""
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    report = _run(project.verify())

    click.echo(f"Project: {report['project_name']} ({report['project_id']})")
    click.echo(f"Chain valid: {report['chain_valid']}")
    click.echo(f"Anchors: {report['total_anchors']}")
    click.echo(f"Decisions: {report['total_decisions']}")
    click.echo(f"Milestones: {report['total_milestones']}")
    click.echo(f"Audits: {report['total_audits']}")

    if report["integrity_issues"]:
        click.echo("\nINTEGRITY ISSUES:")
        for issue in report["integrity_issues"]:
            click.echo(f"  - {issue}")
        sys.exit(1)
    else:
        click.echo("\nNo integrity issues detected.")


@main.command()
@click.pass_context
def status(ctx):
    """Show project status."""
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)
    m = project.manifest

    click.echo(f"Project: {m.project_name}")
    click.echo(f"  ID:         {m.project_id}")
    click.echo(f"  Author:     {m.author}")
    click.echo(f"  Created:    {m.created_at.isoformat()}")
    click.echo(f"  Genesis:    {m.genesis_id}")
    click.echo(f"  Decisions:  {m.total_decisions}")
    click.echo(f"  Milestones: {m.total_milestones}")
    click.echo(f"  Audits:     {m.total_audits}")
    if m.constraints:
        click.echo(f"  Constraints: {', '.join(m.constraints)}")


@main.command()
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def decisions(ctx, json_output):
    """List all decision records."""
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    records = project.get_decisions()
    if not records:
        click.echo("No decisions recorded yet.")
        return

    if json_output:
        click.echo(json.dumps([r.to_dict() for r in records], indent=2, default=str))
    else:
        for r in records:
            click.echo(
                f"[{r.decision_id}] {_decision_type_value(r.decision_type)}: {r.decision}"
            )
            click.echo(f"  Rationale: {r.rationale}")
            click.echo(
                f"  Review: {r.review_requirement.value} | Confidence: {r.confidence}"
            )
            click.echo()


@main.command(name="export")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "html", "soc2", "iso27001", "cef", "ocsf", "syslog"]),
    default="json",
    help="Export format (default: json). soc2/iso27001 produce a ZIP evidence package. cef/ocsf/syslog for SIEM.",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    default=None,
    type=click.Path(),
    help="Output file path (default: stdout for json, auto for html/soc2/iso27001)",
)
@click.option(
    "--confidentiality",
    type=click.Choice(["public", "restricted", "confidential", "secret"]),
    default="public",
    help="Maximum confidentiality level to include (default: public)",
)
@click.option(
    "--period",
    default=None,
    help="Date range filter as START:END (ISO 8601, e.g. 2026-01-01:2026-03-31)",
)
@click.option(
    "--since",
    "since_str",
    default=None,
    help="Time filter for SIEM export: 1h, 24h, 7d (e.g. --since 24h)",
)
@click.option(
    "--host",
    default=None,
    help="Syslog server hostname (required for --format syslog)",
)
@click.option(
    "--port",
    default=514,
    type=int,
    help="Syslog server port (default: 514)",
)
@click.option(
    "--protocol",
    type=click.Choice(["udp", "tcp"]),
    default="udp",
    help="Syslog transport protocol (default: udp)",
)
@click.pass_context
def export_cmd(
    ctx, fmt, output_path, confidentiality, period, since_str, host, port, protocol
):
    """Export a VerificationBundle, compliance evidence, or SIEM events.

    \b
    For json/html formats, exports a VerificationBundle for independent verification.
    For soc2/iso27001 formats, generates a ZIP evidence package.
    For cef/ocsf formats, exports SIEM events to stdout (or --output file).
    For syslog format, streams CEF events to a syslog server.

    \b
    SIEM examples:
        attest export --format cef                    # CEF events to stdout
        attest export --format ocsf                   # OCSF JSON to stdout
        attest export --format cef --since 24h        # Last 24 hours
        attest export --format syslog --host siem.local  # Stream to syslog
    """
    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    if fmt in ("cef", "ocsf", "syslog"):
        _export_siem(ctx, project, fmt, output_path, since_str, host, port, protocol)
    elif fmt in ("soc2", "iso27001"):
        _export_compliance(ctx, project, fmt, output_path, period)
    else:
        from eatp.reasoning import ConfidentialityLevel

        from trustplane.bundle import VerificationBundle

        ceiling = ConfidentialityLevel(confidentiality)
        bundle = _run(
            VerificationBundle.create(project, confidentiality_ceiling=ceiling)
        )

        if fmt == "json":
            content = bundle.to_json()
        else:
            content = bundle.to_html()

        if output_path:
            from trustplane._locking import _safe_write_text

            _safe_write_text(Path(output_path), content)
            click.echo(f"Exported {fmt} bundle to {output_path}")
        else:
            click.echo(content)


def _parse_period(period_str: str | None) -> tuple[datetime | None, datetime | None]:
    """Parse a period string like '2026-01-01:2026-03-31' into datetimes.

    Returns:
        Tuple of (period_start, period_end). Either may be None if
        the period string is None.

    Raises:
        click.BadParameter: If the period string is malformed.
    """
    if period_str is None:
        return None, None

    from datetime import timezone

    parts = period_str.split(":")
    if len(parts) != 2:
        raise click.BadParameter(
            f"Invalid period format '{period_str}'. "
            f"Expected START:END (e.g. 2026-01-01:2026-03-31)"
        )

    try:
        start_str, end_str = parts
        period_start = datetime.fromisoformat(start_str.strip())
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise click.BadParameter(f"Invalid start date: {e}") from e

    try:
        period_end = datetime.fromisoformat(end_str.strip())
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise click.BadParameter(f"Invalid end date: {e}") from e

    return period_start, period_end


def _export_compliance(
    ctx: click.Context,
    project: "TrustProject",
    fmt: str,
    output_path: str | None,
    period: str | None,
) -> None:
    """Generate a compliance evidence ZIP package (SOC2 or ISO 27001).

    The ZIP contains:
    - evidence-summary.md
    - control-mapping.json
    - decision-log.csv
    - violation-log.csv
    - chain-verification.json
    """
    import zipfile

    from trustplane.compliance import (
        export_decisions_csv,
        export_violations_csv,
        generate_control_mapping_json,
        generate_evidence_summary_md,
        generate_iso27001_evidence,
        generate_soc2_evidence,
    )

    period_start, period_end = _parse_period(period)

    # Generate evidence
    if fmt == "soc2":
        evidence = generate_soc2_evidence(project, period_start, period_end)
    else:
        evidence = generate_iso27001_evidence(project, period_start, period_end)

    # Generate chain verification
    verification = _run(project.verify())

    # Generate evidence summary markdown
    summary_md = generate_evidence_summary_md(evidence, verification=verification)

    # Generate control mapping JSON
    control_mapping = generate_control_mapping_json(framework=fmt)

    # Generate CSVs
    decisions = project.get_decisions()
    # Apply period filter to decisions for CSV
    if period_start or period_end:
        from trustplane.compliance import _filter_by_period

        decisions = _filter_by_period(decisions, period_start, period_end)

    decisions_csv = export_decisions_csv(decisions)

    holds = project._tp_store.list_holds()
    if period_start or period_end:
        from trustplane.compliance import _filter_holds_by_period

        holds = _filter_holds_by_period(holds, period_start, period_end)

    violations_csv = export_violations_csv(holds)

    # Determine output path
    if not output_path:
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = f"trust-plane-{fmt}-evidence-{date_str}.zip"

    # Write ZIP
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence-summary.md", summary_md)
        zf.writestr(
            "control-mapping.json",
            json.dumps(control_mapping, indent=2, default=str),
        )
        zf.writestr("decision-log.csv", decisions_csv)
        zf.writestr("violation-log.csv", violations_csv)
        zf.writestr(
            "chain-verification.json",
            json.dumps(verification, indent=2, default=str),
        )

    click.echo(f"Exported {fmt.upper()} evidence package to {output_path}")
    click.echo(f"  Decisions:  {len(decisions)}")
    click.echo(f"  Violations: {len(holds)}")
    if period:
        click.echo(f"  Period:     {period}")


def _export_siem(
    ctx: click.Context,
    project: "TrustProject",
    fmt: str,
    output_path: str | None,
    since_str: str | None,
    host: str | None,
    port: int,
    protocol: str,
) -> None:
    """Export trust records in SIEM format (CEF, OCSF, or syslog).

    For cef/ocsf: writes formatted events to stdout or --output file.
    For syslog: streams CEF events to a syslog server at host:port.
    """
    import logging as _logging

    from trustplane.siem import create_syslog_handler, export_events, format_cef

    # Parse --since into a datetime
    since = None
    if since_str:
        since = _parse_duration(since_str)

    project_name = project.manifest.project_name

    if fmt == "syslog":
        if not host:
            click.echo("Error: --host is required for syslog export.", err=True)
            sys.exit(1)

        # Export as CEF and stream to syslog
        events = export_events(
            project._tp_store,
            fmt="cef",
            since=since,
            project_name=project_name,
        )

        if not events:
            click.echo("No events to export.")
            return

        syslog_handler = create_syslog_handler(host=host, port=port, protocol=protocol)
        syslog_logger = _logging.getLogger("trustplane.siem.export")
        syslog_logger.setLevel(_logging.INFO)
        syslog_logger.addHandler(syslog_handler)

        for event in events:
            syslog_logger.info(str(event))

        syslog_handler.close()
        syslog_logger.removeHandler(syslog_handler)

        click.echo(
            f"Streamed {len(events)} events to syslog at {host}:{port} ({protocol})"
        )

    else:
        # CEF or OCSF to stdout / file
        events = export_events(
            project._tp_store,
            fmt=fmt,
            since=since,
            project_name=project_name,
        )

        if not events:
            click.echo("No events to export.")
            return

        if fmt == "ocsf":
            content = json.dumps(events, indent=2, default=str)
        else:
            content = "\n".join(str(e) for e in events)

        if output_path:
            from trustplane._locking import _safe_write_text

            _safe_write_text(Path(output_path), content)
            click.echo(f"Exported {len(events)} {fmt.upper()} events to {output_path}")
        else:
            click.echo(content)


@main.command()
@click.option("--output", "-o", default=None, type=click.Path(), help="Output file")
@click.pass_context
def audit(ctx, output):
    """Generate a human-readable audit report (Markdown)."""
    from trustplane.reports import generate_audit_report

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    verification = _run(project.verify())
    report = generate_audit_report(project, verification=verification)

    if output:
        from trustplane._locking import _safe_write_text

        _safe_write_text(Path(output), report)
        click.echo(f"Audit report written to {output}")
    else:
        click.echo(report)


@main.command()
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def mirror(ctx, json_output):
    """Show the Mirror Thesis competency map.

    Analyzes execution, escalation, and intervention records to reveal
    what AI handles autonomously and where human judgment is needed.
    """
    from trustplane.mirror import (
        build_competency_map,
        competency_map_json,
        format_competency_map,
    )

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    records = project.get_mirror_records()
    cmap = build_competency_map(
        records,
        project_name=project.manifest.project_name,
    )

    if json_output:
        click.echo(competency_map_json(cmap))
    else:
        click.echo(format_competency_map(cmap))


@main.group(name="template")
@click.pass_context
def template_group(ctx):
    """Constraint template management."""
    pass


@template_group.command(name="list")
def template_list():
    """List available constraint templates."""
    from trustplane.templates import list_templates

    templates = list_templates()
    if not templates:
        click.echo("No templates available.")
        return

    for t in templates:
        click.echo(f"  {t['name']:15s}  {t['description']}")


@template_group.command(name="apply")
@click.argument("name")
@click.option("--author", default="", help="Author to sign the envelope")
@click.pass_context
def template_apply(ctx, name, author):
    """Apply a constraint template to the current project."""
    from trustplane.templates import get_template

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    if not author:
        author = project.manifest.author

    try:
        envelope = get_template(name, author=author)
    except KeyError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    # Apply envelope to project manifest and persist
    project._manifest.constraint_envelope = envelope
    project._write_json("manifest.json", project._manifest.to_dict())
    project._write_json("constraint-envelope.json", envelope.to_dict())
    click.echo(f"Applied template '{name}' to project.")
    click.echo(f"  Signed by: {envelope.signed_by}")
    click.echo(f"  Hash:      {envelope.envelope_hash()[:16]}...")


@template_group.command(name="describe")
@click.argument("name")
def template_describe(name):
    """Show detailed description of a constraint template."""
    from trustplane.templates import describe_template

    try:
        description = describe_template(name)
    except KeyError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(description)


@main.command()
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def diagnose(ctx, json_output):
    """Analyze constraint quality and generate recommendations.

    Examines the audit trail to score how well constraints are tuned.
    Identifies unused constraints, high-friction boundaries, and
    unconstrained actions.
    """
    from trustplane.diagnostics import analyze_constraints, format_diagnostics

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    envelope = project.manifest.constraint_envelope
    report = analyze_constraints(trust_dir, envelope=envelope)

    if json_output:
        click.echo(json.dumps(report, indent=2, default=str))
    else:
        click.echo(format_diagnostics(report))


@main.group(name="delegate")
@click.pass_context
def delegate_group(ctx):
    """Manage delegates for multi-stakeholder review."""
    pass


@delegate_group.command(name="add")
@click.argument("name")
@click.option(
    "--dimensions",
    required=True,
    help="Comma-separated constraint dimensions (operational,data_access,financial,temporal,communication)",
)
@click.option("--expires", default=None, help="Expiry in hours (e.g., 24)")
@click.option("--parent", default=None, help="Parent delegate ID for sub-delegation")
@click.pass_context
def delegate_add(ctx, name, dimensions, expires, parent):
    """Add a delegate with specific dimension scope."""
    from trustplane.delegation import DelegationManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)  # verify project exists

    dim_list = [d.strip() for d in dimensions.split(",")]
    expires_at = None
    if expires:
        from datetime import datetime, timedelta, timezone

        expires_at = datetime.now(timezone.utc) + timedelta(hours=float(expires))

    mgr = DelegationManager(Path(trust_dir))
    try:
        delegate = mgr.add_delegate(
            name=name,
            dimensions=dim_list,
            expires_at=expires_at,
            parent_delegate_id=parent,
        )
    except (ValueError, KeyError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Added delegate: {delegate.name}")
    click.echo(f"  ID:         {delegate.delegate_id}")
    click.echo(f"  Dimensions: {', '.join(delegate.dimensions)}")
    if expires_at:
        click.echo(f"  Expires:    {expires_at.isoformat()}")


@delegate_group.command(name="list")
@click.option("--all", "show_all", is_flag=True, help="Include revoked delegates")
@click.pass_context
def delegate_list(ctx, show_all):
    """List delegates."""
    from trustplane.delegation import DelegationManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    mgr = DelegationManager(Path(trust_dir))
    delegates = mgr.list_delegates(active_only=not show_all)

    if not delegates:
        click.echo("No delegates configured.")
        return

    for d in delegates:
        status = f" [{d.status.value}]" if d.status.value != "active" else ""
        click.echo(f"  {d.delegate_id}  {d.name}{status}")
        click.echo(f"    Dimensions: {', '.join(d.dimensions)}")


@delegate_group.command(name="revoke")
@click.argument("delegate_id")
@click.pass_context
def delegate_revoke(ctx, delegate_id):
    """Revoke a delegate (cascades to sub-delegates)."""
    from trustplane.delegation import DelegationManager

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    def _audit_callback(action: str, resource: str, context_data: dict) -> None:
        """Create an Audit Anchor for each revocation per EATP spec."""
        from eatp.chain import ActionResult

        _run(
            project._ops.audit(
                agent_id=project._agent_id,
                action=action,
                resource=resource,
                result=ActionResult.SUCCESS,
                context_data=context_data,
            )
        )

    mgr = DelegationManager(Path(trust_dir), audit_callback=_audit_callback)
    try:
        revoked = mgr.revoke_delegate(delegate_id)
    except KeyError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Revoked {len(revoked)} delegate(s): {', '.join(revoked)}")


@main.command()
@click.option(
    "--report",
    "show_report",
    is_flag=True,
    help="Generate shadow report for most recent session",
)
@click.option("--json", "as_json", is_flag=True, help="Output report as JSON")
@click.option(
    "--last",
    default=None,
    help="Duration filter for report: 1h, 24h, 7d",
)
@click.pass_context
def shadow(ctx, show_report, as_json, last):
    """Zero-config shadow mode — observe AI activity without enforcement.

    Shadow mode records tool calls, classifies them, and evaluates what
    WOULD have happened under constraint enforcement. No 'attest init'
    required — shadow data is stored separately in shadow.db.

    \b
    Examples:
        attest shadow                    # Start/show shadow mode info
        attest shadow --report           # Markdown report for latest session
        attest shadow --report --json    # JSON report for latest session
        attest shadow --report --last 7d # Weekly summary
    """
    from trustplane.shadow import generate_report, generate_report_json
    from trustplane.shadow_store import ShadowStore

    trust_dir = ctx.obj["trust_dir"]
    trust_path = Path(trust_dir)
    shadow_db = trust_path / "shadow.db"

    if show_report:
        # Report mode: show shadow observations
        if not shadow_db.exists():
            click.echo("No shadow data found. Run 'attest shadow' first.")
            return

        store = ShadowStore(shadow_db)
        store.initialize()
        try:
            since = None
            if last:
                since = _parse_duration(last)

            sessions = store.list_sessions(limit=100, since=since)
            if not sessions:
                click.echo("No shadow sessions found for the given time range.")
                return

            if as_json:
                # JSON report combining all matching sessions
                reports = [generate_report_json(s) for s in sessions]
                click.echo(json.dumps(reports, indent=2, default=str))
            else:
                # Markdown report for each session
                for session in sessions:
                    click.echo(generate_report(session))
                    click.echo()
        finally:
            store.close()
    else:
        # Info mode: show shadow mode status
        store = ShadowStore(shadow_db)
        store.initialize()
        try:
            sessions = store.list_sessions(limit=5)
            click.echo(
                "Shadow mode is available (zero-config, no 'attest init' needed)."
            )
            click.echo(f"  Shadow DB: {shadow_db}")
            click.echo(f"  Sessions recorded: {len(sessions)}")
            click.echo()
            click.echo("Shadow mode passively observes AI tool calls and evaluates")
            click.echo("what WOULD happen under constraint enforcement.")
            click.echo()
            click.echo("Commands:")
            click.echo("  attest shadow --report           # View latest report")
            click.echo("  attest shadow --report --json    # JSON format")
            click.echo("  attest shadow --report --last 7d # Last 7 days")
        finally:
            store.close()


# ============================================================================
# Shadow Management Commands (cleanup / stats)
# ============================================================================


@main.group(name="shadow-manage")
@click.pass_context
def shadow_manage_group(ctx):
    """Shadow store management — cleanup and statistics."""
    pass


@shadow_manage_group.command(name="cleanup")
@click.option(
    "--max-age",
    "max_age_days",
    default=90,
    type=int,
    show_default=True,
    help="Delete sessions older than N days",
)
@click.option(
    "--max-sessions",
    "max_sessions",
    default=10_000,
    type=int,
    show_default=True,
    help="Keep at most N sessions",
)
@click.option(
    "--max-size",
    "max_size_mb",
    default=500,
    type=int,
    show_default=True,
    help="Trigger cleanup when store exceeds N MB",
)
@click.pass_context
def shadow_cleanup(ctx, max_age_days, max_sessions, max_size_mb):
    """Remove old shadow sessions according to retention policy.

    Applies three retention rules in order:
    1. Delete sessions older than --max-age days.
    2. Keep at most --max-sessions sessions (oldest removed first).
    3. If the database exceeds --max-size MB, remove oldest sessions until under limit.

    Cleanup is atomic — sessions and their tool calls are deleted together.

    \b
    Examples:
        attest shadow-manage cleanup                   # Defaults: 90d / 10k / 500MB
        attest shadow-manage cleanup --max-age 30      # Keep only last 30 days
        attest shadow-manage cleanup --max-sessions 100 --max-size 50
    """
    from trustplane.shadow_store import ShadowStore

    trust_dir = ctx.obj["trust_dir"]
    trust_path = Path(trust_dir)
    shadow_db = trust_path / "shadow.db"

    if not shadow_db.exists():
        click.echo("No shadow data found. Nothing to clean up.")
        return

    store = ShadowStore(shadow_db)
    store.initialize()
    try:
        removed = store.cleanup(
            max_age_days=max_age_days,
            max_sessions=max_sessions,
            max_size_mb=max_size_mb,
        )
        if removed > 0:
            click.echo(f"Cleaned up {removed} session(s).")
        else:
            click.echo("No sessions needed cleanup.")
    finally:
        store.close()


@shadow_manage_group.command(name="stats")
@click.option("--json", "as_json", is_flag=True, help="Output stats as JSON")
@click.pass_context
def shadow_stats(ctx, as_json):
    """Show shadow store statistics.

    Displays session count, tool call count, age range, and disk usage.

    \b
    Examples:
        attest shadow-manage stats           # Human-readable output
        attest shadow-manage stats --json    # JSON output
    """
    from trustplane.shadow_store import ShadowStore

    trust_dir = ctx.obj["trust_dir"]
    trust_path = Path(trust_dir)
    shadow_db = trust_path / "shadow.db"

    if not shadow_db.exists():
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "session_count": 0,
                        "tool_call_count": 0,
                        "oldest_session": None,
                        "newest_session": None,
                        "disk_usage_bytes": 0,
                    },
                    indent=2,
                )
            )
        else:
            click.echo("No shadow data found.")
        return

    store = ShadowStore(shadow_db)
    store.initialize()
    try:
        info = store.stats()
        if as_json:
            click.echo(json.dumps(info, indent=2))
        else:
            click.echo(f"Shadow Store: {shadow_db}")
            click.echo(f"  Sessions:    {info['session_count']}")
            click.echo(f"  Tool calls:  {info['tool_call_count']}")
            click.echo(f"  Oldest:      {info['oldest_session'] or 'N/A'}")
            click.echo(f"  Newest:      {info['newest_session'] or 'N/A'}")
            disk_mb = info["disk_usage_bytes"] / (1024 * 1024)
            click.echo(f"  Disk usage:  {disk_mb:.2f} MB")
    finally:
        store.close()


def _parse_duration(duration_str: str) -> datetime:
    """Parse a duration string like '1h', '24h', '7d' into a datetime.

    Returns a datetime representing 'now - duration'.
    """
    from datetime import timedelta

    duration_str = duration_str.strip().lower()
    if duration_str.endswith("d"):
        days = int(duration_str[:-1])
        delta = timedelta(days=days)
    elif duration_str.endswith("h"):
        hours = int(duration_str[:-1])
        delta = timedelta(hours=hours)
    elif duration_str.endswith("m"):
        minutes = int(duration_str[:-1])
        delta = timedelta(minutes=minutes)
    else:
        raise click.BadParameter(
            f"Invalid duration '{duration_str}'. Use format like 1h, 24h, 7d."
        )

    from datetime import timezone

    return datetime.now(timezone.utc) - delta


@main.command()
@click.argument("mode", type=click.Choice(["strict", "shadow"]))
@click.pass_context
def enforce(ctx, mode):
    """Switch enforcement mode (strict or shadow).

    strict: Actions that violate constraints are HELD or BLOCKED.
    shadow: Actions are recorded but never blocked.
    """
    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)  # Validate project exists

    config_path = Path(trust_dir) / "config.json"
    config = {}
    if config_path.exists():
        config = safe_read_json(config_path)
    config["enforcement_mode"] = mode
    atomic_write(config_path, config)
    click.echo(f"Enforcement mode set to: {mode}")


@main.group(name="hold")
@click.pass_context
def hold_group(ctx):
    """Manage held actions awaiting approval."""
    pass


@hold_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def hold_list(ctx, as_json):
    """List active holds awaiting resolution."""
    from trustplane.holds import HoldManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    mgr = HoldManager(Path(trust_dir))
    holds = mgr.list_pending()

    if not holds:
        click.echo("No pending holds.")
        return

    if as_json:
        click.echo(json.dumps([h.to_dict() for h in holds], indent=2, default=str))
    else:
        for h in holds:
            click.echo(f"  {h.hold_id}  {h.action}")
            click.echo(f"    Resource: {h.resource}")
            click.echo(f"    Reason:   {h.reason}")
            click.echo(f"    Created:  {h.created_at.isoformat()}")
            click.echo()


@hold_group.command(name="approve")
@click.argument("hold_id")
@click.option("--approver", default=None, help="Name of the approver")
@click.pass_context
def hold_approve(ctx, hold_id, approver):
    """Approve a held action."""
    from trustplane.holds import HoldManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    if not approver:
        approver = "human"

    mgr = HoldManager(Path(trust_dir))
    try:
        hold = mgr.resolve(
            hold_id, approved=True, resolved_by=approver, reason="Approved via CLI"
        )
    except (KeyError, ValueError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Hold {hold.hold_id} approved by {approver}.")


@hold_group.command(name="deny")
@click.argument("hold_id")
@click.option("--reason", required=True, help="Reason for denial")
@click.pass_context
def hold_deny(ctx, hold_id, reason):
    """Deny a held action."""
    from trustplane.holds import HoldManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    mgr = HoldManager(Path(trust_dir))
    try:
        hold = mgr.resolve(hold_id, approved=False, resolved_by="human", reason=reason)
    except (KeyError, ValueError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Hold {hold.hold_id} denied. Reason: {reason}")


@main.command()
@click.option(
    "--to",
    "target",
    type=click.Choice(["sqlite"]),
    default=None,
    help="Target store backend (e.g., sqlite)",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be migrated without writing"
)
@click.option(
    "--confirm-delete",
    is_flag=True,
    help="Delete filesystem record data after successful migration",
)
@click.pass_context
def migrate(ctx, target, dry_run, confirm_delete):
    """Migrate project data between store backends.

    Without --to, migrates a pre-v0.2.1 project to FilesystemStore format.
    With --to sqlite, migrates filesystem records into a SQLite database.
    """
    trust_dir = ctx.obj["trust_dir"]
    trust_path = Path(trust_dir)
    if not (trust_path / "manifest.json").exists():
        click.echo(
            f"No project found at {trust_dir}. Run 'attest init' first.", err=True
        )
        sys.exit(1)

    if target == "sqlite":
        from trustplane.migrate import migrate_to_sqlite

        result = migrate_to_sqlite(
            trust_dir, dry_run=dry_run, confirm_delete=confirm_delete
        )
        status = result["status"]
        counts = result.get("counts", {})

        if status == "already_sqlite":
            click.echo("Project already uses SQLite store.")
        elif status == "dry_run":
            click.echo("Dry run — no changes made.")
            for record_type, count in counts.items():
                click.echo(f"  {record_type}: {count}")
        elif status == "migrated":
            click.echo("Migration to SQLite complete.")
            for record_type, count in counts.items():
                click.echo(f"  {record_type}: {count}")
            if confirm_delete:
                click.echo("  Filesystem record data deleted.")
            click.echo("  Run 'attest verify' to confirm integrity.")
        elif status == "error":
            click.echo(f"Migration failed: {result['message']}", err=True)
            sys.exit(1)
    else:
        # Legacy migration (pre-v0.2.1 → FilesystemStore)
        result = _run(migrate_project(trust_dir))

        status = result["status"]
        if status == "already_migrated":
            click.echo(f"Project '{result['project_name']}' is already migrated.")
        elif status == "marked":
            click.echo(f"Project '{result['project_name']}': {result['message']}")
        elif status == "migrated":
            click.echo(f"Migrated project '{result['project_name']}'.")
            click.echo(f"  Anchors updated: {result['anchors_updated']}")
            click.echo("  Run 'attest verify' to confirm chain integrity.")
        elif status == "error":
            click.echo(f"Migration failed: {result['message']}", err=True)
            sys.exit(1)


@main.group(name="integration")
@click.pass_context
def integration_group(ctx):
    """IDE and tool integration management."""
    pass


@integration_group.group(name="setup")
@click.pass_context
def integration_setup_group(ctx):
    """Set up integrations with AI-powered IDEs and tools."""
    pass


@integration_setup_group.command(name="cursor")
@click.option(
    "--mode",
    type=click.Choice(["shadow", "strict"]),
    default="shadow",
    help="Enforcement mode (default: shadow)",
)
@click.option(
    "--merge",
    is_flag=True,
    help="Merge with existing .cursorrules instead of overwriting",
)
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    help="Project root directory (default: current directory)",
)
@click.pass_context
def integration_setup_cursor(ctx, mode, merge, project_dir):
    """Set up Cursor IDE integration with TrustPlane.

    Configures Cursor to enforce trust constraints:
    \b
    1. Generates .cursorrules with trust enforcement rules
    2. Configures MCP server in .cursor/mcp.json
    3. Installs pre-tool hook script

    \b
    Examples:
        attest integration setup cursor                    # Shadow mode (default)
        attest integration setup cursor --mode strict      # Strict enforcement
        attest integration setup cursor --merge            # Merge with existing .cursorrules
    """
    from trustplane.integration.cursor import setup_cursor

    trust_dir = ctx.obj["trust_dir"]
    project_path = Path(project_dir)
    cursorrules_path = project_path / ".cursorrules"

    # If .cursorrules exists and --merge not set, ask for confirmation
    if cursorrules_path.exists() and not merge:
        click.echo(f"Found existing {cursorrules_path}")
        if not click.confirm(
            "Overwrite? (Use --merge to append instead)", default=False
        ):
            click.echo("Aborted. Use --merge to append TrustPlane rules.")
            return

    result = setup_cursor(
        project_dir=project_path,
        trust_dir=trust_dir,
        mode=mode,
        merge=merge,
    )

    click.echo(f"Cursor integration configured ({mode} mode):")
    click.echo(f"  .cursorrules: {result['cursorrules_action']}")
    click.echo(
        f"  MCP server:   {'configured' if result['mcp_configured'] else 'skipped'}"
    )
    click.echo(
        f"  Hook script:  {'installed' if result['hook_installed'] else 'skipped'}"
    )
    click.echo()
    click.echo("Files written:")
    for f in result["files_written"]:
        click.echo(f"  {f}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Open your project in Cursor")
    click.echo("  2. Cursor will auto-detect .cursorrules and MCP config")
    click.echo("  3. The AI will now check trust constraints before actions")
    click.echo()
    if mode == "shadow":
        click.echo("  Shadow mode: Actions are logged but never blocked.")
        click.echo("  Run 'attest shadow --report' to review observations.")
        click.echo("  Switch to strict: attest integration setup cursor --mode strict")
    else:
        click.echo("  Strict mode: Actions violating constraints are blocked.")
        click.echo("  Run 'attest hold list' to see pending holds.")
        click.echo("  Switch to shadow: attest integration setup cursor --mode shadow")


@main.group(name="tenants")
@click.pass_context
def tenants_group(ctx):
    """Manage tenants for multi-tenancy isolation."""
    pass


@tenants_group.command(name="list")
@click.pass_context
def tenants_list(ctx):
    """List all tenant directories under the trust-plane root."""
    base_dir = Path(ctx.obj["base_trust_dir"])

    if not base_dir.exists():
        click.echo(f"Trust plane directory does not exist: {base_dir}")
        return

    tenants: list[str] = []
    try:
        for entry in sorted(base_dir.iterdir()):
            if entry.is_dir():
                # A tenant directory must contain a manifest.json or trust.db
                # to be considered initialized. But we list all subdirectories
                # that have valid tenant-id names (no special files like keys/).
                name = entry.name
                try:
                    validate_tenant_id(name)
                    tenants.append(name)
                except ValueError:
                    # Skip directories with invalid tenant names (e.g. "keys",
                    # "chains", "decisions" — these are project subdirectories)
                    continue
    except OSError as e:
        click.echo(f"Error reading {base_dir}: {e}", err=True)
        sys.exit(1)

    if not tenants:
        click.echo("No tenants found.")
        return

    click.echo(f"Tenants ({len(tenants)}):")
    for t in tenants:
        tenant_dir = base_dir / t
        # Check if initialized
        has_manifest = (tenant_dir / "manifest.json").exists()
        status = "initialized" if has_manifest else "empty"
        click.echo(f"  {t}  [{status}]")


@tenants_group.command(name="create")
@click.argument("name")
@click.pass_context
def tenants_create(ctx, name):
    """Create a new tenant directory and initialize the store.

    Creates the tenant directory under the trust-plane root and
    sets up the SQLite store for the tenant.
    """
    try:
        validate_tenant_id(name)
    except ValueError as e:
        click.echo(f"Invalid tenant ID: {e}", err=True)
        sys.exit(1)

    base_dir = Path(ctx.obj["base_trust_dir"])
    tenant_dir = base_dir / name

    if tenant_dir.exists():
        click.echo(f"Tenant directory already exists: {tenant_dir}", err=True)
        sys.exit(1)

    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Initialize SQLite store for the tenant
    from trustplane.store.sqlite import SqliteTrustPlaneStore

    db_path = tenant_dir / "trust.db"
    store = SqliteTrustPlaneStore(db_path)
    store.initialize()
    store.close()

    click.echo(f"Created tenant: {name}")
    click.echo(f"  Directory: {tenant_dir}")
    click.echo(f"  Store:     {db_path}")
    click.echo()
    click.echo(f"Initialize a project in this tenant:")
    click.echo(f'  attest --tenant {name} init --name "My Project" --author "Author"')


@main.command()
@click.option(
    "--port",
    default=8080,
    type=int,
    help="Port to bind on (default: 8080)",
)
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    help="Open dashboard in default browser",
)
@click.option(
    "--no-auth",
    "no_auth",
    is_flag=True,
    help="Disable bearer token authentication (NOT recommended)",
)
@click.pass_context
def dashboard(ctx, port, open_browser, no_auth):
    """Start a web-based trust status dashboard.

    Serves a read-only HTML dashboard on localhost showing decisions,
    milestones, holds, and verification status.

    API endpoints require bearer token authentication by default.
    The token is generated on first start and displayed in the terminal.
    Use --no-auth to disable (prints a security warning).

    \b
    Examples:
        attest dashboard                 # Start on port 8080
        attest dashboard --port 9090     # Custom port
        attest dashboard --open          # Auto-open browser
        attest dashboard --no-auth       # Disable API auth (not recommended)
    """
    from trustplane.dashboard import serve_dashboard

    trust_dir = ctx.obj["trust_dir"]

    # Verify project exists before starting server
    _load_project(trust_dir)

    serve_dashboard(
        trust_dir=trust_dir,
        port=port,
        open_browser=open_browser,
        no_auth=no_auth,
    )


# ============================================================================
# Identity (OIDC) Commands
# ============================================================================


@main.group(name="identity")
@click.pass_context
def identity_group(ctx):
    """Manage OIDC identity provider configuration."""
    pass


@identity_group.command(name="setup")
@click.option(
    "--issuer", required=True, help="OIDC issuer URL (e.g., https://dev-12345.okta.com)"
)
@click.option("--client-id", required=True, help="OAuth2 client ID")
@click.option(
    "--provider",
    type=click.Choice(["okta", "azure_ad", "google", "generic_oidc"]),
    default="generic_oidc",
    help="Provider type (default: generic_oidc)",
)
@click.option(
    "--domain", default=None, help="IdP domain (auto-detected from issuer if omitted)"
)
@click.pass_context
def identity_setup(ctx, issuer, client_id, provider, domain):
    """Configure an OIDC identity provider.

    \b
    Examples:
        attest identity setup --issuer https://dev-123.okta.com --client-id abc123
        attest identity setup --issuer https://login.microsoftonline.com/tenant --client-id abc --provider azure_ad
    """
    from urllib.parse import urlparse

    from trustplane.identity import IdentityConfig, IdentityProvider

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    if domain is None:
        parsed = urlparse(issuer)
        domain = parsed.hostname or issuer

    try:
        idp = IdentityProvider(
            provider_type=provider,
            domain=domain,
            client_id=client_id,
            issuer_url=issuer,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    config_path = Path(trust_dir) / "identity-config.json"
    config = IdentityConfig(config_path)
    config.configure(idp)

    click.echo(f"OIDC identity provider configured:")
    click.echo(f"  Provider: {provider}")
    click.echo(f"  Domain:   {domain}")
    click.echo(f"  Issuer:   {issuer}")
    click.echo(f"  Client:   {client_id}")


@identity_group.command(name="status")
@click.pass_context
def identity_status(ctx):
    """Show current OIDC identity configuration.

    \b
    Examples:
        attest identity status
    """
    from trustplane.identity import IdentityConfig

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    config_path = Path(trust_dir) / "identity-config.json"
    config = IdentityConfig(config_path)

    if not config.is_configured():
        click.echo("No OIDC identity provider configured.")
        click.echo(
            "Run 'attest identity setup --issuer <url> --client-id <id>' to configure."
        )
        return

    provider = config.get_provider()
    click.echo("OIDC Identity Configuration:")
    click.echo(f"  Provider: {provider.provider_type}")
    click.echo(f"  Domain:   {provider.domain}")
    click.echo(f"  Issuer:   {provider.issuer_url}")
    click.echo(f"  Client:   {provider.client_id}")


@identity_group.command(name="verify")
@click.argument("token")
@click.pass_context
def identity_verify(ctx, token):
    """Verify a JWT token against the configured OIDC provider.

    TOKEN is the encoded JWT string to verify.

    \b
    Examples:
        attest identity verify eyJhbGciOiJSUzI1NiI...
    """
    from trustplane.identity import (
        IdentityConfig,
        JWKSProvider,
        OIDCVerifier,
        TokenVerificationError,
    )

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    config_path = Path(trust_dir) / "identity-config.json"
    config = IdentityConfig(config_path)

    if not config.is_configured():
        click.echo("No OIDC identity provider configured.", err=True)
        click.echo("Run 'attest identity setup' first.", err=True)
        sys.exit(1)

    provider = config.get_provider()

    # Use JWKS auto-discovery
    jwks = JWKSProvider(issuer_url=provider.issuer_url)
    verifier = OIDCVerifier(provider=provider, jwks_provider=jwks)

    try:
        claims = verifier.verify_token(token)
    except TokenVerificationError as e:
        click.echo(f"Token verification FAILED: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Verification error: {e}", err=True)
        sys.exit(1)

    click.echo("Token verification PASSED")
    click.echo()
    click.echo("Claims:")
    for key, value in sorted(claims.items()):
        click.echo(f"  {key}: {value}")


# ============================================================================
# RBAC Commands
# ============================================================================


@main.group(name="rbac")
@click.pass_context
def rbac_group(ctx):
    """Manage role-based access control."""
    pass


@rbac_group.command(name="assign")
@click.argument("user_id")
@click.argument("role")
@click.pass_context
def rbac_assign(ctx, user_id, role):
    """Assign a role to a user.

    \b
    Roles: admin, auditor, delegate, observer

    \b
    Examples:
        attest rbac assign alice admin
        attest rbac assign bob auditor
    """
    from trustplane.rbac import RBACError, RBACManager, Role

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    try:
        role_enum = Role(role.lower())
    except ValueError:
        valid = ", ".join(r.value for r in Role)
        click.echo(f"Invalid role '{role}'. Valid roles: {valid}", err=True)
        sys.exit(1)

    rbac_path = Path(trust_dir) / "rbac.json"
    mgr = RBACManager(rbac_path)
    try:
        mgr.assign_role(user_id, role_enum)
    except (ValueError, RBACError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Assigned role '{role_enum.value}' to user '{user_id}'")


@rbac_group.command(name="revoke")
@click.argument("user_id")
@click.pass_context
def rbac_revoke(ctx, user_id):
    """Revoke a user's role.

    \b
    Examples:
        attest rbac revoke alice
    """
    from trustplane.rbac import RBACError, RBACManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    rbac_path = Path(trust_dir) / "rbac.json"
    mgr = RBACManager(rbac_path)
    try:
        mgr.revoke_role(user_id)
    except (ValueError, RBACError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Revoked role for user '{user_id}'")


@rbac_group.command(name="list")
@click.pass_context
def rbac_list(ctx):
    """List all role assignments.

    \b
    Examples:
        attest rbac list
    """
    from trustplane.rbac import RBACManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    rbac_path = Path(trust_dir) / "rbac.json"
    mgr = RBACManager(rbac_path)
    assignments = mgr.list_assignments()

    if not assignments:
        click.echo("No role assignments configured.")
        return

    click.echo(f"{'USER ID':<30} {'ROLE':<15}")
    click.echo("-" * 45)
    for entry in assignments:
        click.echo(f"{entry['user_id']:<30} {entry['role']:<15}")


@rbac_group.command(name="check")
@click.argument("user_id")
@click.argument("operation")
@click.pass_context
def rbac_check(ctx, user_id, operation):
    """Check if a user has permission for an operation.

    \b
    Operations: decide, milestone, verify, status, export,
                hold_approve, hold_deny, shadow, init, migrate,
                rbac_assign, decisions

    \b
    Examples:
        attest rbac check alice decide
        attest rbac check bob export
    """
    from trustplane.rbac import OPERATIONS, RBACManager

    trust_dir = ctx.obj["trust_dir"]
    _load_project(trust_dir)

    if operation not in OPERATIONS:
        valid = ", ".join(sorted(OPERATIONS))
        click.echo(
            f"Unknown operation '{operation}'. Valid operations: {valid}", err=True
        )
        sys.exit(1)

    rbac_path = Path(trust_dir) / "rbac.json"
    mgr = RBACManager(rbac_path)

    try:
        allowed = mgr.check_permission(user_id, operation)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    if allowed:
        role = mgr.get_role(user_id)
        click.echo(
            f"ALLOWED: user '{user_id}' (role={role.value}) may perform '{operation}'"
        )
    else:
        role = mgr.get_role(user_id)
        role_str = role.value if role else "none"
        click.echo(
            f"DENIED: user '{user_id}' (role={role_str}) may not perform '{operation}'"
        )
        sys.exit(1)


# ============================================================================
# SIEM Commands
# ============================================================================


@main.group(name="siem")
@click.pass_context
def siem_group(ctx):
    """SIEM integration and testing."""
    pass


@siem_group.command(name="test")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["cef", "ocsf"]),
    default="cef",
    help="Output format (default: cef)",
)
@click.option(
    "--target",
    type=click.Choice(["splunk", "sentinel", "qradar", "syslog"]),
    default="syslog",
    help="SIEM target (default: syslog)",
)
@click.option(
    "--host",
    default="localhost",
    help="Syslog host (default: localhost)",
)
@click.option(
    "--port",
    "siem_port",
    default=514,
    type=int,
    help="Syslog port (default: 514)",
)
@click.option(
    "--send",
    is_flag=True,
    help="Actually transmit the test event (dry-run by default)",
)
@click.option(
    "--tls",
    is_flag=True,
    help="Use TLS-encrypted syslog (RFC 5425, port 6514 by default)",
)
@click.option(
    "--ca-cert",
    default=None,
    type=click.Path(exists=True),
    help="Path to CA certificate for TLS verification",
)
@click.option(
    "--client-cert",
    default=None,
    type=click.Path(exists=True),
    help="Path to client certificate for mutual TLS",
)
@click.option(
    "--client-key",
    default=None,
    type=click.Path(exists=True),
    help="Path to client private key for mutual TLS",
)
@click.pass_context
def siem_test(
    ctx, fmt, target, host, siem_port, send, tls, ca_cert, client_cert, client_key
):
    """Send a test event to verify SIEM connectivity.

    By default, displays the formatted test event without sending.
    Use --send to actually transmit to the configured endpoint.

    \b
    Examples:
        attest siem test                                 # Show CEF test event
        attest siem test --format ocsf                   # Show OCSF test event
        attest siem test --target splunk --send           # Send to Splunk
        attest siem test --host siem.local --port 514 --send
    """
    import logging as _logging

    from trustplane.models import DecisionRecord, DecisionType, ReviewRequirement
    from trustplane.siem import create_syslog_handler, format_cef, format_ocsf

    # Create a test decision record
    test_record = DecisionRecord(
        decision_type=DecisionType.SCOPE,
        decision="SIEM connectivity test",
        rationale="Verifying SIEM integration is working",
        confidence=1.0,
        review_requirement=ReviewRequirement.QUICK,
    )

    project_name = "siem-test"
    formatted_dict: dict = {}

    if fmt == "cef":
        event_str = format_cef(test_record, project_name=project_name)
        click.echo("CEF Test Event:")
        click.echo(event_str)
    else:
        formatted_dict = format_ocsf(test_record, project_name=project_name)
        event_str = json.dumps(formatted_dict, indent=2)
        click.echo("OCSF Test Event:")
        click.echo(event_str)

    if send:
        click.echo()
        if tls:
            from trustplane.siem import TLSSyslogError, create_tls_syslog_handler

            tls_port = siem_port if siem_port != 514 else 6514
            click.echo(f"Sending to {target} at {host}:{tls_port} via TLS...")
            try:
                handler = create_tls_syslog_handler(
                    host=host,
                    port=tls_port,
                    ca_cert=ca_cert,
                    client_cert=client_cert,
                    client_key=client_key,
                )
                test_logger = _logging.getLogger("trustplane.siem.test")
                test_logger.addHandler(handler)
                test_logger.setLevel(_logging.INFO)

                send_str = event_str if fmt == "cef" else json.dumps(formatted_dict)
                test_logger.info(send_str)
                handler.close()
                test_logger.removeHandler(handler)
                click.echo(f"Test event sent to {host}:{tls_port} via TLS")
            except TLSSyslogError as e:
                click.echo(f"TLS connection failed: {e}", err=True)
                click.echo()
                click.echo("Troubleshooting:")
                click.echo(f"  1. Verify {host}:{tls_port} accepts TLS connections")
                click.echo("  2. Check CA certificate if using custom PKI (--ca-cert)")
                click.echo(
                    "  3. Verify client cert/key for mutual TLS (--client-cert, --client-key)"
                )
                sys.exit(1)
            except Exception as e:
                click.echo(f"Failed to send test event: {e}", err=True)
                sys.exit(1)
        else:
            protocol = "tcp" if target in ("splunk", "sentinel") else "udp"
            click.echo(
                f"Sending to {target} at {host}:{siem_port} via {protocol.upper()}..."
            )
            try:
                handler = create_syslog_handler(
                    host=host, port=siem_port, protocol=protocol
                )
                test_logger = _logging.getLogger("trustplane.siem.test")
                test_logger.addHandler(handler)
                test_logger.setLevel(_logging.INFO)

                send_str = event_str if fmt == "cef" else json.dumps(formatted_dict)
                test_logger.info(send_str)
                handler.close()
                test_logger.removeHandler(handler)
                click.echo(
                    f"Test event sent to {host}:{siem_port} via {protocol.upper()}"
                )
            except Exception as e:
                click.echo(f"Failed to send test event: {e}", err=True)
                click.echo()
                click.echo("Troubleshooting:")
                click.echo(f"  1. Verify {host}:{siem_port} is reachable")
                click.echo(
                    f"  2. Check firewall rules for {protocol.upper()} port {siem_port}"
                )
                click.echo(f"  3. Verify the {target} collector is running")
                sys.exit(1)
    else:
        click.echo()
        click.echo("(Dry-run mode. Use --send to transmit the event.)")


# ============================================================================
# Archive Commands
# ============================================================================


@main.group(name="archive")
@click.pass_context
def archive_group(ctx):
    """Manage store archives for old records."""
    pass


@archive_group.command(name="create")
@click.option(
    "--max-age-days",
    default=365,
    type=int,
    help="Archive records older than this many days (default: 365)",
)
@click.pass_context
def archive_create(ctx, max_age_days):
    """Archive old records to a ZIP bundle.

    Moves decisions, milestones, and resolved holds older than --max-age-days
    to a compressed archive in {trust_dir}/archives/. Archived records are
    removed from the live store but remain verifiable via the bundle manifest.
    """
    from trustplane.archive import ArchiveError, create_archive

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    try:
        bundle = create_archive(project._tp_store, trust_dir, max_age_days=max_age_days)
    except ArchiveError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    total = sum(bundle.record_counts.values())
    click.echo(f"Created archive: {bundle.bundle_id}")
    click.echo(f"  Records:    {total}")
    click.echo(f"  Decisions:  {bundle.record_counts.get('decisions', 0)}")
    click.echo(f"  Milestones: {bundle.record_counts.get('milestones', 0)}")
    click.echo(f"  Holds:      {bundle.record_counts.get('holds', 0)}")
    click.echo(f"  Date range: {bundle.date_range[0]} to {bundle.date_range[1]}")
    click.echo(f"  SHA-256:    {bundle.sha256_hash[:16]}...")


@archive_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def archive_list(ctx, as_json):
    """List archived bundles."""
    from trustplane.archive import list_archives

    trust_dir = ctx.obj["trust_dir"]

    bundles = list_archives(trust_dir)

    if not bundles:
        click.echo("No archives found.")
        return

    if as_json:
        click.echo(json.dumps([b.to_dict() for b in bundles], indent=2, default=str))
    else:
        for b in bundles:
            total = sum(b.record_counts.values())
            click.echo(f"  {b.bundle_id}  ({total} records)")
            click.echo(f"    Created:    {b.created_at.isoformat()}")
            click.echo(f"    Date range: {b.date_range[0]} to {b.date_range[1]}")
            click.echo(f"    SHA-256:    {b.sha256_hash[:16]}...")
            click.echo()


@archive_group.command(name="restore")
@click.argument("bundle_id")
@click.pass_context
def archive_restore(ctx, bundle_id):
    """Restore records from an archive bundle.

    Brings archived records back into the live store and removes
    the archive ZIP file.
    """
    from trustplane.archive import ArchiveError, restore_archive

    trust_dir = ctx.obj["trust_dir"]
    project = _load_project(trust_dir)

    try:
        count = restore_archive(project._tp_store, trust_dir, bundle_id)
    except (ArchiveError, ValueError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"Restored {count} records from archive {bundle_id}.")


if __name__ == "__main__":
    main()

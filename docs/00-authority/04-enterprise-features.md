# Trust-Plane Enterprise Features

## SIEM Integration

Export trust records to enterprise SIEM platforms via CEF v0 and OCSF 1.1 formats.

### Supported Formats

| Format   | Target Platforms             | Function                            |
| -------- | ---------------------------- | ----------------------------------- |
| CEF v0   | Splunk, QRadar, ArcSight     | `format_cef(record, project_name)`  |
| OCSF 1.1 | CrowdStrike Falcon, Sentinel | `format_ocsf(record, project_name)` |
| Syslog   | Any syslog receiver          | `create_syslog_handler(host, port)` |

### Supported Record Types

All trust record types can be exported: DecisionRecord, MilestoneRecord, HoldRecord, ExecutionRecord, EscalationRecord, InterventionRecord.

```python
from kailash.trust.plane.siem import format_cef, format_ocsf, export_events

# Single record
cef_line = format_cef(decision_record, project_name="research-project")

# Bulk export since a timestamp
events = export_events(store, format="cef", since=datetime(2026, 1, 1))
```

## Compliance Mapping

SOC2 Trust Services Criteria and ISO 27001 Annex A evidence mapping with GRC export.

### SOC2 Control Mapping

| Record Type        | SOC2 Control | Description                      |
| ------------------ | ------------ | -------------------------------- |
| DecisionRecord     | CC6.7        | Restriction of Privileged Access |
| MilestoneRecord    | CC7.2        | System Monitoring                |
| ExecutionRecord    | CC6.8        | Monitoring                       |
| HELD/BLOCKED       | CC7.3        | Evaluation of Security Events    |
| Delegation records | CC6.3        | Removal of Access                |
| Genesis record     | CC6.2        | Inventory of Information Assets  |

### ISO 27001 Control Mapping

| Record Type     | ISO 27001 Control | Description                                  |
| --------------- | ----------------- | -------------------------------------------- |
| DecisionRecord  | A.9.2             | User Access Management                       |
| MilestoneRecord | A.12.4            | Logging and Monitoring                       |
| HELD/BLOCKED    | A.16.1            | Management of Information Security Incidents |

### Export

```python
from kailash.trust.plane.compliance import export_soc2_evidence, export_iso27001_evidence

soc2_csv = export_soc2_evidence(store, format="csv")
iso_json = export_iso27001_evidence(store, format="json")
```

## Shadow Mode

Zero-config observation of AI activity. Records what tools are called, classifies them, and reports what WOULD have happened under constraint enforcement.

Shadow mode does NOT require `attest init`. Shadow data is stored in `.trust-plane/shadow.db` (separate from the main trust database).

```python
from kailash.trust.plane.shadow import ShadowObserver, ShadowSession

observer = ShadowObserver()
session = ShadowSession(session_id="s1")

# Record AI tool calls
observer.record(session, action="Read", resource="/src/main.py")
observer.record(session, action="Write", resource="/src/utils.py")

# Generate report: what would have been held/blocked
report = observer.generate_report(session)
```

### Shadow vs Strict Mode

| Feature                | Shadow Mode       | Strict Mode |
| ---------------------- | ----------------- | ----------- |
| Records activity       | Yes               | Yes         |
| Enforces constraints   | No (reports only) | Yes         |
| Requires `attest init` | No                | Yes         |
| Data location          | `shadow.db`       | `trust.db`  |

Configure in `.trustplane.toml`:

```toml
[enforcement]
mode = "shadow"  # or "strict"

[shadow]
report_schedule = "daily"  # daily, weekly, never
report_output = "file"     # stdout, file
```

## Dashboard

Web-based trust status dashboard using stdlib `http.server`. Binds to `127.0.0.1` only (never `0.0.0.0`).

```bash
attest dashboard --port 8080
```

```python
from kailash.trust.plane.dashboard import serve_dashboard
serve_dashboard(trust_dir=".trust-plane", port=8080)
```

Shows: recent decisions, milestone timeline, active holds, delegation chain status, verification results.

## Multi-Tenancy

Filesystem-level tenant isolation via directory scoping. Each tenant gets an isolated `.trust-plane/<tenant-id>/` directory.

```bash
attest init --name "Project" --author "Admin" --tenant acme-corp
attest decide --type scope --decision "..." --tenant acme-corp
```

Tenant IDs validated via `validate_tenant_id()` (alphanumeric + hyphens, no traversal).

For PostgreSQL: Row-Level Security (RLS) provides database-level tenant isolation.

## IDE Integrations

### Claude Code

Hook integration via `kailash.trust.plane.integration.claude_code`. Automatically records attestations during Claude Code sessions.

### Cursor

Hook integration via `kailash.trust.plane.integration.cursor`. Records tool calls and decisions during Cursor sessions.

```python
from kailash.trust.plane.integration.cursor.hook import CursorHook

hook = CursorHook(trust_dir=".trust-plane")
hook.on_tool_call(tool_name="edit", resource="/src/main.py")
```

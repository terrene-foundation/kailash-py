# Trust-Plane CLI Reference

Entry point: `attest` (installed via `pip install trust-plane`).

## Global Options

```
--dir PATH      Trust plane directory (default: ./trust-plane)
--tenant ID     Tenant ID for multi-tenancy (scopes to .trust-plane/<tenant>/)
```

## Commands

### `attest init`

Initialize a new TrustPlane project with EATP genesis record.

```bash
attest init --name "My Project" --author "Dr. Smith"
attest init --name "Project" --author "Admin" --constraint "no-external-api"
```

Options:
- `--name` (required) — Project name
- `--author` (required) — Human authority name
- `--constraint` (repeatable) — Project constraints

### `attest quickstart`

Interactive setup wizard with domain templates and mode selection.

```bash
attest quickstart
attest quickstart --project-name "My App" --author "Alice" --domain web-app --mode shadow-first
```

Options:
- `--project-name` — Project name (prompted if omitted)
- `--author` — Author name (prompted if omitted)
- `--domain` — `web-app`, `data-pipeline`, `research`, `custom`
- `--mode` — `shadow-first`, `full-governance`, `exploring`

### `attest decide`

Record a decision with EATP audit trail.

```bash
attest decide --type scope --decision "Focus on dataset A" --rationale "Higher quality data"
attest decide --type methodology --decision "Use random forest" --rationale "Best F1 score" \
  --alternative "SVM" --alternative "Neural net" --risk "Overfitting" --confidence 0.85
```

Options:
- `--type` (required) — Decision category (scope, methodology, design, etc.)
- `--decision` (required) — What was decided
- `--rationale` (required) — Why this choice was made
- `--alternative` (repeatable) — Alternatives considered
- `--risk` (repeatable) — Known risks
- `--grade` — Review requirement: `standard`, `detailed`, `critical` (default: standard)
- `--confidence` — Confidence level 0.0-1.0 (default: 0.8)
- `--author` — Decision author (default: human)

### `attest milestone`

Record a milestone with EATP audit trail.

```bash
attest milestone --version v0.1 --description "Initial data processing" --file data/output.csv
```

### `attest verify`

Verify the project's EATP trust chain integrity. Checks anchor hashes, signatures, linkage, and delegation authority.

```bash
attest verify
```

### `attest status`

Show project status (name, ID, author, counts).

```bash
attest status
```

### `attest decisions`

List all decision records.

```bash
attest decisions
attest decisions --json-output
```

### `attest export`

Export verification bundles, compliance evidence, or SIEM events.

```bash
# Verification bundle
attest export --format json
attest export --format html -o report.html

# Compliance evidence (ZIP package)
attest export --format soc2 --period 2026-01-01:2026-03-31
attest export --format iso27001

# SIEM events
attest export --format cef
attest export --format ocsf --since 24h
attest export --format syslog --host siem.local --port 514
```

Options:
- `--format` — `json`, `html`, `soc2`, `iso27001`, `cef`, `ocsf`, `syslog`
- `--output` / `-o` — Output file path
- `--confidentiality` — Max level to include: `public`, `restricted`, `confidential`, `secret`
- `--period` — Date range: `START:END` (ISO 8601)
- `--since` — Time window for SIEM: `1h`, `24h`, `7d`
- `--host` — Syslog server hostname (required for `--format syslog`)
- `--port` — Syslog port (default: 514)
- `--protocol` — Syslog transport: `udp`, `tcp`

### `attest dashboard`

Start the web-based trust status dashboard.

```bash
attest dashboard --port 8080
```

Binds to `127.0.0.1` only (never `0.0.0.0`).

### `attest migrate`

Migrate project from older formats or between backends.

```bash
attest migrate              # Auto-detect and upgrade
attest migrate --to-sqlite  # Filesystem -> SQLite
```

## Configuration

Per-project settings in `.trustplane.toml`:

```toml
[store]
backend = "sqlite"          # or "filesystem"
sqlite_path = ".trust-plane/trust.db"

[enforcement]
mode = "strict"             # or "shadow"

[shadow]
report_schedule = "daily"   # daily, weekly, never
report_output = "file"      # stdout, file

[logging]
level = "INFO"              # DEBUG, INFO, WARNING, ERROR
```

Precedence: CLI flags > env vars > `.trustplane.toml` > defaults.

Environment variables: `TRUSTPLANE_STORE`, `TRUSTPLANE_MODE`, `TRUSTPLANE_LOG_LEVEL`.

## MCP Server

```bash
trustplane-mcp
```

Starts a FastMCP server for AI agent integration. Exposes trust-plane operations as MCP tools.

# TrustPlane Tutorial: Your First Trust-Governed Project

This tutorial walks you through using TrustPlane from zero to a fully
verified trust chain. The scenario: you are a developer using AI assistance
to build a new feature on a web application, and you want a cryptographic
record of every decision the AI makes along the way.

By the end, you will have:

- Observed AI activity with shadow mode (zero config)
- Read and understood a shadow report
- Initialized a governed project with a constraint envelope
- Recorded decisions and milestones with cryptographic audit trails
- Verified the integrity of the entire chain
- Exported a verification bundle for stakeholders

**Prerequisites**: Python 3.11+ and a terminal.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Shadow Mode First](#2-shadow-mode-first)
3. [Reading the Shadow Report](#3-reading-the-shadow-report)
4. [Graduating to Full Governance](#4-graduating-to-full-governance)
5. [Applying a Constraint Template](#5-applying-a-constraint-template)
6. [Recording a Decision](#6-recording-a-decision)
7. [Recording a Milestone](#7-recording-a-milestone)
8. [Checking Actions Against Constraints](#8-checking-actions-against-constraints)
9. [Verifying the Chain](#9-verifying-the-chain)
10. [Exporting a Bundle](#10-exporting-a-bundle)
11. [What's Next](#11-whats-next)

---

## 1. Installation

Install TrustPlane from PyPI:

```bash
pip install trust-plane
```

Verify the installation:

```bash
attest --help
```

You should see output like:

```
Usage: attest [OPTIONS] COMMAND [ARGS]...

  TrustPlane -- EATP-powered trust environment for collaborative work.

  Cryptographic attestation for decisions, milestones, and verification
  in human-AI collaborative projects.

Options:
  --dir PATH  Trust plane directory (default: ./trust-plane)
  --help      Show this message and exit.

Commands:
  audit       Generate a human-readable audit report (Markdown).
  decide      Record a decision with EATP audit trail.
  decisions   List all decision records.
  delegate    Manage delegates for multi-stakeholder review.
  diagnose    Analyze constraint quality and generate recommendations.
  enforce     Switch enforcement mode (strict or shadow).
  export      Export a VerificationBundle for independent verification.
  hold        Manage held actions awaiting approval.
  init        Initialize a new TrustPlane project with EATP Genesis Record.
  migrate     Migrate project data between store backends.
  milestone   Record a milestone with EATP audit trail.
  mirror      Show the Mirror Thesis competency map.
  shadow      Zero-config shadow mode -- observe AI activity without...
  status      Show project status.
  template    Constraint template management.
  verify      Verify the project's EATP trust chain integrity.
```

The `attest` command is TrustPlane's CLI entry point. Every subcommand
operates on a trust-plane directory (defaulting to `./trust-plane` in
your current working directory).

---

## 2. Shadow Mode First

Shadow mode is the best way to start. It requires zero setup -- no
project initialization, no configuration files. Shadow mode passively
observes AI tool calls, classifies them, and evaluates what WOULD have
happened if constraints were enforced.

Think of it as a flight data recorder that you turn on before takeoff.
Nothing changes about the flight, but afterward you have a complete
record of everything that happened.

### Start shadow mode

```bash
attest shadow
```

Expected output:

```
Shadow mode is available (zero-config, no 'attest init' needed).
  Shadow DB: ./trust-plane/shadow.db
  Sessions recorded: 0

Shadow mode passively observes AI tool calls and evaluates
what WOULD happen under constraint enforcement.

Commands:
  attest shadow --report           # View latest report
  attest shadow --report --json    # JSON format
  attest shadow --report --last 7d # Last 7 days
```

Shadow mode stores its data in a SQLite database at
`./trust-plane/shadow.db`, separate from any governed project data.
You do not need to run `attest init` first.

### How shadow data gets recorded

When TrustPlane is integrated with an AI coding assistant (e.g., via
the MCP server or Claude Code hooks), every tool call the AI makes is
automatically recorded into the shadow database. Each call gets:

- **Classified** into a category: `file_read`, `file_write`,
  `shell_command`, `web_request`, or `other`.
- **Evaluated** against a reference constraint envelope (the "software"
  template by default) to determine whether it WOULD have been blocked,
  held for review, or auto-approved.

No actions are actually blocked in shadow mode. The AI works normally.
The value is the after-the-fact analysis.

### Let the AI do some work

Use your AI assistant to implement a feature on your web app. For
example, ask it to:

- Read source files
- Write new code
- Run tests
- Search the web for documentation

Each of these tool calls will be captured by shadow mode.

---

## 3. Reading the Shadow Report

After the AI has done some work, generate a shadow report:

```bash
attest shadow --report
```

You will see a Markdown-formatted report like this:

```markdown
# Shadow Mode Report

**Session**: a1b2c3d4-e5f6-7890-abcd-ef1234567890
**Started**: 2026-03-15T10:30:00+00:00

## Summary

- **Total tool calls**: 42
- **Would pass**: 38
- **Would be held**: 3
- **Would be blocked**: 1
- **Block rate**: 2.4%

## By Category

### file_read

- Count: 20

### file_write

- Count: 12
- Would be held: 3

### shell_command

- Count: 8

### web_request

- Count: 2
- Would be blocked: 1

## Flagged Actions

- **[HELD]** `Edit` on `config/production.yml`
  - Reason: Write to 'config/production.yml' not in allowed write paths
- **[HELD]** `Write` on `.github/workflows/deploy.yml`
  - Reason: Write to '.github/workflows/deploy.yml' not in allowed write paths
- **[HELD]** `Edit` on `database/migrations/001.sql`
  - Reason: Write to 'database/migrations/001.sql' not in allowed write paths
- **[BLOCKED]** `access_production` on `prod-server`
  - Reason: Action 'access_production' is in blocked_actions
```

### Understanding each section

**Summary**: The top-level numbers tell you how much of the AI's work
would have been affected by constraints. A low block rate (under 5%)
typically means your constraints are well-tuned. A high block rate
means your constraints may be too tight, or the AI is doing things
it should not.

**By Category**: Shows the breakdown of AI activity by type. This is
useful for understanding what the AI actually spent its time doing.
Was it mostly reading files? Writing code? Running shell commands?

**Flagged Actions**: The most important section. Each flagged action
tells you exactly what the AI did, what resource it touched, and why
that action would have been restricted. There are two severity levels:

- **BLOCKED**: The action directly violates a constraint. Under strict
  enforcement, this action would be denied outright.
- **HELD**: The action falls outside the expected boundaries. Under
  strict enforcement, it would be paused for human review before
  proceeding.

### JSON format

For programmatic consumption or CI integration:

```bash
attest shadow --report --json
```

This produces a JSON array of session reports with structured data:

```json
[
  {
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "started_at": "2026-03-15T10:30:00+00:00",
    "ended_at": null,
    "summary": {
      "total_calls": 42,
      "passed": 38,
      "held": 3,
      "blocked": 1,
      "block_rate": 2.4
    },
    "categories": {
      "file_read": 20,
      "file_write": 12,
      "shell_command": 8,
      "web_request": 2
    },
    "flagged_actions": [
      {
        "action": "access_production",
        "resource": "prod-server",
        "category": "other",
        "would_be_blocked": true,
        "would_be_held": false,
        "reason": "Action 'access_production' is in blocked_actions"
      }
    ]
  }
]
```

### Filtering by time

To see only the last 24 hours:

```bash
attest shadow --report --last 24h
```

Or the last 7 days:

```bash
attest shadow --report --last 7d
```

Valid duration suffixes are `m` (minutes), `h` (hours), and `d` (days).

---

## 4. Graduating to Full Governance

Once you have seen what shadow mode reveals, you are ready to set up
a governed project. This creates a cryptographic trust chain rooted in
a Genesis Record -- the starting point for all attestation.

### Initialize the project

```bash
attest init --name "Acme Web App" --author "Jane Developer"
```

Expected output:

```
Initialized project: Acme Web App
  Project ID: proj-a1b2c3d4e5f6
  Genesis:    genesis-789abcdef012
  Trust dir:  ./trust-plane
```

What just happened:

1. **A project identity was created.** The `Project ID` is a unique
   identifier for this trust-governed project. It never changes.

2. **A Genesis Record was written.** This is the cryptographic root of
   trust. It records who created the project (`--author`), when it was
   created, and a cryptographic keypair for signing all subsequent
   records. Think of it as the first commit in a git repository, except
   it is cryptographically signed.

3. **A trust-plane directory was created.** All trust data lives inside
   `./trust-plane/`. This directory contains:
   - `manifest.json` -- project identity and aggregate stats
   - `keys/` -- Ed25519 keypair for signing
   - `trust.db` -- SQLite database for records (default backend)

### Adding initial constraints

You can also specify constraints at initialization time:

```bash
attest init \
  --name "Acme Web App" \
  --author "Jane Developer" \
  --constraint "no_production_access" \
  --constraint "no_force_push"
```

These legacy-format constraints are stored as blocked actions. For
structured constraints across all five EATP dimensions, use constraint
templates (see next section).

### Verifying the initial state

After initialization, check the project status:

```bash
attest status
```

Expected output:

```
Project: Acme Web App
  ID:         proj-a1b2c3d4e5f6
  Author:     Jane Developer
  Created:    2026-03-15T10:00:00+00:00
  Genesis:    genesis-789abcdef012
  Decisions:  0
  Milestones: 0
  Audits:     0
```

Everything starts at zero. As you record decisions and milestones,
these counters increment and the trust chain grows.

---

## 5. Applying a Constraint Template

Constraint templates are pre-built, tested constraint envelopes for
common domains. They save you from having to configure all five EATP
dimensions manually.

### List available templates

```bash
attest template list
```

Expected output:

```
  governance    Governance, documentation, and policy work. Protects constitution and compliance records.
  software      Software development with CI/CD protection. Blocks production access and force operations.
  research      Research and analysis projects. Protects raw data and requires publication review.
```

### Apply the software template

Since we are working on a web app, the software template is a good fit:

```bash
attest template apply software
```

Expected output:

```
Applied template 'software' to project.
  Signed by: Jane Developer
  Hash:      a1b2c3d4e5f6...
```

This configured all five constraint dimensions:

- **Operational**: AI can write code, run tests, create PRs, review
  code, and format code. It CANNOT merge to main, modify CI/CD,
  access production, or delete branches.

- **Data Access**: AI can read from `src/`, `tests/`, and `docs/`.
  It can write to `src/` and `tests/`. It CANNOT access `.env`,
  `secrets/`, `production/`, or any `*.key`, `*.pem`, or
  `credentials*` files.

- **Financial**: Maximum $10 per session, $1 per action, with budget
  tracking enabled.

- **Temporal**: Maximum 8-hour sessions.

- **Communication**: AI can post to GitHub PRs and Slack dev channels.
  It CANNOT access external APIs or trigger production deploys.
  Merges to GitHub require human review.

### Why templates matter

Templates encode best practices. The software template was designed
to prevent the most common AI-assisted development mistakes: pushing
directly to production, accessing secrets, and making unsupervised
infrastructure changes. You can always customize the envelope later.

---

## 6. Recording a Decision

Decisions are the core unit of TrustPlane's audit trail. Every time a
significant choice is made during AI-assisted work, it should be
recorded as a decision.

### Record a scoping decision

```bash
attest decide \
  --type scope \
  --decision "Add user authentication with OAuth2 instead of custom auth" \
  --rationale "OAuth2 reduces security surface area and maintenance burden" \
  --alternative "Build custom JWT-based auth" \
  --alternative "Use session cookies with CSRF tokens" \
  --risk "Dependency on third-party OAuth provider" \
  --confidence 0.9
```

Expected output:

```
Recorded decision: dec-a1b2c3d4e5f6
  Type:       scope
  Grade:      standard
  Confidence: 0.9
```

What got recorded:

- **Decision ID**: A content-derived unique identifier. Deterministic
  enough to detect duplicates, random enough to prevent collisions.

- **Type**: The category of decision. Built-in types include `scope`,
  `design`, `technical`, `policy`, `argument`, `literature`,
  `structure`, `framing`, `evidence`, `methodology`, `process`,
  `trade_off`, and `requirement`. You can also pass any custom string.

- **Decision**: What was decided.

- **Rationale**: Why this choice was made. The most important field
  for future auditing -- a decision without rationale is useless.

- **Alternatives**: What was considered and rejected. This proves the
  decision was deliberate, not accidental.

- **Risks**: Known risks that were accepted. Acknowledging risk upfront
  is more valuable than pretending it does not exist.

- **Confidence**: A 0.0-1.0 score. At 0.9, the decision-maker is
  highly confident. Below 0.5 suggests the decision may need revisiting.

- **Grade**: The review requirement. Defaults to `standard` (human can
  inspect, not required to approve each one). Other options: `quick`
  (agent-to-agent work, hashed but not human-reviewed) and `full`
  (human must explicitly approve before work continues).

### Record a design decision

```bash
attest decide \
  --type design \
  --decision "Use React Server Components for the auth flow" \
  --rationale "SSR improves initial load and SEO; reduces client JS bundle" \
  --confidence 0.85 \
  --grade standard
```

Expected output:

```
Recorded decision: dec-f6e5d4c3b2a1
  Type:       design
  Grade:      standard
  Confidence: 0.85
```

### Record a technical decision with full review

For high-stakes decisions, use `--grade full`:

```bash
attest decide \
  --type technical \
  --decision "Store OAuth tokens in httpOnly cookies, not localStorage" \
  --rationale "httpOnly cookies prevent XSS token theft" \
  --alternative "localStorage with token rotation" \
  --risk "CSRF requires additional mitigation" \
  --grade full \
  --confidence 0.95
```

### List all decisions

```bash
attest decisions
```

Expected output:

```
[dec-a1b2c3d4e5f6] scope: Add user authentication with OAuth2 instead of custom auth
  Rationale: OAuth2 reduces security surface area and maintenance burden
  Review: standard | Confidence: 0.9

[dec-f6e5d4c3b2a1] design: Use React Server Components for the auth flow
  Rationale: SSR improves initial load and SEO; reduces client JS bundle
  Review: standard | Confidence: 0.85

[dec-1234abcd5678] technical: Store OAuth tokens in httpOnly cookies, not localStorage
  Rationale: httpOnly cookies prevent XSS token theft
  Review: full | Confidence: 0.95
```

### JSON output

For programmatic access:

```bash
attest decisions --json-output
```

This produces a JSON array of all decision records with full detail.

---

## 7. Recording a Milestone

Milestones are versioned checkpoints. They mark a point in time where
a deliverable was completed and can optionally hash a file for tamper
detection. Milestones always have a `full` review requirement -- the
human must explicitly engage.

### Record a milestone with a file hash

```bash
attest milestone \
  --version v0.1 \
  --description "OAuth2 login flow implemented and passing tests" \
  --file src/auth/oauth.py
```

Expected output:

```
Recorded milestone: ms-abcdef123456
  Version: v0.1
```

What happened:

1. The file `src/auth/oauth.py` was read and its SHA-256 hash was
   recorded in the milestone. If the file is later modified, the hash
   mismatch will be detectable during verification.

2. The milestone was added to the trust chain as a new EATP Audit
   Anchor with `FULL` verification level.

3. The project's milestone counter was incremented.

### Record a milestone without a file

Not every milestone is tied to a specific file:

```bash
attest milestone \
  --version v0.2 \
  --description "Security review completed, no critical findings"
```

### When to use milestones vs. decisions

Use **decisions** for choices that shape the work: architecture,
design, scope, trade-offs. Decisions answer "what did we choose and
why?"

Use **milestones** for deliverables and checkpoints: completed
features, passing test suites, shipped releases. Milestones answer
"what was delivered and when?"

---

## 8. Checking Actions Against Constraints

Once a project has a constraint envelope, you can check whether
specific actions would be allowed. This is how TrustPlane enforces
constraints in real-time (when running in strict mode).

### Using the Python API

```python
import asyncio
from trustplane.project import TrustProject

async def check_action():
    project = await TrustProject.load("./trust-plane")

    # Check a write action
    verdict = await project.check(
        action="write_code",
        resource="src/auth/oauth.py",
    )
    print(f"Verdict: {verdict}")  # Verdict.AUTO_APPROVED

    # Check a blocked action
    verdict = await project.check(
        action="access_production",
        resource="prod-server",
    )
    print(f"Verdict: {verdict}")  # Verdict.BLOCKED

asyncio.run(check_action())
```

### Switching enforcement modes

By default, constraints are informational. To enforce them:

```bash
attest enforce strict
```

Expected output:

```
Enforcement mode set to: strict
```

In strict mode, actions that violate the constraint envelope will be
HELD (paused for human approval) or BLOCKED (denied outright).

To go back to observation-only:

```bash
attest enforce shadow
```

Expected output:

```
Enforcement mode set to: shadow
```

### Managing held actions

When the enforcement mode is `strict`, actions that would be held are
queued for human review:

```bash
attest hold list
```

To approve a held action:

```bash
attest hold approve <hold-id> --approver "Jane Developer"
```

To deny a held action:

```bash
attest hold deny <hold-id> --reason "Not authorized for production changes"
```

---

## 9. Verifying the Chain

Verification checks the integrity of the entire trust chain from
Genesis to the latest record. It answers the question: "Has anyone
tampered with the audit trail?"

```bash
attest verify
```

Expected output (clean):

```
Project: Acme Web App (proj-a1b2c3d4e5f6)
Chain valid: True
Anchors: 5
Decisions: 3
Milestones: 2
Audits: 0

No integrity issues detected.
```

What gets verified:

1. **Genesis Record**: The root of trust exists and is properly signed.
2. **Chain links**: Every Audit Anchor references the previous anchor's
   hash. Any insertion, deletion, or modification breaks the chain.
3. **Signatures**: Every record is signed with the project's Ed25519
   key. Forged records are detected.
4. **Counters**: The aggregate statistics in the manifest match the
   actual record counts.

### When verification fails

If someone tampers with a record:

```
Project: Acme Web App (proj-a1b2c3d4e5f6)
Chain valid: False
Anchors: 5
Decisions: 3
Milestones: 2
Audits: 0

INTEGRITY ISSUES:
  - Chain hash mismatch at anchor 3: expected abc123, got def456
```

A failed verification exits with code 1, making it easy to use in CI
pipelines:

```bash
attest verify || echo "Trust chain compromised!"
```

### Generating an audit report

For a human-readable Markdown audit report:

```bash
attest audit
```

Or save to a file:

```bash
attest audit -o audit-report.md
```

---

## 10. Exporting a Bundle

A verification bundle packages everything needed to independently
verify your project's trust chain -- without access to the TrustPlane
installation or the EATP SDK.

### JSON export

```bash
attest export --format json -o bundle.json
```

Expected output:

```
Exported json bundle to bundle.json
```

The bundle contains:

- Genesis Record (full)
- Constraint Envelope (full)
- All Audit Anchors in chain order
- Reasoning Traces (filtered by confidentiality)
- Public key for signature verification
- Chain hash for integrity verification

### HTML export

For stakeholders who need a visual report:

```bash
attest export --format html -o bundle.html
```

This produces a self-contained HTML file that can be opened in any
browser. No server needed.

### Confidentiality filtering

By default, exports include only `public` records. To include
restricted records:

```bash
attest export --format json --confidentiality restricted -o bundle.json
```

Available levels: `public`, `restricted`, `confidential`, `secret`.
Each level includes all records at that level and below.

---

## 11. What's Next

You now have a working trust-governed project. Here are the next steps
to deepen your use of TrustPlane.

### Pre-commit hook

Add TrustPlane verification to your git pre-commit hook so that
every commit verifies the trust chain:

```bash
#!/bin/sh
# .git/hooks/pre-commit
attest verify || {
    echo "Trust chain verification failed. Commit blocked."
    exit 1
}
```

### GitHub Action

Run verification in CI:

```yaml
# .github/workflows/trust.yml
name: Trust Verification
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install trust-plane
      - run: attest verify
```

### Delegation

For projects with multiple reviewers, use delegation to grant
scoped authority:

```bash
# Add a delegate for operational and data access dimensions
attest delegate add "Security Lead" \
  --dimensions "operational,data_access" \
  --expires 24

# List delegates
attest delegate list

# Revoke a delegate
attest delegate revoke <delegate-id>
```

Delegates receive scoped authority over specific constraint dimensions,
with optional time-based expiry and sub-delegation.

### Constraint diagnostics

After running for a while, analyze how well your constraints are
tuned:

```bash
attest diagnose
```

This examines the audit trail to identify unused constraints (too
tight), high-friction boundaries (too many holds), and unconstrained
actions (gaps in coverage).

### Mirror Thesis competency map

See what AI handles autonomously versus where human judgment is
needed:

```bash
attest mirror
```

This analyzes execution, escalation, and intervention records to
reveal patterns in human-AI collaboration.

### Store migration

For high-volume projects, migrate from the default SQLite backend to
optimize performance:

```bash
# Preview what would be migrated
attest migrate --to sqlite --dry-run

# Execute the migration
attest migrate --to sqlite
```

### Using the Python API

For programmatic access, import TrustProject directly:

```python
import asyncio
from trustplane.project import TrustProject
from trustplane.models import DecisionRecord, DecisionType

async def main():
    # Create a project
    project = await TrustProject.create(
        trust_dir="./trust-plane",
        project_name="My Project",
        author="Developer",
    )

    # Record a decision
    record = DecisionRecord(
        decision_type=DecisionType.SCOPE,
        decision="Use microservices architecture",
        rationale="Better scalability and team independence",
        alternatives=["Monolith", "Modular monolith"],
        confidence=0.85,
    )
    decision_id = await project.record_decision(record)
    print(f"Decision: {decision_id}")

    # Record a milestone
    milestone_id = await project.record_milestone(
        version="v1.0",
        description="Initial architecture complete",
    )
    print(f"Milestone: {milestone_id}")

    # Verify the chain
    report = await project.verify()
    print(f"Chain valid: {report['chain_valid']}")

asyncio.run(main())
```

### MCP server

TrustPlane includes an MCP (Model Context Protocol) server for direct
integration with AI assistants:

```bash
trustplane-mcp
```

This exposes TrustPlane operations as MCP tools that AI assistants can
call directly, enabling real-time constraint checking and attestation
during AI-assisted work.

---

## Summary

| Step       | Command                                                         | What it does                   |
| ---------- | --------------------------------------------------------------- | ------------------------------ |
| Observe    | `attest shadow`                                                 | Zero-config activity recording |
| Report     | `attest shadow --report`                                        | See what the AI did            |
| Initialize | `attest init --name "..." --author "..."`                       | Create trust chain root        |
| Template   | `attest template apply software`                                | Configure constraint envelope  |
| Decide     | `attest decide --type scope --decision "..." --rationale "..."` | Record a decision              |
| Milestone  | `attest milestone --version v0.1 --description "..."`           | Record a checkpoint            |
| Verify     | `attest verify`                                                 | Check chain integrity          |
| Export     | `attest export --format json -o bundle.json`                    | Share verification bundle      |
| Status     | `attest status`                                                 | View project overview          |
| Audit      | `attest audit`                                                  | Generate audit report          |

Every command creates a cryptographically signed record in the trust
chain. Once written, records cannot be modified without breaking the
chain. This is the foundation of trustworthy human-AI collaboration.

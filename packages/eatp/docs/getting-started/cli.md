# CLI Guide

EATP includes a command-line interface for managing trust chains.

## Installation

The CLI is included with the `eatp` package:

```bash
pip install eatp
eatp --help
```

## Commands

| Command | Purpose |
|---------|---------|
| `eatp init` | Initialize trust authority |
| `eatp establish` | Create trust chain for agent |
| `eatp verify` | Verify agent trust for action |
| `eatp delegate` | Delegate trust to sub-agent |
| `eatp audit` | View audit trail |
| `eatp constrain` | Apply constraint template |
| `eatp revoke` | Revoke delegation |
| `eatp status` | Show agent trust status |
| `eatp score` | Compute trust score |
| `eatp export` | Export trust chain |
| `eatp import` | Import trust chain |
| `eatp dashboard` | Trust overview dashboard |
| `eatp scan` | Scan for EATP configuration |
| `eatp quickstart` | Interactive quickstart |
| `eatp version` | Show version |

## Quick Workflow

```bash
# Initialize
eatp init --name "My Authority" --yes

# Establish agent
eatp establish my-agent --authority <id> --capabilities read,write --yes

# Apply constraints
eatp constrain my-agent --template minimal --yes

# Verify
eatp verify my-agent --action read --json

# View status
eatp status my-agent --json
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
eatp verify my-agent --action read --json | jq '.valid'
```

## Store Directory

By default, EATP stores data in `~/.eatp/`. Override with `--store-dir`:

```bash
eatp init --store-dir /path/to/store --name "Test"
```

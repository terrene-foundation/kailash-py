# Cursor IDE Integration for TrustPlane

This guide walks you through setting up TrustPlane trust gating in Cursor IDE.
After setup, Cursor's AI assistant will check trust constraints before modifying
files, creating content, or making decisions.

## Prerequisites

- [Cursor IDE](https://cursor.com) installed
- TrustPlane installed: `pip install trust-plane`
- A TrustPlane project initialized (optional for shadow mode)

## Quick Start

Run the setup command from your project root:

```bash
# Shadow mode (default) — observe without blocking
attest integration setup cursor

# Strict mode — enforce constraints
attest integration setup cursor --mode strict
```

This creates three files:

| File                               | Purpose                                       |
| ---------------------------------- | --------------------------------------------- |
| `.cursorrules`                     | AI behavior rules with trust enforcement      |
| `.cursor/mcp.json`                 | MCP server configuration for TrustPlane tools |
| `.cursor/hooks/trustplane_hook.py` | Pre-tool hook for constraint checking         |

## Step-by-Step Setup

### 1. Initialize a TrustPlane Project (Optional)

If you want constraint enforcement (not just shadow observation), initialize
a trust-plane project first:

```bash
attest init --name "My Project" --author "Your Name"
```

Apply a constraint template:

```bash
# See available templates
attest template list

# Apply one
attest template apply software --author "Your Name"
```

### 2. Run Cursor Integration Setup

```bash
attest integration setup cursor
```

If you already have a `.cursorrules` file, you have two options:

```bash
# Overwrite existing .cursorrules
attest integration setup cursor
# (You will be prompted for confirmation)

# Merge with existing .cursorrules
attest integration setup cursor --merge
```

The `--merge` flag appends TrustPlane rules to your existing `.cursorrules`
file, wrapped in markers (`# --- TrustPlane Begin ---` / `# --- TrustPlane End ---`)
so they can be updated independently.

### 3. Open Your Project in Cursor

Cursor automatically detects:

- `.cursorrules` for AI behavior instructions
- `.cursor/mcp.json` for MCP server configuration

The AI assistant will now have access to TrustPlane tools:

- `trust_check` — Verify an action is allowed before execution
- `trust_record` — Record decisions with EATP audit trail
- `trust_status` — Query current trust posture
- `trust_envelope` — Read the constraint envelope
- `trust_verify` — Verify trust chain integrity

### 4. Verify the Integration

In Cursor's AI chat, ask:

> What is the current trust status?

The AI should call `trust_status` and report the project's trust posture,
constraint summary, and session information.

## Enforcement Modes

### Shadow Mode (Default)

Shadow mode records all AI activity without blocking any actions. This is
the recommended starting mode:

- All tool calls are logged
- Constraint violations are recorded but not enforced
- The AI is instructed to note violations to the user
- Review observations with `attest shadow --report`

Shadow mode lets you tune constraints before enabling enforcement.

### Strict Mode

Strict mode actively blocks actions that violate constraints:

- The hook script intercepts tool calls before execution
- Actions receiving HELD verdicts are paused for human approval
- Actions receiving BLOCKED verdicts are rejected
- The AI is instructed to explain why an action was blocked

Manage held actions:

```bash
# List pending holds
attest hold list

# Approve a held action
attest hold approve <hold_id>

# Deny a held action
attest hold deny <hold_id> --reason "Not appropriate"
```

### Switching Modes

```bash
# Switch to strict mode
attest integration setup cursor --mode strict

# Switch to shadow mode
attest integration setup cursor --mode shadow
```

You can also switch the project-level mode:

```bash
attest enforce strict
attest enforce shadow
```

## How It Works

### Architecture

```
Cursor AI Assistant
    |
    |--- reads .cursorrules (behavioral instructions)
    |
    |--- calls MCP tools (trust_check, trust_record, etc.)
    |         |
    |         +--- trustplane-mcp server
    |                   |
    |                   +--- TrustPlane project (constraint envelope)
    |
    +--- hook intercepts tool calls
              |
              +--- trustplane_hook.py
                        |
                        +--- checks constraints
                        +--- logs verdicts
                        +--- blocks if strict mode + violation
```

### The .cursorrules File

The generated `.cursorrules` file contains:

1. **Anti-amnesia rules** — Remind the AI of TrustPlane on every turn,
   surviving context compaction
2. **Constraint checking protocol** — Instructions to call `trust_check`
   before gated actions
3. **Verdict interpretation** — How to handle each verdict type
4. **Protected paths** — Directories the AI must not modify directly

### The Hook Script

The hook script (`trustplane_hook.py`) provides a second layer of enforcement:

1. Intercepts tool calls (Edit, Write, Bash, Delete)
2. Checks the action against the constraint envelope
3. In shadow mode: logs the verdict, always allows
4. In strict mode: blocks HELD/BLOCKED verdicts
5. Always blocks direct modification of `trust-plane/` directory

The hook writes a log to `.cursor/trustplane-hook.log` for debugging.

### MCP Server

The MCP server (`trustplane-mcp`) exposes TrustPlane as tools the AI can call.
It is configured in `.cursor/mcp.json` and started automatically by Cursor.

## Environment Variables

| Variable              | Default                       | Description                       |
| --------------------- | ----------------------------- | --------------------------------- |
| `TRUSTPLANE_DIR`      | `./trust-plane`               | Path to the trust-plane directory |
| `TRUSTPLANE_MODE`     | `shadow`                      | Enforcement mode for the hook     |
| `TRUSTPLANE_HOOK_LOG` | `.cursor/trustplane-hook.log` | Hook log file path                |

## Troubleshooting

### AI is not calling trust_check

1. Verify `.cursorrules` exists in the project root
2. Check that the file contains TrustPlane rules (search for "TrustPlane")
3. Restart Cursor to reload the rules
4. Ask the AI: "Are you aware of TrustPlane trust gating?"

### MCP server not starting

1. Verify `trustplane-mcp` is on your PATH: `which trustplane-mcp`
2. Check `.cursor/mcp.json` has the correct configuration
3. Try running manually: `trustplane-mcp --trust-dir ./trust-plane`
4. Check Cursor's MCP server logs for error messages

### Hook script not intercepting

1. Verify `.cursor/hooks/trustplane_hook.py` exists
2. Check that Python 3.11+ is available on your PATH
3. Review `.cursor/trustplane-hook.log` for entries
4. Cursor may require a restart to detect new hooks

### Constraint violations not blocking (strict mode)

1. Confirm mode is set to strict: check `.cursorrules` for `Mode: strict`
2. Verify the constraint envelope is configured: `attest status`
3. Check the hook log for verdict entries
4. Run `attest integration setup cursor --mode strict` to reconfigure

### Merging .cursorrules failed

If the merge produces unexpected results:

1. Check for `# --- TrustPlane Begin ---` and `# --- TrustPlane End ---` markers
2. Run setup again without `--merge` to get a clean `.cursorrules`
3. Manually copy your custom rules back in

## Uninstalling

To remove TrustPlane integration from Cursor:

```bash
# Remove .cursorrules (or remove TrustPlane section if merged)
rm .cursorrules

# Remove MCP config
rm .cursor/mcp.json

# Remove hook
rm .cursor/hooks/trustplane_hook.py

# Remove hook log
rm .cursor/trustplane-hook.log
```

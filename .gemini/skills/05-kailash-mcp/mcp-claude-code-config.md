---
name: mcp-claude-code-config
description: "Configure Claude Code mcpServers for kailash-mcp platform server. Stdio and SSE setup, troubleshooting. Use when asking 'claude code mcp setup', 'mcpServers config', 'kailash mcp settings', or 'mcp connection issues'."
---

# MCP Claude Code Configuration

How to configure Claude Code to connect to the kailash-mcp platform server. Covers stdio (local development) and SSE (remote server) configurations, plus troubleshooting common connection issues.

> **Skill Metadata**
> Category: `mcp`
> Priority: `HIGH`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-security-tiers`](mcp-security-tiers.md)
> Related Subagents: `mcp-specialist` (connection troubleshooting, advanced configuration)

## Stdio Configuration (Local Development)

The recommended configuration for local development. Claude Code launches the kailash-mcp server as a subprocess and communicates over stdin/stdout.

### Project-Level Settings

Add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "kailash": {
      "command": "kailash-mcp",
      "args": ["--project-root", "."]
    }
  }
}
```

**Why project-level?** Each project has its own models, handlers, and agents. The `--project-root` argument tells the server which directory to scan.

### With Virtual Environment

If `kailash-mcp` is installed in a project virtual environment:

```json
{
  "mcpServers": {
    "kailash": {
      "command": ".venv/bin/kailash-mcp",
      "args": ["--project-root", "."]
    }
  }
}
```

### With uv

If using `uv` and the command is not on PATH:

```json
{
  "mcpServers": {
    "kailash": {
      "command": "uv",
      "args": ["run", "kailash-mcp", "--project-root", "."]
    }
  }
}
```

### With Execution Tier Enabled

To enable Tier 4 execution tools (handler/agent testing):

```json
{
  "mcpServers": {
    "kailash": {
      "command": "kailash-mcp",
      "args": ["--project-root", "."],
      "env": {
        "KAILASH_MCP_ENABLE_EXECUTION": "true"
      }
    }
  }
}
```

**Why set env in config?** This ensures the execution tier is enabled specifically for this MCP server connection, without affecting the rest of the shell environment.

### With Custom Environment Variables

Pass database URL and API keys to the MCP server:

```json
{
  "mcpServers": {
    "kailash": {
      "command": "kailash-mcp",
      "args": ["--project-root", "."],
      "env": {
        "DATABASE_URL": "postgresql://localhost:5432/myapp",
        "KAILASH_MCP_ENABLE_EXECUTION": "true"
      }
    }
  }
}
```

**Why might you need DATABASE_URL?** The `dataflow.query_schema` tool checks whether a database connection is configured. Without it, the tool reports `database_url_configured: false` but still discovers models via AST scanning.

## SSE Configuration (Remote Server)

For connecting to a kailash-mcp server running on a remote machine or as a shared service.

### Start the Remote Server

```bash
# On the server machine
kailash-mcp --transport sse --port 8900 --project-root /path/to/project
```

### Claude Code Settings

```json
{
  "mcpServers": {
    "kailash": {
      "url": "http://server-host:8900/sse"
    }
  }
}
```

### SSE with Authentication

If the remote server is behind an authenticated proxy:

```json
{
  "mcpServers": {
    "kailash": {
      "url": "https://mcp.company.com/sse",
      "headers": {
        "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

## Global vs Project Settings

| Setting Level | File                      | Use When                                        |
| ------------- | ------------------------- | ----------------------------------------------- |
| **Project**   | `.claude/settings.json`   | Different projects need different project roots |
| **User**      | `~/.claude/settings.json` | Same kailash-mcp config across all projects     |

**Recommendation**: Use project-level settings. Each project has different frameworks installed and different artifacts to discover.

## Verifying the Connection

After configuring, verify the MCP server is working:

1. Open Claude Code in the project directory
2. Ask: "What Kailash frameworks are installed?"
3. Claude should call `core.get_sdk_version` or `platform.project_info` and report installed versions

If the server is not connected, Claude will not have access to any `core.*`, `platform.*`, `dataflow.*`, etc. tools.

## Troubleshooting

### Server Not Starting

**Symptom**: Claude Code shows no kailash tools available.

**Check 1**: Is `kailash-mcp` on PATH?

```bash
which kailash-mcp
# Should show a path. If not:
pip install kailash  # or: uv pip install kailash
```

**Check 2**: Can the server start manually?

```bash
kailash-mcp --project-root . 2>/dev/null
# Should not produce errors on stderr
```

**Check 3**: Is the virtual environment correct?

```bash
.venv/bin/kailash-mcp --project-root . 2>/dev/null
# If this works but the config doesn't, use the full path in settings
```

### Server Starts But No Tools Appear

**Symptom**: Server connects but Claude sees zero tools.

**Cause**: The `mcp` pip package (FastMCP) is not installed or the wrong version.

```bash
pip show mcp
# Requires: mcp >= 1.23.0, < 2.0
pip install 'mcp[cli]>=1.23.0,<2.0'
```

**Why?** The `kailash.mcp` sub-package shadows the top-level `mcp` package. The platform server has special import logic to resolve this, but it requires the third-party `mcp` package to be installed in site-packages.

### Framework Tools Missing

**Symptom**: `core.*` and `platform.*` tools work, but `dataflow.*` or `kaizen.*` are missing.

**Cause**: The framework sub-package is not installed.

```bash
pip install kailash-dataflow  # for dataflow.* tools
pip install kailash-nexus     # for nexus.* tools
pip install kailash-kaizen    # for kaizen.* tools
pip install kailash-pact      # for pact.* tools
```

Check with `core.get_sdk_version` -- it reports `null` for packages not installed.

### Wrong Project Root

**Symptom**: Tools return empty results (zero models, zero handlers) even though the project has them.

**Cause**: `--project-root` points to the wrong directory.

The server scans `project_root` recursively for Python files. If it points to a parent directory or a subdirectory without source files, it finds nothing.

**Fix**: Ensure `--project-root` points to the directory containing your `src/`, `models/`, `handlers/`, or `agents/` directories:

```json
{
  "mcpServers": {
    "kailash": {
      "command": "kailash-mcp",
      "args": ["--project-root", "/absolute/path/to/project"]
    }
  }
}
```

### SSE Connection Refused

**Symptom**: Claude Code cannot connect to the SSE server.

**Check 1**: Is the server running?

```bash
curl http://server-host:8900/sse
# Should return an SSE event stream
```

**Check 2**: Firewall or network issues?

```bash
nc -zv server-host 8900
# Should show "Connection succeeded"
```

**Check 3**: Is the URL correct? The SSE endpoint is at `/sse`, not the root.

### Timeout During Scan

**Symptom**: Tools take very long or time out on large projects.

**Cause**: The AST scanner is processing too many files.

The scanner skips `.venv`, `__pycache__`, `node_modules`, `.git`, and other non-project directories. If your project has additional large directories that should be skipped, restructure so source code is under `src/`.

## Quick Tips

- Use stdio for local development -- it is simpler and faster
- Use SSE only when the server must run on a different machine
- Always specify `--project-root` explicitly -- do not rely on cwd detection
- Set `KAILASH_MCP_ENABLE_EXECUTION=true` only in trusted environments
- Check `core.get_sdk_version` first to verify the connection works

## When to Escalate to Subagent

Use `mcp-specialist` when:

- Configuring SSE behind a reverse proxy with TLS termination
- Debugging import shadowing issues between `kailash.mcp` and `mcp`
- Setting up multi-project MCP server configurations
- Integrating with non-Claude MCP clients (Cursor, custom clients)

<!-- Trigger Keywords: claude code mcp setup, mcpServers config, kailash mcp settings, mcp connection issues, mcp troubleshooting, settings.json mcp, stdio mcp config, sse mcp config -->

# MCP Configurations for Kailash Projects

## CRITICAL: Context Impact Warning

**Without MCP limits**:
- 200k total context
- 20+ MCPs enabled
- Each MCP: ~2-5k tokens
- Result: ~70k usable (65% loss!)

**Safe Limits**:
- <10 MCPs enabled per project
- <80 tools active
- Monitor with `/context` command

## Available Configurations

| Configuration | MCPs | Context Cost | Use Case |
|--------------|------|--------------|----------|
| `kailash-minimal.json` | 2 | ~10k | Basic projects, documentation |
| `kailash-dev.json` | 3 | ~17k | Active development |
| `kailash-full.json` | 5 | ~30k | Full-stack with database |

## Configuration Selection Guide

### Choose Minimal When:
- Working on documentation
- Simple code reviews
- Context efficiency is critical
- Not using database or deployment

### Choose Development When:
- Active feature development
- Need filesystem operations
- Building workflows
- Standard development work

### Choose Full When:
- Database operations needed
- Deployment integration required
- Complex reasoning needed
- Full-stack development

## Usage

### Option 1: Copy to home directory
```bash
cp mcp-configs/kailash-dev.json ~/.claude.json
```

### Option 2: Reference in Claude session
```bash
claude --mcp-config mcp-configs/kailash-dev.json
```

### Switch configurations
```bash
# Switch to minimal (context efficiency)
cp mcp-configs/kailash-minimal.json ~/.claude.json

# Switch to full (database work)
cp mcp-configs/kailash-full.json ~/.claude.json
```

## MCP Categories

### Essential (Always Needed)
- **github**: PR/issue management (~8k tokens)
- **memory**: Session persistence (~2k tokens)

### Development
- **filesystem**: File operations (~4k tokens)

### Full-Stack
- **postgres**: Database operations (~5k tokens)
- **sequential-thinking**: Extended reasoning (~3k tokens)

## Context Budget Planning

| Configuration | MCP Cost | System | CLAUDE.md | Available |
|---------------|----------|--------|-----------|-----------|
| No MCPs | 0 | ~5k | ~3k | ~192k |
| Minimal | ~10k | ~5k | ~3k | ~182k |
| Development | ~17k | ~5k | ~3k | ~175k |
| Full | ~30k | ~5k | ~3k | ~162k |

## Validation

```bash
# Verify JSON syntax
node -e "JSON.parse(require('fs').readFileSync('mcp-configs/kailash-minimal.json'))"
node -e "JSON.parse(require('fs').readFileSync('mcp-configs/kailash-dev.json'))"
node -e "JSON.parse(require('fs').readFileSync('mcp-configs/kailash-full.json'))"

# Check context in session
# /context
```

## Customization

Start with a tier, add project-specific MCPs:

```json
{
  "mcpServers": {
    // ... base config ...
    "my-custom-mcp": {
      "type": "stdio",
      "command": "my-mcp-server",
      "args": []
    }
  }
}
```

## Kailash Framework Recommendations

### DataFlow Projects
- Use `kailash-full.json` for database operations
- postgres MCP enables direct DB queries

### Nexus Projects
- Use `kailash-dev.json` typically
- Add vercel/railway MCP for deployment

### Kaizen Projects
- Use `kailash-dev.json` with sequential-thinking
- Consider adding memory for agent state

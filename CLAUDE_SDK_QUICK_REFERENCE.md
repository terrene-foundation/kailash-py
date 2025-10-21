# Claude Agent SDK: Quick Reference Guide

## TL;DR - Three Capabilities

| Capability | Type | Discovery | Config | Default |
|-----------|------|-----------|--------|---------|
| **Subagents** | Programmatic | In Python code | `agents` dict | None |
| **Settings** | Filesystem | `.claude/` scan | `setting_sources` list | DISABLED |
| **CLAUDE.md** | Filesystem | `.claude/CLAUDE.md` | `setting_sources` list | DISABLED |

## How to Enable Each

### Enable Subagents (Programmatic)

```python
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

options = ClaudeAgentOptions(
    agents={
        "my-agent": AgentDefinition(
            description="What this agent does",
            prompt="You are...",
            tools=["Read", "Write"],
            model="sonnet",
        )
    }
)
```

### Enable Settings/Skills/CLAUDE.md (Filesystem)

```python
options = ClaudeAgentOptions(
    setting_sources=["project"],  # Loads .claude/
)
# This enables:
# - .claude/CLAUDE.md (injected to context)
# - .claude/settings.json (configuration)
# - .claude/commands/*.md (slash commands)
# - .claude/skills/*/SKILL.md (skills)
```

### Enable All Settings (User + Project)

```python
options = ClaudeAgentOptions(
    setting_sources=["user", "project", "local"],
)
# This enables:
# - ~/.claude/ (user settings)
# - .claude/ (project settings)
# - .claude-local/ (local gitignored settings)
```

### Enable Nothing (Isolated, Default)

```python
options = ClaudeAgentOptions()
# setting_sources NOT specified
# Result: No filesystem settings loaded, fully isolated
```

## Type Definitions Reference

### AgentDefinition

```python
@dataclass
class AgentDefinition:
    description: str                                    # Required: What agent does
    prompt: str                                        # Required: System prompt
    tools: list[str] | None = None                    # Optional: Tool names
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
```

### ClaudeAgentOptions (Relevant Fields)

```python
@dataclass
class ClaudeAgentOptions:
    agents: dict[str, AgentDefinition] | None = None
    setting_sources: list[SettingSource] | None = None
    cwd: str | Path | None = None
    # ... other fields ...

# SettingSource enum
SettingSource = Literal["user", "project", "local"]
```

## Setting Sources Explained

| Source | Location | When | Use Case |
|--------|----------|------|----------|
| **user** | `~/.claude/` | Global | Developer's personal settings |
| **project** | `.claude/` | Per-project | Team/project standard configs |
| **local** | `.claude-local/` | Local only | Machine-specific gitignored settings |

## Data Locations

### User Settings
```
~/.claude/
├── settings.json
├── CLAUDE.md
├── commands/
└── agents/
```

### Project Settings
```
.claude/
├── settings.json
├── CLAUDE.md              ← This gets injected automatically
├── commands/
├── agents/
└── skills/
    └── {skill-name}/
        └── SKILL.md
```

### Local Settings
```
.claude-local/
├── settings.local.json
├── CLAUDE.md
└── commands/
```

## CLI Command Generated

```bash
# Input
options = ClaudeAgentOptions(
    agents={"my-agent": AgentDefinition(...)},
    setting_sources=["project"],
)

# Becomes
claude \
    --output-format stream-json \
    --agents '{"my-agent": {...}}' \
    --setting-sources project \
    --print -- "Your prompt"
```

## Code Pattern: Python SDK → CLI → Runtime

```
┌──────────────────────────────────────┐
│ User Python Code                     │
│ options = ClaudeAgentOptions(...)   │
└──────────────────────────────────────┘
                ↓
┌──────────────────────────────────────┐
│ Python SDK (Type Safety)             │
│ ClaudeAgentOptions validation        │
│ JSON serialization                   │
└──────────────────────────────────────┘
                ↓
┌──────────────────────────────────────┐
│ Command Building                     │
│ Convert options to --flags            │
│ Serialize dicts to JSON              │
└──────────────────────────────────────┘
                ↓
┌──────────────────────────────────────┐
│ Claude Code CLI (Engine)             │
│ File discovery                       │
│ Context injection                    │
│ Agent registration                   │
└──────────────────────────────────────┘
```

## Common Mistakes & Fixes

### Mistake 1: Expecting CLAUDE.md to Load by Default

```python
# ❌ WRONG - CLAUDE.md won't load
options = ClaudeAgentOptions(cwd="/my/project")

# ✅ CORRECT - CLAUDE.md loads
options = ClaudeAgentOptions(
    cwd="/my/project",
    setting_sources=["project"],
)
```

### Mistake 2: Loading Filesystem Agents Instead of Programmatic

```python
# ❌ WRONG - Trying to load from filesystem
options = ClaudeAgentOptions(
    # agents parameter not specified
    setting_sources=["project"],
)
# Result: .claude/agents/*.md might be loaded by CLI, but not guaranteed

# ✅ CORRECT - Define agents in code
options = ClaudeAgentOptions(
    agents={
        "my-agent": AgentDefinition(...)
    }
)
```

### Mistake 3: Mixing Programmatic and Filesystem Agents

```python
# ❌ UNCLEAR - Both mechanisms at once
options = ClaudeAgentOptions(
    agents={"my-agent": AgentDefinition(...)},
    setting_sources=["project"],  # .claude/agents/ also loaded
)

# ✅ CLEAR - Pick one or document why both
# Use programmatic for code-defined agents
# Use filesystem for user-customizable agents
```

## Testing Patterns

### Test 1: Isolated (No Settings)

```python
def test_isolated():
    options = ClaudeAgentOptions()  # No setting_sources
    # Verify: No .claude/ content loaded
    # Verify: Only programmatic agents available
```

### Test 2: Project Settings Only

```python
def test_project_only():
    options = ClaudeAgentOptions(
        setting_sources=["project"],
    )
    # Verify: .claude/CLAUDE.md injected
    # Verify: User settings NOT loaded
```

### Test 3: Combined Settings

```python
def test_combined():
    options = ClaudeAgentOptions(
        setting_sources=["user", "project"],
    )
    # Verify: Both ~/.claude/ and .claude/ loaded
    # Verify: Conflicts resolved (project overrides user)
```

### Test 4: Programmatic Agents

```python
def test_programmatic():
    options = ClaudeAgentOptions(
        agents={
            "test-agent": AgentDefinition(...)
        }
    )
    # Verify: Agent available for invocation
    # Verify: Agent has correct tools/model
```

## File vs. Programmatic: When to Use Each

### Use Programmatic (`agents` dict)
- Defining agents in code (most use cases)
- Dynamic agent creation
- Testing
- CI/CD pipelines
- Keeping agents version-controlled with code
- Type safety

### Use Filesystem (`.claude/agents/`)
- User customization (let users add agents)
- Team standards (shared across projects)
- Interactive development
- Large agent collections
- Separation of concerns

### Use Both
- Base agents in code (templates)
- User customizations in .claude/
- Document interaction clearly

## CLAUDE.md Content Pattern

```markdown
# Project Context

## Key Principles

1. Always use our framework
2. Never write code from scratch

## Implementation Rules

- Use async/await for all I/O
- Follow naming conventions

## Tool Guidelines

- Read: Use for exploring
- Write: Use for creation
- Bash: Use for execution

## Critical Directives

- ALWAYS run tests after changes
- NEVER commit without review
```

## Migration Checklist (v0.0.x → v0.1.0+)

```
[ ] Audit code for auto-loaded CLAUDE.md assumptions
[ ] Add setting_sources=["project"] if CLAUDE.md needed
[ ] Test in CI/CD with no setting_sources
[ ] Document setting_sources requirement
[ ] Update examples to show explicit loading
[ ] Remove implicit .claude/ dependencies
```

## Decision Tree: Which Mechanism to Use

```
Need to customize agent behavior per run?
├─ YES → Use programmatic agents (ClaudeAgentOptions.agents)
└─ NO → Continue

Need persistent team standards?
├─ YES → Use .claude/ settings + CLAUDE.md
└─ NO → Use isolated mode (no setting_sources)

Need user customization?
├─ YES → Use .claude/ for extensibility
└─ NO → Use programmatic for simplicity

In CI/CD?
├─ YES → Use programmatic agents + no setting_sources
└─ NO → Continue

Local development with global settings?
├─ YES → Use setting_sources=["user", "project"]
└─ NO → Use setting_sources=["project"]
```

## Performance Notes

- Programmatic agents: Fast (in-memory)
- Filesystem scanning: Slower (I/O bound)
- JSON serialization: Negligible overhead
- CLI startup: Dominant cost

## Gotchas

1. **Setting sources order matters** - User settings loaded first, project overrides
2. **setting_sources=None is NOT the same as setting_sources=[]** - None means disabled, [] means enabled but empty
3. **CLAUDE.md only loads when "project" is in setting_sources** - Not loaded for user/local only
4. **Skills and commands are CLI-only** - Not exposed in Python SDK types
5. **Agent names must be CLI-safe** - Avoid special characters in agent names

## Real-World Example

```python
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
)

# Production setup with team standards + custom agents
options = ClaudeAgentOptions(
    # Load team standards from project
    setting_sources=["project"],

    # Add custom agents for this specific session
    agents={
        "my-reviewer": AgentDefinition(
            description="Code review specialist",
            prompt="You are a code reviewer focusing on security...",
            tools=["Read", "Grep"],
            model="sonnet",
        ),
    },

    cwd="/my/project",
)

async with ClaudeSDKClient(options=options) as client:
    # CLAUDE.md from .claude/ is injected
    # /commit slash command available (from .claude/commands/)
    # my-reviewer agent available
    # /code-reviewer skill available (from .claude/skills/)

    await client.query("Use the my-reviewer agent to check this PR")
```

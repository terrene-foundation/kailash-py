# Claude Agent SDK Architecture: Design Patterns for Kaizen

## Quick Reference

### Three Capability Types

```
┌─────────────────────────────────────────────────────────────────┐
│           CLAUDE AGENT SDK USER-DEFINED CAPABILITIES            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. SUBAGENTS (Programmatic)                                   │
│     └─ In-memory Python objects                               │
│     └─ Passed via --agents JSON flag                          │
│     └─ Type: ClaudeAgentOptions.agents                        │
│     └─ Invoked via: /agent-name command                       │
│                                                                 │
│  2. SETTINGS & SKILLS (Filesystem)                            │
│     └─ ~/.claude/ (user)                                      │
│     └─ .claude/ (project)                                     │
│     └─ .claude-local/ (local)                                 │
│     └─ Control: setting_sources parameter                     │
│     └─ Default: NOT loaded (explicit opt-in)                  │
│                                                                 │
│  3. CLAUDE.MD (Context Auto-Injection)                        │
│     └─ Discovered at .claude/CLAUDE.md                        │
│     └─ Auto-loaded when setting_sources includes "project"    │
│     └─ Injected into system prompt                            │
│     └─ User-editable markdown file                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Architecture Pattern: Delegation Model

### Python SDK Does NOT Load Files

```
User Code
  ↓
ClaudeAgentOptions (configuration objects)
  ↓
SubprocessCLITransport (command builder)
  ↓
CLI subprocess spawning
  ↓
Claude Code CLI (actual file loading)
```

**Why?**
- Keeps Python SDK simple
- Avoids path conflicts
- All filesystem logic in one place (CLI)
- Testable via CLI contracts

### Key Design Principle: Explicit Over Implicit

```python
# ❌ Before (v0.0.x): Auto-loaded everything
# CLAUDE.md was loaded
# .claude/settings.json was loaded
# /commands/ were registered
# ALL without user asking

# ✅ After (v0.1.0+): Explicit opt-in
options = ClaudeAgentOptions(
    setting_sources=["project", "user"],  # Explicitly enable
)
# Now CLAUDE.md is loaded
```

## Implementation Patterns from Claude Agent SDK

### Pattern 1: Type-Safe Configuration (AgentDefinition)

```python
@dataclass
class AgentDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
```

**Lessons for Kaizen**:
- Use dataclasses, not raw dicts
- Provide sensible defaults (None for optional fields)
- Use Literal types for constrained values
- Always include description fields for CLI display

### Pattern 2: Source Enumeration (SettingSource)

```python
SettingSource = Literal["user", "project", "local"]

# In options
setting_sources: list[SettingSource] | None = None
```

**Lessons for Kaizen**:
- Use Literal types for enumeration
- Make list-based composition explicit
- Support multiple sources (user + project + local)
- None = disabled (not implicit loading)

### Pattern 3: JSON Serialization for CLI

```python
# Command building
if self._options.agents:
    agents_dict = {
        name: {k: v for k, v in asdict(agent_def).items() if v is not None}
        for name, agent_def in self._options.agents.items()
    }
    cmd.extend(["--agents", json.dumps(agents_dict)])
```

**Lessons for Kaizen**:
- Convert objects to JSON for CLI flags
- Filter None values (clean JSON)
- Use `asdict()` for dataclass conversion
- CLI gets JSON, not Python objects

### Pattern 4: Filesystem Discovery Delegation

```python
# Python SDK
cmd.extend(["--setting-sources", ",".join(setting_sources)])

# Claude Code CLI handles:
# - Scanning ~/.claude/ (if "user" specified)
# - Scanning .claude/ (if "project" specified)
# - Loading CLAUDE.md
# - Loading settings.json
# - Registering commands
# - Registering skills
```

**Lessons for Kaizen**:
- Don't load files in Python SDK
- Pass control flags to runtime
- Let runtime handle discovery
- Keep SDK lightweight

## File Structure by Setting Source

```
User Settings (~/.claude/):
  ├── settings.json
  ├── settings.user.json
  ├── CLAUDE.md          ← User's global context
  ├── commands/
  │   ├── my-command.md
  │   └── helper.md
  └── agents/
      └── my-agent.md

Project Settings (.claude/):
  ├── settings.json
  ├── settings.project.json
  ├── CLAUDE.md          ← Project context (THIS ONE IS AUTO-LOADED)
  ├── commands/
  │   ├── commit.md
  │   └── deploy.md
  └── skills/
      ├── python-expert/
      │   └── SKILL.md
      └── code-reviewer/
          └── SKILL.md

Local Settings (.claude-local/):
  ├── settings.local.json
  ├── CLAUDE.md
  └── commands/
      └── local-command.md
```

## Configuration Examples

### Example 1: Isolated (Default)

```python
options = ClaudeAgentOptions(
    cwd="/my/project",
    # setting_sources NOT specified
)

# Result:
# ✓ Only programmatic agents available (if specified in code)
# ✗ No .claude/ settings loaded
# ✗ No CLAUDE.md loaded
# ✗ No slash commands from .claude/commands/
```

### Example 2: Project-Only

```python
options = ClaudeAgentOptions(
    cwd="/my/project",
    setting_sources=["project"],
)

# Result:
# ✓ .claude/ settings loaded
# ✓ CLAUDE.md loaded and injected
# ✓ Slash commands from .claude/commands/
# ✓ Skills from .claude/skills/
# ✗ User settings NOT loaded
```

### Example 3: Full Integration

```python
options = ClaudeAgentOptions(
    cwd="/my/project",
    setting_sources=["user", "project", "local"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Reviews code",
            prompt="You are a code reviewer",
            tools=["Read", "Grep"],
        ),
    },
)

# Result:
# ✓ User settings loaded
# ✓ Project settings loaded
# ✓ Local settings loaded
# ✓ Programmatic agents registered
# ✓ CLAUDE.md injected into context
# ✓ All slash commands available
# ✓ All skills available
```

## Breaking Change Analysis: v0.1.0

### What Changed

```
BEFORE (implicit):
- CLAUDE.md auto-loaded ← BIG CHANGE
- settings.json auto-loaded
- /commands/ auto-registered
- SDK inherited project context automatically

AFTER (explicit):
- Must specify setting_sources
- setting_sources=None = no settings loaded
- Fully isolated by default
- CI/CD gets consistent behavior
```

### Migration Path

```python
# ❌ Old code (might break in v0.1.0+)
options = ClaudeAgentOptions(cwd="/my/project")
# CLAUDE.md was loaded, now it's NOT

# ✅ New code
options = ClaudeAgentOptions(
    cwd="/my/project",
    setting_sources=["user", "project"],  # Explicit!
)
# CLAUDE.md is loaded
```

## Type Hierarchy

```python
ClaudeAgentOptions
├── agents: dict[str, AgentDefinition]
│   └── AgentDefinition
│       ├── description: str
│       ├── prompt: str
│       ├── tools: list[str] | None
│       └── model: Literal[...]
├── setting_sources: list[SettingSource] | None
│   └── SettingSource = Literal["user", "project", "local"]
├── cwd: str | Path | None
└── ... other options ...
```

## Implementation Checklist for Kaizen

Based on Claude Agent SDK patterns:

### Configuration Layer
- [ ] Create type-safe config dataclass (like AgentDefinition)
- [ ] Use Literal types for enumerations
- [ ] Support optional fields with defaults
- [ ] Include description fields for discovery

### Storage Layer
- [ ] Support multiple setting sources (user/project/local)
- [ ] Make loading explicit (opt-in), not implicit
- [ ] Use well-known directories (.kaizen/, .kaizen-local/)
- [ ] Support KAIZEN.md for context injection

### CLI Integration Layer
- [ ] Serialize config to JSON for CLI flags
- [ ] Filter None values before serialization
- [ ] Delegate filesystem operations to runtime
- [ ] Document expected CLI flags

### Discovery Layer
- [ ] Don't scan filesystem in Python
- [ ] Pass control flags to runtime
- [ ] Let runtime handle .kaizen/ directory structure
- [ ] Support dynamic agent registration

### Testing Layer
- [ ] Test each setting_source separately
- [ ] Test combinations (user+project, etc.)
- [ ] Test isolated (setting_sources=None)
- [ ] Test programmatic agents override filesystem agents

## Recommended Kaizen Architecture

```python
# 1. Type Definitions (kaizen/types.py)
@dataclass
class SpecialistDefinition:
    description: str
    system_prompt: str
    available_tools: list[str] | None = None
    model: str | None = None

# 2. Configuration (kaizen/options.py)
@dataclass
class KaizenOptions:
    specialists: dict[str, SpecialistDefinition] | None = None
    setting_sources: list[Literal["user", "project", "local"]] | None = None
    cwd: str | Path | None = None

# 3. Command Building (kaizen/runtime.py)
def build_command(options: KaizenOptions) -> list[str]:
    cmd = ["kaizen"]
    if options.specialists:
        cmd.extend(["--specialists", json.dumps(...)])
    if options.setting_sources:
        cmd.extend(["--setting-sources", ",".join(...)])
    return cmd

# 4. User Code
options = KaizenOptions(
    specialists={
        "dataflow-specialist": SpecialistDefinition(
            description="Database expertise",
            system_prompt="You are a DataFlow expert",
            available_tools=["Read", "Write"],
        ),
    },
    setting_sources=["user", "project"],
    cwd="/my/kaizen/project",
)

result = await kaizen_runtime.execute(options)
```

## Red Flags to Avoid

❌ **DON'T** auto-load .claude/ without explicit opt-in
- Breaks in CI/CD
- Leaks developer settings
- Makes behavior non-deterministic

❌ **DON'T** require filesystem for agents
- Prevents programmatic creation
- Locks users into files
- Can't be tested easily

❌ **DON'T** scan filesystem in Python SDK
- Duplicates CLI logic
- Creates maintenance burden
- Causes path conflicts

❌ **DON'T** use raw dicts for configuration
- No type safety
- No IDE autocomplete
- Easy to make mistakes

✅ **DO** support both programmatic and filesystem agents
✅ **DO** make settings explicit (opt-in)
✅ **DO** delegate filesystem logic to runtime
✅ **DO** use type-safe configuration classes
✅ **DO** test all setting_source combinations
✅ **DO** document migration path for users

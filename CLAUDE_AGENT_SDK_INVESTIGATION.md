# Claude Code SDK Python: User-Defined Capabilities Investigation

## EXECUTIVE SUMMARY

The Claude Agent SDK (Python) provides THREE mechanisms for user-defined capabilities, all delegated to the underlying Claude Code CLI:

1. **Subagents** (.claude/agents/) - Programmatic via `agents` parameter
2. **Settings & Skills** (.claude/) - File-based via `setting_sources` parameter
3. **Auto-loaded Context** (CLAUDE.md) - File-based via `setting_sources` parameter

**CRITICAL FINDING**: Unlike the CLI which auto-loads filesystem settings by default, the **SDK explicitly defaults to NOT loading any settings** to ensure predictable, isolated behavior. Settings must be explicitly enabled via `setting_sources`.

---

## 1. SUBAGENTS (Programmatic Definition)

### 1.1 How Subagents Are Loaded

**Location**: Programmatically via `ClaudeAgentOptions.agents` parameter (NOT filesystem)

**Path Resolution**: Not filesystem-based. Agents are defined inline in Python code.

**Loading Mechanism**:
- User defines `AgentDefinition` objects in Python
- Passed to CLI via `--agents` JSON flag
- No directory scanning or file discovery

### 1.2 Data Structure (AgentDefinition)

```python
# File: src/claude_agent_sdk/types.py, lines 29-36

@dataclass
class AgentDefinition:
    """Agent definition configuration."""

    description: str           # Agent description (required)
    prompt: str               # Agent system prompt (required)
    tools: list[str] | None = None      # List of allowed tools (optional)
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
```

**Fields**:
- `description`: Human-readable description for Claude to understand when to use agent
- `prompt`: Custom system prompt for the agent's behavior
- `tools`: Optional list of tool names agent can use (e.g., ["Read", "Write", "Bash"])
- `model`: Optional model override (sonnet/opus/haiku/inherit)

### 1.3 Invocation Mechanism

Users invoke agents via slash commands in conversation:
```
/agent-name <request>
```

Claude can also suggest using agents when appropriate.

### 1.4 API Surface (ClaudeAgentOptions)

```python
# File: src/claude_agent_sdk/types.py, line 542

@dataclass
class ClaudeAgentOptions:
    # ... other fields ...
    agents: dict[str, AgentDefinition] | None = None
```

### 1.5 Configurability

**Status**: NOT configurable path-wise (programmatic only)

The agents parameter:
- Is always passed via `--agents` CLI flag with JSON serialization
- Never loads from filesystem
- Provides complete isolation from local .claude/agents/ directory

### 1.6 CLI Integration

**Command Building** (subprocess_cli.py, lines 171-176):

```python
if self._options.agents:
    agents_dict = {
        name: {k: v for k, v in asdict(agent_def).items() if v is not None}
        for name, agent_def in self._options.agents.items()
    }
    cmd.extend(["--agents", json.dumps(agents_dict)])
```

**Example JSON sent to CLI**:
```json
{
  "code-reviewer": {
    "description": "Reviews code for best practices",
    "prompt": "You are a code reviewer...",
    "tools": ["Read", "Grep"],
    "model": "sonnet"
  },
  "doc-writer": {
    "description": "Writes documentation",
    "prompt": "You are a documentation expert...",
    "tools": ["Read", "Write", "Edit"]
  }
}
```

### 1.7 Code Examples from SDK

**Basic Usage** (examples/agents.py):
```python
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    query,
)

options = ClaudeAgentOptions(
    agents={
        "code-reviewer": AgentDefinition(
            description="Reviews code for best practices and potential issues",
            prompt="You are a code reviewer. Analyze code for bugs...",
            tools=["Read", "Grep"],
            model="sonnet",
        ),
    },
)

async for message in query(
    prompt="Use the code-reviewer agent to review the code",
    options=options,
):
    print(message)
```

**Testing** (e2e-tests/test_agents_and_settings.py, lines 20-47):
```python
async def test_agent_definition():
    options = ClaudeAgentOptions(
        agents={
            "test-agent": AgentDefinition(
                description="A test agent for verification",
                prompt="You are a test agent. Always respond...",
                tools=["Read"],
                model="sonnet",
            )
        },
        max_turns=1,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("What is 2 + 2?")

        async for message in client.receive_response():
            if isinstance(message, SystemMessage) and message.subtype == "init":
                agents = message.data.get("agents", [])
                assert "test-agent" in agents
                break
```

---

## 2. SKILLS & SETTINGS (File-Based)

### 2.1 How Skills/Settings Are Loaded

**Location**: Filesystem directories
- **User settings**: `~/.claude/` (global user directory)
- **Project settings**: `.claude/` (project directory)
- **Local settings**: `.claude-local/` (gitignored local directory)

**Path Resolution**: Hardcoded but scoped via `setting_sources`

**Loading Mechanism**:
- Settings are NOT loaded by default (v0.1.0 breaking change)
- Explicitly enabled via `setting_sources` parameter
- CLI scans filesystem for:
  - `settings.json` / `settings.local.json` - configuration
  - `.claude/commands/` - slash commands
  - `.claude/agents/` - agent definitions (filesystem-based)
  - `CLAUDE.md` - project context (auto-loaded when settings enabled)

### 2.2 SettingSource Type Definition

```python
# File: src/claude_agent_sdk/types.py, line 18

SettingSource = Literal["user", "project", "local"]
```

### 2.3 Skills Structure (Inferred from CLI)

Skills are NOT explicitly defined in the Python SDK. They're managed by Claude Code CLI:
- Located in: `.claude/skills/*/SKILL.md`
- Structure: Markdown files with metadata
- Discovery: CLI scans `.claude/skills/` directory
- Invocation: Via `/skill-name` commands
- Progressive disclosure: Metadata → SKILL.md → additional files

**Note**: Skills aren't exposed via Python SDK types. They're CLI-only features.

### 2.4 CLI Integration

**Command Building** (subprocess_cli.py, lines 178-183):

```python
sources_value = (
    ",".join(self._options.setting_sources)
    if self._options.setting_sources is not None
    else ""
)
cmd.extend(["--setting-sources", sources_value])
```

**Default Behavior** (CHANGELOG.md, line 64):
> "Settings files (settings.json, CLAUDE.md), slash commands, and subagents are
> no longer loaded automatically. This ensures SDK applications have predictable
> behavior independent of local filesystem configurations"

### 2.5 Configurability

**Status**: Fully configurable via `setting_sources` parameter

```python
# File: src/claude_agent_sdk/types.py, line 544

@dataclass
class ClaudeAgentOptions:
    setting_sources: list[SettingSource] | None = None
```

**Valid Combinations**:
- `None` (default): NO settings loaded
- `["user"]`: Only global user settings
- `["project"]`: Only project settings
- `["local"]`: Only local gitignored settings
- `["user", "project"]`: User + project
- `["user", "project", "local"]`: All sources

### 2.6 Code Examples from SDK

**Default (Isolated)** (examples/setting_sources.py, lines 47-71):
```python
# No settings loaded by default
options = ClaudeAgentOptions(
    cwd="/path/to/project",
    # setting_sources NOT specified - defaults to None
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("What is 2 + 2?")
    async for msg in client.receive_response():
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            commands = extract_slash_commands(msg)
            # Result: NO custom slash commands available
```

**User Settings Only** (examples/setting_sources.py, lines 75-103):
```python
# Load only user-level settings
options = ClaudeAgentOptions(
    setting_sources=["user"],
    cwd=sdk_dir,
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("What is 2 + 2?")
    # Result: Project slash commands NOT available
    #         User slash commands ARE available
```

**Project + User Settings** (examples/setting_sources.py, lines 107-133):
```python
# Load both project and user settings
options = ClaudeAgentOptions(
    setting_sources=["user", "project"],
    cwd=sdk_dir,
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("What is 2 + 2?")
    # Result: Both project AND user settings loaded
    #         .claude/commands/commit.md is available
```

**Testing** (e2e-tests/test_agents_and_settings.py, lines 136-165):
```python
async def test_setting_sources_project_included():
    """Test that setting_sources=['user', 'project'] includes settings."""
    project_dir = Path(tmpdir)
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)

    # Create local settings
    settings_file = claude_dir / "settings.local.json"
    settings_file.write_text('{"outputStyle": "local-test-style"}')

    # Enable project settings
    options = ClaudeAgentOptions(
        setting_sources=["user", "project", "local"],
        cwd=project_dir,
        max_turns=1,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("What is 2 + 2?")

        async for message in client.receive_response():
            if isinstance(message, SystemMessage) and message.subtype == "init":
                output_style = message.data.get("output_style")
                assert output_style == "local-test-style"
                break
```

---

## 3. AUTO-LOADED CONTEXT (CLAUDE.md)

### 3.1 How CLAUDE.md Is Loaded

**Location**: Filesystem
- **Project-level**: `.claude/` directory (via setting_sources)
- **Implicit discovery**: When `setting_sources` includes "project"

**Path Resolution**: Hardcoded filename `CLAUDE.md`, loaded from project root

**Loading Mechanism**:
1. User specifies `setting_sources=["project", ...]`
2. CLI discovers `.claude/CLAUDE.md` or `.claude/context.md` (inferred)
3. Content injected into system context
4. NOT explicitly exposed in Python SDK - managed by CLI

**Discovery Logic** (Inferred from CLI behavior):
- CLI searches `.claude/` for CLAUDE.md
- Filename is hardcoded (NOT configurable)
- Auto-loaded when setting_sources includes "project"

### 3.2 Data Structure

**CLAUDE.md Format** (Markdown file):
```markdown
# Project Context

## Framework Instructions

1. Always use kailash SDK with its frameworks
2. Never attempt to write code from scratch

## Implementation Patterns

### For Docker/FastAPI Deployment
- Use AsyncLocalRuntime
- Never use LocalRuntime with threads

## Critical Rules
- ALWAYS: runtime.execute(workflow.build())
- String-based nodes: workflow.add_node("NodeName", "id", {})
```

**Location of Example**: `./repos/dev/kailash_kaizen/CLAUDE.md`

### 3.3 Invocation Mechanism

CLAUDE.md is NOT invoked - it's injected as context:
1. When `setting_sources=["project", ...]` is set
2. CLI loads CLAUDE.md content
3. Content is prepended/appended to system prompt
4. Claude sees it as part of instructions

### 3.4 API Surface

**Configuration** (types.py, line 544):
```python
@dataclass
class ClaudeAgentOptions:
    setting_sources: list[SettingSource] | None = None
```

**No explicit CLAUDE.md parameter** - it's auto-loaded via setting_sources

### 3.5 Configurability

**Status**: Hardcoded to `CLAUDE.md`
- Filename: NOT configurable
- Directory: Controlled via `setting_sources` (only "project" source)
- Content: User-defined (arbitrary markdown)

**Control Points**:
1. Enable/disable via `setting_sources`: Yes
2. Custom filename: No
3. Custom content location: No

### 3.6 CLI Integration

**Command Building** (subprocess_cli.py, lines 178-183):
```python
sources_value = (
    ",".join(self._options.setting_sources)
    if self._options.setting_sources is not None
    else ""
)
cmd.extend(["--setting-sources", sources_value])

# CLI interprets "project" source and discovers:
# - .claude/CLAUDE.md (auto-loaded)
# - .claude/settings.json
# - .claude/commands/*.md
```

### 3.7 Code Examples from SDK

**Enable CLAUDE.md Loading**:
```python
from claude_agent_sdk import ClaudeAgentOptions, query

options = ClaudeAgentOptions(
    setting_sources=["project", "user"],
    cwd="/path/to/project",
)

async for message in query(
    prompt="Help me with this code",
    options=options,
):
    # CLAUDE.md is now auto-loaded and injected as context
    print(message)
```

**Disable CLAUDE.md Loading** (Default):
```python
options = ClaudeAgentOptions(
    cwd="/path/to/project",
    # setting_sources not specified - CLAUDE.md NOT loaded
)

async for message in query(
    prompt="Help me with this code",
    options=options,
):
    # CLAUDE.md is NOT loaded - isolated behavior
    print(message)
```

---

## 4. DETAILED COMPARISON TABLE

| Capability | Discovery | Path | Configuration | API |
|-----------|-----------|------|---------------|-----|
| **Subagents** | Programmatic | N/A (in-memory) | `agents` parameter | `ClaudeAgentOptions.agents: dict[str, AgentDefinition]` |
| **Settings** | Filesystem scanning | `~/.claude/`, `.claude/`, `.claude-local/` | `setting_sources` parameter | `ClaudeAgentOptions.setting_sources: list[SettingSource]` |
| **Skills** | Filesystem scanning | `.claude/skills/` | Implicit (via setting_sources) | Not exposed - CLI only |
| **CLAUDE.md** | Filesystem discovery | `.claude/CLAUDE.md` | `setting_sources` parameter | Not exposed - CLI only |

---

## 5. COMPLETE DATA FLOW

### 5.1 Subagents Flow

```
Python Code
    ↓
ClaudeAgentOptions(agents={...})
    ↓
SubprocessCLITransport._build_command()
    ↓
JSON serialization: {"agent-name": {"description": "...", "prompt": "...", ...}}
    ↓
CLI flag: --agents '{"agent-name": {...}}'
    ↓
Claude Code CLI
    ↓
In-process agent registration
    ↓
User invokes: /agent-name request
```

### 5.2 Settings/Skills/CLAUDE.md Flow

```
Python Code
    ↓
ClaudeAgentOptions(setting_sources=["user", "project", "local"])
    ↓
SubprocessCLITransport._build_command()
    ↓
CLI flag: --setting-sources user,project,local
    ↓
Claude Code CLI
    ↓
Filesystem scan:
  - ~/.claude/ (user)
  - .claude/ (project)
    - settings.json
    - settings.local.json
    - CLAUDE.md ← Auto-loaded
    - commands/*.md
    - agents/*.md
  - .claude-local/ (local)
    ↓
Settings merged/injected
    ↓
CLAUDE.md content added to system context
    ↓
Skills registered
    ↓
Slash commands available
```

---

## 6. BREAKING CHANGE: v0.1.0 Settings Isolation

**CHANGELOG.md, Lines 62-65**:
> "No filesystem settings by default: Settings files (settings.json, CLAUDE.md),
> slash commands, and subagents are no longer loaded automatically. This ensures
> SDK applications have predictable behavior independent of local filesystem
> configurations."

**Impact**:
- **Before**: All .claude/ content auto-loaded
- **After**: Must explicitly enable via `setting_sources`
- **Reason**: Isolate SDK applications from local developer settings
- **Migration**: Explicitly specify `setting_sources` if you need settings

---

## 7. KEY ARCHITECTURAL INSIGHTS

### 7.1 No Filesystem Abstraction

The Python SDK has **NO abstraction layer** for settings:
- No SettingLoader class
- No file discovery logic
- All delegated to Claude Code CLI
- CLI handles all filesystem operations

### 7.2 Delegation Model

```
Python SDK
  └─ ClaudeAgentOptions (configuration)
      └─ SubprocessCLITransport (command builder)
          └─ CLI subprocess (actual implementation)
              └─ Claude Code CLI (engine)
```

### 7.3 String-Based vs Path-Based

| Type | How Specified | Storage |
|------|--------------|---------|
| Subagents | String (name) | In Python objects |
| Settings | Path-based | Filesystem |
| Skills | Path-based | Filesystem (.claude/skills/) |
| CLAUDE.md | Hardcoded filename | Filesystem (.claude/CLAUDE.md) |

### 7.4 Isolation by Default

**Philosophy Change** (v0.1.0):
- Old: Implicit loading (auto-load everything)
- New: Explicit loading (opt-in via setting_sources)
- Reason: CI/CD, testing, production isolation

---

## 8. COMPLETE SOURCE FILE LOCATIONS

### Types Definitions
- `./repos/projects/claude-agent-sdk-python/src/claude_agent_sdk/types.py`
  - AgentDefinition (lines 29-36)
  - SettingSource (line 18)
  - ClaudeAgentOptions (lines 501-545)

### Command Building
- `./repos/projects/claude-agent-sdk-python/src/claude_agent_sdk/_internal/transport/subprocess_cli.py`
  - _build_command() (lines 87-202)
  - Agents handling (lines 171-176)
  - Settings handling (lines 178-183)

### Public API
- `./repos/projects/claude-agent-sdk-python/src/claude_agent_sdk/__init__.py`
  - AgentDefinition export (line 19)
  - SettingSource export (line 42)

### Examples
- `./repos/projects/claude-agent-sdk-python/examples/agents.py` - Agent usage
- `./repos/projects/claude-agent-sdk-python/examples/setting_sources.py` - Settings control

### Tests
- `./repos/projects/claude-agent-sdk-python/e2e-tests/test_agents_and_settings.py`

### Documentation
- `./repos/projects/claude-agent-sdk-python/CHANGELOG.md` - Breaking changes
- `./repos/projects/claude-agent-sdk-python/README.md` - Quick start

---

## 9. DESIGN IMPLICATIONS FOR KAIZEN

### Key Findings

1. **No File Loading in SDK** - Python SDK delegates all filesystem operations to CLI
2. **Explicit Configuration** - Settings are opt-in, not auto-loaded
3. **JSON Serialization** - Agents passed as JSON via CLI flags
4. **Hardcoded Paths** - But paths are fully controlled by CLI
5. **No Skills API** - Skills are CLI-only, not exposed in Python SDK

### Recommendations for Kaizen Framework

1. **Follow Delegation Model**: Don't load files in Python, pass config to runtime
2. **Explicit Over Implicit**: Make settings opt-in, not auto-loaded
3. **CLI Integration**: Use CLI flags for configuration, not direct file loading
4. **Type Safety**: Use dataclasses/TypedDict like AgentDefinition
5. **Hardcoded Paths**: Use well-known directories (.claude/) but make them configurable
6. **Progressive Disclosure**: Metadata first, then detailed files on demand

---

## 10. COMPLETE CODE EXAMPLE

```python
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    SystemMessage,
)

# Define agents programmatically
options = ClaudeAgentOptions(
    agents={
        "code-reviewer": AgentDefinition(
            description="Reviews code for issues",
            prompt="You are an expert code reviewer",
            tools=["Read", "Grep"],
            model="sonnet",
        ),
        "doc-writer": AgentDefinition(
            description="Writes documentation",
            prompt="You are a technical writer",
            tools=["Read", "Write"],
        ),
    },
    # Enable loading of project and user settings
    setting_sources=["user", "project"],
    # This enables:
    # - ~/.claude/settings.json (user)
    # - .claude/settings.json (project)
    # - .claude/CLAUDE.md (auto-loaded)
    # - .claude/commands/*.md (slash commands)
    cwd="/path/to/project",
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Use the code-reviewer agent to review this code")

    async for message in client.receive_response():
        if isinstance(message, SystemMessage):
            if message.subtype == "init":
                print(f"Available agents: {message.data.get('agents', [])}")
                print(f"Available commands: {message.data.get('slash_commands', [])}")
```

# ClaudeCodeAgent Architecture Guide

**Version**: 0.1.0
**Status**: Production Ready
**Test Coverage**: 38/38 tests passing
**Created**: 2025-10-22

---

## Overview

ClaudeCodeAgent implements Claude Code's proven autonomous coding architecture, enabling 30+ hour autonomous coding sessions with the `while(tool_calls_exist)` pattern. This agent is specifically designed for long-running coding tasks with built-in context management, diff-first workflows, and system reminders to combat model drift.

## Table of Contents

1. [What is ClaudeCodeAgent?](#what-is-claudecodeagent)
2. [Architecture](#architecture)
3. [Key Features](#key-features)
4. [15-Tool Ecosystem](#15-tool-ecosystem)
5. [Configuration](#configuration)
6. [Usage Examples](#usage-examples)
7. [Advanced Features](#advanced-features)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## What is ClaudeCodeAgent?

ClaudeCodeAgent is a specialized autonomous agent that implements Claude Code's production architecture patterns:

### Core Characteristics

- **15-Tool Ecosystem**: File operations, search, execution, web access, workflow management
- **Diff-First Workflow**: Shows minimal diffs before applying changes
- **System Reminders**: Periodic state injection to combat model drift
- **Context Management**: 92% compression trigger with intelligent reduction
- **CLAUDE.md Memory**: Project-specific conventions and context
- **100+ Cycle Sessions**: Supports multi-hour autonomous execution

### Comparison with BaseAutonomousAgent

| Feature | BaseAutonomousAgent | ClaudeCodeAgent |
|---------|---------------------|-----------------|
| Max Cycles | 20 (default) | 100 (default) |
| Context Management | Manual | 92% trigger + compression |
| System Reminders | No | Yes (every 10 cycles) |
| Diff Workflow | Manual | Built-in |
| Tool Ecosystem | Varies | 15 tools (standardized) |
| Project Memory | No | CLAUDE.md integration |
| Target Use Case | General | Coding tasks |
| Session Duration | Minutes | Hours |

---

## Architecture

### Class Hierarchy

```
BaseAgent
    ↓
BaseAutonomousAgent
    ↓
ClaudeCodeAgent
```

### Execution Flow

```
1. execute_autonomously(task)
   ↓
2. Load CLAUDE.md (project memory)
   ↓
3. Setup 15-tool ecosystem
   ↓
4. Create plan (if enabled)
   ↓
5. Autonomous loop (while tool_calls exist):
   ├── Cycle N: Execute with tools
   ├── Apply changes with diff preview
   ├── Save checkpoint (every 10 cycles)
   ├── Inject reminder (every 10 cycles)
   ├── Check context usage (compress at 92%)
   └── Check convergence (objective via tool_calls)
   ↓
6. Return result + metadata
```

### Key Components

1. **ClaudeCodeConfig**: Configuration with Claude Code-specific parameters
2. **Tool Ecosystem**: 15 standardized tools for coding tasks
3. **Diff Engine**: Preview changes before applying
4. **Reminder System**: Combat drift with periodic state reminders
5. **Context Manager**: Monitor and compress context at 92% threshold

---

## Key Features

### 1. 15-Tool Ecosystem

ClaudeCodeAgent provides 15 standardized tools:

**File Operations** (5 tools):
- `read_file` - Read file contents
- `write_file` - Create or overwrite files
- `edit_file` - Apply diff-based edits
- `delete_file` - Remove files
- `list_directory` - List directory contents

**Search Operations** (2 tools):
- `glob_search` - Find files by pattern (e.g., `**/*.py`)
- `grep_search` - Search file contents by regex

**Execution** (1 tool):
- `bash_command` - Execute shell commands

**Web Access** (2 tools):
- `fetch_url` - HTTP GET requests
- `web_search` - Search web

**Workflow Management** (2 tools):
- `todo_write` - Update task list
- `task_spawn` - Create sub-agents

**Additional** (3 tools):
- `python_repl` - Execute Python code
- `ask_user` - Request user input
- `pause_execution` - Pause for manual intervention

### 2. Diff-First Workflow

Show changes before applying:

```python
# Original file
def calculate_total(items):
    return sum(items)

# Diff preview
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,5 @@
 def calculate_total(items):
-    return sum(items)
+    """Calculate total of items with validation."""
+    if not items:
+        return 0
+    return sum(items)

# User can review before applying
```

### 3. System Reminders

Combat model drift with periodic state injection:

```
System Reminder (Cycle 10):
- Current task: Refactor authentication module
- Plan status: 3/5 tasks completed
  ✓ Design new structure
  ✓ Implement dependency injection
  ✓ Update tests
  ⏳ Update documentation
  ⏳ Deploy changes
- Context usage: 78.5%
- Last action: Updated UserAuth class with DI pattern
- Next action: Continue with documentation updates
```

### 4. Context Management

Monitor context usage and compress at 92% threshold:

```python
# Context monitoring
if self.context_usage > self.config.context_threshold:  # 0.92
    # Compress context
    self._compress_context()
    # Reduces to ~50% of max context
    # Preserves important information:
    #   - Current task
    #   - Active plan
    #   - Recent actions (last 5)
    #   - Key observations
```

### 5. CLAUDE.md Integration

Load project-specific conventions and context:

```markdown
# CLAUDE.md
## Project Conventions
- Use absolute imports
- Follow PEP 8 style
- Add docstrings to all functions
- Run pytest before committing

## Architecture
- /src - Source code
- /tests - Test files
- /docs - Documentation
```

Agent loads and follows these conventions automatically.

---

## 15-Tool Ecosystem

### File Operations

#### read_file
```python
{
    "name": "read_file",
    "description": "Read contents of a file",
    "parameters": {
        "path": "Path to file (relative or absolute)",
        "encoding": "File encoding (default: utf-8)"
    },
    "returns": "File contents as string",
    "danger_level": "SAFE"
}
```

**Example Usage**:
```python
tool_calls = [
    {
        "name": "read_file",
        "arguments": {"path": "src/auth/user.py"}
    }
]
```

#### write_file
```python
{
    "name": "write_file",
    "description": "Write or overwrite file contents",
    "parameters": {
        "path": "Path to file",
        "content": "New file contents",
        "encoding": "File encoding (default: utf-8)"
    },
    "returns": "Success message",
    "danger_level": "MODERATE"
}
```

#### edit_file
```python
{
    "name": "edit_file",
    "description": "Apply diff-based edits to file",
    "parameters": {
        "path": "Path to file",
        "old_content": "Content to replace",
        "new_content": "Replacement content"
    },
    "returns": "Diff preview + success message",
    "danger_level": "MODERATE"
}
```

### Search Operations

#### glob_search
```python
{
    "name": "glob_search",
    "description": "Find files by pattern",
    "parameters": {
        "pattern": "Glob pattern (e.g., '**/*.py')",
        "base_path": "Base directory (default: current)"
    },
    "returns": "List of matching file paths",
    "danger_level": "SAFE"
}
```

**Example Usage**:
```python
tool_calls = [
    {
        "name": "glob_search",
        "arguments": {"pattern": "tests/**/*_test.py"}
    }
]
```

#### grep_search
```python
{
    "name": "grep_search",
    "description": "Search file contents by regex",
    "parameters": {
        "pattern": "Regex pattern",
        "path": "Path or directory to search",
        "file_pattern": "Filter files (e.g., '*.py')"
    },
    "returns": "Matching lines with file:line:content",
    "danger_level": "SAFE"
}
```

### Execution

#### bash_command
```python
{
    "name": "bash_command",
    "description": "Execute shell command",
    "parameters": {
        "command": "Command to execute",
        "working_dir": "Working directory (default: current)",
        "timeout": "Timeout in seconds (default: 30)"
    },
    "returns": "Command output (stdout + stderr)",
    "danger_level": "DANGEROUS"
}
```

**Security**: Requires approval for DANGEROUS commands.

### Web Access

#### fetch_url
```python
{
    "name": "fetch_url",
    "description": "Fetch content from URL",
    "parameters": {
        "url": "URL to fetch",
        "method": "HTTP method (default: GET)",
        "headers": "Optional headers dict",
        "data": "Optional request body"
    },
    "returns": "Response content + status code",
    "danger_level": "MODERATE"
}
```

#### web_search
```python
{
    "name": "web_search",
    "description": "Search the web",
    "parameters": {
        "query": "Search query",
        "num_results": "Number of results (default: 5)"
    },
    "returns": "List of search results",
    "danger_level": "MODERATE"
}
```

### Workflow Management

#### todo_write
```python
{
    "name": "todo_write",
    "description": "Update task list",
    "parameters": {
        "tasks": "List of task dicts with status",
        "mode": "replace or append"
    },
    "returns": "Updated task list",
    "danger_level": "SAFE"
}
```

#### task_spawn
```python
{
    "name": "task_spawn",
    "description": "Create sub-agent for parallel work",
    "parameters": {
        "task": "Task description",
        "agent_type": "Agent type to spawn",
        "config": "Optional agent config"
    },
    "returns": "Sub-agent result",
    "danger_level": "MODERATE"
}
```

---

## Configuration

### ClaudeCodeConfig

```python
from dataclasses import dataclass
from kaizen.agents.autonomous import AutonomousConfig

@dataclass
class ClaudeCodeConfig(AutonomousConfig):
    """Configuration for ClaudeCodeAgent."""

    # Autonomous config (inherited)
    llm_provider: str = "openai"
    model: str = "gpt-4"
    max_cycles: int = 100  # vs 20 for BaseAutonomousAgent
    planning_enabled: bool = True
    checkpoint_frequency: int = 10

    # Claude Code-specific
    context_threshold: float = 0.92  # 92% compression trigger
    enable_diffs: bool = True  # Show diffs before applying
    enable_reminders: bool = True  # Periodic state reminders
    reminder_frequency: int = 10  # Every N cycles
    claude_md_path: str = "CLAUDE.md"  # Project memory file

    # Advanced
    max_diff_lines: int = 100  # Max lines in diff preview
    context_compression_ratio: float = 0.5  # Target after compression
    preserve_recent_cycles: int = 5  # Keep last N cycles in context
```

### Configuration Examples

#### Minimal Configuration
```python
config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4"
)
# Uses all defaults:
# - max_cycles=100
# - context_threshold=0.92
# - enable_diffs=True
# - enable_reminders=True
```

#### Custom Configuration
```python
config = ClaudeCodeConfig(
    llm_provider="anthropic",
    model="claude-3-opus-20240229",
    max_cycles=150,
    context_threshold=0.88,  # Compress earlier
    reminder_frequency=15,  # Remind less often
    checkpoint_frequency=5  # Checkpoint more often
)
```

#### Lightweight Configuration (Faster)
```python
config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-3.5-turbo",  # Cheaper/faster
    max_cycles=50,  # Shorter sessions
    enable_reminders=False,  # Disable reminders
    checkpoint_frequency=15  # Checkpoint less often
)
```

---

## Usage Examples

### Example 1: Basic Code Refactoring

```python
import asyncio
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig
from kaizen.signatures import Signature, InputField, OutputField
# Tools auto-configured via MCP


# Define signature
class CodingSignature(Signature):
    task: str = InputField(description="Coding task")
    context: str = InputField(description="Code context", default="")
    observation: str = InputField(description="Last observation", default="")

    code_changes: str = OutputField(description="Code modifications")
    next_action: str = OutputField(description="Next action")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# Create configuration
config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=50,
    enable_diffs=True
)

# Setup tools

# 12 builtin tools enabled via MCP

# Create agent
agent = ClaudeCodeAgent(
    config=config,
    signature=CodingSignature(),
    tools="all"  # Enable 12 builtin tools via MCP
)

# Execute refactoring task
async def refactor_auth():
    result = await agent.execute_autonomously(
        "Refactor the UserAuthentication class in src/auth/user.py "
        "to use dependency injection. Add unit tests for the new structure."
    )

    print(f"✅ Refactoring complete in {result['cycles_used']} cycles")
    print(f"Changes made: {result.get('code_changes', 'N/A')}")

    return result

asyncio.run(refactor_auth())
```

### Example 2: Bug Fix with Tests

```python
async def fix_bug():
    """Fix bug and ensure tests pass."""
    config = ClaudeCodeConfig(
        llm_provider="openai",
        model="gpt-4",
        max_cycles=30,
        enable_diffs=True,
        enable_reminders=True
    )

    agent = ClaudeCodeAgent(config, signature, registry)

    result = await agent.execute_autonomously(
        "Fix bug #123: User authentication timeout after 30 minutes. "
        "Issue is in src/auth/session.py. Add test to prevent regression."
    )

    # Check if tests passed
    if "all tests passed" in result.get("observation", "").lower():
        print("✅ Bug fixed and tests passing")
    else:
        print("⚠️ Bug fix complete but tests may need attention")

    return result

asyncio.run(fix_bug())
```

### Example 3: Feature Implementation

```python
async def implement_feature():
    """Implement new feature with full workflow."""
    config = ClaudeCodeConfig(
        llm_provider="anthropic",
        model="claude-3-opus-20240229",
        max_cycles=80,
        enable_diffs=True,
        planning_enabled=True,
        checkpoint_frequency=10
    )

    agent = ClaudeCodeAgent(config, signature, registry)

    result = await agent.execute_autonomously(
        "Implement user profile management feature:\n"
        "1. Add User model with profile fields\n"
        "2. Create ProfileService with CRUD operations\n"
        "3. Add API endpoints for profile management\n"
        "4. Write unit and integration tests\n"
        "5. Update documentation"
    )

    print(f"Feature implementation:")
    print(f"  - Cycles: {result['cycles_used']}/{result['total_cycles']}")
    print(f"  - Plan tasks: {len(result.get('plan', []))}")

    if result.get('plan'):
        print("  - Tasks completed:")
        for task_item in result['plan']:
            status = "✓" if task_item['status'] == 'completed' else "⏳"
            print(f"    {status} {task_item['task']}")

    return result

asyncio.run(implement_feature())
```

### Example 4: Long-Running Session with Context Management

```python
async def long_session():
    """Demonstrate long-running session with context management."""
    config = ClaudeCodeConfig(
        llm_provider="openai",
        model="gpt-4",
        max_cycles=100,
        context_threshold=0.92,
        enable_reminders=True,
        reminder_frequency=10,
        checkpoint_frequency=10
    )

    agent = ClaudeCodeAgent(config, signature, registry)

    # Complex task requiring many cycles
    result = await agent.execute_autonomously(
        "Refactor the entire authentication system:\n"
        "1. Migrate from JWT to OAuth2\n"
        "2. Add support for social login (Google, GitHub)\n"
        "3. Implement refresh token rotation\n"
        "4. Add rate limiting to auth endpoints\n"
        "5. Update all tests\n"
        "6. Update documentation"
    )

    print(f"Long session completed:")
    print(f"  - Cycles: {result['cycles_used']}")
    print(f"  - Context compressions: {result.get('compressions', 0)}")
    print(f"  - Checkpoints saved: {result['cycles_used'] // 10}")
    print(f"  - Duration: ~{result['cycles_used'] * 2} minutes")

    return result

asyncio.run(long_session())
```

---

## Advanced Features

### Custom Tool Addition

Add custom tools to the 15-tool ecosystem:

```python
from kaizen.tools import Tool, ToolParameter

# Create custom tool
custom_tool = Tool(
    name="analyze_complexity",
    description="Analyze code complexity metrics",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            required=True,
            description="Path to Python file"
        ),
        ToolParameter(
            name="metrics",
            type="array",
            required=False,
            description="Metrics to calculate (default: all)"
        )
    ],
    executor=analyze_complexity_function,
    danger_level="SAFE"
)

# Register tool

# 12 builtin tools enabled via MCP
registry.register(custom_tool)

# Create agent with extended tools
agent = ClaudeCodeAgent(config, signature, registry)
# Now has 16 tools (15 + 1 custom)
```

### Custom Diff Formatting

Override diff formatting:

```python
class CustomClaudeCodeAgent(ClaudeCodeAgent):
    """ClaudeCodeAgent with custom diff formatting."""

    def _apply_changes_with_diff(self, changes: List[Dict]) -> str:
        """Custom diff formatting."""
        diff_output = []

        for change in changes:
            file_path = change.get("file", "unknown")
            old_content = change.get("old_content", "")
            new_content = change.get("new_content", "")

            # Custom diff format (e.g., side-by-side)
            diff_output.append(f"File: {file_path}")
            diff_output.append("=" * 80)
            diff_output.append(f"Old ({len(old_content)} chars)")
            diff_output.append(old_content)
            diff_output.append("-" * 80)
            diff_output.append(f"New ({len(new_content)} chars)")
            diff_output.append(new_content)
            diff_output.append("=" * 80)

        return "\n".join(diff_output)
```

### Custom Reminder Content

Override reminder content:

```python
class CustomClaudeCodeAgent(ClaudeCodeAgent):
    """ClaudeCodeAgent with custom reminders."""

    def _inject_system_reminder(self, cycle_num: int) -> str:
        """Custom reminder content."""
        reminder = super()._inject_system_reminder(cycle_num)

        # Add custom sections
        reminder += "\n\nCustom Reminders:"
        reminder += f"\n- Code style: Follow PEP 8"
        reminder += f"\n- Testing: Maintain 80%+ coverage"
        reminder += f"\n- Documentation: Update docstrings"

        # Add metrics
        reminder += f"\n\nMetrics:"
        reminder += f"\n- Files modified: {len(self._modified_files)}"
        reminder += f"\n- Tests added: {self._tests_added}"
        reminder += f"\n- Lines changed: {self._lines_changed}"

        return reminder
```

### Context Compression Strategy

Custom context compression:

```python
class CustomClaudeCodeAgent(ClaudeCodeAgent):
    """ClaudeCodeAgent with custom context compression."""

    def _compress_context(self) -> None:
        """Custom context compression strategy."""
        # Keep important elements
        preserved = {
            "task": self.current_task,
            "plan": self.current_plan,
            "recent_actions": self._action_history[-5:],  # Last 5
            "key_files": self._identify_key_files(),
            "test_results": self._last_test_results,
        }

        # Clear non-essential history
        self._action_history = self._action_history[-5:]
        self._observation_history = self._observation_history[-3:]

        # Update context usage
        self.context_usage = 0.5  # Reduced to 50%

        logger.info(f"Context compressed from 92% to 50%")
        logger.debug(f"Preserved: {list(preserved.keys())}")
```

---

## Best Practices

### 1. Choose Appropriate max_cycles

✅ **DO**: Match cycles to task complexity
```python
# Simple refactoring: 30-50 cycles
config = ClaudeCodeConfig(max_cycles=40)

# Complex feature: 50-80 cycles
config = ClaudeCodeConfig(max_cycles=70)

# Major refactoring: 80-100+ cycles
config = ClaudeCodeConfig(max_cycles=100)
```

❌ **DON'T**: Use excessive cycles for simple tasks
```python
# Wrong: 100 cycles for simple fix
config = ClaudeCodeConfig(max_cycles=100)
result = await agent.execute_autonomously("Fix typo in comment")
```

### 2. Enable Diffs for Safety

✅ **DO**: Always enable diffs for production
```python
config = ClaudeCodeConfig(
    enable_diffs=True  # See changes before applying
)
```

❌ **DON'T**: Disable diffs unless testing
```python
# Risky: Changes applied without preview
config = ClaudeCodeConfig(enable_diffs=False)
```

### 3. Use System Reminders

✅ **DO**: Enable reminders for long sessions
```python
config = ClaudeCodeConfig(
    max_cycles=100,
    enable_reminders=True,
    reminder_frequency=10  # Every 10 cycles
)
```

❌ **DON'T**: Disable reminders for 50+ cycle tasks
```python
# Risky: Model drift in long sessions
config = ClaudeCodeConfig(
    max_cycles=100,
    enable_reminders=False  # No drift prevention
)
```

### 4. Configure Context Management

✅ **DO**: Set appropriate context threshold
```python
# Standard: 92% threshold
config = ClaudeCodeConfig(context_threshold=0.92)

# Conservative: Compress earlier
config = ClaudeCodeConfig(context_threshold=0.85)
```

❌ **DON'T**: Set threshold too high (risk context overflow)
```python
# Risky: May overflow before compression
config = ClaudeCodeConfig(context_threshold=0.98)
```

### 5. Provide CLAUDE.md for Project Context

✅ **DO**: Create CLAUDE.md with project conventions
```markdown
# CLAUDE.md
## Coding Standards
- Use absolute imports
- Follow PEP 8 style
- Add type hints
- Write docstrings for all functions

## Testing
- Use pytest
- Maintain 80%+ coverage
- Add integration tests for APIs

## Project Structure
- /src - Source code
- /tests - Test files
- /docs - Documentation
```

### 6. Monitor Execution Progress

✅ **DO**: Check cycle usage and context
```python
result = await agent.execute_autonomously(task)

print(f"Execution metrics:")
print(f"  - Cycles: {result['cycles_used']}/{result['total_cycles']}")
print(f"  - Efficiency: {(result['cycles_used']/result['total_cycles'])*100:.1f}%")
print(f"  - Checkpoints: {result['cycles_used'] // config.checkpoint_frequency}")

if result.get('compressions'):
    print(f"  - Context compressions: {result['compressions']}")
```

---

## Troubleshooting

### Issue 1: Context Overflow

**Symptom**: Agent fails with context length error

**Solutions**:
```python
# Lower threshold
config = ClaudeCodeConfig(context_threshold=0.85)

# Increase compression ratio
config = ClaudeCodeConfig(context_compression_ratio=0.4)  # Was 0.5

# Disable reminders (reduces context)
config = ClaudeCodeConfig(enable_reminders=False)
```

### Issue 2: Diffs Too Large

**Symptom**: Diff previews are overwhelming

**Solutions**:
```python
# Limit diff lines
config = ClaudeCodeConfig(max_diff_lines=50)  # Was 100

# Show summary instead of full diff
class SummaryClaudeCodeAgent(ClaudeCodeAgent):
    def _apply_changes_with_diff(self, changes):
        summary = [f"Changes in {len(changes)} files:"]
        for change in changes:
            summary.append(f"  - {change['file']}: {change['type']}")
        return "\n".join(summary)
```

### Issue 3: Reminders Too Frequent

**Symptom**: Too many reminders slow execution

**Solutions**:
```python
# Reduce reminder frequency
config = ClaudeCodeConfig(reminder_frequency=20)  # Was 10

# Disable reminders for short tasks
config = ClaudeCodeConfig(
    max_cycles=30,
    enable_reminders=False  # Not needed for short sessions
)
```

### Issue 4: CLAUDE.md Not Loading

**Symptom**: Agent doesn't follow project conventions

**Solutions**:
```python
# Verify CLAUDE.md path
import os
assert os.path.exists("CLAUDE.md"), "CLAUDE.md not found"

# Specify absolute path
config = ClaudeCodeConfig(
    claude_md_path="/absolute/path/to/CLAUDE.md"
)

# Check CLAUDE.md format
with open("CLAUDE.md") as f:
    content = f.read()
    print(f"CLAUDE.md loaded: {len(content)} chars")
```

---

## Performance

### Cycle Duration

Average cycle durations:

| Task Type | Cycles | Duration/Cycle | Total Duration |
|-----------|--------|----------------|----------------|
| Simple refactoring | 20-30 | 30-60s | 10-30 min |
| Bug fix | 15-25 | 45-75s | 11-31 min |
| Feature implementation | 40-60 | 45-90s | 30-90 min |
| Major refactoring | 80-100 | 60-120s | 80-200 min |

### Cost Estimation (GPT-4)

| Task Type | Cycles | Tokens/Cycle | Total Tokens | Cost |
|-----------|--------|--------------|--------------|------|
| Simple | 25 | 5K | 125K | $1.25 |
| Medium | 50 | 6K | 300K | $3.00 |
| Complex | 80 | 7K | 560K | $5.60 |
| Major | 100 | 8K | 800K | $8.00 |

---

## Examples

Working examples available in:
- `examples/autonomy/02_claude_code_agent_demo.py`

---

## References

- **[autonomous-patterns.md](autonomous-patterns.md)** - Overview of autonomous patterns
- **[docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md](../research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md)** - Research documentation
- **`src/kaizen/agents/autonomous/claude_code.py`** - Implementation (691 lines)
- **`tests/unit/agents/autonomous/test_claude_code.py`** - Tests (38 passing)

---

**Last Updated**: 2025-10-22
**Version**: 0.1.0
**Status**: Production Ready

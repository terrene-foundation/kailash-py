# ADR-015: Replace Custom Builtin Tools with Claude Code MCP Tools

**Date**: 2025-10-22
**Status**: Proposed
**Decision Makers**: Kaizen Framework Team
**Impact**: CRITICAL - Complete replacement of custom tool system

---

## Context

### Problem Statement

Our current `src/kaizen/tools/builtin/` contains **12 custom tools** that are:
- NOT MCP-compliant
- NOT compatible with Claude Code ecosystem
- "Toy mickey mouse product" quality (user feedback)

### Claude Code's Tool Set (from Research)

**Source**: `docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md:33`

**15 Built-in Tools**:

1. **Read** - Text, images, PDFs, Jupyter notebooks with line numbers
2. **Edit** - Exact string replacements preserving indentation
3. **Write** - Create/overwrite files
4. **Glob** - Fast pattern matching (faster than bash find)
5. **Grep** - Built on ripgrep with regex, case-insensitive, multiline
6. **Bash** - Persistent shell session with state across commands
7. **Task** - Launch specialized subagents
8. **WebFetch** - HTML to markdown with 15-min caching
9. **WebSearch** - Current information lookup
10. **TodoWrite** - Structured task lists (JSON format)
11. **AskUserQuestion** - Interactive user questions
12. **Skill** - Execute skills from .claude/skills/
13. **SlashCommand** - Execute slash commands
14. **NotebookEdit** - Edit Jupyter notebook cells
15. **BashOutput/KillShell** - Background bash management

### Tool Usage Pattern (from Research)

**Line 41-43**:
> "Tool selection hierarchy explicitly prioritizes built-in tools: use Read not cat, Edit not sed, Glob not find, Grep not bash grep."

> "The canonical workflow follows: TodoWrite for planning → Grep/Glob for discovery → Read files (batched) → Edit/Write code → Bash to test → TodoWrite to mark complete → Bash to commit."

---

## Decision

We will **delete custom builtin tools** and **replace with MCP-based tools matching Claude Code's exact capabilities**.

### Implementation Approach

**Option A: Use Existing MCP Servers** (RECOMMENDED)
- Leverage official MCP servers from MCP ecosystem
- Filesystem server: Read, Write, Edit, Glob
- Brave search server: WebSearch
- Custom Kaizen MCP server: TodoWrite, AskUserQuestion (already in Control Protocol)

**Option B: Build Kaizen MCP Server**
- Create `kailash-kaizen-mcp-server` package
- Implements all 15 Claude Code tools as MCP tools
- Standalone server agents can connect to

---

## Implementation Plan

### Phase 1: Delete Custom Tools (Day 1)

**Files to Delete**:
```bash
src/kaizen/tools/builtin/
├── __init__.py
├── api.py       # http_get, http_post, http_put, http_delete
├── bash.py      # bash_command
├── file.py      # read_file, write_file, delete_file, list_directory, file_exists
└── web.py       # fetch_url, extract_links
```

**Also Delete**:
- `src/kaizen/tools/executor.py` - Custom tool executor
- `src/kaizen/tools/registry.py` - Custom tool registry
- `src/kaizen/tools/types.py` - Custom type definitions

**Rationale**: Complete clean slate for MCP integration

---

### Phase 2: Create Kaizen MCP Server (Week 1)

**Goal**: Standalone MCP server with Claude Code-compatible tools

**Package Structure**:
```
kailash-kaizen-mcp-server/
├── pyproject.toml
├── README.md
├── src/kaizen_mcp/
│   ├── __init__.py
│   ├── server.py          # Main MCP server
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── file_ops.py    # Read, Write, Edit
│   │   ├── search.py      # Grep, Glob
│   │   ├── exec.py        # Bash, BashOutput, KillShell
│   │   ├── todo.py        # TodoWrite (MCP version)
│   │   ├── interaction.py # AskUserQuestion (MCP version)
│   │   └── notebook.py    # NotebookEdit
│   └── resources/
│       └── context.py     # Project context resources
└── tests/
    └── ...
```

**Tool Implementations**:

#### 1. File Operations (file_ops.py)
```python
from kailash.mcp_server import MCPServer

server = MCPServer("kaizen-filesystem")

@server.tool(
    description="Read file contents with line numbers (supports text, images, PDFs, notebooks)"
)
async def read(file_path: str, offset: int = None, limit: int = None) -> dict:
    """
    Claude Code compatible Read tool.

    Returns:
        {
            "content": str,  # cat -n format with line numbers
            "lines": int,
            "truncated": bool
        }
    """
    # Implementation matching Claude Code behavior
    # - Line numbers starting at 1
    # - cat -n format
    # - Support images, PDFs, notebooks
    pass

@server.tool(
    description="Edit file with exact string replacement (preserves indentation)"
)
async def edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> dict:
    """
    Claude Code compatible Edit tool.

    Returns:
        {
            "success": bool,
            "message": str,
            "diff": str  # Unified diff format
        }
    """
    # Implementation matching Claude Code behavior
    # - Exact string match only
    # - Preserves indentation after line numbers
    # - Fails if old_string not unique (unless replace_all)
    pass

@server.tool(description="Write file (create or overwrite)")
async def write(file_path: str, content: str) -> dict:
    """
    Claude Code compatible Write tool.

    Returns:
        {
            "success": bool,
            "message": str,
            "file_path": str
        }
    """
    pass
```

#### 2. Search Tools (search.py)
```python
@server.tool(description="Fast file pattern matching using glob syntax")
async def glob(pattern: str, path: str = None) -> dict:
    """
    Claude Code compatible Glob tool.

    Returns:
        {
            "files": List[str],  # Sorted by modification time
            "count": int
        }
    """
    # Implementation using glob.glob
    # - Supports **/*.js patterns
    # - Faster than bash find
    pass

@server.tool(description="Search code using ripgrep (supports regex, case-insensitive, multiline)")
async def grep(
    pattern: str,
    path: str = None,
    glob: str = None,
    output_mode: str = "files_with_matches",  # content, files_with_matches, count
    case_insensitive: bool = False,
    multiline: bool = False,
    context_before: int = 0,
    context_after: int = 0,
    line_numbers: bool = False
) -> dict:
    """
    Claude Code compatible Grep tool.

    Returns:
        {
            "matches": List[str],
            "count": int
        }
    """
    # Implementation using ripgrep (rg)
    # - Full regex syntax
    # - Multiline mode
    # - Context lines
    pass
```

#### 3. Execution Tools (exec.py)
```python
@server.tool(description="Execute bash commands in persistent shell session")
async def bash(
    command: str,
    description: str = None,
    timeout: int = 120000,  # milliseconds
    run_in_background: bool = False
) -> dict:
    """
    Claude Code compatible Bash tool.

    Returns:
        {
            "stdout": str,
            "stderr": str,
            "exit_code": int,
            "bash_id": str  # If run_in_background
        }
    """
    # Implementation with persistent shell
    # - Maintains state across commands
    # - Supports background processes
    # - Timeout handling
    pass

@server.tool(description="Get output from background bash shell")
async def bash_output(bash_id: str, filter: str = None) -> dict:
    """Returns new output from background shell."""
    pass

@server.tool(description="Kill background bash shell")
async def kill_shell(shell_id: str) -> dict:
    """Terminates background shell."""
    pass
```

#### 4. Todo Tool (todo.py)
```python
@server.tool(description="Create structured task list (JSON format)")
async def todo_write(
    todos: List[dict]  # [{"content": str, "status": str, "activeForm": str}]
) -> dict:
    """
    Claude Code compatible TodoWrite tool.

    Status: pending, in_progress, completed

    Returns:
        {
            "success": bool,
            "todos": List[dict]
        }
    """
    # Implementation matching Claude Code behavior
    # - Exactly ONE task in_progress at a time
    # - Only mark completed when FULLY accomplished
    pass
```

#### 5. Interaction Tool (interaction.py)
```python
@server.tool(description="Ask user questions during execution")
async def ask_user_question(
    questions: List[dict]  # [{"question": str, "header": str, "options": List[dict], "multiSelect": bool}]
) -> dict:
    """
    Claude Code compatible AskUserQuestion tool.

    Returns:
        {
            "answers": dict  # {question_id: answer}
        }
    """
    # Implementation using Control Protocol
    # - Interactive UI for questions
    # - Multi-select support
    pass
```

#### 6. Notebook Tool (notebook.py)
```python
@server.tool(description="Edit Jupyter notebook cells")
async def notebook_edit(
    notebook_path: str,
    cell_id: str = None,
    cell_type: str = None,  # code, markdown
    new_source: str = None,
    edit_mode: str = "replace"  # replace, insert, delete
) -> dict:
    """
    Claude Code compatible NotebookEdit tool.

    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    pass
```

---

### Phase 3: BaseAgent MCP Integration (Week 2)

**Goal**: Connect BaseAgent to Kaizen MCP Server

**Configuration**:
```python
from kaizen.core.base_agent import BaseAgent

# Configure Kaizen MCP server
mcp_servers = [
    {
        "name": "kaizen",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "kaizen_mcp.server"]
    }
]

agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=mcp_servers
)

# Discover Claude Code-compatible tools
tools = await agent.discover_tools()
# Returns: [
#   {"name": "mcp__kaizen__read", ...},
#   {"name": "mcp__kaizen__edit", ...},
#   {"name": "mcp__kaizen__write", ...},
#   {"name": "mcp__kaizen__grep", ...},
#   {"name": "mcp__kaizen__glob", ...},
#   {"name": "mcp__kaizen__bash", ...},
#   {"name": "mcp__kaizen__todo_write", ...},
#   {"name": "mcp__kaizen__ask_user_question", ...},
#   {"name": "mcp__kaizen__notebook_edit", ...},
#   {"name": "mcp__kaizen__bash_output", ...},
#   {"name": "mcp__kaizen__kill_shell", ...}
# ]

# Execute tool
result = await agent.execute_tool("mcp__kaizen__read", {"file_path": "src/main.py"})
```

**Tool Naming Convention**:
- Claude Code uses: `Read`, `Edit`, `Write`, `Grep`, `Glob`, `Bash`
- MCP naming: `mcp__kaizen__read`, `mcp__kaizen__edit`, etc.
- Internal mapping: `mcp__kaizen__read` → `read` tool on kaizen server

---

### Phase 4: Migration (Week 3)

**Update All Examples**:
```bash
examples/workflows/05_autonomous_research_agent.py
examples/autonomy/tools/*.py
tests/unit/tools/
tests/integration/autonomy/tools/
```

**Before (Custom Tools)**:
```python
# Tools auto-configured via MCP



# 12 builtin tools enabled via MCP

agent = ReActAgent(tools="all"  # Enable 12 builtin tools via MCP

# Execute custom tool
result = await agent.execute_tool("read_file", {"path": "data.txt"})
```

**After (MCP Tools)**:
```python
from kaizen.core.base_agent import BaseAgent

mcp_servers = [{"name": "kaizen", "transport": "stdio", ...}]

agent = BaseAgent(mcp_servers=mcp_servers)

# Execute MCP tool (Claude Code compatible!)
result = await agent.execute_tool("mcp__kaizen__read", {"file_path": "data.txt"})
```

---

## Comparison: Custom vs. MCP Tools

| Tool Category | Custom (DELETED) | MCP (NEW) |
|---------------|------------------|-----------|
| **File Read** | `read_file(path)` | `mcp__kaizen__read(file_path, offset, limit)` |
| **File Write** | `write_file(path, content)` | `mcp__kaizen__write(file_path, content)` |
| **File Edit** | ❌ (not implemented) | `mcp__kaizen__edit(file_path, old_string, new_string)` ✅ |
| **File Delete** | `delete_file(path)` | ❌ (not in Claude Code) |
| **List Dir** | `list_directory(path)` | `mcp__kaizen__glob(pattern="**/*")` (better) |
| **File Exists** | `file_exists(path)` | `mcp__kaizen__read(file_path)` + error handling |
| **Search** | ❌ (not implemented) | `mcp__kaizen__grep(pattern)` ✅ |
| **Find Files** | ❌ (not implemented) | `mcp__kaizen__glob(pattern)` ✅ |
| **HTTP** | `http_get/post/put/delete` | Use MCP http server (separate) |
| **Bash** | `bash_command(command)` | `mcp__kaizen__bash(command, timeout, run_in_background)` (better) |
| **Web** | `fetch_url`, `extract_links` | Use MCP brave-search server (separate) |
| **Todo** | ❌ (not implemented) | `mcp__kaizen__todo_write(todos)` ✅ |
| **Questions** | ❌ (not implemented) | `mcp__kaizen__ask_user_question(questions)` ✅ |
| **Notebooks** | ❌ (not implemented) | `mcp__kaizen__notebook_edit(...)` ✅ |

**Gained**: Edit, Grep, Glob, TodoWrite (MCP), AskUserQuestion (MCP), NotebookEdit
**Lost**: delete_file (intentional - Claude Code doesn't have it), HTTP tools (use separate MCP server)

---

## MCP Server Ecosystem Integration

### Core Filesystem Server (Kaizen MCP Server)
```json
{
  "mcpServers": {
    "kaizen": {
      "command": "python",
      "args": ["-m", "kaizen_mcp.server"],
      "transport": "stdio"
    }
  }
}
```

### Additional MCP Servers (Optional)
```json
{
  "mcpServers": {
    "kaizen": {
      "command": "python",
      "args": ["-m", "kaizen_mcp.server"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "..."
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "..."
      }
    }
  }
}
```

---

## Testing Strategy

### Unit Tests (Tier 1)
```bash
tests/unit/mcp/
├── test_read_tool.py         # 20 tests
├── test_edit_tool.py         # 25 tests
├── test_write_tool.py        # 15 tests
├── test_grep_tool.py         # 20 tests
├── test_glob_tool.py         # 15 tests
├── test_bash_tool.py         # 25 tests
├── test_todo_tool.py         # 15 tests
├── test_ask_user_tool.py     # 15 tests
└── test_notebook_tool.py     # 15 tests
```

### Integration Tests (Tier 2)
```bash
tests/integration/mcp/
├── test_baseagent_mcp_tools.py       # 30 tests (real MCP server)
├── test_autonomous_with_mcp.py       # 20 tests (autonomous workflow)
└── test_claude_code_parity.py        # 25 tests (exact Claude Code behavior)
```

---

## Success Criteria

1. **100% Claude Code Parity**: All 11 core tools match Claude Code behavior exactly
2. **Zero Custom Tools**: Complete deletion of `src/kaizen/tools/builtin/`
3. **MCP Standard**: All tools accessible via standard MCP protocol
4. **Backward Compatibility**: Existing examples work with MCP tools (after migration)
5. **Performance**: <100ms tool invocation latency
6. **Documentation**: Complete migration guide with examples

---

## Rationale

### Why Delete Custom Tools?

1. **Not MCP-compliant**: Incompatible with Claude Code ecosystem
2. **Incomplete**: Missing Grep, Glob, Edit, TodoWrite (MCP)
3. **Poor quality**: User feedback: "toy mickey mouse product"
4. **Maintenance burden**: Duplicate effort vs. using standard

### Why Build Kaizen MCP Server?

1. **Claude Code Parity**: Exact tool names and behaviors
2. **Standalone Package**: Can be used by any MCP client
3. **Control Protocol Integration**: TodoWrite, AskUserQuestion use existing Control Protocol
4. **Ecosystem Contribution**: Sharable with broader MCP community

---

## Migration Timeline

### Week 1: Kaizen MCP Server
- Day 1-2: Delete custom tools, create MCP server package
- Day 3-4: Implement Read, Write, Edit, Grep, Glob
- Day 5: Implement Bash, TodoWrite, AskUserQuestion
- Day 6: Implement NotebookEdit, BashOutput, KillShell
- Day 7: Unit tests (165 tests)

### Week 2: BaseAgent Integration
- Day 1-2: Add MCP client to BaseAgent
- Day 3-4: Implement discover_mcp_tools, execute_mcp_tool
- Day 5: Integration tests (75 tests)
- Day 6-7: Claude Code parity validation

### Week 3: Migration & Documentation
- Day 1-3: Update all examples to use MCP tools
- Day 4-5: Update tests
- Day 6: Write comprehensive migration guide
- Day 7: Release kaizen-mcp-server v1.0.0

---

## Decision Outcome

**PROPOSED** - Awaiting user confirmation on:
1. ✅ Delete all custom builtin tools?
2. ✅ Build Kaizen MCP Server with Claude Code-compatible tools?
3. ❓ Package name: `kailash-kaizen-mcp-server` or `kaizen-mcp`?
4. ❓ Start implementation immediately?

**Next Step**: User approval to proceed with deletion and MCP server creation.

---

**Last Updated**: 2025-10-22
**Supersedes**: None (first tool replacement ADR)
**Superseded By**: None (active)

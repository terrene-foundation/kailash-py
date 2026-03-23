# kz v0.1 Implementation Plan

**Date**: 2026-03-21
**Scope**: Core agent loop with model-agnostic execution and streaming
**Autonomous estimate**: 2-3 sessions (applying 10x multiplier to the ~2,500 new lines needed)

---

## Deliverable

`pip install kailash-kaizen[cli]` installs a `kz` command that can:

1. Start an interactive agent session
2. Execute multi-turn agent loops with tool calling
3. Stream responses in real-time
4. Work with any Tier 1/2 model (Claude, OpenAI, Gemini)
5. Enforce budget controls (max_turns, max_budget_usd)
6. Load KAIZEN.md project instructions

---

## Architecture (v0.1)

```
                    ┌──────────────┐
                    │  kz CLI      │  typer entry point
                    │  ~200 lines  │  arg parsing, REPL
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  Session     │  JSONL persistence
                    │  Manager     │  resume, fork
                    │  ~200 lines  │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  Turn        │  Single turn execution
                    │  Runner      │  Hook dispatch, tool routing
                    │  ~500 lines  │  Modeled on Codex run_turn()
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────┴──────┐ ┌──┴──────┐ ┌──┴──────────┐
     │ Model Adapter │ │ Tool    │ │ Streaming   │
     │ (EXISTING)    │ │ System  │ │ (EXISTING)  │
     │ Claude/OAI/   │ │(EXISTING│ │ 10 events   │
     │ Gemini        │ │ 12 tools│ │             │
     └───────────────┘ └─────────┘ └─────────────┘
```

## Implementation Tasks

### Task 1: CLI Entry Point

**New file**: `packages/kailash-kaizen/src/kaizen/cli/__init__.py`
**New file**: `packages/kailash-kaizen/src/kaizen/cli/main.py`

```python
# Entry point pattern (typer-based)
import typer

app = typer.Typer()

@app.command()
def run(
    prompt: str = typer.Argument(None, help="Initial prompt (omit for interactive mode)"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model"),
    max_turns: int = typer.Option(100, "--max-turns", help="Maximum agent turns"),
    max_budget: float = typer.Option(None, "--max-budget", help="Max budget in USD"),
    resume: str = typer.Option(None, "--resume", "-r", help="Resume session ID"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Start a kz autonomous agent session."""
    ...

@app.command()
def sessions():
    """List saved sessions."""
    ...
```

**pyproject.toml update**:

```toml
[project.scripts]
kz = "kaizen.cli.main:app"

[project.optional-dependencies]
cli = ["typer>=0.9.0", "rich>=13.0.0"]
```

### Task 2: Configuration & KAIZEN.md Loading

**New file**: `packages/kailash-kaizen/src/kaizen/cli/config.py`

- Walk UP from CWD to find project root (`.git`, `KAIZEN.md`, `.kaizen/`)
- Load KAIZEN.md content (hierarchical: `~/.kaizen/KAIZEN.md` → project `KAIZEN.md`)
- Load `.kaizen/settings.toml` for permissions, model defaults, tool config
- Load `.env` for API keys (existing Kaizen pattern)
- Merge into `AgentConfig` (existing Kaizen dataclass)

**Pattern**: Codex's `project_doc.rs` — walk up to `.git`, collect AGENTS.md files downward.

### Task 3: Turn Runner (Core Agent Loop)

**New file**: `packages/kailash-kaizen/src/kaizen/cli/turn_runner.py`

The heart of kz. Modeled on Codex's `run_turn()`:

```python
class TurnRunner:
    """Execute a single agent turn with tool calling."""

    async def run_turn(self, user_input: str, context: TurnContext) -> TurnResult:
        """
        1. Assemble prompt (system + KAIZEN.md + tools + history + user_input)
        2. Call LLM via model adapter (streaming)
        3. Process stream events:
           - Text chunks → emit to terminal
           - Tool calls → dispatch to tool system
           - Tool results → feed back into conversation
        4. Check termination (no tool calls → done)
        5. Check budget (tokens, cost)
        6. Return turn result
        """
```

**Wiring to existing Kaizen**:

- Uses `LocalKaizenAdapter` for the LLM call
- Uses `StreamingExecutor` for event emission
- Uses `CostTracker` for budget enforcement
- Uses existing 12 native tools via `BaseTool` interface

### Task 4: Streaming Terminal UI

**New file**: `packages/kailash-kaizen/src/kaizen/cli/ui.py`

```python
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

class TerminalUI:
    """Real-time streaming output for kz."""

    async def stream_response(self, events: AsyncIterator[ExecutionEvent]):
        """Render streaming events to terminal."""
        # Text events → render as markdown
        # ToolUse events → show tool name + spinner
        # ToolResult events → show result summary
        # CostUpdate events → update status bar
        # Error events → show error with context
```

**Pattern**: Claude Code's line-by-line streaming + Gemini's React/Ink (simplified to `rich`).

### Task 5: Session Persistence

**New file**: `packages/kailash-kaizen/src/kaizen/cli/session.py`

```python
class SessionManager:
    """JSONL-based session persistence."""

    def save_turn(self, turn: TurnResult):
        """Append turn to session JSONL file."""

    def load_session(self, session_id: str) -> List[TurnResult]:
        """Load session history from JSONL."""

    def list_sessions(self) -> List[SessionInfo]:
        """List all saved sessions."""
```

**Storage**: `~/.kaizen/sessions/{session_id}/transcript.jsonl`

**Pattern**: Claude Code's JSONL format — one JSON object per line, preserves tool interactions.

### Task 6: Model Adapter Integration

**Existing**: `kaizen/runtime/adapters/tool_mapping/` already has Claude, OpenAI, Gemini mappers.

**New**: Wire the model selection to CLI flags:

```python
# Model tier resolution
def resolve_model(model_flag: str | None, config: AgentConfig) -> str:
    """
    Priority: --model flag → KAIZEN.md default → .env → tier 2 default
    Tier 1: claude-opus-4-6, minimax-m1
    Tier 2: claude-sonnet-4-6, gpt-5-codex, gemini-2.5-pro
    Tier 3: claude-haiku-4-5, gpt-5.2-nano
    """
```

### Task 7: Budget Controls

**Existing**: `kaizen/cost/tracker.py` has full budget tracking.

**New**: Wire to CLI:

```python
# Budget enforcement in turn runner
async def check_budget(self, tracker: CostTracker, config: AgentConfig):
    if config.max_budget_usd and tracker.total_cost_usd >= config.max_budget_usd:
        raise BudgetExceededError(f"Budget limit ${config.max_budget_usd} reached")
    if self.turn_count >= config.max_turns:
        raise MaxTurnsExceededError(f"Turn limit {config.max_turns} reached")
```

---

## Dependencies (New)

| Package        | Purpose                                         | Size   |
| -------------- | ----------------------------------------------- | ------ |
| `typer>=0.9.0` | CLI framework (built on Click)                  | ~50KB  |
| `rich>=13.0.0` | Terminal rendering (markdown, tables, progress) | ~500KB |

Both are standard Python CLI dependencies with no native compilation required.

---

## Testing Strategy

| Test Tier                | What                                                                  | How                      |
| ------------------------ | --------------------------------------------------------------------- | ------------------------ |
| **Tier 1 (Unit)**        | Config loading, KAIZEN.md parsing, session JSONL, model resolution    | Mock LLM calls           |
| **Tier 2 (Integration)** | Turn runner with real tool execution (file read/write, bash)          | Real tools, mock LLM     |
| **Tier 3 (E2E)**         | Full session: start → tool calls → budget check → session save/resume | Real LLM (ollama or API) |

---

## File Layout (New Files)

```
packages/kailash-kaizen/
├── src/kaizen/cli/
│   ├── __init__.py          # Package init
│   ├── main.py              # typer entry point (Task 1)
│   ├── config.py            # KAIZEN.md + settings loading (Task 2)
│   ├── turn_runner.py       # Core agent loop (Task 3)
│   ├── ui.py                # Terminal streaming UI (Task 4)
│   ├── session.py           # JSONL persistence (Task 5)
│   └── models.py            # Model tier resolution (Task 6)
├── pyproject.toml           # Add [cli] extra + kz script entry
└── tests/
    └── cli/
        ├── test_config.py
        ├── test_turn_runner.py
        ├── test_session.py
        └── test_models.py
```

---

## Success Criteria (v0.1)

- [ ] `pip install kailash-kaizen[cli]` installs `kz` command
- [ ] `kz "hello world"` executes a single-turn interaction
- [ ] `kz` (no args) starts interactive REPL mode
- [ ] `kz --model claude-sonnet-4-6 "write a file"` uses specified model with tool calling
- [ ] Streaming output renders in real-time (line-by-line)
- [ ] `kz --max-turns 5` enforces turn limit
- [ ] `kz --max-budget 0.50` enforces cost limit
- [ ] `kz sessions` lists saved sessions
- [ ] `kz --resume <id>` resumes a session
- [ ] KAIZEN.md loaded and injected into system prompt
- [ ] All tests pass (Tier 1 + Tier 2)

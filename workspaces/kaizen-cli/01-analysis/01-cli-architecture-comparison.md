# CLI Architecture Comparison: Architecture / Model / Binary Boundaries

**Date**: 2026-03-21
**Sources**: Direct source code analysis of Claude Code, Codex, and Gemini CLI repos

---

## The Three Boundaries

Every agent CLI has three distinct layers:

1. **Architecture/Control** — The agent loop, tool system, hooks, context management, permissions. This is the orchestration logic.
2. **Model Capability** — What the LLM API provides: inference, function calling decisions, reasoning, token counting. This is behind the API wall.
3. **Binary/Opaque** — Compiled components where source is not inspectable or modifiable. This varies dramatically across the three CLIs.

---

## Comparative Matrix

### Language & Distribution

| Dimension             | Claude Code                                               | Codex                                                                         | Gemini CLI                                   |
| --------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------- |
| **Primary language**  | TypeScript (compiled to binary)                           | Rust (core) + JS (shim)                                                       | TypeScript                                   |
| **Distribution**      | Pre-compiled Node.js binary via Homebrew/npm              | Platform-specific Rust binaries via npm (`@openai/codex-*`)                   | npm package + Node.js SEA                    |
| **Source visibility** | Plugins only (hooks, commands, skills). Core is compiled. | Full Rust source visible in repo. Binaries are pre-compiled for distribution. | 100% source visible. No compiled components. |
| **Build system**      | Not available (binary distribution)                       | Bazel + pnpm                                                                  | esbuild + pnpm                               |
| **LOC (visible)**     | ~5 TS files (CI scripts only) + Markdown plugins          | ~1,418 Rust files, 1M+ LOC (full core)                                        | ~1,718 TS/TSX files (full codebase)          |

### Agent Loop

| Dimension                   | Claude Code                                                              | Codex                                                                                                          | Gemini CLI                                                                                                    |
| --------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Loop location**           | Binary (inferred from hooks)                                             | `codex.rs` (7,334 lines) — fully visible                                                                       | `client.ts` (39K) + `geminiChat.ts` (35K)                                                                     |
| **Loop pattern**            | Stream → identify tool calls → execute → feed back → loop until no tools | `run_turn()` → `run_sampling_request()` → stream events → `handle_output_item_done()` → drain in-flight → loop | `processTurn()` → `sendMessageStream()` → `processToolCall()` → `Scheduler.schedule()` → loop (max 100 turns) |
| **Parallel tool execution** | Yes (FuturesOrdered from changelog)                                      | Yes (`in_flight: FuturesOrdered` in Rust)                                                                      | Yes (`Scheduler.schedule()` batches)                                                                          |
| **Termination**             | No tool calls in response                                                | `needs_follow_up` is false                                                                                     | No pending tool calls after turn                                                                              |
| **Mid-turn compaction**     | Yes (PostCompact hook exists)                                            | Yes (`auto_compact` mid-turn if tokens exhausted)                                                              | Yes (threshold at 50% of model limit)                                                                         |

### Tool System

| Dimension            | Claude Code                                               | Codex                                                            | Gemini CLI                                                 |
| -------------------- | --------------------------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------- |
| **Built-in tools**   | 40+ (Bash, Read, Write, Edit, Glob, Grep, WebFetch, etc.) | Shell, apply-patch, code-mode + MCP                              | edit, execute, ask-user, glob, grep, fetch-web, search     |
| **Tool definition**  | Binary-internal + MCP schemas                             | `ToolRouter` with `ToolSpec` (Rust structs)                      | `tool-registry.ts` with `getFunctionDeclarations()`        |
| **MCP support**      | stdio, HTTP, SSE transports                               | `rmcp-client` crate + `shell-tool-mcp`                           | Full MCP client in `mcp/` package                          |
| **Permission model** | Settings JSON + PreToolUse hooks (exit code 2 = block)    | `ExecPolicyManager` + `ApprovalStore` + `NetworkApprovalService` | `ApprovalModes` (AUTOMATIC/ASK_USER/BLOCK) + TOML policies |
| **Denial handling**  | Tool result message ("Permission denied")                 | Approval event → UI → approval store                             | Confirmation bus → synthetic response                      |

### Hook/Lifecycle System

| Dimension          | Claude Code                                                                                                                | Codex                                                                            | Gemini CLI                                                                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hook events**    | 9: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, StopFailure, PostCompact, Elicitation, ElicitationResult | Hooks present but less documented; session_start, user_prompt_submit, stop hooks | 11: BeforeAgent, AfterAgent, BeforeModel, AfterModel, BeforeTool, AfterTool, BeforeToolSelection, SessionStart, SessionEnd, PreCompress, Notification |
| **Hook execution** | Shell/Python scripts, JSON stdin/stdout                                                                                    | Rust-native hooks + shell commands                                               | Shell commands (TOML config) + TypeScript runtime hooks                                                                                               |
| **Blocking**       | PreToolUse (exit 2), Stop (decision: block)                                                                                | Policy-based blocking                                                            | BeforeTool (can block), BeforeAgent (can stop)                                                                                                        |
| **Fail behavior**  | Fail-open (hook errors never crash session)                                                                                | Configurable                                                                     | Configurable                                                                                                                                          |

### Context Management

| Dimension                | Claude Code                                                         | Codex                                                                     | Gemini CLI                                                                          |
| ------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Project instructions** | `CLAUDE.md` (project root)                                          | `AGENTS.md` / `AGENTS.override.md` (hierarchical: home → project → CWD)   | `GEMINI.md` (project root) + `.gemini/` hierarchy                                   |
| **Context hierarchy**    | Core prompt → CLAUDE.md → rules → skills → hooks → memory → history | `config.user_instructions` → AGENTS.md → JS REPL                          | Runtime → Project → User → System → Extensions                                      |
| **Compaction strategy**  | Extract key facts, replace old turns (binary logic)                 | LLM-generated summary replaces old items; 20K token max for user messages | Preserve last 30% of history, truncate older tool responses to 30 lines + temp file |
| **Session persistence**  | JSONL transcript files                                              | In-memory Vec + disk persistence per thread                               | Chat recording service                                                              |
| **Resume**               | `--resume` flag, worktree support                                   | Thread-based resume                                                       | Session ID resume                                                                   |

### Sandbox & Security

| Dimension   | Claude Code               | Codex                               | Gemini CLI                         |
| ----------- | ------------------------- | ----------------------------------- | ---------------------------------- |
| **macOS**   | Seatbelt (`sandbox-exec`) | Shell restriction policies          | Seatbelt via `MacOsSandboxManager` |
| **Linux**   | Seccomp-like              | Docker-based                        | bubblewrap                         |
| **Windows** | WSL required              | `WindowsSandbox` elevation levels   | Windows Sandbox integration        |
| **Network** | Settings-based deny lists | `NetworkApprovalService` intercepts | Domain-based allow/deny            |

### Model Coupling

| Dimension                       | Claude Code                                            | Codex                                                      | Gemini CLI                                                         |
| ------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------ |
| **API**                         | Claude Messages API (streaming SSE)                    | OpenAI Responses API (WebSocket + HTTPS fallback)          | Gemini API via `@google/genai` SDK                                 |
| **Model lock-in**               | Tight — Claude-specific system prompt, tool format     | Tight — Responses API event model specific                 | Moderate — `BaseLlmClient` abstraction exists but only Gemini impl |
| **Multi-provider**              | Via Vertex AI, Bedrock proxies (same Claude model)     | Via OpenRouter (same API contract)                         | Router strategies (same Gemini backend)                            |
| **Could support other models?** | Theoretically via wrapper, but deep Claude assumptions | Requires alternative `ResponseEvent` stream implementation | Architecture supports it; `BaseLlmClient` is the interface         |

---

## Binary Boundary Analysis

### Claude Code: Maximum Opacity

```
Binary (NOT visible)                     Extensible (visible)
────────────────────                     ────────────────────
Core agent loop                          Hooks (Python/shell scripts)
Streaming engine                         Commands (Markdown + frontmatter)
Permission UI                            Agents (Markdown + YAML)
Terminal rendering                       Skills (Markdown knowledge)
Authentication (OAuth/keychain)          MCP servers (external processes)
Session persistence (JSONL)              Settings (JSON config)
Tool implementations (40+)              CLAUDE.md (project instructions)
Plugin loader                            Memory files (.claude/memory/)
Sandbox enforcement
Token counting
Context compaction
```

**Implication for kz**: We cannot learn HOW the agent loop works from Claude Code. We can only learn WHAT extension points it exposes. The hook system design is the valuable artifact — not the core engine.

### Codex: Maximum Source Visibility (Rust)

```
Visible Source (Rust)                    Distribution (compiled)
─────────────────────                    ──────────────────────
codex.rs (7.3K lines) — full loop       @openai/codex-{platform} npm packages
client.rs (1.8K) — API calls            Pre-compiled Rust binaries
compact.rs (442) — compaction logic
tools/spec.rs (3.1K) — tool system
project_doc.rs — AGENTS.md loading
config/ — settings and policies
sandbox/ — approval + execution
context_manager/ — history
```

**Implication for kz**: Codex's architecture is the most instructive. We can see exactly how `run_turn()` works, how `try_run_sampling_request()` handles streaming, how compaction is implemented. The Rust source is the best reference for building our own agent loop. Key pattern: `FuturesOrdered` for parallel tool execution, turn-scoped context, mid-turn compaction.

### Gemini CLI: Full Transparency

```
All Source (TypeScript)                  Binary Components
───────────────────────                  ──────────────────
packages/core/ — full agent engine       NONE
packages/cli/ — terminal UI (React/Ink)  (Node.js SEA for distribution only)
packages/sdk/ — programmatic API
packages/devtools/ — inspector
Hooks, tools, sandbox, routing — all TS
```

**Implication for kz**: Gemini CLI proves that a full-featured agent CLI can be 100% source-transparent with zero compiled components. The hook system (11 events) is the most comprehensive. The React/Ink UI pattern is interesting but may be over-engineered for v0.1.

---

## Key Patterns to Adopt for `kz`

### From Claude Code

- **Hook event model**: PreToolUse/PostToolUse/UserPromptSubmit/SessionStart are the essential lifecycle points
- **Plugin architecture**: Commands, agents, skills as Markdown with YAML frontmatter
- **Fail-open hooks**: Hook errors never crash the session
- **CLAUDE.md → KAIZEN.md**: Project instructions that persist across compaction

### From Codex

- **Turn-scoped execution**: `TurnContext` pattern — each turn has its own model, permissions, sandbox policy
- **Parallel tool execution**: `FuturesOrdered` pattern for concurrent tool calls
- **Mid-turn compaction**: When tokens exhaust mid-response, compact and continue (don't fail)
- **Stateless API contract**: Each request carries full context reconstruction logic
- **Rust core + JS shim**: Validates the pattern of having a compiled core with a thin wrapper

### From Gemini CLI

- **Full transparency**: Proves we don't NEED compiled binaries for v0.1-v0.3
- **11-event hook system**: Most comprehensive lifecycle coverage
- **Router strategies**: Pluggable model selection is the right architecture for multi-model
- **Mid-stream retry**: Up to 4 attempts with exponential backoff
- **Scheduler for tool execution**: Batched tool calls with confirmation bus
- **Skills as discoverable units**: User/workspace/builtin skill hierarchy

---

## What the Binary Hides (and Whether We Need It)

| Capability          | In Binary?                                         | Do We Need It?   | Our Approach                                     |
| ------------------- | -------------------------------------------------- | ---------------- | ------------------------------------------------ |
| Agent loop          | Claude Code: yes. Codex: visible. Gemini: visible. | Yes — core of kz | Python (using Codex + Gemini as reference)       |
| Streaming parser    | All three: in core                                 | Yes              | Python asyncio (Kaizen StreamingExecutor exists) |
| Token counting      | All three: in core                                 | Yes              | `tiktoken` (Python) or Rust binding for speed    |
| Context compaction  | All three: in core                                 | Yes              | LLM-generated summary (Python, like Codex)       |
| Terminal UI         | Claude Code: binary. Gemini: React/Ink.            | Yes              | `rich` (Python) — simpler than React/Ink         |
| Sandbox enforcement | All three: OS-level                                | Phase 3          | Python subprocess + Seatbelt/bubblewrap          |
| Authentication      | All three: in core                                 | Yes              | Python (standard OAuth2/API key)                 |
| Permission system   | All three: in core                                 | Yes              | Python (policy engine + hook interception)       |

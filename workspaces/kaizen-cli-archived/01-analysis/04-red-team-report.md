# kz CLI Architecture: Red Team Report

**Date**: 2026-03-21
**Analyst**: deep-analyst (adversarial mode)
**Scope**: Full architecture plan review -- strategy brief, architecture comparison, binary boundary decision, Kaizen reuse map, v0.1 implementation plan
**Verdict**: 7 CRITICAL, 11 HIGH, 9 MEDIUM, 5 LOW findings

---

## Executive Summary

The kz CLI plan is strategically sound in its vision (PACT-constrained model-agnostic agent CLI) but architecturally underspecified in ways that will cause painful rework. The plan claims 70% infrastructure reuse but my inspection of the actual codebase reveals the existing components were designed for a different execution model (batch agent execution, not interactive turn-by-turn CLI streaming). The gap between "exists in Kaizen" and "works for a CLI turn runner" is larger than the plan acknowledges. The most dangerous risk is shipping v0.1-v0.2 without any sandboxing, giving an LLM unrestricted filesystem and shell access through 12 native tools that include bash execution.

**Complexity Score**: 27 (Complex) -- Governance: 7, Technical: 12, Strategic: 8

---

## 1. ARCHITECTURAL VULNERABILITIES

### FINDING A-1: StreamingExecutor Is Batch-Oriented, Not Turn-Interactive [CRITICAL]

**Evidence**: Reading `/packages/kailash-kaizen/src/kaizen/execution/streaming_executor.py`, the `StreamingExecutor` calls `agent.run()` or `agent.run_async()` as a single blocking operation (lines 211-224), then emits tool events AFTER execution completes (lines 395-468). It does NOT stream token-by-token from the LLM. It streams execution lifecycle events.

The plan (reuse map, line "StreamingExecutor (EXISTING) -- 10 events") implies this component handles real-time LLM streaming. It does not. The executor collects events post-hoc from the agent result dictionary. For a CLI that must render text as tokens arrive from the LLM (like Claude Code does), a fundamentally different streaming architecture is needed.

**Impact**: The ~500 lines estimated for "new streaming" is a severe undercount. The entire model-to-terminal streaming pipeline must be built, not wired.

**Mitigation**: Acknowledge that StreamingExecutor is for server-side event emission, not CLI streaming. Budget 800-1,200 lines for a new `TurnStreamRunner` that consumes provider-specific SSE/streaming responses and emits incremental text deltas.

### FINDING A-2: No Anthropic/Claude Tool Mapper Exists [CRITICAL]

**Evidence**: The tool_mapping directory contains `OpenAIToolMapper`, `GeminiToolMapper`, and `MCPToolMapper`. There is NO `AnthropicToolMapper` or `ClaudeToolMapper`. The `extract_tool_call()` function in `base.py` (lines 304-363) has an `"anthropic"` branch that handles Claude's `tool_use` content blocks, and `format_tool_result()` has an `"anthropic"` branch. But these are standalone utility functions, not a full mapper class.

The plan says "Model adapter layer: Already exists in `kaizen/runtime/adapters/tool_mapping/`" and lists Claude as the first Tier 1 model. But Claude's Messages API uses a different tool definition format (`input_schema` instead of `parameters`, content blocks instead of function calls, `tool_use`/`tool_result` instead of `function`/`tool`). The existing `KaizenTool` dataclass canonicalizes to OpenAI format internally (line 52: "Kaizen tool definition (OpenAI function calling format)").

**Impact**: Claude -- the primary development and testing model -- has no proper tool mapper. The first model you will test with is the one with the least infrastructure.

**Mitigation**: Build `AnthropicToolMapper` before v0.1. This is not Phase 2 work; it blocks the core agent loop.

### FINDING A-3: LocalKaizenAdapter's Streaming Is Queue-Based Simulation [HIGH]

**Evidence**: `kaizen_local.py` lines 1182-1254 show the `stream()` method creates an `asyncio.Queue`, runs execution in a background task, and yields chunks from the queue. The chunks are human-readable status strings like `"[Thinking: cycle 2]\n"` and `"[Tool: bash]\n"` -- NOT actual LLM text deltas.

The plan says "Uses `LocalKaizenAdapter` for the LLM call" and "Uses `StreamingExecutor` for event emission." Neither of these components provides real token streaming. The plan's Task 4 (Terminal UI) assumes `AsyncIterator[ExecutionEvent]` with text chunks, but no existing component produces text chunks from the LLM stream.

**Impact**: The plan's architecture diagram shows the Turn Runner consuming "EXISTING" streaming. This is architecturally misleading. The Turn Runner must implement its own provider-specific streaming consumption.

**Mitigation**: The Turn Runner needs to directly call provider SDKs (anthropic, openai, google-genai) with streaming enabled and consume their respective stream formats. This is 300-500 lines of new code per provider, not "wiring."

### FINDING A-4: No Context Window Management Strategy [HIGH]

**Evidence**: The v0.1 plan mentions KAIZEN.md loading (Task 2) and budget controls (Task 7) but has zero mention of: (a) tracking token count of conversation history, (b) triggering compaction when approaching the context limit, (c) handling different model context sizes (200K for Claude, 128K for GPT-4o, 2M for Gemini). The architecture comparison document identifies compaction as a core pattern (Pattern 4), but the implementation plan defers it entirely.

Compaction is listed as Phase 2 feature. But without any token tracking in v0.1, the CLI will silently fail when conversation history exceeds the model's context window. This will happen within 5-10 tool-heavy turns for smaller models.

**Impact**: v0.1 will crash or produce degraded results on sessions longer than ~15 turns. Users will blame model quality when the real issue is context overflow.

**Mitigation**: v0.1 must include at minimum: (a) token counting per turn using tiktoken, (b) a hard context limit check that warns the user when approaching 80%, (c) a naive truncation strategy (drop oldest non-system turns) as a stopgap until Phase 2 compaction.

### FINDING A-5: CostTracker Is Modality-Oriented, Not Token-Oriented [MEDIUM]

**Evidence**: `cost/tracker.py` tracks costs by `provider` + `modality` (vision, audio, text, mixed). It has hardcoded `OPENAI_VISION_COST = 0.01` and `OPENAI_AUDIO_COST_PER_MIN = 0.006`. It does NOT have per-model token pricing tables. The `record_usage()` method accepts a pre-computed `cost: float` parameter -- it does not calculate cost from input/output token counts.

For a CLI that must display real-time cost tracking (Pattern 10), the Turn Runner must compute cost from each LLM response's token usage metadata, using per-model pricing. The CostTracker can accumulate, but the pricing logic does not exist.

**Impact**: Budget enforcement in v0.1 requires building a model pricing table and cost calculation layer that does not exist. The plan's Task 7 ("Wire to CLI") is oversimplified.

**Mitigation**: Create a `ModelPricing` registry mapping model names to input/output token costs. Wire it between the Turn Runner and CostTracker.

### FINDING A-6: Single-Process Architecture Becomes a Ceiling [MEDIUM]

**Evidence**: The plan is entirely single-process Python. Pattern 7 (Subagent/Isolation) is deferred to Phase 3. But subagents need either: (a) separate processes with their own context windows, or (b) a fundamentally different memory architecture within the same process. The plan never addresses how the single asyncio event loop will handle concurrent subagent execution with independent context windows.

**Impact**: When Phase 3 arrives, adding subagents will require either forking processes (which breaks the asyncio model) or implementing a virtual context isolation system. This is an architectural decision that should be made now, even if implementation is later.

**Mitigation**: Design the Turn Runner's context management to support multiple independent conversation histories from the start. Use a `SessionContext` per conversation that can be cloned for subagents.

### FINDING A-7: No Graceful Degradation for Missing Provider SDKs [MEDIUM]

**Evidence**: The plan requires `anthropic`, `openai`, and `google-genai` SDKs for the three providers. But the dependency list (implementation plan, Dependencies section) only lists `typer` and `rich`. There is no discussion of: (a) which provider SDKs are required vs. optional, (b) what happens if a user has only one provider's API key, (c) how to detect and report missing SDKs at runtime.

**Impact**: `pip install kailash-kaizen[cli]` will either pull in all three provider SDKs (bloated) or none of them (broken). The user experience for "I only have an OpenAI key" is undefined.

**Mitigation**: Use extras: `kailash-kaizen[cli,anthropic]`, `kailash-kaizen[cli,openai]`, `kailash-kaizen[cli,gemini]`, `kailash-kaizen[cli,all]`. Lazy-import provider SDKs and give clear errors.

---

## 2. COMPETITIVE WEAKNESSES

### FINDING C-1: 12 Tools vs 40+ Tools Is a UX Chasm [HIGH]

**Evidence**: The plan says kz starts with 12 native tools. Claude Code has 40+. The gap is not just quantity -- it is capability coverage. Claude Code's tools include: `WebFetch` (HTTP requests), `Edit` (surgical line-range edits with conflict detection), `MultiEdit` (batch edits), `TodoRead`/`TodoWrite` (task management), `LS` (directory listing), `NotebookEdit` (Jupyter). The 12 Kaizen native tools (from `tools/native/`) are: bash, file read/write, search (grep/glob), interaction (ask user), planning, process, skill, task, todo, notebook.

Critical gaps: No `Edit` tool (surgical edits are the #1 developer tool), no `WebFetch` tool (needed for documentation lookup), no `LS` equivalent (file tools do file ops but not directory listing as a dedicated tool).

**Impact**: Without an `Edit` tool, kz will use full file rewrites for every change. This is catastrophic for large files (wrong output, token waste) and will make kz feel primitive compared to Claude Code.

**Mitigation**: Build `Edit` (line-range replacement with conflict detection) and `WebFetch` before v0.1 launch. These are non-negotiable for developer adoption.

### FINDING C-2: No Multi-Agent / Subagent in Any Phase Before Phase 3 [HIGH]

**Evidence**: Claude Code has `Task` tool (subagents with fresh context, depth-limited) from day one. It is one of the most-used tools for complex workflows. The kz plan defers subagents to Phase 3 (v0.3). This means v0.1 and v0.2 cannot delegate subtasks, cannot parallelize independent work, and cannot scope context for focused operations.

**Impact**: Any task requiring exploration of multiple files or parallel investigation will be significantly slower in kz than Claude Code. This directly undermines the "autonomous agent" positioning.

**Mitigation**: Move a basic `Task` tool to v0.1. It does not need PACT governance yet -- just spawn a secondary agent call with a fresh conversation and return the result. The Kaizen `task_tool.py` already exists in `tools/native/`; verify it implements subprocess isolation.

### FINDING C-3: No Hook Event Model Specification [HIGH]

**Evidence**: The plan mentions hooks in Phase 2 and references Claude Code's 9 events and Gemini's 11 events. But it never specifies kz's hook event model. How many events? What are their names? What data do they receive? What can they return? Can they block execution? This is not a "Phase 2 detail" -- hooks define the extension surface area. Developers choosing between kz and Claude Code will check hook coverage on day one.

**Impact**: Without a hook specification, Phase 2 implementation will be designed ad-hoc. The extension surface will be inconsistent. COC artifacts that depend on `PreToolUse` and `PostToolUse` hooks cannot be ported until the event model is defined.

**Mitigation**: Define the hook event model now. Minimum viable set: `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreModel`, `PostModel`, `PreCompact`, `Stop`. Specify input/output JSON schemas for each. Specify blocking semantics (which hooks can return exit code 2 to block).

### FINDING C-4: Python Startup Time Is Measurable [MEDIUM]

**Evidence**: The plan dismisses startup time with "LLM latency dominates." But startup time is the FIRST thing users experience. `python -c "import kaizen"` baseline latency needs measurement. Kaizen imports `anyio`, the full autonomy stack, hooks, permissions, etc. Claude Code (compiled Node.js) starts in ~200ms. Codex (Rust binary) starts in ~50ms.

A Python CLI with `typer` + `rich` + `kaizen` (with its 50+ module imports) could easily take 1-2 seconds to show the first prompt. This is noticeable.

**Impact**: Users who type `kz "quick question"` and wait 1.5 seconds before seeing anything will perceive kz as slow, regardless of LLM response time.

**Mitigation**: (a) Measure actual cold start time. (b) Use lazy imports aggressively (the `core/framework.py` already has lazy loading -- verify it covers all heavy imports). (c) Show a prompt character immediately, load heavy modules in background. (d) Set a target: first prompt visible in <500ms.

---

## 3. MODEL-AGNOSTIC RISKS

### FINDING M-1: Streaming Event Models Are Fundamentally Incompatible [CRITICAL]

**Evidence**: The three providers use completely different streaming protocols:

- **Anthropic**: Server-Sent Events with `message_start`, `content_block_start`, `content_block_delta` (with `text_delta` or `input_json_delta` for tool calls), `content_block_stop`, `message_delta`, `message_stop`. Tool calls arrive as `tool_use` content blocks with JSON deltas.
- **OpenAI**: Server-Sent Events (Chat Completions) or WebSocket (Responses API). Tool calls arrive as `function` with `arguments` as partial JSON strings that must be accumulated.
- **Gemini**: Uses `@google/genai` SDK's `generate_content_stream()` which yields `GenerateContentResponse` chunks. Tool calls arrive as `FunctionCall` parts.

The Turn Runner must normalize ALL of these into a single internal event stream. The plan does not address this at all. The existing tool_mapping layer handles tool DEFINITIONS (static schemas), not tool CALL streaming (dynamic event normalization).

**Impact**: This is the hardest engineering problem in the entire CLI and it receives zero lines in the plan. Building a universal streaming normalizer that correctly handles partial tool call JSON across three different wire formats is 500-800 lines of careful, test-heavy code.

**Mitigation**: Define a `StreamEvent` protocol with types: `TextDelta`, `ToolCallStart`, `ToolCallArgumentDelta`, `ToolCallEnd`, `UsageUpdate`, `Error`, `Done`. Build provider-specific stream adapters that normalize to this protocol. Test with real provider streams, not mocks.

### FINDING M-2: Tool Call JSON Accumulation Differs by Provider [HIGH]

**Evidence**: OpenAI streams tool call arguments as partial JSON strings: `{"file_` then `path": "/` then `tmp/foo"`. The consumer must accumulate these fragments and parse the complete JSON only after the tool call is done. Anthropic sends `input_json_delta` events that are also partial. Gemini sends complete `FunctionCall` objects (no partial JSON).

The `extract_tool_call()` function in `base.py` (lines 304-363) handles COMPLETE tool calls from finished responses. It does NOT handle streaming accumulation of partial tool call arguments.

**Impact**: Without a streaming argument accumulator, the Turn Runner cannot dispatch tool calls mid-stream. It must wait for the entire LLM response to complete before identifying tool calls. This breaks the "streaming output" success criteria.

**Mitigation**: Build a `ToolCallAccumulator` per provider that buffers argument fragments and emits complete tool calls when the stream signals tool call completion.

### FINDING M-3: Context Window Sizes Differ by 10x [MEDIUM]

**Evidence**: Claude Opus: 200K tokens. GPT-4o: 128K tokens. Gemini 2.5 Pro: 1M tokens. The plan has no per-model context limit configuration. The compaction strategy (Phase 2) and the token tracking (not in any phase) must be model-aware.

A session that works fine on Gemini (1M context) will crash when switched to GPT-4o (128K) mid-session via `--model` flag, or even between sessions when resuming with a different model.

**Impact**: Model switching -- a key selling point of model-agnosticism -- will fail silently or catastrophically when context sizes differ.

**Mitigation**: Maintain a `ModelCapabilities` registry with context window size per model. Check history token count against target model's limit before every LLM call. If history exceeds, trigger compaction or refuse with a clear error.

### FINDING M-4: System Prompt Formats Differ [MEDIUM]

**Evidence**: Anthropic uses a dedicated `system` parameter (string or content blocks). OpenAI uses a `system` role message. Gemini uses `system_instruction`. The Turn Runner's prompt assembly (Step 1 in `run_turn`) must construct provider-specific message arrays. This is not just a tool mapping problem -- it is a conversation structure problem.

**Impact**: A system prompt that works for Claude (content blocks with caching) will not work for OpenAI (single string in messages array) or Gemini (separate parameter). KAIZEN.md injection, which goes into the system prompt, must be format-aware.

**Mitigation**: Abstract prompt assembly into provider-specific builders. The Turn Runner should produce a `PromptRequest` and each provider adapter should serialize it to the provider's format.

---

## 4. PERFORMANCE RISKS

### FINDING P-1: asyncio Event Loop Reliability for Long Sessions [HIGH]

**Evidence**: The plan targets "multi-turn agent loops" that can run for 100 turns (default `max_turns`). Each turn involves: (a) async LLM call with streaming, (b) async tool execution (possibly subprocess for bash), (c) async hook dispatch, (d) async session persistence. A 100-turn session with 3-5 tool calls per turn means ~500 async operations on a single event loop.

Python's asyncio has known issues with: (a) unhandled exceptions in tasks silently disappearing, (b) `create_task()` without reference collection causing GC of running tasks, (c) signal handler limitations (Ctrl+C handling), (d) subprocess management on macOS.

The `LocalKaizenAdapter.stream()` method (line 1238) uses `asyncio.create_task(run_execution())` -- if this task raises an unhandled exception, it will be silently lost unless `task.result()` is explicitly checked.

**Impact**: Long sessions will accumulate leaked tasks, uncollected exceptions, and growing memory from unbounded conversation history. The session will degrade or hang without clear error messages.

**Mitigation**: (a) Use structured concurrency (`asyncio.TaskGroup` or `anyio.create_task_group`) instead of raw `create_task`. (b) Register exception handlers on all tasks. (c) Implement a session health check that monitors event loop lag and memory usage.

### FINDING P-2: Memory Growth from Conversation History [HIGH]

**Evidence**: Session history is kept in-memory as a list of messages. Each tool result can be large (file contents from Read, command output from Bash). A 50-turn session with file reads averaging 5KB per tool result generates ~250KB of history. With 10 file reads per turn and larger files, this grows to multi-MB quickly.

The CostTracker's `_records` deque is bounded at 10,000 (good). But conversation history has no bound in the plan. The session JSONL file grows linearly. Neither the Turn Runner nor the Session Manager specifies memory limits.

**Impact**: Sessions working with large codebases will consume hundreds of MB of memory for conversation history alone. Python's garbage collector will not reclaim this because it is all live data.

**Mitigation**: (a) Truncate tool results above a threshold (e.g., 10KB -- store full result in session JSONL but only keep summary in memory). (b) Implement a sliding window over conversation history. (c) Set a memory budget for history and trigger compaction when exceeded.

### FINDING P-3: Subprocess Overhead for Bash Tool [MEDIUM]

**Evidence**: The `bash_tools.py` native tool executes shell commands via subprocess. Each bash tool invocation spawns a new process. In a typical coding session, bash is called 5-20 times per turn (running tests, checking file existence, git operations). This means 5-20 process spawns per turn.

On macOS, process creation is ~10ms. On Linux, ~3ms. For a 100-turn session, this is 500-2,000 process spawns, adding 5-20 seconds of cumulative latency.

**Impact**: While individually small, subprocess overhead compounds. The plan's claim that "LLM latency dominates" is true per-turn but false per-session for subprocess-heavy workflows.

**Mitigation**: Consider a persistent shell subprocess (like a bash session) that commands are piped into, rather than spawning a new process per invocation. This is what Codex does with its shell tool.

---

## 5. SECURITY RISKS

### FINDING S-1: v0.1-v0.2 Has Zero Sandboxing with Full Shell Access [CRITICAL]

**Evidence**: The plan explicitly states sandbox is Phase 3 (v0.3). The 12 native tools include `bash_tools.py` (arbitrary shell execution), `file_tools.py` (arbitrary filesystem read/write), and `process_tool.py` (process management). These tools run with the user's full permissions.

An LLM that is prompted to "clean up the project" could execute `rm -rf /` if it hallucinated the wrong command. An LLM tricked by a malicious KAIZEN.md could exfiltrate data via `curl`. There is no permission system, no tool approval, no network restriction.

For comparison: Claude Code ships with sandbox-exec (Seatbelt) enabled by default. Codex runs in a Docker container by default. Gemini CLI uses bubblewrap. ALL of them have sandboxing from v1.0.

**Impact**: kz v0.1 gives an LLM unrestricted access to the user's entire system. Any prompt injection, hallucination, or malicious instruction in KAIZEN.md can cause irreversible damage.

**Mitigation**: This cannot wait for Phase 3. At minimum, v0.1 MUST have:

1. A confirmation prompt for destructive commands (rm, mv, chmod, chown, git push --force)
2. A working directory restriction (tool execution confined to project root)
3. Network access off by default (no curl, wget, or outbound connections from bash)
4. File write restricted to project directory only

This is a basic permission-as-middleware implementation (Pattern 3), not full OS sandboxing.

### FINDING S-2: KAIZEN.md Is an Injection Vector [CRITICAL]

**Evidence**: KAIZEN.md is loaded from the filesystem and injected into the system prompt. If a user clones a malicious repository that contains a crafted KAIZEN.md, the LLM will follow those instructions. This is the exact same attack vector as `.claude/` directory injection in Claude Code.

The plan has NO mention of: (a) KAIZEN.md content sanitization, (b) warning users when KAIZEN.md is loaded from an untrusted source, (c) limiting what KAIZEN.md can instruct (e.g., it should not be able to disable safety checks).

**Impact**: A malicious KAIZEN.md could instruct the LLM to: exfiltrate API keys from .env, modify ~/.ssh/authorized_keys, install backdoors, or ignore user safety instructions. This is a well-known attack vector in the agent CLI space.

**Mitigation**: (a) Display KAIZEN.md content on first load and require user confirmation. (b) Hash KAIZEN.md and warn if it changes between sessions. (c) Never allow KAIZEN.md to override safety-critical instructions (tool restrictions, network policy). (d) Study Claude Code's trust model for CLAUDE.md -- it treats project instructions as lower priority than system safety.

### FINDING S-3: Session JSONL Files Are Plaintext with Full Tool Output [HIGH]

**Evidence**: Session persistence stores full conversation history as JSONL in `~/.kaizen/sessions/{id}/transcript.jsonl`. Tool results include file contents (which may contain secrets), bash output (which may contain environment variables), and API responses.

There is no encryption, no access control, and no redaction.

**Impact**: A session that reads `.env` files (common in development) will persist API keys in plaintext JSONL. If `~/.kaizen/sessions/` is backed up, synced, or accessible to other users, secrets are exposed.

**Mitigation**: (a) Redact known secret patterns (API keys, tokens) from session JSONL. (b) Encrypt session files at rest using a user-derived key. (c) At minimum, set file permissions to 0600 (owner read/write only) on session files.

### FINDING S-4: MCP Server Trust Model Undefined [MEDIUM]

**Evidence**: The plan mentions MCP integration via "Kaizen MCP client." MCP servers are external processes that provide additional tools. The plan does not specify: (a) how MCP servers are authenticated, (b) what data MCP servers can access, (c) whether MCP tool calls go through the permission system, (d) how to prevent a rogue MCP server from reading arbitrary files.

**Impact**: An MCP server configured in `.kaizen/settings.toml` has implicit trust. A malicious or compromised MCP server can exfiltrate data through tool result channels.

**Mitigation**: (a) MCP tool calls MUST go through the same permission middleware as native tools. (b) MCP servers should declare their required permissions upfront. (c) User must explicitly approve each MCP server's permission scope.

### FINDING S-5: Hook System Executes Arbitrary Code [MEDIUM]

**Evidence**: The hook system (Phase 2) will execute shell/Python scripts triggered by agent lifecycle events. If KAIZEN.md or `.kaizen/hooks/` can define hooks, then a malicious repository can execute arbitrary code when the user starts a kz session.

**Impact**: Similar to S-2 but worse -- hooks execute before the user sees any prompt, giving no opportunity for review.

**Mitigation**: (a) Hooks must be explicitly approved by the user on first encounter. (b) Hooks from project directories are untrusted by default. (c) Display hook source and require confirmation before first execution.

---

## 6. MISSING CONCERNS

### FINDING X-1: No Error Recovery or Retry Strategy [CRITICAL]

**Evidence**: The v0.1 plan has zero mention of: (a) what happens when the LLM API returns a 429 (rate limit), (b) what happens when the LLM API returns a 500 (server error), (c) what happens when a tool execution fails, (d) what happens when the network drops mid-stream.

Gemini CLI has "mid-stream retry: up to 4 attempts with exponential backoff." Codex has configurable retry. The plan has nothing.

**Impact**: The first time a user hits a rate limit (common with Claude Opus), kz will crash with an unhandled exception. This is a day-one user experience failure.

**Mitigation**: Build a retry layer with: (a) exponential backoff for rate limits (429), (b) configurable max retries (default: 3), (c) graceful degradation for server errors (save session, offer to resume), (d) tool execution retry with user confirmation.

### FINDING X-2: No Ctrl+C / Signal Handling [HIGH]

**Evidence**: The plan mentions `interrupt_manager` in the LocalKaizenAdapter but the v0.1 plan never wires signal handling. When a user presses Ctrl+C during an LLM call, Python raises `KeyboardInterrupt` which will: (a) kill the asyncio event loop, (b) corrupt any in-progress session write, (c) leave orphaned subprocess (bash tool) running.

For comparison: Claude Code catches Ctrl+C, offers "Cancel current request?" and allows graceful continuation. Codex has signal handling in its Rust core.

**Impact**: Every Ctrl+C will potentially corrupt the session and require a fresh start. Users press Ctrl+C frequently (wrong prompt, too long, changed mind).

**Mitigation**: (a) Register SIGINT handler that sets a cancellation flag. (b) Check flag between turns and between tool calls. (c) On first Ctrl+C: cancel current LLM call, preserve session. (d) On second Ctrl+C (within 1 second): force exit with session save.

### FINDING X-3: No Token Estimation Before LLM Call [HIGH]

**Evidence**: The plan says budget controls enforce `max_budget_usd` but there is no pre-call token estimation. Without knowing how many tokens the current prompt will consume, the budget check can only happen AFTER the LLM response arrives -- by which point the money is already spent.

**Impact**: A user with `--max-budget 1.00` could have $0.95 spent, and the next turn (which might cost $0.50 for a large context with Opus) will exceed the budget. The check happens after the call, so $1.45 is spent instead of $1.00.

**Mitigation**: (a) Estimate token count of the outgoing prompt using tiktoken. (b) Estimate cost of the next call based on prompt tokens + expected output tokens. (c) If estimated cost would exceed remaining budget, warn the user BEFORE making the call.

### FINDING X-4: No Progress Indication During Tool Execution [MEDIUM]

**Evidence**: The plan's Terminal UI (Task 4) mentions "ToolUse events -> show tool name + spinner." But the implementation for long-running tools (e.g., `pytest` via bash taking 30 seconds) has no intermediate progress. The user sees "Running bash..." and then nothing for 30 seconds.

**Impact**: Users will think kz has hung during long tool executions.

**Mitigation**: For bash tool specifically: stream subprocess stdout to the terminal in real-time (behind a `--verbose` flag or collapsible section).

### FINDING X-5: No Update/Version Check Mechanism [MEDIUM]

**Evidence**: The plan has no mention of how users will know a new version is available. `pip install` does not auto-update. There is no `kz update` command, no version check on startup, no notification system.

**Impact**: Users will run outdated versions indefinitely. Bug fixes and security patches will not propagate.

**Mitigation**: On session start, check PyPI for latest version (async, non-blocking). If newer version exists, display a one-line notice. Do NOT auto-update.

### FINDING X-6: No Telemetry or Crash Reporting [LOW]

**Evidence**: No mention of telemetry, usage analytics, or crash reporting. This is a Terrene Foundation project (open source), so telemetry must be opt-in, but crash reporting is essential for quality.

**Impact**: Bugs in production will be invisible. Users will silently churn.

**Mitigation**: Implement opt-in crash reporting using Sentry or equivalent. On unhandled exception, offer to send anonymized crash report.

### FINDING X-7: No Concurrent Session Protection [LOW]

**Evidence**: Session files are stored in `~/.kaizen/sessions/{id}/`. There is no file locking. If a user opens two terminals and runs `kz --resume <id>` in both, both will write to the same JSONL file concurrently, causing corruption.

**Mitigation**: Use a lock file (`transcript.lock`) with `fcntl.flock()` to prevent concurrent access to the same session.

### FINDING X-8: No Configuration Validation [LOW]

**Evidence**: The config loading (Task 2) walks up to find KAIZEN.md and loads `.kaizen/settings.toml`. There is no schema validation for settings.toml. A typo (`max_tuRns` instead of `max_turns`) will be silently ignored.

**Mitigation**: Define a TOML schema and validate on load. Report unknown keys as warnings.

### FINDING X-9: No Offline / Local Model Support in v0.1 [LOW]

**Evidence**: The plan mentions model tiers but all listed models are cloud APIs. There is no mention of Ollama, llama.cpp, or other local model support. The CostTracker already has Ollama support, but the Turn Runner and model resolution have no local model path.

**Mitigation**: Add Ollama as a provider in the model resolution. It already has cost tracking support (cost = $0.00). This is a differentiation opportunity -- none of the three competitors have seamless local model support.

---

## Risk Register Summary

| ID  | Severity | Finding                                           | Likelihood | Impact   | Mitigation Status  |
| --- | -------- | ------------------------------------------------- | ---------- | -------- | ------------------ |
| A-1 | CRITICAL | StreamingExecutor is batch, not streaming         | Certain    | High     | Needs new design   |
| A-2 | CRITICAL | No Anthropic/Claude tool mapper                   | Certain    | High     | Build before v0.1  |
| M-1 | CRITICAL | Streaming event models incompatible across models | Certain    | High     | Needs new design   |
| S-1 | CRITICAL | No sandboxing with full shell access              | Certain    | Critical | Must add to v0.1   |
| S-2 | CRITICAL | KAIZEN.md injection vector                        | Likely     | Critical | Must add to v0.1   |
| X-1 | CRITICAL | No error recovery or retry                        | Certain    | High     | Must add to v0.1   |
| A-4 | HIGH     | No context window management                      | Certain    | High     | Must add to v0.1   |
| A-3 | HIGH     | Streaming is queue-based simulation               | Certain    | Medium   | Needs new design   |
| C-1 | HIGH     | 12 tools vs 40+ (missing Edit, WebFetch)          | Certain    | High     | Build Edit tool    |
| C-2 | HIGH     | No subagent support until v0.3                    | Certain    | Medium   | Move to v0.1       |
| C-3 | HIGH     | No hook event model specification                 | Certain    | Medium   | Specify now        |
| M-2 | HIGH     | Tool call JSON accumulation differs by provider   | Certain    | High     | Build accumulator  |
| P-1 | HIGH     | asyncio reliability for long sessions             | Likely     | High     | Use TaskGroup      |
| P-2 | HIGH     | Memory growth from conversation history           | Likely     | Medium   | Bound history      |
| S-3 | HIGH     | Session files are plaintext with secrets          | Likely     | High     | Encrypt/redact     |
| X-2 | HIGH     | No Ctrl+C / signal handling                       | Certain    | High     | Must add to v0.1   |
| X-3 | HIGH     | No token estimation before LLM call               | Certain    | Medium   | Add tiktoken       |
| A-5 | MEDIUM   | CostTracker is modality-oriented                  | Certain    | Medium   | Build pricing      |
| A-6 | MEDIUM   | Single-process ceiling for subagents              | Likely     | Medium   | Design now         |
| A-7 | MEDIUM   | No graceful degradation for missing SDKs          | Certain    | Medium   | Use extras         |
| C-4 | MEDIUM   | Python startup time                               | Likely     | Low      | Measure + lazy     |
| M-3 | MEDIUM   | Context window sizes differ 10x                   | Certain    | Medium   | Model capabilities |
| M-4 | MEDIUM   | System prompt formats differ                      | Certain    | Medium   | Provider builders  |
| P-3 | MEDIUM   | Subprocess overhead for bash tool                 | Likely     | Low      | Persistent shell   |
| S-4 | MEDIUM   | MCP server trust model undefined                  | Possible   | High     | Permission system  |
| S-5 | MEDIUM   | Hook system executes arbitrary code               | Possible   | High     | Approval system    |
| X-4 | MEDIUM   | No progress for long tool executions              | Certain    | Low      | Stream subprocess  |
| X-5 | MEDIUM   | No update mechanism                               | Certain    | Low      | Version check      |
| X-6 | LOW      | No telemetry or crash reporting                   | Certain    | Low      | Opt-in Sentry      |
| X-7 | LOW      | No concurrent session protection                  | Possible   | Medium   | File locking       |
| X-8 | LOW      | No configuration validation                       | Certain    | Low      | Schema validation  |
| X-9 | LOW      | No local model support                            | Certain    | Low      | Add Ollama         |

---

## Revised Effort Estimate

The plan estimates ~2,500 new lines for v0.1. Based on this red team analysis:

| Component                           | Plan Estimate | Red Team Estimate | Delta      |
| ----------------------------------- | ------------- | ----------------- | ---------- |
| CLI entry point                     | 200           | 300               | +100       |
| Config + KAIZEN.md loading          | 150           | 250               | +100       |
| Turn runner (core loop)             | 500           | 800               | +300       |
| **Stream normalizer (3 providers)** | 0             | 600               | **+600**   |
| **Anthropic tool mapper**           | 0             | 200               | **+200**   |
| **Tool call accumulator**           | 0             | 300               | **+300**   |
| Terminal UI                         | 300           | 400               | +100       |
| Session persistence                 | 200           | 300               | +100       |
| Model resolution + pricing          | 0             | 200               | **+200**   |
| **Error recovery + retry**          | 0             | 250               | **+250**   |
| **Signal handling**                 | 0             | 100               | **+100**   |
| **Basic permission middleware**     | 0             | 200               | **+200**   |
| **Token counting + estimation**     | 0             | 150               | **+150**   |
| **Edit tool**                       | 0             | 300               | **+300**   |
| Budget controls                     | 50            | 100               | +50        |
| Tests                               | 400           | 800               | +400       |
| **TOTAL**                           | **~2,000**    | **~5,250**        | **+3,250** |

The plan underestimates by approximately 2.6x. The "70% existing infrastructure" claim is more accurately "40% existing infrastructure, 30% infrastructure that exists but needs significant adaptation, 30% genuinely new."

---

## Decision Points Requiring Stakeholder Input

1. **Sandboxing in v0.1**: Ship unsandboxed with basic permission middleware, or delay launch until Phase 3 sandbox is ready? The security risk of unsandboxed shell access is real.

2. **Streaming architecture**: Build three provider-specific stream adapters now, or start with one provider (Anthropic) and add others in v0.2?

3. **Edit tool priority**: Is the `Edit` tool (surgical line-range replacement) a v0.1 blocker or v0.2 feature?

4. **Subagent priority**: Is a basic `Task` tool (subagent with fresh context) a v0.1 feature or does it stay in v0.3?

5. **Session encryption**: Is plaintext session storage acceptable for v0.1, or must session files be encrypted from day one?

6. **Local model support**: Should Ollama support be in v0.1 as a differentiation feature?

---

## Files Referenced

- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-cli/briefs/01-kz-cli-strategy.md`
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-cli/01-analysis/01-cli-architecture-comparison.md`
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-cli/01-analysis/02-kz-binary-boundary.md`
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-cli/01-analysis/03-kaizen-reuse-map.md`
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-cli/02-plans/01-kz-v01-implementation-plan.md`
- `/Users/esperie/repos/terrene/terrene/workspaces/pact/02-plans/04-agent-cli-patterns-reference.md`
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/runtime/adapters/tool_mapping/base.py` -- KaizenTool is OpenAI-canonical, no Anthropic mapper
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/runtime/adapters/tool_mapping/__init__.py` -- Only exports MCP, OpenAI, Gemini mappers
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/execution/streaming_executor.py` -- Batch execution, not real-time streaming
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/cost/tracker.py` -- Modality-oriented, no per-model token pricing
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/runtime/adapters/kaizen_local.py` -- Queue-based stream simulation
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/core/autonomy/control/transports/cli.py` -- Line-based JSON protocol, not token streaming

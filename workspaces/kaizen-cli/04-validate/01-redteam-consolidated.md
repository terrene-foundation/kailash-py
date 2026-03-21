# kz CLI Red Team: Consolidated Report

**Date**: 2026-03-21
**Red Team Composition**: 4 analysis agents + main context web research + self-introspection
**Scope**: Pre-implementation architectural validation of kz CLI v0.1 plan
**Verdict**: Plan is strategically correct but architecturally underspecified. Major revision needed before implementation.

---

## Part 1: Autonomy Mechanisms — How Each CLI Achieves Agent Autonomy

### Claude Code: Subagents + Agent Teams

**Core autonomy loop**: `while (tool_calls > 0)` — the model generates text and tool calls; all tool calls are executed (in parallel where possible); results feed back as conversation turns; loop continues until the model produces text with no tool calls.

**Subagent mechanism** (Agent/Task tool):

- Each subagent gets a **fresh 200K context window** (no parent history)
- Subagent receives ONLY the parent's prompt string — no other channel
- All intermediate tool calls stay inside the subagent's context
- Only the **final message** returns to the parent
- **Depth limited to 1**: subagents cannot spawn further subagents
- Subagent transcripts persist independently (survive parent compaction)

**Agent Teams** (experimental, 2026):

- Multiple Claude Code sessions coordinated via `SendMessage`
- One session acts as **team lead**, others as **teammates**
- Message types: `message` (direct), `broadcast` (all), `shutdown_request/response`, `plan_approval_response`
- **NO shared memory** — task files on disk + SendMessage are the ONLY coordination channels
- Each teammate has its own independent context window
- Use cases: parallel research, cross-layer coordination, competing hypotheses

**What makes it work**: The combination of fresh context windows (prevents pollution) + depth limiting (prevents explosion) + parallel execution (prevents sequential bottleneck). The model itself decides WHEN to delegate — this is the key insight. The autonomy is in the model's reasoning, not in the infrastructure.

### Codex: Unified App Server + Subagents

**Core autonomy loop**: `run_turn()` in `codex.rs` — turn-scoped execution with `FuturesOrdered` for parallel tool calls, mid-turn compaction, and `needs_follow_up` continuation.

**App Server architecture**: Three conversation primitives:

- **Item**: Atomic unit (user message, agent message, tool execution, approval, diff) with lifecycle: started → delta events → completed
- **Turn**: Sequence of items from a single unit of agent work
- **Thread**: Durable container with persisted event history

**Subagent mechanism**:

- Codex handles orchestration: spawning, routing, waiting, consolidation
- Subagents run in parallel for tasks like codebase exploration or multi-step implementation
- Results consolidated before returning to user

**Five collaboration tools** (from `multi_agents.rs`):

1. `spawn_agent` — Creates a new agent thread (with optional `fork_context` to clone parent history)
2. `send_input` — Sends messages to running agents (with optional `interrupt` flag)
3. `wait_agent` — Blocks until target agents reach final status (configurable timeout: 30s default, max 1hr)
4. `close_agent` — Shuts down an agent and all its descendants
5. `resume_agent` — Resumes an existing agent from rollout

**Concurrency limits** (from `config/mod.rs`):

- `DEFAULT_AGENT_MAX_THREADS = 6` (configurable)
- `DEFAULT_AGENT_MAX_DEPTH = 1` (configurable — unlike Claude Code's hard limit)

**AgentControl** (`agent/control.rs`): A control plane held by each session. Spawns new `CodexThread` instances with inherited config (sandbox, approval, cwd). Tracks parent-child relationships in SQLite state DB, surviving session resumption. Model is explicitly prompted (in `orchestrator.md`) to "Prefer multiple sub-agents to parallelize your work."

**What makes it work**: The Item/Turn/Thread abstraction creates a clean separation between the agent loop (which operates on Turns) and persistence (which operates on Threads). The 5-tool collaboration model is the most architecturally complete multi-agent implementation of the three — it's the reference for kz.

### Gemini CLI: A2A Protocol + Plan Mode

**Core autonomy loop**: `processTurn()` in `client.ts` — up to 100 turns per session, with `Scheduler.schedule()` for batched tool execution and mid-stream retry (4 attempts, exponential backoff).

**A2A Protocol** (Agent-to-Agent):

- Open standard (Linux Foundation)
- `A2AExecutor` wraps agent logic with standardized message exchange methods
- `A2AServer` provides API endpoints
- HTTP-authenticated remote agents (OAuth 2.0 flows)
- Recent: `a2a-server` experimental package in the monorepo

**Plan Mode**:

- Built-in research subagents
- Annotation support for user feedback on plans
- Generalist agent for task delegation and routing

**Local subagents** (from `local-executor.ts`):

- `SubagentTool` exposes agents as regular tools to the parent model
- `LocalSubagentInvocation`, `RemoteAgentInvocation`, `BrowserAgentInvocation` — three invocation types
- **Recursion explicitly prevented**: "Check if the tool is a subagent to prevent recursion. We do not allow agents to call other agents."
- Limits: `DEFAULT_MAX_TURNS = 30`, `DEFAULT_MAX_TIME_MINUTES = 10`
- Built-in agents: CodebaseInvestigator (read-only research), GeneralistAgent, BrowserAgent (Playwright)

**What makes it work**: A2A is the most forward-looking — it enables cross-organization agent communication with OAuth2 auth. But local subagents are strictly single-level with no inter-agent communication. The unique capability is exposing itself AS an A2A server (experimental `a2a-server` package).

### Comparative Autonomy Assessment

| Dimension                     | Claude Code                             | Codex                                | Gemini CLI                   |
| ----------------------------- | --------------------------------------- | ------------------------------------ | ---------------------------- |
| **Intra-session parallelism** | Subagents (fresh context, depth-1)      | FuturesOrdered (parallel tool calls) | Scheduler batching           |
| **Multi-agent coordination**  | Agent Teams (SendMessage, experimental) | App Server orchestration             | A2A Protocol (open standard) |
| **Context isolation**         | Fresh 200K per subagent                 | Turn-scoped context                  | Per-turn context             |
| **Depth**                     | 1 (subagents cannot spawn subagents)    | Flat (orchestrator manages all)      | Flat (scheduler manages all) |
| **Inter-agent communication** | SendMessage (direct, broadcast)         | Via App Server                       | A2A HTTP endpoints           |
| **Shared state**              | None (files on disk only)               | Thread history                       | A2A message exchange         |
| **Autonomy ceiling**          | High (model decides when to delegate)   | High (turn-based with follow-up)     | Moderate (scheduler-driven)  |

---

### What Each Does That The Others Can't

- **Claude Code**: Agent Teams with true peer-to-peer collaboration. Teammates message EACH OTHER directly (not just report to parent). Shared file-locked task lists. No other CLI has this.
- **Codex**: Full agent lifecycle in Rust — `spawn_agent`, `send_input`, `wait_agent`, `close_agent`, `resume_agent`. Context forking. Persistent agent tree in SQLite. Most architecturally complete multi-agent system.
- **Gemini CLI**: A2A protocol for calling remote agents over HTTP/gRPC with OAuth2. Can expose itself as an A2A server. No other CLI can communicate with arbitrary external agents via standardized protocol.

### kz's Unique Opportunity

**None of these CLIs have organizational governance.** kz with PACT adds:

- 5-dimensional operating envelope (financial, operational, temporal, data access, communication) constraining every agent
- Monotonic tightening (child envelope can never exceed parent)
- Per-dimension verification gradient (auto/flagged/held/blocked)
- Cryptographic audit trail (EATP) for every action across the agent tree
- Knowledge clearance levels independent of authority

**This is the governance layer that turns "multi-agent autonomy" into "governed multi-agent autonomy."** It's what makes enterprises trust agent systems enough to deploy them.

---

## Part 2: What This Reveals About kz's Weaknesses

### WEAKNESS 1: No Subagent Model At All [CRITICAL]

The v0.1 plan has **zero subagent capability**. This is the single most important gap.

From my introspection of the current Claude Code session: I spawned 4 research agents in parallel, each with fresh context, and synthesized their results. Without this capability, this red team would have taken 4x longer and consumed 4x the main context.

**Every competitor has subagent-like capabilities from day one.** Claude Code has the Agent tool. Codex has subagent orchestration. Gemini has Plan Mode with research subagents.

**Impact on kz positioning**: Without subagents, kz cannot:

- Parallelize independent research tasks
- Scope context for focused operations (file-heavy exploration pollutes main context)
- Implement the COC phase workflow (which relies on agent teams)
- Compete with Claude Code on complex multi-step tasks

**Recommendation**: A basic Task tool (spawn a secondary LLM call with fresh conversation, return the result) MUST be in v0.1. It does not need PACT governance yet. Minimum viable: `asyncio.create_task()` with an independent message history.

### WEAKNESS 2: No Streaming Normalization Layer [CRITICAL]

The three providers use completely different streaming protocols. The plan trusts "existing Kaizen adapters" but inspection reveals:

- `StreamingExecutor` is batch-oriented (emits events post-hoc, not real-time)
- `LocalKaizenAdapter.stream()` produces status strings, not text deltas
- There is NO `AnthropicToolMapper` despite Claude being Tier 1
- Tool call argument accumulation differs by provider (partial JSON vs complete)

**This is 600-800 lines of the hardest engineering in the entire CLI.** It receives zero lines in the plan.

### WEAKNESS 3: The "70% Reuse" Is 40% [HIGH]

Both the architecture red team and the veteran critique independently verified:

- **Will reuse cleanly (~40%)**: CostTracker, native tools, event types, tool format mapping
- **Needs significant adaptation (~20%)**: LocalKaizenAdapter (batch → interactive), StreamingExecutor (batch → real-time)
- **Won't reuse at all (~30%)**: Agent unified API (CLI is itself the user layer), BaseAgent (workflow node, not agent loop), specialist system (wrong abstraction for KAIZEN.md)
- **Not addressed in plan (~10%)**: LLM client abstraction, streaming parsers, Anthropic mapper, error recovery

**Revised effort**: ~5,250 lines, not ~2,500. Still achievable in 3-5 autonomous sessions, but the scope is honest.

### WEAKNESS 4: Zero Sandboxing Until Phase 3 [CRITICAL]

v0.1 ships 12 native tools (including bash execution and filesystem write) with NO sandboxing. Every competitor ships with sandboxing from v1.0.

**Minimum v0.1 mitigation** (not full sandbox, but basic safety):

1. Confirmation prompt for destructive commands (rm, mv, chmod, git push --force)
2. Working directory restriction (tool execution confined to project root)
3. File write restricted to project directory
4. KAIZEN.md content display + confirmation on first load

### WEAKNESS 5: No Hook System = No COC [CRITICAL for strategy]

The entire strategic rationale for kz is "COC embodiment — trigger COC artifacts autonomously." But hooks are Phase 2. Without hooks, there is no mechanism to:

- Run PreToolUse guards
- Inject anti-amnesia reminders (user-prompt-rules-reminder)
- Enforce zero-tolerance rules
- Fire session-start context loading

**kz without hooks is just another chat CLI.** Hooks are what make it a COC platform.

---

## Part 3: The 5 Critical Decisions

These decisions, identified by the veteran critique and confirmed by architectural analysis, will determine success or failure:

### Decision 1: LLM Client Abstraction

**Options**: (A) litellm, (B) raw httpx per provider, (C) official SDKs with thin adapter

**Recommendation**: **(C) Official SDKs** (anthropic, openai, google-genai) behind a 30-line protocol:

```python
class LLMClient(Protocol):
    async def stream_completion(
        self, messages: list, tools: list, system: str
    ) -> AsyncIterator[StreamEvent]: ...
```

Official SDKs are most stable. litellm adds complexity without proportional value at this scale.

### Decision 2: Conversation State Structure

**Options**: (A) Flat message list, (B) Structured turns

**Recommendation**: **(B) Structured turns** from day 1. Every CLI that starts with (A) rewrites to (B) within 6 months. Codex's Item/Turn/Thread model is the reference.

### Decision 3: Async REPL

**Options**: (A) asyncio.run() with typer, (B) anyio/trio, (C) prompt_toolkit

**Recommendation**: **(C) prompt_toolkit** for the REPL + typer for CLI arg parsing. prompt_toolkit gives async input, key bindings, history, auto-complete, and paste handling for free.

### Decision 4: Parallel Tool Execution

**Options**: (A) Sequential, (B) asyncio.gather(), (C) TaskGroup with topological ordering

**Recommendation**: **(B) asyncio.gather()** with same-path serialization guard. Covers 95% of cases.

### Decision 5: Error Taxonomy

**Options**: (A) Catch-all, (B) Classified errors

**Recommendation**: **(B) Classified** from day 1:

- `RecoverableError` (rate limit, network timeout) → auto-retry with backoff
- `UserRecoverableError` (auth failure, invalid model) → show error, prompt user
- `TerminalError` (budget exceeded) → save session, exit gracefully

---

## Part 4: What's Missing (Production Essentials)

Both red team agents independently identified these gaps:

| Gap                                    | Lines Est. | Priority    | Why                                                          |
| -------------------------------------- | ---------- | ----------- | ------------------------------------------------------------ |
| **Ctrl+C / signal handling**           | 100-150    | v0.1 MUST   | Without it, every interrupt corrupts the session             |
| **prompt_toolkit REPL**                | 200-300    | v0.1 MUST   | Typer doesn't do REPL; users need history, multi-line, paste |
| **First-run API key UX**               | 100        | v0.1 MUST   | 50% of GitHub issues will be "how do I set my API key"       |
| **Output truncation for tool results** | 100        | v0.1 MUST   | 10K-line file reads fill context in 3 turns                  |
| **--print non-interactive mode**       | 50         | v0.1 SHOULD | 40% of usage is scripting/CI/piping                          |
| **Rate limit feedback**                | 50         | v0.1 MUST   | "Rate limited. Retrying in 32s..." with countdown            |
| **Per-turn cost display**              | 50         | v0.1 SHOULD | Users want to see what each turn costs                       |
| **Tool execution timeout**             | 50         | v0.1 MUST   | Bash tool can hang forever                                   |
| **Invalid JSON repair for tool calls** | 100        | v0.1 MUST   | Models return broken JSON, especially Tier 3                 |
| **Graceful partial tool loading**      | 50         | v0.1 SHOULD | Missing optional deps shouldn't crash the registry           |
| **Version check on startup**           | 30         | v0.2        | Non-blocking PyPI version check                              |
| **Session file permissions**           | 20         | v0.1 MUST   | 0600 on JSONL files (contain secrets from .env reads)        |

---

## Part 5: Competitive Landscape

### Direct Competitors (2026)

| Tool            | Stars             | Language    | Models         | Key Differentiator                                           |
| --------------- | ----------------- | ----------- | -------------- | ------------------------------------------------------------ |
| **Claude Code** | N/A (proprietary) | TS (binary) | Claude only    | Deepest autonomy (subagents + teams), richest tool set (40+) |
| **Codex CLI**   | N/A (proprietary) | Rust + JS   | OpenAI only    | Best architecture (Item/Turn/Thread), sandbox-first          |
| **Gemini CLI**  | Open source       | TypeScript  | Gemini only    | Full transparency, A2A protocol, 11 hook events              |
| **OpenCode**    | 95K+              | Go          | 75+ providers  | Model-agnostic leader, TUI, open source                      |
| **Junie CLI**   | New (JetBrains)   | ?           | BYOK           | JetBrains ecosystem, governance focus                        |
| **OpenHands**   | High              | Python      | Model-agnostic | Docker/K8s isolation, enterprise                             |
| **Droid**       | ?                 | ?           | Model-agnostic | Specialized sub-agents, top Terminal-Bench                   |

### kz's Positioning

**Strongest vs competitors**:

- PACT governance (5-dimensional operating envelope) — nobody else has this
- Organizational hierarchy (D/T/R addressing) — unique
- Cryptographic audit trail (EATP trust lineage) — unique
- Built on full SDK (Core SDK + DataFlow + Nexus + Kaizen) — competitors are standalone tools

**Weakest vs competitors**:

- Tool set (12 vs Claude Code's 40+)
- Maturity (v0.1 vs years of production use)
- Model support at launch (3 providers vs OpenCode's 75+)
- No subagent model in v0.1
- Python startup time vs Go/Rust/compiled Node
- No sandbox until Phase 3

**Killer feature gap**: Claude Code's subagent + agent teams model gives it a massive productivity advantage for complex tasks. kz must close this gap by v0.2 at latest.

**Enterprise buyer argument**: "Claude Code is Claude-only. Codex is OpenAI-only. Gemini CLI is Gemini-only. kz is model-agnostic with organizational governance — the only CLI that fits in a regulated enterprise where model choice is a policy decision, not a developer preference."

---

## Part 6: Introspection — What My Own Execution Reveals

I (Claude Code CLI, Opus 4.6) am currently executing the very workflow that kz must replicate. Key observations from self-analysis:

1. **Subagent spawning is the autonomy mechanism**: I spawned 4 research agents + 4 red team agents. Each had fresh context. My main context stayed clean. **kz without subagents is a chat wrapper.**

2. **Background execution is the multiplier**: I launched agents with `run_in_background: true` and continued doing web searches while they ran. **kz must be async-first.**

3. **The skill/command system IS the COC**: When `/redteam` loaded, it gave me structured methodology. Without it, I'd improvise. **kz must load KAIZEN.md commands from day 1.**

4. **Hooks are invisible but always working**: Every turn, `user-prompt-rules-reminder.js` fires. I don't see it consciously. **kz must have hooks in v0.1, not v0.2.**

5. **Failure adaptation is first-class**: The competitive-researcher agent failed (no web search). I detected and handled it myself. **kz must classify and recover from errors.**

6. **The filesystem is durable memory**: I wrote analysis documents to disk. If my context compacts, the documents survive. **kz sessions must externalize important state to files.**

7. **Permission model is layered**: Some tools auto-approve, some ask. **kz needs basic permission middleware in v0.1.**

---

## Part 7: Revised v0.1 Scope

Based on all red team findings, the v0.1 scope must expand:

### MUST HAVE (blocks launch)

| Feature                                       | Lines      | Source             |
| --------------------------------------------- | ---------- | ------------------ |
| CLI entry point (typer + prompt_toolkit REPL) | 400        | Plan + veteran     |
| LLM client abstraction (3 provider SDKs)      | 300        | Decision 1         |
| Stream normalizer (3 providers)               | 600        | A-1, M-1           |
| Anthropic tool mapper                         | 200        | A-2                |
| Tool call accumulator                         | 300        | M-2                |
| Turn runner (core loop)                       | 800        | Plan (revised)     |
| Structured turn state                         | 200        | Decision 2         |
| Terminal UI (rich streaming)                  | 400        | Plan               |
| Session persistence (JSONL)                   | 300        | Plan               |
| Basic subagent (Task tool)                    | 300        | C-2, introspection |
| Basic hook system (5 events)                  | 300        | C-3, introspection |
| KAIZEN.md + config loading                    | 250        | Plan               |
| Error recovery + retry                        | 250        | X-1                |
| Signal handling (Ctrl+C)                      | 150        | X-2                |
| Basic permission middleware                   | 200        | S-1                |
| Output truncation for tool results            | 100        | Veteran            |
| Tool execution timeout                        | 50         | Veteran            |
| Token estimation (tiktoken)                   | 150        | X-3                |
| Model pricing table                           | 100        | A-5                |
| Budget controls                               | 100        | Plan               |
| First-run API key UX                          | 100        | Veteran            |
| Edit tool                                     | 300        | C-1                |
| Tests (Tier 1 + 2)                            | 800        | Plan (revised)     |
| **TOTAL**                                     | **~6,150** |                    |

### SHOULD HAVE (v0.1 nice-to-have)

- `--print` non-interactive mode (50 lines)
- Per-turn cost display (50 lines)
- Ollama/local model support (100 lines)
- Graceful partial tool loading (50 lines)

### DEFER TO v0.2

- Context compaction (LLM-generated summaries)
- Full hook system (11 events)
- Advanced subagent features (background execution, teams)
- Session encryption
- MCP server trust model

### DEFER TO v0.3

- OS-level sandbox (Seatbelt, bubblewrap)
- Full permission policy engine
- Multi-session management
- Telemetry / crash reporting

---

## Autonomous Estimate (Revised)

- **Lines**: ~6,150 (was ~2,500)
- **Complexity**: Streaming normalization is the hardest engineering problem
- **Sessions**: 4-6 autonomous sessions (was 2-3)
- **Critical path**: Stream normalizer → Turn runner → Subagent → Hooks

This is still fast under the autonomous execution model — the original plan (03-kaizen-py-constrained-agent.md) estimated 33-50 human-days for the full constrained agent. With the 10x multiplier, 4-6 sessions is ~2-3 days of clock time.

---

## Decision Points for Stakeholder

1. **Accept revised scope?** v0.1 is ~6,150 lines, not ~2,500. The quality bar is higher but so is the deliverable.
2. **Subagent in v0.1?** Red team unanimously recommends yes. Without it, kz is a chat wrapper.
3. **Hooks in v0.1?** Red team unanimously recommends yes. Without them, kz cannot trigger COC artifacts.
4. **Start with Anthropic-only streaming, add others in v0.2?** Or build all 3 providers for v0.1?
5. **Edit tool in v0.1?** Without it, kz uses full file rewrites — feels primitive.
6. **Ollama in v0.1?** Differentiation opportunity — no competitor has seamless local models.

Sources:

- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)
- [Codex Subagents](https://developers.openai.com/codex/subagents)
- [Codex App Server Architecture](https://www.infoq.com/news/2026/02/opanai-codex-app-server/)
- [Gemini CLI Multi-Agent Proposal](https://github.com/google-gemini/gemini-cli/discussions/7637)
- [OpenCode vs Claude Code](https://www.infralovers.com/blog/2026-01-29-claude-code-vs-opencode/)
- [Junie CLI Beta](https://blog.jetbrains.com/junie/2026/03/junie-cli-the-llm-agnostic-coding-agent-is-now-in-beta/)
- [Unrolling the Codex Agent Loop](https://openai.com/index/unrolling-the-codex-agent-loop/)

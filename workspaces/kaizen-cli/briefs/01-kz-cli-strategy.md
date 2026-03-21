# kz CLI: Strategic Brief

## Vision

Build `kz` — a model-agnostic autonomous agent CLI that inherits the best architectural patterns from Claude Code, OpenAI Codex, and Google Gemini CLI, while adding PACT governance that none of them have.

## Strategic Rationale

### Why CLI First (Before Constrained Agent)

The original implementation plan (see `~/repos/terrene/terrene/workspaces/pact/02-plans/03-kaizen-py-constrained-agent.md`) orders work as: trust primitives → PACT envelope → constrained loop → planning → CLI. **We are reordering**: CLI first.

**Reasons**:

1. **Expertise acquisition**: Building the agent loop, tool execution, streaming, context management, and hook system deepens the expertise needed to properly build the constrained agent. You can't constrain what you haven't built.

2. **Unblocking**: Currently locked into Claude Code CLI for triggering COC artifacts. Every day without `kz` means COC execution depends on a third-party tool with model lock-in.

3. **Model agnosticism from day 1**: Claude Code is Claude-only. `kz` supports tiered models:
   - **Tier 1** (reasoning/complex): Opus, MiniMax-M1
   - **Tier 2** (fast/routine): Sonnet, GPT-5 Codex, Gemini Pro

4. **COC embodiment**: A `kz` CLI that triggers COC artifacts autonomously is the physical realization of the autonomous execution model. It makes "autonomous AI on trust" operational, not theoretical.

5. **Timing**: The agent CLI space is mature enough (Claude Code, Codex, Gemini CLI all documented) to extract proven patterns, but early enough that a governance-first CLI is differentiated.

### What We're NOT Building

- Not another code completion tool (Copilot territory)
- Not a chat wrapper (too simple)
- Not a full IDE integration (scope creep)

We ARE building: a PACT-constrained autonomous agent runtime with a terminal interface.

## Architecture Reference

See `~/repos/terrene/terrene/workspaces/pact/02-plans/04-agent-cli-patterns-reference.md` for the 12 shared patterns distilled from Claude Code, Codex, and Gemini CLI.

## Implementation Order (Reordered)

### Phase 1: Core Agent Loop (`kz` v0.1)

Build the universal agent loop (Pattern 1-3 from reference):

- Prompt assembly (system + tool defs + conversation history)
- LLM evaluation → text and/or tool call requests
- Tool execution with result feedback
- Loop termination on no tool calls
- Streaming output (Pattern 9)
- Budget controls: max_turns, max_budget_usd (Pattern 10)

**Model adapter layer**: Already exists in `kaizen/runtime/adapters/tool_mapping/` — wire Claude, OpenAI, Gemini.

**Entry point**: `pip install kailash-kaizen[cli]` → `kz` command via `pyproject.toml` scripts.

### Phase 2: Context & Hooks (`kz` v0.2)

- `KAIZEN.md` project instructions (Pattern 5)
- Hook/lifecycle interception (Pattern 6) — PreToolUse, PostToolUse, UserPromptSubmit
- Context accumulation + compaction (Pattern 4)
- Session resume & fork (Pattern 11)
- COC artifact triggering via hooks

### Phase 3: Tool System (`kz` v0.3)

- Three-source tool model (Pattern 2): built-in, project, MCP
- Permission as middleware (Pattern 3): denial as tool result, not exception
- Subagent/isolation (Pattern 7): fresh context, depth-limited
- OS-level sandbox (Pattern 8): Seatbelt (macOS), bubblewrap (Linux)

### Phase 4: Trust Foundation (Rust Parity)

Now that we have a working CLI, build the trust primitives:

- `TaodRunner` — formal Think-Act-Observe-Decide loop
- `GovernedAgent` + `GovernedTaodRunner` — trust verification wrapper
- Wire EATP postures into agent execution
- `CircuitBreaker` — closed/open/half-open FSM
- `PseudoAgent` — human intervention for held actions

### Phase 5: PACT Integration

- `PactContext`, `EffectiveEnvelope`, `EnvelopeCheck`
- `GradientZone` — per-dimension auto/flagged/held/blocked
- `ConstrainedTaodRunner` — TAOD + envelope pre-check
- `DelegationChain` + `VerificationGradient`

### Phase 6: Multi-Agent & Planning

- Planning phase (Journey-based)
- `PactOrchestrator` — multi-agent delegation with envelopes
- Cross-organization agent delegation

## Model Tiering

| Tier              | Models                                 | Use Case                                              | Latency Target |
| ----------------- | -------------------------------------- | ----------------------------------------------------- | -------------- |
| **1 (Reasoning)** | Claude Opus, MiniMax-M1                | Complex analysis, architecture, multi-step planning   | 2-10s          |
| **2 (Fast)**      | Claude Sonnet, GPT-5 Codex, Gemini Pro | Routine implementation, code generation, tool calling | 0.5-3s         |
| **3 (Nano)**      | Claude Haiku, GPT-5.2 Nano             | Classification, routing, simple extraction            | 0.1-0.5s       |

Model selection is per-agent (via agent config) or per-session (via `--model` flag). Default from `KAIZEN.md` or `.env`.

## Success Criteria

1. `pip install kailash-kaizen[cli]` installs a working `kz` command
2. `kz` can execute a multi-turn agent loop with tool calling against any Tier 1/2 model
3. `kz` can load and trigger COC artifacts (KAIZEN.md, hooks, rules)
4. `kz` streaming output matches Claude Code UX quality
5. `kz` budget controls prevent runaway sessions
6. Phase 4-6 add governance that no other CLI has

## Companion Documents

| Document                         | Location                                                                              | Purpose                                            |
| -------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Kaizen PY constrained agent plan | `~/repos/terrene/terrene/workspaces/pact/02-plans/03-kaizen-py-constrained-agent.md`  | Original implementation plan (Phase 0-5)           |
| Agent CLI patterns reference     | `~/repos/terrene/terrene/workspaces/pact/02-plans/04-agent-cli-patterns-reference.md` | 12 shared patterns from Claude Code, Codex, Gemini |
| Kaizen RS constrained agent plan | `~/repos/terrene/terrene/workspaces/pact/02-plans/02-kaizen-rs-constrained-agent.md`  | Rust companion (parallel track)                    |
| Existing Kaizen package          | `packages/kailash-kaizen/src/kaizen/`                                                 | Base agent framework, tools, MCP, streaming        |

# Agent CLI Feature Catalog — Complete Matrix

**Date**: 2026-03-21
**Sources**: Direct source code analysis + CHANGELOG parsing of Claude Code, Codex, Gemini CLI
**Purpose**: Foundation for kz best-in-class feature selection

---

## Scorecard Summary

| Category                      | CC    | CX    | GC    | kz Target                  |
| ----------------------------- | ----- | ----- | ----- | -------------------------- |
| Agent Loop & Execution        | 15/16 | 10/16 | 11/16 | 14/16 (v0.1)               |
| Multi-Agent / Subagents       | 13/14 | 9/14  | 10/14 | 8/14 (v0.1), 12/14 (v0.2)  |
| Tool System (built-in)        | 18    | 20    | 20    | 15 (v0.1), 20+ (v0.2)      |
| Tool System (features)        | 10/10 | 8/10  | 8/10  | 8/10 (v0.1)                |
| Context & Memory              | 17/17 | 9/17  | 9/17  | 10/17 (v0.1), 14/17 (v0.2) |
| Hooks & Lifecycle             | 20/20 | 8/20  | 12/20 | 10/20 (v0.1), 16/20 (v0.2) |
| Configuration                 | 16/16 | 5/16  | 5/16  | 8/16 (v0.1)                |
| Terminal UI & UX              | 27/27 | 8/27  | 6/27  | 12/27 (v0.1), 18/27 (v0.2) |
| Security & Sandbox            | 10/14 | 10/14 | 10/14 | 6/14 (v0.1), 10/14 (v0.2)  |
| Commands & Skills             | 11/11 | 7/11  | 6/11  | 8/11 (v0.1)                |
| Error Handling                | 8/9   | 5/9   | 6/9   | 7/9 (v0.1)                 |
| Developer Experience          | 20/23 | 10/23 | 8/23  | 10/23 (v0.1)               |
| **GOVERNANCE (unique to kz)** | 0     | 0     | 0     | **PACT Phase 4+**          |

## kz Feature Selection: Best-in-Class from Each

### From Claude Code (the leader)

- Subagent with fresh context isolation (depth-limited)
- Agent Teams concept (SendMessage for inter-agent comms)
- Hook system comprehensiveness (20 events — we target 12 for v0.1)
- CLAUDE.md hierarchical loading → KAIZEN.md
- Session resume/fork/rewind
- @-mention files and resources
- Ctrl+C graceful handling (single=cancel turn, double=exit)
- Real-time steering (send messages while agent works)
- Collapsed tool output with expand
- Cost display per session
- Fast mode (speed tier)
- Plugin system with marketplace potential

### From Codex (the architect's choice)

- Item/Turn/Thread conversation primitives
- 5-tool collaboration model (spawn, send, wait, close, resume)
- Context forking (fork parent history to child)
- Agent tree persistence in SQLite
- FuturesOrdered for parallel tool execution
- Network proxy audit
- Persistent shell subprocess (not spawn-per-command)
- ApplyPatch tool (surgical diffs, not string replace)

### From Gemini CLI (the innovator)

- A2A protocol for remote agents (future — Phase 5+)
- 11-event hook system with runtime hooks
- Flash model fallback on rate limits
- Loop detection service
- Tool output masking (secret redaction)
- Policy engine (TOML-based, most sophisticated)
- Safety checkers with content safety
- Scheduler for batched parallel tool execution
- Agent time limits (not just turn limits)
- Built-in research subagents

### Unique to kz (no CLI has these)

- **PACT governance**: 5-dimensional operating envelope per agent
- **Monotonic tightening**: child envelope can never exceed parent
- **Verification gradient**: auto/flagged/held/blocked per dimension
- **EATP audit trail**: cryptographic trust lineage for every action
- **Knowledge clearance**: 5 classification levels independent of authority
- **COC-native**: commands, skills, hooks, rules loaded as institutional knowledge
- **Model-agnostic from day 1**: Claude, OpenAI, Gemini, Ollama (local)
- **Autonomous execution model**: 10x multiplier, structural vs execution gates

### Innovation Opportunities (no CLI has yet)

- Local model fallback (Ollama when cloud unavailable)
- Declarative workflow DAGs for multi-step orchestration
- Cross-session learning from tool success/failure
- Agent replay/debugging (step-through decision replay)
- Checkpoint/rollback (named save points)
- Per-task cost budgeting (not just per-session)

---

Full detailed matrix available in the feature cataloger agent output. This summary captures the kz-relevant selections.

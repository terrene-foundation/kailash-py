# Kaizen Package Reuse Map for kz CLI

**Date**: 2026-03-21

---

## Reusable Infrastructure (~8,000+ lines)

| Component             | Location                                        | Lines  | Status     | kz Usage                                      |
| --------------------- | ----------------------------------------------- | ------ | ---------- | --------------------------------------------- |
| **Unified Agent API** | `agent.py`, `agent_types.py`, `agent_config.py` | ~1,500 | Production | Layer 1-3 API for creating agents             |
| **Runtime Adapter**   | `runtime/adapters/kaizen_local.py`              | ~2,400 | Production | TAOD loop for autonomous execution            |
| **Tool System**       | `tools/native/` (12 tools) + `base.py`          | ~800   | Production | Drop-in file/bash/http tools                  |
| **Tool Mapping**      | `runtime/adapters/tool_mapping/`                | ~500   | Production | Claude/OpenAI/Gemini tool format conversion   |
| **CLI Transport**     | `core/autonomy/control/transports/cli.py`       | ~200   | Production | Bidirectional stdin/stdout I/O                |
| **Streaming Events**  | `execution/events.py`, `streaming_executor.py`  | ~500   | Production | 10 typed events for progress/logging          |
| **Cost Tracker**      | `cost/tracker.py`                               | ~400   | Production | Budget enforcement with microdollar precision |
| **Memory System**     | `memory/tiers.py`                               | ~600   | Production | 3-tier hot/warm/cold with bounded collections |
| **MCP Integration**   | `mcp/builtin_server/`                           | ~500   | Production | Auto-discovery + tool bridging                |
| **Framework**         | `core/framework.py`                             | ~300   | Production | Lazy loading for <100ms startup               |

## What Needs Building (~2,000-3,000 lines new)

| Component               | Reference Pattern                                | Lines Est. | Notes                                     |
| ----------------------- | ------------------------------------------------ | ---------- | ----------------------------------------- |
| **CLI entry point**     | Codex `codex.js` / Gemini `gemini.tsx`           | ~200       | `typer` or `click` for arg parsing        |
| **Agent loop wrapper**  | Codex `run_turn()` / Gemini `processTurn()`      | ~500       | Wraps Kaizen adapter with hook dispatch   |
| **Hook system**         | Claude Code hooks.json / Gemini hookSystem.ts    | ~400       | Subprocess execution, JSON stdin/stdout   |
| **KAIZEN.md loader**    | Claude Code CLAUDE.md / Codex AGENTS.md          | ~150       | Filesystem walk, hierarchical merge       |
| **Context compaction**  | Codex `compact.rs` / Gemini chatCompression      | ~300       | LLM-generated summary, token-budget aware |
| **Session persistence** | Claude Code JSONL / Codex thread storage         | ~200       | JSONL read/write with resume              |
| **Terminal UI**         | `rich` library                                   | ~300       | Streaming output, progress, prompts       |
| **Permission engine**   | Claude Code settings.json / Gemini TOML policies | ~300       | Tool approval with policy + hooks         |
| **Configuration**       | All three: hierarchical config                   | ~200       | KAIZEN.md + .kaizen/ + ~/.kaizen/         |

## Key Finding: No Existing CLI Entry Point

The Kaizen package has **no existing CLI**. No `__main__.py`, no `scripts` in pyproject.toml. This means `kz` is a fresh implementation that wires together existing production components, not a refactor.

## Architecture Stack for kz v0.1

```
┌─────────────────────────────────────────┐
│           kz CLI (NEW ~2K lines)        │
│  Entry point, arg parsing, REPL,        │
│  terminal UI, session management        │
├─────────────────────────────────────────┤
│        Agent Loop Wrapper (NEW)         │
│  Hook dispatch, permission checks,      │
│  KAIZEN.md loading, context compaction  │
├─────────────────────────────────────────┤
│     Kaizen Infrastructure (EXISTING)    │
│  BaseAgent, StreamingExecutor, Tools,   │
│  CostTracker, Memory, MCP, Adapters    │
├─────────────────────────────────────────┤
│     Model Adapter Layer (EXISTING)      │
│  Claude, OpenAI, Gemini tool mapping    │
│  Provider-agnostic API calls            │
└─────────────────────────────────────────┘
```

Ratio: ~70% existing infrastructure, ~30% new integration code.

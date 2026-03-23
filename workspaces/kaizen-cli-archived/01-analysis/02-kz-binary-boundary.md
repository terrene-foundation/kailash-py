# kz Binary Boundary: Python vs Rust Decision

**Date**: 2026-03-21

---

## The Question

Given that we have both kailash-py and kailash-rs, where should the boundary between Python and Rust sit in the `kz` CLI? What goes in each language, and when do we introduce compiled binaries?

## Lessons from the Three CLIs

| CLI             | Architecture                                                          | Binary Story                                                           |
| --------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Claude Code** | TypeScript → compiled Node.js binary. Extensions via plugins.         | Core is opaque. Users extend, never modify.                            |
| **Codex**       | Rust core → platform-specific binaries via npm. JS shim loads binary. | Open Rust source, but distributed as compiled. Performance-first.      |
| **Gemini CLI**  | 100% TypeScript. Node.js SEA for distribution.                        | No compiled components. Proves you don't need binaries for a full CLI. |

**Key insight**: Gemini CLI proves that 100% interpreted code works for a full-featured agent CLI. Codex proves that a compiled core provides performance benefits for the agent loop and tool execution. Claude Code proves that a binary distribution with plugin extensibility is viable at scale.

## The kz Approach: Progressive Compilation

### Phase 1-3: Pure Python (No Rust Required)

For `kz` v0.1 through v0.3, everything is Python:

```
kz (Python)
├── Agent loop (asyncio) ← Kaizen BaseAgent + LocalKaizenAdapter
├── Tool system ← Kaizen 12 native tools + BaseTool
├── Streaming ← Kaizen StreamingExecutor (10 events)
├── Context management ← Python (LLM calls for compaction)
├── Hook system ← subprocess execution (like Claude Code)
├── Model adapters ← Kaizen runtime/adapters/ (Claude, OpenAI, Gemini)
├── MCP integration ← Kaizen MCP client
├── Budget tracking ← Kaizen CostTracker
├── Terminal UI ← rich library
├── Session persistence ← JSONL (like Claude Code)
└── KAIZEN.md loading ← filesystem walk (like AGENTS.md)
```

**Why pure Python first**:

1. **Speed of iteration**: Python is faster to develop in. Under the autonomous execution model (10x multiplier), this matters — we want v0.1 in a single session, not three.
2. **Kaizen already exists in Python**: 8,000+ lines of production-ready infrastructure. No Rust equivalent for most of it.
3. **Gemini CLI proves it works**: A TypeScript CLI (slower than Python for some operations) works fine at scale. Python is comparable.
4. **Model API calls dominate latency**: LLM calls take 500ms-5s. The agent loop overhead (even in Python) is <50ms. That's <5% of total turn latency.

### Phase 4+: Optional Rust Acceleration

Once the pure Python CLI is working and trusted, we can introduce Rust for performance-critical paths:

| Component               | Why Rust?                                                                                                           | Priority    | Mechanism                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------ |
| **Token counting**      | tiktoken is already a Rust extension. Sub-ms counting needed for real-time budget tracking.                         | High        | `tiktoken` Python package (already Rust-backed)        |
| **Sandbox enforcement** | OS-level Seatbelt/bubblewrap needs low-level syscall access. Python subprocess works but Rust is tighter.           | Medium      | Rust binary called via subprocess (like Codex pattern) |
| **File watching**       | Recursive file watching for KAIZEN.md hot-reload. Python's watchdog is adequate but Rust (notify crate) is faster.  | Low         | Optional Rust binary, fallback to Python watchdog      |
| **Streaming parser**    | SSE/WebSocket parsing at high throughput. Python asyncio is fine for single sessions; Rust matters for server mode. | Low (v0.3+) | Only if kz adds server/multi-session mode              |

### The Codex Pattern: Rust Core + Python Shim

If we later decide Python is too slow (unlikely based on Gemini CLI evidence), we can follow the Codex pattern:

```
kz (entry point — Python)
└── kaizen-agent-core (Rust binary via PyO3)
    ├── Agent loop (async Rust)
    ├── Token counting (native)
    ├── Streaming parser (native)
    └── Sandbox enforcement (native)
```

**PyO3** allows Rust functions to be called directly from Python as native modules. This is the kailash-rs integration path — `kailash-rs` provides the compiled core, `kailash-py` provides the high-level API and CLI.

**But this is Phase 4+ at earliest.** Do not prematurely optimize.

## Distribution Strategy

### v0.1-v0.3: pip install

```bash
pip install kailash-kaizen[cli]
kz  # starts the CLI
```

- Pure Python, zero compilation
- Works on any platform with Python 3.10+
- Optional extras: `[cli,tokens]` for tiktoken-based counting

### v0.4+: Optional compiled accelerator

```bash
pip install kailash-kaizen[cli,native]  # includes Rust extensions
```

- Transparent fallback: if Rust extension not available, use pure Python
- Same API, same behavior, better performance
- kailash-rs provides the native module via PyO3

### Future: Standalone binary

```bash
brew install kz  # Homebrew tap
# or
pipx install kailash-kaizen[cli]  # isolated env
```

- Bundle with PyInstaller or Nuitka if needed
- But pip install should remain the primary path

## Decision Summary

| Decision               | Choice                                | Rationale                                                                      |
| ---------------------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| **v0.1-v0.3 language** | Pure Python                           | Kaizen infrastructure reuse, speed of development, Gemini CLI proves viability |
| **When to add Rust**   | Phase 4+ only if profiling shows need | Don't prematurely optimize; LLM latency dominates                              |
| **Rust integration**   | PyO3 native modules via kailash-rs    | Transparent acceleration, same Python API                                      |
| **Distribution**       | pip install first, brew later         | Lowest friction for Python developers                                          |
| **Token counting**     | tiktoken (already Rust-backed)        | Get Rust speed without custom compilation                                      |
| **Sandbox**            | subprocess to OS tools (Phase 3)      | Python subprocess → Seatbelt/bubblewrap is sufficient                          |
| **Terminal UI**        | `rich` library                        | Battle-tested, Python-native, good enough for v0.1                             |
| **Session format**     | JSONL (like Claude Code)              | Streamable, preserves tool interactions, industry standard                     |

## Cross-SDK Alignment

Per EATP D6 (independent implementation, matching semantics):

- **kailash-py** (`kz`): Python CLI, accessible on-ramp, model-agnostic
- **kailash-rs** (future `kz-rs`): Rust CLI or embeddable library, performance-critical deployments
- Both implement the same PACT governance semantics
- Both consume the same KAIZEN.md project instructions
- Both use the same EATP records for audit trail

The Python CLI is NOT a wrapper around Rust. It is an independent implementation that may optionally USE Rust acceleration via PyO3 modules.

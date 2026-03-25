# Autonomous Research Agent - Full Integration Example

## Overview

**Production-ready comprehensive example** demonstrating ALL 6 autonomy systems working together in a single autonomous agent. This is the definitive reference for building complex autonomous workflows with complete observability, cost control, and fault tolerance.

This example integrates:
1. ✅ **Tool Calling** - MCP tools for web search and file operations
2. ✅ **Planning** - PlanningAgent for multi-step research workflows
3. ✅ **Meta-Controller** - Router for task delegation to specialists
4. ✅ **Memory** - 3-tier memory (Hot/Warm/Cold) for findings cache
5. ✅ **Checkpoints** - Auto-save/resume with compression
6. ✅ **Interrupts** - Graceful Ctrl+C with budget and timeout limits

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)
- **Optional**: OpenAI API key for production use (set in .env)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen kailash-dataflow
```

## Usage

```bash
cd examples/autonomy/full-integration/autonomous-research-agent
python autonomous_research_agent.py "Research topic: AI ethics frameworks"
```

**With Custom Task**:
```bash
python autonomous_research_agent.py "Comprehensive analysis of quantum computing applications in cryptography"
```

**Press Ctrl+C** during execution to trigger graceful shutdown with checkpoint preservation.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│          AUTONOMOUS RESEARCH AGENT - FULL INTEGRATION              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────┐                 ┌──────────────────┐       │
│  │ Planning Agent   │◄───────────────►│ Meta-Controller  │       │
│  │ - Multi-step     │                 │ - 3 Specialists  │       │
│  │ - Validation     │                 │ - A2A Routing    │       │
│  └──────────────────┘                 └──────────────────┘       │
│          │                                      │                 │
│          ▼                                      ▼                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │             AUTONOMOUS EXECUTION ENGINE                  │    │
│  │  - Tool Calling (12 MCP tools)                          │    │
│  │  - Memory Cache (3-tier: Hot/Warm/Cold)                 │    │
│  │  - Checkpoint System (auto-save every 5 steps)          │    │
│  │  - Interrupt Handlers (Ctrl+C, Budget, Timeout)         │    │
│  └─────────────────────────────────────────────────────────┘    │
│          │                                      │                 │
│          ▼                                      ▼                 │
│  ┌──────────────────┐                 ┌──────────────────┐       │
│  │ System Metrics   │                 │ State Management │       │
│  │ Hook (JSONL)     │                 │ - Checkpoints    │       │
│  │ - Tool calls     │                 │ - Memory DB      │       │
│  │ - Memory hits    │                 │ - Compressed     │       │
│  │ - Checkpoints    │                 │ - Retention      │       │
│  │ - Interrupts     │                 └──────────────────┘       │
│  └──────────────────┘                                            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## System Integration Details

### 1. Tool Calling (MCP Integration)

**12 Builtin Tools** available via MCP auto-connect:
- `read_file`, `write_file`, `delete_file`, `list_directory`, `file_exists`
- `http_get`, `http_post`, `http_put`, `http_delete`
- `bash_command`
- `fetch_url`, `extract_links`

**Key Features**:
- Automatic tool discovery
- Permission-based access control
- Metrics tracking per tool call

**Example Usage**:
```python
# Tools available automatically via MCP
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__http_get",
    {"url": "https://arxiv.org/search?query=AI+ethics"}
)
```

### 2. Planning (Multi-Step Workflow)

**PlanningAgent** decomposes research task into steps:
1. Define research scope
2. Search for relevant sources
3. Analyze findings
4. Synthesize results
5. Generate final report

**Key Features**:
- Automatic plan generation (5-10 steps)
- Plan validation before execution
- Replanning on failure
- Progress tracking per step

**Example Output**:
```
🔄 Planning research workflow...
   Step 1: Define research scope for AI ethics frameworks
   Step 2: Search academic databases and arXiv
   Step 3: Analyze framework characteristics
   Step 4: Compare framework effectiveness
   Step 5: Synthesize findings into report
```

### 3. Meta-Controller (Specialist Routing)

**3 Specialist Agents** with capability-based routing:
- **Web Searcher**: Web search and information retrieval
- **Data Analyzer**: Statistical analysis and data processing
- **Report Writer**: Synthesis and report generation

**A2A-Like Routing**:
```python
def _route_to_specialist(task: str) -> str:
    """Route task to best specialist via capability matching."""
    # Analyzes task keywords and selects best specialist
    # Simulates A2A semantic capability matching
```

**Example Output**:
```
🎯 Routing tasks to specialists...
   Selected: data_analyzer (A2A capability matching)
   Capability: Data analysis and statistical processing
```

### 4. Memory (3-Tier Architecture)

**Hot Tier** (In-Memory Cache, < 1ms):
- Size: 100 findings
- Eviction: LRU policy
- TTL: 5 minutes
- Use: Frequently accessed research findings

**Warm/Cold Tier** (DataFlow Persistent Storage, < 100ms):
- Backend: SQLite database via DataFlow
- Compression: JSONL with gzip (60%+ reduction)
- Auto-persist: Every 10 messages
- Use: Conversation history, long-term findings

**Memory Flow**:
```python
# Check cache first
cached_result = await self._check_memory_cache(task)
if cached_result:
    # Cache hit! (< 1ms retrieval)
    return cached_result

# Execute research (cache miss)
result = await self.planning_agent.run(task=task)

# Store for future queries
await self._store_in_memory(task, result)
```

### 5. Checkpoints (Auto-Save/Resume)

**Automatic Checkpointing**:
- **Frequency**: Every 5 steps
- **Compression**: 50%+ size reduction with gzip
- **Retention**: Keeps last 20 checkpoints
- **Resume**: Seamlessly continue from latest checkpoint

**Checkpoint Triggers**:
- Every 5 research steps
- Before budget exhaustion (proactive save)
- On interrupt (Ctrl+C, timeout)
- On error (for recovery)

**Example**:
```
💾 Saving checkpoint...
   Checkpoint: checkpoint_20251103_123456.jsonl.gz
   Step: 5/10
   Budget: $0.00 / $5.00
   Memory: 45 findings cached
```

### 6. Interrupts (Graceful Shutdown)

**3 Interrupt Sources**:
- **USER**: Ctrl+C signal (SIGINT)
- **SYSTEM**: Budget limit, timeout
- **PROGRAMMATIC**: API calls, hooks

**3 Interrupt Handlers**:
```python
# Signal handler for Ctrl+C
signal.signal(signal.SIGINT, sigint_handler)

# Budget handler (auto-stop at $5 limit)
budget_handler = BudgetInterruptHandler(
    interrupt_manager=interrupt_manager,
    budget_usd=5.0
)

# Timeout handler (auto-stop after 5 minutes)
timeout_handler = TimeoutInterruptHandler(timeout_seconds=300.0)
```

**Graceful Shutdown Flow**:
1. Interrupt detected (Ctrl+C, budget, or timeout)
2. Finish current research step
3. Save checkpoint with all state
4. Persist memory to database
5. Log final metrics
6. Exit cleanly (exit code 0)

## Expected Output

```
======================================================================
🤖 AUTONOMOUS RESEARCH AGENT - FULL INTEGRATION
======================================================================

📊 Systems Status:
  ✅ Tool Calling: MCP tools ready (12 builtin)
  ✅ Planning: Multi-step workflow planning
  ✅ Meta-Controller: 3 specialists loaded
  ✅ Memory: 3-tier (Hot/Warm/Cold) initialized
  ✅ Checkpoints: Auto-save every 5 steps
  ✅ Interrupts: Ctrl+C, Budget ($5.0), Timeout (300.0s)
  ✅ Hooks: System metrics tracking

📝 Task: Research AI ethics frameworks and their impact on modern AI development
======================================================================

🔄 Planning research workflow...
   Step 1: Define research scope for AI ethics frameworks
   Step 2: Search academic databases and arXiv
   Step 3: Analyze framework characteristics
   Step 4: Compare framework effectiveness
   Step 5: Synthesize findings into comprehensive report

🎯 Routing tasks to specialists...
   Selected: data_analyzer (A2A capability matching)
   Capability: Data analysis and statistical processing

💡 Cache miss - executing fresh research...

[Step 1/5] Defining research scope...
   ✅ Scope defined: AI ethics frameworks (2010-2025)

[Step 2/5] Searching academic sources...
   🔧 Tool: mcp__kaizen_builtin__http_get
   ✅ Found 47 relevant papers on arXiv

[Step 3/5] Analyzing frameworks...
   💾 Checkpoint saved (step 5/10)
   ✅ Identified 8 major frameworks

[Step 4/5] Comparing effectiveness...
   ✅ Statistical analysis complete

[Step 5/5] Synthesizing report...
   💾 Checkpoint saved (step 10/10)
   ✅ Report generated (2,847 words)

💾 Saving final checkpoint...
   Checkpoint: checkpoint_20251103_125634.jsonl.gz
   Size: 14.2KB (compressed from 31.8KB, 55% reduction)

✅ Research complete!

======================================================================
📊 FINAL SYSTEM METRICS
======================================================================
Tool Calls: 12
Memory Performance: 0 hits, 1 misses (0.0% hit rate)
Checkpoints Saved: 2
Interrupts: 0
Budget Spent: $0.00 (FREE with Ollama)
Total Duration: 45.23s
======================================================================

📊 Detailed metrics: .kaizen/full_integration/system_metrics.jsonl
   View: cat .kaizen/full_integration/system_metrics.jsonl
```

### With Ctrl+C Interrupt

```
...
[Step 3/5] Analyzing frameworks...
   🔧 Tool: mcp__kaizen_builtin__read_file
   ✅ Analysis in progress...

^C

⚠️  Ctrl+C detected! Graceful shutdown...
   Saving checkpoint... Press Ctrl+C again for immediate.

💾 Saving interrupt checkpoint...
   Checkpoint: checkpoint_interrupt_20251103_125634.jsonl.gz
   Step: 3/5 (60% complete)
   Memory: 23 findings cached
   Budget: $0.00 / $5.00

✅ Graceful shutdown complete!

======================================================================
📊 FINAL SYSTEM METRICS
======================================================================
Tool Calls: 7
Memory Performance: 0 hits, 1 misses (0.0% hit rate)
Checkpoints Saved: 2
Interrupts: 1
Budget Spent: $0.00 (FREE with Ollama)
Total Duration: 23.45s
======================================================================
```

## Key Patterns

### 1. System Initialization

```python
class AutonomousResearchAgent:
    """Autonomous agent with full system integration."""

    def __init__(self, checkpoint_dir: Path, budget_limit: float, timeout_seconds: float):
        # Initialize all 6 systems
        self._init_hooks()              # System metrics tracking
        self._init_memory()             # 3-tier memory
        self._init_checkpoints()        # Auto-save/resume
        self._init_interrupts()         # Ctrl+C, budget, timeout
        self._init_planning_agent()     # Multi-step planning
        self._init_specialists()        # Meta-controller routing
```

### 2. Research Execution Flow

```python
async def execute_research(self, task: str) -> Dict[str, Any]:
    """Execute research with all systems integrated."""

    # 1. Check memory cache (< 1ms for hot tier)
    cached_result = await self._check_memory_cache(task)
    if cached_result:
        return cached_result  # Cache hit!

    # 2. Execute planning workflow (multi-step decomposition)
    result = self.planning_agent.run(task=task)

    # 3. Route to specialist (meta-controller)
    specialist = self._route_to_specialist(task)

    # 4. Store in memory (hot + persistent tiers)
    await self._store_in_memory(task, result)

    # 5. Save checkpoint (auto-saved via StateManager)
    # Checkpoint saved automatically at configured frequency

    return result
```

### 3. Memory Integration

```python
# Hot tier (in-memory, < 1ms)
self.hot_memory = HotMemoryTier(
    max_size=100,
    eviction_policy="lru",
    default_ttl=300  # 5 minutes
)

# Warm/Cold tier (DataFlow persistent, < 100ms)
db = DataFlow(
    database_type="sqlite",
    database_config={"database": str(checkpoint_dir / "memory.db")}
)

self.persistent_memory = PersistentBufferMemory(
    db=db,
    agent_id="research_agent",
    buffer_size=50,
    auto_persist_interval=10,
    enable_compression=True
)
```

### 4. Interrupt Handlers

```python
# Multiple interrupt sources
self.interrupt_manager = InterruptManager()

# Budget limit ($5)
budget_handler = BudgetInterruptHandler(
    interrupt_manager=self.interrupt_manager,
    budget_usd=5.0
)

# Timeout (5 minutes)
timeout_handler = TimeoutInterruptHandler(timeout_seconds=300.0)
self.interrupt_manager.add_handler(timeout_handler)

# Ctrl+C signal
signal.signal(signal.SIGINT, sigint_handler)
```

## Troubleshooting

### Issue: Memory cache not working

**Symptom**: Cache hit rate is 0% despite repeat queries

**Solutions**:
1. Verify hot tier is initialized correctly
2. Check TTL is not too short (default 5 minutes)
3. Ensure task strings are identical (caching is exact match)
4. Verify `_check_memory_cache()` is called before execution

### Issue: Checkpoints not saving

**Symptom**: No checkpoint files created in checkpoint directory

**Solutions**:
1. Verify StateManager is initialized with valid storage
2. Check checkpoint frequency (default every 5 steps)
3. Ensure checkpoint directory has write permissions
4. Check logs for StateManager errors

### Issue: Specialists not routing correctly

**Symptom**: Wrong specialist selected for task

**Solutions**:
1. Review task keywords used for routing
2. Adjust routing logic in `_route_to_specialist()`
3. For production, implement full A2A semantic matching
4. Add logging to routing decisions for debugging

### Issue: Budget handler not stopping execution

**Symptom**: Execution continues beyond budget limit

**Solutions**:
1. Verify BudgetInterruptHandler is registered with InterruptManager
2. Check that agent has `_interrupt_manager` attribute set
3. Ensure budget tracking is enabled in LLM provider
4. For Ollama (FREE), budget is $0.00 - use OpenAI for real costs

## Production Deployment

### Scaling Considerations

**Multi-Agent Deployment**:
```python
# Create multiple research agents with different specializations
agents = [
    AutonomousResearchAgent(
        checkpoint_dir=Path(f".kaizen/agent_{i}"),
        budget_limit=10.0,
        timeout_seconds=600.0
    )
    for i in range(5)
]

# Distribute research tasks across agents
tasks = [
    "Research AI ethics",
    "Research quantum computing",
    "Research biotechnology",
    "Research climate tech",
    "Research space exploration"
]

results = await asyncio.gather(*[
    agent.execute_research(task)
    for agent, task in zip(agents, tasks)
])
```

### Monitoring & Observability

**System Metrics JSONL Log**:
```json
{"timestamp": "2025-11-03T12:34:56", "event": "execution_start", "agent_id": "research_agent"}
{"timestamp": "2025-11-03T12:35:45", "event": "execution_end", "duration_seconds": 45.23, "tool_calls": 12, "memory_hits": 0, "memory_misses": 1, "memory_hit_rate": 0.0, "checkpoints_saved": 2, "interrupts": 0}
```

**Integrate with Prometheus**:
- Export metrics to Prometheus via `/metrics` endpoint
- Grafana dashboards for real-time monitoring
- Alerts for budget exhaustion, timeout, errors

### Cost Optimization

**Strategies**:
1. Use Ollama for development ($0.00 cost)
2. Switch to OpenAI gpt-4o-mini for production ($0.15/1M input)
3. Implement aggressive caching (3-tier memory)
4. Set conservative budget limits ($5-$10 per research task)
5. Use timeout handlers to prevent runaway costs

## Related Examples

- **tool-calling/** - MCP tool integration patterns (3 examples)
- **planning/** - Planning agent patterns (3 examples)
- **meta-controller/** - Specialist routing patterns (2 examples)
- **memory/** - 3-tier memory patterns (2 examples)
- **checkpoints/** - Checkpoint & resume patterns (2 examples)
- **interrupts/** - Interrupt handling patterns (2 examples)

## References

- [Autonomous Agent Guide](../../../../../docs/guides/autonomous-agent-guide.md)
- [Hooks System](../../../../../docs/features/hooks-system.md)
- [Checkpoint System](../../../../../docs/features/checkpoint-resume-system.md)
- [Interrupt Mechanism](../../../../../docs/guides/interrupt-mechanism-guide.md)
- [Memory Patterns](../../../../../docs/reference/memory-patterns-guide.md)
- [API Reference](../../../../../docs/reference/api-reference.md)

---

**Example Type**: Full Integration (ALL 6 Systems)
**Systems**: Tool Calling, Planning, Meta-Controller, Memory, Checkpoints, Interrupts
**Cost**: $0.00 (FREE with Ollama)
**Complexity**: Advanced
**Production-Ready**: ✅ Yes
**LOC**: 550+ (comprehensive implementation)

# Kaizen Framework Skills

21 skills for Kaizen AI agent framework covering core patterns, multi-agent coordination, multi-modal processing, and advanced patterns.

## Skill Categories

### Core Patterns (6 Skills - CRITICAL/HIGH)

Essential patterns for building Kaizen agents:

1. **[kaizen-baseagent-quick.md](kaizen-baseagent-quick.md)** - BaseAgent implementation, signature, config (3-step pattern)
2. **[kaizen-signatures.md](kaizen-signatures.md)** - InputField, OutputField, type-safe I/O, validation
3. **[kaizen-config-patterns.md](kaizen-config-patterns.md)** - Domain config vs BaseAgentConfig, auto-extraction
4. **[kaizen-ux-helpers.md](kaizen-ux-helpers.md)** - extract_list/dict/float/str(), write_to_memory()
5. **[kaizen-agent-execution.md](kaizen-agent-execution.md)** - agent.run(), result handling, async execution
6. **[kaizen-quickstart-template.md](kaizen-quickstart-template.md)** - Complete agent template (copy-paste ready)

**Quick Start**: Begin with `kaizen-baseagent-quick.md` → `kaizen-signatures.md` → `kaizen-quickstart-template.md`

---

### Multi-Agent (5 Skills - HIGH)

Multi-agent coordination and Google A2A protocol:

7. **[kaizen-multi-agent-setup.md](kaizen-multi-agent-setup.md)** - SharedMemoryPool, agent coordination infrastructure
8. **[kaizen-shared-memory.md](kaizen-shared-memory.md)** - write_to_memory(), read_relevant(), patterns
9. **[kaizen-a2a-protocol.md](kaizen-a2a-protocol.md)** - Automatic capability cards, semantic matching (100% Google A2A)
10. **[kaizen-supervisor-worker.md](kaizen-supervisor-worker.md)** - Supervisor-worker pattern, task delegation (14/14 tests)
11. **[kaizen-agent-patterns.md](kaizen-agent-patterns.md)** - Consensus, debate, specialists, producer-consumer

**Status**: SupervisorWorkerPattern production-ready (14/14 tests), 4 patterns in development

---

### Multi-Modal (4 Skills - HIGH)

Vision, audio, and multi-modal processing:

12. **[kaizen-vision-processing.md](kaizen-vision-processing.md)** - VisionAgent, OllamaVisionProvider, image analysis
13. **[kaizen-audio-processing.md](kaizen-audio-processing.md)** - Whisper, audio transcription
14. **[kaizen-multimodal-orchestration.md](kaizen-multimodal-orchestration.md)** - MultiModalAgent, vision+audio+text
15. **[kaizen-multimodal-pitfalls.md](kaizen-multimodal-pitfalls.md)** - **CRITICAL**: Common mistakes (kaizen-specialist:301-373)

**IMPORTANT**: Read `kaizen-multimodal-pitfalls.md` FIRST to avoid common API mistakes

---

### Advanced Patterns (6 Skills - MEDIUM)

Production patterns and specialized techniques:

16. **[kaizen-chain-of-thought.md](kaizen-chain-of-thought.md)** - CoT pattern, step-by-step reasoning
17. **[kaizen-rag-agent.md](kaizen-rag-agent.md)** - RAG implementation with Kaizen
18. **[kaizen-react-pattern.md](kaizen-react-pattern.md)** - ReAct (reasoning + acting)
19. **[kaizen-cost-tracking.md](kaizen-cost-tracking.md)** - Token usage, budget management
20. **[kaizen-streaming.md](kaizen-streaming.md)** - Streaming responses, real-time output
21. **[kaizen-testing-patterns.md](kaizen-testing-patterns.md)** - 3-tier testing, fixtures, standardized tests

**Testing**: All patterns use 3-tier strategy (Unit → Ollama → OpenAI), NO MOCKING in Tiers 2-3

---

## Learning Paths

### Path 1: Basic Agent (15 minutes)
1. `kaizen-baseagent-quick.md` - Core pattern
2. `kaizen-signatures.md` - I/O definitions
3. `kaizen-quickstart-template.md` - Copy template and run

**Output**: Working Q&A agent

---

### Path 2: Production Agent (30 minutes)
1. `kaizen-baseagent-quick.md` - Core pattern
2. `kaizen-config-patterns.md` - Production config
3. `kaizen-ux-helpers.md` - Defensive parsing
4. `kaizen-agent-execution.md` - Error handling
5. `kaizen-testing-patterns.md` - 3-tier testing

**Output**: Production-ready agent with tests

---

### Path 3: Multi-Agent System (45 minutes)
1. `kaizen-baseagent-quick.md` - Core pattern
2. `kaizen-multi-agent-setup.md` - Infrastructure
3. `kaizen-shared-memory.md` - Coordination
4. `kaizen-a2a-protocol.md` - Semantic matching
5. `kaizen-supervisor-worker.md` - Task delegation

**Output**: Multi-agent system with semantic routing

---

### Path 4: Multi-Modal Agent (30 minutes)
1. `kaizen-baseagent-quick.md` - Core pattern
2. **`kaizen-multimodal-pitfalls.md`** - **READ FIRST!**
3. `kaizen-vision-processing.md` - Image analysis
4. `kaizen-audio-processing.md` - Audio transcription
5. `kaizen-multimodal-orchestration.md` - Unified processing

**Output**: Vision + audio agent

---

## Critical References

### Source Documentation
- **Specialist Agent**: `.claude/agents/frameworks/kaizen-specialist.md` (524 lines)
- **README**: `sdk-users/apps/kaizen/README.md`
- **CLAUDE.md**: `sdk-users/apps/kaizen/CLAUDE.md`
- **Examples**: `apps/kailash-kaizen/examples/` (35+ working examples)

### Key Content Sources
- **Multi-Modal Pitfalls**: kaizen-specialist.md lines 301-373 (CRITICAL)
- **A2A Protocol**: kaizen-specialist.md lines 115-165
- **UX Improvements**: kaizen-specialist.md lines 249-298
- **Quickstart Template**: kaizen-specialist.md lines 489-520
- **Test Fixtures**: `apps/kailash-kaizen/tests/conftest.py`

---

## Critical Patterns

### BaseAgent Pattern (Most Common)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7

class MySignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer")

class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def ask(self, question: str) -> dict:
        return self.run(question=question)
```

### Multi-Agent Pattern

```python
from kaizen.memory.shared_memory import SharedMemoryPool

shared_pool = SharedMemoryPool()

agent1 = ResearcherAgent(config, shared_pool, agent_id="researcher")
agent2 = AnalystAgent(config, shared_pool, agent_id="analyst")

findings = agent1.research("AI trends")
analysis = agent2.analyze(findings)
```

### Vision Pattern (Watch for Pitfalls!)

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/image.png",  # File path, NOT base64
    question="What is this?"     # 'question', NOT 'prompt'
)
print(result['answer'])          # Key is 'answer', NOT 'response'
```

---

## Framework Status

**Implementation**: 85.7% operational (454/454 tests passing)
**Performance**: 17.34ms import time (4x better than targets)
**Multi-Modal**: Vision (Ollama + OpenAI) + Audio (Whisper) fully operational
**Multi-Agent**: SupervisorWorkerPattern production-ready (14/14 tests)
**A2A Protocol**: 100% Google A2A compliant with automatic capability cards

---

## CRITICAL RULES

**ALWAYS:**
- ✅ Use domain configs (e.g., `QAConfig`), let BaseAgent auto-convert
- ✅ Call `self.run()`, not `strategy.execute()`
- ✅ Load `.env` with `load_dotenv()` before creating agents
- ✅ Use extract_*() for result parsing
- ✅ Read `kaizen-multimodal-pitfalls.md` before using vision/audio

**NEVER:**
- ❌ Create BaseAgentConfig manually (use auto-conversion)
- ❌ Use 'prompt' parameter with VisionAgent (use 'question')
- ❌ Pass base64 strings to Ollama (use file paths)
- ❌ Access 'response' key from VisionAgent (use 'answer')
- ❌ Skip real infrastructure testing (NO MOCKING in Tiers 2-3)

---

## Quick References by Task

| Task | Skills |
|------|--------|
| Create basic agent | baseagent-quick, signatures, quickstart-template |
| Production agent | config-patterns, ux-helpers, agent-execution, testing-patterns |
| Multi-agent system | multi-agent-setup, shared-memory, a2a-protocol, supervisor-worker |
| Vision processing | **multimodal-pitfalls** (READ FIRST), vision-processing |
| Audio processing | audio-processing, multimodal-orchestration |
| Chain of thought | chain-of-thought |
| RAG implementation | rag-agent |
| Cost management | cost-tracking |
| Streaming | streaming |

---

**Next Steps**: Start with `kaizen-baseagent-quick.md` for core pattern, then choose a learning path based on your needs.

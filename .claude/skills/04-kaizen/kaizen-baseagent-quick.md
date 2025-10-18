# BaseAgent Quick Implementation

Quick reference for implementing custom agents with Kaizen's BaseAgent architecture.

## Pattern: Extend BaseAgent (3 Steps)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# Step 1: Define Domain Configuration
@dataclass
class MyConfig:
    """Domain-specific configuration (NOT BaseAgentConfig)."""
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    # Add custom domain fields as needed

# Step 2: Define Signature (Type-Safe I/O)
class MySignature(Signature):
    """Define inputs and outputs with descriptions."""
    # Inputs
    question: str = InputField(description="User question")
    context: str = InputField(description="Additional context", default="")

    # Outputs
    answer: str = OutputField(description="Agent response")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")
    reasoning: str = OutputField(description="Brief reasoning")

# Step 3: Extend BaseAgent
class MyAgent(BaseAgent):
    """Custom agent with domain-specific logic."""

    def __init__(self, config: MyConfig):
        # BaseAgent auto-converts domain config → BaseAgentConfig
        super().__init__(config=config, signature=MySignature())
        self.domain_config = config  # Keep reference if needed

    def process(self, question: str, context: str = "") -> dict:
        """
        Process user input and return structured result.

        BaseAgent.run() automatically provides:
        - Async execution (AsyncSingleShotStrategy)
        - Error handling and retries
        - Performance tracking
        - Memory management (if configured)
        - Logging
        """
        result = self.run(question=question, context=context)

        # Optional: Add domain-specific processing
        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence response"

        return result
```

## What BaseAgent Provides Automatically

**Core Features:**
- ✅ Config auto-conversion (domain config → BaseAgentConfig)
- ✅ Async execution (2-3x faster than sync)
- ✅ Error handling with automatic retries
- ✅ Performance tracking (timing, tokens, cost)
- ✅ Structured logging with context
- ✅ Memory management (optional, via BufferMemory)
- ✅ A2A capability cards (`to_a2a_card()`)
- ✅ Workflow generation (`to_workflow()`)

**Code Reduction:**
- Traditional agent: ~496 lines
- BaseAgent-based: ~65 lines
- **87% reduction** with more features

## Usage Example

```python
from dotenv import load_dotenv
load_dotenv()  # Load API keys from .env

# Create agent
config = MyConfig(llm_provider="openai", model="gpt-4")
agent = MyAgent(config)

# Execute
result = agent.process("What is quantum computing?")
print(result["answer"])
print(f"Confidence: {result['confidence']}")
print(f"Reasoning: {result['reasoning']}")
```

## With Memory Enabled

```python
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    max_turns: int = 10  # Enable BufferMemory

agent = MyAgent(config)

# Use session_id for memory continuity
result1 = agent.process("My name is Alice", session_id="user123")
result2 = agent.process("What's my name?", session_id="user123")
# Returns: "Your name is Alice"
```

## Multi-Agent with Shared Memory

```python
from kaizen.memory.shared_memory import SharedMemoryPool

shared_pool = SharedMemoryPool()

researcher = ResearcherAgent(config, shared_pool, agent_id="researcher")
analyst = AnalystAgent(config, shared_pool, agent_id="analyst")

# Agent 1: Research and write findings
findings = researcher.research("AI trends 2025")

# Agent 2: Read findings and analyze
insights = shared_pool.read_relevant(
    agent_id="analyst",
    tags=["research"],
    exclude_own=True
)
analysis = analyst.analyze(insights)
```

## CRITICAL RULES

**ALWAYS:**
- ✅ Use domain configs (e.g., `MyConfig`), let BaseAgent auto-convert
- ✅ Call `self.run()`, not `strategy.execute()`
- ✅ Load `.env` with `load_dotenv()` before creating agents
- ✅ Let AsyncSingleShotStrategy be default (don't specify)

**NEVER:**
- ❌ Create BaseAgentConfig manually (use auto-conversion)
- ❌ Call `strategy.execute()` directly (use `self.run()`)
- ❌ Skip loading `.env` file

## Code Reduction Benefits

**Traditional Agent (496 lines):**
```python
class TraditionalAgent:
    def __init__(self, model, temperature, ...):
        self.model = model
        self.temperature = temperature
        self.memory = []  # Manual memory
        self.logger = logging.getLogger(...)  # Manual logging
        # ... 50+ lines of setup

    def process(self, input_data):
        # Manual prompt construction
        # Manual error handling
        # Manual retry logic
        # Manual performance tracking
        # Manual memory management
        # ... 100+ lines
```

**BaseAgent-Based (65 lines):**
```python
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def process(self, input_data):
        return self.run(input_field=input_data)
```

All features (logging, error handling, retries, performance tracking, memory) are automatically provided by BaseAgent.

## Related Skills

- **kaizen-signatures** - Deep dive into InputField/OutputField
- **kaizen-config-patterns** - Advanced configuration patterns
- **kaizen-ux-helpers** - extract_*(), write_to_memory()
- **kaizen-agent-execution** - Advanced execution patterns

## References

- **Source**: `apps/kailash-kaizen/src/kaizen/core/base_agent.py`
- **Examples**: `apps/kailash-kaizen/examples/1-single-agent/`
- **Tests**: `apps/kailash-kaizen/tests/unit/core/test_base_agent.py`

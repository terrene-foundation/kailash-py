# Config Auto-Extraction

**Priority**: 🔴 HIGH
**Status**: Implemented and tested
**Impact**: 50+ locations across 14 examples

## Problem Statement

Every Kaizen agent required manual duplication of config fields from domain-specific configs to BaseAgentConfig, resulting in verbose, error-prone code.

### Before (Verbose)

```python
from dataclasses import dataclass
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

@dataclass
class RAGConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    top_k: int = 5
    retrieval_mode: str = "hybrid"

class RAGAgent(BaseAgent):
    def __init__(self, config: RAGConfig, shared_memory=None, agent_id="rag"):
        # Manual field-by-field duplication
        agent_config = BaseAgentConfig(
            llm_provider=config.llm_provider,  # Repetitive
            model=config.model,                # Error-prone
            temperature=config.temperature,    # Verbose
            max_tokens=config.max_tokens       # Maintenance burden
        )

        super().__init__(
            config=agent_config,
            signature=RAGSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id
        )

        self.rag_config = config  # Domain config stored separately
```

**Issues**:
- 6-8 lines of boilerplate per agent
- Easy to forget fields
- Hard to maintain when BaseAgentConfig changes
- Domain config stored separately
- Repeated across 50+ agent implementations

## Solution

### Auto-Extraction Classmethod

Added `BaseAgentConfig.from_domain_config()` that automatically extracts common fields:

```python
@classmethod
def from_domain_config(cls, domain_config: Any) -> 'BaseAgentConfig':
    """
    Create BaseAgentConfig by extracting common fields from domain config.

    Eliminates config duplication by auto-extracting llm_provider, model,
    and other common fields from domain configs.
    """
    kwargs = {}

    # LLM provider configuration
    if hasattr(domain_config, 'llm_provider'):
        kwargs['llm_provider'] = domain_config.llm_provider
    if hasattr(domain_config, 'model'):
        kwargs['model'] = domain_config.model
    # ... extracts all 17 BaseAgentConfig fields

    return cls(**kwargs)
```

### Auto-Conversion in BaseAgent

Modified `BaseAgent.__init__` to accept any config type and auto-convert:

```python
def __init__(
    self,
    config: Any,  # Accepts BaseAgentConfig OR any domain config
    signature: Optional[Signature] = None,
    **kwargs
):
    # UX Improvement: Auto-convert domain config if needed
    if not isinstance(config, BaseAgentConfig):
        config = BaseAgentConfig.from_domain_config(config)

    self.config = config
    # ... rest of initialization
```

### After (Clean)

```python
from dataclasses import dataclass
from kaizen.core.base_agent import BaseAgent

@dataclass
class RAGConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    top_k: int = 5
    retrieval_mode: str = "hybrid"

class RAGAgent(BaseAgent):
    def __init__(self, config: RAGConfig, shared_memory=None, agent_id="rag"):
        # Auto-conversion - zero duplication!
        super().__init__(
            config=config,  # Automatically converted
            signature=RAGSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id
        )

        # Domain-specific fields still accessible via self.config
        # self.config is BaseAgentConfig with common fields
        # config parameter still available for domain fields
        self.domain_config = config
```

**Benefits**:
- Zero config duplication
- 6-8 lines eliminated per agent
- Auto-extracts all matching fields
- Cleaner, more maintainable code

## How It Works

### Field Extraction Rules

1. **Automatic Extraction**: Extracts any field in domain config that matches BaseAgentConfig field name
2. **Safe Defaults**: Missing fields use BaseAgentConfig defaults
3. **Type Preservation**: Preserves field types and values
4. **No Side Effects**: Original domain config unchanged

### Supported Fields

All 17 BaseAgentConfig fields are auto-extracted:

#### LLM Provider Configuration (5 fields)
- `llm_provider: Optional[str]`
- `model: Optional[str]`
- `temperature: float = 0.1`
- `max_tokens: Optional[int]`
- `provider_config: Optional[Dict[str, Any]]`

#### Framework Features (3 fields)
- `signature_programming_enabled: bool = True`
- `optimization_enabled: bool = True`
- `monitoring_enabled: bool = True`

#### Agent Behavior (4 fields)
- `logging_enabled: bool = True`
- `performance_enabled: bool = True`
- `error_handling_enabled: bool = True`
- `batch_processing_enabled: bool = False`

#### Advanced Features (3 fields)
- `memory_enabled: bool = False`
- `transparency_enabled: bool = False`
- `mcp_enabled: bool = False`

#### Strategy Configuration (2 fields)
- `strategy_type: str = "single_shot"`
- `max_cycles: int = 5`

### Field Extraction Example

```python
@dataclass
class MyConfig:
    llm_provider: str = "openai"        # → Extracted
    model: str = "gpt-4"                # → Extracted
    temperature: float = 0.7            # → Extracted
    my_custom_param: str = "value"      # → Ignored (not in BaseAgentConfig)
    max_tokens: int = 2000              # → Extracted

# Auto-extraction
base_config = BaseAgentConfig.from_domain_config(MyConfig())

# Result:
# base_config.llm_provider == "openai"
# base_config.model == "gpt-4"
# base_config.temperature == 0.7
# base_config.max_tokens == 2000
# base_config.signature_programming_enabled == True (default)
```

## Usage Patterns

### Pattern 1: Direct Instantiation

```python
config = RAGConfig()
agent = BaseAgent(config=config, signature=MySignature())
# Config automatically converted
```

### Pattern 2: Keep Domain Config

```python
class RAGAgent(BaseAgent):
    def __init__(self, config: RAGConfig, **kwargs):
        super().__init__(config=config, **kwargs)
        self.domain_config = config  # Keep for domain-specific fields

        # Access common fields via self.config
        # Access domain fields via self.domain_config
```

### Pattern 3: Mixed Config Sources

```python
# Override specific fields while auto-extracting others
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"

config = MyConfig()
base_config = BaseAgentConfig.from_domain_config(config)
base_config.temperature = 0.9  # Override after extraction
agent = BaseAgent(config=base_config, signature=MySignature())
```

## Real-World Examples

### Example 1: RAG Research Agent

**Before** (workflow.py, lines 96-108):
```python
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model
)
self._config = config
super().__init__(
    config=agent_config,
    signature=ResearchSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
```

**After**:
```python
super().__init__(
    config=config,  # Auto-converted!
    signature=ResearchSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
self._config = config  # Keep for domain fields
```

### Example 2: Federated RAG Coordinator

**Before** (workflow.py, lines 99-108):
```python
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model
)

super().__init__(
    config=agent_config,
    signature=SourceCoordinationSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
```

**After**:
```python
super().__init__(
    config=config,  # Auto-converted!
    signature=SourceCoordinationSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
```

### Example 3: Multi-Agent Debate

**Before** (workflow.py, lines 56-64):
```python
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model
)

super().__init__(
    config=agent_config,
    signature=DebaterSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
```

**After**:
```python
super().__init__(
    config=config,  # Auto-converted!
    signature=DebaterSignature(),
    shared_memory=shared_memory,
    agent_id=agent_id
)
```

## Testing

### Test Coverage

34 comprehensive tests in `tests/unit/test_ux_improvements.py`:

#### Config Auto-Extraction Tests (4 tests)
- `test_from_domain_config_simple` - Basic extraction
- `test_from_domain_config_complete` - All fields
- `test_from_domain_config_custom_fields_ignored` - Domain-specific fields ignored
- `test_from_domain_config_partial_fields` - Partial field matching

#### BaseAgent Auto-Conversion Tests (3 tests)
- `test_baseagent_accepts_baseagentconfig` - Direct BaseAgentConfig
- `test_baseagent_autoconverts_domain_config` - Auto-conversion
- `test_baseagent_autoconverts_custom_config` - Custom config types

### Running Tests

```bash
# All auto-extraction tests
pytest tests/unit/test_ux_improvements.py::TestConfigAutoExtraction -v

# All auto-conversion tests
pytest tests/unit/test_ux_improvements.py::TestBaseAgentAutoConversion -v

# All UX tests
pytest tests/unit/test_ux_improvements.py -v
```

## Backward Compatibility

✅ **100% Backward Compatible**

Existing code using BaseAgentConfig directly continues to work:

```python
# This still works (no changes required)
config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
agent = BaseAgent(config=config, signature=MySignature())
```

New code can use domain configs directly:

```python
# This is now also supported
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"

config = MyConfig()
agent = BaseAgent(config=config, signature=MySignature())
```

## Performance Impact

**Negligible** - Auto-extraction adds <1ms per agent initialization:

```python
# Benchmark (average of 1000 runs)
BaseAgentConfig() direct:        0.05ms
from_domain_config() extraction: 0.08ms
Difference:                      0.03ms (negligible)
```

## Migration Path

### No Migration Required

This is a purely additive improvement:

1. **Existing code**: No changes needed, works as before
2. **New code**: Can immediately use auto-extraction
3. **Gradual adoption**: Update code incrementally as convenient

### Recommended Migration

For new agents, prefer auto-extraction:

```python
# Before
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig, **kwargs):
        agent_config = BaseAgentConfig(
            llm_provider=config.llm_provider,
            model=config.model
        )
        super().__init__(config=agent_config, **kwargs)

# After (simpler)
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig, **kwargs):
        super().__init__(config=config, **kwargs)
```

## Summary

### Key Benefits

1. **Zero Duplication**: Eliminates 6-8 lines per agent
2. **Auto-Extraction**: Automatically extracts common fields
3. **Safe Defaults**: Missing fields use sensible defaults
4. **Type-Safe**: Preserves field types and validation
5. **Backward Compatible**: No breaking changes

### Impact Metrics

- **Lines Eliminated**: 6-8 per agent × 50+ agents = **300+ lines**
- **Maintenance**: Field changes in BaseAgentConfig auto-propagate
- **Error Reduction**: Eliminates copy-paste errors
- **Developer Experience**: Cleaner, more intuitive API

---

**Next**: [Shared Memory Convenience →](02-shared-memory-convenience.md)

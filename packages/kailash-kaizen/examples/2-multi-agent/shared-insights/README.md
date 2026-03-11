# Multi-Agent Shared Memory Collaboration

## Overview

This example demonstrates multi-agent collaboration using **SharedMemoryPool** from Phase 2 (Week 3). Three specialized agents collaborate on a research task, sharing insights through a shared memory pool.

**Collaboration Flow:**
```
ResearcherAgent → Findings → SharedMemoryPool
                                    ↓
                          AnalystAgent reads findings
                                    ↓
                          AnalystAgent → Analysis → SharedMemoryPool
                                    ↓
                          SynthesizerAgent reads all insights
                                    ↓
                          Final Synthesis Report
```

## Features

- **SharedMemoryPool**: Centralized insight storage for multi-agent collaboration
- **Attention Filtering**: Filter insights by tags, importance, segment, age
- **Exclude Own Insights**: Agents read only others' work (configurable)
- **Statistics Tracking**: Monitor insight count, agent count, tag/segment distributions
- **Thread-Safe**: Supports concurrent agent execution

## Architecture

### Agent Roles

#### 1. ResearcherAgent
**Responsibility**: Conduct research and document findings

**Behavior**:
- Research a given topic
- Extract key findings and points
- Write findings to shared memory

**Shared Memory**:
- Tags: `["research", topic]`
- Importance: `0.8`
- Segment: `"findings"`

#### 2. AnalystAgent
**Responsibility**: Analyze research findings and generate insights

**Behavior**:
- Read research findings from shared memory
- Perform deep analysis
- Write analysis insights to shared memory

**Shared Memory**:
- Reads: Tags `["research", topic]`, exclude_own=True
- Writes: Tags `["analysis", topic]`
- Importance: `0.9`
- Segment: `"analysis"`

#### 3. SynthesizerAgent
**Responsibility**: Synthesize all insights into final report

**Behavior**:
- Read ALL insights from shared memory
- Create comprehensive synthesis
- Generate final report with conclusions

**Shared Memory**:
- Reads: Tags `[topic]`, exclude_own=False (includes all agents)
- Does NOT write (final step)

### ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Research Collaboration                     │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐
│ ResearcherAgent  │  Conducts research
└────────┬─────────┘
         │ write_insight()
         │ tags: ["research", "topic"]
         │ importance: 0.8
         │ segment: "findings"
         ↓
┌──────────────────────────────────────────────────────────────┐
│                    SharedMemoryPool                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Insight 1: ResearcherAgent → Findings                  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         │
         │ read_relevant()
         │ tags: ["research", "topic"]
         │ exclude_own: True
         ↓
┌──────────────────┐
│  AnalystAgent    │  Analyzes findings
└────────┬─────────┘
         │ write_insight()
         │ tags: ["analysis", "topic"]
         │ importance: 0.9
         │ segment: "analysis"
         ↓
┌──────────────────────────────────────────────────────────────┐
│                    SharedMemoryPool                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Insight 1: ResearcherAgent → Findings                  │  │
│  │ Insight 2: AnalystAgent → Analysis                     │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         │
         │ read_relevant()
         │ tags: ["topic"]
         │ exclude_own: False (all agents)
         ↓
┌──────────────────┐
│ SynthesizerAgent │  Creates synthesis
└────────┬─────────┘
         │
         ↓
    Final Report
```

## Shared Memory Operations

### Writing Insights

Agents write insights to shared memory using the `write_insight()` method:

```python
insight = {
    "agent_id": self.agent_id,           # Agent identifier
    "content": "Research findings...",   # Insight content
    "tags": ["research", "Python"],      # Topic tags
    "importance": 0.8,                   # Relevance (0.0-1.0)
    "segment": "findings",               # Phase/segment
    "metadata": {                        # Additional context
        "topic": "Python",
        "confidence": 0.9
    }
}
shared_memory.write_insight(insight)
```

### Reading Insights

Agents read insights using `read_relevant()` with filtering:

```python
insights = shared_memory.read_relevant(
    agent_id=self.agent_id,       # Current agent ID
    tags=["research", "Python"],  # Filter by tags (ANY match)
    min_importance=0.7,           # Minimum importance threshold
    segments=["findings"],        # Filter by segments
    exclude_own=True,             # Exclude own insights
    limit=10                      # Top 10 most relevant
)
```

### Attention Filtering Examples

#### Filter by Tags
```python
# Get insights about Python
python_insights = pool.read_relevant(
    agent_id="analyst_1",
    tags=["Python"],
    exclude_own=True
)
```

#### Filter by Importance
```python
# Get high-importance insights only
high_priority = pool.read_relevant(
    agent_id="synthesizer_1",
    min_importance=0.8,
    exclude_own=False
)
```

#### Filter by Segment
```python
# Get only analysis insights
analysis_insights = pool.read_relevant(
    agent_id="reviewer_1",
    segments=["analysis"],
    exclude_own=True
)
```

#### Filter by Age
```python
# Get insights from last 5 minutes
recent_insights = pool.read_relevant(
    agent_id="monitor_1",
    max_age_seconds=300,
    exclude_own=True
)
```

#### Combined Filtering
```python
# Get recent, high-importance Python analysis insights
filtered = pool.read_relevant(
    agent_id="expert_1",
    tags=["Python"],
    min_importance=0.8,
    segments=["analysis"],
    max_age_seconds=600,
    exclude_own=True,
    limit=5
)
```

## Quick Start

### Installation

```bash
# Install Kaizen with dependencies
pip install kailash[kaizen]
```

### Basic Usage

```python
from workflow import research_collaboration_workflow

# Run collaboration workflow
topic = "Artificial Intelligence in Healthcare"
result = research_collaboration_workflow(topic)

# Access results
print(f"Research: {result['research']}")
print(f"Analysis: {result['analysis']}")
print(f"Synthesis: {result['synthesis']}")
print(f"Stats: {result['stats']}")
```

### Manual Agent Control

```python
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.core.config import AgentConfig
from workflow import ResearcherAgent, AnalystAgent, SynthesizerAgent

# Setup
shared_pool = SharedMemoryPool()
config = AgentConfig(llm_provider="openai", model="gpt-4")

# Create agents
researcher = ResearcherAgent(config, shared_pool, agent_id="researcher_1")
analyst = AnalystAgent(config, shared_pool, agent_id="analyst_1")
synthesizer = SynthesizerAgent(config, shared_pool, agent_id="synthesizer_1")

# Execute pipeline
topic = "Machine Learning"
research_result = researcher.research(topic)
analysis_result = analyst.analyze(topic)
synthesis_result = synthesizer.synthesize(topic)

# View statistics
stats = shared_pool.get_stats()
print(f"Insights: {stats['insight_count']}")
print(f"Agents: {stats['agent_count']}")
```

## Configuration Options

### Agent Configuration

```python
config = AgentConfig(
    llm_provider="openai",  # LLM provider (openai, anthropic, mock)
    model="gpt-4",          # Model name
    temperature=0.7,        # Temperature (0.0-1.0)
    max_tokens=2000         # Max response tokens
)
```

### Shared Memory Configuration

SharedMemoryPool is configured via filtering parameters:

```python
# Default read behavior
insights = pool.read_relevant(
    agent_id="my_agent",
    exclude_own=True,  # Exclude own insights
    limit=10           # Top 10 most relevant
)

# Custom filtering
insights = pool.read_relevant(
    agent_id="my_agent",
    tags=["research", "important"],
    min_importance=0.8,
    segments=["findings", "analysis"],
    max_age_seconds=3600,  # Last hour
    exclude_own=True,
    limit=20
)
```

## Use Cases

### 1. Research Team Collaboration
- **Researchers** gather information from multiple sources
- **Analysts** analyze aggregated research
- **Writers** synthesize into reports

### 2. Customer Service Pipeline
- **Classifier** analyzes customer request
- **Specialist** handles specific domain
- **Responder** formulates final response

### 3. Content Generation
- **Researcher** gathers facts and context
- **Writer** creates draft content
- **Editor** refines and finalizes

### 4. Software Development
- **Analyzer** examines requirements
- **Architect** designs solution
- **Implementer** writes code based on insights

### 5. Data Processing Pipeline
- **Collector** gathers data from sources
- **Processor** transforms and analyzes
- **Reporter** generates insights report

## Testing

### Unit Tests

```bash
# Run all tests
pytest tests/unit/examples/test_shared_insights.py -v

# Run specific test class
pytest tests/unit/examples/test_shared_insights.py::TestAgentInitialization -v

# Run with coverage
pytest tests/unit/examples/test_shared_insights.py --cov=examples/2-multi-agent/shared-insights
```

### Manual Testing

```bash
# Run example directly
cd examples/2-multi-agent/shared-insights
python workflow.py

# Expected output:
# ============================================================
# Multi-Agent Research Collaboration: Artificial Intelligence in Healthcare
# ============================================================
#
# Step 1: Researching 'Artificial Intelligence in Healthcare'...
#   - Findings: ...
#   - Key points: 3
#
# Step 2: Analyzing findings...
#   - Analysis: ...
#   - Insights: 2
#   - Recommendations: 3
#
# Step 3: Synthesizing insights...
#   - Synthesis: ...
#   - Summary: ...
#   - Conclusions: 4
#
# ============================================================
# Shared Memory Statistics:
# ============================================================
#   - Total insights: 2
#   - Agents involved: 2
#   - Tag distribution: {'research': 1, 'Artificial Intelligence in Healthcare': 2, 'analysis': 1}
#   - Segment distribution: {'findings': 1, 'analysis': 1}
# ============================================================
```

## Implementation Details

### Insight Format

Every insight in SharedMemoryPool has this structure:

```python
{
    "agent_id": "researcher_1",           # Agent identifier (required)
    "content": "Key findings...",         # Insight content (required)
    "tags": ["research", "Python"],       # Topic tags (required)
    "importance": 0.8,                    # Relevance 0.0-1.0 (required)
    "segment": "findings",                # Phase/segment (required)
    "timestamp": "2025-10-02T10:30:00",  # ISO timestamp (auto-generated)
    "metadata": {                         # Additional context (optional)
        "topic": "Python",
        "confidence": 0.9
    }
}
```

### Filtering Algorithm

`read_relevant()` applies filters in this order:

1. **Exclude Own**: Remove insights from calling agent (if `exclude_own=True`)
2. **Tag Filter**: Keep insights with ANY matching tag
3. **Importance Filter**: Keep insights >= `min_importance`
4. **Segment Filter**: Keep insights with matching segment
5. **Age Filter**: Keep insights within `max_age_seconds`
6. **Sort**: By importance (desc), then timestamp (desc)
7. **Limit**: Return top N most relevant

### Thread Safety

SharedMemoryPool uses a threading lock for all operations:

```python
# Internal implementation
with self._lock:
    self._insights.append(insight)  # Thread-safe write
```

This ensures safe concurrent access by multiple agents.

## Performance Considerations

### Memory Usage

- Each insight is ~500 bytes (average)
- Pool grows linearly with insights
- Consider clearing old insights periodically

### Filtering Performance

- Tag filtering: O(n * m) where n=insights, m=tags
- Sorting: O(n log n)
- Limit: O(k) where k=limit

### Recommendations

- Use `limit` parameter to cap results
- Apply `max_age_seconds` to filter old insights
- Use specific tags for faster filtering
- Clear pool with `pool.clear()` when done

## Advanced Patterns

### Conditional Insight Writing

```python
# Write only high-confidence insights
if confidence > 0.8:
    insight = {
        "agent_id": self.agent_id,
        "content": findings,
        "tags": ["research", topic],
        "importance": confidence,
        "segment": "findings"
    }
    self.shared_memory.write_insight(insight)
```

### Multi-Stage Filtering

```python
# Stage 1: Get all research insights
research = pool.read_relevant(
    agent_id=self.agent_id,
    tags=["research"],
    exclude_own=True
)

# Stage 2: Filter high-quality insights
high_quality = [
    i for i in research
    if i.get("metadata", {}).get("confidence", 0) > 0.9
]
```

### Insight Aggregation

```python
# Aggregate insights by segment
stats = pool.get_stats()
segments = stats["segment_distribution"]

for segment, count in segments.items():
    insights = pool.read_relevant(
        agent_id=self.agent_id,
        segments=[segment],
        exclude_own=False
    )
    print(f"{segment}: {count} insights")
```

## References

- **SharedMemoryPool Implementation**: `src/kaizen/memory/shared_memory.py`
- **BaseAgent Integration**: `src/kaizen/core/base_agent.py:138-139,348-424`
- **Unit Tests**: `tests/unit/memory/test_shared_memory_pool.py`
- **Integration Tests**: `tests/unit/memory/test_base_agent_shared_memory.py`
- **Phase 2 Completion**: Week 3, Task 2M (Shared Memory Systems)

## Support

For issues or questions:
- GitHub Issues: [kailash-sdk/issues](https://github.com/kailash-sdk/issues)
- Documentation: `docs/memory/shared-memory.md`
- Examples: `examples/2-multi-agent/`

---

**Author**: Kaizen Framework Team
**Created**: 2025-10-02 (Phase 4, Task 4I.3)
**License**: MIT

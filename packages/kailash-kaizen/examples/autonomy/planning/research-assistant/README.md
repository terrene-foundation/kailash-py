# Research Assistant (PlanningAgent)

## Overview

Automated research assistant that generates comprehensive research reports using the PlanningAgent pattern. The agent creates a complete research plan, validates its feasibility, then executes the plan step-by-step to generate a detailed report with cited sources.

**Pattern**: Plan → Validate → Execute (three-phase workflow)

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)

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
pip install kailash-kaizen
```

## Usage

```bash
python research_assistant.py "research topic"
```

### Basic Examples

```bash
# Simple research
python research_assistant.py "quantum computing applications"

# With context parameters
python research_assistant.py "artificial intelligence ethics" max_sources=10 report_length="3000 words"
```

### Context Parameters

- `max_sources`: Maximum number of sources to cite (default: 5)
- `report_length`: Target report length (default: "2000 words")

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              RESEARCH ASSISTANT                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐        ┌───────────────────┐   │
│  │ Control Protocol │        │  Audit Hook       │   │
│  │ (Progress)       │        │  (JSONL Trail)    │   │
│  └──────────────────┘        └───────────────────┘   │
│          │                            │               │
│          │                            │               │
│          ▼                            ▼               │
│  ┌──────────────────────────────────────────────┐   │
│  │         PlanningAgent                        │   │
│  │  Phase 1: Generate Research Plan             │   │
│  │  Phase 2: Validate Plan Feasibility          │   │
│  │  Phase 3: Execute Plan Step-by-Step          │   │
│  └──────────────────────────────────────────────┘   │
│          │                                           │
│          ▼                                           │
│  ┌──────────────────────────────────────────────┐   │
│  │         Hot Memory Tier (LRU Cache)          │   │
│  │  - Cache research results (1 hour TTL)       │   │
│  │  - < 1ms retrieval latency                   │   │
│  │  - 100 item capacity                         │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Three-Phase Workflow

### Phase 1: Plan Generation

The agent creates a detailed research plan with 5-10 steps:

```
📋 RESEARCH PLAN
============================================================
1. Define research scope and objectives
2. Identify 5 authoritative sources on quantum computing
3. Extract key applications from each source
4. Analyze current trends and future potential
5. Synthesize findings into coherent report
6. Add citations and references
============================================================
```

### Phase 2: Plan Validation

The agent validates the plan for feasibility and completeness:

```
✅ PLAN VALIDATION
============================================================
Status: validated
Issues: None
✅ Plan is feasible and complete
============================================================
```

**Validation Modes**:
- `strict`: Blocks execution if any issues found
- `warn`: Warns but proceeds with execution
- `off`: Skips validation (faster but risky)

### Phase 3: Plan Execution

The agent executes each step sequentially:

```
🔬 EXECUTION RESULTS
============================================================
Step 1: completed
  Research scope defined: Applications of quantum computing in...

Step 2: completed
  5 authoritative sources identified: Nature Physics, IEEE Quantum...

Step 3: completed
  Key applications extracted: Cryptography, drug discovery...

[... more steps ...]
============================================================
```

## Expected Output

```
============================================================
🤖 RESEARCH ASSISTANT INITIALIZED
============================================================
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
📊 Max Plan Steps: 10
✅ Validation Mode: strict
🔄 Replanning: True
📝 Audit Trail: True
============================================================

🔍 Starting research on: quantum computing applications

📝 Audit: Research started - quantum computing applications...

============================================================
📋 RESEARCH PLAN
============================================================
1. Define research scope and key questions
2. Identify 5 authoritative sources
3. Extract key applications and use cases
4. Analyze market trends and adoption
5. Synthesize findings into comprehensive report
6. Add citations and future outlook
============================================================

============================================================
✅ PLAN VALIDATION
============================================================
Status: validated
✅ Plan is feasible and complete
============================================================

============================================================
🔬 EXECUTION RESULTS
============================================================
Step 1: completed
  Research scope: Applications of quantum computing across industries...

Step 2: completed
  Sources identified: 5 peer-reviewed papers and industry reports...

[... execution continues ...]
============================================================

============================================================
📊 RESEARCH REPORT
============================================================
# Quantum Computing Applications

## Executive Summary
Quantum computing represents a paradigm shift in computational power...

## Key Applications

### 1. Cryptography
Quantum computers can break traditional encryption methods...

### 2. Drug Discovery
Simulating molecular interactions at quantum level...

### 3. Optimization Problems
Solving complex logistics and scheduling challenges...

[... comprehensive report continues ...]

## References
1. Nature Physics, "Quantum Advantage in Practical Applications"
2. IBM Quantum Computing Roadmap 2024
3. Google AI Quantum Supremacy Study
[...]
============================================================

✅ Audit: Research completed successfully

============================================================
📈 RESEARCH STATISTICS
============================================================
Plan Steps: 6
Validation: validated
Execution Steps: 6
💰 Cost: $0.00 (using Ollama local inference)
============================================================
```

## Features

### 1. Three-Phase Planning Pattern

**Plan**: Generate complete research plan before execution
**Validate**: Check plan feasibility (sources, steps, dependencies)
**Execute**: Execute validated plan step-by-step

**Benefits**:
- Upfront validation prevents wasted work
- Structured execution ensures completeness
- Clear progress tracking (% completion)

### 2. Memory Caching (Hot Tier)

- **LRU Cache**: Stores recent research results
- **< 1ms Latency**: Fast retrieval for repeated queries
- **1 Hour TTL**: Fresh results for repeated topics
- **100 Item Capacity**: Configurable cache size

### 3. Audit Trail (Hooks System)

- **JSONL Format**: Immutable append-only log
- **Event Tracking**: Research start/complete events
- **Compliance**: SOC2, GDPR, HIPAA audit requirements
- **Location**: `./research_audit.jsonl`

### 4. Progress Reporting (Control Protocol)

- **Real-time Updates**: Progress percentage (0-100%)
- **Status Messages**: "Generating plan", "Executing step 3/6"
- **Bidirectional**: Can request user input if needed

### 5. Error Handling

- **Replanning**: Automatically replan if validation fails
- **Graceful Degradation**: Partial results on errors
- **User Interruption**: Handles Ctrl+C gracefully

## Configuration

### PlanningConfig Options

```python
config = PlanningConfig(
    llm_provider="ollama",       # LLM provider
    model="llama3.1:8b-instruct-q8_0",          # Model name
    temperature=0.3,              # 0.0-1.0 (lower = more factual)
    max_plan_steps=10,            # Maximum steps in plan
    validation_mode="strict",     # strict/warn/off
    enable_replanning=True,       # Auto-replan on validation failure
    timeout=30,                   # Request timeout (seconds)
    max_retries=3                 # Retry count on errors
)
```

### Environment Variables

```bash
export KAIZEN_LLM_PROVIDER=ollama
export KAIZEN_MODEL=llama3.1:8b-instruct-q8_0
export KAIZEN_TEMPERATURE=0.3
```

## Troubleshooting

### Issue: "Ollama connection refused"
**Solution**: Make sure Ollama is running:
```bash
ollama serve
```

### Issue: "Model not found"
**Solution**: Pull the model first:
```bash
ollama pull llama3.1:8b-instruct-q8_0
```

### Issue: "Plan validation failed"
**Solution**: Check validation issues in output, or use `validation_mode="warn"` to proceed anyway

### Issue: "Research takes too long"
**Solution**: Reduce `max_plan_steps` or use faster model:
```bash
# Reduce steps
python research_assistant.py "topic" max_sources=3

# Or set timeout
config = PlanningConfig(timeout=60)  # 60 seconds
```

## Production Notes

### Deployment Considerations

1. **Scalability**:
   - Cache research results to reduce redundant work
   - Use parallel execution for multiple research queries
   - Implement database backend for persistent cache

2. **Cost Optimization**:
   - Ollama: $0.00 (unlimited research)
   - GPT-4: ~$0.50 per research report (better quality)
   - Budget tracking prevents runaway costs

3. **Quality Improvement**:
   - Use GPT-4 for higher quality research
   - Increase `max_plan_steps` for comprehensive reports
   - Add custom validation rules for domain-specific research

4. **Monitoring**:
   - Audit trail tracks all research activities
   - Progress reporting enables real-time monitoring
   - Memory cache metrics for performance tuning

### Cost Analysis

**Ollama (FREE):**
- $0.00 per research report
- Unlimited queries
- Local inference (no network required)
- Good for development and testing
- ~5-10 minute research time

**GPT-4 (Paid):**
- ~$0.50 per research report
- Better quality and depth
- Cloud API (requires network)
- Good for production
- ~2-3 minute research time

## Next Steps

1. **Web Search Integration**: Add real web search tools for live data
2. **Citation Management**: Automatic citation formatting (APA, MLA)
3. **Export Formats**: Export reports to PDF, Markdown, HTML
4. **Multi-Source Validation**: Cross-validate facts across sources
5. **Collaborative Research**: Multi-agent research teams

## Related Examples

- [Content Creator (PEV)](../content-creator/) - Iterative content refinement
- [Problem Solver (ToT)](../problem-solver/) - Multi-path exploration
- [Code Review Agent](../../tool-calling/code-review-agent/) - File tools with permissions

# Problem Solver (Tree-of-Thoughts Agent)

## Overview

Multi-path problem solver that explores alternative solutions using the Tree-of-Thoughts (ToT) Agent pattern. The agent generates multiple reasoning paths in parallel, evaluates each path independently, then selects and executes the best solution based on quality scores.

**Pattern**: Generate → Evaluate → Select → Execute (parallel multi-path exploration)

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
python problem_solver.py "problem description"
```

### Basic Examples

```bash
# Database optimization
python problem_solver.py "optimize database query performance"

# Architecture design
python problem_solver.py "design scalable microservices architecture"

# Business strategy
python problem_solver.py "increase customer retention by 20%"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              PROBLEM SOLVER                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐        ┌───────────────────┐   │
│  │ Control Protocol │        │  Path Comparison  │   │
│  │ (Progress)       │        │  Hook (JSONL)     │   │
│  └──────────────────┘        └───────────────────┘   │
│          │                            │               │
│          │                            │               │
│          ▼                            ▼               │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tree-of-Thoughts Agent               │   │
│  │                                              │   │
│  │  Generate (Parallel):                        │   │
│  │    Path 1 ──┐                                │   │
│  │    Path 2 ──┼─→ Evaluate (Score each)       │   │
│  │    Path 3 ──┤                                │   │
│  │    Path 4 ──┤   ↓                            │   │
│  │    Path 5 ──┘   Select Best (highest score) │   │
│  │                 ↓                            │   │
│  │                 Execute Winner               │   │
│  │                                              │   │
│  └──────────────────────────────────────────────┘   │
│          │                                           │
│          ▼                                           │
│  ┌──────────────────────────────────────────────┐   │
│  │         Export (Markdown Analysis)           │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Multi-Path Exploration Flow

### Phase 1: Generate Paths

```
🌳 SOLUTION PATHS (5 alternatives)
============================================================
Path 1: Index Optimization
  Create composite indexes on frequently queried columns...

Path 2: Query Rewrite
  Rewrite query to eliminate subqueries and use JOINs...

Path 3: Caching Layer
  Implement Redis caching for repeated queries...

Path 4: Database Sharding
  Partition data across multiple database instances...

Path 5: Hardware Upgrade
  Increase server memory and CPU cores...
============================================================
```

### Phase 2: Evaluate Paths

```
📊 PATH EVALUATIONS
============================================================
🏆 Path 2: Score 0.92
  Pros:
    + Low implementation cost
    + Immediate performance gain (10x faster)
    + No infrastructure changes needed
  Cons:
    - Requires testing existing queries
    - May need query refactoring

  Path 1: Score 0.85
  Pros:
    + Improves all queries on indexed columns
    + Relatively easy to implement
  Cons:
    - Increases database size
    - Slows down write operations

  Path 3: Score 0.78
  Pros:
    + Excellent for read-heavy workloads
    + Reduces database load
  Cons:
    - Cache invalidation complexity
    - Additional infrastructure cost

[... more evaluations ...]
============================================================
```

### Phase 3: Select Best

```
🏆 SELECTED BEST PATH
============================================================
Path ID: 2
Score: 0.92

Rationale:
  Query rewriting provides the best balance of immediate
  performance improvement (10x speedup) with minimal
  infrastructure changes. Implementation cost is low and
  risk is manageable through thorough testing.
============================================================
```

### Phase 4: Execute Winner

```
✅ SOLUTION
============================================================
## Database Query Optimization Solution

### Approach: Query Rewrite

1. **Analysis**: Current query uses correlated subqueries
   that execute N times. Rewrite to use JOINs reduces
   execution to single pass.

2. **Implementation**:
   ```sql
   -- Before (slow)
   SELECT * FROM orders WHERE customer_id IN
     (SELECT id FROM customers WHERE active = 1);

   -- After (10x faster)
   SELECT o.* FROM orders o
   INNER JOIN customers c ON o.customer_id = c.id
   WHERE c.active = 1;
   ```

3. **Testing**: Validate results match, benchmark performance.

4. **Expected Impact**: 10x query speedup, no infrastructure cost.

============================================================
```

## Expected Output

```
============================================================
🤖 PROBLEM SOLVER INITIALIZED
============================================================
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
🌳 Number of Paths: 5
📊 Evaluation Criteria: quality
⚡ Parallel Execution: True
📝 Comparison Logging: True
============================================================

🎯 Solving problem: optimize database query performance

============================================================
🌳 SOLUTION PATHS (5 alternatives)
============================================================

Path 1: Index Optimization
  Create composite indexes on frequently queried columns to
  reduce query execution time by 50-70%...

Path 2: Query Rewrite
  Rewrite queries to eliminate correlated subqueries and use
  efficient JOIN operations for 10x speedup...

Path 3: Caching Layer
  Implement Redis caching layer for frequently accessed data
  to reduce database load by 80%...

Path 4: Database Sharding
  Horizontal partitioning across multiple database instances
  for linear scalability...

Path 5: Hardware Upgrade
  Increase server memory from 16GB to 64GB and add SSD storage
  for 3x performance improvement...

============================================================

============================================================
📊 PATH EVALUATIONS
============================================================

🏆 Path 2: Score 0.92
  Pros:
    + Low implementation cost (~2 days)
    + Immediate 10x performance gain
    + No infrastructure changes required
    + Low risk with proper testing
  Cons:
    - Requires query testing
    - May need application code changes

  Path 1: Score 0.85
  Pros:
    + Improves all queries on indexed columns
    + Relatively easy to implement (~1 day)
    + No application code changes
  Cons:
    - Increases database size by 10-20%
    - Slows down write operations by 5-10%

  Path 3: Score 0.78
  Pros:
    + Excellent for read-heavy workloads (80% load reduction)
    + Reduces database contention
  Cons:
    - Cache invalidation complexity
    - Additional infrastructure cost ($100/month)
    - Increased system complexity

  Path 4: Score 0.65
  Pros:
    + Linear scalability
    + Handles unlimited data growth
  Cons:
    - High implementation cost (~4 weeks)
    - Complex application changes
    - Expensive infrastructure ($500+/month)

  Path 5: Score 0.55
  Pros:
    + Simple implementation
    + Guaranteed performance boost
  Cons:
    - Most expensive option ($5000+)
    - Linear scaling only
    - Hardware depreciation

============================================================

============================================================
🏆 SELECTED BEST PATH
============================================================
Path ID: 2
Score: 0.92

Rationale:
  Query rewriting provides the optimal balance between
  immediate performance gains (10x speedup), low
  implementation cost (2 days), and minimal risk. No
  infrastructure changes required. Testing ensures
  correctness before deployment.
============================================================

📊 Path Comparison: 5 paths evaluated, best score: 0.92

============================================================
✅ SOLUTION
============================================================
## Database Query Optimization: Query Rewrite Approach

### Problem Analysis
Current queries use inefficient correlated subqueries that
execute multiple times per row, causing O(N²) complexity.

### Solution: Query Rewrite

[... detailed solution continues ...]

### Implementation Steps
1. Identify all correlated subqueries
2. Rewrite using JOINs or EXISTS clauses
3. Test query results for correctness
4. Benchmark performance improvement
5. Deploy to production

### Expected Impact
- **Performance**: 10x speedup (500ms → 50ms)
- **Cost**: $0 (no infrastructure changes)
- **Timeline**: 2 days implementation
- **Risk**: Low (with proper testing)

============================================================

============================================================
💾 SOLUTION EXPORTED
============================================================
✅ Analysis: ./solution_output/solution_analysis_20251103_143045.md
============================================================

============================================================
📈 PROBLEM SOLVING STATISTICS
============================================================
Paths Explored: 5
Best Path Score: 0.92
Evaluation Criteria: quality
💰 Cost: $0.00 (using Ollama local inference)
============================================================
```

## Features

### 1. Multi-Path Exploration (ToT)

**Generate**: Create N parallel reasoning paths (default: 5)
**Evaluate**: Score each path independently on criteria
**Select**: Choose highest-scoring path as winner
**Execute**: Implement only the best solution

**Benefits**:
- Explores diverse alternatives
- Identifies hidden tradeoffs
- Evidence-based decision making
- Prevents premature convergence

### 2. Path Evaluation Criteria

**Quality** (`evaluation_criteria="quality"`):
- Solution effectiveness
- Implementation feasibility
- Long-term maintainability
- Best for: Strategic decisions

**Speed** (`evaluation_criteria="speed"`):
- Time to implement
- Quick wins prioritized
- Best for: Urgent problems

**Creativity** (`evaluation_criteria="creativity"`):
- Novel approaches
- Non-obvious solutions
- Best for: Innovation challenges

### 3. Pros/Cons Analysis

Each path evaluation includes:
- **Pros**: Benefits and advantages
- **Cons**: Drawbacks and risks
- **Score**: 0.0-1.0 quality rating
- **Rationale**: Selection reasoning

### 4. Parallel Execution

- **Concurrent Path Generation**: All paths generated simultaneously
- **Independent Evaluation**: Each path scored without bias
- **10-100x Speedup**: vs sequential generation
- **Resource Controlled**: Configurable `num_paths` limit

### 5. Comparison Logging (Hooks)

- **JSONL Format**: Immutable append-only log
- **Path Scores**: Track all path evaluations
- **Best Path Selection**: Decision audit trail
- **Location**: `./path_comparison.jsonl`

## Configuration

### ToTAgentConfig Options

```python
config = ToTAgentConfig(
    llm_provider="ollama",           # LLM provider
    model="llama3.1:8b-instruct-q8_0",              # Model name
    temperature=0.9,                  # HIGH for diversity (0.8-1.0)
    num_paths=5,                      # Number of alternatives (3-10)
    max_paths=20,                     # Safety limit
    evaluation_criteria="quality",    # quality/speed/creativity
    parallel_execution=True,          # Concurrent path generation
    timeout=30,                       # Request timeout (seconds)
    max_retries=3                     # Retry count on errors
)
```

### Temperature Settings

**High (0.8-1.0)**: More diverse paths (recommended for ToT)
**Medium (0.5-0.7)**: Balanced diversity and consistency
**Low (0.1-0.4)**: Similar paths (not recommended for ToT)

### Number of Paths

**3 paths**: Quick decisions, obvious alternatives
**5 paths** (default): Balanced exploration
**7-10 paths**: Comprehensive exploration, creative problems
**10+ paths**: Diminishing returns, longer execution time

### Environment Variables

```bash
export KAIZEN_LLM_PROVIDER=ollama
export KAIZEN_MODEL=llama3.1:8b-instruct-q8_0
export KAIZEN_TEMPERATURE=0.9  # HIGH for diversity
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

### Issue: "All paths have similar scores"
**Solution**: Increase temperature for more diversity:
```python
config = ToTAgentConfig(temperature=0.95)  # Higher diversity
```

### Issue: "Path generation takes too long"
**Solution**: Reduce number of paths or disable parallel execution:
```python
config = ToTAgentConfig(
    num_paths=3,                # Fewer paths
    parallel_execution=False    # Sequential generation
)
```

### Issue: "Selected path is not optimal"
**Solution**: Change evaluation criteria or generate more paths:
```python
config = ToTAgentConfig(
    num_paths=10,                    # More alternatives
    evaluation_criteria="quality"    # Emphasize solution quality
)
```

## Production Notes

### Deployment Considerations

1. **Scalability**:
   - Parallel path generation is resource-intensive
   - Use GPUs for faster LLM inference
   - Queue system for multiple problem requests

2. **Cost Optimization**:
   - Ollama: $0.00 (unlimited problem solving)
   - GPT-4: ~$0.30 per problem (5 paths × $0.06/path)
   - Reduce `num_paths` to lower costs

3. **Quality Improvement**:
   - Use GPT-4 for better path quality
   - Increase `num_paths` for comprehensive exploration
   - Custom evaluation criteria for domain-specific problems

4. **Monitoring**:
   - Comparison logging tracks path selection decisions
   - Progress reporting enables real-time monitoring
   - Export logs for decision audit trail

### Cost Analysis

**Ollama (FREE):**
- $0.00 per problem
- Unlimited problem solving
- Local inference (no network required)
- Good for development and testing
- ~30-60 seconds per problem (5 paths)

**GPT-4 (Paid):**
- ~$0.30 per problem (5 paths)
- Better path quality and evaluation
- Cloud API (requires network)
- Good for production
- ~15-20 seconds per problem

## Use Cases

### Strategic Decisions
- Business strategy selection
- Architecture design choices
- Technology stack selection
- Investment decisions

### Technical Problems
- Performance optimization
- System scalability
- Algorithm selection
- Infrastructure design

### Creative Challenges
- Product feature brainstorming
- Marketing campaign ideas
- Innovation opportunities
- Problem reframing

## Next Steps

1. **Custom Evaluation Criteria**: Domain-specific scoring functions
2. **Multi-Agent Voting**: Ensemble evaluation from multiple agents
3. **Path Visualization**: Tree diagram showing path relationships
4. **Iterative Refinement**: Refine selected path with PEV pattern
5. **Cost-Benefit Analysis**: Automatic ROI calculation for each path

## Related Examples

- [Research Assistant (Planning)](../research-assistant/) - Three-phase planning pattern
- [Content Creator (PEV)](../content-creator/) - Iterative refinement
- [DevOps Agent](../../tool-calling/devops-agent/) - Danger-level approval workflows

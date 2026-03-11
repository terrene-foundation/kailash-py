# Kaizen Performance Benchmarks

**Comprehensive benchmark suite for measuring Kaizen framework performance across 7 key areas.**

---

## Quick Start

### Prerequisites

1. **Python 3.12+**
2. **Ollama with llama3.1:8b-instruct-q8_0 model**
   ```bash
   ollama pull llama3.1:8b-instruct-q8_0
   ollama list  # Verify model is available
   ```
3. **Dependencies**
   ```bash
   pip install -e ".[dev]"
   pip install kailash-dataflow>=0.7.12 psutil
   ```

### Run All Suites

```bash
# Run all 7 suites sequentially
for suite in suite*.py; do
    python "$suite"
done
```

### Run Individual Suite

```bash
# Example: Run initialization benchmarks
python suite1_initialization.py

# Example: Run memory benchmarks
python suite3_memory.py
```

### View Results

Results are saved to `benchmarks/results/`:
```bash
ls -lh results/
# suite1_initialization_results.json
# suite2_execution_results.json
# ...
```

---

## Benchmark Suites

### Suite 1: Initialization Performance
**File**: `suite1_initialization.py`
**Duration**: ~10-15 minutes
**Benchmarks**: 3
- Cold Start (Fresh Process)
- Warm Start (Reused Runtime)
- Lazy Initialization (On-Demand)

### Suite 2: Execution Performance
**File**: `suite2_execution.py`
**Duration**: ~20-30 minutes
**Benchmarks**: 3
- Single-Shot Execution
- Multi-Turn Conversations
- Long-Running Autonomous Tasks

### Suite 3: Memory Performance
**File**: `suite3_memory.py`
**Duration**: ~15-20 minutes
**Benchmarks**: 3
- Hot Tier Access (< 1ms target)
- Warm Tier Access (< 10ms target)
- Cold Tier Persistence (< 100ms target)

### Suite 4: Tool Calling Performance
**File**: `suite4_tool_calling.py`
**Duration**: ~15-20 minutes
**Benchmarks**: 3
- Permission Check Overhead
- Approval Workflow Execution
- Tool Execution Performance

### Suite 5: Interrupt Handling Performance
**File**: `suite5_interrupts.py`
**Duration**: ~10-15 minutes
**Benchmarks**: 3
- Interrupt Detection Latency
- Graceful Shutdown Time
- Checkpoint Save on Interrupt

### Suite 6: Checkpoint Performance
**File**: `suite6_checkpoints.py`
**Duration**: ~10-15 minutes
**Benchmarks**: 3
- Checkpoint Save Performance
- Checkpoint Load Performance
- Compression Efficiency

### Suite 7: Multi-Agent Coordination Performance
**File**: `suite7_multi_agent.py`
**Duration**: ~15-20 minutes
**Benchmarks**: 3
- A2A Protocol Overhead
- Semantic Routing Latency
- Multi-Agent Task Delegation

---

## Framework

### `framework.py`

Production-grade benchmark harness providing:
- **Statistical rigor**: 100+ iterations, outlier removal (>3 std dev)
- **Percentile metrics**: p50, p95, p99, mean, stddev
- **Resource monitoring**: CPU%, memory MB via psutil
- **Confidence intervals**: 95% confidence for mean estimates
- **JSON export**: Structured results for CI integration

**Example Usage:**
```python
from benchmarks.framework import BenchmarkSuite

suite = BenchmarkSuite(name="My Benchmarks")

@suite.benchmark(name="Test Benchmark", warmup=10, iterations=100)
def bench_test():
    # Benchmark code here
    result = my_function()
    assert result is not None

# Run suite
results = suite.run()
suite.print_summary()
suite.export_results("results.json")
```

---

## Documentation

### Complete Guides

1. **[BENCHMARK_GUIDE.md](../docs/benchmarks/BENCHMARK_GUIDE.md)** (200+ lines)
   - Installation & setup
   - Running benchmarks
   - Interpreting results
   - Statistical methodology
   - Performance targets
   - Troubleshooting

2. **[CLAUDE_COMPARISON.md](../docs/benchmarks/CLAUDE_COMPARISON.md)** (200+ lines)
   - Feature parity matrix (Kaizen vs Claude SDK)
   - Architecture differences
   - Performance comparison
   - Cost analysis
   - Use case recommendations
   - Migration path

3. **[OPTIMIZATION_ROADMAP.md](../docs/benchmarks/OPTIMIZATION_ROADMAP.md)** (300+ lines)
   - Top 10 bottlenecks
   - Proposed solutions with effort estimates
   - Expected performance gains
   - Prioritization matrix (impact vs effort)
   - Implementation timeline (Q1-Q2 2025)

---

## CI Integration

### GitHub Actions

**File**: `.github/workflows/benchmarks.yml`

**Triggers**:
- Manual (workflow_dispatch)
- Weekly (Sunday at midnight UTC)
- On push to main (track performance over time)

**Features**:
- Runs all 7 suites
- Archives results (90-day retention)
- Commits baselines to repository
- Comments on PRs with results

**Usage**:
```bash
# Trigger manually via GitHub UI
# or wait for weekly scheduled run
```

---

## Docker Container

### Reproducible Benchmarks

**File**: `Dockerfile.benchmarks`

**Features**:
- Fixed Python 3.12 environment
- Pre-installed Ollama + llama3.1:8b-instruct-q8_0
- All dependencies included
- Documented hardware specs

**Build & Run**:
```bash
# Build container
docker build -f Dockerfile.benchmarks -t kaizen-benchmarks .

# Run all suites
docker run --rm \
    -v $(pwd)/results:/app/benchmarks/results \
    kaizen-benchmarks

# View results
ls -lh results/
```

---

## Performance Targets

### Current Baseline (v0.6.5)

| Area | Current (p50) | Target (p50) | Status |
|------|---------------|--------------|--------|
| Initialization | 13ms | 5ms | 🟡 Needs Work |
| Single-shot | 800ms | 300ms | 🔴 Critical |
| Multi-turn | 1200ms | 500ms | 🔴 Critical |
| Hot tier | 0.8ms | 0.5ms | 🟢 Good |
| Warm tier | 5ms | 3ms | 🟢 Good |
| Tool calling | 25ms | 10ms | 🟡 Needs Work |
| Checkpoints | 30ms | 15ms | 🟢 Good |
| A2A routing | 4ms | 2ms | 🟢 Good |

### Optimization Roadmap

**Phase 1 (Q1 2025)**: 30-40% latency reduction
**Phase 2 (Q2 2025)**: Additional 20-30% reduction
**Total**: 50-70% improvement by mid-2025

See [OPTIMIZATION_ROADMAP.md](../docs/benchmarks/OPTIMIZATION_ROADMAP.md) for detailed plan.

---

## Cost

**Total**: $0.00 (100% FREE)

All benchmarks use **Ollama llama3.1:8b-instruct-q8_0** - a FREE, open-source model running locally with no API costs.

---

## Troubleshooting

### Issue: Ollama not found

```bash
# Install Ollama
brew install ollama  # macOS
# or visit https://ollama.ai/download

# Start Ollama
ollama serve

# Pull model
ollama pull llama3.1:8b-instruct-q8_0
```

### Issue: High variance in results

**Causes**:
- Background processes
- Thermal throttling
- Insufficient warmup

**Solutions**:
- Close browser, IDE, other heavy apps
- Increase warmup iterations (edit suite file)
- Use Docker for isolated environment

### Issue: Memory benchmarks fail

**Cause**: DataFlow not installed

**Solution**:
```bash
pip install kailash-dataflow>=0.7.12
```

---

## File Structure

```
benchmarks/
├── README.md                    # This file
├── framework.py                 # Benchmark harness (300+ lines)
├── suite1_initialization.py     # Initialization benchmarks
├── suite2_execution.py          # Execution benchmarks
├── suite3_memory.py             # Memory benchmarks
├── suite4_tool_calling.py       # Tool calling benchmarks
├── suite5_interrupts.py         # Interrupt benchmarks
├── suite6_checkpoints.py        # Checkpoint benchmarks
├── suite7_multi_agent.py        # Multi-agent benchmarks
├── results/                     # JSON results (gitignored)
└── baselines/                   # Archived results (committed)
```

---

## Contributing

### Adding New Benchmarks

1. **Create benchmark function**:
   ```python
   @suite.benchmark(name="My Benchmark", warmup=10, iterations=100)
   def bench_my_feature():
       # Benchmark code
       result = my_feature()
       assert result is not None
   ```

2. **Run benchmark**:
   ```bash
   python suite_new.py
   ```

3. **Update documentation**:
   - Add to README.md
   - Update BENCHMARK_GUIDE.md
   - Document performance targets

### Best Practices

1. **Use warmup**: 5-10 iterations to eliminate JIT effects
2. **Use iterations**: 50-100 for statistical significance
3. **Verify results**: Add assertions to catch regressions
4. **Document targets**: Set clear performance goals
5. **Test isolation**: Avoid global state, cleanup after each iteration

---

## FAQ

**Q: Why Ollama instead of OpenAI/Anthropic?**
A: Zero cost for continuous benchmarking. Paid APIs would be expensive for 100+ iterations across 21 benchmarks.

**Q: How accurate are the benchmarks?**
A: Very accurate. 100+ iterations with outlier removal (>3 std dev) and 95% confidence intervals ensure statistical rigor.

**Q: Can I run benchmarks with different models?**
A: Yes! Edit suite files, change `LLAMA_MODEL` to your preferred model (e.g., "gpt-4", "claude-3-haiku"). Note: May incur API costs.

**Q: How do I compare versions?**
A: Archive results from v0.6.5, upgrade to v0.7.0, re-run benchmarks, then use `diff` or JSON comparison tools.

**Q: Why are execution benchmarks slow?**
A: Ollama llama3.1:8b-instruct-q8_0 has ~800ms inference latency. This is expected for local models. OpenAI/Anthropic would be faster (~300-500ms).

---

## Next Steps

1. ✅ Install Ollama + llama3.1:8b-instruct-q8_0
2. ✅ Run all 7 suites
3. ✅ Review results in `results/` directory
4. ✅ Read [BENCHMARK_GUIDE.md](../docs/benchmarks/BENCHMARK_GUIDE.md) for interpretation
5. ✅ Check [OPTIMIZATION_ROADMAP.md](../docs/benchmarks/OPTIMIZATION_ROADMAP.md) for improvements
6. ✅ Compare with Claude SDK via [CLAUDE_COMPARISON.md](../docs/benchmarks/CLAUDE_COMPARISON.md)

---

**Last Updated**: 2025-11-03
**Version**: 1.0.0
**TODO-171 Status**: ✅ Complete

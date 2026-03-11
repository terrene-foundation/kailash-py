# E2E Test Suite Quick Reference

**Phase 5 Production Readiness | TODO-170 | Budget: <$20**

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Total Tests | 39 (36 E2E + 3 long-running) |
| Projected Cost | $4.70 |
| Budget Remaining | $15.30 (76% under) |
| Timeline | 3 weeks |
| Test Duration | ~6-13 hours total |
| Infrastructure | Ollama + OpenAI + PostgreSQL |

---

## Test Distribution

```
Autonomy E2E Tests (36 tests)
├── Tool Calling (12 tests)
│   ├── Builtin tools (4): file, HTTP, bash, web
│   ├── Custom tools (2): definition, complex params
│   ├── Approval workflows (4): SAFE, MODERATE, DANGEROUS, CRITICAL
│   └── Dangerous operations (2): deletion, system commands
│
├── Planning (5 tests)
│   ├── Planning Agent (3): multi-step, execution, adaptation
│   ├── PEV Agent (1): plan-execute-verify cycle
│   └── ToT Agent (1): tree-of-thoughts exploration
│
├── Meta-Controller (3 tests)
│   ├── Semantic routing (2): specialist selection, complexity-based
│   ├── Fallback handling (1): primary failure → secondary
│   └── Task decomposition (1): complex → subtasks
│
├── Memory (7 tests)
│   ├── Hot tier (2): in-memory, eviction
│   ├── Warm tier (1): Redis persistence
│   ├── Cold tier (1): PostgreSQL long-term
│   └── Persistence (2): restart, tier promotion
│
├── Checkpoints (5 tests)
│   ├── Auto-checkpoint (2): creation, frequency
│   ├── Resume (2): crash recovery, state preservation
│   └── Compression (1): production optimization
│
└── Interrupts (4 tests)
    ├── Ctrl+C (2): graceful shutdown, propagation
    ├── Timeout (1): duration limit
    └── Budget (1): cost control

Long-Running Tests (3 tests, 6-12 hours)
├── Code Review (1): 50 files, 2-4 hours, $0.50
├── Data Analysis (1): 10 datasets, 2-4 hours, $1.00
└── Research (1): 100 documents, 2-4 hours, $1.50
```

---

## LLM Strategy

### Ollama (Free)
- **Model**: llama3.1:8b-instruct-q8_0
- **Usage**: 80% of tests
- **Tests**: Tool calling, memory, checkpoints, interrupts, planning
- **Cost**: $0.00
- **Why**: Fast, local, cost-free for high-volume testing

### GPT-4o-mini (Paid)
- **Usage**: 20% of tests
- **Tests**: Meta-controller (semantic matching), PEV/ToT validation, long-running insights
- **Cost**: $4.70 total
- **Why**: Quality semantic routing, synthesis, validation

---

## File Organization

```
tests/
├── E2E_TEST_ARCHITECTURE_PLAN.md      ← Full architecture (this doc's parent)
├── E2E_IMPLEMENTATION_CHECKLIST.md    ← Day-by-day implementation plan
├── E2E_QUICK_REFERENCE.md             ← This file (quick lookup)
│
├── e2e/autonomy/
│   ├── tools/                         ← 12 tests
│   ├── planning/                      ← 5 tests
│   ├── meta_controller/               ← 3 tests
│   ├── memory/                        ← 7 tests
│   ├── checkpoints/                   ← 5 tests (2 existing + 3 new)
│   └── interrupts/                    ← 4 tests (1 existing + 3 new)
│
├── e2e/long_running/                  ← 3 tests (2-4 hours each)
│   ├── test_code_review_workload.py
│   ├── test_data_analysis_workload.py
│   └── test_research_workload.py
│
├── fixtures/e2e/                      ← Test data
│   ├── code_review_dataset.py
│   ├── data_analysis_dataset.py
│   ├── research_dataset.py
│   └── approval_scenarios.py
│
└── utils/                             ← Shared utilities
    ├── cost_tracking.py               ← Budget enforcement
    ├── reliability_helpers.py         ← Flaky test prevention
    └── long_running_helpers.py        ← Multi-hour test support
```

---

## Running Tests

### Quick Commands

```bash
# All E2E tests (20+ tests, ~20-40 min, $0.40)
pytest tests/e2e/autonomy/ -v --timeout=300

# Specific system
pytest tests/e2e/autonomy/tools/ -v             # Tool calling only
pytest tests/e2e/autonomy/planning/ -v          # Planning only
pytest tests/e2e/autonomy/memory/ -v            # Memory only

# Long-running tests (6-12 hours, $3.00)
pytest tests/e2e/long_running/ -v --timeout=14400

# Single long-running test
pytest tests/e2e/long_running/test_code_review_workload.py -v

# With cost tracking
pytest tests/e2e/ -v --cost-report
```

### Infrastructure Setup

```bash
# Start Ollama (required for most tests)
ollama pull llama3.1:8b-instruct-q8_0

# Start PostgreSQL (for memory/persistence tests)
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15

# Start Redis (for warm memory tests)
docker run -d -p 6379:6379 redis:7

# Verify infrastructure
ollama list                    # Check llama3.1:8b-instruct-q8_0 available
docker ps                      # Check PostgreSQL/Redis running
echo $OPENAI_API_KEY          # Check API key set
```

---

## Cost Breakdown

| Week | Phase | Tests | Duration | Cost |
|------|-------|-------|----------|------|
| 1 | Tool Calling + Planning | 17 | 10-20 min | $0.10 |
| 1 | Memory + Checkpoints | 10 | 7-10 min | $0.00 |
| 2 | Meta-Controller | 3 | 1.5-4.5 min | $0.30 |
| 2 | Interrupts | 4 | 2-6 min | $0.10 |
| 2 | Code Review (long) | 1 | 2-4 hours | $0.50 |
| 3 | Data Analysis (long) | 1 | 2-4 hours | $1.00 |
| 3 | Research (long) | 1 | 2-4 hours | $1.50 |
| 3 | Validation Runs (3x) | 36 | 1-2 hours | $1.20 |
| **TOTAL** | **All Tests** | **39** | **6-13 hours** | **$4.70** |

---

## Implementation Timeline

### Week 1: Core E2E (Days 1-5)
- **Day 1**: Tool calling - builtin (6 tests)
- **Day 2**: Tool calling - approval (6 tests)
- **Day 3**: Planning + meta-controller pt1 (5 tests)
- **Day 4**: Meta-controller pt2 (3 tests)
- **Day 5**: Memory + checkpoints (7 tests)
- **Outcome**: 27 tests, $0.40

### Week 2: Long-Running Setup (Days 6-10)
- **Day 6**: Checkpoint enhancements (5 tests)
- **Day 7**: Interrupts (4 tests)
- **Day 8-9**: Infrastructure + fixtures (9-12 hours)
- **Day 10**: Code review test (2-4 hours, $0.50)
- **Outcome**: 9 tests + infrastructure, $0.60

### Week 3: Long-Running + Validation (Days 11-15)
- **Day 11**: Data analysis test (2-4 hours, $1.00)
- **Day 12**: Research test (2-4 hours, $1.50)
- **Day 13-14**: 3 validation runs ($1.20)
- **Day 15**: CI integration + docs
- **Outcome**: 3 long tests + validation, $3.70

---

## Success Criteria

### Test Coverage ✅
- [ ] 20+ E2E tests covering 6 autonomy systems
- [ ] 3 long-running tests (2-4 hours each)
- [ ] 100% real infrastructure (NO MOCKING)

### Reliability ✅
- [ ] 3 consecutive clean runs (no flakes)
- [ ] All tests pass with timeout guards
- [ ] No memory leaks in long-running tests

### Cost Control ✅
- [ ] Total cost <$20 ($4.70 projected)
- [ ] Per-test cost tracking
- [ ] Abort at 80% budget ($16)

### CI Integration ✅
- [ ] GitHub Actions workflow
- [ ] Nightly long-running tests
- [ ] PR validation (short tests)

---

## Common Issues & Solutions

### Issue: Ollama timeout on first call
**Solution**: Add warmup fixture in conftest.py
```python
@pytest.fixture(scope="session", autouse=True)
def warmup_ollama():
    subprocess.run(["ollama", "run", "llama3.1:8b-instruct-q8_0", "Hello"], timeout=30)
```

### Issue: PostgreSQL connection refused
**Solution**: Ensure Docker container running
```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15
```

### Issue: OpenAI rate limit
**Solution**: Add retry with exponential backoff
```python
from tests.utils.reliability_helpers import retry_async
await retry_async(agent.run, RetryConfig(max_attempts=3))
```

### Issue: Test timeout in long-running tests
**Solution**: Increase timeout for long tests
```python
@pytest.mark.timeout(14400)  # 4 hours
async def test_code_review_workload():
    ...
```

### Issue: Cost exceeding budget
**Solution**: Cost tracker aborts at 80% automatically
```python
# In conftest.py
@pytest.fixture(autouse=True)
def enforce_cost_budget(cost_tracker):
    if cost_tracker.total_cost > 16.0:  # 80% of $20
        pytest.exit("Budget limit approaching")
```

---

## Key Files Reference

### Architecture & Planning
- `tests/E2E_TEST_ARCHITECTURE_PLAN.md` - Complete architecture (Section 1-12)
- `tests/E2E_IMPLEMENTATION_CHECKLIST.md` - Day-by-day checklist
- `tests/E2E_QUICK_REFERENCE.md` - This file

### Utilities (Week 2 Day 8-9)
- `tests/utils/cost_tracking.py` - CostTracker, BudgetExceededError
- `tests/utils/reliability_helpers.py` - retry_async, ReliabilityMonitor
- `tests/utils/long_running_helpers.py` - ProgressTracker, with_timeout

### Fixtures (Week 2 Day 9)
- `tests/fixtures/e2e/code_review_dataset.py` - 50 Python files
- `tests/fixtures/e2e/data_analysis_dataset.py` - 100k row datasets
- `tests/fixtures/e2e/research_dataset.py` - 100 markdown docs
- `tests/fixtures/e2e/approval_scenarios.py` - 4 danger levels

### Existing Files (Enhance)
- `tests/e2e/autonomy/test_checkpoint_e2e.py` - Add Tests 28-29
- `tests/e2e/autonomy/interrupts/test_interrupt_e2e.py` - Add Tests 33-34
- `tests/conftest.py` - Add E2E fixtures (long_running_config, cost_tracker)

---

## Next Steps

1. **Review** this architecture with team
2. **Approve** budget allocation ($4.70 projected)
3. **Create** directory structure
4. **Implement** utility modules (Week 2 Day 8)
5. **Start** Day 1 implementation (tool calling tests)

**Estimated Total Effort**: 40-50 hours over 3 weeks

---

**Questions?** See full architecture in `E2E_TEST_ARCHITECTURE_PLAN.md`

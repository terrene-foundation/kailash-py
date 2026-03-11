# E2E Test Implementation Checklist - TODO-170

**Objective**: Phase 5 Production Readiness - Comprehensive E2E test suite for v1.0 release
**Budget**: <$20 total | **Timeline**: 3 weeks | **Tests**: 20+ E2E + 3 long-running

---

## Week 1: Core E2E Tests (Days 1-5)

### Day 1: Tool Calling - Builtin Tools (6 tests)

**File**: `tests/e2e/autonomy/tools/test_builtin_tools_e2e.py`

- [ ] Test 1: File tools (read_file, write_file, list_files, delete_file)
  - Create test directory with sample files
  - Agent reads, modifies, and deletes files
  - Validate filesystem state after each operation
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

- [ ] Test 2: HTTP tools (http_get, http_post)
  - Use httpbin.org for real HTTP testing
  - Agent makes GET/POST requests
  - Validate response parsing
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

- [ ] Test 3: Bash tools (bash_execute, bash_stream)
  - Agent executes safe bash commands (ls, echo, date)
  - Validate command output parsing
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

- [ ] Test 4: Web tools (web_search, web_scrape)
  - Agent searches and scrapes real websites
  - Validate content extraction
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/tools/test_custom_tools_e2e.py`

- [ ] Test 5: Custom tool definition and registration
  - Define custom "calculate_statistics" tool
  - Register with agent
  - Validate tool discovery and execution
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

- [ ] Test 6: Custom tool with complex parameters
  - Define tool with nested parameters and validation
  - Test parameter validation errors
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-60s
  - **Cost**: $0.00

**Day 1 Total**: 6 tests, 3-6 minutes, $0.00

---

### Day 2: Tool Calling - Approval Workflows (6 tests)

**File**: `tests/e2e/autonomy/tools/test_approval_workflows_e2e.py`

- [ ] Test 7: SAFE level tools (auto-approve)
  - Agent uses read_file (SAFE level)
  - Validate no approval required
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

- [ ] Test 8: MODERATE level tools (require approval)
  - Agent uses write_file (MODERATE level)
  - Simulate approval workflow
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

- [ ] Test 9: DANGEROUS level tools (require confirmation)
  - Agent uses delete_file (DANGEROUS level)
  - Test multi-step approval
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

- [ ] Test 10: CRITICAL level tools (multi-step approval)
  - Agent uses bash_execute with rm command (CRITICAL)
  - Test approval chain
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/tools/test_dangerous_operations_e2e.py`

- [ ] Test 11: File deletion with approval workflow
  - Complete workflow: request → approve → execute → verify
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 45s
  - **Cost**: $0.00

- [ ] Test 12: System command execution with safety checks
  - Test rejection of dangerous commands
  - Validate safety sandbox
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 45s
  - **Cost**: $0.00

**Day 2 Total**: 6 tests, 3-4 minutes, $0.00

---

### Day 3: Planning + Meta-Controller Part 1 (5 tests)

**File**: `tests/e2e/autonomy/planning/test_planning_agent_e2e.py`

- [ ] Test 13: Planning agent creates multi-step plan
  - Task: "Analyze CSV file and generate report"
  - Validate plan has 3+ steps
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

- [ ] Test 14: Plan execution with real tool calls
  - Execute plan from Test 13
  - Validate each step executes successfully
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

- [ ] Test 15: Plan adaptation on errors
  - Introduce file not found error
  - Validate plan adapts to error
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/planning/test_pev_agent_e2e.py`

- [ ] Test 16: PEV agent (Plan-Execute-Verify) complete cycle
  - Task: "Process data and verify results"
  - Validate plan → execute → verify cycle
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0 + gpt-4o-mini (verification)
  - **Duration**: 1-2 minutes
  - **Cost**: $0.05

**File**: `tests/e2e/autonomy/planning/test_tot_agent_e2e.py`

- [ ] Test 17: Tree-of-Thoughts agent exploration
  - Task: "Find optimal solution to problem"
  - Validate multiple branches explored
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0 + gpt-4o-mini (evaluation)
  - **Duration**: 1-2 minutes
  - **Cost**: $0.05

**Day 3 Total**: 5 tests, 5-10 minutes, $0.10

---

### Day 4: Meta-Controller Part 2 (3 tests)

**File**: `tests/e2e/autonomy/meta_controller/test_semantic_routing_e2e.py`

- [ ] Test 18: Semantic routing to correct specialist agent
  - Create 3 specialist agents (code, data, writing)
  - Task: "Analyze sales data" → should route to data specialist
  - Validate correct routing
  - **LLM**: gpt-4o-mini (semantic matching)
  - **Duration**: 30-90s
  - **Cost**: $0.10

- [ ] Test 19: Dynamic agent selection based on task complexity
  - Task with varying complexity
  - Validate complexity-based routing
  - **LLM**: gpt-4o-mini
  - **Duration**: 30-90s
  - **Cost**: $0.10

**File**: `tests/e2e/autonomy/meta_controller/test_fallback_handling_e2e.py`

- [ ] Test 20: Fallback when primary agent fails
  - Primary agent fails intentionally
  - Validate fallback to secondary agent
  - **LLM**: gpt-4o-mini
  - **Duration**: 30-90s
  - **Cost**: $0.10

**Day 4 Total**: 3 tests, 1.5-4.5 minutes, $0.30

---

### Day 5: Memory + Checkpoints (7 tests)

**File**: `tests/e2e/autonomy/meta_controller/test_task_decomposition_e2e.py`

- [ ] Test 21: Complex task decomposition into subtasks
  - Task: "Build complete data pipeline"
  - Validate decomposition into 5+ subtasks
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1 minute
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/memory/test_hot_tier_e2e.py`

- [ ] Test 22: Hot memory (in-memory cache) operations
  - Store and retrieve from hot tier
  - Validate <10ms access time
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

- [ ] Test 23: Hot memory eviction policy (LRU)
  - Fill hot tier beyond capacity
  - Validate LRU eviction
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/memory/test_warm_tier_e2e.py`

- [ ] Test 24: Warm memory (Redis) with real Redis instance
  - Store and retrieve from Redis
  - Validate persistence across agent restarts
  - **Infrastructure**: Docker Redis
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/memory/test_cold_tier_e2e.py`

- [ ] Test 25: Cold memory (PostgreSQL) with real database
  - Store and retrieve from PostgreSQL
  - Validate long-term persistence
  - **Infrastructure**: Docker PostgreSQL
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/memory/test_persistence_e2e.py`

- [ ] Test 26: Memory persistence across agent restarts
  - Store data, restart agent, retrieve data
  - **Infrastructure**: PostgreSQL
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1 minute
  - **Cost**: $0.00

- [ ] Test 27: Memory tier promotion/demotion
  - Access cold data → promoted to warm → hot
  - **Infrastructure**: PostgreSQL + Redis
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1 minute
  - **Cost**: $0.00

**Day 5 Total**: 7 tests, 4.5-6 minutes, $0.00

**Week 1 Total**: 27 tests, 17-30 minutes, $0.40

---

## Week 2: Interrupts + Long-Running Setup (Days 6-10)

### Day 6: Checkpoints Enhancement (3 tests)

**File**: `tests/e2e/autonomy/checkpoints/test_auto_checkpoint_e2e.py` (ENHANCE EXISTING)

- [ ] Test 28: Automatic checkpoint creation during long execution
  - Enhance existing test with validation
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

- [ ] Test 29: Checkpoint frequency configuration
  - Test different frequencies (1, 5, 10 steps)
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/checkpoints/test_resume_e2e.py` (NEW)

- [ ] Test 30: Resume from checkpoint after crash simulation
  - Simulate crash mid-execution
  - Resume from last checkpoint
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1-2 minutes
  - **Cost**: $0.00

- [ ] Test 31: Resume preserves agent state correctly
  - Validate memory, tools, and history preserved
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1 minute
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/checkpoints/test_compression_e2e.py` (NEW)

- [ ] Test 32: Checkpoint compression for production scenarios
  - Create large checkpoint (>10MB)
  - Validate compression reduces size
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 1 minute
  - **Cost**: $0.00

**Day 6 Total**: 5 tests, 5-8 minutes, $0.00

---

### Day 7: Interrupts (3 tests)

**File**: `tests/e2e/autonomy/interrupts/test_interrupt_e2e.py` (ENHANCE EXISTING)

- [ ] Test 33: Ctrl+C interrupt with graceful shutdown
  - Enhance existing test with validation
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-90s
  - **Cost**: $0.00

- [ ] Test 34: Signal propagation in multi-agent system
  - Parent interrupt cascades to children
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-90s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/interrupts/test_timeout_e2e.py` (NEW)

- [ ] Test 35: Timeout interrupt after specified duration
  - Set 30s timeout on long task
  - Validate graceful shutdown
  - **LLM**: Ollama llama3.1:8b-instruct-q8_0
  - **Duration**: 30-90s
  - **Cost**: $0.00

**File**: `tests/e2e/autonomy/interrupts/test_budget_limit_e2e.py` (NEW)

- [ ] Test 36: Budget limit interrupt (cost control)
  - Set $0.10 budget limit
  - Validate auto-stop at limit
  - **LLM**: gpt-4o-mini (to trigger cost)
  - **Duration**: 30-90s
  - **Cost**: $0.10

**Day 7 Total**: 4 tests, 2-6 minutes, $0.10

---

### Day 8-9: Infrastructure + Fixtures

**Utility Modules** (Day 8)

- [ ] Create `tests/utils/cost_tracking.py`
  - CostTracker class with budget enforcement
  - APICall dataclass for recording calls
  - Cost reporting functionality
  - **Estimated**: 2-3 hours

- [ ] Create `tests/utils/reliability_helpers.py`
  - RetryConfig and retry_async for flaky test prevention
  - ReliabilityMonitor for tracking issues
  - ensure_no_memory_leaks decorator
  - **Estimated**: 2-3 hours

- [ ] Create `tests/utils/long_running_helpers.py`
  - ProgressTracker for long-running tests
  - with_timeout wrapper
  - checkpoint_every decorator
  - **Estimated**: 1-2 hours

**Fixtures** (Day 9)

- [ ] Create `tests/fixtures/e2e/__init__.py`

- [ ] Create `tests/fixtures/e2e/code_review_dataset.py`
  - get_python_files() - select 50 Python files from src/kaizen/
  - get_review_criteria() - code quality, security, performance
  - **Estimated**: 1 hour

- [ ] Create `tests/fixtures/e2e/data_analysis_dataset.py`
  - generate_sales_data() - 100k row DataFrame
  - get_analysis_tasks() - 5 analysis tasks
  - **Estimated**: 1 hour

- [ ] Create `tests/fixtures/e2e/research_dataset.py`
  - get_research_documents() - 100 markdown files from docs/
  - get_research_questions() - 5 research questions
  - **Estimated**: 1 hour

- [ ] Create `tests/fixtures/e2e/approval_scenarios.py`
  - get_approval_scenarios() - 4 danger levels
  - **Estimated**: 30 minutes

- [ ] Enhance `tests/conftest.py`
  - Add long_running_config fixture
  - Add cost_tracker fixture with budget enforcement
  - Add reliability_monitor fixture
  - **Estimated**: 1 hour

**Days 8-9 Total**: 9-12 hours of implementation

---

### Day 10: Long-Running Test 1 - Code Review

**File**: `tests/e2e/long_running/conftest.py`

- [ ] Create long-running fixtures
  - Long-running agent configuration
  - Progress tracking setup
  - Cost monitoring setup
  - **Estimated**: 1 hour

**File**: `tests/e2e/long_running/test_code_review_workload.py`

- [ ] Implement code review workload test
  - Load 50 Python files from src/kaizen/
  - First pass: Ollama syntax analysis (free)
  - Second pass: gpt-4o-mini quality validation (10 files)
  - Generate comprehensive review report
  - Checkpoint every 10 files
  - **LLM**: Ollama (40 files) + gpt-4o-mini (10 files)
  - **Duration**: 2-4 hours
  - **Cost**: $0.50
  - **Estimated Implementation**: 2-3 hours

- [ ] Run and validate test
  - Execute full test
  - Validate report quality
  - Check memory usage (no leaks)
  - Verify checkpoint creation
  - **Duration**: 2-4 hours

**Day 10 Total**: 1 test, 2-4 hours execution, $0.50, 3-4 hours implementation

---

## Week 3: Long-Running + Validation (Days 11-15)

### Day 11: Long-Running Test 2 - Data Analysis

**File**: `tests/e2e/long_running/test_data_analysis_workload.py`

- [ ] Implement data analysis workload test
  - Generate 10 CSV files (100k rows each)
  - Statistical analysis with Ollama
  - Insight generation with gpt-4o-mini (20 analyses)
  - Create 20+ visualizations
  - Generate executive summary
  - **LLM**: Ollama (data processing) + gpt-4o-mini (insights)
  - **Duration**: 2-4 hours
  - **Cost**: $1.00
  - **Estimated Implementation**: 2-3 hours

- [ ] Run and validate test
  - Execute full test
  - Validate visualizations created
  - Check report quality
  - Verify no crashes
  - **Duration**: 2-4 hours

**Day 11 Total**: 1 test, 2-4 hours execution, $1.00, 2-3 hours implementation

---

### Day 12: Long-Running Test 3 - Research

**File**: `tests/e2e/long_running/test_research_workload.py`

- [ ] Implement research workload test
  - Load 100 markdown files from docs/
  - Extract key information with Ollama
  - Synthesize findings with gpt-4o-mini (30 summaries)
  - Generate research report >5000 words
  - Create citation index
  - Checkpoint every 20 documents
  - **LLM**: Ollama (extraction) + gpt-4o-mini (synthesis)
  - **Duration**: 2-4 hours
  - **Cost**: $1.50
  - **Estimated Implementation**: 2-3 hours

- [ ] Run and validate test
  - Execute full test
  - Validate cross-references
  - Check report length >5000 words
  - Verify checkpoint frequency
  - **Duration**: 2-4 hours

**Day 12 Total**: 1 test, 2-4 hours execution, $1.50, 2-3 hours implementation

---

### Days 13-14: Validation (3 Consecutive Clean Runs)

**Run 1** (Day 13 Morning)
- [ ] Execute all 20+ E2E tests
  - `pytest tests/e2e/autonomy/ -v --timeout=300`
  - **Duration**: 20-40 minutes
  - **Cost**: $0.40
- [ ] Record results
  - Pass/fail for each test
  - Flaky test detection
  - Performance metrics
- [ ] Fix any issues
  - Address flaky tests
  - Fix assertion errors
  - Improve reliability

**Run 2** (Day 13 Afternoon)
- [ ] Execute all 20+ E2E tests (second run)
  - **Duration**: 20-40 minutes
  - **Cost**: $0.40
- [ ] Compare with Run 1
  - Identify remaining flaky tests
  - Validate fixes
- [ ] Additional fixes if needed

**Run 3** (Day 14 Morning)
- [ ] Execute all 20+ E2E tests (third run)
  - **Duration**: 20-40 minutes
  - **Cost**: $0.40
- [ ] Final validation
  - All tests pass
  - No flaky tests detected
  - Performance within limits

**Cost Validation** (Day 14 Afternoon)
- [ ] Calculate total cost across all runs
  - Week 1-2: $0.50
  - 3 validation runs: $1.20
  - 3 long-running tests: $3.00
  - **Total**: $4.70 (well under $20 budget)
- [ ] Generate cost report
- [ ] Verify cost tracking accuracy

**Days 13-14 Total**: 3 validation runs, 1-2 hours execution, $1.20

---

### Day 15: CI Integration + Documentation

**CI Integration**

- [ ] Create `.github/workflows/e2e-tests.yml`
  - Short E2E tests on PR (20+ tests)
  - Long-running tests on nightly schedule
  - Cost reporting
  - **Estimated**: 1-2 hours

- [ ] Test CI workflow
  - Create test PR
  - Validate short tests run
  - Check cost reporting
  - **Estimated**: 1 hour

**Documentation**

- [ ] Create `tests/E2E_EXECUTION_GUIDE.md`
  - How to run E2E tests locally
  - Infrastructure setup requirements
  - Cost tracking instructions
  - Troubleshooting guide
  - **Estimated**: 2-3 hours

- [ ] Update main documentation
  - Add E2E testing section to docs
  - Reference new test files
  - **Estimated**: 1 hour

**Day 15 Total**: 4-7 hours

---

## Summary Checklist

### Tests Created
- [ ] 12 Tool Calling tests (builtin, custom, approval, dangerous)
- [ ] 5 Planning tests (Planning Agent, PEV, ToT)
- [ ] 3 Meta-Controller tests (routing, fallback, decomposition)
- [ ] 7 Memory tests (hot, warm, cold, persistence)
- [ ] 5 Checkpoint tests (auto, resume, compression)
- [ ] 4 Interrupt tests (Ctrl+C, timeout, budget)
- [ ] 3 Long-Running tests (code review, data analysis, research)

**Total**: 39 tests

### Infrastructure Created
- [ ] 3 Utility modules (cost tracking, reliability, long-running)
- [ ] 4 E2E fixture files (code review, data analysis, research, approval)
- [ ] Enhanced conftest.py with E2E fixtures

### CI/Documentation
- [ ] GitHub Actions workflow for E2E tests
- [ ] E2E execution guide
- [ ] Cost reports

### Validation
- [ ] 3 consecutive clean runs (no flakes)
- [ ] Total cost <$20 (projected $4.70)
- [ ] All tests pass with timeout guards
- [ ] No memory leaks detected

---

## Cost Summary

| Category | Tests | Estimated Cost |
|----------|-------|----------------|
| Week 1 E2E (Tools, Planning, Memory) | 27 | $0.40 |
| Week 2 E2E (Checkpoints, Interrupts) | 9 | $0.10 |
| Long-Running (Code, Data, Research) | 3 | $3.00 |
| Validation Runs (3x) | 36 | $1.20 |
| **TOTAL** | **39** | **$4.70** |

**Budget**: $20.00
**Projected**: $4.70
**Under Budget**: $15.30 (76%)

---

## Next Action

**Ready to begin implementation?**

Recommended starting point:
1. Create directory structure
2. Implement utility modules (cost tracking, reliability, long-running)
3. Create E2E fixtures
4. Start Day 1: Tool calling tests

**Command to create directories**:
```bash
cd tests/e2e/autonomy
mkdir -p tools planning meta_controller memory checkpoints
cd ../..
mkdir -p long_running fixtures/e2e
```

**First file to implement**: `tests/utils/cost_tracking.py`

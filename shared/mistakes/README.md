# Kailash SDK - Mistakes Index

Quick reference for finding documented mistakes and solutions. Each mistake has its own detailed file.

## 🔍 Quick Lookup by Error Message

| Error | File | Fix |
|-------|------|-----|
| `NameError: name 'NameError' is not defined` (PythonCodeNode) | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Use bare except clauses |
| `NameError: name 'globals' is not defined` (PythonCodeNode) | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Add to allowed_builtins |
| `NameError: name 'open' is not defined` (PythonCodeNode) | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Add to allowed_builtins |
| `Code contains unsafe operations: Import of module 'os' is not allowed` | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Add to ALLOWED_MODULES |
| `WorkflowValidationError: Node missing required inputs` (with input_types) | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Map all params in cycles |
| `TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'` | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Add `name` parameter first |
| `NameError: name 'kwargs' is not defined` (PythonCodeNode) | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Use direct variable names |
| `TypeError: Workflow.connect() got an unexpected keyword argument 'output_key'` | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Remove `output_key`, use mapping |
| `WARNING: Expression evaluation failed: name 'converged' is not defined` | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Fix convergence_check format |
| `AssertionError: 1 >= 2` (cycle iterations) | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Relax iteration count assertions |
| `NameError: name 'data' is not defined` (multi-node) | [065](065-multi-node-input-aggregation-without-merge.md) | Use MergeNode pattern |
| `Input type not allowed: <class 'NoneType'>` (multi-input) | [065](065-multi-node-input-aggregation-without-merge.md) | Use MergeNode pattern |
| `Complex 5+ node workflow for simple MCP usage` | [064](064-mcp-client-as-separate-node.md) | Use LLMAgent with built-in MCP |
| `TypeError: Object of type DataFrame is not JSON serializable` | [068](068-pythoncode-dataframe-serialization.md) | Use `.to_dict('records')` |
| `AttributeError: module 'numpy' has no attribute 'string_'` | [069](069-numpy-version-compatibility.md) | Use `np.bytes_` instead |
| `AttributeError: module 'numpy' has no attribute 'float128'` | [069](069-numpy-version-compatibility.md) | Check with `hasattr()` |
| `TypeError: data is not a valid config parameter` | [053](053-confusion-between-configuration-and-runtime-parameters.md) | Use runtime parameters |
| `RuntimeError: unhandled errors in a TaskGroup` | [002](002-async-node-usage.md) | Use AsyncNode |
| `AttributeError: 'Workflow' object has no attribute 'add'` | [056](056-inconsistent-connection-apis-between-workflow-and-workflowbuilder.md) | Use workflow.add_node() |
| `KeyError: 'node_state'` | [060](060-incorrect-cycle-state-access-patterns.md) | Use `.get()` with default |
| `AssertionError: 7 != 5` | [061](061-overly-rigid-test-assertions-for-cycles.md) | Use range assertions |
| `ValueError: Required parameter 'input_data' not provided` (SwitchNode) | [072](072-switchnode-mapping-specificity.md) | Use `{"output": "input_data"}` mapping |
| `KeyError: 'results'` (cycle state) | [073](073-cycle-state-persistence-assumptions.md) | Use state fallbacks and defaults |
| `assert 1 >= 3` (cycle state not persisting) | [074](074-generic-output-mapping-in-cycles.md) | Use specific field mapping, not `{"output": "output"}` |
| `assert 0.0 >= 0.7` (quality score not improving) | [074](074-generic-output-mapping-in-cycles.md) | Use specific field mapping, not `{"output": "output"}` |
| `assert 10 == 45` (accumulation failing in cycles) | [074](074-generic-output-mapping-in-cycles.md) | Use specific field mapping, not `{"output": "output"}` |
| `WorkflowValidationError: No source nodes found` | [049](049-missing-data-source-nodes-in-workflow-design.md) | Add source or use parameters |
| `NodeConfigurationError: Required parameter 'data' not provided` | [011](011-cycle-aware-nodes-parameter-passing.md) | Use `required=False` with defaults |
| `ValidationError: Input should be a type [Union[float, int]]` | [011](011-cycle-aware-nodes-parameter-passing.md) | Use simple types only |

## 📑 Browse by Category

### Critical Issues
- [001](001-config-vs-runtime.md) - Config vs Runtime Parameters ⚠️
- [002](002-async-node-usage.md) - Async Node Usage ⚠️

### Architecture & Design (10-24, 33-34)
- [010](010-mixed-state-management-patterns.md) - Mixed State Management
- [011](011-incomplete-abstract-method-implementation.md) - Incomplete Abstract Methods
- [012](012-registry-pattern-misuse.md) - Registry Pattern Misuse
- [021](021-node-connection-validation.md) - Node Connection Validation
- [022](022-resource-cleanup-issues.md) - Resource Cleanup
- [023](023-parallel-execution-race-conditions.md) - Parallel Execution Race
- [033](033-god-classes-functions.md) - God Classes/Functions
- [034](034-circular-dependencies.md) - Circular Dependencies

### Testing (3-8, 28-30, 43-44)
- [003](003-test-parameter-mismatch.md) - Test Parameter Mismatch
- [004](004-mock-object-configuration-errors.md) - Mock Configuration
- [005](005-async-test-configuration-issues.md) - Async Test Config
- [006](006-lambda-closure-issues-in-tests.md) - Lambda Closures
- [007](007-workflow-validation-errors.md) - Workflow Validation
- [008](008-run-id-management-conflicts.md) - Run ID Conflicts
- [028](028-insufficient-test-coverage.md) - Test Coverage
- [029](029-test-environment-isolation.md) - Test Isolation
- [030](030-mock-leakage-between-tests.md) - Mock Leakage
- [043](043-flaky-tests-due-to-timing.md) - Flaky Tests
- [044](044-testing-external-dependencies.md) - External Dependencies

### Workflow & Execution (49, 54-56, 65-67)
- [049](049-missing-data-source-nodes-in-workflow-design.md) - Missing Data Sources
- [054](054-workflow-execution-input-parameter-confusion.md) - Execution Input Confusion
- [055](055-assumption-that-workflows-must-start-with-source-nodes.md) - Workflow Start Assumptions
- [056](056-inconsistent-connection-apis-between-workflow-and-workflowbuilder.md) - Connection API Inconsistency
- [065](065-multi-node-input-aggregation-without-merge.md) - Multi-Node Input Aggregation ⚠️
- [066](066-phase-6-3-cycle-test-implementation-mistakes.md) - Cycle Test Implementation ⚠️
- [067](067-phase-6-3-completion-pythoncode-execution-environment.md) - PythonCodeNode Execution Environment ⚠️
- [074](074-generic-output-mapping-in-cycles.md) - Generic Output Mapping in Cycles ⚠️

### Configuration & Parameters (1, 20, 53, 58)
- [001](001-config-vs-runtime.md) - Config vs Runtime ⚠️
- [020](020-configuration-parameter-validation.md) - Config Validation
- [053](053-confusion-between-configuration-and-runtime-parameters.md) - Config/Runtime Confusion
- [058](058-node-configuration-vs-runtime-parameters-confusion.md) - Node Config vs Runtime

### Error Handling (25, 50)
- [025](025-missing-error-documentation.md) - Missing Error Docs
- [050](050-bare-except-clauses.md) - Bare Except Clauses

### Async/Await (2, 5, 18, 41-42)
- [002](002-async-node-usage.md) - Async Node Usage ⚠️
- [005](005-async-test-configuration-issues.md) - Async Test Config
- [018](018-blocking-operations-in-async-context.md) - Blocking in Async
- [041](041-forgetting-to-await-async-functions.md) - Forgetting Await
- [042](042-mixing-sync-and-async-code-incorrectly.md) - Mixing Sync/Async

### Performance (16-17, 37-38)
- [016](016-memory-leaks-in-long-running-processes.md) - Memory Leaks
- [017](017-inefficient-data-processing.md) - Inefficient Processing
- [037](037-n-plus-one-query-problems.md) - N+1 Queries
- [038](038-inefficient-data-structures.md) - Inefficient Data Structures

### Security (35-36)
- [035](035-input-validation-vulnerabilities.md) - Input Validation
- [036](036-path-traversal-vulnerabilities.md) - Path Traversal

### Data Handling (13-15, 68-70)
- [013](013-json-serialization-failures.md) - JSON Serialization
- [014](014-type-validation-issues.md) - Type Validation
- [015](015-schema-mismatch-issues.md) - Schema Mismatch
- [068](068-pythoncode-dataframe-serialization.md) - DataFrame Serialization ⚠️
- [069](069-numpy-version-compatibility.md) - NumPy Version Compatibility ⚠️
- [070](070-data-science-workflow-patterns.md) - Data Science Workflow Patterns

### Code Organization (9, 31-32, 51)
- [009](009-file-path-inconsistencies.md) - File Path Issues
- [031](031-inconsistent-naming-conventions.md) - Naming Conventions
- [032](032-node-component-naming-without-node-suffix.md) - Missing Node Suffix
- [051](051-unused-variables-in-examples.md) - Unused Variables

### Cyclic Workflows (57-63, 071-073, 045, 011)
- [045](045-cyclic-workflow-fundamental-issues.md) - Cyclic Workflow Fundamental Issues ⚠️
- [057](057-missing-cycle-flag.md) - Missing Cycle Flag
- [059](059-creating-unintended-workflow-cycles.md) - Unintended Cycles
- [060](060-incorrect-cycle-state-access-patterns.md) - Cycle State Access
- [061](061-overly-rigid-test-assertions-for-cycles.md) - Rigid Cycle Tests
- [062](062-cyclic-parameter-propagation-failure.md) - Parameter Propagation ⚠️
- [063](063-cyclic-parameter-propagation-multi-fix.md) - Cyclic Parameter Multi-Fix
- [071](071-cyclic-workflow-parameter-passing-patterns.md) - Parameter Passing Patterns ⚠️
- [072](072-switchnode-mapping-specificity.md) - SwitchNode Mapping Issues ⚠️
- [073](073-cycle-state-persistence-assumptions.md) - State Persistence Assumptions
- [074](074-generic-output-mapping-in-cycles.md) - Generic Output Mapping Fails ⚠️
- [011](011-cycle-aware-nodes-parameter-passing.md) - Cycle-Aware Node Parameter Issues

### API Design (64, 77)
- [064](064-mcp-client-as-separate-node.md) - MCP Client as Separate Node ⚠️
- [077](077-pythoncode-string-blocks-vs-from-function.md) - PythonCodeNode String vs from_function() ⚠️

### Other Categories
- **Documentation**: [024](024-inconsistent-documentation.md), [039](039-insufficient-logging.md), [040](040-missing-metrics-collection.md)
- **Integration**: [019](019-missing-optional-dependencies.md), [026](026-api-version-compatibility.md), [027](027-database-connection-management.md)
- **Environment**: [045](045-platform-specific-code.md), [046](046-missing-environment-configuration.md)
- **Process**: [047](047-insufficient-code-review.md), [048](048-technical-debt-accumulation.md), [052](052-pytorch-model-eval-false-positive.md)

## 📋 Adding New Mistakes
1. Create file: `NNN-short-description.md` (next sequential number)
2. Use [template.md](template.md) format
3. Add entry to relevant category above

---
Total: 74 documented mistakes | Most common: Config/Runtime confusion

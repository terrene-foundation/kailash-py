# Migration Plan

## 1. Overview

This plan covers the full 18-24 month migration from Kailash SDK v1.x (pure Python) to
SDK v2.0 (Rust core + multi-language SDKs). The plan is structured in 5 phases with clear
milestones, staffing requirements, and risk mitigation strategies.

## 2. Phase Overview

```
Month:  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21
Phase:  |-----Phase 1-------|--Phase 2--|----Phase 3----|----Phase 4----|--P5--|
        |  Rust Core (6mo)  | Python   |   Go SDK     |   Java SDK    | Stab |
        |                   | Binding  |   (4mo)      |   (4mo)       | (3mo)|
        |                   | (3mo)    |              |               |      |
```

## 3. Phase 1: Rust Core (Months 1-6)

### 3.1 Goals

- Implement the shared Rust core library (`kailash-core`)
- Build C-compatible FFI layer (`kailash-ffi`)
- Achieve feature parity with Python networkx-based implementation
- Comprehensive test suite with benchmarks

### 3.2 Monthly Milestones

**Month 1: Foundation**

- Set up Cargo workspace with crate structure
- Implement `WorkflowGraph` data structure (add_node, connect, remove)
- Implement topological sort (Kahn's algorithm)
- Unit tests for graph operations
- CI pipeline with multi-platform builds

**Month 2: Scheduling & Cycles**

- Implement level-based execution scheduling
- Implement Tarjan's SCC for cycle detection
- Implement cycle group management and iteration tracking
- Implement input routing computation
- Benchmark suite with `criterion`

**Month 3: Validation & Resources**

- Implement workflow structure validation
- Implement connection type validation
- Implement parameter completeness checking
- Implement resource limit checking (via `sysinfo`)
- Implement `ResourceManager`

**Month 4: Trust & Execution**

- Implement trust chain verification (SHA-256 chains)
- Implement trust posture computation
- Implement execution engine with callback mechanism
- Implement conditional execution (route_data, skip_branches)
- Integration tests for full execution flow

**Month 5: FFI Layer**

- Implement C-compatible FFI in `kailash-ffi`
- Generate C headers with `cbindgen`
- Implement opaque handle pattern for memory safety
- Implement callback registration mechanism
- Cross-platform testing (Linux, macOS, Windows)

**Month 6: Polish & Documentation**

- Performance optimization (cache tuning, allocation reduction)
- API documentation (rustdoc)
- Architecture decision records
- Cross-platform build verification
- Release `kailash-core` v0.1.0

### 3.3 Staffing

| Role                 | Count | Skills                         | Duration      |
| -------------------- | ----- | ------------------------------ | ------------- |
| Rust Engineer (Lead) | 1     | Rust, FFI, systems programming | Full 6 months |
| Rust Engineer        | 1     | Rust, graph algorithms         | Months 1-4    |
| DevOps Engineer      | 0.5   | CI/CD, cross-compilation       | Months 1, 5-6 |

### 3.4 Deliverables

- `kailash-core` crate: ~10K LOC Rust
- `kailash-ffi` crate: ~3K LOC Rust
- Test suite: ~5K LOC (300+ tests)
- Benchmark suite: ~1K LOC
- Pre-built binaries for 5 platforms

## 4. Phase 2: Python Binding (Months 7-9)

### 4.1 Goals

- Integrate Rust core into existing Python SDK via PyO3
- Maintain 100% backward compatibility
- Achieve 7x performance improvement in SDK overhead
- Zero code changes required in DataFlow, Nexus, Kaizen

### 4.2 Monthly Milestones

**Month 7: PyO3 Bindings**

- Build `kailash-python` crate with PyO3
- Implement `PyWorkflowGraph` wrapper
- Implement `_kailash_rust` extension module
- Feature flag: `KAILASH_USE_RUST=1`
- Comparison test framework (both backends)

**Month 8: Integration & Parity**

- Integrate Rust backend into `workflow/graph.py`
- Integrate Rust scheduler into `runtime/local.py`
- Integrate Rust validator into `workflow/validation.py`
- networkx compatibility shim (`_NetworkXCompat`)
- Run full existing test suite against Rust backend

**Month 9: Switchover & Release**

- Make Rust backend the default
- Deprecate networkx dependency
- Performance benchmarking and regression tests
- Documentation updates
- Release `kailash` v2.0.0-beta

### 4.3 Staffing

| Role                 | Count | Skills                 | Duration      |
| -------------------- | ----- | ---------------------- | ------------- |
| Rust/Python Engineer | 1     | PyO3, Python internals | Full 3 months |
| Python Engineer      | 1     | Kailash SDK, testing   | Months 7-8    |
| QA Engineer          | 0.5   | Python testing, CI     | Month 9       |

### 4.4 Deliverables

- `kailash-python` crate: ~2K LOC Rust
- Python integration changes: ~1K LOC modified
- Comparison tests: ~2K LOC
- Performance benchmarks: ~500 LOC
- PyPI wheels for 5 platforms

## 5. Phase 3: Go SDK (Months 10-13)

### 5.1 Goals

- Build Go SDK with idiomatic Go patterns
- Implement DataFlow-Go, Nexus-Go, Kaizen-Go
- CGo bindings to shared Rust core
- Comprehensive test suite and documentation

### 5.2 Monthly Milestones

**Month 10: Core Bindings & Workflow**

- CGo bindings to `kailash-ffi`
- Go WorkflowBuilder and LocalRuntime
- Callback mechanism (Go -> Rust -> Go)
- Basic node system (Node interface, registry)
- Unit tests for core bindings

**Month 11: DataFlow-Go**

- Model definition via struct tags
- CRUD operations wrapping `database/sql`
- PostgreSQL and SQLite drivers
- Bulk operations
- Filter system

**Month 12: Nexus-Go**

- Handler registration and middleware
- REST API channel (wrapping `net/http`)
- CLI channel
- MCP channel
- Auth plugin with JWT

**Month 13: Kaizen-Go & Release**

- Agent implementation wrapping `go-openai`
- Tool registration and memory
- Anthropic provider
- Documentation and examples
- Release `kailash-go` v0.1.0

### 5.3 Staffing

| Role               | Count | Skills              | Duration      |
| ------------------ | ----- | ------------------- | ------------- |
| Go Engineer (Lead) | 1     | Go, CGo, API design | Full 4 months |
| Go Engineer        | 1     | Go, database, web   | Months 11-13  |
| Rust Engineer      | 0.25  | CGo header support  | Month 10      |

### 5.4 Deliverables

- Go SDK: ~19K LOC
- Test suite: ~5K LOC
- Documentation: User guide, API reference
- Examples: 10+ working examples
- Pre-built Rust libraries for Go platforms

## 6. Phase 4: Java SDK (Months 14-17)

### 6.1 Goals

- Build Java SDK with Spring Boot integration
- Implement DataFlow-Java, Nexus-Java, Kaizen-Java
- JNI bindings to shared Rust core
- Maven Central publication

### 6.2 Monthly Milestones

**Month 14: Core Bindings & Workflow**

- JNI bindings via `jni` crate
- Native library loader
- Java WorkflowBuilder and LocalRuntime
- AsyncRuntime with CompletableFuture
- JUnit test suite

**Month 15: DataFlow-Java**

- Annotation-based model definition
- CRUD operations wrapping JDBC
- HikariCP connection pooling
- Bulk operations and filters
- Spring Data repository interface

**Month 16: Nexus-Java & Spring Boot**

- Handler registration and middleware
- REST API channel (Jakarta Servlet / Spring MVC)
- CLI and MCP channels
- Auth plugin
- Spring Boot auto-configuration starters

**Month 17: Kaizen-Java & Release**

- Agent implementation with LangChain4j
- Spring AI integration
- Tool registration and memory
- Documentation and examples
- Release to Maven Central

### 6.3 Staffing

| Role                 | Count | Skills                 | Duration      |
| -------------------- | ----- | ---------------------- | ------------- |
| Java Engineer (Lead) | 1     | Java, JNI, Spring Boot | Full 4 months |
| Java Engineer        | 1     | Java, JDBC, Spring     | Months 15-17  |
| Rust Engineer        | 0.25  | JNI crate support      | Month 14      |

### 6.4 Deliverables

- Java SDK: ~24K LOC
- Test suite: ~5K LOC
- Spring Boot starters: 4 modules
- Maven Central artifacts
- Documentation: User guide, Javadoc

## 7. Phase 5: Stabilization (Months 18-20)

### 7.1 Goals

- Cross-language equivalence verification
- Performance optimization across all SDKs
- Documentation completion
- Community readiness (migration guides, tutorials)

### 7.2 Activities

**Month 18: Cross-Language Testing**

- Implement cross-language equivalence test suite
- Same workflow, same inputs -> verify same outputs across Python/Go/Java
- FFI boundary stress testing (10K+ workflow executions)
- Memory leak detection across all language bindings

**Month 19: Optimization & Polish**

- Performance profiling across all SDKs
- Optimization for identified bottlenecks
- API consistency review across languages
- Edge case testing (large workflows, deep cycles, many connections)

**Month 20: Documentation & Release**

- Migration guide for existing Python SDK users
- Language-specific getting started guides
- API reference for all three languages
- Blog posts and announcement preparation
- SDK v2.0 GA release

### 7.3 Staffing

| Role             | Count | Duration      |
| ---------------- | ----- | ------------- |
| Technical Lead   | 1     | Full 3 months |
| QA Engineer      | 1     | Full 3 months |
| Technical Writer | 0.5   | Months 19-20  |
| DevOps Engineer  | 0.25  | Month 20      |

## 8. Staffing Summary

### 8.1 Total Staffing by Phase

| Phase                   | Duration      | Engineering FTEs | Total Person-Months   |
| ----------------------- | ------------- | ---------------- | --------------------- |
| Phase 1: Rust Core      | 6 months      | 2.5              | 15                    |
| Phase 2: Python Binding | 3 months      | 2.5              | 7.5                   |
| Phase 3: Go SDK         | 4 months      | 2.25             | 9                     |
| Phase 4: Java SDK       | 4 months      | 2.25             | 9                     |
| Phase 5: Stabilization  | 3 months      | 2.75             | 8.25                  |
| **Total**               | **20 months** |                  | **~49 person-months** |

### 8.2 Skill Requirements

| Skill                    | Critical? | Phases     |
| ------------------------ | --------- | ---------- |
| Rust (systems, FFI)      | YES       | 1, 2, 3, 4 |
| Python (internals, PyO3) | YES       | 2          |
| Go (CGo, stdlib)         | YES       | 3          |
| Java (JNI, Spring)       | YES       | 4          |
| Graph algorithms         | YES       | 1          |
| CI/CD, cross-compilation | YES       | All        |
| Technical writing        | Helpful   | 5          |

### 8.3 Hiring Strategy

- **Rust Lead**: Hire first (Month -1). Critical path.
- **Language specialists**: Can be contractors (3-4 month engagements).
- **QA**: Can overlap with Phase 2-4 work.
- **DevOps**: Part-time throughout, full-time in Phase 1 and 5.

## 9. Risk Mitigation

### 9.1 Technical Risks

| Risk                                | Probability | Impact | Mitigation                                                               |
| ----------------------------------- | ----------- | ------ | ------------------------------------------------------------------------ |
| FFI performance worse than expected | Low         | High   | Benchmark early (Month 2), optimize before Phase 2                       |
| PyO3 compatibility issues           | Medium      | Medium | Test with Python 3.11-3.13, pin PyO3 version                             |
| CGo callback complexity             | Medium      | Medium | Prototype in Month 1, validate approach early                            |
| JNI memory management issues        | Medium      | Medium | Use JNI 0.21+ with improved safety, integration tests with LeakSanitizer |
| Cross-platform build failures       | Medium      | Low    | CI matrix from Day 1, Docker-based builds                                |
| networkx behavior differences       | Low         | High   | 500+ comparison tests before switchover                                  |

### 9.2 Schedule Risks

| Risk                                       | Probability | Impact | Mitigation                                                 |
| ------------------------------------------ | ----------- | ------ | ---------------------------------------------------------- |
| Rust core takes longer than 6 months       | Medium      | High   | Reduce scope: trust and resource management can be Phase 5 |
| Framework adaptation harder than expected  | Low         | Medium | Minimize public API changes, use internal substitution     |
| Hiring delays for Rust engineer            | High        | High   | Start recruiting 2 months before Phase 1                   |
| Cross-language testing reveals deep issues | Medium      | Medium | Buffer in Phase 5 (3 months, can extend to 4)              |

### 9.3 Business Risks

| Risk                                      | Probability | Impact | Mitigation                                            |
| ----------------------------------------- | ----------- | ------ | ----------------------------------------------------- |
| Existing Python users resist migration    | Low         | Medium | Zero breaking changes in Python API, opt-in Rust      |
| Go/Java SDKs have low adoption            | Medium      | Low    | Focus on Python first, Go/Java are incremental        |
| Competitor ships multi-language SDK first | Low         | Medium | Our depth (DataFlow, Nexus, Kaizen) is differentiator |

## 10. Backward Compatibility Guarantees

### 10.1 Python SDK v2.0

- **API Compatibility**: 100%. All existing `WorkflowBuilder`, `LocalRuntime`,
  `AsyncLocalRuntime`, `Node`, `AsyncNode` APIs preserved.
- **Behavior Compatibility**: 100%. Same inputs produce same outputs.
- **Import Compatibility**: 100%. All `from kailash.*` imports work unchanged.
- **Exception Compatibility**: 100%. Same exception types raised.
- **Framework Compatibility**: 100%. DataFlow, Nexus, Kaizen require zero changes.

### 10.2 What Changes in Python v2.0

- `networkx` moves from required to optional dependency
- `kailash-core` (Rust binary wheel) becomes a required dependency
- Performance improves 7x for SDK overhead
- Memory usage decreases 10x for graph operations
- New env var: `KAILASH_USE_RUST=0` to force networkx fallback (deprecated)

### 10.3 Migration Guide for Python Users

```python
# Before (v1.x) - STILL WORKS IN v2.0
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeType", "id", {"param": "value"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# After (v2.0) - SAME CODE, FASTER
# No changes needed! The Rust core is used automatically.
# To verify: check runtime._use_rust == True
```

## 11. Success Criteria

### 11.1 Phase 1 Exit Criteria

- [ ] All graph operations pass 300+ unit tests
- [ ] Topological sort matches networkx output for 100+ test graphs
- [ ] Benchmark: < 0.05ms for 20-node scheduling
- [ ] FFI builds on all 5 target platforms
- [ ] Architecture documented in ADRs

### 11.2 Phase 2 Exit Criteria

- [ ] 100% existing Python test suite passes with Rust backend
- [ ] Zero DataFlow/Nexus/Kaizen code changes required
- [ ] Performance: 7x improvement in SDK overhead
- [ ] Memory: 10x improvement in graph memory
- [ ] PyPI wheels published for all platforms

### 11.3 Phase 3 Exit Criteria

- [ ] Go SDK passes 200+ tests
- [ ] DataFlow-Go CRUD operations verified against PostgreSQL and SQLite
- [ ] Nexus-Go serves API requests, CLI commands, MCP tools
- [ ] Kaizen-Go agent completes LLM inference with OpenAI
- [ ] Cross-language test: Go output matches Python output for 50+ workflows

### 11.4 Phase 4 Exit Criteria

- [ ] Java SDK passes 200+ tests
- [ ] Spring Boot starters auto-configure correctly
- [ ] DataFlow-Java CRUD operations verified with JDBC
- [ ] Maven Central artifacts published
- [ ] Cross-language test: Java output matches Python/Go output

### 11.5 Phase 5 Exit Criteria

- [ ] All three SDKs produce identical outputs for 100+ test workflows
- [ ] No memory leaks detected in 10K-execution stress test
- [ ] Documentation complete for all three languages
- [ ] Migration guide reviewed and validated
- [ ] SDK v2.0 GA released

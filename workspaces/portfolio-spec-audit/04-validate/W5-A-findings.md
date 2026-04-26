# W5-A Findings — core + infra + node-catalog

**Specs audited:** 7
**§ subsections enumerated:** TBD (see per-spec sections)
**Findings:** CRIT=0 HIGH=0 MED=0 LOW=0 (running tally — updated per commit)
**Audit completed:** 2026-04-26
**Branch:** `audit/w5-a-core-spec-audit`
**Base SHA:** `6142ea52`
**Working tree:** `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/w5-a-core`

## Methodology

Per `.claude/skills/spec-compliance/SKILL.md`:

1. Each spec read in full.
2. Acceptance assertions extracted (class names, method signatures, exception types, BLOCKED patterns, security threats).
3. Each assertion verified via `Grep` (class/method names) + targeted `Read` (signature confirmation) against `src/` and `packages/`.
4. Findings classified CRIT/HIGH/MED/LOW per task brief.

## Severity Definitions

- **CRIT** — Security/governance contract claimed but absent (orphan facade per `rules/orphan-detection.md` §1)
- **HIGH** — Public API claimed but absent or signature-divergent
- **MED** — Internal helper or utility claimed but absent
- **LOW** — Naming/terminology drift, doc-only assertions

---

# Spec 1: `specs/core-nodes.md`

**Subsections audited:** §1.1 (Node ABC + 6 subsections), §1.2 (NodeParameter), §1.3 (NodeMetadata), §1.4 (NodeRegistry).
**Verification source:** `src/kailash/nodes/base.py` (2,700+ lines).

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class NodeMetadata(BaseModel)` exists at `kailash.nodes.base` | grep | match | line 44 | OK |
| `class NodeParameter(BaseModel)` exists | grep | match | line 77 | OK |
| `class Node(ABC)` exists | grep | match | line 152 | OK |
| `class NodeRegistry` exists | grep | match | line 2129 | OK |
| `Node._DEFAULT_CACHE_SIZE = 128` | grep | int 128 | line 191 (`= 128`) | OK |
| `Node._SPECIAL_PARAMS = {"context", "config"}` | grep | set | line 192 | OK |
| `Node._strict_unknown_params = False` | grep | False | line 193 | OK |
| `Node._env_cache: dict[str, str \| None] = {}` | grep | empty dict | line 194 | OK |
| `Node._clear_env_cache()` classmethod | grep | classmethod | line 208 | OK |
| `Node.id` property (getter + setter) | grep | both | lines 422, 435 | OK |
| `Node.metadata` property (getter + setter, type-routed) | grep | both | lines 448, 469 | OK |
| Abstract `get_parameters` | grep | abstractmethod | line 506 | OK |
| Abstract `run` | grep | abstractmethod | line 610 | OK |
| `get_output_schema` (optional, default `{}`) | grep | match | line 553 | OK |
| `get_workflow_context` | grep | match | line 373 | OK |
| `set_workflow_context` | grep | match | line 399 | OK |
| `_validate_config` invoked in `__init__` | grep | match | line 661 | OK |
| `validate_inputs` | grep | match | line 787 | OK |
| `execute` (orchestrator) | grep | match | line 1347 | OK |
| `NodeMetadata` fields: `id`, `name`, `description`, `version`, `author`, `created_at`, `tags` | Read | all 7 | lines 65–74 | OK |
| `NodeParameter` fields: `name`, `type`, `required`, `default`, `description`, `choices`, `enum`, `default_value`, `category`, `display_name`, `icon`, `input`, `output`, `auto_map_from`, `auto_map_primary`, `workflow_alias` | Read | all 16 | lines 112–149 | OK |
| `NodeRegistry.register` | grep | match | line 2189 | OK |

**Spec 1 findings:** 0 CRIT / 0 HIGH / 0 MED / 0 LOW.

Note: All claims in `core-nodes.md` are present in `src/kailash/nodes/base.py`. Class field counts and signatures match the spec verbatim. The spec accurately documents the implementation; no drift detected.

---

# Spec 2: `specs/core-workflows.md`

**Subsections audited:** §2.1 (WorkflowBuilder + 8 method subsections), §2.2 (Workflow + 5 subsections), §3.1 (Connection), §3.2 (CyclicConnection), §3.3 (NodeInstance), §3.4 (ConnectionContract), §3.5 (Data Flow Semantics), §8.1–§8.3 (Validation).
**Verification source:** `src/kailash/workflow/{builder,graph,contracts,validation,cycle_builder}.py`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class WorkflowBuilder` at `kailash.workflow.builder` | grep | match | builder.py:20 | OK |
| `WorkflowBuilder.add_node(*args, **kwargs) -> str` | grep | match | builder.py:200 | OK |
| `WorkflowBuilder.add_connection(from_node, from_output, to_node, to_input)` | grep | match | builder.py:536 | OK |
| `WorkflowBuilder.connect(from_node, to_node, mapping=...)` | grep | match | builder.py:656 | OK |
| `WorkflowBuilder.add_typed_connection(..., contract, validate_immediately=False)` | grep | match | builder.py:711 | OK |
| `WorkflowBuilder.set_metadata(**kwargs) -> WorkflowBuilder` | grep | match | builder.py:698 | OK |
| `WorkflowBuilder.validate_parameter_declarations(warn_on_issues=True)` | grep | match | builder.py:106 | OK |
| `WorkflowBuilder.build(workflow_id=None, **kwargs) -> Workflow` | grep | match | builder.py:901 | OK |
| `WorkflowValidationError`, `ConnectionError` imports from `kailash.sdk_exceptions` | grep | match | builder.py:8 | OK |
| `class Workflow` at `kailash.workflow.graph` | grep | match | graph.py:106 | OK |
| `Workflow.add_node(node_id, node_or_type, **config)` | grep | match | graph.py:233 | OK |
| `Workflow.connect(source_node, target_node, mapping, cycle, max_iterations, ...)` | grep | match | graph.py:331 | OK |
| `Workflow.get_node(node_id) -> Node \| None` | grep | match | graph.py:713 | OK |
| `Workflow.separate_dag_and_cycle_edges()` | grep | match | graph.py:733 | OK |
| `Workflow.get_cycle_groups() -> dict[str, list[tuple]]` | grep | match | graph.py:760 | OK |
| `Workflow.create_cycle(cycle_id=None)` | grep | match | graph.py:615 | OK |
| `class Connection(BaseModel)` at `kailash.workflow.graph` | grep | match | graph.py:72 | OK |
| `class CyclicConnection(Connection)` | grep | match | graph.py:81 | OK |
| `class NodeInstance(BaseModel)` | grep | match | graph.py:38 | OK |
| `NodeInstance._SENSITIVE_KEYS` (frozenset, includes api_key, password, token, secret, etc.) | grep | match | graph.py:42 | OK |
| `class ConnectionContract` at `kailash.workflow.contracts` | grep | match | contracts.py:51 | OK |
| `class SecurityPolicy(Enum)` at `kailash.workflow.contracts` | grep | match | contracts.py:28 | OK |
| `class ValidationIssue` at `kailash.workflow.validation` | grep | match | validation.py:135 | OK |
| `class IssueSeverity(Enum)` at `kailash.workflow.validation` | grep | match | validation.py:126 | OK |
| `class CycleBuilder` at `kailash.workflow.cycle_builder` | grep | match | cycle_builder.py:58 | OK |
| `class WorkflowDAG` at `kailash.workflow.dag` | grep | match | dag.py:141 | OK |

**Spec 2 findings:** 0 CRIT / 0 HIGH / 0 MED / 0 LOW.

Note: All workflow construction classes, connection types, contract types, and validation primitives are present at the spec-claimed module paths with the spec-claimed signatures.

---

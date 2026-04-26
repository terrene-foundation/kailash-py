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

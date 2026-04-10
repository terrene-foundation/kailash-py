# SPEC-04 Drift Inventory & Removal List — 2026-04-10

**Purpose**: After confirming the regression in `09-spec04-drift-verification.md` and `journal/0003-RISK-...`, this document gives a line-by-line disposition of the drift and a concrete removal list for Option A. Also: a feasibility verdict (trivial / tractable / tangled).

## TL;DR — Feasibility verdict

**Option A is TRIVIAL.** The 1,109-line regression is concentrated in a single deletable block. No byte-level conflict analysis is needed; there is zero functional code to preserve.

- Delete one contiguous 1,079-line block (`base_agent.py` lines 855–1933, the `# TOOL CALLING INTEGRATION - MCP Only` section)
- Preserve one 15-line bug fix (#357 Gemini structured output)
- Optionally drop 15 lines of decorative imports
- Result: `base_agent.py` goes from **2,103 → 1,024 LOC** (or 1,009 with the optional drop)

## Full diff decomposition

`git diff 1e39a061 HEAD -- base_agent.py` produces exactly **three hunks**. Every added line falls into one of these three groups; there is no drift outside them.

| Hunk | Old range | New range  | Δ lines   | What it is                                | Origin commit      | Disposition   |
| ---- | --------- | ---------- | --------- | ----------------------------------------- | ------------------ | ------------- |
| 1    | `29,10`   | `29,25`    | +15       | TYPE_CHECKING block + decorative comments | `7d237786` (merge) | Optional drop |
| 2    | `165,16`  | `180,31`   | +15       | #357 Gemini structured output fix         | `fca3b1fb`         | **KEEP**      |
| 3    | `821,7`   | `851,1086` | +1079     | Re-inlined MCPMixin methods (shadow code) | `7d237786` (merge) | **DELETE**    |
|      |           |            | **+1109** | (matches 2103 - 994)                      |                    |               |

### Hunk 1 — TYPE_CHECKING + comments (lines 29–53 in HEAD)

```python
# Core SDK imports                                                  # +1 comment
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
from kailash_mcp.client import MCPClient

# Type checking imports (not available at runtime in all environments)  # +1 comment
if TYPE_CHECKING:                                                    # +1
    try:                                                             # +1
        from kaizen.nodes.ai.a2a import (                            # +1
            A2AAgentCard,                                            # +1
            Capability,                                              # +1
            CollaborationStyle,                                      # +1
            PerformanceMetrics,                                      # +1
            ResourceRequirements,                                    # +1
        )                                                            # +1
    except ImportError:                                              # +1
        pass                                                         # +1

# Kaizen framework imports                                           # +1 comment
```

**Analysis**: These are `TYPE_CHECKING` imports — they don't execute at runtime. The types (`A2AAgentCard`, etc.) are not used by any method in the current HEAD `base_agent.py` (confirmed by grep). They were useful in the pre-slim 3681 LOC version where those type hints appeared in method signatures; after slimming those methods were moved to `a2a_mixin.py`, so the imports are now orphaned.

**Disposition**: Optional drop. Low-risk delete saves 15 lines. Keeping them has no functional effect. Recommendation: drop them for line-count target.

### Hunk 2 — #357 Gemini structured output fix (lines 180–210 in HEAD)

```python
# MCP initialization
# When mcp_servers is not specified (None), auto-inject the builtin       # +6 comment lines
# MCP server UNLESS the config requests structured output.  Gemini
# (and potentially other providers) reject requests that combine
# function calling with JSON response mode (response_mime_type).
# Structured output takes priority over auto-tool discovery.
# See: https://github.com/terrene-foundation/kailash-py/issues/357
if mcp_servers is None:
    if self.config.has_structured_output:                                 # +8 functional lines
        logger.debug(
            "MCP auto-discovery suppressed: config has structured output "
            "enabled (response_format=%s), which is incompatible with "
            "function calling on some providers (e.g. Gemini).",
            self.config.response_format,
        )
        self._mcp_servers = []
    else:
        self._mcp_servers = [ ... builtin kaizen server ... ]
```

**Analysis**: Introduced by `fca3b1fb` (full clearance). Resolves issue #357 — Gemini rejects requests combining function calling with `response_mime_type`. The fix suppresses auto-tool-discovery when the config requests structured output. The +15 lines include 6 comment lines documenting the rationale and 9 functional lines.

**Disposition**: **KEEP**. This is a legitimate bug fix with an upstream issue reference. Attempting to remove or slim it would require re-solving #357.

### Hunk 3 — Re-inlined MCPMixin methods (lines 855–1933 in HEAD)

A 1,079-line block starts at section header:

```python
# =============================================================================
# TOOL CALLING INTEGRATION - MCP Only
# =============================================================================
```

and ends before:

```python
# =========================================================================
# Observability
# =========================================================================
```

**14 methods in the block**:

| Method                        | Inline LOC | Mixin LOC | Δ   | Delta explanation                      |
| ----------------------------- | ---------- | --------- | --- | -------------------------------------- |
| `discover_tools`              | 35         | ?         | —   | Thin wrapper over `discover_mcp_tools` |
| `execute_tool`                | ?          | ?         | —   | Thin wrapper over `call_mcp_tool`      |
| `discover_mcp_tools`          | 119        | 86        | +33 | Verbose docstring with example         |
| `call_mcp_tool`               | 78         | 52        | +26 | Verbose docstring (md5-matched body)   |
| `execute_mcp_tool`            | 138        | 99        | +39 | Verbose docstring                      |
| `discover_mcp_resources`      | ?          | ?         | —   | Verbose docstring                      |
| `read_mcp_resource`           | ?          | ?         | —   | Verbose docstring                      |
| `discover_mcp_prompts`        | ?          | ?         | —   | Verbose docstring                      |
| `get_mcp_prompt`              | ?          | ?         | —   | Verbose docstring                      |
| `setup_mcp_client`            | ?          | ?         | —   | Verbose docstring                      |
| `expose_as_mcp_server`        | 116        | 71        | +45 | Verbose docstring                      |
| `_with_mcp_session`           | ?          | ?         | —   | Verbose docstring                      |
| `_convert_mcp_result_to_dict` | 98         | 68        | +30 | Verbose docstring                      |
| `has_mcp_support`             | 21         | 5         | +16 | `>>> Example:` block in docstring      |

**Every method is present in `mcp_mixin.py`** — verified by symmetric difference:

```
comm -12 methods-reinlined.txt methods-mcpmixin.txt  # = 14 methods (intersection = full set)
comm -23 methods-reinlined.txt methods-mcpmixin.txt  # = 0 methods (nothing unique to inline)
```

**The line-count difference between inline (1,079) and mixin (774) is explained entirely by docstring verbosity.** Spot-checks:

- `has_mcp_support` — 21 lines inline (16 lines are `>>> Example:` docstring), 5 lines mixin. Logic: `return self._mcp_servers is not None`. Identical.
- `call_mcp_tool` — first 50 lines of inline version md5-match the mixin version byte-for-byte.

**Disposition**: **DELETE ENTIRELY**. The mixin inheritance (`class BaseAgent(MCPMixin, A2AMixin, Node)`) is already present. Removing the inline shadows exposes the mixin methods via MRO. Zero functional code is lost. The only user-visible effect is: `help(agent.has_mcp_support)` will show the terser mixin docstring instead of the verbose example-rich one.

**Risk**: If any consumer has built tooling around the verbose docstrings (e.g., auto-generated docs that snapshot the inline version), they would see a docstring change on upgrade. This is a **documentation** concern, not a functional one.

## Proposed removal plan

### Step 1 — Delete the shadow block

```bash
# Remove lines 855-1933 (inclusive) of base_agent.py
# Result: 2103 → 1024 LOC
```

Concrete: delete from the `# TOOL CALLING INTEGRATION - MCP Only` section header through the last line before `# Observability` section header.

### Step 2 — Optionally drop Hunk 1 imports

```bash
# Remove the 15 decorative import lines (29-53 in current HEAD)
# Result: 1024 → 1009 LOC
```

### Step 3 — Add the line-count invariant test

```python
# tests/invariants/test_base_agent_line_count.py
import pathlib
import pytest

BASE_AGENT = pathlib.Path("packages/kailash-kaizen/src/kaizen/core/base_agent.py")
HARD_LIMIT = 1050  # see SPEC-04 §6 "line-count budget"

def test_base_agent_line_count_under_budget():
    """SPEC-04: base_agent.py MUST stay under budget. Regression guard."""
    loc = len(BASE_AGENT.read_text().splitlines())
    assert loc < HARD_LIMIT, (
        f"base_agent.py has grown to {loc} LOC (budget: <{HARD_LIMIT}). "
        f"This likely indicates a merge regression re-inlined mixin code. "
        f"See workspaces/platform-architecture-convergence/journal/"
        f"0003-RISK-spec04-silent-regression-via-parallel-merge.md"
    )
```

**Why `<1050` not `<1000`**: Gives ~26 LOC of headroom for legitimate fixes that may land between now and the next slimming pass. Matches the Option A final state of 1024 LOC. A stricter `<1000` would block legitimate bug fixes; a looser `<2000` would not catch the next regression.

### Step 4 — Run kaizen test suite

Expected result: all tests pass, because:

- Every deleted method is still resolved via `MCPMixin` inheritance
- Python's MRO prefers the first class in the bases list: `class BaseAgent(MCPMixin, A2AMixin, Node)` → `MCPMixin` wins
- The inline versions were shadowing the mixin (MRO was ignoring MCPMixin entirely for these methods), so deleting inline versions REVEALS the mixin

Risk: If any subclass explicitly calls `super()._convert_mcp_result_to_dict(...)` or similar, it was calling the inline version (MCPMixin wouldn't be in its MRO). After deletion, `super()` will find `MCPMixin` via the base class. Same interface, same logic — should be transparent.

### Step 5 — Close the remaining §10 security surfaces

Independent of the regression fix, the following SPEC-04 §10 surfaces are still open and should be closed in the same PR:

- **§10.2 `**kwargs`allowlist**:`base_agent.py:133`accepts`\*\*kwargs`. Replace with explicit allowlist + `\_DEPRECATED_PARAMETERS`filter +`UnknownParameterError`.
- **§10.3 Freeze `BaseAgentConfig`**: `config.py:37` is plain `@dataclass`. Add `frozen=True`. Private `_posture` copy per SPEC-04 TASK-04-06.

## What this means for the 53-task plan

With Option A, the following tasks from `todos/active/05-phase3-baseagent.md` are **already done** (from commits `626b008b` + `1e39a061`):

- TASK-04-03 — `agent_loop.py` module ✓
- TASK-04-04 — `BaseAgentConfig` frozen dataclass — PARTIAL (field added, frozen=True not applied)
- TASK-04-07 — `AgentPosture` helpers ✓
- TASK-04-15 — `@deprecated` decorator ✓
- TASK-04-16 — Apply `@deprecated` to 7 hooks ✓
- TASK-04-32 — `__init__` rewrite — PARTIAL (structure rewritten, `**kwargs` not removed)
- TASK-04-33..04-40 — BaseAgent slim phase ✓ (but regressed, needs restoration)
- SPEC-02 provider split — already done, not a SPEC-04 task

Tasks that become **new work** after Option A:

- **TASK-04-50 (upgraded)** — Add the line-count invariant test as the first action (prevents recurrence)
- **TASK-04-20..27** — `_DEPRECATED_PARAMETERS` filter + UnknownParameterError (§10.2) — not yet started
- **TASK-04-04 finalization** — freeze `BaseAgentConfig` (§10.3) — started, not finished
- **TASK-04-01** — Subclass audit (still useful; numbers may have changed)
- **TASK-04-48..49** — Posture tests + security tests §10.1-§10.5
- **TASK-04-51** — Migration guide — not yet started
- **TASK-04-52** — Cross-SDK issue — not yet started

Tasks that are **no longer relevant** (the spec assumed structures that no longer exist):

- TASK-04-28 `_build_messages` signature-first — `_build_messages` does not exist in current code
- TASK-04-24..27 `_deferred_mcp` tuple guard — `_deferred_mcp` does not exist; MCP is initialized directly
- Various TAOD-loop extraction tasks — already completed in `agent_loop.py`

Net new task count after Option A: approximately **20 tasks** (down from the claimed 53).

## For Discussion

1. **Why did the inline versions get verbose docstrings in the first place?** The `>>> Example:` blocks in `has_mcp_support` and friends look like they were added by a docstring-generation pass, probably as part of an earlier "documentation sprint." Someone saw `def has_mcp_support(self): return self._mcp_servers is not None` as "too terse" and wrote a 16-line example. This is a case study in how "well-intentioned documentation" creates regression fodder — the slimming pass correctly moved these methods to a mixin with terser docstrings, and the regression brought back the verbose originals. Does the project want a rule that says "docstrings live with the canonical implementation, not in wrappers"?

2. **Counterfactual: what if the regression had removed a method instead of duplicating one?** The current regression is "easy" because the mixin still has the canonical version — MRO hides the problem at runtime. If a future regression instead DELETES a mixin method from a worktree branch's stale base, the merge could silently remove a method from production. The line-count guard doesn't catch deletions — we need a method-count invariant too (`len(MCPMixin.__dict__) >= 14`), or a set-membership invariant (`{discover_mcp_tools, call_mcp_tool, ...} ⊆ dir(MCPMixin)`).

3. **Is 1024 LOC close enough to `<1000`?** The SPEC-04 target is `<1000 LOC`. Option A lands at 1024. Options: (a) accept the overage, document the 24-line deviation in the spec; (b) aggressively slim the `__init__` method to shed ~30 lines; (c) extract something else (e.g., the `_apply_*_mixin` methods at lines 311-353 that are just delegation shims — move to a `mixin_application.py` helper). (c) is cleanest and gives another extracted module to test independently. Which does the team prefer?

## See also

- `09-spec04-drift-verification.md` — the finding that led to this inventory
- `journal/0003-RISK-spec04-silent-regression-via-parallel-merge.md` — risk framing
- `packages/kailash-kaizen/src/kaizen/core/mcp_mixin.py` — the canonical home for the 14 shadow methods
- `/tmp/spec04-verify/` — extracted reference files (post-slim 925, post-deprecated 994, head 2103)

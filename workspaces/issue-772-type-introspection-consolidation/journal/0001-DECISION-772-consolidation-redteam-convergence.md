---
type: DECISION
date: 2026-06-06
created_at: 2026-06-06T00:00:00Z
author: agent
session_id: autonomize-redteam-2026-06-06
project: kailash-py / kailash-dataflow
topic: "#772 type-introspection consolidation — /redteam convergence receipt"
phase: redteam
tags: [dataflow, refactor, type-introspection, "772", redteam, convergence]
---

# DECISION — #772 type-introspection consolidation reached /redteam convergence

## What shipped (working tree, branch `refactor/772-consolidate-type-introspection`)

New `packages/kailash-dataflow/src/dataflow/core/type_introspection.py`:

- `union_non_none_args(annotation) -> list | None` — the SINGLE two-spelling
  Optional/Union detection primitive (`typing.Union`/`Optional` AND PEP 604 `X | None`).
- `strip_annotated(annotation)` — `Annotated[T, ...] -> T` (strict ADD; verified 3.12 API).

**10 caller-methods routed** through it (each keeps its own post-detection policy):
type_processor `_resolve_type` + `validate_field`; nodes `_normalize_type_annotation` +
`_normalize_id_type` + `_unwrap_optional_type`; engine `_python_type_to_sql_type`;
schema `_parse_field`; model_validator (×2); fk_aware `_is_nullable_field`; **model_registry
`_normalize_field_type` (the 10th site, found during redteam — see Round 1)**.

Root cause the consolidation closes: #1228 (PEP 604) had to patch the union-spelling check
in every site independently — the maintenance tax #772 predicted, now empirically confirmed.

## Round history (durable receipts per verify-resource-existence MUST-4)

| Round | Reviewer                                                                | Verdict         | Findings                                                                                                                                                                                                                                                                                                                |
| ----- | ----------------------------------------------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1    | orchestrator inline (AST sweep + per-site policy diff + behavior probe) | CHANGES → fixed | **1 MEDIUM**: `model_registry._normalize_field_type` was a 10th union-detection site (`isinstance(_, types.UnionType)`) the specialist's "same-unwrap" filter missed; AND the structural-invariant test used a SUBSTRING check (`"is types.UnionType"`) that did not catch the `isinstance` spelling → test blind spot. |
| R2    | security-reviewer (agent `ace1e3d70d2e23c66`)                           | **APPROVE**     | 0 CRIT/HIGH/MED/LOW. Confirmed `strip_annotated` purely additive (no constraint/classification metadata on annotations anywhere in src; `@classify` is class-decorator-based, orthogonal); no SQL-type-inference drift; PK-rejects-Optional preserved; no injection surface.                                            |
| R2    | correctness reviewer (agent `a688bd9f8cf6ad271`)                        | **APPROVE**     | 0 CRIT/HIGH/MED. Adversarially injected a re-inlined detection into schema.py → the AST invariant test FIRED (not theatre). model_registry verified byte-for-byte across 11 input classes. 3 non-blocking observations (disposed below).                                                                                |

Two prior redteam dispatches died on infrastructure (Workflow `wf_d40ee06d-961` + a 2-agent
parallel pass) — server-side rate-limit (`not your usage limit`) following a mid-session
account swap, NOT any finding. Re-dispatched single/sequential per worktree-isolation Rule 4
once the account recovered.

## R1 fix (the 10th site)

- `model_registry._normalize_field_type`: hoisted union detection to the top via
  `union_non_none_args`; removed `isinstance(_, types.UnionType)` + dead `import types` +
  `get_args` import. **Behavior preserved byte-for-byte** (probed all 7 prior outputs:
  Optional[int]/int|None→"Optional", str|int/Union[int,str,None]/int|str|None→"Union",
  list[str]→"list", str→"str").
- Structural-invariant test rewritten from substring (`"is types.UnionType"`) to **AST**
  (`ast.Attribute` attr=`UnionType`) — now catches every spelling AND ignores docstring/
  comment prose without special-casing. model_registry added to the routed-callers list.
  Behavioral coverage for the site added.
- engine.py dead `import types` removed (specialist routed its UnionType use but left the
  import — Ruff-clean now).
- model_validator.py:469 dead `origin = get_origin(...)` assignment removed (R2 obs 3).

## R2 non-blocking observations — dispositions

1. **Doc site-count** (plan says "9/TEN"): actual = 10 caller-methods / 12 raw call sites
   (two nodes.py methods detect twice; the #514 site). Cosmetic; recorded here.
2. **`strip_annotated` applied only at type_processor + nodes, not engine/schema/validators**:
   NOT a gap. The two reviews are complementary — the security-reviewer showed schema.py +
   model_validator.py read annotations via `get_type_hints(include_extras=False)`, which the
   stdlib ALREADY strips Annotated through before those sites see it; only the RAW field-dict
   paths (type_processor/nodes) ever receive `Annotated[...]`, which is exactly where the
   strip is placed. Adding it elsewhere would be dead code. Pre-#772 NO site stripped
   Annotated, so nodes/type_processor strictly improved; nothing regressed.
3. **model_validator.py:469 dead assignment**: FIXED (removed).

## Test receipts (verified, command-produced)

- `test_type_introspection.py` + `test_issue_772_*.py`: **74 passed**.
- Prior regressions #768/#1207/#1228: **39 passed** (kept green through the consolidated path).
- **Broad kailash-dataflow unit suite: 3513 passed, 17 skipped, 56 warnings** — identical to
  the pre-#772 baseline (zero regression; the 56 warnings are pre-existing — `MLTenantRequiredError`
  deprecation alias test + VAL-00x assertions).
- AST single-site: `union_non_none_args` def ×1 (`type_introspection.py:28`); `UnionType`
  ref ×1 (`type_introspection.py:52`). Invariant holds tree-wide.
- 20 failed / 19 errors in the `-k model_registry` integration run are pre-existing infra
  (`psycopg2.OperationalError: role "dataflow_test" does not exist`, port 5434 — no local PG).

## Pre-existing (NOT introduced; cite-pre-session-SHA per zero-tolerance Rule 1c)

- Pyright IDE diagnostics on nodes.py/engine.py/model_registry.py/model_validator.py/
  fk_aware (Node-shadowing, str|None arg-types, duck-typed attrs) — every flagged line is
  OUTSIDE the edit hunks; all six modules import cleanly; Ruff + the project pre-commit
  type-gate pass. Not gated by project CI; out of #772 scope.
- `fk_aware_model_integration.py` broken `migration_engine` import — unimportable on
  pristine main; pre-existing, out of scope.

## Outstanding (human-gated — surfaced to user)

1. GPG commit — `commit.gpgsign=true`; the operator key passphrase cannot be supplied
   non-interactively (subagent + main session both lack a TTY). Commit staged-ready.
2. kailash-dataflow version bump (2.11.2 → 2.11.3 patch) + PR + `/release` (BUILD-repo gate).
3. Issue hygiene: close #596 (obsolete, cite SHA 090c0e97a), update #643 status comment.

## For Discussion

1. Should `strip_annotated` be extended to engine/schema/validators for full Annotated parity
   even though `get_type_hints(include_extras=False)` already strips it there (dead code), to
   guard against a future caller that bypasses get_type_hints? (Disposition: no — YAGNI; zero
   Annotated field usage in src; revisit only if Annotated-field support is requested.)
2. The consolidation went BROADER than the plan's 4 named methods (10 caller-methods). Is the
   structural-invariant test (single `union_non_none_args` def + zero tree-wide `UnionType`
   refs) sufficient to prevent a future 11th site from re-inlining, given it caught the 10th
   only after the substring→AST strengthening?
3. #1228 patched the union check across 9 sites a month ago; #772 now consolidates 10. Should
   a follow-up extend the same single-primitive discipline to kailash-rs (different type
   system — Rust has no runtime Optional/Union introspection, so structurally N/A)?

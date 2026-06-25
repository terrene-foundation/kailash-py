# 0006 — DECISION — Naming aliases for #1035 acceptance gate

## Context

`/redteam` Round 1 analyst found 5 CRITICAL import-path mismatches between
the #1035 issue body (`Delegate, ConstraintEnvelope, GenesisRecord,
PostureState, AuditChain`) and the shipped names (`DelegateRuntime`,
`DelegateConstraintEnvelope`, `DelegateGenesisRecord`, `Posture`,
`AuditChainEngine`).

## Decision

Add 5 module-scope aliases in `src/kailash/delegate/__init__.py`.
Both forms work; prefixed names remain canonical.

| #1035 spec name       | Canonical (shipped) class name  |
| --------------------- | ------------------------------- |
| `Delegate`            | `DelegateRuntime`               |
| `ConstraintEnvelope`  | `DelegateConstraintEnvelope`    |
| `GenesisRecord`       | `DelegateGenesisRecord`         |
| `PostureState`        | `Posture`                       |
| `AuditChain`          | `AuditChainEngine`              |

`PrincipalDirectory` and `Connector` already shipped under their spec names;
no alias needed.

## Rationale

- The prefixed names are DELIBERATE disambiguation per the existing module
  docstring (`__init__.py:8-9`) — they prevent collision with
  `kaizen_agents.delegate.Delegate` (LLM execution facade).
- The unprefixed names satisfy the #1035 acceptance-criterion import line
  AND match the architecture plan §Goal verbatim.
- Aliases preserve BOTH constraints — disambiguation in new code + spec
  compliance for existing #1035 acceptance.
- Identity-aliases (`Delegate = DelegateRuntime`) mean
  `isinstance(x, Delegate) is isinstance(x, DelegateRuntime)` and
  `Delegate is DelegateRuntime` both hold — zero behavioural divergence.

## Alternative considered (rejected)

Renaming the shipped classes to drop the `Delegate*`/`Engine` prefix.
**Rejected** — would re-introduce the `kaizen_agents.delegate.Delegate`
naming collision the team deliberately solved with the prefix, AND would
break every existing call site that imports the prefixed names.

## Out of scope

Closing #1035 itself remains gated on maintainer-side close per session-notes.
This DECISION only addresses the acceptance-gate import-path mismatch.

## User-impact note (per `rules/recommendation-quality.md` MUST-2)

- **What changes for users:** the literal #1035 issue-body import line now
  succeeds. Downstream consumers can use either name interchangeably.
- **Reviewer signal for new code:** SHOULD prefer the prefixed names
  (`DelegateRuntime`, etc.) for grep-ability and to avoid the
  `kaizen_agents.delegate.Delegate` collision; the unprefixed aliases
  exist for spec adherence + import ergonomics.
- **Ongoing maintenance:** zero — aliases are 5 module-scope assignments,
  no runtime overhead, no migration path required.
- **Reversibility:** trivial; the aliases can be removed in a future
  major version if/when the kaizen-agents collision is otherwise resolved.

## Receipts

- /redteam Round 1 analyst finding: `04-validate/01-spec-compliance.md`
  (CRITICAL section, 5 entries)
- Existing disambiguation docstring:
  `src/kailash/delegate/__init__.py:8-9`
- Shard Z branch: `feat/1035-shard-z-naming-aliases`
- Shard Z commit: aliases + invariant-count update landed in one commit
  per `orphan-detection.md` Rule 6a (Merge-Time `__all__` Reconciliation)
- Architecture plan §Goal deviation note: this entry IS the receipt;
  the architecture plan does not yet exist on this worktree's base SHA
  (`6f22db92b`), so the deviation is documented here and the orchestrator
  will reconcile with `02-plans/01-architecture.md` at merge time.

## Tests

`tests/unit/delegate/test_naming_aliases.py` covers:

1. Literal #1035 issue-body import line succeeds end-to-end.
2. Each alias `is` (identity-equal to) its canonical class.
3. Each alias appears in `kailash.delegate.__all__`
   (per `orphan-detection.md` Rule 6).

`tests/unit/delegate/test_package_shell.py::test_kailash_delegate_imports_cleanly`
count updated 48 → 53 in the SAME commit as the alias additions
(per `orphan-detection.md` Rule 6a).

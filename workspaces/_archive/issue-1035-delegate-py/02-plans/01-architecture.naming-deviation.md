# Architecture Plan — §Goal Naming Disambiguation Deviation

> **Orchestrator note:** This file is a SUPPLEMENT authored by Shard Z
> (`feat/1035-shard-z-naming-aliases`) on a worktree branched from
> `main` (`6f22db92b`). The base `02-plans/01-architecture.md` does not
> exist on this base SHA — Shard X / Shard Y / orchestrator likely
> author it. At merge time, fold this §Goal deviation note into the
> main plan's §Goal section per `rules/specs-authority.md` MUST Rule 6
> (deviation notes record where the implementation diverges from the
> spec — and why).

## §Goal — Naming Disambiguation Deviation (2026-05-24)

The architecture plan's §Goal specifies the #1035 acceptance-criterion
import line:

```python
from kailash.delegate import (
    Delegate, ConstraintEnvelope, PrincipalDirectory,
    GenesisRecord, PostureState, AuditChain, Connector,
)
```

The shipped class names are `DelegateRuntime`, `DelegateConstraintEnvelope`,
`DelegateGenesisRecord`, `Posture`, `AuditChainEngine` (prefixed to avoid
collision with `kaizen_agents.delegate.Delegate` LLM facade — see
`src/kailash/delegate/__init__.py:8-9` for the disambiguation docstring).

Per #1035 acceptance-criterion gate, both forms are exposed:

- **Canonical (use in new code):** `DelegateRuntime`,
  `DelegateConstraintEnvelope`, `DelegateGenesisRecord`, `Posture`,
  `AuditChainEngine`.
- **Aliases (spec-compliance):** `Delegate`, `ConstraintEnvelope`,
  `GenesisRecord`, `PostureState`, `AuditChain` — direct identity
  aliases (`Delegate is DelegateRuntime` at runtime).

Both `from kailash.delegate import Delegate` (issue body) and
`from kailash.delegate import DelegateRuntime` (canonical) resolve to
the same class object.

**User impact:** zero — downstream consumers can use either name
interchangeably. `isinstance(x, Delegate) is isinstance(x, DelegateRuntime)`
holds.

**Reviewer signal:** new code SHOULD prefer the prefixed names for
grep-ability and disambiguation; the aliases exist for spec adherence +
import ergonomics.

**Implementation:** 5 module-scope assignments + 5 `__all__` entries
under "Group 10 — #1035 acceptance-gate aliases" in
`src/kailash/delegate/__init__.py`. Invariant-count test updated 48→53
in the same commit per `orphan-detection.md` Rule 6a.

**Tests:** `tests/unit/delegate/test_naming_aliases.py` covers the
literal issue-body import line + the identity-alias relationship +
`__all__` membership.

**Receipt:** `workspaces/issue-1035-delegate-py/journal/0006-DECISION-naming-aliases-for-1035-acceptance.md`.

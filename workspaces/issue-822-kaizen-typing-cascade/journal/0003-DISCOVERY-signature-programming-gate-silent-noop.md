---
type: DISCOVERY
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: agent
session_id: issue-822-kaizen-typing-cascade
session_turn: /analyze
project: kailash-py / issue-822-kaizen-typing-cascade
topic: signature_programming_enabled gate silent no-op against KaizenConfig dataclass
phase: analyze
tags: [issue-822, silent-fallback, rule-3, kaizen-config, gate-semantics]
---

# DISCOVERY — `signature_programming_enabled` gate is a silent no-op for explicit `KaizenConfig` callers

**Date:** 2026-05-05
**Phase:** /analyze (Cluster A + Cluster B reconciliation)
**File:** `agents.py:455–462`

## Finding

The signature-programming gate at `agents.py:455–462`:

```python
if (
    self.kaizen
    and hasattr(self.kaizen, "config")
    and hasattr(self.kaizen.config, "get")          # ← line 458
    and self.kaizen.config.get("signature_programming_enabled", False) == True
):
    raise ValueError("Agent must have a signature for structured execution")
```

`Kaizen.config` (`framework.py:1283`) is a property with two return shapes:

1. **`ConfigWrapper(dict)` (default path)** — when user passed a dict or no config
2. **`KaizenConfig` (`@dataclass`, `core/config.py:383`)** — when user passed an explicit
   `KaizenConfig` instance (`_config_was_object` flag set)

`KaizenConfig` has NO `.get()` method (it's a dataclass, not dict-subclass).
`hasattr(self.kaizen.config, "get")` returns:

- `True` for `ConfigWrapper(dict)` → gate fires correctly
- `False` for `KaizenConfig` → **gate silently flips to False; the documented gate never raises**

## Why this matters

This is `rules/zero-tolerance.md` Rule 3 silent-fallback on a documented public-API
gate. The signature-programming feature claims to enforce signatures on agents
when enabled, but it ONLY enforces against users who pass dict-shaped config —
exactly the opposite of "library users pass our typed config object."

Tests pass because they use dict shapes (`{"signature_programming_enabled": True}`),
which DO have `.get`. The fail mode only manifests for users who follow the
documented `KaizenConfig(signature_programming_enabled=True)` pattern.

This is the same failure-mode class as Phase 5.11 fake-encryption: the audit trail
shows "encryption" (the documented gate "fires"), but the disk shows plaintext (the
gate is a no-op for the typed-config path).

## Why this surfaced in #822

Pyright's `reportAttributeAccessIssue` flagged `agents.py:459` because pyright
narrows `self.kaizen.config` to `KaizenConfig` (the property's declared return path)
and `KaizenConfig` has no `.get`. The Cluster A deep-dive initially classified
this as a real runtime bug; Cluster B reconciliation showed the property has a dual
shape and the bug only manifests for the explicit-config branch. Both readings are
correct — the gate is correct for default users and broken for typed-config users.

## Action

Architecture plan § Shard 1 includes the fix:

```python
# Replace:
and hasattr(self.kaizen.config, "get")
and self.kaizen.config.get("signature_programming_enabled", False) == True
# With:
and (
    getattr(self.kaizen.config, "signature_programming_enabled", None) is True
    or (hasattr(self.kaizen.config, "get") and
        self.kaizen.config.get("signature_programming_enabled", False) is True)
)
```

Plus a Tier-2 regression test (`tests/regression/test_issue_822_signature_programming_gate.py`):

```python
@pytest.mark.regression
def test_signature_programming_gate_fires_against_kaizen_config_dataclass():
    """The gate MUST fire when user passes explicit KaizenConfig with the flag set."""
    config = KaizenConfig(signature_programming_enabled=True)
    kaizen = Kaizen(config=config)
    agent = kaizen.create_agent("a", config={})  # NO signature
    with pytest.raises(ValueError, match="Agent must have a signature"):
        agent.execute(input="x")
```

This test would have caught the silent no-op when it shipped.

## Why it's a #822 finding rather than a separate issue

The bug surfaced AS the typing-cascade pyright warning. Rule 1 ("if you found it,
you own it") + autonomous-execution.md Rule 4 (same-bug-class fix-immediately within
shard budget) make this part of Shard 1. The fix is ~3 LOC; the regression is ~10
LOC; both fit comfortably under the ~140 LOC Shard 1 budget.

## For Discussion

1. **Counterfactual:** if `Kaizen.config` had a single return shape (either
   always-dataclass or always-dict) instead of the property dual-shape, would
   the gate have fired correctly for every user? Is the dual-shape API itself
   the root cause (bigger refactor) versus the gate's inability to handle
   both shapes (smaller fix)?
2. **Specific data:** the gate shipped silently broken for users who pass
   explicit `KaizenConfig(signature_programming_enabled=True)` (the typed-config
   path). Tests pass dicts; the typed-config path was never exercised. How
   many other gates in `kaizen/` have the same pattern (`hasattr` guard that
   silently flips on the typed-config branch)? Is a sweep warranted?
3. **Trade-off:** the proposed fix (unified read across both shapes) keeps the
   dual-shape `Kaizen.config` API but adds defensive code to every consumer.
   Alternative: collapse `Kaizen.config` to always return ConfigWrapper(dict)
   even for typed-config users (smaller call-site footprint, larger property
   refactor). Out of scope for #822 but worth flagging.

## References

- `01-analysis/01-cluster-a-lying-types.md` site #9
- `01-analysis/02-cluster-b-agent-model.md` § 1 — `Kaizen.config` property dual-shape
- `framework.py:1283–1310` — property body showing `_config_was_object` branching
- `core/config.py:383` — `KaizenConfig` dataclass definition

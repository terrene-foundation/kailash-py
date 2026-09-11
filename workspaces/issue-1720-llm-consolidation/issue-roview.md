> **RECONCILED 2026-09-11 (/sweep): RESOLVED ON DEV — DO NOT FILE.**
> The `_ReadOnlyGovernanceView` `__getattr__`-only bypass this draft describes is CLOSED on
> `origin/dev` by lane L13 (`f1de3d68f`): `_ReadOnlyGovernanceView` now extends
> `kailash.trust.readonly_proxy.ReadOnlyAttributeProxy`, which guards `__getattribute__`
> (`src/kailash/trust/readonly_proxy.py:250`, raises `_denial` at :257) AND `__setattr__` (:264).
> `__getattribute__` fires for EVERY access including `_engine`, so `view._engine.<mutation>` is denied.
> RESIDUAL (UNVERIFIED, genuinely open): archived `d684ce20f` fixed "1 CRIT + 5 HIGH"; the CRIT (this)
> landed via L13, but the 5 HIGH across serving.py/express.py/rest.py/trust/pact/context.py are
> UNVERIFIED on dev — `git cherry origin/dev d684ce20f` = `+` (not landed as a unit). See new-session instructions.

## Summary

`_ReadOnlyGovernanceView` is not read-only. It guards a **13-name blocklist** in `__getattr__`, but `__getattr__` is only consulted when normal attribute lookup FAILS — and `self._engine` is a normal instance attribute. So `view._engine` never reaches the guard at all, and `view._engine.<any mutation method>` bypasses the entire blocklist in one attribute access.

This was found by re-adjudicating archived refs. A **red-team fix for exactly this** exists on `refs/archive/2026-08-21/feat/outstanding-issues-consolidation` (commit `d684ce20f`, 2026-04-05, "security: fix 1 CRITICAL + 5 HIGH findings from red team") and **never landed on trunk**. Two sibling HIGH findings from the same commit are also still missing (below).

## Verified against origin/dev this session

```
git merge-base --is-ancestor d684ce20f origin/dev   -> NOT ancestor
git merge-base --is-ancestor 73c45fa43 origin/dev   -> ancestor      (control: discriminates)
```

`packages/kailash-pact/src/pact/engine.py:1338-1362`:

```python
def __getattr__(self, name: str) -> Any:
    # Every mutation method on GovernanceEngine MUST be listed here.
    # Verified against GovernanceEngine method inventory (2026-04-06).
    _BLOCKED = { ...13 names... }
    if name in _BLOCKED:
        raise AttributeError(...)
    return getattr(self._engine, name)     # <-- fallthrough
```

And `__init__` is simply `self._engine = engine`. Measured in-process:

```
has __getattr__ blocklist : True
has __getattribute__ guard: False
```

`grep -c '__getattribute__'` over the file returns **0**, against a control where `__getattr__` matches — so the matcher fires and the absence is real.

## Two independent failure modes

1. **`._engine` escape (the sharp one).** `__getattr__` is a fallback. `_engine` is set in `__init__`, so it resolves normally and the guard is never invoked. `view._engine.grant_clearance(...)` works despite `grant_clearance` being in `_BLOCKED`. The blocklist protects the view's own surface and nothing behind it.
2. **Blocklist staleness.** The comment states the requirement plainly — _"Every mutation method on GovernanceEngine MUST be listed here. Verified against GovernanceEngine method inventory (2026-04-06)."_ Any mutation method added to `GovernanceEngine` after that date is exposed by default. A manually-maintained denylist over a surface someone else extends is fail-OPEN by construction, and nothing enforces the invariant the comment asserts.

Internals are exposed the same way: `view._store`, `view._lock`, and anything else not among the 13 names.

## The archived fix

`d684ce20f` replaces the blocklist with an **allowlist** — `_ALLOWED = frozenset({...10 explicit read-only names...})` — plus a `__getattribute__` override that blocks `_engine` access outright. That is fail-CLOSED, and it closes both failure modes: an unlisted method is denied by default, and the escape hatch is gone.

**Do not cherry-pick blindly.** `engine.py` has moved substantially since 2026-04-05, and a separate fix for #2218 is currently in flight in this same file. Re-derive the allowlist against the CURRENT `GovernanceEngine` surface.

## Sibling HIGH findings from the same commit, also missing

- **RT-277-1** — `src/kailash/trust/pact/context.py::GovernanceContext`: `__reduce_ex__` / `__deepcopy__` blocking is absent from trunk (grep: 0 matches). Without it a governance context can be copied or pickled out of its intended scope.
- **RT-SERVE-1** — `packages/kailash-dataflow/src/dataflow/fabric/serving.py::_make_batch_handler`: no cap on `products=` batch size. The archived version rejects >50 with a 400. Trunk's handler has since gained multi-tenant and parameterized-product routing, so re-derive rather than cherry-pick.

Lower-severity items in `d684ce20f` (RT-3a rate-limit try/except, RT-1b pagination cursor dedup, RT-6a `bulk_update` empty-list early-return) were **not** individually re-verified; `express.py::_bulk_update` has been substantially rewritten since. Treat those three as unconfirmed, not as cleared.

## Acceptance criteria

- [ ] `_ReadOnlyGovernanceView` denies by default: an attribute not on an explicit allowlist raises, rather than falling through to the engine.
- [ ] `view._engine` is not reachable.
- [ ] A test asserts **both poles** — an allowed read-only method still works AND a mutation method (plus `_engine`, plus a name invented by the test that is on no list) is denied. A deny-only test cannot distinguish this fix from one that breaks the view entirely.
- [ ] A test pins the staleness property: adding a new mutation method to `GovernanceEngine` does not silently expose it. This is the invariant the current comment asserts and nothing enforces.
- [ ] `GovernanceContext` blocks `__reduce_ex__` / `__deepcopy__`.
- [ ] `_make_batch_handler` caps batch size and rejects over-cap requests with a 4xx.
- [ ] Each new test is shown capable of failing (run against the unfixed code).
- [ ] The archived ref is retained until this lands, then may be pruned.

## Provenance note

This gap was invisible to the prior adjudication pass, which found a different single landable ref. Detecting it required reading the current implementation of `_ReadOnlyGovernanceView` line by line — `git cherry` and branch-name inference both miss it, because the branch's _name_ says "outstanding issues consolidation" and gives no hint that it carries an unlanded CRITICAL security round.

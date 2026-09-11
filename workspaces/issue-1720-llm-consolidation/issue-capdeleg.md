> **RECONCILED 2026-09-11 (/sweep): RESOLVED ON DEV — DO NOT FILE.**
> The raw-allowlist assignment this draft flags (`capabilities_delegated=list(...allowed_actions)`)
> is GONE on `origin/dev`: both sites (`src/kailash/trust/pact/engine.py:3224`,`:3317`) now call
> `delegated_capabilities(...)` (`src/kailash/trust/action_policy.py:251`), which returns
> `allowed - blocked` from the SAME derivation enforcement uses (parent-intersection handled by
> monotonic-tightening validation). The helper docstring cites GH #2225 — fixed by the governance cluster.

## Summary

`DelegationRecord.capabilities_delegated` is populated from the **raw** child allowlist — not intersected with the parent, and not reduced by `blocked_actions`. So a delegation record can **advertise a capability that every enforcement surface denies**.

Surfaced by the #2218 lane while fixing the empty-`allowed_actions` bypass, and deliberately scoped out of that change as a distinct bug class. Verified against `origin/dev` this session at `f1563d9ab`.

## Measured

`src/kailash/trust/pact/engine.py:3216` and `:3305`:

```python
delegation = DelegationRecord(
    id=f"pact-deleg-{uuid4().hex[:8]}",
    delegator_id=envelope.defining_role_address,
    delegatee_id=envelope.target_role_address,
    task_id="",
    capabilities_delegated=list(
        envelope.envelope.operational.allowed_actions      # <-- raw
    ),
    constraint_subset=[],
```

No intersection with the delegator's own allowlist, and no `blocked_actions` subtraction. `grep -c 'def verify_action'` over the same file returns 1, so the matcher fires and the absence is a real absence rather than a missed hit.

## Concrete divergence

An envelope declaring `allowed=["read", "transfer_funds"]` with `blocked=["transfer_funds"]`:

- **Enforcement** — every surface denies `transfer_funds`. The envelope intersection unions the allowlist and re-subtracts the blocklist, and after #2218 all ten surfaces agree on that.
- **The delegation record** — advertises `capabilities_delegated: ["read", "transfer_funds"]`.

The record is the durable, signed artifact an auditor or a downstream consumer reads to answer _"what was this agent delegated?"_ It answers with a superset of what the agent can actually do.

## Why it matters beyond cosmetics

This is not a display bug. `DelegationRecord` is an EATP trust-chain artifact:

- An auditor reconstructing the delegation graph sees authority that was never granted.
- A downstream consumer that trusts the record rather than re-deriving from the envelope will believe a capability is available, and its behaviour on discovering otherwise is undefined.
- The divergence is **silent and one-directional** — it always over-states, never under-states, so nothing fails loudly to reveal it.

It is the same family as #2189 ("an absence rendered as a success") pointed the other way: a denial rendered as a grant.

## Suggested fix

Populate `capabilities_delegated` from the same computation enforcement uses — intersect with the delegator's effective allowlist, then subtract `blocked_actions` — rather than reading the child's declared list. The predicate landed for #2218 (`src/kailash/trust/action_policy.py`) is the natural home for that shared derivation, so the record and the enforcement path cannot drift again.

Check `:3013` in the same file too: it hardcodes `capabilities_delegated=[]`, which is safe (understates rather than overstates) but is a third spelling of the same field and worth confirming it is deliberate.

## Acceptance criteria

- [ ] `capabilities_delegated` never contains an action the enforcement surfaces would deny for that envelope.
- [ ] A test asserts the divergence case directly: `allowed=["read","transfer_funds"]` + `blocked=["transfer_funds"]` produces a record listing `["read"]` only.
- [ ] A test asserts **both poles** — the record also still lists a genuinely-granted capability. An emptied-record fix would pass a deny-only test.
- [ ] Both emission sites (`:3216`, `:3305`) are fixed in the same change; fixing one leaves the other diverging.
- [ ] The record derives from the shared predicate rather than a second hand-written computation, so the two cannot drift apart again.
- [ ] Each new test is shown capable of failing (run against the unfixed code).

## Related

- `#2218` — the empty-`allowed_actions` bypass. Same field, same file; this was explicitly scoped out as a different bug class and is recorded here rather than left in a commit body.
- `#2189` — "an absence rendered as a success". This is its mirror: a denial rendered as a grant.

## Other residuals from the same lane, recorded so they are not lost

Each needs its own assessment; none is claimed verified here beyond what is stated:

- `envelopes.py::validate_tightening` has **no blocklist-superset check** at all, while three sibling validators do — a child can strip a parent's blocked action and still register. Eval-time intersection keeps `verify_action` safe, but the two surfaces reading the child envelope directly are not.
- `envelope_adapter.py:149` and `envelope.py:1626` collapse absent→empty, so an envelope round trip turns permit-all into deny-all. Fixing it touches the signed-envelope pre-image — larger blast radius.
- `plane/models.py:52` `OperationalConstraints` is `frozen=True` but **shallow** — `from_dict` aliases the caller's list, so an allowlist can be mutated after a tightening check passes.
- `GovernanceContext.allowed_actions` (`engine.py:2274`) is the raw allowlist and collapses absent with empty.

# R1 Security Review — #1338 TenantScopedEventBus

Verdict: APPROVE with one MEDIUM hardening (now FIXED in R2 — see below).
Agent: security-reviewer (Read/Grep/Glob only; static reasoning + parent ran the live probe).

## MEDIUM — Mixed-separator cross-tenant collision on a shared bus (CONFIRMED)

Per-wrapper `separator in tenant_id` guard does NOT enforce a uniform
separator across wrappers sharing one bus. With differing separators two
distinct tenants can produce overlapping prefixes.

Empirical proof (parent, Bash):

```
A = TenantScopedEventBus('a', bus, separator='::')   # prefix 'a::'
B = TenantScopedEventBus('a:', bus, separator=':x')  # prefix 'a::x'  (':x' not in 'a:' → passes)
B.subscribe('foo')        # topic 'a::xfoo'
A.publish('xfoo', {...})  # topic 'a::xfoo'
→ B (tenant 'a:') received {'tenant': 'A-secret'} from A (tenant 'a')   # CROSS-TENANT LEAK
```

Fix (R2): stamp the separator on the shared bus at first wrap; a later
wrapper passing a different separator raises ValueError. Under a uniform
separator the existing `separator in tenant_id` guard makes collision
structurally impossible (first-occurrence-of-sep is at index len(tenant_id);
byte-equal scoped strings ⟹ equal tenant_id).

## PASS (R1)

1. Uniform-separator crafted tenant_id — REFUTED (constructor rejects sep-in-id).
2. Separator-bearing event_type — PASS (un-prefix by known-length, not split).
3. Empty/None tenant_id/separator validation — PASS.
4. subscribe_events un-prefix — PASS (subscription registered on scoped topic;
   exact-match dispatch only routes this tenant's own events).
5. Shared-bus close() lifecycle isolation — PASS (close() only closes owned bus).
6. DomainEvent payload cross-tenant tampering — PASS (publish reaches only
   same-tenant subscribers; no cross-tenant shared-mutable hazard).

No secrets/SQL/eval in new code. `__all__` export contract correct.

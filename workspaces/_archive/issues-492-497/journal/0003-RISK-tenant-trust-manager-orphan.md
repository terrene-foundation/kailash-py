---
type: RISK
date: 2026-04-18
author: agent
project: kailash-py
topic: DataFlow._tenant_trust_manager facade had zero production call sites
phase: redteam
tags: [orphan, trust-plane, multi-tenant, phase-5-11-class]
---

# `DataFlow._tenant_trust_manager` facade was a Phase-5.11-shaped orphan

**Files**:

- `packages/kailash-dataflow/src/dataflow/core/engine.py:627, 661-665`
  (pre-fix)
- `specs/dataflow-core.md:373` (spec line pre-fix)

**Finding**: `DataFlow.__init__` constructed `TenantTrustManager(strict_mode=True)`
and assigned it to `self._tenant_trust_manager` when both
`multi_tenant=True` and trust mode != "disabled". The spec at
`dataflow-core.md:373` advertised this as "Multi-tenant trust isolation".
But the framework's hot paths (`features/express.py`,
`trust/query_wrapper.py`) had zero call sites into any of the manager's
8 public methods:

```bash
rg 'self\._tenant_trust_manager\.' packages/ src/
# 0 matches

rg '_tenant_trust_manager\.' packages/ src/
# 0 matches (excluding init at engine.py:664)
```

The existing Tier 2 test at `tests/regression/test_phase_5_11_trust_wiring.py:263`
only asserted `db._tenant_trust_manager is not None` — never that the
framework actually invoked it during a multi-tenant read. Classic Phase
5.11 failure pattern: facade exists, downstream consumers import it,
framework never calls it.

**Blast radius**: Operators who enabled `multi_tenant=True + trust=enforcing`
believed cross-tenant verification was running. It wasn't. Every
multi-tenant read and write bypassed the manager's
`verify_cross_tenant_access`, `get_row_filter_for_access`, and
delegation checks.

**Fix options weighed**:

- **(A) Wire** `_tenant_trust_manager` into `features/express.py` at list/
  read for cross-tenant verification. ~200-400 LOC + Tier 2 tests. Pulls
  into feature-work scope beyond the redteam's per-session capacity
  budget (already at 5 invariants this session).
- **(B) Delete** the facade, keep the class available standalone at
  `dataflow.trust.multi_tenant.TenantTrustManager` for consumers who
  need cross-tenant verification. Aligns with `orphan-detection.md`
  MUST 3 ("Removed = Deleted, Not Deprecated").

**Chose (B)**. Deleted the `_tenant_trust_manager` attribute init and
conditional construction block. Updated `specs/dataflow-core.md` § 21.2
to document that `TenantTrustManager` is a standalone class — not a
`db.*` facade — with a pin that says the facade will be wired in the
SAME PR as a production call site.

**Call site needed for future wiring**: when a consumer (or this
project) needs cross-tenant delegation verification on
`express.list()` / `express.read()`, the correct pattern is:

```python
# In DataFlowExpress.list(self, model, filter, ...):
if self._db._tenant_trust_manager is not None:
    if not await self._db._tenant_trust_manager.verify_cross_tenant_access(
        source_tenant_id=..., target_tenant_id=..., model=model, operation="list"
    ):
        raise PermissionError("cross-tenant access denied")
    row_filter = self._db._tenant_trust_manager.get_row_filter_for_access(...)
    # apply row_filter to WHERE clause
```

At that PR, re-add the attribute + construction block in
`engine.py`. The 8 public methods on `TenantTrustManager` already have
Tier 1 tests in `tests/unit/trust/test_multi_tenant.py`.

## For Discussion

- Phase 5.11 taught us to audit for orphans at every release. Why did
  this one slip through? The Phase 5.11 audit focused on
  `_trust_executor` and `_audit_store`; `_tenant_trust_manager` lived
  in the same file but was gated behind `multi_tenant=True`, which was
  not a path the audit tested.
- Counterfactual: if we had an AST-level check "every `self._X` with
  `X.endswith("manager")` must have at least one `self._X.` usage in
  `packages/`", would that have caught this? Yes. Should that be in
  `/redteam` as a grep?
- The spec update documents the attribute's absence. A future session
  reading only the spec sees a clean architectural decision, not a
  historical orphan. Is that right, or should the spec keep a
  "removed 2026-04-18" marker per `rules/specs-authority.md` MUST 6?

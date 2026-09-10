## Summary

Every access-check method on `MiddlewareAccessControlManager` constructs `AccessDecision` with keyword arguments that class does not accept, so each raises `TypeError` on the path that reaches the constructor. This is a **different root cause from #2166** (which is about `PermissionCheckNode` kwargs) and covers **different methods**, so it is filed separately.

Surfaced while fixing #2057 site 1; verified independently against `origin/dev` this session.

## Measured

`src/kailash/middleware/auth/access_control.py:18` imports `AccessDecision` from `kailash.access_control`. That class's constructor:

```
>>> import inspect; from kailash.access_control import AccessDecision
>>> list(inspect.signature(AccessDecision.__init__).parameters)
['self', 'allowed', 'reason', 'applied_rules', 'conditions_met', 'masked_fields', 'redirect_node']

>>> AccessDecision(allowed=True, reason='r', user_id='u', resource_id='x', permission='p')
TypeError: AccessDecision.__init__() got an unexpected keyword argument 'user_id'
```

The middleware passes exactly those rejected kwargs at three sites:

- `:90` — `check_session_access` (`user_id=`, `resource_id=`, `permission=`)
- `:117` — `check_workflow_access` (same)
- `:152` — `check_node_access` (same)

**Discrimination note:** the constructor call above is the control — it returns a _different_ result (`TypeError`) from the kwarg set the class does accept, so this distinguishes "wrong kwargs" from "class is broken generally". `AccessDecision(allowed=True, reason='r')` constructs fine.

There are **two** distinct `AccessDecision` classes in the tree — `src/kailash/access_control.py:218` (the one imported here) and `src/kailash/access_control/rule_evaluators.py:52` (fields `allowed`, `reason`, `applied_rules`, `conditions_met`). Neither declares `user_id`, `resource_id` or `permission`, so this is not a case of the import pointing at the wrong one of the two.

## Relationship to #2166 — overlapping but distinct

`#2166` covers `check_session_access` only, and its defect fires **earlier**: `PermissionCheckNode.execute()` raises `NodeValidationError` before control reaches the `AccessDecision` constructor at `:90`. So `:90` is currently _masked_ by #2166 and would surface the moment #2166 is fixed.

`:117` and `:152` are not masked — `check_workflow_access` and `check_node_access` reach their constructors and raise `TypeError` directly. Those two are the un-tracked part.

Fixing #2166 alone will therefore NOT make this module work; it will move the failure from `NodeValidationError` to `TypeError`, one line later.

## Also in the same module

Both `audit_node.execute()` calls use a kwarg set `EnterpriseAuditLogNode` rejects — it expects `operation="log_event"` plus `event_data={...}`. Relatedly, `permission_rule_created` is not a member of `AuditEventType`. These were observed while fixing #2057 and are recorded here rather than left in a commit body.

## Assessment

`MiddlewareAccessControlManager` was written against an earlier generation of these dataclasses and node signatures and has never been exercised end-to-end. It was **unconstructable** until PR #2140 fixed an unrelated assert (per #2166's own analysis), which is why none of this surfaced before.

The #2057 fix that surfaced this is correct and complete on its own terms — it fails **loud** (raising a typed error) rather than falsely succeeding, which is the improvement. But the module needs its own repair shard, and that shard needs a design pass on `AuditEventType` and on which `AccessDecision` shape is canonical.

## Acceptance criteria

- [ ] `check_workflow_access` and `check_node_access` return an `AccessDecision` instead of raising `TypeError`.
- [ ] The canonical `AccessDecision` shape is decided — either the class gains `user_id`/`resource_id`/`permission`, or the call sites stop passing them. Two classes of the same name with different fields is itself worth resolving.
- [ ] Both `audit_node.execute()` calls use a kwarg set the node accepts, and the audit event type is a real `AuditEventType` member.
- [ ] A test exercises each of the three methods end-to-end against a constructed manager. The absence of any such test is why this shipped — the module has never been run.
- [ ] Each new test is shown capable of failing (run against the unfixed code).

## Related

- `#2166` — `check_session_access` / `PermissionCheckNode` kwargs. Same module, earlier failure point, different root cause. **Note:** #2166 is currently on hold pending a co-owner schema decision; this issue is a separate defect and its status should be assessed on its own, not inherited.
- `#2057` — the dead-guard fix that surfaced this (`ac01fa77d`).
- `#2108` — named by #2166 as the same family: an authorization path that can only refuse, shipped as a working feature.

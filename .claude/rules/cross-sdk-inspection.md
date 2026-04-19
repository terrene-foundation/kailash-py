---
paths:
  - "**/src/**"
  - "**/tests/**"
---

# Cross-SDK Issue Inspection

## Scope

These rules apply to ALL bug fixes, feature implementations, and issue resolutions in BOTH BUILD repos (kailash-rs and kailash-py).

## MUST Rules

### 1. Cross-SDK Inspection on Every Issue

When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue.

**Why:** Bugs in shared architecture (trust plane, DataFlow, Nexus) almost always exist in both SDKs — fixing only one leaves users of the other SDK hitting the same issue.

**kailash-rs issue found → inspect kailash-py**:

- Does the Python SDK have the same bug?
- Does the Python SDK need the equivalent feature?
- File a GitHub issue on `terrene-foundation/kailash-py` if relevant.

**kailash-py issue found → inspect kailash-rs**:

- Does the Rust SDK have the same bug?
- Does the Rust SDK need the equivalent feature?
- File a GitHub issue on `esperie-enterprise/kailash-rs` if relevant.

### 2. Cross-Reference in Issues

When filing a cross-SDK issue, MUST include:

- Link to the originating issue in the other repo
- Tag: `cross-sdk` label
- Note: "Cross-SDK alignment: this is the [Rust/Python] equivalent of [link]"

**Why:** Without cross-references, the same bug gets fixed independently with different approaches, causing semantic divergence between SDKs that violates EATP D6.

### 3. EATP D6 Compliance

Per EATP SDK conventions (D6: independent implementation, matching semantics):

- Both SDKs implement features independently
- Semantics MUST match (same API shape, same behavior)
- Implementation details may differ (Rust idioms vs Python idioms)

**Why:** Semantic divergence between SDKs means code ported from Python to Rust (or vice versa) silently changes behavior, breaking user trust in the platform's cross-language promise.

### 3a. Structural API-Divergence Disposition

When the sibling SDK reports a bug at an API surface this SDK does NOT expose (e.g., the Rust `execute_raw(sql, params)` bug class requires a `params` arg that the Python `execute_raw(sql)` doesn't have), the disposition MUST include BOTH:

1. **A Tier 2 test through the sibling path that DOES bind parameters** — the bug class may still manifest at a different API surface in this SDK (e.g., Express `bulk_create`, `update`, `upsert`). The test mirrors the sibling SDK's repro scenario through the equivalent parameter-binding path in this SDK.
2. **A structural invariant test that pins the signature** — asserts the API signature that prevents the bug class from existing at this surface (e.g., `execute_raw` takes only `sql` as a positional arg, no `params`). If a future refactor grows the signature to match the sibling SDK's shape, the invariant test fails loudly and forces a re-audit.

```python
# DO — both tests; one exercises the sibling path, one locks the signature
@pytest.mark.regression
async def test_issue_XXX_cross_sdk_parity_via_sibling_path(test_suite):
    # The Rust bug triggered at execute_raw(sql, params). Python execute_raw
    # has no params. The parameter-binding path in Python is Express.bulk_create.
    db = DataFlow(test_suite.config.url)
    # ... exercise shrinking-arity bulk_create against real Postgres
    assert poisoned_result.get("success") is True

@pytest.mark.regression
def test_issue_XXX_execute_raw_has_no_params_arg():
    # Structural invariant: if this signature ever grows a `params` kwarg,
    # the sibling bug class becomes reachable here and cross-SDK parity
    # MUST be re-audited.
    import inspect
    from dataflow.core.pool_lightweight import LightweightPool
    sig = inspect.signature(LightweightPool.execute_raw)
    non_self = [p.name for n, p in sig.parameters.items() if n != "self"]
    assert non_self == ["sql"], f"signature drifted: {sig}"

# DO NOT — close the cross-SDK issue with only a hand-waving comment
gh issue close XXX --comment "N/A — Python execute_raw has no params arg"
# ↑ no test, no invariant; a future refactor silently reopens the bug class
#   and the original sibling-report loses its correlation
```

**BLOCKED rationalizations:**

- "The signatures are obviously different, no test needed"
- "Our implementation can't have that bug"
- "The structural invariant is enforced by the type system"
- "Cross-SDK is belt-and-suspenders; one test is enough"
- "We'll add the invariant test when the signature changes"

**Why:** "Our signature doesn't have the arg" is true today and false the day someone ports a convenience method from the sibling SDK. The structural invariant test is the only mechanism that makes the signature _itself_ part of the contract — the moment the signature grows toward the sibling shape, the test fails and the agent reading the failure has a direct pointer back to the cross-SDK bug class. The sibling-path Tier 2 test proves the bug class does not manifest through the surface it COULD manifest through; without it, "different API" conceals a parallel bug the other SDK's API shape hid. Evidence: issue #525 (cross-SDK of kailash-rs#424) — Python `execute_raw(sql)` structurally cannot hit the Rust binding-layer UTF-8 corruption; disposition landed both an Express `bulk_create` sibling-path test AND a signature invariant test locking `LightweightPool.execute_raw(sql)` at PR #528.

Origin: Issue #525 / PR #528 (2026-04-19) — kailash-rs#424 parity check.

### 4. Inspection Checklist

When closing any issue, verify:

- [ ] Does the other SDK have this issue? (check or file)
- [ ] If feature: is it in the other SDK's roadmap?
- [ ] If bug: could the same bug exist in the other SDK?
- [ ] Cross-reference added to both issues if applicable

**Why:** Closing without cross-SDK verification is the primary cause of feature drift — the checklist is the last gate before an issue is forgotten.

## Examples

```
# Issue #52 in kailash-rs: per-request API key override
# → Filed kailash-py#12 as cross-SDK alignment
gh issue create --repo terrene-foundation/kailash-py \
  --title "feat(kaizen): per-request API key override" \
  --label "cross-sdk" \
  --body "Cross-SDK alignment with esperie-enterprise/kailash-rs#52"
```

## Automation

When the Claude Code Maintenance workflow is active, the fix job prompt
includes cross-SDK inspection as Phase 4.5 (between codify and commit).
When paused, this must be done manually.

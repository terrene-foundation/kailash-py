# Cross-SDK Issue Inspection

## Scope

These rules apply to ALL bug fixes, feature implementations, and issue resolutions in BOTH BUILD repos (kailash-rs and kailash-py).

## MUST Rules

### 1. Cross-SDK Inspection on Every Issue

When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue.

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

### 3. EATP D6 Compliance

Per EATP SDK conventions (D6: independent implementation, matching semantics):

- Both SDKs implement features independently
- Semantics MUST match (same API shape, same behavior)
- Implementation details may differ (Rust idioms vs Python idioms)

### 4. Inspection Checklist

When closing any issue, verify:

- [ ] Does the other SDK have this issue? (check or file)
- [ ] If feature: is it in the other SDK's roadmap?
- [ ] If bug: could the same bug exist in the other SDK?
- [ ] Cross-reference added to both issues if applicable

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

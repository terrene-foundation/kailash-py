# Milestone 0: Git Operations (Before Implementation)

## TODO-00A: Create feature branch

Per `rules/branch-protection.md`, all changes must go through a PR.

```bash
git checkout -b feat/trust-merge
```

**Acceptance**: Working on `feat/trust-merge` branch.

---

## TODO-00B: File cross-SDK notification on kailash-rs

Per `rules/cross-sdk-inspection.md` Rule 1, notify kailash-rs of this merge:

```bash
gh issue create --repo esperie/kailash-rs \
  --title "info: kailash-py merging eatp + trust-plane into kailash.trust.*" \
  --label "cross-sdk" \
  --body "Cross-SDK notification: kailash-py v2.0.0 merges the eatp and trust-plane packages into kailash.trust.* namespace. This is a Python packaging change only — no semantic changes to the EATP protocol. The Rust SDK implements EATP independently and does not need equivalent changes."
```

**Acceptance**: Issue filed with `cross-sdk` label.

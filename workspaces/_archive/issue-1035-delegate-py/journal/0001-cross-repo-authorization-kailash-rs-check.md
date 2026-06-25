# 0001 — Cross-Repo Authorization: Read-only check of kailash-rs Delegate status

**Date:** 2026-05-21
**Requester:** user (jack@researchroom.sg)
**Verbatim instruction:** "Please check kailash-rs (cross repo) and verify Delegate is built there too"
**Target repo:** terrene-foundation/kailash-rs (sibling SDK)
**Action (bounded):** read-only — `gh issue list/view` for Delegate references, filesystem `ls`/`grep` against `~/repos/loom/kailash-rs/` checkout if present, to verify whether the Delegate composition primitive (Connector × Signature × Envelope × Executor, per Delegate Spec v0) is implemented in the Rust SDK.
**Scope exclusions:** no writes, no PRs, no comments, no source edits, no issue creation against kailash-rs in this session.

cross-repo-authorized: terrene-foundation/kailash-rs

Per `rules/repo-scope-discipline.md` § User-Authorized Exception. Authorization is limited to this single read sweep; any subsequent cross-repo action (filing a paired issue, opening a PR) requires a fresh user gate.

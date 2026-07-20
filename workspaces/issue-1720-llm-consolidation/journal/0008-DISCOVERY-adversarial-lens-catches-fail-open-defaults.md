# DISCOVERY — The adversarial security lens is where fail-open defaults surface

Date: 2026-07-20. Repo class: BUILD (`name = "kailash"`). Author: agent (pattern
surfaced during this session's redteam). Coordination OFF.

## The pattern the next session should inherit

Two failure shapes recurred this session and share ONE root: a security feature's
correctness (does it work on the tested paths?) and its security posture (can an attacker
defeat it off the tested paths?) are DISJOINT questions, and the fail-open-default is
invisible to the first while obvious to the second.

1. **Fail-open default shape.** When a new security control is gated behind a flag /
   kwarg / injected dependency, the enabling DEFAULT is itself a security decision. A
   default that makes the feature a silent no-op ships the protection's headline claim
   with none of the protection — and the gap is invisible _precisely because nothing
   fires_. The tests pass (they exercise the wired path); the deployer runs the un-wired
   default in production. The fix is fail-CLOSED-by-default, or a LOUD one-time WARN when
   backward-compat forbids on-by-default. NEVER a silent no-op.

2. **Correctness-clean is not security-clean.** A correctness/closure-parity reviewer maps
   ACs → code and runs the tests; it returns CLEAN on a change whose attacker-path bypass
   was never looked at. On #1842-S3 the correctness lens passed 13/13 tests + all 3 ACs
   while the adversarial lens (same round) found a CRITICAL resurrection bypass, a HIGH
   monotonic regression, and the fail-open `revocation_verifier=None`. Both lenses are
   non-negotiable on the security surface.

## Why this generalizes

The two shapes are the same discipline at two layers: **default-value** (shape 1, the
code contract in security.md) and **review-lens** (shape 2, the orchestration contract in
agents.md). A security-critical change needs BOTH a secure default AND an adversarial
reviewer prompted to REFUTE — because the failure lives off the author's tested paths, and
neither the author's tests nor a correctness reviewer walks there. Cross-SDK: both shapes
apply identically to the kailash-rs binding (a new signed-revocation / caller-identity gate
defaulting to a silent no-op, and a correctness-only review of it, are the same bugs).

## For Discussion

1. Counterfactual: if #1842-S3 had shipped on the correctness-clean verdict alone (no
   adversarial round), how many releases would the single-file-delete resurrection bypass
   have survived before a user — not a reviewer — discovered revoked delegations silently
   re-activating? What is the detection cost off the tested path vs at the redteam?
2. The secure-default rule allows a backward-compat WARN fallback (path b). What stops that
   fallback from becoming the lazy default — "just add a WARN and ship it off" — instead of
   doing the harder work of making the feature constructible fail-closed? (The codified
   Detection answer: the reviewer must interrogate whether fail-closed was _genuinely_
   infeasible, not merely assert the WARN's presence.)
3. Both clauses detect at the review layer (halt-and-report), not a structural hook. Is a
   Phase-2 lexical/structural detector feasible for "a new security feature whose enabling
   default is a silent no-op", or is the silent-no-op judgment irreducibly semantic — i.e.
   does the gate depend permanently on an adversarial reviewer being dispatched at all?

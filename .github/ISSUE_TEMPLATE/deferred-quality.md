---
name: Deferred Quality (INCREMENTAL)
about: An INCREMENTAL improvement deferred under the four zero-tolerance Rule-1b conditions
labels: deferred-quality
---

<!--
Only an INCREMENTAL finding may be filed here.

A finding that BLOCKS testing or closure of an in-scope item — a failing
test/build/type-check, a shipped path that is wrong/insecure/lossy, a
contract/API break, a gate-integrity defect, an unmet success-criterion on a
SHIPPED feature — is a BUG and is fixed now, regardless of severity.
A finding with material forward-impact (foundational / architectural /
shared-substrate) is INVEST-NOW and is fixed now.

Severity (CRIT/HIGH/MED/LOW) RANKS a finding; it NEVER gates fix-vs-defer.
Relabelling a BUG or INVEST-NOW as "incremental" to defer it is BLOCKED.

See rules/product-completion-first.md for the classifier.

ALL FOUR sections below are REQUIRED. An entry missing any one of them is a
silent deferral, which product-completion-first.md MUST-2 BLOCKS.
-->

## 1. Blocking-safety note

<!-- Which SHIPPED / success path does this NOT touch? Name it explicitly.
     This is what proves the finding is genuinely off-path INCREMENTAL and
     not a mis-labelled BUG. -->

## 2. Value-anchor

<!-- ONE sentence: why this delivers value to the USER, citing a user-anchored
     source. The allowlist is CLOSED (value-prioritization.md MUST-2):
       (a) the user's brief in this session
       (b) a file under workspaces/<project>/briefs/
       (c) a journal DECISION- entry
       (d) a literal user quote in a session transcript
       (e) a spec § success criterion the user authored or approved
     Code-health rationale (coverage, blast radius, tech debt) is SECONDARY —
     it belongs under acceptance criteria, not here. -->

## 3. Full-fix acceptance criteria

<!-- The testable definition of done. Bulleted, observable.
     - [ ] ... -->

## 4. Revisit trigger

<!-- EXACTLY ONE of:
       after-milestone:<name>    (fires when <name> lands)
       on-demand
     Sweep-10 surfaces a "still wanted?" gate for any item deferred
     >= 2 sweeps / sessions ago. Disposition at revisit is user-gated:
     implement / re-defer-with-fresh-anchor / close-with-gate.
     Auto-closing as not_planned is BLOCKED (value-prioritization.md MUST-4). -->

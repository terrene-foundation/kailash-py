---
type: DISCOVERY
date: 2026-04-06
issue: "#309"
---

# FSM validation in grant_clearance() conflicts with revoke->re-grant flow

Adding FSM enforcement to `grant_clearance()` while simultaneously changing `revoke_clearance()` from DELETE to SET creates a conflict: REVOKED is a terminal state with no outgoing transitions, so re-granting a revoked role is rejected.

Resolution: `grant_clearance()` only validates FSM transitions for "living" states (PENDING, ACTIVE, SUSPENDED). Terminal states (REVOKED, EXPIRED) and missing records allow unconditional overwrite. This also protects the backup/restore path which calls `grant_clearance()` unconditionally.

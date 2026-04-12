---
type: DISCOVERY
date: 2026-04-06
issue: "#309"
---

# SUSPENDED->ACTIVE reinstatement is essential

The issue's original FSM proposes `SUSPENDED -> {REVOKED}` only, with reinstatement requiring a fresh PENDING grant. This defeats the purpose of SUSPENDED as distinct from REVOKED.

The FSM must include `SUSPENDED -> ACTIVE` for direct reinstatement. Similarly, `EXPIRED -> ACTIVE` enables clean renewals without record deletion. Only REVOKED is truly terminal.

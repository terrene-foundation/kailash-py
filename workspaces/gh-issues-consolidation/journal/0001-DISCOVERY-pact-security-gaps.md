# DISCOVERY: PACT Engine Has 4 Security Invariant Violations

All 4 confirmed against source code:

1. **Single-gate governance** (#234) — verify_action() called once at submit, not per-node. Envelope constraints (blocked_actions, temporal, compartments) bypassed after gate.
2. **Stale supervisor budget** (#235) — cached supervisor reuses original budget across multiple submit() calls.
3. **Mutable governance exposed** (#236) — .governance property returns full mutable GovernanceEngine, enabling privilege escalation.
4. **NaN budget evasion** (#237) — NaN > 0 is False, so NaN budget_consumed silently skips cost recording.

These are not theoretical — code paths confirmed at exact lines in pact/engine.py.

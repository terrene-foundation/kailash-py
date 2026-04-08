# Issue #308: Cross-SDK Governance Helpers Audit

## Finding: All capabilities already at L1 in kailash-py

The issue states that capabilities need to be moved from L3 (PACT Platform) to L1 (kailash-pact engine). **Audit shows they're already at L1.**

| Capability                | L1 Location                                         | Status            | Notes                                              |
| ------------------------- | --------------------------------------------------- | ----------------- | -------------------------------------------------- |
| Degenerate detection      | `envelopes.py:1059` `check_degenerate_envelope()`   | Fully implemented | NaN/Inf security checks included                   |
| Bootstrap defaults        | `envelopes.py:853` `default_envelope_for_posture()` | Fully implemented | 5 posture levels, $0-$100k                         |
| Explain functions         | `explain.py` (3 functions)                          | Fully implemented | describe_address, explain_envelope, explain_access |
| Bridge enhancements       | `access.py:85-118` PactBridge                       | Fully implemented | standing/scoped/ad_hoc + bilateral + expiration    |
| Containment unit accessor | `addressing.py:130` `Address.containment_unit`      | Fully implemented | Named `containment_unit` (not `team_segment`)      |

Additional bonus helpers already at L1:

- `check_passthrough_envelope()` (envelopes.py:992)
- `check_gradient_dereliction()` (envelopes.py:1124)

## Action Required

**No Python work.** This is a kailash-rs tracking issue. When kailash-rs implements #216, #217, #219, ensure semantic alignment per EATP D6.

## Cross-SDK Note

The `containment_unit` accessor is named differently than kailash-rs's proposed `team_segment`. Per EATP D6, semantics must match but naming follows language conventions. Should align on naming — `containment_unit` is more accurate (covers both departments and teams).

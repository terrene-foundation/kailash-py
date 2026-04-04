# DECISION: Red Team Todo Fixes Applied

Red team of todo list found 5 issues, all resolved:

1. **MISSING Communication dimension** in PR 1C envelope adapter — added mapping for `allowed_channels` and `notification_policy` from Communication constraint dimension. All 5 canonical PACT dimensions now covered.

2. **GAP #232 tracker closure** — added explicit tracker closure step to PR 1C Definition of Done.

3. **GAP provenance-audit connection** — added wire task 8 to PR 4B: enrich audit events with provenance metadata when Provenance fields are updated. This connects #242 and #243 per the brief requirement.

4. **INCOMPLETE C2 fallback** — removed hardcoded "claude-sonnet-4-6" fallback entirely. PactEngine now reads from constructor param or DEFAULT_LLM_MODEL env var only, with no silent fallback to a hardcoded string.

5. **INCOMPLETE PR 5D reverse shim** — clarified that all 15 adapter subclasses are updated atomically in the same PR, so no reverse shim is needed. Third-party subclasses get a clear TypeError.

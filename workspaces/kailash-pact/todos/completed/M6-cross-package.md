# Milestone 6: Cross-Package Integration

Dependencies: Milestone 4 (CI passing, package installable)
Estimated: 1 autonomous session (post-release)

---

## TODO-20: Kaizen integration test

**Priority**: MEDIUM
**Files**: Create `packages/kailash-pact/tests/integration/test_kaizen_governed.py`

### Test scenario
1. Create a Kaizen `BaseAgent` with a tool
2. Wrap with `PactGovernedAgent` using a compiled org
3. Verify governance checks run before agent execution
4. Verify BLOCKED actions don't execute the tool
5. Verify ALLOWED actions execute the tool and return results
6. Verify audit trail records governance decisions

### Acceptance criteria
- Test passes with `kailash-kaizen>=2.0.0` installed
- Test skipped gracefully when kaizen not installed

---

## TODO-21: Trust integration test

**Priority**: MEDIUM
**Files**: Create `packages/kailash-pact/tests/integration/test_trust_bridge.py`

### Test scenario
1. Create GovernanceEngine with envelope
2. Use GovernanceEnvelopeAdapter to produce trust-layer ConstraintEnvelope
3. Verify the trust-layer envelope has correct constraint values
4. Verify NaN/Inf rejection at the adapter boundary
5. Verify the trust-layer envelope can be used with kailash.trust operations

### Acceptance criteria
- Adapter produces valid `kailash.trust.plane.models.ConstraintEnvelope`
- Constraint values map correctly between governance and trust layers

---

## TODO-22: Vertical validation (Astra/Arbor)

**Priority**: LOW (external validation)
**Files**: None in this repo

### Steps
1. In `~/repos/terrene/astra`:
   - `pip install -e ~/repos/kailash/kailash-py`
   - `pip install -e ~/repos/kailash/kailash-py/packages/kailash-pact`
   - Verify existing governance code works with new import paths
2. In `~/repos/terrene/arbor`:
   - Same verification
3. Document any breaking changes for vertical teams

### Acceptance criteria
- Verticals can import GovernanceEngine from kailash-pact
- Existing governance tests in verticals pass (or breaking changes documented)

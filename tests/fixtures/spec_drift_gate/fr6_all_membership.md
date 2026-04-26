<!-- expected: findings=1 fr_codes=[FR-6 x1] origin=fr6_all_membership -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — FR-6 `__all__` Membership

Status: TESTING-FIXTURE — asserts a lowercase symbol is exported in
`__all__` that does NOT appear in any package's `__all__`. The
lowercase shape is intentional: it bypasses FR-1 (which requires a
Cap-prefixed class name) so this fixture isolates the FR-6 sweep
cleanly.

## Public API

`nonexistent_function_fr6_fixture` is exported in `__all__`.

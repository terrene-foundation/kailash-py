<!-- expected: findings=1 fr_codes=[FR-3 x1] origin=fr3_decorator_count -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — FR-3 Decorator Count

Status: TESTING-FIXTURE — asserts a decorator name + count that does
NOT match source. The gate's FR-3 sweep MUST flag this.

## Construction

The `@nonexistent_decorator_fr3_fixture` is applied to 99 functions
across the runtime layer.

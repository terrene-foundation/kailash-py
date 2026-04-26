<!-- expected: findings=1 fr_codes=[FR-5 x1] origin=fr5_field_existence -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — FR-5 Dataclass Field Existence

Status: TESTING-FIXTURE — asserts `Class.field` (no parens — field
form) where the class is real (`A2AAgentCard` exists in source with
indexed AnnAssign fields) but the field is fabricated. The gate's
FR-5 sweep MUST flag this once. The chosen class is stable: any
refactor that renames it triggers a FR-1 finding instead, which is the
desired loud-fail signal.

## Construction

The agent card carries `A2AAgentCard.fabricated_field_fr5_fixture`
for every row.

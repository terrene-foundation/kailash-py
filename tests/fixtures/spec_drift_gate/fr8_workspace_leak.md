<!-- expected: findings=1 fr_codes=[FR-8 x1] origin=fr8_workspace_leak -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — FR-8 Workspace Artifact Leak

Status: TESTING-FIXTURE — embeds an unprefixed `workspaces/<dir>/`
reference outside the legitimate citation prefixes (`Origin:`, `See`,
`Per`). The gate's FR-8 sweep MUST flag this once.

## Surface

The detailed design lives at workspaces/some-feature/02-plans/01-design.md
and informs the implementation order.

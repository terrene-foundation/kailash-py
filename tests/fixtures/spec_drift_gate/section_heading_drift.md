<!-- expected: findings=0 fr_codes=[] origin=section_heading_drift expected_warn=zero_allowlisted_sections -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — Heading-Drift Test

Status: TESTING-FIXTURE — exercises spec § 3.3 (zero allowlisted headings
emit a WARN line). The author wrote `## Public Interface` instead of
`## Surface` / `## Public API`; the gate's allowlist does NOT match, so
no FR sweeps fire AND a WARN is emitted noting "zero allowlisted sections
found".

## Public Interface

`FooManager` exposes a `read()` method.

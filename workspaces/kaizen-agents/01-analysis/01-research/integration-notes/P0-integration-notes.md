# Integration Notes — Milestone P0 (SDK Wiring)

## Discoveries

1. **Enum casing is the #1 adapter challenge** — SDK uses UPPERCASE values (e.g., `"AUTO_APPROVED"`), local uses lowercase (`"auto_approved"`). Name-based mapping (`SdkEnum[local.name]`) is robust because member NAMES are the same; only VALUES differ.

2. **Pre-computed lookup dicts are essential** — Building `{local_member: sdk_member}` maps at import time avoids per-call overhead. All 4 enum converters use this pattern.

3. **SDK PlanNode uses `agent_spec_id: str`** — Local uses `agent_spec: AgentSpec` (full object). Conversion requires flattening to spec_id for SDK, and looking up by spec_id for reverse. The reverse requires a `spec_registry` parameter.

4. **SDK Plan.gradient is `dict[str, Any]`** — Local uses `PlanGradient` dataclass. Must serialize PlanGradient to dict (with timedelta→float, GradientZone→string) at the boundary.

5. **ConstraintEnvelope has no SDK equivalent** — SDK uses opaque `dict[str, Any]` for envelopes. The local ConstraintEnvelope dataclass is an orchestration-specific type that STAYS. `envelope_to_dict()` / `envelope_from_dict()` handle conversion.

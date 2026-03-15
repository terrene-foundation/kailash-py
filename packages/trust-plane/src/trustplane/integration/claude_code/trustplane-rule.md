# TrustPlane Trust Environment

## Scope

These rules apply to ALL operations in this project.

## MUST Rules

### 1. Check Before Acting

Before performing any action in a gated category, call `trust_check` via the TrustPlane MCP server:

```
trust_check(action="<action>", resource="<file_or_resource>")
```

**Gated categories** (configurable per project):

- File modifications in protected directories
- Decision recording
- Content publication
- External communications

If `trust_check` returns **BLOCKED**, do NOT proceed. Explain the constraint to the user.
If `trust_check` returns **HELD**, wait for human resolution before proceeding.
If `trust_check` returns **FLAGGED**, proceed but note the flag to the user.

### 2. Record Significant Decisions

After completing any significant decision, call `trust_record`:

```
trust_record(
    decision="<what was decided>",
    rationale="<why>",
    decision_type="scope|design|argument|evidence|methodology",
    confidence=0.8
)
```

### 3. Do Not Modify Trust Infrastructure

MUST NOT directly modify files in the `trust-plane/` directory:

- `trust-plane/manifest.json`
- `trust-plane/anchors/`
- `trust-plane/chains/`
- `trust-plane/keys/`
- `trust-plane/holds/`

All modifications to trust state must go through TrustPlane tools.

### 4. Report Trust Status

When starting a new task, call `trust_status` to understand:

- Current trust posture
- Active session (if any)
- Constraint envelope

## Enforcement Tiers

| Tier | Mechanism                               | Status      |
| ---- | --------------------------------------- | ----------- |
| 1    | This rule file (contextual guidance)    | Active      |
| 2    | Pre-tool-use hook (process validation)  | Available   |
| 3    | MCP proxy (transport-level enforcement) | Implemented |

For infrastructure-enforced constraint checking, configure the MCP proxy (Tier 3).

# TrustPosture Canonical Reference

Authority: `src/kailash/trust/posture/postures.py`.

Every session that has touched TrustPosture has inverted the canonical-vs-alias relationship at least once — this reference makes the five canonical postures the grep target so the trap stops recurring.

## Canonical postures (use these in new code)

| Posture      | autonomy_level | Meaning                                                |
| ------------ | -------------- | ------------------------------------------------------ |
| `AUTONOMOUS` | 5              | Full autonomy; remote monitoring                       |
| `DELEGATING` | 4              | Agent executes, human monitors in real-time            |
| `SUPERVISED` | 3              | Agent proposes actions, human approves each one        |
| `TOOL`       | 2              | Human and agent co-plan; agent executes approved plans |
| `PSEUDO`     | 1              | Agent is interface only; human performs all reasoning  |

The enum is `str`-backed with lowercase values (`"autonomous"`, `"delegating"`, etc.). `autonomy_level` is a property on the enum, not a separate map.

## Backward-compat aliases (accepted but not preferred)

These aliases exist for deserializing records written against older code. New code MUST use the canonical names above.

| Alias attribute      | Resolves to canonical |
| -------------------- | --------------------- |
| `DELEGATED`          | `AUTONOMOUS`          |
| `CONTINUOUS_INSIGHT` | `DELEGATING`          |
| `SHARED_PLANNING`    | `SUPERVISED`          |
| `PSEUDO_AGENT`       | `PSEUDO`              |

`TrustPosture._missing_` also accepts the lowercase wire-format strings (`"delegated"`, etc.) and normalises hyphens/underscores.

## Removed names that raise `AttributeError`

If a test or older comment mentions one of these, it references a posture that no longer exists. Do NOT try to add them back — map to the canonical equivalent that matches the mapper's actual branch logic.

| Legacy name     | Canonical equivalent                                      |
| --------------- | --------------------------------------------------------- |
| `FULL_AUTONOMY` | `AUTONOMOUS`                                              |
| `HUMAN_DECIDES` | `TOOL` (approval_required branch of `TrustPostureMapper`) |
| `BLOCKED`       | `PSEUDO` (is_valid=False / denied branch)                 |
| `ASSISTED`      | `SUPERVISED` (sensitive/high-risk tool branch)            |

**`HUMAN_DECIDES → TOOL`, not `PSEUDO`.** This mapping is the one that keeps getting wrong. The mapper's approval_required branch returns `TOOL` (autonomy_level 2 — co-plan with human approval), not `PSEUDO` (autonomy_level 1 — pure interface). Read `TrustPostureMapper.map_verification_result` before inferring a mapping; do not guess from the enum name.

## Why this keeps going wrong

Two consecutive sessions' wrapup notes have listed the aliases as canonical:

- First inversion: session of 2026-04-15. Notes claimed "canonical values are `DELEGATED / CONTINUOUS_INSIGHT / SHARED_PLANNING / PSEUDO_AGENT`."
- Second inversion: session of 2026-04-16 (this session). Notes repeated the same claim. I briefed the first kaizen-specialist agent with the inverted mapping; the agent correctly read the source file and ignored the bias.

The trap is that the alias names are more verbose and "look more canonical" than the short canonical names. Grep for this file when in doubt.

## Mapper branch → canonical posture

From `TrustPostureMapper.map_verification_result` in `src/kailash/trust/posture/postures.py`:

| Condition                                                   | Returned posture |
| ----------------------------------------------------------- | ---------------- |
| `not is_valid`                                              | `PSEUDO`         |
| `approval_required or human_in_loop`                        | `TOOL`           |
| `is_sensitive_capability or is_high_risk_tool`              | `SUPERVISED`     |
| `audit_required` with `trust_level in {normal, high, full}` | `DELEGATING`     |
| `audit_required` with low/none trust                        | `SUPERVISED`     |
| `trust_level in {high, full}` and no audit/approval         | `AUTONOMOUS`     |
| default                                                     | `SUPERVISED`     |

Use this table when realigning tests after an API change — don't invent a mapping from the enum name, read the branch the verification takes.

## Serialization

- `posture.value` is the lowercase wire-format string (`"autonomous"`, `"tool"`, etc.).
- `PostureResult.to_dict()["posture"]` is the `.value`, not the name. A test asserting `data["posture"] == "tool"` passes; `data["posture"] == "TOOL"` does not.

# /redteam Integration — Posture-Scaled Audit Depth

/redteam audit rigor scales with posture. Higher trust = lighter touch; lower trust = full red-team.

## Audit Depth By Posture

| Posture               | /redteam mandatory rounds                                                                                          | Optional rounds                     |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------- |
| L5 DELEGATED          | Round 1 OPTIONAL (agent's discretion)                                                                              | Round 2+ on agent's discretion      |
| L4 CONTINUOUS_INSIGHT | **Round 1 MANDATORY** before merge — mechanical sweeps (grep, AST, pytest --collect-only, file-existence)          | Round 2 closure-parity recommended  |
| L3 SHARED_PLANNING    | **Round 1 + Round 2 MANDATORY** — closure-parity verification of every prior-round finding                         | Round 3 spec-compliance recommended |
| L2 SUPERVISED         | **Full red-team (Round 1+2+3) MANDATORY** — including spec compliance grep against every pending_verification rule | Round 4 if surface > 1000 LOC       |
| L1 PSEUDO_AGENT       | **N/A** — no autonomous /implement to red-team. /redteam invocations at L1 are advisory simulation only            |

## Mechanical Sweeps (Round 1)

Per `rules/agents.md` "Reviewer Mechanical Sweeps":

- `grep -c` parity on critical call-site patterns
- `pytest --collect-only -q` exit 0 across all test dirs
- Every public symbol in `__all__` added by this PR has an eager import
- AST-walk every `Literal[...]` / `Enum`-valued dispatch parameter; confirm exhaustive branches
- Grep `.claude/learning/violations.jsonl` for unaddressed entries from current session

## Closure-Parity (Round 2)

Per `rules/agents.md` "Audit/Closure-Parity Verification Specialist":

- For every prior-round finding, run gh pr view / gh pr diff / pytest --collect-only
- Convert FORWARDED rows to VERIFIED with command output evidence
- Specialist MUST be Bash+Read equipped (pact-specialist or general-purpose, NOT analyst)

## Spec Compliance (Round 3)

Per `rules/specs-authority.md`:

- For every promise in `specs/`, extract literal assertions (class signatures, field names, test names)
- AST-parse / grep the actual code; compute compliance percentage
- < 100% = block; feed gaps back to /implement

## Posture-aware /redteam invocation

```bash
# /redteam reads posture.json automatically; explicit posture override:
/redteam --posture L4   # forces L4 audit depth even if posture.json says L5
```

The invocation logs a violation if the agent attempts to UNDER-audit (e.g., running Round 1 only at L3 posture).

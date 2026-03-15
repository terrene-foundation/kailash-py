# TrustPlane Anti-Amnesia Entry

Add this to your project's anti-amnesia configuration to ensure
the AI remembers TrustPlane is active across context compactions.

## Template

```
This project uses TrustPlane for trust-gated operations.
- Call trust_status at session start to check posture and constraints
- Call trust_check before modifying protected files
- Call trust_record after significant decisions
- Never modify trust-plane/ directory directly
```

## Integration

In `.claude/hooks/anti-amnesia-rules.md`, add:

```markdown
## TrustPlane Active

This project uses TrustPlane. Before any action:

1. Check trust_status for current posture
2. Call trust_check for gated actions
3. Record decisions with trust_record
```

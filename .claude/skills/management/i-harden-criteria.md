# I-Harden Criteria

Reference material for the /i-harden command.


### Resilience Score: [X/6 categories passing]

| Category | Status | Critical Issues |
|----------|--------|-----------------|
| Text & Content | PASS/FAIL | ... |
| Internationalization | PASS/FAIL | ... |
| Error States | PASS/FAIL | ... |
| Edge Cases | PASS/FAIL | ... |
| Accessibility | PASS/FAIL | ... |
| Performance | PASS/FAIL | ... |

### Critical Fixes (must fix before shipping)
1. ...
# ... (see skill reference for full example)
```

## Testing Commands

After hardening, verify with these tests:

```bash
# Simulate slow network (Chrome DevTools)
# Network tab → Throttling → Slow 3G

# Test with screen reader
# macOS: Cmd+F5 (VoiceOver)

# Test zoom resilience
# Ctrl/Cmd + scroll to 200%

# Test keyboard navigation
# Tab through entire page, verify focus order
```

## Related Commands

- `/i-audit` - Run design audit before hardening
- `/design` - Design principles and responsive patterns
- `/test` - Testing strategies for frontend

## Agent Teams

Deploy specialist agents as needed. See agent definitions for review criteria.

## Skill References

- `.claude/skills/23-uiux-design-principles/SKILL.md` - Design principles (states, responsive)
- `.claude/skills/12-testing-strategies/SKILL.md` - Testing patterns

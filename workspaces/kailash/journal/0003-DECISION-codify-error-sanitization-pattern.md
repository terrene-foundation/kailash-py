---
type: DECISION
date: 2026-03-29
project: kailash
topic: Codified error sanitization as institutional security pattern
phase: codify
tags: [kaizen-agents, security, error-handling, codification]
---

# Decision: Codify Error Sanitization Pattern

## Choice

Added `str(exc)` → `type(exc).__name__` sanitization pattern to `kaizen-agents-security.md` as an institutional security pattern with enforcement table.

## Rationale

The red team (R2) found `str(exc)` leaking internal details in 4 locations across the delegate system. After fixing all 4, the pattern should be codified so future development follows the same approach. This prevents regression and ensures the pattern is applied consistently in new code.

## What Was Codified

1. **kaizen-delegate.md**: Event ordering documentation + error reporting semantics (which field carries errors in which path)
2. **kaizen-agents-security.md**: Error sanitization pattern with DO/DON'T examples and enforcement table listing all 5 sanitized locations

## What Was NOT Codified

- The error sanitization pattern was not promoted to a global rule — it's kaizen-agents specific. Global security rules (`rules/security.md`) already cover the principle; the skill captures the delegate-specific implementation.
- No new agent was created — the existing kaizen-specialist already covers this domain.

---
id: "S18-SECURITY-PATTERNS"
name: security-patterns
description: "Kailash security (Python) — validation, secrets, injection, authn/z. Hardcoded secrets BLOCKED."
---

# Security Patterns - Kailash SDK

Mandatory security patterns for all Kailash SDK development. These patterns prevent common vulnerabilities and ensure secure application development.

## Overview

Security patterns cover:

- Secret management (no hardcoded credentials)
- Input validation (prevent injection attacks)
- Authentication and authorization
- OWASP Top 10 prevention
- Secure API design
- Environment variable handling

## Critical Rules

### 1. NEVER Hardcode Secrets

```python
# ❌ WRONG - Hardcoded credentials
api_key = "sk-1234567890abcdef"
db_password = "mypassword123"

# ✅ CORRECT - Environment variables
import os
api_key = os.environ["API_KEY"]
db_password = os.environ["DATABASE_PASSWORD"]
```

### 2. Validate All User Inputs

```python
# ❌ WRONG - No validation
def process_user_input(user_data):
    return db.execute(f"SELECT * FROM users WHERE id = {user_data}")

# ✅ CORRECT - Parameterized queries (via DataFlow)
workflow.add_node("User_Read", "read_user", {
    "id": validated_user_id  # DataFlow handles parameterization
})
```

### 3. Use HTTPS for API Calls

```python
# ❌ WRONG - HTTP in production
workflow.add_node("HTTPRequestNode", "api", {
    "url": "http://api.example.com/data"  # Insecure!
})

# ✅ CORRECT - HTTPS always
workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com/data"
})
```

## Reference Documentation

Each entry below is a depth file that ships alongside this skill. Regenerated
from the directory contents — the previous index listed eight `security-*.md`
files that exist nowhere in the corpus, so every lookup dead-ended.

### Credentials & Secrets

- **[credential-decode-helpers](credential-decode-helpers.md)** - One shared userinfo decoder; null-byte rejection after percent-decoding
- **[credential-url-handling](credential-url-handling.md)** - Canonical connection-string credential pipeline (py)

### Input Handling & Injection

- **[sanitizer-contract](sanitizer-contract.md)** - Display hygiene: token-replace sentinels, type-confusion raises
- **[path-containment](path-containment.md)** - Resolve and normalize both candidate and root before the trust decision

### Authorization & Defaults

- **[secure-defaults-and-approver-identity](secure-defaults-and-approver-identity.md)** - Fail-closed defaults; server-derived, immutably-pinned approver identity
- **[multi-site-kwarg-plumbing](multi-site-kwarg-plumbing.md)** - Every call site learns a security-relevant kwarg in the same PR
- **[frontmatter-directive-trust-surface](frontmatter-directive-trust-surface.md)** - Frontmatter is the directive trust surface, never a body scan

### Database (DataFlow / RLS)

- **[dataflow-rls-posture](dataflow-rls-posture.md)** - RLS as a runtime predicate, not DDL
- **[rls-security-definer-preauth-carveout](rls-security-definer-preauth-carveout.md)** - The SECURITY DEFINER pre-auth carveout

### Build & Distribution

- **[docker-disclosure-scrub](docker-disclosure-scrub.md)** - Build-time public-surface disclosure gate

### Chained Exploits (cross-cutting)

- **[security-attack-chains](security-attack-chains.md)** - Multi-step chains from the v2.1.0 red team: Redis-URL injection + `pickle.loads` RCE, `eval`/`__import__` code injection, auth degradation + timing, PACT governance bypass (py)

## Security Checklist

### Before Every Commit

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL/code injection prevented
- [ ] HTTPS used for all API calls
- [ ] Sensitive data not logged
- [ ] Error messages don't expose internals

### Before Every Deployment

- [ ] Environment variables configured
- [ ] Secrets stored in secure vault
- [ ] Authentication enabled
- [ ] Authorization rules defined
- [ ] OWASP Top 10 checked
- [ ] Security review completed

## Common Vulnerabilities Prevented

| Vulnerability            | Prevention Pattern                        |
| ------------------------ | ----------------------------------------- |
| SQL Injection            | Use DataFlow parameterized nodes          |
| Code Injection           | Avoid `eval()`, use PythonCodeNode safely |
| Credential Exposure      | Environment variables, secret managers    |
| XSS                      | Output encoding, CSP headers              |
| CSRF                     | Token validation, SameSite cookies        |
| Insecure Deserialization | Validate serialized data                  |

## Integration with Rules

Security patterns are enforced by:

- `.claude/rules/security.md` - Security rules
- `.claude/hooks/validate-bash-command.js` - Command validation
- `gold-standards-validator` agent - Compliance checking

## When to Use This Skill

Use this skill when:

- Handling user input or external data
- Storing or transmitting credentials
- Making API calls to external services
- Implementing authentication/authorization
- Conducting security reviews
- Preparing for deployment

## Related Skills

- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Mandatory best practices
- **[16-validation-patterns](../16-validation-patterns/SKILL.md)** - Validation patterns
- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core workflow patterns

## Support

For security-related questions, invoke:

- `security-reviewer` - OWASP-based security analysis
- `gold-standards-validator` - Compliance checking
- `testing-specialist` - Security testing patterns

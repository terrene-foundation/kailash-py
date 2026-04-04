---
name: security-patterns
description: "Security patterns and best practices for Kailash SDK including input validation, secret management, injection prevention, authentication, authorization, and OWASP compliance. Use when asking about 'security', 'secrets', 'authentication', 'authorization', 'injection prevention', 'input validation', 'OWASP', 'credentials', 'API keys', 'secure coding', or 'security review'."
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
workflow.add_node("APICallNode", "api", {
    "url": "http://api.example.com/data"  # Insecure!
})

# ✅ CORRECT - HTTPS always
workflow.add_node("APICallNode", "api", {
    "url": "https://api.example.com/data"
})
```

## Reference Documentation

### Core Security
- **[security-secrets](security-secrets.md)** - Secret management patterns
- **[security-input-validation](security-input-validation.md)** - Input validation
- **[security-injection-prevention](security-injection-prevention.md)** - SQL/code injection prevention

### Authentication & Authorization
- **[security-auth-patterns](security-auth-patterns.md)** - Auth best practices
- **[security-api-keys](security-api-keys.md)** - API key management
- **[security-tokens](security-tokens.md)** - Token handling

### OWASP Compliance
- **[security-owasp-top10](security-owasp-top10.md)** - OWASP Top 10 prevention
- **[security-audit-checklist](security-audit-checklist.md)** - Security audit checklist

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

| Vulnerability | Prevention Pattern |
|--------------|-------------------|
| SQL Injection | Use DataFlow parameterized nodes |
| Code Injection | Avoid `eval()`, use PythonCodeNode safely |
| Credential Exposure | Environment variables, secret managers |
| XSS | Output encoding, CSP headers |
| CSRF | Token validation, SameSite cookies |
| Insecure Deserialization | Validate serialized data |

## Integration with Rules

Security patterns are enforced by:
- `.claude/rules/security.md` - Security rules
- `scripts/hooks/validate-bash-command.js` - Command validation
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

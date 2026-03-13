# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.12.x  | Yes                |
| < 0.12  | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in Kailash, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email **security@terrene.foundation** with:

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Any suggested fixes (optional)

We will acknowledge receipt within 48 hours and provide an initial assessment within 5 business days.

## Security Practices

- All API keys and credentials must use environment variables (never hardcoded)
- All database queries use parameterized queries or ORM
- All user input is validated before use
- Dependencies are regularly audited for known vulnerabilities
- The CARE/EATP trust framework provides cryptographic verification of workflow execution

## Disclosure Policy

We follow coordinated disclosure. Once a fix is available, we will:

1. Release a patched version
2. Publish a security advisory on GitHub
3. Credit the reporter (unless they prefer anonymity)

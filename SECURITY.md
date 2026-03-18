# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in Kailash Python SDK, please report it
responsibly through coordinated disclosure.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email **security@terrene.foundation** with:

- A description of the vulnerability
- Steps to reproduce the issue
- Affected versions
- Potential impact assessment
- Any suggested fixes (optional)

We will acknowledge receipt within 48 hours and provide an initial assessment
within 5 business days.

## Disclosure Policy

We follow coordinated disclosure. No public disclosure is made until a fix is
released. Once a patched version is available, we will:

1. Release the patched version to PyPI
2. Publish a GitHub Security Advisory
3. Credit the reporter (unless they prefer anonymity)

## Security Practices

- All API keys and credentials must use environment variables — never hardcoded
- All database queries use parameterized queries or ORM
- All user input is validated before use
- Dependencies are audited regularly for known vulnerabilities
- The CARE/EATP trust framework provides cryptographic verification of workflow
  execution via Ed25519 signatures and HMAC-based tamper detection

## License

Kailash Python SDK is licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE) for details.

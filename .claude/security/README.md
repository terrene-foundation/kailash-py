# Security Testing Resources

This directory contains comprehensive penetration testing and security assessment resources for the Kaizen AI Framework.

## Contents

### 1. **PENETRATION_TESTING_GUIDE.md**
Comprehensive, framework-agnostic penetration testing methodology covering:
- OWASP Top 10 (2021)
- PTES (Penetration Testing Execution Standard)
- NIST Cybersecurity Framework
- Tool arsenal (Nmap, Burp Suite, OWASP ZAP, Metasploit, etc.)
- Compliance frameworks (PCI DSS, HIPAA, GDPR, ISO 27001)
- Reporting templates
- CI/CD security integration

**Use Case**: Reusable across ALL projects (web apps, APIs, cloud infrastructure)

### 2. **KAIZEN_PENTEST_CHECKLIST.md**
Kaizen-specific penetration testing checklist covering:
- AI-specific attack vectors (prompt injection, model manipulation)
- Control Protocol security (HTTP/HTTPS enforcement)
- Hooks System security (RBAC, hook validation, process isolation)
- Memory & Checkpoint security (encryption, multi-tenancy)
- Multi-agent coordination security (A2A protocol)
- LLM integration security (API key management, rate limiting)
- DataFlow security (SQL injection prevention)
- Infrastructure security (containers, Kubernetes, AWS)

**Use Case**: Kaizen framework-specific security validation

### 3. **run_security_scan.sh**
Automated security scanning orchestration script:
- Dependency vulnerability scanning (safety, pip-audit)
- Secret scanning (detect-secrets, pattern matching)
- Static analysis (bandit, semgrep)
- Container scanning (trivy)
- License compliance checking
- Consolidated reporting with severity classification

**Use Case**: Automated daily/weekly security scanning

### 4. **automated_pentest.py**
Kaizen-specific automated penetration testing script:
- Prompt injection resistance testing
- Tool calling security validation
- Control protocol TLS enforcement verification
- Checkpoint encryption validation
- Multi-tenancy isolation testing
- API key leakage detection
- CVSS scoring and remediation priorities

**Use Case**: Framework-specific security validation with automated test execution

### 5. **GitHub Actions Workflow (../.github/workflows/security-scan.yml)**
CI/CD security integration:
- Runs on push, PR, and weekly schedule
- Parallel execution of all security scans
- SARIF upload to GitHub Security
- Artifact retention for 30 days
- Automated summary reports

**Use Case**: Continuous security validation in CI/CD pipeline

## Quick Start

### Option 1: Automated Security Scanning (Recommended)

```bash
# 1. Set up test environment (IMPORTANT: Use test API keys only!)
cd ./repos/dev/kailash_kaizen/apps/kailash-kaizen

# Copy environment template
cp .env.example .env.pentest

# Edit .env.pentest with TEST API keys (not production!)
vim .env.pentest

# 2. Run comprehensive automated security scan
./.claude/security/run_security_scan.sh

# Run full scan (slower, more thorough)
./.claude/security/run_security_scan.sh --full

# Custom report directory
./.claude/security/run_security_scan.sh --report-dir /path/to/reports
```

### Option 2: Kaizen-Specific Automated Tests

```bash
# Run Kaizen-specific penetration tests
python .claude/security/automated_pentest.py

# Run full scan with all tests
python .claude/security/automated_pentest.py --full

# Custom report directory
python .claude/security/automated_pentest.py --report-dir /path/to/reports
```

### Option 3: Manual Security Scans

```bash
# 1. Set up test environment (IMPORTANT: Use test API keys only!)
cd ./repos/dev/kailash_kaizen/apps/kailash-kaizen

# Copy environment template
cp .env.example .env.pentest

# Edit .env.pentest with TEST API keys (not production!)
vim .env.pentest

# 2. Install security testing dependencies
pip install safety bandit detect-secrets semgrep pip-audit pip-licenses

# 3. Run basic security scans
#    Dependency vulnerabilities
safety check
pip-audit

#    Static analysis (Python security issues)
bandit -r src/kaizen -ll

#    Secret scanning
detect-secrets scan --baseline .secrets.baseline

# 4. Run Kaizen-specific tests
#    Follow KAIZEN_PENTEST_CHECKLIST.md manually
```

### AWS Penetration Testing Infrastructure

If you need dedicated AWS infrastructure for penetration testing:

```bash
# 1. Configure AWS SSO for Terrene Foundation account
aws configure sso

# 2. Launch Kali Linux pentest workstation
aws ec2 run-instances \
  --image-id ami-xxxxx \  # Kali Linux AMI (find latest in your region)
  --instance-type t3.medium \
  --key-name your-pentest-key \
  --security-group-ids sg-xxxxx \  # Configure security group first
  --subnet-id subnet-xxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=kaizen-pentest-workstation}]'

# 3. SSH into pentest workstation
ssh -i ~/.ssh/your-pentest-key.pem kali@<instance-public-ip>

# 4. Run tests from isolated environment
# (Prevents accidental production system impact)
```

### Reporting Security Issues

**CRITICAL SECURITY VULNERABILITIES**: Report privately to security@terrene-foundation.ai

**For all findings**:
1. Document vulnerability with:
   - Description
   - Reproduction steps
   - Impact assessment (CVSS score)
   - Proof of concept (PoC)
   - Screenshots/evidence
2. Classify severity: CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL
3. Propose remediation
4. Set remediation timeline based on severity:
   - CRITICAL (CVSS 9.0-10.0): 0-24 hours
   - HIGH (CVSS 7.0-8.9): 7 days
   - MEDIUM (CVSS 4.0-6.9): 30 days
   - LOW (CVSS 0.1-3.9): 90 days

## Security Testing Schedule

### Weekly (Automated)
- Dependency scanning (safety, npm audit, pip audit)
- Secret scanning (truffleHog, git-secrets)
- Static analysis (bandit, semgrep)
- Container scanning (trivy)

### Monthly (Semi-Automated)
- Dynamic application security testing (DAST) with OWASP ZAP
- API security testing
- Infrastructure security scanning (AWS Prowler, ScoutSuite)

### Quarterly (Manual)
- Comprehensive penetration testing (follow KAIZEN_PENTEST_CHECKLIST.md)
- Social engineering tests (if authorized)
- Physical security assessment (if applicable)

### Annually
- Third-party security audit
- Compliance validation (PCI DSS, HIPAA, GDPR, SOC 2)
- Disaster recovery testing
- Incident response tabletop exercises

## Compliance Validation

### PCI DSS v4.0
- **Requirement 11.4**: Penetration testing at least annually
- **Requirement 11.4.1**: Follow industry-standard methodology (PTES, OWASP)
- **Requirement 11.4.2**: Cover all system components
- **Requirement 11.4.3**: Test web applications
- **Requirement 11.4.4**: Correct exploitable vulnerabilities

### HIPAA
- **§ 164.308(a)(8)**: Periodic evaluation of security measures
- **§ 164.312(a)(2)(iv)**: Audit controls
- **§ 164.308(a)(1)(ii)(A)**: Risk analysis

### GDPR
- **Article 32**: Regular testing and evaluation of security measures

### ISO 27001
- **Control A.18.2.3**: Technical compliance review

## Tool Recommendations

### Open Source (Free)
- **Nmap**: Network scanning
- **OWASP ZAP**: Web application scanner
- **Nikto**: Web server scanner
- **SQLMap**: SQL injection testing
- **Metasploit**: Exploitation framework
- **Burp Suite Community**: Web app testing
- **Trivy**: Container vulnerability scanner
- **Prowler**: AWS security assessment

### Commercial (Paid)
- **Burp Suite Professional**: Comprehensive web app testing ($449/year)
- **Nessus Professional**: Vulnerability scanner ($4,890/year)
- **Acunetix**: Web app scanner ($4,500/year)
- **Qualys**: Continuous security monitoring (contact sales)
- **Synopsys**: Static analysis (contact sales)

### Cloud-Native
- **AWS Inspector**: Automated vulnerability management
- **AWS GuardDuty**: Threat detection
- **Azure Security Center**: Unified security management
- **GCP Security Command Center**: Centralized security

## Resources

### Training
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **Portswigger Web Security Academy**: https://portswigger.net/web-security (Free!)
- **HackTheBox**: https://www.hackthebox.com/ (CTF platform)
- **TryHackMe**: https://tryhackme.com/ (Beginner-friendly)
- **SANS Penetration Testing**: https://www.sans.org/cyber-security-courses/

### Certifications
- **CEH (Certified Ethical Hacker)**: Entry-level
- **OSCP (Offensive Security Certified Professional)**: Practical
- **GWAPT (GIAC Web Application Penetration Tester)**: Web-focused
- **GPEN (GIAC Penetration Tester)**: Network-focused

### Communities
- **OWASP**: https://owasp.org/
- **HackerOne**: https://hackerone.com/
- **Bugcrowd**: https://www.bugcrowd.com/
- **/r/netsec**: https://reddit.com/r/netsec

## Legal Notice

**IMPORTANT**: Only test systems you own or have written authorization to test.

Unauthorized access to computer systems is illegal under laws including:
- **USA**: Computer Fraud and Abuse Act (CFAA)
- **UK**: Computer Misuse Act 1990
- **EU**: Directive 2013/40/EU on attacks against information systems

**Always obtain written authorization before testing.**

---

**Last Updated**: 2025-11-02
**Next Review**: 2026-02-02
**Maintainer**: Security Team (security@terrene-foundation.ai)

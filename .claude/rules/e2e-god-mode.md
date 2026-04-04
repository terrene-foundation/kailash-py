---
paths:
  - "tests/e2e/**"
  - "**/*e2e*"
  - "**/*playwright*"
---

# E2E God-Mode Testing Rules

### 1. Create ALL Missing Records

When a required record is missing (404, 403, empty response): create it immediately via API or direct DB. MUST NOT skip, document as "gap", or report as "expected behavior."

### 2. Adapt to Data Changes

Test data changes between runs. Query the API to discover actual records before testing. MUST NOT hardcode user emails, IDs, or other test data.

### 3. Implement Missing Endpoints

If an API endpoint doesn't exist and testing needs it: implement it immediately. MUST NOT document as "limitation."

### 4. Follow Up on Failures

When an operation fails gracefully (error displayed, no crash): investigate root cause and fix. MUST NOT report "graceful failure" and move on.

### 5. Assume Correct Role

During multi-persona testing, log in as the role needed for each operation (admin for admin actions, restricted user for restricted views).

## Pre-E2E Checklist

- Backend and frontend running
- .env loaded and verified
- Required users, resources, and access records exist (query API, create if missing)

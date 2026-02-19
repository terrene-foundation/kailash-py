# E2E God-Mode Testing Rules

## Scope

These rules apply to ALL end-to-end testing, validation, and browser-based test runs.

## ABSOLUTE RULES

### 1. God-Mode: Create ALL Missing Records

When running E2E tests and a required record is missing (404, 403, empty response):

**MUST**: Create the missing record immediately using the appropriate API or direct database access.
**MUST NOT**: Skip the test, document it as a "gap", or report it as "expected behavior".

**Pattern:**

```
1. Attempt operation
2. If 404/403/missing -> identify what's missing
3. Create the missing record via API (use admin credentials)
4. Retry the original operation
5. NEVER skip or move on
```

### 2. Adapt to Data Changes

Test data WILL change between runs. User emails, IDs, names may all differ.

**MUST**: Query the API to discover actual records before testing.
**MUST NOT**: Hardcode user emails, IDs, or other test data.

**Pattern:**

```
1. Before testing, query the list endpoint to get actual records
2. Find the record matching the role/type, not a hardcoded name
3. Use the ACTUAL values from the query
4. If no matching record exists, CREATE one
```

### 3. Implement Missing Endpoints

If an API endpoint doesn't exist and testing needs it:

**MUST**: Implement the endpoint immediately.
**MUST NOT**: Document it as a "limitation" and move on.

### 4. Follow Up on Failures

When an operation fails gracefully (error message displayed, no crash):

**MUST**: Investigate the root cause and implement a fix.
**MUST NOT**: Report "graceful failure" and move to next test.

**Pattern:**

```
1. Operation fails with error
2. Check backend logs for root cause
3. If missing API key -> verify .env is loaded
4. If missing record -> create it (Rule 1)
5. If missing endpoint -> implement it (Rule 3)
6. Retry the operation
7. Only move on after SUCCESS or explicit user instruction to skip
```

### 5. Assume Correct Role

During multi-persona testing, assume the role needed for each operation.

**Pattern:**

```
1. Need admin actions -> log in as admin/owner
2. Need to test restricted views -> log in as restricted user
3. Need to test RBAC -> try each role and verify access/denial
```

## Pre-E2E Checklist

Before starting ANY E2E test run:

- [ ] Backend running and healthy
- [ ] Frontend dev server running
- [ ] .env loaded and verified (check MODEL and API_KEY vars)
- [ ] Required users exist (query API, create if missing)
- [ ] Required resources exist (query API, create if missing)
- [ ] Access records exist (query API, create if missing)

## Exceptions

NO EXCEPTIONS for rules 1-4. If you cannot create a record, escalate to the user immediately.
Rule 5 exception: User explicitly says "only test as X role".

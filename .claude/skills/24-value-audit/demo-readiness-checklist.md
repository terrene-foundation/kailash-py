# Demo Readiness Checklist

A pass/fail checklist to run before any enterprise demo. Each item is binary — it either passes or it doesn't. A single CRITICAL failure means the demo is not ready.

## Pre-Flight Checks

### Environment

- [ ] **Login works** — credentials authenticate, redirect to correct page
- [ ] **Zero console errors** — no JavaScript errors across all demo pages
- [ ] **Pages load under 3s** — no spinners hanging, no blank screens
- [ ] **SSL valid** — no certificate warnings

### Data State

- [ ] **No empty pages in the demo path** — every page shown has meaningful data
- [ ] **Numbers add up** — metrics are internally consistent (trust agent count matches posture breakdown, success rates have actual completions, etc.)
- [ ] **Realistic data** — names, roles, dates, amounts look like a real organization (not "Test User 1", "Lorem Ipsum")
- [ ] **Appropriate recency** — dates and timestamps are recent, not weeks/months old
- [ ] **Role correctness** — user roles match the story (CEO is Owner, CIO is Admin, not Developer)

### Value Flow

- [ ] **At least one completed objective** — demonstrates the full cycle: submit → agent work → result
- [ ] **At least one in-progress item** — shows the system is alive, not historical
- [ ] **At least one human-in-the-loop moment** — escalation, approval, or decision point
- [ ] **Trust progression visible** — at least one agent has moved from Pseudo to Supervised or higher
- [ ] **Governance evidence** — audit trail has entries, compliance dashboard has data

### Navigation

- [ ] **All demo flow links work** — every click in the planned demo path leads to the right page
- [ ] **No dead ends** — every page has a meaningful next action
- [ ] **Back navigation works** — can recover from any accidental click

## Severity Criteria

### CRITICAL (Demo cannot proceed)

- Login fails
- Any page in the demo path shows an error
- Any page in the demo path is completely empty
- Core value claim is unsubstantiated (e.g., "governance" with empty compliance)

### HIGH (Demo credibility at risk)

- Data contradictions visible on screen
- Key metrics are obviously wrong (100% success with 0 completions)
- Trust chain shows "Invalid"
- Console errors visible if DevTools opened

### MEDIUM (Demo needs explanation)

- Non-demo pages are empty (acceptable if not shown)
- Terminology unclear without explanation
- Two pages overlap in purpose

### LOW (Ignorable in demo context)

- Minor label issues
- Pagination not needed for demo data size
- Settings pages incomplete

## Quick Verification Script

For each demo step, verify in Playwright:

```
1. Navigate to page
2. Take accessibility snapshot
3. Check: are there data records? (not just headers and empty states)
4. Check: do metrics show non-zero values?
5. Check: are primary actions visible and enabled?
6. Check: console has 0 errors
7. Record: pass/fail per criterion
```

## Demo Data Requirements

### Minimum Viable Demo State

| Entity                 | Count    | Key Properties                                         |
| ---------------------- | -------- | ------------------------------------------------------ |
| Users                  | 3-5      | Varied roles (Owner, Admin, Developer), all active     |
| Shadow Agents          | 3-5      | Varied trust postures (not all Pseudo), health metrics |
| Completed Objectives   | 2-3      | With visible results and audit trail                   |
| In-Progress Objectives | 1        | With real-time agent activity                          |
| Knowledge Items        | 3-5      | Policies, procedures, frameworks                       |
| Directives             | 2-3      | Mix of acknowledged, pending                           |
| Bridges                | 1-2      | At least 1 standing, 1 scoped                          |
| Policies (ABAC)        | 2-3      | Budget, data access, working hours                     |
| Audit Events           | 10+      | Recent, varied types                                   |
| Constraint Violations  | 2-3      | With severity levels                                   |
| Metrics                | Non-zero | Executions, success rate, tokens, cost                 |
| Task Inbox Items       | 1-2      | At least 1 escalation requiring approval               |

### Data Consistency Rules

- Agent count on Shadow Agents page = agent count on Trust Postures page
- Trust posture breakdown accounts for ALL agents
- Success rate denominator is > 0 (never show 100% with 0 completions)
- "Active" agents have recent activity timestamps
- Role assignments in Org Builder match user assignments
- Session message counts are > 0 for active sessions

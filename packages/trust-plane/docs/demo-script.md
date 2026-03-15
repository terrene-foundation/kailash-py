# TrustPlane Demo Script

A before-and-after demonstration of TrustPlane. Use this script for
live demos, internal pitches, or to explain the value proposition to
someone in under five minutes.

---

## The Setup

You are a developer. You asked an AI assistant to implement a user
authentication feature on your web app. The AI wrote code, ran tests,
read documentation, and modified configuration files. Thirty minutes
later, the feature is done.

Your manager asks: "What exactly did the AI do?"

---

## WITHOUT TrustPlane

You open your terminal and try to reconstruct what happened.

**Q: What files did the AI modify?**

You check git:

```bash
git diff --stat HEAD~1
```

```
 src/auth/oauth.py              | 142 +++++++++++++++
 src/auth/middleware.py          |  38 +++++
 tests/test_oauth.py            |  89 ++++++++++
 config/production.yml           |   3 +-
 .github/workflows/deploy.yml   |   7 ++-
 5 files changed, 276 insertions(+), 3 deletions(-)
```

You can see WHAT changed, but not WHY. And you notice two concerning
files: `config/production.yml` and `.github/workflows/deploy.yml`.

**Q: Why did the AI modify the production config?**

You don't know. The AI conversation is gone. Maybe it was necessary.
Maybe it was a mistake. Maybe the AI hallucinated a requirement. You
have no way to tell.

**Q: Did the AI access any secrets?**

You don't know. There's no record of what the AI read. It might have
read `.env` to check variable names. It might not have. You can't
answer this question.

**Q: Did anyone review the architecture decision?**

What architecture decision? You asked for "auth" and got OAuth2. Was
that the right choice? Were alternatives considered? You have a PR
with code, but no record of the reasoning.

**Q: Can you prove to compliance that the AI stayed within bounds?**

No. You have code diffs. That is all.

---

## WITH TrustPlane

Same scenario. Same AI. Same feature. But this time, TrustPlane was
running.

### Step 1: You started with shadow mode (zero config)

Before the AI began work, shadow mode was already recording. No setup
required.

```bash
attest shadow --report
```

```markdown
# Shadow Mode Report

**Session**: 7f3a9b2c-...
**Started**: 2026-03-15T14:00:00+00:00

## Summary

- **Total tool calls**: 47
- **Would pass**: 43
- **Would be held**: 3
- **Would be blocked**: 1
- **Block rate**: 2.1%

## Flagged Actions

- **[HELD]** `Edit` on `config/production.yml`
  - Reason: Write to 'config/production.yml' not in allowed write paths
- **[HELD]** `Write` on `.github/workflows/deploy.yml`
  - Reason: Write to '.github/workflows/deploy.yml' not in allowed write paths
- **[HELD]** `Edit` on `database/migrations/001.sql`
  - Reason: Write to 'database/migrations/001.sql' not in allowed write paths
- **[BLOCKED]** `access_production` on `prod-db.internal`
  - Reason: Action 'access_production' is in blocked_actions
```

Now you KNOW:

- The AI made 47 tool calls (not a mystery anymore).
- 43 of them were fine.
- 3 would have been held for review.
- 1 would have been blocked outright.
- The production config change is flagged -- you know it happened and
  can investigate.

### Step 2: You initialized governance

```bash
attest init --name "Acme Auth Feature" --author "Jane Developer"
attest template apply software
```

### Step 3: Decisions were recorded

```bash
attest decisions
```

```
[dec-a1b2c3d4e5f6] scope: Use OAuth2 instead of custom auth
  Rationale: Reduces security surface area and maintenance burden
  Review: standard | Confidence: 0.9

[dec-f6e5d4c3b2a1] design: React Server Components for auth flow
  Rationale: SSR improves initial load; reduces client JS bundle
  Review: standard | Confidence: 0.85

[dec-1234abcd5678] technical: httpOnly cookies for token storage
  Rationale: Prevents XSS token theft
  Review: full | Confidence: 0.95
```

Now you can answer "why OAuth2?" with a specific, timestamped,
cryptographically signed record.

### Step 4: The chain verifies

```bash
attest verify
```

```
Project: Acme Auth Feature (proj-a1b2c3d4e5f6)
Chain valid: True
Anchors: 6
Decisions: 3
Milestones: 1
Audits: 0

No integrity issues detected.
```

Every record is linked, signed, and verifiable. No one -- not the AI,
not the developer, not an attacker -- can modify the audit trail
without breaking the chain.

### Step 5: You exported proof

```bash
attest export --format json -o auth-feature-bundle.json
```

This bundle contains everything a third party needs to independently
verify what happened, without access to your TrustPlane installation.

---

## The Contrast

| Question                             | Without TrustPlane | With TrustPlane                                                 |
| ------------------------------------ | ------------------ | --------------------------------------------------------------- |
| What did the AI do?                  | Check git diff     | `attest shadow --report` -- every tool call recorded            |
| Why did it modify production config? | No idea            | Shadow report flags it; decision record explains why            |
| Did it access secrets?               | Unknown            | Shadow mode shows all file reads; blocked paths prevent access  |
| Were alternatives considered?        | No record          | Decision record lists alternatives and rationale                |
| Can you prove compliance?            | Code diffs only    | Cryptographically signed, hash-linked, independently verifiable |
| How long to answer these questions?  | Hours of forensics | Seconds with `attest verify` and `attest decisions`             |

---

## The Pitch (30 seconds)

TrustPlane is a flight recorder for AI-assisted work. You install it,
the AI works normally, and afterward you have a cryptographic record
of every decision, every action, and every checkpoint. When someone
asks "what did the AI do?", you don't guess -- you prove it.

Shadow mode requires zero setup. Governance adds constraint enforcement.
The trust chain is tamper-evident and independently verifiable. That is
the difference between "I think the AI was fine" and "here is the
signed proof."

---

## Running This Demo Live

If you are presenting this demo live, here is the sequence:

```bash
# 1. Show shadow mode (no init needed)
attest shadow

# 2. Show a shadow report (pre-recorded sessions)
attest shadow --report

# 3. Initialize governance
attest init --name "Demo Project" --author "Presenter"

# 4. Show available templates
attest template list

# 5. Apply the software template
attest template apply software

# 6. Record a decision
attest decide \
  --type scope \
  --decision "Use OAuth2 for authentication" \
  --rationale "Industry standard, reduced maintenance" \
  --alternative "Custom JWT auth" \
  --confidence 0.9

# 7. Record a milestone
attest milestone \
  --version v0.1 \
  --description "Authentication feature complete"

# 8. Show project status
attest status

# 9. List decisions
attest decisions

# 10. Verify the chain
attest verify

# 11. Export
attest export --format json -o demo-bundle.json
```

Total time: under 3 minutes. The audience sees the full lifecycle from
observation to cryptographic proof.

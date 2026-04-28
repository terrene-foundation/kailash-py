# User Flow: Developer Adoption

## Persona: Senior Developer Using AI Coding Assistant

**Context**: Uses Claude Code (or Cursor/Copilot) daily. Has heard about AI governance requirements. Wants to try TrustPlane.

---

## Flow 1: First Contact (Shadow Mode)

### Step 1: Install

```bash
pip install trust-plane
```

**Sees**: Clean install, pulls eatp dependency automatically
**Expects**: No errors, no configuration needed

### Step 2: Initialize

```bash
cd my-project
attest init --name "My Project" --author "Jane Doe"
```

**Sees**: `Trust plane initialized at .trust-plane/` with genesis record
**Expects**: Quick, simple, one command

### Step 3: Shadow Mode (zero-config observation)

```bash
attest shadow
```

**Sees**: "Shadow mode active. Observing AI activity. Run `attest report` to see findings."
**Expects**: AI assistant continues working normally. No interruption.

### Step 4: First Report

```bash
attest report
```

**Sees**: Summary of AI actions taken, constraint utilization, decisions made
**Expects**: "Ah, I can see what the AI actually did. Interesting."

**Value moment**: The developer sees for the first time a structured view of what their AI assistant has been doing. This is the hook.

---

## Flow 2: Constraint Setup

### Step 5: Apply Template

```bash
attest template list
attest template apply software
```

**Sees**: Constraint envelope applied — operational, data access, financial, temporal, communication dimensions configured with sensible defaults
**Expects**: Reasonable defaults that can be customized

### Step 6: Check Constraint Status

```bash
attest diagnose
```

**Sees**: Constraint quality score (0-100), recommendations for tuning
**Expects**: Guidance on what to tighten/loosen

### Step 7: Switch to Strict Mode

```bash
attest enforce strict
```

**Sees**: "Enforcement mode: strict. Actions exceeding constraints will be held."
**Expects**: The AI will now be constrained. Held actions require human approval.

---

## Flow 3: Daily Workflow (with AI assistant)

### Step 8: Start Session

AI assistant calls `trust_check` before tool use (via MCP server or Tier 2 hook).

**Sees** (AI perspective): `{"verdict": "AUTO_APPROVED", "constraints_checked": 5}`
**Developer sees**: Nothing — approved actions proceed silently

### Step 9: Constraint Hit

AI assistant tries to access a blocked path.

**Sees** (AI perspective): `{"verdict": "HELD", "reason": "Path /production/db not in allowed write scope"}`
**Developer sees**: "Action held: AI attempted to write to /production/db. Approve or deny?"

### Step 10: Human Resolution

```bash
attest hold list
attest hold approve hold-001 --reason "One-time migration approved"
```

**Sees**: Hold resolved, AI can proceed
**Expects**: Clear workflow for approving/denying held actions

---

## Flow 4: Audit & Verification

### Step 11: Verify Chain Integrity

```bash
attest verify
```

**Sees**: "Chain integrity: VALID. 47 anchors verified. No tampering detected."
**Expects**: Confidence that the audit trail is intact

### Step 12: Generate Report

```bash
attest audit
```

**Sees**: Markdown report with timeline, decisions, constraint utilization, competency map
**Expects**: Auditor-ready documentation

### Step 13: Export for Independent Verification

```bash
attest export --format bundle
```

**Sees**: JSON + HTML verification bundle. Anyone with the public key can verify.
**Expects**: Self-contained artifact for external auditors

---

## Flow 5: CI Integration

### Step 14: Pre-commit Verification

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: trust-verify
        name: TrustPlane Verify
        entry: attest verify
        language: system
        pass_filenames: false
```

**Sees**: Every commit verified against trust chain
**Expects**: Automated, no manual steps

### Step 15: GitHub Action

```yaml
# .github/workflows/trust.yml
- uses: trustplane/verify-action@v1
  with:
    trust-dir: .trust-plane
```

**Sees**: PR check showing trust chain status
**Expects**: Visual indicator that governance is maintained

---

## Key Transitions

| From               | To                 | Trigger                       | Friction                          |
| ------------------ | ------------------ | ----------------------------- | --------------------------------- |
| Not installed      | Installed          | Curiosity, recommendation     | LOW — `pip install`               |
| Installed          | Shadow mode        | `attest init + shadow`        | LOW — 2 commands                  |
| Shadow mode        | Reviewing reports  | First `attest report`         | MEDIUM — understanding the output |
| Reviewing reports  | Template applied   | Wanting constraints           | MEDIUM — choosing template        |
| Template applied   | Strict enforcement | Confidence in constraints     | LOW — one command                 |
| Strict enforcement | Daily workflow     | AI starts hitting constraints | LOW — organic                     |
| Daily workflow     | CI integration     | Want automated verification   | LOW — one config file             |

---

## Drop-off Risk Points

1. **After install, before shadow mode**: "What do I do next?" — needs onboarding guidance
2. **First report**: "I don't understand these EATP dimensions" — needs plain-English explanations
3. **Template selection**: "Which template is right for me?" — needs clear descriptions
4. **First HELD action**: "This is slowing me down" — needs quick resolution workflow
5. **CI integration**: "This broke my build" — needs graceful degradation

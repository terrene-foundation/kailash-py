# TrustPlane Concepts

This document explains the core ideas behind TrustPlane in plain
language. You do not need to know EATP, cryptography, or trust
frameworks to understand these concepts. Each section starts with
what the concept means to you as a developer, then maps it to the
formal terminology for those who want to go deeper.

---

## What Is a Trust Plane?

**Analogy: A flight data recorder for AI-assisted work.**

When an airplane flies, its black box records everything: altitude,
speed, control inputs, engine status. The pilots do not interact with
the black box during flight. Its value is entirely after the fact: when
someone asks "what happened?", the recorder provides an irrefutable
answer.

A trust plane works the same way for AI-assisted software development.
It sits between the human (who has authority) and the AI (which does
the work), recording every decision, every action, and every
checkpoint. The AI's work is not slowed down. But afterward -- or
during, if you choose -- you have a complete, tamper-evident record of
what happened, what was decided, and why.

The trust plane is NOT a permissions system (though it can enforce
permissions). It is fundamentally an **accountability layer**. It
makes the question "what did the AI do and why?" answerable with
cryptographic proof.

**Formal term**: Trust Plane (from the CARE framework's Dual Plane
Architecture -- the Execution Plane where work happens, and the
Trust Plane where work is attested).

---

## What Is a Constraint Envelope?

**Analogy: Access control policies for AI assistants.**

When you hire a contractor to renovate your kitchen, you give them
boundaries: they can tear out cabinets (operational), they can access
the kitchen and garage (data access), they have a budget of $20,000
(financial), they should work weekdays 8am-5pm (temporal), and they
should call you before contacting the HOA (communication).

A constraint envelope defines exactly these five dimensions of
boundaries for an AI assistant:

1. **Operational** -- What actions the AI can and cannot take. For
   example: can write code, cannot merge to main.

2. **Data Access** -- What files and directories the AI can read and
   write. For example: can read `src/` and `tests/`, cannot access
   `.env` or `secrets/`.

3. **Financial** -- Cost limits per session and per action. Prevents
   runaway API calls or expensive operations.

4. **Temporal** -- Time boundaries. Maximum session length, allowed
   working hours, cooldown periods between actions.

5. **Communication** -- What external channels the AI can use. For
   example: can post to GitHub PRs, cannot send emails or trigger
   production deploys.

Constraint envelopes have two important properties:

- **They are monotonically tightening.** Once signed, constraints can
  only become MORE restrictive. You can add new blocked actions but
  you cannot remove existing ones. Loosening requires creating an
  entirely new project (a new Genesis Record). This prevents gradual
  erosion of safety boundaries.

- **They are tamper-evident.** Every envelope has a SHA-256 hash. If
  any constraint is modified after signing, the hash changes and
  verification fails.

**Formal term**: Constraint Envelope (maps to EATP's five
ConstraintType dimensions).

---

## What Is a Trust Posture?

**Analogy: Graduated trust levels, like a new employee's access.**

When a new employee joins a company, they do not get full admin access
on day one. They start with limited access, and as they prove
competent and trustworthy, their access grows. If they make a mistake,
access may be tightened.

Trust postures work the same way:

- **Shadow**: Observation only. The AI works normally, and TrustPlane
  records what happens but enforces nothing. This is where every
  project starts. Think of it as the probation period.

- **Standard**: Basic governance. Constraints are defined, decisions
  are recorded, and violations are flagged. Most day-to-day
  development happens at this level.

- **High-Assurance**: Elevated scrutiny. Every action is checked
  against the constraint envelope. Violations are held for human
  review before proceeding. Used for security-sensitive work.

- **Critical**: Maximum governance. Full multi-party verification.
  Every action requires explicit approval. Used for production
  deployments, security incidents, or compliance-critical work.

The posture can only escalate during a session (shadow to standard
to high-assurance to critical), never relax. If the AI encounters
something unexpected, the posture ratchets up, never down. Relaxing
requires starting a new session.

**Formal term**: Trust Posture (from EATP's PostureStateMachine,
implementing monotonic escalation per the CARE security model).

---

## What Is the Mirror Thesis?

**Analogy: Learning what AI cannot do by watching what humans do.**

The Mirror Thesis comes from the CARE governance framework. The idea
is simple: if you watch what an AI does autonomously and what requires
human intervention, the pattern of human engagement reveals what AI
currently cannot handle.

TrustPlane captures three types of records that make this visible:

1. **Execution Records** -- The AI acted on its own, within the
   constraint envelope. No human needed. This reveals what AI can
   handle reliably.

2. **Escalation Records** -- The AI reached the boundary of its
   constraints and asked a human for input. This reveals where AI
   knows its limits.

3. **Intervention Records** -- A human stepped in even though the AI
   did not ask. The human noticed something the AI missed. This is the
   most revealing data point -- it shows where AI has blind spots.

Over time, the ratio of executions to escalations to interventions
paints a picture of AI capability in your specific context. If
interventions cluster around security decisions, that tells you
something concrete about where human judgment is still needed.

TrustPlane calls this the "competency map" and you can view it with:

```bash
attest mirror
```

The six categories of human competency tracked are:

- Ethical judgment
- Relationship capital
- Contextual wisdom
- Creative synthesis
- Emotional intelligence
- Cultural navigation

These are "current AI limitations, not principled impossibilities" --
a snapshot of what AI cannot do well in 2026, not a permanent boundary.

**Formal term**: Mirror Thesis (from CARE Part IV -- "Irreducible
Human Competencies").

---

## What Is a Trust Chain?

**Analogy: Like git commit history, but cryptographically enforced.**

In git, every commit references the hash of its parent commit. If you
change an old commit, every subsequent hash changes, making tampering
detectable. But git does not enforce this -- you CAN force-push and
rewrite history.

A trust chain works the same way, but with cryptographic enforcement
that cannot be bypassed:

1. **Genesis Record**: The first link. Records who created the project,
   when, and with what authority. Signed with an Ed25519 key.

2. **Audit Anchors**: Every subsequent record (decision, milestone,
   audit event) is an anchor that references the previous anchor's
   hash. Each anchor is signed with the same key.

3. **Verification**: At any time, you can walk the chain from Genesis
   to the latest anchor and verify that:
   - Every hash matches its content
   - Every signature is valid
   - No links are missing or inserted
   - The chain is contiguous

If ANY record is modified, added, or removed, the chain breaks.
Unlike git, there is no force-push equivalent. The only way to
"fix" a broken chain is to create a new project with a new Genesis
Record.

The verification command walks the entire chain:

```bash
attest verify
```

**Formal term**: Trust Chain (implemented as a sequence of EATP Audit
Anchors with hash-linked predecessor references).

---

## Glossary

A mapping from EATP/CARE terminology to plain-language equivalents.

| Formal Term               | Plain Language                                      | Where Used                                                   |
| ------------------------- | --------------------------------------------------- | ------------------------------------------------------------ |
| **Audit Anchor**          | A signed record in the trust chain                  | Every decision, milestone, audit event                       |
| **Authority**             | The human who has final say                         | Project creator (the `--author` in `attest init`)            |
| **CARE**                  | Governance framework for AI accountability          | Background theory; you don't need to read it                 |
| **Capability Request**    | A proposed action checked against constraints       | `project.check(action, resource)`                            |
| **Confidentiality Level** | Who can see a record                                | `public`, `restricted`, `confidential`, `secret`             |
| **Constraint Envelope**   | The boundaries for AI behavior (5 dimensions)       | Applied via `attest template apply`                          |
| **Constraint Type**       | One of the five dimensions                          | Operational, Data Access, Financial, Temporal, Communication |
| **Decision Record**       | A recorded choice with rationale                    | Created via `attest decide`                                  |
| **Delegation**            | Granting scoped authority to another person         | `attest delegate add`                                        |
| **Dual Plane**            | Execution (work) + Trust (attestation)              | Architecture concept                                         |
| **EATP**                  | Extensible Attestation Trust Protocol               | The cryptographic protocol underneath                        |
| **Ed25519**               | Signing algorithm                                   | Used for all signatures in the trust chain                   |
| **Enforcement Mode**      | How constraints are applied                         | `shadow` (observe) or `strict` (enforce)                     |
| **Execution Record**      | AI acted autonomously, no human needed              | Mirror Thesis data                                           |
| **Escalation Record**     | AI asked a human for help                           | Mirror Thesis data                                           |
| **Genesis Record**        | The first record in a trust chain                   | Created by `attest init`                                     |
| **Hold**                  | An action paused for human review                   | `attest hold list`, `attest hold approve`                    |
| **Intervention Record**   | Human stepped in without being asked                | Mirror Thesis data                                           |
| **Milestone Record**      | A versioned checkpoint with optional file hash      | Created via `attest milestone`                               |
| **Mirror Thesis**         | What AI can/cannot do, revealed by human engagement | `attest mirror`                                              |
| **Monotonic Escalation**  | Trust can only tighten, never relax                 | Posture, constraints, verification categories                |
| **Project Manifest**      | Project identity and stats                          | `manifest.json` in the trust-plane directory                 |
| **Reasoning Trace**       | Detailed rationale attached to an audit anchor      | Internal to decision/milestone records                       |
| **Review Requirement**    | How much human attention a record needs             | `quick`, `standard`, `full`                                  |
| **Shadow Mode**           | Observe without enforcing                           | `attest shadow`, `attest enforce shadow`                     |
| **Trust Posture**         | Current governance level                            | `shadow`, `standard`, `high_assurance`, `critical`           |
| **Verification Bundle**   | Self-contained package for independent verification | `attest export`                                              |
| **Verification Category** | What happened to an action                          | `auto_approved`, `flagged`, `held`, `blocked`                |

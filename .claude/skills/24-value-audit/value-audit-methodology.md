# Value Audit Methodology

## Philosophy

A value audit evaluates a product demo the way an enterprise buyer experiences it — not as a collection of features, but as a **narrative about transformation**. The buyer is asking one meta-question: _"Will this make my organization better, and can I prove it to my board?"_

Every element on every page either advances or undermines that narrative.

## The Auditor Persona

The auditor is NOT a friendly tester. They are:

- **Skeptical**: They've seen 50 demos this quarter. They've heard every promise. They want proof.
- **Outcome-oriented**: Features are irrelevant. Outcomes are everything. "We have 26 pages" means nothing. "Your agents completed 47 tasks today at 94% accuracy" means everything.
- **System thinkers**: They don't evaluate pages in isolation. They evaluate how pages connect to form value chains. A brilliant compliance dashboard that isn't connected to actual agent activity is a Potemkin village.
- **Data literate**: They notice when numbers don't add up. "3 trusted agents" but only 1 in the posture breakdown. "100% success rate" with 0 completions. "Active" agents doing nothing. These contradictions destroy credibility faster than missing features.

## Three-Level Evaluation

### Level 1: Page-Level Audit

For each page, evaluate four dimensions:

| Dimension            | Ratings                         | What It Measures                                        |
| -------------------- | ------------------------------- | ------------------------------------------------------- |
| **Purpose Clarity**  | CLEAR / VAGUE / MISSING         | Can a client state what this page does in one sentence? |
| **Data Credibility** | REAL / EMPTY / CONTRADICTORY    | Does the data tell a believable, consistent story?      |
| **Value Connection** | CONNECTED / ISOLATED / DEAD END | Does this page connect to the broader value story?      |
| **Action Clarity**   | OBVIOUS / HIDDEN / ABSENT       | Can a user take meaningful action here?                 |

**Verdict options**: VALUE ADD / NEUTRAL / VALUE DRAIN

A "value drain" is worse than a missing page — it actively hurts the demo by showing something broken, empty, or contradictory.

### Level 2: Flow-Level Audit

Trace the intended value flows end-to-end:

**Primary flow** (the money shot):

```
Design Org → Configure Trust → Deploy Agents → Submit Objective → Agent Works → Human Oversight → Results Delivered
```

**Supporting flows**:

```
Agent Activity → Compliance Dashboard → Audit Trail (governance story)
User Invited → Agent Created → Trust Established → Agent Earns Autonomy (onboarding story)
Constraint Violated → Alert Generated → Human Intervenes → Agent Corrected (safety story)
```

For each flow, assess:

- **Completeness**: Does the flow work end-to-end, or does it break at a specific step?
- **Narrative coherence**: Does each step naturally lead to the next, or are there jarring transitions?
- **Evidence of value**: Is the outcome demonstrated with real data, or is it theoretical?

### Level 3: Cross-Cutting Audit

Identify systemic patterns that affect multiple pages:

| Pattern                | Description                               | Example                                       |
| ---------------------- | ----------------------------------------- | --------------------------------------------- |
| **Empty Room**         | Pages with zero data                      | 12+ pages showing no records                  |
| **Contradictory Data** | Numbers that don't add up                 | 3 agents, but posture shows 1                 |
| **Orphaned Features**  | Features not connected to value flows     | Knowledge page with no link to agent behavior |
| **Concept Overload**   | Too many unexplained concepts             | Knowledge vs Directives vs Policies           |
| **Dead Ends**          | Pages that don't lead anywhere meaningful | Dashboard that duplicates Home                |
| **False Confidence**   | Metrics that mislead                      | 100% success rate with 0 completions          |

## The Five Questions — Deep Guide

### 1. What is this FOR?

**Bad answer**: "It shows shadow agents."
**Good answer**: "It lets me verify that every role in my organization has an operational AI counterpart, monitor their health, and intervene when needed."

The difference: a bad answer describes the feature. A good answer describes the business outcome the feature enables.

**Red flag**: If you can't articulate the business outcome in one sentence, the page lacks purpose clarity.

### 2. What does it LEAD TO?

Every page should be a **node in a value graph**, not a dead end.

**Test**: After viewing this page, what is the natural next action? If the answer is "go back to sidebar and pick something else," the page is isolated.

**Good connections**:

- Trust Dashboard → "Establish Trust" → Shadow Agents (configure trust for a specific agent)
- Shadow Agent Detail → "Open Observation Dashboard" → Metrics (see what the agent has done)
- Compliance Violation → "View Details" → Audit Trail (investigate what happened)

**Bad connections**:

- Dashboard → nothing (dead end)
- Knowledge → nothing (dead end)
- Directives → nothing (dead end)

### 3. Why do I NEED this?

**The deletion test**: If you removed this page from the product, would the value story be weaker?

- Remove Compliance Dashboard → governance story collapses → CRITICAL
- Remove Knowledge → agent learning story weakens → HIGH
- Remove Billing → operational but not demo-critical → LOW

### 4. How do I USE this?

**The 5-second test**: Can a first-time user take a meaningful action within 5 seconds of landing on the page?

- Good: Objective input on Home page — type and submit immediately
- Bad: Organization Builder — need to understand node types, drag mechanics, save/deploy pipeline before doing anything

**The value action test**: Is the primary action on the page the one that creates the most value? Or is it buried?

### 5. Where's the PROOF?

**The empty state problem**: An empty page is worse than a missing page. A missing page is invisible. An empty page is visible evidence that nothing has happened.

**Proof hierarchy** (strongest to weakest):

1. **Live demonstration**: Agent completing a task in real-time
2. **Historical data**: "47 tasks completed today, 94% success rate"
3. **Activity log**: Timestamped events showing the system in action
4. **Configuration state**: "3 agents deployed, trust postures configured"
5. **Schema/structure**: "Here's what you COULD do" (weakest)

Most demo failures happen at level 5 — showing capability without evidence.

## Audit Execution Checklist

### Before Starting

- [ ] Identify the target persona (CTO, VP Eng, Head of AI, CISO)
- [ ] Understand the claimed value proposition
- [ ] Know the competitor landscape (what alternatives exist)
- [ ] Prepare the demo flow (which pages in which order)

### During Audit

- [ ] Login experience captured (first impression)
- [ ] Home page gut reaction recorded
- [ ] Primary value flow traced end-to-end
- [ ] All data-bearing pages checked for credibility
- [ ] All governance pages checked for evidence
- [ ] Cross-cutting patterns identified
- [ ] Screenshots captured for evidence

### After Audit

- [ ] Executive summary written (2-3 sentences)
- [ ] Page-by-page assessments completed
- [ ] Value flows traced and assessed
- [ ] Cross-cutting issues categorized and severity-rated
- [ ] "What great looks like" section written
- [ ] Single highest-impact recommendation identified
- [ ] Bottom line verdict delivered

## Severity Framework

| Severity     | Definition                                                        | Example                                      |
| ------------ | ----------------------------------------------------------------- | -------------------------------------------- |
| **CRITICAL** | Kills the value story. Demo cannot proceed credibly.              | 12+ pages showing zero data                  |
| **HIGH**     | Undermines credibility. Client will question claims.              | Contradictory metrics, invalid trust chains  |
| **MEDIUM**   | Creates confusion. Client needs explanation.                      | Two overlapping dashboards, unclear taxonomy |
| **LOW**      | Minor imperfection. Client unlikely to notice unless pointed out. | Wrong role label, redirect quirk             |

## Fix Categories

| Category      | Description                                                | Effort                                   |
| ------------- | ---------------------------------------------------------- | ---------------------------------------- |
| **DATA**      | Populate with realistic demo data                          | Low — seed scripts, API calls            |
| **DESIGN**    | Restructure page layout or information architecture        | Medium — frontend changes                |
| **FLOW**      | Connect features into value chains                         | Medium — navigation, CTAs, cross-linking |
| **NARRATIVE** | Rewrite copy, labels, descriptions to tell the value story | Low — content changes                    |
| **FEATURE**   | Build missing functionality                                | High — backend + frontend development    |

# Value Flow Patterns

Patterns and anti-patterns for enterprise AI platform demos, distilled from value audit experience.

## What Is a Value Flow?

A value flow is a **connected sequence of pages and actions** that demonstrates a complete business outcome. It's the story the product tells as the user moves through it.

A feature in isolation is a fact. A feature in a value flow is a story.

## Primary Value Flows

### 1. The Transformation Flow (The Money Shot)

**Story**: "I designed my organization, deployed it as AI agents, and now those agents produce results under my governance."

```
Organization Builder    → Shadow Agents Dashboard → Submit Objective
(design the org)          (see the agents live)      (give them work)
        ↓                         ↓                        ↓
Configure Trust         → Agent Detail Panel      → Work Session
(set boundaries)          (verify health/trust)      (watch agent work)
        ↓                         ↓                        ↓
Deploy                  → Metrics                 → Results Delivered
(agents come alive)       (see the impact)           (value realized)
```

**Critical moments**:

- The deploy step: "This role BECAME this agent" — the transformation must be visible
- The work session: agent must visibly DO something, not just exist
- The results: concrete output, not just status changes

**Where it typically breaks**: Step 3 (Submit Objective) → Step 4 (Work Session). The agent either doesn't respond, produces generic output, or the session shows 0 messages.

### 2. The Governance Flow (The Trust Builder)

**Story**: "My agents operate within boundaries. When they hit a boundary, the system catches it, alerts the right human, and maintains an audit trail."

```
Trust Postures          → Agent Activity          → Constraint Violation
(boundaries defined)      (agent operates)          (boundary hit)
        ↓                         ↓                        ↓
Compliance Dashboard    → Escalation Alert        → Audit Trail
(overview of governance)  (human notified)           (immutable record)
        ↓                         ↓                        ↓
Trust Progression       → Human Decision          → Agent Corrected
(agent earns autonomy)    (approve/deny)             (system adapts)
```

**Critical moments**:

- The constraint violation: proof that governance isn't theoretical
- The escalation: proof that humans stay in the loop
- The audit trail: proof that everything is recorded

**Where it typically breaks**: No constraint violations exist. No audit events exist. The governance story is entirely theoretical.

### 3. The Collaboration Flow (The Differentiator)

**Story**: "Agents don't work alone. They collaborate across organizational boundaries, maintaining trust throughout."

```
CEO Agent               → Bridge Created          → CIO Agent
(needs analysis)          (cross-functional)         (receives request)
        ↓                         ↓                        ↓
Task Delegated          → Trust Verified          → Analysis Completed
(within constraints)      (EATP check)               (results returned)
        ↓                         ↓                        ↓
Results Aggregated      → Bridge Closed           → CEO Reviews
(multi-agent output)      (scoped access ends)       (value delivered)
```

**Critical moments**:

- The bridge: demonstrating controlled cross-agent communication
- The trust verification: proving access is governed, not open
- The multi-agent output: showing agents working together produces better results than a single agent

**Where it typically breaks**: No bridges exist. No cross-agent activity. The collaboration story is entirely in the marketing copy.

### 4. The Onboarding Flow (The Aha Moment)

**Story**: "A new team member joins, gets a personal AI agent, meets their agent, and starts producing value on day one."

```
Invitation Sent         → Account Created         → Meet Your Agent
(admin invites)           (user accepts)              (onboarding step)
        ↓                         ↓                        ↓
Trust Initialized       → First Objective          → Agent Delivers
(Pseudo posture set)      (user asks for something)    (immediate value)
        ↓                         ↓                        ↓
Trust Earned            → Agent Grows              → Autonomous Work
(through performance)     (Pseudo → Supervised)        (within constraints)
```

**Critical moments**:

- Meet Your Agent: the first time the user sees their personal AI counterpart
- First Objective: the user's first experience of agent value
- Trust Earned: the agent proving itself worthy of increased autonomy

## Anti-Patterns

### 1. The Empty Museum

**What it is**: Beautiful pages with no data. Like a museum with frames on the walls but no paintings.

**Signs**:

- "No items found" on data pages
- Metrics showing all zeros
- Activity feeds with no activity
- "Empty state" illustrations everywhere

**Fix**: Demo seed data. Every page in the demo path must have meaningful data.

### 2. The Feature Safari

**What it is**: Demo that tours 26 pages sequentially — "and here's the Knowledge page, and here's the Directives page, and here's the Bridges page" — without connecting them into a story.

**Signs**:

- Linear page-by-page walkthrough
- No cross-page connections demonstrated
- Features described in isolation
- "This page lets you..." repeated for every page

**Fix**: Structure the demo as 3-4 value flows, not 26 page visits. Each flow tells a story with a beginning, middle, and end.

### 3. The Potemkin Dashboard

**What it is**: Impressive-looking dashboards with no data or with data that contradicts itself.

**Signs**:

- Charts with "No data" placeholders
- Metrics at 0% or 100% with no underlying activity
- Trust levels that don't match agent counts
- Success rates with zero denominator

**Fix**: Either populate with real data or don't show the dashboard. A Potemkin dashboard is worse than no dashboard.

### 4. The Concept Avalanche

**What it is**: Introducing 10+ new concepts (Shadow Enterprise, Trust Postures, EATP, Bridges, Directives, Knowledge, Constraint Envelopes, CARE, Workspaces, Personas) without letting any single one land.

**Signs**:

- Sidebar with 26 items
- Multiple pages serving similar purposes (Knowledge/Directives/Policies)
- Acronyms used before defined (EATP, CARE, ABAC)
- User needs a glossary to navigate

**Fix**: Introduce concepts through the value flow, not through page labels. "Let me show you how trust works" (navigates to Trust Postures in the context of an agent's journey) vs. "Here's the Trust Postures page" (isolated visit).

### 5. The Dead-End Garden

**What it is**: Pages that don't lead anywhere. You visit, you see, you go back to the sidebar and pick something else.

**Signs**:

- No meaningful CTAs on the page
- No links to related features
- "View Details" leads to more data but no actions
- The only navigation is the sidebar

**Fix**: Every page should have at least one forward action: "Establish Trust" → Shadow Agents. "View Audit Trail" → Audit Trail. "Submit Objective" → Work Session.

## Value Flow Design Principles

### 1. Every Page Is a Node

In the value graph, every page should have:

- At least one **incoming edge** (how do you get here?)
- At least one **outgoing edge** (where do you go next?)
- A **unique contribution** to the value story (what does this page add that no other page does?)

Pages with zero outgoing edges are dead ends. Pages with zero unique contribution are candidates for merging.

### 2. Data Tells the Story

The most compelling demo is one where the presenter doesn't need to explain what's happening — the data on the screen tells the story by itself.

- "Your agent completed 5 tasks today" > "Your agent can complete tasks"
- "Trust level advanced to Supervised after 10 successful executions" > "Trust levels can advance"
- "Budget constraint triggered: CIO agent blocked from $50K purchase" > "Budget constraints can be set"

### 3. The 30-Second Test

A value flow should be communicable in 30 seconds:

- **Transformation**: "Design your org. Deploy as AI. Agents produce results. Humans govern."
- **Governance**: "Set boundaries. Agent hits boundary. System catches it. Audit trail records it."
- **Collaboration**: "CEO agent needs data. Creates bridge to CIO agent. Trust verified. Results returned."

If it takes more than 30 seconds to explain, the flow is too complex or too abstract.

### 4. Proof Over Promise

At every step, prefer showing evidence over describing capability:

| Promise (Weak)                   | Proof (Strong)                                                     |
| -------------------------------- | ------------------------------------------------------------------ |
| "Agents can complete objectives" | "Agent completed Q4 analysis in 12 minutes"                        |
| "Trust levels can progress"      | "CEO Agent: Pseudo → Supervised (after 10 tasks, 94% success)"     |
| "Compliance is tracked"          | "3 constraint violations this week, all resolved within 2 hours"   |
| "Agents collaborate"             | "CIO Agent requested financial data from CFO Agent via Bridge-007" |

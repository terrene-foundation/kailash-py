# Product Analysis: kailash-pact

## What PACT Is

PACT (Principled Architecture for Constrained Trust) is an organizational governance framework for AI agent systems. It answers: "Who can do what, with what data, under what constraints, in an organization of AI agents?"

## Value Propositions

### VP1: Organizational Accountability Grammar (D/T/R)

**What**: A formal grammar for addressing roles within an organization — Department/Team/Role (D/T/R). Every agent, every action, every knowledge item has an address.

**Why it matters**: Current AI agent frameworks have flat agent registries. You deploy agents and give them tools. There's no organizational structure — no departments, no teams, no reporting lines. When something goes wrong, there's no accountability chain.

**Unique**: No competing framework has a formal organizational grammar for AI agents. LangGraph, CrewAI, AutoGen — all have flat agent pools or hardcoded hierarchies.

### VP2: Knowledge Clearance (5-Level Classification)

**What**: A 5-level knowledge classification system (PUBLIC to TOP_SECRET) with per-role clearance assignments, compartmentalization, and posture ceilings.

**Why it matters**: Enterprise AI agents process sensitive data. Today, every agent sees everything it can access. There's no concept of "this agent has CONFIDENTIAL clearance but not SECRET." PACT makes knowledge access a first-class governance concern.

**Unique**: No competing framework has multi-level knowledge clearance for AI agents. This is a direct application of security clearance models (government/military) to AI systems.

### VP3: Operating Envelopes (3-Layer Constraint Model)

**What**: Three-layer constraint envelope model — Role Envelopes (standing constraints), Task Envelopes (ephemeral), Effective Envelopes (computed intersection). Monotonic tightening guarantee.

**Why it matters**: Enterprise AI needs bounded autonomy. "This agent can spend up to $10K, make up to 100 API calls per hour, access only customer data in region X, and communicate only via approved channels." PACT makes these constraints composable and provably monotonic (they can only get tighter, never looser).

**Unique**: While EATP has constraint dimensions, PACT adds the three-layer composition model with monotonic tightening guarantees. No competing framework has this.

### VP4: Cross-Functional Knowledge Sharing (Bridges + KSPs)

**What**: Formal mechanisms for cross-organizational knowledge sharing — Standing Bridges (permanent cross-functional access) and Knowledge Share Policies (scoped, time-limited access).

**Why it matters**: In real organizations, information doesn't respect org chart boundaries. The CFO needs engineering cost data. Legal needs product plans. PACT formalizes these cross-functional flows with explicit governance.

**Unique**: This models real organizational information flow, not just access control lists.

## Competitive Landscape

### Agent Governance in 2026

| Framework        | Organizational Structure | Knowledge Clearance    | Constraint Envelopes  | Cross-Functional | Audit        |
| ---------------- | ------------------------ | ---------------------- | --------------------- | ---------------- | ------------ |
| **kailash-pact** | D/T/R grammar            | 5-level + compartments | 3-layer monotonic     | Bridges + KSPs   | EATP anchors |
| CrewAI           | Flat roles               | None                   | Per-agent tool limits | None             | Logging      |
| LangGraph        | Graph nodes              | None                   | None                  | Explicit edges   | LangSmith    |
| AutoGen          | Flat agents              | None                   | None                  | Group chat       | Logging      |
| AgentOps         | Flat + tags              | None                   | Budget limits         | None             | Metrics      |
| Anthropic HAAS   | Nested hierarchy         | None                   | Constitutional rules  | None             | Trust tokens |

### Key Differentiators

1. **Formal organizational grammar** — nobody else has D/T/R addressing
2. **Knowledge clearance** — nobody else has multi-level classification for AI
3. **Monotonic tightening** — provably-correct constraint composition
4. **EATP integration** — cryptographic audit trail, not just logging
5. **Thread-safe, fail-closed** — production-grade by default

### Gaps vs Competition

1. **No real-time monitoring dashboard** — CrewAI and AgentOps have observability UIs
2. **No visual org chart builder** — manual YAML or Python definition
3. **No agent lifecycle management** — PACT governs decisions, not agent runtime
4. **No natural language policy definition** — constraints are code/config, not prose

## Platform Model Analysis

### Producers

- **Platform operators** who define organizational structures (D/T/R hierarchies)
- **Compliance officers** who set clearance levels and knowledge policies
- **Team leads** who define task envelopes and operating constraints

### Consumers

- **AI agents** that execute within governance constraints
- **Auditors** who review governance decisions and knowledge access patterns
- **Developers** who integrate governance into their agent workflows

### Partners

- **EATP protocol** — provides cryptographic audit trail
- **Kailash Kaizen** — provides agent execution runtime
- **Vertical platforms** (Astra, Arbor) — consume governance as a service

### Network Behaviors

| Behavior        | Implementation                                          | Status  |
| --------------- | ------------------------------------------------------- | ------- |
| Accessibility   | GovernanceEngine API, CLI, REST endpoints               | DONE    |
| Engagement      | explain_access(), explain_envelope(), GovernanceVerdict | DONE    |
| Personalization | Per-role envelopes, per-task constraints                | DONE    |
| Connection      | EATP audit chain, Kaizen agent bridge                   | PARTIAL |
| Collaboration   | Bridges, KSPs, cross-functional sharing                 | DONE    |

## AAA Framework

### Automate

- **Envelope computation**: Automatic intersection of role + task constraints
- **Access enforcement**: 5-step algorithm runs on every action
- **Audit trail**: Every decision automatically recorded as EATP anchor

### Augment

- **explain_access()**: Human-readable explanation of why access was granted/denied
- **explain_envelope()**: Shows how effective envelope was computed
- **GovernanceVerdict**: Rich decision object with reasoning

### Amplify

- **YAML org definition**: Non-developers can define organizational structure
- **Template envelopes**: Pre-built constraint profiles for common roles
- **Posture ceilings**: Automatic clearance restriction based on trust posture

## Risk Assessment

### Technical Risks

| Risk                                                   | Severity | Mitigation                                            |
| ------------------------------------------------------ | -------- | ----------------------------------------------------- |
| pact.build.config.schema types don't exist in monorepo | CRITICAL | Extract from pact repo into pact.governance.config    |
| engine.py is 35K lines                                 | HIGH     | Already well-structured; consider splitting if needed |
| Pydantic dependency for non-API types                  | MEDIUM   | Convert config types to dataclasses                   |
| No integration tests with kaizen                       | MEDIUM   | Phase 3 of integration brief                          |

### Adoption Risks

| Risk                                          | Severity | Mitigation                                             |
| --------------------------------------------- | -------- | ------------------------------------------------------ |
| Complexity barrier for simple use cases       | HIGH     | Provide "governance-lite" mode with sensible defaults  |
| YAML org definition learning curve            | MEDIUM   | Visual builder, good docs, examples                    |
| Performance at scale (thread lock contention) | LOW      | Per-org engine instances, read-write lock upgrade path |

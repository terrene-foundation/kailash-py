# TrustPlane Competitive Landscape

## Market Category

TrustPlane operates in an emergent category: **AI Decision Governance** — proving what AI actually did, not just what it should do. This category does not yet have a Gartner Magic Quadrant or established name.

---

## Competitive Map

### Runtime Guardrails (Different Layer)

| Product                            | Focus                                                  | Differentiation from TrustPlane                                               |
| ---------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------- |
| **Guardrails AI**                  | Input/output validation (hallucination, toxicity, PII) | Content quality, not organizational governance. No cryptographic attestation. |
| **NVIDIA NeMo Guardrails**         | Conversational flow control for chatbots               | Dialogue safety, not decision auditing. No constraint envelopes.              |
| **LangChain/LangGraph guardrails** | Orchestration-level controls                           | Framework-locked. No standalone governance.                                   |

**TrustPlane is not a guardrail.** Guardrails filter bad outputs. TrustPlane proves good governance.

### Platform-Level Controls (Different Granularity)

| Product                          | Focus                                 | Differentiation from TrustPlane                      |
| -------------------------------- | ------------------------------------- | ---------------------------------------------------- |
| **Anthropic Console**            | Organization-level API usage policies | Per-org, not per-project. No per-action attestation. |
| **OpenAI Organization Controls** | Usage limits, content policies        | No cryptographic audit trail.                        |
| **Azure AI Content Safety**      | Content filtering                     | Filtering, not governance.                           |

**TrustPlane provides per-project, per-session, per-action governance.** Platform controls provide organization-level limits.

### Observability (Complementary)

| Product       | Focus                                   | Differentiation from TrustPlane                                                    |
| ------------- | --------------------------------------- | ---------------------------------------------------------------------------------- |
| **LangSmith** | LLM observability (traces, evaluations) | What happened (observability). TrustPlane: what should have happened (governance). |
| **LangFuse**  | Open-source LLM observability           | Same distinction. Complement, not compete.                                         |
| **Helicone**  | LLM request logging and analytics       | Logging, not attestation. No constraint enforcement.                               |

**TrustPlane could integrate with these.** Observability + governance = complete picture.

### Enterprise GRC (Adjacent Market)

| Product                         | Focus                                     | Differentiation from TrustPlane                    |
| ------------------------------- | ----------------------------------------- | -------------------------------------------------- |
| **OneTrust AI Governance**      | Policy management, risk assessment for AI | Documentation-focused, not runtime enforcement.    |
| **IBM OpenPages AI FactSheets** | ML model governance and documentation     | Model lineage, not decision lineage.               |
| **ServiceNow AI Governance**    | IT governance workflows for AI deployment | Process governance, not cryptographic attestation. |

**Enterprise GRC platforms document policies. TrustPlane enforces and proves compliance.**

### Status Quo (Primary Competitor)

Most teams today handle AI accountability through:

1. **Git blame + code review** — human reviews what AI produced
2. **Access controls** — AI can only touch what developer can touch
3. **Nothing** — zero AI-specific accountability

**TrustPlane's actual competitor is "nothing."** The market must be educated.

---

## TrustPlane's Unique Differentiators

1. **Cryptographic audit chain** — Ed25519-signed audit anchors with hash-linked chains. No competitor has this.
2. **Five-dimension constraint envelope** — Structured model (operational, data access, financial, temporal, communication) with monotonic tightening. Novel.
3. **Three-tier enforcement** — Rule file (advisory) → pre-tool hook (process) → MCP proxy (transport). Progressive enforcement depth.
4. **Mirror Thesis competency map** — Reveals what AI handles autonomously vs. where humans contribute. Unique data product.
5. **Verification bundles** — Self-contained export for independent verification. Auditor-ready.
6. **Zero infrastructure** — Filesystem-based, no database, no server. As easy as `git init`.

---

## Where TrustPlane Is Weak vs. Competition

| Area                       | TrustPlane              | Competitors                                               |
| -------------------------- | ----------------------- | --------------------------------------------------------- |
| **Ecosystem integration**  | Claude Code only (MCP)  | Guardrails AI integrates with LangChain, LlamaIndex, etc. |
| **UI/Dashboard**           | CLI-only                | Most competitors have web dashboards                      |
| **Enterprise tooling**     | No SIEM, no GRC, no SSO | Enterprise GRC platforms have full integration suites     |
| **Multi-language support** | Python only             | Some competitors have multi-language SDKs                 |
| **Market awareness**       | New, unnamed category   | Guardrails AI has $35M+ funding, established brand        |

---

## Strategic Positioning

**TrustPlane should NOT position against guardrails.** Different layer, different buyer.

**TrustPlane SHOULD position as:**

- "The cryptographic audit trail for AI-assisted work"
- Infrastructure that makes AI governance provable, not just promised
- The equivalent of `git` for decision lineage (as `git` is for code lineage)

**The ideal positioning statement:**

> "Today you have policy documents that say what AI should do. TrustPlane proves what AI actually did."

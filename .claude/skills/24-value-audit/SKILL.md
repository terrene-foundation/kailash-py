---
name: value-audit
description: "Value-critical QA for enterprise demos: skeptical-buyer evaluation of value props, value flow, data credibility, narrative coherence."
---

# Value Audit Skills

Enterprise demo QA methodology that goes beyond functional testing to evaluate whether a product tells a compelling, credible story to skeptical enterprise buyers.

## Quick Reference

| Skill File                                                 | Purpose                                                                     | When to Use                                     |
| ---------------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------- |
| [value-audit-methodology.md](value-audit-methodology.md)   | Full audit methodology, Five Questions framework, 3-level evaluation        | Running a complete value audit                  |
| [demo-readiness-checklist.md](demo-readiness-checklist.md) | Pre-demo verification with pass/fail criteria                               | Quick readiness check before a demo             |
| [value-flow-patterns.md](value-flow-patterns.md)           | Common value flow patterns for enterprise AI platforms, anti-patterns       | Analyzing or designing value flows              |
| [full-demo-audit.md](full-demo-audit.md)                   | Combined technical + value audit orchestration (testing-specialist + value-auditor) | Running both technical and value QA in sequence |

## Core Concept

Traditional QA asks: "Does it work?"
Value Audit asks: "Does it sell?"

A product can pass every functional test and still fail a demo because:

- Pages show zero data (empty room problem)
- Features exist in isolation without connecting to the value story
- Metrics contradict the narrative (100% success with 0 completions)
- The transformation story (before → after) is missing

## The Five Questions

Every page, section, and element is interrogated with:

1. **What is this FOR?** — Business outcome, not feature description
2. **What does it LEAD TO?** — Connection in the value chain
3. **Why do I NEED this?** — What breaks if it doesn't exist
4. **How do I USE this?** — Path from viewing to getting value
5. **Where's the PROOF?** — Evidence it works, not promise it can

## Related Agent

Use the **value-auditor** agent (`.claude/agents/value-auditor.md`) to run automated audits via Playwright MCP.

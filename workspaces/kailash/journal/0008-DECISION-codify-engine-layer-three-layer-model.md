---
type: DECISION
date: 2026-03-30
project: kailash
topic: Codify three-layer model and engine-first principle as COC institutional knowledge
phase: codify
tags: [codify, engine-first, three-layer, framework-first, delegate, COC]
---

# Decision: Codify Three-Layer Model as COC Institutional Knowledge

## What Was Codified

11 COC artifacts created or updated at the kailash/ source of truth to establish the three-layer model (Raw → Primitives → Engine) and engine-first principle as institutional knowledge:

1. **New rule**: `rules/framework-first.md` — defines the three layers per framework, MUST prefer engine
2. **New skill**: `skills/04-kaizen/kaizen-delegate-vs-baseagent.md` — decision guide
3. **Updated**: 3 framework specialists (kaizen, dataflow, nexus) with Layer Preference sections
4. **Updated**: framework-advisor with Step 2b Layer Selection
5. **Updated**: decide-framework skill with Within-Framework Layer section
6. **Updated**: patterns.md Kaizen section (Agent → Delegate)
7. **Updated**: 2 SKILL.md files (kaizen, dataflow) with engine-first quick starts
8. **Updated**: sync-manifest.yaml to include framework-first.md in COC tier

## Why This Was Codified

Three independent dev teams (Arbor, Pact, ImpactVerse) independently reported that they couldn't find the engine layer. The COC only taught primitives. The friction gradient was backwards — the simplest API (Delegate, 2 lines) had the highest discovery friction. This is a Layer 5 (institutional knowledge) failure that perpetuated Layer 2 (agent) failures.

## Alternatives Considered

1. **Document-only approach**: Just update README and docs. Rejected — COC artifacts are what agents read; docs are what humans read. The problem is agent guidance, not human documentation.
2. **Rule-only approach**: Just create framework-first.md. Rejected — rules establish "what to do" but specialists establish "how to think about it." Both are needed.
3. **Skill-only approach**: Just update skills. Rejected — skills are loaded on-demand. Rules and specialist agents load contextually. The teaching path must work from the first moment.

## Consequences

- All new Kailash projects using COC will default to engine-level APIs
- Developers asking "how do I build an agent?" will see Delegate first, not BaseAgent
- The three-layer model is now a named, teachable concept across both SDKs
- kailash-rs gets the same guidance via /sync (all artifacts are GLOBAL tier)

# Journal Rules

## Scope

These rules apply to ALL workspace operations. The journal is the primary knowledge trail for every project.

## MUST Rules

### 1. Journal Every Insight

Every CO command that produces insights, decisions, or discoveries MUST create corresponding journal entries in the workspace's `journal/` directory. No insight should be lost between sessions.

### 2. Sequential Naming

Journal entries MUST use sequential naming: `NNNN-TYPE-topic.md` (e.g., `0001-DECISION-chose-event-driven.md`, `0002-DISCOVERY-connection-pool-bottleneck.md`). Before creating a new entry, MUST check the highest existing number in the journal directory.

### 3. Frontmatter Required

Journal entries MUST include YAML frontmatter with these fields:

```yaml
---
type: DECISION | DISCOVERY | TRADE-OFF | RISK | CONNECTION | GAP
date: YYYY-MM-DD
project: [project name]
topic: [brief description]
phase: analyze | todos | implement | redteam | codify | deploy
tags: [list of relevant tags]
---
```

### 4. Use Correct Entry Types

Six entry types exist. Use the right one:

| Type | Purpose | When Created |
|------|---------|-------------|
| **DECISION** | Record a choice with rationale, alternatives considered, and consequences | When making architectural, design, strategic, or scope decisions |
| **DISCOVERY** | Capture something learned — a concept, pattern, insight, or finding | When research, analysis, or exploration reveals new understanding |
| **TRADE-OFF** | Document a trade-off evaluation — what was gained and what was sacrificed | When balancing competing concerns |
| **RISK** | Record an identified risk, vulnerability, or concern | When stress-testing, reviewing, or validating reveals potential problems |
| **CONNECTION** | Note a relationship between concepts, components, or findings | When cross-referencing reveals links that matter |
| **GAP** | Flag something missing that needs attention | When analysis reveals missing data, untested assumptions, or unresolved questions |

### 5. Self-Contained Entries

Each journal entry MUST be self-contained — readable without requiring other context. Include enough background that a future session (or a different person) can understand the entry on its own.

## SHOULD Rules

### 1. Decision Rationale

DECISION entries SHOULD include alternatives considered and the rationale for the choice, not just the decision itself.

### 2. Consequences and Follow-Up

Entries SHOULD include consequences, follow-up actions, or next steps where applicable.

## MUST NOT Rules

### 1. No Overwriting

MUST NOT overwrite existing journal entries. Each entry is immutable once created. If a decision changes, create a new entry that references the original.

### 2. No Entries Without Frontmatter

MUST NOT create journal entries without proper YAML frontmatter. The frontmatter enables searching, filtering, and cross-referencing.

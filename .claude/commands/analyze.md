---
name: analyze
description: "Load phase 01 (analyze) for the current workspace"
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Output goes into `workspaces/<project>/01-analysis/`, `workspaces/<project>/02-plans/`, and `workspaces/<project>/03-user-flows/`

## Execution Model

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). All analysis, deliberation, and recommendations MUST assume autonomous AI agent execution — not human team constraints. Do not estimate effort in human-days. Do not constrain recommendations by team size or hiring. Recommend the technically optimal approach; agents scale horizontally.

## Workflow

### 1. Be explicit about objectives and expectations

Understand the product idea before diving into research.

### 2. Perform Deep Research

Document in detail in `workspaces/<project>/01-analysis/01-research`.

- Use as many subdirectories and files as required
- Name them sequentially as 01-, 02-, etc, for easy referencing

### 3. Ensure strong product focus

Keep this soft rule in mind for everything:

- 80% of the codebase/features/efforts can be reused (agnostic)
- 15% of client specific requirements goes into consideration for self-service functionalities that can be reused (agnostic)
- 5% customization

Steps:

1. Research thoroughly and distill value propositions and UNIQUE SELLING POINTS
   - Scrutinize and critique the intent and vision, focusing on perfect product-market fit
   - Research competing products, gaps, painpoints, and any other information that helps build solid value propositions
   - Define unique selling points (not the same as value propositions) — be extremely critical and scrutinize them
2. Evaluate using platform model thinking
   - Seamless direct transactions between users (producers, consumers, partners)
     - Producers: Users who offer/deliver a product or service
     - Consumers: Users who consume a product or service
     - Partners: To facilitate the transaction between producers and consumers
3. Evaluate using the AAA framework
   - Automate: Reduce operational costs
   - Augment: Reduce decision-making costs
   - Amplify: Reduce expertise costs (for scaling)
4. Features must cover network behaviors for strong network effects
   - Accessibility: Easy for users to complete a transaction (activity between producer and consumer, not necessarily monetary)
   - Engagement: Information useful to users for completing a transaction
   - Personalization: Information curated for an intended use
   - Connection: Information sources connected to the platform (one or two-way)
   - Collaboration: Producers and consumers can jointly work seamlessly

### 4. Document everything

Document analysis in `workspaces/<project>/01-analysis/`, plans in `workspaces/<project>/02-plans/`, and user flows in `workspaces/<project>/03-user-flows/`.

- Use as many subdirectories and files as required
- Name them sequentially as 01-, 02-, etc, for easy referencing

### 5. Red team

Work with red team agents to scrutinize analysis, plans and user flows.

- Identify any gaps, regardless how small
- Always go back to first principles, identify the roots, and plan the most optimal and elegant implementations
- Analysis, user flows must flow into plans

## Agent Teams

Deploy these agents as a team for analysis:

- **deep-analyst** — Failure analysis, complexity assessment, identify risks
- **requirements-analyst** — Break down requirements, create ADRs, define scope
- **coc-expert** — Ground analysis in COC methodology; identify institutional knowledge gaps and guard against the three fault lines (amnesia, convention drift, security blindness)
- **framework-advisor** — Choose implementation approach (if applicable)
- **sdk-navigator** — Find existing patterns and documentation before designing from scratch (if applicable)

For product/market analysis, additionally deploy:

- **value-auditor** — Evaluate from enterprise buyer perspective, critique value propositions

For frontend projects, additionally deploy:

- **uiux-designer** — Information architecture, visual hierarchy, design system planning
- **ai-ux-designer** — AI interaction patterns (if the project involves AI interfaces)

Red team the analysis with agents until they confirm no gaps remain in research, plans, and user flows.

### Journal

Create journal entries in the workspace's `journal/` directory for insights produced during analysis:
- **DISCOVERY** entries for key findings, patterns, or domain knowledge uncovered
- **GAP** entries for missing information, unvalidated assumptions, or areas needing research
- **CONNECTION** entries for relationships between components, requirements, or findings

Use sequential naming: check the highest existing `NNNN-` prefix and increment.

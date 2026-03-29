# CO Setup Guide

How to apply, adapt, and maintain the Cognitive Orchestration (CO) setup across different project types — coding (COC), governance, research, education, or any other domain.

## Guides

| Guide                                                 | Purpose                                                                                |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [01 - Architecture](01-architecture.md)               | The 5 component types, how they map to CO layers, what's shared vs project-specific    |
| [02 - Project Types](02-project-types.md)             | Coding, governance, education, and other archetypes — what to include/exclude for each |
| [03 - Creating Components](03-creating-components.md) | How to create agents, skills, rules, commands, and hooks for any domain                |
| [04 - Propagation](04-propagation.md)                 | How to apply updates across repositories                                               |

## Quick Start

Setting up CO for a new repo? Start with [02 - Project Types](02-project-types.md) to determine which archetype fits, then follow the component creation guide.

Propagating updates from the canonical source (terrene) to other repos? See [04 - Propagation](04-propagation.md).

## CO vs COC

- **CO** (Cognitive Orchestration) — The domain-agnostic base methodology. 7 first principles, 5-layer architecture. Applies to any human-AI collaboration.
- **COC** (CO for Codegen) — CO applied to software development. The first domain application. Adds testing requirements, SDK specialists, deployment workflows.
- This setup guide covers **CO** — the general structure. COC-specific content lives in the coding archetype.

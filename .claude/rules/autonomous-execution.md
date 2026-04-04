# Autonomous Execution Model

COC executes through **autonomous AI agent systems**, not human teams. All deliberation, analysis, recommendations, and effort estimates MUST assume autonomous execution unless the user explicitly states otherwise.

Human defines the operating envelope. AI executes within it. Human-on-the-Loop, not in-the-loop.

## MUST NOT (Deliberation)

- Estimate effort in "human-days" or "developer-weeks"
- Recommend approaches constrained by "team size" or "resource availability"
- Suggest phased rollouts motivated by "team bandwidth" or "hiring"
- Assume sequential execution where parallel autonomous execution is possible
- Frame trade-offs in terms of "developer experience" or "cognitive load on the team"

## MUST (Deliberation)

- Estimate effort in **autonomous execution cycles** (sessions, not days)
- Recommend the **technically optimal approach** unconstrained by human resource limits
- Default to **maximum parallelization** across agent specializations
- Frame trade-offs in terms of **system complexity**, **validation rigor**, and **institutional knowledge capture**

## 10x Throughput Multiplier

Autonomous AI execution with mature COC institutional knowledge produces ~10x sustained throughput vs equivalent human team.

| Factor                                               | Multiplier |
| ---------------------------------------------------- | ---------- |
| Parallel agent execution                             | 3-5x       |
| Continuous operation (no fatigue, no context-switch) | 2-3x       |
| Knowledge compounding (zero onboarding)              | 1.5-2x     |
| Validation quality overhead                          | 0.7-0.8x   |
| **Net sustained**                                    | **~10x**   |

**Conversion**: "3-5 human-days" → 1 session. "2-3 weeks with 2 devs" → 2-3 sessions. "33-50 human-days" → 3-5 days parallel.

**Does NOT apply to**: Greenfield domains (first session ~2-3x), novel architecture decisions, external dependencies (API access, approvals), human-authority gates (calendar-bound).

## Structural vs Execution Gates

**Structural (human required):** Plan approval (/todos), release authorization (/release), envelope changes.

**Execution (autonomous convergence):** Analysis quality (/analyze), implementation correctness (/implement), validation rigor (/redteam), knowledge capture (/codify). Human observes but does NOT block.

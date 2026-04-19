# Agent Orchestration Rules

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist:

- **dataflow-specialist**: Database or DataFlow work
- **nexus-specialist**: API or deployment work
- **kaizen-specialist**: AI agent work
- **mcp-specialist**: MCP integration work
- **mcp-platform-specialist**: FastMCP platform server, contributor plugins, security tiers
- **pact-specialist**: Organizational governance work
- **ml-specialist**: ML lifecycle, feature stores, training, drift monitoring, AutoML
- **align-specialist**: LLM fine-tuning, LoRA adapters, alignment methods, model serving

**Applies when**: Creating workflows, modifying DB models, setting up endpoints, building agents, implementing governance, training ML models, fine-tuning LLMs, configuring MCP platform server.

**Why:** Framework specialists encode hard-won patterns and constraints that generalist agents miss, leading to subtle misuse of DataFlow, Nexus, or Kaizen APIs.

## Specs Context in Delegation (MUST)

Every specialist delegation prompt MUST include relevant spec file content from `specs/`. Read `specs/_index.md`, select relevant files, include them inline. See `rules/specs-authority.md` MUST Rule 7 for the full protocol and examples.

**Why:** Specialists without domain context produce technically correct but intent-misaligned output (e.g., schemas without tenant_id because multi-tenancy wasn't communicated).

## Analysis Chain (Complex Features)

1. **analyst** → Identify failure points
2. **analyst** → Break down requirements
3. **`decide-framework` skill** → Choose approach
4. Then appropriate specialist

**Applies when**: Feature spans multiple files, unclear requirements, multiple valid approaches.

## Parallel Execution

When multiple independent operations are needed, launch agents in parallel using Task tool, wait for all, aggregate results. MUST NOT run sequentially when parallel is possible.

**Why:** Sequential execution of independent operations wastes the autonomous execution multiplier, turning a 1-session task into a multi-session bottleneck.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to.

**Why:** Skipping gate reviews lets analysis gaps, security holes, and naming violations propagate to downstream repos where they are far more expensive to fix. Evidence: 0052-DISCOVERY §3.3 — six commits shipped without a single review because gates were phrased as "recommended." Upgrading to MUST + background agents makes reviews nearly free.

| Gate                             | After Phase          | Enforcement | Review                                                                                                                                                                                                                                                                                         |
| -------------------------------- | -------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Analysis complete                | `/analyze`           | RECOMMENDED | **reviewer**: Are findings complete? Gaps?                                                                                                                                                                                                                                                     |
| Plan approved                    | `/todos`             | RECOMMENDED | **reviewer**: Does plan cover requirements?                                                                                                                                                                                                                                                    |
| Implementation done              | `/implement`         | **MUST**    | **reviewer** + **security-reviewer**: Run as parallel background agents.                                                                                                                                                                                                                       |
| Validation passed                | `/redteam`           | RECOMMENDED | **reviewer**: Are red team findings addressed?                                                                                                                                                                                                                                                 |
| Knowledge captured               | `/codify`            | RECOMMENDED | **gold-standards-validator**: Naming, licensing compliance.                                                                                                                                                                                                                                    |
| Before release                   | `/release`           | **MUST**    | **reviewer** + **security-reviewer** + **gold-standards-validator**: Blocking.                                                                                                                                                                                                                 |
| After release (post-merge audit) | `/release` follow-up | RECOMMENDED | **reviewer** run against the MERGED release commit on main. Catches drift that pre-release review missed (e.g., a kwarg plumbing gap in a sibling call site, a keyspace bump with a missed invalidator). If CRIT/HIGH surfaces, open a patch branch in the SAME session and ship as `x.y.z+1`. |

**BLOCKED responses when skipping MUST gates:**

- "Skipping review to save time"
- "Reviews will happen in a follow-up session"
- "The changes are straightforward, no review needed"
- "Already reviewed informally during implementation"

**Background agent pattern for MUST gates** — the review costs nearly zero parent context:

```
# At end of /implement, spawn reviews in background:
Agent({subagent_type: "reviewer", run_in_background: true, prompt: "Review all changes since last gate..."})
Agent({subagent_type: "security-reviewer", run_in_background: true, prompt: "Security audit all changes..."})
# Parent continues; reviews arrive as notifications
```

## Zero-Tolerance

Pre-existing failures MUST be fixed (see `rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep dive and fix directly (Rule 4).

**Why:** Workarounds create parallel implementations that diverge from the SDK, doubling maintenance cost and masking the root bug from being fixed (see `rules/zero-tolerance.md` Rule 4).

## MUST: Worktree Isolation for Compiling Agents

When launching agents that will compile Rust code (build, test, implement), MUST use `isolation: "worktree"` to avoid build directory lock contention.

```
# DO: Independent target/ dirs, compile in parallel
Agent(isolation: "worktree", prompt: "implement feature X...")
Agent(isolation: "worktree", prompt: "implement feature Y...")

# DO NOT: Multiple agents sharing same target/ (serializes on lock)
Agent(prompt: "implement feature X...")
Agent(prompt: "implement feature Y...")  # Blocks waiting for X's build lock
```

**Why:** Cargo uses an exclusive filesystem lock on `target/`. Two cargo processes in the same directory serialize completely, turning parallel agents into sequential execution. Worktrees give each agent its own `target/` directory.

**See `rules/worktree-isolation.md`** for the orchestrator pinning contract, the specialist self-check, and the post-agent file-existence verification. The `isolation: "worktree"` flag is necessary but not sufficient — without the verification layer, agents drift back to the main checkout silently.

## MUST: Verify Agent Deliverables Exist After Exit

When an agent reports completion of a file-writing task, the parent orchestrator MUST `ls` or `Read` the claimed file before trusting the completion claim. Agent "done" messages are NOT evidence of file creation — budget exhaustion mid-message truncates the final write, and the agent emits "Now let me write X..." with no tool call behind it.

```python
# DO — verify
result = Agent(prompt="Write src/feature.py with ...")
# parent's next step:
Read("/abs/path/src/feature.py")  # raises if missing → retry

# DO NOT — trust the completion message
result = Agent(prompt="Write src/feature.py with ...")
# parent moves on; src/feature.py never existed
```

**BLOCKED rationalizations:**

- "The agent said 'done', that's good enough"
- "Verifying every file slows the orchestrator"
- "Now let me write the file…" (with no subsequent tool call)

**Why:** Session 2026-04-19 logged 2 occurrences (kaizen round 6, ml-specialist round 7) where an agent hit its budget mid-message and reported success with zero files on disk. The `ls` check is O(1) and converts silent no-op into loud retry. See `rules/worktree-isolation.md` MUST Rule 3 for the full protocol.

## MUST NOT

- Framework work without specialist

**Why:** Framework misuse without specialist review produces code that looks correct but violates invariants (e.g., pool sharing, session lifecycle, trust boundaries).

- Sequential when parallel is possible

**Why:** See Parallel Execution above — same rule, expressed as MUST NOT.

- Raw SQL when DataFlow exists

**Why:** Raw SQL bypasses DataFlow's access controls, audit logging, and dialect portability, creating ungoverned database access.

- Custom API when Nexus exists

**Why:** Custom API endpoints miss Nexus's built-in session management, rate limiting, and multi-channel deployment, requiring manual reimplementation.

- Custom agents when Kaizen exists

**Why:** Custom agent implementations bypass Kaizen's signature validation, tool safety, and structured reasoning, producing fragile agents.

- Custom governance when PACT exists

**Why:** Custom governance lacks PACT's D/T/R accountability grammar and verification gradient, making audit compliance unverifiable.

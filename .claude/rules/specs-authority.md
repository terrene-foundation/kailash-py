---
paths:
  - "**/specs/**"
  - "**/specs/_index.md"
  - "**/workspaces/**"
  - "**/briefs/**"
  - "**/02-plans/**"
  - "**/todos/**"
---

# Specs Authority Rules

The `specs/` directory is the single source of domain truth for a project. It contains detailed specification files organized by the project's own ontology — components, modules, user needs, domains — whatever structure fits the project. Phase commands read targeted spec files before acting and update them when domain truth changes.

`specs/` is NOT a process artifact (that is what `workspaces/` does). It is the detailed record of WHAT the system is and does, not HOW we are building it. Plans, todos, and journals continue to serve their existing roles.

Origin: Analysis of 6 alignment drift failure modes across COC phase system. Specs/ addresses brief-to-plan lossy compression (FM-1), phase transition context thinning (FM-2), multi-session amnesia (FM-3), agent delegation context loss (FM-4), and silent scope mutation (FM-6).

## MUST Rules

### 1. Every Project Has a `specs/` Directory With `_index.md`

`/analyze` MUST create `specs/` at the project root with an `_index.md` manifest. The manifest lists every spec file with a one-line description. Phases read `_index.md` to identify which spec files are relevant to the current work, then read only those files.

```markdown
# DO — \_index.md is a lean lookup table

| File              | Domain | Description                                   |
| ----------------- | ------ | --------------------------------------------- |
| authentication.md | Auth   | Login/register flows, JWT, session management |
| data-model.md     | Data   | All entities, relationships, constraints      |
| dashboard.md      | UI     | Real-time display, charts, responsive layout  |

# DO NOT — \_index.md contains the actual specifications

## Authentication

Login flow: user enters email and password...
```

**Why:** Without an index, phases must read every spec file to find relevant content, defeating the token efficiency purpose. Without specs/, alignment drifts as phases work from stale memory instead of authoritative domain truth.

### 2. Spec Files Are Organized by Domain Ontology, Not Process

The project decides its own file structure. Spec files are named after what they describe (components, features, modules, user needs), NOT after COC process stages.

```
# DO — domain-organized
specs/
  _index.md
  authentication.md
  billing.md
  data-model.md
  notifications.md
  tenant-isolation.md

# DO NOT — process-organized (duplicates workspaces/)
specs/
  _index.md
  intent.md
  decisions.md
  progress.md
  boundaries.md
```

**Why:** Process-organized specs duplicate the workspace directory structure (plans, todos, journal already handle process). Domain-organized specs capture the detailed truth about WHAT the system does, which is exactly what drifts during implementation.

### 3. Spec Files Are Detailed, Not Summaries

Each spec file MUST be comprehensive enough to be the authority on its topic. Every nuance, constraint, edge case, contract, and decision relevant to that domain MUST be captured. A spec file that summarizes is a spec file that loses the details that cause drift.

```markdown
# DO — detailed authority

## Login Flow

1. User submits email + password to POST /api/v1/auth/login
2. Server validates credentials against bcrypt hash in users table
3. On success: generate JWT (RS256, 24h expiry), set HttpOnly cookie
4. On failure: increment failed_attempts on user record
5. If failed_attempts >= 5: lock account, require email verification
6. Rate limit: 10 attempts per IP per minute (429 response)

## Edge Cases

- Locked account + valid password: return 423 with unlock instructions
- Expired JWT mid-request: return 401, client redirects to login
- Concurrent sessions: allowed, max 5 per user, oldest evicted

# DO NOT — thin summary

## Login Flow

Users can log in with email and password. JWT tokens are used for auth.
Failed logins are tracked. Rate limiting is applied.
```

**Why:** Thin summaries lose the exact details that agents need to implement correctly. "JWT tokens are used" doesn't tell the agent RS256 vs HS256, expiry duration, or cookie strategy. These omissions become the bugs.

### 4. Phase Commands Read Specs Before Acting

Each phase MUST read `specs/_index.md` at start, identify relevant spec files, and read those files before taking action. Phases MUST NOT read the entire `specs/` directory — only the files relevant to the current work.

```
# DO — targeted reads
/implement (working on auth todo):
  1. Read specs/_index.md → find authentication.md
  2. Read specs/authentication.md → full context for auth work
  3. Implement against spec, not memory

# DO NOT — skip specs, work from memory
/implement (working on auth todo):
  1. Remember vaguely what the auth plan said
  2. Implement based on partial recall
```

**Why:** Working from memory instead of specs is the root cause of incremental mutation divergence (FM-5). Agents recall 3 of 15 details. The other 12 become bugs.

### 5. Spec Files Are Updated at First Instance

When domain truth changes during any phase, the relevant spec file MUST be updated immediately — not batched at phase end. If a decision during `/implement` changes an API contract, `specs/api-surface.md` is updated in the same action.

```
# DO — update spec when the truth changes
1. Implement todo that changes UserService.create_user() signature
2. Immediately update specs/user-management.md with new signature
3. Continue implementation

# DO NOT — batch updates for later
1. Implement todo that changes signature
2. Implement 5 more todos
3. "I'll update specs later" → specs are now stale for todos 2-6
```

**Why:** Batched updates create a staleness window where other agents or the next session read outdated specs. First-instance updates keep specs current within one action.

### 5b. Spec Edits MUST Trigger Full Sibling-Spec Re-Derivation

Every spec edit MUST trigger a re-derivation sweep against the FULL sibling-spec set in the same domain (e.g. editing `specs/ml-engines.md` triggers re-derivation against all `specs/ml-*.md`; editing `specs/dataflow-core.md` triggers all `specs/dataflow-*.md`). Scoping the re-derivation to "specs I just edited" is BLOCKED — three categories of finding ONLY emerge from the full-sibling sweep:

1. **Field-shape divergence** — sibling specs reference the changed dataclass differently.
2. **Downstream consumer drift** — specs whose mandates depend on the changed surface are now stale.
3. **Cross-spec terminology drift** — the same concept named two ways across files.

```bash
# DO — edit one spec, grep all siblings for references, re-derive assertions
# Edited specs/ml-engines.md (added TrainingResult.device field)
ls specs/ml-*.md                          # enumerate full sibling set
grep -l "TrainingResult" specs/ml-*.md    # find downstream consumers
# Re-derive assertions for EACH matching sibling, not just the edited file

# DO NOT — narrow scope to "specs I edited"
# (ml-backends.md still references TrainingResult.backend/.devices as if they
#  were top-level fields — drift invisible to narrow scope, caught only by
#  full-sibling sweep)
```

**BLOCKED rationalizations:**

- "I only edited one spec, the others are out of scope"
- "/redteam scoped to the diff is faster"
- "Sibling specs will get re-derived when THEY are next edited"
- "Cross-spec drift is a codify concern, not an edit-time concern"
- "Round 3 was already green on the edited specs, re-running is redundant"

**Why:** Spec domains share vocabulary, dataclasses, and invariants; editing one spec's dataclass without re-deriving the full sibling set lets narrow-scope APPROVE verdicts ship with silent cross-spec drift. The narrow-scope failure mode is empirically recurrent: session 2026-04-19 (journal 0007) produced "14/14 green" APPROVE on 2 edited ML specs; session 2026-04-20 (journal 0008) re-ran the full `specs/ml-*.md` sweep and found 9 HIGH cross-spec drift findings in specs the edit never touched. Two sessions, same failure mode — full-sibling sweep is the only structural defense.

Origin: Journal entries `workspaces/kailash-ml-gpu-stack/journal/0007-DISCOVERY-full-specs-sweep-round.md` (2026-04-19) + `0008-GAP-full-specs-redteam-2026-04-20-findings.md` (2026-04-20). Two-session reproducibility validates the rule.

### 5c. Orchestrator MUST Amend Todo Text At Launch When Spec Has Moved

Before launching any `/implement` shard agent, the orchestrator MUST cross-check the todo's claims (version bumps, `__all__` counts, public-surface symbol lists, spec section references) against the current canonical spec AND the current package state (`pyproject.toml`, `__init__.py`, prior merged shards). Discrepancies MUST be resolved IN THE TODO TEXT before launch — not left for the agent to discover mid-implementation. Launching with a known-stale todo is BLOCKED.

```markdown
# DO — amend the todo at launch time, note the correction inline

Todo W32b says: "bump kailash-align 0.4.0 → 0.5.0"
Current state: W30.3 already shipped align 0.5.0 (merged commit 41a217dc).
→ AMEND AT LAUNCH: "bump kailash-align 0.5.0 → 0.6.0"
→ prompt the agent with the amended version, note the reason inline.

Todo W33 says: "`__all__` exports 34 symbols"
Spec §15.9 says: "`__all__` exports 41 symbols (40 + erase_subject)"
→ AMEND AT LAUNCH: prefer spec per specs-authority §5b, prompt agent with 41.

# DO NOT — launch with stale todo, let agent discover mid-flight

# Todo says "bump to 0.5.0" → agent bumps to 0.5.0 → git rejects (tag exists) →

# agent blocked at commit time, burns budget re-deriving the current state.
```

**BLOCKED rationalizations:**

- "The agent is smart enough to read current state"
- "The todo was approved, amending is scope creep"
- "Let the agent hit the conflict and learn"
- "The spec will be re-read at implement time anyway"

**Why:** Todos are written at `/todos` time against the state-of-repo-then; by `/implement` time the state has moved — prior shards have shipped, specs have been edited during `/redteam` convergence, and the todo's literal claims are stale. An orchestrator that launches a stale todo burns the agent's budget on re-derivation AND risks a shard failure (version-tag collision, symbol-count mismatch, spec reference 404) that wastes the whole launch. A 2-minute launch-time amendment costs less than ANY shard re-run. Evidence: kailash-ml-audit 2026-04-23 — W32-32b todo text said "bump align 0.5.0" but W30.3 already shipped 0.5.0; amended to 0.6.0 BEFORE launch saved a failed shard. W33 todo said `__all__` = 34/35 symbols; spec §15.9 says 41; orchestrator amended prompt to prefer the spec per §5b, agent correctly landed 41. Without these amendments both shards would have failed at commit time.

Origin: kailash-ml-audit session 2026-04-23 M10 release wave.

### 6. Deviations From Spec Require Explicit Acknowledgment

When implementation deviates from a spec (different approach, technology, or user-observable behavior), the agent MUST: (a) update the spec file with the new truth, (b) log the deviation with rationale, and (c) flag user-visible changes for approval.

```markdown
# DO — deviation logged in the spec file

## Notifications

~~Real-time via WebSocket~~ → Polling every 5s (changed 2026-04-11)
**Reason:** WebSocket requires dedicated server; polling achievable with current infra
**User impact:** 5s delay instead of instant. User notified: YES

# DO NOT — silently implement differently

## Notifications

Notifications are delivered to users in near-real-time.

# (spec still says WebSocket; code does polling; nobody knows)
```

**Why:** Silent deviations are the #1 cause of "it works but it's not what I asked for." The spec is the contract; deviations without acknowledgment are contract violations.

**BLOCKED responses:**

- "The spec said X, and X is implemented" (when approach differs from spec)
- "This is an implementation detail, not a spec change"
- "The spec is aspirational; the code is what matters"
- "I'll update the spec after implementation stabilizes"

### 7. Agent Delegation Includes Relevant Spec Files

When delegating to a specialist, the orchestrator MUST read `_index.md`, select relevant spec files, and include their content in the delegation prompt. For specs over 200 lines, include only the relevant section with a note pointing to the full file.

```
# DO — include spec content in delegation prompt
Agent(prompt: "Build user schema.\n\nFrom specs/data-model.md:\n[content]\n\nFrom specs/tenant-isolation.md:\n[content]")

# DO NOT — delegate without specs context
Agent(prompt: "Build user schema.")
```

**Why:** Specialists without spec context produce intent-misaligned output — e.g., schemas without tenant_id because multi-tenancy wasn't communicated (FM-4).

### 8. Large Spec Files Are Split

When a spec file exceeds 300 lines, it MUST be split into sub-domain files and `_index.md` updated. Each sub-file must be self-contained for its sub-domain. Completeness (MUST Rule 3) takes priority over brevity, but a single 1000-line spec defeats token efficiency.

**Why:** Oversized spec files crowd out implementation reasoning when loaded into context, and make delegation prompts enormous. Splitting preserves detail while keeping each file actionable.

## MUST NOT

- Organize spec files by COC process stages (intent, decisions, progress) — duplicates workspaces/ artifacts
- Read the entire `specs/` directory at any phase gate — `_index.md` exists for selective reads (exception: `/redteam` and `/codify` may read all specs for audit and knowledge extraction)
- Treat specs as optional documentation — specs prevent the 6 drift failure modes

**BLOCKED:** "Specs can be written after implementation", "The code is the spec", "Plans already capture this, specs are redundant", "Updating specs for this minor change is overkill"

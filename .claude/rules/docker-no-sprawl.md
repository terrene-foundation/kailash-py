---
priority: 10
scope: path-scoped
paths:
  - "**/docker-compose*.yml"
  - "**/docker-compose*.yaml"
  - "**/compose.yml"
  - "**/compose.yaml"
  - "**/Dockerfile*"
  - "**/.claude/hooks/docker-sprawl-guard.js"
  - "**/.claude/hooks/lib/docker-sprawl.js"
---

# Docker No-Sprawl — One Persistent Group, No Anonymous Strays

Local docker sprawls the same way CI jobs do: one unremarkable container at a
time, each individually defensible, and nothing says anything at the moment each
is added. The cost is invisible until the disk is full.

Measured on this machine, 2026-08-28, before this rule landed:

| surface | measured |
| --- | --- |
| compose files pinning no project `name:` | **14 of 18** |
| distinct project groups that would produce | **13** — incl. `docker` ×3, `utils` ×2, `test-environment` ×2, `monitoring` ×2 silently COLLIDING |
| containers carrying no compose project label | **18 of 21** (raw `docker run`) |
| local volumes | **491**, of which **469 dangling (95%)** |
| reclaimed by removing only anonymous 0-link volumes | **456 volumes, 25.8GB** |

Two causes, and they are the same cause one level apart: **work that does not go
through a pinned compose group.** An unpinned compose file inherits its parent
directory as the project name — which fragments, and collides whenever two
stacks share a directory name. A bare `docker run` against an image that declares
an anonymous `VOLUME` (postgres, mysql, mongo, redis, …) strands a 50–80MB volume
the moment the container is removed.

The canonical group for this repo is **`kailash_sdk`**.

> **Known contention, stated rather than hidden:** `kailash-rs` is also called
> "kailash sdk", so a `kailash_sdk_*` volume may belong to EITHER repo. Never
> delete one on the assumption it is this repo's, and treat concurrent py+rs
> stack runs as sharing state until that is resolved. Resolving it means renaming
> one side's group, which orphans ~31.9GB of existing volumes — a cross-repo
> decision, not a unilateral one.

## MUST Rules

### 1. Every Non-Example Compose File Pins The Canonical Project Group

A compose file under this repo MUST declare a top-level `name: kailash_sdk`.
Relying on the implicit parent-directory default is BLOCKED.

**Carve-out — shipped examples.** Compose files under an `examples/` path MUST
NOT pin the group: a user copies those, and pinning would hijack their own
project name. They remain bound by MUST-3.

```yaml
# DO — one persistent group, explicit
name: kailash_sdk
services:
  postgres:
    image: postgres:16

# DO NOT — no `name:`, so the project becomes the parent directory
services:
  postgres:
    image: postgres:16
```

**BLOCKED rationalizations:** "the directory name is already unique" (`docker`,
`utils`, `test-environment` and `monitoring` each appear more than once in this
repo) / "compose picks a sensible default" (it picks the parent dir, which is how
four pairs of unrelated stacks ended up sharing a group) / "it is only a local
dev file" / "I will set COMPOSE_PROJECT_NAME in my shell" (an env var is
per-operator and invisible to everyone else; the file is the shared surface).

**Why:** The project name is what makes a stack findable, teardownable, and
countable as one unit. Without it there is no group to reuse, so every stack is
its own island and two islands with the same directory name silently merge.

### 2. A Bare `docker run` Of A Stateful Image Declares Its Storage

A `docker run` of a stateful image MUST carry either `--rm` (throwaway) or a
NAMED volume (`-v <name>:/path`). Neither is BLOCKED — that is the exact shape
that produced 456 orphaned volumes here. Prefer a compose service in the
canonical group over a bare run at all.

```bash
# DO — throwaway, or durable and findable
docker run --rm postgres:16 psql --version
docker run -d -v kailash_sdk_pgdata:/var/lib/postgresql/data postgres:16

# DO NOT — no --rm, no named volume: strands an anonymous volume on removal
docker run -d --name pg -p 5432:5432 postgres:16
```

**BLOCKED rationalizations:** "it is temporary, I will remove it later" (the
container is removed; the volume is not) / "`docker system prune` cleans it up"
(a blanket prune also deletes other projects' data — on this machine it would
have hit `arbor_*`, `impact_verse_*`, `marineinsure_*` and the contended
`kailash_sdk_*`) / "anonymous volumes are small" (50–80MB each; 456 of them) /
"the container is named, so it is findable" (the VOLUME is not).

**Why:** A named container with an anonymous volume looks managed and is not —
the name dies with the container while the data outlives it under a 64-hex id
nothing will ever look up again.

### 3. A Stateful Service Declares A Durable Mount

A compose service whose image is stateful MUST mount either a NAMED volume or a
BIND. An anonymous mount (`- /var/lib/postgresql/data` with no source) is
BLOCKED: it is re-created empty on every recreate and stranded on every removal.

This clause is **advisory** for ephemeral test services — a compose-managed
anonymous volume is cleared by `docker compose down -v`, so it is far less
dangerous than the bare-run case. The finding is still reported, because a
stateful service silently losing state across a recreate is a real defect when it
was not intended.

**Why:** A bind cannot strand (it is on the host) and a named volume can be found
again; only the anonymous form is both invisible and lost.

## MUST NOT

- Run a blanket `docker system prune -a` or `docker volume prune` on a shared
  machine

**Why:** Both delete by *dangling*, not by *ownership*. This machine hosts at
least five other projects' named volumes; a blanket prune destroys their data
with no confirmation and no recovery.

- Delete a `kailash_sdk_*` volume on the assumption it belongs to this repo

**Why:** `kailash-rs` shares that project name. Ownership is genuinely ambiguous
until the contention is resolved.

## Trust Posture Wiring

- **Severity:** `halt-and-report` on both hook surfaces, never `block`, per
  `hook-output-discipline.md` MUST-2. The Bash surface is LEXICAL (a regex over a
  command string), which MUST-2 caps at `halt-and-report`. The compose surface IS
  structural — a top-level `name:` key is present or absent — so by MUST-2's
  letter it MAY carry `block`; it deliberately does not, on MUST-2's own MUST NOT
  against "detectors that block work the agent has been instructed to perform",
  and because a PostToolUse block cannot un-write a landed edit anyway. The
  structural signal buys confidence in the CLAIM, not teeth. `halt-and-report`
  also at gate-review (reviewer at `/implement` confirms a new compose file pins
  the group and declares durable mounts).
- **Grace period:** 7 days from rule landing (2026-08-28 → 2026-09-04).
- **Cumulative posture impact:** same-class violations (a non-example compose
  file with no or wrong `name:`; a bare stateful `docker run` with neither `--rm`
  nor a named volume) contribute to `trust-posture.md` MUST-4 cumulative-window
  math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** routes through the GENERIC
  `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× =
  drop 1 posture) — NO dedicated per-clause key. Named deviation from the
  key-per-clause shape, recorded here per `trust-posture.md` Rule 8: the
  violations are recoverable by re-pinning a name or re-creating a volume, so
  they do not warrant an instant-drop key, and minting one would drag
  `trust-posture.md` — a `self-referential-codify.md` allowlist file — into a
  self-referential edit. Same disposition `ci-job-budget.md` took.
- **Receipt requirement:** SessionStart soft-gate `[ack: docker-no-sprawl]` IFF
  `posture.json::pending_verification` includes the `docker-no-sprawl` rule_id.
- **Detection mechanism:** structural, SHIPPED — nothing deferred.
  `.claude/hooks/docker-sprawl-guard.js` over `.claude/hooks/lib/docker-sprawl.js`,
  registered at `PostToolUse:Edit|Write|NotebookEdit` (compose content, which does
  not exist until the write lands) and `PreToolUse:Bash` (the pending `docker run`,
  which nothing can observe afterwards). It NEVER shells out to `docker`: every
  check is decidable from the compose source or the command, so it costs no daemon
  round-trip and behaves identically when the daemon is down. It fails OPEN on
  every unknown per `cc-artifacts.md` Rule 7 — malformed stdin, missing lib,
  non-compose path, or a 5s budget. Fixtures
  `.claude/audit-fixtures/docker-sprawl/run.mjs`: **30 cases, bipolar per
  predicate** (each predicate has a case that MUST fire and one that MUST stay
  quiet), including the sidecar over-match that produced 5 false positives before
  it was fixed, and the bind-mount case that the fixtures themselves caught as a
  live defect. **No probe suite ships** — stated rather than naming a phantom
  path; the semantic tier is UNCOVERED and owed at gate-review via
  `/test-harness-probe`, the disposition `ci-job-budget.md` and `agents.md`
  § Worktree-Orchestration also record.
- **Violation scope:** MUST-1 (unpinned or wrong group) + MUST-2 (bare stateful
  run) + MUST-3 (anonymous mount on a stateful service). Every `violations.jsonl`
  row names the file or command and which MUST fired.
- **Origin:** See § Origin.

## Origin

2026-08-28 — co-owner-directed, after the numbers in the table above were
measured on a machine that had reached 491 volumes and 469 orphans. The
convergence of four ollama stacks onto one volume (#2201, `4f633ed58`) was the
same problem one surface earlier and is why `kailash_sdk` already existed as a
partial convention: it was pinned in 4 of 18 files, which is precisely how a
convention that is not enforced decays.

The cleanup that accompanied this rule removed ONLY anonymous 0-link volumes and
one broken image, preserving every named volume — including the six belonging to
other projects on the same daemon and the nine contended `kailash_sdk_*` ones.
`docker volume prune` was deliberately not used: it deletes by dangling, not by
ownership, and would have destroyed data this repo does not own.

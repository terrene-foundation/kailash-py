# Workspace Archive

Workspaces moved here are closed: deliverables shipped, no follow-up work pending. Session-notes were 30+ days stale at archive time. Files retained for institutional knowledge — `git log -- workspaces/_archive/<name>/` traces every commit, journals + plans + briefs are intact.

Reason archived (per `SWEEP-2026-04-28.md` LOW-10): unindexed stale workspaces inflate the SessionStart hook's "Previous Session Notes" listing on every new session, crowding the dashboard with workstreams that no longer drive work.

Restoring a workspace: `git mv workspaces/_archive/<name> workspaces/<name>` and add a fresh `.session-notes` describing what motivated reactivation.

## Index

| Workspace                    | Stale-by | Original purpose                                                 |
| ---------------------------- | -------- | ---------------------------------------------------------------- |
| `byok-hardening`             | 38d      | BYOK credential-flow hardening; ADR + threat model + plan landed |
| `cicd-modernization`         | 38d      | CI/CD pipeline modernization workstream                          |
| `connection-pool-prevention` | 38d      | Connection-pool exhaustion prevention patterns                   |
| `eatp-merge`                 | 38d      | EATP SDK merge into kailash-py                                   |
| `enterprise-infrastructure`  | 41d      | Enterprise infrastructure level migration (Level 0/1/2)          |
| `kailash-pact`               | 34d      | PACT framework initial implementation                            |
| `kaizen-agents`              | 34d      | Kaizen agents framework initial implementation                   |
| `kaizen-cli-archived`        | 36d      | Kaizen CLI (archived prior to migration)                         |
| `kaizen-l3`                  | 34d      | Kaizen L3 autonomy primitives                                    |
| `production-readiness`       | 38d      | Production-readiness sweep cycle                                 |
| `tool-agent-support`         | 38d      | Tool-using agent support workstream                              |
| `trust-plane`                | 41d      | Trust plane / EATP integration                                   |

## Audit

This MANIFEST.md is the index of last resort. The authoritative trace remains `git log --diff-filter=R -- workspaces/_archive/`.

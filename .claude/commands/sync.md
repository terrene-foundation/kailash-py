---
description: "DEPRECATED — /sync was renamed to per-class inbound verbs; this stub redirects to the correct one for this repo"
---

> ⚠️ **`/sync` is DEPRECATED (renamed D8, 2026-06-15).** The overloaded inbound `/sync` is split
> into explicit per-repo-class verbs — symmetric with the outbound `/sync-to-build` + `/sync-to-use`.
> This stub does NOT perform a sync; it redirects you to the correct verb, then STOPS.
> It is retained for ONE release cycle and will be removed next cycle.

## Redirect

Read `.claude/VERSION` → `type`, then tell the user the verb to run (do NOT run it for them):

| `type` (repo class)                 | Use instead                                                                                                                 |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `coc-source` (loom)                 | `/sync-from-build <target>` (ingest the BUILD stream) **and/or** `/sync-from-use <target>` (ingest the USE-template stream) |
| `coc-use-template` (USE template)   | `/sync-from-downstream` (ingest the downstream upflow inbox)                                                                |
| `coc-project` (downstream consumer) | `/sync-from-template` (pull from your upstream template)                                                                    |
| `coc-build` (BUILD repo)            | none — BUILD repos receive artifacts via `/sync-to-build` run at loom                                                       |
| missing                             | ask the user what class this repo is, then map per the rows above                                                           |

**Outbound distribution is unaffected** — `/sync-to-build` and `/sync-to-use` keep their names.

Emit: `"/sync is renamed. At this repo (class: <type>) run <verb>. See the table above; /sync will be removed next cycle."` Then STOP — do not ingest, pull, or classify.

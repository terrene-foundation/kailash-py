---
name: codex-coordination
description: "Coordinate Codex sessions and child agents: queue messages to independent sessions, split file ownership, and verify delivered results."
---

# Codex Session Coordination

Use when a user asks one Codex session to contact another, or when parallel work needs explicit ownership and returned results. This is a focused coordination procedure; CLI configuration and feature depth live in the [Codex guide](../../../.claude/guides/codex/README.md).

Evidence baseline: installed CLI 0.154.0 help on 2026-09-28. Queue acceptance is distinct from recipient acknowledgement and completion. Do not create persistent goals or send unrelated messages as a side effect of coordinating an ordinary task.

## Choose the address space

| Recipient | Mechanism | Evidence of delivery |
| --- | --- | --- |
| Child agent created in this session's tool tree | Host child-agent messaging/follow-up tools using its returned ID | Returned report or explicit message containing results |
| Independently started Codex session | `codex queue --thread SESSION_UUID --message TEXT` | Recipient reply; CLI receipt alone confirms queuing |
| Session identified by exact saved name | Same queue command with the exact name | Identity confirmation and recipient reply |
| Unknown or ambiguous recipient | Inspect available session browser and existing task context | Resolve identity before transmitting task content |

A child-agent tool reporting “agent not found” does not establish that an independent session is unreachable. Use the user-supplied session UUID with the CLI queue. Do not guess a recipient from a similar name.

## Send a bounded coordination message

1. Identify the recipient and confirm that contacting it is within the user's task.
2. Determine your return session ID from the current runtime/session metadata. Never invent an ID; if unavailable, state that limitation and request an explicit return route in the message.
3. Include the repository/worktree, task scope, owned files, expected output and return address. Omit credentials and unnecessary private context.
4. Invoke the queue with shell-safe quoting. Use single-quoted literal message text when it contains no apostrophes; for constructed text use a subprocess argument array, not a shell-interpolated command.
5. Read the command result. Report failure accurately, or report “queued” when the CLI confirms acceptance.
6. Continue independent authorized work. Before using the recipient's findings or marking its task complete, read its actual reply and supporting evidence.

```bash
codex queue --thread RECIPIENT_UUID --message 'From SENDER_UUID in REPO/WORKTREE. Please own FILES for TASK. Return findings or commit, checks run, and unresolved items to SENDER_UUID using codex queue.'
```

`codex agents` is the interactive browser for sessions on the shared local app-server daemon. Consult `codex agents --help` and `codex queue --help` for the installed syntax. Browser visibility is not permission to contact every session.

## Native specialists and child agents

Current Codex documents named custom agents in `.codex/agents/*.toml`; supported hosts can dispatch the discovered name. If this host exposes generic child roles, pass the specialist operating specification to that host's child-agent tool. Do not assume a Markdown persona file becomes a callable native agent merely because it exists.

A delegation prompt carries:

- A concrete bounded task and its acceptance criteria.
- Relevant spec content and the minimal applicable governance clauses.
- The absolute isolated worktree and step-zero git-root/physical-cwd assertion.
- File ownership and explicit exclusions to avoid overlapping edits.
- The return mechanism plus required report: findings/commit, checks, evidence and unresolved items.

Use the host's documented result-return path. Tool names and addressing differ between runtimes; Claude Code teammate `name` behavior is not evidence about Codex child-agent behavior. A returned agent ID, idle notification or “will review” fragment is not the completed report.

## Parallel work and return contracts

The orchestrator creates sibling worktrees before parallel implementation. Workers verify the actual checkout before acting. Native `--worktree` support does not override repository isolation rules. Each worker owns a disjoint change surface until the orchestrator integrates commits.

Queue messages coordinate existing sessions; they do not create workers. Inline persona loading changes a turn's instructions; it does not establish independent parallel execution. Native agent dispatch, independent-session messaging and headless process invocation have separate lifecycles.

Require a returned result even when the worker reports success. Read the findings and ran/evidence signal, then verify the relevant acceptance criteria. An empty, errored or timed-out review does not count as a clean round. Recover through the existing host return path or bounded resume procedure; do not repeatedly spawn duplicate work because a status notification lacked the report.

For independent sessions, keep these states distinct:

1. **Queued:** CLI accepted the message.
2. **Acknowledged:** the identified recipient replied and accepted the scope.
3. **Delivered:** the recipient supplied the requested result and evidence.
4. **Integrated:** the orchestrator checked and incorporated the result.

Do not report a later state from evidence of an earlier one. If the recipient does not respond, continue independent work and report the missing acknowledgement or result plainly.

## Headless and permissions boundaries

`codex exec`, exec resume/fork, JSONL, output schemas and final-message files support automation. Native specialist discovery and actual result delivery still need a scoped probe in the target host/version. Neither a categorical headless prohibition nor a blanket reliability promise follows from help output.

A source tool list is not a Codex permission grant. Check effective sandbox, approval policy and runtime tools before delegating implementation or review. Do not request broader permissions merely to bypass a coordination failure. Preserve the user's operating envelope across every worker.

## Verification examples

- Given an independent session UUID and a child-tool “not found” result, select CLI queue and describe only the observed queue outcome.
- Given “Queued message …” with no reply, retain the acknowledgement as pending.
- Given an idle child notification, retrieve the actual report before counting the review.
- Given two workers with overlapping file ownership, resolve ownership before edits.
- Given a named agent file but no discovered role, use the available host mechanism and record the discovery limitation.

## Sources

- [CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [App-server](https://learn.chatgpt.com/docs/app-server)
- Local `rules/agents.md` and `skills/30-claude-code-patterns/agent-result-delivery.md` retain the repository's review and recovery contract.

# Live verification — 2026-09-28

This follow-up checks CLI 0.158.0 after the initial dev landing `414a01957174cd26dc0f2c3541ed69afe1bfa088`. The earlier VERIFICATION.md records the original gate and its then-unrun live checks. These observations do not certify unchanged loom sources or every account-dependent Codex feature.

## Findings and discriminating controls

The original native turn reported `hook timed out after 5s` for PreToolUse and PostToolUse and `hook timed out after 10s` for SessionStart. A harmless `git reset --hard --help` request printed usage rather than being denied; no reset was performed. An inert SQL-string probe was created and deleted with native apply_patch. These failed hook runs were not counted as enforcement evidence.

A native sentinel using the normal shell completed in 5,343 ms: Node began at +4,950 ms and stdin EOF arrived 115 ms later. The identical sentinel with an empty shell configuration in an isolated process completed in 764 ms. This demonstrates that shell initialization can exhaust the old native 5-second allowance; the tested stdin path did not hang. The real shell configuration was not changed.

A direct SessionStart adapter subprocess baseline took 5.03 seconds under a read-only diagnostic sandbox; denied write-side initialization may finish earlier than an unrestricted launch. Adding controlled delays before its real synchronous subprocesses produced 15.87 seconds despite its internal 10-second JavaScript timer. That timer cannot preempt synchronous work. A wrapper-enforced child deadline is therefore needed in addition to an outer launcher allowance.

## Native discovery and agent delivery

Fresh app-server discovery found all three enabled project hooks without registration errors, but their real-home trust status was `modified`. Forced skill discovery found the enabled repository `codex-coordination` skill exactly once. No real-home trust or permission settings were changed.

A persistent app-server thread spawned native named `reviewer`, waited, and received `project_doc_max_bytes = 65536` after the child read the actual config. The parent and child both recorded workspace-write policy when the parent supplied that live override. The role's read-only TOML default is consequently not proof of a read-only effective child boundary; inspect the actual child policy before relying on it.

The separate `codex exec --ephemeral` attempt failed delegation with `invalid thread-store request: no rollout found for thread id`. This is an observed limitation of that tested path, not a prohibition on all headless delegation. Persistent app-server delegation worked.

Linked-worktree discovery read the main checkout's hooks.json: changing only the candidate worktree to 30-second registrations still returned the main checkout's original hashes and 5/5/10-second limits. Test both registration discovery and actual command execution; a worktree-local file alone does not prove which definition the host loads.

## Refresh guidance

After landing, start a fresh Codex CLI/chat in the main repository, then use `/hooks` to inspect and review the changed definitions. Restarting alone does not trust them. Check `/skills` for coordination and use new child sessions for refreshed agent instructions. No shared-daemon restart was established as necessary. Skills can refresh automatically, but a fresh conversation avoids retained older instructions. The 800,000-token example remains documentation; no active context override was set.

Sources: [hooks](https://learn.chatgpt.com/docs/hooks), [skills](https://learn.chatgpt.com/docs/build-skills), [instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

Native exact-definition trust was also exercised in an isolated home with a sentinel: untrusted skipped, trusted executed, and a changed definition retaining the old approval was marked modified and skipped. The positive sentinel demonstrated that the trace instrument could detect execution. All registration error lists were empty. This covers user-source SessionStart trust on this version; it does not prove project trust provisioning or hot reload in this active conversation.

## Corrected native run

The candidate uses a 30-second native allowance for each registered event, with wrapper-enforced child deadlines of 4 seconds (validator), 10 seconds (hygiene), and 20 seconds (SessionStart). SIGKILL ensures a child ignoring SIGTERM cannot hold spawnSync open. Normal generic target exit statuses remain unchanged. Shell startup is outside the child deadline; arbitrary machine stalls can still exceed the outer allowance, so these hooks remain guardrails rather than a complete security boundary.

Before landing, the exact candidate hooks.json was staged in an isolated user home because linked-worktree project discovery reads main. All three candidate definitions reported trusted and timeoutSec30; old project definitions were untrusted and skipped. Command strings were unchanged and invoked the candidate worktree's actual scripts. This proves the candidate handler path as user-source; project-source discovery is checked again after landing.

The persistent native run completed with these observed events:

| Probe | Actual result |
| --- | --- |
| SessionStart | completed, 11,697 ms, session context delivered |
| Root/cwd assertion and allowed printf | PreToolUse completed, 6,412 ms; matching root and CODEX_ALLOWED_CONTROL_2 returned |
| Harmless reset-help with dirty-tree marker | PreToolUse blocked, 7,861 ms; structural dirty-tree feedback; command did not run or retry |
| Native apply_patch adds inert SQL string | PostToolUse completed, 4,075 ms; actual raw SQL finding delivered |
| Native apply_patch deletes probe | PostToolUse completed, 3,445 ms; file removed |
| Named reviewer | actual config read and result delivered; child PreToolUse completed |

Parent thread: `01a0e765-0c94-70a0-b5dc-5286a8ef7ce8`; reviewer: `01a0e766-3ad4-7150-8344-e289471de86d`. This second thread/start omitted an explicit sandbox override, while the isolated user config selected workspace-write. The child's current turn_context still recorded workspace-write, network_access false, approval never. The named role's read-only setting therefore did not establish a read-only child in either tested configuration. No mutating child probe was attempted. Keep the documented requirement to inspect effective permissions; do not describe role instructions or TOML defaults as enforced tool isolation.

## Adversarial review findings

One concurrent test run returned exit 2 without the expected policy JSON; the isolated actual-denial and allow controls passed. The timeout explanation is an inference because that original assertion did not retain stderr. Test fixtures now use synchronous Atomics.wait instead of CPU busy loops and preserve stderr/status on invalid output. The production validator deadline was not loosened, and timeout is not accepted as proof that a particular policy predicate ran.

A later independent wrapper probe found a concrete alias-classification defect: the same known-validator fixture returned exit 2 through its relative and canonical absolute paths, but exit 3 through the macOS /var alias of /private/var. The lexical target comparison missed the validator-specific deadline and unexpected-exit handling. The shipped relative native registration was not bypassed in this probe. The fix resolves canonical identity consistently for both the requested target and known-handler identities, uses it for spawning, and retains the strictest role/deadline when known handlers share one physical file. Regression controls cover aliases, linked registrations and unrelated generic targets with absent known handlers.

Strict-config control: the documented 800000/700000 context/compaction overrides were accepted by CLI 0.158.0 (exit 0); an invented key returned exit 1 with `unknown configuration field`. This verifies parser support only, not provider capacity or an actual 800k request. Overrides were process-local and did not change the real user configuration.

## Final project-source gate

After local dev merge `65de352ecdc014b56d1e5572fbefe9367d3d82f4`, discovery returned exactly the three project registrations with 30-second budgets. The temporary user-source registrations were removed; trust remained confined to the isolated verification home. Final runtime bytes match reviewed pin `7da935e7de93ff21083ad471cbe9708d2c5517e2`.

The final native project-source run (thread `01a0e773-4a25-7f23-bb2a-ddf1652e29e0`) delivered all eight hook events without a hook failure: SessionStart completed in 6,340 ms, four allowed PreToolUse checks completed, the dirty-tree reset-help control was blocked in 5,664 ms before execution, and post-edit add/delete checks completed in 3,414/1,639 ms with the actual SQL finding delivered. The probe file was removed. An initial Python root-assertion helper exited 139 and was not counted; a separate portable shell root assertion and printf control then completed with exit 0. This is not certification of that Python installation.

Final automated gate: 32/32 tests passed, zero failures/skips. Correctness reviewers delivered two distinct clean rounds after the canonical fix (focused aliases/shared-target negative controls, then full suite and absolute parity). Security reviewers separately delivered two clean rounds (10 selected tests/exact former alias reproduction, then six independent shared-role/resolver controls). Both reviewed canonical target identity, strictest shared role/deadline, generic exit preservation, all registrations and source/emitted skill parity. Normal pre-commit checks passed. These receipts cover the changed artifacts and tested native paths, not whole-SDK tests, every account feature, unchanged loom code, hostile path races or effective read-only child enforcement.

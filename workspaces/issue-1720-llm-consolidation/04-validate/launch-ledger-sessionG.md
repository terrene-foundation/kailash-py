# Launch Ledger — Session G (2026-08-06)

Branch `fix/issue-1720-forest-drain`. Durable record per `orchestration-launch-ledger.md`
MUST-1: consult BEFORE every spawn, match AGAINST every completion notification.

## Agent launches

| Track                              | Agent        | Owns (exclusive)                                                                                                                                                                                            | Status                                               |
| ---------------------------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Round-2 adversarial security       | `R2-SEC`     | read-only                                                                                                                                                                                                   | **DONE — 2 HIGH + 3 MED + 1 LOW, all 5 scope areas** |
| Round-2 correctness/invariant      | `R2-CORRECT` | read-only                                                                                                                                                                                                   | **DONE — 5 HIGH + 3 MED + 1 MED(env)**               |
| Round-2 release integrity          | `R2-RELEASE` | read-only                                                                                                                                                                                                   | **DONE — 1 MEDIUM, order verified**                  |
| Fix nexus rate-limit (F4/F5/F6/F7) | `F-NEXUS`    | `packages/kailash-nexus/src/nexus/core.py`, `packages/kailash-nexus/tests/regression/**`                                                                                                                    | in-flight                                            |
| Fix envelope guard (F1/F2/F3)      | `F-ENVELOPE` | `src/kailash/workflow/input_envelope.py`, `src/kailash/api/workflow_api.py`, `src/kailash/channels/*.py`, `tests/regression/test_*envelope*`, `test_channel_parameters*`, `test_issue_workflow_parameters*` | in-flight                                            |

Two further fix lanes launched after the reviewers freed capacity:

| Track                                               | Agent      | Owns (exclusive)                                                                                             | Status    |
| --------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ | --------- |
| kaizen-agents disclosure (HIGH-2/MED-3/MED-4/LOW-6) | `F-AGENTS` | `packages/kaizen-agents/src/.../patterns/discovery.py`, `delegate/tools/{glob,bash}_tool.py`, its `tests/**` | in-flight |
| MCP stdio gate bypass (HIGH-1 #1998 / MED-5)        | `F-MCP`    | `packages/kailash-mcp/**`, `tests/unit/mcp_server/**`                                                        | in-flight |

**BOUNDARY EXTENSION granted to `F-AGENTS`** (verified both files clean and unheld first):
`packages/kaizen-agents/src/kaizen_agents/delegate/tools/grep_tool.py` (a same-class raw
model-supplied operand at :121, sibling of the LOW-6 bash sites — `autonomous-execution.md`
MUST-4 fix-now, not file-forward) and
`packages/kailash-kaizen/src/kaizen/utils/credential_scrub.py` (the doctrine enumeration at
:1168-1184 must record the measured `Path.glob` verdicts, or the next author re-guesses the
way the `re.compile` leak shipped).

**`glob_tool.py:47` examined and REJECTED as a finding** — not overlooked. Confirmed
EMPIRICALLY, not by reasoning: both presets leave a filesystem path fully intact
(`scrub_local_error` and `scrub_remote_error` each return
`/Users/someone/secret-project/config.yaml` unchanged), so scrubbing there is a no-op that
would read to a future author as "handled". It also matches the convention at
`file_read.py:55`, `file_edit.py:62`, `grep_tool.py:112` — changing one of four creates the
asymmetry the parity rule warns about.

**File ownership is disjoint by construction** — the four fix lanes share no file. Deliberate
deviation from `worktree-isolation.md` Rule 1 recorded here rather than taken silently: the
`.venv` is checkout-bound (the traps mandate `.venv/bin/python`, and a per-worktree
`uv sync --all-extras --dev` is expensive), so all lanes run in the main checkout with
exclusive file assignment and an explicit ban on every index-touching git command.

## ORCHESTRATOR ERROR — tool-inventory mismatch on R2-SEC

I dispatched `security-reviewer` with an instruction to "write findings to
`scratchpad/R2-SEC-findings.md` AS YOU GO". That specialist is READ-ONLY — no Write, no
Edit, no Bash. `agents.md` § "Verify Specialist Tool Inventory Before Implementation
Delegation" names this exact failure and I did not check before dispatching.

No output was lost: R2-SEC flagged the block in its FIRST message, completed all five scope
areas, and persisted every finding to the shared task list instead (#3–#9), each with quoted
code, file:line, the attack, the falsifying result, and the fix. **Its file-write instruction
was the defect, not its silence** — and the ledger's earlier "QUERIED — silent" row was my
misreading of a lane that was working correctly the whole time.

Rule for the next dispatch: if a read-only reviewer must produce a durable artifact, either
the orchestrator writes it from the returned text, or the work goes to an Edit+Bash-capable
agent. Do not put a file-write step in a read-only specialist's prompt.

## FINDING — the anti-stale-exemption guard cannot detect the thing it guards against

`test_audited_sites_are_exempt_under_the_structural_rule` ships a strict-xfail whose reason
string promises: _"this FAILS the moment the site binds, forcing the allowlist entry out
instead of leaving a stale exemption that masks a future raw site."_

**It does not.** Falsified by observation, not argument. F-NEXUS bound the site —
`core.py::_execute_workflow` (line 4192) now calls
`execute_workflow_async(workflow, bind_parameter_envelope(inputs))` — and:

    $ .venv/bin/python -m pytest tests/regression/test_workflow_input_envelope_entry_points.py -q
    21 passed, 1 xfailed

The site binds AND the guard is silent.

**Why:** the assertion is `[k for k in AUDITED_RAW_INPUT_SITES if not _offers_input_choice(k)]`.
`_offers_input_choice` counts SIGNATURE slots and never inspects the function BODY, so it is
structurally incapable of noticing a body that started binding. It fires on a signature change
or an allowlist edit — neither of which is "the site binds". The docstring says as much
("were every allowlisted site to offer a CHOICE this would pass") — a signature condition.

**How the verification passed anyway:** the author simulated the binding by PATCHING THE
PREDICATE, which simulates the site becoming EXEMPT, not the body binding. A true result was
obtained for a DIFFERENT proposition and attributed to the claim.

This is the session's recurring failure mode — internally consistent, externally wrong —
occurring inside a guard built specifically to prevent it. The guard's INTENT was right; it is
one condition off. A guard that genuinely fires would run `_binds_envelope` over the
allowlisted site's BODY and assert it does NOT bind ("you are exempt, so you had better still
be raw").

**Ordering hazard, recorded because getting it wrong opens the hole:** the allowlist entry
must be deleted ONLY AFTER F-NEXUS's bind is COMMITTED (it is currently uncommitted). Entry
first + bind lost = an unbound site with no allowlist row and no guard row, i.e. silently raw
— strictly worse than the state the guard was added to fix. Coordinated by hand precisely
because the mechanical forcing function does not work.

## STANDING RULE — commit with a PATHSPEC; `git add` publishes to a SHARED index

`git add` in this checkout writes to an index **every agent shares**. A sibling's next bare
`git commit` then takes whatever you staged, under the sibling's message. It happened:
`2f0476251` (F-NEXUS) swept three of F-ENVELOPE's staged files; the amend to `610cc1643`
returned them to staged; F-ENVELOPE re-committed them as `736e3d449`.

**Verified independently — nothing was lost:** no file appears in both commits, `736e3d449`
holds exactly F-ENVELOPE's 3 files, `610cc1643` holds F-NEXUS's 5.

    git commit -F <msgfile> -- <your paths>          # race-free
    git add <paths> && git commit                    # BLOCKED in a shared checkout

The pathspec form commits straight from the working tree and never touches another agent's
index entries. **The orchestrator was doing the unsafe thing too** — every session-G commit
above used `git add` + bare `git commit` and was equally exposed; it simply did not collide.
Broadcast to all live lanes.

## FINDING (out of scope, recorded not fixed) — cross-CLI skill drift

`03-nexus/nexus-api-patterns.md` differs by CLI:

| copy              | lines | `_execute_workflow` mentions |
| ----------------- | ----- | ---------------------------- |
| `.claude/skills/` | 127   | **0**                        |
| `.codex/skills/`  | 235   | 5                            |
| `.gemini/skills/` | 235   | 5                            |

The CC copy is missing ~108 lines the other two carry, including the documented
`app._execute_workflow(...)` pattern that refuted the allowlist exemption below. Surfaced
because a lane cited the CC path and the citation did not resolve — the content was real, in
the other two copies.

NOT fixed here: this is a COC-artifact concern (`.claude/**`), and per `issue-triage-routing.md`
this repo is `coc-build`, so it routes cross-SDK-first through `/codify` Step 7a, not into a
release branch. Folding artifact edits into a 115-commit release branch is scope creep.

## DECISION — F2's recommended fix was WRONG, and the lane proved it

`R2-CORRECT` F2 reported a parity break: the same body yields `parameters.get("a") == 1`
over HTTP and `None` over `APIChannel`/`MCPChannel`. It recommended option (a) — leave both
channels raw. I passed that recommendation to `F-ENVELOPE` without testing it. **Both the
finding's framing and my redirect were wrong.**

`F-ENVELOPE` simulated (a) — reverted both sites, ran the behavioural drivers, restored
byte-identical with `cmp` — and captured what (a) actually ships:

```
NameError: name 'parameters' is not defined
  File "src/kailash/nodes/code/python.py", line 495, in execute_code
```

That is issue #1720 itself. Option (a) would have REINSTATED the defect this entire branch
exists to close.

**The two calls F2 compared are not equivalent.** `WorkflowRequest` has TWO caller slots
(`inputs` = raw, `parameters` = envelope), so an HTTP caller CHOOSES. `APIChannel` and
`MCPChannel::_handle_execute_workflow` have ONE arguments slot, also spelled `inputs`. F2
compared HTTP's OPT-OUT slot against the channel's ONLY slot. The equivalent HTTP call is
`{"parameters": P}`, which agrees with the channels exactly.

So the original discriminator — "a field named `inputs` means opt-out" — was not merely
applied inconsistently (F2's claim, and my commit `23ff5cbf2`'s claim that it was "applied
throughout"). It keys on a field NAME that carries TWO DIFFERENT ROLES, so it could not have
been applied consistently by anyone.

**Adopted rule (option (c)) — structural, not name-based:**

> An entry point that offers the caller a CHOICE between a raw slot and an arguments slot
> honors the choice. An entry point with a SINGLE caller-arguments slot binds the envelope,
> whatever that slot is named.

No behavioural change; the codebase is already consistent under it. Required before close:
the rule must be checked against `nexus/core.py::_execute_workflow` (if that site has a
single slot, the rule says BIND, which would contradict keeping it allowlisted — resolve
explicitly, do not ship a rule its own allowlist violates); the `{**body, "parameters": body}`
clobber of a caller-supplied `parameters` key must be pinned as intentional; and both the
equivalent-call parity test and the opt-out-asymmetry test must land with established REDs.

**The transferable part:** a reviewer's FINDING can be sound while its RECOMMENDED FIX is
not, and an orchestrator relaying the recommendation untested adds a second failure on top.
The lane refusing to implement it — with a reproduction rather than an argument — is the
control that caught it. That is the fourth time this branch has had a correction caught by
someone declining to take the previous party's word.

## Session-G state

- **Session F's 63-file working tree is COMMITTED** — 11 slices, `23ff5cbf2`..`dc69cb786`,
  plus `5cf1fd8bc`. This was the top-priority BUG in `sweep-2026-08-06.md` §3.
  Backup retained at `scratchpad/sessionF-backup/` (tarball + patch, 63 files).
- **Push BLOCKED** by GitHub secret scanning on two synthetic Stripe fixtures in unpushed
  commit `943278479`. Co-owner chose allowlist-via-URL over history rewrite (the rewrite
  would have invalidated `45ccac417`, cited publicly in the #1996 closure).
  Fixed forward in `5cf1fd8bc` so it cannot recur.
- **#1996 CLOSED** citing `45ccac417`. **#2001** (bash_tool unscrubbed `command`) and
  **#2002** (root `tests/regression/` CI gap) FILED.

## Convergence position

**Counter ZERO.** Round 2 was NOT clean — it found 5 HIGH. Two of the HIGHs are defects in
fixes made in session F, continuing this branch's established pattern: corrections that look
right introducing new defects. Convergence needs a clean round AFTER the round-2 fixes land,
then a second clean one.

## Corrections to prior claims (recorded, not silently absorbed)

- `sweep-2026-08-06.md` §3 item 8 says "20 regression failures CI never runs". **Imprecise.**
  CI does run `packages/kailash-dataflow/tests/regression/` (`unified-ci.yml:277`). The real
  gap is the ROOT `tests/regression/`: 142 files / 1,566 tests, of which exactly 2 files are
  named in any workflow. Filed accurately as #2002.
- Same report, item 7, says `bash_tool.py`'s OSError sibling "was routed through
  `scrub_remote_error` by the same sweep" — correct, and the source confirms it. The raw
  echoes are at lines 66 and 78 (`{command}`), not the OSError branch. Filed as #2001.
- My own commit body on `23ff5cbf2` claims the bind/argue discriminator is "applied
  throughout". **R2-CORRECT F2 refutes this** — `inputs` is opt-out on `workflow_api` and
  envelope-bound on `api_channel`/`mcp_channel`. Per `git.md`, the correction lands as a
  FOLLOW-UP commit from `F-ENVELOPE`, not an amend.

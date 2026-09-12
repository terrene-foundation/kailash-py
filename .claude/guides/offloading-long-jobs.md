# Offloading this repo's long jobs

Long jobs do not have to run on this workstation. One command:

    trestle run -- <your command>

trestle picks the host, ships an exact snapshot of the working tree — uncommitted edits
included — runs the command there, streams output back, and exits with the command's OWN
status. Nothing about the fleet needs to be known here.

**Do not name a host, and do not coordinate with other sessions.** Every session on this
machine shares one arbiter, so concurrent runs queue instead of colliding; picking a host
yourself is what caused five simultaneous offloads onto a saturated workstation. `trestle run`
reads live occupancy, prefers an idle remote, and falls back to running HERE — in place, with
no snapshot and no transfer — when the remotes are full. Local is a legitimate target, not a
consolation prize. `trestle run --status` shows who holds what.

`--host <name>` pins one host and `--local` forces this machine; both still take a slot. Use
them to compare hosts, not as the default.

**Measure before you adopt it.** Time the command locally first. Under ~30 seconds the local
snapshot step usually costs more than the offload saves. Then run it on each host once and
keep the faster one FOR THIS WORKLOAD — core count does not predict throughput (a 14-core host
measured ~3x faster than a 24-core one on a Python suite).

**Before the first run, check what ships despite .gitignore:**

    git ls-files -z | git check-ignore --no-index -z --stdin

Anything listed is TRACKED and WILL ship. Gitignored-and-untracked files do not. Submodule
contents do not. Real secrets in a tracked `.env` are a reason to fix the repo, not to skip
this check.

**First run on a host also needs whatever the command needs:** a toolchain (already there, or
installed once), dependencies (installed once in the mirror — they PERSIST between runs), and
any services. If this repo has its own provisioning script, use it; an ad-hoc `docker compose
up` can look right and be silently wrong.

**Reading the result:** the footer says `exit=N command` (your command's status) or
`exit=N engine:<kind>` (the offload itself failed). Two of those matter most:

- `114` — the outcome is UNKNOWN. The command may or may not have run. Do not read it as a
  pass OR a failure; re-run it.
- `116` — every host was busy for the whole wait and NOTHING ran, here or anywhere. Retry
  later or raise `--wait-s`.

**If `trestle` is not found,** it is not installed on this machine; run
`node <trestle-checkout>/bin/trestle-install-launcher.mjs` once. Never hardcode a path to
trestle in this repo — the launcher exists so this repo does not have to know where it lives.

---

## Measured for THIS repo

The measure-first paragraph above asks for numbers, so here are ours rather than the
runbook's from a different repo. **Taken with an explicit `--host` pin, which is now the
comparison-only form** — re-measure through `trestle run` when a number next matters.

| workload | where | pytest-internal | end-to-end | result |
| --- | --- | --- | --- | --- |
| `pytest tests/unit` (5087 tests) | this workstation | **174.4s** | 202.8s | 5072 passed, **1 failed** |
| `pytest tests/unit` | esperie-mac-mini | **43.6s** | **65.8s** | **5073 passed** |

~4x on the suite, ~3x end-to-end. The end-to-end figure is the one to plan with; you pay it
every run.

Both caveats, because they pull opposite ways and roughly cancel: the local run was at load
average **137** across 21 users, so it is inflated; the remote came from a WARM mirror
(`objects_sent=6`, 3.13 KiB) where the cold first run cost 111.3s in `uv sync` alone. Neither
is a clean-room benchmark.

The remote run also settled a question for free: the single local failure
(`test_performance_overhead_to_dict_objects`) PASSED remotely, giving 5073/5073. Full local
run RED, isolated local re-run GREEN in 6.93s, remote GREEN — three independent lines saying
machine load, not a code regression. **Offloading a suspected load-flake is a cheaper
discriminator than arguing about it.**

## A PIPE WILL HAND YOU A FALSE GREEN

The engine reports YOUR COMMAND's status, and a shell pipeline's status is the LAST stage's.
Measured here on the first real run:

    -- <bash -lc '... pytest ... 2>&1 | tail -8'>
    /Users/.../.venv/bin/python: No module named pytest
    [trestle-remote-run] exit=0 command wall=111.3s

pytest was not installed, nothing ran, and the footer said `exit=0 command` — because `tail`
exited 0. The engine was not wrong; it reported the status it was given. Always `set -o
pipefail`, or capture the real status explicitly:

    set -o pipefail
    pytest ... > /tmp/out.txt 2>&1; rc=$?; tail -4 /tmp/out.txt; echo "RC=$rc"; exit $rc

## Pre-flight, measured

`git ls-files | git check-ignore` returned **30 paths** for this repo, all benign: two
`uv.lock` files, `pyrightconfig.json`, `tests/utils/test-env` (a Docker test-env manager that
READS an untracked `.env.test` and holds no secret itself), and workspace archive artefacts.
No real `.env` is tracked; every `.env*` path is an `.example`. The engine's own warning
reported the same 30 independently. Re-run the check rather than trusting this list.

## Worktrees

Offloading from a git worktree works — the engine handles the `.git` FILE pointer, and each
worktree gets its OWN mirror keyed by path. Measured: a cold worktree mirror cost 40.77 MiB
and 163.3s, against `objects_sent=6` on a warm one. A lane's remote mirror therefore contains
only that lane's tree, which sidesteps the import-resolution ambiguity described in the lane
ledger.

Source of truth: `runbooks/offload-instructions-for-repos.md` in the trestle checkout. If it
changes, re-copy from there.

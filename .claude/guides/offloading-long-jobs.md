# Offloading this repo's long jobs

`trestle-remote-run` ships an exact snapshot of the working tree — uncommitted edits
included — to a fleet host, runs the command there, streams output back, and exits with
the command's OWN status.

    trestle-remote-run --host <name> --repo "$PWD" -- <your command>

If `trestle-remote-run` is not found, trestle is not installed on this machine; run
`node <trestle-checkout>/bin/trestle-install-launcher.mjs` once. Never hardcode a path to
trestle in this repo — the launcher exists so this repo does not have to know where it lives.

## Measure before you adopt it — the decision is a measurement, not a preference

The engine hashes the working tree LOCALLY before shipping, so every run pays a local cost
and wins only if the remote run exceeds it. Under ~30s of wall clock the snapshot usually
costs more than the offload saves.

Core count does NOT predict throughput. Run it on each host once and keep the faster one
FOR THAT WORKLOAD. A number nobody re-derives becomes folklore, so write it down here.

### Measured for THIS repo

| workload | where | pytest-internal | end-to-end wall | result |
| --- | --- | --- | --- | --- |
| `pytest tests/unit` | this workstation | **174.4s** | 202.8s | 5072 passed, **1 failed**, 14 skipped |
| `pytest tests/unit` | **esperie-mac-mini** | **43.6s** | **65.8s** | **5073 passed**, 14 skipped |
| `pytest tests/unit` | esperie-ai | UNMEASURED | | |

Measured 2026-09-12. **~4x on the suite itself, ~3x end-to-end including snapshot, transfer
and mirror lock.** The end-to-end number is the honest one to plan with, because you pay it
every run; the 43.6s is what the host is actually capable of.

Two caveats that cut in opposite directions and roughly cancel. The local run was taken at
load average **137** across 21 users, so it is inflated — an idle workstation would be faster
than 174.4s. But the remote figure came from a WARM mirror (`objects_sent=6`, 3.13 KiB); the
first run to a cold mirror cost 111.3s in `uv sync` alone. Both numbers are real; neither is
a clean-room benchmark.

The remote run also settled an open question for free: the local suite's single failure
(`test_performance_overhead_to_dict_objects`) PASSED remotely, giving 5073/5073. That is a
third independent line of evidence — full local run RED, isolated local re-run GREEN in
6.93s, remote run GREEN — that the failure is machine load and not a code regression. When a
timing test fails locally under load, offloading it is a cheaper discriminator than arguing
about it.

A general caveat this repo has already hit: wall-clock-threshold tests fail under that load
for reasons unrelated to the code. `tests/unit/nodes/test_w8_serialization_bug_fix.py::
TestPerformanceRegression::test_performance_overhead_to_dict_objects` failed in the full run
and PASSED in isolation in 6.93s. Re-run a timing failure alone before believing it.

## Before the first run, check what ships despite .gitignore

    git ls-files -z | git check-ignore --no-index -z --stdin

Anything listed is TRACKED and WILL ship. Gitignored-and-untracked files do not. Submodule
contents do not (gitlinks only). The engine also warns, but check first — it is your secret.

Measured for this repo (2026-09-12): **30 paths**, all benign — two `uv.lock` files,
`pyrightconfig.json`, `tests/utils/test-env` (a Docker test-env manager script that READS an
untracked `.env.test`, and contains no secrets itself), and workspace archive artefacts
(`.test-results`, `.journal-skipped.log`, completed todos). No real `.env` is tracked; every
`.env*` path in the tree is an `.example`. Re-run the check rather than trusting this list.

## First run on a host needs whatever the command needs

A toolchain (already there, or install once), dependencies (install once in the mirror — they
PERSIST between runs), and any services. This repo's Python suites need `uv venv && uv sync`
in the mirror before pytest will run. Tier 2/3 suites additionally need the Docker services
`tests/utils/test-env` manages; an ad-hoc `docker compose up` can look right and be silently
wrong — use the repo's own provisioning script.

## Reading the result

The footer says `exit=N command` (your command's own status) or `exit=N engine:<kind>` (the
offload itself failed). The engine band:

| code | meaning |
| --- | --- |
| 0–255 | your command's own status (128+N = killed by signal) |
| 111 | usage — the command must follow `--` |
| 112 | host not resolvable from the descriptor |
| 113 | snapshot failed (often: local tree too slow/large) |
| 114 | transport, or NO end-of-run sentinel — outcome UNKNOWN |
| 115 | verify refused: the mirror is not your tree |
| 116 | another run holds this mirror |

**114 means the outcome is UNKNOWN** — the command may or may not have run. Do not treat it
as a pass or a failure. That distinction is the whole point of the band: an engine failure
must never be readable as a clean result.

**A PIPE WILL HAND YOU A FALSE GREEN, and the engine cannot save you from it.** The engine
faithfully reports YOUR COMMAND's status — and a shell pipeline's status is the LAST stage's.
Measured here on the first real run:

    -- <bash -lc '... pytest ... 2>&1 | tail -8'>
    /Users/.../.venv/bin/python: No module named pytest
    [trestle-remote-run] exit=0 command wall=111.3s

pytest was not installed, nothing ran, and the footer said `exit=0 command` — because `tail`
exited 0. The engine was not wrong; it reported the status it was given. Always `set -o
pipefail`, or capture the real status explicitly:

    set -o pipefail
    pytest ... > /tmp/out.txt 2>&1; rc=$?; tail -4 /tmp/out.txt; echo "RC=$rc"; exit $rc

This is the same failure this repo keeps finding in other clothes: an absence rendered as a
success. The remote ran nothing and reported cleanly.

Also note `objects_sent=0` on a repeat run — the mirror persists, so a second run is cheap
even when the first is slow. A slow first run is not evidence the offload is a bad trade.

Hosts are shared. A run can sit waiting on another repo's mirror lock (116 after
`--lock-wait-s`), and a host busy with someone else's job is slower than its idle benchmark —
which is a reason to re-measure rather than to trust a stale number.

Source: `runbooks/offload-instructions-for-repos.md` in the trestle checkout.

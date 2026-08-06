# Release order — session F

This branch bumps six packages in one release-prep pass. `publish-pypi.yml` is
tag-triggered, one package per tag pattern (`v*`, `dataflow-v*`, `kaizen-v*`,
`nexus-v*`, `kaizen-agents-v*`, `ml-v*`, `mcp-v*`, plus `pact-v*`/`align-v*`
for packages not touched here). Each tag's job graph is scoped to that one
package — there is **no cross-package ordering logic** in the workflow at
all; publish order is entirely operator-manual (or `workflow_dispatch`-manual)
and CI-unenforced. This note exists so that ordering constraint survives
outside the conversation that derived it.

## 1. Required publish sequence

| Step | Package          | Tag                     | Why this position                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---- | ---------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | kailash-mcp      | `mcp-v0.5.0`            | Nothing in this release depends on it publishing after anything else. Must go first because step 2 depends on it.                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2    | kailash-kaizen   | `kaizen-v2.46.0`        | `packages/kailash-kaizen/pyproject.toml:46` declares `kailash-mcp>=0.5.0` as a mandatory (non-extra) dependency. If `kaizen-v2.46.0` is tagged before `mcp-v0.5.0` publishes, `pip install kailash-kaizen==2.46.0` fails to resolve — no matching distribution for `kailash-mcp>=0.5.0`.                                                                                                                                                                                                                                                           |
| 3    | kaizen-agents    | `kaizen-agents-v0.13.0` | `packages/kaizen-agents/pyproject.toml:62` declares `kailash-kaizen>=2.46.0` as a mandatory dependency. Same failure mode as step 2 if published early.                                                                                                                                                                                                                                                                                                                                                                                            |
| 4    | kailash-dataflow | `dataflow-v2.20.0`      | No cross-dependency on any other package bumped in this release. May publish any time after step 1 (or even before it — included here for a single linear sequence, not because ordering is required).                                                                                                                                                                                                                                                                                                                                             |
| 4    | kailash-nexus    | `nexus-v2.16.0`         | Same as dataflow — no cross-dependency on the other five. Steps 4 (dataflow/nexus/ml) may run in any relative order to each other.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 4    | kailash-ml       | `ml-v2.2.3`             | Same as dataflow/nexus — no cross-dependency on the other five.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 5    | kailash (core)   | `v2.63.0`               | Last, for two independent reasons: (a) nothing in this release requires `kailash>=2.63.0` — the highest existing floor on core is `packages/kailash-nexus/pyproject.toml:39`'s `kailash>=2.62.0`, already satisfied by the currently-published core version, so core has no forward pressure to publish early; (b) publishing last leaves room for the deferred floor-raise commit (§2) to land and be verified before the core tag is cut, so `v2.63.0` ships with corrected floors from day one instead of needing an immediate follow-up patch. |

Steps 4's three packages (dataflow/nexus/ml) have no ordering constraint
relative to each other or to step 1 — they could in principle run in
parallel with kailash-mcp. They are listed after kaizen-agents here only to
keep the table linear; the load-bearing constraint is 1 → 2 → 3, and 5 last.

## 2. Deferred floor bumps — required release step, not optional

Root `pyproject.toml:165-170` (the `dataflow`/`nexus`/`kaizen`/`pact`/`ml`/`align`
extras block) and `pyproject.toml:265-270` (the `all` aggregate extra) were
deliberately **left at their pre-release, currently-published floors** in
this release-prep commit:

```
dataflow = ["kailash-dataflow>=2.19.1"]   # pyproject.toml:165
nexus    = ["kailash-nexus>=2.15.0"]      # pyproject.toml:166
kaizen   = ["kailash-kaizen>=2.45.0", "kaizen-agents>=0.12.0"]  # pyproject.toml:167
ml       = ["kailash-ml>=2.2.2"]          # pyproject.toml:169
```

This is a **known, deliberate gap** in this release, not an oversight — the
inline comment at `pyproject.toml:138-164` records why, and states the
mechanism precisely: `pyproject.toml`'s `[tool.uv.sources]` block
(`pyproject.toml:346-354`) is a **uv-specific extension**, not PEP 621
`[project]` metadata — `pip` never reads it, and it only governs how
`uv sync`/`uv pip install -e .` resolves THIS repo's own local checkout.
It has no effect on the PUBLISHED `kailash` wheel; a real
`pip install kailash[kaizen]` resolves purely against what these extras
declare in the published metadata. Raising these floors in the SAME
commit as the version bumps would have meant: the moment `kailash` core
published with a `kaizen>=2.46.0` floor already in its extras, resolving
`kailash[kaizen]` would depend on `kaizen-v2.46.0` already being live —
collapsing the ordering risk from "one mandatory dependency in one
package" (§1, accepted) into "six packages' publish timing coupled
through the core package's own extras metadata" (not accepted at this
scope). No `.github/workflows/*.yml` job currently installs any of
these extras (confirmed by grep across the workflow directory), so this
is a publish-boundary / real-user-install risk, not a CI-job failure —
CI going green proves nothing about whether this gap exists.

**Required follow-up commit**, timed strictly between step 3 and step 5
above (after `dataflow`/`nexus`/`kaizen`/`kaizen-agents`/`ml` have actually
published, before the `kailash` core tag is cut):

```
dataflow = ["kailash-dataflow>=2.20.0"]
nexus    = ["kailash-nexus>=2.16.0"]
kaizen   = ["kailash-kaizen>=2.46.0", "kaizen-agents>=0.13.0"]
ml       = ["kailash-ml>=2.2.3"]
```

and the matching four lines inside the `all` aggregate extra
(`pyproject.toml:265-270`: `kailash-dataflow[security,monitoring,api]`,
`kailash-nexus`, `kailash-kaizen[...]`, `kaizen-agents`, `kailash-ml`).

Without this follow-up, an operator who runs `pip install --upgrade
kailash[kaizen]` (or any extra install, not just a bare `pip install
kailash --upgrade`) after this release still resolves to a `kailash-kaizen`
that can satisfy `>=2.45.0` — including 2.45.0 itself, which lacks the
credential-scrub fixes this release exists to ship. The fix would be
published and not delivered to that install path.

## 3. Same-class residual — out of scope for this release, recorded for follow-up

`kailash-ml` (`packages/kailash-ml/pyproject.toml:144`, plus the
`kaizen-judges` and `kaizen-observability` optional-extras copies at
`:151`/`:152`), `kailash-pact` (`packages/kailash-pact/pyproject.toml:52`),
and `kailash-align` (`packages/kailash-align/pyproject.toml:30`) each pin
`kailash-kaizen>=2.7.5` — a floor low enough to be satisfied by a
`kailash-kaizen` that predates every fix in this release by many versions.

**Disposition: out of scope for this release, in scope for a follow-up.**
None of these three packages are version-bumped or otherwise touched on
this branch — raising their floors here would add three additional
unreleased-package tags to the publish sequence in §1 for no benefit these
three packages' own users would see today (they are not being published in
this release, so the floor-raise itself cannot ship until they are). The
correct follow-up is a dedicated PR that bumps these three floors to
`kailash-kaizen>=2.46.0`, sequenced after step 2 (§1) publishes, independent
of and not blocking this release.

## 4. Pre-tag verification — every declared floor is satisfiable from PyPI

Run this before cutting `v2.63.0` (or any tag in §1), to confirm every
package this release depends on with a floor referencing this branch's own
work is actually resolvable from the live PyPI index at that moment.

**Walked, not just written** (`user-flow-validation.md` MUST-1/2). The first
version of this script used `declare -A` (an associative array), which
requires bash 4+; the operator-default `bash` on macOS is 3.2.57 (Apple ships
3.2 for licensing reasons, not 4+), so the script never ran at all — it
failed at the array declaration with `unbound variable` before reaching any
PyPI check. A script that cannot execute on the platform its own operator
runs is worse than no script: it would have been trusted and never actually
gated anything. Rewritten below to use only bash-3.2-portable indexed arrays.
Walking it also surfaced a second defect: on a network failure or an
unpublished/misspelled package name, the original piped `curl | python3 -c
'json.load(...)'` failed with a raw Python traceback (`JSONDecodeError`) —
technically non-fatal (the `||` in the calling loop still caught it and
correctly set a failing exit status) but useless as operator-facing output.
Rewritten to fail with a clean, actionable `FAIL:` line instead.

```bash
#!/usr/bin/env bash
# Usage: run from the repo root, any time before cutting a tag in the §1
# sequence. Exits non-zero (and prints every violation) if any declared
# floor exceeds what is currently live on PyPI — i.e. the package that
# declares the floor is not yet safe to publish.
#
# Portable to bash 3.2 (the macOS system default — no Homebrew bash
# required): uses plain indexed arrays, never `declare -A` (bash 4+ only).
#
# NOTE: this does NOT parse pyproject.toml. FLOOR_FILES/FLOOR_PKGS/
# FLOOR_VERSIONS below is a manually maintained mirror of the floors
# declared in the named files — extend it by hand when a new floor is
# added, keeping it in sync. A floor with an extras marker in the source
# (e.g. `kailash-kaizen[providers-azure,...]>=X`) still resolves here by
# PACKAGE NAME ONLY (`kailash-kaizen`) and FLOOR VERSION ONLY (`X`) — strip
# the bracketed extras list yourself when adding an entry; there is no
# TOML/extras parser here to do it for you.
set -euo pipefail

FLOOR_FILES=(
  "packages/kailash-kaizen/pyproject.toml"
  "packages/kaizen-agents/pyproject.toml"
)
FLOOR_PKGS=(
  "kailash-mcp"
  "kailash-kaizen"
)
FLOOR_VERSIONS=(
  "0.5.0"
  "2.46.0"
)

check_floor() {
  local file="$1" pkg="$2" floor="$3"
  local response live

  response=$(curl -fsSL "https://pypi.org/pypi/${pkg}/json" 2>&1) || {
    echo "FAIL: ${file} declares ${pkg}>=${floor} — PyPI request failed (network error or package not found): ${response}"
    return 1
  }

  live=$(printf '%s' "$response" | python3 -c '
import json, sys
print(json.load(sys.stdin)["info"]["version"])
' 2>&1) || {
    echo "FAIL: ${file} declares ${pkg}>=${floor} — could not parse PyPI response (unexpected JSON shape or empty body)"
    return 1
  }

  python3 -c "
from packaging.version import Version
import sys
live_v, floor_v = Version('$live'), Version('$floor')
if live_v < floor_v:
    print(f'FAIL: $file declares $pkg>=$floor, but PyPI live=$live')
    sys.exit(1)
print(f'OK:   $file declares $pkg>=$floor, PyPI live=$live satisfies it')
"
}

status=0
for i in "${!FLOOR_PKGS[@]}"; do
  check_floor "${FLOOR_FILES[$i]}" "${FLOOR_PKGS[$i]}" "${FLOOR_VERSIONS[$i]}" || status=1
done
exit "$status"
```

**Walk receipt** (run from the repo root, `bash --version` confirmed
`GNU bash, version 3.2.57(1)-release`, the same default an operator on this
platform gets):

```
$ bash verify-floors.sh
FAIL: packages/kailash-kaizen/pyproject.toml declares kailash-mcp>=0.5.0, but PyPI live=0.4.3
FAIL: packages/kaizen-agents/pyproject.toml declares kailash-kaizen>=2.46.0, but PyPI live=2.45.0
$ echo $?
1
```

This is the CORRECT result today, not a bug: `kailash-mcp` 0.5.0 and
`kailash-kaizen` 2.46.0 are this branch's own unpublished bumps (§1), so the
script finding them unsatisfiable is it working — it would have blocked
tagging `kaizen-v2.46.0` right now, which is exactly the unsafe tag §1
exists to prevent. It is expected to flip to two clean `OK:` lines and exit
0 only after `mcp-v0.5.0` and `kaizen-v2.46.0` are actually published, in
that order.

Two additional scenarios were walked to confirm the error-handling fix:
a deliberately-misspelled package name produced a single clean
`FAIL: ... PyPI request failed (network error or package not found): curl:
(56) The requested URL returned error: 404` line (no raw traceback) and
still correctly continued to check the remaining entries; and lowering a
floor to a currently-satisfiable value produced `OK: ... PyPI live=0.4.3
satisfies it` and exit `0`, confirming the pass path is equally correct.

Extend `FLOOR_FILES`/`FLOOR_PKGS`/`FLOOR_VERSIONS` (three parallel arrays,
same index) with the four entries from §2's deferred commit
(`kailash-dataflow`, `kailash-nexus`, `kailash-kaizen`, `kaizen-agents`,
`kailash-ml` against the root `pyproject.toml` extras) once that follow-up
commit lands, so the same script also gates the `kailash` core tag.

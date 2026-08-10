# PR body draft — `fix/issue-1720-forest-drain`

> **SUPERSEDED by `pr-body-v2.md`. MUST NOT be opened as written.**
>
> Its § Verification asserts "Convergence was reached by rotated-lens redteam rounds" —
> a convergence that was never reached. It also gates on a "round 3" that has since been
> superseded, carries counts from an earlier HEAD, and lists an incomplete set of filed
> issues.
>
> Kept, not deleted: this is the record of what was nearly published, and the claim it
> makes is the reason the replacement leads with "NOT converged. Do not merge on the
> strength of this description alone."

> DRAFT. Do not open the PR until (a) round 3 reaches convergence, and (b) the push
> succeeds. Numbers below are orchestrator-verified; re-derive before opening — several
> will have moved.

---

## Summary

Closes the #1720 forest: a set of security and correctness defects across the core SDK,
Nexus, Kaizen, kaizen-agents and the MCP server, plus the release anchoring for seven
packages.

The headline is not any single fix. It is that **every real finding in this work was a
non-discriminating instrument** — a check that returned the same answer whether or not the
thing it measured was true. That shaped how the work was verified, and it is the part worth
carrying forward.

## What changed, by user-visible effect

**A workflow no longer behaves differently depending on which channel invoked it.** Six entry
points each rebuilt the same parameter-envelope expression by hand and had drifted, so the
same workflow succeeded on one channel and returned an opaque 500 on another. They now share
one binder. The SDK's own documented endpoint example — `app._execute_workflow(name, body)`
from the Nexus API patterns — raised `NameError` for any workflow reading `parameters.get(...)`;
it works now.

**A gated MCP tool is no longer visible to an unauthenticated client on the default
transport.** The default stdio path served FastMCP's own registry, which had never been taught
the gated projection, so a permission-gated tool disclosed its full input schema and a
`disable_tool()`'d tool could still be listed and invoked. Scoped honestly: this was
disclosure plus a `disable_tool` bypass — invocation authentication always held.

**Rate limiting does what its documentation says.** `rate_limit=None` is documented as
unlimited and was an unconditional 500 on every request. The IP-tracking map was unbounded;
its first fix replaced the leak with a 7,170x per-request CPU amplification that stalled the
event loop process-wide, so the eviction is now O(1) amortised with a cost assertion pinned as
a self-normalising ratio rather than a wall-clock threshold.

**Credentials survive fewer paths.** A password containing a comma leaked in full through both
scrub presets. Several tool error sinks echoed model-supplied operands raw. Skill discovery
widened to every registered agent when caller identity was partially supplied.

## Release

Seven packages, version-anchored atomically (0 split state, re-derived with `tomllib`):
core 2.63.0, kaizen 2.46.0, kaizen-agents 0.13.0, dataflow 2.20.0, nexus 2.16.0, ml 2.2.3,
mcp 0.5.0. `kailash-mcp` was missing from the prior session's release set entirely and carries
this branch's tool-gating fixes.

**The publish order is load-bearing and CI-unenforced:**
`mcp 0.5.0 → kaizen 2.46.0 → kaizen-agents 0.13.0 → dataflow/nexus/ml → kailash 2.63.0 last`.
kaizen floors `kailash-mcp>=0.5.0`, so tagging out of order fails to resolve. Root extras
floors must be raised between the sub-package publishes and the core tag.

**Known and deliberate:** breaking changes ship in MINOR bumps while the changelogs claim
semver adherence. Pre-existing project-wide pattern, not introduced here; flagged for a
separate versioning decision rather than folded into this release.

## Verification

Convergence was reached by rotated-lens redteam rounds, not by a single pass. Round 1 found
2 HIGH + 2 release-blocking; round 2 found 7 HIGH + 6 MEDIUM; round 3 rotated to cross-lane
composition and to the fixes themselves as attack surface.

**A substantial share of this branch's defects were introduced by corrections that looked
right** — `sweep-2026-08-06.md` §5-A records five as of round 1, and round 2 added more (the
envelope fix introduced a cross-channel parity break; the unbounded-map fix introduced the CPU
amplification; the WARN-predicate fix matched on a bare type name; the AST guard was blind to
half the bug class it was built for). That rate is why the rounds kept going and why each
round's instrument was rotated rather than repeated.

> Deliberately not stated as a single total: no one has tallied it rigorously, and a precise
> count here would be exactly the unverified durable claim this branch keeps catching. The
> five is cited because it is written down; the rest are named individually because they are
> checkable. If a number is wanted for the release notes, derive it from the round-1/2/3
> findings files first.

Orchestrator-verified suite counts (not lane-reported):

| Tree                     | Result                                      |
| ------------------------ | ------------------------------------------- |
| root `tests/unit/`       | 4798 passed, 4 skipped                      |
| root `tests/regression/` | 1566 passed, 2 skipped, 22 infra deselected |
| `tests/unit/mcp_server/` | 645 passed                                  |
| `kailash-mcp` regression | 515 passed, 1 skipped                       |

## Related issues

Fixes #1720. Closes #1996 (delivered by `45ccac417`). Filed during this work: #2001
(bash_tool raw `command` echo), #2002 (root `tests/regression/` has no CI — 1,564 of 1,566
tests never run).

Carried, not closed: #1970, #1971, #1972, #1974, #1981, #1995, #1997, #1998, #2000.

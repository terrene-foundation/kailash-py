# /sweep — Management Decision Report (cont-20)

main `d5b8fe390` · **28 PRs merged across cont-18/19/20** · **6 packages released to PyPI** ·
45 open issues · 2 open PRs

Every "complete" claim below cites a durable receipt (merge SHA, PyPI version, verified command
output). No self-attested completion.

---

## 1. Completion status

### The release shipped — that was the outstanding risk, and it is closed

Six packages published to production PyPI and verified installable from clean venvs. **Zero
drift across all nine packages** (three were already in sync).

| package          | PyPI       | GH Release |
| ---------------- | ---------- | ---------- |
| kailash          | **2.63.0** | ✅         |
| kailash-dataflow | **2.20.0** | ✅         |
| kailash-ml       | **2.2.3**  | ✅         |
| kaizen-agents    | **0.13.0** | ✅         |
| kailash-kaizen   | **2.46.0** | ✅         |
| kailash-nexus    | **2.16.0** | ✅         |

Every security fix from the last three sessions is now installable: credential redaction at
every log sink, API-key auth that could not authenticate anyone, the session-ownership IDOR,
the SSRF guard consolidation, and the mock embedder that shipped as a production default.

**The publish-order constraint held, verified end to end rather than assumed:** a clean
`pip install kailash-kaizen==2.46.0` from production resolved `kailash 2.63.0`, imported
`network_guard`, and the BREAKING change failed closed —
`ConfigurationError: VectorMemory: 'embedding_fn' is required`.

### Is the product complete and visible?

**Visible now, in a way it was not 48 hours ago.** Before this block, PyPI carried none of the
auth, redaction, or SSRF work; `main` was red; and a green CI run carried almost no information
about the integration, kaizen, or root regression suites. All three are now true. What remains
is a correctness backlog, not a delivery gap.

---

## 2. ETA to completion — in autonomous cycles

**~3–4 cycles** for the remaining BUG + INVEST-NOW set. Down from 4–6 at cont-18: the release
is done, the CI chain is closed, and the auth surface has landed.

| bucket                                                                       | items   | est. cycles          |
| ---------------------------------------------------------------------------- | ------- | -------------------- |
| #2189 absence-rendered-as-success sweep (sibling found 22 / 3 critical)      | 1 sweep | 1–1.5                |
| Un-gated HTTP surfaces (#2141, #2142)                                        | 2       | 0.75                 |
| #2166 `check_session_access` cannot succeed — needs an authz-schema decision | 1       | 0.5 (after decision) |
| Correctness set (#2138, #2151, #2153, #2162, #2163, #2172, #2175)            | 7       | 1                    |
| Docs/claim accuracy (#2168, #2170, #2171, #2173)                             | 4       | 0.5                  |
| PR close-out (#2192, #2123)                                                  | 2       | 0.25                 |

---

## 3. Prioritized immediate queue (value-ranked)

Value anchor: the co-owner's directives this block — _"root cause long term fix please"_,
_"approved"_, _"proceed"_ — i.e. close real defect classes at the root, and ship.

1. **#2189 — sweep for "an absence rendered as a success."** A sibling SDK swept this exact
   class and found **22 instances, three critical, all in code that looked correct on review**,
   and the filer notes several shapes are _sharper_ in Python than in a typed language. This
   session independently found the same class ~12 times without looking for it systematically.
   **Highest expected yield of anything open.**
2. **#2141 / #2142 — un-gated HTTP surfaces.** #2141 is the sharper: an unauthenticated
   `DELETE /api/runs/{id}`, and `--auth` unlocks a `0.0.0.0` bind while installing nothing —
   the flag that advertises security widens exposure.
3. **#2166 — `MiddlewareAccessControlManager.check_session_access` can never succeed.** Passes
   three kwargs `PermissionCheckNode` does not declare, omits the required `operation`, misreads
   the return shape. Blocked on an authorization-schema decision; **fixing it blind would ship a
   WRONG authz check in place of a loud failure.**
4. **#2192 — recovered work, needs a red established.** Its 6 tests pass but nobody has shown
   they RED against unfixed code.
5. **#2170 — docstring corrections only.** The behaviour decision is recorded and settled; what
   remains is making the documentation match it.

---

## 4. Deferred-quality backlog

**Empty** — `gh issue list --label deferred-quality` returns nothing. Sweep-N has nothing to
fire on. Several items are deferred by judgment with runtime-safety proofs (#2146, #2178, #2181)
and follow `zero-tolerance.md` Rule 1b's four conditions rather than the label. **Recommendation:
leave as-is** — relabelling would be bookkeeping, not value.

---

## 5. Decision points for the co-owner

**D1 — #2180: wire `tests/integration/` into CI (131 files).** Currently invoked by no workflow;
fourth instance of the #2038/#2074 bug class. _Pro:_ closes a tier that is green-by-absence.
_Con:_ real recurring CI cost and job wall-clock, and a baseline pass/fail count should be
recorded before wiring so pre-existing failures surface as a number rather than a wall of red.
**Recommendation: wire it, with the baseline captured first.** It is the last known
green-by-absence surface.

**D2 — #2166 authorization schema.** The manager cannot work; the fix requires deciding what the
(actor, action, subject) triple should be. _Pro of deciding now:_ unblocks a real authz path.
_Con:_ it is a design decision, and an agent guessing it would ship a plausible-looking wrong
check — worse than the current loud failure. **Recommendation: you specify the intended schema,
then it is a single shard.**

**D3 — 165 historical local branches** (oldest 2025-06-09), unmerged, unpushed. Not this
session's work. _Pro of pruning:_ `git branch` becomes usable again. _Con:_ some may hold
unlanded work nobody has audited; deleting them is irreversible without reflog. **Recommendation:
leave them. Audit as a separate, explicitly-scoped task** — this sweep did not examine their
contents and will not claim they are disposable.

---

## 6. Recommendation — next steps, for ratification

1. **Run the #2189 sweep** — highest expected yield, and the class is already demonstrated in
   this codebase.
2. **Close out #2192** (establish the red, merge) and **#2123** (loom sync, 116 behind).
3. **Then #2141/#2142**, the last un-gated HTTP surfaces.
4. **D1 and D2 need your call**; nothing else is blocked on you.

**The pattern worth carrying:** every product defect this block found, and every one of my own
dozen instrument failures, share one shape — **a control that reports success without
discriminating.** A sanitizer that renders but never withholds. A fingerprint that does not
conceal. An embedder that does not embed, documented and demoed as if it did. A scanner alert
going green because a line moved. Two duplicate function bodies held in sync by nothing. And on
my side: an empty capture, a truncated diff, a clean worktree, a rootdir that swapped the code
under test, and a hash of nothing that printed as "IDENTICAL".

**None are tested-path defects. All ship green.** Ask of every check, before citing it: _what
result would this produce if the thing it checks were false?_ If the answer is "the same one",
it is not evidence.

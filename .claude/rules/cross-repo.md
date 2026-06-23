---
priority: 10
scope: path-scoped
paths:
  - ".claude/**"
  - "sync-manifest.yaml"
  - "**/*.mjs"
  - "**/*.js"
---

# Cross-Repo Target Resolution

loom and its tooling coordinate across sibling repos — BUILD repos, USE
templates, the loom self-checkout, atelier, downstream consumers. Historically
every tool found a linked repo POSITIONALLY (`path.join(HOME, "repos", <name>)`,
`../<name>`, `~/repos/loom/<tmpl>`). That positional assumption breaks the
moment an operator lays repos out differently AND re-creates the issue
#255/#252 disclosure class whenever a repo registry is embedded inline in a
synced artifact. The shared resolver at `bin/lib/loom-links.mjs` is the
canonical NAME→location binding; positional guessing is the fragility it
removes.

## MUST Rules

### 1. Cross-Repo Tooling MUST Resolve Targets Via The Linkage Resolver

Any tool, hook, agent, or script that needs the on-disk location of another
repo MUST resolve it through `bin/lib/loom-links.mjs::resolveRepo(<logical-key>)`
(or `resolveAll` / `resolveShard`), never by constructing a positional path
(`~/repos/<name>`, `../<name>`, `path.join(HOME, "repos", <name>)`,
`dirname(cwd)/<name>`). An undeclared linkage is an explicit not-found
(`LinkError` / `{skipped, reason}` under `require:false`) — NOT a prompt to
fall back to a positional guess.

```js
// DO — resolve through the canonical NAME→location binding
import { resolveRepo } from "../lib/loom-links.mjs";
const { value: buildPath } = resolveRepo("build.py"); // throws LinkError if undeclared
// require:false for survey/fan-out callers that tolerate gaps:
const r = resolveRepo("use-template.claude-rs", { require: false });
if (r.skipped) {
  /* explicit not-found — surface the reason, do NOT positional-guess */
}

// DO NOT — positional construction
const buildPath = path.join(process.env.HOME, "repos", "kailash-py");
const tmpl = path.join(path.dirname(cwd), "kailash-coc-claude-rs");
```

**Why:** A positional path is correct only on the layout the author happened
to have; every other operator's tooling silently resolves the wrong directory
(or a non-existent one) with no loud failure. Routing every NAME→path through
one resolver makes the binding declarative, auditable, and operator-portable —
and keeps the repo registry out of synced artifacts (the #255/#252 fence).

### 2. Orchestration Roots Are EXEMPT From The Positional-Guess Prohibition, Not From The Resolver

At the `~/repos/` orchestration root and inside `loom/` itself, cross-repo
coordination is the POINT (`/sync`, `/sync-to-build`, `/inspect`, `/repos`).
Rule 1 does NOT forbid these operations — it forbids the positional _guess_.
Orchestration-root tooling MUST still resolve targets via the resolver; it is
exempt only from the "don't reach into another repo" framing of
`repo-scope-discipline.md`, not from the NAME→path binding.

```js
// DO — orchestration root: cross-repo IS the purpose, still resolver-driven
for (const [key, r] of resolveAll()) {
  if (r.kind === "path") inspectRepo(r.value); // /inspect, /repos, /sync
}

// DO NOT — orchestration root treated as license to hardcode the layout
const repos = ["kailash-py", "kailash-rs"].map((n) =>
  path.join(process.env.HOME, "repos", n),
); // positional guess even at the root is still BLOCKED
```

**Why:** The exemption is for the _operation_ (an in-repo session must not
reach cross-repo; the root must), not for the _resolution mechanism_. A
hardcoded layout at the root is just as operator-fragile as one in a hook —
the resolver is the single binding everywhere; the orchestration carve-out
only lifts the scope boundary, never the positional-guess prohibition.

## Ecosystem-Scoped Remote Links (design contract)

The resolver's NAME→location binding (Rule 1) is **per-operator-local** — it maps a
logical key to wherever THIS operator checked the repo out. The multi-ecosystem model adds a
second axis: the NAME→**remote** binding is **per-ecosystem**. Canon's `build.py` and a client
fork's `build.py` are the SAME logical key resolving to DIFFERENT remotes (canon's
`kailash-py` vs the fork's own copy that syncs upstream from canon). The intended composition
is **ecosystem-remote ⊕ operator-local**: the ecosystem layer fixes which remote a key points
at; the operator layer fixes where on THIS machine it is checked out. An operator working in a
client fork resolves keys against the fork's remote registry, never canon's.

This is the **design contract**, not yet the implementation. The two-layer `loom-links.mjs`
(ecosystem-remote layer + operator-local layer) and the active pull-merge-at-start are a
separate build (the ecosystem-relative parameterization primitive) — deferred, not shipped
here. Today's resolver remains single-layer (operator-local only); this subsection records the
direction so the single-layer code is understood as the canon-only special case of the
two-layer model, not the final shape.

**Why:** Without the ecosystem-remote axis, a client fork's tooling resolves a logical key to
CANON's remote — pulling canon's code into the fork instead of the fork's own upstream-syncing
copy, silently collapsing the ecosystem boundary the fork model depends on.

## Canonical Sublayout (Recommended — F61)

The recommended on-disk sublayout for a fresh operator workstation is
`~/repos/kailash/{build,use}/<slug>`: BUILD repos under
`~/repos/kailash/build/{py,rs,prism}` and USE templates under
`~/repos/kailash/use/{py,rs,rb,claude-py,claude-rs,claude-rb}`; `loom` and
`atelier` remain peer entries at `~/repos/{loom,atelier}`. This is a HINT,
NOT a MUST clause — the resolver IS the canonical NAME→location binding
(Rule 1) and the sublayout is operator-portable. Pre-existing operators on
other layouts (flat `~/repos/<slug>`, nested `~/repos/loom/<slug>`, or any
declared `loom-links.local.json` mapping) remain fully supported. The
canonical sublayout's value is institutional: a fresh operator copying the
example config gets a coherent default and a sibling operator joining the
same machine finds repos in a predictable place — without changing what the
resolver, validators, or sync tooling actually do at runtime. The committed
example at `.claude/bin/loom-links.local.example.json` carries the canonical
sublayout as synthetic example tokens (`example/build/py`, `example/use/py`,
etc.) so the disclosure-scrub fence is unaffected.

```text
# DO — fresh operator workstation uses the canonical sublayout
~/repos/kailash/build/py         (BUILD: kailash-py)
~/repos/kailash/build/rs         (BUILD: kailash-rs)
~/repos/kailash/use/py           (USE-template: kailash-coc-py)
~/repos/kailash/use/rs           (USE-template: kailash-coc-rs)
~/repos/loom                     (loom self-checkout)
~/repos/atelier                  (CC + CO authority)

# DO — pre-existing operators on other layouts proceed unchanged
~/repos/kailash-py               (flat layout — declare in loom-links.local.json)
~/repos/loom/kailash-py          (nested layout — declare via absolute path)
```

**Why:** The canonical sublayout is the suggested on-disk REALIZATION of the
logical key namespace at `artifact-flow.md` § "Repo Classes Map 1:1 To
Resolver Logical Keys" — a default that encodes the BUILD-vs-USE class
distinction directly in the path, with `loom`/`atelier` as peer roots (not
nested under `kailash/`). Without it, every fresh operator invents an ad-hoc
layout and sibling operators on the same machine end up grepping each other's
resolver configs; the hint costs zero structural enforcement, buys consistency
across fresh workstations, and existing operators on other layouts pay nothing
(the resolver remains layout-agnostic and any operator-local layout stays
fully supported via `loom-links.local.json`).

## MUST NOT

- Embed a repo registry (paths, org slugs, hostnames) inline in any synced
  `.claude/` artifact instead of routing through the gitignored resolver
  config.

**Why:** An inline registry in a synced file propagates to 30+ downstream
consumers and is correlatable across all of them — the exact #255/#252
disclosure class the resolver's gitignored-config design fences.

- Add a positional fallback "for robustness" when the resolver returns
  not-configured / unknown-key.

**Why:** A positional fallback re-introduces the bug the resolver removes; an
undeclared linkage MUST fail loud (typed `LinkError`) so the operator declares
it once, not silently resolve a wrong directory forever.

Origin: 2026-05-17 — user-defined repo-linkage system (Shards 1–3,
`feat/loom-links-resolver`). Resolver + schema + bootstrap landed Shard 1;
the one real positional code site (`hooks/lib/template-resolver.js`) migrated
Shard 2; spec/doc/rule alignment Shard 3. Journal `0086-DECISION-user-defined-repo-linkage-system-2026-05-17.md`.
Extended 2026-05-28 (F61 wave, journal/0168): § "Canonical Sublayout
(Recommended — F61)" added as a non-MUST hint encoding the BUILD-vs-USE
class distinction in `~/repos/kailash/{build,use}/<slug>` for fresh
operators; mirror clause in `artifact-flow.md` § "Repo Classes Map 1:1 To
Resolver Logical Keys"; canonical-sublayout block added to the committed
example schema `.claude/bin/loom-links.local.example.json` `_README`.

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

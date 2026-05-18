# User-Defined Repo Linkages

loom coordinates across sibling repos — BUILD repos, USE templates, the loom
self-checkout, atelier, downstream consumers. This guide explains the shared
linkage resolver that owns the NAME→on-disk-location binding, why it replaced
positional path guessing, and how to configure it.

## Why — Positional Fragility + Disclosure

Historically every loom tool resolved a linked repo POSITIONALLY:
`path.join(HOME, "repos", <name>)`, `../<name>`, `~/repos/loom/<tmpl>`. Two
problems compounded:

1. **Operator fragility.** A positional path is correct only on the exact
   layout the author happened to have. Any operator with a different layout
   gets the wrong directory (or a non-existent one) with no loud failure —
   the tool silently resolves garbage.
2. **Disclosure (#255 / #252 class).** When a repo registry is embedded
   inline in a synced `.claude/` artifact, it propagates to 30+ downstream
   consumers and is correlatable across all of them.

`bin/lib/loom-links.mjs` is the general fix: one shared resolver every
linkage-aware tool reads from, with the real registry in a gitignored
operator-local config — zero embedded paths in any synced file.

## The Config File

| File                                | Status                         |
| ----------------------------------- | ------------------------------ |
| `bin/loom-links.local.json`         | operator-local, **gitignored** |
| `bin/loom-links.local.example.json` | committed schema (synthetic)   |
| `$LOOM_LINKS_CONFIG`                | absolute-path override         |

Resolution precedence (NO silent positional fallback — ever):

1. `$LOOM_LINKS_CONFIG` (absolute path) — highest
2. `bin/loom-links.local.json` — operator-local
3. typed `LinkError("not-configured")` — fail loud (mirrors repin)

The committed `.example.json` carries only synthetic `example-*` /
`example.com` tokens (scanner-allowlisted). The real registry lives
exclusively in the gitignored `.local.json`.

## The Resolver

`bin/lib/loom-links.mjs` (ESM, zero-dependency) exports:

- `resolveRepo(key, { require })` → `{ kind: "path"|"url", value }`, or
  `{ skipped, reason }` when `require:false` and the key/config is absent.
- `resolveAll()` → `Map` of every declared link (survey / fan-out callers).
- `resolveShard(label)` → repin-compatible downstream shard paths.
- `isConfigured()` / `configPath()` — diagnostics without try/catch.
- typed `LinkError` with subtypes: `not-configured`, `unknown-key`,
  `ambiguous`, `config-error`.

Logical-key vocabulary: `build.{py,rs,prism}`,
`use-template.{py,rs,rb,claude-py,claude-rs,claude-rb}`, `loom`, `atelier`,
`downstream.<slug>`. These map 1:1 to the repo classes in
`rules/artifact-flow.md` — the manifest still owns the logical NAME and tier
membership; the resolver owns NAME→path.

An undeclared linkage is an **explicit not-found** (typed `LinkError` /
`{skipped, reason}`), NEVER a prompt to fall back to a positional guess.

## The Bootstrap Importer

`bin/loom-links-init.mjs` seeds a starter `loom-links.local.json` from the
committed schema so operators don't hand-author the file. Run it once, then
fill in real paths in the gitignored config.

## Orchestration-Root Exemption

At `~/repos/` and inside `loom/`, cross-repo coordination IS the purpose
(`/sync`, `/sync-to-build`, `/inspect`, `/repos`). `rules/cross-repo.md`
MUST-1 does NOT forbid these operations there — it forbids the positional
_guess_. Orchestration-root tooling MUST still resolve every target through
the resolver; the carve-out lifts the scope boundary for the operation, never
the NAME→path binding. (See `rules/repo-scope-discipline.md` for the
in-repo-vs-root scope rule the resolver reinforces.)

## Repin Unify + Migration

`repin-downstream.mjs` previously read its own
`bin/repin-targets.local.json`. The resolver's `shards` block now owns the
downstream-shard registry (`resolveShard`). `repin-downstream.mjs` reads
loom-links config FIRST (unified path) and falls back to the legacy
`repin-targets.local.json` only when no loom-links config exists — a
back-compat shim, still active, not removed.

**Migration**: copy your `reposRoot` + `shards` from
`repin-targets.local.json` into `loom-links.local.json`'s `shards` block, then
delete `repin-targets.local.json`. The legacy `.example` file is retained for
the shim and carries a top `_DEPRECATED` note.

## Intentionally-Positional Carve-Outs

A few paths stay positional by design — they are NOT linkages:

- The XDG-conventional template cache `~/.cache/kailash-coc/` (a cache
  location, not a repo linkage).

Everything that is a _repo linkage_ routes through the resolver.

See: `rules/cross-repo.md` (MUST clauses), `rules/artifact-flow.md`
(class→key mapping), journal
`0086-DECISION-user-defined-repo-linkage-system-2026-05-17.md`.

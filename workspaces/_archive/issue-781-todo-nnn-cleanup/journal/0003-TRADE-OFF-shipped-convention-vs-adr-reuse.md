# TRADE-OFF: `(SHIPPED-vX.Y.Z)` over `(ADR-NNN)` reuse

**Date:** 2026-05-03
**Phase:** /todos
**Status:** locked-in default, pending human approval at /todos gate

## Options weighed

| Option                                   | In-tree precedent                                    | Coverage                                                                                  | Grep clarity                                                  | Decision   |
| ---------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ---------- |
| A. `(SHIPPED-vX.Y.Z)`                    | none                                                 | full (paired version always available from git blame)                                     | unambiguous — never confused with active TODO                 | **chosen** |
| B. `(ADR-NNN)` reuse                     | 32 hits in production source                         | partial — only 1 of ~30 sampled markers has a corresponding ADR; rest fall back to delete | mixed — `ADR-NNN` reads as "see ADR" not "shipped here"       | rejected   |
| C. `(V<release>-NNN)` (brief's proposal) | none — brief incorrectly cited `(GOV-NNN)` precedent | full                                                                                      | visually collides with semver pre-release tags (`v1.0.0-rc1`) | rejected   |

## Why A wins

- **Coverage:** every Class-1a hit pairs with a release version (the brief's own example: `(v0.12.0, TODO-015)`). When a version isn't paired, the simpler disposition is to drop the parenthetical entirely (the section header survives), not invent a SHIPPED tag.
- **Reviewer cognition:** `# === Coordinated Shutdown (SHIPPED-v0.12.0) ===` reads as "this is shipped code" without context; `(ADR-NNN)` requires a roundtrip to the ADR.
- **No precedent ≠ wrong:** the codebase already mixes ~10 different `(XXX-NNN)` parenthetical conventions; adding one more keeps domain-coupling explicit (`SHIPPED` is self-describing; `GOV` would have been opaque).
- **Reversible:** if `SHIPPED-vX.Y.Z` lands wrong, a future grep-and-replace pass converts to `ADR-NNN` for any subset that warrants the upgrade.

## Risk

If the user prefers `(ADR-NNN)` reuse, T1 (the largest, first-merging shard) would need ~80 ADRs filed during /implement to back the rewrite — more administrative weight than the cleanup itself. Caught at /todos gate; trivial to swap to Option A by edit.

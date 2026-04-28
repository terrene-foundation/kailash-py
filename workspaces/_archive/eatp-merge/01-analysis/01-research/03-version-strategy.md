# Version Strategy Analysis — kailash 2.0 vs 1.x Additive

## The Decision

The brief identifies two options:

1. **kailash 2.0** — Semver major bump, clean break
2. **kailash 1.x additive** — Add `kailash.trust.*` without removing old package support

This analysis evaluates both options against the merge requirements.

---

## Option A: kailash 2.0 (Recommended)

### What Changes

- `kailash` version bumps from `1.0.0` to `2.0.0`
- `kailash.trust.*` namespace is added with all EATP + trust-plane code
- `pydantic` floor rises from `>=1.9` to `>=2.6` (breaking)
- New optional extra: `kailash[trust]` (pynacl, filelock)
- New CLI entry points: `eatp`, `attest`, `trustplane-mcp`
- kailash-kaizen bumps to `2.0.0`, drops `eatp` dependency
- Shim packages `eatp==0.3.0` and `trust-plane==0.3.0` depend on `kailash[trust]>=2.0.0`

### Why 2.0

1. **Pydantic v2 floor is a breaking change.** Kailash core currently allows `pydantic>=1.9`. EATP requires `>=2.6`. Raising the floor breaks any consumer still on Pydantic v1. This alone justifies a major bump per semver.

2. **Clean dependency signal.** Consumers see `kailash>=2.0.0` and know trust primitives are available. No guessing about feature availability in 1.x patch releases.

3. **Kaizen version alignment.** Kaizen drops `eatp` and bumps to `kailash>=2.0.0`. A major version boundary makes this dependency change unambiguous.

4. **Shim package coordination.** Shim packages declare `kailash[trust]>=2.0.0`. The major version boundary prevents installation of shims against old kailash.

5. **No backward-compatibility gymnastics.** With 2.0, the message is clear: upgrade kailash, update imports. No confusion about which 1.x version has trust.

### Risks

| Risk                                              | Severity | Mitigation                                                                                        |
| ------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------- |
| Consumers pinned to `kailash<2.0` can't get trust | LOW      | Shim packages bridge the gap during transition                                                    |
| Pydantic v1 users blocked                         | MEDIUM   | Pydantic v2 has been stable since June 2023 (3 years). V1 users should have migrated.             |
| All framework packages need version bumps         | LOW      | DataFlow/Nexus bump kailash dependency to `>=2.0.0,<3.0.0` (no code changes)                      |
| Perception of "big breaking change"               | LOW      | The breaking change is actually small (pydantic floor + new namespace). Clearly communicate this. |

### Version Matrix After 2.0

| Package            | Version | kailash Dependency                          |
| ------------------ | ------- | ------------------------------------------- |
| kailash            | 2.0.0   | —                                           |
| kailash-kaizen     | 2.0.0   | `kailash>=2.0.0,<3.0.0`                     |
| kailash-dataflow   | 1.1.1+  | `kailash>=1.0.0,<3.0.0` (widen upper bound) |
| kailash-nexus      | 1.4.3+  | `kailash>=1.0.0,<3.0.0` (widen upper bound) |
| eatp (shim)        | 0.3.0   | `kailash[trust]>=2.0.0`                     |
| trust-plane (shim) | 0.3.0   | `kailash[trust]>=2.0.0`                     |

**Note**: DataFlow and Nexus don't need major bumps — they have no code changes. Just widen their upper version bound to accept kailash 2.x.

---

## Option B: kailash 1.x Additive

### What Changes

- `kailash` bumps to `1.1.0` (minor)
- `kailash.trust.*` added as new namespace (additive, non-breaking)
- pydantic floor stays at `>=1.9` for core, `>=2.6` only behind `kailash[trust]`
- Trust code uses conditional imports to handle pydantic v1/v2

### Why NOT 1.x

1. **Pydantic version split is unworkable.** EATP code uses Pydantic v2 features. Making trust code work with Pydantic v1 requires extensive compatibility shims — effort with zero value since Pydantic v1 is effectively EOL.

2. **Confusing developer experience.** "Which 1.x has trust?" is a worse signal than "2.0 has trust."

3. **Kaizen can't cleanly drop eatp.** If kailash stays 1.x, kaizen would need to conditionally depend on eatp for kailash<1.1 and drop it for kailash>=1.1. This is fragile.

4. **Shim coordination is harder.** Shim packages can't declare `kailash>=1.1.0` as cleanly — minor version boundaries are weaker signals for packaging tools.

5. **False promise of backward compatibility.** The pydantic floor change IS breaking. Calling it 1.x pretends it isn't. Semver honesty is better.

### When 1.x Might Make Sense

Only if there were large numbers of production consumers pinned to `kailash==1.0.*` who cannot tolerate a major version bump. Given the SDK is at 1.0.0 (first release), this is unlikely.

---

## Recommendation: kailash 2.0.0

**Rationale:**

1. The pydantic floor raise is genuinely breaking — semver requires a major bump
2. Clean signal for consumers: "2.0 = trust included"
3. Simpler shim coordination
4. No compatibility gymnastics
5. Kaizen drops eatp cleanly

**Release sequence:**

1. Merge code into `src/kailash/trust/`
2. Update all imports
3. Bump kailash to 2.0.0
4. Bump kaizen to 2.0.0 (drop eatp dep)
5. Bump DataFlow/Nexus upper bounds to `<3.0.0`
6. Publish shim packages eatp==0.3.0 and trust-plane==0.3.0
7. Publish kailash==2.0.0 to PyPI
8. Publish kaizen==2.0.0 to PyPI

**Publishing order matters:**

1. kailash==2.0.0 FIRST (shims depend on it)
2. Shim packages SECOND (they depend on kailash[trust]>=2.0.0)
3. kaizen==2.0.0 THIRD (depends on kailash>=2.0.0)
4. DataFlow/Nexus minor bumps LAST (just widening upper bound)

---

## Dependency Strategy Sub-Decision

### pynacl: Always-Installed vs Optional Extra

**Recommendation: Optional extra (`kailash[trust]`)**

| Approach         | Impact                                                                                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Always-installed | Every kailash user gets pynacl (C extension, requires libsodium). Adds ~2MB and compile step on some platforms.                                                   |
| Optional extra   | `pip install kailash` stays lightweight. `pip install kailash[trust]` adds pynacl. Trust type imports work without pynacl; crypto operations raise `ImportError`. |

The optional approach is better because:

- Most kailash users use workflow orchestration, not trust primitives
- pynacl requires libsodium (C library) — heavier than pure Python deps
- Trust types (dataclasses, enums) should be importable without crypto
- Kaizen can declare `kailash[trust]` in its dependencies since it needs crypto

### filelock: Always-Installed vs Optional Extra

**Recommendation: Move to core dependencies (always-installed)**

filelock is pure Python, tiny (~20KB), and has zero dependencies. It's useful beyond trust (e.g., concurrent file access in workflows). No reason to make it optional.

---

## Impact on CLAUDE.md and Rules

After the merge, update:

1. `CLAUDE.md` — Add `kailash.trust` to the platform table
2. `.claude/rules/eatp.md` — Update scope from `packages/eatp/**` to `src/kailash/trust/**`
3. `.claude/rules/trust-plane-security.md` — Update scope from `packages/trust-plane/**` to `src/kailash/trust/plane/**`
4. `pyproject.toml` — Version bump, new extras, new entry points

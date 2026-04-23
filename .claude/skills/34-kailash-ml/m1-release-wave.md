# kailash-ml 1.0.0 M1 Release Wave

Session 2026-04-23 shipped the 7-package atomic wave for kailash-ml 1.0.0 M1 on branch `feat/kailash-ml-1.0.0-m1-foundations` (local, PyPI publish W34 pending human auth). This file captures the institutional patterns that emerged from the M10 shard cycle + W33 / W33b / W33c / post-merge reconciliation so future M-waves don't re-derive them.

## Wave Contents — 7 Packages Atomic

| Package          | From   | To     | Shard   | Tests        |
| ---------------- | ------ | ------ | ------- | ------------ |
| kailash          | 2.8.12 | 2.9.0  | W31a+d  | 33/33        |
| kailash-dataflow | 2.0.12 | 2.1.0  | W31b    | 41/41        |
| kailash-nexus    | 2.1.1  | 2.2.0  | W31c    | 27/27        |
| kailash-kaizen   | 2.11.0 | 2.12.0 | W32a    | 26/26 + 1s   |
| kailash-align    | 0.5.0  | 0.6.0  | W32b    | 20/20        |
| kailash-pact     | 0.9.0  | 0.10.0 | W32c    | 42/42        |
| kailash-ml       | 0.13.0 | 1.0.0  | W33/33b | 38 + 227 E2E |

**Totals:** 189 M10 tests + 38 W30 regression = **227 passing on feat branch**.

## Canonical `km.*` **all** — 48 Symbols (W33 + Phase-1)

Post-merge reconciliation (commit `fa300831`) finalised `src/kailash_ml/__init__.py::__all__` at **48 entries**:

- **W33 canonical 41** per `specs/ml-engines-v2.md` §15.9 — 14 lifecycle verbs + 2 discovery verbs + engines + dataclasses
- **+ erase_subject** (GDPR Decision 2, audit-row immutable sha256 fingerprint)
- **+ 7 Phase-1 adapters** (integration surfaces — see next section)

**Mechanical sweep** per `rules/orphan-detection.md` §6:

```bash
grep -c "^from .* import " src/kailash_ml/__init__.py
# must equal
python -c "import kailash_ml as km; print(len(km.__all__))"
# → 48
```

W33 original todo said 34/35; orchestrator amended at launch to 41 per spec §15.9 (specs-authority §5b); post-merge reconciliation added 7 Phase-1 adapter symbols to reach 48. See `rules/specs-authority.md` §5c on launch-time todo amendment.

## km.train + km.register — Canonical Async-Await Pipeline

Both `km.train` and `km.register` are async public-surface verbs. A pipeline is:

```python
import kailash_ml as km

async with km.track("churn-demo") as run:
    result = await km.train(df, target="churned", model="sklearn.ensemble.RandomForestClassifier")
    registered = await km.register(result, name="churn", stage="staging")
    # registered.version, registered.artifact_uris["onnx"]
```

Session 2026-04-23 commit `fdd3040e` fixed a discovered async/sync inconsistency: `km.register` was sync while `km.train` was async, breaking `await km.register(await km.train(...))` ergonomics. Both are now async; callers await both.

**DO NOT** reintroduce sync `km.register` — it breaks the "await the whole pipeline" contract and masks an orphan failure mode where a sync wrapper silently skipped ModelRegistry.initialize().

Origin: W33c follow-up, commit `fdd3040e`.

## TrainingResult.trainable Back-Reference

Commit `15033fa6` added `trainable: MLEngine` as a required field on the frozen `TrainingResult` dataclass. Missing this field was a **fake-integration failure** caught by the W33b release-blocking regression test: `km.train(...) → km.register(result, ...)` looked integrated at unit/integration tiers because each had its own tests, but the chain was broken — `km.register` couldn't resolve the trainable's engine metadata without the back-reference, falling through to a "best-guess" registry insert that silently dropped artifact URIs.

```python
# DO — result carries trainable back-reference for downstream verbs
@dataclass(frozen=True)
class TrainingResult:
    model: Any
    metrics: dict[str, float]
    device: DeviceReport
    trainable: MLEngine  # ← added W33b; required for km.register chain

# DO NOT — omit trainable, let km.register guess
# Registry insert proceeds with partial metadata; artifact_uris["onnx"] is None;
# downstream km.serve("model@v1") fails with "onnx artifact not found".
```

Origin: W33b regression, commit `15033fa6`.

## Release-Blocking README Quick Start Regression (W33b)

The W33b shard introduced a **release-blocking regression tier** above Tier 3 E2E: a test that executes the README Quick Start end-to-end against real infra AND asserts the resulting pipeline fingerprint (SHA-256 over deterministic output) matches the pinned value in `specs/ml-engines-v2.md` §16.3:

```
c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00
```

Any change that alters the Quick Start's observable behavior (different engine default, different metric rounding, different artifact format) flips the fingerprint and **blocks release**. The regression caught the `km.train → km.register` trainable-field gap that unit tests couldn't — each half worked, the chain didn't.

See `skills/16-validation-patterns/SKILL.md` § "End-to-End Pipeline Regression Above Unit/Integration" for the general pattern.

Origin: W33b shard, spec §16.3 fingerprint contract.

## MIGRATION.md Sunset Contract (W33b)

W33b landed `packages/kailash-ml/MIGRATION.md` documenting the 0.x → 1.0.0 breaking surface:

- Legacy status vocabulary (`SUCCESS`, `COMPLETED`) hard-migrated to `FINISHED` at install (Decision 1)
- Raw sklearn/torch training loops blocked via `UnsupportedTrainerError` (Decision 8)
- `ModelRegistry.register()` now returns `RegisterResult` with `artifact_uris: dict[str, str]` (was `artifact_uri: str`)
- 14 Decisions pinned 2026-04-21 (see SKILL.md § "14 Approved Decisions")

**Contract:** MIGRATION.md is the 1.x back-compat shim's operating envelope. When 2.x ships a DeprecationWarning, MIGRATION.md converts to a "deprecated-in-2.x, removed-in-3.x" table per Decision 11.

## 7 Phase-1 Integration Surfaces

The M1 wave landed 7 sibling-package integration surfaces, each exposing `ml` as a sub-namespace or callable:

| Surface                    | Owner          | Spec                                                                 |
| -------------------------- | -------------- | -------------------------------------------------------------------- |
| `kailash.ml`               | kailash 2.9.0  | `specs/kailash-core-ml-integration.md`                               |
| `kailash.observability.ml` | kailash 2.9.0  | `specs/kailash-core-ml-integration.md` § obs                         |
| `dataflow.ml`              | dataflow 2.1.0 | `specs/dataflow-ml-integration.md`                                   |
| `nexus.ml`                 | nexus 2.2.0    | `specs/nexus-ml-integration.md`                                      |
| `kaizen.ml`                | kaizen 2.12.0  | `specs/kaizen-ml-integration.md`                                     |
| `align.ml` / `rl_bridge`   | align 0.6.0    | `specs/align-ml-integration.md` + `specs/ml-rl-align-unification.md` |
| `pact.ml`                  | pact 0.10.0    | `specs/pact-ml-integration.md`                                       |

Each surface is covered by a Tier-2 wiring test per `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md`. The `kailash.ml` namespace import alone proves nothing — the wiring test imports through the facade and asserts the externally-observable effect (a training row, a served prediction, a drift report).

## 8 Institutional Patterns From This Session

1. **Parallel-burst rate limit** — cap at ≤3 Opus worktree agents per wave (`skills/30-claude-code-patterns/worktree-orchestration.md` Rule 6)
2. **Worktree base-SHA drift** — pre-flight merge-base check before launch (Rule 7)
3. **Explicit branch naming** — `feat/<shard-name>` in the prompt, never default hash (Rule 8)
4. **Spec-vs-todo amend at launch** — see `rules/specs-authority.md` §5c
5. **Release-blocking regression tier** — end-to-end above unit/integration (`skills/16-validation-patterns/SKILL.md`)
6. **Fake-integration via missing pipeline field** — TrainingResult.trainable, commit `15033fa6`
7. **Async/sync public-surface consistency** — km.train + km.register both async, commit `fdd3040e`
8. **Post-merge **all** reconciliation** — canonical 41 + 7 Phase-1 adapters = 48, commit `fa300831`

## Related

- `SKILL.md` — top-level km.\* surface + 18-engine catalog + 14 decisions
- `specs/ml-engines-v2.md` §15.9 (canonical `__all__`), §16.3 (Quick Start fingerprint)
- `rules/orphan-detection.md` — mechanical sweep discipline for the 48-symbol **all**
- `rules/specs-authority.md` §5c — launch-time todo amendment against spec truth
- `skills/30-claude-code-patterns/worktree-orchestration.md` — Rules 6/7/8 for parallel launches
- `skills/10-deployment-git/multi-package-release-wave.md` — 7-package atomic release coordination

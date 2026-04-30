# Issue #701 — `diagnose()` Family Analysis

## 1. Current entry-point + dispatch

**Public signature** — `packages/kailash-ml/src/kailash_ml/_wrappers.py:449-457`:

```python
def diagnose(
    subject: Any,
    *,
    kind: str = "auto",
    data: Any = None,
    tracker: Any = None,
    show: bool = True,
    sensitive: bool = False,
) -> Any
```

`diagnose` is exported from `kailash_ml/__init__.py:51-62` (eager import) and listed in `__all__` Group 1 (`__init__.py:674`). Re-export from `kailash_ml/diagnostics/__init__.py:142-152` covers `DLDiagnostics`, `RAGDiagnostics`, `RLDiagnostics`, `diagnose_classifier`, `diagnose_regressor`.

**Accepted `kind` literals** (`_wrappers.py:474-485`): `"auto"`, `"dl"`, `"classical_classifier"`, `"classical_regressor"`, `"clustering"`, `"rag"`, `"rl"`, `"alignment"`, `"llm"`, `"agent"`. `"classifier"` and `"regressor"` are **not** in the accepted set — `diagnose(model, kind="classifier", data=(X,y))` raises `ValueError`. `"clustering"`, `"alignment"`, `"llm"`, `"agent"` are accepted but **fall through** the dispatch (no branch handles them) → all four return `DLDiagnostics(subject, tracker=tracker)` via the `kind == "auto"` fallback at line 564 (silent mis-dispatch — second-instance violation).

**Dispatch table** (`_wrappers.py:491-512`):

| `kind`                                         | Branch                                                                       | File:line              | Drops `data=`?                   |
| ---------------------------------------------- | ---------------------------------------------------------------------------- | ---------------------- | -------------------------------- |
| `"dl"`                                         | `DLDiagnostics(subject, tracker=tracker)`                                    | `_wrappers.py:492`     | **YES** — `data` not forwarded   |
| `"rl"`                                         | `RLDiagnostics(algo=..., tracker=tracker)`                                   | `_wrappers.py:494-496` | YES                              |
| `"rag"`                                        | `RAGDiagnostics(tracker=tracker)`                                            | `_wrappers.py:498`     | YES                              |
| `"classical_classifier"`                       | `diagnose_classifier(subject, X, y, tracker=tracker)`                        | `_wrappers.py:499-505` | NO — required, raises if missing |
| `"classical_regressor"`                        | `diagnose_regressor(subject, X, y, tracker=tracker)`                         | `_wrappers.py:506-512` | NO — required                    |
| `"clustering"`/`"alignment"`/`"llm"`/`"agent"` | falls through; auto-branch returns `DLDiagnostics(subject, ...)` at line 564 | `_wrappers.py:564`     | **silent mis-dispatch**          |

## 2. DLDiagnostics surface

`DLDiagnostics.__init__` (`diagnostics/dl.py:251-322`) signature: `(model, *, dead_neuron_threshold=0.5, window=64, run_id=None, tracker=None)` — **no `data=` parameter**. Public methods that consume training input: `track_gradients()`, `track_activations()`, `track_dead_neurons()`, `record_batch(loss=..., lr=...)`, `record_epoch(...)`, `report()`, `as_lightning_callback()`, `as_transformers_callback()`, `from_training_result(result, *, tracker=None)`, `from_checkpoint()`, `checkpoint_state()`, `skip_batch()`. **None** accept a `DataLoader` — the design assumes the caller drives the loop and calls `record_batch` per batch via the context-manager pattern shown in spec § 1 (`ml-diagnostics.md:24-32`). The closest existing primitive that consumes a loader is `as_lightning_callback()` — it observes the Lightning Trainer's loader indirectly through `on_train_batch_end` hooks.

## 3. Spec authority direction

`specs/ml-diagnostics.md` § 3.1 (lines 122-133) declares `data: Optional[Union[polars.DataFrame, tuple, "torch.utils.data.DataLoader"]] = None` — DataLoader is **explicitly in the type union**.

§ 3.2 dispatch table (lines 141-152) row 6: `Trainable / torch.nn.Module / lightning.LightningModule` → `data` marked **`required`** → returns `DLDiagnostics(subject, tracker=tracker)` context manager. The spec marks `data` REQUIRED for the DL branch but the dispatch target ignores it. **Spec is internally inconsistent**: type union claims DataLoader is consumed, but the dispatched constructor ignores `data`. Spec edit needed alongside code fix per `rules/specs-authority.md` § 5/5b.

§ 3.4 (line 167): `TypeError` when subject is not dispatchable; `ValueError` when kind/model mismatch — silent-drop of unknown kwargs not contemplated.

§ 5.1 (lines 294-307): `DLDiagnostics` v0.18.0 construction adds `tracker`, `auto`, `log_every_n_steps`, `rank`, `sensitive`, `dead_neuron_threshold`, `window`, `run_id` — **no `data=`**. The 1.1.x kwargs (`title`, `n_batches`, `train_losses`, `val_losses`, `forward_returns_tuple`) are not present in any current spec section.

## 4. Silent-drop kwarg census

`diagnose(...)` signature is **fixed** (no `**kwargs`) — unknown kwargs raise `TypeError` from Python directly. Per-kwarg behavior:

| Kwarg                            | Behavior                                                      | Classification                                            |
| -------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------- |
| `data=loader` (with `kind="dl"`) | Accepted in signature, **silently ignored** — never forwarded | **Accepted-and-silent** (zero-tolerance Rule 3 violation) |
| `kind="classifier"`              | Rejected at line 486 with `ValueError` listing literals       | Accepted-and-raised                                       |
| `kind="regressor"`               | Same — rejected                                               | Accepted-and-raised                                       |
| `title=...`                      | `TypeError: unexpected keyword argument 'title'`              | Unsupported in signature                                  |
| `n_batches=...`                  | Same                                                          | Unsupported                                               |
| `train_losses=...`               | Same                                                          | Unsupported                                               |
| `val_losses=...`                 | Same                                                          | Unsupported                                               |
| `forward_returns_tuple=...`      | Same                                                          | Unsupported                                               |

**One silent-drop** (`data` on `kind="dl"`); **two pseudo-accept** (`kind="classifier"`/`"regressor"` rejected with confusing literal); **five hard-rejects** (1.1.x plotting kwargs). The brief's framing "old kwargs gone" is accurate — unsupported in signature → `TypeError`, not silent drop. The brief is also accurate that `data` is silently dropped on `kind="dl"`. The brief's framing "DLDiagnostics has no public method that consumes a DataLoader" is **correct** (verified § 2).

## 5. Recommended fix path — Path A

**Recommend Path A (additive)** per `zero-tolerance.md` Rule 3 ("silent fallback" / "fake integration via missing handoff field" — accepted kwarg with zero effect IS the failure mode). Specifically:

1. **`kind="dl"` consumes `data=`**: extend `DLDiagnostics.__init__` with `data: Optional[Any] = None` storing as `self._data = data`; add a new public method `report(data=None)` (or `evaluate(loader)`) that — when `data` is a DataLoader — drives a read-only forward pass through the loader, records `record_batch(loss=..., lr=...)` via a user-supplied loss-fn (default: subject's `.loss` if present), then returns the same dict `report()` produces today. `_wrappers.py:492` becomes `return DLDiagnostics(subject, tracker=tracker, data=data)`. Spec § 3.2 row 6 + § 5.1 amended same PR per `specs-authority.md` § 5b.
2. **Aliases**: `kind="classifier"` → `"classical_classifier"`, `kind="regressor"` → `"classical_regressor"`. Two-line addition at `_wrappers.py:474` (extend tuple) + dispatch normalization before line 491.
3. **1.1.x kwargs (`title`, `n_batches`, etc.)** — recommend Path A.b (deprecation accept): add to signature with `DeprecationWarning`. `title` → forward to `DLDiagnostics(...).set_dashboard_title(title)` (new no-op-on-base method, real on `[dl]`); `n_batches` → forward as `DLDiagnostics(..., n_batches_hint=n_batches)` for progress reporting; `train_losses`/`val_losses` → drive `record_epoch()` over the lists if `subject` is fitted; `forward_returns_tuple` → store flag for hook installation. Each emits one `DeprecationWarning` naming the canonical replacement. **Alternative (simpler)**: TypeError on these kwargs with explicit migration message in error string. Recommend the simpler form for 1.5.2 patch; revisit deprecation-accept for 1.6.0 if user pushback warrants.
4. **No silent drop on unknown kwargs**: signature is already fixed-arity → Python's native `TypeError` handles it. No `**kwargs` should be added.

**Why Path A over Path B** (purist removal): silent-drop is the Rule 3 violation — fixing the kwarg's wiring closes the bug; removing it from the signature breaks every 1.1.x→1.5.x migrating user. Spec § 3.1 already declares the kwarg accepts DataLoader; making the implementation honor the spec is structurally cleaner than amending the spec to declare a no-op kwarg.

## 6. Tier-2 regression test design

```python
# tests/regression/test_issue_701_diagnose_dl_pytorch_dataloader.py
import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import kailash_ml as km

@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_dl_pytorch_dataloader_end_to_end():
    """Issue #701: diagnose(kind='dl', data=loader) MUST consume the loader."""
    model = nn.Sequential(nn.Linear(10, 32), nn.ReLU(), nn.Linear(32, 1))
    X = torch.randn(64, 10); y = torch.randn(64, 1)
    loader = DataLoader(TensorDataset(X, y), batch_size=8)

    diag = km.diagnose(model, kind="dl", data=loader)
    report = diag.report(data=loader)  # or .evaluate(loader)

    # Loader was actually consumed end-to-end:
    assert diag.batch_count > 0, "DataLoader was silently dropped"
    assert "loss_trend" in report
    # Aliases work:
    assert km.diagnose is not None  # signature acceptance smoke
```

Plus a sibling `test_diagnose_classifier_alias_resolves` (Tier 1) asserting `kind="classifier"` accepts and dispatches identically to `kind="classical_classifier"`. Per `rules/testing.md` § "End-to-End Pipeline Regression" — DOCS-EXACT chain from spec § 3 example. Lives in `packages/kailash-ml/tests/regression/`.

## 7. Release cycle classification

**Split fix.** `data=` wiring is regression-class — closes a documented kwarg silently misbehaving (Rule 3). Ship in **1.5.2 patch** alongside #699/#701 wiring fix. Aliases (`classifier`/`regressor`) and 1.1.x kwarg deprecation-accepts are additive public-API extensions — ship in **1.6.0 minor**. Per the brief's release framing (§ "Why one workspace") this matches: 1.5.2 = regression patches, 1.6.0 = additive surface incl. deprecation adapters. The split keeps the patch surgical (one method body change + one constructor arg) and lets aliases land with sibling #700 deprecation work.

## 8. Risk register

| Risk                                                                                                                                      | Likelihood | Impact                                                           | Mitigation                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reviving `title=` for plotly figure title couples the patch to the `[dl]` extra                                                           | Med        | Med                                                              | Make `title` a no-op on base install; only effective when plotly installed; documented in CHANGELOG                                                                                                                                                                 |
| `data=` shape ambiguity (DataLoader vs `(X, y)` tuple vs polars DF) — same kwarg used by classical branches with tuple                    | High       | Med                                                              | Type-dispatch on isinstance: DataLoader for DL, tuple for classical, polars for clustering. Raise `TypeError` on shape mismatch with explicit message naming branch                                                                                                 |
| Aliases create two kwargs naming the same dispatch — drift over time                                                                      | Low        | Low                                                              | Normalize at entry (line 491): `kind = {"classifier": "classical_classifier", "regressor": "classical_regressor"}.get(kind, kind)`. Single-source dispatch downstream                                                                                               |
| `kind="clustering"`/`"alignment"`/`"llm"`/`"agent"` already silently fall through to DL — fixing #701 must not pretend these are wired    | Med        | High (silent mis-dispatch is the same Rule 3 violation at scale) | Same PR: each fall-through `kind` → raise `NotImplementedError` naming the spec section that owes the implementation OR dispatch to the correct adapter (RAG-equivalent for `llm`, etc.). Treat as same-bug-class per `autonomous-execution.md` § "Fix-Immediately" |
| 1.1.x kwarg deprecation-accept doubles the public API surface                                                                             | Med        | Med                                                              | Use TypeError-with-migration-hint in 1.5.2; revisit deprecation-accept only if user pushback is concrete                                                                                                                                                            |
| Spec § 3.2 says "data required" for DL row but spec § 4.1 example calls `DLDiagnostics(model)` with no data — internal spec inconsistency | High       | Med                                                              | Spec edit same PR per `specs-authority.md` § 5b — full-sibling sweep of `ml-diagnostics.md` + cross-refs in `ml-engines-v2.md` § 15.8                                                                                                                               |

## 9. Codify candidates

1. **"Documented kwarg with zero effect = silent fallback violation"** — already in brief § Codify Candidates (3). Promote to explicit clause in `zero-tolerance.md` Rule 3: BLOCKED pattern "kwarg accepted in signature, dropped at dispatch site". One-line extension; high reuse across SDK.
2. **"Dispatch table parity audit"** — `_wrappers.py:474-485` accepts 10 `kind` literals; `_wrappers.py:491-564` only handles 5. Mechanical sweep (`grep -E 'kind == "'`) on every multi-branch dispatch surface. Belongs in `rules/orphan-detection.md` as a sibling to § 1 (facade with no call site).
3. **"Spec type-union must match dispatch implementation"** — `data: Optional[Union[polars.DataFrame, tuple, DataLoader]]` declared but only tuple/None branches exist. Belongs in `rules/specs-authority.md` § 5b — extend the full-sibling re-derivation to require parity check between spec type-unions and code's actual `isinstance` branches.

---

**Investigation summary**: 8 file:line citations verified by direct read; brief framings confirmed accurate (silent drop on `data=` for `kind="dl"`; `kind="classifier"` rejected; 1.1.x kwargs unsupported in signature). One brief inaccuracy minor: brief says "old kwargs gone" — they were never present in the 1.5.x signature; they don't silently drop, they raise `TypeError`. Spec internally inconsistent: § 3.1 declares DataLoader in type union; dispatched constructor ignores `data`. Path A recommended; 1.5.2 + 1.6.0 split.

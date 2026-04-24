# Align × kailash-ml Integration — TRL Trainers Implement RLLifecycleProtocol

Version: 1.0.0 (draft)
Package: `kailash-align`
Target release: **kailash-align 0.5.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/align-ml-integration-draft.md`. Promotes to `specs/align-ml-integration.md` after round-3 convergence.
Supersedes: none — this spec specifies the kailash-align-side bridge to kailash-ml's `RLLifecycleProtocol`.
Parent domain: Kailash Align (LLM fine-tuning + alignment).
Sibling specs: `specs/alignment-training.md`, `specs/alignment-serving.md`, `specs/alignment-diagnostics.md`.

Origin: `ml-rl-align-unification-draft.md` — the shared `RLLifecycleProtocol` is authored on the kailash-ml side. This spec specifies the kailash-align-side concrete adapters that satisfy the Protocol so `km.rl_train(..., algo="dpo")` dispatches to a TRL-backed trainer that emits metrics to the same `km.track()` store as classical SB3 RL. Closes round-1 theme T4 (RL as a pinned orphan) + HIGH-8 (cross-SDK facet) + HIGH-11 (kaizen-align-ml tri-framework alignment).

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Four deliverables from the align side of the RL-unification bridge:

1. **Adapter classes** satisfying `kailash_ml.rl.protocols.RLLifecycleProtocol` at runtime for `DPOTrainer`, `PPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer` (the 4 TRL trainers most structurally RL-shaped). Each lives in `kailash_align.rl_bridge`.
2. **Auto-emission** of `rl.policy.kl_from_ref`, `rl.policy.loss`, `rl.reward_model.score`, `rl.reward_model.margin` (for DPO), plus alignment-specific keys under the `align.*` namespace.
3. **Telemetry parity** with classical RL — same metric names where semantically equivalent (e.g. `rl.policy.loss` means policy-gradient loss for both classical PPO and TRL PPO).
4. **Optional dependency declaration** — `[rl-bridge]` extra pulls `kailash-ml>=1.0.0`. kailash-align remains installable standalone.

### 1.2 Out of Scope (Owned By Sibling Specs)

- `RLLifecycleProtocol` definition → `ml-rl-align-unification-draft.md`.
- Classical-RL adapters (SB3, d3rlpy) → `ml-rl-algorithms-draft.md`.
- TRL trainer internals (loss math, reward model mechanics) → `specs/alignment-training.md`.
- Adapter merging, GGUF export, vLLM serving → `specs/alignment-serving.md`.
- Evaluation harness (lm-eval) → `specs/alignment-serving.md`.
- Agents for strategy / data curation → existing `kailash_align.agents` module (unchanged).

### 1.3 Non-Goals

- **No replacement of TRL.** kailash-align keeps TRL as its training backend. Adapters are thin wrappers; TRL owns the training loop.
- **No new reward-function protocols.** Existing `kailash_align.rewards.RewardFunction` protocol is unchanged.
- **No new method registry.** Existing `method_registry.py` keeps every TRL trainer; the adapter surface is ADDITIVE.
- **No hard dependency on kailash-ml for standalone align users.** `[rl-bridge]` extra is opt-in.

---

## 2. `RLLifecycleProtocol` Compliance

### 2.1 Protocol recap (from `ml-rl-align-unification-draft.md` §2)

```python
@runtime_checkable
class RLLifecycleProtocol(Protocol):
    name: ClassVar[str]
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]]
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]]
    run_id: str
    tenant_id: str | None
    device: DeviceReport
    def build(self) -> None: ...
    def learn(self, total_timesteps, *, callbacks, eval_env_fn, eval_freq, n_eval_episodes) -> RLTrainingResult: ...
    def save(self, path: Path) -> PolicyArtifactRef: ...
    @classmethod
    def load(cls, ref: PolicyArtifactRef) -> "RLLifecycleProtocol": ...
    def checkpoint(self, path: Path) -> None: ...
    def resume(self, path: Path) -> None: ...
    def emit_metric(self, key: str, value: float, *, step: int) -> None: ...
```

### 2.2 Four adapters

Each adapter wraps an existing TRL trainer AND tracks `RLLifecycleProtocol` at runtime. `paradigm` and `buffer_kind` declarations:

| Adapter                 | Wraps                  | `name`               | `paradigm` | `buffer_kind`  |
| ----------------------- | ---------------------- | -------------------- | ---------- | -------------- |
| `AlignDPOAdapter`       | `trl.DPOTrainer`       | `"align-dpo"`        | `"rlhf"`   | `"preference"` |
| `AlignPPOAdapter`       | `trl.PPOTrainer`       | `"align-ppo"`        | `"rlhf"`   | `"rollout"`    |
| `AlignRLOOAdapter`      | `trl.RLOOTrainer`      | `"align-rloo"`       | `"rlhf"`   | `"rollout"`    |
| `AlignOnlineDPOAdapter` | `trl.OnlineDPOTrainer` | `"align-online-dpo"` | `"rlhf"`   | `"preference"` |

### 2.3 `isinstance` conformance

```python
from kailash_ml.rl.protocols import RLLifecycleProtocol
from kailash_align.rl_bridge import AlignDPOAdapter

adapter = AlignDPOAdapter(...)
assert isinstance(adapter, RLLifecycleProtocol)  # runtime Protocol check
```

Protocol is imported LAZILY at adapter construction time — only if `kailash-ml` is installed. A standalone kailash-align user who never calls `from kailash_align.rl_bridge import ...` has no hard dependency.

### 2.4 Adapter construction

```python
adapter = AlignDPOAdapter(
    model_id="meta-llama/Llama-3.1-8B",
    ref_model_id=None,                       # implicit: a frozen copy of model_id
    dataset=pref_dataset,                    # HF Dataset of chosen/rejected pairs
    reward_fn=None,                          # DPO implicit reward; None is valid
    tenant_id=tenant,                        # MANDATORY per rules/tenant-isolation.md §2
    actor_id=actor,                          # MANDATORY per ml-tracking §6
    device=None,                             # auto-detect via kailash_ml._device_report
    training_args=DPOConfig(...),            # TRL-native config passed through
)
adapter.build()
result = adapter.learn(total_timesteps=..., callbacks=[...], eval_env_fn=None, eval_freq=0, n_eval_episodes=0)
```

Note: `eval_env_fn`/`eval_freq`/`n_eval_episodes` are meaningless for RLHF preference training; adapters accept them as Protocol requirements but ignore them (TRL uses its own eval harness).

### 2.5 `device: DeviceReport`

Adapters auto-detect device via `kailash_ml._device_report.device_report_from_backend_info()`. For RLHF, typical resolution: CUDA if available, else CPU with a WARN (LLM training on CPU is pedagogical-only). MPS/XPU supported per `approved-decisions.md §5` XPU dual-path (native `torch.xpu` preferred over `ipex`).

### 2.6 `save` / `load` round-trip

`save(path)` serializes:

- LoRA adapter weights (via `peft.save_pretrained`).
- Tokenizer (if modified).
- `training_args` as JSON.
- `optimizer.state_dict()` (for resume).
- RNG state (torch + numpy + random).
- Training progress `{step, epoch, loss}` snapshot.

Returns `PolicyArtifactRef(path=<save_dir>, algorithm="align-dpo", kailash_ml_version="1.0.0", kailash_align_version="0.5.0")`.

`load(ref)` is the round-trip complement. `checkpoint()` / `resume()` use the same pair for mid-run persistence.

---

## 3. Auto-Emission

### 3.1 Metric namespace

All alignment adapters MUST emit under the `rl.*` namespace (classical-RL parity) PLUS the `align.*` namespace (alignment-specific). Emission is gated on `self._active_tracker is not None` — same discipline as `kaizen-ml-integration-draft.md` §3.

| Metric key                     | Paradigm              | Source                                      | Emit when            |
| ------------------------------ | --------------------- | ------------------------------------------- | -------------------- |
| `rl.policy.kl_from_ref`        | rlhf (all 4)          | TRL internal (`KLControllerCallback`)       | every optimizer step |
| `rl.policy.loss`               | rlhf (all 4)          | TRL `log_metrics` `loss` field              | every optimizer step |
| `rl.reward_model.score`        | dpo, rloo, online-dpo | implicit reward from chosen/rejected logits | every optimizer step |
| `rl.reward_model.margin`       | dpo only              | `chosen_reward - rejected_reward`           | every optimizer step |
| `rl.policy.ref_log_probs_mean` | rlhf                  | TRL internal                                | every optimizer step |
| `align.dpo.beta`               | dpo, online-dpo       | static hparam                               | `log_param` at start |
| `align.ppo.cliprange`          | ppo                   | static hparam                               | `log_param` at start |
| `align.rloo.k`                 | rloo                  | static hparam (rollout count)               | `log_param` at start |
| `align.completion_length_p95`  | rlhf (all 4)          | per-batch histogram                         | every eval step      |
| `align.chosen_token_acc`       | dpo, rloo, online-dpo | fraction of tokens where chosen > rejected  | every eval step      |

### 3.2 Parity with classical RL

Classical PPO (`kailash_ml.rl.trainer.RLTrainer` wrapping `stable_baselines3.PPO`) emits the SAME `rl.policy.loss` key (per `ml-rl-core-draft.md` §7). A researcher comparing "classical RF vs TRL-PPO" reads both values off one dashboard panel.

Keys that do NOT parity-map (e.g. `rl.env.episode_reward_mean` which requires a gym.Env) are absent from the RLHF side. That is DOCUMENTED, not a gap.

### 3.3 Emission via Protocol `emit_metric`

```python
class AlignDPOAdapter:
    def emit_metric(self, key: str, value: float, *, step: int) -> None:
        """Single emission point per Protocol."""
        tracker = self._active_tracker  # resolves via get_current_run()
        if tracker is not None:
            # Schedule the log call on the running event loop
            asyncio.get_event_loop().create_task(
                tracker.log_metric(key, value, step=step)
            )
        # Also forward to the adapter's own RLDiagnostics instance (per Protocol §2.1)
        if self._diagnostics is not None:
            self._diagnostics.record_metric(key, value, step=step)
```

### 3.4 TRL callback bridge

The adapter registers a `TrainerCallback` with TRL's `Trainer.add_callback()`. The callback's `on_log()` method reads TRL's `logs` dict and routes each key through `self.emit_metric()`. This is the only integration point between TRL's training loop and kailash-ml's tracker — kept intentionally narrow.

```python
class _KailashEmitCallback(TrainerCallback):
    def __init__(self, adapter: "AlignDPOAdapter"):
        self._adapter = adapter

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        step = state.global_step
        for trl_key, value in logs.items():
            kml_key = _TRL_TO_KML_METRIC_NAME.get(trl_key)
            if kml_key is not None and isinstance(value, (int, float)) and math.isfinite(value):
                self._adapter.emit_metric(kml_key, float(value), step=step)
```

`_TRL_TO_KML_METRIC_NAME` is a frozen dict at module load time — the single source of truth for the TRL→kailash-ml key renaming.

### 3.5 Rank-0-only emission

In multi-GPU training via `accelerate`, metrics MUST emit ONLY from the rank-0 process (per approved-decisions.md Decision 4). The callback guards:

```python
def on_log(self, args, state, control, logs=None, **kwargs):
    if state.is_world_process_zero is False:  # Accelerate sets this
        return
    # ... emit ...
```

---

## 4. Optional Dependency Declaration

### 4.1 Extras

`kailash-align 0.5.0` pyproject declares `[rl-bridge]`:

```toml
[project.optional-dependencies]
rl-bridge = ["kailash-ml>=1.0.0,<2.0.0"]
```

Per approved-decisions.md Decision 13 (extras naming), `[rl-bridge]` is a multi-word hyphenated extra name.

### 4.2 Install modes

- `pip install kailash-align` — standalone alignment (no RL bridge).
- `pip install kailash-align[rl-bridge]` — adds the ml bridge; `from kailash_align.rl_bridge import AlignDPOAdapter` works.
- `pip install kailash-ml[rl]` + `pip install kailash-align[rl-bridge]` — full unified RL + RLHF surface.

### 4.3 Import-time deferral

`kailash_align/__init__.py`'s lazy `__getattr__` MUST NOT import `kailash_align.rl_bridge` eagerly. The bridge module imports `kailash_ml.rl.protocols` at its own module-scope; if kailash-ml is absent the import raises — which is the correct error ("install kailash-ml to use the RL bridge").

Per approved-decisions.md implications and `rules/orphan-detection.md` §6: new `__all__` entries for `AlignDPOAdapter`, `AlignPPOAdapter`, `AlignRLOOAdapter`, `AlignOnlineDPOAdapter` live in `kailash_align.rl_bridge.__all__`, NOT in the top-level `kailash_align.__all__` (to avoid `from kailash_align import *` forcing kailash-ml).

---

## 5. Error Taxonomy

All errors inherit from `kailash_align.exceptions.AlignmentError` (existing base):

```python
class AlignmentError(Exception):
    """Base for every kailash-align exception."""

class RLBridgeError(AlignmentError):
    """Base for rl_bridge-specific errors."""

class RLBridgeImportError(RLBridgeError):
    """Raised when kailash-ml is not installed but rl_bridge is imported.
    Message: 'Install kailash-ml>=1.0.0 to use kailash_align.rl_bridge.'"""

class RLBridgeProtocolViolationError(RLBridgeError):
    """Raised at adapter construction if the Protocol isinstance check fails.
    Indicates a Python-version or kailash-ml-version mismatch."""

class RLBridgeTRLVersionError(RLBridgeError):
    """Raised when the installed TRL version is incompatible with the
    adapter (currently trl>=1.0.0 required)."""
```

`RLTrainingResult` and `PolicyArtifactRef` are imported from kailash-ml — not redefined here.

---

## 6. Test Contract

### 6.1 Tier 1 (unit)

- `test_align_dpo_adapter_satisfies_protocol.py` — `isinstance(adapter, RLLifecycleProtocol)` holds.
- `test_align_ppo_adapter_satisfies_protocol.py` — ditto PPO.
- `test_align_rloo_adapter_satisfies_protocol.py` — ditto RLOO.
- `test_align_online_dpo_adapter_satisfies_protocol.py` — ditto OnlineDPO.
- `test_trl_to_kml_metric_map_complete.py` — every TRL log key has a kailash-ml rename OR is explicitly in the drop-list.
- `test_rank0_only_emission.py` — `state.is_world_process_zero = False` → callback skips.
- `test_bridge_import_without_kailash_ml_raises_typed.py` — simulated absent ml → `RLBridgeImportError`.

### 6.2 Tier 2 (integration wiring, per `rules/facade-manager-detection.md` §2)

File naming:

- `tests/integration/test_align_dpo_adapter_emits_to_tracker_wiring.py` — real 2-step TRL DPO run on a tiny GPT-2-small toy model with a 4-sample preference dataset → `rl.policy.loss` appears in `_kml_metric` table.
- `tests/integration/test_align_ppo_adapter_save_load_roundtrip_wiring.py` — save → load → verify adapter state matches.
- `tests/integration/test_align_dpo_kl_controller_wiring.py` — run with nonzero beta → `rl.policy.kl_from_ref` appears; monotone-non-negative.

All tests CPU-only (tiny toy model) + require `[dev]` extras installing `trl`, `peft`, `transformers>=4.40`, `torch>=2.2`. See `ml-backends-draft.md` for the backend-compat matrix.

### 6.3 Regression tests

- `tests/regression/test_issue_NNN_dpo_adapter_tracker_kwarg_type_is_experiment_run.py` — ensures the lazy-resolved tracker is `ExperimentRun`, not `ExperimentTracker`.
- `tests/regression/test_issue_NNN_rloo_k_logged_as_param.py` — `align.rloo.k` appears as a PARAM (not a metric).

---

## 7. Cross-SDK Parity Requirements

kailash-align does NOT have a Rust equivalent today (LLM training is Python-first). Cross-SDK parity applies only to the metric key names:

- Every `rl.*` key emitted by an align adapter MUST match the key emitted by the corresponding classical-RL adapter in kailash-rs where semantically equivalent.
- Every `align.*` key is Python-only; Rust MAY adopt the same names if kailash-align gains a Rust presence in the future.

Cross-SDK follow-up is deferred post-1.0 per `rules/zero-tolerance.md` Rule 1 Exception clause. kailash-rs does not currently ship an `align` equivalent; if/when a Rust kailash-align surface lands, the metric-key contract above is the parity baseline. No tracking issue required until the Rust surface is scoped.

---

## 8. Industry Comparison

| Capability                              | kailash-align 0.5.0 | TRL (bare)   | Axolotl      | LLaMA-Factory | Hugging Face AutoTrain |
| --------------------------------------- | ------------------- | ------------ | ------------ | ------------- | ---------------------- |
| `RLLifecycleProtocol` conformance       | Y                   | N            | N            | N             | N                      |
| Auto-emit to shared run-tracker         | Y                   | N (W&B only) | N (W&B only) | Partial       | N                      |
| Adapter save/load round-trip with RNG   | Y                   | Partial      | Partial      | Partial       | N                      |
| Rank-0-only distributed emission        | Y                   | Manual       | Manual       | Manual        | N                      |
| Unified dashboard (classical RL + RLHF) | Y                   | N            | N            | N             | N                      |
| Cross-SDK metric-key parity             | Y (names locked)    | N            | N            | N             | N                      |

**Position:** kailash-align is the only alignment framework that treats RLHF as a first-class RL paradigm — a researcher's sweep comparing classical SB3-PPO vs TRL-PPO vs TRL-DPO reads all three trajectories off ONE MLDashboard.

---

## 9. Migration Path (kailash-align 0.4.x → 0.5.0)

0.4.x users:

- `kailash_align.rl_bridge` — NEW module. No breaking change.
- `AlignmentPipeline` — unchanged.
- `method_registry` — unchanged.
- `CostTracker` surface — IF kailash-align exposed one in 0.4.x it migrates to microdollar wire format per `kaizen-ml-integration-draft.md` §4 (cross-SDK cost parity).
- `DeprecationWarning` on any `cents`-based API surface for one release cycle (0.5.x), removed at 0.6.0.

No breaking removal in 0.5.0. Pure additive bridge.

---

## 10. Release Coordination Notes

Part of the kailash-ml 1.0.0 wave release (see `pact-ml-integration-draft.md` §10 for the full wave list).

**Release order position:** AFTER kailash-ml 1.0.0 — align depends on `kailash_ml.rl.protocols.RLLifecycleProtocol` (kailash-ml is the Protocol authoring side). kailash-align is the LAST package in the wave to release.

**Parallel-worktree ownership:** align-specialist agent owns `packages/kailash-align/pyproject.toml`, `packages/kailash-align/src/kailash_align/__init__.py::__version__`, and `packages/kailash-align/CHANGELOG.md`. Every other agent's prompt MUST exclude these files.

---

## 11. Cross-References

- kailash-ml specs consuming this surface:
  - `ml-rl-align-unification-draft.md` — canonical Protocol source.
  - `ml-rl-algorithms-draft.md` — classical-RL adapters (parity targets).
  - `ml-rl-core-draft.md` — RLTrainingResult + PolicyArtifactRef.
  - `ml-tracking-draft.md` §10 — ambient run resolution.
  - `ml-diagnostics-draft.md` — RLDiagnostics contract (shared between classical + RLHF).
- kailash-align companion specs:
  - `specs/alignment-training.md` — existing TRL trainer surface (unchanged in shape).
  - `specs/alignment-diagnostics.md` — alignment-specific diagnostics (unchanged).
  - `specs/alignment-serving.md` — unchanged.
- Rule references:
  - `rules/tenant-isolation.md` §1, §2 — mandatory tenant_id.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring tests.
  - `rules/orphan-detection.md` §6 — `__all__` hygiene for bridge module.
  - `rules/independence.md` — no commercial-SDK coupling.

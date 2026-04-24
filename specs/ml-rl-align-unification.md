# Spec (draft) — ML RL + Align TRL Cross-SDK Unification

Version: 1.0.0

**Status:** AUTHORITATIVE (promoted from DRAFT 2026-04-23, user-approved spec-led W30 path).
**Packages:** `kailash-ml` (target: 1.0.0) + `kailash-align` (target: 0.5.0+).
**Modules:** `kailash_ml.rl.protocols` (shared Protocol), `kailash_ml.rl.align_adapter`, `kailash_align.rl_bridge`.
**Parent specs:** `ml-rl-core-draft.md`, `ml-rl-algorithms-draft.md`.
**Cross-references:** `specs/alignment-training.md`, `specs/alignment-diagnostics.md`.
**Closes round-1 findings:** HIGH-11, CRIT-2 (cross-SDK facet), HIGH-8 (cross-SDK facet).

## 1. Problem Statement

`kailash-align` already ships TRL-backed RLHF trainers under `kailash_align.method_registry` — `DPOTrainer`, `PPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer`, `KTOTrainer`, `SimPOTrainer`, `CPOTrainer`, `GRPOTrainer`, `ORPOTrainer`, `BCOTrainer`, etc. (verified: `packages/kailash-align/src/kailash_align/method_registry.py:205-377`).

Structurally, RLHF IS reinforcement learning: a POLICY (language model) maximizes an objective that weights reward-model advantages against a KL penalty to a reference policy. The `trl.PPOTrainer` implements the SAME proximal policy optimization algorithm as `stable_baselines3.PPO` — clipped surrogate objective, advantage normalization, multi-epoch optimization per rollout. The ONLY differences are:

1. **Policy class** — `AutoModelForCausalLM` instead of `ActorCriticPolicy`.
2. **Environment** — token-generation trajectory instead of `gym.Env`.
3. **Reward signal** — reward-model score instead of env reward.
4. **Buffer kind** — token-level rollout instead of state-level rollout.

Today these two code paths do NOT share a single abstraction:

- **Two result types**: `RLTrainingResult` (kailash-ml 0.17.0) vs `AlignmentResult` (kailash-align). Neither extends the other.
- **Two tracker stacks**: the align pipeline does not emit to the same `km.track()` store as classical RL would (because classical RL doesn't emit either — HIGH-8).
- **Two registries**: kailash-align has its own trainer registry; classical RL has `PolicyRegistry`; neither talks to `kailash_ml.ModelRegistry`.
- **Two device resolvers**: align uses `accelerate`; ml uses `detect_backend()`; they do not share `DeviceReport`.

A researcher doing "baseline: train a bandit policy with SB3 PPO; fine-tune: LLM RLHF with TRL PPO" gets two experiments, two dashboards, two registries, two APIs. Per the audit brief's non-negotiable #4 (Full lifecycle coverage — classical ML + DL + RL + LLM fine-tune as peer capabilities), this is BLOCKED.

## 2. Shared `RLLifecycleProtocol`

The bridge is a runtime-checkable Protocol in `kailash_ml.rl.protocols` that BOTH kailash-ml's SB3-backed adapters AND kailash-align's TRL-backed adapters implement.

### 2.1 Protocol definition

```python
# packages/kailash-ml/src/kailash_ml/rl/protocols.py

from __future__ import annotations
from typing import Protocol, runtime_checkable, Any, Callable, ClassVar, Literal
from pathlib import Path
from dataclasses import dataclass
import polars as pl

from kailash_ml._result import TrainingResult
from kailash_ml._device_report import DeviceReport


@runtime_checkable
class RLLifecycleProtocol(Protocol):
    """The shared cross-SDK contract for every reinforcement-learning
    training run — classical (SB3, d3rlpy) or RLHF (TRL via kailash-align).

    Any adapter satisfying this Protocol can be dispatched via
    ``km.rl_train(..., algo=<registered-name>)`` and emits metrics to the
    same ``km.track()`` backend as every other kailash-ml engine.
    """

    # ─────────── Class-level declarations ─────────────────────────────
    name: ClassVar[str]
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]]
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]]

    # ─────────── Instance state ───────────────────────────────────────
    run_id: str
    tenant_id: str | None
    device: DeviceReport

    # ─────────── Lifecycle methods ────────────────────────────────────
    def build(self) -> None:
        """Construct the backend trainer (SB3 model / TRL trainer / d3rlpy algo)."""

    def learn(
        self,
        total_timesteps: int,
        *,
        callbacks: list[Any],
        eval_env_fn: Callable[[], Any] | None,
        eval_freq: int,
        n_eval_episodes: int,
    ) -> "RLTrainingResult":
        """Run training; emit rl.* metrics via the ambient tracker."""

    def save(self, path: Path) -> "PolicyArtifactRef":
        """Persist the policy (+ optimizer + buffer + RNG) to disk."""

    @classmethod
    def load(cls, ref: "PolicyArtifactRef") -> "RLLifecycleProtocol":
        """Round-trip complement of save()."""

    def checkpoint(self, path: Path) -> None:
        """Persist full training state for ``resume_from=``."""

    def resume(self, path: Path) -> None:
        """Restore full training state from a checkpoint directory."""

    # ─────────── Telemetry contract ───────────────────────────────────
    def emit_metric(self, key: str, value: float, *, step: int) -> None:
        """Canonical metric emit point; forwards to the ambient tracker
        AND to the adapter's own RLDiagnostics instance."""
```

### 2.2 Why Protocol, not ABC

Protocol conformance is duck-typed and runtime-checkable. `kailash-align` already has `trl.PPOTrainer`, `trl.DPOTrainer` etc. as the actual trainer classes — wrapping them in a kailash-align adapter that SATISFIES the Protocol at runtime (without inheriting from an ABC that would require kailash-align to take a hard dependency on kailash-ml) is the only cross-SDK-safe approach. This mirrors `kailash.diagnostics.protocols.Diagnostic` / `JudgeCallable` (already shared across kailash + kaizen + align).

### 2.3 `isinstance` check is the conformance gate

```python
from kailash_ml.rl.protocols import RLLifecycleProtocol
from kailash_align.rl_bridge import AlignDPOAdapter

adapter = AlignDPOAdapter(...)
assert isinstance(adapter, RLLifecycleProtocol)  # must hold at runtime
```

The Protocol is NOT imported at `kailash-align` runtime unless `kailash-ml` is installed — kailash-align declares an OPTIONAL dependency `[rl-bridge]` that pulls kailash-ml only when a user wants the unified dispatch. See §7.

## 3. Dispatch from `km.rl_train` to kailash-align

### 3.1 Algorithm name → backend routing

`km.rl_train(algo=<name>)` resolves `<name>` via a two-level lookup:

1. First-party classical adapter registry (`kailash_ml.rl.algorithms`) — `ppo`, `a2c`, `trpo`, `dqn`, `sac`, `td3`, `ddpg`, `bc`, `cql`, `iql`.
2. Align-bridge registry (`kailash_ml.rl.align_adapter`) — `dpo`, `ppo-rlhf`, `rloo`, `online-dpo`, `kto`, `simpo`, `cpo`, `grpo`, `orpo`, `bco`.

When a name resolves to a bridge adapter, `km.rl_train`:

1. Imports `kailash_align.rl_bridge` (lazy — fails with actionable error if `kailash-align` is not installed).
2. Constructs `AlignAdapter(name=<name>, policy=<lm>, reward_model=<rm>, reference_model=<ref>, preference_dataset=<ds>, hyperparameters=<hp>, device=<device>, tenant_id=<tenant>)`.
3. Asserts the adapter satisfies `RLLifecycleProtocol`.
4. Calls `adapter.learn(total_timesteps, callbacks=[_KailashRLCallback(tracker)], ...)`.
5. Returns the `RLTrainingResult` produced by the adapter.

### 3.2 Result type parity

Both classical SB3 adapters AND kailash-align bridge adapters return `RLTrainingResult` (see `ml-rl-core-draft.md` §3.2). The RLHF-specific fields live alongside classical fields with `None` when not applicable:

| Field                 | Classical RL (SB3) | RLHF (TRL)                                             |
| --------------------- | ------------------ | ------------------------------------------------------ |
| `algorithm`           | "ppo"              | "dpo"                                                  |
| `env_spec`            | "CartPole-v1"      | "text:alpaca-v1" (dataset ref)                         |
| `total_env_steps`     | env steps          | generated-token count                                  |
| `episode_reward_mean` | env reward         | reward-model score mean (or preference-margin for DPO) |
| `kl_divergence`       | approx_kl (PPO)    | KL-from-reference (RLHF)                               |
| `explained_variance`  | value-fn EV        | `None` for DPO; value-fn EV for PPO-RLHF               |
| `replay_buffer_size`  | int                | `None` (RLHF is on-policy rollout or preference-based) |
| `policy_entropy`      | action entropy     | token entropy                                          |

Closes CRIT-2 (cross-SDK facet): the SAME dataclass works for both.

### 3.3 Tracker parity

Per `ml-rl-core-draft.md` §8.1, `km.rl_train` auto-attaches `_KailashRLCallback` to emit `rl.*` metrics to the ambient tracker. The align bridge adapters MUST forward their internal metric streams (TRL's `trainer.state.log_history`, `trainer.optimizer`, `trainer.reward_model` scores) through the SAME callback — NOT through a separate logger.

This means `MLDashboard` renders a DPO run with the same RL tab panels as a SAC run, modulo the metric availability per-paradigm. A researcher viewing experiments sees RL + RLHF runs in one list, same dashboard, same filterable columns.

### 3.4b DPO Reference-Model Temperature Contract

DPO and DPO-family algorithms (DPO / online-DPO / KTO / SimPO / CPO / ORPO) require a REFERENCE model for computing log-ratios. The reference model's generation temperature at LOG-PROB extraction time determines which quantity `reward_margin` represents; mixing temperatures across runs produces incomparable margins.

```python
class DPOAdapter:
    def __init__(
        self,
        *,
        policy: PolicyProtocol,
        reference_model: PolicyProtocol,
        preference_dataset: PreferenceDataset,
        hyperparameters: dict,
        ref_temperature: float = 1.0,       # log-prob extraction temperature (canonical)
        sampling_temperature: float = 0.0,  # sampling-time (irrelevant for offline DPO)
        ...
    ) -> None: ...
```

#### MUST: Reference-Model `eval()` + Pinned Temperature for Log-Prob Extraction

1. Every DPO-family adapter MUST call `reference_model.eval()` before log-prob extraction and MUST NOT toggle it back to `.train()` in the adapter's scope.
2. Log-prob extraction MUST use `ref_temperature = 1.0` by default (TRL-canonical). Users who deliberately want T < 1 for sample-efficient training pass an explicit `ref_temperature=0.9`; the resulting `reward_margin` is tagged with the temperature in the tracker payload.
3. Sampling-time temperature (online-DPO: `0.9`; RLOO: `0.7`) is SEPARATE from log-prob-time temperature and lives under `sampling_temperature`.
4. The tracker emits `rl.train.update.ref_temperature` as a categorical tag alongside `reward_margin`. Dashboards filter cross-run comparisons to matching `ref_temperature` OR annotate mixed-temperature comparisons as potentially biased.

```python
# DO — TRL-canonical reference temperature (1.0) unless explicitly overridden
adapter = DPOAdapter(policy=π, reference_model=π_ref, preference_dataset=ds,
                     ref_temperature=1.0)

# DO — opt-in to T=0.9 AND the tracker tag records it
adapter = DPOAdapter(..., ref_temperature=0.9)
# → run.metric["ref_temperature"] = 0.9 emitted every update

# DO NOT — let sampling-time temperature leak into log-prob extraction
# adapter = DPOAdapter(..., temperature=0.9)  # ambiguous which T is meant
```

**Why:** TRL uses `temperature=1.0` by default for log-prob extraction while online-DPO / RLOO variants use `0.9` / `0.7` for SAMPLING. A user comparing DPO runs across adapters without knowing which T produced the margin is comparing different quantities. Pinning `ref_temperature=1.0` as the canonical default AND emitting the tag closes the comparability gap.

### 3.4 Telemetry emitted by RLHF bridge

| Metric family        | Keys (RLHF specifics)                                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `rl.rollout.step`    | `reward_model_score`, `token_entropy`, `generation_latency_ms`                                                               |
| `rl.rollout.episode` | for RLHF: episode = one completion; `ep_reward` = reward-model score                                                         |
| `rl.train.update`    | `policy_loss` (DPO/PPO-RLHF loss), `kl_from_reference`, `reward_accuracy`, `reward_margin` (DPO), `clip_fraction` (PPO-RLHF) |
| `rl.eval`            | `judge_score` (online-dpo), `generation_reward_mean`, `reference_kl_mean`                                                    |
| `rl.buffer.stats`    | preference-buffer: `pair_count`, `chosen_reward_mean`, `rejected_reward_mean`, `reward_margin_std`                           |
| `rl.exploration`     | `temperature`, `top_p`, `top_k` (when sampling); `token_entropy`                                                             |

The keys MUST be identical to classical-RL where the concept is identical (e.g. `kl_from_reference` is emitted by both PPO-RLHF and classical SAC's entropy-coef KL proxy, wherever the proxy applies). This lets `MLDashboard` render uniform panels.

## 4. Test Contract — `test_rl_align_cross_sdk_wiring.py`

Tier 2 integration test living in `packages/kailash-ml/tests/integration/rl/test_rl_align_cross_sdk_wiring.py`. Runs when BOTH `kailash-ml[rl]` AND `kailash-align` are installed.

```python
import pytest
import polars as pl
import kailash_ml as km
from kailash_ml.experiment_tracker import ExperimentTracker
from kailash_ml.rl.protocols import RLLifecycleProtocol


@pytest.mark.integration
@pytest.mark.skipif(not _align_installed(), reason="requires kailash-align")
async def test_km_rl_train_dispatches_to_align_dpo(tmp_path):
    """km.rl_train(algo='dpo', ...) dispatches to kailash-align's
    DPOTrainer bridge AND emits identical telemetry to classical RL."""

    # 1. Set up a minimal preference dataset
    prefs = pl.DataFrame({
        "prompt":    ["Hello", "Goodbye"] * 4,
        "chosen":    ["Hi there!", "Farewell!"] * 4,
        "rejected":  ["hrrr", "whatever"] * 4,
    })

    # 2. Tracker — same ExperimentTracker as every other km engine
    tracker = await ExperimentTracker.create(f"sqlite:///{tmp_path}/ml.db")
    async with tracker:
        result = km.rl_train(
            env="text:preferences",
            algo="dpo",
            policy="sshleifer/tiny-gpt2",      # tiny model for CI
            reference_model="sshleifer/tiny-gpt2",
            preference_dataset=prefs,
            total_timesteps=2,                  # a few steps only
            eval_freq=2,
            n_eval_episodes=2,
            tracker=tracker,
            experiment="test-rl-align",
            tenant_id="t-dpo",
            hyperparameters={"beta": 0.1, "learning_rate": 5e-7, "batch_size": 2},
        )

        # 3. Result-shape parity — same type as classical RL
        assert isinstance(result, km.RLTrainingResult)
        assert result.algorithm == "dpo"
        assert result.device is not None

        # 4. The bridge adapter satisfied RLLifecycleProtocol at runtime
        adapter = result._adapter_ref       # test-only accessor
        assert isinstance(adapter, RLLifecycleProtocol)

        # 5. Tracker telemetry parity — same rl.* families as classical PPO
        metrics = await tracker.list_metrics(run_id=result.run_id)
        rl_keys = {m.key for m in metrics if m.key.startswith("rl.")}

        # MUST include structurally-shared families:
        assert any(k == "rl.train.update.policy_loss" for k in rl_keys)
        assert any(k == "rl.train.update.kl_from_reference" for k in rl_keys)
        assert any(k == "rl.eval.mean_reward" for k in rl_keys) or \
               any(k == "rl.eval.generation_reward_mean" for k in rl_keys)

        # 6. RLDiagnostics wiring — align bridge must have emitted to the
        #    same diagnostic store as a classical km.rl_train call would
        assert result.run_id in [r.run_id for r in await tracker.list_runs()]

        # 7. Artifact registered — SAME ModelRegistry lifecycle as sklearn
        assert result.policy_artifact is not None
        assert result.policy_artifact.sha is not None


@pytest.mark.integration
@pytest.mark.skipif(not _align_installed(), reason="requires kailash-align")
def test_align_bridge_adapters_all_satisfy_protocol():
    """Every name the align bridge registers must satisfy RLLifecycleProtocol
    at runtime — closes HIGH-11 structurally."""
    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    for name, adapter_cls in BRIDGE_ADAPTERS.items():
        adapter = adapter_cls.__make_for_test__()   # class-level factory for tests
        assert isinstance(adapter, RLLifecycleProtocol), (
            f"Align bridge adapter '{name}' does not satisfy RLLifecycleProtocol"
        )
```

This test is the anti-regression per `rules/orphan-detection.md` §2a (Crypto-Pair Round-Trip analog): it rides BOTH halves of the contract — ml side defines the Protocol; align side satisfies it — in ONE test that would have caught any drift.

## 5. Cross-SDK Lineage Fields

### 5.1 Lineage dataclass

```python
@dataclass(frozen=True)
class RLLineage:
    run_id: str
    experiment_name: str | None
    tenant_id: str | None
    base_model_ref: str | None           # policy's starting checkpoint (e.g. "sshleifer/tiny-gpt2")
    reference_model_ref: str | None      # RLHF reference
    reward_model_ref: str | None         # RLHF reward model (name + SHA)
    dataset_ref: str | None              # preference dataset ref
    env_spec: str | None                 # "CartPole-v1" or "text:preferences"
    algorithm: str
    paradigm: Literal["on-policy", "off-policy", "offline", "rlhf"]
    parent_run_id: str | None            # for resume-from / fine-tune chains
    sdk_source: Literal["kailash-ml", "kailash-align"]
    sdk_version: str
    created_at: datetime
```

### 5.2 Emission

`RLTrainingResult` gains a `lineage: RLLineage` field. The align bridge populates `sdk_source="kailash-align"`; first-party ml adapters populate `sdk_source="kailash-ml"`. `MLDashboard` renders the lineage as a provenance breadcrumb ("SAC → DPO fine-tune" visible from one view of the experiment).

### 5.3 DataFlow × ML cross-cut

When `kailash-dataflow` is the data source for the preference dataset, `RLLineage` records the dataset's dataflow model name + tenant + row count. This closes the `DataFlow × ML` lineage gap called out in round-1 industry-competitive finding.

## 6. `AlignmentDiagnostics` Parity With `RLDiagnostics`

`kailash-align` already ships `AlignmentDiagnostics` satisfying `kailash.diagnostics.protocols.Diagnostic` (verified via `specs/alignment-diagnostics.md`). For cross-SDK UX:

1. **Protocol parity** — both satisfy the same upstream `Diagnostic` Protocol.
2. **Metric namespace parity** — `AlignmentDiagnostics` reward-hacking findings MUST emit under `rl.train.update.*` when the run is bridged through `km.rl_train` (so `MLDashboard`'s RL tab reads the same keys). When used standalone from `kailash-align`, the keys stay `alignment.*` for backward compatibility.
3. **Severity taxonomy parity** — reward-hacking (CRIT) aligns with classical RL's `episode_reward_collapse` (CRIT). Both emit at the same severity level so a single dashboard alert filter catches both.
4. **Composition** — when `km.rl_train(algo="dpo", ..., experiment="X")` runs, BOTH `RLDiagnostics` AND `AlignmentDiagnostics` can be active on the same run. The bridge adapter MUST forward metrics to BOTH diagnostics; `MLDashboard` deduplicates by (run_id, step, key).

## 7. Dependency Topology

```
kailash-ml (core)
  └── kailash_ml.rl.protocols          # RLLifecycleProtocol — NO trl / align import
  └── kailash_ml.rl.algorithms         # first-party SB3 adapters
  └── kailash_ml.rl.align_adapter      # bridge dispatch — imports kailash_align LAZILY
                                       # under `if TYPE_CHECKING` + runtime importlib

kailash-align
  └── kailash_align.method_registry    # TRL trainers (existing)
  └── kailash_align.rl_bridge          # NEW in 0.5.0 — imports kailash_ml.rl.protocols
                                       # and registers bridge adapters
  pyproject.toml:
    [project.optional-dependencies]
    rl-bridge = ["kailash-ml[rl]>=0.18"]
```

- `kailash-ml[rl]` does NOT pull kailash-align.
- `kailash-align` does NOT pull kailash-ml.
- `kailash-align[rl-bridge]` (new extra) pulls kailash-ml — activates the bridge registration.
- Users installing only kailash-ml and calling `algo="dpo"` get a typed `FeatureNotAvailableError`:
  > "algo='dpo' requires kailash-align[rl-bridge] or kailash-align + kailash-ml[rl]; install via 'pip install kailash-align[rl-bridge]'".

Matches `rules/zero-tolerance.md` Rule 2 (no silent NotImplementedError).

## 8. Version Coordination

- **kailash-ml 1.0.0** — ships `RLLifecycleProtocol`, `km.rl_train`, first-party adapters, `kailash_ml.rl.align_adapter` with the bridge dispatch entry points (but NOT the bridge implementation — that lives in kailash-align).
- **kailash-align 0.5.0** — ships `kailash_align.rl_bridge` with concrete adapters for DPO/PPO-RLHF/RLOO/online-DPO, satisfying `RLLifecycleProtocol`. Depends on `kailash-ml[rl]>=1.0` when `[rl-bridge]` extra installed.
- **Version floor tests** — kailash-align 0.5.0 has a tier-1 test that imports `kailash_ml.rl.protocols.RLLifecycleProtocol` and asserts the expected class-level attributes exist. Prevents silent drift if kailash-ml changes the Protocol.

## 9. Non-Goals for v1

- **kailash-ml → kailash-align reverse dispatch** — we only dispatch ml → align. Align does not need to call classical SB3 adapters.
- **Shared policy weights across classical + RLHF** — training a classical-SAC policy and using its weights as an LLM initializer is out of scope; it's not structurally coherent.
- **Live streaming of RLHF generations to MLDashboard** — the dashboard shows reward-model scores, not generated text. Text-level views belong to a future `ml-rl-generation-view` spec.
- **Multi-node RLHF training** — `accelerate` + `deepspeed` integration lives in kailash-align; kailash-ml's bridge dispatches to kailash-align's configuration path; kailash-ml does not ship a second distributed backend.

## 10. Migration Path

### 10.1 For kailash-align users

No API change. `AlignmentPipeline(...).run()` continues to work. The new `km.rl_train(algo="dpo", ...)` entry is ADDITIVE — users who want a unified dashboard opt in by switching to `km.rl_train`.

### 10.2 For classical RL users

No change. `km.rl_train(algo="ppo", env="CartPole-v1", ...)` is the v1 entry. The bridge does not affect the classical path.

### 10.3 For `kailash_ml.rl.RLTrainer` (0.17.0 orphan)

See `ml-rl-core-draft.md` §16.1. One-release deprecation window.

## 11. Open Design Decisions (resolve before 0.18.0 ships)

These are flagged for `/todos` review, NOT silent defaults:

1. **D1 — where does the bridge live?** Two options:
   - (a) `kailash_ml.rl.align_adapter` imports `kailash-align` lazily when a user passes `algo="dpo"`.
   - (b) `kailash_align.rl_bridge` registers bridge adapters with kailash-ml via entry-point discovery at install time.

   Default: (a). Entry-point discovery adds install-time coupling and makes testing harder. Lazy import is the pattern used by kaizen ↔ kailash-align already. RESOLVED in this draft as (a).

2. **D2 — tracker ownership for bridged runs.** The bridge adapter COULD open its own tracker run OR use the caller's tracker. Default: caller's tracker (the `km.rl_train` orchestrator opens the run and hands it to the adapter). This matches classical RL. RESOLVED.

3. **D3 — `policy=` resolution when bridged.** `km.rl_train(..., algo="dpo", policy="mlp")` is a user error (MLP policy doesn't apply to LM). Options:
   - (a) Raise `RLPolicyShapeMismatchError` immediately.
   - (b) Auto-correct to `policy="lm"` with a WARN.

   Default: (a). `rules/zero-tolerance.md` Rule 3 (no silent fallback). RESOLVED.

4. **D4 — which TRL trainers are bridged in v1?** Candidates: DPO, PPO-RLHF, RLOO, OnlineDPO, KTO, SimPO, CPO, GRPO, ORPO, BCO.

   Default v1: DPO, PPO-RLHF, RLOO, OnlineDPO (the 4 already called out in HIGH-11). Others added in 0.19.0+. RESOLVED for v1.

5. **D5 — does the bridge adapter surface `AlignmentDiagnostics` findings in the `rl.*` namespace or keep `alignment.*`?**

   Default: namespace-shift when called through `km.rl_train` (emits `rl.*`); keep `alignment.*` when called directly from `kailash-align`. Implementation: the bridge passes a `namespace` kwarg to the underlying diagnostic. RESOLVED.

## 12. Attribution

- **TRL** (Apache-2.0, HuggingFace) — the RLHF backend. Already attributed in kailash-align.
- **transformers / datasets / accelerate** (Apache-2.0) — used via TRL. Already attributed.

Spec revisions:

- **2026-04-21 DRAFT** — initial draft defining the RLLifecycleProtocol, dispatch, lineage fields, test contract, and open design decisions.
- **2026-04-23 v1.0.0** — promoted to authoritative; open decisions D1–D5 resolved as documented; W30 implementation in flight across 3 shards (kailash-ml owner).

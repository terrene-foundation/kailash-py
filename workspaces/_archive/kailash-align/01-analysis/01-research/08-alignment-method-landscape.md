# Alignment Method Landscape (2023-2026)

## 1. Complete Inventory of Alignment / Preference Optimization Methods

### 1.1 Foundational Methods (2023)

#### DPO — Direct Preference Optimization

- **Paper**: Rafailov et al., "Direct Preference Optimization: Your Language Model Is Secretly a Reward Model" (NeurIPS 2023)
- **arXiv**: [2305.18290](https://arxiv.org/abs/2305.18290)
- **Key innovation**: Eliminates the reward model from RLHF entirely. Reparameterizes the reward function such that the optimal policy can be extracted directly from a classification loss on preference pairs. The policy is the reward model.
- **Loss**: Sigmoid loss on the difference between log-ratios of chosen/rejected under the policy vs. a reference model. Controlled by `beta` (KL penalty strength).
- **Data format**: `{prompt, chosen, rejected}` — pairwise preference data.
- **When to use**: Default choice for preference alignment when you have pairwise preference data. Works well at all scales (1B-70B). Simple to implement, well-understood failure modes. Good for general instruction-following and chat alignment.
- **Limitations**: Bounded by quality of preference pairs (offline, cannot improve beyond training data). Length bias (prefers longer responses). Reference model dependency (memory overhead). Overfits if trained too long.
- **TRL support**: `DPOTrainer` + `DPOConfig` (stable).
- **Status in kailash-align**: Implemented.

#### IPO — Identity Preference Optimization

- **Paper**: Azar et al., "A General Theoretical Paradigm to Understand Learning from Human Feedback" (NeurIPS 2023, Google DeepMind)
- **arXiv**: [2310.12036](https://arxiv.org/abs/2310.12036)
- **Key innovation**: Adds a regularization term to the DPO loss that prevents overfitting by controlling the gap between the likelihood ratios of the model and a reference model. Bypasses the Bradley-Terry assumption that DPO relies on.
- **Data format**: Same as DPO — `{prompt, chosen, rejected}`.
- **When to use**: When DPO overfits on small datasets. When you want to train to convergence without early stopping tricks. The regularization term makes it more stable on limited data.
- **Limitations**: Similar performance to DPO on large datasets; the benefit is primarily on smaller datasets where overfitting is a concern.
- **TRL support**: Available via `DPOTrainer` with `loss_type="ipo"`. Not a separate trainer.
- **Implementation note**: Drop-in replacement for DPO in kailash-align — just set the loss_type parameter.

#### CPO — Contrastive Preference Optimization

- **Paper**: Xu et al., "Contrastive Preference Optimization: Pushing the Boundaries of LLM Performance in Machine Translation" (ICML 2024)
- **arXiv**: [2401.08417](https://arxiv.org/abs/2401.08417)
- **Key innovation**: Trains models to avoid generating adequate-but-imperfect translations by contrasting chosen vs. rejected completions. Unlike DPO, does not require a reference model — the SFT loss itself acts as the regularizer. Combines SFT and preference optimization into one objective.
- **Data format**: Same as DPO — `{prompt, chosen, rejected}`.
- **When to use**: When you want to combine SFT and preference optimization in a single training step. Originally designed for machine translation, but applicable to general alignment. Good when you want to save the memory of a reference model.
- **Limitations**: Originally validated on translation tasks; generalization to broader alignment tasks is less studied than DPO.
- **TRL support**: `CPOTrainer` + `CPOConfig` (experimental). Also available as `DPOTrainer` with `loss_type="cpo"`.

### 1.2 Reference-Free and Data-Efficient Methods (2024)

#### KTO — Kahneman-Tversky Optimization

- **Paper**: Ethayarajh et al., "KTO: Model Alignment as Prospect Theoretic Optimization" (ICML 2024, Contextual AI)
- **arXiv**: [2402.01306](https://arxiv.org/abs/2402.01306)
- **Key innovation**: Uses prospect theory (Kahneman & Tversky) to model human decision-making biases, particularly loss aversion. Only requires a binary signal — "desirable" or "undesirable" — instead of pairwise preferences. This is the key advantage: binary feedback is vastly cheaper and more abundant in production systems than paired comparisons.
- **Data format**: `{prompt, completion, label}` where `label` is boolean (desirable/undesirable). In TRL format: dataset with `chosen` OR `rejected` completions (not necessarily paired).
- **When to use**: When you have thumbs-up/thumbs-down feedback but NOT pairwise preferences. When collecting paired preferences is expensive (most real production systems). Matches or exceeds DPO performance at 1B-30B scale despite weaker signal.
- **Configuration**: `desirable_weight` and `undesirable_weight` parameters for handling imbalanced data. Recommended ratio of (desirable_weight x num_positives) to (undesirable_weight x num_negatives) is 1:1 to 4:3.
- **TRL support**: `KTOTrainer` + `KTOConfig` (experimental, candidate for promotion to stable).

#### ORPO — Odds Ratio Preference Optimization

- **Paper**: Hong et al., "ORPO: Monolithic Preference Optimization without Reference Model" (EMNLP 2024)
- **arXiv**: [2403.07691](https://arxiv.org/abs/2403.07691)
- **Key innovation**: Truly monolithic — combines SFT and preference alignment into a single training step with a single loss function. Appends a log odds ratio term to the negative log-likelihood loss. No reference model. No separate SFT phase. One pass.
- **Data format**: Same as DPO — `{prompt, chosen, rejected}`.
- **When to use**: When you want the absolute simplest pipeline — one training run instead of SFT + DPO. Good for smaller models (Phi-2 2.7B, Mistral 7B). Eliminates the SFT-then-DPO sequencing complexity entirely. Results show it surpasses state-of-the-art on AlpacaEval 2.0 (12.20%) and MT-Bench (7.32).
- **Key parameter**: `lambda` controls the balance between SFT loss and odds ratio loss.
- **TRL support**: `ORPOTrainer` + `ORPOConfig` (experimental).
- **Impact on kailash-align**: If adopted, eliminates the `sft_then_dpo` pipeline concept for ORPO users.

#### SimPO — Simple Preference Optimization

- **Paper**: Meng et al., "SimPO: Simple Preference Optimization with a Reference-Free Reward" (NeurIPS 2024, Princeton NLP)
- **arXiv**: [2405.14734](https://arxiv.org/abs/2405.14734)
- **Key innovation**: Uses the average log probability of a sequence as the implicit reward (not total log probability). This aligns training reward with generation likelihood — in DPO, ~50% of instances show misalignment between reward ranking and generation metric ranking. SimPO eliminates this discrepancy entirely. Also introduces a target reward margin (`gamma`) to encourage larger separation between chosen/rejected.
- **Data format**: Same as DPO — `{prompt, chosen, rejected}`.
- **When to use**: When you want a reference-free method that outperforms DPO. Outperforms DPO by up to 6.4 points on AlpacaEval 2 and 7.5 points on Arena-Hard. No reference model means ~50% less GPU memory. Best results on instruction-tuned models (Mistral, Llama 3, Gemma 2).
- **Key parameter**: `simpo_gamma` (target reward margin, default 0.5).
- **TRL support**: Available via `DPOTrainer` with `loss_type="simpo"`. Also supported in `CPOTrainer`.

#### NCA — Noise Contrastive Alignment

- **Paper**: Chen et al., "Noise Contrastive Alignment of Language Models with Explicit Rewards" (NeurIPS 2024, THU)
- **arXiv**: [2402.05369](https://arxiv.org/abs/2402.05369)
- **Key innovation**: Bridges the gap between preference-based alignment (DPO) and explicit reward-based alignment. Provides a general framework using Noise Contrastive Estimation (NCE). Key finding: DPO/InfoNCA focus on adjusting _relative_ likelihood across responses, which causes the well-known "decreasing chosen likelihood" phenomenon. NCA optimizes _absolute_ likelihood, preventing chosen likelihood from decreasing.
- **Data format**: Works with both preference data AND scalar reward data. `{prompt, completion, reward_score}` or standard preference pairs.
- **When to use**: When you have explicit numerical reward scores (not just preference pairs). When DPO causes chosen response likelihood to decrease (a known DPO failure mode). Significantly outperforms DPO on complex reasoning tasks (math, coding).
- **TRL support**: Available via `DPOTrainer` with `loss_type="nca_pair"`.

#### BCO — Binary Classifier Optimization

- **Paper**: Jung et al., "BCO: Binary Classifier Optimization for LLM Alignment" (2024)
- **arXiv**: [2404.04656](https://arxiv.org/abs/2404.04656)
- **Key innovation**: Frames alignment as a binary classification problem. Like KTO, works with unpaired data (desirable/undesirable). Uses a binary classifier to separate good from bad completions.
- **Data format**: Unpaired — `{prompt, completion, label}` (desirable/undesirable).
- **When to use**: Alternative to KTO for unpaired data scenarios. When your data naturally comes as labeled completions rather than preference pairs.
- **TRL support**: `BCOTrainer` + `BCOConfig` (experimental). Also available via `DPOTrainer` with `loss_type="bco_pair"`.

### 1.3 Online RL Methods (2024-2025)

#### GRPO — Group Relative Policy Optimization

- **Paper**: Shao et al., "DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models" (2024); DeepSeek-AI, "DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning" (January 2025)
- **arXiv**: [2402.03300](https://arxiv.org/abs/2402.03300) (DeepSeekMath), [2501.12948](https://arxiv.org/abs/2501.12948) (DeepSeek-R1)
- **Key innovation**: Eliminates the critic (value) network required by PPO, reducing memory by ~50%. Generates multiple completions per prompt, uses their average reward as a baseline, and computes advantages relative to the group. No separate reward model needed — uses verifiable rewards (rule-based scoring). This is the method that trained DeepSeek-R1.
- **Data format**: `{prompt}` — only prompts are needed. Completions are generated online by the policy. Requires a `reward_func(completions) -> list[float]` function.
- **When to use**: Reasoning tasks (math, coding, logic) where correctness is verifiable. When you want to improve _beyond_ the quality of your training data (online methods can discover better solutions). When PPO is too expensive or unstable. DeepSeek-R1 configuration: 16 outputs per prompt, max length 32,768, KL coefficient 0.001.
- **Key parameters**: `num_generations` (group size per prompt), `temperature` (sampling temperature for diversity), reward functions (synchronous or async, multiple combinable).
- **TRL support**: `GRPOTrainer` + `GRPOConfig` (stable). Supports vLLM backend for fast generation.
- **Production adoption**: DeepSeek-R1, QwQ, Kimi k1.5, Nemotron 3 Super.

#### RLOO — REINFORCE Leave-One-Out

- **Paper**: Ahmadian et al., "Back to Basics: Revisiting REINFORCE Style Optimization for Learning from Human Feedback in LLMs" (ACL 2024)
- **arXiv**: [2402.14740](https://arxiv.org/abs/2402.14740)
- **Key innovation**: Shows that simple REINFORCE with a leave-one-out baseline matches or outperforms PPO while being far simpler. For each prompt, generates K completions, and the baseline for completion k is the average reward of the other K-1 completions. No critic network, no value function training.
- **Data format**: Like GRPO — `{prompt}` + reward function. Can use a trained reward model or rule-based rewards.
- **When to use**: When you want online RL but PPO is too complex or unstable. Consistently outperforms PPO and DPO across datasets. Simpler to implement and tune than PPO. Basically "GRPO's older sibling" — similar ideas, slightly different formulation.
- **TRL support**: `RLOOTrainer` + `RLOOConfig` (stable).

#### Online DPO

- **Paper**: Guo et al., "Direct Language Model Alignment from Online AI Feedback" (2024)
- **arXiv**: [2402.04792](https://arxiv.org/abs/2402.04792)
- **Key innovation**: Makes DPO online — instead of training on static preference pairs, the model generates its own completions during training, which are then ranked by a judge (reward model or LLM-as-judge). This addresses DPO's fundamental limitation of being bounded by the quality of offline preference data.
- **Data format**: `{prompt}` — only prompts needed. A `judge` (PairRM or reward model) scores the generated completions online.
- **When to use**: When you want the simplicity of DPO but with online data generation. When your static preference data is limited or stale. When you want the model to improve beyond the original preference data quality.
- **TRL support**: `OnlineDPOTrainer` + `OnlineDPOConfig` (experimental). Uses either a `judge` (pairwise comparison) or `reward_funcs` (scalar reward model).

#### PPO — Proximal Policy Optimization (for RLHF)

- **Paper**: Schulman et al., "Proximal Policy Optimization Algorithms" (2017); Ouyang et al., "Training language models to follow instructions with human feedback" (NeurIPS 2022)
- **arXiv**: [1707.06347](https://arxiv.org/abs/1707.06347) (PPO), [2203.02155](https://arxiv.org/abs/2203.02155) (InstructGPT/RLHF)
- **Key innovation**: The original RLHF method. Trains a reward model on human preferences, then optimizes the policy (LLM) using PPO with the reward model as the signal. Uses a clipped surrogate objective for stable updates.
- **Data format**: Two-stage: (1) `{prompt, chosen, rejected}` for reward model training, then (2) `{prompt}` for RL training with the trained reward model scoring online completions.
- **When to use**: Highest alignment quality for 10B+ models. Best for frontier lab scenarios with large compute budgets. ChatGPT and Claude were trained with PPO-based RLHF. Being replaced by GRPO/RLOO in most production settings due to complexity.
- **Limitations**: Requires training and maintaining a separate reward model (2x memory). Notorious instability and hyperparameter sensitivity. Reward hacking. Complex implementation.
- **TRL support**: `PPOTrainer` + `PPOConfig` (stable, but being superseded by GRPO/RLOO).

#### XPO — Exploratory Preference Optimization

- **Paper**: Related to Nash-MD and online preference methods.
- **Key innovation**: Combines online DPO with exploration bonuses to encourage the model to explore diverse response strategies. Addresses the "mode collapse" problem in preference optimization.
- **Data format**: `{prompt}` + judge/reward model for online scoring.
- **TRL support**: `XPOTrainer` + `XPOConfig` (experimental). Supports vLLM.

#### Nash-MD — Nash Mirror Descent

- **Key innovation**: Game-theoretic approach to alignment. Treats alignment as finding the Nash equilibrium between the policy and a best-response opponent. Provides stronger theoretical guarantees than standard preference optimization.
- **Data format**: `{prompt}` + judge/reward model.
- **TRL support**: `NashMDTrainer` + `NashMDConfig` (experimental). Supports vLLM.

### 1.4 Self-Play and Iterative Methods (2024)

#### SPIN — Self-Play Fine-Tuning

- **Paper**: Chen et al., "Self-Play Fine-Tuning Converts Weak Language Models to Strong Language Models" (ICML 2024, UCLA)
- **arXiv**: [2401.01335](https://arxiv.org/abs/2401.01335)
- **Key innovation**: The LLM plays against previous versions of itself. In each iteration, the current model generates responses that the next iteration must distinguish from human-annotated responses. No additional human annotation required after initial SFT data. With a logistic loss, SPIN's training objective is equivalent to DPO loss.
- **Data format**: `{prompt, human_response}` — only SFT-quality data needed. The model itself generates the "rejected" responses from its previous iteration.
- **When to use**: When you only have SFT data (no preference pairs). When you want to squeeze more performance from existing human-annotated data without collecting new feedback. Can outperform DPO even when DPO has access to GPT-4 preference data.
- **TRL support**: Not natively supported. Requires custom implementation (iterate DPO with self-generated negatives).

#### Constitutional AI / RLAIF

- **Paper**: Bai et al., "Constitutional AI: Harmlessness from AI Feedback" (2022, Anthropic)
- **Key innovation**: Uses AI feedback instead of human feedback. A "constitution" (set of principles) guides the AI to critique and revise its own responses. Two phases: (1) supervised learning on AI-revised responses, (2) RLHF using AI-generated preference labels.
- **Data format**: Principles/constitution + prompts. AI generates, critiques, and revises autonomously.
- **When to use**: When human feedback is expensive or slow. When you have well-defined principles for desired behavior. Anthropic's Claude uses this extensively.
- **TRL support**: Not directly supported as a trainer. Can be implemented using SFTTrainer + DPOTrainer with AI-generated preference data.

### 1.5 Reinforcement Learning with Verifiable Rewards (2025-2026)

#### RLVR — RL with Verifiable Rewards

- **Not a single paper** — an emerging paradigm used by DeepSeek-R1, Tulu 3, and others.
- **Key innovation**: Uses objective, programmatically verifiable criteria as reward signals (e.g., "did the math answer match ground truth?" or "did the code pass the test suite?"). Binary rewards (correct/incorrect) rather than learned reward models. Eliminates reward hacking entirely for verifiable domains.
- **Data format**: `{prompt, ground_truth_answer}` + verification function.
- **When to use**: Math, coding, structured reasoning, any domain where correctness can be verified automatically. This is the dominant training paradigm for reasoning models in 2025-2026.
- **TRL support**: Implemented via `GRPOTrainer` with custom `reward_funcs` that verify correctness.
- **Production adoption**: DeepSeek-R1 (math/coding verification), QwQ, Kimi k1.5.

#### DAPO — Decoupled Clip and Dynamic Sampling Policy Optimization

- **Paper**: ByteDance Seed, "DAPO: An Open-Source LLM Reinforcement Learning System at Scale" (March 2025)
- **arXiv**: [2503.14476](https://arxiv.org/abs/2503.14476)
- **Key innovation**: Four techniques that improve on GRPO for long chain-of-thought (CoT) RL: (1) Clip-Higher — decouples clip ratios for up/down updates to prevent entropy collapse; (2) Dynamic Sampling — adjusts sample allocation based on problem difficulty; (3) Token-Level Policy Gradient — critical for long-CoT scenarios; (4) Overlong Reward Shaping — reduces reward noise for length-capped generations.
- **Data format**: Same as GRPO — `{prompt}` + verifiable reward function.
- **When to use**: When GRPO training is unstable on long-CoT tasks. When entropy collapse prevents exploration. Achieves 50 points on AIME 2024 (vs. 47 for DeepSeek-R1-Zero) with 50% fewer training steps.
- **TRL support**: Not natively supported (as of early 2026). Implemented in the `verl` framework. Could be implemented as custom modifications to `GRPOTrainer`.

### 1.6 Distillation and Knowledge Transfer Methods

#### GKD — Generalized Knowledge Distillation

- **TRL support**: `GKDTrainer` + `GKDConfig` (experimental, `trl.experimental.gkd`).
- **Purpose**: On-policy distillation training — train a smaller model to mimic a larger teacher model's behavior. Not strictly "alignment" but part of the post-training stack.
- **When to use**: Distilling a large aligned model into a smaller deployable model.

#### GOLD — General Online Logit Distillation

- **TRL support**: `GOLDTrainer` + `GOLDConfig` (experimental, `trl.experimental.gold`).
- **Purpose**: Online distillation where the teacher generates responses during training.

### 1.7 Additional DPO Variants (Available as loss_type in TRL)

These are not separate methods with independent papers but variants accessible through TRL's `DPOTrainer` `loss_type` parameter:

| loss_type        | Description                                           | Source               |
| ---------------- | ----------------------------------------------------- | -------------------- |
| `"sigmoid"`      | Standard DPO loss (default)                           | Rafailov et al. 2023 |
| `"ipo"`          | Identity Preference Optimization — regularized DPO    | Azar et al. 2023     |
| `"hinge"`        | Hinge loss on normalized likelihood                   | SLiC paper           |
| `"simpo"`        | Reference-free, length-normalized, with reward margin | Meng et al. 2024     |
| `"nca_pair"`     | Noise Contrastive Alignment for preference pairs      | Chen et al. 2024     |
| `"bco_pair"`     | Binary Classifier Optimization for preference pairs   | Jung et al. 2024     |
| `"exo_pair"`     | Exact Optimization variant                            | —                    |
| `"robust"`       | Robust DPO variant                                    | —                    |
| `"sppo_hard"`    | Self-Play Preference Optimization (hard variant)      | —                    |
| `"aot"`          | Alignment via Optimal Transport                       | —                    |
| `"aot_unpaired"` | AOT for unpaired data                                 | —                    |
| `"apo_zero"`     | Anchored Preference Optimization (zero variant)       | —                    |
| `"apo_down"`     | Anchored Preference Optimization (down variant)       | —                    |
| `"discopop"`     | Discovery of Preference Optimization                  | —                    |
| `"sft"`          | Pure SFT loss (no preference component)               | —                    |

**Important architectural note**: Many "methods" are actually just different loss functions applied within the same trainer infrastructure. TRL's `DPOTrainer` with `loss_type` parameter covers DPO, IPO, SimPO, NCA, BCO, and several others. This means kailash-align does NOT need a separate trainer wrapper for each method — it needs a configurable loss_type parameter on the existing DPO pipeline.

---

## 2. TRL Trainer Coverage (v1.0+, 2025-2026)

### 2.1 Stable API (Semantic Versioning Guaranteed)

These trainers are part of TRL's stable surface. API changes follow semantic versioning.

| Trainer         | Config         | Method                             | Data Format                  | vLLM Support |
| --------------- | -------------- | ---------------------------------- | ---------------------------- | ------------ |
| `SFTTrainer`    | `SFTConfig`    | Supervised Fine-Tuning             | `{text}` or chat format      | No           |
| `DPOTrainer`    | `DPOConfig`    | DPO + 14 loss variants             | `{prompt, chosen, rejected}` | No           |
| `RewardTrainer` | `RewardConfig` | Outcome Reward Model (ORM)         | `{prompt, chosen, rejected}` | No           |
| `RLOOTrainer`   | `RLOOConfig`   | REINFORCE Leave-One-Out            | `{prompt}` + reward_funcs    | Yes          |
| `GRPOTrainer`   | `GRPOConfig`   | Group Relative Policy Optimization | `{prompt}` + reward_funcs    | Yes          |

### 2.2 Experimental API (May Change Without Notice)

| Trainer            | Config            | Method                             | Data Format                   | vLLM Support |
| ------------------ | ----------------- | ---------------------------------- | ----------------------------- | ------------ |
| `OnlineDPOTrainer` | `OnlineDPOConfig` | Online DPO with judge/reward       | `{prompt}` + judge            | Yes          |
| `XPOTrainer`       | `XPOConfig`       | Exploratory Preference Opt.        | `{prompt}` + judge            | Yes          |
| `NashMDTrainer`    | `NashMDConfig`    | Nash Mirror Descent                | `{prompt}` + judge            | Yes          |
| `PPOTrainer`       | `PPOConfig`       | Proximal Policy Optimization       | `{prompt}` + reward model     | No           |
| `KTOTrainer`       | `KTOConfig`       | Kahneman-Tversky Optimization      | `{prompt, completion, label}` | No           |
| `CPOTrainer`       | `CPOConfig`       | Contrastive Preference Opt.        | `{prompt, chosen, rejected}`  | No           |
| `ORPOTrainer`      | `ORPOConfig`      | Odds Ratio Preference Opt.         | `{prompt, chosen, rejected}`  | No           |
| `BCOTrainer`       | `BCOConfig`       | Binary Classifier Opt.             | `{prompt, completion, label}` | No           |
| `PRMTrainer`       | `PRMConfig`       | Process Reward Model               | Step-level labels             | No           |
| `GKDTrainer`       | `GKDConfig`       | Generalized Knowledge Distillation | Teacher + student             | No           |
| `GOLDTrainer`      | `GOLDConfig`      | General Online Logit Distillation  | Teacher + student             | No           |

### 2.3 Methods NOT Directly Supported by TRL (Require Custom Implementation)

| Method                    | Why Not in TRL                                | Implementation Path                                           |
| ------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| SPIN (Self-Play)          | Iterative process, not a single training loop | Script that runs DPO iterations with self-generated negatives |
| DAPO                      | New (March 2025), in verl framework           | Fork GRPOTrainer with 4 DAPO modifications                    |
| Constitutional AI / RLAIF | Meta-process (generate + critique + RL)       | Pipeline of SFTTrainer + DPOTrainer with AI-generated data    |
| RLVR (generic)            | Paradigm, not algorithm                       | GRPOTrainer + custom verification reward_funcs                |

### 2.4 TRL API Surface for Each Trainer

#### GRPOTrainer (Most Important New Addition)

```python
from trl import GRPOTrainer, GRPOConfig

# Reward functions: sync or async, single or multiple
def accuracy_reward(completions, **kwargs) -> list[float]:
    """Return reward per completion."""
    return [1.0 if is_correct(c) else 0.0 for c in completions]

async def style_reward(completions, **kwargs) -> list[float]:
    """Async reward for I/O-bound evaluation."""
    return await evaluate_style(completions)

config = GRPOConfig(
    output_dir="./grpo_output",
    num_generations=16,           # Group size (completions per prompt)
    temperature=1.0,              # Sampling temperature
    max_completion_length=2048,   # Max tokens per completion
    beta=0.001,                   # KL penalty coefficient
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=3e-6,
    bf16=True,
)

trainer = GRPOTrainer(
    model="Qwen/Qwen2.5-7B-Instruct",
    reward_funcs=[accuracy_reward, style_reward],  # Multiple combinable
    reward_weights=[1.0, 0.5],                     # Optional weighting
    args=config,
    train_dataset=prompts_dataset,
)
trainer.train()
```

#### KTOTrainer

```python
from trl import KTOTrainer, KTOConfig

config = KTOConfig(
    output_dir="./kto_output",
    beta=0.1,
    desirable_weight=1.0,      # Weight for positive examples
    undesirable_weight=1.0,    # Weight for negative examples
    per_device_train_batch_size=4,
    bf16=True,
)

# Dataset: each row has either a chosen or rejected completion
# Column "label" is True (desirable) or False (undesirable)
trainer = KTOTrainer(
    model=model,
    args=config,
    train_dataset=binary_feedback_dataset,
    processing_class=tokenizer,
)
trainer.train()
```

#### ORPOTrainer

```python
from trl import ORPOTrainer, ORPOConfig

config = ORPOConfig(
    output_dir="./orpo_output",
    beta=0.1,                  # Odds ratio weight (lambda in paper)
    per_device_train_batch_size=4,
    bf16=True,
)

# Same data format as DPO: {prompt, chosen, rejected}
trainer = ORPOTrainer(
    model=model,
    args=config,
    train_dataset=preference_dataset,
    processing_class=tokenizer,
)
trainer.train()
```

#### RLOOTrainer

```python
from trl import RLOOTrainer, RLOOConfig

config = RLOOConfig(
    output_dir="./rloo_output",
    per_device_train_batch_size=4,
    num_generations=8,             # K completions per prompt
    temperature=0.7,
    bf16=True,
)

trainer = RLOOTrainer(
    model="Qwen/Qwen2.5-7B-Instruct",
    reward_funcs=accuracy_reward,  # Same interface as GRPO
    args=config,
    train_dataset=prompts_dataset,
)
trainer.train()
```

#### DPOTrainer with Variants

```python
from trl import DPOTrainer, DPOConfig

# Standard DPO
dpo_config = DPOConfig(output_dir="./dpo_output", beta=0.1, loss_type="sigmoid")

# IPO variant (better for small datasets)
ipo_config = DPOConfig(output_dir="./ipo_output", beta=0.1, loss_type="ipo")

# SimPO variant (reference-free, length-normalized)
simpo_config = DPOConfig(output_dir="./simpo_output", loss_type="simpo", simpo_gamma=0.5)

# NCA variant (explicit reward-aware)
nca_config = DPOConfig(output_dir="./nca_output", loss_type="nca_pair", beta=0.1)

# All use the same trainer class and data format
trainer = DPOTrainer(
    model=model,
    args=simpo_config,
    train_dataset=preference_dataset,
    processing_class=tokenizer,
)
```

---

## 3. RL-for-LLMs vs. Classical RL — Domain Boundary

### 3.1 The Two Domains

| Aspect               | LLM Alignment RL                                 | Classical RL                                        |
| -------------------- | ------------------------------------------------ | --------------------------------------------------- |
| **Environment**      | Token generation (autoregressive text)           | Gymnasium/MuJoCo/Atari environments                 |
| **State**            | Prompt + generated tokens so far                 | Environment observation (pixels, vectors)           |
| **Action**           | Next token (discrete, vocabulary-sized)          | Joint torques, movement directions                  |
| **Episode**          | One complete text generation                     | Hundreds/thousands of environment steps             |
| **Transition**       | Deterministic (given token, next state is known) | Stochastic (environment dynamics)                   |
| **Reward**           | End-of-sequence (sparse) or per-token            | Per-step (often dense)                              |
| **Critic necessity** | Low (deterministic transitions reduce variance)  | High (stochastic transitions need value estimation) |
| **Key libraries**    | TRL, verl, OpenRLHF                              | stable-baselines3, CleanRL, RLlib                   |
| **Key frameworks**   | HuggingFace transformers, vLLM                   | Gymnasium, MuJoCo, dm_control                       |

### 3.2 Why the Distinction Matters

PPO exists in both domains, but the implementations are fundamentally different:

**LLM PPO** (TRL `PPOTrainer`):

- Policy is a causal LM (billions of parameters)
- Actions are tokens from a vocabulary of 32K-128K
- Episodes are short (one response generation)
- Deterministic transitions mean simpler advantage estimation
- Reference model KL penalty replaces environment reward shaping

**Classical PPO** (stable-baselines3 `PPO`):

- Policy is a small MLP/CNN (thousands to millions of parameters)
- Actions are continuous (torque) or small discrete sets
- Episodes are long (hundreds of steps)
- Stochastic transitions require careful value function estimation
- No reference model concept

GRPO was designed specifically for LLMs — it exploits the deterministic transition property to eliminate the critic entirely. In classical RL, GRPO's group-relative baseline is less effective because stochastic transitions introduce variance that a learned value function handles better. Recent research (arXiv:2511.03527) explores GRPO in classical RL but finds PPO's critic still valuable in stochastic environments.

### 3.3 Boundary for kailash-align

```
kailash-align (LLM alignment)              kailash-ml[rl] (classical RL)
───────────────────────────────             ─────────────────────────────
GRPO, RLOO, PPO (TRL)                      PPO, SAC, TD3 (stable-baselines3)
DPO, KTO, ORPO, SimPO (TRL)                Q-learning, DQN (custom)
Reward modeling (TRL RewardTrainer)         Gymnasium environments
Verifiable rewards (RLVR)                   MuJoCo/Atari/custom envs

Policy = LLM (billions of params)           Policy = MLP/CNN (millions of params)
Environment = token generation              Environment = physics simulation

Dependencies: trl, transformers, vLLM       Dependencies: stable-baselines3, gymnasium
```

**Rule**: If the policy is a language model and the "environment" is text generation, it belongs in kailash-align. If the policy controls an agent in a simulated/real environment with observation-action-reward loops, it belongs in kailash-ml[rl].

---

## 4. Industry Trends 2025-2026

### 4.1 The Modern Post-Training Stack

The field has converged on a three-layer post-training stack:

```
Layer 1: SFT (Supervised Fine-Tuning)
    Purpose: Teach format, instruction following, conversational style
    Data: 1-10M curated instruction-response pairs
    Method: SFTTrainer (universally used, not controversial)

Layer 2: Preference Optimization (Offline)
    Purpose: Align with human preferences, safety, helpfulness
    Data: Pairwise preferences or binary feedback
    Methods: DPO (still dominant), SimPO (gaining), KTO (production-friendly)
    Trend: Moving toward reference-free methods (SimPO, ORPO)

Layer 3: RL with Verifiable Rewards (Online)
    Purpose: Reasoning improvement, code generation, math
    Data: Prompts + verification functions
    Methods: GRPO (dominant), RLOO (strong alternative), DAPO (emerging)
    Trend: Rapidly growing; the defining technique of 2025-2026
```

### 4.2 Method Adoption by Major Labs (2025-2026)

| Organization      | SFT | Preference Optimization   | Online RL                 |
| ----------------- | --- | ------------------------- | ------------------------- |
| **DeepSeek**      | Yes | DPO                       | GRPO (R1), RLVR           |
| **Meta/Llama**    | Yes | DPO + PPO (Llama 3)       | GRPO (Llama 4)            |
| **Anthropic**     | Yes | Constitutional AI (RLAIF) | PPO-based RLHF            |
| **OpenAI**        | Yes | Undisclosed (likely RLHF) | PPO + verifiers           |
| **Google**        | Yes | DPO variants              | REINFORCE variants        |
| **Alibaba/Qwen**  | Yes | DPO                       | GRPO (QwQ)                |
| **Moonshot/Kimi** | Yes | DPO                       | GRPO (k1.5)               |
| **NVIDIA**        | Yes | DPO                       | GRPO (Nemotron 3 Super)   |
| **HuggingFace**   | Yes | DPO/SimPO                 | GRPO/RLOO (open research) |

### 4.3 Key Trends

#### Trend 1: GRPO Has Replaced PPO for Most Use Cases

DeepSeek-R1's success made GRPO the default online RL method. PPO is now reserved for frontier labs with massive compute budgets. GRPO's advantages — no critic network, 50% less memory, simpler hyperparameter tuning — make it accessible to smaller teams. Recent research (arXiv:2510.00977) shows that 2-GRPO (just 2 completions per prompt) achieves performance on par with 16-GRPO at 1/8 the compute.

#### Trend 2: DPO Is Still Dominant but Being Augmented

DPO remains the most widely used preference optimization method, but production teams are increasingly pairing it with online RL (GRPO/RLOO) for reasoning tasks. The stack is becoming SFT -> DPO -> GRPO rather than SFT -> DPO alone. SimPO is gaining traction as a drop-in DPO replacement with better empirical results and no reference model overhead.

#### Trend 3: Verifiable Rewards Are the Future for Reasoning

The dominant 2025-2026 narrative: "LLM development is essentially dominated by reasoning models using RLVR and GRPO." Verifiable rewards eliminate reward hacking, provide unambiguous training signal, and scale without human annotators. The limitation is that RLVR only works for domains with verifiable answers (math, coding, logic). Open question: can RLVR be extended to open-ended generation (creative writing, summarization)?

#### Trend 4: Reference-Free Methods Are Winning

DPO requires a reference model (2x memory or implicit reference with training overhead). SimPO, ORPO, and CPO eliminate the reference model entirely. This is both a memory savings and a simplification. SimPO in particular shows strong results without a reference model, outperforming DPO on multiple benchmarks.

#### Trend 5: Binary Feedback Methods Gaining Production Traction

KTO's insight — that binary "good/bad" feedback is vastly more available than pairwise preferences — is validated by production experience. Companies with existing feedback systems (thumbs up/down, star ratings, report buttons) can use KTO directly without expensive preference pair curation.

#### Trend 6: Constitutional AI / RLAIF for Scaling Feedback

Human feedback does not scale. AI-generated feedback (RLAIF) is standard practice. The debate is now about _which_ AI feedback pipeline — LLM-as-judge (used in Online DPO), constitutional critique-and-revision, or automated verification.

### 4.4 Decision Matrix for kailash-align Users

| Your Situation                          | Recommended Method           | TRL Trainer                      | Priority  |
| --------------------------------------- | ---------------------------- | -------------------------------- | --------- |
| Standard SFT + preference alignment     | SFT -> DPO                   | SFTTrainer + DPOTrainer          | P0 (done) |
| Have binary feedback (thumbs up/down)   | KTO                          | KTOTrainer                       | P1        |
| Want simpler pipeline (no SFT step)     | ORPO                         | ORPOTrainer                      | P2        |
| Want better DPO without reference model | SimPO                        | DPOTrainer(loss_type="simpo")    | P1        |
| Math/coding reasoning improvement       | GRPO with verifiable rewards | GRPOTrainer                      | P1        |
| Want online improvement beyond data     | RLOO or GRPO                 | RLOOTrainer / GRPOTrainer        | P1        |
| Small dataset, overfitting concerns     | IPO                          | DPOTrainer(loss_type="ipo")      | P2        |
| Explicit numerical rewards available    | NCA                          | DPOTrainer(loss_type="nca_pair") | P3        |
| Only have SFT data, no preferences      | SPIN (iterative DPO)         | Custom (iterative DPO)           | P3        |
| Reasoning with long chain-of-thought    | DAPO                         | Custom (modified GRPO)           | P3        |

---

## 5. Impact Assessment for kailash-align

### 5.1 What Must Change in kailash-align

#### Current State

```
AlignmentConfig.method: "sft" | "dpo" | "sft_then_dpo"
Pipeline: SFTTrainer -> DPOTrainer (2 methods)
```

#### Required State

```
AlignmentConfig.method: "sft" | "dpo" | "sft_then_dpo" | "kto" | "orpo" | "grpo" | "rloo"
AlignmentConfig.dpo_loss_type: "sigmoid" | "ipo" | "simpo" | "nca_pair" | "hinge" | ...
Pipeline: SFTTrainer, DPOTrainer (14 variants), KTOTrainer, ORPOTrainer, GRPOTrainer, RLOOTrainer
```

#### Implementation Complexity Assessment

**Low complexity (config change only)**:

- IPO, SimPO, NCA, BCO, hinge, and all other DPO loss variants — these are a single `loss_type` parameter on the existing `DPOConfig`. The kailash-align `DPOConfig` dataclass needs a `loss_type` field. The `_run_dpo()` method passes it through to TRL. No new trainer code.

**Medium complexity (new trainer wrapper)**:

- KTO — new `KTOConfig` dataclass, new `_run_kto()` method, different data format (binary labels instead of preference pairs).
- ORPO — new `ORPOConfig` dataclass, new `_run_orpo()` method. Eliminates the SFT step (monolithic).
- CPO — can reuse DPO infrastructure with `loss_type` or use separate `CPOTrainer`.

**High complexity (new paradigm)**:

- GRPO — fundamentally different from DPO. Requires `reward_funcs` (callable functions), online generation, group sampling. New `GRPOConfig` dataclass, new `_run_grpo()` method.
- RLOO — similar to GRPO. Requires `reward_funcs`, online generation. New `RLOOConfig` dataclass, new `_run_rloo()` method.

### 5.2 Recommended Implementation Priority

**Phase 1 (v1.0 — minimal effort, high value)**:

1. Add `loss_type` parameter to `DPOConfig` — unlocks IPO, SimPO, NCA, and 11 other variants immediately.
2. Add `simpo_gamma` parameter to `DPOConfig` — needed when `loss_type="simpo"`.

**Phase 2 (v1.1 — new data formats)**: 3. Add `KTOConfig` + `_run_kto()` — unlocks binary feedback alignment. 4. Add `ORPOConfig` + `_run_orpo()` — unlocks monolithic SFT+preference in one step.

**Phase 3 (v1.2 — online RL)**: 5. Add `GRPOConfig` + `_run_grpo()` — unlocks reasoning improvement with verifiable rewards. 6. Add `RLOOConfig` + `_run_rloo()` — alternative to GRPO, simpler.

**Phase 4 (v2.0 — advanced)**: 7. Add `RewardModelConfig` + reward model training pipeline. 8. Add SPIN support (iterative DPO with self-generated negatives). 9. Add DAPO modifications to GRPO for long-CoT scenarios.

### 5.3 Data Format Summary

All methods in kailash-align need to support these data formats:

| Format                    | Columns                                                       | Used By                         |
| ------------------------- | ------------------------------------------------------------- | ------------------------------- |
| **Instruction**           | `{text}` or `{messages}` (chat format)                        | SFT                             |
| **Preference pairs**      | `{prompt, chosen, rejected}`                                  | DPO, IPO, SimPO, NCA, CPO, ORPO |
| **Binary feedback**       | `{prompt, completion, label}` (label = desirable/undesirable) | KTO, BCO                        |
| **Prompts + reward**      | `{prompt}` + `reward_func(completions) -> list[float]`        | GRPO, RLOO, Online DPO          |
| **Reward model training** | `{prompt, chosen, rejected}` + scalar scores                  | RewardTrainer                   |

### 5.4 Configuration Dataclass Design

```python
@dataclass(frozen=True)
class PreferenceConfig:
    """Configuration for preference optimization (DPO and all variants).

    Covers: DPO, IPO, SimPO, NCA, BCO, hinge, CPO, and 8 other loss variants.
    All accessible through a single TRL DPOTrainer with loss_type parameter.
    """
    loss_type: str = "sigmoid"       # "sigmoid", "ipo", "simpo", "nca_pair", etc.
    beta: float = 0.1                # KL penalty (interpretation varies by loss_type)
    simpo_gamma: float = 0.5         # Target reward margin (SimPO only)
    # ... standard training params (epochs, batch_size, lr, etc.)

@dataclass(frozen=True)
class KTOConfig:
    """Configuration for Kahneman-Tversky Optimization.
    Binary desirable/undesirable signal — no preference pairs needed.
    """
    beta: float = 0.1
    desirable_weight: float = 1.0
    undesirable_weight: float = 1.0
    # ... standard training params

@dataclass(frozen=True)
class GRPOConfig:
    """Configuration for Group Relative Policy Optimization.
    Online RL with verifiable rewards — no preference data needed.
    """
    num_generations: int = 16        # Group size per prompt
    temperature: float = 1.0         # Sampling temperature
    beta: float = 0.001              # KL coefficient
    max_completion_length: int = 2048
    # ... standard training params
    # Note: reward_funcs are passed to the pipeline, not config

@dataclass(frozen=True)
class ORPOConfig:
    """Configuration for Odds Ratio Preference Optimization.
    Monolithic SFT + preference in one step — no separate SFT phase.
    """
    beta: float = 0.1               # Lambda (odds ratio weight)
    # ... standard training params
```

---

## 6. References

### Core Papers

| Method            | Paper                                                                                       | Year | Venue        |
| ----------------- | ------------------------------------------------------------------------------------------- | ---- | ------------ |
| DPO               | Rafailov et al., "Direct Preference Optimization"                                           | 2023 | NeurIPS 2023 |
| IPO               | Azar et al., "A General Theoretical Paradigm to Understand Learning from Human Feedback"    | 2023 | NeurIPS 2023 |
| GRPO              | Shao et al., "DeepSeekMath"                                                                 | 2024 | arXiv        |
| DeepSeek-R1       | DeepSeek-AI, "DeepSeek-R1"                                                                  | 2025 | arXiv        |
| KTO               | Ethayarajh et al., "Model Alignment as Prospect Theoretic Optimization"                     | 2024 | ICML 2024    |
| ORPO              | Hong et al., "ORPO: Monolithic Preference Optimization without Reference Model"             | 2024 | EMNLP 2024   |
| SimPO             | Meng et al., "SimPO: Simple Preference Optimization with a Reference-Free Reward"           | 2024 | NeurIPS 2024 |
| RLOO              | Ahmadian et al., "Revisiting REINFORCE Style Optimization for Learning from Human Feedback" | 2024 | ACL 2024     |
| NCA               | Chen et al., "Noise Contrastive Alignment with Explicit Rewards"                            | 2024 | NeurIPS 2024 |
| CPO               | Xu et al., "Contrastive Preference Optimization"                                            | 2024 | ICML 2024    |
| BCO               | Jung et al., "Binary Classifier Optimization for LLM Alignment"                             | 2024 | arXiv        |
| SPIN              | Chen et al., "Self-Play Fine-Tuning Converts Weak to Strong LMs"                            | 2024 | ICML 2024    |
| DAPO              | ByteDance, "DAPO: An Open-Source LLM RL System at Scale"                                    | 2025 | arXiv        |
| PPO/RLHF          | Ouyang et al., "Training LMs to Follow Instructions with Human Feedback"                    | 2022 | NeurIPS 2022 |
| Constitutional AI | Bai et al., "Constitutional AI: Harmlessness from AI Feedback"                              | 2022 | arXiv        |

### Industry Analysis

| Source                                                     | URL                                                       | Date     |
| ---------------------------------------------------------- | --------------------------------------------------------- | -------- |
| "Post-Training in 2026: GRPO, DAPO, RLVR & Beyond"         | llm-stats.com/blog/research/post-training-techniques-2026 | 2026     |
| "The Production Alignment Stack"                           | medium.com/@adnanmasood                                   | Feb 2026 |
| "How to align open LLMs in 2025 with DPO & synthetic data" | philschmid.de                                             | 2025     |
| "It Takes Two: Your GRPO Is Secretly DPO"                  | arxiv.org/abs/2510.00977                                  | 2025     |
| TRL v1.0 Blog Post                                         | huggingface.co/blog/trl-v1                                | 2025     |

### TRL Documentation

| Resource                             | URL                                                  |
| ------------------------------------ | ---------------------------------------------------- |
| TRL Main Documentation               | https://huggingface.co/docs/trl/                     |
| TRL Trainer Index                    | https://huggingface.co/docs/trl/main/en/trainer      |
| GRPOTrainer Docs                     | https://huggingface.co/docs/trl/main/en/grpo_trainer |
| DPOTrainer Docs (loss_type variants) | https://huggingface.co/docs/trl/main/en/dpo_trainer  |
| TRL GitHub                           | https://github.com/huggingface/trl                   |

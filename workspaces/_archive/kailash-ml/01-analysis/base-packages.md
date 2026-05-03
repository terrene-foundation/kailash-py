# kailash-ml Base Packages

Complete list of all dependencies by tier with version pins.

## Tier 0: Core Data Libraries (always installed)

These ship with the base `pip install kailash-ml` alongside the Kailash ecosystem packages.

| Package | Version Pin | Size | Purpose |
|---------|------------|------|---------|
| polars | `>=1.0` | ~30MB | DataFrame library, Arrow-native. THE data type for all kailash-ml engines. |
| numpy | `>=1.26` | ~25MB | Array computation. Required by sklearn, lightgbm, scipy. Used at conversion boundaries only. |
| scipy | `>=1.12` | ~35MB | Statistics (KS test for DriftMonitor), optimization (Bayesian search for HyperparameterSearch). |
| plotly | `>=5.18` | ~15MB | Visualization. DataExplorer produces plotly Figures. |

## Base: Classical ML (in base, not optional)

These are in the BASE install. This is a deliberate decision: a base install that cannot train a model is useless.

| Package | Version Pin | Size | Purpose |
|---------|------------|------|---------|
| scikit-learn | `>=1.4` | ~30MB | Breadth library: every common algorithm (random forests, linear models, SVM, clustering, preprocessing). Used by FeatureEngineer (mutual_info scoring), TrainingPipeline (classical path), AutoMLEngine. |
| lightgbm | `>=4.3` | ~5MB | Production workhorse for gradient boosting. Faster than sklearn GBMs. Used as default baseline in AutoML guardrail 4. |
| skl2onnx | `>=1.16` | ~5MB | ONNX export for sklearn models. Required for the ONNX bridge. |
| onnxmltools | `>=1.12` | ~5MB | ONNX export for LightGBM, XGBoost, CatBoost. Required for the ONNX bridge. |

**Total base: ~195MB** (including Kailash ecosystem ~15MB for kailash + kailash-dataflow + kailash-nexus + kailash-ml-protocols)

## Kailash Ecosystem (always installed)

| Package | Version Pin | Purpose |
|---------|------------|---------|
| kailash | `>=1.0` | Core SDK: WorkflowBuilder, LocalRuntime, nodes |
| kailash-dataflow | `>=1.0` | FeatureStore storage, ModelRegistry metadata, DriftMonitor history |
| kailash-nexus | `>=1.0` | InferenceServer auto-endpoint registration, API exposure |
| kailash-ml-protocols | `>=1.0` | AgentInfusionProtocol, MLToolProtocol, FeatureSchema (circular dep resolution) |

## [dl]: Deep Learning (CPU)

Adds ~285MB on top of base for deep learning capabilities.

| Package | Version Pin | Size | Purpose |
|---------|------------|------|---------|
| torch | `>=2.2` | ~200MB (CPU) | PyTorch. Foundation for all deep learning in TrainingPipeline. |
| lightning | `>=2.2` | ~5MB | Training orchestration: distributed, mixed precision, checkpointing, logging. |
| torchvision | `>=0.17` | ~10MB (CPU) | Vision model building blocks. Required by timm. |
| torchaudio | `>=2.2` | ~10MB (CPU) | Audio model building blocks. |
| timm | `>=1.0` | ~5MB | 800+ pretrained vision models. Model definitions only (weights downloaded on demand). |
| transformers | `>=4.40` | ~50MB | HuggingFace transformers. Model loading, tokenizers. Required for NLP tasks. |
| onnxruntime | `>=1.17` | ~50MB (CPU) | ONNX model inference. The Python-side ONNX runtime for InferenceServer. |

## [dl-gpu]: Deep Learning (GPU)

Same as [dl] but with CUDA-enabled packages. ~2.5GB total due to CUDA toolkit.

| Package | Version Pin | Size | Notes |
|---------|------------|------|-------|
| torch | `>=2.2` | ~2.0GB | **Must install from CUDA index**: `--extra-index-url https://download.pytorch.org/whl/cu121` |
| lightning | `>=2.2` | ~5MB | Same as CPU |
| torchvision | `>=0.17` | ~30MB | CUDA variant |
| torchaudio | `>=2.2` | ~30MB | CUDA variant |
| timm | `>=1.0` | ~5MB | Same (model defs only) |
| transformers | `>=4.40` | ~50MB | Same |
| onnxruntime-gpu | `>=1.17` | ~200MB | GPU execution provider for ONNX |

**CUDA caveat**: PyTorch CUDA builds are NOT on PyPI. Users must supply `--extra-index-url`. The `kailash-ml-gpu-setup` CLI detects CUDA version and prints the correct command.

## [rl]: Classical Reinforcement Learning

Adds only ~15MB on top of [dl]. This is intentionally thin.

| Package | Version Pin | Size | Purpose |
|---------|------------|------|---------|
| stable-baselines3 | `>=2.3` | ~5MB | PPO, SAC, DQN, A2C algorithms for classical RL environments |
| gymnasium | `>=0.29` | ~10MB | RL environment interface (successor to OpenAI Gym) |

**TRL is NOT here.** TRL (for LLM fine-tuning) is in kailash-align, not kailash-ml. Classical RL (game agents, robotics) and LLM alignment are different domains with different users.

## [agents]: Kaizen Agent Infusion

| Package | Version Pin | Purpose |
|---------|------------|---------|
| kailash-kaizen | `>=1.0` | Provides Delegate, Signature, BaseAgent for ML agent infusion |

## Single-Package Extras

| Extra | Package | Version Pin | Size | Purpose |
|-------|---------|------------|------|---------|
| `[xgb]` | xgboost | `>=2.0` | ~15MB | Alternative gradient boosting (AutoML candidate) |
| `[catboost]` | catboost | `>=1.2` | ~100MB | Gradient boosting with native categorical support |
| `[stats]` | statsmodels | `>=0.14` | ~20MB | Classical time series (ARIMA, VAR, exponential smoothing) |

## Composite Extras

| Extra | Includes | Total Size (approx) |
|-------|----------|---------------------|
| `[full]` | dl + xgb + catboost + stats + rl + agents | ~530MB (CPU) |
| `[full-gpu]` | dl-gpu + xgb + catboost + stats + rl + agents | ~2.8GB |

## NOT in kailash-ml (lives in kailash-align)

These packages are explicitly NOT dependencies of kailash-ml. They belong to the kailash-align package:

| Package | Why NOT here |
|---------|-------------|
| trl | LLM fine-tuning (SFTTrainer, DPOTrainer) is alignment, not classical/DL ML |
| peft | LoRA/QLoRA adapters are for LLM fine-tuning |
| accelerate | Multi-GPU for LLM training (kailash-ml uses Lightning for DL multi-GPU) |
| bitsandbytes | 4-bit/8-bit quantization for QLoRA |
| datasets (HuggingFace) | Preference data for DPO. kailash-ml uses polars directly. |
| lm-eval | LLM evaluation benchmarks |

## Version Pinning Strategy

- **Minimum version only** (`>=X.Y`): for most packages. Allows users to bring their own compatible version.
- **Range pin** (`>=X.Y,<Z.0`): for Kailash ecosystem packages (`kailash>=1.0,<2.0`). Breaking changes in DataFlow/Nexus should not silently break kailash-ml.
- **No maximum version on ML libraries**: sklearn, lightgbm, torch evolve rapidly. Maximum pins would create dependency conflicts in user environments.

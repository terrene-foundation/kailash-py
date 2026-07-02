# Air-Gap Feasibility Analysis

## 1. HuggingFace Hub Offline Mode

### Built-in Mechanisms

HuggingFace provides three levels of offline support:

1. **`local_files_only=True`** parameter on `from_pretrained()`:

   ```python
   model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.2-8B", local_files_only=True)
   ```

   This prevents ALL network requests. If the model is not in the local cache, it raises an error immediately.

2. **`HF_HUB_OFFLINE=1`** environment variable:
   Sets offline mode globally for all HuggingFace Hub operations. Equivalent to `local_files_only=True` everywhere.

3. **`TRANSFORMERS_OFFLINE=1`** environment variable:
   Older mechanism, specific to transformers library. `HF_HUB_OFFLINE` is the preferred method.

### Pre-downloading Models

```python
from huggingface_hub import snapshot_download

# Download entire model repository
snapshot_download(
    repo_id="meta-llama/Llama-3.2-8B",
    cache_dir="/data/models",
    local_dir="/data/models/meta-llama--Llama-3.2-8B",
)
```

After downloading, the model can be loaded with:

```python
model = AutoModelForCausalLM.from_pretrained(
    "/data/models/meta-llama--Llama-3.2-8B",
    local_files_only=True,
)
```

### Cache Structure

HuggingFace uses `~/.cache/huggingface/hub/` by default. Can be overridden with `HF_HOME` or `HF_HUB_CACHE` env vars.

Cache layout:

```
~/.cache/huggingface/hub/
  models--meta-llama--Llama-3.2-8B/
    blobs/         # Actual file content (deduplicated by hash)
    refs/          # Branch/tag pointers
    snapshots/     # Revision directories with symlinks to blobs
```

## 2. What Breaks When There Is No Internet

### Things That Break

1. **Model downloads**: Obviously. Must be pre-cached.
2. **Tokenizer downloads**: Tokenizer files are separate from model weights and must also be cached.
3. **Dataset downloads**: HuggingFace `datasets` library downloads from the Hub by default. Must pre-download training data.
4. **lm-eval task definitions**: lm-eval-harness downloads task definitions and prompts from the internet. Must be pre-cached or use local task configs.
5. **`trust_remote_code=True` models**: Models that require remote code (custom architectures) cannot fully load in offline mode. The custom code files must already be in the cache.
6. **pip install**: Package installation requires internet. All Python packages must be pre-installed or transferred as wheels.
7. **llama.cpp tools**: If using pip to install `gguf` package, must be pre-installed.
8. **Ollama model pulls**: `ollama pull` requires internet. Models must be created locally via `ollama create`.

### Things That Work Fine Offline

1. **`from_pretrained()` with local path**: Loading from a local directory works perfectly offline.
2. **PEFT adapter loading**: `PeftModel.from_pretrained()` with local path works.
3. **TRL training**: Once model, tokenizer, and dataset are local, training is fully local.
4. **GGUF conversion**: `convert_hf_to_gguf.py` is a local script operating on local files.
5. **Ollama inference**: Ollama runs entirely locally once the model is created.
6. **vLLM inference**: vLLM loads local model files.

### Subtle Gotcha: HEAD Requests

Even with `local_files_only=True`, some HuggingFace library paths may attempt a HEAD request to check for newer versions. This silently fails in air-gapped environments (timeout, then falls back to cache), but it adds latency on first load. Setting `HF_HUB_OFFLINE=1` suppresses even these requests.

## 3. Is `OnPremModelCache` Just a Wrapper Around HF_HOME?

### Honest Assessment: Mostly Yes

Looking at the architecture doc, `OnPremModelCache` provides:

| Method                            | What It Does                       | HF Equivalent                                              |
| --------------------------------- | ---------------------------------- | ---------------------------------------------------------- |
| `download(model_id, cache_dir)`   | Downloads model to local directory | `snapshot_download(repo_id, cache_dir)`                    |
| `list(cache_dir)`                 | Lists cached models with sizes     | `scan_cache_dir()` from huggingface_hub                    |
| `verify(model_id, cache_dir)`     | Checks model files are complete    | `scan_cache_dir()` + file integrity check                  |
| `cache_path(model_id, cache_dir)` | Returns local path                 | `snapshot_download(repo_id, local_dir_use_symlinks=False)` |

**Every one of these methods has a direct HuggingFace Hub equivalent.**

### What OnPremModelCache Adds Over Raw HuggingFace

1. **Simplified API**: One method call vs. understanding HuggingFace cache internals. The `cache_path()` method abstracts away the symlink/blob structure.

2. **Verification**: HuggingFace `scan_cache_dir()` can list cached models but doesn't verify file integrity (SHA256 checksums). OnPremModelCache.verify() should check file sizes and optionally checksums.

3. **CLI experience**: `kailash-align-prepare` CLI provides a guided workflow for downloading before going air-gapped. Without it, users must know the HuggingFace CLI (`huggingface-cli download ...`).

4. **Integration with OnPremConfig**: When `offline_mode=True`, all kailash-align components automatically use the cache directory. Without this, users must set `HF_HUB_OFFLINE=1` and `HF_HUB_CACHE` manually in every process.

### Verdict

OnPremModelCache is a **thin convenience wrapper** with moderate value. The CLI experience (`kailash-align-prepare`) is the highest-value piece -- it turns a multi-step manual process into guided commands. The library API itself is low value over raw HuggingFace Hub utilities.

## 4. Practical Air-Gap Deployment Workflow

### Phase 1: Preparation (Internet Available)

```bash
# 1. Install all Python packages
pip install kailash-align[full]

# 2. Download base model
kailash-align-prepare download --model meta-llama/Llama-3.2-8B --cache-dir /data/models

# 3. Download training data (if from HuggingFace)
python -c "from datasets import load_dataset; load_dataset('tatsu-lab/alpaca', cache_dir='/data/datasets')"

# 4. Download lm-eval tasks (if using standard benchmarks)
# lm-eval caches task configs on first use

# 5. Verify everything
kailash-align-prepare verify --model meta-llama/Llama-3.2-8B --cache-dir /data/models

# 6. Install Ollama + llama.cpp tools
# (system admin responsibility)
```

### Phase 2: Transfer to Air-Gapped Environment

Transfer `/data/models`, `/data/datasets`, and the Python environment to the target machine. This is an organizational/sysadmin task, not a kailash-align task.

### Phase 3: Training + Deployment (Offline)

```python
from kailash_align import AlignmentPipeline, OnPremConfig

config = OnPremConfig(
    model_cache_dir="/data/models",
    offline_mode=True,
    ollama_host="http://localhost:11434",
)

pipeline = AlignmentPipeline(registry=registry, onprem_config=config)
# All from_pretrained() calls now use local_files_only=True
```

## 5. How Many Users Actually Need This?

### Target Audience

Air-gapped deployment is relevant for:

- **Government/defense contractors**: Common requirement, hard mandate
- **Healthcare organizations**: HIPAA environments sometimes restrict internet access
- **Financial institutions**: Sensitive data processing in isolated networks
- **Research institutions**: HPC clusters with limited internet access

### Realistic Assessment

The brief states this is for "on-prem secured environments." The full air-gap (zero internet) is the extreme case. Most on-prem deployments have:

- **Restricted internet**: Firewall rules, proxy-only access -- `HF_HUB_OFFLINE=1` + manual downloads is sufficient
- **Full air-gap**: No internet at all -- needs the full OnPremModelCache + CLI workflow

**Estimate**: Maybe 10-20% of kailash-align users will need full air-gap support. But for those who need it, it is a hard requirement -- not a nice-to-have.

### YAGNI Assessment

Air-gap support is **low code volume** (OnPremModelCache is ~150 lines, CLI is ~200 lines, OnPremConfig is ~20 lines) with **high value for the users who need it**. The main cost is testing -- verifying that offline mode actually works end-to-end requires manual testing with network disabled.

**Verdict**: Keep in v1 scope. The implementation cost is low and the value for the target audience (on-prem SLM deployment) is high. Without air-gap support, those users cannot use kailash-align at all.

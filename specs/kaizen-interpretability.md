# Kailash Kaizen Interpretability — Open-Weight LLM Diagnostics Adapter

Version: 2.13.1
Package: `kailash-kaizen`
Parent domain: Kaizen AI agent framework. This spec covers the post-hoc interpretability adapter that introspects local open-weight language models (Llama / Gemma / Phi / Mistral). It lives alongside other Diagnostic adapters (`specs/ml-diagnostics.md` for `DLDiagnostics`, forthcoming `kaizen-rag.md` for `RAGDiagnostics`, `kaizen-alignment.md` for `AlignmentDiagnostics`, etc.).
Scope authority: `kaizen.interpretability.InterpretabilityDiagnostics` and the `kaizen.interpretability` facade module; the conformance contract against `kailash.diagnostics.protocols.Diagnostic`; the extras-gating contract for the `[interpretability]` extra.

Status: LIVE — landed in kailash-kaizen 2.8.0. PR#4 of 7 for the MLFP diagnostics donation plan tracked in kailash-py issue #567.

Origin: Originally contributed from MLFP module `mlfp06/diagnostics/interpretability.py` (Apache-2.0). Re-authored for the Kailash ecosystem with medical metaphors stripped, the transformer backend moved from `transformer_lens` / `nnterp` to pure `transformers` for wider compatibility, and bounded-memory discipline applied (deque maxlen) to every per-analysis buffer.

---

## 1. Scope

### 1.1 In Scope

This spec is authoritative for:

- **`InterpretabilityDiagnostics` adapter** — context-manager session that operates on a local open-weight `transformers.PreTrainedModel` loaded lazily on first method call.
- **Diagnostic Protocol conformance** — `kaizen.interpretability.InterpretabilityDiagnostics` MUST satisfy the `@runtime_checkable` Protocol at `kailash.diagnostics.protocols.Diagnostic` (`run_id` + `__enter__` + `__exit__` + `report()`).
- **Attention heatmaps** — per-layer per-head token-to-token attention weights, recorded to a bounded-memory deque and rendered as plotly heatmaps.
- **Logit lens** — early-exit top-`k` predictions per transformer block via the shared unembedding, returned as a polars DataFrame and rendered as plotly bar charts.
- **Linear probes** — scikit-learn logistic regression on last-token hidden states at a chosen layer with cross-validated accuracy.
- **SAE features (optional)** — pre-trained sparse autoencoder (Gemma Scope, TransformerLens-compatible releases) top-`k` feature activations via `sae-lens`. Gated by the `[interpretability]` extra.
- **Bounded memory** — every per-analysis buffer uses `deque(maxlen=window)` so long sessions on large models cannot exhaust VRAM or host RAM.
- **Open-weight refusal** — API-only model prefixes (`gpt-*`, `o1-*`, `o3-*`, `o4-*`, `claude-*`, `gemini-*`, `deepseek-*`) are refused with a canonical `{"mode": "not_applicable"}` reading. No fake readings per `rules/zero-tolerance.md` Rule 2.
- **Local-files-only default** — `from_pretrained(local_files_only=True)` is the default so a diagnostic call NEVER silently downloads multi-GB over the network. `allow_download=True` opts in explicitly.
- **Cross-SDK contract** — how the Python `InterpretabilityDiagnostics` correlates with the cross-SDK `kailash.diagnostics.protocols` surface.

### 1.2 Out of Scope

- **The Diagnostic Protocol itself** — defined in `src/kailash/diagnostics/protocols.py` (PR#0) and is cross-SDK canonical. This spec references it as a dependency but does not define it.
- **Training the open-weight model** — pre-training and fine-tuning are the domain of `specs/alignment-training.md`. `InterpretabilityDiagnostics` is a read-only instrument.
- **Training SAEs** — students do NOT train SAEs here. `sae_features()` loads pre-trained Gemma Scope / compatible releases via `sae-lens` and reads the top-`k` activations.
- **LLM API diagnostics** — GPT / Claude / Gemini reasoning traces belong under `kaizen-agents-core.md` / `kaizen-advanced.md` telemetry, not this adapter.
- **Running inference workloads** — production serving belongs to `kaizen-llm-deployments.md`.
- **Other diagnostic adapters** — `DLDiagnostics` (PR#1, ml-diagnostics.md), `RAGDiagnostics` (PR#2), `AlignmentDiagnostics` (PR#3), `LLMDiagnostics` (PR#5), `AgentDiagnostics` (PR#6), `GovernanceEngine` extensions (PR#7) each land in their own package with their own spec.

---

## 2. Protocol Conformance Contract

### 2.1 Diagnostic Protocol Shape

The `Diagnostic` Protocol lives in `src/kailash/diagnostics/protocols.py`:

```python
@runtime_checkable
class Diagnostic(Protocol):
    run_id: str
    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]: ...
    def report(self) -> dict[str, Any]: ...
```

### 2.2 MUST Conformance Contract

The `InterpretabilityDiagnostics` adapter MUST:

1. Expose `run_id: str` as a public instance attribute populated in `__init__`. Defaulted to `uuid.uuid4().hex` when the caller omits it; honored verbatim when the caller supplies a non-empty string.
2. `__enter__` returns `self`.
3. `__exit__` returns `Optional[bool]` — never raises from `__exit__`; always runs `close()` to release the model + clear the CUDA / MPS cache.
4. `report() -> dict[str, Any]` is callable at any time (including on an empty session with no analysis calls) and never raises.
5. `isinstance(obj, Diagnostic)` returns `True` at runtime — the Protocol is `@runtime_checkable` and the Tier 2 wiring test MUST assert this (see `tests/integration/interpretability/test_interpretability_wiring.py::test_protocol_conformance_on_real_construction`).

**Why:** Downstream consumers use `isinstance(obj, Diagnostic)` for type-safe Protocol dispatch (e.g., a generic `record_diagnostic(d: Diagnostic)` sink in a telemetry pipeline or a GovernanceEngine audit chain). If conformance breaks, every downstream consumer silently skips the adapter.

### 2.3 `report()` Return Shape

`InterpretabilityDiagnostics.report()` returns a dict with this exact structure when the model is open-weight:

```python
{
    "run_id": str,                           # echoes self.run_id
    "model_name": str,                       # echoes self.model_name
    "mode": "real",
    "attention_heatmaps": int,               # count recorded
    "logit_lens_sweeps": int,                # count recorded
    "linear_probes": {                       # {"count": int} on empty
        "count": int,
        "last_accuracy": float,              # present iff count > 0
        "last_layer": int,                   # present iff count > 0
    },
    "sae_feature_reads": int,                # count recorded
    "messages": list[str],                   # human-readable summary lines
}
```

And this shape when the model is API-only (see §3.5):

```python
{
    "run_id": str,
    "model_name": str,
    "mode": "not_applicable",
    "attention_heatmaps": 0,
    "logit_lens_sweeps": 0,
    "linear_probes": {"count": 0},
    "sae_feature_reads": 0,
    "messages": [str],                       # explains why
}
```

---

## 3. `InterpretabilityDiagnostics` Public API

### 3.1 Construction

```python
from kaizen.interpretability import InterpretabilityDiagnostics

InterpretabilityDiagnostics(
    *,
    model_name: str = "google/gemma-2-2b",
    device: Optional[str] = None,            # auto: cuda > mps > cpu
    dtype: str = "float16",                  # "float16" | "bfloat16" | "float32"
    window: int = 4096,                      # >= 1, bounded-memory cap
    run_id: Optional[str] = None,            # UUID4 hex if omitted
    local_files_only: bool = True,
    allow_download: bool = False,            # opt in to network fetch
)
```

**Raises:**

- `TypeError` if `model_name` is not a string.
- `ValueError` if `model_name` is empty, `window < 1`, `run_id == ""`, or `dtype` outside the allowed set.

**Device resolution:** `cuda` > `mps` > `cpu`. A partially-broken GPU probe falls back to CPU rather than crashing session construction (DEBUG-logged as `interpretability.device_resolver_failed`).

**Security posture:** `local_files_only=True` is the default. A diagnostic call NEVER silently downloads multi-GB weights; operators pass `allow_download=True` to opt in.

### 3.2 Context-Manager Semantics

```python
with InterpretabilityDiagnostics(model_name="google/gemma-2-2b") as diag:
    diag.attention_heatmap("the cat sat", layer=0, head=0)
    ...
# model + tokenizer released; CUDA/MPS caches cleared on __exit__.
```

- `__enter__` returns `self` per Protocol §2.2 item 2.
- `__exit__` always calls `close()` and returns `None`.
- `close()` is idempotent — repeat calls are safe.

### 3.3 Analysis Methods

| Method                                                                          | Returns          | Records                                                                                                                       |
| ------------------------------------------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `attention_heatmap(prompt, *, layer, head, run_id=None)`                        | plotly Figure    | `_AttentionRecord(run_id, layer, head, tokens, matrix)` into `_attention_log` deque.                                          |
| `logit_lens(prompt, *, top_k, run_id=None)`                                     | polars DataFrame | One summary dict into `_logit_log` deque; DataFrame returned to the caller with `layer`/`rank`/`token`/`prob`/`mode` columns. |
| `probe(prompts, labels, *, layer, run_id=None)`                                 | dict             | `{run_id, layer, n_prompts, n_classes, cv_accuracy, mode}` into `_probe_log` deque AND returned to the caller.                |
| `sae_features(prompt, *, layer, top_k, release=None, sae_id=None, run_id=None)` | polars DataFrame | DataFrame with `feature_index`/`activation`/`mode` returned; summary dict into `_sae_log` deque.                              |

**Bounded memory:** every deque uses `maxlen=self.window` so long sessions on large models cannot exhaust VRAM or host RAM. The `window` parameter defaults to 4096 — enough for a 32-layer model at `top_k=10` logit-lens sweeps without risk.

**run_id correlation:** every recorded row carries a per-reading `run_id = f"{self.run_id}-<method>-<12 hex>"`. Callers who want to correlate a specific reading across logs / events use that ID; the session-level `self.run_id` appears in `report()`.

### 3.4 Plotting Surface

Plotting methods route through `_require_plotly()` / `_require_matplotlib()` helpers that raise a loud `ImportError` naming the `[interpretability]` extra if the library is absent.

| Method                           | Backend | Notes                                                                        |
| -------------------------------- | ------- | ---------------------------------------------------------------------------- |
| `plot_attention_heatmap(record)` | plotly  | Called internally by `attention_heatmap`; exposed for post-hoc re-rendering. |
| `plot_logit_lens(df)`            | plotly  | Bar chart of top-1 probability per layer.                                    |

Future expansions (`plot_probe_trajectory`, `plot_sae_features`) land in the same `[interpretability]`-gated module.

### 3.5 API-Only Refusal

When `model_name` matches an API-only prefix (`gpt-*`, `o1-*`, `o3-*`, `o4-*`, `claude-*`, `gemini-*`, `deepseek-*`):

- `_load_model()` raises `RuntimeError` with guidance to use an open-weight model.
- `attention_heatmap` / `logit_lens` / `probe` / `sae_features` each return the canonical not-applicable payload WITHOUT raising — the logic is a static safety guard on a configuration string, not an agent decision path (permitted per `rules/agent-reasoning.md` § "Permitted Deterministic Logic" item 4).
- `report()` returns `mode="not_applicable"` with a single message explaining why.

**Why:** The adapter needs hidden states, attention matrices, and access to the unembedding matrix. API providers serve tokens, not weights — there is no meaningful interpretability reading to produce. Refusing is honest failure; returning fabricated readings would violate `rules/zero-tolerance.md` Rule 2 ("no fake readings").

---

## 4. Extras Gating Contract

The `[interpretability]` extra declares:

```toml
interpretability = [
    "transformers>=4.40,<5.0",
    "sae-lens>=3.0",
]
```

Additional deps are loaded per method:

- `attention_heatmap` / `logit_lens` / `probe` / `sae_features` require `torch` — imported via `_require_torch()`. `torch` is a base dep of kaizen-ml / kaizen but not of kailash-kaizen core; when absent, a loud `ImportError` names the `[interpretability]` extra as the remedy.
- `probe` requires `scikit-learn` — imported via `_require_sklearn()`.
- `sae_features` requires `sae-lens` — imported via `_require_sae_lens()`.
- Plotting methods require `plotly` — imported via `_require_plotly()`.

Every helper raises:

```
ImportError: "<method> require <library>. Install the interpretability extras: pip install kailash-kaizen[interpretability]"
```

This satisfies `rules/dependencies.md` § "Optional Extras with Loud Failure". Silent degradation to `None` is BLOCKED.

---

## 5. VRAM & Memory Budget Guidance

Large open-weight models (Gemma-2-9B in float16 is ~18 GB) make memory discipline load-bearing:

- `dtype="float16"` halves VRAM vs float32. `dtype="bfloat16"` on Ampere / MI250 / newer for numerical stability parity with training.
- `window` caps each per-analysis deque. 4096 is safe for a 32-layer model at `top_k=10` (roughly 32 × 10 × 80 bytes per logit-lens sweep = 25 KB / sweep — 4096 sweeps = 100 MB worst case). Larger models or `top_k=50` should reduce `window` proportionally.
- `close()` on context exit clears CUDA + MPS caches. Callers running long-lived processes (dashboards, CI jobs) MUST wrap each session in a `with` block or call `close()` manually.
- A partially-broken GPU driver falls back to CPU at construction time — the `_resolve_device` helper catches every probe exception and DEBUG-logs `interpretability.device_resolver_failed` without crashing the session.

---

## 6. Observability Contract

Every method emits structured INFO logs with `interp_*` domain-prefixed field names per `rules/observability.md` MUST Rule 9 (LogRecord collides on `module` / `filename` / etc.):

| Event                         | Fields                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `interp_diagnostics.init`     | `interp_model_name`, `interp_device`, `interp_dtype`, `interp_window`, `interp_run_id`, `interp_local_files_only` |
| `interp.load_model.start`     | `interp_model_name`, `interp_device`, `interp_dtype`, `interp_local_files_only`, `interp_run_id`                  |
| `interp.load_model.ok`        | `interp_model_name`, `interp_n_layers`, `interp_run_id`                                                           |
| `interp.attention_heatmap.ok` | `interp_run_id`, `interp_layer`, `interp_head`, `interp_n_tokens`, `interp_mode`                                  |
| `interp.logit_lens.ok`        | `interp_run_id`, `interp_n_layers`, `interp_top_k`, `interp_mode`                                                 |
| `interp.probe.ok`             | `interp_run_id`, `interp_layer`, `interp_n_prompts`, `interp_n_classes`, `interp_cv_accuracy`, `interp_mode`      |
| `interp.sae_features.ok`      | `interp_run_id`, `interp_layer`, `interp_top_k`, `interp_mode`                                                    |
| `interp.not_applicable`       | `interp_method`, `interp_model_name`, `interp_mode`, `interp_run_id`                                              |

**Why:** All correlation IDs route through `interp_run_id` so a downstream aggregator can `WHERE interp_run_id = ?` and reconstruct the full session without reading raw prompt text (which may be user-sensitive).

No user-supplied prompt text is emitted to logs. Operators who need a correlation hook between prompt and log emit a hash via `_fingerprint_prompt()` (8 hex chars, sha256) outside the adapter and bind it to their own structured-log scope.

---

## 7. Security Threats & Mitigations

### 7.1 Threat: Silent multi-GB download during a diagnostic call

**Mitigation:** `local_files_only=True` is the default. Operators opt in via `allow_download=True`. No network fetch without an explicit flag.

### 7.2 Threat: HF auth token hardcoded in source

**Mitigation:** Token read from `HF_TOKEN` / `HUGGINGFACE_TOKEN` environment variables only, via `os.environ.get`. No CI artifact / tarball contains a hardcoded token. Per `rules/security.md` § "No Hardcoded Secrets".

### 7.3 Threat: Prompt content leaked in structured logs

**Mitigation:** No log emits the raw prompt. Correlation by `interp_run_id` only; operators who need prompt-level correlation use the adapter's `_fingerprint_prompt` helper to emit an 8-hex-char fingerprint outside the structured-log scope. Per `rules/observability.md` § "Never Log Secrets, Tokens, or PII".

### 7.4 Threat: Arbitrary code execution via tokenizer / model file parsing

**Mitigation:** No `eval` / `exec` / `subprocess` invocations anywhere on the adapter path. All parsing delegated to the `transformers` library's built-in safetensors / tokenizers code paths, which are audited upstream.

### 7.5 Threat: VRAM exhaustion from long-running session

**Mitigation:** Every per-analysis buffer uses `deque(maxlen=window)` (default 4096). `close()` on context exit clears CUDA / MPS caches. Operators tune `window` downward for very large models (see §5).

### 7.6 Threat: API-only model silently returns fabricated readings

**Mitigation:** API-only prefixes (`gpt-*`, `o1-*`, `o3-*`, `o4-*`, `claude-*`, `gemini-*`, `deepseek-*`) are detected at method-call time via a static prefix check. Every method returns the canonical `{"mode": "not_applicable"}` payload instead of hallucinating a reading. Per `rules/zero-tolerance.md` Rule 2.

---

## 8. Testing Contract

### 8.1 Tier 1 Unit Tests

Location: `packages/kailash-kaizen/tests/unit/interpretability/test_interpretability_diagnostics_unit.py`.

MUST cover:

- `__init__` input validation — TypeError on non-string model_name, ValueError on empty string / `window < 1` / empty `run_id` / unknown `dtype`.
- `run_id` autogen + uniqueness + explicit override.
- Protocol conformance via `isinstance(diag, Diagnostic)`.
- Context-manager `__enter__ == diag`; `__exit__` closes cleanly.
- `report()` callable on empty session (never raises).
- API-only refusal across every prefix variant; open-weight identifiers classified correctly.
- `_load_model()` refuses API-only with `RuntimeError`.
- Probe input validation (length mismatch, single-class rejection).
- Linear-probe math on synthetic linearly-separable features via `sklearn.linear_model.LogisticRegression` + `cross_val_score` directly (does not require `transformers`).
- Default SAE release resolution.
- `_fingerprint_prompt` determinism + 8-hex-char contract.
- `close()` idempotent.
- `local_files_only=True` by default; `allow_download=True` overrides it.

### 8.2 Tier 2 Integration Tests

Location: `packages/kailash-kaizen/tests/integration/interpretability/test_interpretability_wiring.py`.

MUST:

1. Import through the facade: `from kaizen.interpretability import InterpretabilityDiagnostics` (NOT the concrete `core` module) per `rules/orphan-detection.md` §1.
2. Use `pytest.importorskip("transformers", "torch")` so missing extras skip cleanly.
3. Exercise Protocol conformance via `isinstance(diag, Diagnostic)` against a real construction.
4. Verify `run_id` propagation from `__init__` through `report()["run_id"]`.
5. Drive a real forward pass on `sshleifer/tiny-gpt2` (skipif not in HF cache — per `rules/testing.md` Test-Skip Triage ACCEPTABLE tier, infra-conditional) and assert:
   - `attention_heatmap` records one reading + returns a plotly Figure.
   - `logit_lens` produces a non-empty polars DataFrame with the expected column set.
   - `probe` yields a cv_accuracy in `[0, 1]` with `mode="real"`.
   - `deque(maxlen=window)` bounded-memory cap is honoured.
6. Exercise the full wiring (facade → API-only refusal → empty DataFrame) without requiring the HF cache.

### 8.3 Collect-Only Gate

`pytest --collect-only -q packages/kailash-kaizen/tests/` MUST exit 0 per `rules/orphan-detection.md` §5 + §5a (per-package collection allowed).

### 8.4 Medical-Metaphor Sweep

`grep -ri 'stethoscope\|x-ray\|ECG\|flight recorder\|endoscope' packages/kailash-kaizen/` MUST return empty. This spec authoring removed medical metaphors from the MLFP source (the MLFP docstring referred to "the X-Ray" — re-authored to production-neutral language).

---

## 9. Attribution

**MLFP donation:** `InterpretabilityDiagnostics` originates from the MLFP `mlfp06/diagnostics/interpretability.py` module (Apache-2.0). Re-authored for the Kailash ecosystem with:

- Medical metaphors ("The X-Ray" / "attention lens") stripped — production-neutral `InterpretabilityDiagnostics` naming.
- Transformer backend switched from `transformer_lens` / `nnterp` to pure `transformers` for compatibility with the broader HuggingFace ecosystem. `sae-lens` retained as an optional dep for SAE features.
- Bounded-memory discipline applied — every per-analysis buffer is a `deque(maxlen=window)` rather than an unbounded list.
- `local_files_only=True` default — no silent multi-GB downloads during diagnostic calls.
- Structured observability with `interp_*` domain-prefixed field names per `rules/observability.md` MUST Rule 9.
- Protocol conformance against `kailash.diagnostics.protocols.Diagnostic` added on top of the original class shape.

**kailash-py issue #567:** PR#4 of 7 in the cross-SDK Diagnostic Protocol adoption plan. See `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md` for the full 7-PR sequence.

---

## 10. Cross-SDK Contract

**Rust equivalent:** This adapter does NOT have a Rust counterpart (kailash-rs does not ship a transformers wrapper). The Diagnostic Protocol IS cross-SDK (PR#0) so Rust-side diagnostic sinks that consume `interp_run_id` correlation and hashed prompt fingerprints will interop correctly with Python-emitted readings when both SDKs participate in a polyglot deployment. See `rules/cross-sdk-inspection.md` §3a — this spec documents the structural API divergence (Python has the adapter, Rust does not).

---

## 11. Deprecation & Forward Compatibility

- `transformers>=4.40,<5.0` is the floor (capped to protect against a 5.0 breaking change that has not yet shipped). When 5.0 lands the cap is revisited per `rules/dependencies.md` § "Latest Versions Always".
- `sae-lens>=3.0` is the floor; the `SAE.from_pretrained` return tuple shape changed in 3.0 and is handled defensively.
- The `mode` key in DataFrame outputs is reserved — future expansions (`"cached"`, `"interpolated"`) MUST NOT collide with `"real"` or `"not_applicable"`.
- The API-only prefix list is intentionally a small static set. Expanding it is a backward-compatible change; shrinking it (accepting an API-only model as real) is BREAKING because downstream alerting pipelines rely on the refusal shape.

# Issue #700 — `InferenceServer` Hard-Break Analysis

Filed 2026-04-28 from MLFP M5 sweep. Cross-SDK audit confirms Python-only.

## 1. Current 1.5.x surface

Canonical file: `packages/kailash-ml/src/kailash_ml/serving/server.py:254`. Reachable as `kailash_ml.InferenceServer` via lazy `__getattr__` only (`packages/kailash-ml/src/kailash_ml/__init__.py:614` — entry `"InferenceServer": "kailash_ml.serving.server"`). NOT in canonical `__all__` (§15.9 group-set; lines 667–727).

Constructor (`server.py:276–299`):

```python
def __init__(self, config: InferenceServerConfig, *,
             registry: "ModelRegistry", server_id: Optional[str] = None) -> None:
```

Public surface — properties: `config`, `server_id`, `status`, `bindings`, `model_signature` (lines 304–324). Async methods: `start() -> ServeHandle` (line 410), `from_registry(model_uri_or_name, *, registry, alias=, version=, tenant_id=, channels=, runtime=, batch_size=, server_id=) -> InferenceServer` (classmethod, line 329). `predict()` and `stop()` continue past line 500 (not read in full but referenced at lines 267–269).

`InferenceServerConfig` (`server.py:172–234`, frozen+slots dataclass): `tenant_id: Optional[str]`, `model_name: str`, `model_version: int`, `alias`, `channels: tuple[str, ...] = ("rest",)`, `runtime: Literal["onnx","pickle"] = "onnx"`, `batch_size: Optional[int] = None`. `__post_init__` validates non-empty model_name, version ≥ 1, runtime ∈ ALLOWED_RUNTIMES, channels non-empty subset of ALLOWED_CHANNELS, batch_size ≥ 1 or None.

`from_registry` semantics (lines 329–405): resolves `name@alias`/`name:version` via registry, returns a SINGLE-MODEL server pre-attached `_LoadedModel(model_version=..., onnx_bytes=None)`. Caller must `await server.start()` to fetch artifact bytes. NOT thread-safe across servers; per-server `asyncio.Lock` (line 296). Does NOT cache — each call constructs a fresh `InferenceServer`.

## 2. 1.1.x → 1.5.x diff archaeology

The brief documents the surface delta but the legacy file `packages/kailash-ml/src/kailash_ml/engines/inference_server.py` does NOT exist on disk (verified `engines/__init__.py` is 5 lines; W6-004 deleted it per `__init__.py:611–613` comment: "lazy-loaded from the canonical surface `kailash_ml.serving.server` after W6-004 deleted the legacy `engines.inference_server` module (F-E1-28)"). Git history search via `git log -- packages/kailash-ml/src/kailash_ml/engines/inference_server.py` is required to surface the W6-004 commit SHA — outside this read-only audit's tool budget but mandatory before fix-PR. Brief asserts removed surface: `InferenceServer(registry=, cache_size=)` + `await server.warm_cache([names])` + `await server.load_model(name, model)`.

Architectural shift: 1.1.x = ONE server, MANY models (LRU cache of size `cache_size`); 1.5.x = ONE server, ONE model (caller constructs N servers for N models). The shift is intentional per spec direction (§3 below) but no shim/deprecation cycle bridged it.

## 3. Spec authority direction

`specs/ml-serving.md §1.1` (lines 13–24): "InferenceServer is the canonical inference runtime ... loads a model via `ModelRegistry.get_model(name, alias='@production')`". Singular "a model" throughout. §2.1 (lines 47–85): the canonical `InferenceServerConfig` carries singular `model_uri: str` — no `cache_size`, no model list. §2.2 (lines 91–108) shows DIRECT construction `InferenceServer(InferenceServerConfig(...), registry=my_registry)` and says "engine.serve() owns composition" — implying multi-model is composed at the engine level, not within one server.

§2.3 (lines 111–144) `km.serve("fraud@production")` returns ONE `ServeHandle` per call — the multi-model pattern is `[await km.serve(n) for n in names]`. `from_registry_many` is NOT mentioned in the spec. **Verdict: ONE-per-model is the spec direction.** A 1.1.x `cache_size`-shaped `InferenceServer` is structurally incompatible with §2.1 — the deprecation adapter must be a back-compat shim AROUND the spec, not a spec-violating restoration.

**Spec amendment proposed:** add §2.6 "Multi-Model Convenience" documenting `InferenceServer.from_registry_many(names, *, registry) -> dict[str, InferenceServer]` as additive sugar atop the singular spec.

## 4. Deprecation adapter design

The constructor needs a 1.1.x-shape kwarg path that emits `DeprecationWarning` and routes to a new `MultiModelAdapter`. **In-class branching is BLOCKED** — `InferenceServer` is `frozen+slots`-config-shaped (§2.1) and the spec freezes its surface; a separate `MultiModelAdapter` class is the only structural fit. The 1.5.x `__init__(config, *, registry, server_id)` keeps its current first-positional `config: InferenceServerConfig` requirement; the adapter intercepts BEFORE that signature.

Skeleton (lives at `packages/kailash-ml/src/kailash_ml/serving/_legacy_multi_model.py`):

```python
class MultiModelAdapter:
    """1.1.x-shape deprecation shim. NEW code MUST use km.serve(uri) per
       specs/ml-serving.md §2.3. Lazy-constructs one InferenceServer per
       model name on warm_cache/load_model/predict."""
    def __init__(self, *, registry: ModelRegistry, cache_size: int = 8) -> None:
        warnings.warn(
            "InferenceServer(registry=, cache_size=) is the 1.1.x surface; "
            "1.5.x ships ONE-per-model via InferenceServer.from_registry(name, registry=). "
            "For multi-model use km.serve(uri) per call. See CHANGELOG 1.6.0.",
            DeprecationWarning, stacklevel=3)
        self._registry, self._cache_size, self._servers = registry, cache_size, OrderedDict()
    async def warm_cache(self, names: list[str]) -> None: ...    # 1.1.x signature
    async def load_model(self, name: str, model: Any) -> None: ...  # raises if model arg passed
    async def predict(self, name: str, payload: Any) -> Any: ...  # LRU-evict at cache_size

# In kailash_ml/serving/server.py:
class InferenceServer:
    def __init__(self, config=None, *, registry=None, cache_size=None,
                 server_id=None) -> "InferenceServer | MultiModelAdapter":
        if cache_size is not None or (config is None and registry is not None):
            from ._legacy_multi_model import MultiModelAdapter
            return MultiModelAdapter(registry=registry, cache_size=cache_size or 8)
        # ... existing 1.5.x body
```

`__init__` returning a different type is unidiomatic Python — better: convert `InferenceServer.__init__` to delegate via `__new__` (returns `MultiModelAdapter` instance when 1.1.x kwargs detected). This is the standard Python "constructor-returns-subtype" pattern.

Additive helper (canonical multi-model, NOT deprecated):

```python
@classmethod
async def from_registry_many(
    cls, names: list[str], *, registry: ModelRegistry,
    tenant_id: Optional[str] = None,
) -> dict[str, "InferenceServer"]:
    """Construct one InferenceServer per name. Spec §2.6 (proposed)."""
    return {n: await cls.from_registry(n, registry=registry, tenant_id=tenant_id)
            for n in names}
```

## 5. Call-site census

Read-only audit deferred (Read-tool only; no Bash). MUST run before fix-PR:

```bash
grep -rn 'InferenceServer(' packages/kailash-ml/src tests/ packages/kailash-ml/tests/ docs/ examples/
grep -rn 'warm_cache\|load_model' packages/kailash-ml/
```

Known site: `packages/kailash-ml/src/kailash_ml/__init__.py:614` (lazy `__getattr__` exposes `InferenceServer` from `kailash_ml.serving.server`). Additional sites (production engines, MLEngine.serve, channel adapters) tracked under brief MLFP ex_2/03 + ex_7/05 as hard-broken — exhaustive grep needed.

## 6. Tier-2 regression test design

Per `rules/testing.md` § "End-to-End Pipeline Regression". File: `packages/kailash-ml/tests/regression/test_issue_700_inference_server_surfaces.py`.

```python
@pytest.mark.regression
@pytest.mark.integration
async def test_inference_server_legacy_multi_model_adapter_predicts(real_registry, sample_models):
    """1.1.x DOCS-EXACT path; emits DeprecationWarning; predicts on registered model."""
    with pytest.warns(DeprecationWarning, match="1.1.x surface"):
        server = InferenceServer(registry=real_registry, cache_size=4)
    await server.warm_cache(["fraud_model"])
    out = await server.predict("fraud_model", {"x": [[1.0, 2.0]]})
    assert "prediction" in out  # external assertion per facade-manager-detection §1

@pytest.mark.regression
@pytest.mark.integration
async def test_inference_server_canonical_per_model_predicts(real_registry):
    """1.5.x DOCS-EXACT (km.serve) path; no DeprecationWarning."""
    handle = await km.serve("fraud_model@production")
    try:
        resp = await http_post(handle.urls["rest"], json={"x": [[1.0, 2.0]]})
        assert resp.status_code == 200
    finally:
        await handle.stop()
```

## 7. Release cycle classification

**1.6.0 (minor) — recommended.** Adapter is additive (re-introducing removed surface as deprecated path) but signals an architectural shift documented in CHANGELOG. 1.5.2 framing is wrong: "1.1.x→1.5.x regression fix" implies the 1.5.x removal was a regression; spec §2.1 confirms it was intentional. Restoring 1.1.x as the canonical surface would re-violate the spec — restoring as a deprecated adapter is additive minor-class work. Per `rules/zero-tolerance.md` Rule 1b deferral framework: NOT applicable here — this is fix-now (deprecation cycle), not defer.

`from_registry_many` ships in 1.6.0 same-PR, gated by spec amendment §2.6 (`rules/specs-authority.md` §5b — full sibling re-derivation against `ml-serving.md` + `ml-engines-v2.md`).

## 8. Risk register

| Risk                                                                                                                                                   | Likelihood | Impact | Mitigation                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `__new__`-returning-subtype confuses static analyzers (pyright, IDE autocomplete)                                                                      | High       | Medium | Type hint `**new** -> InferenceServer                                                                                                            | MultiModelAdapter`; document in CHANGELOG; add `# pyright: ignore` if needed |
| LRU eviction races against `predict()` in adapter (no `asyncio.Lock` planned)                                                                          | Medium     | High   | Per-name `asyncio.Lock`; mirrors per-server lock in §1.5.x line 296                                                                              |
| `MultiModelAdapter.warm_cache` swallows registry errors (1.1.x semantics unclear)                                                                      | Medium     | Medium | Surface partial-failure WARN per `rules/observability.md` Rule 7; raise on full-cache failure                                                    |
| Signature drift: `cache_size` defaulted to 8 silently caps user; 1.1.x default unknown                                                                 | High       | Low    | Match brief's documented kwarg shape; document in CHANGELOG migration section                                                                    |
| `from_registry_many` parallel construction stresses registry connection pool                                                                           | Medium     | Medium | `asyncio.gather` with bounded `Semaphore(8)`; matches `rules/dataflow-pool` cap pattern                                                          |
| Adapter routes to `from_registry`, which auto-loads `_LoadedModel.onnx_bytes=None` — 1.1.x `load_model(name, model)` accepted a pre-built model object | High       | High   | Adapter MUST raise `TypeError` if `model` arg passed (1.5.x cannot accept user-supplied bytes; registry is authoritative); document in CHANGELOG |

## 9. Codify candidates

1. **Public-API removal requires DeprecationWarning shim for ≥1 minor cycle.** Brief lists this as a global rule candidate (§Codify candidates row 1). Cross-SDK applicability: same gap exists in Rust (`#[deprecated(since=...)]`). Likely new file `rules/api-deprecation.md` — extends `rules/zero-tolerance.md` Rule 6 + `rules/orphan-detection.md` Rule 3 ("Removed = Deleted, Not Deprecated" — note tension: that rule says delete unwired orphans; THIS rule says shim wired-but-replaced public surfaces. Distinguishable: orphans were never called; this case has documented users).

2. **Spec direction shifts MUST ship a back-compat adapter, not a hard break.** Specifically when an architectural shift (one-many → one-one) lands in a release, the OLD shape MUST remain importable behind a `DeprecationWarning` for the next minor cycle. Sibling of #1 but more specific.

3. **`from_registry_many` pattern (multi-resource bulk constructor).** When a singular `from_registry(name, ...)` exists and users routinely need N parallel constructions, the spec MUST mandate a `from_registry_many(names, ...)` sibling; otherwise users build it ad-hoc with subtle bugs (ordering, error handling, connection saturation).

---

**File written:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-1.5.x-followup/01-analysis/05-issue-700-inferenceserver-analysis.md`

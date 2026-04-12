# Research: Cross-Framework (#301), CI (#303), Docs (#302)

## Issue #301: WS-4.5 Integration Gate

### Scenario Status

| Scenario                                | Infrastructure                 | Test       | Blocker                                |
| --------------------------------------- | ------------------------------ | ---------- | -------------------------------------- |
| 1: DataFlow → EventBus → DerivedModel   | ✅ All exists                  | ❌ Missing | None                                   |
| 2: InferenceServer via Nexus HTTP + MCP | ✅ HTTP exists, ❌ MCP missing | ❌ Missing | MCP endpoint for InferenceServer       |
| 3: platform_map() cross-framework graph | ❌ **Function doesn't exist**  | ❌ Missing | **Critical: platform_map() undefined** |

### Scenario 1 Infrastructure

- **DerivedModelEngine**: `packages/kailash-dataflow/src/dataflow/features/derived.py`
- **EventBus**: `packages/kailash-nexus/src/nexus/events.py` (janus.Queue, bounded)
- **DataFlow events**: `packages/kailash-dataflow/src/dataflow/core/events.py` (8 WRITE_OPERATIONS)
- **setup_event_subscriptions()**: Called in engine.py after initialize()
- Flow: write → \_emit_write_event → EventBus → DerivedModel debounced refresh

### Scenario 2 Infrastructure

- **InferenceServer**: `packages/kailash-ml/src/kailash_ml/engines/inference_server.py`
- **register_endpoints()**: Lines 307-330, registers /api/predict/{model_name}, /api/predict_batch/{model_name}
- **ONNX Bridge**: `packages/kailash-ml/src/kailash_ml/bridge/onnx_bridge.py`
- **Missing**: No MCP tool definition for InferenceServer predictions

### Scenario 3: platform_map() — BLOCKER

`platform_map()` does not exist. The MCP platform contributor registers tools from DataFlow, Nexus, Kaizen contributors, but no function produces a cross-framework graph.

**Recommendation**: Implement `platform_map()` as a new tool in the platform MCP contributor (`src/kailash/mcp/contrib/platform.py`). It should introspect registered contributors and return:

```python
{
    "models": [...],       # from DataFlow contributor
    "handlers": [...],     # from Nexus contributor
    "agents": [...],       # from Kaizen contributor
    "connections": [...]   # inferred from static analysis
}
```

---

## Issue #303: CI Test Pipelines

### Current CI

- **unified-ci.yml**: Primary test runner (Python 3.11-3.13, unit + tier2)
- **publish-pypi.yml**: Handles ml-v* and align-v* tags, OIDC publishing
- **No package-specific test workflows exist**

### Required

1. **test-kailash-ml.yml**: Matrix (Python 3.10-3.13), 3 variants (base, [dl], [rl])
2. **test-kailash-align.yml**: Test job + optional GPU job (workflow_dispatch)
3. **Publish requires test pass**: `needs: [test-base, test-dl, test-rl]`
4. **Version consistency check**: pyproject.toml == **init**.py.**version**

### Package Extras

**kailash-ml**: `[dl]` (torch+transformers), `[rl]` (stable-baselines3), `[xgb]`, `[catboost]`, `[stats]`, `[agents]`, `[full]`
**kailash-align**: `[rlhf]`, `[eval]`, `[serve]`, `[online]`, `[full]`

---

## Issue #302: Framework Guides (12 total)

### Current State

- **kailash-ml**: No docs/ directory at all
- **kailash-align**: docs/ exists with only method-selection guide and authority docs
- **Pattern**: kailash-dataflow has 13 guides in docs/guides/

### Required Guides

**kailash-ml (6)**:

1. 01-quickstart.md
2. 02-feature-pipelines.md
3. 03-model-registry.md
4. 04-inference-server.md
5. 05-agent-augmented.md
6. 06-onnx-export.md

**kailash-align (6)**:

1. 01-quickstart.md
2. 02-fine-tuning.md
3. 03-evaluation.md
4. 04-serving.md
5. 05-kaizen-bridge.md (existing method-selection guide becomes 02)

### Requirements

- Runnable code examples tested against real package
- "Common errors" section with 2-3 mistakes and fixes per guide

---

## Issue #294: Cross-SDK Vector Node (Tracking)

No code changes needed on kailash-py. Python pgvector support is complete. Close with note pointing to kailash-rs#196 for Rust implementation.

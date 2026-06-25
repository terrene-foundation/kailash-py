# Brief — Issue #1125: from_brief() primitives

**Source:** GitHub issue [terrene-foundation/kailash-py#1125](https://github.com/terrene-foundation/kailash-py/issues/1125)
**Title:** `feat: from_brief() primitives — natural-language brief → executable framework primitive`
**Type:** SDK feature / cross-framework API surface
**Severity asserted by reporter:** HIGH

## Framing (orchestrator's understanding)

The reporter is asking the Kailash platform to expose a single, consistent "natural-language brief → executable primitive" entry point across all 5 framework surfaces (Core SDK Workflow, DataFlow, Kaizen, the `kailash.bootstrap` shim, and kailash-ml). Today the path from prose intent → running workflow requires a human to hand-author Python classes (`@db.model`, `Signature` subclasses, `add_node` graphs); existing MCP `scaffold_*` tools return code-as-strings, NOT executable primitives. The issue asserts this places a mandatory human-code-author step between intent and execution, demoting the high-level API to a documentation artifact.

The proposed surfaces:

1. `kailash.Workflow.from_brief(brief: str) -> WorkflowBuilder`
2. `kailash.DataFlow.from_brief(brief: str, conn_str: str | None = None) -> DataFlow`
3. `kailash.Kaizen.signature_from_brief(brief: str) -> Signature`
4. `kailash.bootstrap(brief: str, profile: str = "dev") -> BootstrapConfig`
5. `kailash_ml.from_brief(brief: str, df: DataFrame) -> tuple[FeatureSchema, ModelSpec, EvalSpec]`

This is a ≥5-issue brief by surface count and ≥10-criterion brief by acceptance count. Multi-framework. Cross-cuts Kaizen (LLM reasoning), DataFlow (DB schema synthesis), Core SDK (workflow graph synthesis), kailash-ml (feature/model spec synthesis), and a new `kailash.bootstrap` shim.

The brief is in the GitHub issue body (NOT inlined here per `rules/repo-scope-discipline.md` discipline — it's already on the public record). Acceptance criteria are 10 bullets covering the 5 surfaces' return-shape contracts + 5 Tier-2 integration tests + a README Quick Start update.

## Issue body — verbatim

## Affected API

- `kailash.Workflow.from_brief(brief: str) -> WorkflowBuilder`
- `kailash.DataFlow.from_brief(brief: str, conn_str: str | None = None) -> DataFlow`
- `kailash.Kaizen.signature_from_brief(brief: str) -> Signature`
- `kailash.bootstrap(brief: str, profile: str = "dev") -> BootstrapConfig`
- `kailash_ml.from_brief(brief: str, df: DataFrame) -> tuple[FeatureSchema, ModelSpec, EvalSpec]`

## Minimal repro

```python
import kailash
from kailash import DataFlow, Kaizen, Workflow

# The five surfaces this issue proposes — none exist today.

# 1. Workflow.from_brief — reify natural-language intent into a built workflow.
brief = "Summarize uploaded customer emails and route negative-sentiment messages to support."
wf = Workflow.from_brief(brief)  # AttributeError: type object 'Workflow' has no attribute 'from_brief'

# 2. DataFlow.from_brief — synthesize @db.model-equivalent schemas from intent.
df = DataFlow.from_brief("Customers have name, email, and signup_date.")  # AttributeError

# 3. Kaizen.signature_from_brief — derive a typed I/O Signature from intent.
sig = Kaizen.signature_from_brief("Input: customer email. Output: one-sentence summary.")  # AttributeError

# 4. kailash.bootstrap — single-call configuration from intent + profile.
cfg = kailash.bootstrap("Use Postgres for storage and a local LLM for summarization.", profile="dev")  # AttributeError

# 5. kailash_ml.from_brief — synthesize feature schema + training plan + eval criteria.
import kailash_ml
import pandas as pd
df = pd.read_csv("customers.csv")
feature_schema, model_spec, eval_spec = kailash_ml.from_brief(
    "Predict churn from customer behavior features.", df
)  # AttributeError
```

Each call AttributeError-raises today; no `from_brief` / `signature_from_brief` / `bootstrap` symbols exist on any of the four public modules. Equivalent functionality is achieved only by hand-authoring Python classes (`@db.model class Customer: ...`, `class SummarizeSignature(Signature): ...`) and per-node `add_node` / `add_connection` sequences.

## Expected vs actual

**Expected:** Natural-language brief reifies to executable framework primitive via the surfaces enumerated under "Affected API". The user passes prose intent; the SDK returns a built or buildable object that subsequent calls can execute against.

**Actual:** Every framework Quick Start opens with engineer-authored `@db.model` / `Signature` / `add_node` Python class authoring. The MCP `scaffold_*` tools (`dataflow.scaffold_model`, `nexus.scaffold_handler`, `kaizen.scaffold_agent`) ALREADY perform intent→code translation, but return code-as-STRINGS for human review — not executable primitives.

## Severity

HIGH — Without `from_brief()` primitives, the documented "natural-language to running workflow" pipeline cannot complete without an engineer hand-authoring the intermediate Python classes. The scaffold-as-strings path documented today places a mandatory human-code-author step between intent and execution, which makes the SDK's high-level API a documentation artifact rather than an executable contract.

## Acceptance criteria

- [ ] `kailash.Workflow.from_brief(brief: str)` returns a `WorkflowBuilder` whose `.build().execute()` runs end-to-end on the synthesized graph.
- [ ] `kailash.DataFlow.from_brief(brief, conn_str=None)` returns a configured `DataFlow` whose synthesized model classes pass round-trip `create()` → `get()` against the connection string.
- [ ] `kailash.Kaizen.signature_from_brief(brief)` returns a `Signature` subclass with typed input + output fields, usable as the `signature=` arg to any Kaizen agent constructor.
- [ ] `kailash.bootstrap(brief, profile="dev")` returns a `BootstrapConfig` resolving `db_url`, `llm_model`, `runtime`, and `deployment_target` consistent with the brief + profile.
- [ ] `kailash_ml.from_brief(brief, df)` returns a `(FeatureSchema, ModelSpec, EvalSpec)` triple whose `FeatureSchema` matches the dataframe's columns and `ModelSpec.task` matches the brief's stated prediction goal.
- [ ] Tier 2 integration test added at `tests/integration/kailash/test_workflow_from_brief.py` covering ≥3 brief shapes (simple linear, branching, error-path).
- [ ] Tier 2 integration test added at `tests/integration/dataflow/test_dataflow_from_brief.py` covering ≥2 brief shapes (single-model, multi-model with relationship).
- [ ] Tier 2 integration test added at `tests/integration/kaizen/test_signature_from_brief.py` covering ≥2 brief shapes (single-input single-output, multi-field).
- [ ] Tier 2 integration test added at `tests/integration/kailash/test_bootstrap.py` covering ≥2 profile values (`dev`, `prod`) with matching env-var resolution.
- [ ] Tier 2 integration test added at `tests/integration/ml/test_ml_from_brief.py` covering ≥2 brief shapes (classification, regression).
- [ ] Public docs (README Quick Start) updated to use `from_brief()` entry points instead of class-authoring entry points.

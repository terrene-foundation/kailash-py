# Spec — Kaizen Evaluation (Algorithmic NLP Metrics)

**Status:** Authoritative as of 2026-04-20 (PR#5 of 7, issue #567).
**Package:** `kailash-kaizen` (v2.9.0+).
**Module:** `kaizen.evaluation`.

## Purpose

`kaizen.evaluation` hosts **pure-algorithmic NLP metrics** that share NO surface with `kaizen.judges`. The split is deliberate:

- **`kaizen.judges`** — LLM dispatch + cost budget + Delegate routing + typed error surface.
- **`kaizen.evaluation`** — lightweight reference-comparison math over strings. No LLM call, no cost tracker, no budget enforcement, no `run_id` correlation.

Users who want to run ROUGE / BLEU / BERTScore against a reference set do NOT need the judge runtime. Users who want judges to aggregate ROUGE alongside their LLM verdicts can import from both namespaces.

## Public surface (facade import)

```python
from kaizen.evaluation import ROUGE, BLEU, BERTScore

rouge_df = ROUGE.score(predictions=[...], references=[...])
bleu_corpus = BLEU.corpus(predictions=[...], references=[...])
bert_df = BERTScore.score(predictions=[...], references=[...])
```

All three classes expose `classmethod` entry points so downstream code uses `ROUGE.score(...)` uniformly rather than mixing functions and methods.

## Metrics

### `ROUGE` (`kaizen.evaluation.rouge`)

- **Backend**: `rouge-score>=0.1.2`.
- **Variants**: ROUGE-1, ROUGE-2, ROUGE-L (F-score / precision / recall).
- **Entry point**: `ROUGE.score(predictions: Sequence[str], references: Sequence[str], *, variants=("rouge1", "rouge2", "rougeL")) -> pl.DataFrame`.
- **Output schema**: one row per prediction × variant with columns `prediction_idx`, `variant`, `precision`, `recall`, `fmeasure`.

### `BLEU` (`kaizen.evaluation.bleu`)

- **Backend**: `sacrebleu>=2.4`.
- **Variants**: corpus-level `BLEU.corpus(predictions, references)` + sentence-level `BLEU.sentence(prediction, references)`.
- **Output**: corpus returns a scalar BLEU score; sentence returns `pl.DataFrame` with per-sentence score + n-gram precisions.

### `BERTScore` (`kaizen.evaluation.bertscore`)

- **Backend**: `bert-score>=0.3.13`.
- **Entry point**: `BERTScore.score(predictions, references, *, model_type=None, lang="en", rescale_with_baseline=False) -> pl.DataFrame`.
- **Output schema**: one row per prediction with columns `prediction_idx`, `precision`, `recall`, `f1`.

## Invariants

1. **Zero LLM surface** — `grep -rn 'openai\|anthropic\|litellm\|Delegate' packages/kailash-kaizen/src/kaizen/evaluation/` MUST return zero matches. Any metric that needs an LLM belongs in `kaizen.judges`, not here.
2. **Zero cost surface** — no `CostTracker`, no `budget_microdollars`, no `JudgeBudgetExhaustedError`. Metrics are O(string-length) math; there is no budget concept.
3. **Loud optional-import failure** — each module imports its backend inside a `try/except ImportError` guard that raises a descriptive `ImportError` at call time naming the `[evaluation]` extra per `rules/dependencies.md` "Optional Extras with Loud Failure". Silent degradation to `None` is BLOCKED.
4. **Polars DataFrames for multi-row output** — matches the sibling adapters (DL, RAG, Alignment, Interpretability, LLMDiagnostics). No pandas.
5. **Deterministic** — same inputs produce identical outputs. No randomness, no timestamps, no model hash in output.

## Optional extras

```toml
[project.optional-dependencies]
evaluation = [
    "rouge-score>=0.1.2",
    "sacrebleu>=2.4",
    "bert-score>=0.3.13",
]
```

Note: the `[judges]` extra has the same dep list (algorithmic metrics are shared helpers inside the judge path too). Users who only want metrics — not the judge runtime — install `kailash-kaizen[evaluation]` and pay for the same three deps; users who install `[judges]` get these metrics transitively.

## Test discipline

Per `rules/testing.md` 3-tier model:

- **Tier 1 (unit)** — `packages/kailash-kaizen/tests/unit/evaluation/test_evaluation_unit.py` (to be added in a follow-up patch; base install doesn't pull the extras so the unit tests MUST `importorskip` each backend).
- **Tier 2 (integration)** — covered inline by the judge path — the LLMDiagnostics end-to-end test uses a DeterministicJudge that conforms to the `JudgeCallable` Protocol AND the evaluation helpers are used internally by LLMJudge's faithfulness / self_consistency paths. Separate Tier 2 evaluation-only tests can be added if the evaluation surface grows beyond the three classes.

## Security threats

| Threat                                             | Mitigation                                                                                                                                                                                                     |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tokenizer download on first use                    | Each backend (`rouge-score`, `sacrebleu`, `bert-score`) downloads tokenizer / model on first use. This happens WITHOUT a user-visible prompt. Document in user guide: "first call downloads ~500MB of models". |
| Multi-lingual surprise                             | `BERTScore.score` defaults `lang="en"`. Callers pass `lang=` explicitly for non-English corpora. Wrong `lang` silently produces garbage scores.                                                                |
| Reference-comparison false positives on short text | Algorithmic metrics over ≤5-token strings produce unstable precision / recall. Callers handle this at the application layer — the metrics never filter input.                                                  |

## Relationship to `kaizen.judges`

The judge runtime imports these metrics for fallback scoring when a Delegate call is too expensive:

```python
# Inside kaizen.judges.LLMJudge — on-the-cheap pre-filter
from kaizen.evaluation import ROUGE

if ROUGE.score(pred, ref)["fmeasure"][0] > 0.95:
    # Obvious match — skip LLM call, return high-confidence score
    return JudgeResult(score=0.95, winner=None, ...)
```

This cross-namespace import is fine — `kaizen.judges` reads FROM `kaizen.evaluation`, not the other way around. The split remains clean: judges compose evaluation; evaluation does NOT compose judges.

## Attribution

The ROUGE / BLEU / BERTScore wrappers are thin adapters over the upstream libraries (`rouge-score`, `sacrebleu`, `bert-score`). No original scoring logic is re-implemented here — the Foundation contribution is the uniform classmethod entry point + polars output schema + loud-fail optional-import discipline. Upstream libraries are MIT / Apache 2.0 compatible; attribution via `pip install` transitive dep declarations.

## Origin

- Issue: [`kailash-py#567`](https://github.com/terrene-foundation/kailash-py/issues/567) (SYNTHESIS plan § "One namespace hygiene clean-up").
- Sibling spec: `specs/kaizen-judges.md`.
- Plan: `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md`.

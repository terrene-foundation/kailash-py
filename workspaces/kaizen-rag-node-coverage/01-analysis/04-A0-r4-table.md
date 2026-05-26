---
type: A0-OUTPUT
shard: A0
workspace: kaizen-rag-node-coverage
branch: feat/kaizen-rag-A0-r4-enumeration
base_sha: ca552101d
produced_by: F17/A0 pure-AST enumeration
---

# A0 — R4 LEAK Enumeration Table

## Scope

Pure AST walk over `packages/kailash-kaizen/src/kaizen/nodes/rag/*.py` looking for code-template f-strings (any `JoinedStr` that is a dict value where the key is `code`, an assignment to a name containing `code`/`template`/`src`, or a kwarg named `code`/`template`).

For each `JoinedStr.values[FormattedValue]`, classify LEAK vs BENIGN based on:
1. **Quoted-context heuristic** — if the FV is immediately surrounded by `"` or `'` in the f-string body, the substituted value becomes a quoted-string literal in the exec'd code → BENIGN.
2. **Type-aware heuristic** — for unquoted FVs, infer the referenced name's type:
   - `int`/`float`/`bool` → substitutes as numeric/bool literal at exec → BENIGN
   - `list`/`dict`/`tuple` → substitutes via `repr()` as a valid Python container literal → BENIGN
   - `str` → substitutes as bare identifier in exec'd code → **LEAK** (NameError at exec)
   - complex expressions (`self.x.y`, calls, subscripts) → BENIGN-COMPLEX (typically resolves to literal/repr)

Loop-variable detection (e.g. `{i}` inside a template that generates per-iteration code) is folded into the type heuristic: such names are typically int-bound by `enumerate()` / `range()`, so they classify BENIGN as int literals.

Type inference sources: function-parameter annotations, `__init__` parameter annotations on enclosing class, `AnnAssign` type hints, obvious coercion assignments (`int(...)`, `float(...)`, `bool(...)`), `for` loop targets bound by `enumerate()` / `range()`, and constant-RHS assignments.

## Summary

- **Total files with code-template f-strings**: 13 / 16 rag modules (excluding `__init__.py` and `registry.py`/`router.py` which contain no exec'd templates)
- **Total code-template f-strings (`JoinedStr` instances)**: 31
- **Total FormattedValue interpolation sites**: 51
- **LEAK verdicts**: 0
- **BENIGN verdicts** (incl. BENIGN-COMPLEX): 51
- **ADJUDICATE verdicts**: 0

**Brief expectation**: ~30 code templates / 12 modules. **Found**: 31 templates / 13 modules. Counts match within ±1.

## Brief Anchor Site Re-Classification

The brief tagged three sites as ground-truth anchors. Re-verification:

| Site | Brief claim | Verified verdict | Disposition |
|---|---|---|---|
| `strategies.py:240` (actual line 253) `"fusion_method": "{fusion_method}"` | LEAK (`fusion_method` is local, unbound at exec) | **BENIGN** | Quoted-context: substitutes to `"fusion_method": "rrf"` — valid Python string literal in generated code. The construct-time `fusion_method` (function parameter, `str = "rrf"`) becomes a literal value, NOT a bare identifier at exec. |
| `privacy.py:152` `region` | LEAK (similar pattern) | **NO MATCH** | No `{region}` interpolation exists at or near privacy.py:152. The brief's anchor may reference a different module/version, OR refer to the `{self.redact_pii}` / `{self.anonymize_queries}` interpolations in `detect_and_redact_pii(text, redact={self.redact_pii})` at L117/L184 etc. Those interpolate `bool` types → BENIGN (substitute as `True`/`False` literals). |
| `privacy.py:221` | "likely benign loop var; verify" | **BENIGN** | Line 221 is inside an f-string body literal `"depression|anxiety": "mental health condition",` (no FV here). The nearest FVs at privacy.py:184/198/273 are bool/float substitutions; loop vars inside generated `for ... f"semantic_{{i}}"` patterns use `{{i}}` (escaped) which the parser does NOT emit as a FormattedValue. |

## LEAK Enumeration Table

**Mechanical AST sweep verdict: ZERO LEAKs across all 51 FormattedValue interpolation sites in the rag/ source tree.**

Every interpolated value is either:
- Wrapped in surrounding string-literal quotes (BENIGN: substitutes as Python string literal at exec)
- A numeric (`int`/`float`) or `bool` value (BENIGN: substitutes as numeric/bool literal)
- A `list`/`dict` value (BENIGN: substitutes as Python container literal via `repr()`)
- A complex expression resolving to a literal/repr at construct time (BENIGN-COMPLEX)

## Full Site Inventory

Below is every code-template FV in rag/, grouped by file. Format: `file:line | name | type | verdict | excerpt`.

| file:line | f-string body excerpt | name | type | verdict | reason |
|---|---|---|---|---|---|
| `advanced.py:127` | `fusion(doc_lists, k=60, top_k={retrieval_k}):\n    fused_sco` | `retrieval_k` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `advanced.py:156` | `"sparse"],\n    "retrieval_k": {retrieval_k},\n    "dense_co` | `retrieval_k` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `agentic.py:395` | `  if state["current_step"] >= {self.max_reasoning_steps}:\n ` | `self.max_reasoning_steps` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `agentic.py:521` | `        "planning_strategy": "{self.planning_strategy}",\n  ` | `self.planning_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `agentic.py:522` | `y}",\n            "max_steps": {self.max_reasoning_steps},\n` | `self.max_reasoning_steps` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `conversational.py:166` | `ent_turns = session["turns"][-{self.max_context_turns}:]\n\n` | `self.max_context_turns` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `conversational.py:467` | `   if len(session["turns"]) > {self.max_context_turns} * 1.5` | `self.max_context_turns` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `conversational.py:469` | `["turns"] = session["turns"][-{self.max_context_turns}:]\n\n` | `self.max_context_turns` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `evaluation.py:445` | `              "metrics_used": {self.metrics},\n             ` | `self.metrics` | list | BENIGN | unquoted but type='list' → substitutes as repr() literal (valid Python container literal) |
| `federated.py:139` | `,\n            "min_required": {self.min_participating_nodes` | `self.min_participating_nodes` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `federated.py:140` | `          "timeout_per_node": {self.timeout_per_node},\n    ` | `self.timeout_per_node` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `federated.py:141` | `     "aggregation_strategy": "{self.aggregation_strategy}"\n` | `self.aggregation_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `federated.py:159` | `    },\n            "timeout": {self.timeout_per_node}\n    ` | `self.timeout_per_node` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `federated.py:254` | `it": random.random() > 0.7 if {self.enable_caching} else Fal` | `self.enable_caching` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `federated.py:261` | `mum_met = successful_nodes >= {self.min_participating_nodes}` | `self.min_participating_nodes` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `federated.py:297` | `,\n                "required": {self.min_participating_nodes` | `self.min_participating_nodes` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `federated.py:342` | `ate based on strategy\n    if "{self.aggregation_strategy}" ` | `self.aggregation_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `federated.py:372` | `"])\n            })\n\n    elif "{self.aggregation_strategy}` | `self.aggregation_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `federated.py:428` | `\n                "strategy": "{self.aggregation_strategy}",` | `self.aggregation_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `federated.py:525` | `ion_metadata.get("strategy", "{self.aggregation_strategy}"),` | `self.aggregation_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `federated.py:528` | `    "minimum_nodes_required": {self.min_participating_nodes}` | `self.min_participating_nodes` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `federated.py:540` | `    if cache_coordination and {self.enable_caching}:\n      ` | `self.enable_caching` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `graph.py:190` | `   if len(G) > 0:\n        if "{self.community_algorithm}" =` | `self.community_algorithm` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `graph.py:283` | `)\n                if depth >= {self.max_hops}:\n           ` | `self.max_hops` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `multimodal.py:178` | `ract text here\n            if {self.enable_ocr} and image_p` | `self.enable_ocr` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `multimodal.py:281` | `          "encoding_method": "{self.image_encoder}"\n       ` | `self.image_encoder` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `optimized.py:111` | `ry, cached_queries, threshold={self.similarity_threshold}):\` | `self.similarity_threshold` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `optimized.py:184` | `_similarity and similarity >= {self.similarity_threshold}:\n` | `self.similarity_threshold` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `optimized.py:349` | ` execution tasks\nstrategies = {self.strategies}\nquery_data` | `self.strategies` | list | BENIGN | unquoted but type='list' → substitutes as repr() literal (valid Python container literal) |
| `optimized.py:423` | `om each strategy\nstrategies = {self.strategies}\nfor strate` | `self.strategies` | list | BENIGN | unquoted but type='list' → substitutes as repr() literal (valid Python container literal) |
| `optimized.py:554` | `aming parameters\nchunk_size = {self.chunk_size}\ntotal_resu` | `self.chunk_size` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `optimized.py:741` | `) else [queries]\nbatch_size = {self.batch_size}\n\n# Create` | `self.batch_size` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `privacy.py:117` | `t_and_redact_pii(text, redact={self.redact_pii}):\n    '''De` | `self.redact_pii` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `privacy.py:184` | `t_and_redact_pii(text, redact={self.redact_pii})\n# Drop the` | `self.redact_pii` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `privacy.py:198` | `ry(query, pii_info, anonymize={self.anonymize_queries}):\n  ` | `self.anonymize_queries` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `privacy.py:273` | `privacy_noise(scores, epsilon={self.privacy_budget}):\n    '` | `self.privacy_budget` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `privacy.py:546` | `record.get("audit_record") if {self.audit_logging} else None` | `self.audit_logging` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `privacy.py:549` | `       "privacy_budget_used": {self.privacy_budget},\n      ` | `self.privacy_budget` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `realtime.py:180` | `ffer, new_documents, max_size={self.max_buffer_size}):\n    ` | `self.max_buffer_size` | int | BENIGN | unquoted but type='int' → substitutes as numeric/bool literal |
| `realtime.py:241` | `amp, current_time, decay_rate={self.relevance_decay_rate}):\` | `self.relevance_decay_rate` | float | BENIGN | unquoted but type='float' → substitutes as numeric/bool literal |
| `similarity.py:488` | `s\n\n# Main execution\nmethod = "{self.method}"\nquery = que` | `self.method` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `similarity.py:491` | `.get("expanded_terms", []) if {self.use_query_expansion} els` | `self.use_query_expansion` | bool | BENIGN | unquoted but type='bool' → substitutes as numeric/bool literal |
| `similarity.py:703` | `token_embeddings(text, model="{self.token_model}"):\n    '''` | `self.token_model` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `similarity.py:1661` | `fusion logic\nfusion_method = "{self.fusion_method}"\nweight` | `self.fusion_method` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `similarity.py:1662` | `elf.fusion_method}"\nweights = {self.weights}\nresult_lists ` | `self.weights` | dict | BENIGN | unquoted but type='dict' → substitutes as repr() literal (valid Python container literal) |
| `strategies.py:253` | `]],\n        "fusion_method": "{fusion_method}"\n    }\n\n# ` | `fusion_method` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `workflows.py:523` | `ocuments, query="", strategy="{self.default_strategy}", **kw` | `self.default_strategy` | str | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `workflows.py:529` | `ze": kwargs.get("chunk_size", {self.rag_config.chunk_size}),` | `self.rag_config.chunk_size` | expression | BENIGN-COMPLEX | complex expression 'self.rag_config.chunk_size' — typically resolves to a literal/repr at construct |
| `workflows.py:530` | `: kwargs.get("chunk_overlap", {self.rag_config.chunk_overlap` | `self.rag_config.chunk_overlap` | expression | BENIGN-COMPLEX | complex expression 'self.rag_config.chunk_overlap' — typically resolves to a literal/repr at construct |
| `workflows.py:531` | `wargs.get("embedding_model", "{self.rag_config.embedding_mod` | `self.rag_config.embedding_model` | expression | BENIGN | quoted-context (substitutes as string literal in generated code) |
| `workflows.py:532` | `k": kwargs.get("retrieval_k", {self.rag_config.retrieval_k})` | `self.rag_config.retrieval_k` | expression | BENIGN-COMPLEX | complex expression 'self.rag_config.retrieval_k' — typically resolves to a literal/repr at construct |

## Methodology Notes

**What this enumeration found**: every code-template f-string in `kaizen.nodes.rag/*.py` interpolates either (a) construct-time numeric/bool/list/dict values whose Python `repr()` is a valid literal in the generated code, OR (b) string values wrapped in surrounding quotes so substitution produces a string literal, NOT a bare identifier.

**What this enumeration did NOT find**: the brief-anticipated NameError-from-leaked-single-brace pattern (unquoted `{some_str_local}` substituting to a bare identifier the exec scope does not bind). Such a pattern would surface as a `str` type in an UNQUOTED context — zero such sites exist in the current rag/ tree at base_sha `ca552101d`.

**Implications for B-shard sizing**: the R4 fix surface is **EMPTY** for the rag/ tree at this commit. Either (1) the R4 class was structurally fixed prior to this enumeration, (2) the brief's ground-truth anchors reference a different commit or module path, or (3) the brief's failure-mode framing requires a different detection lens (e.g. runtime NameError traces from actual exec rather than static interpolation analysis).

**Recommendation for A3 R4 disposition**: re-verify the brief's anchor sites against an actual `NameError` runtime trace from `PrivacyPreservingRAGNode` exec, OR reframe the R4 failure-class detection lens (e.g. include runtime-binding mismatches such as undeclared `exec()` globals, or escaped-brace `{{X}}` that should have been `{X}`). Pure-AST interpolation analysis at this commit yields zero LEAK sites.

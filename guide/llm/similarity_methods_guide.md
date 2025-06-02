# Guide • Similarity Scoring Methods for RAG (June 2025)

Retrieval quality in RAG depends on **how you measure similarity** between queries and passages.
This playbook summarises the state‑of‑the‑art methods and when to use each.

---
## 1. Method Landscape

| Category | Core idea | Latency | Memory | When it excels |
|----------|-----------|---------|--------|----------------|
| **Dense single‑vector** (dot / cosine) | One embedding per text; rank by dot product. | ★ | ★★ | General retrieval ≤ 5 M docs. |
| **Late‑interaction (ColBERT)** | Keep per‑token vectors; MaxSim query‑to‑doc. | ★★ | ★★★ | Synonym‑heavy or code search; explainability. |
| **Sparse lexical (BM25, SPLADE)** | Overlap of exact or learned terms. | ★ | ★ | Proper nouns, IDs, formulas. |
| **Hybrid fusion (dense + sparse)** | Fuse scores (RRF / linear). | ★★ | ★★ | Mixed query styles, large corpora. |
| **Cross‑encoder rerank** | ⟨q⟩[SEP]⟨d⟩ through transformer. | ★★★ | ★★ | Top‑k ≤ 100, quality matters. |
| **Listwise / LLM rerank** | LLM sees entire candidate list. | ★★★★ | ★★ | Mission‑critical correctness. |

Legend: ★ = fast / small … ★★★★ = slow / large.

---
## 2. Cheat‑Sheet by Corpus Size & SLA

| Corpus / latency budget | Recommended stack |
|-------------------------|-------------------|
| **≤ 1 M docs, GPU OK** | Dense bi‑encoder → Cross‑encoder rerank (MonoT5‑3B / RankLLM‑8B). |
| **10 M+ docs, mixed vocab** | Hybrid: BM25 + Dense; fuse with RRF. |
| **Legal / code** | SPLADE or ColBERT‑v3 late‑interaction. |
| **Very long answers (2 k+ tokens)** | Dense retrieval → GPT‑4‑Turbo listwise rerank (k≤20). |
| **Edge / CPU** | Small dense (Nomic‑Embed‑Text) + BM25. |

---
## 3. Implementation Notes

### Dense Bi‑Encoder
```python
doc_vecs = encoder.encode(passages, normalize=True)
q_vec     = encoder.encode(query, normalize=True)
scores    = np.dot(doc_vecs, q_vec)
```

* Use cosine‑trained models (E5, BGE, SFR…).
* Index with FAISS HNSW or IVF‑PQ for O(10 ms) hits.

### Late‑Interaction (ColBERT‑v2)
```text
score(q,d) = Σ_i max_j cos(q_i, d_j)
```
* Index stores 32‑bit vectors per **token**; requires 4‑10 × RAM vs. dense.
* Gains ≥+5 nDCG on code/FAQ vs. dense.

### Sparse + Dense Fusion
```python
final = λ · rank_dense + (1‑λ) · rank_bm25   # λ≈0.6 works well
```
* Or use **Reciprocal Rank Fusion**: `RRF = Σ 1/(60 + rank)`

### Cross‑Encoder
```text
[CLS]  query  [SEP]  passage  [EOS]  →  sigmoid(logit)
```
* Re‑score top‑k (k = 50‑200). Expect +2‑10 nDCG over dense.
* Distil into “compact reranker” (≤ 440 M) for speed.

### Listwise LLM Reranker
```prompt
Given the query and the 20 candidate passages, reorder them from most to least relevant…
```
* Highest quality, highest token cost. Cache aggressively.

---
## 4. Take‑Aways for Builders & Agents
1. **Layer cheap recall with costly precision.** Most prod systems: Dense/Sparse → Rerank.
2. **Hybrid dense + BM25 is the current sweet spot** for large, unpredictable corpora.
3. **ColBERT or SPLADE** if exact structure or synonyms dominate.
4. **LLM listwise rerank** is your final mile when factual fidelity outweighs cost.
5. **Monitor retrieval metrics** (hit@k, MRR) whenever you swap similarity logic – generation quality is capped by retrieval.

---
*Updated Jun 02 2025*

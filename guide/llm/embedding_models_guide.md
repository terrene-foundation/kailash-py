# Guide • Choosing an Embedding Model for RAG (June 2025)

Retrieval‑Augmented Generation (RAG) systems live or die by the quality of their vector representations.
This quick‑start guide tells **builders** and **LLM agents** how to pick an embedding model that matches a new use‑case.

---
## 1. How We Judge “Best” Today
| Metric | Why it matters |
|--------|----------------|
| **MTEB composite score** | 56 retrieval, clustering & STS tasks – the de‑facto leaderboard. |
| **Context window** | Upper bound on chunk size you can embed. |
| **Vector dim** | Directly drives memory/latency of ANN indices. |
| **Multilingual & code support** | Needed if your corpus is not pure English prose. |
| **License & size** | Dictate deployability on‑prem or edge. |

*Tip ▶ Scores ≥66 points on MTEB are considered state‑of‑the‑art.*

---
## 2. Top Open Models Available via **`ollama`**
| Tag | Params | Context | Dim | Stand‑out strengths | Good for |
|-----|--------|---------|-----|---------------------|----------|
| `avr/sfr-embedding-mistral` | 7 B | 8 k | 768 | Highest open MTEB (≈ 67.6). Shares tokenizer with Mistral‑7B. | Best‑quality general RAG, legal, research. |
| `snowflake-arctic-embed2:568m-l` | 568 M | 512 | 768 | Multilingual + fast. Beats OpenAI **TE‑3‑large**. | Enterprise KBs in many languages. |
| `mxbai-embed-large` | 335 M | 512 | 768 | Punches above its size; easy to quantise. | High‑throughput SaaS search. |
| `bge-m3` | 567 M | 8 k | 1024 | Multi‑function (retrieval, rerank, STS). | Long‑doc, multi‑Ling, one‑model stacks. |
| `nomic-embed-text-v1` | 137 M | 8 k | 768 | Edge‑friendly; beats Ada‑002. | Mobile, browser, IoT. |
| `jina/jina-embeddings-v2-base-en` | 220 M | **8 k** | 768 | Longest context for its footprint. | Log/legal archives, bulky PDFs. |
| `granite-embedding:278m` | 278 M | 512 | 768 | IBM research SOTA on code+IR. | Corporate search where IBM license is OK. |

---
## 3. Decision Matrix

| If you… | Pick… | Rationale |
|---------|-------|-----------|
| Need raw maximum recall | **SFR‑Embedding‑Mistral** | Top leaderboard score; pairs with Mistral LLM. |
| Serve many languages | **Arctic‑Embed 2** or **BGE‑M3** | Trained on 30 + langs. |
| Run on CPU / Pi | **Nomic‑Embed‑Text** (4‑bit) | 137 M weights fit in 2 GB RAM. |
| Handle 5 k+‑token chunks | **BGE‑M3**, **Jina‑v2**, **Nomic** | 8 k token window. |
| Want smallest Ops complexity | Use *same‑family* embedder as your generator (e.g.\ `sfr-embedding-mistral` with `mistral` generation). | Shares tokenizer & many weights. |

---
## 4. Quick‑start with Ollama
```bash
# pull a model
ollama pull avr/sfr-embedding-mistral:7b-fp16

# embed a sentence
curl http://localhost:11434/api/embed -d '{
  "model": "avr/sfr-embedding-mistral:7b-fp16",
  "input": "Vector search is eating search."
}'
```
Change only **`model:`** to swap embeddings – everything else in your RAG stays untouched.

---
## 5. Best Practices
* **Normalize** vectors (ℓ2) before indexing if the model was trained with cosine loss.
* **Quantise** to int8 or int4 for 2‑3 × memory savings – quality drop is typically \<1 MTEB point.
* **Store the model tag** with every vector; upgrading models later without re‑indexing is painful.
* **Monitor retrieval hit@K** after any model swap – generation quality cannot exceed retrieval quality.

---
*Updated Jun 02 2025*

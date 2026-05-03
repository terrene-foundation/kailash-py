# Brief — GPU Stack for kailash-ml (First-Class)

Source: user request 2026-04-19 following GPU-acceleration research.

## Constraints

kailash-ml must deliver:

1. **Seamless across ml / dl / rl** — one user-facing API, no three
   branches of ceremony for each domain.
2. **GPU-first** — if a GPU is present, it gets used by default.
3. **Auto-detect + CPU fallback** — when no GPU is present, the same
   code path runs on CPU transparently.
4. **No manual configuration** — users MUST NOT have to set
   `device=...`, flip feature flags, or wrap calls in
   `with sklearn.config_context(array_api_dispatch=True)`.
5. **Transparent** — users can see which device/backend/precision is
   actually in use, per call, via logs and return metadata.
6. **Efficient** — no RAPIDS-style overhead (huge containers, pandas⇄cudf
   trampoline, CUDA-version coupling, slow cold-start).
7. **Maintainable** — stack is owned or replaceable; we can re-engineer
   any layer when it stops serving us.
8. **First-class, not bolted on** — the GPU path is THE path, not a
   `--gpu` flag on the CPU path.

## Non-goals

- Covering exotic hardware (e.g. Cerebras, Groq). The mainstream four
  are enough: NVIDIA CUDA, AMD ROCm, Apple MPS, Intel XPU.
- Maximum theoretical throughput. We want "fast by default", not the
  speed-of-light kernel for every op.

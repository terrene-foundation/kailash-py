# #1779 — `governance_required` posture for direct LLM egress (EATP D6 parity)

**Shard:** Wave-1 1D · **Mode:** /analyze (design-only, NO code) · **Date:** 2026-07-17
**Issue:** #1779 — process/env posture that fail-closed refuses bare un-governed LLM egress.

---

## 0. EXISTS-ALREADY verdict — **NO** (net-new posture; opt-IN seam exists, opt-OUT posture does not)

Mandatory grep returned **zero** hits for the posture's own identifiers:

```
grep -rn "governance_required|is_governance_required|set_governance_required|KAILASH_GOVERNANCE_REQUIRED" packages/kailash-kaizen/src/ src/
# → (no matches)
```

The only `ungoverned` hits are the **#1517 opt-IN outbound seam**, which is the substrate #1779 builds on — not the posture itself:

- `src/kailash/trust/pact/outbound.py` — the domain-neutral interceptor core. `resolve_interceptor()` (line 96) already fails closed: _"Refusing to build an ungoverned transport (fail-closed)."_ But this only fires when a transport is ALREADY wired to the seam.
- `packages/kailash-kaizen/src/kaizen/trust/governance/outbound.py:98` — `GovernedProvider` / `resolve_interceptor` production wiring, same fail-closed line.

**The gap is real and precisely bounded.** Today's model is **opt-IN**: unless a caller wraps the provider (`GovernedProvider`) or installs a process-global interceptor (`install_interceptor`), a bare client makes **silently ungoverned** real egress. #1779 adds the **opt-OUT posture** on top: when `KAILASH_GOVERNANCE_REQUIRED` is ON, a bare un-governed client that _would_ make real egress is **refused at construction** unless the caller attaches a governance pair OR passes `ungoverned=True`. EATP **D6 is a live cross-SDK contract** in this tree (`src/kailash/trust/pact/audit.py:59`, `reasoning/origin.py:38`, `revocation/cascade.py:31`), so a Rust-SDK mirror is expected (handoff noted in §8).

Adjacent prior art to reuse, not reinvent: the `KAIZEN_ALLOW_MOCK` env gate at `packages/kailash-kaizen/src/kaizen/agent.py:327` already establishes the "env-var flips a fail-closed egress posture" pattern.

---

## 1. Egress points — where "real egress" is actually decided (file:line)

There are **two** egress surfaces. Real-vs-mock is decidable by **transport/provider class identity**, never a network probe.

### A. New four-axis path — `kaizen.llm.client.LlmClient`

Real egress happens when a real `LlmHttpClient` (SSRF-safe httpx, `llm/http_client.py:243`) is acquired and used:

- `complete()` — `client.py:1255-1262` (`self._http_client = LlmHttpClient(...)` managed, or a fresh one-shot `LlmHttpClient(...)`).
- `stream()` — `client.py:1451-1458` (same shape).
- `embed()` — `client.py:714-722` (same shape).

Mock/deterministic path: a `MockLlmHttpClient` (`llm/testing/mock_transport.py`) is injected via the `http_client=` kwarg present on all three methods (`client.py:1176`, `1365`, `588`). `LlmHttpClient` is **always** a real transport — there is no "mock mode" of it. So **the discriminator is the transport class**: `isinstance(resolved_transport, LlmHttpClient)` ⇒ real; `MockLlmHttpClient` ⇒ exempt.

### B. Legacy provider path — `kaizen.providers.llm.*` via `LLMAgentNode`

- Real egress: `OpenAIProvider.chat()` → `client.chat.completions.create(**request_params)` at `providers/llm/openai.py:268` (async `chat_async` → `:405`). Sibling providers (anthropic/google/…) mirror this.
- Provider selection: `LLMAgentNode` branches on the `provider` param — `provider == "mock"` → `_mock_llm_response` (`nodes/ai/llm_agent.py:986`, `1068`); else `_provider_llm_response` (`:1022`, `:1073`) → `registry.get_provider(name)` → `provider_class()` (`providers/registry.py:126`).
- Mock discriminator: registry key `"mock"` → `MockProvider` (`providers/registry.py:65`, `providers/llm/mock.py:24`). So **the discriminator is the provider name / `isinstance(p, MockProvider)`**.

### C. Kaizen `Agent` (the primary "agent constructor" the issue names)

`kaizen.agent.Agent.__init__` (`agent.py:71`) takes `model` + `llm_provider` (`llm_provider="mock"` selects mock) and delegates to `BaseAgent` (`_initialize_base_agent`, `agent.py:238`). This is the "agent builds its OWN client from env" surface.

---

## 2. Design recommendations (one clear pick per open question)

### Q1 — Where does the posture (reader/setter/env-resolution) live?

**Recommendation: core `kailash-py`, enforced from `kaizen`.**
Add `src/kailash/trust/pact/governance_posture.py` holding a module-global `bool | None` override + a lock (mirror the exact shape of `_active_interceptor` / `_active_lock` in `outbound.py:531`). Re-export `is_governance_required` / `set_governance_required` at the `kailash.` top level via the existing PEP-562 `__getattr__` + `__all__` in `src/kailash/__init__.py:37,99` (same lazy pattern already used for server names).

- **Why core, not kaizen:** the issue's public surface is literally `kailash.is_governance_required()`; the D6 seam already lives in core `trust/pact`; kaizen depends on kailash (not vice-versa), so kaizen can read `kailash.is_governance_required()` at its gate. This is the clean layering framework-first mandates: **PACT/core owns the governance posture + typed error; Kaizen owns the client and performs enforcement.**
- **Resolution (most-specific-wins):** programmatic override (`set_governance_required(True/False)`) → env `KAILASH_GOVERNANCE_REQUIRED` truthy in `{1,true,yes,on}` case-insensitive → default **OFF**. Unrecognized env value → OFF (byte-identical to today). _Con:_ a process-global posture is not tenant-scoped; honest and acceptable — the issue explicitly specifies a **process/env** posture, and per-tenant governance is already the interceptor/envelope's job.

### Q2 — Gate placement (the crux: "real egress" is decidable without a network call)

**Recommendation: eager refusal at CONSTRUCTION, keyed off the resolved transport/provider class identity — with the legacy/agent path gating at construction (class known) and the LlmClient path gating at the point its real transport is bound.**

Concretely:

- **`Agent` / legacy provider selection:** at `Agent.__init__` and at `get_provider()` / `LLMAgentNode` selection, the provider class is known _before_ any call. If posture ON ∧ provider is real (not `MockProvider` / name≠`"mock"`) ∧ not `ungoverned` ∧ no governance pair present ⇒ **refuse now**.
- **`LlmClient`:** the transport is real unless a `MockLlmHttpClient` is bound or the deployment is `mock_preset()`-derived. Add a `deterministic: bool` marker to `LlmDeployment` set by `mock_preset()` (the ONE clean way to know "mock" at construction without a call), and refuse at `from_env()` / `from_deployment()` when the resolved deployment is real ∧ posture ON ∧ not `ungoverned` ∧ no pair. For the inject-at-call-time case (`complete(http_client=…)`), add a **defense-in-depth** re-check at first real-transport acquisition (the `LlmHttpClient(...)` lines in §1.A) raising the same typed error.

_Why not "always lazy at first egress"?_ The issue's acceptance text says **construction** is refused; eager refusal gives the caller the error at the call site they control, not deep inside an async send. _Why the lazy defense-in-depth too?_ Because the LlmClient transport can be injected post-construction; the second check closes that hole. Same error type both places ⇒ no double-gating ambiguity.

### Q3 — `ungoverned=True` plumbing + "own pair vs builds-own-client-from-env"

**Recommendation:** add `ungoverned: bool = False` to `LlmClient.__init__` / `from_env` / `from_deployment` and to `Agent.__init__`; store it; the gate is a no-op when set.

- **Not re-gated:** a client the caller **passes in** to an `Agent`, or a provider already wrapped by `GovernedProvider`, or a process with `active_interceptor() is not None`. "Carries its own governance pair" = `active_interceptor()` set OR the bound provider/transport is a governed proxy.
- **Gated:** only when the agent **builds its own client from env** (the `from_env` / auto-provider branch) with no pair and no `ungoverned`. Detection: the gate fires inside the env-construction branch only; a caller-supplied client never reaches it.

### Q4 — Typed error naming BOTH remedies

**Recommendation:** define `UngovernedEgressRefused(PactError)` in core `src/kailash/trust/pact/` (D6 parity → cross-SDK mirrorable), raised from the kaizen gate. Message MUST name both remedies verbatim, e.g.:

> `UngovernedEgressRefused: KAILASH_GOVERNANCE_REQUIRED is active and this <LlmClient|Agent> would make a real LLM call with no governance attached. Either (1) attach a governance pair — install_interceptor(...) or wrap the provider with GovernedProvider — or (2) pass ungoverned=True to explicitly opt out.`

### Q5 — Mock/deterministic exemption boundary (no network probe)

**Recommendation:** exempt by class identity, computed at construction:

- Legacy/Agent: `name == "mock"` or `isinstance(provider, MockProvider)`.
- LlmClient: bound transport `isinstance(_, MockLlmHttpClient)` OR `deployment.deterministic is True` (new `mock_preset()` marker).
  This is a pure type/flag check — it never issues a request, so a "would make REAL egress" decision costs nothing and cannot itself leak egress.

---

## 3. Invariants (fail-closed contract)

1. **Default OFF, byte-identical to today** — no gate fires; construction path unchanged when posture unresolved/OFF.
2. **Most-specific-wins** — programmatic override > env > default OFF; unrecognized env value ⇒ OFF.
3. **Mock/deterministic ALWAYS exempt** — by transport/provider class identity, never a probe.
4. **No double-gating** — caller-supplied client / own-pair / installed interceptor ⇒ not re-gated; single typed error type shared by eager + lazy checks.
5. **Fail-closed on the gate itself** — any error deciding real-vs-mock ⇒ treat as real ⇒ refuse (never silently allow).
6. **Thread-safe posture state** — module global + lock, mirroring `_active_interceptor`.
7. **No secrets in the error** — message names remedies only; no URL/key/model interpolation.

---

## 4. Wave-2 file-overlap answer (CRITICAL for sequencing)

**Does #1779 collide with Wave-2 2A (#1727 `max_completion_tokens` on `providers/llm/openai.py`)? — NO, if the gate is placed as recommended.**

The recommended gate placement touches:

- `src/kailash/__init__.py`, `src/kailash/trust/pact/governance_posture.py` (new), `src/kailash/trust/pact/__init__.py` (error export) — **core, 2A never touches these.**
- `packages/kailash-kaizen/src/kaizen/llm/client.py`, `llm/deployment.py` (`deterministic` marker), `llm/testing/mock_transport.py` (marker), `kaizen/agent.py` — **2A touches none of these.**
- Legacy secondary surface (optional): `kaizen/providers/registry.py` and/or `nodes/ai/llm_agent.py` provider-selection branch.

2A's file is **`providers/llm/openai.py`** (per-provider `max_completion_tokens` emission). #1779's recommended placement gates at **selection / construction**, NOT inside `openai.py`'s `chat()` body. **Zero shared file** ⇒ no merge conflict.

**Sequencing recommendation:** #1779 and 2A can run **in parallel**. The only file that could bring them into contact is `providers/llm/openai.py`; the recommended #1779 gate deliberately lives at the registry/selection + LlmClient/deployment/Agent layer and never edits `openai.py`. To keep the parallel guarantee firm, the #1779 shard MUST NOT add the gate inside any per-provider `chat()` body (that would collide with 2A and with every sibling provider); gating at `get_provider()` / `LLMAgentNode` selection covers all providers at once and stays out of 2A's diff. If the orchestrator prefers a hard guarantee, run #1779 on the core + `kaizen/llm/**` + `kaizen/agent.py` surface only and defer the optional `llm_agent.py` legacy-selection gate to a follow-up — but that deferral is not required for parallelism, since `llm_agent.py` is not in 2A's scope either.

---

## 5. Shard-fit estimate

**One shard.** Load-bearing logic ≈ posture module (~60 LOC) + `UngovernedEgressRefused` (~25) + LlmClient gate & `ungoverned` plumbing (~50) + Agent gate & plumbing (~40) + `deterministic` marker on deployment/mock_preset (~20) + top-level re-export (~10) ≈ **~205 LOC**, well under the 500-LOC load-bearing cap. Invariants held simultaneously: **7** (§3) — at the upper edge but within the 5–10 band. Call-graph depth ≈ 3 (top-level reader → kaizen gate → transport/provider identity). Feedback loop is live (Tier-2 test harness with `mock_preset` + real-egress refusal assertion), qualifying for the multiplier. Describable in 3 sentences. **Fits one Wave-2 shard.**

**Tier-2 acceptance tests (per issue):** (a) reader/setter round-trip + env resolution precedence; (b) posture ON + bare real client → `UngovernedEgressRefused` naming both remedies; (c) posture ON + `ungoverned=True` → allowed; (d) posture ON + mock/deterministic → allowed (exempt); (e) posture ON + client carrying a pair / installed interceptor → allowed (not re-gated); (f) OFF → byte-identical to today.

---

## 6. Open items / evidence-resolvable unknowns

- **`LlmDeployment.deterministic` marker** — I recommend adding it to `mock_preset()` as the construction-time mock discriminator for the LlmClient path. If `mock_preset()` already routes exclusively through an injected `MockLlmHttpClient` at call sites (i.e. the deployment is never used without the mock transport), the marker is optional and the transport-class check alone suffices. **Resolves by:** reading `mock_preset()`'s body + its Tier-2 usage in `tests/unit/llm/` to confirm whether a mock deployment can ever bind a real `LlmHttpClient`.
- **Cross-SDK D6 handoff (Rust SDK):** EATP D6 is a live contract in this tree; a `governance_required` posture likely needs a Rust-SDK mirror. This is a **cross-repo action** — NOT self-authorized here. Surfaced as PENDING: if parity is required, it needs a filed issue on the Rust SDK repo with the operator's authorization (per handoff-completion + repo-scope-discipline). Flagged, not actioned.

---

## 7. Deliverable pointers

- Design doc: `workspaces/issue-1720-llm-consolidation/01-analysis/1779-governance-egress-analysis.md` (this file).
- Primary impl surface (Wave-2): core `src/kailash/trust/pact/governance_posture.py` (new) + `src/kailash/__init__.py`; `kaizen/llm/client.py`, `kaizen/agent.py`, `kaizen/llm/deployment.py`, `kaizen/llm/testing/mock_transport.py`.
- Non-overlap with 2A confirmed: `providers/llm/openai.py` is NOT in #1779's recommended diff.

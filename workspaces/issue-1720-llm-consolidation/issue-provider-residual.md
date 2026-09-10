## Summary

`#2069` closed on a fix that covers only the **keyless** path. Its own acceptance criterion — _"unknown models fail loudly rather than defaulting"_ — does **not** hold when an API key is present, which is the common developer configuration. An unrecognized model still resolves silently to `openai`, which is the exact behaviour `#2069`'s title names.

This is live in **published `kailash-kaizen 2.46.0`** (on PyPI since 2026-08-17), not just on trunk.

## Reproduction (run this session against `origin/dev`)

```python
import os, sys
sys.path.insert(0, "packages/kailash-kaizen/src")
from kaizen.agent_config import AgentConfig

def probe(model, env=None):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    if env:
        os.environ[env] = "sk-test-not-real"
    try:
        return f"llm_provider={AgentConfig(model=model).llm_provider!r}"
    except Exception as e:
        return f"{type(e).__module__}.{type(e).__name__}"
```

Observed:

```
=== KEYLESS ===
  llama-3.1        -> kaizen.config.providers.ConfigurationError
  mistral-large    -> kaizen.config.providers.ConfigurationError
  gpt-4            -> llm_provider='openai'
=== WITH OPENAI_API_KEY SET ===
  llama-3.1        -> llm_provider='openai'      <-- silent wrong-vendor dispatch
  mistral-large    -> llm_provider='openai'      <-- silent wrong-vendor dispatch
  gpt-4            -> llm_provider='openai'
```

The keyless column is the discrimination control: the same code path **can** return a loud error, so the keyed result is a real behavioural difference and not an artifact of the probe.

## Why this matters more than a mis-set default

An Ollama user runs a **local** model precisely so the prompt does not leave the machine. If `OPENAI_API_KEY` happens to be exported — extremely common on a developer box, and often set for an unrelated tool — then `AgentConfig(model="llama-3.1")` dispatches to **OpenAI**:

- the prompt, and any context or retrieved documents in it, are sent to a third-party API the user did not choose;
- it is billed;
- nothing warns. There is no log line, no exception, no diagnostic.

Supplying a _credential for one vendor_ is being read as _evidence about which vendor a model belongs to_. Those are unrelated facts.

## Root cause

`resolve_agent_provider` composes model-keyed resolution first, then falls back to `detect_provider_from_env()` (`packages/kailash-kaizen/src/kaizen/core/_provider_env.py:55-81`), whose order is `OPENAI_API_KEY` -> `ANTHROPIC_API_KEY` -> `None`.

The model-keyed registry is 7 prefix rows (`packages/kailash-kaizen/src/kaizen/llm/provider.py:244`): `claude-` -> anthropic, `deepseek-` -> deepseek, `gemini-` -> google, `gpt-`/`o1-`/`o3-`/`o4-` -> openai. **There is no `ollama` row and there cannot be one** — Ollama serves arbitrary model names, so no prefix identifies it.

So every Ollama model name misses the registry and lands in the env fallback by construction. The fallback's own docstring (`_provider_env.py:117-124`) calls it "a GUESS".

## Suggested fix

Two options; recommending the first.

1. **Do not let the env fallback resolve a model the registry did not recognize.** If model-keyed resolution fails, raise `ConfigurationError` naming the model and instructing the caller to pass `llm_provider=` explicitly — i.e. make the keyed path behave like the keyless path already does. The env key answers "what credentials exist", never "what vendor is this model". Breaking for anyone currently relying on the guess, which is the point: today that reliance is silent and sometimes wrong.

2. If (1) is judged too breaking for a patch release, then per the secure-default rule an env-guessed provider for an unregistered model MUST emit a **loud one-time WARN** at resolution naming the model, the guessed provider, and the exact wiring to set it explicitly. A silent no-op default is not acceptable for a dispatch decision that leaves the machine.

## Acceptance criteria

- [ ] `AgentConfig(model="llama-3.1")` with `OPENAI_API_KEY` set does not silently resolve to `openai` — it raises, or warns loudly and unmissably.
- [ ] A test pins the **keyed** case specifically. `#2069`'s tests pinned only the keyless case, which is how this shipped.
- [ ] The test asserts both poles: keyless raises AND keyed does not silently dispatch. A single-pole test cannot distinguish this fix from the one already shipped.
- [ ] CHANGELOG records the behaviour change against the version it ships in.

## Related

- `#2069` — the parent; closed 2026-08-16, fix `3300eb341`, released in kaizen 2.46.0. Its acceptance criteria were partially met.
- `#1952` — the keyless silent-mock fallback, the sibling defect in the same resolver.
- `#1899` — a passed client's provider ignored in favour of model-name prefix routing; same "infer the vendor" family.

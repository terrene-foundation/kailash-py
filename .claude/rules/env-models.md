# Environment Variables & Model Rules

## .env Is The Single Source of Truth

ALL API keys and model names MUST be read from `.env`. NEVER hardcode.

**Why:** Hardcoded keys leak into git history and hardcoded models lock deployments to a single provider, preventing rotation or migration.

## NEVER Hardcode Model Names

**Why:** Hardcoded model names break when providers deprecate versions, and prevent per-environment model selection (e.g., cheaper model for dev, capable model for prod).

```
BLOCKED: model="gpt-4"
BLOCKED: model="claude-3-opus"
BLOCKED: model="gemini-1.5-pro"
```

```python
# ✅ Python
import os
from dotenv import load_dotenv
load_dotenv()
model = os.environ.get("OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL"))

# ✅ TypeScript
const model = process.env.OPENAI_PROD_MODEL ?? process.env.DEFAULT_LLM_MODEL;
```

## ALWAYS Load .env Before Operations

**Why:** Accessing `os.environ` before `load_dotenv()` returns `None` for every `.env`-defined key, causing silent failures or crashes deep in the call stack.

```python
from dotenv import load_dotenv
load_dotenv()  # MUST be before any os.environ access
```

For pytest: root `conftest.py` auto-loads `.env`.

## Model-Key Pairings

| Model Prefix                    | Required Key                         |
| ------------------------------- | ------------------------------------ |
| `gpt-*`, `o1-*`, `o3-*`, `o4-*` | `OPENAI_API_KEY`                     |
| `claude-*`                      | `ANTHROPIC_API_KEY`                  |
| `gemini-*`                      | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `deepseek-*`                    | `DEEPSEEK_API_KEY`                   |
| `mistral-*`, `mixtral-*`        | `MISTRAL_API_KEY`                    |

NO EXCEPTIONS. If `.env` doesn't have the key, fix the `.env` — don't hardcode.

**Why:** Sending requests with a mismatched model-key pairing produces opaque 401/403 errors that are hard to diagnose downstream.

# Environment Variables & Model Rules

## Scope

These rules apply to ALL operations involving API keys, LLM models, or environment configuration.

## ABSOLUTE RULES (BLOCKING - Exit Code 2)

### 1. .env Is The Single Source of Truth

ALL API keys and model names MUST be read from `.env`. NEVER hardcode them.

**Before ANY LLM operation**: Check `.env` for current model names and keys.

### 2. NEVER Hardcode Model Names

MUST NOT use hardcoded model strings like `"gpt-4"`, `"claude-3-opus"`, `"gemini-pro"`.

**Detection Patterns:**

```
BLOCKED: model="gpt-4"
BLOCKED: model="claude-3-opus"
BLOCKED: model="gemini-1.5-pro"
BLOCKED: "model_name": "gpt-4o"
```

**Correct Pattern (Python):**

```python
import os
from dotenv import load_dotenv
load_dotenv()

model = os.environ.get("OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL"))
```

**Correct Pattern (TypeScript):**

```typescript
const model = process.env.OPENAI_PROD_MODEL ?? process.env.DEFAULT_LLM_MODEL;
```

**Enforced by**: validate-workflow.js hook (BLOCKS Python, WARNS JS/TS)
**Violation**: BLOCK - must fix before proceeding

### 3. ALWAYS Load .env Before Operations

Every Python script, test, or service that uses environment variables MUST load .env first.

**Correct Pattern:**

```python
from dotenv import load_dotenv
load_dotenv()  # MUST be before any os.environ access
```

**For pytest**: Root `conftest.py` auto-loads `.env` (no manual setup needed).

**Enforced by**: session-start.js hook, validate-workflow.js hook
**Violation**: BLOCK test/script execution

### 4. Model-Key Pairings

Each model provider requires a matching API key in `.env`:

| Model Prefix                    | Required Key(s)                      |
| ------------------------------- | ------------------------------------ |
| `gpt-*`, `o1-*`, `o3-*`, `o4-*` | `OPENAI_API_KEY`                     |
| `claude-*`                      | `ANTHROPIC_API_KEY`                  |
| `gemini-*`                      | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `deepseek-*`                    | `DEEPSEEK_API_KEY`                   |
| `mistral-*`, `mixtral-*`        | `MISTRAL_API_KEY`                    |
| `command-*`                     | `COHERE_API_KEY`                     |
| `pplx-*`, `sonar-*`             | `PERPLEXITY_API_KEY`                 |

If a `*_MODEL` var references a model but the corresponding key is missing, the session-start hook will WARN and validate-workflow will BLOCK Python writes.

**Enforced by**: lib/env-utils.js (shared by all hooks)

## Exceptions

NO EXCEPTIONS. This rule is absolute. If `.env` doesn't have the key, fix the `.env` — don't hardcode.

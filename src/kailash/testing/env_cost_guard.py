# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Active LLM cost-guard for pytest — never spend on a bare test run.

Invariant
---------
A bare ``pytest`` (no ``KAIZEN_ALLOW_REAL_LLM=1``) MUST make ZERO billed LLM
calls, even when a real provider credential sits in ``.env`` OR is exported in
the shell. A test that would reach a provider must find no credential.

Why an *active* guard (not a decline-to-add loader)
---------------------------------------------------
An earlier design merely *withheld* provider secrets while parsing ``.env``.
That is defeated three ways, all live in this repo:

1. **Incomplete name match.** ``AWS_BEARER_TOKEN_BEDROCK`` (a billable Bedrock
   key) ends in neither ``_API_KEY`` nor ``_SECRET``.
2. **Re-injection.** Any later ``load_dotenv()`` — and dozens of test modules
   call it at import scope — re-adds every withheld key (``override=False``
   only skips keys already present; the withheld ones are absent).
3. **Unguarded sibling sessions / inherited env.** A sub-package that declares
   its own pytest ``rootdir`` never runs the repo-root guard; a shell-exported
   key is never in ``.env`` at all.

So the guard is active and process-wide:

* :func:`is_provider_secret` — a comprehensive, fail-closed name predicate
  (substring + suffix families covering every provider credential shape).
* :func:`scrub_provider_secrets` — POPS every provider secret already present
  in ``os.environ`` (unless opted in). Removes inherited/exported keys too.
* :func:`install_dotenv_guard` — monkeypatches ``dotenv.load_dotenv`` so EVERY
  call (conftest, module-scope, runtime fixture) scrubs afterward.
* :func:`install_cost_guard` — the one-call entry every conftest uses:
  monkeypatch + guarded load + scrub. Idempotent.

Model names, DB URLs, and every non-secret var still load normally; an
already-set env var is never overridden.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"

# This is a COST guard: it scopes to LLM-PROVIDER credentials — the only keys
# whose presence causes LLM billing. It deliberately does NOT scrub every
# secret-shaped var: an over-broad predicate that popped app secrets like
# ``SAAS_STARTER_JWT_SECRET`` or infra creds like ``DB_PASSWORD`` /
# ``AWS_ACCESS_KEY_ID`` would break non-LLM tests that legitimately set them,
# without preventing any LLM spend.

# Config vars that are NEVER credentials (loaded normally even if a provider
# token appears in the name, e.g. ``OPENAI_PROD_MODEL``).
_NONSECRET_SUFFIXES = (
    "_MODEL",
    "_URL",
    "_BASE_URL",
    "_BASE",
    "_ENDPOINT",
    "_HOST",
    "_PORT",
    "_REGION",
    "_LOCATION",
    "_VERSION",
    "_API_VERSION",
    "_DEPLOYMENT",
    "_DEPLOYMENT_NAME",
    "_ORG",
    "_ORG_ID",
    "_ORGANIZATION",
    "_PROJECT",
    "_PROJECT_ID",
)

# Credential-shaped suffixes (a secret ends this way).
_CREDENTIAL_SUFFIXES = ("_KEY", "_SECRET", "_TOKEN", "_CREDENTIALS", "_APIKEY")

# Known LLM-provider name fragments. A credential-shaped name containing one of
# these is a provider secret. (Generic ``*_API_KEY`` / ``*_API_TOKEN`` is also
# caught below, covering any provider not enumerated here.)
_LLM_PROVIDER_TOKENS = (
    "OPENAI",
    "ANTHROPIC",
    "CLAUDE",
    "GEMINI",
    "VERTEX",
    "DEEPSEEK",
    "MISTRAL",
    "MIXTRAL",
    "COHERE",
    "REPLICATE",
    "HUGGINGFACE",
    "HUGGING_FACE",
    "TOGETHER",
    "GROQ",
    "PERPLEXITY",
    "FIREWORKS",
    "OPENROUTER",
    "BEDROCK",
    "AZURE_OPENAI",
    "WATSONX",
    "AI21",
    "NVIDIA",
    "XAI",
    "MOONSHOT",
    "DASHSCOPE",
    "ANYSCALE",
    "DEEPINFRA",
    "OLLAMA",
)

# Explicit provider-credential names that don't fit the shape rules above.
_EXPLICIT_PROVIDER_SECRETS = frozenset(
    {
        "GOOGLE_APPLICATION_CREDENTIALS",  # Vertex/Gemini service-account JSON path
        "HF_TOKEN",  # HuggingFace short form
        "HF_API_TOKEN",
    }
)


def _real_llm_allowed() -> bool:
    """True only when the operator explicitly opted into real (billed) LLM calls."""
    return os.environ.get(_REAL_LLM_ENV_FLAG) == "1"


def is_provider_secret(key: str) -> bool:
    """True if ``key`` names an LLM-PROVIDER credential that would bill on a bare run.

    Scoped to LLM billing — the guard's purpose. Returns True for:
      * any ``*_API_KEY`` / ``*_API_TOKEN`` (generic provider-credential shape);
      * a credential-shaped name (``*_KEY`` / ``*_SECRET`` / ``*_TOKEN`` /
        ``*_CREDENTIALS``, or containing ``BEARER``) that ALSO names a known LLM
        provider (``OPENAI``, ``ANTHROPIC``, ``BEDROCK``, ``AZURE_OPENAI`` …);
      * a small explicit set (``GOOGLE_APPLICATION_CREDENTIALS``, ``HF_TOKEN`` …).

    Returns False for config vars (``*_MODEL``, ``*_URL``, ``*_REGION`` …) and for
    NON-LLM secrets (``SAAS_STARTER_JWT_SECRET``, ``DB_PASSWORD``,
    ``AWS_ACCESS_KEY_ID`` …) — those cause no LLM spend and are needed by tests
    that set them; scrubbing them was a real regression.
    """
    k = key.upper()
    if k in _EXPLICIT_PROVIDER_SECRETS:
        return True
    if any(k.endswith(suf) for suf in _NONSECRET_SUFFIXES):
        return False
    # Generic provider-credential shape (covers any provider, enumerated or not).
    if k.endswith("_API_KEY") or k.endswith("_API_TOKEN"):
        return True
    # Named LLM provider + credential shape.
    names_provider = any(tok in k for tok in _LLM_PROVIDER_TOKENS)
    credential_shaped = "BEARER" in k or any(
        k.endswith(suf) for suf in _CREDENTIAL_SUFFIXES
    )
    return names_provider and credential_shaped


def scrub_provider_secrets(environ: Optional[dict] = None) -> list[str]:
    """Remove every provider-secret env var from ``environ`` unless opted in.

    Active removal — closes the re-injection (a later ``load_dotenv``) and the
    inherited/exported-key vectors that a decline-to-add loader cannot. Returns
    the list of removed NAMES (never values) for optional diagnostics.
    """
    if _real_llm_allowed():
        return []
    env = os.environ if environ is None else environ
    removed = [k for k in list(env.keys()) if is_provider_secret(k)]
    for k in removed:
        env.pop(k, None)
    return removed


_GUARD_ATTR = "_kailash_cost_guard_wrapped"


def install_dotenv_guard() -> None:
    """Monkeypatch ``dotenv.load_dotenv`` so every call scrubs provider secrets.

    Idempotent and process-wide: once installed, any ``load_dotenv()`` — in a
    conftest, at module import, or inside a runtime fixture — self-scrubs unless
    ``KAIZEN_ALLOW_REAL_LLM=1``. A no-op if python-dotenv is not importable.
    """
    try:
        import dotenv
        import dotenv.main as dotenv_main
    except ImportError:
        return

    real = dotenv.load_dotenv
    if getattr(real, _GUARD_ATTR, False):
        return  # already wrapped

    def _guarded_load_dotenv(*args, **kwargs):
        result = real(*args, **kwargs)
        scrub_provider_secrets()
        return result

    setattr(_guarded_load_dotenv, _GUARD_ATTR, True)
    dotenv.load_dotenv = _guarded_load_dotenv
    # Modules that did `from dotenv import load_dotenv` after this point pick up
    # the wrapper; patch the canonical definition site too.
    dotenv_main.load_dotenv = _guarded_load_dotenv


def _find_env_upwards() -> Optional[Path]:
    """Locate the nearest ``.env`` by walking up from the cwd (dependency-free)."""
    here = Path.cwd()
    for d in (here, *here.parents):
        candidate = d / ".env"
        if candidate.exists():
            return candidate
    return None


def _parse_env_file(env_path: Path) -> dict:
    """Parse a ``.env`` file into a dict WITHOUT python-dotenv.

    The cost-guard is installed at every package rootdir, including packages that
    do not declare ``python-dotenv`` (dataflow, pact, nexus, align, ml). A hard
    ``import dotenv`` here would crash their test collection — so the parse is
    dependency-free (same lightweight grammar the repo-root conftest used).
    """
    result: dict = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip()
        val = line[eq + 1 :].strip()
        is_quoted = (val.startswith('"') and val.endswith('"') and len(val) >= 2) or (
            val.startswith("'") and val.endswith("'") and len(val) >= 2
        )
        if is_quoted:
            val = val[1:-1]
        else:
            comment_idx = val.find(" #")
            if comment_idx > -1:
                val = val[:comment_idx].strip()
        result[key] = val
    return result


def load_env_cost_guarded(env_path: Optional[Path] = None) -> None:
    """Load ``.env`` into ``os.environ`` with the cost-guard applied.

    Provider secrets are withheld on load AND actively scrubbed afterward.
    Model names, DB URLs, and non-secret vars load; already-set vars are not
    overridden. Dependency-free (no python-dotenv required).

    Args:
        env_path: Path to the ``.env`` file. When ``None``, the nearest ``.env``
            is located by walking up from the current working directory.
    """
    if env_path is None:
        env_path = _find_env_upwards()
        if env_path is None:
            scrub_provider_secrets()
            return
    env_path = Path(env_path)
    if not env_path.exists():
        scrub_provider_secrets()
        return

    allow_real_llm = _real_llm_allowed()
    for key, val in _parse_env_file(env_path).items():
        if val is None:
            continue
        if not allow_real_llm and is_provider_secret(key):
            continue  # withhold on load …
        if key not in os.environ:
            os.environ[key] = val
    # … and actively scrub anything already present (inherited / prior load).
    scrub_provider_secrets()


def install_cost_guard(env_path: Optional[Path] = None) -> None:
    """One-call cost-guard setup for a pytest conftest.

    (1) monkeypatch ``dotenv.load_dotenv`` (guards module-scope + runtime calls),
    (2) load ``.env`` with secrets withheld, (3) actively scrub. Idempotent —
    safe to call from the repo-root conftest AND every sub-package conftest.
    """
    install_dotenv_guard()
    load_env_cost_guarded(env_path)
    scrub_provider_secrets()

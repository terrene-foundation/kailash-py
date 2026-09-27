# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2220 residual — a SHAPE guard, so this class cannot silently re-open.

#2220 was fixed once at ``resolve_agent_provider`` and stayed live at ~30
other sites, because each of those sites had independently reached for
``detect_provider_from_env()`` and paired its answer with a ``model``. Fixing
those sites one by one closes today's instances and nothing else: the next
RAG node or agent surface added re-opens the hole, silently, and the next
person to measure it starts from scratch.

So the property is asserted STRUCTURALLY over the whole package, not
enumerated. Two independent checks, because they fail in different directions:

1. **The direct-call check.** ``detect_provider_from_env`` answers "which
   credentials exist". Only the module that defines it may call it; every
   other caller goes through ``resolve_node_provider`` (model-keyed, fails
   closed) or ``describe_node_provider`` (non-dispatching, for cache keys).
   A new module calling it directly fails here, named with its line.

2. **The composition check.** The defect shape itself, independent of which
   helper produced the value: a dict literal that is an LLM node config —
   it has a ``model`` key — whose ``provider`` value is computed from the
   environment. This catches a re-opening that bypasses check 1 by reading
   ``os.environ["OPENAI_API_KEY"]`` inline instead of calling the helper.

Both walk the AST rather than grepping, and both resolve import ALIASES:
``core/agents.py`` and ``core/base_agent.py`` each imported the helper under
a private alias (``_detect_provider_from_env``, ``_detect_provider``), so a
literal-name grep would have under-counted the original defect set by two of
its highest-harm members.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

ENV_HELPER = "detect_provider_from_env"

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "kaizen"

# The ONE module permitted to call the credential helper: the module that
# defines it, whose `resolve_node_provider` delegates to it on the no-model
# path. Adding an entry here is a deliberate, reviewable act — which is the
# point. It is keyed by path relative to `src/kaizen`.
DIRECT_CALL_ALLOWLIST = {"core/_provider_env.py"}

# Credential env vars that answer "which account do I hold", never "which
# vendor serves this model".
CREDENTIAL_VARS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}


def _python_files() -> list[pathlib.Path]:
    return sorted(SRC.rglob("*.py"))


def _aliases_for(tree: ast.AST, name: str) -> set[str]:
    """Every local name bound to ``name`` by an import in this module."""
    found = {name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name:
                    found.add(alias.asname or alias.name)
    return found


def _called_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_no_module_calls_the_credential_helper_directly():
    """Check 1 — every model-bearing site routes through the shared predicate.

    Fails naming file and line, so a new un-routed site reds in CI with the
    exact location rather than a count.
    """
    offenders: list[str] = []

    for path in _python_files():
        rel = path.relative_to(SRC).as_posix()
        if rel in DIRECT_CALL_ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(), str(path))
        aliases = _aliases_for(tree, ENV_HELPER)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) in aliases:
                offenders.append(f"  {rel}:{node.lineno}")

    assert not offenders, (
        "These sites call detect_provider_from_env() directly:\n"
        + "\n".join(offenders)
        + "\n\nThat helper answers 'which credentials exist'. Pairing its "
        "answer with a model in a node config is the #2220 defect: it sent "
        "locally-served models' prompts to whichever vendor happened to hold "
        "a key.\n"
        "Use kaizen.core._provider_env.resolve_node_provider(model, "
        "explicit=..., component=...) instead — it is model-keyed and fails "
        "closed. For a non-dispatching use such as a cache key, use "
        "describe_node_provider(), which never raises."
    )


def test_no_node_config_computes_its_provider_from_the_environment():
    """Check 2 — the defect SHAPE, whoever produced the value.

    A dict literal carrying both ``model`` and ``provider`` is an LLM node
    config. Its ``provider`` value must not be derived from a credential
    env var — directly, or via the credential helper under any alias.
    """
    offenders: list[str] = []

    for path in _python_files():
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(), str(path))
        aliases = _aliases_for(tree, ENV_HELPER)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if not {"model", "provider"} <= keys:
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "provider"):
                    continue
                for inner in ast.walk(value):
                    if isinstance(inner, ast.Call) and _called_name(inner) in aliases:
                        offenders.append(
                            f"  {rel}:{key.lineno} (provider from {ENV_HELPER})"
                        )
                    if isinstance(inner, ast.Constant) and inner.value in (
                        CREDENTIAL_VARS
                    ):
                        offenders.append(
                            f"  {rel}:{key.lineno} (provider from {inner.value})"
                        )

    assert not offenders, (
        "These LLM node configs decide 'provider' from the environment while "
        "also carrying a 'model':\n"
        + "\n".join(offenders)
        + "\n\nA credential names the account you hold, never the vendor that "
        "serves this model (#2220). Resolve with resolve_node_provider(model, "
        "...) so an unregistered model fails closed instead of being "
        "dispatched to whichever vendor has a key."
    )


def test_the_guard_can_actually_see_a_violation():
    """Negative control for both checks above.

    Without this, a guard that silently matched nothing — a renamed helper, a
    moved source root, an AST walk that never reached a node — would pass
    exactly as loudly as a clean tree. Both checks are fired at a synthetic
    module that deliberately contains the defect, and must find it.
    """
    offending_source = (
        "from kaizen.core._provider_env import detect_provider_from_env as _d\n"
        "cfg = {'provider': _d(), 'model': 'llama3.1:8b'}\n"
    )
    tree = ast.parse(offending_source, "<synthetic>")
    aliases = _aliases_for(tree, ENV_HELPER)

    # Check 1's matcher must see the aliased call.
    assert "_d" in aliases, "alias resolution failed — check 1 would under-count"
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _called_name(n) in aliases
    ]
    assert len(calls) == 1, f"check 1's matcher found {len(calls)} calls, expected 1"

    # Check 2's matcher must see the model+provider composition.
    dicts = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Dict)
        and {"model", "provider"}
        <= {k.value for k in n.keys if isinstance(k, ast.Constant)}
    ]
    assert len(dicts) == 1, f"check 2's matcher found {len(dicts)} dicts, expected 1"


def test_source_root_is_real():
    """A guard pointed at an empty directory passes vacuously.

    ``SRC`` is computed by walking up from this file, so a tests/ move would
    silently aim both checks at nothing.
    """
    assert SRC.is_dir(), f"source root does not exist: {SRC}"
    files = _python_files()
    assert len(files) > 100, f"source root looks wrong: only {len(files)} files"

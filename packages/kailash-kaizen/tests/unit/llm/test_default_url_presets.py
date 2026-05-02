# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Default-URL convenience preset tests (#787).

Cross-SDK parity with kailash-rs zero-arg classmethods on `LlmDeployment`:

- `LlmDeployment::ollama_default()`        → `crates/kailash-kaizen/src/llm/deployment/presets.rs:509`
- `LlmDeployment::lm_studio_default()`     → `presets.rs:1138`
- `LlmDeployment::llama_cpp_default()`     → `presets.rs:1170`
- `LlmDeployment::docker_model_runner()`   → `presets.rs:527`

Each Python `<provider>_default_preset(model)` factory is byte-equivalent to
calling the parent factory with the canonical localhost URL kailash-rs
publishes. The deployment carries the PARENT preset literal (`"ollama"`,
`"lm_studio"`, etc.) per Rust semantics — `<provider>_default()` calls
`Self::<provider>(...)` internally — so capability-matrix lookups behave
identically to the long-form constructor (`for_preset("ollama")` and
`for_preset(deployment.preset_name)` agree).

Per `rules/cross-sdk-inspection.md` § 3 EATP D6: implementation-idiom
difference (Python requires `model` per `rules/env-models.md`; Rust accepts
truly zero-arg) is acceptable when semantics match.
"""

from __future__ import annotations

import pytest

from kaizen.llm.auth.bearer import StaticNone
from kaizen.llm.deployment import LlmDeployment, WireProtocol
from kaizen.llm.presets import (
    docker_model_runner_default_preset,
    docker_model_runner_preset,
    get_preset,
    list_presets,
    llama_cpp_default_preset,
    llama_cpp_preset,
    lm_studio_default_preset,
    lm_studio_preset,
    ollama_default_preset,
    ollama_preset,
)

# ---------------------------------------------------------------------------
# Cross-SDK parity: registry name byte-match the Rust classmethod literals
# ---------------------------------------------------------------------------


_DEFAULT_URL_PRESETS_RUST_PARITY = frozenset(
    {
        "ollama_default",
        "lm_studio_default",
        "llama_cpp_default",
        "docker_model_runner_default",
    }
)


def test_default_url_preset_names_match_rust_literals() -> None:
    """Each `_default` registry name byte-matches the Rust classmethod literal.

    Rust exposes `LlmDeployment::ollama_default()` etc. Python's registry
    convention names the convenience surface `<parent>_default` to keep both
    `get_preset("ollama_default")` and `LlmDeployment.ollama_default(model)`
    grep-able cross-SDK.
    """
    registered = set(list_presets())
    missing = _DEFAULT_URL_PRESETS_RUST_PARITY - registered
    assert not missing, (
        f"Default-URL presets missing from registry: {sorted(missing)}. "
        f"Every Rust `<provider>_default()` classmethod MUST have a Python "
        f"registered factory under the byte-matching name."
    )


# ---------------------------------------------------------------------------
# Ollama default — http://localhost:11434/v1
# ---------------------------------------------------------------------------


def test_ollama_default_preset_shape() -> None:
    """`ollama_default_preset(model)` yields a deployment with the canonical
    localhost URL and the parent preset_name."""
    dep = ollama_default_preset("llama3.1")
    assert dep.wire == WireProtocol.OllamaNative
    assert isinstance(dep.auth, StaticNone)
    assert dep.default_model == "llama3.1"
    assert dep.preset_name == "ollama"  # parent literal, mirrors Rust
    # Pydantic HttpUrl normalises path-bearing URLs without a trailing slash;
    # str() coercion is required because Endpoint.base_url is HttpUrl, not str.
    assert str(dep.endpoint.base_url) == "http://localhost:11434/v1"
    assert dep.endpoint.path_prefix == ""


def test_ollama_default_preset_byte_equivalent_to_long_form() -> None:
    """`ollama_default_preset(model)` ≡ `ollama_preset(default_url, model)`.

    Cross-SDK invariant: Rust's `ollama_default()` calls `Self::ollama(URL)`,
    so the resulting deployment is indistinguishable from the long-form. The
    Python variant MUST preserve the same equivalence.
    """
    short = ollama_default_preset("llama3.1")
    long = ollama_preset("http://localhost:11434/v1", "llama3.1")
    assert short.wire == long.wire
    assert short.preset_name == long.preset_name
    assert short.default_model == long.default_model
    assert short.endpoint.base_url == long.endpoint.base_url
    assert short.endpoint.path_prefix == long.endpoint.path_prefix


def test_ollama_default_classmethod_matches_factory() -> None:
    """`LlmDeployment.ollama_default(model)` matches the free function."""
    cm = LlmDeployment.ollama_default("llama3.1")
    fn = ollama_default_preset("llama3.1")
    assert cm.preset_name == fn.preset_name == "ollama"
    assert cm.endpoint.base_url == fn.endpoint.base_url
    assert cm.default_model == fn.default_model == "llama3.1"


def test_ollama_default_rejects_empty_model() -> None:
    """Per `rules/env-models.md`: model is REQUIRED, never silently defaulted."""
    with pytest.raises(ValueError, match="model"):
        ollama_default_preset("")


# ---------------------------------------------------------------------------
# LM Studio default — http://localhost:1234/v1
# ---------------------------------------------------------------------------


def test_lm_studio_default_preset_shape() -> None:
    dep = lm_studio_default_preset("Meta-Llama-3.1-8B-Instruct")
    assert dep.wire == WireProtocol.OpenAiChat
    assert isinstance(dep.auth, StaticNone)
    assert dep.default_model == "Meta-Llama-3.1-8B-Instruct"
    assert dep.preset_name == "lm_studio"
    # Pydantic HttpUrl normalises hostname-only URLs by appending a trailing
    # slash; str() coercion is required because Endpoint.base_url is HttpUrl.
    assert str(dep.endpoint.base_url) == "http://localhost:1234/"
    # lm_studio_preset's path_prefix default is "/v1"
    assert dep.endpoint.path_prefix == "/v1"


def test_lm_studio_default_preset_byte_equivalent_to_long_form() -> None:
    short = lm_studio_default_preset("Meta-Llama-3.1-8B-Instruct")
    long = lm_studio_preset("http://localhost:1234", "Meta-Llama-3.1-8B-Instruct")
    assert short.wire == long.wire
    assert short.preset_name == long.preset_name
    assert short.default_model == long.default_model
    assert short.endpoint.base_url == long.endpoint.base_url
    assert short.endpoint.path_prefix == long.endpoint.path_prefix


def test_lm_studio_default_classmethod_matches_factory() -> None:
    cm = LlmDeployment.lm_studio_default("Meta-Llama-3.1-8B-Instruct")
    fn = lm_studio_default_preset("Meta-Llama-3.1-8B-Instruct")
    assert cm.preset_name == fn.preset_name == "lm_studio"
    assert cm.endpoint.base_url == fn.endpoint.base_url


def test_lm_studio_default_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        lm_studio_default_preset("")


# ---------------------------------------------------------------------------
# llama.cpp default — http://localhost:8080/v1
# ---------------------------------------------------------------------------


def test_llama_cpp_default_preset_shape() -> None:
    dep = llama_cpp_default_preset("llama-3-8b-instruct")
    assert dep.wire == WireProtocol.OpenAiChat
    assert isinstance(dep.auth, StaticNone)
    assert dep.default_model == "llama-3-8b-instruct"
    assert dep.preset_name == "llama_cpp"
    assert str(dep.endpoint.base_url) == "http://localhost:8080/"
    assert dep.endpoint.path_prefix == "/v1"


def test_llama_cpp_default_preset_byte_equivalent_to_long_form() -> None:
    short = llama_cpp_default_preset("llama-3-8b-instruct")
    long = llama_cpp_preset("http://localhost:8080", "llama-3-8b-instruct")
    assert short.wire == long.wire
    assert short.preset_name == long.preset_name
    assert short.default_model == long.default_model
    assert short.endpoint.base_url == long.endpoint.base_url
    assert short.endpoint.path_prefix == long.endpoint.path_prefix


def test_llama_cpp_default_classmethod_matches_factory() -> None:
    cm = LlmDeployment.llama_cpp_default("llama-3-8b-instruct")
    fn = llama_cpp_default_preset("llama-3-8b-instruct")
    assert cm.preset_name == fn.preset_name == "llama_cpp"
    assert cm.endpoint.base_url == fn.endpoint.base_url


def test_llama_cpp_default_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        llama_cpp_default_preset("")


# ---------------------------------------------------------------------------
# Docker Model Runner default — http://localhost:12434/engines/llama.cpp/v1
# ---------------------------------------------------------------------------


def test_docker_model_runner_default_preset_shape() -> None:
    """The `_default` variant uses Rust's engine-specific path
    `/engines/llama.cpp/v1`, which differs from `docker_model_runner_preset`'s
    generic `/engines/v1` default — both are valid Docker Model Runner
    endpoints; the convenience variant targets the llama.cpp engine specifically
    per Rust's zero-arg shortcut."""
    dep = docker_model_runner_default_preset("ai/llama3.2:3B-Q4_0")
    assert dep.wire == WireProtocol.OpenAiChat
    assert isinstance(dep.auth, StaticNone)
    assert dep.default_model == "ai/llama3.2:3B-Q4_0"
    assert dep.preset_name == "docker_model_runner"
    assert str(dep.endpoint.base_url) == "http://localhost:12434/"
    assert dep.endpoint.path_prefix == "/engines/llama.cpp/v1"


def test_docker_model_runner_default_preset_byte_equivalent_to_long_form() -> None:
    short = docker_model_runner_default_preset("ai/llama3.2:3B-Q4_0")
    long = docker_model_runner_preset(
        "http://localhost:12434",
        "ai/llama3.2:3B-Q4_0",
        path_prefix="/engines/llama.cpp/v1",
    )
    assert short.wire == long.wire
    assert short.preset_name == long.preset_name
    assert short.default_model == long.default_model
    assert short.endpoint.base_url == long.endpoint.base_url
    assert short.endpoint.path_prefix == long.endpoint.path_prefix


def test_docker_model_runner_default_classmethod_matches_factory() -> None:
    cm = LlmDeployment.docker_model_runner_default("ai/llama3.2:3B-Q4_0")
    fn = docker_model_runner_default_preset("ai/llama3.2:3B-Q4_0")
    assert cm.preset_name == fn.preset_name == "docker_model_runner"
    assert cm.endpoint.base_url == fn.endpoint.base_url
    assert cm.endpoint.path_prefix == fn.endpoint.path_prefix


def test_docker_model_runner_default_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        docker_model_runner_default_preset("")


# ---------------------------------------------------------------------------
# Registry round-trip: get_preset retrieves the same factory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,factory,model",
    [
        ("ollama_default", ollama_default_preset, "llama3.1"),
        ("lm_studio_default", lm_studio_default_preset, "Meta-Llama-3.1-8B-Instruct"),
        ("llama_cpp_default", llama_cpp_default_preset, "llama-3-8b-instruct"),
        (
            "docker_model_runner_default",
            docker_model_runner_default_preset,
            "ai/llama3.2:3B-Q4_0",
        ),
    ],
)
def test_default_url_preset_registry_roundtrip(
    name: str, factory: object, model: str
) -> None:
    """`get_preset(name)(model)` returns a deployment matching the direct
    factory call. Every default-URL preset registered AND attached as a
    classmethod survives the round-trip."""
    registered_factory = get_preset(name)
    assert registered_factory is factory, (
        f"registry maps {name!r} to a different factory; "
        f"registered={registered_factory}, expected={factory}"
    )
    via_registry = registered_factory(model=model)
    via_function = factory(model)  # type: ignore[operator]
    assert via_registry.preset_name == via_function.preset_name
    assert via_registry.endpoint.base_url == via_function.endpoint.base_url
    assert via_registry.default_model == via_function.default_model


# ---------------------------------------------------------------------------
# Capability-matrix routing: deployment carries the PARENT preset_name so
# capability lookup goes through the parent row (no orphan "_default" lookup).
# ---------------------------------------------------------------------------


def test_default_url_deployment_supports_routes_through_parent_row() -> None:
    """A deployment built via `<provider>_default` MUST report the same
    capability matrix as the parent `<provider>` preset.

    This is the structural invariant that makes the `_default` variant a
    pure constructor convenience rather than a distinct preset identity:
    `dep.preset_name` == parent literal → `dep.supports()` returns the
    parent row.
    """
    short = ollama_default_preset("llama3.1")
    long = ollama_preset("http://localhost:11434/v1", "llama3.1")
    assert short.supports() == long.supports()

    short_lms = lm_studio_default_preset("Meta-Llama-3.1-8B-Instruct")
    long_lms = lm_studio_preset("http://localhost:1234", "Meta-Llama-3.1-8B-Instruct")
    assert short_lms.supports() == long_lms.supports()

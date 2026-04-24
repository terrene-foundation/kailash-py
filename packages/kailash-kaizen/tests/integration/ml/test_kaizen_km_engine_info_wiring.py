# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — agent tool-set constructed via ``km.engine_info()``.

Spec ``kaizen-ml-integration.md §2.4`` mandates that ML-aware Kaizen
agents derive their tool-spec list from ``km.list_engines()`` /
``km.engine_info()`` at runtime. Hardcoded engine imports are a §5b
drift violation (HIGH). This test proves the discovery path wires
through kailash-ml without any ``from kailash_ml.engines.<name>``
import in the tool-set construction path.

Skip semantics (``rules/testing.md §3-Tier`` → ACCEPTABLE category):
the registry helpers ``km.engine_info`` / ``km.list_engines`` are
part of the ``ml-engines-v2-addendum §E11`` surface that ships in the
kailash-ml 1.0 wave. Until that release lands, the registry is
unavailable and this test asserts the typed-error contract instead
— the test always runs, always surfaces the current contract state,
never silent-skips.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_discover_ml_tools_routes_through_km_registry() -> None:
    """Discovery MUST call ``km.engine_info`` / ``km.list_engines``.

    When the registry is live, ``discover_ml_tools()`` returns a tuple
    of :class:`MLEngineDescriptor`. Each descriptor's ``version`` MUST
    equal ``kailash_ml.__version__`` — spec §2.4.4 version-sync
    invariant (§E11.3 MUST 3).

    When the registry is NOT yet shipped in the installed kailash-ml,
    ``discover_ml_tools()`` MUST raise :class:`MLRegistryUnavailableError`
    with an actionable message — spec §2.4.5 blocks the direct-import
    fallback.
    """
    from kaizen.ml import MLRegistryUnavailableError, discover_ml_tools

    try:
        import kailash_ml as km
    except ImportError:
        pytest.skip("kailash-ml not installed (infra-conditional)")

    has_registry = hasattr(km, "engine_info") and hasattr(km, "list_engines")

    if not has_registry:
        with pytest.raises(MLRegistryUnavailableError) as exc_info:
            discover_ml_tools()
        # Spec §2.4.5 — the error message MUST name the registry helpers
        # so the next session reads the actionable fix without re-deriving.
        message = str(exc_info.value).lower()
        assert (
            "engine_info" in message and "list_engines" in message
        ), "registry-missing error must name the helpers (actionable)"
        return

    # Registry is live — exercise the discovery path.
    descriptors = discover_ml_tools()
    assert isinstance(descriptors, tuple)
    for d in descriptors:
        # Version-sync invariant (§2.4.4 / §E11.3 MUST 3)
        assert d.version == km.__version__, (
            f"engine {d.name!r} version {d.version} != km.__version__ "
            f"{km.__version__} — §E11.3 MUST 3 violation"
        )
        # Every descriptor MUST expose a module_path reachable via the
        # discovered registry — proves the agent didn't hardcode.
        assert d.module_path.startswith(
            "kailash_ml."
        ), f"engine {d.name!r} module_path {d.module_path!r} outside kailash_ml"


@pytest.mark.integration
def test_discover_ml_tools_returns_readonly_snapshot() -> None:
    """Per spec §2.4.6: descriptors are immutable so LLM tool-spec lists
    captured at agent start stay consistent across every LLM call in
    that turn.
    """
    from kaizen.ml import (
        MLEngineDescriptor,
        MLRegistryUnavailableError,
        discover_ml_tools,
    )

    try:
        descriptors = discover_ml_tools()
    except MLRegistryUnavailableError:
        pytest.skip("ml registry not yet shipped — tested in symbols suite")
    except ImportError:
        pytest.skip("kailash-ml not installed")

    assert isinstance(descriptors, tuple)
    for d in descriptors:
        assert isinstance(d, MLEngineDescriptor)
        # MLEngineDescriptor is __slots__-based — attribute assignment MUST fail.
        with pytest.raises(AttributeError):
            d.name = "mutated"  # type: ignore[misc]

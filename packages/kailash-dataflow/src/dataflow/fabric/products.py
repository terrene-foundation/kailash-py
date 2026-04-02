# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Product registration for DataFlow Fabric.

Products are declarative data transformations that auto-refresh when their
source dependencies change. Each product has a mode (materialized,
parameterized, virtual), a staleness policy, and an optional cron schedule.

The ``register_product`` function validates configuration and stores a
``ProductRegistration`` in the DataFlow instance's ``_products`` dict.
``ProductInvokeNode`` is a thin wrapper enabling products to participate
in WorkflowBuilder graphs (reading from cache, not re-executing).

See TODO-09 and the layer-redteam convergence report (F2) for design
rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy

logger = logging.getLogger(__name__)

__all__ = [
    "ProductRegistration",
    "ProductInvokeNode",
    "register_product",
    "topological_order",
]


@dataclass
class ProductRegistration:
    """Registration metadata for a data product.

    Created by ``register_product`` and stored in
    ``DataFlow._products[name]``.

    Attributes:
        name: Unique product identifier.
        fn: The decorated product function (receives ``FabricContext``).
        mode: Execution mode controlling caching and query behaviour.
        depends_on: Model or source names this product reads from.
        staleness: Policy governing how stale cache entries are handled.
        schedule: Optional cron expression for time-based refresh.
        multi_tenant: Whether cache is partitioned per tenant.
        auth: Optional auth configuration (e.g. ``{"roles": ["admin"]}``).
        rate_limit: Request throttling configuration.
        write_debounce: Minimum interval between successive cache writes
            triggered by source changes.
        cache_miss: Strategy when a parameterized product has a cache miss
            (``"timeout"``, ``"async_202"``, or ``"inline"``).
    """

    name: str
    fn: Callable[..., Any]
    mode: ProductMode
    depends_on: List[str]
    staleness: StalenessPolicy
    schedule: Optional[str] = None
    multi_tenant: bool = False
    auth: Optional[Dict[str, Any]] = None
    rate_limit: RateLimit = field(default_factory=RateLimit)
    write_debounce: timedelta = field(default_factory=lambda: timedelta(seconds=1))
    cache_miss: str = "timeout"


def register_product(
    products: Dict[str, ProductRegistration],
    models: Dict[str, Any],
    sources: Dict[str, Any],
    name: str,
    fn: Callable[..., Any],
    mode: str = "materialized",
    depends_on: Optional[List[str]] = None,
    staleness: Optional[StalenessPolicy] = None,
    schedule: Optional[str] = None,
    multi_tenant: bool = False,
    auth: Optional[Dict[str, Any]] = None,
    rate_limit: Optional[RateLimit] = None,
    write_debounce: Optional[timedelta] = None,
    cache_miss: str = "timeout",
) -> None:
    """Register a data product in the fabric engine.

    Validates all configuration, resolves defaults, and stores a
    ``ProductRegistration`` in the provided *products* dict.

    Args:
        products: The ``DataFlow._products`` dict to write into.
        models: The ``DataFlow._models`` dict (for depends_on validation).
        sources: The ``DataFlow._sources`` dict (for depends_on validation).
        name: Unique product identifier.
        fn: The product function (receives ``FabricContext``).
        mode: ``"materialized"``, ``"parameterized"``, or ``"virtual"``.
        depends_on: Model/source names this product depends on.
        staleness: Staleness policy. Defaults to ``StalenessPolicy()``.
        schedule: Optional cron expression for scheduled refresh.
        multi_tenant: Whether to partition cache per tenant.
        auth: Auth configuration dict.
        rate_limit: Rate-limiting config. Defaults to ``RateLimit()``.
        write_debounce: Debounce interval. Defaults to 1 second.
        cache_miss: Cache-miss strategy for parameterized products.

    Raises:
        ValueError: On invalid mode, duplicate name, unresolvable
            dependency, or invalid cache_miss strategy.
        ImportError: If *schedule* is provided but ``croniter`` is not
            installed.
    """
    deps = depends_on or []

    # Validate name uniqueness
    if name in products:
        raise ValueError(
            f"Product '{name}' is already registered. "
            f"Registered products: {list(products.keys())}"
        )

    # Validate mode
    try:
        product_mode = ProductMode(mode)
    except ValueError:
        raise ValueError(
            f"Invalid product mode '{mode}'. "
            f"Must be one of: materialized, parameterized, virtual."
        )

    # Validate depends_on references exist in models or sources
    if product_mode in (ProductMode.MATERIALIZED, ProductMode.PARAMETERIZED):
        if not deps:
            raise ValueError(
                f"Product '{name}' (mode={mode}) requires at least one "
                f"depends_on reference."
            )

    known_names = set(models.keys()) | set(sources.keys()) | set(products.keys())
    for dep in deps:
        if dep not in known_names:
            raise ValueError(
                f"Product '{name}' depends_on '{dep}' which is not a "
                f"registered model, source, or product. "
                f"Known: {sorted(known_names)}"
            )

    # Validate cache_miss strategy
    valid_strategies = ("timeout", "async_202", "inline")
    if cache_miss not in valid_strategies:
        raise ValueError(
            f"Invalid cache_miss strategy '{cache_miss}'. "
            f"Must be one of: {valid_strategies}"
        )

    # Validate cron schedule if provided
    if schedule is not None:
        try:
            from croniter import croniter
        except ImportError as exc:
            raise ImportError(
                "croniter is required for scheduled products. "
                "Install with: pip install croniter"
            ) from exc
        if not croniter.is_valid(schedule):
            raise ValueError(
                f"Invalid cron expression for product '{name}': {schedule!r}"
            )

    # Build registration
    registration = ProductRegistration(
        name=name,
        fn=fn,
        mode=product_mode,
        depends_on=deps,
        staleness=staleness or StalenessPolicy(),
        schedule=schedule,
        multi_tenant=multi_tenant,
        auth=auth,
        rate_limit=rate_limit or RateLimit(),
        write_debounce=write_debounce or timedelta(seconds=1),
        cache_miss=cache_miss,
    )

    products[name] = registration
    logger.info(
        "Registered product '%s' (mode=%s, depends_on=%s, schedule=%s)",
        name,
        product_mode.value,
        deps,
        schedule,
    )


class ProductInvokeNode:
    """Thin node wrapper enabling products to participate in WorkflowBuilder graphs.

    ``ProductInvokeNode`` reads from the fabric cache -- it does NOT
    re-execute the product function. This makes products composable: a
    workflow step can consume a product's cached result alongside other
    nodes.

    Design rationale: layer-redteam convergence F2.

    Attributes:
        product_name: The registered product name to read from.
    """

    def __init__(
        self,
        product_name: str,
        fabric_runtime: Any = None,
    ) -> None:
        """Initialise the invoke node.

        Args:
            product_name: Name of the registered product to invoke.
            fabric_runtime: Reference to the FabricRuntime that manages
                the product cache. Will be wired by the runtime at
                startup; may be ``None`` during registration.
        """
        self.product_name = product_name
        self._fabric_runtime = fabric_runtime

    async def execute(self, **params: Any) -> Dict[str, Any]:
        """Read the cached product result.

        For *materialized* products the result is the full cached dataset.
        For *parameterized* products ``params`` are forwarded to the cache
        key lookup. For *virtual* products the call delegates to the
        product function directly.

        Args:
            **params: Optional parameters (used for parameterized products).

        Returns:
            The cached (or freshly computed for virtual) product data.

        Raises:
            RuntimeError: If the fabric runtime has not been wired yet.
        """
        if self._fabric_runtime is None:
            raise RuntimeError(
                f"ProductInvokeNode for '{self.product_name}' has no fabric "
                f"runtime. Ensure DataFlow.start() has been called before "
                f"executing product nodes."
            )

        result = await self._fabric_runtime.get_cached_product(
            self.product_name, params=params
        )
        return result  # type: ignore[return-value]

    def __repr__(self) -> str:
        return (
            f"ProductInvokeNode(product_name={self.product_name!r}, "
            f"runtime_wired={self._fabric_runtime is not None})"
        )


# ---------------------------------------------------------------------------
# Product DAG — topological ordering for pre-warming and cascade refresh
# (TODO-34)
# ---------------------------------------------------------------------------


def topological_order(
    products: Dict[str, ProductRegistration],
) -> List[str]:
    """Return product names in topological order for pre-warming.

    Products that depend on other products must be warmed after their
    dependencies. Uses graphlib.TopologicalSorter (Python 3.9+ stdlib).

    Args:
        products: All registered products.

    Returns:
        List of product names in safe execution order.

    Raises:
        ValueError: If a circular dependency is detected.
    """
    from graphlib import CycleError, TopologicalSorter

    # Build adjacency: product -> set of product dependencies (not model/source deps)
    product_names = set(products.keys())
    graph: Dict[str, set] = {}

    for name, product in products.items():
        deps = set()
        for dep in product.depends_on:
            if dep in product_names:
                deps.add(dep)
        graph[name] = deps

    try:
        sorter = TopologicalSorter(graph)
        return list(sorter.static_order())
    except CycleError as e:
        raise ValueError(
            f"Circular product dependency detected: {e}. "
            f"Products cannot depend on each other in a cycle."
        ) from e


def get_cascade_order(
    products: Dict[str, ProductRegistration],
    changed_source: str,
) -> List[str]:
    """Return products in cascade refresh order after a source change.

    When a source changes, products are refreshed in topological order
    so downstream products see upstream's latest cache.

    Args:
        products: All registered products.
        changed_source: The source or model that changed.

    Returns:
        List of product names to refresh, in order.
    """
    # Find directly affected products
    affected = set()
    for name, product in products.items():
        if changed_source in product.depends_on:
            affected.add(name)

    # Find transitively affected (products depending on affected products)
    product_names = set(products.keys())
    changed = True
    while changed:
        changed = False
        for name, product in products.items():
            if name not in affected:
                for dep in product.depends_on:
                    if dep in affected and dep in product_names:
                        affected.add(name)
                        changed = True

    # Return in topological order (filter to only affected)
    try:
        full_order = topological_order(products)
    except ValueError:
        # If there's a cycle, return affected in arbitrary order
        return sorted(affected)

    return [name for name in full_order if name in affected]

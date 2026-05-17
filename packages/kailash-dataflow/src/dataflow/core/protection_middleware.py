"""
DataFlow Protection Middleware

Integrates write protection with DataFlow's workflow execution system.
Provides runtime enforcement through node execution interception.
"""

import logging
from typing import Any, Dict, Optional, Type

from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from .protection import (
    OperationType,
    ProtectionViolation,
    WriteProtectionConfig,
    WriteProtectionEngine,
)

logger = logging.getLogger(__name__)


class ProtectedDataFlowRuntime(LocalRuntime):
    """
    Extended LocalRuntime with write protection enforcement.

    This runtime intercepts node execution to enforce protection rules
    before any database operations are performed.
    """

    def __init__(self, protection_config: WriteProtectionConfig, **kwargs):
        super().__init__(**kwargs)
        # ProtectedDataFlowRuntime is a long-lived, framework-held runtime:
        # DataFlow constructs it via create_protected_runtime() and drives
        # execute() directly without the `with LocalRuntime() as rt:` context
        # manager. Without this opt-out, LocalRuntime.execute() emits a
        # DeprecationWarning ("without context manager ... error in v0.12.0")
        # on every protection-enforced workflow run. mark_externally_managed()
        # is the SDK-blessed opt-out for exactly this framework-ownership case
        # (see kailash.runtime.local.LocalRuntime.mark_externally_managed,
        # issue #478) and is the established DataFlow convention (engine.py,
        # auto_migration_system.py, connection_adapter.py). The owning caller
        # is responsible for close() at teardown.
        self.mark_externally_managed()
        self.protection_engine = WriteProtectionEngine(protection_config)

    def execute(self, workflow, task_manager=None, parameters=None, *args, **kwargs):
        """Override execute to handle ProtectionViolations specially.

        Forwards every positional/keyword argument transparently to
        ``LocalRuntime.execute`` so callers passing ``idempotency_key``,
        ``time_limit``, ``cancellation_token`` etc. on the protection-enforced
        path are not silently dropped (signature parity with the base).
        """
        # Call parent execute which returns (results, run_id)
        results, run_id = super().execute(
            workflow, task_manager, parameters, *args, **kwargs
        )

        # Check results for protection violations
        for node_result in results.values():
            if isinstance(node_result, dict):
                # Check if this node failed with a protection violation
                error_msg = node_result.get("error", "")
                failed = node_result.get("failed", False)

                if failed and (
                    "Global protection blocks" in error_msg
                    or "Model protection blocks" in error_msg
                    or "Connection protection blocks" in error_msg
                    or "Field protection blocks" in error_msg
                ):
                    # Extract operation from message
                    operation_type = OperationType.CREATE  # Default
                    if "create" in error_msg.lower():
                        operation_type = OperationType.CREATE
                    elif "update" in error_msg.lower():
                        operation_type = OperationType.UPDATE
                    elif "delete" in error_msg.lower():
                        operation_type = OperationType.DELETE
                    elif "read" in error_msg.lower():
                        operation_type = OperationType.READ

                    # Create and raise ProtectionViolation
                    violation = ProtectionViolation(
                        message=error_msg,
                        operation=operation_type,
                        level=self.protection_engine.config.global_protection.protection_level,
                    )
                    logger.error(
                        f"Protection violation detected in results: {violation}"
                    )
                    raise violation

        return results, run_id


class DataFlowProtectionMixin:
    """
    Mixin for DataFlow to add write protection capabilities.

    This mixin extends the DataFlow class with protection features
    without requiring inheritance changes.
    """

    # Tracks every ProtectedDataFlowRuntime returned by
    # create_protected_runtime() so close()/close_async() can drain their
    # externally-managed event loops (issue #1045). Class-level annotation so
    # static analysis resolves the attribute through the ProtectedDataFlow
    # MRO; the real value is assigned in __init__ below.
    _protected_runtimes: list

    def __init__(
        self, *args, protection_config: Optional[WriteProtectionConfig] = None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._protection_config = protection_config or WriteProtectionConfig()
        self._protection_engine = WriteProtectionEngine(self._protection_config)
        # Issue #1045 — every ProtectedDataFlowRuntime returned by
        # create_protected_runtime() calls mark_externally_managed() in its
        # __init__ (the Shard A deprecation fix). mark_externally_managed()
        # deliberately SKIPS atexit.register(self._cleanup_event_loop)
        # (kailash.runtime.local.LocalRuntime._get_persistent_loop) —
        # transferring cleanup responsibility to the owning framework. The
        # owner MUST close() each runtime at teardown or its persistent
        # asyncio event loop leaks (one per create_protected_runtime() call).
        #
        # This is the same owner-tracks-then-drains invariant every sibling
        # mark_externally_managed() call site already honors:
        #   - engine.py:883  -> self._sync_runtime_singleton, drained in
        #     DataFlow.close()/close_async() (engine.py rt.close() loop)
        #   - auto_migration_system.py:279/1074/1703 -> self._explicit_runtime,
        #     drained in their close()
        # ProtectedDataFlowRuntime is structurally different (it IS the
        # runtime, not a wrapper holding one) and create_protected_runtime()
        # returns a fresh instance per call, so the owner tracks the LIST.
        self._protected_runtimes: list = []

    def set_protection_config(self, config: WriteProtectionConfig):
        """Update the protection configuration."""
        self._protection_config = config
        self._protection_engine = WriteProtectionEngine(config)

    def add_model_protection(self, model_name: str, **protection_kwargs):
        """Add protection for a specific model."""
        from .protection import ModelProtection

        protection = ModelProtection(model_name=model_name, **protection_kwargs)
        self._protection_config.model_protections.append(protection)
        self._protection_engine = WriteProtectionEngine(self._protection_config)

    def add_field_protection(
        self, model_name: str, field_name: str, **protection_kwargs
    ):
        """Add protection for a specific field."""
        from .protection import FieldProtection

        # Find or create model protection
        model_protection = None
        for prot in self._protection_config.model_protections:
            if prot.model_name == model_name:
                model_protection = prot
                break

        if not model_protection:
            from .protection import ModelProtection

            model_protection = ModelProtection(model_name=model_name)
            self._protection_config.model_protections.append(model_protection)

        # Add field protection
        field_protection = FieldProtection(field_name=field_name, **protection_kwargs)
        model_protection.protected_fields.append(field_protection)
        self._protection_engine = WriteProtectionEngine(self._protection_config)

    def enable_read_only_mode(self, reason: str = "Read-only mode enabled"):
        """Enable global read-only mode."""
        config = WriteProtectionConfig.read_only_global(reason)
        self.set_protection_config(config)

    def enable_business_hours_protection(self, start_hour: int = 9, end_hour: int = 17):
        """Enable business hours protection."""
        config = WriteProtectionConfig.business_hours_protection(start_hour, end_hour)
        self.set_protection_config(config)

    def get_protection_audit_log(self) -> list:
        """Get the protection audit log."""
        return self._protection_config.auditor.events

    def create_protected_runtime(self, **runtime_kwargs) -> ProtectedDataFlowRuntime:
        """Create a runtime with protection enforcement.

        The returned runtime is registered on this owning DataFlow so
        ``close()`` / ``close_async()`` can drain its persistent event loop
        at teardown (issue #1045). ``ProtectedDataFlowRuntime`` opts out of
        ``atexit`` cleanup via ``mark_externally_managed()`` — without this
        registration the loop would leak.
        """
        runtime = ProtectedDataFlowRuntime(
            protection_config=self._protection_config, **runtime_kwargs
        )
        # Track for owner-driven cleanup. Plain list (not WeakSet): the
        # owner is the sole lifecycle authority for these runtimes, and a
        # weak ref would let the loop be collected without close(), which
        # is the leak itself.
        runtimes = getattr(self, "_protected_runtimes", None)
        if runtimes is None:
            # Defensive: a subclass may construct the runtime before the
            # mixin __init__ ran (unusual, but the attribute MUST exist
            # before the first append or the drain in close() misses it).
            self._protected_runtimes = runtimes = []
        runtimes.append(runtime)
        return runtime

    def _drain_protected_runtimes(self) -> None:
        """Close every runtime handed out by create_protected_runtime().

        Sync — ``LocalRuntime.close()`` is synchronous (it joins the
        persistent loop thread / closes the loop). Idempotent: each
        runtime's own ref-count logic makes a second close() a no-op, and
        the tracking list is cleared so a second drain is empty. Safe to
        call from both close() and close_async().
        """
        runtimes = getattr(self, "_protected_runtimes", None)
        if not runtimes:
            return
        for runtime in list(runtimes):
            try:
                runtime.close()
            except Exception as e:
                # Mirror the sibling-pattern disposition in
                # DataFlow.close() (engine.py rt.close() loop): a failure
                # closing one externally-managed runtime MUST NOT abort the
                # rest of teardown. Logged, not swallowed silently
                # (rules/zero-tolerance.md Rule 3 / observability.md).
                logger.warning(
                    "protection_middleware.error_closing_protected_runtime",
                    extra={
                        "runtime_id": getattr(runtime, "_runtime_id", "unknown"),
                        "error": str(e),
                    },
                )
        runtimes.clear()

    def close(self) -> None:
        """Drain protected runtimes, then delegate to DataFlow.close().

        Cooperative-MRO override. ``ProtectedDataFlow`` resolves
        ``DataFlowProtectionMixin -> DataFlow``; draining BEFORE
        ``super().close()`` releases the protection runtimes' loops while
        the rest of the engine is still live, matching the
        release-subsystems-first ordering DataFlow.close() already uses.
        """
        self._drain_protected_runtimes()
        # super() may not define close() in every composition; guard so the
        # mixin is safe if applied to a base without it.
        parent_close = getattr(super(), "close", None)
        if callable(parent_close):
            parent_close()

    async def close_async(self) -> None:
        """Async-context teardown: drain protected runtimes, then delegate.

        ``LocalRuntime.close()`` is sync, so the drain itself is sync; only
        the delegation to ``DataFlow.close_async()`` is awaited. Mirrors the
        sync ``close()`` ordering (drain first, engine last).
        """
        self._drain_protected_runtimes()
        parent_close_async = getattr(super(), "close_async", None)
        if parent_close_async is not None:
            result = parent_close_async()
            if result is not None:
                await result


def protect_dataflow_node(original_class: Type[Node]) -> Type[Node]:
    """
    Decorator to add protection checks to DataFlow-generated nodes.

    This decorator wraps the run method of generated nodes to
    perform protection checks before database operations.
    """

    class ProtectedNode(original_class):
        # Injected post-construction by DataFlow's node-generation machinery
        # (the generated node is bound to its owning DataFlow instance there).
        # Declared so static analysis knows the attribute exists; every read
        # is still hasattr()-guarded because it is absent until injection.
        dataflow_instance: Any

        # Issue #1050: the protection check is wired into async_run(), NOT
        # the sync run() override that previously lived here. The generated
        # DataFlowNode is an AsyncNode subclass; EVERY real path converges
        # on async_run():
        #   - db.express.* calls `await node.async_run(**data)` directly
        #     (features/express.py).
        #   - LocalRuntime / AsyncLocalRuntime dispatch prefers
        #     execute_async() over sync run() (runtime/local.py); AsyncNode.
        #     execute_async() calls `await self.async_run()`.
        #   - A raw sync `node.execute()` caller still routes through
        #     AsyncNode.execute() -> execute_async() -> async_run()
        #     (AsyncNode.run() itself raises NotImplementedError).
        # The old sync run() override (deleted in this commit) was NEVER
        # invoked on any real path — it was a facade orphan
        # (orphan-detection.md §1). It is intentionally NOT replaced with a
        # sync run() override: DataFlowNode.run() is already a correct
        # async_safe_run(self.async_run(**kwargs)) bridge, so it reaches
        # this protected async_run() with exactly ONE check. Adding a sync
        # run() override here would re-introduce a double-check
        # (sync run() check -> async_safe_run -> async_run() check again).
        # This satisfies spec invariant I1 (single-check, no double-check).

        async def async_run(self, **kwargs) -> Dict[str, Any]:
            """Run the write-protection check, then delegate to async_run.

            The check runs BEFORE ``super().async_run(**kwargs)`` — i.e.
            before lazy table-existence DDL and before any connection-pool
            acquisition (spec invariant I2: a blocked write never takes a
            connection). Arguments are built from ``self.operation`` /
            ``self.model_name`` (the canonical lowercase strings set in
            ``DataFlowNode.__init__``), NOT a brittle class-name parse —
            spec invariant I3. ``self.model_name`` reaching
            ``check_operation`` is what makes ``add_model_protection`` /
            ``add_field_protection`` enforce (spec invariant I4).
            ``check_operation`` routes a block through
            ``WriteProtectionEngine._handle_violation``, which raises for
            BLOCK/AUDIT and only logs for WARN (spec invariant I6) AND
            emits the audit record before the raise (spec invariant I9) —
            both are automatic by going through ``check_operation`` rather
            than a hand-rolled level check. A raised ``ProtectionViolation``
            propagates to the caller (spec invariant I5): on the Express
            path directly (Express does not swallow it into a result
            dict); on the workflow-runtime path it survives
            ``AsyncNode.execute_async``'s re-raise allowlist because
            ``ProtectionViolation`` is a ``NodeExecutionError`` subclass
            (Shard 1a, issue #1050).
            """
            # Get protection engine from DataFlow instance. Carried over
            # verbatim from the removed sync override: dataflow_instance is
            # injected post-construction (Express _create_node binds it;
            # the workflow node generator binds it in __init__), so the
            # hasattr guard is the documented fail-open posture when the
            # node is constructed before binding — NOT introduced here.
            if hasattr(self, "dataflow_instance"):
                df = self.dataflow_instance

                if hasattr(df, "_protection_engine"):
                    protection_engine = df._protection_engine

                    # Only check if a protection engine is actually wired
                    # (ProtectedDataFlow with enable_protection=False sets
                    # _protection_engine = None).
                    if protection_engine is not None:
                        # I3: canonical operation string set in
                        # DataFlowNode.__init__ (self.operation), e.g.
                        # "create" / "read" / "update" / "delete" / "list"
                        # / "count" / "upsert" / "bulk_create" / ... It maps
                        # directly through WriteProtectionEngine.
                        # _operation_mapping. This REPLACES the removed
                        # override's class-name if-ladder, which mis-mapped
                        # upsert/count/bulk_* to "unknown" -> CUSTOM_QUERY
                        # (over-blocking count under read-only, never
                        # enforcing bulk_*).
                        operation = getattr(self, "operation", None) or "custom_query"

                        # I4: model name from the instance attribute (set in
                        # DataFlowNode.__init__), with the class-name strip
                        # retained ONLY as a defensive fallback for the
                        # (not-expected-on-real-paths) case where the
                        # attribute is absent.
                        model_name = getattr(self, "model_name", None)
                        if not model_name:
                            class_name = self.__class__.__name__
                            if "Node" in class_name:
                                for op in [
                                    "BulkCreate",
                                    "BulkUpdate",
                                    "BulkDelete",
                                    "BulkUpsert",
                                    "Create",
                                    "Update",
                                    "Delete",
                                    "Read",
                                    "List",
                                    "Count",
                                ]:
                                    if op + "Node" in class_name:
                                        model_name = class_name.replace(op + "Node", "")
                                        break

                        # Context for dynamic protection conditions /
                        # auditing. Same shape the removed sync override
                        # built.
                        context = {
                            "node_id": getattr(self, "node_id", "unknown"),
                            "model_fields": getattr(self, "model_fields", {}),
                            "inputs": kwargs,
                        }

                        # Connection-string resolution identical to the
                        # removed sync override: explicit database_url kwarg
                        # first, then the bound DataFlow instance's
                        # database_url (drives connection-level protection,
                        # e.g. production_safe's r".*prod.*" pattern).
                        connection_string = kwargs.get("database_url")
                        if not connection_string and hasattr(df, "database_url"):
                            connection_string = df.database_url

                        # I6 + I9: check_operation -> _handle_violation
                        # raises for BLOCK/AUDIT, logs+allows for WARN, and
                        # emits the auditor.log_violation record BEFORE the
                        # raise. Do NOT hand-roll the level check here — the
                        # single routing point is the structural guarantee
                        # the audit record always fires.
                        try:
                            protection_engine.check_operation(
                                operation=operation,
                                model_name=model_name,
                                connection_string=connection_string,
                                context=context,
                            )
                        except ProtectionViolation as e:
                            logger.error(
                                "protection_middleware.protection_violation",
                                extra={
                                    "node_id": getattr(self, "node_id", "unknown"),
                                    "operation": operation,
                                    "error": str(e),
                                },
                            )
                            raise

            # I5: protection passed — delegate to the generated node's
            # async_run. original_class is ALWAYS a concrete generated
            # DataFlow node at runtime (the decorator only wraps concrete
            # *Node classes); the Type[Node] parameter annotation makes
            # pyright resolve super() to `object`, so it cannot see
            # async_run. Static-analysis expressiveness gap, not a real
            # bug (runtime MRO resolves to DataFlowNode.async_run).
            return (
                await super().async_run(  # pyright: ignore[reportAttributeAccessIssue]
                    **kwargs
                )
            )

    # Preserve class metadata
    ProtectedNode.__name__ = original_class.__name__
    ProtectedNode.__qualname__ = original_class.__qualname__
    ProtectedNode.__module__ = original_class.__module__

    return ProtectedNode

"""
DataFlow Bulk Operations

High-performance bulk database operations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from kailash.utils.url_credentials import mask_url

from ..core.exceptions import BulkUpsertConflictTargetError
from ..core.exceptions import is_conflict_target_error as _is_conflict_target_error
from ..core.exceptions import sanitize_db_error as _sanitize_db_error
from ..core.tenant_context import get_current_tenant_id
from ..nodes.bulk_result_processor import BulkCreateResultProcessor


class BulkOperations:
    """High-performance bulk operations for DataFlow."""

    def __init__(self, dataflow_instance):
        self.dataflow = dataflow_instance

    def _is_multi_tenant(self) -> bool:
        """True iff this DataFlow instance is configured multi-tenant."""
        return bool(
            getattr(
                getattr(getattr(self.dataflow, "config", None), "security", None),
                "multi_tenant",
                False,
            )
        )

    def _model_has_tenant_field(self, model_name: str) -> bool:
        """True iff the model carries a ``tenant_id`` field (a tenant table)."""
        try:
            return "tenant_id" in self.dataflow.get_model_fields(model_name)
        except Exception as exc:
            # Fail-closed for tenant *detection* would over-scope non-tenant
            # models, so we return False — but log it: a genuine tenant model
            # whose field lookup raised would otherwise skip tenant scoping
            # SILENTLY (zero-tolerance.md Rule 3). Loud, not silent.
            logging.getLogger(__name__).warning(
                "bulk._model_has_tenant_field: field lookup raised for "
                "model=%s (%s); treating as non-tenant",
                model_name,
                type(exc).__name__,
            )
            return False

    def _model_has_soft_delete(self, model_name: str) -> bool:
        """True iff the model declares ``soft_delete: True`` in ``__dataflow__``.

        Mirrors the config-access pattern used by the read path (core/nodes.py
        list/read/count soft-delete auto-filter) and the DeleteNode single-record
        tombstone: prefer the structured ``_models[...]['config']`` dict, fall
        back to the registered class's ``_dataflow_config`` attribute. This is
        the source of truth for the bulk_delete tombstone-vs-hard-delete branch
        so bulk deletes stay consistent with single-record deletes.
        """
        model_info = self.dataflow._models.get(model_name)
        if isinstance(model_info, dict):
            config = model_info.get("config")
            if isinstance(config, dict) and config.get("soft_delete", False):
                return True
        registered = getattr(self.dataflow, "_registered_models", {})
        model_cls = registered.get(model_name) if isinstance(registered, dict) else None
        if model_cls is not None:
            cfg = getattr(model_cls, "_dataflow_config", None)
            if isinstance(cfg, dict) and cfg.get("soft_delete", False):
                return True
        return False

    def _resolve_bulk_tenant(self, model_name: str) -> Optional[str]:
        """Resolve the bound tenant for a bulk op, fail-closed under multi-tenant.

        Issue #1252 — the bulk subsystem builds its own SQL and previously read
        the bound tenant from the stale ``self.dataflow._tenant_context`` dict
        (only ever populated by the unused ``set_tenant_context()`` legacy API),
        which is empty ``{}`` under ``tenant_context.switch()``. That made every
        bulk write persist ``tenant_id=NULL`` (rows invisible to all tenants) and
        left bulk_update / bulk_delete unscoped (latent cross-tenant write/delete).

        This reads the SAME contextvar source the single-record path uses
        (``get_current_tenant_id()``) and FAILS CLOSED — mirroring the #1249
        ``_apply_tenant_isolation`` guard in ``core/nodes.py`` — per
        ``tenant-isolation.md`` MUST-2 + ``zero-tolerance.md`` Rule 3.

        Returns:
            The bound tenant id when the model is a tenant table under
            multi_tenant. ``None`` when the model is NOT a tenant table OR the
            instance is single-tenant (caller injects nothing in that case).

        Raises:
            RuntimeError: when the model is a tenant table under multi_tenant but
            no tenant is bound to the current context — refusing to write a
            NULL-tenant row or run an unscoped UPDATE/DELETE.
        """
        if not self._is_multi_tenant():
            return None
        if not self._model_has_tenant_field(model_name):
            return None
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise RuntimeError(
                f"Tenant isolation failed for {model_name}: multi_tenant=True but "
                f"no tenant is bound to the current context. Bind one via "
                f"db.tenant_context.switch(tenant_id) before this bulk operation. "
                f"Refusing to execute an unscoped query (potential cross-tenant leak)."
            )
        return tenant_id

    def _tenant_where_predicate(
        self, database_type: str, params_offset: int, tenant_id: str
    ) -> tuple:
        """Build the ``tenant_id = <bound>`` SQL fragment for a WHERE clause.

        Returns a dialect-correct placeholder fragment (NO leading ``AND``/``WHERE``
        — the caller composes that) plus the single bound parameter. The tenant
        value is always a BOUND parameter, never string-interpolated, per
        ``security.md`` § Parameterized Queries.

        Args:
            database_type: 'postgresql' | 'mysql' | 'sqlite'.
            params_offset: count of params already bound BEFORE this predicate
                (drives PostgreSQL ``$N`` numbering).
            tenant_id: the bound tenant id to compare against.

        Returns:
            tuple: (fragment: str, params: list) e.g. ``("tenant_id = $3", [tid])``.
        """
        # tenant_id is a fixed column literal, but quote it via the dialect so
        # every identifier this file interpolates goes through one path
        # (rules/dataflow-identifier-safety.md MUST-1, defense-in-depth).
        from ..adapters.dialect import DialectManager

        quoted_tenant = DialectManager.get_dialect(database_type).quote_identifier(
            "tenant_id"
        )
        db_lower = database_type.lower()
        if db_lower == "postgresql":
            fragment = f"{quoted_tenant} = ${params_offset + 1}"
        elif db_lower == "mysql":
            fragment = f"{quoted_tenant} = %s"
        else:  # sqlite
            fragment = f"{quoted_tenant} = ?"
        return fragment, [tenant_id]

    def _serialize_params_for_sql(self, params: list, model_name: str) -> list:
        """Serialize dict/list parameters to JSON for SQL binding.

        BUG #515 FIX: This method ensures dict/list values are serialized
        to JSON strings at the SQL parameter binding stage, NOT during
        validation. This preserves type integrity through validation while
        ensuring database compatibility.

        NATIVE ARRAY FIX: Only JSON-serialize lists when use_native_arrays=False.
        When use_native_arrays=True (PostgreSQL), lists are passed through as-is
        for native array columns (TEXT[], INTEGER[], etc.). asyncpg expects
        Python lists for PostgreSQL array types, not JSON strings.

        Args:
            params: List of parameter values
            model_name: Name of the model to check config

        Returns:
            List with appropriate serialization based on model config
        """
        # Check if this model uses native PostgreSQL arrays
        use_native_arrays = False
        try:
            model_info = self.dataflow.get_model_info(model_name)
            if model_info:
                config = model_info.get("config", {})
                use_native_arrays = config.get("use_native_arrays", False)
        except Exception:
            pass  # Default to JSON serialization on any error

        serialized = []
        for value in params:
            if isinstance(value, dict):
                # Dicts are always JSON-serialized (JSONB columns)
                serialized.append(json.dumps(value))
            elif isinstance(value, list):
                if use_native_arrays:
                    # Native arrays: pass list as-is for asyncpg
                    serialized.append(value)
                else:
                    # JSON mode: serialize list to JSON string
                    serialized.append(json.dumps(value))
            else:
                serialized.append(value)
        return serialized

    def _build_where_clause(
        self,
        filter_criteria: Dict[str, Any],
        database_type: str,
        params_offset: int = 0,
    ) -> tuple:
        """Build WHERE clause from filter criteria with MongoDB operator support.

        Supports MongoDB-style operators:
        - $in: IN clause
        - $nin: NOT IN clause
        - $gt, $gte, $lt, $lte: Comparison operators
        - $ne: Not equal

        Args:
            filter_criteria: Filter dictionary (may contain MongoDB operators)
            database_type: Database type ('postgresql', 'mysql', or 'sqlite')
            params_offset: Starting offset for parameter numbering

        Returns:
            tuple: (where_clause: str, params: list)
        """
        if not filter_criteria:
            return ("", [])

        # rules/dataflow-identifier-safety.md MUST-1 + security.md: filter keys
        # are column IDENTIFIERS interpolated into the WHERE clause (drivers
        # cannot bind identifiers). Route every one through
        # ``dialect.quote_identifier`` (validate-then-quote, reject-don't-escape)
        # matching core/nodes.py + core/engine.py. Values stay BOUND params.
        from ..adapters.dialect import DialectManager

        dialect = DialectManager.get_dialect(database_type)
        where_parts = []
        params = []
        db_lower = database_type.lower()

        for field, value in filter_criteria.items():
            quoted_field = dialect.quote_identifier(field)
            # Check if value is a MongoDB-style operator dict
            if isinstance(value, dict) and len(value) == 1:
                operator = list(value.keys())[0]
                operand = value[operator]

                if operator == "$in":
                    # Convert MongoDB $in to SQL IN clause
                    if not isinstance(operand, list):
                        raise ValueError(
                            f"$in operator requires a list, got {type(operand)}"
                        )

                    # Handle empty list - should match nothing (use FALSE condition)
                    if len(operand) == 0:
                        where_parts.append("1 = 0")  # Always false - matches nothing
                        continue

                    # Filter out None values (SQL IN clause doesn't handle NULL properly)
                    operand_cleaned = [v for v in operand if v is not None]

                    # After filtering, check if list is now empty
                    if len(operand_cleaned) == 0:
                        where_parts.append(
                            "1 = 0"
                        )  # All values were None, matches nothing
                        continue

                    # Deduplicate for efficiency
                    operand_deduped = list(
                        dict.fromkeys(operand_cleaned)
                    )  # Preserves order

                    # Check size limit (PostgreSQL max params ~32,767, be conservative)
                    if len(operand_deduped) > 10000:
                        raise ValueError(
                            f"$in operator list too large ({len(operand_deduped)} items after deduplication). "
                            f"Maximum 10,000 items supported. Consider restructuring your query or using bulk operations."
                        )

                    # Build IN clause with placeholders
                    if db_lower == "postgresql":
                        placeholders = ", ".join(
                            [
                                f"${len(params) + params_offset + i + 1}"
                                for i in range(len(operand_deduped))
                            ]
                        )
                    elif db_lower == "mysql":
                        placeholders = ", ".join(["%s"] * len(operand_deduped))
                    else:  # sqlite
                        placeholders = ", ".join(["?"] * len(operand_deduped))

                    where_parts.append(f"{quoted_field} IN ({placeholders})")
                    params.extend(operand_deduped)

                elif operator == "$nin":
                    # Convert MongoDB $nin to SQL NOT IN clause
                    if not isinstance(operand, list):
                        raise ValueError(
                            f"$nin operator requires a list, got {type(operand)}"
                        )

                    # Handle empty list - should match everything (use TRUE condition)
                    if len(operand) == 0:
                        where_parts.append("1 = 1")  # Always true - matches everything
                        continue

                    # Filter out None values (SQL NOT IN clause doesn't handle NULL properly)
                    operand_cleaned = [v for v in operand if v is not None]

                    # After filtering, check if list is now empty
                    if len(operand_cleaned) == 0:
                        where_parts.append(
                            "1 = 1"
                        )  # All values were None, matches everything
                        continue

                    # Deduplicate for efficiency
                    operand_deduped = list(
                        dict.fromkeys(operand_cleaned)
                    )  # Preserves order

                    # Check size limit (PostgreSQL max params ~32,767, be conservative)
                    if len(operand_deduped) > 10000:
                        raise ValueError(
                            f"$nin operator list too large ({len(operand_deduped)} items after deduplication). "
                            f"Maximum 10,000 items supported. Consider restructuring your query."
                        )

                    # Build NOT IN clause with placeholders
                    if db_lower == "postgresql":
                        placeholders = ", ".join(
                            [
                                f"${len(params) + params_offset + i + 1}"
                                for i in range(len(operand_deduped))
                            ]
                        )
                    elif db_lower == "mysql":
                        placeholders = ", ".join(["%s"] * len(operand_deduped))
                    else:  # sqlite
                        placeholders = ", ".join(["?"] * len(operand_deduped))

                    where_parts.append(f"{quoted_field} NOT IN ({placeholders})")
                    params.extend(operand_deduped)

                elif operator in ["$gt", "$gte", "$lt", "$lte", "$ne"]:
                    # Convert MongoDB comparison operators
                    sql_op_map = {
                        "$gt": ">",
                        "$gte": ">=",
                        "$lt": "<",
                        "$lte": "<=",
                        "$ne": "!=",
                    }
                    sql_operator = sql_op_map[operator]

                    if db_lower == "postgresql":
                        where_parts.append(
                            f"{quoted_field} {sql_operator} ${len(params) + params_offset + 1}"
                        )
                    elif db_lower == "mysql":
                        where_parts.append(f"{quoted_field} {sql_operator} %s")
                    else:  # sqlite
                        where_parts.append(f"{quoted_field} {sql_operator} ?")
                    params.append(operand)

                else:
                    # Unknown operator - treat as equality
                    if db_lower == "postgresql":
                        where_parts.append(
                            f"{quoted_field} = ${len(params) + params_offset + 1}"
                        )
                    elif db_lower == "mysql":
                        where_parts.append(f"{quoted_field} = %s")
                    else:  # sqlite
                        where_parts.append(f"{quoted_field} = ?")
                    params.append(value)
            else:
                # Regular equality comparison
                if db_lower == "postgresql":
                    where_parts.append(
                        f"{quoted_field} = ${len(params) + params_offset + 1}"
                    )
                elif db_lower == "mysql":
                    where_parts.append(f"{quoted_field} = %s")
                else:  # sqlite
                    where_parts.append(f"{quoted_field} = ?")
                params.append(value)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        return (where_clause, params)

    async def bulk_create(
        self,
        model_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000,
        transaction: Optional[Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk create operation.

        #1585: when ``transaction`` is a borrowed adapter txn handle ``(conn, tx)``
        (threaded from a generated bulk node inside a ``TransactionScopeNode``),
        every batch INSERT runs ON that transaction's connection instead of
        auto-committing on its own — so a bulk write inside a rolled-back scope
        is discarded. ``None`` (``db.express``/no-scope) preserves auto-commit.
        """
        import logging

        logger = logging.getLogger(__name__)

        # DEBUG (not WARN): kwargs may carry connection strings / caller values;
        # entry traces must not reach log aggregators at WARN+ (observability.md
        # Rule 8, security.md § No secrets in logs).
        logger.debug(
            f"BULK_CREATE ENTRY: model={model_name}, data_count={len(data) if data else 0}, kwargs={kwargs}"
        )

        # Handle None data
        if data is None:
            return {"success": False, "error": "Data cannot be None"}

        # Handle empty data list (valid - insert 0 records)
        if len(data) == 0:
            return {
                "records_processed": 0,
                "success_count": 0,
                "failure_count": 0,
                "batches": 0,
                "batch_size": batch_size,
                "success": True,
            }

        # Issue #1252 — stamp tenant_id from the contextvar source (the one
        # tenant_context.switch() actually sets), NOT the stale legacy
        # self.dataflow._tenant_context dict. Fails closed under multi_tenant
        # with no bound tenant; returns None (no stamp) for single-tenant or
        # non-tenant models. See _resolve_bulk_tenant.
        bound_tenant = self._resolve_bulk_tenant(model_name)
        if bound_tenant is not None:
            for record in data:
                record["tenant_id"] = bound_tenant

        # Auto-convert ISO datetime strings to datetime objects for each record
        from ..core.nodes import convert_datetime_fields

        model_fields = self.dataflow.get_model_fields(model_name)
        for record in data:
            convert_datetime_fields(record, model_fields, logger)

        # Type-aware field validation
        try:
            from ..core.type_processor import TypeAwareFieldProcessor

            type_processor = TypeAwareFieldProcessor(model_fields, model_name)
            data = type_processor.process_records(
                data,
                operation="bulk_create",
                strict=False,
                skip_fields=set(),  # Timestamps already excluded
            )
        except ImportError:
            logger.debug(
                "TypeAwareFieldProcessor not available, skipping type validation"
            )
        except TypeError as e:
            return {"success": False, "error": str(e)}

        # Perform actual database insertion
        try:
            connection_string = self.dataflow.config.database.get_connection_url(
                self.dataflow.config.environment
            )
            database_type = self.dataflow._detect_database_type()
            # Use stored table_name from _models (respects custom __tablename__)
            model_info = self.dataflow._models.get(model_name, {})
            table_name = model_info.get(
                "table_name"
            ) or self.dataflow._class_name_to_table_name(model_name)

            # Round 2 red team fix: route connection_string through mask_url —
            # NO truncation. Slicing connection_string[:50] cuts BEFORE the
            # ``@`` separator on long URLs, which would leak the credential
            # tail through a "looks truncated, looks safe" log line.
            # See rules/security.md § "No secrets in logs" and
            # rules/observability.md Rule 6.
            # DEBUG (not WARN): table_name is a schema identifier (observability.md
            # Rule 8); conn is masked.
            logger.debug(
                f"BULK_CREATE: conn={mask_url(connection_string)}, db_type={database_type}, table={table_name}"
            )

            # Build INSERT query from data
            if not data:
                return {
                    "records_processed": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "batches": 0,
                    "batch_size": batch_size,
                    "success": True,
                }

            # Get column names from first record.
            # rules/dataflow-identifier-safety.md MUST-1: table_name AND every
            # column key are interpolated as bare identifiers (drivers cannot
            # bind identifiers). Record keys are NOT constrained to declared
            # model fields, so quote-validate each via the dialect before
            # interpolation (reject-don't-escape), matching bulk_upsert + core.
            from ..adapters.dialect import DialectManager

            dialect = DialectManager.get_dialect(database_type)
            quoted_table = dialect.quote_identifier(table_name)
            columns = list(data[0].keys())
            column_names = ", ".join(dialect.quote_identifier(c) for c in columns)

            # Build VALUES clause with placeholders
            total_inserted = 0
            batches_processed = 0

            # Process in batches
            for i in range(0, len(data), batch_size):
                batch = data[i : i + batch_size]
                values_placeholders = []
                params = []

                for record in batch:
                    if database_type.lower() == "postgresql":
                        placeholders = ", ".join(
                            [
                                f"${j + 1}"
                                for j in range(len(params), len(params) + len(columns))
                            ]
                        )
                    elif database_type.lower() == "mysql":
                        placeholders = ", ".join(["%s"] * len(columns))
                    else:  # sqlite
                        placeholders = ", ".join(["?"] * len(columns))

                    values_placeholders.append(f"({placeholders})")
                    record_params = [record.get(col) for col in columns]
                    # BUG #515 FIX: Serialize dict/list for SQL parameter binding
                    # NATIVE ARRAY FIX: Pass model_name to check use_native_arrays config
                    record_params = self._serialize_params_for_sql(
                        record_params, model_name
                    )
                    params.extend(record_params)

                values_clause = ", ".join(values_placeholders)
                query = f"INSERT INTO {quoted_table} ({column_names}) VALUES {values_clause}"

                # DEBUG (not WARN): the query carries schema column names —
                # observability.md Rule 8.
                logger.debug(
                    f"BULK_CREATE: Executing batch {batches_processed + 1}, query='{query[:100]}...', param_count={len(params)}"
                )

                # Execute using cached AsyncSQLDatabaseNode
                # FIX: Use cached node instead of creating fresh instance
                # This ensures connection pooling and data visibility across operations
                sql_node = self.dataflow._get_or_create_async_sql_node(database_type)

                result = await sql_node.async_run(
                    query=query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                    transaction=transaction,  # #1585: join active scope (None = auto-commit)
                )

                logger.debug("bulk.bulk_create_sql_result", extra={"result": result})

                # Use shared result processor for consistent behavior
                # This applies the Phase 1 fix: fallback to batch_size when rows_affected=0
                batch_inserted, batch_ids = (
                    BulkCreateResultProcessor.process_insert_result(
                        result, len(batch), conflict_resolution="error"
                    )
                )

                total_inserted += batch_inserted
                batches_processed += 1

            success_result = {
                # Primary fields
                "success": True,
                "inserted": total_inserted,  # FIX: Add consistent field name
                "rows_affected": total_inserted,  # API consistency
                "failed": 0,
                "total": len(data),
                "batch_count": batches_processed,
                # Compatibility fields for existing tests
                "records_processed": total_inserted,
                "success_count": total_inserted,
                "failure_count": 0,
                "batches": batches_processed,
                "batch_size": batch_size,
            }
            logger.info(
                "bulk.bulk_create_success", extra={"success_result": success_result}
            )
            return success_result

        except Exception as e:
            # Redteam MEDIUM (scanner-surface symmetry): scrub driver-error
            # column VALUES (potential PII) before log/return — same shared
            # redactor as bulk_upsert / the workflow node.
            safe_error = _sanitize_db_error(str(e))
            error_result = {
                "success": False,
                "error": f"Bulk create operation failed: {safe_error}",
                "records_processed": 0,
            }
            logger.error(
                # exc_info dropped: the traceback's terminal frame re-emits the
                # raw driver message (potential PII) the sanitizer just scrubbed
                # (redteam LOW). Match the P2 node's no-exc_info bulk-error log.
                "bulk.bulk_create_exception",
                extra={"error": safe_error},
            )
            logger.error(
                "bulk.bulk_create_error_result", extra={"error_result": error_result}
            )
            return error_result

    async def bulk_update(
        self,
        model_name: str,
        data: Optional[List[Dict[str, Any]]] = None,
        filter_criteria: Optional[Dict[str, Any]] = None,
        update_values: Optional[Dict[str, Any]] = None,
        batch_size: int = 1000,
        transaction: Optional[Any] = None,
        include_deleted: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk update operation.

        #1585: a borrowed ``transaction`` handle makes every UPDATE run ON the
        scope's connection (joins a ``TransactionScopeNode``); ``None`` preserves
        auto-commit.

        ``include_deleted`` (soft_delete models only, FILTER-based path):
        by default a filter-based bulk_update adds a ``deleted_at IS NULL``
        guard so it skips tombstoned rows — consistent with the list/read/count
        read auto-filter. ``include_deleted=True`` bypasses that guard, enabling
        the un-delete workflow (``update_values={"deleted_at": None}``). The
        explicit per-row ``data=[{id:..}]`` path is NEVER guarded: it targets
        rows by primary key, so mutating a named tombstoned row is intentional
        (mirrors single-record update-by-PK).
        """
        import logging

        logger = logging.getLogger(__name__)

        # DEBUG (not WARN): data / update_values carry raw row VALUES (potential
        # PII) and kwargs may carry caller values — must not reach log
        # aggregators at WARN+ (observability.md Rule 8, security.md § No secrets
        # in logs). Matches the query/params downgrade below.
        logger.debug(
            f"BULK_UPDATE ENTRY: model={model_name}, data={data}, filter={filter_criteria}, update={update_values}, kwargs={kwargs}"
        )

        # Extract safe_mode and confirmed parameters
        safe_mode = kwargs.get("safe_mode", True)
        confirmed = kwargs.get("confirmed", False)

        # Determine operation mode based on which parameters have actual content
        # Filter-based: has non-empty update_values (filter can be empty = update all)
        # Data-based: has data parameter (can be empty list)
        has_update_values = update_values is not None and bool(update_values)
        has_data = data is not None

        is_filter_based = has_update_values
        is_data_based = has_data and not has_update_values

        # Validation: Empty filter requires confirmation (only for filter-based updates)
        if is_filter_based and not filter_criteria:
            # Empty dict {} means update ALL records - require confirmation
            logger.warning("BULK_UPDATE: Empty filter detected, checking confirmation")
            if safe_mode and not confirmed:
                error_result = {
                    "success": False,
                    "error": "Bulk update with empty filter requires confirmed=True. "
                    "Empty filter will update ALL records in the table. "
                    "Set confirmed=True to proceed or provide a specific filter.",
                    "records_processed": 0,
                }
                logger.error(
                    "bulk.bulk_update_validation_failed",
                    extra={"error_result": error_result},
                )
                return error_result

        if is_filter_based:
            # Filter-based bulk update - perform actual database operation
            logger.debug("BULK_UPDATE: Processing filter-based update")

            # Issue #1252 — resolve the bound tenant up front, OUTSIDE the try so
            # the fail-closed RuntimeError PROPAGATES (raises) rather than being
            # swallowed into an error dict by the broad `except Exception` below.
            # Mirrors the #1249 _apply_tenant_isolation raise in core/nodes.py.
            # None for single-tenant or non-tenant models. The tenant predicate is
            # AND-ed into the WHERE below so it can never be dropped (latent
            # cross-tenant write protection). See _resolve_bulk_tenant.
            bound_tenant = self._resolve_bulk_tenant(model_name)

            try:
                # Auto-convert ISO datetime strings to datetime objects in update_values
                from ..core.nodes import convert_datetime_fields

                model_fields = self.dataflow.get_model_fields(model_name)
                update_values = convert_datetime_fields(
                    update_values, model_fields, logger
                )

                # Type-aware field validation
                try:
                    from ..core.type_processor import TypeAwareFieldProcessor

                    type_processor = TypeAwareFieldProcessor(model_fields, model_name)
                    update_values = type_processor.process_record(
                        update_values,
                        operation="bulk_update",
                        strict=False,
                        skip_fields=set(),
                    )
                except ImportError:
                    logger.debug(
                        "TypeAwareFieldProcessor not available, skipping type validation"
                    )
                except TypeError as e:
                    return {"success": False, "error": str(e), "records_processed": 0}

                # Get database connection and execute UPDATE
                connection_string = self.dataflow.config.database.get_connection_url(
                    self.dataflow.config.environment
                )
                database_type = self.dataflow._detect_database_type()
                # Use stored table_name from _models (respects custom __tablename__)
                model_info = self.dataflow._models.get(model_name, {})
                table_name = model_info.get(
                    "table_name"
                ) or self.dataflow._class_name_to_table_name(model_name)

                # DEBUG (not WARN): conn masked via mask_url, but table_name is a
                # schema identifier — observability.md Rule 8 keeps schema names
                # off WARN+ aggregators.
                logger.debug(
                    f"BULK_UPDATE: conn={mask_url(connection_string)}, db_type={database_type}, table={table_name}"
                )

                # rules/dataflow-identifier-safety.md MUST-1: table_name AND
                # every SET/WHERE column key are interpolated as bare
                # identifiers (drivers cannot bind identifiers). update_values
                # keys are NOT constrained to declared model fields, so
                # quote-validate each via the dialect (reject-don't-escape).
                from ..adapters.dialect import DialectManager

                dialect = DialectManager.get_dialect(database_type)
                quoted_table = dialect.quote_identifier(table_name)

                # Build SET clause from update_values
                set_parts = []
                params = []
                for field, value in update_values.items():
                    quoted_field = dialect.quote_identifier(field)
                    if database_type.lower() == "postgresql":
                        set_parts.append(f"{quoted_field} = ${len(params) + 1}")
                    elif database_type.lower() == "mysql":
                        set_parts.append(f"{quoted_field} = %s")
                    else:  # sqlite
                        set_parts.append(f"{quoted_field} = ?")
                    # BUG #515 FIX + NATIVE ARRAY FIX: Use _serialize_params_for_sql
                    # This respects use_native_arrays config for PostgreSQL TEXT[] etc.
                    serialized_value = self._serialize_params_for_sql(
                        [value], model_name
                    )[0]
                    params.append(serialized_value)

                set_clause = "SET " + ", ".join(set_parts)

                # Build WHERE clause from filter using shared helper
                where_clause, where_params = self._build_where_clause(
                    filter_criteria, database_type, params_offset=len(params)
                )
                params.extend(where_params)

                # Issue #1252 — AND the tenant predicate into the WHERE so a
                # filter that would otherwise match another tenant's rows can
                # only touch the bound tenant's rows. The tenant value is a
                # BOUND parameter. An empty user filter yields no WHERE keyword,
                # so add one when the tenant predicate is the only condition.
                if bound_tenant is not None:
                    tenant_fragment, tenant_params = self._tenant_where_predicate(
                        database_type, params_offset=len(params), tenant_id=bound_tenant
                    )
                    if where_clause:
                        where_clause = f"{where_clause} AND {tenant_fragment}"
                    else:
                        where_clause = f"WHERE {tenant_fragment}"
                    params.extend(tenant_params)

                # SOFT DELETE read-consistency: by default a FILTER-based
                # bulk_update skips tombstoned rows (deleted_at IS NULL),
                # matching the list/read/count read auto-filter — a
                # bulk_update(filter_criteria={status:"active"}) must not
                # silently mutate rows the caller can't even see. The
                # ``AND deleted_at IS NULL`` fragment has no bound parameter,
                # so params numbering is untouched. include_deleted=True skips
                # the guard (un-delete: update_values={"deleted_at": None}).
                # deleted_at is dialect-quoted per dataflow-identifier-safety.
                # The explicit per-row data= path (below) is intentionally NOT
                # guarded — it targets rows by PK.
                if self._model_has_soft_delete(model_name) and not include_deleted:
                    from ..adapters.dialect import DialectManager

                    dialect = DialectManager.get_dialect(database_type)
                    quoted_deleted_at = dialect.quote_identifier("deleted_at")
                    if where_clause:
                        where_clause = f"{where_clause} AND {quoted_deleted_at} IS NULL"
                    else:
                        where_clause = f"WHERE {quoted_deleted_at} IS NULL"

                query = f"UPDATE {quoted_table} {set_clause} {where_clause}"
                # DEBUG (not WARN): the query carries schema column names and
                # params carry row VALUES (potential PII) — must not reach log
                # aggregators at WARN+ (observability.md Rule 8, security.md).
                logger.debug(
                    f"BULK_UPDATE: Executing query='{query}' with params={params}"
                )

                # Execute using cached AsyncSQLDatabaseNode
                # FIX: Use cached node instead of creating fresh instance
                # This ensures connection pooling and data visibility across operations
                sql_node = self.dataflow._get_or_create_async_sql_node(database_type)

                result = await sql_node.async_run(
                    query=query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                    transaction=transaction,  # #1585: join active scope (None = auto-commit)
                )

                logger.debug("bulk.bulk_update_sql_result", extra={"result": result})

                # Extract rows_affected from result
                # NEW format: {'result': {'data': {'rows_affected': N}, ...}}
                # OLD format: {'result': {'data': [{'rows_affected': N}], ...}}
                rows_affected = 0
                if result and "result" in result:
                    result_data = result["result"]
                    if "data" in result_data:
                        data = result_data["data"]
                        # Handle new format (dict with rows_affected)
                        if isinstance(data, dict) and "rows_affected" in data:
                            rows_affected = data["rows_affected"]
                        # Handle old format (list with rows_affected in first item)
                        elif isinstance(data, list) and len(data) > 0:
                            rows_affected = data[0].get("rows_affected", 0)

                success_result = {
                    "filter": filter_criteria,
                    "update": update_values,
                    "records_processed": rows_affected,
                    "success_count": rows_affected,
                    "failure_count": 0,
                    "success": True,
                }
                # DEBUG (not WARN): success_result carries raw filter/update row
                # VALUES (potential PII) — observability.md Rule 8, security.md.
                logger.debug(
                    "bulk.bulk_update_success", extra={"success_result": success_result}
                )
                return success_result
            except Exception as e:
                # Redteam MEDIUM (scanner-surface symmetry): scrub driver-error
                # column VALUES (potential PII) before log/return.
                safe_error = _sanitize_db_error(str(e))
                error_result = {
                    "success": False,
                    "error": f"Bulk update operation failed: {safe_error}",
                    "records_processed": 0,
                }
                logger.error(
                    # exc_info dropped: traceback re-leaks raw driver PII the
                    # sanitizer scrubbed (redteam LOW).
                    "bulk.bulk_update_exception",
                    extra={"error": safe_error},
                )
                logger.error(
                    "bulk.bulk_update_error_result",
                    extra={"error_result": error_result},
                )
                return error_result
        elif data is not None:
            # Data-based bulk update - update records by id
            logger.debug("BULK_UPDATE: Processing data-based update")

            # Issue #1252 — resolve the bound tenant; AND-ed into each per-record
            # WHERE id = ? below so tenant A cannot update tenant B's row by
            # supplying its id. Fails closed under multi_tenant with no bound
            # tenant. See _resolve_bulk_tenant.
            bound_tenant = self._resolve_bulk_tenant(model_name)

            # Handle empty data list (valid - update 0 records)
            if len(data) == 0:
                return {
                    "records_processed": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "batches": 0,
                    "batch_size": batch_size,
                    "success": True,
                }

            # Auto-convert ISO datetime strings to datetime objects for each record
            from ..core.nodes import convert_datetime_fields

            model_fields = self.dataflow.get_model_fields(model_name)
            for record in data:
                convert_datetime_fields(record, model_fields, logger)

            # Type-aware field validation
            try:
                from ..core.type_processor import TypeAwareFieldProcessor

                type_processor = TypeAwareFieldProcessor(model_fields, model_name)
                data = type_processor.process_records(
                    data,
                    operation="bulk_update",
                    strict=False,
                    skip_fields=set(),
                )
            except ImportError:
                logger.debug(
                    "TypeAwareFieldProcessor not available, skipping type validation"
                )
            except TypeError as e:
                return {"success": False, "error": str(e), "records_processed": 0}

            try:
                connection_string = self.dataflow.config.database.get_connection_url(
                    self.dataflow.config.environment
                )
                database_type = self.dataflow._detect_database_type()
                # Use stored table_name from _models (respects custom __tablename__)
                model_info = self.dataflow._models.get(model_name, {})
                table_name = model_info.get(
                    "table_name"
                ) or self.dataflow._class_name_to_table_name(model_name)

                # DEBUG (not WARN): conn masked via mask_url, but table_name is a
                # schema identifier — observability.md Rule 8 keeps schema names
                # off WARN+ aggregators.
                logger.debug(
                    f"BULK_UPDATE: conn={mask_url(connection_string)}, db_type={database_type}, table={table_name}"
                )

                # rules/dataflow-identifier-safety.md MUST-1: table_name, the id
                # PK column, and every SET column key are interpolated as bare
                # identifiers (drivers cannot bind identifiers). Record keys are
                # NOT constrained to declared model fields, so quote-validate
                # each via the dialect (reject-don't-escape).
                from ..adapters.dialect import DialectManager

                dialect = DialectManager.get_dialect(database_type)
                quoted_table = dialect.quote_identifier(table_name)
                quoted_id = dialect.quote_identifier("id")

                total_updated = 0
                batches_processed = 0

                # Process in batches
                for i in range(0, len(data), batch_size):  # type: ignore[arg-type]
                    batch = data[i : i + batch_size]  # type: ignore[index]

                    # Execute individual UPDATEs for each record
                    for record in batch:
                        if "id" not in record:
                            # WARN kept (operator should see skipped rows) but log
                            # only the key set, never the raw record VALUES
                            # (observability.md Rule 8, security.md).
                            logger.warning(
                                f"BULK_UPDATE: Skipping record without id: keys={sorted(record.keys())}"
                            )
                            continue

                        # Build SET clause from record (exclude id)
                        set_parts = []
                        params = []
                        for field, value in record.items():
                            if field == "id":
                                continue
                            quoted_field = dialect.quote_identifier(field)
                            if database_type.lower() == "postgresql":
                                set_parts.append(f"{quoted_field} = ${len(params) + 1}")
                            elif database_type.lower() == "mysql":
                                set_parts.append(f"{quoted_field} = %s")
                            else:  # sqlite
                                set_parts.append(f"{quoted_field} = ?")
                            # BUG #515 FIX: Serialize dict/list for SQL parameter binding
                            if isinstance(value, (dict, list)):
                                params.append(json.dumps(value))
                            else:
                                params.append(value)

                        if not set_parts:
                            # WARN kept (operator visibility) but log only the id,
                            # never the raw record VALUES (observability.md Rule 8).
                            logger.warning(
                                f"BULK_UPDATE: No fields to update for record: id={record.get('id')!r}"
                            )
                            continue

                        set_clause = "SET " + ", ".join(set_parts)

                        # Build WHERE clause for id.
                        # SOFT DELETE decision: this explicit per-row path targets
                        # a row by its PRIMARY KEY, so it is intentionally NOT
                        # guarded with deleted_at IS NULL — the caller named the
                        # exact row, which is precisely the un-delete / restore
                        # surface (e.g. data=[{"id": rid, "deleted_at": None}]).
                        # This matches single-record update-by-PK (UpdateNode),
                        # which also does not filter tombstoned rows. Only the
                        # FILTER-based path above (query-shaped) gets the guard.
                        if database_type.lower() == "postgresql":
                            where_clause = f"WHERE {quoted_id} = ${len(params) + 1}"
                        elif database_type.lower() == "mysql":
                            where_clause = f"WHERE {quoted_id} = %s"
                        else:  # sqlite
                            where_clause = f"WHERE {quoted_id} = ?"
                        params.append(record["id"])

                        # Issue #1252 — AND the tenant predicate so the per-id
                        # UPDATE can only touch the bound tenant's row.
                        if bound_tenant is not None:
                            tenant_fragment, tenant_params = (
                                self._tenant_where_predicate(
                                    database_type,
                                    params_offset=len(params),
                                    tenant_id=bound_tenant,
                                )
                            )
                            where_clause = f"{where_clause} AND {tenant_fragment}"
                            params.extend(tenant_params)

                        query = f"UPDATE {quoted_table} {set_clause} {where_clause}"

                        # Execute using cached AsyncSQLDatabaseNode
                        # FIX: Use cached node instead of creating fresh instance
                        # This ensures connection pooling and data visibility across operations
                        sql_node = self.dataflow._get_or_create_async_sql_node(
                            database_type
                        )

                        result = await sql_node.async_run(
                            query=query,
                            params=params,
                            fetch_mode="all",
                            validate_queries=False,
                            transaction_mode="auto",
                            transaction=transaction,  # #1585: join active scope
                        )

                        # Extract rows_affected
                        # NEW format: {'result': {'data': {'rows_affected': N}, ...}}
                        # OLD format: {'result': {'data': [{'rows_affected': N}], ...}}
                        rows_affected = 0
                        if result and "result" in result:
                            result_data = result["result"]
                            if "data" in result_data:
                                data = result_data["data"]
                                # Handle new format (dict with rows_affected)
                                if isinstance(data, dict) and "rows_affected" in data:
                                    rows_affected = data["rows_affected"]
                                # Handle old format (list with rows_affected in first item)
                                elif isinstance(data, list) and len(data) > 0:
                                    rows_affected = data[0].get("rows_affected", 0)

                        total_updated += rows_affected

                    batches_processed += 1

                success_result = {
                    "records_processed": total_updated,
                    "success_count": total_updated,
                    "failure_count": 0,
                    "batches": batches_processed,
                    "batch_size": batch_size,
                    "success": True,
                }
                # DEBUG (not WARN): success_result carries raw filter/update row
                # VALUES (potential PII) — observability.md Rule 8, security.md.
                logger.debug(
                    "bulk.bulk_update_success", extra={"success_result": success_result}
                )
                return success_result
            except Exception as e:
                # Redteam MEDIUM (scanner-surface symmetry): scrub driver-error
                # column VALUES (potential PII) before log/return.
                safe_error = _sanitize_db_error(str(e))
                error_result = {
                    "success": False,
                    "error": f"Bulk update operation failed: {safe_error}",
                    "records_processed": 0,
                }
                logger.error(
                    # exc_info dropped: traceback re-leaks raw driver PII the
                    # sanitizer scrubbed (redteam LOW).
                    "bulk.bulk_update_exception",
                    extra={"error": safe_error},
                )
                logger.error(
                    "bulk.bulk_update_error_result",
                    extra={"error_result": error_result},
                )
                return error_result

        return {"success": False, "error": "Either data or filter+update required"}

    async def bulk_delete(
        self,
        model_name: str,
        data: Optional[List[Dict[str, Any]]] = None,
        filter_criteria: Optional[Dict[str, Any]] = None,
        batch_size: int = 1000,
        transaction: Optional[Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk delete operation.

        #1585: a borrowed ``transaction`` handle makes the DELETE (and its
        pre-delete existence SELECT) run ON the scope's connection (joins a
        ``TransactionScopeNode``); ``None`` preserves auto-commit.
        """
        import logging

        logger = logging.getLogger(__name__)

        # DEBUG (not WARN): data carries raw id/row VALUES and kwargs may carry
        # caller values — must not reach log aggregators at WARN+
        # (observability.md Rule 8, security.md § No secrets in logs).
        logger.debug(
            f"BULK_DELETE ENTRY: model={model_name}, data={data}, filter={filter_criteria}, kwargs={kwargs}"
        )

        # Extract safe_mode and confirmed parameters
        safe_mode = kwargs.get("safe_mode", True)
        confirmed = kwargs.get("confirmed", False)

        logger.debug(
            f"BULK_DELETE VALIDATION: safe_mode={safe_mode}, confirmed={confirmed}"
        )

        # Validation: Empty filter requires confirmation
        if filter_criteria is not None and not filter_criteria:
            # Empty dict {} means delete ALL records - require confirmation
            logger.warning("BULK_DELETE: Empty filter detected, checking confirmation")
            if safe_mode and not confirmed:
                error_result = {
                    "success": False,
                    "error": "Bulk delete with empty filter requires confirmed=True. "
                    "Empty filter will delete ALL records in the table. "
                    "Set confirmed=True to proceed or provide a specific filter.",
                    "records_processed": 0,
                }
                logger.error(
                    "bulk.bulk_delete_validation_failed",
                    extra={"error_result": error_result},
                )
                return error_result

        if filter_criteria is not None:
            # Filter-based bulk delete - perform actual database operation
            logger.debug("BULK_DELETE: Processing filter-based delete")

            # Issue #1252 — resolve the bound tenant up front, OUTSIDE the try so
            # the fail-closed RuntimeError PROPAGATES (raises) rather than being
            # swallowed into an error dict by the broad `except Exception` below.
            # Mirrors the #1249 _apply_tenant_isolation raise in core/nodes.py.
            # None for single-tenant or non-tenant models. AND-ed into the WHERE
            # below so a filter cannot delete another tenant's rows (latent
            # cross-tenant delete protection). See _resolve_bulk_tenant.
            bound_tenant = self._resolve_bulk_tenant(model_name)

            try:
                # Get database connection and execute DELETE
                connection_string = self.dataflow.config.database.get_connection_url(
                    self.dataflow.config.environment
                )
                database_type = self.dataflow._detect_database_type()
                # Use stored table_name from _models (respects custom __tablename__)
                model_info = self.dataflow._models.get(model_name, {})
                table_name = model_info.get(
                    "table_name"
                ) or self.dataflow._class_name_to_table_name(model_name)

                # DEBUG (not WARN): conn masked, but table_name is a schema
                # identifier — observability.md Rule 8.
                logger.debug(
                    f"BULK_DELETE: conn={mask_url(connection_string)}, db_type={database_type}, table={table_name}"
                )

                # rules/dataflow-identifier-safety.md MUST-1: table_name is
                # interpolated as a bare identifier (drivers cannot bind
                # identifiers). Quote-validate via the dialect
                # (reject-don't-escape). WHERE columns are quoted inside
                # ``_build_where_clause``.
                from ..adapters.dialect import DialectManager

                quoted_table = DialectManager.get_dialect(
                    database_type
                ).quote_identifier(table_name)

                # Build WHERE clause from filter using shared helper
                where_clause, params = self._build_where_clause(
                    filter_criteria, database_type, params_offset=0
                )

                # Issue #1252 — AND the tenant predicate into the WHERE so a
                # filter can only delete the bound tenant's rows. Applied BEFORE
                # the COUNT pre-check + the DELETE so both see the scoped WHERE.
                # An empty user filter yields no WHERE keyword, so add one when
                # the tenant predicate is the only condition.
                if bound_tenant is not None:
                    tenant_fragment, tenant_params = self._tenant_where_predicate(
                        database_type, params_offset=len(params), tenant_id=bound_tenant
                    )
                    if where_clause:
                        where_clause = f"{where_clause} AND {tenant_fragment}"
                    else:
                        where_clause = f"WHERE {tenant_fragment}"
                    params.extend(tenant_params)

                # Execute using cached AsyncSQLDatabaseNode
                # FIX: Use cached node instead of creating fresh instance
                # This ensures connection pooling and data visibility across operations
                sql_node = self.dataflow._get_or_create_async_sql_node(database_type)

                logger.debug(
                    f"BULK_DELETE: Using cached sql_node={id(sql_node)}, "
                    f"cache_size={len(self.dataflow._async_sql_node_cache)}"
                )

                # DEBUG: First, check if records exist
                check_query = (
                    f"SELECT COUNT(*) as count FROM {quoted_table} {where_clause}"
                )
                check_result = await sql_node.async_run(
                    query=check_query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                    transaction=transaction,  # #1585: read-your-writes inside scope
                )
                logger.debug(
                    "bulk.bulk_delete_pre_delete_count_check",
                    extra={"check_result": check_result},
                )

                # SOFT DELETE (delete-surface consistency): for soft_delete
                # models a bulk delete MUST tombstone (UPDATE deleted_at), NOT
                # physically remove rows — mirroring the single-record
                # DeleteNode tombstone (core/nodes.py). Hard DELETE on a
                # soft_delete model is silent data loss. The ``AND deleted_at
                # IS NULL`` guard makes a repeat bulk_delete a no-op (already
                # tombstoned rows are not re-stamped). Non-soft-delete models
                # keep the hard DELETE. deleted_at is dialect-quoted per
                # rules/dataflow-identifier-safety.md. The tenant predicate is
                # already ANDed into where_clause above, so tombstone writes
                # inherit the same tenant scoping as the hard delete.
                if self._model_has_soft_delete(model_name):
                    from ..adapters.dialect import DialectManager

                    dialect = DialectManager.get_dialect(database_type)
                    quoted_deleted_at = dialect.quote_identifier("deleted_at")
                    if where_clause:
                        query = (
                            f"UPDATE {quoted_table} SET {quoted_deleted_at} = CURRENT_TIMESTAMP "
                            f"{where_clause} AND {quoted_deleted_at} IS NULL"
                        )
                    else:
                        query = (
                            f"UPDATE {quoted_table} SET {quoted_deleted_at} = CURRENT_TIMESTAMP "
                            f"WHERE {quoted_deleted_at} IS NULL"
                        )
                else:
                    query = f"DELETE FROM {quoted_table} {where_clause}"
                # DEBUG (not WARN): query carries schema names, params carry row
                # VALUES (potential PII) — observability.md Rule 8, security.md.
                logger.debug(
                    f"BULK_DELETE: Executing query='{query}' with params={params}"
                )

                result = await sql_node.async_run(
                    query=query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                    transaction=transaction,  # #1585: join active scope (None = auto-commit)
                )

                logger.debug("bulk.bulk_delete_sql_result", extra={"result": result})

                # Extract rows_affected from result
                # NEW format: {'result': {'data': {'rows_affected': N}, ...}}
                # OLD format: {'result': {'data': [{'rows_affected': N}], ...}}
                rows_affected = 0
                if result and "result" in result:
                    result_data = result["result"]
                    if "data" in result_data:
                        data = result_data["data"]
                        # Handle new format (dict with rows_affected)
                        if isinstance(data, dict) and "rows_affected" in data:
                            rows_affected = data["rows_affected"]
                        # Handle old format (list with rows_affected in first item)
                        elif isinstance(data, list) and len(data) > 0:
                            rows_affected = data[0].get("rows_affected", 0)

                success_result = {
                    "filter": filter_criteria,
                    "records_processed": rows_affected,
                    "success_count": rows_affected,
                    "failure_count": 0,
                    "success": True,
                }
                # DEBUG (not WARN): success_result carries raw filter row VALUES
                # (potential PII) — observability.md Rule 8, security.md.
                logger.debug(
                    "bulk.bulk_delete_success", extra={"success_result": success_result}
                )
                return success_result
            except Exception as e:
                # Redteam MEDIUM (scanner-surface symmetry): scrub driver-error
                # column VALUES (potential PII) before log/return.
                safe_error = _sanitize_db_error(str(e))
                error_result = {
                    "success": False,
                    "error": f"Bulk delete operation failed: {safe_error}",
                    "records_processed": 0,
                }
                logger.error(
                    # exc_info dropped: traceback re-leaks raw driver PII the
                    # sanitizer scrubbed (redteam LOW).
                    "bulk.bulk_delete_exception",
                    extra={"error": safe_error},
                )
                logger.error(
                    "bulk.bulk_delete_error_result",
                    extra={"error_result": error_result},
                )
                return error_result
        elif data is not None:
            # Data-based bulk delete (empty list [] is valid)
            return {
                "records_processed": len(data),
                "success_count": len(data),
                "failure_count": 0,
                "batch_size": batch_size,
                "success": True,
            }

        return {"success": False, "error": "Either data or filter required"}

    async def bulk_upsert(
        self,
        model_name: str,
        data: List[Dict[str, Any]],
        conflict_resolution: str = "update",
        batch_size: int = 1000,
        conflict_on: Optional[List[str]] = None,
        transaction: Optional[Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk upsert (insert or update) operation.

        #1585: a borrowed ``transaction`` handle makes every UPSERT batch run ON
        the scope's connection (joins a ``TransactionScopeNode``); ``None``
        preserves auto-commit.

        Args:
            model_name: Name of the model
            data: List of dictionaries with record data (must include 'id' field)
            conflict_resolution: Strategy for conflicts - "update" or "skip"/"ignore"
            batch_size: Number of records per batch
            conflict_on: Columns that define the conflict target (issue #1519).
                Defaults to ``["id"]``. MUST reference a PRIMARY KEY or UNIQUE
                constraint — a non-unique target raises
                ``BulkUpsertConflictTargetError`` (native ON CONFLICT cannot
                target a non-unique column). Backward-compatible aliases
                ``conflict_columns`` / ``conflict_fields`` are accepted via
                ``kwargs``.

        Returns:
            Dict with records_processed, inserted, updated, skipped, success

        Raises:
            BulkUpsertConflictTargetError: when ``conflict_on`` does not match a
                PK or UNIQUE constraint.
        """
        # Issue #1519: resolve conflict target. Accept legacy aliases that
        # callers / the generated node forward through kwargs.
        if conflict_on is None:
            conflict_on = kwargs.pop("conflict_columns", None) or kwargs.pop(
                "conflict_fields", None
            )
        else:
            kwargs.pop("conflict_columns", None)
            kwargs.pop("conflict_fields", None)
        conflict_columns = list(conflict_on) if conflict_on else ["id"]
        import logging

        logger = logging.getLogger(__name__)

        # DEBUG (not WARN): kwargs may carry caller values — observability.md
        # Rule 8, security.md § No secrets in logs.
        logger.debug(
            f"BULK_UPSERT ENTRY: model={model_name}, data_count={len(data) if data else 0}, "
            f"conflict_resolution={conflict_resolution}, batch_size={batch_size}, kwargs={kwargs}"
        )

        # Handle None data
        if data is None:
            return {"success": False, "error": "Data cannot be None"}

        # Handle empty data list (valid - upsert 0 records)
        if len(data) == 0:
            return {
                "records_processed": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "batches": 0,
                "batch_size": batch_size,
                "conflict_resolution": conflict_resolution,
                "success": True,
            }

        # Validate conflict_resolution
        if conflict_resolution not in ["update", "skip", "ignore"]:
            return {
                "success": False,
                "error": f"Invalid conflict_resolution '{conflict_resolution}'. "
                "Must be 'update', 'skip', or 'ignore'.",
            }

        # Issue #1252 — stamp tenant_id from the contextvar source (the one
        # tenant_context.switch() actually sets), NOT the stale legacy
        # self.dataflow._tenant_context dict. Fails closed under multi_tenant
        # with no bound tenant. tenant_id rides in the column list, so the
        # ON CONFLICT target stays valid (tenant_id is just another
        # INSERT/EXCLUDED column). See _resolve_bulk_tenant.
        bound_tenant = self._resolve_bulk_tenant(model_name)
        if bound_tenant is not None:
            for record in data:
                record["tenant_id"] = bound_tenant

        # Issue #1519: validate every record carries the conflict-target
        # columns, NOT a hardcoded 'id'. With ``conflict_on=["email"]`` and an
        # auto-generated SERIAL id, records legitimately omit 'id' — the old
        # hardcoded 'id' check rejected them, the same conflict_on-ignoring bug.
        # Runs AFTER tenant stamping so a tenant_id conflict target (e.g.
        # conflict_on=["email", "tenant_id"]) is present when checked.
        for i, record in enumerate(data):
            missing = [col for col in conflict_columns if col not in record]
            if missing:
                return {
                    "success": False,
                    "error": (
                        f"Record at index {i} is missing conflict-target "
                        f"column(s) {missing}. Every record MUST supply the "
                        f"conflict_on columns {conflict_columns} for upsert."
                    ),
                    "records_processed": 0,
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                }

        # Auto-convert ISO datetime strings to datetime objects for each record
        from ..core.nodes import convert_datetime_fields

        model_fields = self.dataflow.get_model_fields(model_name)
        for record in data:
            convert_datetime_fields(record, model_fields, logger)

        # Type-aware field validation
        try:
            from ..core.type_processor import TypeAwareFieldProcessor

            type_processor = TypeAwareFieldProcessor(model_fields, model_name)
            data = type_processor.process_records(
                data,
                operation="bulk_upsert",
                strict=False,
                skip_fields=set(),
            )
        except ImportError:
            logger.debug(
                "TypeAwareFieldProcessor not available, skipping type validation"
            )
        except TypeError as e:
            return {"success": False, "error": str(e)}

        # Issue #1519 (redteam H1): collapse duplicate conflict-target keys
        # WITHIN the input to the LAST occurrence BEFORE building the single
        # INSERT ... ON CONFLICT statement. A batch carrying two rows with the
        # same conflict key (e.g. two records id="x") is ambiguous: SQLite
        # applies last-wins in-statement but OVER-COUNTS (RETURNING yields one
        # row per VALUES tuple, not per physical row → created was reported as 2
        # when 1 row landed), while PostgreSQL fails loud ("ON CONFLICT DO
        # UPDATE command cannot affect row a second time"). De-duping last-wins
        # makes the reported counts match rows actually written AND makes both
        # dialects behave identically. Order is preserved by the last index.
        if len(data) > 1:
            _seen: Dict[tuple, int] = {}
            for _i, _rec in enumerate(data):
                _seen[tuple(_rec.get(_c) for _c in conflict_columns)] = _i
            if len(_seen) != len(data):
                data = [data[_i] for _i in sorted(_seen.values())]

        # Perform actual database upsert
        import time

        _upsert_start = time.perf_counter()
        try:
            connection_string = self.dataflow.config.database.get_connection_url(
                self.dataflow.config.environment
            )
            database_type = self.dataflow._detect_database_type()
            # Use stored table_name from _models (respects custom __tablename__)
            model_info = self.dataflow._models.get(model_name, {})
            table_name = model_info.get(
                "table_name"
            ) or self.dataflow._class_name_to_table_name(model_name)

            # Round 2 red team fix: route connection_string through mask_url —
            # NO truncation. See bulk_create above.
            # DEBUG (not WARN): table_name is a schema identifier (observability.md
            # Rule 8); conn is masked.
            logger.debug(
                f"BULK_UPSERT: conn={mask_url(connection_string)}, db_type={database_type}, "
                f"table={table_name}, conflict_resolution={conflict_resolution}"
            )

            # Get column names from first record
            columns = list(data[0].keys())

            # Issue #1519 + rules/dataflow-identifier-safety.md MUST-1: the
            # conflict-target columns are interpolated into ``ON CONFLICT (...)``
            # (drivers cannot bind identifiers), so every one MUST pass the
            # strict allowlist validator before interpolation. A conflict-target
            # column absent from the record set is a caller error.
            from kailash.db.dialect import _validate_identifier

            # rules/dataflow-identifier-safety.md MUST-1 (redteam CRITICAL):
            # table_name AND every column name are interpolated as bare
            # identifiers into INSERT INTO {table} ({columns}) ... ON CONFLICT
            # (...) DO UPDATE SET {col} = excluded.{col} — drivers cannot bind
            # identifiers. TypeAwareFieldProcessor does NOT constrain record
            # keys to declared model fields, so a crafted record key would
            # otherwise reach the SET/INSERT clause as raw SQL. Validate ALL of
            # them against the strict allowlist BEFORE interpolation, mirroring
            # the workflow node (nodes/bulk_upsert.py).
            _validate_identifier(table_name)
            for col in columns:
                _validate_identifier(col)

            for col in conflict_columns:
                if col not in columns:
                    raise ValueError(
                        f"bulk_upsert: conflict_on column '{col}' is not present "
                        f"in the record data (columns: {columns})."
                    )

            # Build upsert query based on database type
            total_inserted = 0
            total_updated = 0
            total_skipped = 0
            batches_processed = 0

            # Issue #1546: resolve the MySQL row-alias upsert form ONCE before the
            # batch loop (one cached SELECT VERSION() round-trip, shared with the
            # single-record path via the DataFlow instance).
            mysql_use_row_alias = False
            if database_type.lower() == "mysql":
                mysql_use_row_alias = (
                    await self.dataflow._resolve_mysql_row_alias_support(
                        self.dataflow._get_or_create_async_sql_node(database_type)
                    )
                )

            # Process in batches
            for i in range(0, len(data), batch_size):
                batch = data[i : i + batch_size]

                # Cross-tenant WRITE breach fix: emit the tenant-scoped DO-UPDATE
                # guard iff this is a multi_tenant model with a bound tenant
                # (``bound_tenant is not None`` ⟺ _resolve_bulk_tenant succeeded).
                tenant_guard = bound_tenant is not None

                # Build database-specific upsert query
                if database_type.lower() == "postgresql":
                    # PostgreSQL: INSERT ... ON CONFLICT (<conflict_on>) DO UPDATE
                    query, params = self._build_postgresql_upsert(
                        table_name,
                        columns,
                        batch,
                        conflict_resolution,
                        model_name,
                        conflict_columns,
                        tenant_guard=tenant_guard,
                    )
                elif database_type.lower() == "mysql":
                    # MySQL: INSERT ... ON DUPLICATE KEY UPDATE ...
                    query, params = self._build_mysql_upsert(
                        table_name,
                        columns,
                        batch,
                        conflict_resolution,
                        model_name,
                        conflict_columns,
                        use_row_alias=mysql_use_row_alias,
                        tenant_guard=tenant_guard,
                    )
                else:  # sqlite
                    # SQLite: INSERT ... ON CONFLICT (<conflict_on>) DO UPDATE
                    query, params = self._build_sqlite_upsert(
                        table_name,
                        columns,
                        batch,
                        conflict_resolution,
                        model_name,
                        conflict_columns,
                        tenant_guard=tenant_guard,
                    )

                logger.debug(
                    f"BULK_UPSERT: Executing batch {batches_processed + 1}, "
                    f"query='{query[:200]}...', param_count={len(params)}"
                )

                # Execute using cached AsyncSQLDatabaseNode
                # FIX: Use cached node instead of creating fresh instance
                # This ensures connection pooling and data visibility across operations
                sql_node = self.dataflow._get_or_create_async_sql_node(database_type)

                # Issue #1519: SQLite RETURNING cannot flag insert-vs-update per
                # row (no xmax), so derive real ``updated`` from a pre-count of
                # existing conflict-target keys. PG uses ``(xmax = 0)`` inline.
                preexisting = None
                if database_type.lower() == "sqlite" and conflict_resolution not in (
                    "skip",
                    "ignore",
                ):
                    preexisting = await self._count_existing_conflicts(
                        sql_node,
                        table_name,
                        conflict_columns,
                        batch,
                        transaction=transaction,  # #1585: read-your-writes in scope
                    )

                try:
                    result = await sql_node.async_run(
                        query=query,
                        params=params,
                        fetch_mode="all",
                        validate_queries=False,
                        transaction_mode="auto",
                        transaction=transaction,  # #1585: join active scope
                    )
                except Exception as exec_err:
                    # Issue #1519: a conflict target that is not a PK/UNIQUE key
                    # is a caller error, not a transient DB failure. Convert the
                    # opaque driver message into the actionable typed error
                    # instead of silently falling back to ON CONFLICT (id).
                    if _is_conflict_target_error(str(exec_err)):
                        raise BulkUpsertConflictTargetError(
                            conflict_on=conflict_columns,
                            model_name=model_name,
                            original_error=exec_err,
                        ) from exec_err
                    raise

                logger.debug("bulk.bulk_upsert_sql_result", extra={"result": result})

                # Extract operation counts from result
                # For UPSERT operations, we need to parse the result to determine
                # inserted vs updated vs skipped counts
                batch_inserted, batch_updated, batch_skipped = (
                    self._parse_upsert_result(
                        result,
                        database_type,
                        len(batch),
                        conflict_resolution,
                        preexisting_count=preexisting,
                    )
                )

                total_inserted += batch_inserted
                total_updated += batch_updated
                total_skipped += batch_skipped
                batches_processed += 1

            records_processed = total_inserted + total_updated + total_skipped

            # Cross-tenant WRITE breach fix (rules/tenant-isolation.md): when the
            # tenant-scoped DO-UPDATE guard is active (multi_tenant model, an
            # ``update`` resolution, and at least one updatable non-tenant column
            # so a real ``WHERE {table}.tenant_id = excluded.tenant_id`` was
            # emitted), a ``skipped`` row can ONLY mean the guard suppressed a
            # cross-tenant ``id`` collision — the ONLY row shape that conflicts
            # yet is neither inserted nor updated. Never a silent no-op: fail
            # closed and hand the express layer a structured signal it converts
            # into the actionable, tenant-scoped #1526 collision diagnostic.
            guarded_update_active = (
                bound_tenant is not None
                and conflict_resolution not in ("skip", "ignore")
                and len(
                    self._upsert_update_columns(
                        columns, conflict_columns, tenant_guarded=True
                    )
                )
                > 0
            )
            if guarded_update_active and total_skipped > 0:
                logger.warning(
                    "bulk.bulk_upsert_cross_tenant_conflict_suppressed",
                    extra={
                        "model": model_name,
                        "suppressed": total_skipped,
                        "tenant_id": bound_tenant,
                    },
                )
                return {
                    "success": False,
                    "cross_tenant_conflict": True,
                    "records_processed": total_inserted + total_updated,
                    "inserted": total_inserted,
                    "updated": total_updated,
                    "skipped": total_skipped,
                    "batches": batches_processed,
                    "batch_size": batch_size,
                    "conflict_resolution": conflict_resolution,
                    "error": (
                        "bulk_upsert refused a cross-tenant id collision: one or "
                        "more supplied ids already belong to a different tenant; "
                        "the existing row(s) were left untouched."
                    ),
                }

            elapsed = time.perf_counter() - _upsert_start
            success_result = {
                "records_processed": records_processed,
                "inserted": total_inserted,
                "updated": total_updated,
                "skipped": total_skipped,
                "batches": batches_processed,
                "batch_size": batch_size,
                "conflict_resolution": conflict_resolution,
                "success": True,
                "performance_metrics": {
                    "elapsed_seconds": elapsed,
                    "execution_time_seconds": elapsed,
                    "records_per_second": (
                        records_processed / elapsed if elapsed > 0 else 0
                    ),
                    "batches_processed": batches_processed,
                },
            }
            # DEBUG (not WARN): success_result carries raw row VALUES (potential
            # PII) — observability.md Rule 8, security.md.
            logger.debug(
                "bulk.bulk_upsert_success", extra={"success_result": success_result}
            )
            return success_result

        except BulkUpsertConflictTargetError:
            # Issue #1519: caller-actionable conflict-target error MUST propagate
            # as a typed raise, not be flattened into a {"success": False} dict.
            raise
        except Exception as e:
            # Redteam MEDIUM: a driver error from a DIFFERENT unique constraint
            # (e.g. "DETAIL: Key (username)=(alice) already exists") embeds
            # column VALUES that may be PII. Scrub them before the message is
            # logged (log aggregators have broader access than the DB) or
            # returned to the caller — same shared redactor as the workflow node
            # (rules/observability.md Rule 8; rules/security.md § No secrets in
            # logs).
            safe_error = _sanitize_db_error(str(e))
            error_result = {
                "success": False,
                "error": f"Bulk upsert operation failed: {safe_error}",
                "records_processed": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
            }
            logger.error(
                # exc_info dropped: see bulk_create — the traceback re-leaks the
                # raw driver message the sanitizer scrubbed (redteam LOW).
                "bulk.bulk_upsert_exception",
                extra={"error": safe_error},
            )
            logger.error(
                "bulk.bulk_upsert_error_result", extra={"error_result": error_result}
            )
            return error_result

    @staticmethod
    def _upsert_update_columns(
        columns: List[str],
        conflict_columns: List[str],
        tenant_guarded: bool = False,
    ) -> List[str]:
        """Columns eligible for the DO UPDATE SET clause (issue #1519).

        Excludes every conflict-target column (updating the conflict key is a
        no-op / error) plus the immutable ``id`` and ``created_at`` columns.

        Cross-tenant WRITE breach fix: on a ``multi_tenant`` model
        (``tenant_guarded=True``) ``tenant_id`` is ALSO excluded so an upsert can
        NEVER re-assign a row's owning tenant — defense-in-depth even inside the
        SAME tenant, and the necessary companion to the ``WHERE {table}.tenant_id
        = excluded.tenant_id`` DO-UPDATE guard the dialect builders emit (see
        ``rules/tenant-isolation.md``).
        """
        excluded = set(conflict_columns) | {"id", "created_at"}
        if tenant_guarded:
            excluded.add("tenant_id")
        return [col for col in columns if col not in excluded]

    def _build_postgresql_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
        conflict_columns: List[str],
        tenant_guard: bool = False,
    ) -> tuple:
        """Build PostgreSQL upsert query with ON CONFLICT clause.

        ``tenant_guard`` (multi_tenant models): the DO UPDATE carries a
        ``WHERE {table}.tenant_id = excluded.tenant_id`` predicate so a
        cross-tenant ``id`` collision does NOT overwrite another tenant's row —
        the row is left untouched (0 rows in RETURNING), which the caller detects
        as a suppressed cross-tenant collision. See ``rules/tenant-isolation.md``.
        """
        # rules/dataflow-identifier-safety.md MUST-1: table_name + every column
        # are interpolated as bare identifiers (drivers cannot bind
        # identifiers). Quote-validate via the dialect (reject-don't-escape);
        # raw ``columns`` stays for ``record.get(col)`` value lookup.
        from ..adapters.dialect import DialectManager

        dialect = DialectManager.get_dialect("postgresql")
        quoted_table = dialect.quote_identifier(table_name)
        column_names = ", ".join(dialect.quote_identifier(c) for c in columns)
        values_placeholders = []
        params = []

        # Build VALUES clause
        for record in batch:
            placeholders = ", ".join(
                [f"${j + 1}" for j in range(len(params), len(params) + len(columns))]
            )
            values_placeholders.append(f"({placeholders})")
            # NATIVE ARRAY FIX: Use _serialize_params_for_sql to respect use_native_arrays
            record_params = [record.get(col) for col in columns]
            record_params = self._serialize_params_for_sql(record_params, model_name)
            params.extend(record_params)

        values_clause = ", ".join(values_placeholders)
        conflict_target = ", ".join(
            dialect.quote_identifier(c) for c in conflict_columns
        )
        # Cross-tenant WRITE breach fix: a bound-tenant DO-UPDATE predicate.
        # ``tenant_id`` is stamped into every record upstream, so ``excluded``
        # carries it; the guard fires ONLY when the existing row belongs to the
        # SAME tenant. A cross-tenant ``id`` collision leaves the row untouched
        # (no theft, no tenant_id flip) — rules/tenant-isolation.md.
        tenant_where = ""
        if tenant_guard and "tenant_id" in columns:
            qtcol = dialect.quote_identifier("tenant_id")
            tenant_where = f" WHERE {quoted_table}.{qtcol} = excluded.{qtcol}"

        # Build ON CONFLICT clause with RETURNING to distinguish INSERT vs UPDATE.
        # xmax = 0 → INSERT, xmax > 0 → UPDATE (exact per-row flag).
        if conflict_resolution in ["skip", "ignore"]:
            conflict_clause = (
                f"ON CONFLICT ({conflict_target}) DO NOTHING "
                f"RETURNING id, (xmax = 0) AS inserted"
            )
        else:  # update
            update_columns = self._upsert_update_columns(
                columns, conflict_columns, tenant_guarded=tenant_guard
            )
            if update_columns:
                set_parts = [
                    f"{dialect.quote_identifier(col)} = EXCLUDED.{dialect.quote_identifier(col)}"
                    for col in update_columns
                ]
                conflict_clause = (
                    f"ON CONFLICT ({conflict_target}) DO UPDATE SET "
                    f"{', '.join(set_parts)}{tenant_where} "
                    f"RETURNING id, (xmax = 0) AS inserted"
                )
            else:
                # Nothing to update (all non-conflict columns are immutable).
                conflict_clause = (
                    f"ON CONFLICT ({conflict_target}) DO NOTHING "
                    f"RETURNING id, (xmax = 0) AS inserted"
                )

        query = f"INSERT INTO {quoted_table} ({column_names}) VALUES {values_clause} {conflict_clause}"
        return query, params

    def _build_mysql_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
        conflict_columns: List[str],
        use_row_alias: bool = False,
        tenant_guard: bool = False,
    ) -> tuple:
        """Build MySQL upsert query with ON DUPLICATE KEY UPDATE clause.

        MySQL auto-detects the violated UNIQUE/PRIMARY key, so ``conflict_on``
        does not appear in the clause itself — it only governs which columns are
        excluded from the update set.

        Issue #1546: ``VALUES(col)`` inside ON DUPLICATE KEY UPDATE is DEPRECATED on
        MySQL 8.0.20+. When ``use_row_alias`` is True (resolved by the caller to
        non-MariaDB MySQL >= 8.0.19), emit the row-alias form
        ``VALUES (...) AS new_row ... col = new_row.col``. The INSERT-side alias
        declaration and the ODKU-side references are built together here so the two
        halves cannot drift. MariaDB / MySQL < 8.0.19 keep the legacy form.

        Cross-tenant WRITE breach fix (``tenant_guard``, multi_tenant models):
        MySQL's ON DUPLICATE KEY UPDATE has NO ``WHERE`` clause, so the guard is
        pushed into each SET expression:
        ``col = IF(tenant_id = <new_tenant>, <new_col>, col)`` — a cross-tenant
        ``id`` collision keeps EVERY existing column value AND the owning
        ``tenant_id`` unchanged (fail-closed, no theft). ``tenant_id`` is excluded
        from the update set outright (rules/tenant-isolation.md).
        """
        # rules/dataflow-identifier-safety.md MUST-1: table_name + every column
        # are interpolated as bare identifiers (drivers cannot bind
        # identifiers). Quote-validate via the dialect (reject-don't-escape);
        # raw ``columns`` stays for ``record.get(col)`` value lookup.
        from ..adapters.dialect import DialectManager

        dialect = DialectManager.get_dialect("mysql")
        quoted_table = dialect.quote_identifier(table_name)
        column_names = ", ".join(dialect.quote_identifier(c) for c in columns)
        values_placeholders = []
        params = []

        # Build VALUES clause
        for record in batch:
            placeholders = ", ".join(["%s"] * len(columns))
            values_placeholders.append(f"({placeholders})")
            # NATIVE ARRAY FIX: Use _serialize_params_for_sql to respect use_native_arrays
            record_params = [record.get(col) for col in columns]
            record_params = self._serialize_params_for_sql(record_params, model_name)
            params.extend(record_params)

        values_clause = ", ".join(values_placeholders)
        alias = "new_row"
        alias_decl = f" AS {alias}" if use_row_alias else ""

        # Build ON DUPLICATE KEY UPDATE clause
        if conflict_resolution in ["skip", "ignore"]:
            # MySQL has no DO NOTHING; a no-op self-assignment of the first
            # conflict column keeps existing rows unchanged (valid in both forms).
            noop_col = dialect.quote_identifier(
                conflict_columns[0] if conflict_columns else "id"
            )
            duplicate_clause = f"ON DUPLICATE KEY UPDATE {noop_col} = {noop_col}"
        else:  # update
            update_columns = self._upsert_update_columns(
                columns, conflict_columns, tenant_guarded=tenant_guard
            )
            if update_columns:
                # Incoming-value reference: row alias (8.0.19+) or VALUES().
                def _new_ref(c: str) -> str:
                    qc = dialect.quote_identifier(c)
                    return f"{alias}.{qc}" if use_row_alias else f"VALUES({qc})"

                emit_guard = tenant_guard and "tenant_id" in columns
                qtcol = dialect.quote_identifier("tenant_id")
                set_parts = []
                for col in update_columns:
                    qc = dialect.quote_identifier(col)
                    new_ref = _new_ref(col)
                    if emit_guard:
                        # Keep the existing value (``{qc}``) unless the existing
                        # row belongs to the SAME tenant as the incoming row.
                        set_parts.append(
                            f"{qc} = IF({qtcol} = {_new_ref('tenant_id')}, "
                            f"{new_ref}, {qc})"
                        )
                    else:
                        set_parts.append(f"{qc} = {new_ref}")
                duplicate_clause = f"ON DUPLICATE KEY UPDATE {', '.join(set_parts)}"
            else:
                noop_col = dialect.quote_identifier(
                    conflict_columns[0] if conflict_columns else "id"
                )
                duplicate_clause = f"ON DUPLICATE KEY UPDATE {noop_col} = {noop_col}"

        query = f"INSERT INTO {quoted_table} ({column_names}) VALUES {values_clause}{alias_decl} {duplicate_clause}"
        return query, params

    def _build_sqlite_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
        conflict_columns: List[str],
        tenant_guard: bool = False,
    ) -> tuple:
        """Build SQLite upsert query with ON CONFLICT clause.

        SQLite RETURNING cannot flag insert-vs-update per row (no xmax); the
        caller derives real counts via a pre-count of existing conflict keys
        (see ``_count_existing_conflicts``). RETURNING id lets the caller count
        how many rows the statement actually affected.

        ``tenant_guard`` (multi_tenant models): the DO UPDATE carries a
        ``WHERE {table}.tenant_id = excluded.tenant_id`` predicate so a
        cross-tenant ``id`` collision leaves the row untouched (absent from
        RETURNING) — the caller detects the suppressed collision. SQLite honors
        the ``WHERE`` on ``ON CONFLICT ... DO UPDATE`` (rules/tenant-isolation.md).
        """
        # rules/dataflow-identifier-safety.md MUST-1: table_name + every column
        # are interpolated as bare identifiers (drivers cannot bind
        # identifiers). Quote-validate via the dialect (reject-don't-escape);
        # raw ``columns`` stays for ``record.get(col)`` value lookup.
        from ..adapters.dialect import DialectManager

        dialect = DialectManager.get_dialect("sqlite")
        quoted_table = dialect.quote_identifier(table_name)
        column_names = ", ".join(dialect.quote_identifier(c) for c in columns)
        values_placeholders = []
        params = []

        # Build VALUES clause
        for record in batch:
            placeholders = ", ".join(["?"] * len(columns))
            values_placeholders.append(f"({placeholders})")
            # NATIVE ARRAY FIX: Use _serialize_params_for_sql to respect use_native_arrays
            record_params = [record.get(col) for col in columns]
            record_params = self._serialize_params_for_sql(record_params, model_name)
            params.extend(record_params)

        values_clause = ", ".join(values_placeholders)
        conflict_target = ", ".join(
            dialect.quote_identifier(c) for c in conflict_columns
        )
        # Cross-tenant WRITE breach fix (see _build_postgresql_upsert).
        tenant_where = ""
        if tenant_guard and "tenant_id" in columns:
            qtcol = dialect.quote_identifier("tenant_id")
            tenant_where = f" WHERE {quoted_table}.{qtcol} = excluded.{qtcol}"

        # SQLite 3.35+ supports RETURNING.
        if conflict_resolution in ["skip", "ignore"]:
            # DO NOTHING returns only the inserted rows.
            conflict_clause = f"ON CONFLICT ({conflict_target}) DO NOTHING RETURNING id"
        else:  # update
            update_columns = self._upsert_update_columns(
                columns, conflict_columns, tenant_guarded=tenant_guard
            )
            if update_columns:
                set_parts = [
                    f"{dialect.quote_identifier(col)} = excluded.{dialect.quote_identifier(col)}"
                    for col in update_columns
                ]
                conflict_clause = (
                    f"ON CONFLICT ({conflict_target}) DO UPDATE SET "
                    f"{', '.join(set_parts)}{tenant_where} RETURNING id"
                )
            else:
                conflict_clause = (
                    f"ON CONFLICT ({conflict_target}) DO NOTHING RETURNING id"
                )

        query = f"INSERT INTO {quoted_table} ({column_names}) VALUES {values_clause} {conflict_clause}"
        return query, params

    async def _count_existing_conflicts(
        self,
        sql_node,
        table_name: str,
        conflict_columns: List[str],
        batch: List[Dict[str, Any]],
        transaction: Optional[Any] = None,
    ) -> int:
        """Count rows already present matching the batch's conflict-target keys.

        Issue #1519: SQLite's RETURNING gives no insert-vs-update signal, so the
        number of pre-existing conflict keys IS the number of UPDATEs the upsert
        will perform. Uses OR-of-AND equality (dialect-agnostic, avoids
        row-value IN quirks) with ``?`` placeholders bound positionally. NULL
        conflict values never match a UNIQUE target and are skipped.

        Concurrency contract (redteam M1): this COUNT and the subsequent upsert
        run as two ``transaction_mode="auto"`` statements, so under a CONCURRENT
        writer inserting a conflicting key between them the insert-vs-update
        split can be off by the number of racing rows. The persisted DATA stays
        correct (the upsert is atomic); only the reported ``inserted``/``updated``
        breakdown is best-effort under concurrency. Within a single call the
        input is de-duplicated on the conflict target upstream, so a batch can
        no longer self-conflict.
        """
        # rules/dataflow-identifier-safety.md MUST-1: table_name + conflict
        # columns are interpolated as bare identifiers (drivers cannot bind
        # identifiers). Quote-validate via the dialect (reject-don't-escape);
        # raw ``conflict_columns`` stays for ``record.get(col)`` value lookup.
        # This pre-count runs only on the SQLite upsert path.
        from ..adapters.dialect import DialectManager

        dialect = DialectManager.get_dialect("sqlite")
        quoted_table = dialect.quote_identifier(table_name)
        clauses: List[str] = []
        params: List[Any] = []
        for record in batch:
            vals = [record.get(col) for col in conflict_columns]
            if any(v is None for v in vals):
                continue
            conds = " AND ".join(
                f"{dialect.quote_identifier(col)} = ?" for col in conflict_columns
            )
            clauses.append(f"({conds})")
            params.extend(vals)

        if not clauses:
            return 0

        where = " OR ".join(clauses)
        query = f"SELECT COUNT(*) AS match_count FROM {quoted_table} WHERE {where}"
        result = await sql_node.async_run(
            query=query,
            params=params,
            fetch_mode="all",
            validate_queries=False,
            transaction_mode="auto",
            transaction=transaction,  # #1585: count on the scope's connection
        )
        rows = []
        if result and "result" in result:
            rows = result["result"].get("data", []) or []
        if rows and isinstance(rows[0], dict):
            value = (
                rows[0].get("match_count")
                or rows[0].get("COUNT(*)")
                or rows[0].get("count")
                or 0
            )
            return int(value)
        return 0

    def _parse_upsert_result(
        self,
        result: Dict[str, Any],
        database_type: str,
        batch_size: int,
        conflict_resolution: str,
        preexisting_count: Optional[int] = None,
    ) -> tuple:
        """Parse upsert result to extract inserted, updated, and skipped counts.

        Issue #1519: counts are derived from real signals — PostgreSQL uses the
        per-row ``(xmax = 0)`` RETURNING flag; SQLite uses ``preexisting_count``
        (rows whose conflict key already existed = UPDATEs); MySQL derives from
        the ``row_count`` (1 per insert, 2 per update). No fabricated ``// 2``.

        Returns:
            tuple: (inserted, updated, skipped)
        """
        returned_rows: List[Any] = []
        if result and "result" in result:
            result_data = result["result"]
            if isinstance(result_data.get("data"), list):
                returned_rows = result_data["data"]

        dbt = database_type.lower()

        # PostgreSQL: exact per-row flag from RETURNING id, (xmax = 0) AS inserted.
        if (
            dbt == "postgresql"
            and returned_rows
            and isinstance(returned_rows[0], dict)
            and "inserted" in returned_rows[0]
        ):
            inserted = sum(1 for row in returned_rows if row.get("inserted") is True)
            updated = sum(1 for row in returned_rows if row.get("inserted") is False)
            skipped = batch_size - len(returned_rows)
            return (inserted, updated, skipped)

        # SQLite: RETURNING id gives the affected-row count; the pre-count of
        # existing conflict keys gives the UPDATE count.
        if dbt == "sqlite":
            affected = len(returned_rows)
            if conflict_resolution in ["skip", "ignore"]:
                # DO NOTHING returns only inserted rows.
                inserted = affected
                updated = 0
                skipped = batch_size - affected
            else:
                pre = preexisting_count or 0
                updated = min(pre, affected)
                inserted = affected - updated
                skipped = batch_size - affected
            return (inserted, updated, skipped)

        # Fallback: Extract row_count from result (for MySQL or when RETURNING not available)
        rows_affected = 0
        if result and "result" in result:
            result_data = result["result"]
            # Try row_count first (INSERT operations)
            if "row_count" in result_data:
                rows_affected = result_data.get("row_count", 0)
            # Fall back to rows_affected in data (other operations)
            elif "data" in result_data and len(result_data["data"]) > 0:
                rows_affected = result_data["data"][0].get("rows_affected", 0)

        # For MySQL: ON DUPLICATE KEY UPDATE affects 1 row for insert, 2 for update
        if database_type.lower() == "mysql":
            if conflict_resolution in ["skip", "ignore"]:
                # All affected rows are inserts (conflicts were skipped)
                inserted = rows_affected
                updated = 0
                skipped = batch_size - rows_affected
            else:  # update
                # MySQL returns row_count = (inserts * 1) + (updates * 2)
                # If row_count > batch_size, some rows were updated
                if rows_affected > batch_size:
                    # row_count = inserts + (updates * 2)
                    # rows_affected - batch_size = extra count from updates
                    extra = rows_affected - batch_size
                    updated = extra
                    inserted = batch_size - updated
                else:
                    # All inserts, no updates
                    inserted = rows_affected
                    updated = 0
                skipped = 0
        else:
            # Fallback for other cases (shouldn't happen with RETURNING)
            if conflict_resolution in ["skip", "ignore"]:
                inserted = rows_affected
                updated = 0
                skipped = batch_size - rows_affected
            else:
                # Conservative estimate when RETURNING data not available
                inserted = rows_affected
                updated = 0
                skipped = batch_size - rows_affected

        return (inserted, updated, skipped)

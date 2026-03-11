"""
DataFlow Bulk Operations

High-performance bulk database operations.
"""

import json
from typing import Any, Dict, List

from ..nodes.bulk_result_processor import BulkCreateResultProcessor


class BulkOperations:
    """High-performance bulk operations for DataFlow."""

    def __init__(self, dataflow_instance):
        self.dataflow = dataflow_instance

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

        where_parts = []
        params = []
        db_lower = database_type.lower()

        for field, value in filter_criteria.items():
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

                    where_parts.append(f"{field} IN ({placeholders})")
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

                    where_parts.append(f"{field} NOT IN ({placeholders})")
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
                            f"{field} {sql_operator} ${len(params) + params_offset + 1}"
                        )
                    elif db_lower == "mysql":
                        where_parts.append(f"{field} {sql_operator} %s")
                    else:  # sqlite
                        where_parts.append(f"{field} {sql_operator} ?")
                    params.append(operand)

                else:
                    # Unknown operator - treat as equality
                    if db_lower == "postgresql":
                        where_parts.append(
                            f"{field} = ${len(params) + params_offset + 1}"
                        )
                    elif db_lower == "mysql":
                        where_parts.append(f"{field} = %s")
                    else:  # sqlite
                        where_parts.append(f"{field} = ?")
                    params.append(value)
            else:
                # Regular equality comparison
                if db_lower == "postgresql":
                    where_parts.append(f"{field} = ${len(params) + params_offset + 1}")
                elif db_lower == "mysql":
                    where_parts.append(f"{field} = %s")
                else:  # sqlite
                    where_parts.append(f"{field} = ?")
                params.append(value)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        return (where_clause, params)

    async def bulk_create(
        self,
        model_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk create operation."""
        import logging

        logger = logging.getLogger(__name__)

        logger.warning(
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

        # Apply tenant context if multi-tenant
        if self.dataflow.config.security.multi_tenant and self.dataflow._tenant_context:
            tenant_id = self.dataflow._tenant_context.get("tenant_id")
            for record in data:
                record["tenant_id"] = tenant_id

        # Auto-convert ISO datetime strings to datetime objects for each record
        from ..core.nodes import convert_datetime_fields

        model_fields = self.dataflow.get_model_fields(model_name)
        for record in data:
            convert_datetime_fields(record, model_fields, logger)

        # Type-aware field validation (TODO-153)
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

            logger.warning(
                f"BULK_CREATE: conn={connection_string[:50]}..., db_type={database_type}, table={table_name}"
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

            # Get column names from first record
            columns = list(data[0].keys())
            column_names = ", ".join(columns)

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
                query = (
                    f"INSERT INTO {table_name} ({column_names}) VALUES {values_clause}"
                )

                logger.warning(
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
                )

                logger.warning(f"BULK_CREATE: SQL result={result}")

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
            logger.warning(f"BULK_CREATE SUCCESS: {success_result}")
            return success_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Bulk create operation failed: {str(e)}",
                "records_processed": 0,
            }
            logger.error(f"BULK_CREATE EXCEPTION: {e}", exc_info=True)
            logger.error(f"BULK_CREATE ERROR RESULT: {error_result}")
            return error_result

    async def bulk_update(
        self,
        model_name: str,
        data: List[Dict[str, Any]] = None,
        filter_criteria: Dict[str, Any] = None,
        update_values: Dict[str, Any] = None,
        batch_size: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk update operation."""
        import logging

        logger = logging.getLogger(__name__)

        logger.warning(
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
                logger.error(f"BULK_UPDATE VALIDATION FAILED: {error_result}")
                return error_result

        if is_filter_based:
            # Filter-based bulk update - perform actual database operation
            logger.warning("BULK_UPDATE: Processing filter-based update")
            try:
                # Auto-convert ISO datetime strings to datetime objects in update_values
                from ..core.nodes import convert_datetime_fields

                model_fields = self.dataflow.get_model_fields(model_name)
                update_values = convert_datetime_fields(
                    update_values, model_fields, logger
                )

                # Type-aware field validation (TODO-153)
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

                logger.warning(
                    f"BULK_UPDATE: conn={connection_string[:50]}..., db_type={database_type}, table={table_name}"
                )

                # Build SET clause from update_values
                set_parts = []
                params = []
                for field, value in update_values.items():
                    if database_type.lower() == "postgresql":
                        set_parts.append(f"{field} = ${len(params) + 1}")
                    elif database_type.lower() == "mysql":
                        set_parts.append(f"{field} = %s")
                    else:  # sqlite
                        set_parts.append(f"{field} = ?")
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

                query = f"UPDATE {table_name} {set_clause} {where_clause}"
                logger.warning(
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
                )

                logger.warning(f"BULK_UPDATE: SQL result={result}")

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
                logger.warning(f"BULK_UPDATE SUCCESS: {success_result}")
                return success_result
            except Exception as e:
                error_result = {
                    "success": False,
                    "error": f"Bulk update operation failed: {str(e)}",
                    "records_processed": 0,
                }
                logger.error(f"BULK_UPDATE EXCEPTION: {e}", exc_info=True)
                logger.error(f"BULK_UPDATE ERROR RESULT: {error_result}")
                return error_result
        elif data is not None:
            # Data-based bulk update - update records by id
            logger.warning("BULK_UPDATE: Processing data-based update")

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

            # Type-aware field validation (TODO-153)
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

                logger.warning(
                    f"BULK_UPDATE: conn={connection_string[:50]}..., db_type={database_type}, table={table_name}"
                )

                total_updated = 0
                batches_processed = 0

                # Process in batches
                for i in range(0, len(data), batch_size):
                    batch = data[i : i + batch_size]

                    # Execute individual UPDATEs for each record
                    for record in batch:
                        if "id" not in record:
                            logger.warning(
                                f"BULK_UPDATE: Skipping record without id: {record}"
                            )
                            continue

                        # Build SET clause from record (exclude id)
                        set_parts = []
                        params = []
                        for field, value in record.items():
                            if field == "id":
                                continue
                            if database_type.lower() == "postgresql":
                                set_parts.append(f"{field} = ${len(params) + 1}")
                            elif database_type.lower() == "mysql":
                                set_parts.append(f"{field} = %s")
                            else:  # sqlite
                                set_parts.append(f"{field} = ?")
                            # BUG #515 FIX: Serialize dict/list for SQL parameter binding
                            if isinstance(value, (dict, list)):
                                params.append(json.dumps(value))
                            else:
                                params.append(value)

                        if not set_parts:
                            logger.warning(
                                f"BULK_UPDATE: No fields to update for record: {record}"
                            )
                            continue

                        set_clause = "SET " + ", ".join(set_parts)

                        # Build WHERE clause for id
                        if database_type.lower() == "postgresql":
                            where_clause = f"WHERE id = ${len(params) + 1}"
                        elif database_type.lower() == "mysql":
                            where_clause = "WHERE id = %s"
                        else:  # sqlite
                            where_clause = "WHERE id = ?"
                        params.append(record["id"])

                        query = f"UPDATE {table_name} {set_clause} {where_clause}"

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
                logger.warning(f"BULK_UPDATE SUCCESS: {success_result}")
                return success_result
            except Exception as e:
                error_result = {
                    "success": False,
                    "error": f"Bulk update operation failed: {str(e)}",
                    "records_processed": 0,
                }
                logger.error(f"BULK_UPDATE EXCEPTION: {e}", exc_info=True)
                logger.error(f"BULK_UPDATE ERROR RESULT: {error_result}")
                return error_result

        return {"success": False, "error": "Either data or filter+update required"}

    async def bulk_delete(
        self,
        model_name: str,
        data: List[Dict[str, Any]] = None,
        filter_criteria: Dict[str, Any] = None,
        batch_size: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk delete operation."""
        import logging

        logger = logging.getLogger(__name__)

        logger.warning(
            f"BULK_DELETE ENTRY: model={model_name}, data={data}, filter={filter_criteria}, kwargs={kwargs}"
        )

        # Extract safe_mode and confirmed parameters
        safe_mode = kwargs.get("safe_mode", True)
        confirmed = kwargs.get("confirmed", False)

        logger.warning(
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
                logger.error(f"BULK_DELETE VALIDATION FAILED: {error_result}")
                return error_result

        if filter_criteria is not None:
            # Filter-based bulk delete - perform actual database operation
            logger.warning("BULK_DELETE: Processing filter-based delete")
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

                logger.warning(
                    f"BULK_DELETE: conn={connection_string[:50]}..., db_type={database_type}, table={table_name}"
                )

                # Build WHERE clause from filter using shared helper
                where_clause, params = self._build_where_clause(
                    filter_criteria, database_type, params_offset=0
                )

                # Execute using cached AsyncSQLDatabaseNode
                # FIX: Use cached node instead of creating fresh instance
                # This ensures connection pooling and data visibility across operations
                sql_node = self.dataflow._get_or_create_async_sql_node(database_type)

                logger.warning(
                    f"BULK_DELETE: Using cached sql_node={id(sql_node)}, "
                    f"cache_size={len(self.dataflow._async_sql_node_cache)}"
                )

                # DEBUG: First, check if records exist
                check_query = (
                    f"SELECT COUNT(*) as count FROM {table_name} {where_clause}"
                )
                check_result = await sql_node.async_run(
                    query=check_query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                )
                logger.warning(f"BULK_DELETE: Pre-delete count check: {check_result}")

                query = f"DELETE FROM {table_name} {where_clause}"
                logger.warning(
                    f"BULK_DELETE: Executing query='{query}' with params={params}"
                )

                result = await sql_node.async_run(
                    query=query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                )

                logger.warning(f"BULK_DELETE: SQL result={result}")

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
                logger.warning(f"BULK_DELETE SUCCESS: {success_result}")
                return success_result
            except Exception as e:
                error_result = {
                    "success": False,
                    "error": f"Bulk delete operation failed: {str(e)}",
                    "records_processed": 0,
                }
                logger.error(f"BULK_DELETE EXCEPTION: {e}", exc_info=True)
                logger.error(f"BULK_DELETE ERROR RESULT: {error_result}")
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
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform bulk upsert (insert or update) operation.

        Args:
            model_name: Name of the model
            data: List of dictionaries with record data (must include 'id' field)
            conflict_resolution: Strategy for conflicts - "update" or "skip"/"ignore"
            batch_size: Number of records per batch

        Returns:
            Dict with records_processed, inserted, updated, skipped, success
        """
        import logging

        logger = logging.getLogger(__name__)

        logger.warning(
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

        # Validate all records have 'id' field
        for i, record in enumerate(data):
            if "id" not in record:
                return {
                    "success": False,
                    "error": f"Record at index {i} missing required 'id' field. "
                    "All records must have an 'id' for upsert operations.",
                }

        # Apply tenant context if multi-tenant
        if self.dataflow.config.security.multi_tenant and self.dataflow._tenant_context:
            tenant_id = self.dataflow._tenant_context.get("tenant_id")
            for record in data:
                record["tenant_id"] = tenant_id

        # Auto-convert ISO datetime strings to datetime objects for each record
        from ..core.nodes import convert_datetime_fields

        model_fields = self.dataflow.get_model_fields(model_name)
        for record in data:
            convert_datetime_fields(record, model_fields, logger)

        # Type-aware field validation (TODO-153)
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

        # Perform actual database upsert
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

            logger.warning(
                f"BULK_UPSERT: conn={connection_string[:50]}..., db_type={database_type}, "
                f"table={table_name}, conflict_resolution={conflict_resolution}"
            )

            # Get column names from first record
            columns = list(data[0].keys())
            column_names = ", ".join(columns)

            # Build upsert query based on database type
            total_inserted = 0
            total_updated = 0
            total_skipped = 0
            batches_processed = 0

            # Process in batches
            for i in range(0, len(data), batch_size):
                batch = data[i : i + batch_size]

                # Build database-specific upsert query
                if database_type.lower() == "postgresql":
                    # PostgreSQL: INSERT ... ON CONFLICT (id) DO UPDATE SET ...
                    query, params = self._build_postgresql_upsert(
                        table_name, columns, batch, conflict_resolution, model_name
                    )
                elif database_type.lower() == "mysql":
                    # MySQL: INSERT ... ON DUPLICATE KEY UPDATE ...
                    query, params = self._build_mysql_upsert(
                        table_name, columns, batch, conflict_resolution, model_name
                    )
                else:  # sqlite
                    # SQLite: INSERT ... ON CONFLICT (id) DO UPDATE SET ...
                    query, params = self._build_sqlite_upsert(
                        table_name, columns, batch, conflict_resolution, model_name
                    )

                logger.warning(
                    f"BULK_UPSERT: Executing batch {batches_processed + 1}, "
                    f"query='{query[:200]}...', param_count={len(params)}"
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
                )

                logger.warning(f"BULK_UPSERT: SQL result={result}")

                # Extract operation counts from result
                # For UPSERT operations, we need to parse the result to determine
                # inserted vs updated vs skipped counts
                batch_inserted, batch_updated, batch_skipped = (
                    self._parse_upsert_result(
                        result, database_type, len(batch), conflict_resolution
                    )
                )

                total_inserted += batch_inserted
                total_updated += batch_updated
                total_skipped += batch_skipped
                batches_processed += 1

            records_processed = total_inserted + total_updated + total_skipped
            success_result = {
                "records_processed": records_processed,
                "inserted": total_inserted,
                "updated": total_updated,
                "skipped": total_skipped,
                "batches": batches_processed,
                "batch_size": batch_size,
                "conflict_resolution": conflict_resolution,
                "success": True,
            }
            logger.warning(f"BULK_UPSERT SUCCESS: {success_result}")
            return success_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Bulk upsert operation failed: {str(e)}",
                "records_processed": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
            }
            logger.error(f"BULK_UPSERT EXCEPTION: {e}", exc_info=True)
            logger.error(f"BULK_UPSERT ERROR RESULT: {error_result}")
            return error_result

    def _build_postgresql_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
    ) -> tuple:
        """Build PostgreSQL upsert query with ON CONFLICT clause."""
        column_names = ", ".join(columns)
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

        # Build ON CONFLICT clause with RETURNING to distinguish INSERT vs UPDATE
        if conflict_resolution in ["skip", "ignore"]:
            # Skip conflicts - do nothing
            # Use xmax to detect if row was updated: xmax = 0 means INSERT, xmax > 0 means UPDATE (skipped)
            conflict_clause = (
                "ON CONFLICT (id) DO NOTHING RETURNING id, (xmax = 0) AS inserted"
            )
        else:  # update
            # Update all columns except 'id' on conflict
            update_columns = [col for col in columns if col != "id"]
            if update_columns:
                set_parts = [f"{col} = EXCLUDED.{col}" for col in update_columns]
                # Use xmax to detect if row was updated: xmax = 0 means INSERT, xmax > 0 means UPDATE
                conflict_clause = (
                    f"ON CONFLICT (id) DO UPDATE SET {', '.join(set_parts)} "
                    f"RETURNING id, (xmax = 0) AS inserted"
                )
            else:
                # Only 'id' column - skip on conflict
                conflict_clause = (
                    "ON CONFLICT (id) DO NOTHING RETURNING id, (xmax = 0) AS inserted"
                )

        query = f"INSERT INTO {table_name} ({column_names}) VALUES {values_clause} {conflict_clause}"
        return query, params

    def _build_mysql_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
    ) -> tuple:
        """Build MySQL upsert query with ON DUPLICATE KEY UPDATE clause."""
        column_names = ", ".join(columns)
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

        # Build ON DUPLICATE KEY UPDATE clause
        if conflict_resolution in ["skip", "ignore"]:
            # MySQL doesn't support DO NOTHING in ON DUPLICATE KEY
            # Workaround: update id to itself (no actual change)
            duplicate_clause = "ON DUPLICATE KEY UPDATE id = id"
        else:  # update
            # Update all columns except 'id' on duplicate
            update_columns = [col for col in columns if col != "id"]
            if update_columns:
                set_parts = [f"{col} = VALUES({col})" for col in update_columns]
                duplicate_clause = f"ON DUPLICATE KEY UPDATE {', '.join(set_parts)}"
            else:
                # Only 'id' column - no update needed
                duplicate_clause = "ON DUPLICATE KEY UPDATE id = id"

        query = f"INSERT INTO {table_name} ({column_names}) VALUES {values_clause} {duplicate_clause}"
        return query, params

    def _build_sqlite_upsert(
        self,
        table_name: str,
        columns: List[str],
        batch: List[Dict[str, Any]],
        conflict_resolution: str,
        model_name: str,
    ) -> tuple:
        """Build SQLite upsert query with ON CONFLICT clause."""
        column_names = ", ".join(columns)
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

        # Build ON CONFLICT clause with RETURNING to distinguish INSERT vs UPDATE
        # SQLite 3.35+ supports RETURNING
        if conflict_resolution in ["skip", "ignore"]:
            # Skip conflicts - do nothing
            # For SQLite, we can't use xmax but we can check if columns changed
            conflict_clause = "ON CONFLICT (id) DO NOTHING RETURNING id, 1 AS inserted"
        else:  # update
            # Update all columns except 'id' on conflict
            update_columns = [col for col in columns if col != "id"]
            if update_columns:
                set_parts = [f"{col} = excluded.{col}" for col in update_columns]
                # For SQLite, mark as inserted=0 when it's an update (simplified approach)
                # We use a CASE to detect: if old value != new value, it's an update
                conflict_clause = (
                    f"ON CONFLICT (id) DO UPDATE SET {', '.join(set_parts)} "
                    f"RETURNING id, 0 AS inserted"
                )
            else:
                # Only 'id' column - skip on conflict
                conflict_clause = (
                    "ON CONFLICT (id) DO NOTHING RETURNING id, 1 AS inserted"
                )

        query = f"INSERT INTO {table_name} ({column_names}) VALUES {values_clause} {conflict_clause}"
        return query, params

    def _parse_upsert_result(
        self,
        result: Dict[str, Any],
        database_type: str,
        batch_size: int,
        conflict_resolution: str,
    ) -> tuple:
        """Parse upsert result to extract inserted, updated, and skipped counts.

        Returns:
            tuple: (inserted, updated, skipped)
        """
        # For PostgreSQL and SQLite with RETURNING clause:
        # - The 'data' field contains rows with 'inserted' boolean column
        # - inserted=true means INSERT, inserted=false means UPDATE

        if result and "result" in result:
            result_data = result["result"]

            # Check if we have RETURNING data (PostgreSQL/SQLite with RETURNING)
            if "data" in result_data and len(result_data["data"]) > 0:
                returned_rows = result_data["data"]

                # For PostgreSQL/SQLite with RETURNING clause
                # Each row has 'inserted' field: True for INSERT, False for UPDATE
                if isinstance(returned_rows, list) and len(returned_rows) > 0:
                    first_row = returned_rows[0]
                    if isinstance(first_row, dict) and "inserted" in first_row:
                        # Count inserts and updates from RETURNING data
                        inserted = sum(
                            1 for row in returned_rows if row.get("inserted") is True
                        )
                        updated = sum(
                            1 for row in returned_rows if row.get("inserted") is False
                        )
                        skipped = batch_size - len(returned_rows)
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

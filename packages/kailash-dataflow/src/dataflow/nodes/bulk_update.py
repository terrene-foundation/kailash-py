"""DataFlow Bulk Update Node - SDK Compliant Implementation."""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

from .workflow_connection_manager import SmartNodeConnectionMixin


@register_node()
class BulkUpdateNode(SmartNodeConnectionMixin, AsyncNode):
    """Node for bulk update operations in DataFlow.

    This node extends AsyncNode with SmartNodeConnectionMixin to provide
    high-performance bulk update operations with connection pool support,
    following SDK architectural patterns.

    Configuration Parameters (set during initialization):
        table_name: Database table to operate on
        connection_string: Database connection string (fallback if no pool)
        connection_pool_id: ID of DataFlowConnectionManager in workflow (preferred)
        database_type: Type of database (postgresql, mysql, sqlite)
        batch_size: Records per batch for processing
        auto_timestamps: Automatically update updated_at timestamps
        multi_tenant: Enable tenant isolation
        tenant_id: Default tenant ID for operations
        version_control: Enable optimistic locking with version field

    Runtime Parameters (provided during execution):
        filter: Filter conditions as dictionary (where clause)
        ids: List of IDs to update
        data: List of records to update (each must have 'id')
        update_fields: Fields to update for filter-based updates
        tenant_id: Override default tenant ID
        return_updated: Return updated records in response
        dry_run: Simulate operation without executing
    """

    def __init__(self, **kwargs):
        """Initialize the BulkUpdateNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.table_name = kwargs.pop("table_name", None)
        self.connection_string = kwargs.pop("connection_string", None)
        self.database_type = kwargs.pop("database_type", "postgresql")
        self.batch_size = kwargs.pop("batch_size", 1000)
        self.auto_timestamps = kwargs.pop("auto_timestamps", True)
        self.multi_tenant = kwargs.pop("multi_tenant", False)
        self.tenant_isolation = kwargs.pop("tenant_isolation", self.multi_tenant)
        self.default_tenant_id = kwargs.pop("tenant_id", None)
        self.version_control = kwargs.pop("version_control", False)
        self.enable_versioning = kwargs.pop("enable_versioning", self.version_control)
        self.version_field = kwargs.pop("version_field", "version")

        # Call parent constructor
        super().__init__(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=False,
                description="Filter conditions for records to update",
            ),
            "ids": NodeParameter(
                name="ids",
                type=list,
                required=False,
                description="List of record IDs to update",
            ),
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,
                description="List of records with updates (must have 'id' field)",
            ),
            "update_fields": NodeParameter(
                name="update_fields",
                type=dict,
                required=False,
                description="Field values to update for filter/id based updates",
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                description="Tenant ID for multi-tenant operations",
            ),
            "return_updated": NodeParameter(
                name="return_updated",
                type=bool,
                required=False,
                default=False,
                description="Return the updated records in the response",
            ),
            "version_check": NodeParameter(
                name="version_check",
                type=bool,
                required=False,
                default=None,
                description="Enable version checking for this operation",
            ),
            "expected_version": NodeParameter(
                name="expected_version",
                type=int,
                required=False,
                description="Expected version for optimistic locking",
            ),
            "conflict_tracking": NodeParameter(
                name="conflict_tracking",
                type=bool,
                required=False,
                default=False,
                description="Track records with version conflicts",
            ),
            "dry_run": NodeParameter(
                name="dry_run",
                type=bool,
                required=False,
                default=False,
                description="Simulate the operation without executing",
            ),
            "workflow_context": NodeParameter(
                name="workflow_context",
                type=dict,
                required=False,
                default={},
                description="Workflow context containing connection pool reference",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute bulk update operation asynchronously with connection pool support."""
        # Use the mixin to execute with proper connection management
        return await self._execute_with_connection(self._perform_bulk_update, **kwargs)

    async def _perform_bulk_update(self, **kwargs) -> dict[str, Any]:
        """Perform the actual bulk update operation."""
        import time

        start_time = time.time()

        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            filter_conditions = validated_inputs.get("filter")
            ids = validated_inputs.get("ids")
            data = validated_inputs.get("data")
            update_fields = validated_inputs.get("update_fields")
            tenant_id = validated_inputs.get("tenant_id", self.default_tenant_id)
            return_updated = validated_inputs.get("return_updated", False)
            dry_run = validated_inputs.get("dry_run", False)

            # Validate input combinations
            # Use key existence check instead of truthiness to allow empty filter {}
            if "filter" not in validated_inputs and not ids and not data:
                raise NodeValidationError(
                    "Either filter conditions, ids, or data must be provided"
                )

            if not update_fields and not data:
                raise NodeValidationError(
                    "Either update_fields or data must be provided"
                )

            # Initialize result tracking
            total_records = 0
            updated_count = 0
            failed_count = 0
            version_conflicts = 0
            conflict_records = []
            updated_records = []
            errors = []
            batch_count = 0

            # Execute different update patterns
            if self.connection_string and not dry_run:
                # Remove parameters that are passed explicitly to avoid duplicate argument error
                kwargs_copy = kwargs.copy()
                kwargs_copy.pop("data", None)
                kwargs_copy.pop("ids", None)
                kwargs_copy.pop("filter", None)
                kwargs_copy.pop("update_fields", None)
                kwargs_copy.pop("tenant_id", None)
                kwargs_copy.pop("return_updated", None)
                kwargs_copy.pop("dry_run", None)
                kwargs_copy.pop("version_check", None)
                kwargs_copy.pop("conflict_tracking", None)

                if data:
                    # Update by data list (each record must have 'id')
                    result = await self._execute_data_update(
                        data, tenant_id, return_updated, validated_inputs, **kwargs_copy
                    )
                    updated_count = result["updated"]
                    updated_records = result.get("records", [])
                    version_conflicts = result.get("version_conflicts", 0)
                    conflict_records = result.get("conflict_records", [])
                    total_records = len(data)
                    batch_count = (
                        total_records + self.batch_size - 1
                    ) // self.batch_size
                elif ids:
                    # Update by ID list
                    result = await self._execute_ids_update(
                        ids,
                        update_fields,
                        tenant_id,
                        return_updated,
                        validated_inputs,
                        **kwargs_copy,
                    )
                    updated_count = result["updated"]
                    updated_records = result.get("records", [])
                    total_records = len(ids)
                    batch_count = 1
                else:
                    # Update by filter
                    result = await self._execute_filter_update(
                        filter_conditions,
                        update_fields,
                        tenant_id,
                        return_updated,
                        validated_inputs,
                        **kwargs_copy,
                    )
                    updated_count = result["updated"]
                    updated_records = result.get("records", [])
                    total_records = updated_count  # For filter updates, we don't know total beforehand
                    batch_count = 1
            else:
                # Dry run simulation
                if data:
                    total_records = len(data)
                elif ids:
                    total_records = len(ids)
                else:
                    # For filter updates in dry run, estimate count
                    total_records, _ = await self._estimate_filter_count(
                        filter_conditions, tenant_id
                    )

                updated_count = total_records
                batch_count = (
                    (total_records + self.batch_size - 1) // self.batch_size
                    if total_records > 0
                    else 0
                )

            # Calculate performance metrics
            end_time = time.time()
            duration = end_time - start_time
            records_per_second = updated_count / duration if duration > 0 else 0

            # Build result following SDK patterns
            result = {
                "success": updated_count > 0 or version_conflicts > 0 or dry_run,
                "updated": updated_count,
                "updated_count": updated_count,  # Compatibility alias for tests
                "failed": failed_count,
                "total": total_records,
                "batches": batch_count,
                "conflicts": version_conflicts,  # Always include conflicts field
                "metadata": {
                    "table": self.table_name,
                    "operation": "bulk_update",
                    "batch_size": self.batch_size,
                    "dry_run": dry_run,
                    "multi_tenant": self.multi_tenant,
                    "version_control": self.version_control,
                },
                "performance_metrics": {
                    "duration_seconds": duration,
                    "records_per_second": records_per_second,
                    "avg_per_record_ms": (
                        (duration * 1000) / updated_count if updated_count > 0 else 0
                    ),
                },
            }

            # Add optional fields based on operation results
            if tenant_id and self.multi_tenant:
                result["tenant_id"] = tenant_id

            if return_updated and updated_records:
                result["records"] = updated_records  # Use consistent field name
                result["updated_records"] = (
                    updated_records  # Compatibility alias for tests
                )

            if version_conflicts > 0:
                result["conflicts"] = (
                    version_conflicts  # Keep consistent with test expectations
                )
                result["version_conflicts"] = (
                    version_conflicts  # Also provide detailed name
                )
                result["conflict_records"] = conflict_records

            if errors:
                result["errors"] = errors

            # Add dry run specific fields
            if dry_run:
                result["would_update"] = updated_count
                result["query"] = f"UPDATE {self.table_name} SET ... WHERE ..."
                result["parameters"] = {
                    "filter": filter_conditions,
                    "update_fields": update_fields,
                }

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            raise NodeExecutionError(f"Bulk update operation failed: {str(e)}")

    def _build_update_operators(
        self, field: str, operators: Dict[str, Any]
    ) -> List[str]:
        """Build SET clauses for MongoDB-style update operators."""
        set_clauses = []

        for operator, operand in operators.items():
            if operator == "$set":
                # Direct assignment
                if isinstance(operand, str):
                    escaped_value = operand.replace("'", "''")
                    set_clauses.append(f"{field} = '{escaped_value}'")
                elif operand is None:
                    set_clauses.append(f"{field} = NULL")
                else:
                    set_clauses.append(f"{field} = {operand}")
            elif operator == "$inc":
                # Increment
                set_clauses.append(f"{field} = {field} + {operand}")
            elif operator == "$mul" or operator == "$multiply":
                # Multiply
                set_clauses.append(f"{field} = {field} * {operand}")
            elif operator == "$dec":
                # Decrement
                set_clauses.append(f"{field} = {field} - {operand}")
            elif operator == "$concat":
                # String concatenation
                if self.database_type == "postgresql":
                    set_clauses.append(f"{field} = {field} || '{operand}'")
                else:
                    set_clauses.append(f"{field} = CONCAT({field}, '{operand}')")
            else:
                # Unknown operator, skip
                pass

        return set_clauses

    async def _execute_data_update(
        self,
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_updated: bool,
        validated_inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute update using data list (each record must have 'id')."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        updated_count = 0
        updated_records = []
        version_conflicts_count = 0
        conflict_records_list = []

        # Process in batches
        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]

            for record in batch:
                if "id" not in record:
                    continue

                record_id = record["id"]
                update_dict = {k: v for k, v in record.items() if k != "id"}

                # Handle version control
                enable_version_check = validated_inputs.get(
                    "version_check", self.enable_versioning
                )
                if enable_version_check and self.version_field in record:
                    current_version = record.pop(self.version_field)
                    update_dict[self.version_field] = current_version + 1
                    version_where = f" AND {self.version_field} = {current_version}"
                else:
                    version_where = ""

                # Add auto timestamps
                if self.auto_timestamps:
                    update_dict["updated_at"] = "CURRENT_TIMESTAMP"

                # Build UPDATE query
                set_clauses = []
                for field, value in update_dict.items():
                    if isinstance(value, dict):
                        # Handle MongoDB-style operators
                        field_clauses = self._build_update_operators(field, value)
                        set_clauses.extend(field_clauses)
                    elif value == "CURRENT_TIMESTAMP":
                        set_clauses.append(f"{field} = CURRENT_TIMESTAMP")
                    elif isinstance(value, str):
                        escaped_value = value.replace("'", "''")
                        set_clauses.append(f"{field} = '{escaped_value}'")
                    elif value is None:
                        set_clauses.append(f"{field} = NULL")
                    else:
                        set_clauses.append(f"{field} = {value}")

                set_clause = ", ".join(set_clauses)

                # Build WHERE clause
                where_conditions = [f"id = {record_id}"]
                if self.multi_tenant and tenant_id:
                    where_conditions.append(f"tenant_id = '{tenant_id}'")

                where_clause = " AND ".join(where_conditions) + version_where

                # Execute update
                query = (
                    f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"
                )

                if return_updated:
                    query += " RETURNING *"

                update_node = AsyncSQLDatabaseNode(
                    connection_string=self.connection_string,
                    database_type=self.database_type,
                    validate_queries=False,
                )

                result = await update_node.async_run(query=query)

                # Process result
                if "result" in result and result["result"]:
                    result_data = result["result"]
                    # Handle AsyncSQLDatabaseNode result format
                    if isinstance(result_data, dict) and "data" in result_data:
                        data_list = result_data["data"]
                        if isinstance(data_list, list) and len(data_list) > 0:
                            first_item = data_list[0]
                            if (
                                isinstance(first_item, dict)
                                and "rows_affected" in first_item
                                and first_item["rows_affected"] > 0
                            ):
                                updated_count += 1
                            elif return_updated:
                                # If we have actual row data
                                updated_count += 1
                                updated_records.append(first_item)
                            elif (
                                first_item["rows_affected"] == 0
                                and enable_version_check
                            ):
                                # Version conflict detected - no rows updated
                                version_conflicts_count += 1
                                if validated_inputs.get("conflict_tracking", False):
                                    conflict_records_list.append(
                                        {
                                            "id": record_id,
                                            "expected_version": (
                                                current_version
                                                if "current_version" in locals()
                                                else None
                                            ),
                                            "reason": "version_mismatch",
                                        }
                                    )
                        elif enable_version_check and validated_inputs.get(
                            "conflict_tracking", False
                        ):
                            # Version conflict - record not updated
                            version_conflicts_count += 1
                            conflict_records_list.append(
                                {
                                    "id": record_id,
                                    "expected_version": current_version,
                                    "reason": "version_mismatch",
                                }
                            )
                    elif isinstance(result_data, list) and len(result_data) > 0:
                        updated_count += 1
                        if return_updated:
                            updated_records.append(result_data[0])
                elif "rows_affected" in result and result["rows_affected"] > 0:
                    updated_count += 1
                elif (
                    "rows_affected" in result
                    and result["rows_affected"] == 0
                    and enable_version_check
                ):
                    # Version conflict - no rows updated
                    version_conflicts_count += 1
                    if validated_inputs.get("conflict_tracking", False):
                        conflict_records_list.append(
                            {
                                "id": record_id,
                                "expected_version": (
                                    current_version
                                    if "current_version" in locals()
                                    else None
                                ),
                                "reason": "version_mismatch",
                            }
                        )
                elif enable_version_check and validated_inputs.get(
                    "conflict_tracking", False
                ):
                    # Check if it was a version conflict
                    version_conflicts_count += 1
                    conflict_records_list.append(
                        {
                            "id": record_id,
                            "expected_version": (
                                current_version
                                if "current_version" in locals()
                                else None
                            ),
                            "reason": "version_mismatch",
                        }
                    )

        return {
            "updated": updated_count,
            "records": updated_records,
            "version_conflicts": version_conflicts_count,
            "conflict_records": conflict_records_list,
        }

    async def _execute_ids_update(
        self,
        ids: List[Any],
        update_fields: Dict[str, Any],
        tenant_id: Optional[str],
        return_updated: bool,
        validated_inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute update using ID list."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Add auto timestamps
        if self.auto_timestamps:
            update_fields = update_fields.copy()
            update_fields["updated_at"] = "CURRENT_TIMESTAMP"

        # Handle version control
        enable_version_check = validated_inputs.get(
            "version_check", self.enable_versioning
        )
        expected_version = validated_inputs.get("expected_version")

        # Build SET clause
        set_clauses = []
        for field, value in update_fields.items():
            if isinstance(value, dict):
                # Handle MongoDB-style operators
                field_clauses = self._build_update_operators(field, value)
                set_clauses.extend(field_clauses)
            elif value == "CURRENT_TIMESTAMP":
                set_clauses.append(f"{field} = CURRENT_TIMESTAMP")
            elif isinstance(value, str):
                escaped_value = value.replace("'", "''")
                set_clauses.append(f"{field} = '{escaped_value}'")
            elif value is None:
                set_clauses.append(f"{field} = NULL")
            else:
                set_clauses.append(f"{field} = {value}")

        # Add version increment if version control is enabled
        if enable_version_check:
            set_clauses.append(f"{self.version_field} = {self.version_field} + 1")

        set_clause = ", ".join(set_clauses)

        # Build WHERE clause
        quoted_ids = [
            f"'{id_val}'" if isinstance(id_val, str) else str(id_val) for id_val in ids
        ]
        id_list = ", ".join(quoted_ids)
        where_conditions = [f"id IN ({id_list})"]

        if self.multi_tenant and tenant_id:
            where_conditions.append(f"tenant_id = '{tenant_id}'")

        # Add version check to WHERE clause if version control is enabled
        if enable_version_check and expected_version is not None:
            where_conditions.append(f"{self.version_field} = {expected_version}")

        where_clause = " AND ".join(where_conditions)

        # Execute update
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"

        if return_updated:
            query += " RETURNING *"

        result = await self._execute_query(query, **kwargs)

        # Process result
        updated_count = 0
        updated_records = []

        # Check for success in result or assume success if we have result data
        if "result" in result and result["result"]:
            result_data = result["result"]
            # Handle AsyncSQLDatabaseNode result format
            if isinstance(result_data, dict) and "data" in result_data:
                data_list = result_data["data"]
                if isinstance(data_list, list) and len(data_list) > 0:
                    first_item = data_list[0]
                    if isinstance(first_item, dict) and "rows_affected" in first_item:
                        updated_count = first_item["rows_affected"]
                    elif return_updated:
                        # If we have actual row data
                        updated_count = len(data_list)
                        updated_records = data_list
            elif isinstance(result_data, list):
                updated_count = len(result_data)
                if return_updated:
                    updated_records = result_data
        elif "rows_affected" in result:
            updated_count = result["rows_affected"]
            # Check for data at top level
            if return_updated and "data" in result and isinstance(result["data"], list):
                updated_records = result["data"]

        return {"updated": updated_count, "records": updated_records}

    async def _execute_filter_update(
        self,
        filter_conditions: Dict[str, Any],
        update_fields: Dict[str, Any],
        tenant_id: Optional[str],
        return_updated: bool,
        validated_inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute update using filter conditions."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Add auto timestamps
        if self.auto_timestamps:
            update_fields = update_fields.copy()
            update_fields["updated_at"] = "CURRENT_TIMESTAMP"

        # Handle version increment
        enable_version_check = validated_inputs.get(
            "version_check", self.enable_versioning
        )
        if enable_version_check:
            # Don't add version increment as a regular field, handle it separately
            pass

        # Build SET clause
        set_clauses = []
        for field, value in update_fields.items():
            if isinstance(value, dict):
                # Handle MongoDB-style operators
                field_clauses = self._build_update_operators(field, value)
                set_clauses.extend(field_clauses)
            elif value == "CURRENT_TIMESTAMP":
                set_clauses.append(f"{field} = CURRENT_TIMESTAMP")
            elif isinstance(value, str):
                escaped_value = value.replace("'", "''")
                set_clauses.append(f"{field} = '{escaped_value}'")
            elif value is None:
                set_clauses.append(f"{field} = NULL")
            else:
                set_clauses.append(f"{field} = {value}")

        set_clause = ", ".join(set_clauses)

        # Build WHERE clause
        where_conditions = []
        if self.multi_tenant and tenant_id:
            where_conditions.append(f"tenant_id = '{tenant_id}'")

        where_conditions.extend(self._build_where_conditions(filter_conditions))
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Execute update
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"

        if return_updated:
            query += " RETURNING *"

        result = await self._execute_query(query, **kwargs)

        # Process result
        updated_count = 0
        updated_records = []

        # Check for success in result or assume success if we have result data
        if "result" in result and result["result"]:
            result_data = result["result"]
            # Handle AsyncSQLDatabaseNode result format
            if isinstance(result_data, dict) and "data" in result_data:
                data_list = result_data["data"]
                if isinstance(data_list, list) and len(data_list) > 0:
                    first_item = data_list[0]
                    if isinstance(first_item, dict) and "rows_affected" in first_item:
                        updated_count = first_item["rows_affected"]
                    elif return_updated:
                        # If we have actual row data
                        updated_count = len(data_list)
                        updated_records = data_list
            elif isinstance(result_data, list):
                updated_count = len(result_data)
                if return_updated:
                    updated_records = result_data
        elif "rows_affected" in result:
            updated_count = result["rows_affected"]

        return {"updated": updated_count, "records": updated_records}

    def _build_where_conditions(self, filter_dict: Dict[str, Any]) -> List[str]:
        """Build WHERE conditions from filter dictionary."""
        conditions = []

        for field, value in filter_dict.items():
            if isinstance(value, dict):
                # Handle operators
                for op, operand in value.items():
                    if op == "$eq":
                        if isinstance(operand, str):
                            conditions.append(f"{field} = '{operand}'")
                        else:
                            conditions.append(f"{field} = {operand}")
                    elif op == "$ne":
                        if isinstance(operand, str):
                            conditions.append(f"{field} != '{operand}'")
                        else:
                            conditions.append(f"{field} != {operand}")
                    elif op == "$gt":
                        conditions.append(f"{field} > {operand}")
                    elif op == "$gte":
                        conditions.append(f"{field} >= {operand}")
                    elif op == "$lt":
                        conditions.append(f"{field} < {operand}")
                    elif op == "$lte":
                        conditions.append(f"{field} <= {operand}")
                    elif op == "$in":
                        values = [
                            f"'{v}'" if isinstance(v, str) else str(v) for v in operand
                        ]
                        conditions.append(f"{field} IN ({', '.join(values)})")
                    elif op == "$like":
                        conditions.append(f"{field} LIKE '{operand}'")
            else:
                # Direct equality
                if isinstance(value, str):
                    conditions.append(f"{field} = '{value}'")
                elif value is None:
                    conditions.append(f"{field} IS NULL")
                else:
                    conditions.append(f"{field} = {value}")

        return conditions

    def _process_update_result(
        self, result: Dict[str, Any], expected_count: int
    ) -> tuple[int, List[Dict[str, Any]]]:
        """Process result from AsyncSQLDatabaseNode to extract update count and records."""
        updated_count = 0
        updated_records = []

        # Check for result data
        if "result" in result and result["result"]:
            result_data = result["result"]
            # Handle AsyncSQLDatabaseNode result format
            if isinstance(result_data, dict) and "data" in result_data:
                data_list = result_data["data"]
                if isinstance(data_list, list) and len(data_list) > 0:
                    first_item = data_list[0]
                    if isinstance(first_item, dict) and "rows_affected" in first_item:
                        updated_count = first_item["rows_affected"]
                    else:
                        # If we have actual row data
                        updated_count = len(data_list)
                        updated_records = data_list
            elif isinstance(result_data, list):
                updated_count = len(result_data)
                updated_records = result_data
        elif "rows_affected" in result:
            updated_count = result["rows_affected"]
        elif result.get("success", False):
            # Assume success if no specific count
            updated_count = expected_count

        return updated_count, updated_records

    async def _estimate_filter_count(
        self, filter_conditions: Dict[str, Any], tenant_id: Optional[str]
    ) -> tuple[int, List[Any]]:
        """Estimate the number of records that would be updated by filter."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Build WHERE clause
        where_conditions = []
        if self.multi_tenant and tenant_id:
            where_conditions.append(f"tenant_id = '{tenant_id}'")

        if filter_conditions:
            where_conditions.extend(self._build_where_conditions(filter_conditions))

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        count_query = (
            f"SELECT COUNT(*) as count FROM {self.table_name} WHERE {where_clause}"
        )

        count_node = AsyncSQLDatabaseNode(
            connection_string=self.connection_string,
            database_type=self.database_type,
            validate_queries=False,
        )

        count_result = await count_node.async_run(query=count_query)

        if "result" in count_result and count_result["result"]:
            result_data = count_result["result"]
            if isinstance(result_data, list) and len(result_data) > 0:
                count_value = result_data[0]
                if isinstance(count_value, dict) and "count" in count_value:
                    return count_value["count"], []

        return 0, []

    async def _execute_query(self, query: str, **kwargs) -> Dict[str, Any]:
        """Execute SQL query using connection pool if available, otherwise direct connection."""
        # Check if we have connection pool access via mixin
        use_pooled_connection = kwargs.get("use_pooled_connection", False)

        if use_pooled_connection and self.connection_pool_id and self._pool_manager:
            # Use connection pool via DataFlowConnectionManager
            try:
                return await self._pool_manager.execute(
                    operation="execute", query=query
                )
            except Exception as e:
                # Log and fallback to direct connection
                import logging

                logging.warning(
                    f"Failed to execute via pool: {e}, falling back to direct connection"
                )

        # Fallback to direct AsyncSQLDatabaseNode
        if not self.connection_string:
            raise NodeValidationError(
                "No connection_string or connection pool available"
            )

        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        db_node = AsyncSQLDatabaseNode(
            connection_string=self.connection_string,
            database_type=self.database_type,
            validate_queries=False,  # Allow UPDATE operations
        )

        return await db_node.async_run(query=query)

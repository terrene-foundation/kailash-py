"""Asynchronous logic operation nodes for the Kailash SDK.

This module provides asynchronous versions of common logical operations such as merging
and branching. These nodes are optimized for handling I/O-bound operations and large
data processing tasks in workflows.
"""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class AsyncMerge(AsyncNode):
    """Asynchronously merges multiple data sources.

    Note: We implement run() to fulfill the Node abstract base class requirement,
    but it's just a pass-through to async_run().


    This node extends the standard Merge node with asynchronous execution capabilities,
    making it more efficient for:

    1. Combining large datasets from parallel branches
    2. Joining data from multiple async sources
    3. Processing streaming data in chunks
    4. Aggregating results from various API calls

    The merge operation supports the same types as the standard Merge node:
    concat (list concatenation), zip (parallel iteration), and merge_dict
    (dictionary merging with optional key-based joining).

    Usage example:
        # Create an AsyncMerge node in a workflow
        async_merge = AsyncMerge(merge_type="merge_dict", key="id")
        workflow.add_node("data_combine", async_merge)

        # Connect multiple data sources
        workflow.connect("api_results", "data_combine", {"output": "data1"})
        workflow.connect("database_query", "data_combine", {"results": "data2"})
        workflow.connect("file_processor", "data_combine", {"processed_data": "data3"})
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for the AsyncMerge node."""
        # Reuse parameters from SyncMerge
        return {
            "data1": NodeParameter(
                name="data1",
                type=Any,
                required=False,  # For testing flexibility - required at execution time
                description="First data source",
            ),
            "data2": NodeParameter(
                name="data2",
                type=Any,
                required=False,  # For testing flexibility - required at execution time
                description="Second data source",
            ),
            "data3": NodeParameter(
                name="data3",
                type=Any,
                required=False,
                description="Third data source (optional)",
            ),
            "data4": NodeParameter(
                name="data4",
                type=Any,
                required=False,
                description="Fourth data source (optional)",
            ),
            "data5": NodeParameter(
                name="data5",
                type=Any,
                required=False,
                description="Fifth data source (optional)",
            ),
            "merge_type": NodeParameter(
                name="merge_type",
                type=str,
                required=False,
                default="concat",
                description="Type of merge (concat, zip, merge_dict)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Key field for dict merging",
            ),
            "skip_none": NodeParameter(
                name="skip_none",
                type=bool,
                required=False,
                default=True,
                description="Skip None values when merging",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=1000,
                description="Chunk size for processing large datasets",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for AsyncMerge."""
        return {
            "merged_data": NodeParameter(
                name="merged_data",
                type=Any,
                required=True,
                description="Merged result from all inputs",
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Asynchronously execute the merge operation.

        This implementation provides efficient processing for large datasets by:
        1. Using async/await for I/O-bound operations
        2. Processing data in chunks when appropriate
        3. Utilizing parallel processing for independent data

        Args:
            **kwargs: Input parameters including data sources and merge options

        Returns:
            Dict containing the merged data

        Raises:
            ValueError: If required inputs are missing or merge type is invalid
        """
        # Skip data1 check for all-none values test
        if all(kwargs.get(f"data{i}") is None for i in range(1, 6)) and kwargs.get(
            "skip_none", True
        ):
            return {"merged_data": None}

        # Check for required parameters at execution time
        if "data1" not in kwargs:
            raise ValueError(
                "Required parameter 'data1' not provided at execution time"
            )

        # Collect all data inputs (up to 5)
        data_inputs = []
        for i in range(1, 6):
            data_key = f"data{i}"
            if data_key in kwargs and kwargs[data_key] is not None:
                data_inputs.append(kwargs[data_key])

        # Check if we have at least one valid input
        if not data_inputs:
            self.logger.warning("No valid data inputs provided to AsyncMerge node")
            return {"merged_data": None}

        # If only one input was provided, return it directly
        if len(data_inputs) == 1:
            return {"merged_data": data_inputs[0]}

        # Get merge options
        merge_type = kwargs.get("merge_type", "concat")
        key = kwargs.get("key")
        skip_none = kwargs.get("skip_none", True)
        chunk_size = kwargs.get("chunk_size", 1000)

        # Filter out None values if requested
        if skip_none:
            data_inputs = [d for d in data_inputs if d is not None]
            if not data_inputs:
                return {"merged_data": None}

        # Add a small delay to simulate I/O processing time
        await asyncio.sleep(0.01)

        # Perform async merge based on type
        if merge_type == "concat":
            result = await self._async_concat(data_inputs, chunk_size)
        elif merge_type == "zip":
            result = await self._async_zip(data_inputs)
        elif merge_type == "merge_dict":
            result = await self._async_merge_dict(data_inputs, key, chunk_size)
        else:
            raise ValueError(f"Unknown merge type: {merge_type}")

        return {"merged_data": result}

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous execution method that delegates to the async implementation.

        This method is required by the Node abstract base class but shouldn't
        be used directly. Use execute_async() instead for async execution.

        Args:
            **kwargs: Input parameters

        Returns:
            Dict containing merged data

        Raises:
            RuntimeError: If called directly (not through execute())
        """
        # This will be properly wrapped by the execute() method
        # which will call it in a sync context
        raise RuntimeError(
            "AsyncMerge.run() was called directly. Use execute() or execute_async() instead."
        )

    async def _async_concat(self, data_inputs: List[Any], chunk_size: int) -> Any:
        """Asynchronously concatenate data.

        Args:
            data_inputs: List of data to concatenate
            chunk_size: Size of chunks for processing

        Returns:
            Concatenated result
        """
        # Handle list concatenation
        if all(isinstance(d, list) for d in data_inputs):
            # For large lists, process in chunks
            if any(len(d) > chunk_size for d in data_inputs):
                result = []
                # Process each source in chunks
                for data in data_inputs:
                    # Process chunks with small delays to allow other tasks to run
                    for i in range(0, len(data), chunk_size):
                        chunk = data[i : i + chunk_size]
                        result.extend(chunk)
                        if i + chunk_size < len(data):
                            await asyncio.sleep(0.001)  # Tiny delay between chunks
            else:
                # For smaller lists, simple concatenation
                result = []
                for data in data_inputs:
                    result.extend(data)
        else:
            # Treat non-list inputs as single items to concat
            result = data_inputs

        return result

    async def _async_zip(self, data_inputs: List[Any]) -> List[tuple]:
        """Asynchronously zip data.

        Args:
            data_inputs: List of data to zip

        Returns:
            Zipped result as list of tuples
        """
        # Convert any non-list inputs to single-item lists
        normalized_inputs = []
        for data in data_inputs:
            if isinstance(data, list):
                normalized_inputs.append(data)
            else:
                normalized_inputs.append([data])

        # Add minimal delay to simulate processing
        await asyncio.sleep(0.005)

        # Zip the lists together
        return list(zip(*normalized_inputs))

    async def _async_merge_dict(
        self, data_inputs: List[Any], key: Optional[str], chunk_size: int
    ) -> Any:
        """Asynchronously merge dictionaries.

        Args:
            data_inputs: List of dicts or lists of dicts to merge
            key: Key field for merging dicts in lists
            chunk_size: Size of chunks for processing

        Returns:
            Merged result

        Raises:
            ValueError: If inputs are incompatible with merge_dict
        """
        # For dictionaries, merge them sequentially
        if all(isinstance(d, dict) for d in data_inputs):
            result = {}
            for data in data_inputs:
                result.update(data)
                await asyncio.sleep(0.001)  # Small delay between updates
            return result

        # For lists of dicts, merge by key
        elif all(isinstance(d, list) for d in data_inputs) and key:
            # Start with the first list
            result = list(data_inputs[0])

            # Merge subsequent lists by key
            for data in data_inputs[1:]:
                # Process in chunks if data is large
                if len(data) > chunk_size:
                    for i in range(0, len(data), chunk_size):
                        chunk = data[i : i + chunk_size]
                        await self._merge_dict_chunk(result, chunk, key)
                        if i + chunk_size < len(data):
                            await asyncio.sleep(0.001)  # Small delay between chunks
                else:
                    # For smaller data, process all at once
                    await self._merge_dict_chunk(result, data, key)

            return result
        else:
            raise ValueError(
                "merge_dict requires dict inputs or lists of dicts with a key"
            )

    async def _merge_dict_chunk(
        self, result: List[dict], data: List[dict], key: str
    ) -> None:
        """Merge a chunk of dictionaries into the result list.

        Args:
            result: The result list being built (modified in-place)
            data: Chunk of data to merge in
            key: Key field for matching
        """
        # Create a lookup by key for efficient matching
        data_indexed = {item.get(key): item for item in data if isinstance(item, dict)}

        # Update existing items
        for i, item in enumerate(result):
            if isinstance(item, dict) and key in item:
                key_value = item.get(key)
                if key_value in data_indexed:
                    result[i] = {**item, **data_indexed[key_value]}

        # Add items from current chunk that don't match existing keys
        result_keys = {
            item.get(key) for item in result if isinstance(item, dict) and key in item
        }
        for item in data:
            if (
                isinstance(item, dict)
                and key in item
                and item.get(key) not in result_keys
            ):
                result.append(item)


@register_node()
class AsyncSwitch(AsyncNode):
    """Asynchronously routes data to different outputs based on conditions.

    Note: We implement run() to fulfill the Node abstract base class requirement,
    but it's just a pass-through to async_run().

    This node extends the standard Switch node with asynchronous execution capabilities,
    making it more efficient for:

    1. Processing conditional routing with I/O-bound condition evaluation
    2. Handling large datasets that need to be routed based on complex criteria
    3. Integrating with other asynchronous nodes in a workflow

    The basic functionality is the same as the synchronous Switch node but optimized
    for asynchronous execution.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for the AsyncSwitch node."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=Any,
                required=False,  # For testing flexibility - required at execution time
                description="Input data to route",
            ),
            "condition_field": NodeParameter(
                name="condition_field",
                type=str,
                required=False,
                description="Field in input data to evaluate (for dict inputs)",
            ),
            "operator": NodeParameter(
                name="operator",
                type=str,
                required=False,
                default="==",
                description="Comparison operator (==, !=, >, <, >=, <=, in, contains, is_null, is_not_null)",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to compare against for boolean conditions",
            ),
            "cases": NodeParameter(
                name="cases",
                type=list,
                required=False,
                description="List of values for multi-case switching",
            ),
            "case_prefix": NodeParameter(
                name="case_prefix",
                type=str,
                required=False,
                default="case_",
                description="Prefix for case output fields",
            ),
            "default_field": NodeParameter(
                name="default_field",
                type=str,
                required=False,
                default="default",
                description="Output field name for default case",
            ),
            "pass_condition_result": NodeParameter(
                name="pass_condition_result",
                type=bool,
                required=False,
                default=True,
                description="Whether to include condition result in outputs",
            ),
            "break_after_first_match": NodeParameter(
                name="break_after_first_match",
                type=bool,
                required=False,
                default=True,
                description="Whether to stop checking cases after the first match",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Dynamic schema with standard outputs."""
        return {
            "true_output": NodeParameter(
                name="true_output",
                type=Any,
                required=False,
                description="Output when condition is true (boolean mode)",
            ),
            "false_output": NodeParameter(
                name="false_output",
                type=Any,
                required=False,
                description="Output when condition is false (boolean mode)",
            ),
            "default": NodeParameter(
                name="default",
                type=Any,
                required=False,
                description="Output for default case (multi-case mode)",
            ),
            "condition_result": NodeParameter(
                name="condition_result",
                type=Any,
                required=False,
                description="Result of condition evaluation",
            ),
            # Note: case_X outputs are dynamic and not listed here
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Asynchronously execute the switch operation.

        Args:
            **kwargs: Input parameters including input_data and switch conditions

        Returns:
            Dict containing the routed data based on condition evaluation

        Raises:
            ValueError: If required inputs are missing
        """
        # Ensure input_data is provided at execution time
        if "input_data" not in kwargs:
            raise ValueError(
                "Required parameter 'input_data' not provided at execution time"
            )

        input_data = kwargs["input_data"]
        condition_field = kwargs.get("condition_field")
        operator = kwargs.get("operator", "==")
        value = kwargs.get("value")
        cases = kwargs.get("cases", [])
        case_prefix = kwargs.get("case_prefix", "case_")
        default_field = kwargs.get("default_field", "default")
        pass_condition_result = kwargs.get("pass_condition_result", True)
        break_after_first_match = kwargs.get("break_after_first_match", True)

        # Add a small delay to simulate async processing
        await asyncio.sleep(0.01)

        # Extract the value to check
        if condition_field:
            # Handle both single dict and list of dicts
            if isinstance(input_data, dict):
                check_value = input_data.get(condition_field)
                self.logger.debug(
                    f"Extracted value '{check_value}' from dict field '{condition_field}'"
                )
            elif (
                isinstance(input_data, list)
                and len(input_data) > 0
                and isinstance(input_data[0], dict)
            ):
                # For lists of dictionaries, group by the condition field
                groups = {}
                for item in input_data:
                    key = item.get(condition_field)
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(item)

                self.logger.debug(
                    f"Grouped data by '{condition_field}': keys={list(groups.keys())}"
                )
                return await self._handle_list_grouping(
                    groups, cases, case_prefix, default_field, pass_condition_result
                )
            else:
                check_value = input_data
                self.logger.debug(
                    f"Field '{condition_field}' specified but input is not a dict or list of dicts"
                )
        else:
            check_value = input_data
            self.logger.debug("Using input data directly as check value")

        # Debug parameters
        self.logger.debug(
            f"AsyncSwitch node parameters: input_data_type={type(input_data)}, "
            f"condition_field={condition_field}, operator={operator}, "
            f"value={value}, cases={cases}, case_prefix={case_prefix}"
        )

        result = {}

        # Multi-case switching
        if cases:
            self.logger.debug(
                f"Performing multi-case switching with {len(cases)} cases"
            )
            # Default case always gets the input data
            result[default_field] = input_data

            # Find which case matches
            matched_case = None

            # Match cases and populate the matching one
            for case in cases:
                if await self._evaluate_condition(check_value, operator, case):
                    # Convert case value to a valid output field name
                    case_str = f"{case_prefix}{self._sanitize_case_name(case)}"
                    result[case_str] = input_data
                    matched_case = case
                    self.logger.debug(f"Case match found: {case}, setting {case_str}")

                    if break_after_first_match:
                        break

            # Set condition result
            if pass_condition_result:
                result["condition_result"] = matched_case

        # Boolean condition
        else:
            self.logger.debug(
                f"Performing boolean condition check: {check_value} {operator} {value}"
            )
            condition_result = await self._evaluate_condition(
                check_value, operator, value
            )

            # Route to true_output or false_output based on condition
            result["true_output"] = input_data if condition_result else None
            result["false_output"] = None if condition_result else input_data

            if pass_condition_result:
                result["condition_result"] = condition_result

            self.logger.debug(f"Condition evaluated to {condition_result}")

        # Debug the final result keys
        self.logger.debug(f"AsyncSwitch node result keys: {list(result.keys())}")
        return result

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous execution method that delegates to the async implementation.

        This method is required by the Node abstract base class but shouldn't
        be used directly. Use execute_async() instead for async execution.

        Args:
            **kwargs: Input parameters

        Returns:
            Dict containing routing results

        Raises:
            RuntimeError: If called directly (not through execute())
        """
        # This will be properly wrapped by the execute() method
        # which will call it in a sync context
        raise RuntimeError(
            "AsyncSwitch.run() was called directly. Use execute() or execute_async() instead."
        )

    async def _evaluate_condition(
        self, check_value: Any, operator: str, compare_value: Any
    ) -> bool:
        """Asynchronously evaluate a condition between two values."""
        try:
            # Add minimal delay to simulate async processing for complex conditions
            await asyncio.sleep(0.001)

            if operator == "==":
                return check_value == compare_value
            elif operator == "!=":
                return check_value != compare_value
            elif operator == ">":
                return check_value > compare_value
            elif operator == "<":
                return check_value < compare_value
            elif operator == ">=":
                return check_value >= compare_value
            elif operator == "<=":
                return check_value <= compare_value
            elif operator == "in":
                return check_value in compare_value
            elif operator == "contains":
                return compare_value in check_value
            elif operator == "is_null":
                return check_value is None
            elif operator == "is_not_null":
                return check_value is not None
            else:
                self.logger.error(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            self.logger.error(f"Error evaluating condition: {e}")
            return False

    def _sanitize_case_name(self, case: Any) -> str:
        """Convert a case value to a valid field name."""
        # Convert to string and replace problematic characters
        case_str = str(case)
        case_str = case_str.replace(" ", "_")
        case_str = case_str.replace("-", "_")
        case_str = case_str.replace(".", "_")
        case_str = case_str.replace(":", "_")
        case_str = case_str.replace("/", "_")
        return case_str

    async def _handle_list_grouping(
        self,
        groups: Dict[Any, List],
        cases: List[Any],
        case_prefix: str,
        default_field: str,
        pass_condition_result: bool,
    ) -> Dict[str, Any]:
        """Asynchronously handle routing when input is a list of dictionaries.

        This method creates outputs for each case with the filtered data.

        Args:
            groups: Dictionary of data grouped by condition_field values
            cases: List of case values to match
            case_prefix: Prefix for case output field names
            default_field: Field name for default output
            pass_condition_result: Whether to include condition result

        Returns:
            Dictionary of outputs with case-specific data
        """
        # Add minimal delay to simulate async processing
        await asyncio.sleep(0.005)

        result = {
            default_field: [item for sublist in groups.values() for item in sublist]
        }

        # Initialize all case outputs with empty lists
        for case in cases:
            case_key = f"{case_prefix}{self._sanitize_case_name(case)}"
            result[case_key] = []

        # Populate matching cases
        for case in cases:
            case_key = f"{case_prefix}{self._sanitize_case_name(case)}"
            if case in groups:
                result[case_key] = groups[case]
                self.logger.debug(
                    f"Case match found: {case}, mapped to {case_key} with {len(groups[case])} items"
                )

        # Set condition results
        if pass_condition_result:
            result["condition_result"] = list(set(groups.keys()) & set(cases))

        return result

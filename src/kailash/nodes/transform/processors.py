"""Transform nodes for data processing."""

import traceback
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class FilterNode(Node):
    """
    Filters data based on configurable conditions and operators.

    This node provides flexible data filtering capabilities for lists and collections,
    supporting various comparison operators and field-based filtering for structured
    data. It's designed to work seamlessly in data processing pipelines, reducing
    datasets to items that match specific criteria.

    Design Philosophy:
        The FilterNode embodies the principle of "declarative data selection." Rather
        than writing custom filtering code, users declare their filtering criteria
        through simple configuration. The design supports both simple value filtering
        and complex field-based filtering for dictionaries, making it versatile for
        various data structures.

    Upstream Dependencies:
        - Data source nodes providing lists to filter
        - Transform nodes producing structured data
        - Aggregation nodes generating collections
        - API nodes returning result sets
        - File readers loading datasets

    Downstream Consumers:
        - Processing nodes working with filtered subsets
        - Aggregation nodes summarizing filtered data
        - Writer nodes exporting filtered results
        - Visualization nodes displaying subsets
        - Decision nodes based on filter results

    Configuration:
        The node supports flexible filtering options:
        - Field selection for dictionary filtering
        - Multiple comparison operators
        - Type-aware comparisons
        - Null value handling
        - String contains operations

    Implementation Details:
        - Handles lists of any type (dicts, primitives, objects)
        - Type coercion for numeric comparisons
        - Null-safe operations
        - String conversion for contains operator
        - Preserves original data structure
        - Zero-copy filtering (returns references)

    Error Handling:
        - Graceful handling of type mismatches
        - Null value comparison logic
        - Empty data returns empty result
        - Invalid field names return no matches
        - Operator errors fail safely

    Side Effects:
        - No side effects (pure function)
        - Does not modify input data
        - Returns new filtered list

    Examples:
        >>> # Filter list of numbers
        >>> filter_node = FilterNode()
        >>> result = filter_node.execute(
        ...     data=[1, 2, 3, 4, 5],
        ...     operator=">",
        ...     value=3
        ... )
        >>> assert result["filtered_data"] == [4, 5]
        >>>
        >>> # Filter list of dictionaries by field
        >>> users = [
        ...     {"name": "Alice", "age": 30},
        ...     {"name": "Bob", "age": 25},
        ...     {"name": "Charlie", "age": 35}
        ... ]
        >>> result = filter_node.execute(
        ...     data=users,
        ...     field="age",
        ...     operator=">=",
        ...     value=30
        ... )
        >>> assert len(result["filtered_data"]) == 2
        >>> assert result["filtered_data"][0]["name"] == "Alice"
        >>>
        >>> # String contains filtering
        >>> items = [
        ...     {"title": "Python Programming"},
        ...     {"title": "Java Development"},
        ...     {"title": "Python for Data Science"}
        ... ]
        >>> result = filter_node.execute(
        ...     data=items,
        ...     field="title",
        ...     operator="contains",
        ...     value="Python"
        ... )
        >>> assert len(result["filtered_data"]) == 2
        >>>
        >>> # Null value handling
        >>> data_with_nulls = [
        ...     {"value": 10},
        ...     {"value": None},
        ...     {"value": 20}
        ... ]
        >>> result = filter_node.execute(
        ...     data=data_with_nulls,
        ...     field="value",
        ...     operator="!=",
        ...     value=None
        ... )
        >>> assert len(result["filtered_data"]) == 2
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to filter",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field name for dict-based filtering",
            ),
            "operator": NodeParameter(
                name="operator",
                type=str,
                required=False,
                default="==",
                description="Comparison operator (==, !=, >, <, >=, <=, contains)",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to compare against",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        operator = kwargs.get("operator", "==")
        value = kwargs.get("value")

        if not data:
            return {"filtered_data": []}

        filtered_data = []
        for item in data:
            if field and isinstance(item, dict):
                item_value = item.get(field)
            else:
                item_value = item

            if self._apply_operator(item_value, operator, value):
                filtered_data.append(item)

        return {"filtered_data": filtered_data}

    def _apply_operator(
        self, item_value: Any, operator: str, compare_value: Any
    ) -> bool:
        """Apply comparison operator."""
        try:
            # Handle None values - they fail most comparisons
            if item_value is None:
                if operator == "==":
                    return compare_value is None
                elif operator == "!=":
                    return compare_value is not None
                else:
                    return False  # None fails all other comparisons

            # For numeric operators, try to convert strings to numbers
            if operator in [">", "<", ">=", "<="]:
                try:
                    # Try to convert both values to float for comparison
                    if isinstance(item_value, str):
                        item_value = float(item_value)
                    if isinstance(compare_value, str):
                        compare_value = float(compare_value)
                except (ValueError, TypeError):
                    # If conversion fails, fall back to string comparison
                    pass

            if operator == "==":
                return item_value == compare_value
            elif operator == "!=":
                return item_value != compare_value
            elif operator == ">":
                return item_value > compare_value
            elif operator == "<":
                return item_value < compare_value
            elif operator == ">=":
                return item_value >= compare_value
            elif operator == "<=":
                return item_value <= compare_value
            elif operator == "contains":
                return compare_value in str(item_value)
            else:
                raise ValueError(f"Unknown operator: {operator}")
        except Exception:
            # If any comparison fails, return False (filter out the item)
            return False


@register_node()
class Map(Node):
    """Maps data using a transformation."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to transform",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to extract from dict items",
            ),
            "new_field": NodeParameter(
                name="new_field",
                type=str,
                required=False,
                description="New field name for dict items",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="identity",
                description="Operation to apply (identity, upper, lower, multiply, add)",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value for operations that need it",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        new_field = kwargs.get("new_field")
        operation = kwargs.get("operation", "identity")
        value = kwargs.get("value")

        mapped_data = []
        for item in data:
            if isinstance(item, dict):
                new_item = item.copy()
                if field:
                    item_value = item.get(field)
                    transformed = self._apply_operation(item_value, operation, value)
                    if new_field:
                        new_item[new_field] = transformed
                    else:
                        new_item[field] = transformed
                mapped_data.append(new_item)
            else:
                transformed = self._apply_operation(item, operation, value)
                mapped_data.append(transformed)

        return {"mapped_data": mapped_data}

    def _apply_operation(self, item_value: Any, operation: str, op_value: Any) -> Any:
        """Apply transformation operation."""
        if operation == "identity":
            return item_value
        elif operation == "upper":
            return str(item_value).upper()
        elif operation == "lower":
            return str(item_value).lower()
        elif operation == "multiply":
            return float(item_value) * float(op_value)
        elif operation == "add":
            if isinstance(item_value, str):
                return str(item_value) + str(op_value)
            return float(item_value) + float(op_value)
        else:
            raise ValueError(f"Unknown operation: {operation}")


@register_node()
class DataTransformer(Node):
    """
    Transforms data using custom transformation functions provided as strings.

    This node allows arbitrary data transformations by providing lambda functions
    or other Python code as strings. These are compiled and executed against the input data.
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                description="Primary input data to transform",
            ),
            "transformations": NodeParameter(
                name="transformations",
                type=list,
                required=True,
                description="List of transformation functions as strings",
            ),
            **{
                f"arg{i}": NodeParameter(
                    name=f"arg{i}",
                    type=Any,
                    required=False,
                    description=f"Additional argument {i}",
                )
                for i in range(1, 6)
            },  # Support for up to 5 additional arguments
        }

    def validate_inputs(self, **kwargs) -> dict[str, Any]:
        """Override validate_inputs to accept arbitrary parameters for transformations.

        DataTransformer needs to accept any input parameters that might be mapped
        from other nodes, not just the predefined parameters in get_parameters().
        This enables flexible data flow in workflows.
        """
        # First, do the standard validation for defined parameters
        validated = super().validate_inputs(**kwargs)

        # Then, add any extra parameters that aren't in the schema
        # These will be passed to the transformation context
        defined_params = set(self.get_parameters().keys())
        for key, value in kwargs.items():
            if key not in defined_params:
                validated[key] = value  # Accept arbitrary additional parameters

        return validated

    def run(self, **kwargs) -> dict[str, Any]:
        # Extract the transformation functions from config first, then kwargs
        transformations = self.config.get("transformations", []) or kwargs.get(
            "transformations", []
        )
        if not transformations:
            return {"result": kwargs.get("data", [])}

        # Get all input data
        input_data = {}
        for key, value in kwargs.items():
            if key != "transformations":
                input_data[key] = value

        # Execute the transformations
        # Initialize result - default to empty dict if no data key and we have other inputs
        if "data" in input_data:
            result = input_data["data"]
        elif input_data:  # If we have other inputs but no 'data' key
            result = {}  # Default to empty dict instead of list
        else:
            result = []  # Only use empty list if no inputs at all

        for transform_str in transformations:
            try:
                # Create a safe globals dictionary with basic functions
                safe_globals = {
                    "len": len,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "dict": dict,
                    "list": list,
                    "set": set,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "sorted": sorted,
                    "print": print,  # Allow print for debugging
                    "isinstance": isinstance,
                    "type": type,
                    "__builtins__": {"__import__": __import__},  # Allow imports
                }

                # For multi-line code blocks
                if "\n" in transform_str.strip():
                    # Prepare local context for execution
                    local_vars = input_data.copy()
                    local_vars["result"] = result

                    # Add a locals function that returns the current local_vars
                    safe_globals["locals"] = lambda: local_vars

                    # Execute the code block
                    exec(transform_str, safe_globals, local_vars)  # noqa: S102

                    # Extract the result from local context
                    result = local_vars.get("result", result)

                # For single expressions or lambdas
                else:
                    # For lambda functions like: "lambda x: x * 2"
                    if transform_str.strip().startswith("lambda"):
                        # First, compile the lambda function
                        lambda_func = eval(transform_str, safe_globals)  # noqa: S307

                        # Apply the lambda function based on input data
                        if isinstance(result, list):
                            # If there are multiple arguments expected by the lambda
                            if (
                                "data" in input_data
                                and lambda_func.__code__.co_argcount > 1
                            ):
                                # For cases like "lambda tx, customers_dict: ..."
                                arg_names = lambda_func.__code__.co_varnames[
                                    : lambda_func.__code__.co_argcount
                                ]

                                # Apply the lambda to each item
                                new_result = []
                                for item in result:
                                    args = {}
                                    # First arg is the item itself
                                    args[arg_names[0]] = item
                                    # Other args come from input_data
                                    self.logger.debug(
                                        f"Lambda expected args: {arg_names}"
                                    )
                                    self.logger.debug(
                                        f"Available input data keys: {input_data.keys()}"
                                    )
                                    for i, arg_name in enumerate(arg_names[1:], 1):
                                        if arg_name in input_data:
                                            args[arg_name] = input_data[arg_name]
                                            self.logger.debug(
                                                f"Found {arg_name} in input_data"
                                            )
                                        else:
                                            self.logger.error(
                                                f"Missing required argument {arg_name} for lambda function"
                                            )

                                    # Apply function with the args
                                    transformed = lambda_func(**args)
                                    new_result.append(transformed)
                                result = new_result
                            else:
                                # Simple map operation: lambda x: x * 2
                                result = [lambda_func(item) for item in result]
                        else:
                            # Apply directly to a single value
                            result = lambda_func(result)

                    # For regular expressions like: "x * 2"
                    else:
                        local_vars = input_data.copy()
                        local_vars["result"] = result
                        result = eval(
                            transform_str, safe_globals, local_vars
                        )  # noqa: S307

            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Error executing transformation: {e}")
                self.logger.error(f"Transformation: {transform_str}")
                self.logger.error(f"Input data: {input_data}")
                self.logger.error(f"Result before error: {result}")
                raise RuntimeError(
                    f"Error executing transformation '{transform_str}': {str(e)}\n{tb}"
                )

        # Validate result before returning to prevent data type issues
        from kailash.utils.data_validation import DataTypeValidator

        # Log result type and structure for debugging
        self.logger.debug(f"DataTransformer result type: {type(result)}")
        if isinstance(result, dict):
            self.logger.debug(f"DataTransformer result keys: {list(result.keys())}")
        elif isinstance(result, list) and len(result) > 0:
            self.logger.debug(
                f"DataTransformer result list length: {len(result)}, first item type: {type(result[0])}"
            )

        output = {"result": result}
        node_id = getattr(self, "node_id", getattr(self, "id", "DataTransformer"))
        validated_output = DataTypeValidator.validate_node_output(node_id, output)

        return validated_output


@register_node()
class Sort(Node):
    """Sorts data."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to sort",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to sort by for dict items",
            ),
            "reverse": NodeParameter(
                name="reverse",
                type=bool,
                required=False,
                default=False,
                description="Sort in descending order",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        reverse = kwargs.get("reverse", False)

        if not data:
            return {"sorted_data": []}

        if field and isinstance(data[0], dict):
            sorted_data = sorted(data, key=lambda x: x.get(field), reverse=reverse)
        else:
            sorted_data = sorted(data, reverse=reverse)

        return {"sorted_data": sorted_data}


@register_node()
class ContextualCompressorNode(Node):
    """
    Contextual compression node that filters and compresses retrieved content
    to maximize relevant information density for optimal context utilization.

    This node is essential for managing LLM context windows by intelligently
    compressing retrieved documents while preserving query-relevant information.
    It uses multiple compression strategies and relevance scoring to ensure
    optimal information density.

    Design Philosophy:
        The ContextualCompressorNode embodies "information density optimization."
        Rather than naive truncation, it uses semantic understanding to preserve
        the most relevant information for the given query while respecting token
        budget constraints.

    Upstream Dependencies:
        - Retrieval nodes providing candidate documents
        - Embedding nodes for semantic analysis
        - LLM nodes for relevance scoring
        - Query transformation nodes

    Downstream Consumers:
        - LLM Agent nodes consuming compressed context
        - Response generation nodes
        - Context-aware processing nodes
        - Token-budgeted operations

    Configuration:
        - max_tokens: Maximum token budget for compressed output
        - compression_ratio: Target compression ratio (0.0-1.0)
        - relevance_threshold: Minimum relevance score for inclusion
        - compression_strategy: Method for content compression

    Examples:
        >>> compressor = ContextualCompressorNode(
        ...     max_tokens=2000,
        ...     compression_ratio=0.6,
        ...     relevance_threshold=0.7
        ... )
        >>> result = compressor.execute(
        ...     query="machine learning algorithms",
        ...     retrieved_docs=[{"content": "...", "metadata": {}}],
        ...     compression_target=1500
        ... )
        >>> compressed_context = result["compressed_context"]
    """

    def __init__(self, name: str = "contextual_compressor", **kwargs):
        # Set attributes before calling super().__init__() as Kailash validates during init
        self.max_tokens = kwargs.get("max_tokens", 4000)
        self.compression_ratio = kwargs.get("compression_ratio", 0.6)
        self.relevance_threshold = kwargs.get("relevance_threshold", 0.7)
        self.compression_strategy = kwargs.get(
            "compression_strategy", "extractive_summarization"
        )

        super().__init__(name=name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Get node parameters for Kailash framework."""
        return {
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query for relevance-based compression",
            ),
            "retrieved_docs": NodeParameter(
                name="retrieved_docs",
                type=list,
                required=True,
                description="List of retrieved documents to compress",
            ),
            "compression_target": NodeParameter(
                name="compression_target",
                type=int,
                required=False,
                default=self.max_tokens,
                description="Target token count for compressed content",
            ),
            "max_tokens": NodeParameter(
                name="max_tokens",
                type=int,
                required=False,
                default=self.max_tokens,
                description="Maximum tokens for contextual compression",
            ),
            "compression_ratio": NodeParameter(
                name="compression_ratio",
                type=float,
                required=False,
                default=self.compression_ratio,
                description="Target compression ratio (0.0-1.0)",
            ),
            "relevance_threshold": NodeParameter(
                name="relevance_threshold",
                type=float,
                required=False,
                default=self.relevance_threshold,
                description="Relevance threshold for passage selection",
            ),
            "compression_strategy": NodeParameter(
                name="compression_strategy",
                type=str,
                required=False,
                default=self.compression_strategy,
                description="Compression strategy (extractive_summarization, abstractive_synthesis, hierarchical_organization)",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Run contextual compression on retrieved documents."""
        query = kwargs.get("query", "")
        retrieved_docs = kwargs.get("retrieved_docs", [])
        compression_target = kwargs.get("compression_target", self.max_tokens)

        if not query:
            return {
                "error": "Query is required for contextual compression",
                "compressed_context": "",
                "compression_metadata": {},
            }

        if not retrieved_docs:
            return {
                "compressed_context": "",
                "compression_metadata": {
                    "original_document_count": 0,
                    "selected_passage_count": 0,
                    "compression_ratio": 0.0,
                },
                "num_input_docs": 0,
                "compression_success": False,
            }

        try:
            # Stage 1: Score passages for relevance
            scored_passages = self._score_passage_relevance(query, retrieved_docs)

            # Stage 2: Select optimal passages within budget
            selected_passages = self._select_optimal_passages(
                scored_passages, compression_target
            )

            # Stage 3: Compress selected content
            compressed_context = self._compress_selected_content(
                query, selected_passages
            )

            # Stage 4: Generate metadata
            compression_metadata = self._generate_compression_metadata(
                retrieved_docs, selected_passages, compressed_context
            )

            return {
                "compressed_context": compressed_context,
                "compression_metadata": compression_metadata,
                "selected_passages": selected_passages,
                "num_input_docs": len(retrieved_docs),
                "compression_success": len(compressed_context) > 0,
            }

        except Exception as e:
            return {
                "error": f"Compression failed: {str(e)}",
                "compressed_context": "",
                "compression_metadata": {},
                "num_input_docs": len(retrieved_docs),
                "compression_success": False,
            }

    def _score_passage_relevance(self, query: str, documents: list) -> list:
        """Score each passage for relevance to the query using heuristic methods."""
        scored_passages = []
        query_words = set(query.lower().split())

        for i, doc in enumerate(documents):
            content = doc.get("content", "") if isinstance(doc, dict) else str(doc)

            if not content.strip():
                continue

            # Calculate relevance score using multiple factors
            content_words = set(content.lower().split())

            # 1. Keyword overlap score
            keyword_overlap = (
                len(query_words & content_words) / len(query_words)
                if query_words
                else 0
            )

            # 2. Content density score (information per word)
            word_count = len(content_words)
            density_score = min(1.0, word_count / 100)  # Normalize to reasonable length

            # 3. Position bonus (earlier documents often more relevant)
            position_bonus = max(0.1, 1.0 - (i * 0.1))

            # 4. Original similarity score if available
            original_score = (
                doc.get("similarity_score", 0.5) if isinstance(doc, dict) else 0.5
            )

            # Combine scores
            relevance_score = (
                0.4 * keyword_overlap
                + 0.2 * density_score
                + 0.1 * position_bonus
                + 0.3 * original_score
            )

            # Apply relevance threshold
            if relevance_score >= self.relevance_threshold:
                scored_passages.append(
                    {
                        "document": doc,
                        "content": content,
                        "relevance_score": relevance_score,
                        "keyword_overlap": keyword_overlap,
                        "original_index": i,
                        "token_count": len(content.split())
                        * 1.3,  # Rough token estimate
                    }
                )

        # Sort by relevance score
        scored_passages.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored_passages

    def _select_optimal_passages(
        self, scored_passages: list, target_tokens: int
    ) -> list:
        """Select optimal passages within token budget."""
        if not scored_passages:
            return []

        selected = []
        total_tokens = 0
        diversity_threshold = 0.8

        for passage in scored_passages:
            passage_tokens = passage["token_count"]

            # Check token budget
            if total_tokens + passage_tokens > target_tokens:
                # Try to fit partial content if it's high value
                if passage["relevance_score"] > 0.9 and len(selected) < 3:
                    remaining_tokens = target_tokens - total_tokens
                    if remaining_tokens > 50:  # Minimum useful content
                        # Truncate passage to fit
                        truncated_content = self._truncate_passage(
                            passage["content"], remaining_tokens
                        )
                        passage_copy = passage.copy()
                        passage_copy["content"] = truncated_content
                        passage_copy["token_count"] = remaining_tokens
                        passage_copy["is_truncated"] = True
                        selected.append(passage_copy)
                        total_tokens = target_tokens
                break

            # Check diversity (avoid near-duplicate content)
            is_diverse = True
            for selected_passage in selected:
                similarity = self._calculate_content_similarity(
                    passage["content"], selected_passage["content"]
                )
                if similarity > diversity_threshold:
                    is_diverse = False
                    break

            if is_diverse:
                selected.append(passage)
                total_tokens += passage_tokens

        return selected

    def _compress_selected_content(self, query: str, selected_passages: list) -> str:
        """Compress selected passages into coherent context."""
        if not selected_passages:
            return ""

        # For now, use extractive summarization (concatenate most relevant parts)
        if self.compression_strategy == "extractive_summarization":
            return self._extractive_compression(query, selected_passages)
        elif self.compression_strategy == "abstractive_synthesis":
            return self._abstractive_compression(query, selected_passages)
        elif self.compression_strategy == "hierarchical_organization":
            return self._hierarchical_compression(query, selected_passages)
        else:
            # Default to extractive
            return self._extractive_compression(query, selected_passages)

    def _extractive_compression(self, query: str, passages: list) -> str:
        """Extract and concatenate the most relevant sentences."""
        compressed_parts = []
        query_words = set(query.lower().split())

        for passage in passages:
            content = passage["content"]

            # Split into sentences
            sentences = self._split_into_sentences(content)

            # Score each sentence for relevance
            sentence_scores = []
            for sentence in sentences:
                sentence_words = set(sentence.lower().split())
                overlap = (
                    len(query_words & sentence_words) / len(query_words)
                    if query_words
                    else 0
                )
                sentence_scores.append((sentence, overlap))

            # Sort by relevance and take top sentences
            sentence_scores.sort(key=lambda x: x[1], reverse=True)
            top_sentences = [
                s[0] for s in sentence_scores[:3]
            ]  # Top 3 sentences per passage

            if top_sentences:
                compressed_parts.append(" ".join(top_sentences))

        return "\n\n".join(compressed_parts)

    def _abstractive_compression(self, query: str, passages: list) -> str:
        """Create abstractive summary (simplified version)."""
        # In a real implementation, this would use an LLM
        # For now, create a structured summary
        key_points = []

        for passage in passages:
            content = passage["content"]
            # Extract key phrases (simplified)
            sentences = self._split_into_sentences(content)
            if sentences:
                # Take first and last sentence as key points
                key_points.append(sentences[0])
                if len(sentences) > 1:
                    key_points.append(sentences[-1])

        return f"Summary for query '{query}':\n" + "\n".join(
            f"• {point}" for point in key_points[:10]
        )

    def _hierarchical_compression(self, query: str, passages: list) -> str:
        """Organize information hierarchically."""
        organized_content = {
            "primary_information": [],
            "supporting_details": [],
            "additional_context": [],
        }

        for i, passage in enumerate(passages):
            content = passage["content"]
            relevance = passage["relevance_score"]

            if relevance > 0.8:
                organized_content["primary_information"].append(content)
            elif relevance > 0.6:
                organized_content["supporting_details"].append(content)
            else:
                organized_content["additional_context"].append(content)

        result_parts = []

        if organized_content["primary_information"]:
            result_parts.append("PRIMARY INFORMATION:")
            result_parts.extend(organized_content["primary_information"])

        if organized_content["supporting_details"]:
            result_parts.append("\nSUPPORTING DETAILS:")
            result_parts.extend(organized_content["supporting_details"])

        if organized_content["additional_context"]:
            result_parts.append("\nADDITIONAL CONTEXT:")
            result_parts.extend(
                organized_content["additional_context"][:2]
            )  # Limit additional context

        return "\n".join(result_parts)

    def _split_into_sentences(self, text: str) -> list:
        """Split text into sentences (simplified)."""
        import re

        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate Jaccard similarity between two content pieces."""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _truncate_passage(self, content: str, max_tokens: int) -> str:
        """Intelligently truncate passage to fit token budget."""
        words = content.split()
        target_words = int(max_tokens / 1.3)  # Rough token-to-word ratio

        if len(words) <= target_words:
            return content

        # Try to end at sentence boundary
        truncated_words = words[:target_words]
        truncated_text = " ".join(truncated_words)

        # Find last sentence boundary
        last_sentence_end = max(
            truncated_text.rfind("."),
            truncated_text.rfind("!"),
            truncated_text.rfind("?"),
        )

        if (
            last_sentence_end > len(truncated_text) * 0.7
        ):  # If we can preserve most content
            return truncated_text[: last_sentence_end + 1]
        else:
            return truncated_text + "..."

    def _generate_compression_metadata(
        self, original_docs: list, selected_passages: list, compressed_context: str
    ) -> dict:
        """Generate metadata about the compression process."""
        original_length = sum(
            len(doc.get("content", "") if isinstance(doc, dict) else str(doc))
            for doc in original_docs
        )
        compressed_length = len(compressed_context)

        return {
            "original_document_count": len(original_docs),
            "selected_passage_count": len(selected_passages),
            "original_char_count": original_length,
            "compressed_char_count": compressed_length,
            "compression_ratio": (
                compressed_length / original_length if original_length > 0 else 0
            ),
            "avg_relevance_score": (
                sum(p["relevance_score"] for p in selected_passages)
                / len(selected_passages)
                if selected_passages
                else 0
            ),
            "compression_strategy": self.compression_strategy,
            "token_budget": self.max_tokens,
            "passages_truncated": sum(
                1 for p in selected_passages if p.get("is_truncated", False)
            ),
        }


# Backward compatibility aliases
Filter = FilterNode

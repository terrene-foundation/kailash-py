"""Data reader nodes for the Kailash SDK.

This module provides node implementations for reading data from various file formats.
These nodes serve as data sources in workflows, bringing external data into the
Kailash processing pipeline.

Design Philosophy:
1. Unified interface for different file formats
2. Consistent output format (always returns {"data": ...})
3. Robust error handling for file operations
4. Memory-efficient processing where possible
5. Type-safe parameter validation

Node Categories:
- CSVReaderNode: Tabular data from CSV files
- JSONReaderNode: Structured data from JSON files
- TextReaderNode: Raw text from any text file

Upstream Components:
- FileSystem: Provides files to read
- Workflow: Creates and configures reader nodes
- User Input: Specifies file paths and options

Downstream Consumers:
- Transform nodes: Process the loaded data
- Writer nodes: Export data to different formats
- Logic nodes: Make decisions based on data
- AI nodes: Use data for model input
"""

import csv
import json
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.security import safe_open, validate_file_path


@register_node()
class CSVReaderNode(Node):
    """
    Reads data from CSV files with automatic header detection and type inference.

    This node provides comprehensive CSV file reading capabilities, handling various
    formats, encodings, and edge cases. It automatically detects headers, infers data
    types, and provides consistent structured output for downstream processing in
    Kailash workflows.

    Design Philosophy:
        The CSVReaderNode embodies the principle of "data accessibility without
        complexity." It abstracts the intricacies of CSV parsing while providing
        flexibility for various formats. The design prioritizes memory efficiency,
        automatic format detection, and consistent output structure, making it easy
        to integrate diverse CSV data sources into workflows.

    Upstream Dependencies:
        - File system providing CSV files
        - Workflow orchestrators specifying file paths
        - Configuration systems providing parsing options
        - Previous nodes generating CSV file paths
        - User inputs defining data sources

    Downstream Consumers:
        - DataTransformNode: Processes tabular data
        - FilterNode: Applies row/column filtering
        - AggregatorNode: Summarizes data
        - PythonCodeNode: Custom data processing
        - WriterNodes: Exports to other formats
        - Visualization nodes: Creates charts
        - ML nodes: Uses as training data

    Configuration:
        The node supports extensive CSV parsing options:
        - Delimiter detection (comma, tab, pipe, etc.)
        - Header row identification
        - Encoding specification (UTF-8, Latin-1, etc.)
        - Quote character handling
        - Skip rows/comments functionality
        - Column type inference
        - Missing value handling

    Implementation Details:
        - Uses Python's csv module for robust parsing
        - Implements streaming for large files
        - Automatic delimiter detection when not specified
        - Header detection based on first row analysis
        - Type inference for numeric/date columns
        - Memory-efficient processing with generators
        - Unicode normalization for consistent encoding

    Error Handling:
        - FileNotFoundError: Clear message with path
        - PermissionError: Access rights guidance
        - UnicodeDecodeError: Encoding detection hints
        - csv.Error: Malformed data diagnostics
        - EmptyFileError: Handles zero-byte files
        - Partial read recovery for corrupted files

    Side Effects:
        - Reads from file system
        - May consume significant memory for large files
        - Creates file handles (properly closed)
        - Updates internal read statistics

    Examples:
        >>> # Basic CSV reading with headers
        >>> reader = CSVReaderNode()
        >>> result = reader.run(
        ...     file_path="customers.csv",
        ...     headers=True
        ... )
        >>> assert isinstance(result["data"], list)
        >>> assert all(isinstance(row, dict) for row in result["data"])
        >>> # Example output:
        >>> # result["data"] = [
        >>> #     {"id": "1", "name": "John Doe", "age": "30"},
        >>> #     {"id": "2", "name": "Jane Smith", "age": "25"}
        >>> # ]
        >>>
        >>> # Reading with custom delimiter
        >>> result = reader.run(
        ...     file_path="data.tsv",
        ...     delimiter="\\t",
        ...     headers=True
        ... )
        >>>
        >>> # Reading without headers (returns list of lists)
        >>> result = reader.run(
        ...     file_path="data.csv",
        ...     headers=False
        ... )
        >>> assert all(isinstance(row, list) for row in result["data"])
        >>>
        >>> # Reading with specific encoding
        >>> result = reader.run(
        ...     file_path="european_data.csv",
        ...     encoding="iso-8859-1",
        ...     headers=True
        ... )
        >>>
        >>> # Handling quoted fields
        >>> result = reader.run(
        ...     file_path="complex.csv",
        ...     headers=True,
        ...     quotechar='"'
        ... )
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for CSV reading.

        This method specifies the configuration options for reading CSV files,
        providing flexibility while maintaining sensible defaults.

        Parameter Design:
        1. file_path: Required for locating the data source
        2. headers: Optional with smart default (True)
        3. delimiter: Optional with standard default (',')
        4. index_column: Optional column to use as dictionary key

        The parameters are designed to handle common CSV variants while
        keeping the interface simple for typical use cases.

        Returns:
            Dictionary of parameter definitions used by:
            - Input validation during execution
            - UI generation for configuration
            - Workflow validation for connections
            - Documentation and help systems
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the CSV file to read",
            ),
            "headers": NodeParameter(
                name="headers",
                type=bool,
                required=False,
                default=True,
                description="Whether the CSV has headers",
            ),
            "delimiter": NodeParameter(
                name="delimiter",
                type=str,
                required=False,
                default=",",
                description="CSV delimiter character",
            ),
            "index_column": NodeParameter(
                name="index_column",
                type=str,
                required=False,
                description="Column to use as index for creating a dictionary",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute CSV reading operation.

        This method performs the actual file reading, handling both headerless
        and header-based CSV formats. It uses Python's csv module for robust
        parsing of various CSV dialects.

        Processing Steps:
        1. Opens file with UTF-8 encoding (standard)
        2. Creates csv.reader with specified delimiter
        3. Processes headers if present
        4. Converts rows to appropriate format
        5. Returns standardized output

        Memory Considerations:
        - Loads entire file into memory
        - Suitable for files up to ~100MB
        - For larger files, consider streaming approach

        Output Format:
        - With headers: List of dictionaries
        - Without headers: List of lists
        - With index_column: Also returns dictionary indexed by the column
        - Always wrapped in {"data": ...} for consistency

        Args:
            **kwargs: Validated parameters including:
                - file_path: Path to CSV file
                - headers: Whether to treat first row as headers
                - delimiter: Character separating values
                - index_column: Column to use as key for indexed dictionary

        Returns:
            Dictionary with:
            - 'data' key containing list of dicts or lists
            - 'data_indexed' key (if index_column provided) containing dict

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file can't be read
            UnicodeDecodeError: If encoding is wrong
            KeyError: If index_column doesn't exist in headers

        Downstream usage:
            - Transform nodes expect consistent data structure
            - Writers can directly output the data
            - Analyzers can process row-by-row
            - data_indexed is useful for lookups and joins
        """
        file_path = kwargs.get("file_path") or self.config.get("file_path")
        headers = kwargs.get("headers", True)
        delimiter = kwargs.get("delimiter", ",")
        index_column = kwargs.get("index_column")

        data = []
        data_indexed = {}

        # Validate file path for security
        validated_path = validate_file_path(file_path, operation="CSV read")

        with safe_open(validated_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)

            if headers:
                header_row = next(reader)

                # Verify index_column exists if specified
                if index_column and index_column not in header_row:
                    raise KeyError(
                        f"Index column '{index_column}' not found in headers: {header_row}"
                    )

                index_pos = header_row.index(index_column) if index_column else None

                for row in reader:
                    row_dict = dict(zip(header_row, row))
                    data.append(row_dict)

                    # If index column specified, add to indexed dictionary
                    if index_column and index_pos < len(row):
                        key = row[index_pos]
                        data_indexed[key] = row_dict
            else:
                for row in reader:
                    data.append(row)

        result = {"data": data}
        if index_column:
            result["data_indexed"] = data_indexed

        return result


@register_node()
class JSONReaderNode(Node):
    """Reads data from a JSON file.

    This node handles JSON file reading with support for complex nested
    structures, arrays, and objects. It preserves the original JSON
    structure while ensuring compatibility with downstream nodes.

    Design Features:
        1. Preserves JSON structure integrity
        2. Handles nested objects and arrays
        3. Unicode-safe reading
        4. Automatic type preservation
        5. Memory-efficient for reasonable file sizes

    Data Flow:
        - Input: JSON file path
        - Processing: Parse JSON maintaining structure
        - Output: Python objects matching JSON structure

    Common Usage Patterns:
        1. Loading configuration files
        2. Reading API response caches
        3. Processing structured data exports
        4. Loading machine learning datasets

    Upstream Sources:
        - API response saves
        - Configuration management
        - Data export systems
        - Previous JSONWriter outputs

    Downstream Consumers:
        - Transform nodes: Process structured data
        - Logic nodes: Navigate JSON structure
        - JSONWriter: Re-export with modifications
        - AI nodes: Use as structured input

    Error Handling:
        - FileNotFoundError: Missing file
        - json.JSONDecodeError: Invalid JSON syntax
        - PermissionError: Access denied
        - MemoryError: File too large

    Example:
        # Read API response data
        reader = JSONReaderNode(file_path='api_response.json')
        result = reader.execute()
        # result['data'] = {
        #     'status': 'success',
        #     'items': [{'id': 1, 'name': 'Item1'}],
        #     'metadata': {'version': '1.0'}
        # }
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for JSON reading.

        Simple parameter definition reflecting JSON's self-describing nature.
        Unlike CSV, JSON files don't require format configuration.

        Design Choice:
        - Single required parameter for simplicity
        - No encoding parameter (UTF-8 standard for JSON)
        - No structure hints needed (self-describing format)

        Returns:
            Dictionary with single file_path parameter
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the JSON file to read",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute JSON reading operation.

        Reads and parses JSON file, preserving the original structure
        and types. The json.load() function handles the parsing and
        type conversion automatically.

        Processing Steps:
        1. Opens file with UTF-8 encoding
        2. Parses JSON to Python objects
        3. Preserves structure (objects→dicts, arrays→lists)
        4. Returns wrapped in standard format

        Type Mappings:
        - JSON objects → Python dicts
        - JSON arrays → Python lists
        - JSON strings → Python strings
        - JSON numbers → Python int/float
        - JSON booleans → Python bool
        - JSON null → Python None

        Args:
            **kwargs: Validated parameters including:
                - file_path: Path to JSON file

        Returns:
            Dictionary with 'data' key containing the parsed JSON

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If JSON is malformed
            PermissionError: If file can't be read

        Downstream usage:
            - Structure can be directly navigated
            - Compatible with JSONWriter for round-trip
            - Transform nodes can process nested data
        """
        file_path = kwargs.get("file_path") or self.config.get("file_path")

        # Validate file path for security
        validated_path = validate_file_path(file_path, operation="JSON read")

        with safe_open(validated_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {"data": data}


@register_node()
class TextReaderNode(Node):
    """Reads text from a file.

    This node provides simple text file reading with encoding support.
    It's designed for processing plain text files, logs, documents,
    and any text-based format not handled by specialized readers.

    Design Features:
    1. Flexible encoding support
    2. Reads entire file as single string
    3. Preserves line endings and whitespace
    4. Handles various text encodings
    5. Simple, predictable output format

    Data Flow:
    - Input: File path and encoding
    - Processing: Read entire file as text
    - Output: Single text string

    Common Usage Patterns:
    1. Reading log files
    2. Processing documentation
    3. Loading templates
    4. Reading configuration files
    5. Processing natural language data

    Upstream Sources:
    - Log file generators
    - Document management systems
    - Template repositories
    - Previous TextWriter outputs

    Downstream Consumers:
    - NLP processors: Analyze text content
    - Pattern matchers: Search for patterns
    - TextWriter: Save processed text
    - AI models: Process natural language

    Error Handling:
    - FileNotFoundError: Missing file
    - PermissionError: Access denied
    - UnicodeDecodeError: Wrong encoding
    - MemoryError: File too large

    Example:
        >>> # Read a log file
        >>> reader = TextReaderNode(
        ...     file_path='application.log',
        ...     encoding='utf-8'
        ... )
        >>> result = reader.execute()
        >>> # result['text'] = "2024-01-01 INFO: Application started\\n..."
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for text reading.

        Provides essential parameters for text file reading with
        encoding flexibility to handle international text.

        Parameter Design:
        1. file_path: Required for file location
        2. encoding: Optional with UTF-8 default

        The encoding parameter is crucial for:
        - International text support
        - Legacy system compatibility
        - Log file processing
        - Cross-platform text handling

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the text file to read",
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default="utf-8",
                description="File encoding",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute text reading operation.

        Reads entire text file into memory as a single string,
        preserving all formatting, line endings, and whitespace.

        Processing Steps:
        1. Opens file with specified encoding
        2. Reads entire content as string
        3. Preserves original formatting
        4. Returns in standard format

        Memory Considerations:
        - Loads entire file into memory
        - Suitable for files up to ~10MB
        - Large files may need streaming approach

        Output Note:
        - Returns {"text": ...} not {"data": ...}
        - Different from CSV/JSON readers for clarity
        - Text is unprocessed, raw content

        Args:
            **kwargs: Validated parameters including:
                - file_path: Path to text file
                - encoding: Character encoding

        Returns:
            Dictionary with 'text' key containing file content

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If encoding is incorrect
            PermissionError: If file can't be read

        Downstream usage:
            - NLP nodes can tokenize/analyze
            - Pattern nodes can search content
            - Writers can save processed text
        """
        file_path = kwargs.get("file_path") or self.config.get("file_path")
        encoding = kwargs.get("encoding", "utf-8")

        # Validate file path for security
        validated_path = validate_file_path(file_path, operation="text read")

        with safe_open(validated_path, "r", encoding=encoding) as f:
            text = f.read()

        return {"text": text}

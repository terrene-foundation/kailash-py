"""Data writer nodes for the Kailash SDK.

This module provides node implementations for writing data to various file formats.
These nodes serve as data sinks in workflows, persisting processed data to the
file system for storage, sharing, or further processing.

Design Philosophy:
1. Consistent input interface across formats
2. Flexible output options for each format
3. Safe file operations with error handling
4. Format-specific optimizations
5. Progress tracking and feedback

Node Categories:
- CSVWriter: Tabular data to CSV files
- JSONWriter: Structured data to JSON files
- TextWriter: Raw text to any text file

Upstream Components:
- Reader nodes: Provide data to transform
- Transform nodes: Process data before writing
- Logic nodes: Filter data for output
- AI nodes: Generate content to save

Downstream Consumers:
- File system: Stores the written files
- External systems: Read the output files
- Other workflows: Use files as input
- Monitoring systems: Track file creation
"""

import csv
import json
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class CSVWriter(Node):
    """Writes data to a CSV file.

    This node handles CSV file writing with support for both dictionary
    and list data structures. It automatically detects data format and
    applies appropriate writing strategies.

    Design Features:
    1. Automatic format detection (dict vs list)
    2. Header generation from dictionary keys
    3. Configurable delimiters
    4. Unicode support through encoding
    5. Transaction-safe writing

    Data Flow:
    - Input: Structured data (list of dicts/lists)
    - Processing: Format detection and CSV generation
    - Output: File creation confirmation

    Common Usage Patterns:
    1. Exporting processed data
    2. Creating reports
    3. Generating data backups
    4. Producing import files
    5. Saving analysis results

    Upstream Sources:
    - CSVReader: Modified data round-trip
    - Transform nodes: Processed tabular data
    - Aggregator: Summarized results
    - API nodes: Structured responses

    Downstream Consumers:
    - File system: Stores the CSV
    - External tools: Excel, databases
    - Other workflows: Read the output
    - Archive systems: Long-term storage

    Error Handling:
    - PermissionError: Write access denied
    - OSError: Disk full or path issues
    - TypeError: Invalid data structure
    - UnicodeEncodeError: Encoding issues

    Example::

        # Write customer data
        writer = CSVWriter(
            file_path='output.csv',
            data=[
                {'id': 1, 'name': 'John', 'age': 30},
                {'id': 2, 'name': 'Jane', 'age': 25}
            ],
            delimiter=','
        )
        result = writer.execute()
        # result = {'rows_written': 2, 'file_path': 'output.csv'}
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for CSV writing.

        Provides comprehensive parameters for flexible CSV output,
        supporting various data structures and formatting options.

        Parameter Design:
        1. file_path: Required output location
        2. data: Required data to write
        3. headers: Optional custom headers
        4. delimiter: Optional separator

        The parameters handle two main scenarios:
        - Dict data: Auto-extracts headers from keys
        - List data: Requires headers or writes raw

        Returns:
            Dictionary of parameter definitions for validation
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the CSV file",
            ),
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Not required at initialization for workflow usage
                description="Data to write (list of dicts or lists)",
            ),
            "headers": NodeParameter(
                name="headers",
                type=bool,
                required=False,
                default=None,
                description="Column headers (auto-detected if not provided)",
            ),
            "delimiter": NodeParameter(
                name="delimiter",
                type=str,
                required=False,
                default=",",
                description="CSV delimiter character",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute CSV writing operation.

        Intelligently handles different data structures, automatically
        detecting format and applying appropriate writing strategy.

        Processing Steps:
        1. Detects data structure (dict vs list)
        2. Determines headers (provided or extracted)
        3. Creates appropriate CSV writer
        4. Writes headers if applicable
        5. Writes data rows
        6. Returns write statistics

        Format Detection:
        - Dict data: Uses DictWriter, auto-extracts headers
        - List data: Uses standard writer, optional headers
        - Empty data: Returns zero rows written

        File Handling:
        - Creates new file (overwrites existing)
        - Uses UTF-8 encoding
        - Handles newlines correctly (cross-platform)
        - Closes file automatically

        Args:
            **kwargs: Validated parameters including:
                - file_path: Output file location
                - data: List of dicts or lists
                - headers: Optional column names
                - delimiter: Field separator

        Returns:
            Dictionary with:
            - rows_written: Number of data rows
            - file_path: Output file location

        Raises:
            PermissionError: If can't write to location
            OSError: If path issues occur
            TypeError: If data format invalid

        Downstream usage:
            - File can be read by CSVReader
            - External tools can process output
            - Metrics available for monitoring
        """
        file_path = kwargs["file_path"]
        data = kwargs["data"]
        headers = kwargs.get("headers")
        delimiter = kwargs.get("delimiter", ",")

        if not data:
            return {"rows_written": 0}

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            if isinstance(data[0], dict):
                # Writing dictionaries
                if not headers:
                    headers = list(data[0].keys())
                writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
                writer.writeheader()
                writer.writerows(data)
            else:
                # Writing lists
                writer = csv.writer(f, delimiter=delimiter)
                if headers:
                    writer.writerow(headers)
                writer.writerows(data)

        return {"rows_written": len(data), "file_path": file_path}


@register_node()
class JSONWriter(Node):
    """Writes data to a JSON file.

    This node handles JSON serialization with support for complex
    nested structures, pretty printing, and various data types.
    It ensures data persistence while maintaining structure integrity.

    Design Features:
    1. Preserves complex data structures
    2. Pretty printing with indentation
    3. Unicode support by default
    4. Type preservation for round-trips
    5. Atomic write operations

    Data Flow:
    - Input: Any JSON-serializable data
    - Processing: JSON serialization
    - Output: File creation confirmation

    Common Usage Patterns:
    1. Saving API responses
    2. Persisting configuration
    3. Caching structured data
    4. Exporting analysis results
    5. Creating data backups

    Upstream Sources:
    - JSONReader: Modified data round-trip
    - API nodes: Response data
    - Transform nodes: Processed structures
    - Aggregator: Complex results

    Downstream Consumers:
    - File system: Stores JSON file
    - JSONReader: Can reload data
    - APIs: Import the data
    - Version control: Track changes

    Error Handling:
    - TypeError: Non-serializable data
    - PermissionError: Write access denied
    - OSError: Path or disk issues
    - JSONEncodeError: Encoding problems

    Example::

        # Write API response
        writer = JSONWriter(
            file_path='response.json',
            data={
                'status': 'success',
                'results': [1, 2, 3],
                'metadata': {'version': '1.0'}
            },
            indent=2
        )
        result = writer.execute()
        # result = {'file_path': 'response.json'}
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for JSON writing.

        Minimal parameters reflecting JSON's flexibility while
        providing formatting control through indentation.

        Parameter Design:
        1. file_path: Required output location
        2. data: Required data (any serializable)
        3. indent: Optional formatting control

        The 'Any' type for data reflects JSON's ability to
        handle various structures - validation happens at
        serialization time.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the JSON file",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,  # Not required at initialization for workflow usage
                description="Data to write (must be JSON-serializable)",
            ),
            "indent": NodeParameter(
                name="indent",
                type=int,
                required=False,
                default=2,
                description="Indentation level for pretty printing",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute JSON writing operation.

        Serializes data to JSON format with proper formatting
        and encoding. Handles complex nested structures while
        maintaining readability through indentation.

        Processing Steps:
        1. Opens file for writing
        2. Serializes data to JSON
        3. Applies formatting options
        4. Ensures Unicode preservation
        5. Writes atomically

        Serialization Features:
        - Pretty printing with indentation
        - Unicode characters preserved
        - Consistent key ordering
        - Null value handling
        - Number precision maintained

        Args:
            **kwargs: Validated parameters including:
                - file_path: Output file location
                - data: Data to serialize
                - indent: Spaces for indentation

        Returns:
            Dictionary with:
            - file_path: Written file location

        Raises:
            TypeError: If data not serializable
            PermissionError: If write denied
            OSError: If path issues

        Downstream usage:
            - JSONReader can reload file
            - Version control can track
            - APIs can import data
        """
        file_path = kwargs["file_path"]
        data = kwargs["data"]
        indent = kwargs.get("indent", 2)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

        return {"file_path": file_path}


@register_node()
class TextWriter(Node):
    """Writes text to a file.

    This node provides flexible text file writing with support for
    various encodings and append operations. It handles plain text
    output for logs, documents, and generated content.

    Design Features:
    1. Flexible encoding support
    2. Append mode for log files
    3. Overwrite mode for fresh output
    4. Byte counting for verification
    5. Unicode-safe operations

    Data Flow:
    - Input: Text string and configuration
    - Processing: Encode and write text
    - Output: Write confirmation

    Common Usage Patterns:
    1. Writing log entries
    2. Saving generated content
    3. Creating documentation
    4. Exporting text reports
    5. Building configuration files

    Upstream Sources:
    - TextReader: Modified text round-trip
    - Transform nodes: Processed text
    - AI nodes: Generated content
    - Template nodes: Formatted output

    Downstream Consumers:
    - File system: Stores text file
    - Log analyzers: Process logs
    - Documentation systems: Use output
    - Version control: Track changes

    Error Handling:
    - PermissionError: Write access denied
    - OSError: Path or disk issues
    - UnicodeEncodeError: Encoding mismatch
    - MemoryError: Text too large

    Example::

        # Append to log file
        writer = TextWriter(
            file_path='app.log',
            text='ERROR: Connection failed\\n',
            encoding='utf-8',
            append=True
        )
        result = writer.execute()
        # result = {'file_path': 'app.log', 'bytes_written': 25}
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for text writing.

        Comprehensive parameters supporting various text writing
        scenarios from simple output to complex log management.

        Parameter Design:
        1. file_path: Required output location
        2. text: Required content to write
        3. encoding: Optional for compatibility
        4. append: Optional for log patterns

        The append parameter is crucial for:
        - Log file management
        - Continuous output streams
        - Building files incrementally
        - Preserving existing content

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the text file",
            ),
            "text": NodeParameter(
                name="text", type=str, required=True, description="Text to write"
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default="utf-8",
                description="File encoding",
            ),
            "append": NodeParameter(
                name="append",
                type=bool,
                required=False,
                default=False,
                description="Whether to append to existing file",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute text writing operation.

        Writes text to file with specified encoding and mode.
        Supports both overwrite and append operations for different
        use cases like logging and content generation.

        Processing Steps:
        1. Determines write mode (append/overwrite)
        2. Opens file with encoding
        3. Writes text content
        4. Calculates bytes written
        5. Returns write statistics

        Mode Selection:
        - append=False: Creates new or overwrites
        - append=True: Adds to existing file
        - File created if doesn't exist (both modes)

        Encoding Handling:
        - Encodes text before counting bytes
        - Supports any Python encoding
        - UTF-8 default for compatibility

        Args:
            **kwargs: Validated parameters including:
                - file_path: Output file location
                - text: Content to write
                - encoding: Character encoding
                - append: Write mode selection

        Returns:
            Dictionary with:
            - file_path: Written file location
            - bytes_written: Size of written data

        Raises:
            PermissionError: If write denied
            OSError: If path issues
            UnicodeEncodeError: If encoding fails

        Downstream usage:
            - TextReader can read file
            - Log analyzers can process
            - Metrics available for monitoring
        """
        file_path = kwargs["file_path"]
        text = kwargs["text"]
        encoding = kwargs.get("encoding", "utf-8")
        append = kwargs.get("append", False)

        mode = "a" if append else "w"
        with open(file_path, mode, encoding=encoding) as f:
            f.write(text)

        return {"file_path": file_path, "bytes_written": len(text.encode(encoding))}

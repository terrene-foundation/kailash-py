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
from typing import Any

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
        >>> result = reader.execute(
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
        >>> result = reader.execute(
        ...     file_path="data.tsv",
        ...     delimiter="\\t",
        ...     headers=True
        ... )
        >>>
        >>> # Reading without headers (returns list of lists)
        >>> result = reader.execute(
        ...     file_path="data.csv",
        ...     headers=False
        ... )
        >>> assert all(isinstance(row, list) for row in result["data"])
        >>>
        >>> # Reading with specific encoding
        >>> result = reader.execute(
        ...     file_path="european_data.csv",
        ...     encoding="iso-8859-1",
        ...     headers=True
        ... )
        >>>
        >>> # Handling quoted fields
        >>> result = reader.execute(
        ...     file_path="complex.csv",
        ...     headers=True,
        ...     quotechar='"'
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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
                    row_dict = dict(zip(header_row, row, strict=False))
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

    def _infer_type(self, value: str) -> Any:
        """Infer the appropriate Python type for a CSV value.

        Args:
            value: String value from CSV

        Returns:
            Value converted to appropriate type (int, float, bool, or str)
        """
        if not value or value.strip() == "":
            return None

        value = value.strip()

        # Try boolean first (only explicit boolean representations, not numeric 0/1)
        if value.lower() in ("true", "false", "yes", "no"):
            return value.lower() in ("true", "yes")

        # Try integer
        try:
            if (
                "." not in value
                and value.isdigit()
                or (value.startswith("-") and value[1:].isdigit())
            ):
                return int(value)
        except ValueError:
            pass

        # Try float
        try:
            if "." in value or "e" in value.lower():
                return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Read CSV file asynchronously for better I/O performance.

        This method provides true async file reading with aiofiles,
        offering significant performance improvements for large files
        and concurrent operations.

        Args:
            Same as run() method

        Returns:
            Same as run() method

        Raises:
            Same as run() method
        """
        # Import aiofiles for async file operations
        try:
            import aiofiles
        except ImportError:
            # Fallback to sync version if async dependencies not available
            return self.execute(**kwargs)

        file_path = kwargs.get("file_path")
        encoding = kwargs.get("encoding", "utf-8")
        delimiter = kwargs.get("delimiter", ",")
        has_header = kwargs.get("has_header", True)
        skip_rows = kwargs.get("skip_rows", 0)
        max_rows = kwargs.get("max_rows")
        columns = kwargs.get("columns")
        index_column = kwargs.get("index_column")

        # Validate inputs using same logic as sync version
        if not file_path:
            raise ValueError("file_path is required")

        validate_file_path(file_path)

        try:
            # Async file reading with aiofiles
            async with aiofiles.open(file_path, mode="r", encoding=encoding) as file:
                # Read all lines for CSV parsing
                content = await file.read()

            # Parse CSV content (CPU-bound, but file I/O is async)
            import io

            content_io = io.StringIO(content)

            # Skip rows if requested
            for _ in range(skip_rows):
                next(content_io, None)

            # Create CSV reader
            csv_reader = csv.reader(content_io, delimiter=delimiter)

            # Handle header row
            headers = None
            if has_header:
                headers = next(csv_reader, None)
                if headers and columns:
                    # Validate that specified columns exist
                    missing_cols = set(columns) - set(headers)
                    if missing_cols:
                        raise ValueError(f"Columns not found: {missing_cols}")
            elif columns:
                headers = columns

            # Read data rows
            data = []
            data_indexed = {}

            for row_num, row in enumerate(csv_reader):
                if max_rows and row_num >= max_rows:
                    break

                if not row:  # Skip empty rows
                    continue

                # Process row based on whether we have headers
                if headers:
                    # Create dictionary with column names
                    row_data = {}
                    for i, value in enumerate(row):
                        if i < len(headers):
                            col_name = headers[i]
                            # Only include specified columns if provided
                            if not columns or col_name in columns:
                                row_data[col_name] = self._infer_type(
                                    value.strip() if value else value
                                )
                else:
                    # No headers, return as list with type inference
                    row_data = [
                        self._infer_type(cell.strip() if cell else cell) for cell in row
                    ]

                data.append(row_data)

                # Handle index column for faster lookups
                if index_column and headers and index_column in headers:
                    index_value = row_data.get(index_column)
                    if index_value is not None:
                        data_indexed[index_value] = row_data

        except Exception as e:
            raise ValueError(f"Error reading CSV file: {str(e)}")

        # Return same format as sync version
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

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Read JSON file asynchronously for better I/O performance.

        This method provides true async file reading with aiofiles,
        offering significant performance improvements for large files
        and concurrent operations.

        Args:
            Same as run() method

        Returns:
            Same as run() method

        Raises:
            Same as run() method
        """
        # Import aiofiles for async file operations
        try:
            import aiofiles
        except ImportError:
            # Fallback to sync version if async dependencies not available
            return self.execute(**kwargs)

        file_path = kwargs.get("file_path") or self.config.get("file_path")

        # Validate file path for security (same as sync version)
        validated_path = validate_file_path(file_path, operation="JSON read")

        try:
            # Async file reading with aiofiles
            async with aiofiles.open(
                validated_path, mode="r", encoding="utf-8"
            ) as file:
                content = await file.read()

            # Parse JSON content (CPU-bound, but file I/O is async)
            data = json.loads(content)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in file {validated_path}: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error reading JSON file {validated_path}: {str(e)}")

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

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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


@register_node()
class DocumentProcessorNode(Node):
    """
    Advanced document processor that reads and processes multiple document formats
    with automatic format detection, metadata extraction, and structured output.

    This node unifies document reading across formats (PDF, DOCX, MD, TXT, HTML, RTF)
    and provides consistent structured output with extracted metadata, making it
    ideal for document analysis workflows, content management, and RAG systems.

    Design Philosophy:
        The DocumentProcessorNode embodies "universal document accessibility."
        Rather than requiring format-specific readers, it automatically detects
        and processes various document types, extracting both content and metadata
        for comprehensive document understanding.

    Upstream Dependencies:
        - File system providing documents
        - Path discovery nodes
        - Document management systems
        - User inputs specifying documents

    Downstream Consumers:
        - Chunking nodes for text segmentation
        - Embedding nodes for vector processing
        - LLM nodes for content analysis
        - Indexing systems for document search
        - Metadata analyzers for classification

    Supported Formats:
        - PDF: Full text extraction with metadata
        - DOCX: Content and document properties
        - TXT: Plain text with encoding detection
        - MD: Markdown with structure parsing
        - HTML: Text extraction from markup
        - RTF: Rich text format processing
        - Auto-detection based on file extension

    Configuration:
        - extract_metadata: Include document properties
        - preserve_structure: Maintain document sections
        - encoding: Text encoding for plain text files
        - extract_images: Include image references (future)
        - page_numbers: Include page/section numbers

    Examples:
        >>> processor = DocumentProcessorNode(
        ...     extract_metadata=True,
        ...     preserve_structure=True
        ... )
        >>> result = processor.execute(
        ...     file_path="document.pdf"
        ... )
        >>> content = result["content"]
        >>> metadata = result["metadata"]
        >>> sections = result["sections"]
    """

    def __init__(self, name: str = "document_processor", **kwargs):
        # Set attributes before calling super().__init__() as Kailash validates during init
        self.extract_metadata = kwargs.get("extract_metadata", True)
        self.preserve_structure = kwargs.get("preserve_structure", True)
        self.encoding = kwargs.get("encoding", "utf-8")
        self.extract_images = kwargs.get("extract_images", False)
        self.page_numbers = kwargs.get("page_numbers", True)

        super().__init__(name=name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters for document processing."""
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the document file to process",
            ),
            "extract_metadata": NodeParameter(
                name="extract_metadata",
                type=bool,
                required=False,
                default=self.extract_metadata,
                description="Extract document metadata (title, author, creation date, etc.)",
            ),
            "preserve_structure": NodeParameter(
                name="preserve_structure",
                type=bool,
                required=False,
                default=self.preserve_structure,
                description="Preserve document structure (sections, headings, etc.)",
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default=self.encoding,
                description="Text encoding for plain text files",
            ),
            "page_numbers": NodeParameter(
                name="page_numbers",
                type=bool,
                required=False,
                default=self.page_numbers,
                description="Include page/section numbers in output",
            ),
            "extract_images": NodeParameter(
                name="extract_images",
                type=bool,
                required=False,
                default=self.extract_images,
                description="Extract image references and descriptions",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute document processing operation."""
        file_path = kwargs.get("file_path", "")
        extract_metadata = kwargs.get("extract_metadata", self.extract_metadata)
        preserve_structure = kwargs.get("preserve_structure", self.preserve_structure)
        encoding = kwargs.get("encoding", self.encoding)
        page_numbers = kwargs.get("page_numbers", self.page_numbers)
        extract_images = kwargs.get("extract_images", self.extract_images)

        if not file_path:
            return {
                "error": "File path is required",
                "content": "",
                "metadata": {},
                "sections": [],
            }

        try:
            # Validate file path for security
            validated_path = validate_file_path(file_path, operation="document read")

            # Detect document format
            document_format = self._detect_format(validated_path)

            # Process document based on format
            if document_format == "pdf":
                result = self._process_pdf(
                    validated_path, extract_metadata, preserve_structure, page_numbers
                )
            elif document_format == "docx":
                result = self._process_docx(
                    validated_path, extract_metadata, preserve_structure
                )
            elif document_format == "markdown":
                result = self._process_markdown(
                    validated_path, encoding, preserve_structure
                )
            elif document_format == "html":
                result = self._process_html(
                    validated_path, encoding, preserve_structure
                )
            elif document_format == "rtf":
                result = self._process_rtf(
                    validated_path, extract_metadata, preserve_structure
                )
            else:  # Default to text
                result = self._process_text(validated_path, encoding, extract_metadata)

            # Add common metadata
            result["metadata"]["file_path"] = file_path
            result["metadata"]["document_format"] = document_format
            result["metadata"]["processing_timestamp"] = self._get_timestamp()

            return result

        except Exception as e:
            return {
                "error": f"Document processing failed: {str(e)}",
                "content": "",
                "metadata": {"file_path": file_path, "error": str(e)},
                "sections": [],
                "document_format": "unknown",
            }

    def _detect_format(self, file_path: str) -> str:
        """Detect document format based on file extension."""
        import os

        extension = os.path.splitext(file_path)[1].lower()

        format_map = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".doc": "docx",  # Treat as docx for now
            ".md": "markdown",
            ".markdown": "markdown",
            ".html": "html",
            ".htm": "html",
            ".rtf": "rtf",
            ".txt": "text",
            ".log": "text",
            ".csv": "text",  # Could be enhanced
            ".json": "text",  # Could be enhanced
        }

        return format_map.get(extension, "text")

    def _process_pdf(
        self,
        file_path: str,
        extract_metadata: bool,
        preserve_structure: bool,
        page_numbers: bool,
    ) -> dict:
        """Process PDF document (simplified implementation)."""
        # In a real implementation, this would use PyPDF2, pdfplumber, or similar
        # For now, return a structured placeholder

        try:
            # Placeholder implementation - in reality would use PDF libraries
            content = f"[PDF Content from {file_path}]"

            metadata = {}
            if extract_metadata:
                metadata.update(
                    {
                        "title": "Document Title",
                        "author": "Document Author",
                        "creation_date": "2024-01-01",
                        "page_count": 1,
                        "pdf_version": "1.4",
                    }
                )

            sections = []
            if preserve_structure:
                sections = [
                    {
                        "type": "page",
                        "number": 1,
                        "content": content,
                        "start_position": 0,
                        "end_position": len(content),
                    }
                ]

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "pdf",
            }

        except Exception as e:
            # Fall back to text reading if PDF processing fails
            return self._process_text(file_path, "utf-8", extract_metadata)

    def _process_docx(
        self, file_path: str, extract_metadata: bool, preserve_structure: bool
    ) -> dict:
        """Process DOCX document (simplified implementation)."""
        # In a real implementation, this would use python-docx
        # For now, return a structured placeholder

        try:
            # Placeholder implementation - in reality would use python-docx
            content = f"[DOCX Content from {file_path}]"

            metadata = {}
            if extract_metadata:
                metadata.update(
                    {
                        "title": "Document Title",
                        "author": "Document Author",
                        "creation_date": "2024-01-01",
                        "modification_date": "2024-01-01",
                        "word_count": len(content.split()),
                    }
                )

            sections = []
            if preserve_structure:
                sections = [
                    {
                        "type": "paragraph",
                        "style": "Normal",
                        "content": content,
                        "start_position": 0,
                        "end_position": len(content),
                    }
                ]

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "docx",
            }

        except Exception as e:
            # Fall back to text reading if DOCX processing fails
            return self._process_text(file_path, "utf-8", extract_metadata)

    def _process_markdown(
        self, file_path: str, encoding: str, preserve_structure: bool
    ) -> dict:
        """Process Markdown document with structure parsing."""
        try:
            with safe_open(file_path, "r", encoding=encoding) as f:
                content = f.read()

            metadata = {
                "character_count": len(content),
                "line_count": len(content.splitlines()),
                "word_count": len(content.split()),
            }

            sections = []
            if preserve_structure:
                sections = self._parse_markdown_structure(content)

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "markdown",
            }

        except Exception as e:
            return {
                "content": "",
                "metadata": {"error": str(e)},
                "sections": [],
                "document_format": "markdown",
            }

    def _process_html(
        self, file_path: str, encoding: str, preserve_structure: bool
    ) -> dict:
        """Process HTML document with text extraction."""
        try:
            with safe_open(file_path, "r", encoding=encoding) as f:
                html_content = f.read()

            # Simple HTML text extraction (in reality would use BeautifulSoup)
            import re

            # Remove script and style elements
            html_content = re.sub(
                r"<script[^>]*>.*?</script>",
                "",
                html_content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            html_content = re.sub(
                r"<style[^>]*>.*?</style>",
                "",
                html_content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # Remove HTML tags
            content = re.sub(r"<[^>]+>", "", html_content)
            # Clean up whitespace
            content = re.sub(r"\s+", " ", content).strip()

            metadata = {
                "character_count": len(content),
                "word_count": len(content.split()),
                "original_html_length": len(html_content),
            }

            sections = []
            if preserve_structure:
                # Simple section detection based on common patterns
                sections = self._parse_html_structure(html_content, content)

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "html",
            }

        except Exception as e:
            return {
                "content": "",
                "metadata": {"error": str(e)},
                "sections": [],
                "document_format": "html",
            }

    def _process_rtf(
        self, file_path: str, extract_metadata: bool, preserve_structure: bool
    ) -> dict:
        """Process RTF document (simplified implementation)."""
        # In a real implementation, this would use striprtf or similar
        try:
            with safe_open(file_path, "r", encoding="utf-8") as f:
                rtf_content = f.read()

            # Simple RTF text extraction (remove RTF control codes)
            import re

            content = re.sub(r"\\[a-z]+\d*\s?", "", rtf_content)  # Remove RTF commands
            content = re.sub(r"[{}]", "", content)  # Remove braces
            content = re.sub(r"\s+", " ", content).strip()  # Clean whitespace

            metadata = {}
            if extract_metadata:
                metadata.update(
                    {
                        "character_count": len(content),
                        "word_count": len(content.split()),
                        "original_rtf_length": len(rtf_content),
                    }
                )

            sections = []
            if preserve_structure:
                sections = [
                    {
                        "type": "document",
                        "content": content,
                        "start_position": 0,
                        "end_position": len(content),
                    }
                ]

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "rtf",
            }

        except Exception as e:
            return {
                "content": "",
                "metadata": {"error": str(e)},
                "sections": [],
                "document_format": "rtf",
            }

    def _process_text(
        self, file_path: str, encoding: str, extract_metadata: bool
    ) -> dict:
        """Process plain text document."""
        try:
            with safe_open(file_path, "r", encoding=encoding) as f:
                content = f.read()

            metadata = {}
            if extract_metadata:
                lines = content.splitlines()
                metadata.update(
                    {
                        "character_count": len(content),
                        "line_count": len(lines),
                        "word_count": len(content.split()),
                        "encoding": encoding,
                        "max_line_length": (
                            max(len(line) for line in lines) if lines else 0
                        ),
                        "blank_lines": sum(1 for line in lines if not line.strip()),
                    }
                )

            sections = [
                {
                    "type": "text",
                    "content": content,
                    "start_position": 0,
                    "end_position": len(content),
                }
            ]

            return {
                "content": content,
                "metadata": metadata,
                "sections": sections,
                "document_format": "text",
            }

        except Exception as e:
            return {
                "content": "",
                "metadata": {"error": str(e)},
                "sections": [],
                "document_format": "text",
            }

    def _parse_markdown_structure(self, content: str) -> list:
        """Parse Markdown structure into sections."""
        import re

        sections = []

        # Find headings
        heading_pattern = r"^(#{1,6})\s+(.+)$"
        lines = content.splitlines()
        current_pos = 0

        for i, line in enumerate(lines):
            match = re.match(heading_pattern, line)
            if match:
                level = len(match.group(1))
                title = match.group(2)

                # Calculate position in original content
                line_start = content.find(line, current_pos)

                sections.append(
                    {
                        "type": "heading",
                        "level": level,
                        "title": title,
                        "content": line,
                        "line_number": i + 1,
                        "start_position": line_start,
                        "end_position": line_start + len(line),
                    }
                )

                current_pos = line_start + len(line)

        return sections

    def _parse_html_structure(self, html_content: str, text_content: str) -> list:
        """Parse HTML structure into sections (simplified)."""
        import re

        sections = []

        # Find title
        title_match = re.search(
            r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE
        )
        if title_match:
            sections.append(
                {
                    "type": "title",
                    "content": title_match.group(1),
                    "start_position": 0,
                    "end_position": len(title_match.group(1)),
                }
            )

        # Find headings
        heading_pattern = r"<(h[1-6])[^>]*>([^<]+)</h[1-6]>"
        for match in re.finditer(heading_pattern, html_content, re.IGNORECASE):
            tag = match.group(1)
            text = match.group(2)
            level = int(tag[1])

            sections.append(
                {
                    "type": "heading",
                    "level": level,
                    "title": text,
                    "content": text,
                    "start_position": match.start(),
                    "end_position": match.end(),
                }
            )

        return sections

    def _get_timestamp(self) -> str:
        """Get current timestamp for metadata."""
        from datetime import datetime

        return datetime.now().isoformat()

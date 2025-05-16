"""Data writer nodes for the Kailash SDK."""
import csv
import json
from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class CSVWriter(Node):
    """Writes data to a CSV file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the CSV file"
            ),
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to write (list of dicts or lists)"
            ),
            "headers": NodeParameter(
                name="headers",
                type=list,
                required=False,
                default=None,
                description="Column headers (auto-detected if not provided)"
            ),
            "delimiter": NodeParameter(
                name="delimiter",
                type=str,
                required=False,
                default=",",
                description="CSV delimiter character"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs["file_path"]
        data = kwargs["data"]
        headers = kwargs.get("headers")
        delimiter = kwargs.get("delimiter", ",")
        
        if not data:
            return {"rows_written": 0}
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
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
    """Writes data to a JSON file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the JSON file"
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True,
                description="Data to write (must be JSON-serializable)"
            ),
            "indent": NodeParameter(
                name="indent",
                type=int,
                required=False,
                default=2,
                description="Indentation level for pretty printing"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs["file_path"]
        data = kwargs["data"]
        indent = kwargs.get("indent", 2)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        
        return {"file_path": file_path}


@register_node()
class TextWriter(Node):
    """Writes text to a file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to write the text file"
            ),
            "text": NodeParameter(
                name="text",
                type=str,
                required=True,
                description="Text to write"
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default="utf-8",
                description="File encoding"
            ),
            "append": NodeParameter(
                name="append",
                type=bool,
                required=False,
                default=False,
                description="Whether to append to existing file"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs["file_path"]
        text = kwargs["text"]
        encoding = kwargs.get("encoding", "utf-8")
        append = kwargs.get("append", False)
        
        mode = 'a' if append else 'w'
        with open(file_path, mode, encoding=encoding) as f:
            f.write(text)
        
        return {"file_path": file_path, "bytes_written": len(text.encode(encoding))}
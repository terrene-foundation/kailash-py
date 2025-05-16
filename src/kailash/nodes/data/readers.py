"""Data reader nodes for the Kailash SDK."""
import csv
import json
from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class CSVReader(Node):
    """Reads data from a CSV file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the CSV file to read"
            ),
            "headers": NodeParameter(
                name="headers",
                type=bool,
                required=False,
                default=True,
                description="Whether the CSV has headers"
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
        headers = kwargs.get("headers", True)
        delimiter = kwargs.get("delimiter", ",")
        
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=delimiter)
            
            if headers:
                header_row = next(reader)
                for row in reader:
                    data.append(dict(zip(header_row, row)))
            else:
                for row in reader:
                    data.append(row)
        
        return {"data": data}


@register_node()
class JSONReader(Node):
    """Reads data from a JSON file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the JSON file to read"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs["file_path"]
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {"data": data}


@register_node()
class TextReader(Node):
    """Reads text from a file."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the text file to read"
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default="utf-8",
                description="File encoding"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs["file_path"]
        encoding = kwargs.get("encoding", "utf-8")
        
        with open(file_path, 'r', encoding=encoding) as f:
            text = f.read()
        
        return {"text": text}
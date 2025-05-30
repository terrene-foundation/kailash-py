"""Tests for data nodes (readers and writers)."""

import pytest
import tempfile
import json
import csv
from pathlib import Path
from typing import Dict, Any

from kailash.nodes.data.readers import CSVReader, JSONReader, TextReader
from kailash.nodes.data.writers import CSVWriter, JSONWriter, TextWriter  
from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError


class TestCSVReaderNode:
    """Test CSV reader node."""
    
    def test_read_csv_success(self, temp_dir):
        """Test successful CSV reading."""
        # Create test CSV file
        csv_path = temp_dir / "test.csv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'age', 'city'])
            writer.writeheader()
            writer.writerow({'name': 'Alice', 'age': '30', 'city': 'New York'})
            writer.writerow({'name': 'Bob', 'age': '25', 'city': 'San Francisco'})
        
        node = CSVReader(file_path=str(csv_path))
        result = node.execute()
        
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["data"][0] == {'name': 'Alice', 'age': '30', 'city': 'New York'}
        assert result["data"][1] == {'name': 'Bob', 'age': '25', 'city': 'San Francisco'}
    
    def test_read_csv_with_custom_delimiter(self, temp_dir):
        """Test reading CSV with custom delimiter."""
        csv_path = temp_dir / "test.tsv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'value'], delimiter='\t')
            writer.writeheader()
            writer.writerow({'name': 'Item1', 'value': '100'})
        
        node = CSVReader(file_path=str(csv_path), delimiter="\t")
        result = node.execute()
        
        assert len(result["data"]) == 1
        assert result["data"][0] == {'name': 'Item1', 'value': '100'}
    
    def test_read_csv_file_not_found(self):
        """Test reading non-existent CSV file."""
        node = CSVReaderNode(node_id="csv-reader", name="CSV Reader")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({"file_path": "/nonexistent/file.csv"})
    
    def test_read_csv_invalid_file(self, temp_dir):
        """Test reading invalid CSV file."""
        # Create invalid file
        invalid_path = temp_dir / "invalid.csv"
        with open(invalid_path, 'wb') as f:
            f.write(b'\x00\x01\x02\x03')  # Binary data
        
        node = CSVReaderNode(node_id="csv-reader", name="CSV Reader")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({"file_path": str(invalid_path)})


class TestJSONReaderNode:
    """Test JSON reader node."""
    
    def test_read_json_object(self, temp_dir):
        """Test reading JSON object."""
        json_path = temp_dir / "test.json"
        data = {"name": "Test", "value": 42, "items": [1, 2, 3]}
        
        with open(json_path, 'w') as f:
            json.dump(data, f)
        
        node = JSONReaderNode(node_id="json-reader", name="JSON Reader")
        result = node.execute({"file_path": str(json_path)})
        
        assert result["data"] == data
    
    def test_read_json_array(self, temp_dir):
        """Test reading JSON array."""
        json_path = temp_dir / "test.json"
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        
        with open(json_path, 'w') as f:
            json.dump(data, f)
        
        node = JSONReaderNode(node_id="json-reader", name="JSON Reader")
        result = node.execute({"file_path": str(json_path)})
        
        assert result["data"] == data
    
    def test_read_json_with_encoding(self, temp_dir):
        """Test reading JSON with specific encoding."""
        json_path = temp_dir / "test.json"
        data = {"message": "Hello 世界"}
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        
        node = JSONReaderNode(node_id="json-reader", name="JSON Reader")
        result = node.execute({"file_path": str(json_path), "encoding": "utf-8"})
        
        assert result["data"] == data
    
    def test_read_invalid_json(self, temp_dir):
        """Test reading invalid JSON file."""
        json_path = temp_dir / "invalid.json"
        
        with open(json_path, 'w') as f:
            f.write("{ invalid json }")
        
        node = JSONReaderNode(node_id="json-reader", name="JSON Reader")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({"file_path": str(json_path)})


class TestTextReaderNode:
    """Test text reader node."""
    
    def test_read_text_file(self, temp_dir):
        """Test reading text file."""
        text_path = temp_dir / "test.txt"
        content = "Line 1\nLine 2\nLine 3"
        
        with open(text_path, 'w') as f:
            f.write(content)
        
        node = TextReaderNode(node_id="text-reader", name="Text Reader")
        result = node.execute({"file_path": str(text_path)})
        
        assert result["content"] == content
    
    def test_read_text_with_encoding(self, temp_dir):
        """Test reading text with specific encoding."""
        text_path = temp_dir / "test.txt"
        content = "Hello 世界"
        
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        node = TextReaderNode(node_id="text-reader", name="Text Reader")
        result = node.execute({"file_path": str(text_path), "encoding": "utf-8"})
        
        assert result["content"] == content
    
    def test_read_empty_file(self, temp_dir):
        """Test reading empty text file."""
        text_path = temp_dir / "empty.txt"
        text_path.touch()
        
        node = TextReaderNode(node_id="text-reader", name="Text Reader")
        result = node.execute({"file_path": str(text_path)})
        
        assert result["content"] == ""


class TestCSVWriterNode:
    """Test CSV writer node."""
    
    def test_write_csv_success(self, temp_dir):
        """Test successful CSV writing."""
        csv_path = temp_dir / "output.csv"
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]
        
        node = CSVWriterNode(node_id="csv-writer", name="CSV Writer")
        result = node.execute({
            "file_path": str(csv_path),
            "data": data,
            "fieldnames": ["name", "age"]
        })
        
        assert result["file_path"] == str(csv_path)
        assert result["rows_written"] == 2
        
        # Verify file contents
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["name"] == "Alice"
            assert rows[0]["age"] == "30"
    
    def test_write_csv_auto_fieldnames(self, temp_dir):
        """Test CSV writing with automatic fieldnames."""
        csv_path = temp_dir / "output.csv"
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]
        
        node = CSVWriterNode(node_id="csv-writer", name="CSV Writer")
        result = node.execute({
            "file_path": str(csv_path),
            "data": data
        })
        
        # Should auto-detect fieldnames from first row
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
    
    def test_write_csv_custom_delimiter(self, temp_dir):
        """Test CSV writing with custom delimiter."""
        csv_path = temp_dir / "output.tsv"
        data = [{"name": "Alice", "age": 30}]
        
        node = CSVWriterNode(node_id="csv-writer", name="CSV Writer")
        result = node.execute({
            "file_path": str(csv_path),
            "data": data,
            "delimiter": "\t"
        })
        
        with open(csv_path, 'r') as f:
            content = f.read()
            assert "\t" in content
    
    def test_write_csv_empty_data(self, temp_dir):
        """Test writing empty data."""
        csv_path = temp_dir / "empty.csv"
        
        node = CSVWriterNode(node_id="csv-writer", name="CSV Writer")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "file_path": str(csv_path),
                "data": []
            })
    
    def test_write_csv_invalid_path(self):
        """Test writing to invalid path."""
        node = CSVWriterNode(node_id="csv-writer", name="CSV Writer")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "file_path": "/invalid/path/file.csv",
                "data": [{"test": 1}]
            })


class TestJSONWriterNode:
    """Test JSON writer node."""
    
    def test_write_json_object(self, temp_dir):
        """Test writing JSON object."""
        json_path = temp_dir / "output.json"
        data = {"name": "Test", "value": 42}
        
        node = JSONWriterNode(node_id="json-writer", name="JSON Writer")
        result = node.execute({
            "file_path": str(json_path),
            "data": data
        })
        
        assert result["file_path"] == str(json_path)
        
        # Verify file contents
        with open(json_path, 'r') as f:
            saved_data = json.load(f)
            assert saved_data == data
    
    def test_write_json_array(self, temp_dir):
        """Test writing JSON array."""
        json_path = temp_dir / "output.json"
        data = [1, 2, 3, 4, 5]
        
        node = JSONWriterNode(node_id="json-writer", name="JSON Writer")
        result = node.execute({
            "file_path": str(json_path),
            "data": data
        })
        
        with open(json_path, 'r') as f:
            saved_data = json.load(f)
            assert saved_data == data
    
    def test_write_json_pretty(self, temp_dir):
        """Test writing pretty-printed JSON."""
        json_path = temp_dir / "output.json"
        data = {"name": "Test", "nested": {"key": "value"}}
        
        node = JSONWriterNode(node_id="json-writer", name="JSON Writer")
        result = node.execute({
            "file_path": str(json_path),
            "data": data,
            "indent": 2
        })
        
        with open(json_path, 'r') as f:
            content = f.read()
            # Pretty printed JSON should have newlines and indentation
            assert "\n" in content
            assert "  " in content  # 2-space indentation
    
    def test_write_json_with_encoding(self, temp_dir):
        """Test writing JSON with specific encoding."""
        json_path = temp_dir / "output.json"
        data = {"message": "Hello 世界"}
        
        node = JSONWriterNode(node_id="json-writer", name="JSON Writer")
        result = node.execute({
            "file_path": str(json_path),
            "data": data,
            "encoding": "utf-8",
            "ensure_ascii": False
        })
        
        with open(json_path, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
            assert saved_data == data


class TestTextWriterNode:
    """Test text writer node."""
    
    def test_write_text_file(self, temp_dir):
        """Test writing text file."""
        text_path = temp_dir / "output.txt"
        content = "Hello\nWorld"
        
        node = TextWriterNode(node_id="text-writer", name="Text Writer")
        result = node.execute({
            "file_path": str(text_path),
            "content": content
        })
        
        assert result["file_path"] == str(text_path)
        assert result["bytes_written"] == len(content)
        
        with open(text_path, 'r') as f:
            saved_content = f.read()
            assert saved_content == content
    
    def test_write_text_with_encoding(self, temp_dir):
        """Test writing text with specific encoding."""
        text_path = temp_dir / "output.txt"
        content = "Hello 世界"
        
        node = TextWriterNode(node_id="text-writer", name="Text Writer")
        result = node.execute({
            "file_path": str(text_path),
            "content": content,
            "encoding": "utf-8"
        })
        
        with open(text_path, 'r', encoding='utf-8') as f:
            saved_content = f.read()
            assert saved_content == content
    
    def test_write_empty_content(self, temp_dir):
        """Test writing empty content."""
        text_path = temp_dir / "empty.txt"
        
        node = TextWriterNode(node_id="text-writer", name="Text Writer")
        result = node.execute({
            "file_path": str(text_path),
            "content": ""
        })
        
        assert result["bytes_written"] == 0
        assert text_path.exists()
        assert text_path.stat().st_size == 0
    
    def test_overwrite_existing_file(self, temp_dir):
        """Test overwriting existing file."""
        text_path = temp_dir / "existing.txt"
        
        # Create initial file
        with open(text_path, 'w') as f:
            f.write("Old content")
        
        node = TextWriterNode(node_id="text-writer", name="Text Writer")
        result = node.execute({
            "file_path": str(text_path),
            "content": "New content"
        })
        
        with open(text_path, 'r') as f:
            content = f.read()
            assert content == "New content"
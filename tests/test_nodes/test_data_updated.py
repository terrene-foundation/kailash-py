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


class TestCSVReader:
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
        node = CSVReader(file_path="/nonexistent/file.csv")
        
        with pytest.raises(NodeExecutionError):
            node.execute()


class TestJSONReader:
    """Test JSON reader node."""
    
    def test_read_json_success(self, temp_dir):
        """Test successful JSON reading."""
        json_path = temp_dir / "test.json"
        test_data = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ],
            "count": 2
        }
        
        with open(json_path, 'w') as f:
            json.dump(test_data, f)
        
        node = JSONReader(file_path=str(json_path))
        result = node.execute()
        
        assert "data" in result
        assert result["data"] == test_data
    
    def test_read_json_empty_file(self, temp_dir):
        """Test reading empty JSON file."""
        json_path = temp_dir / "empty.json"
        json_path.touch()
        
        node = JSONReader(file_path=str(json_path))
        
        with pytest.raises(NodeExecutionError):
            node.execute()


class TestTextReader:
    """Test text reader node."""
    
    def test_read_text_success(self, temp_dir):
        """Test successful text reading."""
        text_path = temp_dir / "test.txt"
        test_content = "Line 1\nLine 2\nLine 3"
        
        with open(text_path, 'w') as f:
            f.write(test_content)
        
        node = TextReader(file_path=str(text_path))
        result = node.execute()
        
        assert "text" in result  # TextReader returns 'text' not 'content'
        assert result["text"] == test_content
    
    def test_read_text_with_encoding(self, temp_dir):
        """Test reading text with specific encoding."""
        text_path = temp_dir / "test.txt"
        test_content = "Hello World"
        
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        node = TextReader(file_path=str(text_path), encoding='utf-8')
        result = node.execute()
        
        assert result["text"] == test_content


class TestCSVWriter:
    """Test CSV writer node."""
    
    def test_write_csv_success(self, temp_dir):
        """Test successful CSV writing."""
        csv_path = temp_dir / "output.csv"
        test_data = [
            {'name': 'Alice', 'age': 30},
            {'name': 'Bob', 'age': 25}
        ]
        
        node = CSVWriter(file_path=str(csv_path), data=test_data)
        result = node.execute()
        
        assert result["rows_written"] == 2
        assert csv_path.exists()
        
        # Verify content
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]['name'] == 'Alice'
            assert rows[0]['age'] == '30'


class TestJSONWriter:
    """Test JSON writer node."""
    
    def test_write_json_success(self, temp_dir):
        """Test successful JSON writing."""
        json_path = temp_dir / "output.json"
        test_data = {"key": "value", "number": 42}
        
        node = JSONWriter(file_path=str(json_path), data=test_data)
        result = node.execute()
        
        assert result["file_path"] == str(json_path)
        assert json_path.exists()
        
        # Verify content
        with open(json_path, 'r') as f:
            written_data = json.load(f)
            assert written_data == test_data
    
    def test_write_json_pretty(self, temp_dir):
        """Test writing pretty-printed JSON."""
        json_path = temp_dir / "output.json"
        test_data = {"nested": {"key": "value"}}
        
        # Use indent parameter instead of pretty
        node = JSONWriter(file_path=str(json_path), data=test_data, indent=4)
        result = node.execute()
        
        assert json_path.exists()
        
        # Pretty JSON should be larger due to indentation
        with open(json_path, 'r') as f:
            content = f.read()
            # Check that it has indentation (multiple spaces)
            assert "    " in content  # 4 spaces for indent=4


class TestTextWriter:
    """Test text writer node."""
    
    def test_write_text_success(self, temp_dir):
        """Test successful text writing."""
        text_path = temp_dir / "output.txt"
        test_content = "Hello\nWorld"
        
        # TextWriter expects 'text' parameter, not 'content'
        node = TextWriter(file_path=str(text_path), text=test_content)
        result = node.execute()
        
        assert result["bytes_written"] == len(test_content)
        assert text_path.exists()
        
        # Verify content
        with open(text_path, 'r') as f:
            written_content = f.read()
            assert written_content == test_content
    
    def test_write_text_append(self, temp_dir):
        """Test appending text to existing file."""
        text_path = temp_dir / "output.txt"
        
        # Write initial content
        initial = "First line\n"
        with open(text_path, 'w') as f:
            f.write(initial)
        
        # Append more content
        append_content = "Second line"
        node = TextWriter(file_path=str(text_path), text=append_content, append=True)
        result = node.execute()
        
        # Verify combined content
        with open(text_path, 'r') as f:
            full_content = f.read()
            assert full_content == initial + append_content
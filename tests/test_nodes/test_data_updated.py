"""Updated tests for data nodes using current API."""

import pytest
import tempfile
import csv
import json
from pathlib import Path
from typing import Dict, Any

from kailash.nodes.data.readers import CSVReader, JSONReader, TextReader
from kailash.nodes.data.writers import CSVWriter, JSONWriter, TextWriter
from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


class TestCSVReader:
    """Test CSV reader node."""
    
    def test_csv_reader_init(self):
        """Test CSV reader initialization."""
        reader = CSVReader(file_path="test.csv")
        params = reader.get_parameters()
        
        assert "file_path" in params
        assert "headers" in params
        assert "delimiter" in params
        assert params["file_path"].required is True
        assert params["headers"].default is True
        assert params["delimiter"].default == ","
    
    def test_read_csv_with_headers(self, temp_dir):
        """Test reading CSV file with headers."""
        # Create test CSV file
        csv_path = temp_dir / "test.csv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'age', 'city'])
            writer.writeheader()
            writer.writerow({'name': 'Alice', 'age': '30', 'city': 'New York'})
            writer.writerow({'name': 'Bob', 'age': '25', 'city': 'San Francisco'})
        
        reader = CSVReader(file_path=str(csv_path), headers=True)
        result = reader.execute()
        
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["data"][0] == {'name': 'Alice', 'age': '30', 'city': 'New York'}
        assert result["data"][1] == {'name': 'Bob', 'age': '25', 'city': 'San Francisco'}
    
    def test_read_csv_without_headers(self, temp_dir):
        """Test reading CSV file without headers."""
        csv_path = temp_dir / "test.csv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Alice', '30', 'New York'])
            writer.writerow(['Bob', '25', 'San Francisco'])
        
        reader = CSVReader(file_path=str(csv_path), headers=False)
        result = reader.execute()
        
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["data"][0] == ['Alice', '30', 'New York']
        assert result["data"][1] == ['Bob', '25', 'San Francisco']
    
    def test_read_csv_custom_delimiter(self, temp_dir):
        """Test reading CSV with custom delimiter."""
        csv_path = temp_dir / "test.tsv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['name', 'value'])
            writer.writerow(['Item1', '100'])
            writer.writerow(['Item2', '200'])
        
        reader = CSVReader(file_path=str(csv_path), headers=False, delimiter='\t')
        result = reader.execute()
        
        assert len(result["data"]) == 3
        assert result["data"][0] == ['name', 'value']
        assert result["data"][1] == ['Item1', '100']
    
    def test_read_csv_file_not_found(self):
        """Test error handling for missing file."""
        reader = CSVReader(file_path="nonexistent.csv")
        
        with pytest.raises(NodeExecutionError) as exc_info:
            reader.execute()
        
        assert "No such file or directory" in str(exc_info.value) or "cannot find the file" in str(exc_info.value)
    
    def test_csv_reader_output_schema(self):
        """Test CSV reader output schema."""
        reader = CSVReader(file_path="test.csv")
        schema = reader.get_output_schema()
        
        assert "data" in schema
        assert schema["data"].required is True
        assert schema["data"].type == list


class TestJSONReader:
    """Test JSON reader node."""
    
    def test_json_reader_init(self):
        """Test JSON reader initialization."""
        reader = JSONReader(file_path="test.json")
        params = reader.get_parameters()
        
        assert "file_path" in params
        assert params["file_path"].required is True
    
    def test_read_json_file(self, temp_dir):
        """Test reading JSON file."""
        json_path = temp_dir / "test.json"
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False}
            ],
            "metadata": {"version": "1.0", "created": "2023-01-01"}
        }
        
        with open(json_path, 'w') as f:
            json.dump(test_data, f)
        
        reader = JSONReader(file_path=str(json_path))
        result = reader.execute()
        
        assert "data" in result
        assert result["data"] == test_data
        assert len(result["data"]["users"]) == 2
        assert result["data"]["metadata"]["version"] == "1.0"
    
    def test_read_json_array(self, temp_dir):
        """Test reading JSON array."""
        json_path = temp_dir / "array.json"
        test_data = [
            {"name": "Alice", "score": 95},
            {"name": "Bob", "score": 87},
            {"name": "Charlie", "score": 92}
        ]
        
        with open(json_path, 'w') as f:
            json.dump(test_data, f)
        
        reader = JSONReader(file_path=str(json_path))
        result = reader.execute()
        
        assert result["data"] == test_data
        assert len(result["data"]) == 3
    
    def test_read_json_invalid_file(self, temp_dir):
        """Test error handling for invalid JSON."""
        json_path = temp_dir / "invalid.json"
        with open(json_path, 'w') as f:
            f.write('{"invalid": json content}')
        
        reader = JSONReader(file_path=str(json_path))
        
        with pytest.raises(NodeExecutionError) as exc_info:
            reader.execute()
        
        assert "JSON decode error" in str(exc_info.value) or "Expecting" in str(exc_info.value)


class TestTextReader:
    """Test text reader node."""
    
    def test_text_reader_init(self):
        """Test text reader initialization."""
        reader = TextReader(file_path="test.txt")
        params = reader.get_parameters()
        
        assert "file_path" in params
        assert "encoding" in params
        assert params["file_path"].required is True
        assert params["encoding"].default == "utf-8"
    
    def test_read_text_file(self, temp_dir):
        """Test reading text file."""
        text_path = temp_dir / "test.txt"
        test_content = "Hello, World!\nThis is a test file.\nLine 3."
        
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        reader = TextReader(file_path=str(text_path))
        result = reader.execute()
        
        assert "data" in result
        assert result["data"] == test_content
    
    def test_read_text_file_custom_encoding(self, temp_dir):
        """Test reading text file with custom encoding."""
        text_path = temp_dir / "test_latin1.txt"
        test_content = "Café, naïve, résumé"
        
        with open(text_path, 'w', encoding='latin-1') as f:
            f.write(test_content)
        
        reader = TextReader(file_path=str(text_path), encoding="latin-1")
        result = reader.execute()
        
        assert result["data"] == test_content


class TestCSVWriter:
    """Test CSV writer node."""
    
    def test_csv_writer_init(self):
        """Test CSV writer initialization."""
        writer = CSVWriter(file_path="output.csv")
        params = writer.get_parameters()
        
        assert "file_path" in params
        assert "data" in params
        assert "headers" in params
        assert params["file_path"].required is True
        assert params["data"].required is True
    
    def test_write_csv_with_headers(self, temp_dir):
        """Test writing CSV file with headers."""
        csv_path = temp_dir / "output.csv"
        test_data = [
            {'name': 'Alice', 'age': 30, 'city': 'New York'},
            {'name': 'Bob', 'age': 25, 'city': 'San Francisco'}
        ]
        
        writer = CSVWriter(file_path=str(csv_path))
        result = writer.execute(data=test_data)
        
        assert "file_path" in result
        assert result["file_path"] == str(csv_path)
        
        # Verify file was written correctly
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        assert len(rows) == 2
        assert rows[0]['name'] == 'Alice'
        assert rows[0]['age'] == '30'
        assert rows[1]['name'] == 'Bob'
    
    def test_write_csv_no_headers(self, temp_dir):
        """Test writing CSV file without headers."""
        csv_path = temp_dir / "output.csv"
        test_data = [
            ['Alice', '30', 'New York'],
            ['Bob', '25', 'San Francisco']
        ]
        
        writer = CSVWriter(file_path=str(csv_path))
        result = writer.execute(data=test_data, headers=None)
        
        # Verify file was written correctly
        with open(csv_path, 'r', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        assert len(rows) == 2
        assert rows[0] == ['Alice', '30', 'New York']
        assert rows[1] == ['Bob', '25', 'San Francisco']
    
    def test_write_csv_custom_headers(self, temp_dir):
        """Test writing CSV file with custom headers."""
        csv_path = temp_dir / "output.csv"
        test_data = [
            {'first_name': 'Alice', 'years': 30},
            {'first_name': 'Bob', 'years': 25}
        ]
        custom_headers = ['First Name', 'Age']
        
        writer = CSVWriter(file_path=str(csv_path))
        result = writer.execute(data=test_data, headers=custom_headers)
        
        # Verify file was written correctly
        with open(csv_path, 'r', newline='') as f:
            content = f.read()
            
        assert 'First Name,Age' in content


class TestJSONWriter:
    """Test JSON writer node."""
    
    def test_json_writer_init(self):
        """Test JSON writer initialization."""
        writer = JSONWriter(file_path="output.json")
        params = writer.get_parameters()
        
        assert "file_path" in params
        assert "data" in params
        assert "indent" in params
        assert params["file_path"].required is True
        assert params["data"].required is True
        assert params["indent"].default == 2
    
    def test_write_json_file(self, temp_dir):
        """Test writing JSON file."""
        json_path = temp_dir / "output.json"
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False}
            ],
            "metadata": {"version": "1.0", "created": "2023-01-01"}
        }
        
        writer = JSONWriter(file_path=str(json_path))
        result = writer.execute(data=test_data)
        
        assert "file_path" in result
        assert result["file_path"] == str(json_path)
        
        # Verify file was written correctly
        with open(json_path, 'r') as f:
            written_data = json.load(f)
            
        assert written_data == test_data
    
    def test_write_json_no_indent(self, temp_dir):
        """Test writing JSON file without indentation."""
        json_path = temp_dir / "compact.json"
        test_data = {"key": "value", "number": 42}
        
        writer = JSONWriter(file_path=str(json_path))
        result = writer.execute(data=test_data, indent=None)
        
        # Verify file was written compactly
        with open(json_path, 'r') as f:
            content = f.read()
            
        # Compact JSON should not have extra whitespace
        assert '\n' not in content or content.count('\n') <= 1


class TestTextWriter:
    """Test text writer node."""
    
    def test_text_writer_init(self):
        """Test text writer initialization."""
        writer = TextWriter(file_path="output.txt")
        params = writer.get_parameters()
        
        assert "file_path" in params
        assert "text" in params
        assert "encoding" in params
        assert params["file_path"].required is True
        assert params["text"].required is True
        assert params["encoding"].default == "utf-8"
    
    def test_write_text_file(self, temp_dir):
        """Test writing text file."""
        text_path = temp_dir / "output.txt"
        test_content = "Hello, World!\nThis is a test file.\nLine 3."
        
        writer = TextWriter(file_path=str(text_path))
        result = writer.execute(text=test_content)
        
        assert "file_path" in result
        assert result["file_path"] == str(text_path)
        
        # Verify file was written correctly
        with open(text_path, 'r', encoding='utf-8') as f:
            written_content = f.read()
            
        assert written_content == test_content
    
    def test_write_text_file_custom_encoding(self, temp_dir):
        """Test writing text file with custom encoding."""
        text_path = temp_dir / "output_latin1.txt"
        test_content = "Café, naïve, résumé"
        
        writer = TextWriter(file_path=str(text_path))
        result = writer.execute(text=test_content, encoding="latin-1")
        
        # Verify file was written with correct encoding
        with open(text_path, 'r', encoding='latin-1') as f:
            written_content = f.read()
            
        assert written_content == test_content


class TestDataNodeIntegration:
    """Test integration between data readers and writers."""
    
    def test_csv_round_trip(self, temp_dir):
        """Test reading CSV, then writing it back."""
        # Create initial CSV
        input_path = temp_dir / "input.csv"
        with open(input_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'score'])
            writer.writeheader()
            writer.writerow({'name': 'Alice', 'score': '95'})
            writer.writerow({'name': 'Bob', 'score': '87'})
        
        # Read the CSV
        reader = CSVReader(file_path=str(input_path), headers=True)
        read_result = reader.execute()
        
        # Write it back to a new file
        output_path = temp_dir / "output.csv"
        writer = CSVWriter(file_path=str(output_path))
        write_result = writer.execute(data=read_result["data"])
        
        # Verify round trip
        reader2 = CSVReader(file_path=str(output_path), headers=True)
        final_result = reader2.execute()
        
        assert final_result["data"] == read_result["data"]
    
    def test_json_round_trip(self, temp_dir):
        """Test reading JSON, then writing it back."""
        # Create initial JSON
        input_path = temp_dir / "input.json"
        test_data = {"items": [{"id": 1, "name": "test"}], "count": 1}
        
        with open(input_path, 'w') as f:
            json.dump(test_data, f)
        
        # Read the JSON
        reader = JSONReader(file_path=str(input_path))
        read_result = reader.execute()
        
        # Write it back to a new file
        output_path = temp_dir / "output.json"
        writer = JSONWriter(file_path=str(output_path))
        write_result = writer.execute(data=read_result["data"])
        
        # Verify round trip
        reader2 = JSONReader(file_path=str(output_path))
        final_result = reader2.execute()
        
        assert final_result["data"] == test_data


if __name__ == "__main__":
    pytest.main([__file__])
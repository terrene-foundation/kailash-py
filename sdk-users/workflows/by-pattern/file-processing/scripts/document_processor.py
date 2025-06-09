#!/usr/bin/env python3
"""
Document Processing Workflow
============================

Demonstrates file processing patterns using Kailash SDK.
This workflow processes multiple document types, extracts content,
and generates structured outputs.

Patterns demonstrated:
1. File type detection and routing
2. Content extraction and transformation
3. Multi-format document processing
4. Batch file processing
"""

import json
import os

from kailash import Workflow
from kailash.nodes.data import (
    JSONWriterNode,
)
from kailash.nodes.code import PythonCodeNode
from kailash.runtime import LocalRuntime


def create_document_processing_workflow() -> Workflow:
    """Create a document processing workflow for multiple file types."""
    workflow = Workflow(
        workflow_id="document_processing_001",
        name="document_processing_workflow",
        description="Process multiple document types and extract structured data",
    )

    # === FILE DISCOVERY ===

    # Discover files in the input directory using PythonCodeNode
    file_discoverer = PythonCodeNode(
        name="file_discoverer",
        code="""
# Discover files in input directory
import os
from datetime import datetime

# Scan actual directory
input_dir = "data/inputs"
discovered_files = []

try:
    for filename in os.listdir(input_dir):
        file_path = os.path.join(input_dir, filename)
        
        # Skip directories
        if os.path.isdir(file_path):
            continue
        
        # Get file info
        file_stat = os.stat(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Map extensions to types
        ext_to_type = {
            '.csv': 'csv',
            '.json': 'json',
            '.txt': 'txt',
            '.xml': 'xml',
            '.md': 'markdown'
        }
        
        file_type = ext_to_type.get(file_ext, 'unknown')
        
        # Guess mime type based on extension
        ext_to_mime = {
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.xml': 'application/xml',
            '.md': 'text/markdown'
        }
        mime_type = ext_to_mime.get(file_ext, 'application/octet-stream')
        
        discovered_files.append({
            "file_path": file_path,
            "file_name": filename,
            "file_type": file_type,
            "file_size": file_stat.st_size,
            "mime_type": mime_type,
            "discovered_at": datetime.now().isoformat()
        })
    
    print(f"Discovered {len(discovered_files)} files in {input_dir}")
    
except FileNotFoundError:
    print(f"Input directory '{input_dir}' not found")
    discovered_files = []
except Exception as e:
    print(f"Error discovering files: {e}")
    discovered_files = []

# Group files by type for processing
files_by_type = {}
for file_info in discovered_files:
    file_type = file_info["file_type"]
    if file_type not in files_by_type:
        files_by_type[file_type] = []
    files_by_type[file_type].append(file_info)

# Store results - PythonCodeNode automatically wraps in 'result' key
result = {
    "discovered_files": discovered_files,
    "files_by_type": files_by_type,
    "total_files": len(discovered_files),
    "file_types": list(files_by_type.keys()),
    "discovery_summary": {
        file_type: len(files) for file_type, files in files_by_type.items()
    }
}
""",
    )
    workflow.add_node("file_discoverer", file_discoverer)

    # === FILE TYPE PROCESSING ===

    # Process CSV files using PythonCodeNode to read real files
    csv_processor = PythonCodeNode(
        name="csv_processor",
        code="""
# Process CSV files by reading actual content
import csv
from datetime import datetime

# Get discovered files from discovery_data
files_by_type = discovery_data.get("files_by_type", {})
csv_files_info = files_by_type.get("csv", [])

print(f"Processing {len(csv_files_info)} CSV files")

processed_csv = []
for file_info in csv_files_info:
    file_path = file_info["file_path"]
    
    try:
        # Read actual CSV file
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            content = list(reader)
        
        print(f"Read {len(content)} records from {file_path}")
        
        # Extract statistics
        active_count = sum(1 for record in content if record.get("status") == "active")
        inactive_count = len(content) - active_count
        
        # Get unique email domains
        email_domains = []
        for record in content:
            email = record.get("email", "")
            if "@" in email:
                domain = email.split("@")[1]
                if domain not in email_domains:
                    email_domains.append(domain)
        
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": "csv",
                "size": file_info["file_size"]
            },
            "processing_result": {
                "total_records": len(content),
                "active_customers": active_count,
                "inactive_customers": inactive_count,
                "email_domains": email_domains,
                "columns": list(content[0].keys()) if content else [],
                "sample_records": content[:3]  # First 3 records as sample
            },
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "csv_processor"
            }
        }
        processed_csv.append(processed_file)
        
    except Exception as e:
        print(f"Error processing CSV file {file_path}: {e}")
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": "csv"
            },
            "error": str(e),
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "csv_processor"
            }
        }
        processed_csv.append(processed_file)

# Store results - PythonCodeNode automatically wraps in 'result' key
result = {
    "processed_files": processed_csv,
    "file_count": len(processed_csv),
    "total_records": sum(f["processing_result"]["total_records"] for f in processed_csv if "processing_result" in f)
}
""",
    )
    workflow.add_node("csv_processor", csv_processor)
    workflow.connect(
        "file_discoverer", "csv_processor", mapping={"result": "discovery_data"}
    )

    # Process JSON files using PythonCodeNode to read real files
    json_processor = PythonCodeNode(
        name="json_processor",
        code="""
# Process JSON files by reading actual content
import json
from datetime import datetime

# Get discovered files from discovery_data
files_by_type = discovery_data.get("files_by_type", {})
json_files_info = files_by_type.get("json", [])

print(f"Processing {len(json_files_info)} JSON files")

processed_json = []
for file_info in json_files_info:
    file_path = file_info["file_path"]
    
    try:
        # Read actual JSON file
        with open(file_path, 'r') as f:
            content = json.load(f)
        
        print(f"Read JSON data from {file_path}")
        
        # Extract analytics based on content structure
        if "transactions" in content:
            # Transaction log processing
            transactions = content.get("transactions", [])
            total_amount = sum(txn.get("amount", 0) for txn in transactions)
            customer_ids = list(set(txn.get("customer_id") for txn in transactions if txn.get("customer_id")))
            avg_amount = total_amount / len(transactions) if transactions else 0
            
            processing_result = {
                "data_type": "transaction_log",
                "transaction_count": len(transactions),
                "total_amount": total_amount,
                "average_amount": round(avg_amount, 2),
                "unique_customers": len(customer_ids),
                "customer_ids": customer_ids,
                "metadata": content.get("metadata", {})
            }
        else:
            # Generic JSON processing
            processing_result = {
                "data_type": "generic",
                "key_count": len(content) if isinstance(content, dict) else 0,
                "is_array": isinstance(content, list),
                "array_length": len(content) if isinstance(content, list) else 0,
                "keys": list(content.keys()) if isinstance(content, dict) else [],
                "sample": str(content)[:200] + "..." if len(str(content)) > 200 else str(content)
            }
        
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": "json",
                "size": file_info["file_size"]
            },
            "processing_result": processing_result,
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "json_processor"
            }
        }
        processed_json.append(processed_file)
        
    except Exception as e:
        print(f"Error processing JSON file {file_path}: {e}")
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": "json"
            },
            "error": str(e),
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "json_processor"
            }
        }
        processed_json.append(processed_file)

# Store results - PythonCodeNode automatically wraps in 'result' key
result = {
    "processed_files": processed_json,
    "file_count": len(processed_json),
    "total_transactions": sum(f["processing_result"].get("transaction_count", 0) for f in processed_json if "processing_result" in f)
}
""",
    )
    workflow.add_node("json_processor", json_processor)
    workflow.connect(
        "file_discoverer", "json_processor", mapping={"result": "discovery_data"}
    )

    # Process text and other files using PythonCodeNode to read real files
    text_processor = PythonCodeNode(
        name="text_processor",
        code="""
# Process text and other file types by reading actual content
import re
from datetime import datetime

# Get discovered files from discovery_data
files_by_type = discovery_data.get("files_by_type", {})

# Process txt, xml, and markdown files
file_types_to_process = ["txt", "xml", "markdown"]
all_text_files = []

for file_type in file_types_to_process:
    files_info = files_by_type.get(file_type, [])
    all_text_files.extend(files_info)

print(f"Processing {len(all_text_files)} text-based files")

processed_text = []
for file_info in all_text_files:
    file_path = file_info["file_path"]
    file_type = file_info["file_type"]
    
    try:
        # Read actual text file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"Read {len(content)} characters from {file_path}")
        
        # Extract text analytics
        word_count = len(content.split())
        line_count = len(content.split("\\n"))
        char_count = len(content)
        
        # File-type specific processing
        if file_type == "txt":
            # Find placeholders/variables (things in {})
            placeholders = re.findall(r'\\{([^}]+)\\}', content)
            specific_info = {
                "placeholders": placeholders,
                "placeholder_count": len(placeholders)
            }
        elif file_type == "xml":
            # Extract XML tags
            tags = re.findall(r'<([^/>]+)>', content)
            unique_tags = list(set(tags))
            specific_info = {
                "unique_tags": unique_tags,
                "tag_count": len(unique_tags)
            }
        elif file_type == "markdown":
            # Extract markdown headers
            headers = re.findall(r'^#+\\s+(.+)$', content, re.MULTILINE)
            specific_info = {
                "headers": headers,
                "header_count": len(headers)
            }
        else:
            specific_info = {}
        
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": file_type,
                "size": file_info["file_size"]
            },
            "processing_result": {
                "word_count": word_count,
                "line_count": line_count,
                "character_count": char_count,
                "preview": content[:200] + "..." if len(content) > 200 else content,
                **specific_info
            },
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "text_processor"
            }
        }
        processed_text.append(processed_file)
        
    except Exception as e:
        print(f"Error processing text file {file_path}: {e}")
        processed_file = {
            "file_info": {
                "path": file_info["file_path"],
                "name": file_info["file_name"],
                "type": file_type
            },
            "error": str(e),
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "processor": "text_processor"
            }
        }
        processed_text.append(processed_file)

# Store results - PythonCodeNode automatically wraps in 'result' key
result = {
    "processed_files": processed_text,
    "file_count": len(processed_text),
    "total_words": sum(f["processing_result"]["word_count"] for f in processed_text if "processing_result" in f)
}
""",
    )
    workflow.add_node("text_processor", text_processor)
    workflow.connect(
        "file_discoverer", "text_processor", mapping={"result": "discovery_data"}
    )

    # === MERGE PROCESSING RESULTS ===

    # Merge all processing results using PythonCodeNode
    result_merger = PythonCodeNode(
        name="result_merger",
        code="""
# Merge processing results from all processors
# Inputs come as csv_result, json_result, text_result (wrapped in 'result' key)

all_results = []

# Add CSV processor results
if csv_result and isinstance(csv_result, dict):
    all_results.append(csv_result)

# Add JSON processor results
if json_result and isinstance(json_result, dict):
    all_results.append(json_result)

# Add text processor results
if text_result and isinstance(text_result, dict):
    all_results.append(text_result)

print(f"Merged {len(all_results)} processor results")

# Store results - PythonCodeNode automatically wraps in 'result' key
result = all_results
""",
    )
    workflow.add_node("result_merger", result_merger)
    workflow.connect("csv_processor", "result_merger", mapping={"result": "csv_result"})
    workflow.connect(
        "json_processor", "result_merger", mapping={"result": "json_result"}
    )
    workflow.connect(
        "text_processor", "result_merger", mapping={"result": "text_result"}
    )

    # === SUMMARY GENERATION ===

    # Generate final processing summary using PythonCodeNode
    summary_generator = PythonCodeNode(
        name="summary_generator",
        code="""
# Generate comprehensive processing summary
from datetime import datetime

# Input comes as 'merged_results' which is a list of processor results
processing_results = merged_results if isinstance(merged_results, list) else []

print(f"Generating summary from {len(processing_results)} processor results")

# Aggregate all processing results
all_processed_files = []
total_files = 0
files_by_type = {}
processing_stats = {}
failed_files = 0

for result_set in processing_results:
    if isinstance(result_set, dict):
        processed_files = result_set.get("processed_files", [])
        all_processed_files.extend(processed_files)
        total_files += result_set.get("file_count", 0)
        
        # Aggregate by file type
        for file_info in processed_files:
            # Check for errors
            if "error" in file_info:
                failed_files += 1
                continue
                
            file_type = file_info.get("file_info", {}).get("type", "unknown")
            if file_type not in files_by_type:
                files_by_type[file_type] = 0
            files_by_type[file_type] += 1
            
            # Collect processing stats
            if file_type not in processing_stats:
                processing_stats[file_type] = {}
            
            proc_result = file_info.get("processing_result", {})
            if file_type == "csv":
                processing_stats[file_type]["total_records"] = processing_stats[file_type].get("total_records", 0) + proc_result.get("total_records", 0)
                processing_stats[file_type]["columns_found"] = proc_result.get("columns", [])
            elif file_type == "json":
                if proc_result.get("data_type") == "transaction_log":
                    processing_stats[file_type]["total_transactions"] = processing_stats[file_type].get("total_transactions", 0) + proc_result.get("transaction_count", 0)
                    processing_stats[file_type]["total_amount"] = processing_stats[file_type].get("total_amount", 0) + proc_result.get("total_amount", 0)
            elif file_type in ["txt", "xml", "markdown"]:
                processing_stats[file_type]["total_words"] = processing_stats[file_type].get("total_words", 0) + proc_result.get("word_count", 0)
                processing_stats[file_type]["total_lines"] = processing_stats[file_type].get("total_lines", 0) + proc_result.get("line_count", 0)

# Generate final summary
summary = {
    "processing_summary": {
        "total_files_processed": total_files,
        "files_by_type": files_by_type,
        "processing_stats": processing_stats,
        "successful_files": total_files - failed_files,
        "failed_files": failed_files
    },
    "detailed_results": all_processed_files,
    "metadata": {
        "processed_at": datetime.now().isoformat(),
        "workflow_version": "2.0",
        "processor": "document_processing_workflow"
    },
    "recommendations": []
}

# Generate recommendations based on results
if "csv" in files_by_type:
    for file in all_processed_files:
        if file.get("file_info", {}).get("type") == "csv":
            proc_result = file.get("processing_result", {})
            if proc_result.get("inactive_customers", 0) > 0:
                summary["recommendations"].append("Review inactive customers in CSV files")
                break

if "json" in files_by_type:
    summary["recommendations"].append("Analyze transaction patterns in JSON files")

if "txt" in files_by_type or "xml" in files_by_type:
    summary["recommendations"].append("Update text templates with current data")

if "markdown" in files_by_type:
    summary["recommendations"].append("Review documentation for accuracy")

# Store results - PythonCodeNode automatically wraps in 'result' key
result = summary
""",
    )
    workflow.add_node("summary_generator", summary_generator)
    workflow.connect(
        "result_merger", "summary_generator", mapping={"result": "merged_results"}
    )

    # === OUTPUT ===

    # Save processing summary
    summary_writer = JSONWriterNode(
        id="summary_writer", file_path="data/outputs/processing_summary.json"
    )
    workflow.add_node("summary_writer", summary_writer)
    workflow.connect("summary_generator", "summary_writer", mapping={"result": "data"})

    return workflow


def create_sample_input_files():
    """Create sample input files for testing."""
    os.makedirs("data/inputs", exist_ok=True)

    # Create sample CSV
    csv_content = """customer_id,name,email,status
CUST-001,John Doe,john@example.com,active
CUST-002,Jane Smith,jane@example.com,active
CUST-003,Bob Johnson,bob@example.com,inactive"""

    with open("data/inputs/customer_data.csv", "w") as f:
        f.write(csv_content)

    # Create sample JSON
    json_content = {
        "transactions": [
            {
                "id": "TXN-001",
                "customer_id": "CUST-001",
                "amount": 299.99,
                "timestamp": "2024-01-15T09:00:00Z",
            },
            {
                "id": "TXN-002",
                "customer_id": "CUST-002",
                "amount": 149.50,
                "timestamp": "2024-01-15T09:30:00Z",
            },
            {
                "id": "TXN-003",
                "customer_id": "CUST-001",
                "amount": 79.99,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        ],
        "metadata": {"version": "1.0", "generated_at": "2024-01-15T10:30:00Z"},
    }

    with open("data/inputs/transaction_log.json", "w") as f:
        json.dump(json_content, f, indent=2)

    # Create sample text file
    text_content = """Customer Report Template

Total Customers: {total_customers}
Active Customers: {active_customers}
Revenue: ${total_revenue}

Generated on: {report_date}"""

    with open("data/inputs/report_template.txt", "w") as f:
        f.write(text_content)


def run_document_processing():
    """Execute the document processing workflow."""
    workflow = create_document_processing_workflow()
    runtime = LocalRuntime()

    parameters = {}

    try:
        print("Starting Document Processing Workflow...")
        print("🔍 Discovering files...")

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\\n✅ Document Processing Complete!")
        print("📁 Output generated: data/outputs/processing_summary.json")

        # Show summary
        summary_result = result.get("summary_generator", {}).get("result", {})
        processing_summary = summary_result.get("processing_summary", {})

        print("\\n📊 Processing Summary:")
        print(
            f"   - Total files processed: {processing_summary.get('total_files_processed', 0)}"
        )
        print(f"   - Files by type: {processing_summary.get('files_by_type', {})}")
        print(f"   - Successful files: {processing_summary.get('successful_files', 0)}")

        # Show recommendations
        recommendations = summary_result.get("recommendations", [])
        if recommendations:
            print("\\n💡 Recommendations:")
            for rec in recommendations:
                print(f"   - {rec}")

        return result

    except Exception as e:
        print(f"❌ Document Processing failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create sample input files
    create_sample_input_files()
    print("📝 Created sample input files")

    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the document processing workflow
    run_document_processing()

    # Display generated summary
    print("\\n=== Processing Summary Preview ===")
    try:
        with open("data/outputs/processing_summary.json", "r") as f:
            summary = json.load(f)
            print(json.dumps(summary["processing_summary"], indent=2))
    except Exception as e:
        print(f"Could not read summary: {e}")


if __name__ == "__main__":
    main()

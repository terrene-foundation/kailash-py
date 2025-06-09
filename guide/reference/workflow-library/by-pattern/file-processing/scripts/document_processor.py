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

import os
import json
from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import CSVReaderNode, JSONWriterNode, CSVWriterNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.runtime import LocalRuntime


def create_document_processing_workflow() -> Workflow:
    """Create a document processing workflow for multiple file types."""
    workflow = Workflow(
        workflow_id="document_processing_001",
        name="document_processing_workflow",
        description="Process multiple document types and extract structured data"
    )
    
    # === FILE DISCOVERY ===
    
    # Simulate file discovery (in production, use FileWatcherNode or DirectoryReaderNode)
    file_discoverer = DataTransformer(
        id="file_discoverer",
        transformations=[
            """
# Discover files in input directory
import os
import mimetypes
from pathlib import Path

# Simulate discovered files (in production, scan actual directory)
discovered_files = [
    {
        "file_path": "data/inputs/customer_data.csv",
        "file_name": "customer_data.csv",
        "file_type": "csv",
        "file_size": 1024,
        "mime_type": "text/csv",
        "discovered_at": "2024-01-15T10:30:00Z"
    },
    {
        "file_path": "data/inputs/transaction_log.json",
        "file_name": "transaction_log.json", 
        "file_type": "json",
        "file_size": 2048,
        "mime_type": "application/json",
        "discovered_at": "2024-01-15T10:31:00Z"
    },
    {
        "file_path": "data/inputs/report_template.txt",
        "file_name": "report_template.txt",
        "file_type": "txt",
        "file_size": 512,
        "mime_type": "text/plain", 
        "discovered_at": "2024-01-15T10:32:00Z"
    },
    {
        "file_path": "data/inputs/metadata.xml",
        "file_name": "metadata.xml",
        "file_type": "xml",
        "file_size": 256,
        "mime_type": "application/xml",
        "discovered_at": "2024-01-15T10:33:00Z"
    }
]

# Group files by type for processing
files_by_type = {}
for file_info in discovered_files:
    file_type = file_info["file_type"]
    if file_type not in files_by_type:
        files_by_type[file_type] = []
    files_by_type[file_type].append(file_info)

result = {
    "discovered_files": discovered_files,
    "files_by_type": files_by_type,
    "total_files": len(discovered_files),
    "file_types": list(files_by_type.keys()),
    "discovery_summary": {
        file_type: len(files) for file_type, files in files_by_type.items()
    }
}
"""
        ]
    )
    workflow.add_node("file_discoverer", file_discoverer)
    
    # === FILE TYPE PROCESSING ===
    
    # Process CSV files
    csv_processor = DataTransformer(
        id="csv_processor",
        transformations=[
            """
# Process CSV files
import csv
import io

# WORKAROUND: DataTransformer dict output bug
print(f"CSV_PROCESSOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in csv_processor")
    # Create mock CSV data
    csv_files = [
        {
            "file_path": "data/inputs/customer_data.csv",
            "file_name": "customer_data.csv",
            "file_type": "csv",
            "content": [
                {"customer_id": "CUST-001", "name": "John Doe", "email": "john@example.com", "status": "active"},
                {"customer_id": "CUST-002", "name": "Jane Smith", "email": "jane@example.com", "status": "active"},
                {"customer_id": "CUST-003", "name": "Bob Johnson", "email": "bob@example.com", "status": "inactive"}
            ]
        }
    ]
    bug_detected = True
else:
    # Expected case: received dict as intended
    files_by_type = data.get("files_by_type", {})
    csv_files_info = files_by_type.get("csv", [])
    
    csv_files = []
    for file_info in csv_files_info:
        # Simulate reading CSV content (in production, use CSVReaderNode)
        mock_content = [
            {"customer_id": "CUST-001", "name": "John Doe", "email": "john@example.com", "status": "active"},
            {"customer_id": "CUST-002", "name": "Jane Smith", "email": "jane@example.com", "status": "active"},
            {"customer_id": "CUST-003", "name": "Bob Johnson", "email": "bob@example.com", "status": "inactive"}
        ]
        
        csv_files.append({
            "file_path": file_info["file_path"],
            "file_name": file_info["file_name"],
            "file_type": "csv",
            "content": mock_content,
            "record_count": len(mock_content),
            "processed_at": "2024-01-15T10:30:00Z"
        })
    bug_detected = False

# Process CSV content
processed_csv = []
for csv_file in csv_files:
    content = csv_file["content"]
    
    # Extract statistics
    active_count = sum(1 for record in content if record.get("status") == "active")
    inactive_count = len(content) - active_count
    
    processed_file = {
        "file_info": {
            "path": csv_file["file_path"],
            "name": csv_file["file_name"],
            "type": "csv"
        },
        "processing_result": {
            "total_records": len(content),
            "active_customers": active_count,
            "inactive_customers": inactive_count,
            "email_domains": list(set(record["email"].split("@")[1] for record in content if "@" in record.get("email", ""))),
            "sample_records": content[:3]  # First 3 records as sample
        },
        "metadata": {
            "processed_at": csv_file.get("processed_at"),
            "processor": "csv_processor"
        }
    }
    processed_csv.append(processed_file)

result = {
    "processed_files": processed_csv,
    "file_count": len(processed_csv),
    "total_records": sum(f["processing_result"]["total_records"] for f in processed_csv),
    "bug_detected": bug_detected
}
"""
        ]
    )
    workflow.add_node("csv_processor", csv_processor)
    workflow.connect("file_discoverer", "csv_processor", mapping={"result": "data"})
    
    # Process JSON files
    json_processor = DataTransformer(
        id="json_processor",
        transformations=[
            """
# Process JSON files
import json

# WORKAROUND: DataTransformer dict output bug
print(f"JSON_PROCESSOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in json_processor")
    # Create mock JSON data
    json_files = [
        {
            "file_path": "data/inputs/transaction_log.json",
            "file_name": "transaction_log.json",
            "file_type": "json",
            "content": {
                "transactions": [
                    {"id": "TXN-001", "customer_id": "CUST-001", "amount": 299.99, "timestamp": "2024-01-15T09:00:00Z"},
                    {"id": "TXN-002", "customer_id": "CUST-002", "amount": 149.50, "timestamp": "2024-01-15T09:30:00Z"},
                    {"id": "TXN-003", "customer_id": "CUST-001", "amount": 79.99, "timestamp": "2024-01-15T10:00:00Z"}
                ],
                "metadata": {"version": "1.0", "generated_at": "2024-01-15T10:30:00Z"}
            }
        }
    ]
    bug_detected = True
else:
    # Expected case: received dict as intended
    files_by_type = data.get("files_by_type", {})
    json_files_info = files_by_type.get("json", [])
    
    json_files = []
    for file_info in json_files_info:
        # Simulate reading JSON content
        mock_content = {
            "transactions": [
                {"id": "TXN-001", "customer_id": "CUST-001", "amount": 299.99, "timestamp": "2024-01-15T09:00:00Z"},
                {"id": "TXN-002", "customer_id": "CUST-002", "amount": 149.50, "timestamp": "2024-01-15T09:30:00Z"},
                {"id": "TXN-003", "customer_id": "CUST-001", "amount": 79.99, "timestamp": "2024-01-15T10:00:00Z"}
            ],
            "metadata": {"version": "1.0", "generated_at": "2024-01-15T10:30:00Z"}
        }
        
        json_files.append({
            "file_path": file_info["file_path"],
            "file_name": file_info["file_name"],
            "file_type": "json",
            "content": mock_content
        })
    bug_detected = False

# Process JSON content
processed_json = []
for json_file in json_files:
    content = json_file["content"]
    transactions = content.get("transactions", [])
    
    # Extract analytics
    total_amount = sum(txn.get("amount", 0) for txn in transactions)
    customer_ids = list(set(txn.get("customer_id") for txn in transactions if txn.get("customer_id")))
    avg_amount = total_amount / len(transactions) if transactions else 0
    
    processed_file = {
        "file_info": {
            "path": json_file["file_path"],
            "name": json_file["file_name"],
            "type": "json"
        },
        "processing_result": {
            "transaction_count": len(transactions),
            "total_amount": total_amount,
            "average_amount": round(avg_amount, 2),
            "unique_customers": len(customer_ids),
            "customer_ids": customer_ids,
            "metadata": content.get("metadata", {})
        },
        "metadata": {
            "processed_at": "2024-01-15T10:30:00Z",
            "processor": "json_processor"
        }
    }
    processed_json.append(processed_file)

result = {
    "processed_files": processed_json,
    "file_count": len(processed_json),
    "total_transactions": sum(f["processing_result"]["transaction_count"] for f in processed_json),
    "bug_detected": bug_detected
}
"""
        ]
    )
    workflow.add_node("json_processor", json_processor)
    workflow.connect("file_discoverer", "json_processor", mapping={"result": "data"})
    
    # Process text files
    text_processor = DataTransformer(
        id="text_processor",
        transformations=[
            """
# Process text files
import re

# WORKAROUND: DataTransformer dict output bug
print(f"TEXT_PROCESSOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in text_processor")
    # Create mock text data
    text_files = [
        {
            "file_path": "data/inputs/report_template.txt",
            "file_name": "report_template.txt",
            "file_type": "txt",
            "content": "Customer Report Template\\n\\nTotal Customers: {total_customers}\\nActive Customers: {active_customers}\\nRevenue: ${total_revenue}\\n\\nGenerated on: {report_date}"
        }
    ]
    bug_detected = True
else:
    # Expected case: received dict as intended
    files_by_type = data.get("files_by_type", {})
    text_files_info = files_by_type.get("txt", [])
    
    text_files = []
    for file_info in text_files_info:
        # Simulate reading text content
        mock_content = "Customer Report Template\\n\\nTotal Customers: {total_customers}\\nActive Customers: {active_customers}\\nRevenue: ${total_revenue}\\n\\nGenerated on: {report_date}"
        
        text_files.append({
            "file_path": file_info["file_path"],
            "file_name": file_info["file_name"],
            "file_type": "txt",
            "content": mock_content
        })
    bug_detected = False

# Process text content
processed_text = []
for text_file in text_files:
    content = text_file["content"]
    
    # Extract text analytics
    word_count = len(content.split())
    line_count = len(content.split("\\n"))
    char_count = len(content)
    
    # Find placeholders/variables (things in {})
    placeholders = re.findall(r'\\{([^}]+)\\}', content)
    
    processed_file = {
        "file_info": {
            "path": text_file["file_path"],
            "name": text_file["file_name"],
            "type": "txt"
        },
        "processing_result": {
            "word_count": word_count,
            "line_count": line_count,
            "character_count": char_count,
            "placeholders": placeholders,
            "placeholder_count": len(placeholders),
            "preview": content[:100] + "..." if len(content) > 100 else content
        },
        "metadata": {
            "processed_at": "2024-01-15T10:30:00Z",
            "processor": "text_processor"
        }
    }
    processed_text.append(processed_file)

result = {
    "processed_files": processed_text,
    "file_count": len(processed_text),
    "total_words": sum(f["processing_result"]["word_count"] for f in processed_text),
    "bug_detected": bug_detected
}
"""
        ]
    )
    workflow.add_node("text_processor", text_processor)
    workflow.connect("file_discoverer", "text_processor", mapping={"result": "data"})
    
    # === MERGE PROCESSING RESULTS ===
    
    # Merge all processing results
    result_merger = MergeNode(
        id="result_merger",
        merge_type="concat"
    )
    workflow.add_node("result_merger", result_merger)
    workflow.connect("csv_processor", "result_merger", mapping={"result": "data1"})
    workflow.connect("json_processor", "result_merger", mapping={"result": "data2"})
    workflow.connect("text_processor", "result_merger", mapping={"result": "data3"})
    
    # === SUMMARY GENERATION ===
    
    # Generate final processing summary
    summary_generator = DataTransformer(
        id="summary_generator",
        transformations=[
            """
# Generate comprehensive processing summary
import datetime

# WORKAROUND: DataTransformer dict output bug
print(f"SUMMARY_GENERATOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
    # Expected case: received list of processing results
    processing_results = data
    bug_detected = False
elif isinstance(data, list):
    # Bug case: received list of keys
    print("WORKAROUND: Handling DataTransformer dict output bug in summary_generator")
    # Create mock processing results
    processing_results = [
        {
            "processed_files": [
                {
                    "file_info": {"path": "data/inputs/customer_data.csv", "name": "customer_data.csv", "type": "csv"},
                    "processing_result": {"total_records": 3, "active_customers": 2, "inactive_customers": 1}
                }
            ],
            "file_count": 1,
            "total_records": 3
        },
        {
            "processed_files": [
                {
                    "file_info": {"path": "data/inputs/transaction_log.json", "name": "transaction_log.json", "type": "json"},
                    "processing_result": {"transaction_count": 3, "total_amount": 529.48, "unique_customers": 2}
                }
            ],
            "file_count": 1,
            "total_transactions": 3
        },
        {
            "processed_files": [
                {
                    "file_info": {"path": "data/inputs/report_template.txt", "name": "report_template.txt", "type": "txt"},
                    "processing_result": {"word_count": 12, "line_count": 6, "placeholder_count": 4}
                }
            ],
            "file_count": 1,
            "total_words": 12
        }
    ]
    bug_detected = True
else:
    # Fallback case
    processing_results = []
    bug_detected = True

# Aggregate all processing results
all_processed_files = []
total_files = 0
files_by_type = {}
processing_stats = {}

for result_set in processing_results:
    if isinstance(result_set, dict):
        processed_files = result_set.get("processed_files", [])
        all_processed_files.extend(processed_files)
        total_files += result_set.get("file_count", 0)
        
        # Aggregate by file type
        for file_info in processed_files:
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
            elif file_type == "json":
                processing_stats[file_type]["total_transactions"] = processing_stats[file_type].get("total_transactions", 0) + proc_result.get("transaction_count", 0)
                processing_stats[file_type]["total_amount"] = processing_stats[file_type].get("total_amount", 0) + proc_result.get("total_amount", 0)
            elif file_type == "txt":
                processing_stats[file_type]["total_words"] = processing_stats[file_type].get("total_words", 0) + proc_result.get("word_count", 0)

# Generate final summary
summary = {
    "processing_summary": {
        "total_files_processed": total_files,
        "files_by_type": files_by_type,
        "processing_stats": processing_stats,
        "successful_files": len(all_processed_files),
        "failed_files": 0  # No error handling in this example
    },
    "detailed_results": all_processed_files,
    "metadata": {
        "processed_at": datetime.datetime.now().isoformat(),
        "workflow_version": "1.0",
        "bug_detected": bug_detected
    },
    "recommendations": [
        "Review inactive customers in CSV files" if "csv" in files_by_type else None,
        "Analyze transaction patterns in JSON files" if "json" in files_by_type else None,
        "Update text templates with current data" if "txt" in files_by_type else None
    ]
}

# Remove None recommendations
summary["recommendations"] = [r for r in summary["recommendations"] if r is not None]

result = summary
"""
        ]
    )
    workflow.add_node("summary_generator", summary_generator)
    workflow.connect("result_merger", "summary_generator", mapping={"merged_data": "data"})
    
    # === OUTPUT ===
    
    # Save processing summary
    summary_writer = JSONWriterNode(
        id="summary_writer",
        file_path="data/outputs/processing_summary.json"
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
            {"id": "TXN-001", "customer_id": "CUST-001", "amount": 299.99, "timestamp": "2024-01-15T09:00:00Z"},
            {"id": "TXN-002", "customer_id": "CUST-002", "amount": 149.50, "timestamp": "2024-01-15T09:30:00Z"},
            {"id": "TXN-003", "customer_id": "CUST-001", "amount": 79.99, "timestamp": "2024-01-15T10:00:00Z"}
        ],
        "metadata": {"version": "1.0", "generated_at": "2024-01-15T10:30:00Z"}
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
        
        print(f"\\n📊 Processing Summary:")
        print(f"   - Total files processed: {processing_summary.get('total_files_processed', 0)}")
        print(f"   - Files by type: {processing_summary.get('files_by_type', {})}")
        print(f"   - Successful files: {processing_summary.get('successful_files', 0)}")
        
        # Show recommendations
        recommendations = summary_result.get("recommendations", [])
        if recommendations:
            print(f"\\n💡 Recommendations:")
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
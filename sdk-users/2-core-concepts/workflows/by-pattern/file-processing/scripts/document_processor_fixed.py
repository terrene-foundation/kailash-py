#!/usr/bin/env python3
"""
Fixed Document Processing Workflow
==================================

Demonstrates file processing patterns using Kailash SDK with the improved base nodes.
This workflow uses DirectoryReaderNode for file discovery and proper reader nodes
for content processing.

Patterns demonstrated:
1. Dynamic file discovery with DirectoryReaderNode
2. Type-specific file processing with dedicated readers
3. Data transformation and analysis
4. Result aggregation and summary generation
"""

import json
import os

from kailash import Workflow
from kailash.nodes.data import DirectoryReaderNode, JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime


def create_fixed_document_workflow() -> Workflow:
    """Create a document processing workflow using improved base nodes."""
    workflow = Workflow(
        workflow_id="fixed_document_001",
        name="fixed_document_workflow",
        description="Process multiple document types with dynamic discovery",
    )

    # === DYNAMIC FILE DISCOVERY ===

    # Use DirectoryReaderNode for dynamic file discovery
    file_discoverer = DirectoryReaderNode(
        id="file_discoverer",
        directory_path="data/inputs",
        recursive=False,
        file_patterns=["*.csv", "*.json", "*.txt", "*.xml", "*.md"],
        include_hidden=False,
    )
    workflow.add_node("file_discoverer", file_discoverer)

    # === PROCESS DISCOVERED FILES ===

    # Process CSV files if found
    csv_file_processor = DataTransformer(
        id="csv_file_processor",
        transformations=[
            """
# Process CSV files from discovery results
csv_files = []

# Get CSV files from discovery - use locals() to check available variables
print(f"Available variables: {list(locals().keys())}")

# Get files_by_type from input, with fallback to empty dict
available_files_by_type = locals().get("files_by_type", {})
csv_file_list = available_files_by_type.get("csv", [])

print(f"Found {len(csv_file_list)} CSV files to process")

for file_info in csv_file_list:
    try:
        # Read CSV file manually since we can't chain readers dynamically
        import csv

        file_path = file_info["file_path"]
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            content = list(reader)

        # Extract statistics
        total_records = len(content)

        # Calculate specific statistics based on content
        stats = {
            "total_records": total_records,
            "columns": list(content[0].keys()) if content else [],
            "sample_records": content[:3] if content else []
        }

        # Check for common patterns
        if any("status" in record for record in content):
            active_count = sum(1 for record in content if record.get("status") == "active")
            stats["active_records"] = active_count
            stats["inactive_records"] = total_records - active_count

        if any("email" in record for record in content):
            emails = [r.get("email", "") for r in content if "@" in r.get("email", "")]
            domains = list(set(email.split("@")[1] for email in emails))
            stats["email_domains"] = domains

        csv_files.append({
            "file_info": file_info,
            "processing_result": stats,
            "status": "success"
        })

    except Exception as e:
        csv_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "error"
        })

result = {
    "processed_files": csv_files,
    "file_count": len(csv_files),
    "file_type": "csv"
}
"""
        ],
    )
    workflow.add_node("csv_file_processor", csv_file_processor)
    workflow.connect(
        "file_discoverer",
        "csv_file_processor",
        mapping={"files_by_type": "files_by_type"},
    )

    # Process JSON files if found
    json_file_processor = DataTransformer(
        id="json_file_processor",
        transformations=[
            """
# Process JSON files from discovery results
json_files = []

# Get JSON files from discovery - use locals() to check available variables
print(f"Available variables: {list(locals().keys())}")

# Get files_by_type from input, with fallback to empty dict
available_files_by_type = locals().get("files_by_type", {})
json_file_list = available_files_by_type.get("json", [])

print(f"Found {len(json_file_list)} JSON files to process")

for file_info in json_file_list:
    try:
        import json as json_lib

        file_path = file_info["file_path"]
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json_lib.load(f)

        # Extract statistics based on content structure
        stats = {
            "data_type": "json",
            "structure_type": type(content).__name__
        }

        if isinstance(content, dict):
            stats["key_count"] = len(content)
            stats["keys"] = list(content.keys())

            # Check for transaction patterns
            if "transactions" in content:
                transactions = content["transactions"]
                stats["transaction_count"] = len(transactions)
                if transactions:
                    total_amount = sum(t.get("amount", 0) for t in transactions)
                    stats["total_amount"] = total_amount
                    stats["average_amount"] = total_amount / len(transactions)

                    customers = set(t.get("customer_id") for t in transactions if t.get("customer_id"))
                    stats["unique_customers"] = len(customers)

            # Check for metadata
            if "metadata" in content:
                stats["metadata"] = content["metadata"]

        elif isinstance(content, list):
            stats["array_length"] = len(content)
            if content and isinstance(content[0], dict):
                stats["sample_keys"] = list(content[0].keys())

        stats["sample_content"] = str(content)[:200] + "..." if len(str(content)) > 200 else str(content)

        json_files.append({
            "file_info": file_info,
            "processing_result": stats,
            "status": "success"
        })

    except Exception as e:
        json_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "error"
        })

result = {
    "processed_files": json_files,
    "file_count": len(json_files),
    "file_type": "json"
}
"""
        ],
    )
    workflow.add_node("json_file_processor", json_file_processor)
    workflow.connect(
        "file_discoverer",
        "json_file_processor",
        mapping={"files_by_type": "files_by_type"},
    )

    # Process text files (txt, xml, md)
    text_file_processor = DataTransformer(
        id="text_file_processor",
        transformations=[
            """
# Process text-based files from discovery results
import re

text_files = []

# Get text-based files from discovery - use locals() to check available variables
print(f"Available variables: {list(locals().keys())}")

# Get files_by_type from input, with fallback to empty dict
available_files_by_type = locals().get("files_by_type", {})
text_file_types = ["txt", "xml", "markdown"]
all_text_files = []

for file_type in text_file_types:
    file_list = available_files_by_type.get(file_type, [])
    all_text_files.extend(file_list)

print(f"Found {len(all_text_files)} text-based files to process")

for file_info in all_text_files:
    try:
        file_path = file_info["file_path"]
        file_type = file_info["file_type"]

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Basic text statistics
        lines = content.split("\\n")
        words = content.split()

        stats = {
            "line_count": len(lines),
            "word_count": len(words),
            "character_count": len(content),
            "file_type": file_type
        }

        # File-type specific processing
        if file_type == "txt":
            # Find placeholders in templates
            placeholders = re.findall(r'\\{([^}]+)\\}', content)
            stats["placeholders"] = placeholders
            stats["placeholder_count"] = len(placeholders)

        elif file_type == "xml":
            # Extract XML elements
            tags = re.findall(r'<([^/>\\s]+)', content)
            unique_tags = list(set(tags))
            stats["xml_tags"] = unique_tags
            stats["tag_count"] = len(unique_tags)

        elif file_type == "markdown":
            # Extract markdown headers
            headers = re.findall(r'^#+\\s+(.+)$', content, re.MULTILINE)
            stats["headers"] = headers
            stats["header_count"] = len(headers)

        stats["preview"] = content[:200] + "..." if len(content) > 200 else content

        text_files.append({
            "file_info": file_info,
            "processing_result": stats,
            "status": "success"
        })

    except Exception as e:
        text_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "error"
        })

result = {
    "processed_files": text_files,
    "file_count": len(text_files),
    "file_type": "text"
}
"""
        ],
    )
    workflow.add_node("text_file_processor", text_file_processor)
    workflow.connect(
        "file_discoverer",
        "text_file_processor",
        mapping={"files_by_type": "files_by_type"},
    )

    # === AGGREGATE RESULTS ===

    # Merge all processing results
    result_merger = MergeNode(id="result_merger", merge_type="concat")
    workflow.add_node("result_merger", result_merger)
    workflow.connect("csv_file_processor", "result_merger", mapping={"result": "data1"})
    workflow.connect(
        "json_file_processor", "result_merger", mapping={"result": "data2"}
    )
    workflow.connect(
        "text_file_processor", "result_merger", mapping={"result": "data3"}
    )

    # Generate comprehensive summary
    summary_generator = DataTransformer(
        id="summary_generator",
        transformations=[
            """
# Generate comprehensive processing summary
from datetime import datetime

# merged_data should be a list of processor results
processor_results = merged_data if isinstance(merged_data, list) else []

print(f"Generating summary from {len(processor_results)} processor results")

# Aggregate all processed files
all_processed_files = []
total_successful = 0
total_failed = 0
files_by_type = {}
processing_stats = {}

for processor_result in processor_results:
    if not isinstance(processor_result, dict):
        continue

    processed_files = processor_result.get("processed_files", [])
    file_type = processor_result.get("file_type", "unknown")

    all_processed_files.extend(processed_files)

    # Count successes and failures
    successful = sum(1 for f in processed_files if f.get("status") == "success")
    failed = sum(1 for f in processed_files if f.get("status") == "error")

    total_successful += successful
    total_failed += failed

    # Group by type
    if file_type not in files_by_type:
        files_by_type[file_type] = 0
    files_by_type[file_type] += len(processed_files)

    # Collect processing statistics
    processing_stats[file_type] = {
        "processed_count": len(processed_files),
        "successful_count": successful,
        "failed_count": failed
    }

    # Add type-specific stats
    for file_data in processed_files:
        if file_data.get("status") == "success":
            proc_result = file_data.get("processing_result", {})

            if file_type == "csv":
                if "total_records" not in processing_stats[file_type]:
                    processing_stats[file_type]["total_records"] = 0
                processing_stats[file_type]["total_records"] += proc_result.get("total_records", 0)

            elif file_type == "json":
                if "total_transactions" not in processing_stats[file_type]:
                    processing_stats[file_type]["total_transactions"] = 0
                processing_stats[file_type]["total_transactions"] += proc_result.get("transaction_count", 0)

            elif file_type == "text":
                if "total_words" not in processing_stats[file_type]:
                    processing_stats[file_type]["total_words"] = 0
                processing_stats[file_type]["total_words"] += proc_result.get("word_count", 0)

# Generate final summary
summary = {
    "processing_summary": {
        "total_files_discovered": len(all_processed_files),
        "total_successful": total_successful,
        "total_failed": total_failed,
        "files_by_type": files_by_type,
        "processing_stats": processing_stats
    },
    "detailed_results": all_processed_files,
    "metadata": {
        "processed_at": datetime.now().isoformat(),
        "workflow_version": "fixed_2.0",
        "processor": "fixed_document_workflow"
    },
    "recommendations": []
}

# Generate recommendations
if files_by_type.get("csv", 0) > 0:
    summary["recommendations"].append("CSV files processed - review customer data analysis")

if files_by_type.get("json", 0) > 0:
    summary["recommendations"].append("JSON files processed - analyze transaction patterns")

if files_by_type.get("text", 0) > 0:
    summary["recommendations"].append("Text files processed - update templates and documentation")

if total_failed > 0:
    summary["recommendations"].append(f"Review {total_failed} failed file(s) for processing errors")

result = summary
"""
        ],
    )
    workflow.add_node("summary_generator", summary_generator)
    workflow.connect(
        "result_merger", "summary_generator", mapping={"merged_data": "merged_data"}
    )

    # === OUTPUT ===

    # Save comprehensive summary
    summary_writer = JSONWriterNode(
        id="summary_writer", file_path="data/outputs/fixed_processing_summary.json"
    )
    workflow.add_node("summary_writer", summary_writer)
    workflow.connect("summary_generator", "summary_writer", mapping={"result": "data"})

    return workflow


def run_fixed_processing():
    """Execute the fixed document processing workflow."""
    workflow = create_fixed_document_workflow()
    runtime = LocalRuntime()

    try:
        print("Starting Fixed Document Processing...")
        print("🔍 Discovering files dynamically...")

        result, run_id = runtime.execute(workflow, parameters={})

        print("\n✅ Processing Complete!")
        print("📁 Output: data/outputs/fixed_processing_summary.json")

        # Show discovery results
        if "file_discoverer" in result:
            discovery_stats = result["file_discoverer"]["directory_stats"]
            print("\n📊 Discovery Results:")
            print(f"   - Total files found: {discovery_stats['total_files']}")
            print(f"   - File types: {', '.join(discovery_stats['file_types'])}")
            print(f"   - Files by type: {discovery_stats['files_by_type_count']}")

        # Show processing summary
        if "summary_generator" in result:
            summary_result = result["summary_generator"]["result"]
            processing_summary = summary_result.get("processing_summary", {})

            print("\n📈 Processing Results:")
            print(
                f"   - Files processed: {processing_summary.get('total_files_discovered', 0)}"
            )
            print(f"   - Successful: {processing_summary.get('total_successful', 0)}")
            print(f"   - Failed: {processing_summary.get('total_failed', 0)}")

            # Show recommendations
            recommendations = summary_result.get("recommendations", [])
            if recommendations:
                print("\n💡 Recommendations:")
                for rec in recommendations:
                    print(f"   - {rec}")

        return result

    except Exception as e:
        print(f"❌ Processing failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Ensure output directory exists
    os.makedirs("data/outputs", exist_ok=True)

    # Check if input directory exists
    if not os.path.exists("data/inputs"):
        print("❌ Input directory 'data/inputs' not found")
        print(
            "Please create the directory and add sample files, or run the original document_processor.py first"
        )
        return

    # Run the workflow
    run_fixed_processing()

    # Display output
    print("\n=== Generated Summary ===")
    try:
        with open("data/outputs/fixed_processing_summary.json") as f:
            summary = json.load(f)
            # Show just the processing summary for brevity
            proc_summary = summary.get("processing_summary", {})
            print(json.dumps(proc_summary, indent=2))
    except Exception as e:
        print(f"Could not read summary: {e}")


if __name__ == "__main__":
    main()

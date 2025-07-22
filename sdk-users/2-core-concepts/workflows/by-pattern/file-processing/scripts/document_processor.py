#!/usr/bin/env python3
"""
Document Processing Workflow - Real File Processing
===================================================

Demonstrates comprehensive file processing patterns using Kailash SDK with real files.
This workflow uses existing nodes to discover, read, and process actual files,
avoiding any mock data generation.

Patterns demonstrated:
1. Real file discovery using DirectoryReaderNode
2. Type-specific file processing using existing reader nodes
3. Real content analysis and extraction
4. Structured output generation

Features:
- Uses DirectoryReaderNode for real file discovery
- Uses CSVReaderNode, JSONReaderNode, TextReaderNode for content processing
- Processes actual file content without mocking
- Generates comprehensive analysis reports
"""

import json
import os
from pathlib import Path

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import DirectoryReaderNode, JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime


def ensure_input_data_exists():
    """Ensure sample input data exists for processing."""
    input_dir = Path("data/inputs")
    input_dir.mkdir(parents=True, exist_ok=True)

    # Only create files if they don't exist
    csv_file = input_dir / "customer_data.csv"
    if not csv_file.exists():
        csv_content = """customer_id,name,email,status,registration_date,purchase_amount
CUST-001,John Doe,john@example.com,active,2024-01-15,299.99
CUST-002,Jane Smith,jane@example.com,active,2024-01-16,149.50
CUST-003,Bob Johnson,bob@example.com,inactive,2024-01-17,79.99
CUST-004,Alice Wilson,alice@example.com,active,2024-01-18,399.00
CUST-005,Charlie Brown,charlie@example.com,inactive,2024-01-19,25.99"""
        csv_file.write_text(csv_content)

    json_file = input_dir / "transaction_log.json"
    if not json_file.exists():
        json_content = {
            "transactions": [
                {
                    "id": "TXN-001",
                    "customer_id": "CUST-001",
                    "amount": 299.99,
                    "currency": "USD",
                    "timestamp": "2024-01-15T09:00:00Z",
                    "product": "Premium Plan",
                    "status": "completed",
                },
                {
                    "id": "TXN-002",
                    "customer_id": "CUST-002",
                    "amount": 149.50,
                    "currency": "USD",
                    "timestamp": "2024-01-15T09:30:00Z",
                    "product": "Standard Plan",
                    "status": "completed",
                },
                {
                    "id": "TXN-003",
                    "customer_id": "CUST-001",
                    "amount": 79.99,
                    "currency": "USD",
                    "timestamp": "2024-01-15T10:00:00Z",
                    "product": "Add-on Service",
                    "status": "pending",
                },
            ],
            "metadata": {
                "version": "1.0",
                "generated_at": "2024-01-15T10:30:00Z",
                "total_transactions": 3,
                "total_amount": 529.48,
            },
        }
        json_file.write_text(json.dumps(json_content, indent=2))

    txt_file = input_dir / "report_template.txt"
    if not txt_file.exists():
        txt_content = """Customer Report Template
========================

Generated on: {report_date}
Report Period: {period_start} to {period_end}

Summary:
========
Total Customers: {total_customers}
Active Customers: {active_customers}
Inactive Customers: {inactive_customers}
Total Revenue: ${total_revenue}
Average Revenue per Customer: ${avg_revenue}

Top Performing Products:
=======================
1. {top_product_1} - ${top_revenue_1}
2. {top_product_2} - ${top_revenue_2}
3. {top_product_3} - ${top_revenue_3}

Key Metrics:
===========
- Customer Acquisition Rate: {acquisition_rate}%
- Customer Retention Rate: {retention_rate}%
- Average Order Value: ${avg_order_value}

Recommendations:
===============
{recommendations}

Notes:
======
{additional_notes}"""
        txt_file.write_text(txt_content)

    xml_file = input_dir / "metadata.xml"
    if not xml_file.exists():
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <document>
        <title>Customer Data Processing Metadata</title>
        <version>1.2</version>
        <created>2024-01-15T08:00:00Z</created>
        <last_updated>2024-01-20T14:30:00Z</last_updated>
        <author>Data Processing Team</author>
    </document>
    <data_sources>
        <source type="csv" name="customer_data.csv">
            <description>Customer master data with demographics and status</description>
            <fields>6</fields>
            <records>5</records>
            <last_updated>2024-01-20T12:00:00Z</last_updated>
        </source>
        <source type="json" name="transaction_log.json">
            <description>Transaction history and payment records</description>
            <format>structured_json</format>
            <last_updated>2024-01-20T13:15:00Z</last_updated>
        </source>
    </data_sources>
    <processing>
        <pipeline>document_processing_workflow</pipeline>
        <frequency>daily</frequency>
        <retention_days>90</retention_days>
    </processing>
</metadata>"""
        xml_file.write_text(xml_content)


def create_document_processing_workflow() -> Workflow:
    """Create a comprehensive document processing workflow using real files."""
    workflow = Workflow(
        workflow_id="real_document_processing_001",
        name="real_document_processing_workflow",
        description="Process real documents using DirectoryReader and specialized file readers",
    )

    # === REAL FILE DISCOVERY ===

    # Discover actual files in the input directory
    file_discoverer = DirectoryReaderNode(
        name="file_discoverer",
        directory_path="data/inputs",
        recursive=False,  # Scan only the inputs directory
        file_patterns=[
            "*.csv",
            "*.json",
            "*.txt",
            "*.xml",
            "*.md",
        ],  # Include common formats
        include_hidden=False,
    )
    workflow.add_node("file_discoverer", file_discoverer)

    # === REAL CSV PROCESSING ===

    # Extract CSV files from discovery and process them
    csv_file_extractor = PythonCodeNode(
        name="csv_file_extractor",
        code="""
# Extract CSV files from discovery results
files_by_type = discovery_data.get("files_by_type", {})
csv_files = files_by_type.get("csv", [])

result = {
    "csv_files": csv_files,
    "csv_count": len(csv_files)
}
""",
    )
    workflow.add_node("csv_file_extractor", csv_file_extractor)
    workflow.connect(
        "file_discoverer",
        "csv_file_extractor",
        mapping={"files_by_type": "discovery_data"},
    )

    # Process each CSV file using CSVReaderNode
    csv_processor = PythonCodeNode(
        name="csv_processor",
        code="""
# Process CSV files using CSVReaderNode for each discovered file
from kailash.nodes.data import CSVReaderNode
import json

csv_files = file_data.get("csv_files", [])
processed_csv_results = []

for csv_file_info in csv_files:
    file_path = csv_file_info["file_path"]

    try:
        # Create and execute CSVReaderNode for this file
        csv_reader = CSVReaderNode(name=f"csv_reader_{csv_file_info['file_name']}")
        csv_result = csv_reader.execute(file_path=file_path, headers=True)

        # Extract the actual data
        csv_data = csv_result.get("data", [])

        # Analyze the CSV content
        total_records = len(csv_data)
        columns = list(csv_data[0].keys()) if csv_data else []

        # Calculate statistics based on actual data
        active_count = sum(1 for record in csv_data if record.get("status") == "active")
        total_amount = 0
        for record in csv_data:
            amount_str = record.get("purchase_amount", "0")
            try:
                amount = float(amount_str)
                total_amount += amount
            except (ValueError, TypeError):
                pass

        processing_result = {
            "file_info": csv_file_info,
            "total_records": total_records,
            "columns": columns,
            "active_customers": active_count,
            "inactive_customers": total_records - active_count,
            "total_purchase_amount": total_amount,
            "average_purchase": total_amount / total_records if total_records > 0 else 0,
            "sample_records": csv_data[:3]  # First 3 records
        }

        processed_csv_results.append(processing_result)

    except Exception as e:
        error_result = {
            "file_info": csv_file_info,
            "error": str(e),
            "error_type": type(e).__name__
        }
        processed_csv_results.append(error_result)

result = {
    "processed_csv_files": processed_csv_results,
    "csv_files_processed": len(processed_csv_results)
}
""",
    )
    workflow.add_node("csv_processor", csv_processor)
    workflow.connect(
        "csv_file_extractor", "csv_processor", mapping={"result": "file_data"}
    )

    # === REAL JSON PROCESSING ===

    # Extract and process JSON files
    json_file_extractor = PythonCodeNode(
        name="json_file_extractor",
        code="""
# Extract JSON files from discovery results
files_by_type = discovery_data.get("files_by_type", {})
json_files = files_by_type.get("json", [])

result = {
    "json_files": json_files,
    "json_count": len(json_files)
}
""",
    )
    workflow.add_node("json_file_extractor", json_file_extractor)
    workflow.connect(
        "file_discoverer",
        "json_file_extractor",
        mapping={"files_by_type": "discovery_data"},
    )

    json_processor = PythonCodeNode(
        name="json_processor",
        code="""
# Process JSON files using JSONReaderNode for each discovered file
from kailash.nodes.data import JSONReaderNode

json_files = file_data.get("json_files", [])
processed_json_results = []

for json_file_info in json_files:
    file_path = json_file_info["file_path"]

    try:
        # Create and execute JSONReaderNode for this file
        json_reader = JSONReaderNode(name=f"json_reader_{json_file_info['file_name']}")
        json_result = json_reader.execute(file_path=file_path)

        # Extract the actual data
        json_data = json_result.get("data", {})

        # Analyze JSON structure and content
        if isinstance(json_data, dict):
            keys = list(json_data.keys())

            # Handle transaction log structure
            if "transactions" in json_data:
                transactions = json_data.get("transactions", [])
                metadata = json_data.get("metadata", {})

                total_transactions = len(transactions)
                total_amount = sum(txn.get("amount", 0) for txn in transactions)
                completed_transactions = sum(1 for txn in transactions if txn.get("status") == "completed")

                processing_result = {
                    "file_info": json_file_info,
                    "data_type": "transaction_log",
                    "total_transactions": total_transactions,
                    "completed_transactions": completed_transactions,
                    "pending_transactions": total_transactions - completed_transactions,
                    "total_amount": total_amount,
                    "average_transaction": total_amount / total_transactions if total_transactions > 0 else 0,
                    "metadata": metadata,
                    "sample_transactions": transactions[:3]
                }
            else:
                # Generic JSON processing
                processing_result = {
                    "file_info": json_file_info,
                    "data_type": "generic_json",
                    "top_level_keys": keys,
                    "key_count": len(keys),
                    "is_array": isinstance(json_data, list),
                    "sample_content": str(json_data)[:200] + "..." if len(str(json_data)) > 200 else str(json_data)
                }
        else:
            processing_result = {
                "file_info": json_file_info,
                "data_type": "json_array",
                "array_length": len(json_data) if isinstance(json_data, list) else 0,
                "sample_content": str(json_data)[:200] + "..." if len(str(json_data)) > 200 else str(json_data)
            }

        processed_json_results.append(processing_result)

    except Exception as e:
        error_result = {
            "file_info": json_file_info,
            "error": str(e),
            "error_type": type(e).__name__
        }
        processed_json_results.append(error_result)

result = {
    "processed_json_files": processed_json_results,
    "json_files_processed": len(processed_json_results)
}
""",
    )
    workflow.add_node("json_processor", json_processor)
    workflow.connect(
        "json_file_extractor", "json_processor", mapping={"result": "file_data"}
    )

    # === REAL TEXT PROCESSING ===

    # Extract and process text files (txt, xml, md)
    text_file_extractor = PythonCodeNode(
        name="text_file_extractor",
        code="""
# Extract text-based files from discovery results
files_by_type = discovery_data.get("files_by_type", {})

text_files = []
for file_type in ["txt", "xml", "markdown"]:
    text_files.extend(files_by_type.get(file_type, []))

result = {
    "text_files": text_files,
    "text_count": len(text_files)
}
""",
    )
    workflow.add_node("text_file_extractor", text_file_extractor)
    workflow.connect(
        "file_discoverer",
        "text_file_extractor",
        mapping={"files_by_type": "discovery_data"},
    )

    text_processor = PythonCodeNode(
        name="text_processor",
        code="""
# Process text files using TextReaderNode for each discovered file
from kailash.nodes.data import TextReaderNode
import re

text_files = file_data.get("text_files", [])
processed_text_results = []

for text_file_info in text_files:
    file_path = text_file_info["file_path"]
    file_type = text_file_info["file_type"]

    try:
        # Create and execute TextReaderNode for this file
        text_reader = TextReaderNode(name=f"text_reader_{text_file_info['file_name']}")
        text_result = text_reader.execute(file_path=file_path, encoding="utf-8")

        # Extract the actual text content
        text_content = text_result.get("text", "")

        # Analyze text content
        word_count = len(text_content.split())
        line_count = len(text_content.split("\\n"))
        char_count = len(text_content)

        # File-type specific analysis
        if file_type == "txt":
            # Find template placeholders
            placeholders = re.findall(r'\\{([^}]+)\\}', text_content)
            specific_analysis = {
                "template_placeholders": list(set(placeholders)),
                "placeholder_count": len(placeholders),
                "unique_placeholders": len(set(placeholders))
            }
        elif file_type == "xml":
            # Extract XML tags and structure
            tags = re.findall(r'<([^/>\\s]+)[^>]*>', text_content)
            unique_tags = list(set(tags))
            specific_analysis = {
                "xml_tags": unique_tags,
                "tag_count": len(tags),
                "unique_tag_count": len(unique_tags),
                "is_well_formed": text_content.count("<") == text_content.count(">")
            }
        elif file_type == "markdown":
            # Extract markdown structure
            headers = re.findall(r'^#+\\s+(.+)$', text_content, re.MULTILINE)
            links = re.findall(r'\\[([^\\]]+)\\]\\(([^)]+)\\)', text_content)
            specific_analysis = {
                "headers": headers,
                "header_count": len(headers),
                "links": links,
                "link_count": len(links)
            }
        else:
            specific_analysis = {}

        processing_result = {
            "file_info": text_file_info,
            "word_count": word_count,
            "line_count": line_count,
            "character_count": char_count,
            "content_preview": text_content[:300] + "..." if len(text_content) > 300 else text_content,
            "specific_analysis": specific_analysis
        }

        processed_text_results.append(processing_result)

    except Exception as e:
        error_result = {
            "file_info": text_file_info,
            "error": str(e),
            "error_type": type(e).__name__
        }
        processed_text_results.append(error_result)

result = {
    "processed_text_files": processed_text_results,
    "text_files_processed": len(processed_text_results)
}
""",
    )
    workflow.add_node("text_processor", text_processor)
    workflow.connect(
        "text_file_extractor", "text_processor", mapping={"result": "file_data"}
    )

    # === MERGE ALL PROCESSING RESULTS ===

    # Merge all processing results using MergeNode
    result_merger = MergeNode(id="result_merger", merge_type="merge_dict")
    workflow.add_node("result_merger", result_merger)
    workflow.connect("csv_processor", "result_merger", mapping={"result": "data1"})
    workflow.connect("json_processor", "result_merger", mapping={"result": "data2"})
    workflow.connect("text_processor", "result_merger", mapping={"result": "data3"})

    # === COMPREHENSIVE ANALYSIS ===

    # Generate comprehensive analysis report
    final_analyzer = PythonCodeNode(
        name="final_analyzer",
        code="""
# Generate comprehensive analysis from all processed files
from datetime import datetime

merged_results = merged_data
csv_results = merged_results.get("processed_csv_files", [])
json_results = merged_results.get("processed_json_files", [])
text_results = merged_results.get("processed_text_files", [])

# Aggregate statistics
total_files_processed = len(csv_results) + len(json_results) + len(text_results)
successful_processing = sum(1 for result in csv_results + json_results + text_results if "error" not in result)
failed_processing = total_files_processed - successful_processing

# File type breakdown
file_type_summary = {
    "csv": {
        "processed": len(csv_results),
        "successful": sum(1 for r in csv_results if "error" not in r),
        "total_records": sum(r.get("total_records", 0) for r in csv_results if "total_records" in r),
        "total_customers": sum(r.get("total_records", 0) for r in csv_results if "total_records" in r),
        "active_customers": sum(r.get("active_customers", 0) for r in csv_results if "active_customers" in r),
        "total_revenue": sum(r.get("total_purchase_amount", 0) for r in csv_results if "total_purchase_amount" in r)
    },
    "json": {
        "processed": len(json_results),
        "successful": sum(1 for r in json_results if "error" not in r),
        "total_transactions": sum(r.get("total_transactions", 0) for r in json_results if "total_transactions" in r),
        "completed_transactions": sum(r.get("completed_transactions", 0) for r in json_results if "completed_transactions" in r),
        "transaction_amount": sum(r.get("total_amount", 0) for r in json_results if "total_amount" in r)
    },
    "text": {
        "processed": len(text_results),
        "successful": sum(1 for r in text_results if "error" not in r),
        "total_words": sum(r.get("word_count", 0) for r in text_results if "word_count" in r),
        "total_lines": sum(r.get("line_count", 0) for r in text_results if "line_count" in r),
        "total_characters": sum(r.get("character_count", 0) for r in text_results if "character_count" in r)
    }
}

# Generate insights
insights = []
if file_type_summary["csv"]["active_customers"] > 0:
    active_rate = (file_type_summary["csv"]["active_customers"] / file_type_summary["csv"]["total_customers"]) * 100
    insights.append(f"Customer activation rate: {active_rate:.1f}%")

if file_type_summary["json"]["total_transactions"] > 0:
    completion_rate = (file_type_summary["json"]["completed_transactions"] / file_type_summary["json"]["total_transactions"]) * 100
    insights.append(f"Transaction completion rate: {completion_rate:.1f}%")

if file_type_summary["csv"]["total_revenue"] > 0 and file_type_summary["csv"]["total_customers"] > 0:
    avg_revenue = file_type_summary["csv"]["total_revenue"] / file_type_summary["csv"]["total_customers"]
    insights.append(f"Average revenue per customer: ${avg_revenue:.2f}")

# Generate recommendations
recommendations = []
if failed_processing > 0:
    recommendations.append(f"Review {failed_processing} files that failed processing")

if file_type_summary["csv"]["active_customers"] < file_type_summary["csv"]["total_customers"]:
    inactive_count = file_type_summary["csv"]["total_customers"] - file_type_summary["csv"]["active_customers"]
    recommendations.append(f"Re-engage {inactive_count} inactive customers")

if file_type_summary["json"]["completed_transactions"] < file_type_summary["json"]["total_transactions"]:
    pending_count = file_type_summary["json"]["total_transactions"] - file_type_summary["json"]["completed_transactions"]
    recommendations.append(f"Follow up on {pending_count} pending transactions")

# Create comprehensive report
comprehensive_report = {
    "processing_summary": {
        "total_files_processed": total_files_processed,
        "successful_processing": successful_processing,
        "failed_processing": failed_processing,
        "success_rate": (successful_processing / total_files_processed * 100) if total_files_processed > 0 else 0
    },
    "file_type_breakdown": file_type_summary,
    "business_insights": insights,
    "recommendations": recommendations,
    "detailed_results": {
        "csv_analysis": csv_results,
        "json_analysis": json_results,
        "text_analysis": text_results
    },
    "report_metadata": {
        "generated_at": datetime.now().isoformat(),
        "workflow_version": "real_file_processing_v1.0",
        "processing_method": "DirectoryReader + Specialized FileReaders"
    }
}

result = comprehensive_report
""",
    )
    workflow.add_node("final_analyzer", final_analyzer)
    workflow.connect(
        "result_merger", "final_analyzer", mapping={"merged_data": "merged_data"}
    )

    # === OUTPUT ===

    # Save comprehensive processing report
    report_writer = JSONWriterNode(
        id="report_writer",
        file_path="data/outputs/comprehensive_document_analysis.json",
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("final_analyzer", "report_writer", mapping={"result": "data"})

    return workflow


def run_document_processing():
    """Execute the real document processing workflow."""
    workflow = create_document_processing_workflow()
    runtime = LocalRuntime()

    parameters = {}

    try:
        print("Starting Real Document Processing Workflow...")
        print("🔍 Discovering actual files in data/inputs/...")

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\\n✅ Document Processing Complete!")
        print("📁 Output generated: data/outputs/comprehensive_document_analysis.json")

        # Show processing summary
        final_result = result.get("final_analyzer", {}).get("result", {})
        processing_summary = final_result.get("processing_summary", {})
        file_breakdown = final_result.get("file_type_breakdown", {})

        print("\\n📊 Processing Summary:")
        print(
            f"   - Total files processed: {processing_summary.get('total_files_processed', 0)}"
        )
        print(f"   - Success rate: {processing_summary.get('success_rate', 0):.1f}%")
        print(f"   - CSV files: {file_breakdown.get('csv', {}).get('processed', 0)}")
        print(f"   - JSON files: {file_breakdown.get('json', {}).get('processed', 0)}")
        print(f"   - Text files: {file_breakdown.get('text', {}).get('processed', 0)}")

        # Show business insights
        insights = final_result.get("business_insights", [])
        if insights:
            print("\\n💡 Business Insights:")
            for insight in insights:
                print(f"   - {insight}")

        # Show recommendations
        recommendations = final_result.get("recommendations", [])
        if recommendations:
            print("\\n🎯 Recommendations:")
            for rec in recommendations:
                print(f"   - {rec}")

        return result

    except Exception as e:
        print(f"❌ Document Processing failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Ensure input data exists
    ensure_input_data_exists()
    print("📝 Input data verified/created")

    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the document processing workflow
    run_document_processing()

    # Display generated report preview
    print("\\n=== Document Analysis Report Preview ===")
    try:
        with open("data/outputs/comprehensive_document_analysis.json") as f:
            report = json.load(f)
            processing_summary = report["processing_summary"]
            print(json.dumps(processing_summary, indent=2))

            print("\\n=== File Type Breakdown ===")
            file_breakdown = report["file_type_breakdown"]
            for file_type, stats in file_breakdown.items():
                print(f"{file_type.upper()}: {stats}")

    except Exception as e:
        print(f"Could not read report: {e}")


if __name__ == "__main__":
    main()

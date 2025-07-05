#!/usr/bin/env python3
"""
Consolidated Document Processing Workflow
========================================

A clean, production-ready document processing workflow that demonstrates:
1. Dynamic file discovery using DirectoryReaderNode
2. Type-specific processing for different file formats
3. Optional AI enhancement with Ollama
4. Comprehensive error handling and reporting

This consolidates the best practices from all document processor variants.
"""

import json
import os

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import DirectoryReaderNode, JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime

# Optional: AI enhancement
try:
    from kailash.nodes.ai import LLMAgentNode

    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False


def create_document_processing_workflow(enable_ai: bool = False) -> Workflow:
    """
    Create a comprehensive document processing workflow.

    Args:
        enable_ai: Whether to enable AI-powered analysis (requires Ollama/OpenAI)

    Returns:
        Configured workflow ready for execution
    """
    workflow = Workflow(
        workflow_id="doc_processor_consolidated",
        name="Document Processing Workflow",
        description="Comprehensive document processing with optional AI enhancement",
    )

    # === STAGE 1: FILE DISCOVERY ===

    # Use DirectoryReaderNode for robust file discovery
    file_discoverer = DirectoryReaderNode(
        name="file_discoverer",
        directory_path="data/inputs",
        recursive=True,
        file_patterns=["*.csv", "*.json", "*.txt", "*.xml", "*.md", "*.pdf"],
        include_hidden=False,
        include_metadata=True,
    )
    workflow.add_node("file_discoverer", file_discoverer)

    # === STAGE 2: FILE ROUTING ===

    # Route files to appropriate processors based on type
    file_router = PythonCodeNode(
        name="file_router",
        code="""
import json

# Get discovered files
discovered_files = inputs.get("discovered_files", [])
files_by_type = inputs.get("files_by_type", {})
directory_stats = inputs.get("directory_stats", {})

print(f"Routing {len(discovered_files)} files across {len(files_by_type)} types")

# Prepare routing information
routing_info = {
    "csv_files": files_by_type.get("csv", []),
    "json_files": files_by_type.get("json", []),
    "text_files": files_by_type.get("txt", []) + files_by_type.get("md", []),
    "xml_files": files_by_type.get("xml", []),
    "pdf_files": files_by_type.get("pdf", []),
    "all_files": discovered_files,
    "summary": {
        "total_files": len(discovered_files),
        "file_types": list(files_by_type.keys()),
        "type_counts": {ft: len(files) for ft, files in files_by_type.items()},
        "total_size_mb": directory_stats.get("total_size", 0) / (1024 * 1024)
    }
}

result = routing_info
""",
    )
    workflow.add_node("file_router", file_router)
    workflow.connect("file_discoverer", "file_router")

    # === STAGE 3: TYPE-SPECIFIC PROCESSING ===

    # CSV Processor - Extract statistics and patterns
    csv_processor = PythonCodeNode(
        name="csv_processor",
        code="""
import csv
import pandas as pd
from datetime import datetime

csv_files = inputs.get("csv_files", [])
print(f"Processing {len(csv_files)} CSV files")

processed_files = []

for file_info in csv_files:
    file_path = file_info["file_path"]

    try:
        # Read CSV with pandas for advanced processing
        df = pd.read_csv(file_path)

        # Basic statistics
        stats = {
            "rows": len(df),
            "columns": list(df.columns),
            "column_count": len(df.columns),
            "memory_usage_kb": df.memory_usage(deep=True).sum() / 1024,
            "dtypes": df.dtypes.astype(str).to_dict(),
            "null_counts": df.isnull().sum().to_dict()
        }

        # Numeric column statistics
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            stats["numeric_summary"] = df[numeric_cols].describe().to_dict()

        # Categorical column analysis
        categorical_cols = df.select_dtypes(include=['object']).columns
        categorical_summary = {}
        for col in categorical_cols[:5]:  # Limit to first 5 to avoid too much data
            value_counts = df[col].value_counts().head(10)
            categorical_summary[col] = {
                "unique_values": df[col].nunique(),
                "top_values": value_counts.to_dict()
            }
        stats["categorical_summary"] = categorical_summary

        # Special field detection
        stats["detected_fields"] = {
            "has_email": any("email" in col.lower() for col in df.columns),
            "has_date": any("date" in col.lower() or "time" in col.lower() for col in df.columns),
            "has_status": any("status" in col.lower() for col in df.columns),
            "has_id": any("id" in col.lower() for col in df.columns)
        }

        processed_files.append({
            "file_info": file_info,
            "processing_result": stats,
            "status": "success",
            "processor": "csv_processor"
        })

    except Exception as e:
        processed_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "failed",
            "processor": "csv_processor"
        })

result = {"processed_files": processed_files, "file_count": len(processed_files)}
""",
    )
    workflow.add_node("csv_processor", csv_processor)
    workflow.connect("file_router", "csv_processor", mapping={"csv_files": "csv_files"})

    # JSON Processor - Extract structure and validate
    json_processor = PythonCodeNode(
        name="json_processor",
        code="""
import json
from datetime import datetime

json_files = inputs.get("json_files", [])
print(f"Processing {len(json_files)} JSON files")

processed_files = []

def analyze_json_structure(data, path=""):
    # Recursively analyze JSON structure.
    if isinstance(data, dict):
        return {
            "type": "object",
            "keys": list(data.keys()),
            "key_count": len(data),
            "nested_objects": sum(1 for v in data.values() if isinstance(v, dict)),
            "nested_arrays": sum(1 for v in data.values() if isinstance(v, list))
        }
    elif isinstance(data, list):
        return {
            "type": "array",
            "length": len(data),
            "element_types": list(set(type(item).__name__ for item in data[:10]))
        }
    else:
        return {"type": type(data).__name__}

for file_info in json_files:
    file_path = file_info["file_path"]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Analyze structure
        structure = analyze_json_structure(data)

        # Detect common patterns
        patterns = {
            "is_config": any(key in str(data).lower() for key in ["config", "settings", "options"]),
            "is_data": any(key in str(data).lower() for key in ["data", "records", "items"]),
            "has_schema": "$schema" in data if isinstance(data, dict) else False,
            "has_version": "version" in data if isinstance(data, dict) else False
        }

        # Sample data (for arrays or large objects)
        sample = None
        if isinstance(data, list) and len(data) > 0:
            sample = data[:3]
        elif isinstance(data, dict) and len(str(data)) > 1000:
            sample = {k: v for k, v in list(data.items())[:5]}

        processed_files.append({
            "file_info": file_info,
            "processing_result": {
                "structure": structure,
                "patterns": patterns,
                "sample": sample,
                "size_bytes": len(json.dumps(data))
            },
            "status": "success",
            "processor": "json_processor"
        })

    except Exception as e:
        processed_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "failed",
            "processor": "json_processor"
        })

result = {"processed_files": processed_files, "file_count": len(processed_files)}
""",
    )
    workflow.add_node("json_processor", json_processor)
    workflow.connect(
        "file_router", "json_processor", mapping={"json_files": "json_files"}
    )

    # Text Processor - Extract content and metadata
    text_processor = PythonCodeNode(
        name="text_processor",
        code="""
import re
from datetime import datetime

text_files = inputs.get("text_files", [])
print(f"Processing {len(text_files)} text files")

processed_files = []

def analyze_text_content(content, file_type):
    # Analyze text content based on file type.
    # Basic statistics
    stats = {
        "characters": len(content),
        "words": len(content.split()),
        "lines": len(content.splitlines()),
        "paragraphs": len(re.split(r'\\n\\s*\\n', content.strip()))
    }

    # File type specific analysis
    if file_type == "md":
        # Markdown analysis
        headers = re.findall(r'^#+\\s+(.+)$', content, re.MULTILINE)
        code_blocks = re.findall(r'```[\\s\\S]*?```', content)
        links = re.findall(r'\\[([^\\]]+)\\]\\(([^\\)]+)\\)', content)

        stats.update({
            "markdown_headers": headers,
            "code_block_count": len(code_blocks),
            "link_count": len(links),
            "has_frontmatter": content.strip().startswith('---')
        })
    else:
        # Plain text analysis
        urls = re.findall(r'https?://[^\\s]+', content)
        emails = re.findall(r'[\\w\\.-]+@[\\w\\.-]+\\.\\w+', content)

        stats.update({
            "url_count": len(urls),
            "email_count": len(emails),
            "has_code": any(marker in content for marker in ['def ', 'class ', 'function', 'import'])
        })

    return stats

for file_info in text_files:
    file_path = file_info["file_path"]
    file_type = file_info.get("file_type", "txt")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Analyze content
        analysis = analyze_text_content(content, file_type)

        # Get preview
        preview_length = 500
        preview = content[:preview_length]
        if len(content) > preview_length:
            preview += "..."

        processed_files.append({
            "file_info": file_info,
            "processing_result": {
                "analysis": analysis,
                "preview": preview,
                "encoding": "utf-8"
            },
            "status": "success",
            "processor": "text_processor"
        })

    except Exception as e:
        processed_files.append({
            "file_info": file_info,
            "error": str(e),
            "status": "failed",
            "processor": "text_processor"
        })

result = {"processed_files": processed_files, "file_count": len(processed_files)}
""",
    )
    workflow.add_node("text_processor", text_processor)
    workflow.connect(
        "file_router", "text_processor", mapping={"text_files": "text_files"}
    )

    # === STAGE 4: RESULT AGGREGATION ===

    # Merge all processing results
    result_merger = MergeNode(name="result_merger", merge_strategy="concatenate")
    workflow.add_node("result_merger", result_merger)
    workflow.connect(
        "csv_processor", "result_merger", mapping={"processed_files": "input1"}
    )
    workflow.connect(
        "json_processor", "result_merger", mapping={"processed_files": "input2"}
    )
    workflow.connect(
        "text_processor", "result_merger", mapping={"processed_files": "input3"}
    )

    # === STAGE 5: OPTIONAL AI ENHANCEMENT ===

    if enable_ai and AI_AVAILABLE:
        # AI-powered insights generator
        ai_analyzer = LLMAgentNode(
            name="ai_analyzer",
            model="llama3.2:3b",  # Use Ollama model
            system_prompt="You are a document analysis expert. Analyze the processed files and provide:\n1. Key insights about the data\n2. Potential data quality issues\n3. Recommendations for further processing\n4. Interesting patterns or anomalies\n\nBe concise and focus on actionable insights.",
            temperature=0.7,
        )
        workflow.add_node("ai_analyzer", ai_analyzer)
        workflow.connect(
            "result_merger", "ai_analyzer", mapping={"merged": "processed_files"}
        )

        # Final report generator combines everything
    else:
        # Skip AI if not available
        pass

    # === STAGE 6: SUMMARY GENERATION ===

    summary_generator = PythonCodeNode(
        name="summary_generator",
        code="""
from datetime import datetime

# Get all processed files
if "response" in inputs:
    # AI-enhanced path
    ai_insights = inputs.get("response", "")
    processed_data = inputs.get("processed_files", [])
else:
    # Direct path
    ai_insights = None
    processed_data = inputs.get("merged", [])

# Flatten if nested
if processed_data and isinstance(processed_data[0], list):
    all_files = []
    for batch in processed_data:
        all_files.extend(batch)
else:
    all_files = processed_data

# Calculate statistics
total_files = len(all_files)
successful = sum(1 for f in all_files if f.get("status") == "success")
failed = sum(1 for f in all_files if f.get("status") == "failed")

# Group by processor
by_processor = {}
for file in all_files:
    processor = file.get("processor", "unknown")
    if processor not in by_processor:
        by_processor[processor] = []
    by_processor[processor].append(file)

# Create summary
summary = {
    "processing_summary": {
        "total_files_processed": total_files,
        "successful": successful,
        "failed": failed,
        "success_rate": f"{(successful/total_files*100):.1f}%" if total_files > 0 else "0%",
        "processors_used": list(by_processor.keys()),
        "timestamp": datetime.now().isoformat()
    },
    "detailed_results": all_files,
    "by_processor": {
        processor: {
            "count": len(files),
            "successful": sum(1 for f in files if f.get("status") == "success"),
            "failed": sum(1 for f in files if f.get("status") == "failed")
        }
        for processor, files in by_processor.items()
    }
}

# Add AI insights if available
if ai_insights:
    summary["ai_insights"] = ai_insights

# Generate recommendations
recommendations = []
if failed > 0:
    recommendations.append(f"Review {failed} failed file(s) for processing errors")

if "csv_processor" in by_processor:
    csv_files = by_processor["csv_processor"]
    for file in csv_files:
        if file.get("status") == "success":
            result = file.get("processing_result", {})
            if result.get("detected_fields", {}).get("has_email"):
                recommendations.append("Consider email validation for CSV files with email fields")
            if result.get("null_counts"):
                high_nulls = [col for col, count in result["null_counts"].items() if count > result.get("rows", 1) * 0.5]
                if high_nulls:
                    recommendations.append(f"High null values detected in columns: {', '.join(high_nulls)}")

summary["recommendations"] = recommendations

result = summary
""",
    )
    workflow.add_node("summary_generator", summary_generator)

    if enable_ai and AI_AVAILABLE:
        workflow.connect(
            "ai_analyzer",
            "summary_generator",
            mapping={"response": "response", "processed_files": "processed_files"},
        )
    else:
        workflow.connect(
            "result_merger", "summary_generator", mapping={"merged": "merged"}
        )

    # === STAGE 7: OUTPUT ===

    # Write final summary
    summary_writer = JSONWriterNode(
        name="summary_writer",
        file_path="data/outputs/document_processing_summary.json",
        pretty_print=True,
    )
    workflow.add_node("summary_writer", summary_writer)
    workflow.connect("summary_generator", "summary_writer", mapping={"result": "data"})

    return workflow


def ensure_sample_files():
    """Create sample input files for testing."""
    os.makedirs("data/inputs", exist_ok=True)
    os.makedirs("data/outputs", exist_ok=True)

    # Sample CSV
    csv_content = """id,name,email,status,created_date
1,John Doe,john@example.com,active,2024-01-15
2,Jane Smith,jane@company.org,active,2024-02-20
3,Bob Wilson,bob@test.net,inactive,2024-01-10
4,Alice Brown,alice@example.com,active,2024-03-05
5,Charlie Davis,,pending,2024-03-12"""

    with open("data/inputs/customers.csv", "w") as f:
        f.write(csv_content)

    # Sample JSON
    json_content = {
        "config": {
            "version": "1.0",
            "settings": {"debug": False, "timeout": 30, "retry_count": 3},
        },
        "data": [
            {"id": 1, "value": 100},
            {"id": 2, "value": 200},
            {"id": 3, "value": 150},
        ],
    }

    with open("data/inputs/config.json", "w") as f:
        json.dump(json_content, f, indent=2)

    # Sample text
    text_content = """# Project Documentation

This is a sample documentation file for testing the document processor.

## Features
- Dynamic file discovery
- Multi-format support
- AI-powered analysis (optional)

## Usage
Run the script with Python 3.7+:
```bash
python document_processor_consolidated.py
```

For more information, visit https://example.com/docs
Contact: support@example.com
"""

    with open("data/inputs/readme.md", "w") as f:
        f.write(text_content)

    print("✅ Created sample input files")


def main():
    """Run the document processing workflow."""
    # Ensure we have sample files
    ensure_sample_files()

    # Check if AI is available
    enable_ai = AI_AVAILABLE and os.environ.get("OLLAMA_HOST") is not None

    if enable_ai:
        print("🤖 AI enhancement enabled (using Ollama)")
    else:
        print("📝 Running in basic mode (AI not available)")

    # Create and run workflow
    workflow = create_document_processing_workflow(enable_ai=enable_ai)
    runtime = LocalRuntime()

    print("\n🔄 Starting document processing...")

    try:
        result, run_id = runtime.execute(workflow)
        print(f"\n✅ Processing complete! Run ID: {run_id}")

        # Display summary
        if "summary_writer" in result:
            summary_path = "data/outputs/document_processing_summary.json"
            print(f"\n📊 Summary written to: {summary_path}")

            # Show brief stats
            with open(summary_path) as f:
                summary = json.load(f)
                stats = summary.get("processing_summary", {})
                print("\n📈 Statistics:")
                print(f"  - Total files: {stats.get('total_files_processed', 0)}")
                print(f"  - Success rate: {stats.get('success_rate', 'N/A')}")
                print(f"  - Processors: {', '.join(stats.get('processors_used', []))}")

                if summary.get("recommendations"):
                    print("\n💡 Recommendations:")
                    for rec in summary["recommendations"][:3]:
                        print(f"  - {rec}")

                if summary.get("ai_insights"):
                    print("\n🤖 AI Insights:")
                    print(f"  {summary['ai_insights'][:200]}...")

    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

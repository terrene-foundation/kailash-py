#!/usr/bin/env python3
"""
Examples Overview - Visual summary of all Kailash SDK examples
"""


import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from examples.utils.data_paths import (  # noqa: E402
    ensure_output_dir_exists,
    get_output_data_path,
)

# Define example categories and their descriptions
examples = {
    "Basic Concepts": [
        ("basic_workflow.py", "Simple ETL workflow with validation"),
        ("custom_node.py", "Creating custom nodes and extensions"),
        ("cli_example.sh", "Command-line interface usage"),
    ],
    "Advanced Workflows": [
        ("complex_workflow.py", "Multi-node parallel processing"),
        ("ai_pipeline.py", "Complete ML pipeline with AI agents"),
        ("data_transformation.py", "Comprehensive data processing"),
    ],
    "Production Features": [
        ("task_tracking_example.py", "Task management and monitoring"),
        ("error_handling.py", "Resilient error handling patterns"),
        ("export_workflow.py", "Deployment and export capabilities"),
    ],
    "Visualization": [("visualization_example.py", "Workflow visualization options")],
}

# Create a visual overview
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle("Kailash Python SDK - Examples Overview", fontsize=20, fontweight="bold")

# Colors for categories
colors = ["#3498db", "#2ecc71", "#f39c12", "#9b59b6"]

# 1. Example Distribution by Category
ax1.set_title("Examples by Category", fontsize=14, fontweight="bold")
categories = list(examples.keys())
counts = [len(examples[cat]) for cat in categories]
bars = ax1.bar(categories, counts, color=colors)
ax1.set_ylabel("Number of Examples")
ax1.set_xticklabels(categories, rotation=45, ha="right")

# Add value labels on bars
for bar, count in zip(bars, counts, strict=False):
    height = bar.get_height()
    ax1.text(
        bar.get_x() + bar.get_width() / 2.0,
        height,
        f"{count}",
        ha="center",
        va="bottom",
    )

# 2. Complexity Level Distribution
ax2.set_title("Examples by Complexity", fontsize=14, fontweight="bold")
complexity_levels = {
    "Beginner": ["basic_workflow.py", "cli_example.sh"],
    "Intermediate": [
        "custom_node.py",
        "data_transformation.py",
        "visualization_example.py",
    ],
    "Advanced": [
        "complex_workflow.py",
        "ai_pipeline.py",
        "task_tracking_example.py",
        "error_handling.py",
        "export_workflow.py",
    ],
}
complexity_counts = [len(files) for files in complexity_levels.values()]
wedges, texts, autotexts = ax2.pie(
    complexity_counts,
    labels=list(complexity_levels.keys()),
    autopct="%1.1f%%",
    colors=colors[:3],
)
ax2.axis("equal")

# 3. Feature Coverage
ax3.set_title("Feature Coverage", fontsize=14, fontweight="bold")
features = {
    "Data Processing": 8,
    "AI/ML Integration": 3,
    "Error Handling": 5,
    "Visualization": 4,
    "Task Management": 2,
    "Deployment": 2,
    "Custom Nodes": 3,
}
feature_names = list(features.keys())
feature_counts = list(features.values())
y_pos = np.arange(len(feature_names))
bars = ax3.barh(y_pos, feature_counts, color="#3498db")
ax3.set_yticks(y_pos)
ax3.set_yticklabels(feature_names)
ax3.set_xlabel("Number of Examples")
ax3.invert_yaxis()

# Add value labels
for i, (bar, count) in enumerate(zip(bars, feature_counts, strict=False)):
    width = bar.get_width()
    ax3.text(
        width + 0.1,
        bar.get_y() + bar.get_height() / 2,
        f"{count}",
        ha="left",
        va="center",
    )

# 4. Example Details Table
ax4.set_title("Quick Reference Guide", fontsize=14, fontweight="bold")
ax4.axis("off")

# Create table data
table_data = []
for category, files in examples.items():
    for filename, description in files:
        table_data.append([filename, category, description[:50] + "..."])

# Sort by filename
table_data.sort(key=lambda x: x[0])

# Create table
table = ax4.table(
    cellText=table_data,
    colLabels=["Example File", "Category", "Description"],
    cellLoc="left",
    loc="center",
)
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1.2, 1.5)

# Style the table
for i in range(len(table_data) + 1):
    for j in range(3):
        cell = table[(i, j)]
        if i == 0:  # Header row
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#3498db")
            cell.set_text_props(color="white")
        else:
            if i % 2 == 0:
                cell.set_facecolor("#ecf0f1")
            else:
                cell.set_facecolor("white")

plt.tight_layout()
# Ensure output directory exists
ensure_output_dir_exists("images")
output_path = get_output_data_path("examples_overview.png", "images")
plt.savefig(str(output_path), dpi=300, bbox_inches="tight")
plt.close()

# Create a text summary
summary_text = """
# Kailash Python SDK Examples Summary

## Overview
The Kailash Python SDK includes comprehensive examples covering all major features:

### Categories:
1. **Basic Concepts** ({} examples)
   - Introduction to nodes and workflows
   - Command-line interface usage
   - Custom node creation

2. **Advanced Workflows** ({} examples)
   - Complex multi-node workflows
   - AI/ML pipeline integration
   - Advanced data transformations

3. **Production Features** ({} examples)
   - Task tracking and monitoring
   - Error handling and recovery
   - Export and deployment

4. **Visualization** ({} examples)
   - Workflow visualization options

## Getting Started
1. Start with `basic_workflow.py` for fundamental concepts
2. Explore `custom_node.py` to learn about extensions
3. Study `complex_workflow.py` for advanced patterns
4. Review `error_handling.py` for production best practices

## Requirements
- Python 3.8+
- Kailash SDK installed
- Additional dependencies in requirements.txt

## Running Examples
```bash
python example_name.py
```

Or run all examples:
```bash
./run_all_examples.sh
```
""".format(
    len(examples["Basic Concepts"]),
    len(examples["Advanced Workflows"]),
    len(examples["Production Features"]),
    len(examples["Visualization"]),
)

# Save summary
output_dir = Path("outputs")
output_dir.mkdir(exist_ok=True)
summary_path = output_dir / "examples_summary.md"
with open(summary_path, "w") as f:
    f.write(summary_text)

print("✓ Examples overview created:")
print(f"  - Visual summary: {output_path}")
print(f"  - Text summary: {summary_path}")

# Create an index of all examples
index_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Kailash SDK Examples</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .category { margin: 20px 0; }
        .category h2 { color: #3498db; }
        .example { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px; }
        .example h3 { margin: 0 0 5px 0; }
        .example p { margin: 5px 0; color: #666; }
        .example code { background: #e9ecef; padding: 2px 5px; border-radius: 3px; }
    </style>
</head>
<body>
    <h1>Kailash Python SDK Examples</h1>
"""

for category, files in examples.items():
    index_html += f'<div class="category"><h2>{category}</h2>'
    for filename, description in files:
        index_html += f"""
        <div class="example">
            <h3>{filename}</h3>
            <p>{description}</p>
            <p>Run: <code>python {filename}</code></p>
        </div>
        """
    index_html += "</div>"

index_html += """
</body>
</html>
"""

index_path = output_dir / "examples_index.html"
with open(index_path, "w") as f:
    f.write(index_html)

print(f"  - HTML index: {index_path}")

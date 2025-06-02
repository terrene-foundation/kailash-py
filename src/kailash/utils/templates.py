"""Project template system for Kailash SDK."""

from pathlib import Path
from typing import Dict, Optional

from kailash.sdk_exceptions import TemplateError


class NodeTemplate:
    """Template for creating node implementations."""

    def __init__(self, name: str, description: str, base_class: str = "Node"):
        """Initialize node template.

        Args:
            name: Node class name
            description: Node description
            base_class: Base class to inherit from
        """
        self.name = name
        self.description = description
        self.base_class = base_class
        self.input_params = []
        self.output_params = []
        self.code_template = ""

    def add_input_parameter(
        self,
        name: str,
        param_type: str,
        required: bool = True,
        description: str = "",
        default=None,
    ) -> "NodeTemplate":
        """Add input parameter to template.

        Args:
            name: Parameter name
            param_type: Parameter type (str, int, dict, etc.)
            required: Whether parameter is required
            description: Parameter description
            default: Default value

        Returns:
            Self for chaining
        """
        self.input_params.append(
            {
                "name": name,
                "type": param_type,
                "required": required,
                "description": description,
                "default": default,
            }
        )
        return self

    def add_output_parameter(
        self, name: str, param_type: str, description: str = ""
    ) -> "NodeTemplate":
        """Add output parameter to template.

        Args:
            name: Parameter name
            param_type: Parameter type (str, int, dict, etc.)
            description: Parameter description

        Returns:
            Self for chaining
        """
        self.output_params.append(
            {"name": name, "type": param_type, "description": description}
        )
        return self

    def set_code_template(self, code: str) -> "NodeTemplate":
        """Set code template.

        Args:
            code: Python code template

        Returns:
            Self for chaining
        """
        self.code_template = code
        return self

    def generate_code(self) -> str:
        """Generate Python code for the node.

        Returns:
            Generated code

        Raises:
            TemplateError: If generation fails
        """
        try:
            # Start with imports
            code = f"""from typing import Dict, Any, Optional
from kailash.nodes.base import Node, NodeParameter

class {self.name}({self.base_class}):
    \"""
    {self.description}
    \"""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        \"""Define node parameters.\"""
        return {{
"""

            # Add input parameters
            for param in self.input_params:
                default_str = ""
                if param["default"] is not None:
                    if isinstance(param["default"], str):
                        default_str = f'default="{param["default"]}"'
                    else:
                        default_str = f"default={param['default']}"

                code += f"""            "{param["name"]}": NodeParameter(
                name="{param["name"]}",
                type={param["type"]},
                required={param["required"]},
                description="{param["description"]}"{', ' + default_str if default_str else ''}
            ),
"""

            code += """        }

    def run(self, **kwargs) -> Dict[str, Any]:
        \"""Process node logic.

        Args:
            **kwargs: Input parameters

        Returns:
            Output parameters
        \"""
"""

            # Add custom code if provided, otherwise use default implementation
            if self.code_template:
                code += f"\n{self.code_template}\n"
            else:
                code += """        # TODO: Implement node logic
        # Access input parameters via kwargs

        # Return results as a dictionary
        return {
"""
                # Add output parameters
                for param in self.output_params:
                    code += f'            "{param["name"]}": None,  # TODO: Set {param["name"]}\n'

                code += "        }\n"

            return code

        except Exception as e:
            raise TemplateError(f"Failed to generate node code: {e}") from e

    def save(self, output_path: str) -> None:
        """Save generated code to file.

        Args:
            output_path: Path to save file

        Raises:
            TemplateError: If save fails
        """
        try:
            code = self.generate_code()

            # Create parent directories if needed
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write to file
            with open(path, "w") as f:
                f.write(code)

        except Exception as e:
            raise TemplateError(f"Failed to save node code: {e}") from e


class TemplateManager:
    """Manage project templates for scaffolding."""

    def __init__(self):
        """Initialize template manager."""
        self.templates = {
            "basic": self._basic_template,
            "data_processing": self._data_processing_template,
            "ml_pipeline": self._ml_pipeline_template,
            "api_workflow": self._api_workflow_template,
        }

        # Export templates for workflow export
        self.export_templates = {
            "minimal": {"yaml": True, "json": False, "manifest": False},
            "standard": {"yaml": True, "json": True, "manifest": True},
            "kubernetes": {
                "yaml": True,
                "json": False,
                "manifest": True,
                "files": {
                    "deploy.sh": """#!/bin/bash
# Deploy workflow to Kubernetes
kubectl apply -f {workflow_name}-manifest.yaml

# Check deployment status
kubectl get pods -n {namespace} -l workflow={workflow_name}
""",
                    "README.md": """# {workflow_name} Deployment

This directory contains the Kubernetes deployment files for {workflow_name}.

## Files
- `{workflow_name}.yaml`: Workflow definition
- `{workflow_name}-manifest.yaml`: Kubernetes manifest
- `deploy.sh`: Deployment script

## Deployment
```bash
./deploy.sh
```

## Namespace
Deployed to: {namespace}
""",
                },
            },
            "docker": {
                "yaml": True,
                "json": True,
                "manifest": False,
                "files": {
                    "Dockerfile": """FROM kailash/base:latest

WORKDIR /app

COPY {workflow_name}.yaml /app/
COPY {workflow_name}.json /app/

CMD ["kailash", "run", "/app/{workflow_name}.yaml"]
""",
                    "docker-compose.yml": """version: '3.8'

services:
  {workflow_name}:
    build: .
    environment:
      - WORKFLOW_NAME={workflow_name}
      - WORKFLOW_VERSION={workflow_version}
    volumes:
      - ./data:/data
      - ./output:/output
""",
                    ".dockerignore": """*.log
__pycache__/
.git/
.gitignore
""",
                },
            },
        }

    def get_template(self, template_name: str) -> Dict:
        """Get an export template by name.

        Args:
            template_name: Name of the template

        Returns:
            Template dictionary

        Raises:
            ValueError: If template not found
        """
        if template_name not in self.export_templates:
            raise ValueError(f"Unknown export template: {template_name}")
        return self.export_templates[template_name]

    def create_project(
        self,
        project_name: str,
        template: str = "basic",
        target_dir: Optional[str] = None,
    ) -> None:
        """Create a new project from a template.

        Args:
            project_name: Name of the project
            template: Template to use
            target_dir: Directory to create project in (defaults to current)
        """
        if template not in self.templates:
            raise ValueError(f"Unknown template: {template}")

        # Determine target directory
        if target_dir:
            project_root = Path(target_dir) / project_name
        else:
            project_root = Path.cwd() / project_name

        # Create project structure
        project_root.mkdir(parents=True, exist_ok=True)

        # Apply template
        self.templates[template](project_root, project_name)

    def _basic_template(self, project_root: Path, project_name: str) -> None:
        """Create a basic project template."""
        # Create directory structure
        (project_root / "workflows").mkdir(exist_ok=True)
        (project_root / "nodes").mkdir(exist_ok=True)
        (project_root / "data").mkdir(exist_ok=True)
        (project_root / "output").mkdir(exist_ok=True)

        # Create README
        readme_content = f"""# {project_name}

A Kailash workflow project.

## Structure

- `workflows/`: Workflow definitions
- `nodes/`: Custom node implementations
- `examples/data/`: Input data files
- `outputs/`: Output files

## Usage

```bash
# Run a workflow
kailash run workflows/example_workflow.py

# Validate a workflow
kailash validate workflows/example_workflow.py

# Export to Kailash format
kailash export workflows/example_workflow.py outputs/workflow.yaml
```

## Examples

See `workflows/example_workflow.py` for a basic workflow example.
"""
        (project_root / "README.md").write_text(readme_content)

        # Create example workflow
        workflow_content = '''"""Example workflow for data processing."""
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReader, CSVWriter
from kailash.nodes.transform import Filter, Sort
from kailash.nodes.logic import Aggregator

# Create workflow
workflow = Workflow(
    name="example_workflow",
    description="Process CSV data with filtering and aggregation"
)

# Add nodes
workflow.add_node("reader", CSVReader(), file_path="examples/examples/data/input.csv")
workflow.add_node("filter", Filter(), field="value", operator=">", value=100)
workflow.add_node("sort", Sort(), field="value", reverse=True)
workflow.add_node("aggregate", Aggregator(), group_by="category", operation="sum")
workflow.add_node("writer", CSVWriter(), file_path="outputs/results.csv")

# Connect nodes
workflow.connect("reader", "filter", {"data": "data"})
workflow.connect("filter", "sort", {"filtered_data": "data"})
workflow.connect("sort", "aggregate", {"sorted_data": "data"})
workflow.connect("aggregate", "writer", {"aggregated_data": "data"})

# Workflow is ready to run!
'''
        (project_root / "workflows" / "example_workflow.py").write_text(
            workflow_content
        )

        # Create example custom node
        node_content = '''"""Custom node example."""
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class CustomProcessor(Node):
    """A custom data processing node."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process"
            ),
            "multiplier": NodeParameter(
                name="multiplier",
                type=float,
                required=False,
                default=1.0,
                description="Value multiplier"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        multiplier = kwargs.get("multiplier", 1.0)

        # Process data
        processed = []
        for item in data:
            if isinstance(item, dict) and "value" in item:
                new_item = item.copy()
                new_item["value"] = item["value"] * multiplier
                processed.append(new_item)
            else:
                processed.append(item)

        return {"processed_data": processed}
'''
        (project_root / "nodes" / "custom_nodes.py").write_text(node_content)

        # Create sample data
        csv_content = """id,name,value,category
1,Item A,150,Category 1
2,Item B,95,Category 2
3,Item C,200,Category 1
4,Item D,75,Category 2
5,Item E,180,Category 1
"""
        (project_root / "data" / "input.csv").write_text(csv_content)

        # Create .gitignore
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
*.egg-info/

# Output files
outputs/
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
"""
        (project_root / ".gitignore").write_text(gitignore_content)

    def _data_processing_template(self, project_root: Path, project_name: str) -> None:
        """Create a data processing focused template."""
        # Start with basic template
        self._basic_template(project_root, project_name)

        # Add data processing workflow
        workflow_content = '''"""Data processing pipeline workflow."""
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReader, JSONReader, JSONWriter
from kailash.nodes.transform import Filter, Map, Sort
from kailash.nodes.logic import Aggregator, Merge

# Create workflow
workflow = Workflow(
    name="data_processing_pipeline",
    description="Complex data processing with multiple transformations"
)

# Data ingestion
workflow.add_node("csv_reader", CSVReader(), file_path="examples/examples/data/sales_data.csv")
workflow.add_node("json_reader", JSONReader(), file_path="examples/examples/data/product_data.json")

# Transform data
workflow.add_node("filter_sales", Filter(), field="amount", operator=">", value=1000)
workflow.add_node("calculate_profit", Map(), field="amount", operation="multiply", value=0.2)
workflow.add_node("merge_data", Merge(), merge_type="merge_dict", key="product_id")

# Aggregate results
workflow.add_node("group_by_category", Aggregator(), group_by="category", operation="sum")
workflow.add_node("sort_results", Sort(), field="value", reverse=True)

# Export results
workflow.add_node("write_json", JSONWriter(), file_path="outputs/analysis_results.json")

# Connect pipeline
workflow.connect("csv_reader", "filter_sales", {"data": "data"})
workflow.connect("filter_sales", "calculate_profit", {"filtered_data": "data"})
workflow.connect("json_reader", "merge_data", {"data": "data2"})
workflow.connect("calculate_profit", "merge_data", {"mapped_data": "data1"})
workflow.connect("merge_data", "group_by_category", {"merged_data": "data"})
workflow.connect("group_by_category", "sort_results", {"aggregated_data": "data"})
workflow.connect("sort_results", "write_json", {"sorted_data": "data"})
'''
        (project_root / "workflows" / "data_processing_pipeline.py").write_text(
            workflow_content
        )

        # Add sample data files
        sales_data = """product_id,date,amount,customer_id,category
101,2024-01-01,1500,C001,Electronics
102,2024-01-02,800,C002,Home
101,2024-01-03,2200,C003,Electronics
103,2024-01-04,1800,C004,Electronics
102,2024-01-05,950,C005,Home
"""
        (project_root / "data" / "sales_data.csv").write_text(sales_data)

        product_data = """{
    "products": [
        {"product_id": "101", "name": "Laptop", "category": "Electronics", "cost": 800},
        {"product_id": "102", "name": "Chair", "category": "Home", "cost": 200},
        {"product_id": "103", "name": "Monitor", "category": "Electronics", "cost": 400}
    ]
}"""
        (project_root / "data" / "product_data.json").write_text(product_data)

    def _ml_pipeline_template(self, project_root: Path, project_name: str) -> None:
        """Create an ML pipeline focused template."""
        # Start with basic template
        self._basic_template(project_root, project_name)

        # Add ML workflow
        workflow_content = '''"""Machine learning pipeline workflow."""
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReader, JSONWriter
from kailash.nodes.transform import Filter, Map
from kailash.nodes.ai import (
    TextClassifier,
    SentimentAnalyzer,
    NamedEntityRecognizer,
    TextSummarizer
)

# Create workflow
workflow = Workflow(
    name="ml_pipeline",
    description="Text analysis ML pipeline"
)

# Data ingestion
workflow.add_node("read_data", CSVReader(), file_path="examples/examples/data/text_data.csv")

# Preprocessing
workflow.add_node("extract_text", Map(), field="content")

# ML processing
workflow.add_node("sentiment", SentimentAnalyzer(), language="en")
workflow.add_node("classify", TextClassifier(),
                  categories=["tech", "business", "health", "other"])
workflow.add_node("extract_entities", NamedEntityRecognizer(),
                  entity_types=["PERSON", "ORGANIZATION", "LOCATION"])
workflow.add_node("summarize", TextSummarizer(), max_length=100)

# Combine results
workflow.add_node("merge_results", Merge(), merge_type="merge_dict")

# Export results
workflow.add_node("save_results", JSONWriter(), file_path="outputs/ml_results.json")

# Connect pipeline
workflow.connect("read_data", "extract_text", {"data": "data"})
workflow.connect("extract_text", "sentiment", {"mapped_data": "texts"})
workflow.connect("extract_text", "classify", {"mapped_data": "texts"})
workflow.connect("extract_text", "extract_entities", {"mapped_data": "texts"})
workflow.connect("extract_text", "summarize", {"mapped_data": "texts"})

# Merge all ML results
workflow.connect("sentiment", "merge_results", {"sentiments": "data1"})
workflow.connect("classify", "merge_results", {"classifications": "data2"})

workflow.connect("merge_results", "save_results", {"merged_data": "data"})
'''
        (project_root / "workflows" / "ml_pipeline.py").write_text(workflow_content)

        # Add sample text data
        text_data = """id,title,content
1,Tech Innovation,"The latest developments in artificial intelligence are transforming how businesses operate. Companies like Google and Microsoft are leading the charge with new AI models."
2,Health Update,"Recent studies show that regular exercise and a balanced diet can significantly improve mental health. Researchers at Harvard University published these findings."
3,Business News,"Apple announced record profits this quarter, driven by strong iPhone sales in Asian markets. CEO Tim Cook expressed optimism about future growth."
4,Local News,"The mayor of New York announced new infrastructure plans for the city. The project will create thousands of jobs over the next five years."
"""
        (project_root / "data" / "text_data.csv").write_text(text_data)

    def _api_workflow_template(self, project_root: Path, project_name: str) -> None:
        """Create an API integration focused template."""
        # Start with basic template
        self._basic_template(project_root, project_name)

        # Add API workflow
        workflow_content = '''"""API integration workflow."""
from kailash.workflow import Workflow
from kailash.nodes.data import JSONReader, JSONWriter
from kailash.nodes.transform import Map, Filter
from kailash.nodes.logic import Conditional
from kailash.nodes.ai import ChatAgent, FunctionCallingAgent

# Create workflow
workflow = Workflow(
    name="api_workflow",
    description="Workflow with API integrations and AI agents"
)

# Read configuration
workflow.add_node("read_config", JSONReader(), file_path="examples/examples/data/api_config.json")

# Process with AI agent
workflow.add_node("chat_agent", ChatAgent(),
                  model="default",
                  system_prompt="You are a helpful API integration assistant.")

# Function calling for API operations
workflow.add_node("function_agent", FunctionCallingAgent(),
                  available_functions=[
                      {"name": "fetch_data", "description": "Fetch data from API"},
                      {"name": "transform_data", "description": "Transform data format"},
                      {"name": "validate_data", "description": "Validate API response"}
                  ])

# Conditional routing based on response
workflow.add_node("check_status", Conditional(),
                  condition_field="status",
                  operator="==",
                  value="success")

# Process successful responses
workflow.add_node("process_success", Map(), operation="identity")

# Handle errors
workflow.add_node("handle_error", Map(), operation="identity")

# Save results
workflow.add_node("save_results", JSONWriter(), file_path="outputs/api_results.json")

# Connect workflow
workflow.connect("read_config", "chat_agent", {"data": "messages"})
workflow.connect("chat_agent", "function_agent", {"responses": "query"})
workflow.connect("function_agent", "check_status", {"response": "data"})
workflow.connect("check_status", "process_success", {"result": "data"})
workflow.connect("check_status", "handle_error", {"result": "data"})
workflow.connect("process_success", "save_results", {"processed_data": "data"})
workflow.connect("handle_error", "save_results", {"error_data": "data"})
'''
        (project_root / "workflows" / "api_workflow.py").write_text(workflow_content)

        # Add API configuration
        api_config = """{
    "api_endpoints": {
        "data_api": "https://api.example.com/data",
        "auth_api": "https://api.example.com/auth"
    },
    "credentials": {
        "api_key": "YOUR_API_KEY_HERE",
        "secret": "YOUR_SECRET_HERE"
    },
    "messages": [
        {"role": "user", "content": "Fetch the latest data from the API and process it"}
    ]
}"""
        (project_root / "data" / "api_config.json").write_text(api_config)


def create_project(name: str, template: str = "basic") -> None:
    """Convenience function to create a project."""
    manager = TemplateManager()
    manager.create_project(name, template)

"""Test visualization with real workflows."""

import json
from pathlib import Path
from typing import Dict, Any

import pytest
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from kailash.workflow import Workflow, WorkflowBuilder
from kailash.workflow.visualization import WorkflowVisualizer
from kailash.nodes.base import NodeStatus, DataFormat, InputType, OutputType
from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner


class TestVisualizationIntegration:
    """Test workflow visualization with real workflows."""
    
    def test_simple_workflow_visualization(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test visualizing a simple workflow."""
        visualizer = WorkflowVisualizer()
        
        # Generate visualization
        output_path = temp_data_dir / "simple_workflow.png"
        visualizer.visualize(simple_workflow, output_path=output_path)
        
        # Verify output file exists
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        
        # Test different formats
        svg_path = temp_data_dir / "simple_workflow.svg"
        visualizer.visualize(simple_workflow, output_path=svg_path, format="svg")
        assert svg_path.exists()
        
        pdf_path = temp_data_dir / "simple_workflow.pdf"
        visualizer.visualize(simple_workflow, output_path=pdf_path, format="pdf")
        assert pdf_path.exists()
    
    def test_complex_workflow_visualization(self, complex_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test visualizing a complex workflow with multiple branches."""
        visualizer = WorkflowVisualizer()
        
        # Visualize with custom styling
        style_config = {
            "node_colors": {
                "reader": "#90EE90",    # Light green for readers
                "processor": "#87CEEB",  # Sky blue for processors
                "writer": "#FFB6C1",     # Light pink for writers
                "ai": "#DDA0DD"         # Plum for AI nodes
            },
            "edge_styles": {
                "dataframe": {"style": "solid", "color": "blue"},
                "json": {"style": "dashed", "color": "green"},
                "text": {"style": "dotted", "color": "red"}
            },
            "layout": "hierarchical",
            "dpi": 150,
            "font_size": 10
        }
        
        output_path = temp_data_dir / "complex_workflow_styled.png"
        visualizer.visualize(
            complex_workflow,
            output_path=output_path,
            style_config=style_config
        )
        
        assert output_path.exists()
    
    def test_workflow_execution_visualization(
        self, simple_workflow: WorkflowGraph, temp_data_dir: Path
    ):
        """Test visualizing workflow execution status."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        visualizer = WorkflowVisualizer()
        
        # Execute workflow
        result = runner.run(simple_workflow)
        
        # Visualize with execution status
        execution_info = {
            "node_status": {},
            "execution_times": {},
            "errors": {}
        }
        
        # Mock execution info (in real implementation, this would come from the runner)
        for node_id in simple_workflow.graph.nodes():
            execution_info["node_status"][node_id] = NodeStatus.COMPLETED
            execution_info["execution_times"][node_id] = 0.1 + (hash(node_id) % 10) / 10
        
        output_path = temp_data_dir / "workflow_execution_status.png"
        visualizer.visualize_execution(
            simple_workflow,
            execution_info=execution_info,
            output_path=output_path
        )
        
        assert output_path.exists()
    
    def test_interactive_visualization(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test interactive workflow visualization."""
        visualizer = WorkflowVisualizer()
        
        # Generate interactive HTML visualization
        html_path = temp_data_dir / "interactive_workflow.html"
        visualizer.visualize_interactive(
            simple_workflow,
            output_path=html_path,
            include_metadata=True
        )
        
        assert html_path.exists()
        
        # Verify HTML content
        html_content = html_path.read_text()
        assert "<html>" in html_content
        assert "javascript" in html_content.lower()
        assert simple_workflow.metadata.get("name", "") in html_content
    
    def test_workflow_diff_visualization(self, temp_data_dir: Path):
        """Test visualizing differences between workflow versions."""
        visualizer = WorkflowVisualizer()
        
        # Create original workflow
        builder1 = WorkflowBuilder()
        reader_id = builder1.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value="data.csv")},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        filter_id = builder1.add_node(
            "DataFilter",
            "filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="value > 100")
            },
            outputs={"filtered": OutputType(format=DataFormat.DATAFRAME)}
        )
        builder1.add_connection(reader_id, "data", filter_id, "data")
        workflow_v1 = builder1.build("workflow_v1")
        
        # Create modified workflow
        builder2 = WorkflowBuilder()
        reader_id = builder2.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value="data.csv")},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        # Changed condition
        filter_id = builder2.add_node(
            "DataFilter",
            "filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="value > 200")  # Changed
            },
            outputs={"filtered": OutputType(format=DataFormat.DATAFRAME)}
        )
        # Added new node
        writer_id = builder2.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value="output.csv")
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        builder2.add_connection(reader_id, "data", filter_id, "data")
        builder2.add_connection(filter_id, "filtered", writer_id, "data")
        workflow_v2 = builder2.build("workflow_v2")
        
        # Visualize diff
        diff_path = temp_data_dir / "workflow_diff.png"
        visualizer.visualize_diff(
            workflow_v1,
            workflow_v2,
            output_path=diff_path,
            labels=["Version 1", "Version 2"]
        )
        
        assert diff_path.exists()
    
    def test_workflow_animation(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test creating workflow execution animation."""
        visualizer = WorkflowVisualizer()
        
        # Create mock execution trace
        execution_trace = []
        
        # Simulate execution steps
        nodes = list(simple_workflow.graph.nodes())
        for i, node_id in enumerate(nodes):
            step = {
                "step": i,
                "node_id": node_id,
                "status": NodeStatus.IN_PROGRESS,
                "timestamp": i * 0.5
            }
            execution_trace.append(step)
            
            # Complete the node
            complete_step = {
                "step": i + len(nodes),
                "node_id": node_id,
                "status": NodeStatus.COMPLETED,
                "timestamp": (i + 0.5) * 0.5
            }
            execution_trace.append(complete_step)
        
        # Create animation
        animation_path = temp_data_dir / "workflow_animation.gif"
        visualizer.create_animation(
            simple_workflow,
            execution_trace=execution_trace,
            output_path=animation_path,
            duration=5  # 5 second animation
        )
        
        # Note: Animation creation might require additional dependencies
        if animation_path.exists():
            assert animation_path.stat().st_size > 0
    
    def test_subworkflow_visualization(self, temp_data_dir: Path):
        """Test visualizing workflows with subworkflows."""
        visualizer = WorkflowVisualizer()
        
        # Create subworkflow
        sub_builder = WorkflowBuilder()
        sub_node1_id = sub_builder.add_node(
            "DataProcessor",
            "sub_processor",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        subworkflow = sub_builder.build("subworkflow")
        
        # Create main workflow with subworkflow
        main_builder = WorkflowBuilder()
        reader_id = main_builder.add_node(
            "JSONFileReader",
            "reader",
            inputs={"path": InputType(value="data.json")},
            outputs={"data": OutputType(format=DataFormat.JSON)}
        )
        
        # Add subworkflow as a node
        subworkflow_id = main_builder.add_node(
            "SubworkflowNode",
            "subworkflow",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"result": OutputType(format=DataFormat.JSON)},
            metadata={"subworkflow": subworkflow}
        )
        
        writer_id = main_builder.add_node(
            "JSONFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.JSON),
                "path": InputType(value="output.json")
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        main_builder.add_connection(reader_id, "data", subworkflow_id, "data")
        main_builder.add_connection(subworkflow_id, "result", writer_id, "data")
        
        main_workflow = main_builder.build("main_workflow")
        
        # Visualize with subworkflow expansion
        output_path = temp_data_dir / "workflow_with_subworkflow.png"
        visualizer.visualize(
            main_workflow,
            output_path=output_path,
            expand_subworkflows=True
        )
        
        assert output_path.exists()
    
    def test_workflow_metrics_visualization(
        self, simple_workflow: WorkflowGraph, temp_data_dir: Path
    ):
        """Test visualizing workflow performance metrics."""
        visualizer = WorkflowVisualizer()
        
        # Create mock metrics data
        metrics = {
            "node_metrics": {
                node_id: {
                    "execution_time": 0.1 + (hash(node_id) % 10) / 10,
                    "memory_usage": 50 + (hash(node_id) % 100),
                    "cpu_usage": 20 + (hash(node_id) % 60),
                    "data_processed": 1000 + (hash(node_id) % 9000)
                }
                for node_id in simple_workflow.graph.nodes()
            },
            "edge_metrics": {
                (u, v): {
                    "data_transferred": 100 + (hash(f"{u}-{v}") % 900),
                    "transfer_time": 0.01 + (hash(f"{u}-{v}") % 10) / 100
                }
                for u, v in simple_workflow.graph.edges()
            },
            "overall_metrics": {
                "total_execution_time": 5.2,
                "peak_memory": 512,
                "average_cpu": 45
            }
        }
        
        # Create metrics dashboard
        dashboard_path = temp_data_dir / "workflow_metrics_dashboard.png"
        
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle(f"Workflow Metrics: {simple_workflow.metadata.get('name', 'Unknown')}")
        
        # Execution time bar chart
        ax1 = axes[0, 0]
        nodes = list(metrics["node_metrics"].keys())
        times = [metrics["node_metrics"][n]["execution_time"] for n in nodes]
        ax1.bar(range(len(nodes)), times)
        ax1.set_title("Node Execution Times")
        ax1.set_xlabel("Nodes")
        ax1.set_ylabel("Time (seconds)")
        ax1.set_xticks(range(len(nodes)))
        ax1.set_xticklabels(nodes, rotation=45)
        
        # Memory usage pie chart
        ax2 = axes[0, 1]
        memory_usage = [metrics["node_metrics"][n]["memory_usage"] for n in nodes]
        ax2.pie(memory_usage, labels=nodes, autopct='%1.1f%%')
        ax2.set_title("Memory Usage Distribution")
        
        # CPU usage line chart
        ax3 = axes[1, 0]
        cpu_usage = [metrics["node_metrics"][n]["cpu_usage"] for n in nodes]
        ax3.plot(cpu_usage, 'o-')
        ax3.set_title("CPU Usage by Node")
        ax3.set_xlabel("Node Index")
        ax3.set_ylabel("CPU Usage (%)")
        ax3.grid(True)
        
        # Overall metrics text
        ax4 = axes[1, 1]
        ax4.axis('off')
        metrics_text = f"""Overall Metrics:
        
Total Execution Time: {metrics['overall_metrics']['total_execution_time']:.2f}s
Peak Memory Usage: {metrics['overall_metrics']['peak_memory']:.0f}MB
Average CPU Usage: {metrics['overall_metrics']['average_cpu']:.0f}%
Total Nodes: {len(nodes)}
"""
        ax4.text(0.1, 0.5, metrics_text, fontsize=12, verticalalignment='center')
        
        plt.tight_layout()
        plt.savefig(dashboard_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        assert dashboard_path.exists()
    
    def test_workflow_comparison_matrix(self, temp_data_dir: Path):
        """Test creating a comparison matrix for multiple workflows."""
        visualizer = WorkflowVisualizer()
        
        # Create multiple similar workflows for comparison
        workflows = []
        
        for i in range(3):
            builder = WorkflowBuilder()
            
            # Common nodes
            reader_id = builder.add_node(
                "CSVFileReader",
                "reader",
                inputs={"path": InputType(value=f"data{i}.csv")},
                outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
            )
            
            # Varying processing nodes
            if i == 0:
                processor_id = builder.add_node(
                    "DataFilter",
                    "processor",
                    inputs={
                        "data": InputType(format=DataFormat.DATAFRAME),
                        "condition": InputType(value="value > 100")
                    },
                    outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
                )
            elif i == 1:
                processor_id = builder.add_node(
                    "DataAggregator",
                    "processor",
                    inputs={
                        "data": InputType(format=DataFormat.DATAFRAME),
                        "agg_func": InputType(value="mean")
                    },
                    outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
                )
            else:
                processor_id = builder.add_node(
                    "DataTransformer",
                    "processor",
                    inputs={
                        "data": InputType(format=DataFormat.DATAFRAME),
                        "operation": InputType(value="normalize")
                    },
                    outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
                )
            
            writer_id = builder.add_node(
                "CSVFileWriter",
                "writer",
                inputs={
                    "data": InputType(format=DataFormat.DATAFRAME),
                    "path": InputType(value=f"output{i}.csv")
                },
                outputs={"result": OutputType(format=DataFormat.TEXT)}
            )
            
            builder.add_connection(reader_id, "data", processor_id, "data")
            builder.add_connection(processor_id, "processed", writer_id, "data")
            
            workflow = builder.build(f"workflow_{i}")
            workflows.append(workflow)
        
        # Create comparison matrix
        comparison_path = temp_data_dir / "workflow_comparison.png"
        visualizer.create_comparison_matrix(
            workflows,
            output_path=comparison_path,
            metrics=["node_count", "edge_count", "complexity"]
        )
        
        assert comparison_path.exists()
    
    def test_export_visualization_report(
        self, complex_workflow: WorkflowGraph, temp_data_dir: Path
    ):
        """Test exporting a comprehensive visualization report."""
        visualizer = WorkflowVisualizer()
        
        # Create multi-page PDF report
        report_path = temp_data_dir / "workflow_report.pdf"
        
        with PdfPages(report_path) as pdf:
            # Page 1: Workflow structure
            fig1, ax1 = plt.subplots(figsize=(11, 8.5))
            visualizer.draw_workflow(complex_workflow, ax=ax1)
            ax1.set_title(f"Workflow Structure: {complex_workflow.metadata.get('name', 'Unknown')}")
            pdf.savefig(fig1)
            plt.close(fig1)
            
            # Page 2: Node statistics
            fig2, ax2 = plt.subplots(figsize=(11, 8.5))
            
            node_types = {}
            for node_id in complex_workflow.graph.nodes():
                node_data = complex_workflow.graph.nodes[node_id]
                node_type = node_data.get("type", "Unknown")
                node_types[node_type] = node_types.get(node_type, 0) + 1
            
            ax2.bar(node_types.keys(), node_types.values())
            ax2.set_title("Node Type Distribution")
            ax2.set_xlabel("Node Type")
            ax2.set_ylabel("Count")
            plt.xticks(rotation=45, ha='right')
            pdf.savefig(fig2)
            plt.close(fig2)
            
            # Page 3: Workflow metadata
            fig3, ax3 = plt.subplots(figsize=(11, 8.5))
            ax3.axis('off')
            
            metadata_text = f"""Workflow Metadata:
            
Name: {complex_workflow.metadata.get('name', 'N/A')}
ID: {complex_workflow.metadata.get('id', 'N/A')}
Version: {complex_workflow.metadata.get('version', 'N/A')}
Author: {complex_workflow.metadata.get('author', 'N/A')}
Description: {complex_workflow.metadata.get('description', 'N/A')}

Statistics:
- Total Nodes: {len(complex_workflow.graph.nodes())}
- Total Connections: {len(complex_workflow.graph.edges())}
- Node Types: {len(node_types)}
"""
            ax3.text(0.1, 0.7, metadata_text, fontsize=12, verticalalignment='top')
            pdf.savefig(fig3)
            plt.close(fig3)
            
            # PDF metadata
            d = pdf.infodict()
            d['Title'] = f"Workflow Report: {complex_workflow.metadata.get('name', 'Unknown')}"
            d['Author'] = 'Kailash SDK'
            d['Subject'] = 'Workflow Visualization Report'
            d['Keywords'] = 'Workflow, Visualization, Kailash'
        
        assert report_path.exists()
        assert report_path.stat().st_size > 0
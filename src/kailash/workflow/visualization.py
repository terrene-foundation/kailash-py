"""Workflow visualization utilities."""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, Any, Optional, Tuple

from kailash.workflow.graph import Workflow


class WorkflowVisualizer:
    """Visualize workflows as graphs."""
    
    def __init__(self, workflow: Workflow):
        """Initialize visualizer.
        
        Args:
            workflow: Workflow to visualize
        """
        self.workflow = workflow
        
    def visualize(self, output_path: str, 
                  figsize: Tuple[int, int] = (12, 8),
                  title: Optional[str] = None,
                  show_labels: bool = True,
                  show_connections: bool = True) -> None:
        """Create a visualization of the workflow.
        
        Args:
            output_path: Path to save the image
            figsize: Figure size (width, height)
            title: Optional title for the graph
            show_labels: Whether to show node labels
            show_connections: Whether to show connection labels
        """
        plt.figure(figsize=figsize)
        
        # Create layout
        pos = self._calculate_layout()
        
        # Draw nodes
        node_colors = self._get_node_colors()
        nx.draw_networkx_nodes(
            self.workflow.graph,
            pos,
            node_color=node_colors,
            node_size=3000,
            alpha=0.9
        )
        
        # Draw edges
        nx.draw_networkx_edges(
            self.workflow.graph,
            pos,
            edge_color='gray',
            width=2,
            alpha=0.6,
            arrows=True,
            arrowsize=20,
            arrowstyle='->'
        )
        
        # Draw labels
        if show_labels:
            labels = self._get_node_labels()
            nx.draw_networkx_labels(
                self.workflow.graph,
                pos,
                labels,
                font_size=10,
                font_weight='bold'
            )
        
        # Draw connection labels
        if show_connections:
            edge_labels = self._get_edge_labels()
            nx.draw_networkx_edge_labels(
                self.workflow.graph,
                pos,
                edge_labels,
                font_size=8
            )
        
        # Set title
        if title is None:
            title = f"Workflow: {self.workflow.metadata.name}"
        plt.title(title, fontsize=16, fontweight='bold')
        
        # Remove axes
        plt.axis('off')
        
        # Save
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                    format=output_path.split('.')[-1])
        plt.close()
    
    def _calculate_layout(self) -> Dict[str, Tuple[float, float]]:
        """Calculate node positions for visualization."""
        # Try to use stored positions first
        pos = {}
        for node_id, node_instance in self.workflow.nodes.items():
            if node_instance.position != (0, 0):
                pos[node_id] = node_instance.position
        
        # If no positions stored, calculate them
        if not pos:
            # Use hierarchical layout for DAGs
            try:
                # Create layers based on topological order
                layers = self._create_layers()
                pos = self._hierarchical_layout(layers)
            except:
                # Fallback to spring layout
                pos = nx.spring_layout(self.workflow.graph, k=3, iterations=50)
        
        return pos
    
    def _create_layers(self) -> Dict[int, list]:
        """Create layers of nodes for hierarchical layout."""
        layers = {}
        remaining = set(self.workflow.graph.nodes())
        layer = 0
        
        while remaining:
            # Find nodes with no dependencies in remaining set
            current_layer = []
            for node in remaining:
                predecessors = set(self.workflow.graph.predecessors(node))
                if not predecessors.intersection(remaining):
                    current_layer.append(node)
            
            if not current_layer:
                # Circular dependency, break and use all remaining
                current_layer = list(remaining)
            
            layers[layer] = current_layer
            remaining -= set(current_layer)
            layer += 1
        
        return layers
    
    def _hierarchical_layout(self, layers: Dict[int, list]) -> Dict[str, Tuple[float, float]]:
        """Create hierarchical layout from layers."""
        pos = {}
        layer_height = 2.0
        
        for layer, nodes in layers.items():
            y = layer * layer_height
            if len(nodes) == 1:
                x_positions = [0]
            else:
                width = max(2.0, len(nodes) - 1)
                x_positions = [-width/2 + i*width/(len(nodes)-1) for i in range(len(nodes))]
            
            for i, node in enumerate(nodes):
                pos[node] = (x_positions[i], -y)  # Negative y to flow top to bottom
        
        return pos
    
    def _get_node_colors(self) -> list:
        """Get colors for nodes based on their types."""
        color_map = {
            'CSVReader': 'lightblue',
            'JSONReader': 'lightblue',
            'TextReader': 'lightblue',
            'CSVWriter': 'lightgreen',
            'JSONWriter': 'lightgreen',
            'TextWriter': 'lightgreen',
            'Filter': 'lightyellow',
            'Map': 'lightyellow',
            'Sort': 'lightyellow',
            'Aggregator': 'lightcoral',
            'Conditional': 'lightcoral',
            'Merge': 'lightcoral'
        }
        
        colors = []
        for node_id in self.workflow.graph.nodes():
            node_instance = self.workflow.nodes[node_id]
            node_type = node_instance.node_type
            colors.append(color_map.get(node_type, 'lightgray'))
        
        return colors
    
    def _get_node_labels(self) -> Dict[str, str]:
        """Get labels for nodes."""
        labels = {}
        for node_id in self.workflow.graph.nodes():
            node_instance = self.workflow.nodes[node_id]
            labels[node_id] = f"{node_id}\n({node_instance.node_type})"
        
        return labels
    
    def _get_edge_labels(self) -> Dict[Tuple[str, str], str]:
        """Get labels for edges showing data mappings."""
        edge_labels = {}
        
        for edge in self.workflow.graph.edges(data=True):
            source, target, data = edge
            mapping = data.get('mapping', {})
            
            if mapping:
                # Create label from mapping
                label_parts = []
                for src, dst in mapping.items():
                    label_parts.append(f"{src}'{dst}")
                label = "\n".join(label_parts)
                edge_labels[(source, target)] = label
        
        return edge_labels
    
    def create_execution_graph(self, run_id: str, task_manager: Any) -> None:
        """Create a visualization showing execution status.
        
        Args:
            run_id: Run ID to visualize
            task_manager: Task manager instance
        """
        # Import here to avoid circular dependency
        from kailash.tracking import TaskStatus
        
        # Get tasks for this run
        tasks = task_manager.list_tasks(run_id)
        
        # Create status colors
        status_colors = {
            TaskStatus.PENDING: 'lightgray',
            TaskStatus.RUNNING: 'yellow',
            TaskStatus.COMPLETED: 'lightgreen',
            TaskStatus.FAILED: 'lightcoral',
            TaskStatus.SKIPPED: 'lightblue'
        }
        
        # Map node IDs to statuses
        node_status = {}
        for task in tasks:
            node_status[task.node_id] = task.status
        
        # Create custom node colors based on status
        node_colors = []
        for node_id in self.workflow.graph.nodes():
            status = node_status.get(node_id, TaskStatus.PENDING)
            node_colors.append(status_colors[status])
        
        # Use the regular visualize method with custom colors
        self._visualize_with_colors(
            output_path=f"execution_{run_id}.png",
            node_colors=node_colors,
            title=f"Execution Status: {run_id}"
        )
    
    def _visualize_with_colors(self, output_path: str, 
                              node_colors: list,
                              title: str) -> None:
        """Create visualization with custom node colors."""
        plt.figure(figsize=(12, 8))
        
        pos = self._calculate_layout()
        
        # Draw nodes with custom colors
        nx.draw_networkx_nodes(
            self.workflow.graph,
            pos,
            node_color=node_colors,
            node_size=3000,
            alpha=0.9
        )
        
        # Draw edges
        nx.draw_networkx_edges(
            self.workflow.graph,
            pos,
            edge_color='gray',
            width=2,
            alpha=0.6,
            arrows=True,
            arrowsize=20,
            arrowstyle='->'
        )
        
        # Draw labels
        labels = self._get_node_labels()
        nx.draw_networkx_labels(
            self.workflow.graph,
            pos,
            labels,
            font_size=10,
            font_weight='bold'
        )
        
        plt.title(title, fontsize=16, fontweight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()


# Add visualization method to Workflow class
def add_visualization_to_workflow():
    """Add visualization method to Workflow class."""
    def visualize(self, output_path: str, **kwargs) -> None:
        """Visualize the workflow.
        
        Args:
            output_path: Path to save the visualization
            **kwargs: Additional arguments for the visualizer
        """
        visualizer = WorkflowVisualizer(self)
        visualizer.visualize(output_path, **kwargs)
    
    # Add method to Workflow class
    from kailash.workflow.graph import Workflow
    Workflow.visualize = visualize


# Call this when module is imported
add_visualization_to_workflow()
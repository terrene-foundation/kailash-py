"""Workflow visualization utilities."""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, Any, Optional, Tuple, List, Union

from kailash.workflow.graph import Workflow


class WorkflowVisualizer:
    """Visualize workflows as graphs."""
    
    def __init__(self, workflow: Workflow, 
                node_colors: Optional[Dict[str, str]] = None,
                edge_colors: Optional[Dict[str, str]] = None,
                layout: str = "hierarchical"):
        """Initialize visualizer.
        
        Args:
            workflow: Workflow to visualize
            node_colors: Custom node color map
            edge_colors: Custom edge color map
            layout: Layout algorithm to use
        """
        self.workflow = workflow
        self.node_colors = node_colors or self._default_node_colors()
        self.edge_colors = edge_colors or self._default_edge_colors()
        self.layout = layout
        
    def _default_node_colors(self) -> Dict[str, str]:
        """Get default node color map."""
        return {
            "data": "lightblue",
            "transform": "lightyellow",
            "logic": "lightcoral",
            "ai": "lightpink",
            "default": "lightgray"
        }
    
    def _default_edge_colors(self) -> Dict[str, str]:
        """Get default edge color map."""
        return {
            "default": "gray",
            "error": "red",
            "conditional": "orange"
        }
    
    def _get_node_color(self, node_type: str) -> str:
        """Get color for node based on type."""
        if "Reader" in node_type or "Writer" in node_type:
            return self.node_colors["data"]
        elif "Transform" in node_type or "Filter" in node_type or "Processor" in node_type:
            return self.node_colors["transform"]
        elif "Logic" in node_type or "Merge" in node_type or "Conditional" in node_type:
            return self.node_colors["logic"]
        elif "AI" in node_type or "Model" in node_type:
            return self.node_colors["ai"]
        return self.node_colors["default"]
    
    def _get_node_colors(self) -> List[str]:
        """Get colors for all nodes in workflow."""
        colors = []
        for node_id in self.workflow.graph.nodes():
            node_instance = self.workflow.nodes[node_id]
            node_type = node_instance.node_type
            colors.append(self._get_node_color(node_type))
        return colors
    
    def _get_node_labels(self) -> Dict[str, str]:
        """Get labels for nodes in workflow."""
        labels = {}
        for node_id in self.workflow.graph.nodes():
            # Try to get name from node instance
            node = self.workflow.get_node(node_id)
            if node and hasattr(node, 'name') and node.name:
                # For test compatibility - test expects just the name, not node_id
                labels[node_id] = node.name
            else:
                # Fallback to node type from metadata
                node_instance = self.workflow.nodes.get(node_id)
                if node_instance:
                    labels[node_id] = f"{node_id} ({node_instance.node_type})"
                else:
                    labels[node_id] = node_id
        return labels
    
    def _get_edge_labels(self) -> Dict[Tuple[str, str], str]:
        """Get labels for edges in workflow."""
        edge_labels = {}
        
        for edge in self.workflow.graph.edges(data=True):
            source, target, data = edge
            
            # Try both edge data formats for compatibility
            from_output = data.get('from_output')
            to_input = data.get('to_input')
            
            if from_output and to_input:
                edge_labels[(source, target)] = f"{from_output}→{to_input}"
            else:
                # Fallback to mapping format
                mapping = data.get('mapping', {})
                if mapping:
                    # Create label from mapping
                    label_parts = []
                    for src, dst in mapping.items():
                        label_parts.append(f"{src}→{dst}")
                    label = "\n".join(label_parts)
                    edge_labels[(source, target)] = label
        
        return edge_labels
    
    def _calculate_layout(self) -> Dict[str, Tuple[float, float]]:
        """Calculate node positions for visualization."""
        # Try to use stored positions first
        pos = {}
        for node_id, node_instance in self.workflow.nodes.items():
            if node_instance.position != (0, 0):
                pos[node_id] = node_instance.position
        
        # If no positions stored, calculate them
        if not pos:
            if self.layout == "hierarchical":
                # Use hierarchical layout for DAGs
                try:
                    # Create layers based on topological order
                    layers = self._create_layers()
                    pos = self._hierarchical_layout(layers)
                except Exception:
                    # Fallback to spring layout
                    pos = nx.spring_layout(self.workflow.graph, k=3, iterations=50)
            elif self.layout == "circular":
                pos = nx.circular_layout(self.workflow.graph)
            elif self.layout == "spring":
                pos = nx.spring_layout(self.workflow.graph, k=2, iterations=100)
            else:
                # Default to spring layout
                pos = nx.spring_layout(self.workflow.graph)
        
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
    
    def _draw_graph(self, pos: Dict[str, Tuple[float, float]], 
                   node_colors: List[str], 
                   show_labels: bool, 
                   show_connections: bool) -> None:
        """Draw the graph with given positions and options."""
        # Draw nodes
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
            edge_color=self.edge_colors["default"],
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
    
    def visualize(self, output_path: Optional[str] = None, 
                 figsize: Tuple[int, int] = (12, 8),
                 title: Optional[str] = None,
                 show_labels: bool = True,
                 show_connections: bool = True,
                 dpi: int = 300,
                 **kwargs) -> None:
        """Create a visualization of the workflow.
        
        Args:
            output_path: Path to save the image (if None, shows interactive plot)
            figsize: Figure size (width, height)
            title: Optional title for the graph
            show_labels: Whether to show node labels
            show_connections: Whether to show connection labels
            dpi: Resolution (dots per inch) for saved images
            **kwargs: Additional options passed to plt.savefig
        """
        try:
            plt.figure(figsize=figsize)
            
            # Calculate node positions
            pos = self._calculate_layout()
            
            # Handle empty workflow case
            if not self.workflow.graph.nodes():
                pos = {}
                node_colors = []
            else:
                # Draw the graph with colors
                node_colors = self._get_node_colors()
            
            # Draw the graph components
            if pos and node_colors:
                self._draw_graph(pos, node_colors, show_labels, show_connections)
            
            # Set title
            if title is None:
                title = f"Workflow: {self.workflow.name}"
            plt.title(title, fontsize=16, fontweight='bold')
            
            # Remove axes
            plt.axis('off')
            plt.tight_layout()
            
            # Show or save
            if output_path:
                plt.savefig(output_path, dpi=dpi, bbox_inches='tight', **kwargs)
                plt.close()
            else:
                plt.show()
        except Exception as e:
            plt.close()
            raise e
    
    def save(self, output_path: str, dpi: int = 300, **kwargs) -> None:
        """Save visualization to file.
        
        Args:
            output_path: Path to save the image
            dpi: Resolution (dots per inch)
            **kwargs: Additional options for plt.savefig
        """
        kwargs['dpi'] = dpi
        self.visualize(output_path=output_path, **kwargs)
    
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
        
        # Create the visualization
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
        
        plt.title(f"Execution Status: {run_id}", fontsize=16, fontweight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(f"execution_{run_id}.png", dpi=300, bbox_inches='tight')
        plt.close()


# Add visualization method to Workflow class
def add_visualization_to_workflow():
    """Add visualization method to Workflow class."""
    def visualize(self, output_path: Optional[str] = None, **kwargs) -> None:
        """Visualize the workflow.
        
        Args:
            output_path: Path to save the visualization
            **kwargs: Additional arguments for the visualizer
        """
        visualizer = WorkflowVisualizer(self)
        visualizer.visualize(output_path, **kwargs)
    
    # Add method to Workflow class
    Workflow.visualize = visualize


# Call this when module is imported
add_visualization_to_workflow()
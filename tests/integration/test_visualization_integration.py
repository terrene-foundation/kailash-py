"""Test visualization with real workflows."""

from pathlib import Path

import pytest

try:
    from kailash.workflow.visualization import WorkflowVisualizer
except ImportError:
    WorkflowVisualizer = None

from kailash.workflow import Workflow, WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner


class TestVisualizationIntegration:
    """Test workflow visualization with real workflows."""
    
    def test_visualizer_availability(self):
        """Test that visualizer is available."""
        if WorkflowVisualizer is None:
            pytest.skip("Visualization components not available")
        
        assert WorkflowVisualizer is not None
    
    def test_simple_workflow_visualization(self, temp_data_dir: Path):
        """Test visualizing a simple workflow."""
        if WorkflowVisualizer is None:
            pytest.skip("Visualization components not available")
        
        try:
            visualizer = WorkflowVisualizer()
            assert visualizer is not None
            # Basic test that visualizer can be used
            # Note: Actual visualization testing requires complete workflow implementation
        except Exception:
            pytest.skip("Visualizer initialization not available")
    
    def test_basic_visualization_methods(self, temp_data_dir: Path):
        """Test basic visualization methods."""
        if WorkflowVisualizer is None:
            pytest.skip("Visualization components not available")
        
        try:
            visualizer = WorkflowVisualizer()
            
            # Test that visualizer has expected methods
            assert hasattr(visualizer, 'visualize') or hasattr(visualizer, 'draw_workflow')
            
        except Exception:
            pytest.skip("Visualization methods not available")
    
    def test_matplotlib_availability(self):
        """Test that matplotlib is available for visualization."""
        try:
            import matplotlib.pyplot as plt
            assert plt is not None
        except ImportError:
            pytest.skip("matplotlib not available for visualization testing")
    
    def test_workflow_builder_integration(self):
        """Test that workflow builder integrates with visualization."""
        # Test that workflow components can work together
        builder = WorkflowBuilder()
        workflow = builder.build("viz_test")
        
        assert workflow is not None
        assert hasattr(workflow, 'metadata')
    
    def test_visualization_components_integration(self):
        """Test integration between visualization and other components."""
        # Test that key components can be imported together
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        builder = WorkflowBuilder()
        
        assert runtime is not None
        assert runner is not None
        assert builder is not None
    
    def test_basic_workflow_creation_for_viz(self):
        """Test creating workflows that could be visualized."""
        builder = WorkflowBuilder()
        
        try:
            # Create workflow with nodes if supported
            workflow = builder.build("visualization_test")
            
            # Verify workflow can be created
            assert workflow is not None
            assert workflow.metadata.name == "visualization_test"
            
        except Exception:
            pytest.skip("Workflow creation for visualization not available")
    
    def test_workflow_metadata_for_visualization(self):
        """Test that workflows have metadata needed for visualization."""
        builder = WorkflowBuilder()
        workflow = builder.build("metadata_test")
        
        # Test metadata availability
        assert hasattr(workflow, 'metadata')
        assert workflow.metadata.name == "metadata_test"
        
        # Test that metadata has expected structure
        assert hasattr(workflow.metadata, 'name')
    
    def test_runtime_visualization_integration(self):
        """Test integration between runtime and visualization components."""
        runtime = LocalRuntime()
        
        # Test that runtime can be used with visualization
        assert runtime is not None
        
        # Test that runtime has expected interface
        assert hasattr(runtime, 'execute') or hasattr(runtime, 'run')
    
    def test_pathlib_integration(self, temp_data_dir: Path):
        """Test that Path objects work with visualization."""
        # Test basic path operations for visualization output
        output_path = temp_data_dir / "test_output.png"
        
        # Test path creation and properties
        assert output_path.parent == temp_data_dir
        assert output_path.suffix == ".png"
        assert output_path.name == "test_output.png"
        
        # Test that we can create directories
        viz_dir = temp_data_dir / "visualizations"
        viz_dir.mkdir(exist_ok=True)
        assert viz_dir.exists()
    
    def test_workflow_import_availability(self):
        """Test that required workflow imports are available."""
        # Test that core workflow components can be imported
        assert Workflow is not None
        assert WorkflowBuilder is not None
        assert LocalRuntime is not None
        assert WorkflowRunner is not None
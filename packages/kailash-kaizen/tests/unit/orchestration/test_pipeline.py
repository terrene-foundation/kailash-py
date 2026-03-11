"""
Unit tests for Pipeline infrastructure.

Tests the Pipeline base class and .to_agent() method for composability.
"""

import pytest
from kaizen.orchestration.pipeline import Pipeline, SequentialPipeline


class TestPipelineBasics:
    """Test basic Pipeline functionality."""

    def test_pipeline_requires_run_implementation(self):
        """Test that Pipeline requires run() to be implemented."""
        pipeline = Pipeline()

        with pytest.raises(NotImplementedError):
            pipeline.run()

    def test_custom_pipeline_can_execute(self):
        """Test that custom pipeline can execute."""

        class SimplePipeline(Pipeline):
            def run(self, **inputs):
                return {"result": "processed", "input": inputs}

        pipeline = SimplePipeline()
        result = pipeline.run(data="test")

        assert result["result"] == "processed"
        assert result["input"]["data"] == "test"


class TestPipelineToAgent:
    """Test Pipeline.to_agent() method."""

    def test_to_agent_creates_agent(self):
        """Test that .to_agent() creates a BaseAgent."""
        from kaizen.core.base_agent import BaseAgent

        class SimplePipeline(Pipeline):
            def run(self, **inputs):
                return {"result": "processed"}

        pipeline = SimplePipeline()
        agent = pipeline.to_agent()

        assert isinstance(agent, BaseAgent)

    def test_pipeline_agent_executes(self):
        """Test that PipelineAgent can execute the wrapped pipeline."""

        class DataPipeline(Pipeline):
            def run(self, data: str, **kwargs):
                return {
                    "original": data,
                    "processed": data.upper(),
                    "length": len(data),
                }

        pipeline = DataPipeline()
        agent = pipeline.to_agent()

        result = agent.run(data="hello world")

        assert result["original"] == "hello world"
        assert result["processed"] == "HELLO WORLD"
        assert result["length"] == 11

    def test_pipeline_agent_has_metadata(self):
        """Test that PipelineAgent has correct metadata."""

        class MyPipeline(Pipeline):
            def run(self, **inputs):
                return {"result": "done"}

        pipeline = MyPipeline()
        agent = pipeline.to_agent(name="my_pipeline", description="Test pipeline")

        assert agent.agent_id == "my_pipeline"
        assert agent.description == "Test pipeline"


class TestSequentialPipeline:
    """Test SequentialPipeline convenience class."""

    def test_sequential_pipeline_executes_in_order(self):
        """Test that SequentialPipeline executes agents sequentially."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.signatures import InputField, OutputField, Signature

        class Step1Signature(Signature):
            input: str = InputField()
            step1_output: str = OutputField()

        class Step2Signature(Signature):
            step1_output: str = InputField()
            final_output: str = OutputField()

        class Step1Agent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=Step1Signature(),
                )

            def run(self, **inputs):
                return {"step1_output": f"step1({inputs.get('input', '')})"}

        class Step2Agent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=Step2Signature(),
                )

            def run(self, **inputs):
                return {"final_output": f"step2({inputs.get('step1_output', '')})"}

        pipeline = SequentialPipeline(agents=[Step1Agent(), Step2Agent()])
        result = pipeline.run(input="data")

        # Check final output
        assert "final_output" in result
        assert result["final_output"]["final_output"] == "step2(step1(data))"

        # Check intermediate results
        assert "intermediate_results" in result
        assert len(result["intermediate_results"]) == 2

    def test_sequential_pipeline_to_agent(self):
        """Test that SequentialPipeline can be converted to agent."""
        from kaizen.core.base_agent import BaseAgent

        pipeline = SequentialPipeline(agents=[])
        agent = pipeline.to_agent(name="sequential")

        assert isinstance(agent, BaseAgent)
        assert agent.agent_id == "sequential"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

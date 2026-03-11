"""
Unit tests for the 15 migrated AI nodes.

Tests all the Kaizen AI nodes that were migrated from Core SDK
with signature-based enhancements and optimization hooks.
"""

from unittest.mock import patch

from kaizen.nodes import (  # Text Processing Nodes (5); Conversation & Analysis Nodes (4); Advanced Processing Nodes (3); Integration Nodes (3)
    KaizenAIModelNode,
    KaizenAIWorkflowNode,
    KaizenCodeGenerationNode,
    KaizenConversationNode,
    KaizenDataAnalysisNode,
    KaizenEntityExtractionNode,
    KaizenPromptTemplateNode,
    KaizenQuestionAnsweringNode,
    KaizenReasoningNode,
    KaizenSentimentAnalysisNode,
    KaizenTextClassificationNode,
    KaizenTextEmbeddingNode,
    KaizenTextGenerationNode,
    KaizenTextSummarizationNode,
    KaizenTextTransformationNode,
)
from kaizen.signatures import Signature


class MockSignature(Signature):
    """Mock signature for testing."""

    def define_inputs(self):
        return {"input_text": str, "context": str}

    def define_outputs(self):
        return {"processed_text": str}


class TestTextProcessingNodes:
    """Test the 5 text processing nodes."""

    def test_kaizen_text_generation_node(self):
        """Test KaizenTextGenerationNode."""
        node = KaizenTextGenerationNode()
        result = node.execute(prompt="Generate a story about AI")

        assert "generated_text" in result
        assert "signature_optimized" in result
        assert isinstance(result["generated_text"], str)
        assert len(result["generated_text"]) > 0

    def test_kaizen_text_classification_node(self):
        """Test KaizenTextClassificationNode."""
        node = KaizenTextClassificationNode()
        result = node.execute(texts=["This is great!", "This is terrible"])

        assert "classifications" in result
        assert "total_processed" in result
        assert len(result["classifications"]) == 2
        assert result["total_processed"] == 2

    def test_kaizen_text_summarization_node(self):
        """Test KaizenTextSummarizationNode."""
        node = KaizenTextSummarizationNode()
        long_text = "This is a very long text that needs to be summarized. " * 10
        result = node.execute(texts=[long_text])

        assert "summaries" in result
        assert "total_processed" in result
        assert len(result["summaries"]) == 1
        assert result["total_processed"] == 1

    def test_kaizen_text_embedding_node(self):
        """Test KaizenTextEmbeddingNode."""
        node = KaizenTextEmbeddingNode()
        result = node.execute(texts=["Hello world", "AI is amazing"])

        assert "embeddings" in result
        assert "dimensions" in result
        assert len(result["embeddings"]) == 2
        assert result["dimensions"] == 384

    def test_kaizen_text_transformation_node(self):
        """Test KaizenTextTransformationNode."""
        node = KaizenTextTransformationNode()
        result = node.execute(text="Hello world", target_style="professional")

        assert "transformed_text" in result
        assert "quality_score" in result
        assert "professional" in result["transformed_text"]


class TestConversationAnalysisNodes:
    """Test the 4 conversation and analysis nodes."""

    def test_kaizen_conversation_node(self):
        """Test KaizenConversationNode."""
        node = KaizenConversationNode()
        result = node.execute(
            message="Hello, how are you?", persona="friendly assistant"
        )

        assert "response" in result
        assert "conversation_length" in result
        assert isinstance(result["response"], str)

    def test_kaizen_sentiment_analysis_node(self):
        """Test KaizenSentimentAnalysisNode."""
        node = KaizenSentimentAnalysisNode()
        result = node.execute(texts=["I love this!", "This is terrible"])

        assert "sentiments" in result
        assert "total_processed" in result
        assert len(result["sentiments"]) == 2

    def test_kaizen_entity_extraction_node(self):
        """Test KaizenEntityExtractionNode."""
        node = KaizenEntityExtractionNode()
        result = node.execute(texts=["John works at Microsoft in Seattle"])

        assert "entities" in result
        assert "total_processed" in result
        assert len(result["entities"]) == 1

    def test_kaizen_question_answering_node(self):
        """Test KaizenQuestionAnsweringNode."""
        node = KaizenQuestionAnsweringNode()
        result = node.execute(
            question="What is AI?",
            context="Artificial Intelligence (AI) is machine intelligence.",
        )

        assert "answer" in result
        assert "confidence" in result
        assert "context_used" in result
        assert result["context_used"] is True


class TestAdvancedProcessingNodes:
    """Test the 3 advanced processing nodes."""

    def test_kaizen_code_generation_node(self):
        """Test KaizenCodeGenerationNode."""
        node = KaizenCodeGenerationNode()
        result = node.execute(
            requirements="Write a hello world function", language="python"
        )

        assert "generated_code" in result
        assert "code_quality_score" in result
        assert "python" in result["language"]

    def test_kaizen_data_analysis_node(self):
        """Test KaizenDataAnalysisNode."""
        node = KaizenDataAnalysisNode()
        result = node.execute(data=[1, 2, 3, 4, 5], analysis_type="descriptive")

        assert "results" in result
        assert "statistical_significance" in result
        assert result["data_size"] == 5

    def test_kaizen_reasoning_node(self):
        """Test KaizenReasoningNode."""
        node = KaizenReasoningNode()
        result = node.execute(problem="What causes rain?", reasoning_type="deductive")

        assert "reasoning_chain" in result
        assert "conclusion" in result
        assert "logic_validation" in result


class TestIntegrationNodes:
    """Test the 3 integration nodes."""

    def test_kaizen_ai_model_node(self):
        """Test KaizenAIModelNode."""
        node = KaizenAIModelNode()
        result = node.execute(prompt="Hello", provider="openai", use_fallback=True)

        assert "provider_used" in result
        assert "fallback_used" in result
        assert isinstance(result["fallback_used"], bool)

    def test_kaizen_prompt_template_node(self):
        """Test KaizenPromptTemplateNode."""
        node = KaizenPromptTemplateNode()
        result = node.execute(
            template="Hello {name}, how is {weather}?",
            variables={"name": "Alice", "weather": "sunny"},
        )

        assert "filled_prompt" in result
        assert "quality_score" in result
        assert "Alice" in result["filled_prompt"]
        assert "sunny" in result["filled_prompt"]

    def test_kaizen_ai_workflow_node(self):
        """Test KaizenAIWorkflowNode."""
        node = KaizenAIWorkflowNode()
        workflow_steps = [
            {"type": "prompt", "data": {"prompt": "Step 1"}},
            {"type": "analysis", "data": {"data": [1, 2, 3], "analysis_type": "count"}},
        ]
        result = node.execute(workflow_steps=workflow_steps)

        assert "execution_results" in result
        assert "success_rate" in result
        assert "total_steps" in result
        assert result["total_steps"] == 2


class TestSignatureIntegration:
    """Test signature integration across all nodes."""

    def test_nodes_with_signature_support(self):
        """Test that all nodes support signature integration."""
        signature = MockSignature("test_sig", "Test signature")

        # Test a few representative nodes with signatures
        text_gen = KaizenTextGenerationNode(signature=signature)
        result = text_gen.execute(prompt="Test")
        assert result["signature_optimized"] is True

        conversation = KaizenConversationNode(signature=signature)
        result = conversation.execute(message="Test")
        assert result["signature_optimized"] is True

        code_gen = KaizenCodeGenerationNode(signature=signature)
        result = code_gen.execute(requirements="Test function")
        assert result["signature_optimized"] is True


class TestBackwardCompatibility:
    """Test backward compatibility with Core SDK patterns."""

    def test_core_sdk_parameter_compatibility(self):
        """Test that nodes work with Core SDK parameter patterns."""
        # Test text classification with Core SDK style parameters
        node = KaizenTextClassificationNode()
        result = node.execute(
            texts=["Good product", "Bad experience"],
            categories=["positive", "negative"],
            confidence_threshold=0.7,
        )

        assert "classifications" in result
        assert len(result["classifications"]) == 2

    def test_enhanced_functionality(self):
        """Test that nodes provide enhanced functionality beyond Core SDK."""
        # Test sentiment analysis with multi-dimensional analysis
        node = KaizenSentimentAnalysisNode()
        result = node.execute(
            texts=["Amazing product!"],
            aspects=["product", "quality"],
            granularity="document",
        )

        assert "sentiments" in result
        sentiments = result["sentiments"]
        assert len(sentiments) > 0

        # Check for Kaizen enhancements
        sentiment = sentiments[0]
        assert "dimensions" in sentiment
        assert "aspect_sentiments" in sentiment


class TestPerformanceOptimization:
    """Test performance optimization features."""

    def test_batch_processing_optimization(self):
        """Test batch processing optimization in embedding node."""
        node = KaizenTextEmbeddingNode()
        texts = [f"Text {i}" for i in range(10)]

        result = node.execute(texts=texts, batch_size=5)

        assert "embeddings" in result
        assert len(result["embeddings"]) == 10
        assert result["batch_size"] == 5

    def test_caching_and_optimization_hooks(self):
        """Test that optimization hooks are called."""
        node = KaizenTextGenerationNode()

        # Mock the optimization hooks
        with patch.object(
            node, "pre_execution_hook", wraps=node.pre_execution_hook
        ) as pre_hook:
            with patch.object(
                node, "post_execution_hook", wraps=node.post_execution_hook
            ) as post_hook:
                result = node.execute(prompt="Test optimization")

                # Verify hooks were called
                pre_hook.assert_called_once()
                post_hook.assert_called_once()

                assert "signature_optimized" in result


class TestErrorHandling:
    """Test error handling and recovery features."""

    def test_fallback_execution(self):
        """Test fallback execution in AI model node."""
        node = KaizenAIModelNode()

        # Test with fallback enabled
        result = node.execute(
            prompt="Test",
            provider="invalid_provider",
            fallback_provider="ollama",
            use_fallback=True,
        )

        # Should handle error gracefully
        assert "provider_used" in result or "error" in result

    def test_error_recovery_in_workflow(self):
        """Test error recovery in workflow node."""
        node = KaizenAIWorkflowNode()

        workflow_steps = [
            {"type": "prompt", "data": {"prompt": "Good step"}},
            {"type": "invalid_type", "data": {}},  # This should cause an error
            {"type": "prompt", "data": {"prompt": "Another good step"}},
        ]

        result = node.execute(workflow_steps=workflow_steps, error_handling="continue")

        assert "execution_results" in result
        assert "errors" in result
        # Should have some successful steps despite errors
        assert result["completed_steps"] >= 1


def test_all_15_nodes_registered():
    """Test that all 15 nodes are properly registered and importable."""
    expected_nodes = [
        # Text Processing Nodes (5)
        "KaizenTextGenerationNode",
        "KaizenTextClassificationNode",
        "KaizenTextSummarizationNode",
        "KaizenTextEmbeddingNode",
        "KaizenTextTransformationNode",
        # Conversation & Analysis Nodes (4)
        "KaizenConversationNode",
        "KaizenSentimentAnalysisNode",
        "KaizenEntityExtractionNode",
        "KaizenQuestionAnsweringNode",
        # Advanced Processing Nodes (3)
        "KaizenCodeGenerationNode",
        "KaizenDataAnalysisNode",
        "KaizenReasoningNode",
        # Integration Nodes (3)
        "KaizenAIModelNode",
        "KaizenPromptTemplateNode",
        "KaizenAIWorkflowNode",
    ]

    from kaizen.nodes import __all__ as exported_nodes

    for node_name in expected_nodes:
        assert node_name in exported_nodes, f"{node_name} not in exported nodes"

    # Verify total count
    ai_node_count = len(
        [
            n
            for n in exported_nodes
            if n.startswith("Kaizen")
            and n.endswith("Node")
            and n not in ["KaizenNode", "KaizenLLMAgentNode"]
        ]
    )
    assert ai_node_count == 15, f"Expected 15 AI nodes, got {ai_node_count}"


def test_migration_completeness():
    """Test that migration meets all TODO-143 acceptance criteria."""
    # Test that we can create instances of all 15 nodes
    nodes = [
        KaizenTextGenerationNode(),
        KaizenTextClassificationNode(),
        KaizenTextSummarizationNode(),
        KaizenTextEmbeddingNode(),
        KaizenTextTransformationNode(),
        KaizenConversationNode(),
        KaizenSentimentAnalysisNode(),
        KaizenEntityExtractionNode(),
        KaizenQuestionAnsweringNode(),
        KaizenCodeGenerationNode(),
        KaizenDataAnalysisNode(),
        KaizenReasoningNode(),
        KaizenAIModelNode(),
        KaizenPromptTemplateNode(),
        KaizenAIWorkflowNode(),
    ]

    assert len(nodes) == 15, "All 15 AI nodes should be creatable"

    # Test that all nodes have required methods
    for node in nodes:
        assert hasattr(node, "get_parameters"), "Node should have get_parameters method"
        assert hasattr(node, "run"), "Node should have run method"
        assert hasattr(node, "execute"), "Node should have execute method"
        assert hasattr(
            node, "pre_execution_hook"
        ), "Node should have pre_execution_hook"
        assert hasattr(
            node, "post_execution_hook"
        ), "Node should have post_execution_hook"

    # Test basic execution works for each node
    test_params = {
        "KaizenTextGenerationNode": {"prompt": "Test"},
        "KaizenTextClassificationNode": {"texts": ["Test text"]},
        "KaizenTextSummarizationNode": {"texts": ["Long text to summarize"]},
        "KaizenTextEmbeddingNode": {"texts": ["Text to embed"]},
        "KaizenTextTransformationNode": {"text": "Transform this"},
        "KaizenConversationNode": {"message": "Hello"},
        "KaizenSentimentAnalysisNode": {"texts": ["Happy text"]},
        "KaizenEntityExtractionNode": {"texts": ["John works here"]},
        "KaizenQuestionAnsweringNode": {"question": "What?"},
        "KaizenCodeGenerationNode": {"requirements": "Write code"},
        "KaizenDataAnalysisNode": {"data": [1, 2, 3]},
        "KaizenReasoningNode": {"problem": "Solve this"},
        "KaizenAIModelNode": {"prompt": "Test"},
        "KaizenPromptTemplateNode": {
            "template": "Hello {name}",
            "variables": {"name": "World"},
        },
        "KaizenAIWorkflowNode": {
            "workflow_steps": [{"type": "prompt", "data": {"prompt": "Test"}}]
        },
    }

    for node in nodes:
        node_class = node.__class__.__name__
        params = test_params.get(node_class, {"prompt": "Test"})

        result = node.execute(**params)
        assert isinstance(result, dict), f"{node_class} should return dict result"
        assert (
            "signature_optimized" in result
        ), f"{node_class} should include signature_optimized flag"

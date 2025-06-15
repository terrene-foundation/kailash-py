"""Tests for AI nodes."""

import pytest

from kailash.nodes.ai.agents import (
    ChatAgent,
    FunctionCallingAgent,
    PlanningAgent,
    RetrievalAgent,
)
from kailash.nodes.ai.models import (
    ModelPredictor,
    NamedEntityRecognizer,
    SentimentAnalyzer,
    TextClassifier,
    TextEmbedder,
    TextSummarizer,
)


class TestTextClassifierNode:
    """Test TextClassifier node."""

    def test_text_classification_simple(self):
        """Test basic text classification."""
        node = TextClassifier(texts=["This is a test"])

        result = node.execute()

        # Should have default parameters
        assert "classifications" in result
        assert result["model_used"] == "simple"
        assert result["categories"] == ["positive", "negative", "neutral"]

    def test_text_classification_with_texts(self):
        """Test text classification with specific texts."""
        node = TextClassifier(
            texts=["This is good", "This is bad", "This is neutral"],
            categories=["positive", "negative", "neutral"],
        )

        result = node.execute()

        assert len(result["classifications"]) == 3
        assert result["classifications"][0]["text"] == "This is good"
        assert result["classifications"][0]["category"] == "positive"
        assert result["classifications"][1]["category"] == "negative"
        assert result["classifications"][2]["category"] == "neutral"

    def test_text_classification_confidence_threshold(self):
        """Test confidence threshold filtering."""
        node = TextClassifier(texts=["excellent work"], confidence_threshold=0.9)

        result = node.execute()

        for classification in result["classifications"]:
            assert "passed_threshold" in classification
            assert isinstance(classification["confidence"], float)

    def test_text_classification_empty_input(self):
        """Test with empty text list."""
        node = TextClassifier(texts=[])

        result = node.execute()

        assert result["classifications"] == []
        assert result["model_used"] == "simple"


class TestTextEmbedderNode:
    """Test TextEmbedder node."""

    def test_embedding_generation(self):
        """Test basic embedding generation."""
        node = TextEmbedder(texts=["Hello world", "Testing embeddings"])

        result = node.execute()

        assert "embeddings" in result
        assert len(result["embeddings"]) == 2
        assert result["dimensions"] == 384

        # Check embedding structure
        for embedding in result["embeddings"]:
            assert "text" in embedding
            assert "embedding" in embedding
            assert len(embedding["embedding"]) == 384

    def test_embedding_custom_dimensions(self):
        """Test embeddings with custom dimensions."""
        node = TextEmbedder(texts=["Test text"], dimensions=128)

        result = node.execute()

        assert result["dimensions"] == 128
        assert len(result["embeddings"][0]["embedding"]) == 128

    def test_embedding_consistent_output(self):
        """Test that same text produces same embedding."""
        text = "Consistent test text"

        node1 = TextEmbedder(texts=[text])
        node2 = TextEmbedder(texts=[text])

        result1 = node1.execute()
        result2 = node2.execute()

        # Should be the same embedding for same text
        assert (
            result1["embeddings"][0]["embedding"]
            == result2["embeddings"][0]["embedding"]
        )


class TestSentimentAnalyzerNode:
    """Test SentimentAnalyzer node."""

    def test_sentiment_analysis_positive(self):
        """Test positive sentiment detection."""
        node = SentimentAnalyzer(texts=["I love this! It's amazing and wonderful."])

        result = node.execute()

        assert len(result["sentiments"]) == 1
        sentiment = result["sentiments"][0]
        assert sentiment["sentiment"] == "positive"
        assert sentiment["score"] > 0.5

    def test_sentiment_analysis_negative(self):
        """Test negative sentiment detection."""
        node = SentimentAnalyzer(texts=["This is terrible and awful. I hate it."])

        result = node.execute()

        sentiment = result["sentiments"][0]
        assert sentiment["sentiment"] == "negative"
        assert sentiment["score"] < 0.5

    def test_sentiment_analysis_neutral(self):
        """Test neutral sentiment detection."""
        node = SentimentAnalyzer(texts=["This is a neutral statement about facts."])

        result = node.execute()

        sentiment = result["sentiments"][0]
        assert sentiment["sentiment"] == "neutral"
        assert sentiment["score"] == 0.5

    def test_sentiment_analysis_batch(self):
        """Test batch sentiment analysis."""
        texts = ["Great product!", "Terrible service.", "Average experience."]

        node = SentimentAnalyzer(texts=texts)
        result = node.execute()

        assert len(result["sentiments"]) == 3
        sentiments = [s["sentiment"] for s in result["sentiments"]]
        assert "positive" in sentiments
        assert "negative" in sentiments


class TestNamedEntityRecognizerNode:
    """Test NamedEntityRecognizer node."""

    def test_ner_person_detection(self):
        """Test person entity detection."""
        node = NamedEntityRecognizer(
            texts=["John Smith works at Microsoft in New York."],
            entity_types=["PERSON", "ORGANIZATION", "LOCATION"],
        )

        result = node.execute()

        entities = result["entities"][0]["entities"]
        person_entities = [e for e in entities if e["type"] == "PERSON"]
        assert len(person_entities) > 0
        assert any("John" in e["text"] for e in person_entities)

    def test_ner_organization_detection(self):
        """Test organization entity detection."""
        node = NamedEntityRecognizer(
            texts=["I work at Google and Apple."], entity_types=["ORGANIZATION"]
        )

        result = node.execute()

        entities = result["entities"][0]["entities"]
        org_entities = [e for e in entities if e["type"] == "ORGANIZATION"]
        assert len(org_entities) > 0

    def test_ner_location_detection(self):
        """Test location entity detection."""
        node = NamedEntityRecognizer(
            texts=["I traveled to Paris and London."], entity_types=["LOCATION"]
        )

        result = node.execute()

        entities = result["entities"][0]["entities"]
        location_entities = [e for e in entities if e["type"] == "LOCATION"]
        assert len(location_entities) > 0


class TestModelPredictorNode:
    """Test ModelPredictor node."""

    def test_classification_prediction(self):
        """Test classification predictions."""
        data = [{"feature1": 1, "feature2": 2}, {"feature1": 3, "feature2": 4}]

        node = ModelPredictor(data=data, prediction_type="classification")

        result = node.execute()

        assert len(result["predictions"]) == 2
        assert result["prediction_type"] == "classification"

        for prediction in result["predictions"]:
            assert "prediction" in prediction
            assert "confidence" in prediction
            assert "probabilities" in prediction

    def test_regression_prediction(self):
        """Test regression predictions."""
        data = [100, 200, 300]

        node = ModelPredictor(data=data, prediction_type="regression")

        result = node.execute()

        assert len(result["predictions"]) == 3
        assert result["prediction_type"] == "regression"

        for prediction in result["predictions"]:
            assert "prediction" in prediction
            assert "confidence" in prediction
            assert isinstance(prediction["prediction"], (int, float))


class TestTextSummarizerNode:
    """Test TextSummarizer node."""

    def test_extractive_summarization(self):
        """Test extractive summarization."""
        long_text = "This is the first sentence. This is the second sentence. This is the third sentence. This is a very long fourth sentence that might be truncated."

        node = TextSummarizer(texts=[long_text], style="extractive", max_length=100)

        result = node.execute()

        assert len(result["summaries"]) == 1
        summary = result["summaries"][0]
        assert summary["style"] == "extractive"
        assert len(summary["summary"]) <= 100
        assert summary["compression_ratio"] < 1.0

    def test_abstractive_summarization(self):
        """Test abstractive summarization."""
        text = "This is a test document with multiple sentences. It contains information about testing. The summary should be shorter."

        node = TextSummarizer(texts=[text], style="abstractive", max_length=50)

        result = node.execute()

        summary = result["summaries"][0]
        assert summary["style"] == "abstractive"
        assert "..." in summary["summary"]  # Abstractive summaries end with ...


class TestChatAgentNode:
    """Test ChatAgent node."""

    def test_chat_agent_basic(self):
        """Test basic chat functionality."""
        messages = [{"role": "user", "content": "Hello, how are you?"}]

        node = ChatAgent(messages=messages)

        result = node.execute()

        assert "responses" in result
        assert len(result["responses"]) == 1
        assert result["responses"][0]["role"] == "assistant"
        assert "Hello" in result["responses"][0]["content"]

    def test_chat_agent_weather_query(self):
        """Test weather-related query handling."""
        messages = [{"role": "user", "content": "What's the weather like?"}]

        node = ChatAgent(messages=messages)

        result = node.execute()

        response_content = result["responses"][0]["content"]
        assert "weather" in response_content.lower()

    def test_chat_agent_conversation_history(self):
        """Test conversation history tracking."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        node = ChatAgent(messages=messages)

        result = node.execute()

        assert "full_conversation" in result
        assert (
            len(result["full_conversation"]) >= len(messages) + 1
        )  # +1 for system prompt


class TestRetrievalAgentNode:
    """Test RetrievalAgent node."""

    def test_document_retrieval(self):
        """Test document retrieval functionality."""
        documents = [
            {"content": "This document is about machine learning and AI."},
            {"content": "This document discusses natural language processing."},
            {"content": "This document covers computer vision techniques."},
        ]

        node = RetrievalAgent(query="machine learning", documents=documents, top_k=2)

        result = node.execute()

        assert "retrieved_documents" in result
        assert len(result["retrieved_documents"]) <= 2
        assert result["num_retrieved"] >= 0

    def test_retrieval_with_answer_generation(self):
        """Test answer generation from retrieved documents."""
        documents = [
            {"content": "Python is a programming language used for AI development."},
            {
                "content": "Machine learning models can be trained using Python libraries."
            },
        ]

        node = RetrievalAgent(
            query="Python programming", documents=documents, generate_answer=True
        )

        result = node.execute()

        if result["retrieved_documents"]:
            assert result["answer"] is not None
            assert "Python" in result["answer"]


class TestFunctionCallingAgentNode:
    """Test FunctionCallingAgent node."""

    def test_function_calling_basic(self):
        """Test basic function calling."""
        functions = [
            {
                "name": "calculate",
                "description": "Performs mathematical calculations",
                "parameters": {
                    "operation": {"type": "string"},
                    "value": {"type": "number"},
                },
            }
        ]

        node = FunctionCallingAgent(
            query="calculate the square of 5", available_functions=functions
        )

        result = node.execute()

        assert "function_calls" in result
        assert "response" in result
        assert result["num_calls"] >= 0

    def test_function_calling_no_match(self):
        """Test when no functions match the query."""
        functions = [{"name": "weather", "description": "Get weather information"}]

        node = FunctionCallingAgent(
            query="calculate math problems", available_functions=functions
        )

        result = node.execute()

        assert result["num_calls"] == 0
        assert "couldn't find" in result["response"].lower()


class TestPlanningAgentNode:
    """Test PlanningAgent node."""

    def test_data_processing_plan(self):
        """Test planning for data processing tasks."""
        tools = ["CSVReaderNode", "Filter", "Aggregator", "CSVWriterNode"]

        node = PlanningAgent(
            goal="process customer data and generate summary", available_tools=tools
        )

        result = node.execute()

        assert "plan" in result
        assert result["estimated_steps"] > 0
        assert result["feasibility"] in ["high", "medium", "low"]

    def test_text_analysis_plan(self):
        """Test planning for text analysis tasks."""
        tools = [
            "TextReaderNode",
            "SentimentAnalyzer",
            "TextSummarizer",
            "JSONWriterNode",
        ]

        node = PlanningAgent(
            goal="analyze text sentiment and summarize", available_tools=tools
        )

        result = node.execute()

        assert len(result["plan"]) > 0
        plan_tools = [step["tool"] for step in result["plan"]]
        assert any("Sentiment" in tool or "Summariz" in tool for tool in plan_tools)

    def test_planning_with_constraints(self):
        """Test planning with time constraints."""
        tools = ["Reader", "Processor", "Writer"]
        constraints = {"time_limit": 30}  # 30 seconds

        node = PlanningAgent(
            goal="quick data processing",
            available_tools=tools,
            constraints=constraints,
            max_steps=5,
        )

        result = node.execute()

        # Should respect time constraints
        assert len(result["plan"]) <= 3  # 30 seconds / 10 seconds per step
        assert result["constraints"] == constraints

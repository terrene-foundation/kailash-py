"""Tests for AI nodes - Fixed version."""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

from kailash.nodes.ai.models import (
    TextClassifier,
    ModelPredictor,
    TextEmbedder,
    SentimentAnalyzer,
    TextSummarizer,
    NamedEntityRecognizer
)
from kailash.nodes.ai.agents import (
    ChatAgent,
    RetrievalAgent,
    FunctionCallingAgent,
    PlanningAgent
)
from kailash.sdk_exceptions import KailashValidationError, KailashRuntimeError


class TestTextClassifier:
    """Test text classifier node."""
    
    def test_text_classifier_init(self):
        """Test text classifier initialization."""
        node = TextClassifier()
        params = node.get_parameters()
        
        assert "text" in params
        assert "model_name" in params
        assert "labels" in params
        assert params["text"].required is True
        assert params["model_name"].required is False
        assert params["labels"].required is False
    
    def test_text_classifier_run(self):
        """Test text classifier execution."""
        node = TextClassifier()
        
        # Mock the classification
        with patch.object(node, '_classify_text') as mock_classify:
            mock_classify.return_value = {
                "label": "positive",
                "confidence": 0.95
            }
            
            result = node.run(
                text="This is great!",
                labels=["positive", "negative", "neutral"]
            )
            
            assert result["classification"]["label"] == "positive"
            assert result["classification"]["confidence"] == 0.95
            assert result["text"] == "This is great!"
            assert result["labels"] == ["positive", "negative", "neutral"]


class TestSentimentAnalyzer:
    """Test sentiment analyzer node."""
    
    def test_sentiment_analyzer_init(self):
        """Test sentiment analyzer initialization."""
        node = SentimentAnalyzer()
        params = node.get_parameters()
        
        assert "text" in params
        assert "model_name" in params
        assert params["text"].required is True
    
    def test_sentiment_analyzer_run(self):
        """Test sentiment analyzer execution."""
        node = SentimentAnalyzer()
        
        # Mock the analysis
        with patch.object(node, '_analyze_sentiment') as mock_analyze:
            mock_analyze.return_value = {
                "sentiment": "positive",
                "confidence": 0.89,
                "scores": {
                    "positive": 0.89,
                    "negative": 0.08,
                    "neutral": 0.03
                }
            }
            
            result = node.run(text="I love this product!")
            
            assert result["analysis"]["sentiment"] == "positive"
            assert result["analysis"]["confidence"] == 0.89
            assert result["text"] == "I love this product!"


class TestChatAgent:
    """Test chat agent node."""
    
    def test_chat_agent_init(self):
        """Test chat agent initialization."""
        node = ChatAgent()
        params = node.get_parameters()
        
        assert "messages" in params
        assert "model" in params
        assert "temperature" in params
        assert params["messages"].required is True
        assert params["model"].default == "default"
        assert params["temperature"].default == 0.7
    
    def test_chat_agent_run(self):
        """Test chat agent execution."""
        node = ChatAgent()
        
        messages = [
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        result = node.run(messages=messages)
        
        # Should return a mock response since we're not connected to a real API
        assert "response" in result
        assert "messages" in result
        assert result["messages"][-1]["role"] == "assistant"
        assert "model" in result["response"]
    
    def test_chat_agent_with_system_prompt(self):
        """Test chat agent with system prompt."""
        node = ChatAgent()
        
        messages = [
            {"role": "user", "content": "What's 2+2?"}
        ]
        
        result = node.run(
            messages=messages,
            system_prompt="You are a math tutor."
        )
        
        assert "response" in result
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][0]["content"] == "You are a math tutor."


class TestRetrievalAgent:
    """Test retrieval agent node."""
    
    def test_retrieval_agent_init(self):
        """Test retrieval agent initialization."""
        node = RetrievalAgent()
        params = node.get_parameters()
        
        assert "query" in params
        assert "documents" in params
        assert "top_k" in params
        assert params["query"].required is True
        assert params["documents"].required is True
        assert params["top_k"].default == 5
    
    def test_retrieval_agent_run(self):
        """Test retrieval agent execution."""
        node = RetrievalAgent()
        
        documents = [
            {"id": 1, "content": "Python is a programming language"},
            {"id": 2, "content": "Java is also a programming language"},
            {"id": 3, "content": "Machine learning with Python"}
        ]
        
        result = node.run(
            query="Python programming",
            documents=documents,
            top_k=2
        )
        
        assert "results" in result
        assert "query" in result
        assert len(result["results"]) <= 2
        assert result["query"] == "Python programming"


class TestPlanningAgent:
    """Test planning agent node."""
    
    def test_planning_agent_init(self):
        """Test planning agent initialization."""
        node = PlanningAgent()
        params = node.get_parameters()
        
        assert "goal" in params
        assert "context" in params
        assert "constraints" in params
        assert params["goal"].required is True
    
    def test_planning_agent_run(self):
        """Test planning agent execution."""
        node = PlanningAgent()
        
        result = node.run(
            goal="Build a web application",
            context="Using Python and React",
            constraints=["Must be completed in 2 weeks", "Budget of $5000"]
        )
        
        assert "plan" in result
        assert "steps" in result["plan"]
        assert "estimated_duration" in result["plan"]
        assert "goal" in result
        assert result["goal"] == "Build a web application"


class TestTextEmbedder:
    """Test text embedder node."""
    
    def test_text_embedder_init(self):
        """Test text embedder initialization."""
        node = TextEmbedder()
        params = node.get_parameters()
        
        assert "text" in params
        assert "model_name" in params
        assert params["text"].required is True
    
    def test_text_embedder_run(self):
        """Test text embedder execution."""
        node = TextEmbedder()
        
        result = node.run(text="This is a test sentence")
        
        assert "embedding" in result
        assert "text" in result
        assert "model" in result
        assert isinstance(result["embedding"], list)
        assert len(result["embedding"]) > 0
        assert all(isinstance(x, float) for x in result["embedding"])


class TestTextSummarizer:
    """Test text summarizer node."""
    
    def test_text_summarizer_init(self):
        """Test text summarizer initialization."""
        node = TextSummarizer()
        params = node.get_parameters()
        
        assert "text" in params
        assert "max_length" in params
        assert params["text"].required is True
        assert params["max_length"].default == 100
    
    def test_text_summarizer_run(self):
        """Test text summarizer execution."""
        node = TextSummarizer()
        
        long_text = " ".join(["This is a sentence."] * 20)
        
        result = node.run(text=long_text, max_length=50)
        
        assert "summary" in result
        assert "text" in result
        assert "compression_ratio" in result
        assert len(result["summary"]) <= len(long_text)
        assert result["text"] == long_text
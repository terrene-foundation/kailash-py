"""Tests for AI nodes."""

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
    AgentNode,
    AgentChainNode,
    ToolNode,
    MemoryNode
)
from kailash.sdk_exceptions import KailashValidationError, KailashRuntimeError


class TestLLMNode:
    """Test LLM node."""
    
    @patch('kailash.nodes.ai.models.openai')
    def test_llm_completion(self, mock_openai):
        """Test LLM completion."""
        mock_response = Mock()
        mock_response.choices = [Mock(text="Generated response")]
        mock_openai.Completion.create.return_value = mock_response
        
        node = LLMNode(node_id="llm", name="LLM Node")
        
        result = node.execute({
            "prompt": "Hello, world!",
            "model": "gpt-3.5-turbo",
            "max_tokens": 100
        })
        
        assert result["response"] == "Generated response"
        mock_openai.Completion.create.assert_called_once()
    
    @patch('kailash.nodes.ai.models.anthropic')
    def test_llm_with_anthropic(self, mock_anthropic):
        """Test LLM with Anthropic provider."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.completion = "Claude response"
        mock_client.completions.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client
        
        node = LLMNode(node_id="llm", name="LLM Node")
        
        result = node.execute({
            "prompt": "Hello, Claude!",
            "model": "claude-2",
            "provider": "anthropic",
            "api_key": "test-key"
        })
        
        assert result["response"] == "Claude response"
    
    def test_llm_missing_prompt(self):
        """Test LLM without prompt."""
        node = LLMNode(node_id="llm", name="LLM Node")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "model": "gpt-3.5-turbo"
            })
    
    @patch('kailash.nodes.ai.models.openai')
    def test_llm_with_parameters(self, mock_openai):
        """Test LLM with additional parameters."""
        mock_response = Mock()
        mock_response.choices = [Mock(text="Creative response")]
        mock_openai.Completion.create.return_value = mock_response
        
        node = LLMNode(node_id="llm", name="LLM Node")
        
        result = node.execute({
            "prompt": "Write a story",
            "model": "gpt-3.5-turbo",
            "temperature": 0.9,
            "top_p": 0.95,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1
        })
        
        assert result["response"] == "Creative response"
        
        # Verify parameters were passed
        call_args = mock_openai.Completion.create.call_args[1]
        assert call_args["temperature"] == 0.9
        assert call_args["top_p"] == 0.95
    
    @patch('kailash.nodes.ai.models.openai')
    def test_llm_error_handling(self, mock_openai):
        """Test LLM error handling."""
        mock_openai.Completion.create.side_effect = Exception("API Error")
        
        node = LLMNode(node_id="llm", name="LLM Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "prompt": "Test prompt",
                "model": "gpt-3.5-turbo"
            })


class TestTextClassificationNode:
    """Test text classification node."""
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_text_classification(self, mock_transformers):
        """Test text classification."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"label": "POSITIVE", "score": 0.95},
            {"label": "NEGATIVE", "score": 0.05}
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = TextClassificationNode(node_id="classifier", name="Text Classifier")
        
        result = node.execute({
            "text": "This is a great product!",
            "model": "distilbert-base-uncased-finetuned-sst-2-english"
        })
        
        assert result["label"] == "POSITIVE"
        assert result["score"] == 0.95
        assert len(result["all_scores"]) == 2
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_text_classification_with_labels(self, mock_transformers):
        """Test text classification with candidate labels."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = {
            "labels": ["technology", "sports", "politics"],
            "scores": [0.8, 0.15, 0.05]
        }
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = TextClassificationNode(node_id="classifier", name="Text Classifier")
        
        result = node.execute({
            "text": "The new smartphone features AI capabilities",
            "model": "facebook/bart-large-mnli",
            "candidate_labels": ["technology", "sports", "politics"]
        })
        
        assert result["label"] == "technology"
        assert result["score"] == 0.8
    
    def test_text_classification_missing_text(self):
        """Test classification without text."""
        node = TextClassificationNode(node_id="classifier", name="Text Classifier")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "model": "bert-base-uncased"
            })
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_text_classification_batch(self, mock_transformers):
        """Test batch text classification."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            [{"label": "POSITIVE", "score": 0.9}],
            [{"label": "NEGATIVE", "score": 0.85}]
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = TextClassificationNode(node_id="classifier", name="Text Classifier")
        
        result = node.execute({
            "text": ["Great product!", "Terrible service"],
            "model": "distilbert-base-uncased",
            "batch_size": 2
        })
        
        assert len(result["labels"]) == 2
        assert result["labels"][0] == "POSITIVE"
        assert result["labels"][1] == "NEGATIVE"


class TestTextGenerationNode:
    """Test text generation node."""
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_text_generation(self, mock_transformers):
        """Test text generation."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"generated_text": "Once upon a time, there was a magical kingdom..."}
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = TextGenerationNode(node_id="generator", name="Text Generator")
        
        result = node.execute({
            "prompt": "Once upon a time",
            "model": "gpt2",
            "max_length": 50
        })
        
        assert "generated_text" in result
        assert result["generated_text"].startswith("Once upon a time")
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_text_generation_with_parameters(self, mock_transformers):
        """Test text generation with parameters."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"generated_text": "Creative story about dragons"}
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = TextGenerationNode(node_id="generator", name="Text Generator")
        
        result = node.execute({
            "prompt": "Write a story",
            "model": "gpt2-medium",
            "max_length": 100,
            "temperature": 0.9,
            "top_p": 0.95,
            "do_sample": True
        })
        
        assert "generated_text" in result
        
        # Verify parameters were passed
        call_args = mock_pipeline.call_args[1]
        assert call_args["max_length"] == 100
        assert call_args["temperature"] == 0.9
    
    def test_text_generation_missing_prompt(self):
        """Test generation without prompt."""
        node = TextGenerationNode(node_id="generator", name="Text Generator")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "model": "gpt2"
            })


class TestEmbeddingNode:
    """Test embedding generation node."""
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_embedding_generation(self, mock_transformers):
        """Test embedding generation."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        
        # Mock tokenizer output
        mock_tokenizer.return_value = {
            "input_ids": [[101, 2023, 102]],
            "attention_mask": [[1, 1, 1]]
        }
        
        # Mock model output
        mock_output = Mock()
        mock_output.last_hidden_state = Mock()
        mock_output.last_hidden_state.mean.return_value.numpy.return_value = [
            [0.1, 0.2, 0.3, 0.4]
        ]
        mock_model.return_value = mock_output
        
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        mock_transformers.AutoModel.from_pretrained.return_value = mock_model
        
        node = EmbeddingNode(node_id="embedder", name="Embedding Node")
        
        result = node.execute({
            "text": "Generate embeddings for this text",
            "model": "sentence-transformers/all-MiniLM-L6-v2"
        })
        
        assert "embeddings" in result
        assert len(result["embeddings"]) == 4
    
    @patch('kailash.nodes.ai.models.openai')
    def test_embedding_with_openai(self, mock_openai):
        """Test embedding generation with OpenAI."""
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5])]
        mock_openai.Embedding.create.return_value = mock_response
        
        node = EmbeddingNode(node_id="embedder", name="Embedding Node")
        
        result = node.execute({
            "text": "Generate embeddings",
            "model": "text-embedding-ada-002",
            "provider": "openai",
            "api_key": "test-key"
        })
        
        assert "embeddings" in result
        assert len(result["embeddings"]) == 5
    
    def test_embedding_missing_text(self):
        """Test embedding without text."""
        node = EmbeddingNode(node_id="embedder", name="Embedding Node")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "model": "bert-base-uncased"
            })
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_embedding_batch_processing(self, mock_transformers):
        """Test batch embedding generation."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        
        # Mock for batch processing
        batch_embeddings = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6]
        ]
        
        mock_tokenizer.return_value = {
            "input_ids": [[101, 102], [101, 102]],
            "attention_mask": [[1, 1], [1, 1]]
        }
        
        mock_output = Mock()
        mock_output.last_hidden_state.mean.return_value.numpy.return_value = batch_embeddings
        mock_model.return_value = mock_output
        
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        mock_transformers.AutoModel.from_pretrained.return_value = mock_model
        
        node = EmbeddingNode(node_id="embedder", name="Embedding Node")
        
        result = node.execute({
            "text": ["First text", "Second text"],
            "model": "bert-base-uncased",
            "batch_size": 2
        })
        
        assert "embeddings" in result
        assert len(result["embeddings"]) == 2
        assert len(result["embeddings"][0]) == 3


class TestSentimentAnalysisNode:
    """Test sentiment analysis node."""
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_sentiment_analysis(self, mock_transformers):
        """Test sentiment analysis."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"label": "POSITIVE", "score": 0.98}
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = SentimentAnalysisNode(node_id="sentiment", name="Sentiment Analyzer")
        
        result = node.execute({
            "text": "I love this product! It's amazing!",
            "model": "distilbert-base-uncased-finetuned-sst-2-english"
        })
        
        assert result["sentiment"] == "POSITIVE"
        assert result["confidence"] == 0.98
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_sentiment_analysis_negative(self, mock_transformers):
        """Test negative sentiment analysis."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"label": "NEGATIVE", "score": 0.87}
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = SentimentAnalysisNode(node_id="sentiment", name="Sentiment Analyzer")
        
        result = node.execute({
            "text": "This is terrible. Very disappointed.",
            "model": "distilbert-base-uncased-finetuned-sst-2-english"
        })
        
        assert result["sentiment"] == "NEGATIVE"
        assert result["confidence"] == 0.87
    
    def test_sentiment_analysis_missing_text(self):
        """Test sentiment analysis without text."""
        node = SentimentAnalysisNode(node_id="sentiment", name="Sentiment Analyzer")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "model": "bert-base-uncased"
            })
    
    @patch('kailash.nodes.ai.models.transformers')
    def test_sentiment_analysis_batch(self, mock_transformers):
        """Test batch sentiment analysis."""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            [{"label": "POSITIVE", "score": 0.9}],
            [{"label": "NEGATIVE", "score": 0.85}],
            [{"label": "NEUTRAL", "score": 0.7}]
        ]
        mock_transformers.pipeline.return_value = mock_pipeline
        
        node = SentimentAnalysisNode(node_id="sentiment", name="Sentiment Analyzer")
        
        result = node.execute({
            "text": ["Great!", "Terrible!", "It's okay"],
            "model": "distilbert-base-uncased"
        })
        
        assert len(result["sentiments"]) == 3
        assert result["sentiments"][0] == "POSITIVE"
        assert result["sentiments"][1] == "NEGATIVE"
        assert result["sentiments"][2] == "NEUTRAL"


class TestAgentNode:
    """Test agent node."""
    
    def test_agent_creation(self):
        """Test agent node creation."""
        node = AgentNode(
            node_id="agent",
            name="Test Agent",
            role="Assistant",
            instructions="Help the user",
            tools=["tool1", "tool2"]
        )
        
        assert node.role == "Assistant"
        assert node.instructions == "Help the user"
        assert node.tools == ["tool1", "tool2"]
    
    @patch('kailash.nodes.ai.agents.openai')
    def test_agent_execution(self, mock_openai):
        """Test agent execution."""
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Agent response"))]
        mock_openai.ChatCompletion.create.return_value = mock_response
        
        node = AgentNode(
            node_id="agent",
            name="Test Agent",
            role="Assistant"
        )
        
        result = node.execute({
            "message": "Hello, agent!",
            "context": {}
        })
        
        assert result["response"] == "Agent response"
        assert "conversation_history" in result
    
    def test_agent_with_memory(self):
        """Test agent with memory."""
        node = AgentNode(
            node_id="agent",
            name="Test Agent",
            role="Assistant",
            memory_enabled=True
        )
        
        # First interaction
        result1 = node.execute({
            "message": "My name is John",
            "context": {}
        })
        
        # Second interaction should remember
        result2 = node.execute({
            "message": "What's my name?",
            "context": {"history": result1["conversation_history"]}
        })
        
        # Memory should contain previous interactions
        assert len(result2["conversation_history"]) > 1
    
    def test_agent_missing_message(self):
        """Test agent without message."""
        node = AgentNode(
            node_id="agent",
            name="Test Agent",
            role="Assistant"
        )
        
        with pytest.raises(KailashValidationError):
            node.execute({"context": {}})


class TestAgentChainNode:
    """Test agent chain node."""
    
    def test_agent_chain_creation(self):
        """Test agent chain creation."""
        agents = [
            {"id": "agent1", "role": "Researcher"},
            {"id": "agent2", "role": "Writer"},
            {"id": "agent3", "role": "Editor"}
        ]
        
        node = AgentChainNode(
            node_id="chain",
            name="Agent Chain",
            agents=agents
        )
        
        assert len(node.agents) == 3
        assert node.agents[0]["role"] == "Researcher"
    
    @patch('kailash.nodes.ai.agents.AgentNode')
    def test_agent_chain_execution(self, mock_agent_class):
        """Test agent chain execution."""
        # Mock individual agents
        mock_agents = []
        for i in range(3):
            mock_agent = Mock()
            mock_agent.execute.return_value = {
                "response": f"Agent {i} response",
                "conversation_history": []
            }
            mock_agents.append(mock_agent)
        
        mock_agent_class.side_effect = mock_agents
        
        agents = [
            {"id": f"agent{i}", "role": f"Role{i}"}
            for i in range(3)
        ]
        
        node = AgentChainNode(
            node_id="chain",
            name="Agent Chain",
            agents=agents
        )
        
        result = node.execute({
            "initial_message": "Start the chain",
            "context": {}
        })
        
        assert len(result["chain_results"]) == 3
        assert result["final_response"] == "Agent 2 response"
    
    def test_agent_chain_empty_agents(self):
        """Test agent chain with no agents."""
        with pytest.raises(KailashValidationError):
            AgentChainNode(
                node_id="chain",
                name="Agent Chain",
                agents=[]
            )


class TestToolNode:
    """Test tool node."""
    
    def test_tool_creation(self):
        """Test tool node creation."""
        node = ToolNode(
            node_id="tool",
            name="Calculator Tool",
            tool_type="calculator",
            parameters={"operations": ["add", "subtract", "multiply", "divide"]}
        )
        
        assert node.tool_type == "calculator"
        assert "operations" in node.parameters
    
    def test_tool_execution_calculator(self):
        """Test calculator tool execution."""
        node = ToolNode(
            node_id="tool",
            name="Calculator Tool",
            tool_type="calculator"
        )
        
        result = node.execute({
            "operation": "add",
            "operands": [5, 3]
        })
        
        assert result["result"] == 8
    
    def test_tool_execution_search(self):
        """Test search tool execution."""
        node = ToolNode(
            node_id="tool",
            name="Search Tool", 
            tool_type="search"
        )
        
        with patch('kailash.nodes.ai.agents.requests') as mock_requests:
            mock_response = Mock()
            mock_response.json.return_value = {
                "results": ["Result 1", "Result 2"]
            }
            mock_requests.get.return_value = mock_response
            
            result = node.execute({
                "query": "test search",
                "api_key": "test-key"
            })
            
            assert len(result["results"]) == 2
    
    def test_tool_invalid_type(self):
        """Test tool with invalid type."""
        with pytest.raises(KailashValidationError):
            ToolNode(
                node_id="tool",
                name="Invalid Tool",
                tool_type="nonexistent"
            )
    
    def test_tool_missing_parameters(self):
        """Test tool without required parameters."""
        node = ToolNode(
            node_id="tool",
            name="Calculator Tool",
            tool_type="calculator"
        )
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "operation": "add"
                # Missing operands
            })


class TestMemoryNode:
    """Test memory node."""
    
    def test_memory_creation(self):
        """Test memory node creation."""
        node = MemoryNode(
            node_id="memory",
            name="Conversation Memory",
            memory_type="conversation",
            max_entries=100
        )
        
        assert node.memory_type == "conversation"
        assert node.max_entries == 100
    
    def test_memory_store_and_retrieve(self):
        """Test storing and retrieving from memory."""
        node = MemoryNode(
            node_id="memory",
            name="Test Memory"
        )
        
        # Store data
        store_result = node.execute({
            "operation": "store",
            "key": "user_name",
            "value": "John Doe"
        })
        
        assert store_result["success"] is True
        
        # Retrieve data
        retrieve_result = node.execute({
            "operation": "retrieve",
            "key": "user_name"
        })
        
        assert retrieve_result["value"] == "John Doe"
    
    def test_memory_conversation_history(self):
        """Test conversation history memory."""
        node = MemoryNode(
            node_id="memory",
            name="Conversation Memory",
            memory_type="conversation"
        )
        
        # Add messages
        node.execute({
            "operation": "add_message",
            "role": "user",
            "content": "Hello"
        })
        
        node.execute({
            "operation": "add_message",
            "role": "assistant",
            "content": "Hi there!"
        })
        
        # Get history
        result = node.execute({
            "operation": "get_history",
            "limit": 10
        })
        
        assert len(result["history"]) == 2
        assert result["history"][0]["content"] == "Hello"
    
    def test_memory_clear(self):
        """Test clearing memory."""
        node = MemoryNode(
            node_id="memory",
            name="Test Memory"
        )
        
        # Store data
        node.execute({
            "operation": "store",
            "key": "test",
            "value": "value"
        })
        
        # Clear memory
        clear_result = node.execute({
            "operation": "clear"
        })
        
        assert clear_result["success"] is True
        
        # Try to retrieve cleared data
        retrieve_result = node.execute({
            "operation": "retrieve",
            "key": "test"
        })
        
        assert retrieve_result["value"] is None
    
    def test_memory_max_entries(self):
        """Test memory with max entries limit."""
        node = MemoryNode(
            node_id="memory",
            name="Limited Memory",
            max_entries=3
        )
        
        # Add more than max entries
        for i in range(5):
            node.execute({
                "operation": "store",
                "key": f"key{i}",
                "value": f"value{i}"
            })
        
        # Check that only last 3 entries are kept
        all_entries = node.execute({
            "operation": "get_all"
        })
        
        assert len(all_entries["entries"]) == 3
    
    def test_memory_invalid_operation(self):
        """Test memory with invalid operation."""
        node = MemoryNode(
            node_id="memory",
            name="Test Memory"
        )
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "operation": "invalid_op"
            })
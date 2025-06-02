"""Data source nodes for providing input data to workflows."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class DocumentSourceNode(Node):
    """Provides sample documents for hierarchical RAG processing."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "sample_documents": NodeParameter(
                name="sample_documents",
                type=bool,
                required=False,
                default=True,
                description="Use built-in sample documents",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Sample documents for demonstration
        documents = [
            {
                "id": "doc1",
                "title": "Machine Learning Basics",
                "content": """Machine learning is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed. There are three main types of machine learning: supervised learning, unsupervised learning, and reinforcement learning. Supervised learning uses labeled data to train models that can make predictions on new data. Common algorithms include linear regression, decision trees, and neural networks. The process involves splitting data into training and testing sets to evaluate model performance.""",
            },
            {
                "id": "doc2",
                "title": "Deep Learning Overview",
                "content": """Deep learning is a specialized area of machine learning that uses neural networks with multiple layers to model and understand complex patterns in data. These networks, called deep neural networks, can automatically learn hierarchical representations of data. Popular architectures include convolutional neural networks (CNNs) for image processing, recurrent neural networks (RNNs) for sequential data, and transformers for natural language processing. Deep learning has achieved breakthrough results in computer vision, speech recognition, and language understanding.""",
            },
            {
                "id": "doc3",
                "title": "Natural Language Processing",
                "content": """Natural Language Processing (NLP) is a field that combines computational linguistics with machine learning to help computers understand, interpret, and generate human language. Key NLP tasks include tokenization, part-of-speech tagging, named entity recognition, sentiment analysis, and machine translation. Modern NLP relies heavily on transformer architectures like BERT and GPT, which use attention mechanisms to understand context and relationships between words. Applications include chatbots, search engines, and language translation services.""",
            },
        ]

        print(f"Debug DocumentSource: providing {len(documents)} documents")
        return {"documents": documents}


@register_node()
class QuerySourceNode(Node):
    """Provides sample queries for RAG processing."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                default="What are the main types of machine learning?",
                description="Query to process",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "What are the main types of machine learning?")
        print(f"Debug QuerySource: providing query='{query}'")
        return {"query": query}

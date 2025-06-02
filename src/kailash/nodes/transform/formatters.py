"""Text formatting nodes for transforming and preparing text data."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class ChunkTextExtractorNode(Node):
    """Extracts text content from chunks for embedding generation."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "chunks": NodeParameter(
                name="chunks",
                type=list,
                required=False,
                description="List of chunks to extract text from",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        chunks = kwargs.get("chunks", [])
        # Extract just the content text from chunks
        texts = [chunk["content"] for chunk in chunks]
        return {"input_texts": texts}


@register_node()
class QueryTextWrapperNode(Node):
    """Wraps query string in list for embedding generation."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query string to wrap",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        print(f"Debug QueryTextWrapper: received query='{query}'")
        # Use input_texts for batch embedding (single item list)
        result = {"input_texts": [query]}
        print(f"Debug QueryTextWrapper: returning {result}")
        return result


@register_node()
class ContextFormatterNode(Node):
    """Formats relevant chunks into context for LLM."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "relevant_chunks": NodeParameter(
                name="relevant_chunks",
                type=list,
                required=False,
                description="List of relevant chunks with scores",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Original query string",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        relevant_chunks = kwargs.get("relevant_chunks", [])
        query = kwargs.get("query", "")
        # Format context from relevant chunks
        context_parts = []
        for chunk in relevant_chunks:
            context_parts.append(
                f"From '{chunk['document_title']}' (Score: {chunk['relevance_score']:.3f}):\n"
                f"{chunk['content']}\n"
            )

        context = "\n".join(context_parts)

        # Create prompt for LLM
        prompt = f"""Based on the following context, please answer the question: "{query}"

Context:
{context}

Please provide a comprehensive answer based on the information provided above."""

        # Create messages list for LLMAgent
        messages = [{"role": "user", "content": prompt}]

        return {"formatted_prompt": prompt, "messages": messages, "context": context}

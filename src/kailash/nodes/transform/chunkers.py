"""Document chunking nodes for splitting text into manageable pieces."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class HierarchicalChunkerNode(Node):
    """Splits documents into hierarchical chunks for better retrieval."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=False,
                description="List of documents to chunk",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=200,
                description="Target size for text chunks",
            ),
            "overlap": NodeParameter(
                name="overlap",
                type=int,
                required=False,
                default=50,
                description="Overlap between chunks",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        documents = kwargs.get("documents", [])
        chunk_size = kwargs.get("chunk_size", 200)
        # overlap = kwargs.get("overlap", 50)  # Currently not used in chunking logic

        print(f"Debug Chunker: received {len(documents)} documents")

        all_chunks = []

        for doc in documents:
            content = doc["content"]
            doc_id = doc["id"]
            title = doc["title"]

            # Simple sentence-aware chunking
            sentences = content.split(". ")
            chunks = []
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) < chunk_size:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "

            if current_chunk:
                chunks.append(current_chunk.strip())

            # Create hierarchical chunk structure
            for i, chunk in enumerate(chunks):
                chunk_data = {
                    "chunk_id": f"{doc_id}_chunk_{i}",
                    "document_id": doc_id,
                    "document_title": title,
                    "chunk_index": i,
                    "content": chunk,
                    "hierarchy_level": "paragraph",
                }
                all_chunks.append(chunk_data)

        return {"chunks": all_chunks}

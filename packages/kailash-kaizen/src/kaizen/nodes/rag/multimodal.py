"""
Multimodal RAG Implementation

Wires a real LLM query-analysis + response-generation pipeline over a
lexical/hash-based placeholder encoder. The encoder is a deterministic
hash/character-code heuristic, NOT a learned vision model (no CLIP, no BLIP-2,
no image-pixel understanding). The LLM stages (query analysis, response
generation) are genuine; the cross-modal "encoding" is a stand-in that lets the
pipeline run end-to-end without a vision backend.

Pipeline stages:
- Real LLM query analysis (modality detection)
- Lexical/hash-based placeholder encoding for text + image references
- Real LLM response generation over the assembled context
"""

import logging
import os
from typing import Any, Dict, Union

from kailash.nodes.base import Node, NodeParameter, register_node

# PythonCodeNode and LLMAgentNode are imported for their @register_node
# decorator side-effect: the codegen workflow below references them by the
# string node-type name ("PythonCodeNode" / "LLMAgentNode"), which the runtime
# resolves through the node registry. The imports populate that registry.
from kailash.nodes.code.python import PythonCodeNode  # noqa: F401
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder

from ..ai.llm_agent import LLMAgentNode  # noqa: F401
from kaizen.core._provider_env import detect_provider_from_env

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)

# Vision-capable model for the response-generation stage. Env-resolved so no
# provider-locked model string is hardcoded (env-models compliance); falls back
# to the general default LLM model when OPENAI_VISION_MODEL is unset.
_DEFAULT_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", _DEFAULT_LLM_MODEL)


@register_node()
class MultimodalRAGNode(WorkflowNode):
    """
    Multimodal RAG with Text + Image References

    Wires a real LLM query-analysis + response-generation pipeline over a
    lexical/hash-based placeholder encoder. The encoder is a deterministic
    hash/character-code heuristic — it does NOT run a learned vision model
    (no CLIP, no BLIP-2) and cannot understand image pixels. Use this node to
    demonstrate the multimodal-RAG composition pattern; the genuine
    capabilities are the LLM query-analysis and response-generation stages.

    When to use:
    - Best for: prototyping a multimodal-RAG pipeline shape where the LLM
      stages carry the value and the encoder is a stand-in
    - Not ideal for: production visual retrieval requiring a real vision model

    Key features:
    - Real LLM query analysis (modality detection)
    - Lexical/hash-based placeholder encoding for text + image references
    - Real LLM response generation over the assembled context
    - Support for various image-reference formats (as metadata, not pixels)

    Example:
        multimodal_rag = MultimodalRAGNode(
            image_encoder="placeholder",  # informational label only; no model is loaded
            enable_ocr=True
        )

        # Query: "Show me the architecture diagram for transformers"
        # The pipeline:
        # 1. Real LLM analyses the query for required modalities
        # 2. Placeholder encoder scores text docs + image-reference metadata
        #    (captions/alt-text/paths) lexically — it does NOT read pixels
        # 3. Real LLM generates the answer over the assembled text context
        # Image "results" are the matched image-reference records, not visual
        # understanding of the images themselves.

        result = await multimodal_rag.execute(
            documents=mixed_media_docs,  # text docs + image-reference records
            query="Show me the architecture diagram for transformers"
        )

    Parameters:
        image_encoder: Informational label for the placeholder image encoder
            (no vision model is loaded)
        text_encoder: Informational label for the placeholder text encoder
        enable_ocr: Attach a placeholder OCR field to image references
            (no real OCR engine runs)
        fusion_strategy: How to combine text and image-reference scores

    Returns:
        text_results: Retrieved text documents
        image_results: Retrieved images with captions
        combined_answer: Multimodal response
        modality_scores: Relevance per modality
    """

    def __init__(
        self,
        name: str = "multimodal_rag",
        image_encoder: str = "clip-base",
        enable_ocr: bool = True,
        fusion_strategy: str = "weighted",
    ):
        self.image_encoder = image_encoder
        self.enable_ocr = enable_ocr
        self.fusion_strategy = fusion_strategy
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create multimodal RAG workflow"""
        builder = WorkflowBuilder()

        # Query analyzer for modality detection
        query_analyzer_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_analyzer",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Analyze the query to determine required modalities.

Identify:
1. Is visual information needed?
2. What type of images would be helpful?
3. Should we prioritize text or images?

Return JSON:
{
    "needs_images": true/false,
    "image_types": ["diagram", "photo", "chart", etc.],
    "text_weight": 0.0-1.0,
    "image_weight": 0.0-1.0,
    "query_type": "visual|textual|mixed"
}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Document preprocessor
        doc_preprocessor_id = builder.add_node(
            "PythonCodeNode",
            node_id="doc_preprocessor",
            config={
                "code": f"""
import json
import base64
from pathlib import Path

def preprocess_documents(documents):
    '''Separate and prepare text and image documents'''
    text_docs = []
    image_docs = []

    for doc in documents:
        # Documents are arbitrary user input; skip non-dict elements rather
        # than crash on `.get`.
        if not isinstance(doc, dict):
            continue
        doc_type = doc.get("type", "text")

        if doc_type == "text":
            text_docs.append({{
                "id": doc.get("id", f"text_{{len(text_docs)}}"),
                "content": doc.get("content") or "",
                "title": doc.get("title", ""),
                "metadata": doc.get("metadata", {{}})
            }})

        elif doc_type in ["image", "multimodal"]:
            # Handle image documents
            image_path = doc.get("image_path") or doc.get("path")

            image_doc = {{
                "id": doc.get("id", f"image_{{len(image_docs)}}"),
                "path": image_path,
                "caption": doc.get("caption", ""),
                "alt_text": doc.get("alt_text", ""),
                "metadata": doc.get("metadata", {{}}),
                "associated_text": doc.get("content") or ""
            }}

            # If OCR is enabled, we'd extract text here
            if {self.enable_ocr} and image_path:
                # Placeholder OCR result (no real OCR engine is invoked)
                image_doc["ocr_text"] = f"[OCR text from {{image_path}}]"

            image_docs.append(image_doc)

            # Also add associated text as separate doc
            if doc.get("content"):
                text_docs.append({{
                    "id": f"{{doc.get('id', '')}}_text",
                    "content": doc.get("content") or "",
                    "title": doc.get("title", ""),
                    "metadata": {{"from_multimodal": True}}
                }})

    result = {{
        "preprocessed_docs": {{
            "text_documents": text_docs,
            "image_documents": image_docs,
            "stats": {{
                "total_text": len(text_docs),
                "total_images": len(image_docs),
                "multimodal_docs": len([d for d in documents if isinstance(d, dict) and d.get("type") == "multimodal"])
            }}
        }}
    }}
"""
            },
        )

        # Multimodal encoder
        encoder_id = builder.add_node(
            "PythonCodeNode",
            node_id="multimodal_encoder",
            config={
                "code": f"""
import numpy as np
from typing import List, Dict

def encode_multimodal(text_docs, image_docs, query, modality_analysis):
    '''Encode documents and query for multimodal retrieval'''

    # Deterministic hash/character-code placeholder encoder — NOT a learned
    # vision/CLIP model. Produces stable numeric vectors from raw bytes so the
    # pipeline runs end-to-end without a vision backend.
    def text_encoder(text):
        # Documents are arbitrary user input; a present-but-None content/title
        # would crash `text[:10]`. Coerce non-strings to "" at the boundary.
        text = text if isinstance(text, str) else ""
        # Simple hash-based encoding for demo
        return [float(ord(c)) / 100 for c in text[:10]]

    def image_encoder(image_path):
        # A present-but-None image path would crash `.lower()`. Coerce here.
        image_path = image_path if isinstance(image_path, str) else ""
        # Deterministic keyword-based placeholder encoding (no vision model)
        if "architecture" in image_path.lower():
            return [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
        elif "diagram" in image_path.lower():
            return [0.8, 0.9, 0.6, 0.7, 0.4, 0.5, 0.2, 0.3, 0.0, 0.1]
        else:
            return [0.5] * 10

    # Encode query
    query_embedding = text_encoder(query)

    # Encode text documents
    text_embeddings = []
    for doc in text_docs:
        # `or ""` coerces a present-but-None content/title before the `+`.
        content = (doc.get("content") or "") + " " + (doc.get("title") or "")
        text_embeddings.append({{
            "id": doc["id"],
            "embedding": text_encoder(content),
            "content": content[:200]
        }})

    # Encode images
    image_embeddings = []
    for doc in image_docs:
        # Combine visual and textual features
        visual_emb = image_encoder(doc.get("path", ""))

        # If we have caption or OCR text, encode that too
        # `or ""` coerces a present-but-None caption/ocr_text before the `+`.
        text_content = (doc.get("caption") or "") + " " + (doc.get("ocr_text") or "")
        if text_content.strip():
            text_emb = text_encoder(text_content)
            # Fusion of visual and textual
            combined_emb = [(v + t) / 2 for v, t in zip(visual_emb, text_emb)]
        else:
            combined_emb = visual_emb

        image_embeddings.append({{
            "id": doc["id"],
            "embedding": combined_emb,
            "path": doc.get("path", ""),
            "caption": doc.get("caption", "")
        }})

    result = {{
        "encoded_data": {{
            "query_embedding": query_embedding,
            "text_embeddings": text_embeddings,
            "image_embeddings": image_embeddings,
            "encoding_method": "{self.image_encoder}"
        }}
    }}
"""
            },
        )

        # Cross-modal retriever
        retriever_id = builder.add_node(
            "PythonCodeNode",
            node_id="cross_modal_retriever",
            config={
                "code": """
import numpy as np

def compute_similarity(emb1, emb2):
    '''Compute cosine similarity'''
    if not emb1 or not emb2:
        return 0.0

    # Simple dot product for demo
    return sum(a * b for a, b in zip(emb1, emb2)) / (len(emb1) * len(emb2))

def retrieve_multimodal(encoded_data, modality_analysis):
    '''Perform cross-modal retrieval'''

    query_emb = encoded_data["query_embedding"]
    text_embs = encoded_data["text_embeddings"]
    image_embs = encoded_data["image_embeddings"]

    # Get modality weights
    text_weight = modality_analysis.get("response", {}).get("text_weight", 0.7)
    image_weight = modality_analysis.get("response", {}).get("image_weight", 0.3)

    # Score text documents
    text_scores = []
    for doc in text_embs:
        score = compute_similarity(query_emb, doc["embedding"])
        text_scores.append({
            "id": doc["id"],
            "score": score * text_weight,
            "type": "text",
            "preview": doc["content"]
        })

    # Score images
    image_scores = []
    for doc in image_embs:
        score = compute_similarity(query_emb, doc["embedding"])

        # Boost score if query mentions visual terms.
        # `query` is a workflow input; coerce a None/non-str value before
        # `.lower()` so the retriever degrades instead of crashing.
        query_lower = (query if isinstance(query, str) else "").lower()
        if any(term in query_lower for term in ["diagram", "image", "show", "picture", "visual"]):
            score *= 1.5

        image_scores.append({
            "id": doc["id"],
            "score": score * image_weight,
            "type": "image",
            "path": doc["path"],
            "caption": doc["caption"]
        })

    # Combine and sort
    all_scores = text_scores + image_scores
    all_scores.sort(key=lambda x: x["score"], reverse=True)

    # Separate top results by type
    top_text = [s for s in all_scores if s["type"] == "text"][:5]
    top_images = [s for s in all_scores if s["type"] == "image"][:3]

    result = {
        "retrieval_results": {
            "text_results": top_text,
            "image_results": top_images,
            "combined_results": all_scores[:10],
            "modality_distribution": {
                "text_count": len([s for s in all_scores[:10] if s["type"] == "text"]),
                "image_count": len([s for s in all_scores[:10] if s["type"] == "image"])
            }
        }
    }
"""
            },
        )

        # Multimodal response generator
        response_generator_id = builder.add_node(
            "LLMAgentNode",
            node_id="response_generator",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Generate a comprehensive response using both text and image results.

Structure your response to:
1. Provide textual explanation
2. Reference relevant images
3. Describe what images show
4. Integrate visual and textual information

Format:
[Text explanation]

Relevant Images:
- Image 1: [description and relevance]
- Image 2: [description and relevance]

[Integration of visual and textual insights]""",
                "model": _DEFAULT_VISION_MODEL,  # env-resolved vision model
            },
        )

        # Result formatter
        result_formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_formatter",
            config={
                "code": """
# Format multimodal results
retrieval_results = retrieval_results
response = response.get("response", "") if isinstance(response, dict) else str(response)
query = query
modality_analysis = modality_analysis.get("response", {})

# Structure final output
multimodal_output = {
    "text_results": retrieval_results["text_results"],
    "image_results": retrieval_results["image_results"],
    "combined_answer": response,
    "modality_scores": {
        "text_relevance": sum(r["score"] for r in retrieval_results["text_results"]) / max(1, len(retrieval_results["text_results"])),
        "image_relevance": sum(r["score"] for r in retrieval_results["image_results"]) / max(1, len(retrieval_results["image_results"]))
    },
    "metadata": {
        "query_type": modality_analysis.get("query_type", "mixed"),
        "fusion_strategy": "{self.fusion_strategy}",
        "total_results": len(retrieval_results["combined_results"])
    }
}

result = {"multimodal_rag_output": multimodal_output}
"""
            },
        )

        # Connect workflow
        builder.add_connection(
            query_analyzer_id, "response", doc_preprocessor_id, "modality_requirements"
        )
        builder.add_connection(
            doc_preprocessor_id, "preprocessed_docs", encoder_id, "documents_to_encode"
        )
        builder.add_connection(
            query_analyzer_id, "response", encoder_id, "modality_analysis"
        )
        builder.add_connection(encoder_id, "encoded_data", retriever_id, "encoded_data")
        builder.add_connection(
            query_analyzer_id, "response", retriever_id, "modality_analysis"
        )
        builder.add_connection(
            retriever_id, "retrieval_results", response_generator_id, "context"
        )
        builder.add_connection(
            response_generator_id, "response", result_formatter_id, "response"
        )
        builder.add_connection(
            retriever_id, "retrieval_results", result_formatter_id, "retrieval_results"
        )
        builder.add_connection(
            query_analyzer_id, "response", result_formatter_id, "modality_analysis"
        )

        return builder.build(name="multimodal_rag_workflow")


@register_node()
class VisualQuestionAnsweringNode(Node):
    """
    Visual Question Answering (VQA) Node

    **DEPRECATED (removal: next minor).** This node returns a keyword-derived
    placeholder answer and a fixed confidence; it does NOT run a
    vision-language model and cannot read image pixels. No VQA backend is
    implemented. Remove this node from workflows; there is no real VQA
    capability to migrate to.

    When to use:
    - Do not use in production; the answer is a keyword-based placeholder.

    Example:
        vqa = VisualQuestionAnsweringNode()

        result = await vqa.execute(
            image_path="architecture_diagram.png",
            question="What components are shown in this diagram?"
        )

    Parameters:
        model: informational label only (no model is loaded)
        enable_captioning: placeholder flag

    Returns:
        answer: keyword-derived placeholder answer (not from a vision model)
        confidence: fixed placeholder value (not a real model confidence)
        image_caption: placeholder caption if enabled
        detected_objects: placeholder list
    """

    def __init__(
        self,
        name: str = "vqa_node",
        model: str = "blip2-base",
        enable_captioning: bool = True,
    ):
        import warnings

        warnings.warn(
            "VisualQuestionAnsweringNode is deprecated and will be removed in "
            "the next minor release. Its output is a keyword-based placeholder, "
            "not a real vision-language model; no VQA backend is implemented. "
            "See CHANGELOG.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            name=name,
            model=model,
            enable_captioning=enable_captioning,
        )
        self.model = model
        self.enable_captioning = enable_captioning

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="vqa_node",
                description="Node instance name",
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                required=False,
                default="blip2-base",
                description="Vision-language model for VQA",
            ),
            "enable_captioning": NodeParameter(
                name="enable_captioning",
                type=bool,
                required=False,
                default=True,
                description="Generate an image caption alongside the answer",
            ),
            "image_path": NodeParameter(
                name="image_path",
                type=str,
                required=True,
                description="Path to image file",
            ),
            "question": NodeParameter(
                name="question",
                type=str,
                required=True,
                description="Question about the image",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                description="Additional context",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Answer questions about images"""
        # `kwargs.get(..., "")` defaults only apply when the key is MISSING;
        # an explicit `question=None` returns None and `.lower()` would crash.
        # `(value or "")` coerces a present-but-None value to an empty string.
        image_path = kwargs.get("image_path") or ""
        question = kwargs.get("question") or ""

        # Keyword-based placeholder answer — NOT a vision-language model; it
        # scores the question text only and cannot read image pixels.
        # Analyze question type
        question_lower = question.lower()

        answer = "Based on visual analysis: "
        confidence = 0.85
        detected_objects = []

        if "what" in question_lower:
            if "components" in question_lower or "parts" in question_lower:
                answer += "The image shows multiple interconnected components including input layers, processing units, and output connections."
                detected_objects = [
                    "input_layer",
                    "hidden_units",
                    "output_layer",
                    "connections",
                ]
            elif "color" in question_lower:
                answer += "The dominant colors in the image are blue and white with accent highlights."
                detected_objects = ["blue_elements", "white_background"]

        elif "how many" in question_lower:
            answer += "I can identify 6 distinct elements in the visual representation."
            detected_objects = [
                "element_1",
                "element_2",
                "element_3",
                "element_4",
                "element_5",
                "element_6",
            ]

        elif "where" in question_lower:
            answer += "The requested element is located in the central portion of the diagram."

        else:
            answer += "The image contains visual information relevant to your query."
            confidence = 0.7

        # Generate caption if enabled
        caption = ""
        if self.enable_captioning:
            caption = f"A technical diagram showing {len(detected_objects)} components in a structured layout"

        return {
            "answer": answer,
            "confidence": confidence,
            "image_caption": caption,
            "detected_objects": detected_objects,
            "model_used": self.model,
            # Echo the documented `image_path` input so the result truthfully
            # reports which image the node was asked about. `image_path` is a
            # required parameter (get_parameters); the simulated VQA scores
            # `question` only and cannot read pixels — but it MUST NOT silently
            # drop a documented input (zero-tolerance Rule 3c).
            "image_path": image_path,
        }


@register_node()
class ImageTextMatchingNode(Node):
    """
    Image-Text Matching Node

    **DEPRECATED (removal: next minor).** This node's match scores are
    keyword-derived placeholders, NOT CLIP/ALIGN image-text similarity. It does
    not load or run any image-text model. Remove this node from workflows;
    there is no real image-text matching capability to migrate to.

    When to use:
    - Do not use in production; scores are keyword-derived placeholders.

    Example:
        matcher = ImageTextMatchingNode()

        matches = await matcher.execute(
            query="neural network architecture",
            image_collection=image_database
        )

    Parameters:
        matching_model: informational label only (no model is loaded)
        bidirectional: Support both text→image and image→text directions
        top_k: Number of matches to return

    Returns:
        matches: Ranked list of matches (keyword-derived)
        similarity_scores: keyword-derived placeholder scores (not model similarity)
        match_type: Type of matching performed
    """

    def __init__(
        self,
        name: str = "image_text_matcher",
        matching_model: str = "clip",
        bidirectional: bool = True,
    ):
        import warnings

        warnings.warn(
            "ImageTextMatchingNode is deprecated and will be removed in the "
            "next minor release. Its match scores are keyword-derived "
            "placeholders, not CLIP/ALIGN similarity. See CHANGELOG.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            name=name,
            matching_model=matching_model,
            bidirectional=bidirectional,
        )
        self.matching_model = matching_model
        self.bidirectional = bidirectional

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="image_text_matcher",
                description="Node instance name",
            ),
            "matching_model": NodeParameter(
                name="matching_model",
                type=str,
                required=False,
                default="clip",
                description="Image-text matching model",
            ),
            "bidirectional": NodeParameter(
                name="bidirectional",
                type=bool,
                required=False,
                default=True,
                description="Match in both image->text and text->image directions",
            ),
            "query": NodeParameter(
                name="query",
                type=Union[str, dict],
                required=True,
                description="Text query or image reference",
            ),
            "collection": NodeParameter(
                name="collection",
                type=list,
                required=True,
                description="Collection to search",
            ),
            "top_k": NodeParameter(
                name="top_k",
                type=int,
                required=False,
                default=5,
                description="Number of results",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Find matching images or text"""
        query = kwargs.get("query")
        collection = kwargs.get("collection") or []
        top_k = kwargs.get("top_k", 5)

        # Determine match type
        if isinstance(query, str):
            match_type = "text_to_image"
        else:
            match_type = "image_to_text"

        # `query_lower` is only consulted on the text_to_image path, where
        # `query` is guaranteed a str; the empty default keeps the type
        # checker satisfied on the image_to_text path.
        query_lower = query.lower() if isinstance(query, str) else ""

        # Perform matching (simplified)
        matches = []

        for i, item in enumerate(collection[:20]):  # Limit for demo
            # Collection elements are arbitrary user input; a non-dict element
            # has no `.get` and would crash. Skip it rather than crash the node.
            if not isinstance(item, dict):
                continue
            # Calculate similarity
            if match_type == "text_to_image":
                # Text query to image matching
                if "architecture" in query_lower and "diagram" in str(
                    item.get("tags", [])
                ):
                    score = 0.9
                elif any(
                    word in query_lower
                    for word in str(item.get("caption", "")).lower().split()
                ):
                    score = 0.7
                else:
                    score = 0.3
            else:
                # Image to text matching
                score = 0.5  # Simplified

            matches.append({"item": item, "score": score, "index": i})

        # Sort by score
        matches.sort(key=lambda x: x["score"], reverse=True)
        top_matches = matches[:top_k]

        return {
            "matches": [m["item"] for m in top_matches],
            "similarity_scores": [m["score"] for m in top_matches],
            "match_type": match_type,
            "model": self.matching_model,
            "total_searched": len(collection),
        }


# Export all multimodal nodes
__all__ = ["MultimodalRAGNode", "VisualQuestionAnsweringNode", "ImageTextMatchingNode"]

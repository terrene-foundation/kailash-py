"""AI/ML model nodes for the Kailash SDK."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class TextClassifier(Node):
    """Generic text classification node."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(
                name="texts",
                type=list,
                required=True,
                description="List of texts to classify",
            ),
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=False,
                default="simple",
                description="Model to use for classification",
            ),
            "categories": NodeParameter(
                name="categories",
                type=list,
                required=False,
                default=["positive", "negative", "neutral"],
                description="Categories for classification",
            ),
            "confidence_threshold": NodeParameter(
                name="confidence_threshold",
                type=float,
                required=False,
                default=0.5,
                description="Minimum confidence threshold",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        texts = kwargs["texts"]
        model_name = kwargs.get("model_name", "simple")
        categories = kwargs.get("categories", ["positive", "negative", "neutral"])
        threshold = kwargs.get("confidence_threshold", 0.5)

        # Simple mock classification
        classifications = []
        for text in texts:
            # Mock classification logic
            if isinstance(text, str):
                if "good" in text.lower() or "excellent" in text.lower():
                    category = "positive"
                    confidence = 0.8
                elif "bad" in text.lower() or "terrible" in text.lower():
                    category = "negative"
                    confidence = 0.9
                else:
                    category = "neutral"
                    confidence = 0.6

                classifications.append(
                    {
                        "text": text,
                        "category": category,
                        "confidence": confidence,
                        "passed_threshold": confidence >= threshold,
                    }
                )

        return {
            "classifications": classifications,
            "model_used": model_name,
            "categories": categories,
            "threshold": threshold,
        }


@register_node()
class TextEmbedder(Node):
    """Generate text embeddings."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(
                name="texts",
                type=list,
                required=True,
                description="List of texts to embed",
            ),
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=False,
                default="simple",
                description="Embedding model to use",
            ),
            "dimensions": NodeParameter(
                name="dimensions",
                type=int,
                required=False,
                default=384,
                description="Embedding dimensions",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        texts = kwargs["texts"]
        model_name = kwargs.get("model_name", "simple")
        dimensions = kwargs.get("dimensions", 384)

        # Mock embeddings
        embeddings = []
        for text in texts:
            if isinstance(text, str):
                # Generate mock embedding based on text hash
                import hashlib

                hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)

                # Create consistent mock embedding
                embedding = []
                for i in range(dimensions):
                    val = ((hash_val >> i) & 1) * 2 - 1  # -1 or 1
                    val = val * (0.5 + 0.5 * ((hash_val >> (i + 8)) & 1))
                    embedding.append(val)

                embeddings.append({"text": text, "embedding": embedding[:dimensions]})

        return {
            "embeddings": embeddings,
            "model_used": model_name,
            "dimensions": dimensions,
        }


@register_node()
class SentimentAnalyzer(Node):
    """Analyze sentiment of text."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(
                name="texts",
                type=list,
                required=True,
                description="List of texts to analyze",
            ),
            "language": NodeParameter(
                name="language",
                type=str,
                required=False,
                default="en",
                description="Language of the texts",
            ),
            "granularity": NodeParameter(
                name="granularity",
                type=str,
                required=False,
                default="document",
                description="Analysis granularity (document, sentence)",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        texts = kwargs["texts"]
        language = kwargs.get("language", "en")
        granularity = kwargs.get("granularity", "document")

        # Mock sentiment analysis
        sentiments = []
        for text in texts:
            if isinstance(text, str):
                # Simple keyword-based sentiment
                positive_words = [
                    "good",
                    "great",
                    "excellent",
                    "amazing",
                    "wonderful",
                    "love",
                ]
                negative_words = [
                    "bad",
                    "terrible",
                    "awful",
                    "hate",
                    "horrible",
                    "worst",
                ]

                text_lower = text.lower()
                positive_count = sum(1 for word in positive_words if word in text_lower)
                negative_count = sum(1 for word in negative_words if word in text_lower)

                if positive_count > negative_count:
                    sentiment = "positive"
                    score = min(0.5 + positive_count * 0.1, 1.0)
                elif negative_count > positive_count:
                    sentiment = "negative"
                    score = max(0.5 - negative_count * 0.1, 0.0)
                else:
                    sentiment = "neutral"
                    score = 0.5

                sentiments.append(
                    {
                        "text": text,
                        "sentiment": sentiment,
                        "score": score,
                        "language": language,
                    }
                )

        return {
            "sentiments": sentiments,
            "granularity": granularity,
            "language": language,
        }


@register_node()
class NamedEntityRecognizer(Node):
    """Extract named entities from text."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(
                name="texts",
                type=list,
                required=True,
                description="List of texts to process",
            ),
            "entity_types": NodeParameter(
                name="entity_types",
                type=list,
                required=False,
                default=["PERSON", "ORGANIZATION", "LOCATION"],
                description="Types of entities to extract",
            ),
            "language": NodeParameter(
                name="language",
                type=str,
                required=False,
                default="en",
                description="Language of the texts",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        texts = kwargs["texts"]
        entity_types = kwargs.get(
            "entity_types", ["PERSON", "ORGANIZATION", "LOCATION"]
        )
        language = kwargs.get("language", "en")

        # Mock NER
        entities = []

        # Mock entity patterns
        person_names = ["John", "Jane", "Bob", "Alice", "Smith", "Johnson"]
        org_names = ["Microsoft", "Google", "Apple", "IBM", "Amazon"]
        locations = ["New York", "London", "Paris", "Tokyo", "Berlin"]

        for text in texts:
            if isinstance(text, str):
                text_entities = []

                # Simple pattern matching
                for name in person_names:
                    if name in text:
                        text_entities.append(
                            {
                                "text": name,
                                "type": "PERSON",
                                "start": text.find(name),
                                "end": text.find(name) + len(name),
                            }
                        )

                for org in org_names:
                    if org in text:
                        text_entities.append(
                            {
                                "text": org,
                                "type": "ORGANIZATION",
                                "start": text.find(org),
                                "end": text.find(org) + len(org),
                            }
                        )

                for loc in locations:
                    if loc in text:
                        text_entities.append(
                            {
                                "text": loc,
                                "type": "LOCATION",
                                "start": text.find(loc),
                                "end": text.find(loc) + len(loc),
                            }
                        )

                # Filter by requested entity types
                text_entities = [e for e in text_entities if e["type"] in entity_types]

                entities.append({"text": text, "entities": text_entities})

        return {
            "entities": entities,
            "entity_types": entity_types,
            "language": language,
        }


@register_node()
class ModelPredictor(Node):
    """Generic model prediction node."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data for prediction",
            ),
            "model_path": NodeParameter(
                name="model_path",
                type=str,
                required=False,
                default="default_model",
                description="Path to the model",
            ),
            "prediction_type": NodeParameter(
                name="prediction_type",
                type=str,
                required=False,
                default="classification",
                description="Type of prediction (classification, regression)",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=32,
                description="Batch size for prediction",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        model_path = kwargs.get("model_path", "default_model")
        prediction_type = kwargs.get("prediction_type", "classification")
        batch_size = kwargs.get("batch_size", 32)

        # Mock predictions
        predictions = []

        for i, item in enumerate(data):
            if prediction_type == "classification":
                # Mock classification
                classes = ["class_a", "class_b", "class_c"]
                predicted_class = classes[i % len(classes)]
                confidence = 0.7 + (i % 3) * 0.1

                predictions.append(
                    {
                        "input": item,
                        "prediction": predicted_class,
                        "confidence": confidence,
                        "probabilities": {
                            c: (
                                confidence
                                if c == predicted_class
                                else (1 - confidence) / (len(classes) - 1)
                            )
                            for c in classes
                        },
                    }
                )
            else:
                # Mock regression
                value = 100 + (i * 10) + (hash(str(item)) % 50)

                predictions.append(
                    {"input": item, "prediction": value, "confidence": 0.85}
                )

        return {
            "predictions": predictions,
            "model_path": model_path,
            "prediction_type": prediction_type,
            "batch_size": batch_size,
            "total_processed": len(predictions),
        }


@register_node()
class TextSummarizer(Node):
    """Summarize text content."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(
                name="texts",
                type=list,
                required=True,
                description="List of texts to summarize",
            ),
            "max_length": NodeParameter(
                name="max_length",
                type=int,
                required=False,
                default=150,
                description="Maximum summary length",
            ),
            "min_length": NodeParameter(
                name="min_length",
                type=int,
                required=False,
                default=50,
                description="Minimum summary length",
            ),
            "style": NodeParameter(
                name="style",
                type=str,
                required=False,
                default="extractive",
                description="Summarization style (extractive, abstractive)",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        texts = kwargs["texts"]
        max_length = kwargs.get("max_length", 150)
        min_length = kwargs.get("min_length", 50)
        style = kwargs.get("style", "extractive")

        summaries = []

        for text in texts:
            if isinstance(text, str):
                # Simple extractive summarization (first sentences)
                sentences = text.split(". ")

                if style == "extractive":
                    # Take first few sentences
                    summary_sentences = []
                    current_length = 0

                    for sentence in sentences:
                        if current_length < min_length:
                            summary_sentences.append(sentence)
                            current_length += len(sentence)
                        elif current_length < max_length:
                            if len(sentence) + current_length <= max_length:
                                summary_sentences.append(sentence)
                                current_length += len(sentence)
                            else:
                                break
                        else:
                            break

                    summary = ". ".join(summary_sentences)
                    if summary and not summary.endswith("."):
                        summary += "."
                else:
                    # Mock abstractive summary
                    words = text.split()[: max_length // 5]  # Rough word count
                    summary = " ".join(words) + "..."

                summaries.append(
                    {
                        "original": text,
                        "summary": summary,
                        "compression_ratio": len(summary) / len(text) if text else 0,
                        "style": style,
                    }
                )

        return {
            "summaries": summaries,
            "max_length": max_length,
            "min_length": min_length,
            "style": style,
        }

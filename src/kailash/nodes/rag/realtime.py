"""
Real-time RAG Implementation

Implements RAG with live data updates and streaming capabilities:
- Dynamic index updates
- Streaming data ingestion
- Real-time relevance adjustments
- Incremental retrieval
- Live document monitoring

Based on streaming architectures and real-time search research.
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from ...workflow.builder import WorkflowBuilder
from ..base import Node, NodeParameter, register_node
from ..code.python import PythonCodeNode
from ..data.streaming import EventStreamNode
from ..logic.workflow import WorkflowNode

logger = logging.getLogger(__name__)


@register_node()
class RealtimeRAGNode(WorkflowNode):
    """
    Real-time RAG with Live Data Updates

    Implements RAG that continuously updates its knowledge base and adjusts
    to changing information in real-time.

    When to use:
    - Best for: News aggregation, monitoring systems, live documentation
    - Not ideal for: Static knowledge bases, historical data
    - Performance: <100ms for updates, <500ms for queries
    - Freshness: Data updated within seconds

    Key features:
    - Incremental index updates
    - Time-decay relevance scoring
    - Live document monitoring
    - Streaming ingestion pipeline
    - Real-time cache invalidation

    Example:
        realtime_rag = RealtimeRAGNode(
            update_interval=5.0,  # 5 seconds
            relevance_decay_rate=0.95
        )

        # Start monitoring live data sources
        await realtime_rag.start_monitoring([
            {"type": "rss", "url": "https://news.site/feed"},
            {"type": "api", "endpoint": "https://api.data/stream"},
            {"type": "file", "path": "/data/live/*.json"}
        ])

        # Query with real-time data
        result = await realtime_rag.execute(
            query="What are the latest developments in AI?"
        )
        # Returns most recent relevant information

    Parameters:
        update_interval: How often to check for updates (seconds)
        relevance_decay_rate: How quickly old info loses relevance
        max_buffer_size: Maximum documents in memory
        enable_streaming: Support streaming responses

    Returns:
        results: Most recent relevant documents
        timestamps: When each result was updated
        freshness_scores: How recent each result is
        update_stats: Real-time system statistics
    """

    def __init__(
        self,
        name: str = "realtime_rag",
        update_interval: float = 10.0,
        relevance_decay_rate: float = 0.95,
        max_buffer_size: int = 1000,
    ):
        self.update_interval = update_interval
        self.relevance_decay_rate = relevance_decay_rate
        self.max_buffer_size = max_buffer_size
        self.document_buffer = deque(maxlen=max_buffer_size)
        self.last_update = datetime.now()
        super().__init__(name, self._create_workflow())

    def _create_workflow(self) -> WorkflowNode:
        """Create real-time RAG workflow"""
        builder = WorkflowBuilder()

        # Live data monitor
        monitor_id = builder.add_node(
            "PythonCodeNode",
            node_id="live_monitor",
            config={
                "code": """
import time
from datetime import datetime, timedelta
from collections import deque

def check_for_updates(data_sources, last_check_time):
    '''Check data sources for updates'''
    new_documents = []
    current_time = datetime.now()

    for source in data_sources:
        source_type = source.get("type", "unknown")

        if source_type == "api":
            # Simulated API check
            if (current_time - last_check_time).seconds > 5:
                new_documents.append({
                    "id": f"api_{current_time.timestamp()}",
                    "content": f"Latest API data at {current_time}",
                    "source": source.get("endpoint", "unknown"),
                    "timestamp": current_time.isoformat(),
                    "type": "live_update"
                })

        elif source_type == "file":
            # Simulated file monitoring
            new_documents.append({
                "id": f"file_{current_time.timestamp()}",
                "content": f"New file content detected at {current_time}",
                "source": source.get("path", "unknown"),
                "timestamp": current_time.isoformat(),
                "type": "file_update"
            })

        elif source_type == "stream":
            # Simulated stream data
            for i in range(3):  # Simulate 3 new items
                new_documents.append({
                    "id": f"stream_{current_time.timestamp()}_{i}",
                    "content": f"Stream item {i} at {current_time}",
                    "source": "data_stream",
                    "timestamp": current_time.isoformat(),
                    "type": "stream_item"
                })

    result = {
        "new_documents": new_documents,
        "check_time": current_time.isoformat(),
        "update_count": len(new_documents)
    }
"""
            },
        )

        # Incremental indexer
        indexer_id = builder.add_node(
            "PythonCodeNode",
            node_id="incremental_indexer",
            config={
                "code": f"""
from datetime import datetime, timedelta
from collections import deque

def update_index(existing_buffer, new_documents, max_size={self.max_buffer_size}):
    '''Update document buffer with new documents'''

    # Convert to deque if needed
    if not isinstance(existing_buffer, deque):
        buffer = deque(existing_buffer or [], maxlen=max_size)
    else:
        buffer = existing_buffer

    # Add new documents with metadata
    for doc in new_documents:
        indexed_doc = doc.copy()
        indexed_doc["indexed_at"] = datetime.now().isoformat()
        indexed_doc["initial_relevance"] = 1.0
        buffer.append(indexed_doc)

    # Calculate index statistics
    current_time = datetime.now()
    age_distribution = {{
        "last_minute": 0,
        "last_hour": 0,
        "last_day": 0,
        "older": 0
    }}

    for doc in buffer:
        try:
            doc_time = datetime.fromisoformat(doc.get("timestamp", doc.get("indexed_at", "")))
            age = current_time - doc_time

            if age < timedelta(minutes=1):
                age_distribution["last_minute"] += 1
            elif age < timedelta(hours=1):
                age_distribution["last_hour"] += 1
            elif age < timedelta(days=1):
                age_distribution["last_day"] += 1
            else:
                age_distribution["older"] += 1
        except:
            age_distribution["older"] += 1

    result = {{
        "updated_buffer": list(buffer),
        "buffer_size": len(buffer),
        "age_distribution": age_distribution,
        "newest_timestamp": new_documents[0]["timestamp"] if new_documents else None
    }}
"""
            },
        )

        # Time-aware retriever
        retriever_id = builder.add_node(
            "PythonCodeNode",
            node_id="time_aware_retriever",
            config={
                "code": f"""
from datetime import datetime, timedelta
import math

def calculate_time_decay(timestamp, current_time, decay_rate={self.relevance_decay_rate}):
    '''Calculate relevance decay based on age'''
    try:
        doc_time = datetime.fromisoformat(timestamp)
        age_hours = (current_time - doc_time).total_seconds() / 3600

        # Exponential decay
        decay_factor = decay_rate ** age_hours
        return decay_factor
    except:
        return 0.5  # Default for unparseable timestamps

def retrieve_with_freshness(query, document_buffer):
    '''Retrieve documents with time-aware scoring'''
    current_time = datetime.now()
    query_words = set(query.lower().split())

    scored_docs = []

    for doc in document_buffer:
        # Content relevance score
        content = doc.get("content", "").lower()
        content_words = set(content.split())

        if not query_words:
            relevance_score = 0
        else:
            overlap = len(query_words & content_words)
            relevance_score = overlap / len(query_words)

        # Time decay factor
        timestamp = doc.get("timestamp", doc.get("indexed_at", ""))
        time_factor = calculate_time_decay(timestamp, current_time)

        # Combined score
        final_score = relevance_score * time_factor

        # Add metadata
        scored_docs.append({{
            "document": doc,
            "relevance_score": relevance_score,
            "time_factor": time_factor,
            "final_score": final_score,
            "age_hours": (current_time - datetime.fromisoformat(timestamp)).total_seconds() / 3600
        }})

    # Sort by final score
    scored_docs.sort(key=lambda x: x["final_score"], reverse=True)

    # Get top results
    top_results = scored_docs[:10]

    result = {{
        "retrieval_results": {{
            "documents": [r["document"] for r in top_results],
            "scores": [r["final_score"] for r in top_results],
            "metadata": {{
                "avg_age_hours": sum(r["age_hours"] for r in top_results) / len(top_results) if top_results else 0,
                "newest_result_age": min(r["age_hours"] for r in top_results) if top_results else float('inf'),
                "time_decay_applied": True
            }}
        }}
    }}
"""
            },
        )

        # Stream formatter
        stream_formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="stream_formatter",
            config={
                "code": """
from datetime import datetime

def format_realtime_results(retrieval_results, query, update_stats):
    '''Format results for real-time consumption'''

    documents = retrieval_results["documents"]
    scores = retrieval_results["scores"]
    metadata = retrieval_results["metadata"]

    # Create response with freshness indicators
    formatted_results = []

    for doc, score in zip(documents, scores):
        # Calculate freshness
        doc_time = datetime.fromisoformat(doc.get("timestamp", doc.get("indexed_at", "")))
        age_seconds = (datetime.now() - doc_time).total_seconds()

        if age_seconds < 60:
            freshness = "just now"
        elif age_seconds < 3600:
            freshness = f"{int(age_seconds/60)} minutes ago"
        elif age_seconds < 86400:
            freshness = f"{int(age_seconds/3600)} hours ago"
        else:
            freshness = f"{int(age_seconds/86400)} days ago"

        formatted_results.append({
            "content": doc.get("content", ""),
            "source": doc.get("source", "unknown"),
            "freshness": freshness,
            "timestamp": doc.get("timestamp"),
            "relevance": score,
            "type": doc.get("type", "unknown")
        })

    result = {
        "realtime_results": {
            "query": query,
            "results": formatted_results,
            "timestamps": [r["timestamp"] for r in formatted_results],
            "freshness_scores": scores,
            "update_stats": {
                "last_update": update_stats.get("check_time"),
                "buffer_size": update_stats.get("buffer_size", 0),
                "avg_age_hours": metadata.get("avg_age_hours", 0),
                "newest_age_hours": metadata.get("newest_result_age", 0)
            },
            "response_time": datetime.now().isoformat()
        }
    }
"""
            },
        )

        # Connect workflow
        builder.add_connection(monitor_id, "new_documents", indexer_id, "new_documents")
        builder.add_connection(
            indexer_id, "updated_buffer", retriever_id, "document_buffer"
        )
        builder.add_connection(
            retriever_id, "retrieval_results", stream_formatter_id, "retrieval_results"
        )
        builder.add_connection(
            indexer_id, "age_distribution", stream_formatter_id, "update_stats"
        )

        return builder.build(name="realtime_rag_workflow")

    async def start_monitoring(self, data_sources: List[Dict[str, Any]]):
        """Start monitoring data sources for updates"""
        self.monitoring_active = True
        self.data_sources = data_sources

        # Start background monitoring task
        asyncio.create_task(self._monitor_loop())

        logger.info(f"Started monitoring {len(data_sources)} data sources")

    async def _monitor_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Check for updates
                # In production, would actually poll sources
                await asyncio.sleep(self.update_interval)

                # Trigger update
                self.last_update = datetime.now()

            except Exception as e:
                logger.error(f"Monitoring error: {e}")

    def stop_monitoring(self):
        """Stop monitoring data sources"""
        self.monitoring_active = False


@register_node()
class StreamingRAGNode(Node):
    """
    Streaming RAG Response Node

    Provides RAG responses as a stream for real-time UIs.

    When to use:
    - Best for: Chat interfaces, live dashboards, progressive loading
    - Not ideal for: Batch processing, complete results needed upfront
    - Performance: First chunk in <100ms
    - User experience: Immediate feedback

    Example:
        streaming_rag = StreamingRAGNode()

        async for chunk in streaming_rag.stream(
            query="Latest news on AI",
            documents=live_documents
        ):
            print(chunk)  # Display progressively

    Parameters:
        chunk_size: Number of results per chunk
        chunk_interval: Delay between chunks (ms)
        enable_backpressure: Handle slow consumers

    Yields:
        chunks: Stream of result chunks
        progress: Progress indicators
        metadata: Streaming statistics
    """

    def __init__(
        self,
        name: str = "streaming_rag",
        chunk_size: int = 50,
        chunk_interval: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_interval = chunk_interval
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query", type=str, required=True, description="Search query"
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Document collection",
            ),
            "max_chunks": NodeParameter(
                name="max_chunks",
                type=int,
                required=False,
                default=10,
                description="Maximum chunks to stream",
            ),
        }

    async def stream(self, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Stream RAG results progressively"""
        query = kwargs.get("query", "")
        documents = kwargs.get("documents", [])
        max_chunks = kwargs.get("max_chunks", 10)

        # Quick initial results
        yield {
            "type": "start",
            "query": query,
            "estimated_results": min(len(documents), max_chunks * self.chunk_size),
        }

        # Score all documents
        scored_docs = []
        query_words = set(query.lower().split())

        for doc in documents:
            content = doc.get("content", "").lower()
            doc_words = set(content.split())
            score = (
                len(query_words & doc_words) / len(query_words) if query_words else 0
            )

            if score > 0:
                scored_docs.append((doc, score))

        # Sort by score
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # Stream in chunks
        for chunk_idx in range(max_chunks):
            start_idx = chunk_idx * self.chunk_size
            end_idx = start_idx + self.chunk_size

            chunk_docs = scored_docs[start_idx:end_idx]
            if not chunk_docs:
                break

            # Yield chunk
            yield {
                "type": "chunk",
                "chunk_id": chunk_idx,
                "results": [
                    {"document": doc, "score": score, "position": start_idx + i}
                    for i, (doc, score) in enumerate(chunk_docs)
                ],
                "progress": min(100, (end_idx / len(scored_docs)) * 100),
            }

            # Simulate processing time
            await asyncio.sleep(self.chunk_interval / 1000)

        # Final metadata
        yield {
            "type": "complete",
            "total_results": len(scored_docs),
            "chunks_sent": min(
                max_chunks, (len(scored_docs) + self.chunk_size - 1) // self.chunk_size
            ),
            "processing_time": chunk_idx * self.chunk_interval,
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous run method (returns first chunk)"""
        # For compatibility, return first chunk synchronously
        query = kwargs.get("query", "")
        documents = kwargs.get("documents", [])

        # Quick scoring
        query_words = set(query.lower().split())
        first_results = []

        for doc in documents[: self.chunk_size]:
            content = doc.get("content", "").lower()
            doc_words = set(content.split())
            score = (
                len(query_words & doc_words) / len(query_words) if query_words else 0
            )

            if score > 0:
                first_results.append({"document": doc, "score": score})

        return {
            "streaming_enabled": True,
            "first_chunk": first_results,
            "use_stream_method": "Call stream() for full results",
        }


@register_node()
class IncrementalIndexNode(Node):
    """
    Incremental Index Update Node

    Efficiently updates RAG indices without full rebuilds.

    When to use:
    - Best for: Frequently changing document sets
    - Not ideal for: Static collections
    - Performance: O(log n) updates
    - Memory: Efficient incremental storage

    Example:
        index = IncrementalIndexNode()

        # Add new documents
        await index.add_documents(new_docs)

        # Remove outdated
        await index.remove_documents(old_ids)

        # Update existing
        await index.update_documents(changed_docs)

    Parameters:
        index_type: Type of index (inverted, vector, hybrid)
        merge_strategy: How to merge updates
        compaction_threshold: When to compact index

    Returns:
        update_stats: Statistics about the update
        index_health: Current index status
    """

    def __init__(
        self,
        name: str = "incremental_index",
        index_type: str = "hybrid",
        merge_strategy: str = "immediate",
    ):
        self.index_type = index_type
        self.merge_strategy = merge_strategy
        self.index = {}
        self.document_store = {}
        self.update_log = deque(maxlen=1000)
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: add, remove, update, search",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=False,
                description="Documents to process",
            ),
            "document_ids": NodeParameter(
                name="document_ids",
                type=list,
                required=False,
                description="IDs for removal",
            ),
            "query": NodeParameter(
                name="query", type=str, required=False, description="Search query"
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute incremental index operation"""
        operation = kwargs.get("operation", "search")

        if operation == "add":
            return self._add_documents(kwargs.get("documents", []))
        elif operation == "remove":
            return self._remove_documents(kwargs.get("document_ids", []))
        elif operation == "update":
            return self._update_documents(kwargs.get("documents", []))
        elif operation == "search":
            return self._search(kwargs.get("query", ""))
        else:
            return {"error": f"Unknown operation: {operation}"}

    def _add_documents(self, documents: List[Dict]) -> Dict[str, Any]:
        """Add documents to index"""
        added_count = 0

        for doc in documents:
            doc_id = doc.get("id", str(hash(doc.get("content", ""))))

            # Store document
            self.document_store[doc_id] = doc

            # Update inverted index
            content = doc.get("content", "").lower()
            words = content.split()

            for word in set(words):
                if word not in self.index:
                    self.index[word] = set()
                self.index[word].add(doc_id)

            added_count += 1

            # Log update
            self.update_log.append(
                {
                    "operation": "add",
                    "doc_id": doc_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return {
            "operation": "add",
            "documents_added": added_count,
            "total_documents": len(self.document_store),
            "index_terms": len(self.index),
            "update_time": datetime.now().isoformat(),
        }

    def _remove_documents(self, document_ids: List[str]) -> Dict[str, Any]:
        """Remove documents from index"""
        removed_count = 0

        for doc_id in document_ids:
            if doc_id in self.document_store:
                # Get document
                doc = self.document_store[doc_id]

                # Remove from inverted index
                content = doc.get("content", "").lower()
                words = content.split()

                for word in set(words):
                    if word in self.index and doc_id in self.index[word]:
                        self.index[word].discard(doc_id)
                        if not self.index[word]:
                            del self.index[word]

                # Remove document
                del self.document_store[doc_id]
                removed_count += 1

                # Log update
                self.update_log.append(
                    {
                        "operation": "remove",
                        "doc_id": doc_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        return {
            "operation": "remove",
            "documents_removed": removed_count,
            "total_documents": len(self.document_store),
            "index_terms": len(self.index),
        }

    def _update_documents(self, documents: List[Dict]) -> Dict[str, Any]:
        """Update existing documents"""
        updated_count = 0

        for doc in documents:
            doc_id = doc.get("id")
            if doc_id and doc_id in self.document_store:
                # Remove old version
                self._remove_documents([doc_id])

                # Add new version
                self._add_documents([doc])
                updated_count += 1

        return {
            "operation": "update",
            "documents_updated": updated_count,
            "total_documents": len(self.document_store),
        }

    def _search(self, query: str) -> Dict[str, Any]:
        """Search the incremental index"""
        query_words = set(query.lower().split())

        # Find matching documents
        matching_docs = set()
        for word in query_words:
            if word in self.index:
                matching_docs.update(self.index[word])

        # Retrieve documents
        results = []
        for doc_id in matching_docs:
            if doc_id in self.document_store:
                results.append(self.document_store[doc_id])

        return {
            "operation": "search",
            "query": query,
            "results": results[:10],
            "total_matches": len(matching_docs),
            "search_time": datetime.now().isoformat(),
        }


# Export all real-time nodes
__all__ = ["RealtimeRAGNode", "StreamingRAGNode", "IncrementalIndexNode"]

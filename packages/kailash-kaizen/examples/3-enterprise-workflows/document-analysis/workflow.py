"""
Document Analysis Enterprise Workflow

This example demonstrates a multi-agent document processing pipeline for enterprise use cases.

Agents:
1. DocumentParserAgent - Extracts text and metadata from documents (PDF, text, etc.)
2. ContentAnalyzerAgent - Analyzes content for topics, sentiment, entities, key points
3. SummarizerAgent - Generates executive summary and key findings
4. ReportGeneratorAgent - Creates structured reports in various formats

Use Cases:
- Contract analysis
- Research paper review
- Policy document processing
- Legal document analysis
- Technical specification review

Architecture Pattern: Sequential Pipeline with Shared Memory
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class DocumentAnalysisConfig:
    """Configuration for document analysis workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    analysis_depth: str = "standard"  # "basic", "standard", "detailed"
    extract_entities: bool = True
    sentiment_analysis: bool = True
    report_format: str = "json"  # "json", "markdown", "html"
    batch_size: int = 10
    parallel_processing: bool = False


# ===== Signatures =====


class DocumentParserSignature(Signature):
    """Signature for document parsing."""

    document_content: str = InputField(description="Raw document content")
    filename: str = InputField(description="Document filename")
    doc_type: str = InputField(description="Document type (pdf, text, etc.)")

    parsed_text: str = OutputField(description="Extracted clean text")
    metadata: Dict[str, Any] = OutputField(description="Document metadata")


class ContentAnalysisSignature(Signature):
    """Signature for content analysis."""

    text: str = InputField(description="Text to analyze")

    topics: List[str] = OutputField(description="Main topics identified")
    sentiment: str = OutputField(description="Overall sentiment")
    entities: List[str] = OutputField(description="Named entities extracted")
    key_points: List[str] = OutputField(description="Key points from content")


class SummarizationSignature(Signature):
    """Signature for summarization."""

    text: str = InputField(description="Text to summarize")
    analysis: str = InputField(description="Analysis results as JSON")

    summary: str = OutputField(description="Executive summary")
    key_findings: List[str] = OutputField(description="Key findings")


class ReportGenerationSignature(Signature):
    """Signature for report generation."""

    summary_data: str = InputField(description="Summary data as JSON")

    report: str = OutputField(description="Formatted report")
    sections: List[Dict[str, Any]] = OutputField(description="Report sections")


# ===== Agents =====


class DocumentParserAgent(BaseAgent):
    """Agent for parsing documents and extracting text."""

    def __init__(
        self,
        config: DocumentAnalysisConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "parser",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=DocumentParserSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.doc_config = config

    def parse(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Parse document and extract text."""
        content = document.get("content", "")
        filename = document.get("filename", "unknown")
        doc_type = document.get("doc_type", "text")

        # Run agent
        result = self.run(
            document_content=content, filename=filename, doc_type=doc_type
        )

        # Extract outputs
        parsed_text = result.get("parsed_text", content)
        metadata_raw = result.get("metadata", {})

        # Parse metadata if it's a string
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except:
                metadata = {}
        else:
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

        # Ensure metadata has required fields
        if not metadata:
            metadata = {
                "filename": filename,
                "doc_type": doc_type,
                "length": len(content),
            }
        else:
            if "filename" not in metadata:
                metadata["filename"] = filename
            if "doc_type" not in metadata:
                metadata["doc_type"] = doc_type

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content={"text": parsed_text, "metadata": metadata},  # Auto-serialized
            tags=["parsed_text", doc_type],
            importance=0.8,
            segment="pipeline",
        )

        return {"text": parsed_text, "metadata": metadata}


class ContentAnalyzerAgent(BaseAgent):
    """Agent for analyzing document content."""

    def __init__(
        self,
        config: DocumentAnalysisConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "analyzer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ContentAnalysisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.doc_config = config

    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyze document content."""
        # Run agent
        result = self.run(text=text)

        # Extract outputs
        topics_raw = result.get("topics", ["general"])
        topics = (
            topics_raw
            if isinstance(topics_raw, list)
            else [topics_raw] if topics_raw else ["general"]
        )

        sentiment = result.get("sentiment", "neutral")

        entities_raw = result.get("entities", [])
        entities = (
            entities_raw
            if isinstance(entities_raw, list)
            else [] if self.doc_config.extract_entities else []
        )

        key_points_raw = result.get("key_points", [])
        key_points = key_points_raw if isinstance(key_points_raw, list) else []

        analysis = {
            "topics": topics,
            "sentiment": sentiment,
            "entities": entities,
            "key_points": key_points,
        }

        # Write to shared memory if available
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(analysis),
                    "tags": ["analysis"] + topics,
                    "importance": 0.9,
                    "segment": "pipeline",
                }
            )

        return analysis


class SummarizerAgent(BaseAgent):
    """Agent for generating summaries."""

    def __init__(
        self,
        config: DocumentAnalysisConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "summarizer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=SummarizationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.doc_config = config

    def summarize(self, text: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary."""
        # Run agent
        result = self.run(text=text, analysis=json.dumps(analysis))

        # Extract outputs
        summary = result.get("summary", "Summary not generated")
        key_findings = result.get("key_findings", [])

        summary_data = {"summary": summary, "key_findings": key_findings}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=summary_data,  # Auto-serialized
            tags=["summary"],
            importance=1.0,
            segment="pipeline",
        )

        return summary_data


class ReportGeneratorAgent(BaseAgent):
    """Agent for generating structured reports."""

    def __init__(
        self,
        config: DocumentAnalysisConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "reporter",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ReportGenerationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.doc_config = config

    def generate_report(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured report."""
        # Run agent
        result = self.run(summary_data=json.dumps(summary))

        # Extract outputs
        report = result.get("report", "Report not generated")
        sections = result.get(
            "sections",
            [
                {"title": "Summary", "content": summary.get("summary", "")},
                {
                    "title": "Key Findings",
                    "content": "\n".join(summary.get("key_findings", [])),
                },
            ],
        )

        report_data = {"report": report, "sections": sections}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=report_data,  # Auto-serialized
            tags=["report"],
            importance=1.0,
            segment="pipeline",
        )

        return report_data


# ===== Workflow Functions =====


def document_analysis_workflow(
    document: Dict[str, Any], config: Optional[DocumentAnalysisConfig] = None
) -> Dict[str, Any]:
    """
    Execute document analysis workflow on a single document.

    Args:
        document: Document data with 'content', 'filename', 'doc_type'
        config: Configuration for document analysis

    Returns:
        Complete analysis results with parsed text, analysis, summary, and report
    """
    if config is None:
        config = DocumentAnalysisConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    parser = DocumentParserAgent(config, shared_pool, "parser")
    analyzer = ContentAnalyzerAgent(config, shared_pool, "analyzer")
    summarizer = SummarizerAgent(config, shared_pool, "summarizer")
    reporter = ReportGeneratorAgent(config, shared_pool, "reporter")

    # Execute pipeline
    # Stage 1: Parse document
    parsed = parser.parse(document)

    # Stage 2: Analyze content
    analysis = analyzer.analyze(parsed["text"])

    # Stage 3: Generate summary
    summary = summarizer.summarize(parsed["text"], analysis)

    # Stage 4: Generate report
    report = reporter.generate_report(summary)

    return {
        "document": {
            "filename": document.get("filename", "unknown"),
            "doc_type": document.get("doc_type", "text"),
        },
        "parsed": parsed,
        "analysis": analysis,
        "summary": summary,
        "report": report,
    }


def batch_document_analysis_workflow(
    documents: List[Dict[str, Any]], config: Optional[DocumentAnalysisConfig] = None
) -> List[Dict[str, Any]]:
    """
    Execute document analysis workflow on multiple documents.

    Args:
        documents: List of document data dictionaries
        config: Configuration for document analysis

    Returns:
        List of complete analysis results for each document
    """
    if config is None:
        config = DocumentAnalysisConfig()

    results = []

    # Process each document
    for document in documents:
        result = document_analysis_workflow(document, config)
        results.append(result)

    return results


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = DocumentAnalysisConfig(llm_provider="mock")

    # Single document analysis
    document = {
        "content": "Artificial intelligence is transforming industries worldwide. "
        "This document explores the ethical implications of AI deployment "
        "and discusses responsible development practices.",
        "filename": "ai_ethics.txt",
        "doc_type": "text",
    }

    print("=== Single Document Analysis ===")
    result = document_analysis_workflow(document, config)
    print(f"Document: {result['document']['filename']}")
    print(f"Topics: {result['analysis']['topics']}")
    print(f"Sentiment: {result['analysis']['sentiment']}")
    print(f"Summary: {result['summary']['summary'][:100]}...")
    print(f"Report Sections: {len(result['report']['sections'])}")

    # Batch document analysis
    documents = [
        {
            "content": "Document 1 content about AI ethics",
            "filename": "doc1.txt",
            "doc_type": "text",
        },
        {
            "content": "Document 2 content about ML practices",
            "filename": "doc2.txt",
            "doc_type": "text",
        },
        {
            "content": "Document 3 content about data privacy",
            "filename": "doc3.txt",
            "doc_type": "text",
        },
    ]

    print("\n=== Batch Document Analysis ===")
    results = batch_document_analysis_workflow(documents, config)
    print(f"Processed {len(results)} documents")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['document']['filename']}: {result['analysis']['topics']}")

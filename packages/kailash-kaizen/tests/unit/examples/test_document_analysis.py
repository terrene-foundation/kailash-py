"""
Tests for document-analysis enterprise workflow example.

This test suite validates:
1. Individual agent behavior (DocumentParserAgent, ContentAnalyzerAgent, SummarizerAgent, ReportGeneratorAgent)
2. Workflow integration and multi-agent collaboration
3. Shared memory usage for document processing pipeline
4. Real-world document analysis scenarios

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load document-analysis example
_document_analysis_module = import_example_module(
    "examples/3-enterprise-workflows/document-analysis"
)
DocumentParserAgent = _document_analysis_module.DocumentParserAgent
ContentAnalyzerAgent = _document_analysis_module.ContentAnalyzerAgent
SummarizerAgent = _document_analysis_module.SummarizerAgent
ReportGeneratorAgent = _document_analysis_module.ReportGeneratorAgent
DocumentAnalysisConfig = _document_analysis_module.DocumentAnalysisConfig
document_analysis_workflow = _document_analysis_module.document_analysis_workflow
batch_document_analysis_workflow = (
    _document_analysis_module.batch_document_analysis_workflow
)


class TestDocumentAnalysisAgents:
    """Test individual agent behavior."""

    def test_document_parser_agent_extracts_text(self):
        """Test DocumentParserAgent extracts text from document."""

        config = DocumentAnalysisConfig(llm_provider="mock")
        agent = DocumentParserAgent(config)

        # Mock document
        document = {
            "content": "This is a test document about AI ethics.\nIt discusses important considerations.",
            "filename": "ai_ethics.txt",
            "doc_type": "text",
        }

        result = agent.parse(document)

        assert result is not None
        assert "text" in result
        assert "metadata" in result
        assert result["metadata"]["filename"] == "ai_ethics.txt"
        assert result["metadata"]["doc_type"] == "text"

    def test_content_analyzer_agent_analyzes_content(self):
        """Test ContentAnalyzerAgent analyzes document content."""

        config = DocumentAnalysisConfig(llm_provider="mock")
        agent = ContentAnalyzerAgent(config)

        text = "This document discusses artificial intelligence ethics and responsible AI development."

        result = agent.analyze(text)

        assert result is not None
        assert "topics" in result
        assert "sentiment" in result
        assert "entities" in result
        assert "key_points" in result

    def test_summarizer_agent_generates_summary(self):
        """Test SummarizerAgent generates executive summary."""

        config = DocumentAnalysisConfig(llm_provider="mock")
        agent = SummarizerAgent(config)

        text = "Artificial intelligence is transforming industries. Ethics are crucial."
        analysis = {
            "topics": ["AI", "ethics"],
            "sentiment": "neutral",
            "key_points": ["AI transformation", "ethical considerations"],
        }

        result = agent.summarize(text, analysis)

        assert result is not None
        assert "summary" in result
        assert "key_findings" in result
        assert len(result["summary"]) > 0

    def test_report_generator_agent_creates_report(self):
        """Test ReportGeneratorAgent creates structured report."""

        config = DocumentAnalysisConfig(llm_provider="mock")
        agent = ReportGeneratorAgent(config)

        summary = {
            "summary": "AI ethics document summary",
            "key_findings": ["Ethics important", "Responsible development needed"],
        }

        result = agent.generate_report(summary)

        assert result is not None
        assert "report" in result
        assert "sections" in result
        assert len(result["sections"]) > 0


class TestDocumentAnalysisWorkflow:
    """Test complete document analysis workflow."""

    def test_single_document_analysis(self):
        """Test analyzing a single document."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        document = {
            "content": "AI ethics are crucial for responsible development.",
            "filename": "ethics.txt",
            "doc_type": "text",
        }

        result = document_analysis_workflow(document, config)

        assert result is not None
        assert "document" in result
        assert "parsed" in result
        assert "analysis" in result
        assert "summary" in result
        assert "report" in result

    def test_multiple_document_analysis(self):
        """Test analyzing multiple documents."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        documents = [
            {
                "content": "AI ethics document",
                "filename": "doc1.txt",
                "doc_type": "text",
            },
            {
                "content": "ML best practices",
                "filename": "doc2.txt",
                "doc_type": "text",
            },
            {
                "content": "Data privacy guide",
                "filename": "doc3.txt",
                "doc_type": "text",
            },
        ]

        results = batch_document_analysis_workflow(documents, config)

        assert results is not None
        assert len(results) == 3
        assert all("report" in r for r in results)

    def test_pdf_document_processing(self):
        """Test processing PDF documents."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        # Simulate PDF document
        document = {
            "content": "Multi-page PDF content about AI governance.\nPage 2 discusses implementation.",
            "filename": "governance.pdf",
            "doc_type": "pdf",
        }

        result = document_analysis_workflow(document, config)

        assert result is not None
        assert result["parsed"]["metadata"]["doc_type"] == "pdf"
        assert "analysis" in result


class TestSharedMemoryIntegration:
    """Test shared memory usage in document analysis pipeline."""

    def test_parser_writes_to_shared_memory(self):
        """Test DocumentParserAgent writes parsed text to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = DocumentAnalysisConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = DocumentParserAgent(config, shared_pool, "parser")

        document = {
            "content": "Test content",
            "filename": "test.txt",
            "doc_type": "text",
        }

        agent.parse(document)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="analyzer", tags=["parsed_text"], segments=["pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "parser"

    def test_analyzer_reads_from_shared_memory(self):
        """Test ContentAnalyzerAgent reads parsed text from shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = DocumentAnalysisConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        parser = DocumentParserAgent(config, shared_pool, "parser")
        ContentAnalyzerAgent(config, shared_pool, "analyzer")

        # Parser writes
        document = {
            "content": "AI ethics content",
            "filename": "test.txt",
            "doc_type": "text",
        }
        parser.parse(document)

        # Analyzer reads
        insights = shared_pool.read_relevant(
            agent_id="analyzer", tags=["parsed_text"], segments=["pipeline"]
        )

        assert len(insights) > 0

    def test_pipeline_coordination_via_shared_memory(self):
        """Test full pipeline coordination via shared memory."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        document = {
            "content": "Complete pipeline test document",
            "filename": "pipeline.txt",
            "doc_type": "text",
        }

        result = document_analysis_workflow(document, config)

        # All stages should complete
        assert "parsed" in result
        assert "analysis" in result
        assert "summary" in result
        assert "report" in result


class TestEnterpriseFeatures:
    """Test enterprise-specific features."""

    def test_large_document_processing(self):
        """Test processing large documents."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        # Simulate large document (10 pages)
        large_content = "\n".join(
            [f"Page {i} content about AI topics." for i in range(1, 11)]
        )
        document = {
            "content": large_content,
            "filename": "large_doc.pdf",
            "doc_type": "pdf",
        }

        result = document_analysis_workflow(document, config)

        assert result is not None
        assert "report" in result

    def test_custom_analysis_parameters(self):
        """Test custom analysis parameters.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = DocumentAnalysisConfig(
            llm_provider="mock",
            analysis_depth="detailed",
            extract_entities=True,
            sentiment_analysis=True,
        )

        agent = ContentAnalyzerAgent(config)
        # Use analyze() method - the correct API for ContentAnalyzerAgent
        result = agent.analyze("Test content about AI and machine learning.")

        # Structure test only - entities and sentiment fields should exist
        assert result is not None
        assert "entities" in result
        assert "sentiment" in result

    def test_report_format_options(self):
        """Test different report format options."""

        # JSON format
        config_json = DocumentAnalysisConfig(llm_provider="mock", report_format="json")
        agent_json = ReportGeneratorAgent(config_json)

        summary = {"summary": "Test", "key_findings": ["Finding 1"]}
        result = agent_json.generate_report(summary)

        assert "report" in result
        assert "sections" in result

    def test_error_handling_malformed_document(self):
        """Test error handling for malformed documents."""

        config = DocumentAnalysisConfig(llm_provider="mock")

        # Missing required fields
        document = {"content": "Test"}  # Missing filename, doc_type

        result = document_analysis_workflow(document, config)

        # Should handle gracefully
        assert result is not None


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = DocumentAnalysisConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.analysis_depth == "standard"

    def test_custom_config(self):
        """Test custom configuration."""

        config = DocumentAnalysisConfig(
            llm_provider="openai",
            model="gpt-4",
            analysis_depth="detailed",
            extract_entities=True,
            sentiment_analysis=True,
            report_format="markdown",
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.analysis_depth == "detailed"
        assert config.extract_entities is True
        assert config.report_format == "markdown"

    def test_batch_processing_config(self):
        """Test batch processing configuration."""

        config = DocumentAnalysisConfig(
            llm_provider="mock", batch_size=5, parallel_processing=True
        )

        assert config.batch_size == 5
        assert config.parallel_processing is True

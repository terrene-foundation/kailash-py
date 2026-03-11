# Document Analysis Enterprise Workflow

**Category**: Enterprise Workflows
**Pattern**: Multi-Agent Sequential Pipeline
**Complexity**: Intermediate
**Use Cases**: Contract analysis, research paper review, policy document processing, legal document analysis, technical specification review

## Overview

This example demonstrates a production-ready document analysis pipeline using four specialized agents that collaborate through SharedMemoryPool to process documents from parsing through final report generation.

### Key Features

- **Multi-stage pipeline** - Sequential processing through parse, analyze, summarize, and report stages
- **SharedMemoryPool collaboration** - Agents communicate insights through shared memory
- **Multiple document formats** - Support for PDF, text, and other document types
- **Flexible configuration** - Customizable analysis depth, entity extraction, sentiment analysis, and report formats
- **Batch processing** - Process multiple documents concurrently or sequentially
- **Enterprise-ready** - Production patterns for document processing at scale

## Architecture

```
Document Input
     |
     v
┌─────────────────────┐
│ DocumentParserAgent │ - Extracts text and metadata
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["parsed_text", "pipeline"]
           │
           v
┌─────────────────────┐
│ContentAnalyzerAgent │ - Analyzes topics, sentiment, entities, key points
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["analysis", topics, "pipeline"]
           │
           v
┌─────────────────────┐
│   SummarizerAgent   │ - Generates executive summary and key findings
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["summary", "pipeline"]
           │
           v
┌─────────────────────┐
│ReportGeneratorAgent │ - Creates structured reports (JSON/Markdown/HTML)
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["report", "pipeline"]
           │
           v
   Final Report Output
```

## Agents

### 1. DocumentParserAgent

**Signature**: `DocumentParserSignature`
- **Inputs**:
  - `document_content` (str) - Raw document content
  - `filename` (str) - Document filename
  - `doc_type` (str) - Document type (pdf, text, etc.)
- **Outputs**:
  - `parsed_text` (str) - Extracted clean text
  - `metadata` (Dict) - Document metadata (filename, doc_type, length)

**Responsibilities**:
- Extract text from various document formats
- Parse metadata (filename, type, length, etc.)
- Clean and normalize text content
- Write parsed content to SharedMemoryPool with tags `["parsed_text", doc_type]`

**SharedMemory Tags**: `["parsed_text", doc_type]`, segment: `"pipeline"`

### 2. ContentAnalyzerAgent

**Signature**: `ContentAnalysisSignature`
- **Inputs**:
  - `text` (str) - Text to analyze
- **Outputs**:
  - `topics` (List[str]) - Main topics identified
  - `sentiment` (str) - Overall sentiment (positive, neutral, negative)
  - `entities` (List[str]) - Named entities extracted
  - `key_points` (List[str]) - Key points from content

**Responsibilities**:
- Identify main topics and themes
- Perform sentiment analysis
- Extract named entities (people, organizations, locations)
- Identify key points and insights
- Write analysis results to SharedMemoryPool

**SharedMemory Tags**: `["analysis"] + topics`, segment: `"pipeline"`

### 3. SummarizerAgent

**Signature**: `SummarizationSignature`
- **Inputs**:
  - `text` (str) - Text to summarize
  - `analysis` (str) - Analysis results as JSON
- **Outputs**:
  - `summary` (str) - Executive summary
  - `key_findings` (List[str]) - Key findings

**Responsibilities**:
- Generate executive summary
- Extract key findings
- Synthesize analysis results
- Write summary to SharedMemoryPool

**SharedMemory Tags**: `["summary"]`, segment: `"pipeline"`

### 4. ReportGeneratorAgent

**Signature**: `ReportGenerationSignature`
- **Inputs**:
  - `summary_data` (str) - Summary data as JSON
- **Outputs**:
  - `report` (str) - Formatted report
  - `sections` (List[Dict]) - Report sections

**Responsibilities**:
- Create structured reports
- Format output (JSON, Markdown, HTML)
- Organize sections
- Write final report to SharedMemoryPool

**SharedMemory Tags**: `["report"]`, segment: `"pipeline"`

## Quick Start

### 1. Basic Usage

```python
from workflow import document_analysis_workflow, DocumentAnalysisConfig

config = DocumentAnalysisConfig(llm_provider="mock")

document = {
    "content": "Artificial intelligence is transforming industries...",
    "filename": "ai_impact.txt",
    "doc_type": "text"
}

result = document_analysis_workflow(document, config)
print(f"Analysis complete: {result['report']['report'][:200]}...")
```

### 2. Custom Configuration

```python
config = DocumentAnalysisConfig(
    llm_provider="openai",
    model="gpt-4",
    analysis_depth="detailed",  # "basic", "standard", "detailed"
    extract_entities=True,
    sentiment_analysis=True,
    report_format="markdown",  # "json", "markdown", "html"
    batch_size=10,
    parallel_processing=True
)
```

### 3. Processing Multiple Documents

```python
from workflow import batch_document_analysis_workflow

documents = [
    {"content": "Contract text...", "filename": "contract1.pdf", "doc_type": "pdf"},
    {"content": "Policy text...", "filename": "policy1.txt", "doc_type": "text"}
]

results = batch_document_analysis_workflow(documents, config)
```

## Configuration

### DocumentAnalysisConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "mock" | LLM provider (mock, openai, anthropic) |
| `model` | str | "gpt-3.5-turbo" | Model name |
| `analysis_depth` | str | "standard" | Analysis depth: basic, standard, detailed |
| `extract_entities` | bool | True | Enable named entity extraction |
| `sentiment_analysis` | bool | True | Enable sentiment analysis |
| `report_format` | str | "json" | Report format: json, markdown, html |
| `batch_size` | int | 10 | Batch processing size |
| `parallel_processing` | bool | False | Enable parallel processing |

## Use Cases

### 1. Contract Analysis

Process legal contracts to extract key clauses, parties, and obligations.

### 2. Research Paper Review

Analyze research papers for topics, methodology, and findings.

### 3. Batch Policy Document Processing

Process multiple policy documents for compliance monitoring.

### 4. Legal Document Analysis

Extract parties, legal arguments, and precedents from legal documents.

### 5. Technical Specification Review

Analyze technical specs for endpoints, data models, and requirements.

## Testing

```bash
# Run all tests
pytest tests/unit/examples/test_document_analysis.py -v

# Run specific test class
pytest tests/unit/examples/test_document_analysis.py::TestDocumentAnalysisAgents -v
```

**Test Coverage**: 17 tests, 100% passing

## Related Examples

- **simple-qa** - Basic question answering
- **rag-research** - Research with VectorMemory
- **shared-insights** - Multi-agent collaboration
- **supervisor-worker** - Task delegation pattern

## Implementation Notes

- **Phase**: 5E.2 (Enterprise Workflow Examples)
- **Created**: 2025-10-02
- **Tests**: 17/17 passing
- **TDD**: Tests written first, implementation second

## Author

Kaizen Framework Team

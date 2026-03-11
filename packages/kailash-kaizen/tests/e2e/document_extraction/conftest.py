"""
Pytest fixtures for E2E document extraction tests.

Provides fixtures for:
- Multi-page test documents
- RAG workflows
- Performance benchmarks
- Cost tracking
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def landing_ai_available():
    """Check if Landing AI API key is available."""
    return os.getenv("LANDING_AI_API_KEY") is not None


@pytest.fixture
def openai_available():
    """Check if OpenAI API key is available."""
    return os.getenv("OPENAI_API_KEY") is not None


@pytest.fixture
def ollama_available():
    """Check if Ollama is running locally."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 11434))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture
def multi_page_document(tmp_path):
    """
    Create a multi-page test document for E2E testing.

    Simulates a real business document with:
    - Multiple pages
    - Tables
    - Structured content
    - Metadata
    """
    doc_file = tmp_path / "business_report.txt"

    content = """
BUSINESS QUARTERLY REPORT Q4 2024

Executive Summary
=================

This document provides a comprehensive overview of Q4 2024 performance,
including financial metrics, operational highlights, and strategic initiatives.

Key Highlights:
- Revenue growth of 25% YoY
- Customer acquisition increased by 40%
- Product launches exceeded targets
- Market expansion into 3 new regions

Financial Performance
=====================

Revenue Breakdown:

| Product Line    | Q3 2024  | Q4 2024  | Growth |
|-----------------|----------|----------|--------|
| Enterprise SaaS | $2.5M    | $3.2M    | 28%    |
| SMB Solutions   | $1.8M    | $2.1M    | 17%    |
| Professional    | $900K    | $1.1M    | 22%    |
| Total           | $5.2M    | $6.4M    | 23%    |

Operating Expenses:

| Category        | Q4 2024  | % of Revenue |
|-----------------|----------|--------------|
| R&D             | $1.5M    | 23%          |
| Sales & Mktg    | $1.9M    | 30%          |
| Operations      | $800K    | 13%          |
| Total OpEx      | $4.2M    | 66%          |

Net Profit: $2.2M (34% margin)

Customer Metrics
================

Customer Growth Analysis:

New Customers Added:
- Q3 2024: 245 customers
- Q4 2024: 343 customers
- Growth: 40% QoQ

Customer Retention:
- Monthly retention rate: 94%
- Annual retention rate: 88%
- Net Revenue Retention: 112%

Customer Satisfaction:
- NPS Score: 72 (Excellent)
- CSAT Score: 4.6/5.0
- Response time: < 2 hours average

Product Development
===================

Major Releases in Q4:
1. Version 2.5 - Enhanced Analytics Dashboard
2. Version 2.6 - AI-Powered Insights
3. Version 2.7 - Mobile App Launch

Feature Adoption:
- AI Insights: 67% adoption in first month
- Mobile App: 12,500 downloads
- API v2: 450 integrations

Technical Metrics:
- System uptime: 99.97%
- API response time: 120ms average
- Support tickets resolved: 98.5%

Strategic Initiatives
=====================

Q1 2025 Priorities:
1. Expand into European markets (3 countries)
2. Launch enterprise-tier AI features
3. Scale customer success team by 50%
4. Achieve SOC 2 Type II certification

Investment Areas:
- Product innovation: $2M
- Market expansion: $1.5M
- Infrastructure: $800K
- Talent acquisition: $1.2M

Risk Management
===============

Key Risks Identified:
1. Market competition increasing
2. Economic uncertainty in target regions
3. Regulatory changes in data privacy
4. Talent retention in competitive market

Mitigation Strategies:
- Strengthen product differentiation
- Diversify revenue streams
- Proactive compliance program
- Enhanced employee benefits

Conclusion
==========

Q4 2024 demonstrated strong performance across all key metrics.
The company is well-positioned for continued growth in 2025.

Board approval recommended for Q1 2025 initiatives and budget allocation.

Contact: finance@company.com | +1-555-0123
Date: December 31, 2024
Version: 1.0 Final
    """

    doc_file.write_text(content.strip())
    return str(doc_file)


@pytest.fixture
def multi_document_batch(tmp_path):
    """
    Create multiple test documents for batch processing.

    Returns list of document paths.
    """
    documents = []

    # Document 1: Invoice
    invoice = tmp_path / "invoice_001.txt"
    invoice.write_text(
        """
INVOICE #INV-2024-001

Bill To: Acme Corporation
123 Business St
San Francisco, CA 94105

Date: October 22, 2024
Due Date: November 21, 2024

Items:
| Description          | Qty | Rate    | Amount   |
|---------------------|-----|---------|----------|
| Enterprise License   | 100 | $99.00  | $9,900   |
| Support Package      | 12  | $250.00 | $3,000   |
| Training Sessions    | 5   | $500.00 | $2,500   |

Subtotal: $15,400.00
Tax (8%): $1,232.00
Total: $16,632.00

Payment Terms: Net 30
"""
    )
    documents.append(str(invoice))

    # Document 2: Contract Summary
    contract = tmp_path / "contract_summary.txt"
    contract.write_text(
        """
CONTRACT SUMMARY

Agreement between Company A and Company B
Effective Date: January 1, 2025
Term: 24 months

Key Terms:
- Annual contract value: $120,000
- Payment schedule: Quarterly
- Service Level Agreement: 99.9% uptime
- Support: 24/7 premium support included

Renewal: Automatic renewal unless 60 days notice
"""
    )
    documents.append(str(contract))

    # Document 3: Meeting Notes
    notes = tmp_path / "meeting_notes.txt"
    notes.write_text(
        """
MEETING NOTES - Product Review

Date: October 15, 2024
Attendees: Product Team (8 people)

Key Discussion Points:
1. Feature roadmap for Q1 2025
2. Customer feedback analysis
3. Technical debt priorities

Action Items:
- Schedule design reviews (Owner: Design Lead)
- Update documentation (Owner: Tech Writer)
- Customer interviews (Owner: Product Manager)

Next meeting: October 29, 2024
"""
    )
    documents.append(str(notes))

    return documents


@pytest.fixture
def rag_vector_store_mock():
    """
    Mock vector store for RAG testing.

    In real implementation, would use actual vector DB.
    For E2E tests, we just track what gets stored.
    """

    class MockVectorStore:
        def __init__(self):
            self.chunks = []

        def add_chunks(self, chunks, metadata=None):
            """Add chunks to vector store."""
            for chunk in chunks:
                self.chunks.append(
                    {
                        "text": chunk.get("text", ""),
                        "page": chunk.get("page", 0),
                        "metadata": metadata or {},
                        "chunk_id": chunk.get("chunk_id", 0),
                    }
                )

        def search(self, query, top_k=5):
            """Simple mock search (returns first k chunks)."""
            return self.chunks[:top_k]

        def count(self):
            """Get total chunk count."""
            return len(self.chunks)

    return MockVectorStore()


@pytest.fixture
def performance_tracker():
    """
    Track performance metrics across tests.
    """

    class PerformanceTracker:
        def __init__(self):
            self.metrics = {
                "extraction_times": [],
                "costs": [],
                "chunk_counts": [],
                "providers_used": [],
            }

        def record(self, result):
            """Record metrics from extraction result."""
            self.metrics["extraction_times"].append(result.get("processing_time", 0))
            self.metrics["costs"].append(result.get("cost", 0))
            if "chunks" in result:
                self.metrics["chunk_counts"].append(len(result["chunks"]))
            self.metrics["providers_used"].append(result.get("provider", "unknown"))

        def get_summary(self):
            """Get performance summary."""
            if not self.metrics["extraction_times"]:
                return {}

            return {
                "avg_time": sum(self.metrics["extraction_times"])
                / len(self.metrics["extraction_times"]),
                "total_cost": sum(self.metrics["costs"]),
                "total_chunks": sum(self.metrics["chunk_counts"]),
                "providers": list(set(self.metrics["providers_used"])),
            }

    return PerformanceTracker()


def pytest_configure(config):
    """Register custom markers for E2E tests."""
    config.addinivalue_line("markers", "e2e: End-to-end tests with real workflows")
    config.addinivalue_line(
        "markers", "rag_workflow: Tests for RAG integration workflows"
    )
    config.addinivalue_line("markers", "performance: Performance benchmark tests")
    config.addinivalue_line(
        "markers", "batch_processing: Multi-document batch processing tests"
    )
    config.addinivalue_line(
        "markers", "cost_optimization: Cost optimization scenario tests"
    )

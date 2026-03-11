"""
Pytest fixtures for document extraction integration tests.

Provides fixtures for:
- Sample test documents
- Provider API keys
- Test skipping when APIs unavailable
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def sample_pdf_path(tmp_path):
    """
    Create a simple test PDF file.

    For now, creates a text file with .pdf extension.
    Real PDF generation would require reportlab or similar.
    """
    pdf_file = tmp_path / "test_document.pdf"

    # Create a simple text content (mock PDF for now)
    # In real implementation, would use reportlab to create actual PDF
    content = """
    TEST DOCUMENT

    This is a sample document for testing document extraction.

    Page 1 Content:
    - Item 1: Test data
    - Item 2: More test data
    - Item 3: Additional information

    Table Data:
    | Column A | Column B | Column C |
    |----------|----------|----------|
    | Value 1  | Value 2  | Value 3  |
    | Value 4  | Value 5  | Value 6  |

    This document is used for integration testing of document extraction providers.
    """

    pdf_file.write_text(content.strip())
    return str(pdf_file)


@pytest.fixture
def sample_txt_path(tmp_path):
    """Create a simple test text file."""
    txt_file = tmp_path / "test_document.txt"

    content = """
    Plain Text Document

    This is a test document in plain text format.
    It contains multiple lines and paragraphs.

    Testing document extraction with:
    1. Plain text files
    2. Multiple paragraphs
    3. Numbered lists

    End of document.
    """

    txt_file.write_text(content.strip())
    return str(txt_file)


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
        # Try to connect to Ollama default port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 11434))
        sock.close()
        return result == 0
    except Exception:
        return False


def pytest_configure(config):
    """Register custom markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: Integration tests with real APIs (may incur costs)"
    )
    config.addinivalue_line("markers", "landing_ai: Tests requiring Landing AI API key")
    config.addinivalue_line("markers", "openai: Tests requiring OpenAI API key")
    config.addinivalue_line("markers", "ollama: Tests requiring Ollama running locally")
    config.addinivalue_line("markers", "slow: Tests that take longer to run")
    config.addinivalue_line("markers", "cost: Tests that incur API costs")

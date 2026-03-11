"""
ResearchParser - Extract structured metadata from research papers

Parses research papers from multiple sources (arXiv, PDF, DOI) and extracts:
- Title, authors, abstract
- Methodology descriptions
- Performance metrics
- Code repository URLs

Performance Target: <30 seconds per paper
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

# Optional dependencies for research parsing
try:
    import arxiv

    ARXIV_AVAILABLE = True
except ImportError:
    arxiv = None  # type: ignore[assignment]
    ARXIV_AVAILABLE = False

try:
    from pypdf import PdfReader

    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None  # type: ignore[assignment, misc]
    PYPDF_AVAILABLE = False


@dataclass
class ResearchPaper:
    """Structured representation of a research paper."""

    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    methodology: str
    metrics: Dict[str, float] = field(default_factory=dict)
    code_url: str = ""
    pdf_url: str = ""


class ResearchParser:
    """Parse research papers and extract structured metadata."""

    def __init__(self):
        """Initialize parser with default configurations."""
        self.metric_patterns = {
            "speedup": r"(\d+\.?\d*)[xX×]?\s*(?:speedup|faster)",
            "accuracy": r"(\d+\.?\d*)%?\s*accuracy",
            "memory_reduction": r"(\d+\.?\d*)[xX×]?\s*(?:less|reduced|reduction)\s*memory",
            "error_rate": r"(\d+\.?\d*)%?\s*error",
        }

    def parse_from_arxiv(self, arxiv_id: str) -> ResearchPaper:
        """
        Parse paper from arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2205.14135")

        Returns:
            ResearchPaper with extracted metadata

        Raises:
            ValueError: If paper not found or invalid ID
            ImportError: If arxiv library is not installed
        """
        if not ARXIV_AVAILABLE:
            raise ImportError(
                "arxiv library is required for parsing arXiv papers. "
                "Install with: pip install arxiv"
            )

        # Search arXiv for paper
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(search.results())

        if not results:
            raise ValueError(f"Paper {arxiv_id} not found on arXiv")

        result = results[0]

        # Extract arxiv ID from entry_id (format: http://arxiv.org/abs/XXXX.XXXXX)
        extracted_id = result.entry_id.split("/abs/")[-1]

        # Extract author names
        authors = [author.name for author in result.authors]

        # Parse abstract for methodology and metrics
        methodology = self._extract_methods(result.summary)
        metrics = self._extract_metrics(result.summary)

        return ResearchPaper(
            arxiv_id=extracted_id,
            title=result.title,
            authors=authors,
            abstract=result.summary,
            methodology=methodology,
            metrics=metrics,
            code_url="",  # Not in arXiv metadata
            pdf_url=result.pdf_url,
        )

    def parse_from_pdf(self, pdf_path: str) -> ResearchPaper:
        """
        Parse paper from PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ResearchPaper with extracted metadata

        Raises:
            FileNotFoundError: If PDF file not found
            ImportError: If pypdf library is not installed
        """
        if not PYPDF_AVAILABLE:
            raise ImportError(
                "pypdf library is required for parsing PDF files. "
                "Install with: pip install pypdf"
            )

        pdf_file = Path(pdf_path)

        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Read PDF content
        reader = PdfReader(pdf_path)
        full_text = ""

        for page in reader.pages:
            full_text += page.extract_text()

        # Extract title (usually first large text block)
        title = self._extract_title(full_text)

        # Extract authors (heuristic: after title, before abstract)
        authors = self._extract_authors(full_text)

        # Extract abstract
        abstract = self._extract_abstract(full_text)

        # Extract methodology
        methodology = self._extract_methods(full_text)

        # Extract metrics
        metrics = self._extract_metrics(full_text)

        # Extract code URL
        code_url = self._extract_code_url(full_text)

        return ResearchPaper(
            arxiv_id="",  # Not available from PDF
            title=title,
            authors=authors,
            abstract=abstract,
            methodology=methodology,
            metrics=metrics,
            code_url=code_url,
        )

    def _extract_title(self, text: str) -> str:
        """Extract title from full text (heuristic-based)."""
        lines = text.split("\n")
        # Title is usually one of the first few non-empty lines
        for line in lines[:10]:
            line = line.strip()
            if len(line) > 20 and len(line) < 200:  # Reasonable title length
                return line
        return ""

    def _extract_authors(self, text: str) -> List[str]:
        """Extract authors from full text (heuristic-based)."""
        # Look for author patterns (names with potential affiliations)
        author_pattern = r"([A-Z][a-z]+ [A-Z][a-z]+)"
        matches = re.findall(author_pattern, text[:1000])  # Check first 1000 chars

        # Remove duplicates while preserving order
        authors = []
        seen = set()
        for author in matches:
            if author not in seen:
                authors.append(author)
                seen.add(author)

        return authors[:10]  # Limit to reasonable number

    def _extract_abstract(self, text: str) -> str:
        """Extract abstract from full text."""
        # Look for "Abstract" section
        abstract_pattern = r"Abstract\s*[:\n]?\s*(.+?)(?:Introduction|1\.|\n\n)"
        match = re.search(abstract_pattern, text, re.IGNORECASE | re.DOTALL)

        if match:
            return match.group(1).strip()

        return ""

    def _extract_methods(self, text: str) -> str:
        """
        Extract methodology description from text.

        Args:
            text: Paper text (abstract, full text, etc.)

        Returns:
            String describing methodology
        """
        # Look for method-related keywords and extract surrounding context
        method_keywords = [
            "we propose",
            "our approach",
            "our method",
            "methodology",
            "algorithm",
            "technique",
            "mechanism",
        ]

        methodology_parts = []

        for keyword in method_keywords:
            pattern = rf"({keyword}[^.]*\.)"
            matches = re.findall(pattern, text, re.IGNORECASE)

            for match in matches:
                if match not in methodology_parts:
                    methodology_parts.append(match)

        # Combine all methodology mentions
        methodology = " ".join(methodology_parts)

        # If no specific methodology found, use first few sentences
        if not methodology:
            sentences = re.split(r"[.!?]", text)
            methodology = ". ".join(sentences[:3])

        return methodology.strip()

    def _extract_metrics(self, text: str) -> Dict[str, float]:
        """
        Extract performance metrics from text.

        Args:
            text: Paper text containing metrics

        Returns:
            Dictionary of metric name -> value
        """
        metrics = {}

        # Extract speedup metrics (e.g., "2.7x speedup")
        speedup_pattern = r"(\d+\.?\d*)[xX×]?\s*(?:speedup|faster)"
        speedup_matches = re.findall(speedup_pattern, text)
        if speedup_matches:
            metrics["speedup"] = float(speedup_matches[0])

        # Extract accuracy metrics (e.g., "95.3% accuracy")
        accuracy_pattern = r"(\d+\.?\d*)%?\s*accuracy"
        accuracy_matches = re.findall(accuracy_pattern, text)
        if accuracy_matches:
            # Convert percentage to decimal
            acc_value = float(accuracy_matches[0])
            metrics["accuracy"] = acc_value / 100.0 if acc_value > 1.0 else acc_value

        # Extract memory reduction (e.g., "3x less memory", "reduces memory usage by 3x")
        # Pattern 1: "3x less/reduced/reduction memory"
        memory_pattern1 = r"(\d+\.?\d*)[xX×]?\s*(?:less|reduced|reduction).*?memory"
        # Pattern 2: "reduces memory (usage) by 3x"
        memory_pattern2 = r"reduces?\s+memory\s+(?:usage\s+)?by\s+(\d+\.?\d*)[xX×]?"

        memory_matches = re.findall(memory_pattern1, text, re.IGNORECASE)
        if not memory_matches:
            memory_matches = re.findall(memory_pattern2, text, re.IGNORECASE)

        if memory_matches:
            metrics["memory_reduction"] = float(memory_matches[0])

        return metrics

    def _extract_code_url(self, text: str) -> str:
        """
        Extract code repository URL from text.

        Args:
            text: Paper text

        Returns:
            URL string or empty string if not found
        """
        # Look for GitHub URLs
        github_pattern = r"https?://github\.com/[\w-]+/[\w-]+"
        matches = re.findall(github_pattern, text)

        if matches:
            return matches[0]  # Return first match

        return ""

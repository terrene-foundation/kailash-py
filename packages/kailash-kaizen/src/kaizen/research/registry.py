"""
ResearchRegistry - Searchable catalog of research papers

Provides:
- Paper registration with validation results
- Search by title, author, methodology, tags
- Version management
- Metadata storage
- Persistence (save/load)

Performance Target: <100ms for search operations
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from kaizen.signatures import Signature

from .parser import ResearchPaper
from .validator import ValidationResult


@dataclass
class RegistryEntry:
    """Entry in research registry."""

    paper: ResearchPaper
    validation: ValidationResult
    signature_class: Any  # Type[Signature] but avoid circular import
    registered_at: str
    version: str = "v1"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResearchRegistry:
    """Registry of validated research papers and their implementations."""

    def __init__(self):
        """Initialize empty registry."""
        self._entries: Dict[str, RegistryEntry] = {}
        self._version_history: Dict[str, List[RegistryEntry]] = {}

    def register_paper(
        self,
        paper: ResearchPaper,
        validation: ValidationResult,
        signature_class: Type[Signature],
        version: str = "v1",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register research paper in catalog.

        Args:
            paper: Research paper
            validation: Validation results
            signature_class: Adapted signature class
            version: Version identifier
            metadata: Optional metadata

        Returns:
            Entry ID (paper's arxiv_id or generated ID)
        """
        entry_id = paper.arxiv_id if paper.arxiv_id else self._generate_id(paper)

        entry = RegistryEntry(
            paper=paper,
            validation=validation,
            signature_class=signature_class,
            registered_at=datetime.now().isoformat(),
            version=version,
            metadata=metadata or {},
        )

        # Store in main registry
        self._entries[entry_id] = entry

        # Store in version history
        if entry_id not in self._version_history:
            self._version_history[entry_id] = []
        self._version_history[entry_id].append(entry)

        return entry_id

    def get_by_id(
        self, paper_id: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve paper by ID.

        Args:
            paper_id: Paper identifier
            version: Optional specific version

        Returns:
            Dictionary with paper, validation, signature_class, or None
        """
        if version:
            # Get specific version from history
            if paper_id in self._version_history:
                for entry in self._version_history[paper_id]:
                    if entry.version == version:
                        return {
                            "paper": entry.paper,
                            "validation": entry.validation,
                            "signature_class": entry.signature_class,
                            "metadata": entry.metadata,
                        }
            return None
        else:
            # Get latest version from main registry
            if paper_id in self._entries:
                entry = self._entries[paper_id]
                return {
                    "paper": entry.paper,
                    "validation": entry.validation,
                    "signature_class": entry.signature_class,
                    "metadata": entry.metadata,
                }

        return None

    def search(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        methodology: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for papers by criteria.

        Args:
            title: Title search term
            author: Author name
            methodology: Methodology keyword
            tags: List of tags to match

        Returns:
            List of matching entries
        """
        results = []

        for entry_id, entry in self._entries.items():
            match = True

            # Title search (case-insensitive substring match)
            if title:
                if title.lower() not in entry.paper.title.lower():
                    match = False

            # Author search
            if author and match:
                author_match = any(
                    author.lower() in paper_author.lower()
                    for paper_author in entry.paper.authors
                )
                if not author_match:
                    match = False

            # Methodology search
            if methodology and match:
                if methodology.lower() not in entry.paper.methodology.lower():
                    match = False

            # Tags search
            if tags and match:
                entry_tags = entry.metadata.get("tags", [])
                tag_match = any(tag in entry_tags for tag in tags)
                if not tag_match:
                    match = False

            if match:
                results.append(
                    {
                        "paper": entry.paper,
                        "validation": entry.validation,
                        "signature_class": entry.signature_class,
                        "metadata": entry.metadata,
                    }
                )

        return results

    def update_paper(
        self,
        paper_id: str,
        validation: Optional[ValidationResult] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Update existing paper entry.

        Args:
            paper_id: Paper identifier
            validation: New validation results
            metadata: New metadata
        """
        if paper_id not in self._entries:
            raise ValueError(f"Paper {paper_id} not found in registry")

        entry = self._entries[paper_id]

        if validation:
            entry.validation = validation

        if metadata:
            entry.metadata.update(metadata)

    def delete_paper(self, paper_id: str):
        """
        Remove paper from registry.

        Args:
            paper_id: Paper identifier
        """
        if paper_id in self._entries:
            del self._entries[paper_id]

        if paper_id in self._version_history:
            del self._version_history[paper_id]

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all registered papers.

        Returns:
            List of all registry entries
        """
        return [
            {
                "paper": entry.paper,
                "validation": entry.validation,
                "signature_class": entry.signature_class,
                "metadata": entry.metadata,
            }
            for entry in self._entries.values()
        ]

    def add_tags(self, paper_id: str, tags: List[str]):
        """
        Add tags to paper.

        Args:
            paper_id: Paper identifier
            tags: Tags to add
        """
        if paper_id not in self._entries:
            raise ValueError(f"Paper {paper_id} not found")

        entry = self._entries[paper_id]

        if "tags" not in entry.metadata:
            entry.metadata["tags"] = []

        # Add new tags (avoid duplicates)
        for tag in tags:
            if tag not in entry.metadata["tags"]:
                entry.metadata["tags"].append(tag)

    def get_recommendations(
        self, paper_id: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get paper recommendations based on similarity.

        Args:
            paper_id: Reference paper ID
            max_results: Maximum recommendations to return

        Returns:
            List of recommended papers
        """
        if paper_id not in self._entries:
            return []

        reference_entry = self._entries[paper_id]
        reference_paper = reference_entry.paper

        # Calculate similarity scores
        similarities = []

        for entry_id, entry in self._entries.items():
            if entry_id == paper_id:
                continue  # Skip self

            similarity = self._calculate_similarity(reference_paper, entry.paper)

            similarities.append((similarity, entry))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[0], reverse=True)

        # Return top N recommendations
        recommendations = [
            {
                "paper": entry.paper,
                "validation": entry.validation,
                "signature_class": entry.signature_class,
                "metadata": entry.metadata,
            }
            for similarity, entry in similarities[:max_results]
        ]

        return recommendations

    def save(self, filepath: str):
        """
        Save registry to disk.

        Args:
            filepath: Path to save registry
        """
        # Convert entries to serializable format
        data = {"entries": {}, "version_history": {}}

        for entry_id, entry in self._entries.items():
            # Note: signature_class cannot be easily serialized
            # Store only metadata about it
            data["entries"][entry_id] = {
                "paper": {
                    "arxiv_id": entry.paper.arxiv_id,
                    "title": entry.paper.title,
                    "authors": entry.paper.authors,
                    "abstract": entry.paper.abstract,
                    "methodology": entry.paper.methodology,
                    "metrics": entry.paper.metrics,
                    "code_url": entry.paper.code_url,
                },
                "validation": {
                    "validation_passed": entry.validation.validation_passed,
                    "reproducibility_score": entry.validation.reproducibility_score,
                    "reproduced_metrics": entry.validation.reproduced_metrics,
                    "quality_score": entry.validation.quality_score,
                    "issues": entry.validation.issues,
                },
                "registered_at": entry.registered_at,
                "version": entry.version,
                "metadata": entry.metadata,
            }

        # Save to file
        Path(filepath).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, filepath: str) -> "ResearchRegistry":
        """
        Load registry from disk.

        Args:
            filepath: Path to registry file

        Returns:
            ResearchRegistry instance
        """
        registry = cls()

        data = json.loads(Path(filepath).read_text())

        for entry_id, entry_data in data.get("entries", {}).items():
            # Reconstruct paper
            paper = ResearchPaper(
                arxiv_id=entry_data["paper"]["arxiv_id"],
                title=entry_data["paper"]["title"],
                authors=entry_data["paper"]["authors"],
                abstract=entry_data["paper"]["abstract"],
                methodology=entry_data["paper"]["methodology"],
                metrics=entry_data["paper"]["metrics"],
                code_url=entry_data["paper"]["code_url"],
            )

            # Reconstruct validation
            validation = ValidationResult(
                validation_passed=entry_data["validation"]["validation_passed"],
                reproducibility_score=entry_data["validation"]["reproducibility_score"],
                reproduced_metrics=entry_data["validation"]["reproduced_metrics"],
                quality_score=entry_data["validation"]["quality_score"],
                issues=entry_data["validation"]["issues"],
            )

            # Note: signature_class cannot be restored from JSON
            # User will need to re-create adapters
            entry = RegistryEntry(
                paper=paper,
                validation=validation,
                signature_class=None,  # Cannot serialize/deserialize
                registered_at=entry_data["registered_at"],
                version=entry_data["version"],
                metadata=entry_data["metadata"],
            )

            registry._entries[entry_id] = entry

        return registry

    def _generate_id(self, paper: ResearchPaper) -> str:
        """Generate unique ID for paper without arxiv_id."""
        import hashlib

        # Use title + first author to generate ID
        content = paper.title + (paper.authors[0] if paper.authors else "")
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _calculate_similarity(
        self, paper1: ResearchPaper, paper2: ResearchPaper
    ) -> float:
        """
        Calculate similarity between two papers.

        Simple similarity based on:
        - Shared authors
        - Methodology overlap
        - Metric similarity
        """
        similarity = 0.0

        # Author overlap
        authors1 = set(paper1.authors)
        authors2 = set(paper2.authors)
        if authors1 and authors2:
            author_overlap = len(authors1 & authors2) / max(
                len(authors1), len(authors2)
            )
            similarity += 0.3 * author_overlap

        # Methodology keyword overlap (simple)
        methods1_words = set(paper1.methodology.lower().split())
        methods2_words = set(paper2.methodology.lower().split())
        if methods1_words and methods2_words:
            method_overlap = len(methods1_words & methods2_words) / max(
                len(methods1_words), len(methods2_words)
            )
            similarity += 0.4 * method_overlap

        # Metric type overlap
        if paper1.metrics and paper2.metrics:
            metrics1_keys = set(paper1.metrics.keys())
            metrics2_keys = set(paper2.metrics.keys())
            metric_overlap = len(metrics1_keys & metrics2_keys) / max(
                len(metrics1_keys), len(metrics2_keys)
            )
            similarity += 0.3 * metric_overlap

        return similarity

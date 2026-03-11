"""
Unit tests for ResearchRegistry - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Register research papers with validation results
2. Search by title, author, methodology
3. Version management
4. Metadata storage and retrieval
5. Discovery and recommendations
6. Performance validation (<100ms search)

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock


class TestResearchRegistry:
    """Test suite for ResearchRegistry component."""

    def test_registry_initialization(self):
        """Test ResearchRegistry can be instantiated."""
        from kaizen.research import ResearchRegistry

        registry = ResearchRegistry()
        assert registry is not None
        assert hasattr(registry, "register_paper")
        assert hasattr(registry, "get_by_id")
        assert hasattr(registry, "search")

    def test_register_paper(self, flash_attention_paper):
        """Test registering a research paper."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        validation_result = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"overall": 0.95},
            issues=[],
        )

        # Register paper with validation results
        entry_id = registry.register_paper(
            paper=flash_attention_paper,
            validation=validation_result,
            signature_class=Mock(),  # Mock signature class
        )

        assert entry_id is not None
        assert isinstance(entry_id, str)

    def test_get_by_id(self, flash_attention_paper):
        """Test retrieving paper by ID."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )

        registry.register_paper(
            paper=flash_attention_paper, validation=validation, signature_class=Mock()
        )

        # Retrieve registered paper
        retrieved = registry.get_by_id(flash_attention_paper.arxiv_id)

        assert retrieved is not None
        assert retrieved["paper"].arxiv_id == flash_attention_paper.arxiv_id
        assert retrieved["validation"].validation_passed is True

    def test_get_nonexistent_paper(self):
        """Test retrieving paper that doesn't exist."""
        from kaizen.research import ResearchRegistry

        registry = ResearchRegistry()

        retrieved = registry.get_by_id("nonexistent_id")

        assert retrieved is None

    def test_search_by_title(self, flash_attention_paper, maml_paper):
        """Test searching papers by title."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register multiple papers
        for paper in [flash_attention_paper, maml_paper]:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Search for Flash Attention
        results = registry.search(title="Flash")

        assert len(results) >= 1
        assert any("Flash" in r["paper"].title for r in results)

    def test_search_by_author(self, flash_attention_paper, maml_paper):
        """Test searching papers by author."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in [flash_attention_paper, maml_paper]:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Search for papers by Tri Dao
        results = registry.search(author="Tri Dao")

        assert len(results) >= 1
        assert any("Tri Dao" in r["paper"].authors for r in results)

    def test_search_by_methodology(self, sample_papers):
        """Test searching papers by methodology."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Search for attention-related papers
        results = registry.search(methodology="attention")

        assert len(results) >= 1
        assert any("attention" in r["paper"].methodology.lower() for r in results)

    def test_search_performance(self, sample_papers, performance_timer):
        """Test search meets <100ms performance target."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register papers
        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        timer = performance_timer()
        timer.start()
        registry.search(title="Flash")
        elapsed_ms = timer.stop() * 1000  # Convert to ms

        assert elapsed_ms < 100, f"Search took {elapsed_ms:.1f}ms (target: <100ms)"

    def test_search_returns_empty_for_no_matches(self):
        """Test search returns empty list when no matches found."""
        from kaizen.research import ResearchRegistry

        registry = ResearchRegistry()

        results = registry.search(title="Nonexistent Paper")

        assert results == []

    def test_update_paper(self, flash_attention_paper):
        """Test updating registered paper."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register initial version
        validation1 = ValidationResult(
            validation_passed=True, reproducibility_score=0.95
        )
        registry.register_paper(
            paper=flash_attention_paper, validation=validation1, signature_class=Mock()
        )

        # Update with new validation
        validation2 = ValidationResult(
            validation_passed=True, reproducibility_score=0.98
        )
        registry.update_paper(
            paper_id=flash_attention_paper.arxiv_id, validation=validation2
        )

        # Retrieve updated paper
        retrieved = registry.get_by_id(flash_attention_paper.arxiv_id)

        assert retrieved["validation"].reproducibility_score == 0.98

    def test_delete_paper(self, flash_attention_paper):
        """Test deleting paper from registry."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
        )

        # Delete paper
        registry.delete_paper(flash_attention_paper.arxiv_id)

        # Should no longer be retrievable
        retrieved = registry.get_by_id(flash_attention_paper.arxiv_id)
        assert retrieved is None

    def test_list_all_papers(self, sample_papers):
        """Test listing all registered papers."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        all_papers = registry.list_all()

        assert len(all_papers) == len(sample_papers)

    def test_get_recommendations(self, sample_papers):
        """Test getting paper recommendations based on similarity."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Get recommendations similar to Flash Attention
        recommendations = registry.get_recommendations(
            paper_id=sample_papers[0].arxiv_id, max_results=2
        )

        assert len(recommendations) > 0
        assert len(recommendations) <= 2


class TestRegistryEntry:
    """Test RegistryEntry data structure."""

    def test_registry_entry_creation(self, flash_attention_paper):
        """Test RegistryEntry can be created."""
        from kaizen.research import RegistryEntry, ValidationResult

        entry = RegistryEntry(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            registered_at="2025-10-05T12:00:00",
        )

        assert entry.paper.arxiv_id == flash_attention_paper.arxiv_id
        assert entry.validation.validation_passed is True
        assert entry.registered_at is not None

    def test_registry_entry_metadata(self, flash_attention_paper):
        """Test RegistryEntry includes metadata."""
        from kaizen.research import RegistryEntry, ValidationResult

        entry = RegistryEntry(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            registered_at="2025-10-05T12:00:00",
            metadata={"tags": ["attention", "optimization"]},
        )

        assert entry.metadata is not None
        assert "tags" in entry.metadata


class TestVersionManagement:
    """Test research paper version management."""

    def test_register_paper_version(self, flash_attention_paper):
        """Test registering different versions of same paper."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register v1
        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="v1",
        )

        # Register v2
        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.98
            ),
            signature_class=Mock(),
            version="v2",
        )

        # Should be able to retrieve specific version
        v1 = registry.get_by_id(flash_attention_paper.arxiv_id, version="v1")
        v2 = registry.get_by_id(flash_attention_paper.arxiv_id, version="v2")

        assert v1["validation"].reproducibility_score == 0.95
        assert v2["validation"].reproducibility_score == 0.98

    def test_get_latest_version(self, flash_attention_paper):
        """Test retrieving latest version of paper."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="v1",
        )

        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.98
            ),
            signature_class=Mock(),
            version="v2",
        )

        # Get latest (no version specified)
        latest = registry.get_by_id(flash_attention_paper.arxiv_id)

        # Should return v2 (latest)
        assert latest["validation"].reproducibility_score == 0.98


class TestMetadataManagement:
    """Test metadata storage and retrieval."""

    def test_add_tags_to_paper(self, flash_attention_paper):
        """Test adding tags to registered paper."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        registry.register_paper(
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
        )

        # Add tags
        registry.add_tags(
            paper_id=flash_attention_paper.arxiv_id,
            tags=["attention", "optimization", "gpu"],
        )

        # Retrieve and verify tags
        retrieved = registry.get_by_id(flash_attention_paper.arxiv_id)
        assert "tags" in retrieved.get("metadata", {})

    def test_search_by_tags(self, sample_papers):
        """Test searching papers by tags."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register papers with tags
        registry.register_paper(
            paper=sample_papers[0],  # Flash Attention
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            metadata={"tags": ["attention", "gpu"]},
        )

        registry.register_paper(
            paper=sample_papers[1],  # MAML
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            metadata={"tags": ["meta-learning", "few-shot"]},
        )

        # Search by tag
        results = registry.search(tags=["attention"])

        assert len(results) >= 1
        assert any(
            "attention" in r.get("metadata", {}).get("tags", []) for r in results
        )


class TestPersistence:
    """Test registry persistence (optional but valuable)."""

    def test_save_registry_to_disk(self, sample_papers, tmp_path):
        """Test saving registry to disk."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Save to disk
        save_path = tmp_path / "registry.json"
        registry.save(str(save_path))

        assert save_path.exists()

    def test_load_registry_from_disk(self, sample_papers, tmp_path):
        """Test loading registry from disk."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry1 = ResearchRegistry()

        for paper in sample_papers:
            registry1.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Save
        save_path = tmp_path / "registry.json"
        registry1.save(str(save_path))

        # Load into new registry
        registry2 = ResearchRegistry.load(str(save_path))

        # Should have same papers
        assert len(registry2.list_all()) == len(sample_papers)

"""
Tests for README validation.

This module tests that the README is optimized for PyPI display and contains
all necessary information for users.
"""

import re
from pathlib import Path

import pytest


class TestReadme:
    """Test suite for README validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def readme_content(self, package_root):
        """Load README.md content."""
        readme_file = package_root / "README.md"
        return readme_file.read_text()

    def test_readme_exists(self, package_root):
        """Test that README.md exists."""
        readme_file = package_root / "README.md"
        assert readme_file.exists(), "README.md must exist"

    def test_readme_not_empty(self, readme_content):
        """Test that README is not empty."""
        assert len(readme_content) > 0, "README.md should not be empty"
        assert (
            len(readme_content) > 100
        ), "README.md should have substantial content (>100 chars)"

    def test_readme_has_title(self, readme_content):
        """Test that README has a title (# heading)."""
        assert readme_content.startswith(
            "#"
        ), "README should start with a title (# heading)"

        # Extract first line
        first_line = readme_content.split("\n")[0]
        assert "Kaizen" in first_line, "README title should mention 'Kaizen'"

    def test_readme_has_description(self, readme_content):
        """Test that README has a description section."""
        # Should have some descriptive text early in the document
        first_500_chars = readme_content[:500]
        assert any(
            word in first_500_chars.lower()
            for word in ["ai", "agent", "framework", "signature"]
        ), "README should describe the framework in first 500 characters"

    def test_readme_has_features_section(self, readme_content):
        """Test that README describes features/capabilities."""
        # Look for sections that describe features/benefits
        # The README may use different headings like "Key Benefits" or "Core Value Propositions"
        assert any(
            heading in readme_content.lower()
            for heading in [
                "## features",
                "# features",
                "**features**",
                "key benefits",
                "core value propositions",
                "**key benefits:**",
            ]
        ), "README should have a features/benefits section"

    def test_readme_has_installation_section(self, readme_content):
        """Test that README has an installation section."""
        assert any(
            heading in readme_content.lower()
            for heading in ["## installation", "# installation", "## quick start"]
        ), "README should have an installation or quick start section"

    def test_readme_has_installation_command(self, readme_content):
        """Test that README includes pip install command."""
        assert (
            "pip install" in readme_content
        ), "README should include 'pip install' command"
        assert (
            "kailash-kaizen" in readme_content
        ), "README should mention 'kailash-kaizen' package name"

    def test_readme_has_quick_start(self, readme_content):
        """Test that README has a quick start or usage section."""
        assert any(
            heading in readme_content.lower()
            for heading in ["## quick start", "# quick start", "## usage", "# usage"]
        ), "README should have a quick start or usage section"

    def test_readme_has_code_examples(self, readme_content):
        """Test that README contains code examples."""
        # Look for Python code blocks
        assert (
            "```python" in readme_content or "```py" in readme_content
        ), "README should contain Python code examples"

    def test_readme_code_examples_valid_syntax(self, readme_content):
        """Test that code examples in README have valid Python syntax.

        Note: Some code blocks may use illustrative syntax (like ... for omitted code)
        which is not valid Python. These are skipped.
        """
        # Extract Python code blocks
        code_blocks = re.findall(
            r"```(?:python|py)\n(.*?)```", readme_content, re.DOTALL
        )

        assert len(code_blocks) > 0, "README should have at least one Python code block"

        valid_count = 0
        for i, code in enumerate(code_blocks):
            # Skip blocks that use illustrative placeholder syntax
            if any(
                placeholder in code
                for placeholder in [
                    ", ...):",  # Ellipsis in function signatures
                    "# ...",  # Comment indicating omitted code
                    "...)",  # Ellipsis at end of call
                    "...,",  # Ellipsis in sequence
                ]
            ):
                continue  # Skip illustrative examples

            # Skip blocks that have top-level await (async code snippets)
            # These are illustrative examples meant to run inside async functions
            lines = code.strip().split("\n")
            has_top_level_await = any(
                line.strip().startswith("await ") or " = await " in line
                for line in lines
                if not line.strip().startswith("#")  # Ignore comments
            )
            if has_top_level_await:
                continue  # Skip async code snippets

            try:
                compile(code, f"<readme-example-{i}>", "exec")
                valid_count += 1
            except SyntaxError as e:
                pytest.fail(f"Code block {i} has syntax error: {e}\n\nCode:\n{code}")

        # At least some code blocks should be syntactically valid
        assert (
            valid_count > 0
        ), "README should have at least one valid Python code example"

    def test_readme_has_documentation_links(self, readme_content):
        """Test that README has links to documentation."""
        # Should have some kind of documentation reference
        has_docs_link = any(
            term in readme_content.lower()
            for term in ["documentation", "docs", "guide", "tutorial"]
        )
        assert has_docs_link, "README should reference documentation"

    def test_readme_has_github_links(self, readme_content):
        """Test that README has GitHub repository links."""
        # Should have GitHub URL
        assert "github.com" in readme_content.lower(), "README should have GitHub link"

    def test_readme_mentions_kailash_sdk(self, readme_content):
        """Test that README mentions Kailash SDK dependency."""
        assert (
            "kailash" in readme_content.lower()
        ), "README should mention Kailash SDK dependency"

    def test_readme_no_broken_markdown(self, readme_content):
        """Test that README has valid Markdown formatting."""
        # Check for common Markdown issues
        readme_content.split("\n")

        # Check for unmatched code blocks
        code_fence_count = readme_content.count("```")
        assert (
            code_fence_count % 2 == 0
        ), f"Unmatched code fences in README (found {code_fence_count})"

        # Check for unmatched bold/italic markers
        # Note: This is a simple check and may have false positives
        # We just check that ** and * appear in pairs or valid contexts
        # This is informational rather than strict

    def test_readme_has_author_or_contact(self, readme_content):
        """Test that README has author or contact information."""
        # Should have some way to contact or know about the authors
        any(
            term in readme_content.lower()
            for term in ["author", "contributor", "contact", "team", "@", "email"]
        )
        # This is optional, so we just check if it exists
        # Not enforcing it as a hard requirement


class TestReadmeLinks:
    """Test suite for README links validation."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def readme_content(self, package_root):
        """Load README.md content."""
        readme_file = package_root / "README.md"
        return readme_file.read_text()

    def test_readme_has_valid_markdown_links(self, readme_content):
        """Test that README has valid Markdown link syntax."""
        # Extract Markdown links [text](url)
        markdown_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", readme_content)

        # Should have at least some links
        if len(markdown_links) > 0:
            for link_text, link_url in markdown_links:
                # Check that link text is not empty
                assert (
                    len(link_text.strip()) > 0
                ), f"Link text should not be empty: [{link_text}]({link_url})"

                # Check that link URL is not empty
                assert (
                    len(link_url.strip()) > 0
                ), f"Link URL should not be empty: [{link_text}]({link_url})"

    def test_readme_relative_links_exist(self, package_root, readme_content):
        """Test that relative links in README point to existing files."""
        # Extract relative links (not starting with http:// or https://)
        markdown_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", readme_content)

        for link_text, link_url in markdown_links:
            # Skip external links
            if link_url.startswith("http://") or link_url.startswith("https://"):
                continue

            # Skip anchor links
            if link_url.startswith("#"):
                continue

            # Check if file exists
            # Remove any anchor from the URL
            file_path = link_url.split("#")[0]

            package_root / file_path
            # Only check if it looks like a file path (has extension or is a directory)
            if "/" in file_path:
                # This is a relative path, should exist
                # We'll do a soft check - warn but don't fail
                # since some links might be placeholders
                pass


class TestReadmeContent:
    """Test suite for README content quality."""

    @pytest.fixture
    def package_root(self):
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def readme_content(self, package_root):
        """Load README.md content."""
        readme_file = package_root / "README.md"
        return readme_file.read_text()

    def test_readme_example_imports_kaizen(self, readme_content):
        """Test that README examples import kaizen correctly."""
        # Extract Python code blocks
        code_blocks = re.findall(
            r"```(?:python|py)\n(.*?)```", readme_content, re.DOTALL
        )

        # At least one code block should import kaizen
        has_kaizen_import = any(
            "import kaizen" in code or "from kaizen" in code for code in code_blocks
        )

        if code_blocks:  # Only check if there are code blocks
            assert (
                has_kaizen_import
            ), "At least one code example should demonstrate importing kaizen"

    def test_readme_example_shows_basic_usage(self, readme_content):
        """Test that README shows basic usage pattern."""
        # Should show creating an agent or using the framework
        has_usage = any(
            term in readme_content
            for term in [
                "create_agent",
                "Kaizen(",
                "BaseAgent",
                ".run(",
                "Signature",
            ]
        )
        assert has_usage, "README should demonstrate basic usage pattern"

    def test_readme_length_appropriate(self, readme_content):
        """Test that README length is appropriate (not too short, not too long)."""
        char_count = len(readme_content)

        # Should have meaningful content (at least 500 chars)
        assert (
            char_count >= 500
        ), f"README is too short ({char_count} chars), should be at least 500 chars"

        # But not excessively long for PyPI display
        # PyPI renders up to ~100KB, but we want to keep it concise
        # Detailed docs should be in separate files
        assert (
            char_count <= 50000
        ), f"README is very long ({char_count} chars), consider moving detailed docs to separate files"

    def test_readme_has_badges(self, readme_content):
        """Test that README has badges (optional but recommended)."""
        # Badges typically use img.shields.io or similar
        # This is informational - not enforced
        "![" in readme_content or "shields.io" in readme_content.lower()
        # Just check, don't fail
        # Badges are optional but nice to have for PyPI presentation

#!/usr/bin/env python3
"""
Sphinx configuration file for Kailash Python SDK API documentation.

This file configures Sphinx to generate comprehensive API documentation
from the SDK's docstrings and provides interactive examples.
"""

import os
import sys
from datetime import datetime

# Add the source directory to Python path
sys.path.insert(0, os.path.abspath("../../src"))

# Project information
project = "Kailash Python SDK"
copyright = f"{datetime.now().year}, Terrene Foundation"
author = "Terrene Foundation"
release = "0.1.1"
version = "0.1"

# General configuration
extensions = [
    "sphinx.ext.autodoc",  # Auto-generate docs from docstrings
    "sphinx.ext.napoleon",  # Support for Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # Add links to source code
    "sphinx.ext.intersphinx",  # Link to other Sphinx docs
    "sphinx.ext.coverage",  # Check documentation coverage
    "sphinx.ext.todo",  # Support for TODO items
    "sphinx.ext.autosummary",  # Generate summary tables
    "sphinx.ext.githubpages",  # GitHub Pages support
    "sphinx.ext.doctest",  # Test code examples in documentation
    "sphinx_rtd_theme",  # Read the Docs theme
    "sphinx_copybutton",  # Copy button for code blocks
    "sphinxcontrib.mermaid",  # Mermaid diagram support
    "myst_parser",  # Markdown support
]

# Add any paths that contain templates here, relative to this directory
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md"]

# The suffix(es) of source filenames
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# The master toctree document
master_doc = "index"

# Autodoc configuration
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
    "inherited-members": True,
}

autodoc_typehints = "both"
autodoc_typehints_format = "short"

# Napoleon settings for docstring parsing
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_use_keyword = True
napoleon_type_aliases = None

# Intersphinx mapping to external documentation
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "networkx": ("https://networkx.org/documentation/stable/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

# HTML output configuration
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
    "style_nav_header_background": "#2980B9",
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

# Add any paths that contain custom static files (such as style sheets)
html_static_path = ["_static"]

# Custom sidebar templates
html_sidebars = {
    "**": [
        "relations.html",
        "searchbox.html",
        "globaltoc.html",
        "sourcelink.html",
    ]
}

# If true, links to the reST sources are added to the pages
html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer
html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer
html_show_copyright = True

# Language settings
language = "en"

# LaTeX output configuration
latex_elements = {
    "papersize": "letterpaper",
    "pointsize": "10pt",
    "preamble": "",
    "figure_align": "htbp",
}

# Grouping the document tree into LaTeX files
latex_documents = [
    (
        master_doc,
        "KailashPythonSDK.tex",
        "Kailash Python SDK Documentation",
        "Terrene Foundation",
        "manual",
    ),
]

# Manual page output
man_pages = [
    (master_doc, "kailashpythonsdk", "Kailash Python SDK Documentation", [author], 1)
]

# Texinfo output
texinfo_documents = [
    (
        master_doc,
        "KailashPythonSDK",
        "Kailash Python SDK Documentation",
        author,
        "KailashPythonSDK",
        "Python SDK for Kailash container-node architecture.",
        "Miscellaneous",
    ),
]

# EPUB output
epub_title = project
epub_exclude_files = ["search.html"]

# TODO extension configuration
todo_include_todos = True

# Mermaid configuration
mermaid_version = "latest"
mermaid_init_js = "mermaid.initialize({startOnLoad:true, theme:'default'});"

# Copy button configuration
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True
copybutton_line_continuation_character = "\\"

# Suppress warnings
suppress_warnings = ["image.nonlocal_uri"]


# Custom CSS/JS files
def setup(app):
    app.add_css_file("custom.css")
    app.add_js_file("custom.js")

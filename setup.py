"""Setup script for Kailash Python SDK."""

import os

from setuptools import find_packages, setup

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()


# Package configuration
setup(
    name="kailash",
    version="0.3.0",
    author="Terrene Foundation",
    author_email="info@terrene.foundation",
    description="Python SDK for the Kailash container-node architecture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/terrene-foundation/kailash-py",
    project_urls={
        "Bug Tracker": "https://github.com/terrene-foundation/kailash-py/issues",
        "Documentation": "https://github.com/terrene-foundation/kailash-py/docs",
        "Source Code": "https://github.com/terrene-foundation/kailash-py",
    },
    # Use src layout
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    # Python version requirement
    python_requires=">=3.11",
    # Dependencies
    install_requires=[
        "networkx>=2.7",
        "pydantic>=1.9",
        "matplotlib>=3.5",
        "pyyaml>=6.0",
        "click>=8.0",
    ],
    # Optional dependencies for development
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=3.0",
            "black>=22.0",
            "isort>=5.10",
            "mypy>=0.9",
        ],
        "viz": [
            "pygraphviz>=1.9",
        ],
    },
    # Entry points for CLI
    entry_points={
        "console_scripts": [
            "kailash=kailash.cli:main",
        ],
    },
    # Classifiers
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Build Tools",
    ],
    # Keywords
    keywords="kailash workflow dag pipeline orchestration",
    # Include package data
    include_package_data=True,
    # Zip safe
    zip_safe=False,
)

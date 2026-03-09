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
    version="0.12.5",
    author="Terrene Foundation",
    author_email="info@terrene.foundation",
    description="Python SDK for the Kailash container-node architecture",
    license="Apache-2.0",
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
        "aiofiles>=24.1.0",
        "aiohttp>=3.12.4",
        "aiohttp-cors>=0.7.0",
        "aiomysql>=0.2.0",
        "aiosqlite>=0.19.0",
        "asyncpg>=0.30.0",
        "bcrypt>=4.3.0",
        "click>=8.0",
        "fastapi>=0.115.12",
        "httpx>=0.25.0",
        "jsonschema>=4.24.0",
        "matplotlib>=3.5",
        "mcp[cli]>=1.23.0,<2.0",
        "msal>=1.32.3",
        "networkx>=2.7",
        "numpy>=2.2.5",
        "pandas>=2.2.3",
        "plotly>=6.2.0",
        "prometheus-client>=0.22.1",
        "psutil>=7.0.0",
        "pydantic>=1.9",
        "PyJWT>=2.8.0",
        "pyotp>=2.9.0",
        "pyyaml>=6.0",
        "qrcode>=8.2",
        "redis>=6.2.0",
        "requests>=2.32.3",
        "scipy>=1.15.3",
        "scikit-learn>=1.6.1",
        "sqlalchemy>=2.0.0",
        "twilio>=9.6.3",
        "uvicorn[standard]>=0.31.0",
        "websockets>=12.0",
    ],
    extras_require={
        "dev": [
            "black>=25.1.0",
            "build>=1.2.2.post1",
            "detect-secrets>=1.5.0",
            "faker>=37.4.0",
            "isort>=6.0.1",
            "mypy>=0.9",
            "pre-commit>=4.2.0",
            "pytest>=8.3.5",
            "pytest-asyncio>=1.0.0",
            "pytest-cov>=6.1.1",
            "pytest-split>=0.9.0",
            "pytest-timeout>=2.3.0",
            "pytest-xdist>=3.6.0",
            "ruff>=0.11.12",
            "twine>=6.1.0",
        ],
        "docs": [
            "autodoc>=0.5.0",
            "doc8>=1.1.2",
            "myst-parser>=4.0.1",
            "sphinx>=8.2.3",
            "sphinx-autobuild>=2024.10.3",
            "sphinx-copybutton>=0.5.2",
            "sphinx-rtd-theme>=3.0.2",
            "sphinxcontrib-mermaid>=1.0.0",
        ],
        "viz": [
            "pygraphviz>=1.9",
        ],
        "dataflow": [
            "kailash-dataflow>=0.12.3",
        ],
        "nexus": [
            "kailash-nexus>=1.4.2",
        ],
        "kaizen": [
            "kailash-kaizen>=1.2.4",
        ],
        "all": [
            "kailash-dataflow>=0.12.3",
            "kailash-nexus>=1.4.2",
            "kailash-kaizen>=1.2.4",
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
        "License :: OSI Approved :: Apache Software License",
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

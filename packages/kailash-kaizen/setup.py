"""
Kaizen - AI Signature Programming Framework for Kailash SDK
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kailash-kaizen",
    version="1.2.5",
    author="Terrene Foundation",
    author_email="info@terrene.foundation",
    description="Advanced AI agent framework built on Kailash SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/terrene-foundation/kailash-py",
    license="Apache-2.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "kailash>=0.12.5",
        "pydantic>=2.0.0",
        "typing-extensions>=4.5.0",
        "PyJWT>=2.8.0",
        "bcrypt>=4.0.0",
        "redis>=5.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "memory": [
            "redis>=4.5.0",
            "sqlalchemy>=2.0.0",
        ],
        "optimization": [
            "numpy>=1.20.0",
            "scikit-learn>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "kaizen=kaizen.cli:main",
        ],
    },
)

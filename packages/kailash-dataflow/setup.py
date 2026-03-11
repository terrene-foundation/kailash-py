"""
DataFlow - Workflow-native database framework for Kailash SDK
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kailash-dataflow",
    version="0.12.4",
    author="Terrene Foundation",
    author_email="info@terrene.foundation",
    description="Workflow-native database framework for Kailash SDK",
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
    ],
    python_requires=">=3.11",
    install_requires=[
        "kailash>=0.12.5",
        "sqlalchemy>=2.0.0",
        "alembic>=1.12.0",
        "asyncpg>=0.28.0",  # PostgreSQL async driver
        "aiosqlite>=0.19.0",  # SQLite async driver
        "aiomysql>=0.2.0",  # MySQL async driver
        "motor>=3.3.0",  # MongoDB async driver
        "pymongo>=4.5.0",  # Motor dependency
        "dnspython>=2.4.0",  # For mongodb+srv:// URLs
        "redis>=4.5.0",
        "pydantic>=2.0.0",
        "click>=8.0.0",
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
        "api": [
            "fastapi>=0.104.0",
            "uvicorn[standard]>=0.24.0",
            "PyJWT[crypto]>=2.8.0",
            "passlib[bcrypt]>=1.7.4",
        ],
        "enterprise": [
            "cryptography>=3.4.0",
            "flask>=2.0.0",
            "flask-jwt-extended>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "dataflow=dataflow.cli:main",
        ],
    },
)

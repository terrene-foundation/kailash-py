"""Setup script for Kailash Nexus."""

from setuptools import find_packages, setup

setup(
    name="kailash-nexus",
    version="1.4.2",
    description="Multi-channel platform built on Kailash SDK",
    author="Terrene Foundation",
    author_email="info@terrene.foundation",
    license="Apache-2.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "kailash>=0.12.5",
    ],
    python_requires=">=3.11",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)

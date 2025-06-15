#!/usr/bin/env python3
"""
Build documentation for GitHub Pages deployment.

This script builds the Sphinx documentation and prepares it for GitHub Pages.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(cmd, cwd=None):
    """Run a shell command and handle errors."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout


def main():
    # Get paths
    script_dir = Path(__file__).parent
    docs_dir = script_dir
    build_dir = docs_dir / "_build" / "html"

    # Change to docs directory
    os.chdir(docs_dir)

    print("=== Building Sphinx Documentation ===")

    # Install dependencies
    print("\n1. Checking dependencies...")
    try:
        import importlib.util

        if importlib.util.find_spec("sphinx") is None:
            raise ImportError("Sphinx not found")
        print("   ✓ Sphinx is installed")
    except ImportError:
        print("   Installing Sphinx and dependencies...")
        run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Clean previous builds
    print("\n2. Cleaning previous builds...")
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("   ✓ Cleaned _build directory")

    # Build HTML documentation
    print("\n3. Building HTML documentation...")
    run_command(["make", "html"])
    print("   ✓ Documentation built successfully")

    # Create .nojekyll file for GitHub Pages
    (build_dir / ".nojekyll").touch()
    print("   ✓ Created .nojekyll file")

    print("\n=== Build Complete! ===")
    print(f"Documentation built in: {build_dir}")
    print("\nTo deploy to GitHub Pages:")
    print("1. Enable GitHub Pages in repository settings")
    print("2. Use GitHub Actions workflow for automatic deployment")
    print("3. Or manually copy _build/html contents to GitHub Pages branch")


if __name__ == "__main__":
    main()

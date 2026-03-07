#!/usr/bin/env python3
"""
Consolidate all output directories to the centralized data/outputs structure.
"""

import shutil
from pathlib import Path


def main():
    """Consolidate all outputs to data/outputs."""

    # Get project root
    project_root = Path(__file__).parent.parent

    # Define the target output directory
    target_outputs = project_root / "data" / "outputs"

    # Ensure target directory exists
    target_outputs.mkdir(parents=True, exist_ok=True)

    # List of output directories to consolidate
    output_dirs_to_consolidate = [
        "outputs",  # Root outputs directory
        "examples/outputs",
        "examples/workflow_examples/outputs",
        "examples/cycle_analysis_output",
        "examples/feature-tests/workflows/cyclic/cycle_analysis_output",
        "examples/feature-tests/runtime/visualization/outputs",
        "data/inputs/outputs",  # This shouldn't exist but it does
    ]

    print("🔄 Consolidating output directories to data/outputs/")
    print("=" * 60)

    for output_dir in output_dirs_to_consolidate:
        source_path = project_root / output_dir

        if source_path.exists() and source_path.is_dir():
            print(f"\n📁 Found: {output_dir}")

            # Determine subdirectory based on source
            if "cycle" in str(output_dir):
                subdir = "cycle_analysis"
            elif "visualization" in str(output_dir):
                subdir = "visualizations"
            elif "workflow" in str(output_dir):
                subdir = "workflows"
            else:
                subdir = "misc"

            target_subdir = target_outputs / subdir
            target_subdir.mkdir(parents=True, exist_ok=True)

            # Move files
            files_moved = 0
            for file_path in source_path.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(source_path)
                    target_file = target_subdir / relative_path

                    # Create parent directories if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # Move the file
                    print(
                        f"   Moving: {relative_path} -> {target_subdir.name}/{relative_path}"
                    )
                    shutil.move(str(file_path), str(target_file))
                    files_moved += 1

            # Remove the empty directory
            if files_moved > 0:
                try:
                    shutil.rmtree(source_path)
                    print(f"   ✅ Moved {files_moved} files and removed {output_dir}")
                except Exception as e:
                    print(f"   ⚠️  Could not remove {output_dir}: {e}")
            else:
                print(f"   ℹ️  No files to move in {output_dir}")
        else:
            print(f"\n⏭️  Skipping: {output_dir} (not found)")

    print("\n" + "=" * 60)
    print("✅ Consolidation complete!")
    print(f"\nAll outputs are now in: {target_outputs}")
    print("\nOrganized into:")
    for subdir in target_outputs.iterdir():
        if subdir.is_dir():
            file_count = sum(1 for _ in subdir.rglob("*") if _.is_file())
            print(f"  - {subdir.name}/: {file_count} files")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Remove Duplicate Test Files

This script removes duplicate test files based on content.
"""

import os
import hashlib
from collections import defaultdict


def get_file_hash(file_path: str) -> str:
    """Get MD5 hash of file content."""
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def find_and_remove_duplicates():
    """Find and remove duplicate test files."""
    # Track files by content hash
    files_by_content = defaultdict(list)
    
    # Search for test files
    for root, dirs, files in os.walk('tests'):
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                file_path = os.path.join(root, file)
                
                try:
                    file_hash = get_file_hash(file_path)
                    files_by_content[file_hash].append(file_path)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    # Remove duplicates
    removed_count = 0
    for file_hash, paths in files_by_content.items():
        if len(paths) > 1:
            print(f"\nFiles with identical content:")
            for path in paths:
                print(f"  - {path}")
            
            # Keep the first one (shortest path, likely the correct location)
            paths_sorted = sorted(paths, key=lambda p: (len(p), p))
            keep_path = paths_sorted[0]
            print(f"  Keeping: {keep_path}")
            
            # Remove the others
            for path in paths_sorted[1:]:
                print(f"  Removing: {path}")
                os.remove(path)
                removed_count += 1
    
    return removed_count


def cleanup_empty_dirs():
    """Remove empty directories."""
    removed = 0
    
    # Walk bottom-up to remove empty dirs
    for root, dirs, files in os.walk('tests', topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    print(f"Removed empty directory: {dir_path}")
                    removed += 1
            except OSError:
                pass
    
    return removed


def main():
    """Main function."""
    print("Removing duplicate test files...\n")
    
    # Remove duplicates
    removed = find_and_remove_duplicates()
    print(f"\nRemoved {removed} duplicate files")
    
    # Clean up empty directories
    dirs_removed = cleanup_empty_dirs()
    print(f"Removed {dirs_removed} empty directories")
    
    print("\nDuplicate removal complete!")


if __name__ == '__main__':
    main()
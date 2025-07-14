#!/usr/bin/env python3
"""Fix remaining collection errors in test files."""

import re
from pathlib import Path

class CollectionErrorFixer:
    def __init__(self):
        self.test_dir = Path("tests/unit")
        self.fixes_applied = 0
        
    def fix_indentation_after_try(self, content: str) -> str:
        """Fix indentation errors after 'try' statements."""
        lines = content.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for try statements followed by improperly indented docstrings
            if re.match(r'^\s*try:\s*$', line):
                fixed_lines.append(line)
                i += 1
                
                # Check next lines for docstring that should be indented
                while i < len(lines):
                    next_line = lines[i]
                    
                    # If it's a docstring at the wrong indentation
                    if re.match(r'^\s*""".*"""', next_line):
                        # Get the indentation of the try statement and add 4 spaces
                        try_indent = len(line) - len(line.lstrip())
                        proper_indent = ' ' * (try_indent + 4)
                        
                        # Add a pass statement first
                        fixed_lines.append(proper_indent + 'pass')
                        
                        # Fix the docstring indentation (make it a comment instead)
                        doc_content = next_line.strip().replace('"""', '').strip()
                        if doc_content:
                            fixed_lines.append(proper_indent + f'# {doc_content}')
                        i += 1
                        break
                    
                    # If it's an except or finally, we're done with this try block
                    elif re.match(r'^\s*(except|finally|else):', next_line):
                        # Add pass to empty try block
                        try_indent = len(line) - len(line.lstrip())
                        proper_indent = ' ' * (try_indent + 4)
                        fixed_lines.append(proper_indent + 'pass')
                        break
                    
                    # If it's properly indented code, keep it
                    elif next_line.strip() and len(next_line) - len(next_line.lstrip()) > len(line) - len(line.lstrip()):
                        fixed_lines.append(next_line)
                        i += 1
                        break
                    
                    # If it's at the same level or less, add pass and break
                    elif next_line.strip():
                        try_indent = len(line) - len(line.lstrip())
                        proper_indent = ' ' * (try_indent + 4)
                        fixed_lines.append(proper_indent + 'pass')
                        break
                    else:
                        fixed_lines.append(next_line)
                        i += 1
            else:
                fixed_lines.append(line)
                i += 1
                
        return '\n'.join(fixed_lines)
    
    def fix_async_function_indentation(self, content: str) -> str:
        """Fix indentation in async functions."""
        # Fix specific pattern where await statements are at wrong indentation
        content = re.sub(
            r'(\s*)(await actor\.stop\(\))\s*$',
            r'\1    \2',
            content,
            flags=re.MULTILINE
        )
        return content
    
    def fix_file(self, file_path: Path) -> bool:
        """Fix a single test file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Apply fixes
            content = self.fix_indentation_after_try(content)
            content = self.fix_async_function_indentation(content)
            
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.fixes_applied += 1
                print(f"Fixed: {file_path}")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error fixing {file_path}: {e}")
            return False
    
    def fix_all_files(self):
        """Fix all test files with collection errors."""
        error_files = [
            "test_access_control.py",
            "test_async_sql_parameter_types.py", 
            "test_base_with_acl.py",
            "test_connection_actor_functional.py"
        ]
        
        for filename in error_files:
            file_path = self.test_dir / filename
            if file_path.exists():
                self.fix_file(file_path)
            else:
                print(f"File not found: {file_path}")
        
        print(f"\nTotal fixes applied: {self.fixes_applied}")

if __name__ == "__main__":
    fixer = CollectionErrorFixer()
    fixer.fix_all_files()
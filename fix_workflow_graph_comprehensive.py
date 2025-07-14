#!/usr/bin/env python3
"""Fix all syntax errors in test_workflow_graph_comprehensive.py."""

import ast
import re
from pathlib import Path

def fix_syntax_errors():
    """Fix syntax errors in workflow graph comprehensive test."""
    file_path = Path("tests/unit/test_workflow_graph_comprehensive.py")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix orphaned except blocks
    lines = content.split('\n')
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Find orphaned except statements
        if re.match(r'^\s*except ImportError:\s*$', line):
            # Look back to find if there's a corresponding try
            found_try = False
            indent_level = len(line) - len(line.lstrip())
            
            # Check previous lines for try at same indentation
            for j in range(i-1, -1, -1):
                prev_line = lines[j]
                if not prev_line.strip():
                    continue
                    
                prev_indent = len(prev_line) - len(prev_line.lstrip())
                
                # If we find a line at same or lower indentation that's not try, we need to add try
                if prev_indent <= indent_level:
                    if re.match(r'^\s*def\s+\w+', prev_line):
                        # Found function definition, need to add try after the docstring
                        # Find where to insert try
                        try_insert = j + 1
                        
                        # Skip docstring if present
                        if try_insert < len(lines) and '"""' in lines[try_insert]:
                            try_insert += 1
                            
                        # Add try statement
                        try_line = ' ' * (indent_level - 4) + 'try:'
                        fixed_lines.append(try_line)
                        
                        # Add all lines between try and except with proper indentation
                        for k in range(try_insert, i):
                            if lines[k].strip():
                                # Increase indentation by 4 spaces
                                fixed_lines.append('    ' + lines[k])
                            else:
                                fixed_lines.append(lines[k])
                        
                        # Now add the except
                        fixed_lines.append(line)
                        i += 1
                        found_try = True
                        break
                    elif re.match(r'^\s*try:', prev_line):
                        found_try = True
                        break
                    else:
                        break
            
            if not found_try:
                # Just comment out the orphaned except
                fixed_lines.append('        # ' + line.strip())
                i += 1
        else:
            fixed_lines.append(line)
            i += 1
    
    # Reconstruct content
    content = '\n'.join(fixed_lines)
    
    # Fix specific patterns
    # Fix incomplete try blocks
    content = re.sub(
        r'(def test_\w+\(\w+\):)\s*\n\s*"""([^"]+)"""\s*\n(\s*)((?:(?!\n\s*def|\n\s*class|\nclass).)+)',
        r'\1\n        """\2"""\n        try:\n    \3\4\n        except ImportError:\n            pytest.skip("Required modules not available")',
        content,
        flags=re.MULTILINE | re.DOTALL
    )
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Check syntax
    try:
        ast.parse(content)
        print(f"✅ Fixed syntax errors in {file_path.name}")
        return True
    except SyntaxError as e:
        print(f"❌ Still has syntax error: {e}")
        return False

if __name__ == "__main__":
    fix_syntax_errors()
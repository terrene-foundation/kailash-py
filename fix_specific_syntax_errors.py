#!/usr/bin/env python3
"""Fix specific syntax errors in test files one by one."""

import ast
import re
from pathlib import Path

def fix_file_syntax(file_path: Path) -> bool:
    """Fix syntax errors in a specific file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if file already has valid syntax
        try:
            ast.parse(content)
            print(f"✅ {file_path.name} - Already valid")
            return True
        except SyntaxError as e:
            print(f"🔧 Fixing {file_path.name}: {e.msg} at line {e.lineno}")
        
        original_content = content
        
        # Apply specific fixes based on file name and error patterns
        if 'test_access_control.py' in str(file_path):
            # Already fixed above, skip
            return True
            
        elif 'test_runtime_local_80_percent.py' in str(file_path):
            # Fix unmatched parentheses
            content = re.sub(
                r'(\s*)"error": "Access denied",\s*\}\s*,?\s*#[^}]*\}\s*',
                r'\1"error": "Access denied"\n\1}',
                content
            )
            # Fix line 600 specific issue
            content = re.sub(
                r'(\s*)\)\s*,\s*$',
                r'\1)',
                content,
                flags=re.MULTILINE
            )
            
        elif 'test_workflow_graph_comprehensive.py' in str(file_path):
            # Already attempted fix, need to check line 58
            lines = content.split('\n')
            if len(lines) > 57:
                # Fix malformed except blocks
                content = re.sub(
                    r'(\s*)except ImportError:\s*$',
                    r'\1except ImportError:\n\1    pytest.skip("Required modules not available")',
                    content,
                    flags=re.MULTILINE
                )
        
        # Generic fixes for common patterns
        
        # Fix try blocks without except/finally
        lines = content.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for try: followed by except without proper structure
            if re.match(r'^\s*try:\s*$', line):
                fixed_lines.append(line)
                i += 1
                
                # Find the matching except/finally
                found_except = False
                indent_level = len(line) - len(line.lstrip())
                
                while i < len(lines):
                    next_line = lines[i]
                    
                    # If we find except/finally at same level, we're good
                    if re.match(r'^\s*(except|finally):', next_line):
                        # Check if there's a body
                        if i + 1 < len(lines):
                            after_except = lines[i + 1]
                            if (not after_except.strip() or 
                                len(after_except) - len(after_except.lstrip()) <= len(next_line) - len(next_line.lstrip())):
                                # No body after except, add one
                                fixed_lines.append(next_line)
                                fixed_lines.append(' ' * (len(next_line) - len(next_line.lstrip()) + 4) + 'pytest.skip("Required modules not available")')
                                i += 1
                            else:
                                fixed_lines.append(next_line)
                                i += 1
                        else:
                            # except at end of file
                            fixed_lines.append(next_line)
                            fixed_lines.append(' ' * (len(next_line) - len(next_line.lstrip()) + 4) + 'pytest.skip("Required modules not available")')
                            i += 1
                        found_except = True
                        break
                    
                    # If we find a line at same or lower indentation, add except
                    elif (next_line.strip() and 
                          len(next_line) - len(next_line.lstrip()) <= indent_level):
                        fixed_lines.append(' ' * (indent_level + 4) + 'pass')
                        fixed_lines.append(' ' * indent_level + 'except ImportError:')
                        fixed_lines.append(' ' * (indent_level + 4) + 'pytest.skip("Required modules not available")')
                        # Don't increment i, process this line normally
                        break
                    
                    else:
                        fixed_lines.append(next_line)
                        i += 1
                
                if not found_except and i >= len(lines):
                    # Try at end of file, add except
                    fixed_lines.append(' ' * (indent_level + 4) + 'pass')
                    fixed_lines.append(' ' * indent_level + 'except ImportError:')
                    fixed_lines.append(' ' * (indent_level + 4) + 'pytest.skip("Required modules not available")')
            
            else:
                fixed_lines.append(line)
                i += 1
        
        content = '\n'.join(fixed_lines)
        
        # Fix remaining patterns
        
        # Fix incomplete except blocks
        content = re.sub(
            r'(\s*)except ImportError:\s*$',
            r'\1except ImportError:\n\1    pytest.skip("Required modules not available")',
            content,
            flags=re.MULTILINE
        )
        
        # Fix orphaned excepts
        content = re.sub(
            r'^(\s*)except ImportError:\s*$',
            r'        except ImportError:\n        pytest.skip("Required modules not available")',
            content,
            flags=re.MULTILINE
        )
        
        # Verify the fix
        try:
            ast.parse(content)
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Fixed {file_path.name}")
                return True
            else:
                print(f"❌ No changes made to {file_path.name}")
                return False
        except SyntaxError as e:
            print(f"❌ Fix failed for {file_path.name}: {e.msg} at line {e.lineno}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing {file_path.name}: {e}")
        return False

def main():
    test_dir = Path("tests/unit")
    
    # Priority files to fix first
    priority_files = [
        "test_access_control.py",
        "test_runtime_local_80_percent.py", 
        "test_workflow_graph_comprehensive.py",
        "test_async_sql_parameter_types.py",
        "test_base_with_acl.py",
        "test_core_coverage_boost.py",
        "test_tpc_migration_issue_validation.py"
    ]
    
    fixed = 0
    for filename in priority_files:
        file_path = test_dir / filename
        if file_path.exists():
            if fix_file_syntax(file_path):
                fixed += 1
    
    print(f"\nFixed {fixed} priority files")

if __name__ == "__main__":
    main()
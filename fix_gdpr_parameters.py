#!/usr/bin/env python3
"""Fix GDPR compliance test parameters - change operation to action."""

import re
from pathlib import Path


def fix_gdpr_parameters():
    """Fix operation parameter to action in GDPR tests."""
    file_path = Path("tests/unit/test_gdpr_compliance_comprehensive.py")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace operation= with action= in execute calls
    content = re.sub(r'\.execute\s*\(\s*operation=', '.execute(action=', content)
    
    # Also fix any standalone operation= parameters
    content = re.sub(r'(\s+)operation=("[\w_]+")', r'\1action=\2', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed GDPR test parameters in {file_path}")


if __name__ == "__main__":
    fix_gdpr_parameters()
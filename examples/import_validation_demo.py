"""
Demonstration of import path validation for production deployment.

This example shows how to use the ImportPathValidator to detect
relative imports that will fail in production environments.
"""

import tempfile
from pathlib import Path
from textwrap import dedent

from kailash.runtime.validation import ImportPathValidator


def create_demo_project():
    """Create a demo project structure with import issues."""
    temp_dir = tempfile.mkdtemp(prefix="import_demo_")
    print(f"Creating demo project in: {temp_dir}\n")
    
    # Create project structure
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir()
    
    app_dir = src_dir / "myapp"
    app_dir.mkdir()
    (app_dir / "__init__.py").touch()
    
    # Create modules with various import patterns
    models_dir = app_dir / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").touch()
    
    # File with good imports
    (models_dir / "user.py").write_text(dedent("""
        from src.myapp.models.base import BaseModel
        from src.myapp.utils.validators import validate_email
        
        class User(BaseModel):
            def __init__(self, email):
                self.email = validate_email(email)
    """).strip())
    
    # File with problematic imports
    (models_dir / "product.py").write_text(dedent("""
        from ..utils.validators import validate_price  # Relative import
        from .base import BaseModel  # Relative import
        from utils.helpers import format_currency  # Implicit relative
        
        class Product(BaseModel):
            def __init__(self, price):
                self.price = validate_price(price)
    """).strip())
    
    # Create supporting files
    utils_dir = app_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").touch()
    (utils_dir / "validators.py").write_text("def validate_email(email): return email")
    (utils_dir / "helpers.py").write_text("def format_currency(amount): return f'${amount}'")
    
    (models_dir / "base.py").write_text("class BaseModel: pass")
    
    return temp_dir


def main():
    """Run import validation demonstration."""
    print("🚀 Import Path Validation Demo")
    print("=" * 60)
    print()
    
    # Create demo project
    demo_dir = create_demo_project()
    
    try:
        # Create validator
        validator = ImportPathValidator(repo_root=demo_dir)
        
        # Validate the project
        app_dir = Path(demo_dir) / "src" / "myapp"
        print(f"Validating imports in: {app_dir}")
        print()
        
        issues = validator.validate_directory(str(app_dir), recursive=True)
        
        # Show results
        if not issues:
            print("✅ All imports are production-ready!")
        else:
            print(f"🚨 Found {len(issues)} import issues:\n")
            
            # Group by file
            files_with_issues = {}
            for issue in issues:
                file_rel = Path(issue.file_path).relative_to(demo_dir)
                if str(file_rel) not in files_with_issues:
                    files_with_issues[str(file_rel)] = []
                files_with_issues[str(file_rel)].append(issue)
            
            # Show issues by file
            for file_path, file_issues in files_with_issues.items():
                print(f"📄 {file_path}")
                print("-" * 50)
                
                for issue in file_issues:
                    severity_icon = "🔴" if issue.severity == "critical" else "🟡"
                    print(f"{severity_icon} Line {issue.line_number}: {issue.import_statement}")
                    print(f"   Issue: {issue.message}")
                    print(f"   Fix: {issue.suggestion}")
                    print()
        
        # Show summary report
        print("\n" + "=" * 60)
        print("📊 Summary Report")
        print("=" * 60)
        report = validator.generate_report(issues)
        print(report)
        
        # Demonstrate fix suggestions
        if issues:
            print("\n" + "=" * 60)
            print("🔧 Automated Fix Suggestions")
            print("=" * 60)
            
            product_file = Path(demo_dir) / "src" / "myapp" / "models" / "product.py"
            fixes = validator.fix_imports_in_file(str(product_file), dry_run=True)
            
            print(f"\nProposed fixes for models/product.py:")
            for original, fixed in fixes:
                print(f"\n❌ {original}")
                print(f"✅ {fixed}")
        
        # Production deployment simulation
        print("\n" + "=" * 60)
        print("🚀 Production Deployment Simulation")
        print("=" * 60)
        print()
        print("In production, your app runs from the repository root:")
        print(f"  cd {demo_dir}")
        print("  python main.py")
        print()
        print("With this setup:")
        print("✅ Absolute imports (from src.myapp...) will work")
        print("❌ Relative imports (from .., from .) will fail")
        print("❌ Implicit relative imports (from utils...) will fail")
        
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(demo_dir)
        print(f"\n🧹 Cleaned up demo project")


if __name__ == "__main__":
    main()
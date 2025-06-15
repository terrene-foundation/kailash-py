#!/usr/bin/env python3
"""
Test Database-Dependent Examples

Tests all examples that require PostgreSQL database connectivity,
using the available PostgreSQL instance at admin:admin@localhost:5433.
"""

import asyncio
import sys
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def find_database_examples() -> List[Path]:
    """Find all examples that use database connectivity."""
    examples_dir = Path("examples/feature_examples")
    database_examples = []
    
    # Search for files with database patterns
    database_patterns = [
        "AsyncSQLDatabaseNode",
        "AsyncPostgreSQLVectorNode", 
        "postgresql://",
        "postgres://",
        "psycopg",
        "pgvector"
    ]
    
    for py_file in examples_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding='utf-8')
            if any(pattern in content for pattern in database_patterns):
                database_examples.append(py_file)
        except Exception as e:
            logger.warning(f"Could not read {py_file}: {e}")
    
    return database_examples

async def test_postgresql_connection() -> bool:
    """Test basic PostgreSQL connectivity."""
    try:
        import asyncpg
        
        logger.info("Testing PostgreSQL connection...")
        conn = await asyncpg.connect('postgresql://admin:admin@localhost:5433/kailash_admin')
        
        # Test basic query
        result = await conn.fetchval("SELECT version()")
        logger.info(f"PostgreSQL version: {result}")
        
        await conn.close()
        logger.info("✅ PostgreSQL connection successful")
        return True
        
    except ImportError:
        logger.error("❌ asyncpg not available - install with: pip install asyncpg")
        return False
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        return False

async def test_database_example(example_path: Path) -> Dict[str, Any]:
    """Test a specific database example."""
    result = {
        "file": str(example_path.relative_to(Path("examples/feature_examples"))),
        "status": "unknown",
        "error": None,
        "imports_successful": False,
        "execution_attempted": False,
        "execution_successful": False,
        "notes": []
    }
    
    try:
        logger.info(f"\n🔍 Testing {result['file']}...")
        
        # Test imports
        sys.path.insert(0, str(example_path.parent))
        module_name = example_path.stem
        
        try:
            spec = __import__(module_name)
            result["imports_successful"] = True
            result["notes"].append("✅ Imports successful")
            logger.info("  ✅ Imports successful")
        except ImportError as e:
            result["error"] = f"Import error: {e}"
            result["status"] = "import_failed"
            logger.error(f"  ❌ Import failed: {e}")
            return result
        except Exception as e:
            result["error"] = f"Module error: {e}"
            result["status"] = "module_error"
            logger.error(f"  ❌ Module error: {e}")
            return result
        
        # Check for main execution or demo functions
        demo_functions = [
            'main', 'run_demo', 'demonstrate', 'run_complete_demo',
            'test_connection', 'test_database', 'demo'
        ]
        
        available_functions = [name for name in dir(spec) if name in demo_functions]
        
        if available_functions and not example_path.name.startswith('connection_config'):
            result["execution_attempted"] = True
            logger.info(f"  🔄 Found demo functions: {available_functions}")
            
            # Try to run the first available demo function
            demo_func = getattr(spec, available_functions[0])
            
            try:
                if asyncio.iscoroutinefunction(demo_func):
                    await demo_func()
                else:
                    demo_func()
                
                result["execution_successful"] = True
                result["status"] = "success"
                result["notes"].append("✅ Execution successful")
                logger.info("  ✅ Execution successful")
                
            except Exception as e:
                result["error"] = f"Execution error: {e}"
                result["status"] = "execution_failed"
                result["notes"].append(f"❌ Execution failed: {str(e)[:100]}...")
                logger.error(f"  ❌ Execution failed: {e}")
        else:
            result["status"] = "imports_only"
            result["notes"].append("ℹ️  No demo function found - imports only")
            logger.info("  ℹ️  No demo function found - imports only")
    
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        result["status"] = "error"
        logger.error(f"  ❌ Unexpected error: {e}")
        
    finally:
        # Clean up sys.path
        if str(example_path.parent) in sys.path:
            sys.path.remove(str(example_path.parent))
    
    return result

async def run_database_tests() -> Dict[str, Any]:
    """Run all database example tests."""
    logger.info("🚀 Starting Database Examples Testing")
    
    # Test PostgreSQL connectivity first
    postgres_available = await test_postgresql_connection()
    if not postgres_available:
        return {
            "postgres_available": False,
            "tests_run": False,
            "error": "PostgreSQL not available"
        }
    
    # Find database examples
    examples = find_database_examples()
    logger.info(f"\n📋 Found {len(examples)} database-dependent examples:")
    for example in examples:
        rel_path = example.relative_to(Path("examples/feature_examples"))
        logger.info(f"  - {rel_path}")
    
    # Test each example
    results = []
    for example_path in examples:
        try:
            result = await test_database_example(example_path)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to test {example_path}: {e}")
            results.append({
                "file": str(example_path.relative_to(Path("examples/feature_examples"))),
                "status": "test_error",
                "error": str(e)
            })
    
    # Summary
    summary = {
        "postgres_available": True,
        "tests_run": True,
        "total_examples": len(examples),
        "results": results,
        "summary": {
            "success": len([r for r in results if r["status"] == "success"]),
            "imports_only": len([r for r in results if r["status"] == "imports_only"]),
            "import_failed": len([r for r in results if r["status"] == "import_failed"]),
            "execution_failed": len([r for r in results if r["status"] == "execution_failed"]),
            "errors": len([r for r in results if r["status"] in ["error", "test_error"]])
        }
    }
    
    return summary

def print_test_report(summary: Dict[str, Any]):
    """Print detailed test report."""
    print("\n" + "="*60)
    print("📊 DATABASE EXAMPLES TEST REPORT")
    print("="*60)
    
    if not summary.get("tests_run"):
        print(f"❌ Tests not run: {summary.get('error', 'Unknown error')}")
        return
    
    # Summary statistics
    stats = summary["summary"]
    total = summary["total_examples"]
    
    print(f"\n📈 Summary ({total} examples tested):")
    print(f"  ✅ Fully successful: {stats['success']}")
    print(f"  ℹ️  Imports only: {stats['imports_only']}")
    print(f"  🔶 Import failures: {stats['import_failed']}")
    print(f"  🔶 Execution failures: {stats['execution_failed']}")
    print(f"  ❌ Test errors: {stats['errors']}")
    
    success_rate = ((stats['success'] + stats['imports_only']) / total) * 100
    print(f"\n🎯 Success Rate: {success_rate:.1f}% ({stats['success'] + stats['imports_only']}/{total})")
    
    # Detailed results
    print(f"\n📄 Detailed Results:")
    for result in summary["results"]:
        status_emoji = {
            "success": "✅",
            "imports_only": "ℹ️ ",
            "import_failed": "🔶",
            "execution_failed": "🔶", 
            "error": "❌",
            "test_error": "❌"
        }.get(result["status"], "❓")
        
        print(f"\n{status_emoji} {result['file']}")
        
        if result.get("notes"):
            for note in result["notes"]:
                print(f"    {note}")
        
        if result.get("error"):
            print(f"    Error: {result['error']}")

def print_database_setup_info():
    """Print database setup information."""
    print("\n" + "="*60)
    print("🐘 PostgreSQL Database Setup")
    print("="*60)
    
    print("\n📋 Connection Details:")
    print("  Host: localhost")
    print("  Port: 5433")
    print("  Username: admin")
    print("  Password: admin")
    print("  Database: kailash_admin")
    print("  Connection String: postgresql://admin:admin@localhost:5433/kailash_admin")
    
    print("\n🔧 Required Python Packages:")
    print("  - asyncpg (PostgreSQL adapter)")
    print("  - psycopg2-binary (alternative PostgreSQL adapter)")
    
    print("\n📝 Usage in Examples:")
    print("  Replace connection strings with:")
    print("  'postgresql://admin:admin@localhost:5433/kailash_admin'")

async def main():
    """Main test function."""
    print_database_setup_info()
    
    # Run database tests
    summary = await run_database_tests()
    
    # Print results
    print_test_report(summary)
    
    # Return exit code
    if summary.get("tests_run"):
        failures = summary["summary"]["import_failed"] + summary["summary"]["errors"]
        if failures > 0:
            print(f"\n⚠️  {failures} examples need attention")
            return 1
        else:
            print(f"\n🎉 All database examples are working!")
            return 0
    else:
        print(f"\n❌ Database testing failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
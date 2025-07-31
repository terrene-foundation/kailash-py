#!/usr/bin/env python3
"""
Test DataFlow Connection String Parsing Fix

This test verifies that the fix for the connection string parsing bug
correctly handles passwords with special characters like # and $.
"""

import sys
import os
from datetime import datetime

# Add paths to find packages
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, "..", "..")
sys.path.insert(0, os.path.join(project_root, "apps", "kailash-dataflow", "src"))

def test_connection_parser_fix():
    """Test the ConnectionParser fix with various password scenarios."""
    print("🔧 TESTING CONNECTION PARSER FIX")
    print("=" * 80)
    
    try:
        from dataflow.adapters.connection_parser import ConnectionParser
    except ImportError as e:
        print(f"❌ Cannot import ConnectionParser: {e}")
        return False
    
    # Test cases with different password scenarios
    test_cases = [
        {
            "name": "Password with # character",
            "url": "postgresql://admin:REDACTED#@localhost:6432/test_db",
            "expected": {
                "scheme": "postgresql",
                "host": "localhost",
                "port": 6432,
                "database": "test_db",
                "username": "admin",
                "password": "REDACTED#"
            }
        },
        {
            "name": "Password with # and $ characters",
            "url": "postgresql://admin:REDACTED#$@localhost:6432/test_db",
            "expected": {
                "scheme": "postgresql",
                "host": "localhost",
                "port": 6432,
                "database": "test_db",
                "username": "admin",
                "password": "REDACTED#$"
            }
        },
        {
            "name": "Password with multiple special characters",
            "url": "postgresql://admin:Pass#123$@example.com:5432/mydb",
            "expected": {
                "scheme": "postgresql",
                "host": "example.com",
                "port": 5432,
                "database": "mydb",
                "username": "admin",
                "password": "Pass#123$"
            }
        },
        {
            "name": "Normal password (no special chars)",
            "url": "postgresql://admin:normalpass@localhost:5432/db",
            "expected": {
                "scheme": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "admin",
                "password": "normalpass"
            }
        },
        {
            "name": "Password with @ character",
            "url": "postgresql://admin:pass@word@localhost:5432/db",
            "expected": {
                "scheme": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "admin",
                "password": "pass@word"
            }
        }
    ]
    
    all_passed = True
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print(f"   URL: {test_case['url']}")
        
        try:
            # Test the parsing
            result = ConnectionParser.parse_connection_string(test_case['url'])
            
            # Verify each expected component
            success = True
            for key, expected_value in test_case['expected'].items():
                actual_value = result.get(key)
                if actual_value != expected_value:
                    print(f"   ❌ {key}: expected '{expected_value}', got '{actual_value}'")
                    success = False
                else:
                    print(f"   ✅ {key}: '{actual_value}'")
            
            if success:
                print(f"   ✅ Test passed!")
            else:
                print(f"   ❌ Test failed!")
                all_passed = False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            all_passed = False
    
    return all_passed

def test_database_adapter_integration():
    """Test that DatabaseAdapter correctly uses the fixed parser."""
    print("\n🔌 TESTING DATABASE ADAPTER INTEGRATION")
    print("=" * 80)
    
    try:
        from dataflow.adapters.base import DatabaseAdapter
        from dataflow.adapters.postgresql import PostgreSQLAdapter
    except ImportError as e:
        print(f"❌ Cannot import adapters: {e}")
        return False
    
    # Test problematic connection string that previously failed
    problem_url = "postgresql://admin:REDACTED#$@localhost:6432/tpc_migration_dev"
    
    print(f"Testing problematic URL: {problem_url}")
    
    try:
        # This should now work without the int() parsing error
        adapter = PostgreSQLAdapter(problem_url)
        
        print("✅ Adapter created successfully!")
        print(f"   Host: {adapter.host}")
        print(f"   Port: {adapter.port}")
        print(f"   Database: {adapter.database}")
        print(f"   Username: {adapter.username}")
        print(f"   Password: {'*' * len(adapter.password) if adapter.password else None}")
        
        # Verify the parsed values are correct
        if (adapter.host == "localhost" and 
            adapter.port == 6432 and 
            adapter.database == "tpc_migration_dev" and
            adapter.username == "admin" and
            adapter.password == "REDACTED#$"):
            print("✅ All components parsed correctly!")
            return True
        else:
            print("❌ Some components were parsed incorrectly")
            return False
            
    except Exception as e:
        if "invalid literal for int()" in str(e) and "REDACTED" in str(e):
            print(f"❌ BUG STILL EXISTS: {e}")
            return False
        else:
            print(f"❌ Different error: {e}")
            return False

def test_edge_cases():
    """Test edge cases and complex scenarios."""
    print("\n🧪 TESTING EDGE CASES")
    print("=" * 80)
    
    try:
        from dataflow.adapters.connection_parser import ConnectionParser
    except ImportError as e:
        print(f"❌ Cannot import ConnectionParser: {e}")
        return False
    
    edge_cases = [
        {
            "name": "Empty password",
            "url": "postgresql://admin:@localhost:5432/db",
            "should_parse": True
        },
        {
            "name": "No password",
            "url": "postgresql://admin@localhost:5432/db", 
            "should_parse": True
        },
        {
            "name": "Complex password with many special chars",
            "url": "postgresql://admin:P@ss#w0rd$123!@localhost:5432/db",
            "should_parse": True
        },
        {
            "name": "Password with URL-encoded chars already",
            "url": "postgresql://admin:Pass%23%24@localhost:5432/db",
            "should_parse": True
        }
    ]
    
    all_passed = True
    
    for i, test_case in enumerate(edge_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print(f"   URL: {test_case['url']}")
        
        try:
            result = ConnectionParser.parse_connection_string(test_case['url'])
            if test_case['should_parse']:
                print(f"   ✅ Parsed successfully")
                print(f"      Host: {result.get('host')}")
                print(f"      Port: {result.get('port')}")
                print(f"      Username: {result.get('username')}")
                print(f"      Password: {'***' if result.get('password') else None}")
            else:
                print(f"   ❌ Should not have parsed successfully")
                all_passed = False
                
        except Exception as e:
            if test_case['should_parse']:
                print(f"   ❌ Parsing failed: {e}")
                all_passed = False
            else:
                print(f"   ✅ Correctly failed to parse: {e}")
    
    return all_passed

def run_comprehensive_connection_parsing_tests():
    """Run all connection parsing tests."""
    print("🚀 COMPREHENSIVE CONNECTION PARSING TESTS")
    print("=" * 80)
    print(f"Test started at: {datetime.now()}")
    print("Testing the fix for DataFlow connection string parsing bug")
    print("=" * 80)
    
    results = {}
    
    # Run all test suites
    results["parser_fix"] = test_connection_parser_fix()
    results["adapter_integration"] = test_database_adapter_integration()
    results["edge_cases"] = test_edge_cases()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed_count = sum(1 for result in results.values() if result)
    total_count = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name.upper().replace('_', ' ')}: {status}")
    
    print("\n" + "=" * 80)
    print("FINAL ASSESSMENT:")
    print("=" * 80)
    
    if passed_count == total_count:
        print("✅ ALL TESTS PASSED!")
        print("🎉 DataFlow connection parsing bug has been FIXED!")
        print("\nThe fix successfully handles:")
        print("  - Passwords with # character")
        print("  - Passwords with $ character") 
        print("  - Passwords with multiple special characters")
        print("  - Complex password scenarios")
        print("  - Integration with DatabaseAdapter")
    else:
        print(f"⚠️  {total_count - passed_count} test(s) failed out of {total_count}")
        print("The connection parsing fix may need additional work")
    
    return results

if __name__ == "__main__":
    results = run_comprehensive_connection_parsing_tests()
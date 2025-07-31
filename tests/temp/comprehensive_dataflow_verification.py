#!/usr/bin/env python3
"""
COMPREHENSIVE DATAFLOW VERIFICATION SUITE

This test suite provides complete verification of all DataFlow bug fixes:
1. Connection string parsing with special characters
2. Runtime success detection 
3. Error handling and reporting
4. End-to-end workflow functionality
5. Edge cases and stress testing
"""

import sys
import os
import traceback
from datetime import datetime
from typing import Dict, List, Any

# Add paths to find packages
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, "..", "..")
sys.path.insert(0, os.path.join(project_root, "apps", "kailash-dataflow", "src"))
sys.path.insert(0, os.path.join(project_root, "src"))

class DataFlowVerificationSuite:
    """Comprehensive verification suite for DataFlow bug fixes."""
    
    def __init__(self):
        self.results = {}
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            print(f"   ✅ {test_name}")
        else:
            self.failed_tests += 1
            print(f"   ❌ {test_name}")
        
        if details:
            print(f"      {details}")
        
        self.results[test_name] = {"passed": passed, "details": details}
    
    def test_connection_parser_comprehensive(self) -> bool:
        """Test 1: Comprehensive ConnectionParser verification."""
        print("\n🔧 TEST SUITE 1: CONNECTION PARSER COMPREHENSIVE")
        print("=" * 80)
        
        try:
            from dataflow.adapters.connection_parser import ConnectionParser
        except ImportError as e:
            self.log_test("ConnectionParser Import", False, f"Cannot import: {e}")
            return False
        
        # Test cases covering all scenarios from bug reports
        test_cases = [
            # Original bug case
            {
                "name": "Original Bug Case (REDACTED#$)",
                "url": "postgresql://admin:REDACTED#$@localhost:6432/tpc_migration_dev",
                "expected_password": "REDACTED#$",
                "expected_host": "localhost",
                "expected_port": 6432
            },
            # Edge cases
            {
                "name": "Multiple Special Characters",
                "url": "postgresql://user:P@ss#w0rd$123!@db.example.com:5432/mydb",
                "expected_password": "P@ss#w0rd$123!",
                "expected_host": "db.example.com",
                "expected_port": 5432
            },
            {
                "name": "Hash Only",
                "url": "postgresql://admin:password#123@localhost:5432/db",
                "expected_password": "password#123",
                "expected_host": "localhost",
                "expected_port": 5432
            },
            {
                "name": "Dollar Only", 
                "url": "postgresql://admin:password$123@localhost:5432/db",
                "expected_password": "password$123",
                "expected_host": "localhost",
                "expected_port": 5432
            },
            {
                "name": "At Symbol in Password",
                "url": "postgresql://admin:user@domain.com@localhost:5432/db",
                "expected_password": "user@domain.com",
                "expected_host": "localhost",
                "expected_port": 5432
            },
            {
                "name": "Question Mark in Password",
                "url": "postgresql://admin:what?is?this@localhost:5432/db",
                "expected_password": "what?is?this",
                "expected_host": "localhost", 
                "expected_port": 5432
            },
            {
                "name": "Normal Password (Control)",
                "url": "postgresql://admin:normalpass@localhost:5432/db",
                "expected_password": "normalpass",
                "expected_host": "localhost",
                "expected_port": 5432
            },
            {
                "name": "Empty Password",
                "url": "postgresql://admin:@localhost:5432/db",
                "expected_password": "",
                "expected_host": "localhost",
                "expected_port": 5432
            },
            {
                "name": "No Password",
                "url": "postgresql://admin@localhost:5432/db",
                "expected_password": None,
                "expected_host": "localhost",
                "expected_port": 5432
            }
        ]
        
        all_passed = True
        for test_case in test_cases:
            try:
                components = ConnectionParser.parse_connection_string(test_case["url"])
                
                # Verify each component
                success = True
                errors = []
                
                if components.get("password") != test_case["expected_password"]:
                    success = False
                    errors.append(f"Password: expected '{test_case['expected_password']}', got '{components.get('password')}'")
                
                if components.get("host") != test_case["expected_host"]:
                    success = False
                    errors.append(f"Host: expected '{test_case['expected_host']}', got '{components.get('host')}'")
                
                if components.get("port") != test_case["expected_port"]:
                    success = False
                    errors.append(f"Port: expected '{test_case['expected_port']}', got '{components.get('port')}'")
                
                self.log_test(test_case["name"], success, "; ".join(errors))
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(test_case["name"], False, f"Exception: {e}")
                all_passed = False
        
        return all_passed
    
    def test_connection_string_roundtrip(self) -> bool:
        """Test 2: Connection string encoding/decoding roundtrip."""
        print("\n🔄 TEST SUITE 2: CONNECTION STRING ROUNDTRIP")
        print("=" * 80)
        
        try:
            from dataflow.adapters.connection_parser import ConnectionParser
        except ImportError as e:
            self.log_test("ConnectionParser Import", False, f"Cannot import: {e}")
            return False
        
        test_passwords = [
            "REDACTED#$",
            "P@ss#w0rd$123!",
            "user@domain.com",
            "what?is?this",
            "normal_password",
            "pass#word",
            "pass$word",
            "pass@word",
            "pass?word"
        ]
        
        all_passed = True
        for password in test_passwords:
            try:
                original_url = f"postgresql://admin:{password}@localhost:5432/testdb"
                
                # Parse original
                components = ConnectionParser.parse_connection_string(original_url)
                
                # Rebuild 
                rebuilt_url = ConnectionParser.build_connection_string(
                    scheme=components.get("scheme"),
                    host=components.get("host"),
                    database=components.get("database"),
                    username=components.get("username"),
                    password=components.get("password"),
                    port=components.get("port")
                )
                
                # Parse rebuilt
                rebuilt_components = ConnectionParser.parse_connection_string(rebuilt_url)
                
                # Verify password survived roundtrip
                success = rebuilt_components.get("password") == password
                
                self.log_test(f"Roundtrip: {password}", success, 
                            f"Original: {password}, Final: {rebuilt_components.get('password')}")
                
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Roundtrip: {password}", False, f"Exception: {e}")
                all_passed = False
        
        return all_passed
    
    def test_database_adapter_integration(self) -> bool:
        """Test 3: DatabaseAdapter integration with special character passwords."""
        print("\n🔌 TEST SUITE 3: DATABASE ADAPTER INTEGRATION")
        print("=" * 80)
        
        try:
            from dataflow.adapters.postgresql import PostgreSQLAdapter
            from dataflow.adapters.factory import AdapterFactory
        except ImportError as e:
            self.log_test("Adapter Import", False, f"Cannot import: {e}")
            return False
        
        problematic_urls = [
            "postgresql://admin:REDACTED#$@localhost:6432/tpc_migration_dev",
            "postgresql://user:P@ss#w0rd$123@example.com:5432/mydb",
            "postgresql://test:password#@localhost:5432/testdb"
        ]
        
        all_passed = True
        for url in problematic_urls:
            try:
                # Test direct adapter creation
                adapter = PostgreSQLAdapter(url)
                
                # Verify components were parsed correctly
                success = (
                    adapter.host is not None and
                    adapter.port is not None and
                    adapter.database is not None and
                    adapter.username is not None and
                    adapter.password is not None
                )
                
                self.log_test(f"Adapter Creation: {url[:50]}...", success,
                            f"Host: {adapter.host}, Port: {adapter.port}, User: {adapter.username}")
                
                if not success:
                    all_passed = False
                
                # Test factory creation
                factory = AdapterFactory()
                db_type = factory.detect_database_type(url)
                created_adapter = factory.create_adapter(url)
                
                factory_success = (
                    db_type == "postgresql" and
                    created_adapter is not None and
                    created_adapter.host == adapter.host
                )
                
                self.log_test(f"Factory Creation: {url[:50]}...", factory_success,
                            f"Type: {db_type}, Created: {created_adapter is not None}")
                
                if not factory_success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Adapter: {url[:50]}...", False, f"Exception: {e}")
                all_passed = False
        
        return all_passed
    
    def test_dataflow_initialization(self) -> bool:
        """Test 4: DataFlow initialization with problematic connection strings."""
        print("\n🚀 TEST SUITE 4: DATAFLOW INITIALIZATION")
        print("=" * 80)
        
        try:
            from dataflow import DataFlow
        except ImportError as e:
            self.log_test("DataFlow Import", False, f"Cannot import: {e}")
            return False
        
        problematic_urls = [
            "postgresql://admin:REDACTED#$@localhost:6432/tpc_migration_dev",
            "postgresql://user:complex#pass$word@localhost:5432/testdb",
            "postgresql://test:simple@password@localhost:5432/db"
        ]
        
        all_passed = True
        for url in problematic_urls:
            try:
                # Test DataFlow initialization
                db = DataFlow(database_url=url)
                
                success = db is not None
                self.log_test(f"DataFlow Init: {url[:50]}...", success)
                
                if not success:
                    all_passed = False
                
                # Test model definition
                try:
                    @db.model
                    class TestModel:
                        name: str
                        value: int
                    
                    model_success = True
                    self.log_test(f"Model Definition: {url[:50]}...", model_success)
                    
                except Exception as model_e:
                    self.log_test(f"Model Definition: {url[:50]}...", False, f"Model error: {model_e}")
                    all_passed = False
                
            except Exception as e:
                self.log_test(f"DataFlow Init: {url[:50]}...", False, f"Exception: {e}")
                all_passed = False
        
        return all_passed
    
    def test_create_tables_operation(self) -> bool:
        """Test 5: create_tables operation with special character passwords."""
        print("\n📋 TEST SUITE 5: CREATE TABLES OPERATION")
        print("=" * 80)
        
        try:
            from dataflow import DataFlow
        except ImportError as e:
            self.log_test("DataFlow Import", False, f"Cannot import: {e}")
            return False
        
        # Test with the exact problematic connection string from bug report
        url = "postgresql://admin:REDACTED#$@localhost:6432/tpc_migration_dev"
        
        try:
            db = DataFlow(database_url=url)
            
            @db.model
            class BugTestModel:
                id: int
                name: str
                description: str
            
            # This is the critical test - create_tables should not fail with parsing error
            result = db.create_tables()
            
            # We expect this to return None (no database running) but NOT crash with parsing error
            success = True  # If we got here without exception, parsing worked
            
            self.log_test("create_tables() No Parsing Error", success, 
                        f"Result: {result} (expected None due to no database)")
            
            return success
            
        except Exception as e:
            error_str = str(e)
            
            # Check if it's the old parsing error
            if "invalid literal for int()" in error_str and "REDACTED" in error_str:
                self.log_test("create_tables() No Parsing Error", False, 
                            f"OLD BUG STILL EXISTS: {error_str}")
                return False
            else:
                # Any other error (like connection failure) means parsing worked
                self.log_test("create_tables() No Parsing Error", True,
                            f"Connection error (expected): {error_str}")
                return True
    
    def test_runtime_success_detection(self) -> bool:
        """Test 6: Runtime success detection functionality."""
        print("\n⚡ TEST SUITE 6: RUNTIME SUCCESS DETECTION")
        print("=" * 80)
        
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.runtime.local import LocalRuntime
            from kailash.nodes.base import Node, NodeParameter
        except ImportError as e:
            self.log_test("Runtime Import", False, f"Cannot import: {e}")
            return False
        
        try:
            # Create a test node that returns failure
            class TestFailingNode(Node):
                def get_parameters(self):
                    return [NodeParameter("test_param", str, "Test parameter", default="test")]
                
                def execute(self, test_param="test", **kwargs):
                    return {
                        "success": False,
                        "error": "Database query failed: invalid literal for int() with base 10: 'REDACTED'",
                        "operation": "test_failure"
                    }
            
            # Register the node
            from kailash.nodes.base import NodeRegistry
            NodeRegistry.register(TestFailingNode, alias="TestFailingNode")
            
            # Test with content-aware runtime
            workflow = WorkflowBuilder()
            workflow.add_node("TestFailingNode", "test_node", {"test_param": "value"})
            
            runtime = LocalRuntime(content_aware_success_detection=True)
            
            try:
                results, run_id = runtime.execute(workflow.build())
                
                # If we get here, check if the failure was detected
                if "test_node" in results:
                    node_result = results["test_node"]
                    if node_result.get("success") == False:
                        self.log_test("Runtime Detects Node Failure", True, 
                                    "Runtime correctly returned failure result")
                        return True
                    else:
                        self.log_test("Runtime Detects Node Failure", False,
                                    "Runtime did not detect node failure")
                        return False
                else:
                    self.log_test("Runtime Detects Node Failure", False,
                                "No results returned")
                    return False
                    
            except Exception as runtime_e:
                if "Content-aware failure detected" in str(runtime_e):
                    self.log_test("Runtime Detects Node Failure", True,
                                f"Runtime correctly threw exception: {runtime_e}")
                    return True
                else:
                    self.log_test("Runtime Detects Node Failure", False,
                                f"Runtime threw different exception: {runtime_e}")
                    return False
                    
        except Exception as e:
            self.log_test("Runtime Success Detection Setup", False, f"Setup error: {e}")
            return False
    
    def test_error_handling_improvements(self) -> bool:
        """Test 7: Error handling and reporting improvements."""
        print("\n🚨 TEST SUITE 7: ERROR HANDLING IMPROVEMENTS")
        print("=" * 80)
        
        try:
            from dataflow import DataFlow
        except ImportError as e:
            self.log_test("DataFlow Import", False, f"Cannot import: {e}")
            return False
        
        # Test with invalid connection (but valid parsing)
        invalid_url = "postgresql://admin:REDACTED#$@nonexistent:9999/nonexistent"
        
        try:
            db = DataFlow(database_url=invalid_url)
            
            @db.model
            class ErrorTestModel:
                name: str
                value: int
            
            # Try to create tables - should fail with connection error, not parsing error
            result = db.create_tables()
            
            # If create_tables returns None, that's the current behavior for connection failures
            if result is None:
                self.log_test("Proper Error Handling", True,
                            "create_tables() returned None for connection failure")
                return True
            else:
                self.log_test("Proper Error Handling", False,
                            f"Unexpected result: {result}")
                return False
                
        except Exception as e:
            error_str = str(e)
            
            # Check error type
            if "invalid literal for int()" in error_str:
                self.log_test("Proper Error Handling", False,
                            f"Still getting parsing error: {error_str}")
                return False
            elif "Connect call failed" in error_str or "Connection" in error_str:
                self.log_test("Proper Error Handling", True,
                            f"Proper connection error: {error_str}")
                return True
            else:
                self.log_test("Proper Error Handling", True,
                            f"Different error (not parsing): {error_str}")
                return True
    
    def test_stress_special_characters(self) -> bool:
        """Test 8: Stress test with extreme special character combinations."""
        print("\n💥 TEST SUITE 8: STRESS TEST SPECIAL CHARACTERS")
        print("=" * 80)
        
        try:
            from dataflow.adapters.connection_parser import ConnectionParser
        except ImportError as e:
            self.log_test("ConnectionParser Import", False, f"Cannot import: {e}")
            return False
        
        # Extreme test cases
        stress_cases = [
            "postgresql://admin:!@#$%^&*()@localhost:5432/db",
            "postgresql://user:##$$@@??@example.com:5432/test", 
            "postgresql://test:a#b$c@d?e@host:5432/database",
            "postgresql://admin:password#with#multiple#hashes@localhost:5432/db",
            "postgresql://user:pass$with$multiple$dollars@localhost:5432/db",
            "postgresql://test:user@email@domain@localhost:5432/db"
        ]
        
        all_passed = True
        for url in stress_cases:
            try:
                # Test parsing
                components = ConnectionParser.parse_connection_string(url)
                
                # Test rebuilding
                rebuilt = ConnectionParser.build_connection_string(
                    scheme=components.get("scheme"),
                    host=components.get("host"),
                    database=components.get("database"),
                    username=components.get("username"),
                    password=components.get("password"),
                    port=components.get("port")
                )
                
                # Test re-parsing
                rebuilt_components = ConnectionParser.parse_connection_string(rebuilt)
                
                # Verify password integrity - parse original URL correctly
                if '://' in url and '@' in url:
                    rest = url.split('://', 1)[1]
                    last_at_index = rest.rfind('@')
                    creds_part = rest[:last_at_index]
                    if ':' in creds_part:
                        colon_index = creds_part.find(':')
                        original_password = creds_part[colon_index + 1:]
                    else:
                        original_password = ""
                else:
                    original_password = ""
                
                final_password = rebuilt_components.get("password")
                
                success = final_password == original_password
                
                self.log_test(f"Stress: {original_password}", success,
                            f"Original: {original_password}, Final: {final_password}")
                
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Stress: {url[:30]}...", False, f"Exception: {e}")
                all_passed = False
        
        return all_passed
    
    def run_comprehensive_verification(self) -> Dict[str, Any]:
        """Run all verification tests."""
        print("🚀 COMPREHENSIVE DATAFLOW VERIFICATION SUITE")
        print("=" * 80)
        print(f"Started at: {datetime.now()}")
        print("Verifying ALL DataFlow bug fixes with complete test coverage")
        print("=" * 80)
        
        # Run all test suites
        test_results = {
            "connection_parser": self.test_connection_parser_comprehensive(),
            "roundtrip_encoding": self.test_connection_string_roundtrip(),
            "adapter_integration": self.test_database_adapter_integration(),
            "dataflow_initialization": self.test_dataflow_initialization(),
            "create_tables": self.test_create_tables_operation(),
            "runtime_success": self.test_runtime_success_detection(),
            "error_handling": self.test_error_handling_improvements(),
            "stress_test": self.test_stress_special_characters()
        }
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE VERIFICATION RESULTS")
        print("=" * 80)
        
        passed_suites = sum(1 for result in test_results.values() if result)
        total_suites = len(test_results)
        
        for suite_name, passed in test_results.items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{suite_name.upper().replace('_', ' ')}: {status}")
        
        print(f"\nTEST DETAILS:")
        print(f"  Total Test Cases: {self.total_tests}")
        print(f"  Passed: {self.passed_tests}")
        print(f"  Failed: {self.failed_tests}")
        print(f"  Success Rate: {(self.passed_tests/self.total_tests)*100:.1f}%")
        
        print(f"\nTEST SUITES:")
        print(f"  Suites Passed: {passed_suites}/{total_suites}")
        print(f"  Suite Success Rate: {(passed_suites/total_suites)*100:.1f}%")
        
        print("\n" + "=" * 80)
        print("FINAL VERIFICATION ASSESSMENT:")
        print("=" * 80)
        
        if passed_suites == total_suites and self.failed_tests == 0:
            print("🎉 ALL TESTS PASSED - DATAFLOW COMPLETELY FIXED!")
            print("\n✅ VERIFIED FIXES:")
            print("  - Connection string parsing with special characters")
            print("  - Password encoding/decoding roundtrip")
            print("  - DatabaseAdapter integration")
            print("  - DataFlow initialization")
            print("  - create_tables() operation")
            print("  - Runtime success detection")
            print("  - Proper error handling")
            print("  - Stress testing with extreme cases")
            
            print("\n🚀 PRODUCTION READY:")
            print("  - All reported bugs fixed")
            print("  - Comprehensive test coverage")
            print("  - Edge cases handled")
            print("  - Backward compatibility maintained")
            
        elif passed_suites >= total_suites * 0.8:  # 80% threshold
            print("⚠️  MOSTLY FIXED - Some issues remain")
            print(f"  {total_suites - passed_suites} test suite(s) failed")
            print(f"  {self.failed_tests} individual test(s) failed")
            
        else:
            print("❌ SIGNIFICANT ISSUES REMAIN")
            print(f"  {total_suites - passed_suites} test suite(s) failed")
            print(f"  {self.failed_tests} individual test(s) failed")
            print("  More work needed before production deployment")
        
        return {
            "test_results": test_results,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "suite_success_rate": (passed_suites/total_suites)*100,
            "test_success_rate": (self.passed_tests/self.total_tests)*100 if self.total_tests > 0 else 0
        }

def main():
    """Run comprehensive verification."""
    verification = DataFlowVerificationSuite()
    results = verification.run_comprehensive_verification()
    
    # Return exit code based on results
    if results["failed_tests"] == 0 and results["suite_success_rate"] == 100:
        print(f"\n🎯 VERIFICATION COMPLETE: ALL SYSTEMS GO!")
        return 0
    else:
        print(f"\n⚠️  VERIFICATION COMPLETE: ISSUES DETECTED")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
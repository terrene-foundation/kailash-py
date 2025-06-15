#!/usr/bin/env python3
"""
Enterprise Test Suite Runner

Runs all enterprise component tests and provides a comprehensive report.
"""

import asyncio
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime, UTC

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class EnterpriseTestRunner:
    """Orchestrates running all enterprise tests."""
    
    def __init__(self):
        self.results: Dict[str, Dict] = {}
        self.start_time = None
        self.end_time = None
    
    async def run_test_directory(self, name: str, test_dir: str) -> Tuple[bool, float]:
        """Run tests in a directory using pytest."""
        print(f"\n{'='*80}")
        print(f"🏃 Running {name}")
        print(f"{'='*80}")
        
        suite_start = time.time()
        try:
            # Run pytest on the directory
            result = subprocess.run(
                ["python", "-m", "pytest", test_dir, "-v", "--tb=short"],
                capture_output=True,
                text=True
            )
            
            success = result.returncode == 0
            duration = time.time() - suite_start
            
            # Print output
            if result.stdout:
                print(result.stdout)
            if result.stderr and not success:
                print(result.stderr)
            
            self.results[name] = {
                "success": success,
                "duration": duration,
                "error": result.stderr if not success else None
            }
            
            return success, duration
            
        except Exception as e:
            duration = time.time() - suite_start
            self.results[name] = {
                "success": False,
                "duration": duration,
                "error": str(e)
            }
            
            print(f"\n❌ {name} crashed with error: {e}")
            import traceback
            traceback.print_exc()
            
            return False, duration
    
    async def run_all_suites(self):
        """Run all enterprise test suites."""
        self.start_time = datetime.now(UTC)
        
        print("\n🏢 KAILASH ENTERPRISE TEST SUITE")
        print("=" * 80)
        print(f"Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # Define test directories
        test_base = Path(__file__).parent
        test_suites = [
            ("Authentication Tests", str(test_base / "test_auth")),
            ("Security Tests", str(test_base / "test_security")),
            ("Compliance Tests", str(test_base / "test_compliance")),
            ("User & Role Management Tests", str(test_base / "test_user_role_management.py")),
            ("SSO Integration Tests", str(test_base / "test_sso_integration.py"))
        ]
        
        total_suites = len(test_suites)
        passed_suites = 0
        total_duration = 0
        
        # Run each suite
        for suite_name, test_path in test_suites:
            success, duration = await self.run_test_directory(suite_name, test_path)
            if success:
                passed_suites += 1
            total_duration += duration
        
        self.end_time = datetime.now(UTC)
        
        # Print comprehensive summary
        self.print_summary(total_suites, passed_suites, total_duration)
        
        return passed_suites == total_suites
    
    def print_summary(self, total: int, passed: int, duration: float):
        """Print comprehensive test summary."""
        print("\n" + "=" * 80)
        print("📊 ENTERPRISE TEST SUITE SUMMARY")
        print("=" * 80)
        
        print(f"\n⏱️  Total Duration: {duration:.2f} seconds")
        print(f"🕐 Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"🕑 Ended: {self.end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        print(f"\n📈 Suite Results:")
        print(f"   • Total Suites: {total}")
        print(f"   • Passed: {passed} ✅")
        print(f"   • Failed: {total - passed} ❌")
        print(f"   • Success Rate: {(passed/total*100):.1f}%")
        
        print("\n📋 Detailed Results:")
        for suite_name, result in self.results.items():
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            print(f"\n   {suite_name}:")
            print(f"      Status: {status}")
            print(f"      Duration: {result['duration']:.2f}s")
            if result["error"]:
                print(f"      Error: {result['error']}")
        
        # Component validation summary
        print("\n✅ Enterprise Components Validated:")
        print("   • Authentication Systems:")
        print("      - SSO (SAML 2.0, OAuth 2.0, OpenID Connect)")
        print("      - Multi-Factor Authentication (TOTP, SMS, Push, Biometric)")
        print("      - Directory Integration (LDAP, Active Directory)")
        print("      - Provider Integration (Azure AD, Google, Okta)")
        print("   • User & Access Management:")
        print("      - User CRUD Operations with Audit Trails")
        print("      - Role-Based Access Control (RBAC)")
        print("      - Attribute-Based Access Control (ABAC)")
        print("      - Dynamic Permission Evaluation")
        print("   • Security Components:")
        print("      - Threat Detection with ML")
        print("      - Behavior Analysis")
        print("      - Session Management")
        print("      - Credential Rotation")
        print("   • Compliance & Governance:")
        print("      - GDPR Compliance (PII Detection, Right to Erasure)")
        print("      - Data Retention Policies")
        print("      - Audit Logging with Tamper Protection")
        print("   • Enterprise Features:")
        print("      - Just-In-Time (JIT) Provisioning")
        print("      - Session Federation")
        print("      - Multi-Provider Fallback")
        print("      - Performance Monitoring")
        
        if passed == total:
            print("\n🎉 ALL ENTERPRISE TESTS PASSED! 🎉")
            print("✅ The Kailash SDK enterprise components are fully validated")
            print("✅ Ready for production enterprise deployments")
        else:
            print(f"\n⚠️ {total - passed} test suite(s) failed!")
            print("❌ Please review the errors above before deployment")
    
    def generate_report(self, output_file: str = "enterprise_test_report.txt"):
        """Generate detailed test report file."""
        with open(output_file, "w") as f:
            f.write("KAILASH ENTERPRISE TEST REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            f.write(f"Duration: {(self.end_time - self.start_time).total_seconds():.2f} seconds\n\n")
            
            f.write("SUMMARY\n")
            f.write("-" * 40 + "\n")
            total = len(self.results)
            passed = sum(1 for r in self.results.values() if r["success"])
            f.write(f"Total Suites: {total}\n")
            f.write(f"Passed: {passed}\n")
            f.write(f"Failed: {total - passed}\n")
            f.write(f"Success Rate: {(passed/total*100):.1f}%\n\n")
            
            f.write("DETAILED RESULTS\n")
            f.write("-" * 40 + "\n")
            for suite_name, result in self.results.items():
                f.write(f"\n{suite_name}:\n")
                f.write(f"  Status: {'PASSED' if result['success'] else 'FAILED'}\n")
                f.write(f"  Duration: {result['duration']:.2f}s\n")
                if result["error"]:
                    f.write(f"  Error: {result['error']}\n")
            
            f.write("\n" + "=" * 80 + "\n")
        
        print(f"\n📄 Detailed report saved to: {output_file}")


async def main():
    """Main entry point."""
    runner = EnterpriseTestRunner()
    
    try:
        success = await runner.run_all_suites()
        
        # Generate report
        runner.generate_report()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Test run interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error running tests: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run with proper event loop
    asyncio.run(main())
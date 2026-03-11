#!/usr/bin/env python3
"""
Coverage Measurement Assessment Script
Measures exact coverage improvement and assesses progress toward 85% milestone.
"""

import json
import subprocess
import sys
from pathlib import Path


def run_coverage_analysis():
    """Run comprehensive coverage analysis and return metrics."""
    print("🔍 Running comprehensive coverage analysis...")

    # Run pytest with coverage
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--cov=src/kaizen",
        "--cov-report=json:coverage_current.json",
        "--cov-report=term",
        "-q",
        "--tb=no",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(f"✅ Coverage analysis completed (exit code: {result.returncode})")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ Coverage analysis timed out")
        return False
    except Exception as e:
        print(f"❌ Error running coverage: {e}")
        return False


def load_coverage_data():
    """Load coverage data from JSON report."""
    coverage_file = Path("coverage_current.json")
    if not coverage_file.exists():
        print(f"❌ Coverage file not found: {coverage_file}")
        return None

    try:
        with open(coverage_file, "r") as f:
            data = json.load(f)
        print(f"✅ Loaded coverage data from {coverage_file}")
        return data
    except Exception as e:
        print(f"❌ Error loading coverage data: {e}")
        return None


def analyze_coverage_progress(data):
    """Analyze coverage progress and calculate metrics."""
    if not data:
        return None

    summary = data.get("totals", {})

    # Extract key metrics
    total_statements = summary.get("num_statements", 0)
    covered_statements = summary.get("covered_lines", 0)
    missing_statements = summary.get("missing_lines", 0)
    current_coverage = summary.get("percent_covered", 0.0)

    # Baseline from previous analysis
    baseline_coverage = 72.02

    # Calculate improvements
    coverage_improvement = current_coverage - baseline_coverage

    # Calculate milestone progress
    milestone_85_gap = 85.0 - current_coverage
    target_95_gap = 95.0 - current_coverage

    # Calculate statements needed
    statements_for_85 = int((85.0 * total_statements / 100) - covered_statements)
    statements_for_95 = int((95.0 * total_statements / 100) - covered_statements)

    return {
        "current_coverage": current_coverage,
        "baseline_coverage": baseline_coverage,
        "coverage_improvement": coverage_improvement,
        "total_statements": total_statements,
        "covered_statements": covered_statements,
        "missing_statements": missing_statements,
        "milestone_85_gap": milestone_85_gap,
        "target_95_gap": target_95_gap,
        "statements_for_85": max(0, statements_for_85),
        "statements_for_95": max(0, statements_for_95),
        "milestone_85_progress": max(
            0,
            min(
                100,
                (current_coverage - baseline_coverage)
                / (85.0 - baseline_coverage)
                * 100,
            ),
        ),
    }


def assess_test_quality(data):
    """Assess the quality and effectiveness of new tests."""
    if not data:
        return {}

    files = data.get("files", {})

    # Analyze module coverage
    module_analysis = {}
    for file_path, file_data in files.items():
        if "src/kaizen" in file_path:
            module_name = file_path.replace("src/kaizen/", "").replace(".py", "")
            coverage_pct = file_data.get("summary", {}).get("percent_covered", 0.0)
            missing_lines = file_data.get("summary", {}).get("missing_lines", 0)

            module_analysis[module_name] = {
                "coverage": coverage_pct,
                "missing_lines": missing_lines,
                "covered_lines": file_data.get("summary", {}).get("covered_lines", 0),
            }

    # Identify high-impact improvements
    high_impact = []
    medium_impact = []
    low_impact = []

    for module, data in module_analysis.items():
        if data["coverage"] >= 90:
            high_impact.append((module, data["coverage"]))
        elif data["coverage"] >= 70:
            medium_impact.append((module, data["coverage"]))
        else:
            low_impact.append((module, data["coverage"]))

    return {
        "high_impact_modules": sorted(high_impact, key=lambda x: x[1], reverse=True),
        "medium_impact_modules": sorted(
            medium_impact, key=lambda x: x[1], reverse=True
        ),
        "low_impact_modules": sorted(low_impact, key=lambda x: x[1], reverse=True),
        "total_modules": len(module_analysis),
    }


def generate_assessment_report(metrics, quality_assessment):
    """Generate comprehensive assessment report."""
    if not metrics:
        return "❌ Unable to generate assessment - no coverage data available"

    report = f"""
# TODO-150 Coverage Measurement Assessment Report

## 📊 COVERAGE IMPROVEMENT RESULTS

### Current Status After New Tests
- **Current Coverage**: {metrics['current_coverage']:.2f}%
- **Baseline Coverage**: {metrics['baseline_coverage']:.2f}%
- **Improvement Achieved**: {metrics['coverage_improvement']:+.2f} percentage points

### Progress Toward Milestones
- **85% Milestone Gap**: {metrics['milestone_85_gap']:.2f} percentage points remaining
- **95% Target Gap**: {metrics['target_95_gap']:.2f} percentage points remaining
- **Milestone Progress**: {metrics['milestone_85_progress']:.1f}% toward 85% target

### Statement Coverage Analysis
- **Total Statements**: {metrics['total_statements']:,}
- **Covered Statements**: {metrics['covered_statements']:,}
- **Missing Statements**: {metrics['missing_statements']:,}
- **Statements Needed for 85%**: {metrics['statements_for_85']:,}
- **Statements Needed for 95%**: {metrics['statements_for_95']:,}

## 🎯 MILESTONE ASSESSMENT

### 85% Milestone Status
"""

    if metrics["current_coverage"] >= 85.0:
        report += "✅ **MILESTONE ACHIEVED** - 85% coverage target reached!\n"
    elif metrics["milestone_85_gap"] <= 5.0:
        report += f"🟡 **CLOSE TO TARGET** - Only {metrics['milestone_85_gap']:.1f}% remaining\n"
    elif metrics["milestone_85_gap"] <= 10.0:
        report += (
            f"🟠 **MODERATE PROGRESS** - {metrics['milestone_85_gap']:.1f}% remaining\n"
        )
    else:
        report += (
            f"🔴 **SIGNIFICANT GAP** - {metrics['milestone_85_gap']:.1f}% remaining\n"
        )

    report += """
### Test Quality Assessment
"""

    if quality_assessment:
        report += f"""- **High-Coverage Modules (>90%)**: {len(quality_assessment['high_impact_modules'])} modules
- **Medium-Coverage Modules (70-90%)**: {len(quality_assessment['medium_impact_modules'])} modules
- **Low-Coverage Modules (<70%)**: {len(quality_assessment['low_impact_modules'])} modules
- **Total Modules Analyzed**: {quality_assessment['total_modules']} modules

### Top Performing Modules
"""

        for module, coverage in quality_assessment["high_impact_modules"][:5]:
            report += f"- **{module}**: {coverage:.1f}% coverage ✅\n"

        if quality_assessment["low_impact_modules"]:
            report += """
### Remaining Low-Coverage Modules
"""
            for module, coverage in quality_assessment["low_impact_modules"][:5]:
                report += f"- **{module}**: {coverage:.1f}% coverage ⚠️\n"

    report += """

## 📈 IMPROVEMENT ASSESSMENT

### Effectiveness of Targeted Testing
"""

    if metrics["coverage_improvement"] > 5.0:
        report += f"✅ **HIGHLY EFFECTIVE** - {metrics['coverage_improvement']:+.2f}% improvement achieved\n"
    elif metrics["coverage_improvement"] > 2.0:
        report += f"🟡 **MODERATELY EFFECTIVE** - {metrics['coverage_improvement']:+.2f}% improvement achieved\n"
    elif metrics["coverage_improvement"] > 0:
        report += f"🟠 **LIMITED EFFECTIVENESS** - {metrics['coverage_improvement']:+.2f}% improvement achieved\n"
    else:
        report += (
            f"🔴 **NO IMPROVEMENT** - {metrics['coverage_improvement']:+.2f}% change\n"
        )

    report += """
### Realistic Timeline Assessment
"""

    if metrics["current_coverage"] >= 85.0:
        report += "🎯 **85% MILESTONE COMPLETE** - Ready for final push to 95%\n"
    elif metrics["statements_for_85"] <= 500:
        report += f"🟢 **85% ACHIEVABLE** - Only {metrics['statements_for_85']} statements needed\n"
    elif metrics["statements_for_85"] <= 1000:
        report += f"🟡 **85% CHALLENGING** - {metrics['statements_for_85']} statements needed\n"
    else:
        report += (
            f"🔴 **85% DIFFICULT** - {metrics['statements_for_85']} statements needed\n"
        )

    report += """
## 🎯 TODO-150 COMPLETION ASSESSMENT

### Current Completion Status
"""

    completion_pct = (metrics["current_coverage"] / 95.0) * 100

    if metrics["current_coverage"] >= 95.0:
        report += "✅ **TODO-150 COMPLETE** - >95% coverage achieved\n"
    elif metrics["current_coverage"] >= 85.0:
        report += f"🟡 **SUBSTANTIALLY COMPLETE** - {completion_pct:.1f}% of target achieved\n"
    elif metrics["current_coverage"] >= 75.0:
        report += f"🟠 **GOOD PROGRESS** - {completion_pct:.1f}% of target achieved\n"
    else:
        report += f"🔴 **SIGNIFICANT WORK REMAINING** - {completion_pct:.1f}% of target achieved\n"

    report += """
### Next Steps Recommendation
"""

    if metrics["current_coverage"] >= 95.0:
        report += "🎉 **CELEBRATE & DOCUMENT** - Coverage target achieved!\n"
    elif metrics["current_coverage"] >= 85.0:
        report += "🚀 **FINAL PUSH** - Focus on remaining high-impact modules for 95% target\n"
    elif metrics["milestone_85_gap"] <= 5.0:
        report += "⚡ **SPRINT TO 85%** - Close to milestone, focused effort needed\n"
    else:
        report += "🔄 **SYSTEMATIC COVERAGE** - Continue methodical module-by-module approach\n"

    report += f"""
## 📊 EVIDENCE-BASED CONCLUSION

**Coverage Improvement**: {metrics['coverage_improvement']:+.2f} percentage points from baseline
**Milestone Progress**: {metrics['milestone_85_progress']:.1f}% toward 85% target
**TODO-150 Completion**: {completion_pct:.1f}% of >95% target achieved

**HONEST ASSESSMENT**: """

    if metrics["current_coverage"] >= 85.0:
        report += "TODO-150 substantially complete with excellent progress toward final target."
    elif metrics["coverage_improvement"] >= 5.0:
        report += "Significant improvement achieved. Targeted testing strategy is working effectively."
    elif metrics["coverage_improvement"] >= 2.0:
        report += "Moderate improvement achieved. Strategy needs refinement for faster progress."
    else:
        report += (
            "Limited improvement achieved. Strategy requires fundamental reassessment."
        )

    return report


def main():
    """Main assessment function."""
    print("🎯 TODO-150 Coverage Measurement Assessment")
    print("=" * 50)

    # Run coverage analysis
    success = run_coverage_analysis()
    if not success:
        print("❌ Coverage analysis failed - assessment cannot be completed")
        return 1

    # Load coverage data
    coverage_data = load_coverage_data()
    if not coverage_data:
        print("❌ Coverage data unavailable - assessment cannot be completed")
        return 1

    # Analyze progress
    metrics = analyze_coverage_progress(coverage_data)
    quality_assessment = assess_test_quality(coverage_data)

    # Generate report
    report = generate_assessment_report(metrics, quality_assessment)

    # Write report to file
    report_file = Path("TODO_150_COVERAGE_ASSESSMENT_REPORT.md")
    with open(report_file, "w") as f:
        f.write(report)

    print(f"✅ Assessment report generated: {report_file}")
    print("\n" + "=" * 50)
    print("📊 SUMMARY METRICS")
    print("=" * 50)

    if metrics:
        print(f"Current Coverage: {metrics['current_coverage']:.2f}%")
        print(f"Improvement: {metrics['coverage_improvement']:+.2f} percentage points")
        print(f"85% Milestone Gap: {metrics['milestone_85_gap']:.2f} percentage points")
        print(f"Statements for 85%: {metrics['statements_for_85']:,}")
        print(f"Statements for 95%: {metrics['statements_for_95']:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

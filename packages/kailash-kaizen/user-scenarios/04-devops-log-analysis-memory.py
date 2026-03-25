"""
Scenario 4: DevOps Engineer - Log Analysis with Memory
=======================================================

User Profile:
- DevOps engineer monitoring application logs
- Needs to detect anomalies and patterns
- Wants to track issues across multiple sessions
- Requires persistent memory for context

Use Case:
- Parse and analyze application logs
- Detect errors, warnings, and anomalies
- Track patterns across time periods
- Maintain context across analysis sessions

Developer Experience Goals:
- Simple log parsing
- Pattern detection
- Memory persistence across sessions
- Session continuity with session_id
"""

import re
from datetime import datetime

from dotenv import load_dotenv
from kaizen_agents.agents import MemoryAgent
from kaizen_agents.agents.specialized.memory_agent import MemoryConfig

# Load environment variables
load_dotenv()

# Sample application logs
SAMPLE_LOGS = """
2025-01-17 08:15:23 INFO  [UserService] User login successful: user_id=1234
2025-01-17 08:16:45 WARN  [DatabasePool] Connection pool 80% full
2025-01-17 08:17:12 ERROR [PaymentService] Payment processing failed: timeout after 30s
2025-01-17 08:17:30 INFO  [PaymentService] Retry attempt 1/3
2025-01-17 08:18:05 ERROR [PaymentService] Payment processing failed: timeout after 30s
2025-01-17 08:18:22 INFO  [PaymentService] Retry attempt 2/3
2025-01-17 08:19:10 ERROR [PaymentService] Payment processing failed: timeout after 30s
2025-01-17 08:19:15 ERROR [PaymentService] Maximum retries exceeded, transaction aborted
2025-01-17 08:20:30 WARN  [DatabasePool] Connection pool 90% full
2025-01-17 08:21:45 ERROR [DatabasePool] No available connections, request queued
2025-01-17 08:22:10 INFO  [UserService] User logout: user_id=1234
2025-01-17 08:23:00 WARN  [MemoryMonitor] Heap usage at 85%
2025-01-17 08:24:15 ERROR [APIGateway] Service unavailable: 503 response from backend
2025-01-17 08:25:30 INFO  [HealthCheck] System health check: DEGRADED
"""


def parse_logs(log_content: str) -> list:
    """Parse log entries into structured format."""
    log_pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)\s+\[(.*?)\] (.+)"
    entries = []

    for line in log_content.strip().split("\n"):
        match = re.match(log_pattern, line)
        if match:
            timestamp, level, service, message = match.groups()
            entries.append(
                {
                    "timestamp": timestamp,
                    "level": level,
                    "service": service,
                    "message": message,
                }
            )

    return entries


def main():
    """DevOps workflow - log analysis with memory persistence."""

    print("=" * 70)
    print("DevOps Engineer - Log Analysis with Memory Continuity")
    print("=" * 70 + "\n")

    # Step 1: Parse logs
    print("📋 Parsing application logs...")
    log_entries = parse_logs(SAMPLE_LOGS)
    print(f"✅ Parsed {len(log_entries)} log entries\n")

    # Step 2: Create memory-enabled agent with session continuity
    print("🧠 Creating Memory-Enabled Log Analysis Agent...")
    session_id = f"log_analysis_{datetime.now().strftime('%Y%m%d')}"

    config = MemoryConfig(
        llm_provider="ollama",
        model="llama2",
        temperature=0.3,  # Lower for consistent analysis
        session_id=session_id,  # Persist memory across interactions
        max_tokens=600,
    )
    agent = MemoryAgent(config=config)
    print(f"✅ Session ID: {session_id}\n")

    # Step 3: Initial log analysis
    print("🔍 PHASE 1: Initial Log Analysis")
    print("-" * 70)

    # Filter errors and warnings
    errors = [e for e in log_entries if e["level"] == "ERROR"]
    warnings = [e for e in log_entries if e["level"] == "WARN"]

    print("\n📊 Summary:")
    print(f"  - Total entries: {len(log_entries)}")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Warnings: {len(warnings)}")
    print(f"  - Info: {len(log_entries) - len(errors) - len(warnings)}\n")

    # Analyze error patterns
    error_summary = "\n".join(
        [f"[{e['timestamp']}] {e['service']}: {e['message']}" for e in errors]
    )

    analysis_prompt = f"""
    Analyze these application errors:

    {error_summary}

    Identify:
    1. Root cause of failures
    2. Services affected
    3. Cascading failures (if any)
    4. Recommended actions
    """

    try:
        result = agent.ask(analysis_prompt)
        print("💡 Error Analysis:")
        print("-" * 70)
        print(result["answer"])
        print()

    except Exception as e:
        print(f"❌ Error in analysis: {e}\n")

    # Step 4: Analyze warnings with context
    print("\n🔍 PHASE 2: Warning Analysis (Using Memory Context)")
    print("-" * 70)

    warning_summary = "\n".join(
        [f"[{w['timestamp']}] {w['service']}: {w['message']}" for w in warnings]
    )

    warning_prompt = f"""
    Given the error pattern you just analyzed, now review these warnings:

    {warning_summary}

    Are these warnings related to the errors you identified?
    What preventive actions should be taken?
    """

    try:
        warning_result = agent.ask(warning_prompt)
        print("⚠️  Warning Analysis:")
        print("-" * 70)
        print(warning_result["answer"])
        print()

    except Exception as e:
        print(f"❌ Error in warning analysis: {e}\n")

    # Step 5: Memory continuity test
    print("\n🔍 PHASE 3: Memory Continuity Test")
    print("-" * 70)

    # Ask question that requires context from previous interactions
    memory_test_questions = [
        "What was the main service that had issues?",
        "How many times did the payment processing fail?",
        "What was the connection pool status trend?",
    ]

    for question in memory_test_questions:
        try:
            memory_result = agent.ask(question)
            print(f"\n❓ Q: {question}")
            print(f"💭 A: {memory_result['answer'][:150]}...")  # Truncate

        except Exception as e:
            print(f"❌ Error: {e}")

    # Step 6: Generate action items
    print("\n\n" + "=" * 70)
    print("🎯 ACTION ITEMS SUMMARY")
    print("=" * 70)

    action_prompt = """
    Based on all the log analysis we've done in this session:

    Generate a prioritized action plan with:
    1. Immediate actions (P0 - critical)
    2. Short-term fixes (P1 - important)
    3. Long-term improvements (P2 - preventive)

    Be specific and actionable.
    """

    try:
        action_result = agent.ask(action_prompt)
        print("\n📋 Prioritized Action Plan:")
        print("-" * 70)
        print(action_result["answer"])
        print()

    except Exception as e:
        print(f"❌ Error generating action plan: {e}\n")

    # Step 7: Show memory statistics
    print("=" * 70)
    print("📊 SESSION STATISTICS")
    print("=" * 70)
    print(f"\n✅ Log Entries Analyzed: {len(log_entries)}")
    print(f"✅ Errors Detected: {len(errors)}")
    print(f"✅ Warnings Detected: {len(warnings)}")
    print(f"✅ Session ID: {session_id}")
    print("✅ Memory Enabled: Yes")
    print("\n💡 Next Steps:")
    print("   1. Use the same session_id to continue analysis")
    print("   2. Agent will remember all context from this session")
    print("   3. Add new logs and ask follow-up questions")

    print("\n" + "=" * 70)
    print("✅ Log Analysis Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()

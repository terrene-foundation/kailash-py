"""
A2A Code Review System with Ollama

This example demonstrates a multi-agent code review system where different
Ollama models specialize in different aspects of code review.
"""

import time

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


class CodeReviewSystem:
    """Multi-agent code review system using Ollama models."""

    def __init__(self):
        self.workflow = self._create_workflow()
        self.runtime = LocalRuntime()
        self.memory_pool = self.workflow._node_instances["code_review_memory"]
        self.coordinator = self.workflow._node_instances["review_coordinator"]

    def _create_workflow(self) -> Workflow:
        """Create the code review workflow."""
        workflow = Workflow(
            workflow_id="code_review_system",
            name="Ollama Code Review System",
            description="Multi-agent code review with specialized Ollama models",
        )

        # Shared memory for code review findings
        workflow.add_node("code_review_memory", SharedMemoryPoolNode())

        # Coordinator for managing review process
        workflow.add_node("review_coordinator", A2ACoordinatorNode())

        # Security Reviewer - Using Llama for comprehensive analysis
        workflow.add_node(
            "security_reviewer",
            A2AAgentNode(),
            config={
                "agent_id": "security_llama",
                "agent_role": "security_reviewer",
                "provider": "ollama",
                "model": "llama3.2",
                "system_prompt": """You are a security code reviewer. Focus on:
1. Identifying security vulnerabilities (SQL injection, XSS, etc.)
2. Authentication and authorization issues
3. Data validation and sanitization
4. Secure coding practices
5. Potential attack vectors

Rate security issues as:
- CRITICAL (importance: 1.0): Immediate security vulnerabilities
- HIGH (importance: 0.8): Potential security risks
- MEDIUM (importance: 0.6): Security best practice violations
- LOW (importance: 0.4): Minor security improvements""",
                "attention_filter": {
                    "tags": ["security", "vulnerability", "risk"],
                    "importance_threshold": 0.6,
                    "window_size": 20,
                },
            },
        )

        # Performance Reviewer - Using Mistral for efficiency analysis
        workflow.add_node(
            "performance_reviewer",
            A2AAgentNode(),
            config={
                "agent_id": "performance_mistral",
                "agent_role": "performance_reviewer",
                "provider": "ollama",
                "model": "mistral",
                "system_prompt": """You are a performance optimization expert. Analyze:
1. Algorithm complexity and efficiency
2. Database query optimization
3. Memory usage and leaks
4. Caching opportunities
5. Bottlenecks and hot paths

Categorize findings as:
- CRITICAL (importance: 0.9): Major performance bottlenecks
- HIGH (importance: 0.7): Significant optimization opportunities
- MEDIUM (importance: 0.5): Moderate improvements possible
- LOW (importance: 0.3): Minor optimizations""",
                "attention_filter": {
                    "tags": ["performance", "optimization", "efficiency"],
                    "importance_threshold": 0.5,
                    "window_size": 15,
                },
            },
        )

        # Code Quality Reviewer - Using Phi for style and patterns
        workflow.add_node(
            "quality_reviewer",
            A2AAgentNode(),
            config={
                "agent_id": "quality_phi",
                "agent_role": "quality_reviewer",
                "provider": "ollama",
                "model": "phi",
                "system_prompt": """You are a code quality reviewer. Check for:
1. Code readability and maintainability
2. Design patterns and architecture
3. SOLID principles adherence
4. Documentation completeness
5. Test coverage and quality

Rate issues as:
- HIGH (importance: 0.7): Architectural problems
- MEDIUM (importance: 0.5): Maintainability issues
- LOW (importance: 0.3): Style improvements""",
                "attention_filter": {
                    "tags": ["quality", "maintainability", "architecture"],
                    "importance_threshold": 0.4,
                    "window_size": 25,
                },
            },
        )

        # Lead Reviewer - Synthesizes all findings
        workflow.add_node(
            "lead_reviewer",
            A2AAgentNode(),
            config={
                "agent_id": "lead_reviewer_llama",
                "agent_role": "lead_reviewer",
                "provider": "ollama",
                "model": "llama3.2",
                "system_prompt": """You are the lead code reviewer. Your responsibilities:
1. Synthesize findings from all specialist reviewers
2. Prioritize issues by severity and impact
3. Provide actionable recommendations
4. Create a comprehensive review summary
5. Suggest an overall verdict (Approve/Request Changes/Needs Major Revision)

Consider security issues as highest priority, followed by performance, then quality.""",
                "attention_filter": {
                    "tags": ["security", "performance", "quality", "critical", "high"],
                    "importance_threshold": 0.3,
                    "window_size": 50,
                    "preferred_agents": [
                        "security_llama",
                        "performance_mistral",
                        "quality_phi",
                    ],
                },
            },
        )

        # Connect all reviewers to shared memory
        reviewer_ids = [
            "security_reviewer",
            "performance_reviewer",
            "quality_reviewer",
            "lead_reviewer",
        ]
        for reviewer_id in reviewer_ids:
            workflow.connect(reviewer_id, "code_review_memory")
            workflow.connect(reviewer_id, "review_coordinator")

        return workflow

    def register_reviewers(self):
        """Register all reviewers with the coordinator."""
        reviewers = [
            {
                "id": "security_llama",
                "skills": [
                    "security_analysis",
                    "vulnerability_detection",
                    "secure_coding",
                ],
                "role": "security_reviewer",
            },
            {
                "id": "performance_mistral",
                "skills": ["performance_analysis", "optimization", "profiling"],
                "role": "performance_reviewer",
            },
            {
                "id": "quality_phi",
                "skills": ["code_quality", "architecture_review", "best_practices"],
                "role": "quality_reviewer",
            },
            {
                "id": "lead_reviewer_llama",
                "skills": ["synthesis", "prioritization", "decision_making"],
                "role": "lead_reviewer",
            },
        ]

        for reviewer in reviewers:
            self.coordinator.execute(action="register", agent_info=reviewer)
            print(f"Registered {reviewer['id']}")

    def review_code(self, code_snippet: str, context: str = "") -> dict:
        """Perform multi-agent code review."""
        results = {
            "code": code_snippet,
            "context": context,
            "reviews": {},
            "consensus": None,
            "summary": None,
        }

        print("\n" + "=" * 60)
        print("STARTING CODE REVIEW")
        print("=" * 60)
        print(f"Code length: {len(code_snippet)} characters")
        print(f"Context: {context if context else 'No context provided'}")

        # Phase 1: Security Review
        print("\n📔 Security Review (Llama 3.2)")
        print("-" * 40)

        try:
            security_result, _ = self.runtime.execute(
                self.workflow,
                parameters={
                    "security_reviewer": {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Review this code for security issues:\n\n```\n{code_snippet}\n```\n\nContext: {context}",
                            }
                        ],
                        "memory_pool": self.memory_pool,
                        "provider": "ollama",
                        "model": "llama3.2",
                    }
                },
            )

            if security_result.get("security_reviewer", {}).get("success"):
                response = security_result["security_reviewer"]["response"]["content"]
                print(response[:500] + "..." if len(response) > 500 else response)
                results["reviews"]["security"] = response
            else:
                print("Security review failed")

        except Exception as e:
            print(f"Security review error: {e}")

        time.sleep(1)

        # Phase 2: Performance Review
        print("\n\n⚡ Performance Review (Mistral)")
        print("-" * 40)

        try:
            perf_result, _ = self.runtime.execute(
                self.workflow,
                parameters={
                    "performance_reviewer": {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Analyze this code for performance issues:\n\n```\n{code_snippet}\n```\n\nContext: {context}",
                            }
                        ],
                        "memory_pool": self.memory_pool,
                        "provider": "ollama",
                        "model": "mistral",
                    }
                },
            )

            if perf_result.get("performance_reviewer", {}).get("success"):
                response = perf_result["performance_reviewer"]["response"]["content"]
                print(response[:500] + "..." if len(response) > 500 else response)
                results["reviews"]["performance"] = response
            else:
                print("Performance review failed")

        except Exception as e:
            print(f"Performance review error: {e}")

        time.sleep(1)

        # Phase 3: Code Quality Review
        print("\n\n✨ Code Quality Review (Phi)")
        print("-" * 40)

        try:
            quality_result, _ = self.runtime.execute(
                self.workflow,
                parameters={
                    "quality_reviewer": {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Review code quality and architecture:\n\n```\n{code_snippet}\n```\n\nContext: {context}",
                            }
                        ],
                        "memory_pool": self.memory_pool,
                        "provider": "ollama",
                        "model": "phi",
                    }
                },
            )

            if quality_result.get("quality_reviewer", {}).get("success"):
                response = quality_result["quality_reviewer"]["response"]["content"]
                print(response[:500] + "..." if len(response) > 500 else response)
                results["reviews"]["quality"] = response
            else:
                print("Quality review failed")

        except Exception as e:
            print(f"Quality review error: {e}")

        time.sleep(1)

        # Phase 4: Lead Review and Synthesis
        print("\n\n👨‍💼 Lead Reviewer Summary (Llama 3.2)")
        print("-" * 40)

        try:
            lead_result, _ = self.runtime.execute(
                self.workflow,
                parameters={
                    "lead_reviewer": {
                        "messages": [
                            {
                                "role": "user",
                                "content": "Synthesize all code review findings and provide a final verdict with prioritized action items.",
                            }
                        ],
                        "memory_pool": self.memory_pool,
                        "provider": "ollama",
                        "model": "llama3.2",
                    }
                },
            )

            if lead_result.get("lead_reviewer", {}).get("success"):
                response = lead_result["lead_reviewer"]["response"]["content"]
                print(response)
                results["summary"] = response

                # Extract shared context info
                shared_context = lead_result["lead_reviewer"]["a2a_metadata"][
                    "shared_context_used"
                ]
                print(
                    f"\n📊 Integrated findings from {shared_context} specialist reviewers"
                )
            else:
                print("Lead review failed")

        except Exception as e:
            print(f"Lead review error: {e}")

        # Analyze memory pool
        self._analyze_review_memory(results)

        return results

    def _analyze_review_memory(self, results: dict):
        """Analyze the review memory pool for insights."""
        print("\n\n" + "=" * 60)
        print("REVIEW MEMORY ANALYSIS")
        print("=" * 60)

        # Get high-importance findings
        critical_findings = self.memory_pool.execute(
            action="read",
            agent_id="analyzer",
            attention_filter={
                "importance_threshold": 0.8,
                "window_size": 20,
                "tags": ["security", "critical", "vulnerability"],
            },
        )

        if critical_findings["success"] and critical_findings["memories"]:
            print(f"\n🚨 Critical Findings ({len(critical_findings['memories'])})")
            for finding in critical_findings["memories"]:
                print(
                    f"\n- [{finding['agent_id']}] (importance: {finding['importance']})"
                )
                print(f"  {finding['content'][:150]}...")

        # Get all findings grouped by type
        all_findings = self.memory_pool.execute(
            action="read",
            agent_id="analyzer",
            attention_filter={"importance_threshold": 0.0, "window_size": 100},
        )

        if all_findings["success"]:
            # Group by tags
            tag_counts = {}
            for memory in all_findings["memories"]:
                for tag in memory["tags"]:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            print("\n📈 Finding Categories:")
            for tag, count in sorted(
                tag_counts.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  - {tag}: {count} findings")


def demo_code_reviews():
    """Demonstrate code review on different code snippets."""
    system = CodeReviewSystem()
    system.register_reviewers()

    # Example 1: Python code with potential issues
    print("\n\n" + "=" * 70)
    print("EXAMPLE 1: Python Web Handler")
    print("=" * 70)

    code1 = """
@app.route('/user/<id>')
def get_user(id):
    # Get user from database
    query = f"SELECT * FROM users WHERE id = {id}"
    cursor.execute(query)
    user = cursor.fetchone()

    if user:
        return {
            'id': user[0],
            'name': user[1],
            'email': user[2],
            'password': user[3]  # Returning password hash
        }
    return {'error': 'User not found'}, 404
"""

    system.review_code(code1, context="Flask web application endpoint")

    # Example 2: JavaScript code
    print("\n\n" + "=" * 70)
    print("EXAMPLE 2: JavaScript Data Processing")
    print("=" * 70)

    code2 = """
async function processUserData(users) {
    const results = [];

    for (let i = 0; i < users.length; i++) {
        const user = users[i];
        const profile = await fetchUserProfile(user.id);
        const posts = await fetchUserPosts(user.id);
        const friends = await fetchUserFriends(user.id);

        results.push({
            ...user,
            profile,
            posts,
            friends
        });
    }

    return results;
}
"""

    system.review_code(code2, context="Node.js API data aggregation function")


def main():
    """Run the code review demonstration."""
    print("=" * 70)
    print("OLLAMA MULTI-AGENT CODE REVIEW SYSTEM")
    print("=" * 70)
    print("\nThis demo shows how different Ollama models can collaborate")
    print("to provide comprehensive code reviews from multiple perspectives.")
    print("\nMake sure Ollama is running with these models:")
    print("- ollama pull llama3.2")
    print("- ollama pull mistral")
    print("- ollama pull phi")

    demo_code_reviews()

    print("\n\n" + "=" * 70)
    print("CODE REVIEW COMPLETE")
    print("=" * 70)
    print("\nThe multi-agent system provided:")
    print("✅ Security vulnerability analysis")
    print("✅ Performance optimization suggestions")
    print("✅ Code quality improvements")
    print("✅ Synthesized recommendations")
    print("\nEach agent focused on their specialty while sharing insights!")


if __name__ == "__main__":
    main()

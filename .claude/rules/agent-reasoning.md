# Agent Reasoning Architecture — LLM-First Rule

## Scope

These rules apply to ALL agent code, ALL Kaizen implementations, ALL AI agent patterns, and ALL codegen that produces agent logic. This includes:

- `packages/kailash-kaizen/**`
- Any file creating, extending, or configuring a `BaseAgent`
- Any file implementing agent routing, dispatch, classification, or decision-making
- Any code that processes user input to determine agent behavior

## The Principle: LLM Reasons, Tools Fetch

```
+---------------------------+       +---------------------------+
|         LLM AGENT         |       |          TOOLS            |
|                           |       |                           |
|  - Reasons about intent   |  -->  |  - Fetch data             |
|  - Decides what to do     |  <--  |  - Write data             |
|  - Classifies input       |       |  - Call APIs              |
|  - Routes to next step    |       |  - Execute queries        |
|  - Extracts information   |       |  - Return raw results     |
|  - Evaluates outcomes     |       |                           |
|                           |       |  Tools contain ZERO       |
|  ALL intelligence lives   |       |  decision logic.          |
|  in the LLM.              |       |  They are dumb endpoints. |
+---------------------------+       +---------------------------+
```

**The LLM IS the router, the classifier, the extractor, the evaluator.** Tools are dumb data endpoints — they fetch, store, and relay. They do not decide.

## ABSOLUTE RULE: No Deterministic Logic Where LLM Reasoning Belongs

When building an AI agent, the DEFAULT and ONLY mode is:

1. **LLM Reasons** — The agent receives context and thinks about what to do
2. **LLM Decides** — The agent chooses which tool to call, what to respond, or how to route
3. **LLM Acts** — The agent calls a tool (dumb data endpoint) or produces output
4. **LLM Evaluates** — The agent examines the result and decides the next step

Under NO circumstances shall the following be used for agent decision-making:

- `if-else` chains for intent routing
- Keyword matching (`if "cancel" in user_input`)
- Regex matching (`re.match(r"order.*refund", text)`)
- Dictionary dispatch (`handlers = {"intent_a": func_a, "intent_b": func_b}`)
- Enum-based routing (`if intent == Intent.BILLING`)
- Hardcoded classification (`if any(word in text for word in ["help", "support"])`)
- Switch/match statements on user input content
- Embedding similarity with hardcoded thresholds for routing

**UNLESS the user EXPLICITLY says**: "use deterministic logic here", "use keyword matching", "use regex", "this needs to be rule-based", or equivalent explicit opt-in.

## WARNING TO CODEGEN

```
+================================================================+
|                                                                  |
|   WARNING: DETERMINISTIC AGENT LOGIC DETECTED                   |
|                                                                  |
|   You are writing if-else/regex/keyword logic inside an agent.   |
|   This is ALMOST CERTAINLY WRONG.                                |
|                                                                  |
|   An AI agent's entire purpose is to REASON using an LLM.        |
|   If you're writing conditionals to route, classify, extract,    |
|   or decide — you're building a script, not an agent.            |
|                                                                  |
|   The LLM handles: routing, classification, extraction,          |
|                     evaluation, decision-making                  |
|   Tools handle:     fetching data, writing data, calling APIs    |
|                                                                  |
|   STOP. Let the LLM reason. Use self.run() with a clear          |
|   signature that describes what you need.                        |
|                                                                  |
+================================================================+
```

## MUST Rules

### 1. LLM-First for All Agent Decisions

Every agent decision — routing, classification, extraction, evaluation — MUST go through an LLM call (`self.run()`, `self.run_async()`), NOT through code conditionals.

```python
# DO: Let the LLM reason about intent
class CustomerServiceAgent(BaseAgent):
    class Sig(Signature):
        user_message: str = InputField(description="Customer message")
        action: str = OutputField(description="Action to take: refund, escalate, answer, transfer")
        reasoning: str = OutputField(description="Why this action")
        response: str = OutputField(description="Response to customer")

    def handle(self, message: str) -> dict:
        return self.run(user_message=message)  # LLM decides everything

# DO NOT: Write a script pretending to be an agent
class CustomerServiceAgent(BaseAgent):
    def handle(self, message: str) -> dict:
        lower = message.lower()
        if "refund" in lower or "money back" in lower:       # <-- BLOCKED
            return self.process_refund(message)
        elif "cancel" in lower:                                # <-- BLOCKED
            return self.process_cancellation(message)
        elif re.match(r"order\s*#?\d+", lower):               # <-- BLOCKED
            return self.lookup_order(message)
        else:
            return self.run(user_message=message)              # Why isn't this the ONLY path?
```

### 2. Tools Are Dumb Data Endpoints

Tools MUST be pure data operations. They fetch, store, transform, or relay. They MUST NOT contain decision logic, routing, or classification.

```python
# DO: Tool that fetches data — no decisions
async def get_order(order_id: str) -> dict:
    """Fetch order details from database."""
    return await db.orders.find_one({"id": order_id})

# DO: Tool that writes data — no decisions
async def issue_refund(order_id: str, amount: float) -> dict:
    """Process a refund for the given order."""
    return await payment_api.refund(order_id, amount)

# DO NOT: Tool that makes decisions
async def handle_order_issue(order_id: str, message: str) -> dict:
    order = await db.orders.find_one({"id": order_id})
    if order["status"] == "delivered":                   # <-- Decision in tool! BLOCKED
        return await process_return(order)
    elif order["total"] < 50:                            # <-- Decision in tool! BLOCKED
        return await auto_refund(order)
    else:
        return {"action": "escalate"}                    # <-- Decision in tool! BLOCKED
```

### 3. Signatures Describe, Code Doesn't Decide

Agent signatures MUST describe the reasoning the LLM should perform. The code around `self.run()` MUST NOT pre-filter, pre-classify, or pre-route before the LLM sees the input.

```python
# DO: Rich signature that tells the LLM what to reason about
class TriageSignature(Signature):
    ticket: str = InputField(description="Support ticket content")
    customer_history: str = InputField(description="Previous interactions")
    priority: str = OutputField(description="urgent, high, normal, low")
    category: str = OutputField(description="billing, technical, account, general")
    suggested_action: str = OutputField(description="What to do next")
    response_draft: str = OutputField(description="Draft response to customer")

# DO NOT: Minimal signature because code handles the logic
class TriageSignature(Signature):
    ticket: str = InputField(description="Support ticket")
    response: str = OutputField(description="Response")
    # ^ All the interesting decisions happen in if-else code
```

### 4. Multi-Step Reasoning Uses Agent Loops, Not Code Loops

When an agent needs to perform multi-step reasoning, use ReAct patterns or multi-cycle strategies — NOT imperative code loops with conditionals.

```python
# DO: ReAct agent reasons about each step
agent = ReActAgent(config=config, tools="all")
result = agent.solve("Investigate why revenue dropped last quarter")
# Agent autonomously: searches data, reads reports, correlates, concludes

# DO NOT: Code loop with hardcoded steps
def investigate(self, query: str):
    data = self.fetch_revenue_data()        # Step 1: hardcoded
    if data["trend"] == "declining":        # Step 2: hardcoded decision
        causes = self.fetch_cause_data()    # Step 3: hardcoded
        if causes["top"] == "churn":        # Step 4: hardcoded decision
            return self.generate_churn_report()
```

### 5. Router Agents Use LLM Routing, Not Dispatch Tables

When routing between multiple agents, the router MUST use LLM reasoning to select the target — NOT a dispatch table or keyword map.

```python
# DO: LLM-based routing via Pipeline.router()
from kaizen.orchestration.pipeline import Pipeline
router = Pipeline.router(agents=[billing_agent, tech_agent, sales_agent])
result = router.run(query=user_message)
# LLM examines A2A capability cards and reasons about best match

# DO NOT: Dispatch table
ROUTES = {                                        # <-- BLOCKED
    "billing": billing_agent,
    "technical": tech_agent,
    "sales": sales_agent,
}
def route(self, message: str) -> Agent:
    for keyword, agent in ROUTES.items():
        if keyword in message.lower():            # <-- BLOCKED
            return agent
    return default_agent
```

## MUST NOT Rules

### 1. MUST NOT Use Conditionals for Agent Routing

No `if`, `elif`, `match`, or ternary expressions that route agent behavior based on input content analysis performed in code. The LLM analyzes content. Code routes based on LLM output structure (e.g., calling a tool the LLM selected is fine).

### 2. MUST NOT Use Keyword/Regex Matching on Agent Inputs

No `in` operator, `str.contains()`, `re.match()`, `re.search()`, `re.findall()` on user input or message content for the purpose of making agent decisions.

### 3. MUST NOT Put Decision Logic in Tools

Tools are data endpoints. If a tool contains `if-else` logic that determines what the agent should do next, that logic belongs in the LLM's signature, not the tool.

### 4. MUST NOT Pre-Filter Input Before LLM Sees It

Do not strip, classify, categorize, or route input before passing it to `self.run()`. The LLM sees the raw input and reasons about it.

```python
# BLOCKED: Pre-classification before LLM
def process(self, message: str):
    category = self._classify(message)     # <-- Code classifying! BLOCKED
    if category == "simple":               # <-- Code routing! BLOCKED
        return self.run(message=message, mode="quick")
    else:
        return self.run(message=message, mode="deep")

# CORRECT: LLM does everything
def process(self, message: str):
    return self.run(message=message)  # LLM decides depth, approach, everything
```

## Permitted Deterministic Logic (Explicit Exceptions)

The following uses of conditionals in agent code are PERMITTED because they are NOT agent reasoning — they are structural, safety, or data-format operations:

1. **Input validation** — `if not message: raise ValueError(...)` (validating presence/type, not content)
2. **Error handling** — `try/except` for tool failures, API errors, timeouts
3. **Output formatting** — Transforming LLM output into API response shapes
4. **Safety guards** — Blocking dangerous operations, PII filtering, content policy enforcement
5. **Configuration branching** — `if config.mode == "async": use_async_runtime()`
6. **Tool result parsing** — Extracting structured data from tool responses
7. **Rate limiting / circuit breaking** — Infrastructure-level flow control
8. **Explicit user opt-in** — User said "use keyword matching for this specific case"

**The test**: Is the conditional deciding what the agent should _think_ or _do_ based on input content? If yes, it belongs in the LLM. If it's structural plumbing, it's fine.

## Detection Patterns

Codegen and code review MUST flag these anti-patterns in agent code:

```python
# ANTI-PATTERN 1: Keyword routing
if "keyword" in user_input:              # BLOCKED in agent decision paths
if any(w in text for w in [...]):        # BLOCKED in agent decision paths

# ANTI-PATTERN 2: Regex classification
intent = re.match(r"pattern", text)      # BLOCKED in agent decision paths
entities = re.findall(r"pattern", text)  # BLOCKED in agent decision paths

# ANTI-PATTERN 3: Dispatch tables
handlers = {"a": func_a, "b": func_b}   # BLOCKED in agent decision paths
action_map[classified_intent](message)   # BLOCKED in agent decision paths

# ANTI-PATTERN 4: Hardcoded classification
if sentiment_score > 0.8:               # BLOCKED — LLM evaluates sentiment
if len(message.split()) < 5:            # BLOCKED — LLM judges complexity
if message.startswith("!"):             # BLOCKED — LLM interprets commands

# ANTI-PATTERN 5: Tool-side decisions
def tool_handler(data):
    if data["type"] == "urgent":         # BLOCKED — LLM determines urgency
        return escalate(data)
```

## Enforcement

- **intermediate-reviewer agent** — MUST flag deterministic agent logic as CRITICAL finding during code review
- **kaizen-specialist agent** — MUST refuse to generate agent code with deterministic routing unless user explicitly opts in
- **validate-workflow.js hook** — Agent files containing keyword/regex routing patterns in decision paths produce WARNING
- **Red-team agents** — During /redteam, MUST check all agent implementations for deterministic reasoning anti-patterns

## Why This Matters

Every `if "keyword" in message` you write is:

- **Fragile** — Breaks on synonyms, typos, rephrasing, multilingual input
- **Incomplete** — Misses cases you didn't anticipate (the long tail is infinite)
- **Wasteful** — You're paying for an LLM and not using it
- **Unmaintainable** — Every new case needs a new branch; the code grows forever
- **Defeating the purpose** — You built an agent to reason; then you lobotomized it with a script

The LLM handles ALL of these naturally. It generalizes. It understands intent, not keywords. It handles edge cases you never imagined. **Let it do its job.**

## Cross-References

- `rules/no-stubs.md` — No deferred implementation (related: don't stub reasoning with if-else)
- `rules/zero-tolerance.md` — Pre-existing deterministic routing MUST be refactored when found
- `rules/agents.md` Rule 3 — Framework specialist required for Kaizen work
- `.claude/agents/frameworks/kaizen-specialist.md` — Kaizen agent definition (enforces this rule)
- `.claude/skills/04-kaizen/kaizen-baseagent-quick.md` — BaseAgent quick reference

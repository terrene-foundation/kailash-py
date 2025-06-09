Ensure that the following steps are completed within 1 session (/compact is fine).
Instruct Claude one step at a time, it will help if you give the directory and filename during the prompt (reduce the frequency of tool use by Claude).

## Development Phase
1. (Switch to plan mode) Instruct it based on:
    1. What you want to achieve. WARNING: Don’t be too narrow and technical because Claude is better than 100% of human developers in brainstorming, selecting, and deciding what is the best technical construct for your problem.
    2. YOU MUST take 1 - 2 steps back and give it a helicopter view from the perspective of a user, in terms of what the user wants to achieve, the constraints, and the performance requirements.
    3. Assume that whatever you once knew are OBSOLETE and NOT THE BEST PRACTICE. Ask it to evaluate the options/alternatives, with the advantages and disadvantages.
    4. Include this instruction: Check the reference folders for what API and design patter to use before you code. Create examples and tests that uses actual data and processes, instead of mock data and processes unless its for a strategic reason. Activate ollama if you have to. Do not resort to creating simplified examples and tests just to pass, but it is allowable if you need to use them to test for the original examples and tests to work. When you encounter mistakes, check the mistakes and reference folders first.
2. Check the plan, balance the options, select and adjust accordingly.
3. (Switch to edit mode) Instruct it to:
    1. Document the recommendation and implementation in ADR and relevant docs
    2. Continue with your option with adjustments, if any.
4. LEARN TO SPEED READ THE LOGS and focus on:
    1. The decisions that Claude made
    2. The errors that it encountered
    3. How it resolved it
    4. What it added (green highlight) and what it removed (red highlights)
5. (Post generation) Check the log summary (it will always give a summary) or ask Claude:
    1. Examples created? Did they all pass?
    2. Tests created? Did they all pass?
    3. Did you use any simplified examples and tests using mock data or processes? If so, explain why you did that and state clearly if it would affect real and production-ready deployments.
    4. You need to ask it specifically on the passing of examples or tests.
    5. Prompt it accordingly to ensure that examples, tests are created (without mock inputs and responses) and passed.
6. (Switch to plan mode) Instruct:
    1. Analyze whether we need to update mistakes and reference from what you learnt in this session so that Claude Code will not make the same coding errors in the future.
    2. Are there any design patterns or nodes that need to be updated in reference folder?
7. Inspect the plan then switch to edit mode and execute.
8. Ask Claude to update the master todo list and files in todos.
9. Ask Claude to align the CLAUDE.md files in the respective directories with the READMEs if required. Ensure that CLAUDE.md is always short and used for navigation and critical information purposes.

## Pre-release
1. Perform lint, black, isort, and ruff (automated in pre-commit hooks)
2. Build and deploy Sphinx documentation (automated in pre-commit hooks)
3. Update CHANGELOG.md
4. Commit and push to Github
5. Issue PR
6. If you are releasing it as a package:
    1. Prepare for release

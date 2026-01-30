# Pre-implementation (if using parallel worktrees)
1. Write the detailed instructions for each worktree. We are using CodeGen (Claude Code) to implement the codebase.
2. The instructions should be:
   - Independent to each worktree with the detailed referencing to the detailed todos.
   - Integration between the worktrees
3. Note that I will be pasting each instruction to a fresh terminal for each worktree accordingly.
4. Put these instructions into docs/04-codegen-instructions, naming them sequentially as 01-, 02-, for easy referencing.

# Pre-implementation (if using single repo)
1. Write the detailed instructions for CodeGen to implement the codebase.
2. Put these instructions into 04-codegen-instructions
   - use as many files as required and name them sequentially as 01-, 02-, for easy referencing.

# For context loading (fresh start)
1. Peruse docs/04-codegen-instructions and actively reference any docs so that you can achieve a high level of situational awareness on this project
   - (if you are the ...-backend worktree) Follow the instructions given in docs/04-codegen-instructions/01-backend-worktree.md and implement.
   - (if you are the ...-web worktree) Follow the instructions given in docs/04-codegen-instructions/02-web-worktree.md and implement.
   - (if you are the ...-app worktree) Follow the instructions given in docs/04-codegen-instructions/03-mobile-worktree.md and implement.
   - For reference (if required), consult docs/04-codegen-instructions/04-integration-guide.md to understand how the codebases will come together eventually.

# From todos to implementation
## NOTE: Spam this repeatedly until all todos/active have been moved to todos/completed)
1. You MUST always use the todo-manager to create the detailed todos FOR EVERY SINGLE TODO in 000-master.md
   - Review with subagents, before implementation.
2. Continue with the implementation of the next todo/phase using our subagents, following our procedural directives.
3. At the end of each phase, work with the todo-manager and update the detailed todos in todos/active.
   - Ensure that every task is verified with evidence before you close them, then move completed ones to completed/.
   - Ensure that you test comprehensively as you implement, with all tests passing at 100%
     - No tests can be skipped (make sure docker is up and running).
     - Do not rewrite the tests just to get them passing but ensure that it's not infrastructure issues that is causing the errors.
     - Always tests according to the intent of what we are trying to achieve and against users' expectations
       - Do not write simple naive technical assertions.
       - Do not have stubs, hardcodes, simulations, naive fallbacks without informative logs.
     - If the tests involve LLMs and are too slow, check if you are using local LLMs and switch to OpenAI
     - If the tests involve LLMs and are failing, please check the following errors first before skipping or changing the logic:
       - Structured outputs are not coded properly
       - LLM agentic pipelines are not coded properly
       - Only after exhausting all the input/output and pipeline errors, should you try with a larger model
4. When writing and testing agents, always remember to utilize the LLM's capabilities instead of naive NLP approaches such as keywords, regex etc.
   - Use ollama or openai (if ollama is too slow)
   - always check .env for api keys and model names to use in development.
     - Always assume that the model names in your memory are outdated and perform a web check on our model names in .env before declaring them invalid.
5. At the end of each phase, write your docs into ~/repos/dev/kailash_kaizen/src/kaizen/docs/developers
   - using as many subdirectories and files as required, and naming them sequentially 00-, 01- for easy referencing.
   - Your docs must focus on capturing the essence and intent, the 'what it is' and 'how to use it', and not status/progress/reports and other irrelevant information.

## Transpose docs to guidance
1. Use subagents and peruse ~/repos/dev/kailash_kaizen/src/kaizen/docs/developers in kaizen
2. Think deeply and analyze whether the docs in the following places need to be updated/created:
   - Subagent: ~/repos/dev/kailash_kaizen/.claude/agents/frameworks/kaizen-specialist.md
   - Skills: ~/repos/dev/kailash_kaizen/.claude/skills/04-kaizen
   - Full docs: ~/repos/dev/kailash_kaizen/sdk-users/apps/kaizen
   - Initialization: ~/repos/dev/kailash_kaizen/CLAUDE.md
3. Review thoroughly to ensure that there are no gaps

# Sync all worktrees to main (if using parallel worktrees)
1. Progressively sync all the worktrees (starting from backend, then web, and app) to the main worktree.
2. There may be files that are worked on by different worktrees.
   - Do not blindly adopt theirs/ours, please check for unique codebases between the different versions and integrate them accordingly.
3. Sync across all worktrees and ensure that they are all on the same commit
   - If there are any conflicts, please stop, and ensure that the unique codebase has been properly integrated into the combined one.

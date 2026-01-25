# Pre-implementation (if using parallel worktrees)
1. Write the detailed instructions for each worktree. We are using CodeGen (Claude Code) to implement the codebase.
2. The instructions should be:
   - Independent to each worktree with the detailed referencing to the detailed todos.
   - Integration between the worktrees
3. Note that I will be pasting each instruction to a fresh terminal for each worktree accordingly.
4. Put these instructions into 04-instructions, naming them sequentially as 01-, 02-, for easy referencing.
5. Peruse 04-instructions and actively reference any docs so that you can achieve a high level of situational awareness on this project
   - (if you are the ...-backend worktree) Follow the instructions given in docs/04-instructions/01-backend-worktree.md and implement.
   - (if you are the ...-web worktree) Follow the instructions given in docs/04-instructions/02-web-worktree.md and implement.
   - (if you are the ...-app worktree) Follow the instructions given in docs/04-instructions/03-mobile-worktree.md and implement.
   - For reference (if required), consult 04-instructions/04-integration-guide.md to understand how the codebases will come together eventually.

# Pre-implementation (if using single repo)
1. Write the detailed instructions for CodeGen to implement the codebase.
2. Put these instructions into 04-instructions
   - use as many files as required and name them sequentially as 01-, 02-, for easy referencing.
3. Peruse 04-instructions and actively reference any docs so that you can achieve a high level of situational awareness on this project
   - follow the instructions given and implement.

# From todos to implementation
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
4. When writing agents, always remember to utilize the LLM's capabilities instead of naive NLP approaches such as keywords, regex etc.
5. At the end of each phase, write your docs into src/.../docs/developers
   - using as many subdirectories and files as required, and naming them sequentially 00-, 01- for easy referencing.
   - Your docs must focus on capturing the essence and intent, the 'what it is' and 'how to use it', and not status/progress/reports and other irrelevant information.

## Test with actual LLM APIs (instead of Ollama)
1. Check .env for the api keys and model names to use. Switch the default LLM mode from Ollama to OpenAI.
2. The model to use during development is the OPENAI_DEV_MODEL
   - The valid/current model names in your memory are outdated.
     - I assure you that our model names in .env are present.
     - Please check for yourself before declaring the model name invalid.
   - If we are failing tests due to weak models, please check the following:
     - Structured outputs are not coded properly
     - LLM agentic pipelines are not coded properly
     - Only after exhausting all the input/output and pipeline errors, should you try with a larger model (e.g., OPENAI_FAST_MODEL, OPENAI_PROD_MODEL)
3. Re-run all the LLM related tests using the OpenAI models.

# Sync all worktrees to main (if using parallel worktrees)
1. Progressively sync all the worktrees (starting from backend, then web, and app) to the main worktree.
2. There may be files that are worked on by different worktrees.
   - Do not blindly adopt theirs/ours, please check for unique codebases between the different versions and integrate them accordingly.
3. Sync across all worktrees and ensure that they are all on the same commit
   - If there are any conflicts, please stop, and ensure that the unique codebase has been properly integrated into the combined one.

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
5. At the end of each phase, write your docs into the respective docs/:
   - for kailash sdk: project root
   - for dataflow: apps/kailash-dataflow
   - for kaizen: apps/kailash-kaizen
   - for nexus: apps/kailash-nexus
   - using as many subdirectories and files as required, and naming them sequentially 00-, 01- for easy referencing.
   - Your docs must focus on capturing the essence and intent, the 'what it is' and 'how to use it', and not status/progress/reports and other irrelevant information.
6. Deliberate carefully with agents and red team agents on the guidance docs
   - Remember what each guidance doc is for
     - claude agents: procedures, logic, why, critical information
     - claude skills: details of the how and what
     - sdk-users docs: complete deep dive details documentation as last resort
   - Then inspect each of these docs and update, concisely and accurately:
     - project root CLAUDE.md (entrypoint for codegen to know how to use sdk and frameworks, agents, skills, hooks etc.)
     - dataflow
       - agents: .claude/agents/frameworks/dataflow-specialist.md
       - skills: .claude/skills/02-dataflow
     - kaizen
       - agents: .claude/agents/frameworks/kaizen-specialist.md
       - skills: .claude/skills/04-kaizen
     - nexus
       - agents: .claude/agents/frameworks/nexus-specialist.md
       - skills: .claude/skills/03-nexus
     - sdk-users
       - main docs
       - framework docs in apps/

# Sync all worktrees to main (if using parallel worktrees)
1. Progressively sync all the worktrees (starting from backend, then web, and app) to the main worktree.
2. There may be files that are worked on by different worktrees.
   - Do not blindly adopt theirs/ours, please check for unique codebases between the different versions and integrate them accordingly.
3. Sync across all worktrees and ensure that they are all on the same commit
   - If there are any conflicts, please stop, and ensure that the unique codebase has been properly integrated into the combined one.

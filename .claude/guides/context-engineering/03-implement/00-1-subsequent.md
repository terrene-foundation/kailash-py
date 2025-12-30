# Adding new features/Resolving new issues
1. Discuss the following new features/issues:
   -
2. Please work with subagents and document the plans into 02-plans, following our sequential numbering convention.
3. You MUST always use the todo-manager to create the detailed todos FOR EVERY SINGLE TODO in 000-master.md
   - Review with subagents, before implementation.
4. Continue with the implementation of the next todo/phase using our subagents, following our procedural directives.
5. At the end of each phase, work with the todo-manager and update the detailed todos in todos/active.
   - Ensure that every task is verified with evidence before you close them, then move completed ones to completed/.
   - Ensure that you test comprehensively as you implement, with all tests passing at 100%
     - No tests can be skipped (make sure docker is up and running).
     - Do not rewrite the tests just to get them passing but ensure that it's not infrastructure issues that is causing the errors.
     - Always tests according to the intent of what we are trying to achieve and against users' expectations
       - Do not write simple naive technical assertions.
       - Do not have stubs, hardcodes, simulations, naive fallbacks without informative logs.
6. When writing agents, always remember to utilize the LLM's capabilities instead of naive NLP approaches such as keywords, regex etc.
7. At the end of each phase, write your docs into src/.../docs/developers
   - using as many subdirectories and files as required, and naming them sequentially 00-, 01- for easy referencing.
   - Your docs must focus on capturing the essence and intent, the 'what it is' and 'how to use it', and not status/progress/reports and other irrelevant information.

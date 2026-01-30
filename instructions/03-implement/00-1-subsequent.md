# New features
Always work with subagents in everything that you do.

1. please review one more time with subagents and document the details in  ~/repos/dev/kailash_kaizen/apps/kailash-kaizen/docs/plans/
  05-azure-unified
     - Use as many subdirectories and files as required
     - Name them sequentially as 01-, 02-, etc, for easy referencing

2. After that, work with todo-manager, following our procedural directives, and create detailed todos for EVERY todo/task required.
   - The detailed todos should be created in ~/repos/dev/kailash_kaizen/apps/kailash-kaizen/todos/active
   - Review after you are done to ensure that you leave no gaps behind.

3. Continue with the implementation using our subagents, following our
procedural directives.

4. At the end of each phase, work with the todo-manager and update the detailed todos in todos/active.
   - Ensure that every task is verified with evidence before you close them, then move completed ones to completed/.
   - Ensure that you test comprehensively as you implement, with all tests passing at 100%
     - No tests can be skipped (make sure docker is up and running).
     - Do not rewrite the tests just to get them passing but ensure that it's not infrastructure issues that is causing the errors.
     - Always tests according to the intent of what we are trying to achieve and against users' expectations
       - Do not write simple naive technical assertions.
       - Do not have stubs, hardcodes, simulations, naive fallbacks without informative logs.

5. When writing agents, always remember to utilize the LLM's capabilities
instead of naive NLP approaches such as keywords, regex etc.

6. At the end of each phase, check and update the following docs:
   - ~/repos/dev/kailash_python_sdk/CLAUDE.md
     - Must be concise and short, focus on being entrypoint to subagents, skills, and sdk-users full docs.

   # If you are working on the kaizen framework
   - ~/repos/dev/kailash_python_sdk/.claude/agents/frameworks/kaizen-specialist.md
     - Focus on policies, processes and not details. Know what and where to invoke the skills
     - and how to fallback to sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/.claude/skills/04-kaizen/
     - Focus on the critical information that allows subagents to competently orchestrate and complete their tasks
     - Details that are less likely to be used reside in sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/sdk-users/apps/kaizen
     - FULL and complete documentation of the solution and codebase
     - focus on developer "what it is" and "how to use it" and
     - don't include other irrelevant information such as progress/status/reports etc.

   # If you are working on the dataflow framework
   - ~/repos/dev/kailash_python_sdk/.claude/agents/frameworks/dataflow-specialist.md
     - Focus on policies, processes and not details. Know what and where to invoke the skills
     - and how to fallback to sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/.claude/skills/02-dataflow/
     - Focus on the critical information that allows subagents to competently orchestrate and complete their tasks
     - Details that are less likely to be used reside in sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/sdk-users/apps/dataflow
     - FULL and complete documentation of the solution and codebase
     - focus on developer "what it is" and "how to use it" and
     - don't include other irrelevant information such as progress/status/reports etc.

   # If you are working on the nexus framework
   - ~/repos/dev/kailash_python_sdk/.claude/agents/frameworks/kaizen-nexus.md
     - Focus on policies, processes and not details. Know what and where to invoke the skills
     - and how to fallback to sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/.claude/skills/03-nexus/
     - Focus on the critical information that allows subagents to competently orchestrate and complete their tasks
     - Details that are less likely to be used reside in sdk-users full docs.
   - ~/repos/dev/kailash_python_sdk/sdk-users/apps/nexus
     - FULL and complete documentation of the solution and codebase
     - focus on developer "what it is" and "how to use it" and
     - don't include other irrelevant information such as progress/status/reports etc.

# Implementation <> Validation Iteration
1. Review your implementation
   - Test all the workflows end-to-end
     - using backend api endpoints only
     - using frontend api endpoints only
     - using browser via Playwright only
2. Ensure that your review includes tests are written from the user workflow perspectives.
   - Workflows must be detailed step by step.
   - Generate the tests and metrics for each step, including the transitions between steps.
3. (If parity required)
   - Ensure that our new modifications are on par with the old one
   - Do not compare codebases using logic
   - Test run the old system via all required workflows and write down the output
     - Run multiple times to get a sense whether the outputs are
       - deterministic (e.g. labels, numbers)
       - natural language based
     - For all natural language based output:
       - DO NOT TEST VIA SIMPLE assertions using keywords and regex
         - You must use LLM to evaluate the output and output the confidence level + your rationale
         - The LLM keys are in .env, use gpt-5.2-nano
4. Give me a detailed checklist based on your tests so that I can validate it manually.

# Specific validation
1. Check @narrated_financials/instructions/00-manual_checklist/00-initial.md
   - work out the step by step testing from a user perspective, interacting with frontend components
     - Ensure that you replicate exactly every action and expectation from the user journey
     - ensure everything is returned/processed AS PER EXPECTED from user perspective
   - Understand my intent for this test and not just following my instructions to the word
     - Update your understand if there's nuances and better ways of doing it
       - Then update your manual testing guide accordingly.
2. Test the entire workflow using actual sample documents you can find in this repository
   - docs, pdfs on financial statements to be processed and auditor guidance
   - To ensure that everything is integrated and working as intended, do 3 types of tests
     - using backend api endpoints only
     - using frontend api endpoints only
     - using browser via Playwright only
   - Please report the detailed step by step user actions and the api endpoints you tested
     - including the components that are triggered and that they are working if not api endpoints.
   - Ensure that you replicate exactly every action and expectation from the user journey and ensure everything is returned/processed AS PER EXPECTED
   - You must work on the errors iteratively until all the tests passed.

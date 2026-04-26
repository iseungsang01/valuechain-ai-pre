# Draft: Gemini API Integration for Ralph Loop

## Goal
Integrate Gemini 3.1 Pro via API into the existing `ralph_loop.sh` to replace the mock agent. The agent should be able to read the prompt, generate code, and write it to the file system autonomously.

## Scope
**IN:**
- Create a Python script (`agent.py`) using `urllib` (no external dependencies) to call Gemini API.
- Use XML tagging format (`<file path="...">`) for the LLM to output files safely.
- Modify `ralph_loop.sh` to pipe prompt into `python agent.py`.
- Add instructions on how to run with `GEMINI_API_KEY`.

**OUT:**
- Converting `ralph_loop.sh` to PowerShell (sticking to Git Bash implementation for now).
- Installing third party libraries (e.g., `google-generativeai`).

## Technical Approach
1. **XML Parsing**: `agent.py` will instruct the Gemini model to output file creations inside `<file path="filename">...</file>` blocks.
2. **Python Regex**: Use `re.finditer` to parse the output and create directories/files automatically.
3. **Environment Variables**: Use `os.environ.get("GEMINI_API_KEY")`.
4. **Shell Hook**: Update `ralph_loop.sh` -> `cat "$TEMP_PROMPT" | python agent.py`.

## Test Strategy
- The loop already has a mock `test_command`. We will update `RALPH_TASK.md` to have a slightly more real test (e.g., `python test_calc.py`) to verify the loop can recover from an error and succeed.
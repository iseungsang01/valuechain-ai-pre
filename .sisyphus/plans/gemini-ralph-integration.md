# Work Plan: Gemini API Integration for Ralph Loop

## 1. Goal & Context
Integrate the Gemini 3.1 Pro API into the existing `ralph_loop.sh` framework to replace the mock agent with a functioning, autonomous AI coding agent. The agent must read prompts, generate code, and securely write files to the local file system.

## 2. Scope Boundaries
**IN:**
- Creating a zero-dependency Python script (`agent.py`) using `urllib`.
- Modifying `ralph_loop.sh` to execute the Python script.
- Implementing robust, regex-based XML tag parsing for file generation.
- Validating file paths to prevent directory traversal attacks (Path Traversal Protection).
- Updating `RALPH_TASK.md` to a realistic TDD scenario for end-to-end testing.

**OUT:**
- Converting `ralph_loop.sh` to PowerShell.
- Adding third-party libraries (e.g., `requests`, `google-generativeai`).
- Complex rollback logic for partial file writes (overwriting is acceptable for this MVP).

## 3. Technical Approach & Task Breakdown

### Task 1: Create `agent.py` (The Gemini Bridge)
- **File**: `agent.py`
- **Dependencies**: None (Use `os`, `sys`, `json`, `urllib.request`, `re`, `pathlib`).
- **Core Logic**:
  - Read `sys.stdin` for the prompt.
  - Require `GEMINI_API_KEY` from environment variables. Exit `1` if missing. (Note: Currently the system environment does not have GEMINI_API_KEY exported. Ensure the user sets it or the loop script handles it safely).
  - Structure the API payload using `generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent`. (Note: use gemini-1.5-pro-latest as the stable fallback for 3.1 Pro endpoint routing if needed).
  - Include a strong `systemInstruction` demanding output in `<file path="..."></file>` format.
  - Set `temperature: 0.1` for deterministic code generation.
  - **Security (Metis Guardrail)**: Validate paths to reject absolute paths or paths containing `..` to prevent directory traversal.
  - **Parsing (Metis Guardrail)**: Use robust Regex `re.finditer(r'<file path="([^"]+)">\n?(.*?)\n?</file>', text, re.DOTALL)` to extract files even if LLM outputs markdown noise.
  - Automatically create parent directories using `os.makedirs(..., exist_ok=True)`.
  - Log raw LLM response to `.ralph/last_response.log` for debugging.

### Task 2: Update Orchestrator (`ralph_loop.sh`)
- **File**: `ralph_loop.sh`
- **Modifications**:
  - Remove the mock `agent()` bash function.
  - Replace the `cat "$TEMP_PROMPT" | agent` line with `cat "$TEMP_PROMPT" | python agent.py`.
  - **Error Handling (Metis Guardrail)**: Capture the exit code of `agent.py`. If `$? -ne 0`, print a clear error (e.g., "API Error or Missing Key") and `exit 1` to prevent infinite hallucination loops.

### Task 3: Update Test Scenario
- **File**: `RALPH_TASK.md`
- **Modifications**:
  - Change the task from a simple `echo` to a real Python TDD task.
  - **Scenario**: "Write a Python calculator class in `calc.py` with `add` and `subtract` methods. Write tests for it in `test_calc.py`."
  - **Test Command**: `python test_calc.py` (Using standard Python assert or unittest so it fails naturally if unimplemented).

## 4. Final Verification Wave
- [ ] Run `ralph_loop.sh` without setting `GEMINI_API_KEY`. It MUST fail safely with a clear warning.
- [ ] Set `GEMINI_API_KEY` and run `ralph_loop.sh`.
- [ ] Verify `calc.py` and `test_calc.py` are successfully created.
- [ ] Verify the loop detects test success and terminates cleanly with code `0`.
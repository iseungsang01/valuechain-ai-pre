# Work Plan: Fix Port 9000 Conflict & Update Default Company

## Goal
Resolve the `port 9000` conflict by changing the backend and frontend default port to `8000`. Also, update the default selected company from "LG이노텍" to "SK하이닉스".

## Scope boundaries
- **IN**: Updating port configuration in `backend/main.py`, `frontend/app/page.tsx`, and `frontend/hooks/useAgentStream.ts`. Updating the default `targetNode` state in `frontend/app/page.tsx`.
- **OUT**: Any other architectural changes or logic changes in the supply chain graph AI.

## Tasks

### 1. Update Backend Port
**File:** `backend/main.py`
- Locate the `uvicorn.run()` call at the bottom of the file (around line 449).
- Change `port=9000` to `port=8000`.
- **QA Scenario:** Run `python backend/main.py` and verify it starts successfully on port 8000 without conflict.

### 2. Update Frontend Port Defaults & Company State
**File:** `frontend/app/page.tsx`
- Change the initial state for `targetNode`:
  ```typescript
  // Old
  const [targetNode, setTargetNode] = useState("LG이노텍");
  // New
  const [targetNode, setTargetNode] = useState("SK하이닉스");
  ```
- Change the hardcoded fallback API URL in the error message (around line 49):
  ```typescript
  // Old
  URL ({process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000"}).
  // New
  URL ({process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}).
  ```

### 3. Update Frontend Agent Stream Hook Port
**File:** `frontend/hooks/useAgentStream.ts`
- Locate the default API base URL assignment.
- Change it to port 8000:
  ```typescript
  // Old
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";
  // New
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  ```
- **QA Scenario:** Run the frontend with `npm run dev` and confirm the `useAgentStream` hook attempts to connect to port 8000. Start both services and ensure they communicate correctly.

## Final Verification Wave
- [ ] Backend starts on port 8000 successfully.
- [ ] Frontend uses port 8000 for backend requests.
- [ ] Frontend default selected node is "SK하이닉스".
- [ ] The supply chain graph successfully connects to the backend and streams data.
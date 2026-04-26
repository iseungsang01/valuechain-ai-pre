# Work Plan: Frontend UI Visualization & SSE Integration

## 1. Goal & Context
The goal of this phase is to build the initial Next.js Frontend for **ValueChain AI**. It will connect to the existing Backend SSE endpoint (`/api/analyze`) to receive real-time AI Agent thought processes and graph evaluations. The UI will feature a dashboard layout (Top: Time Slider, Left: Supply Chain Graph, Right: Agent Log) using React Flow to visualize the supply chain data structure.

## 2. Scope Boundaries
**IN:**
- Installing required visualization libraries (`@xyflow/react`, `dagre`).
- Defining TypeScript interfaces for the SSE Event Contract (`COLLECTING`, `ESTIMATING`, `EVALUATING`, `FEEDBACK`, `RESULT`).
- Creating a robust client-side SSE hook handling connections, reconnections, and state management.
- Implementing the three core UI components defined in `SPEC.md`:
  - **Quarterly Time Slider** (Top)
  - **Supply Chain Graph** (Left) using `dagre` for auto-layout.
  - **Agent Thought Process Log** (Right) with auto-scrolling.
- Assembling the layout in `app/page.tsx` or `app/analyze/page.tsx`.

**OUT:**
- Backend logic changes (Backend currently returns deterministic mock data; we will rely on this as-is).
- Complex authentication or deployment configurations.
- Real Gemini API calls from the frontend (Everything routes through the backend).

## 3. Technical Approach & Task Breakdown

### Task 1: Environment Setup & Dependencies
- **Files**: `frontend/package.json`
- **Actions**:
  - Run `npm install @xyflow/react dagre` (or yarn equivalent) in the `frontend` directory.
  - Run `npm install -D @types/dagre`.
  - Ensure Tailwind CSS is configured to parse the new components.

### Task 2: Type Definitions (The MVContract)
- **Files**: `frontend/types/index.ts` (New)
- **Actions**:
  - Define interfaces matching `backend/agents/models.py`.
  - `Node` (id, name, type, reported_cogs_krw).
  - `Edge` (id, source, target, estimated_revenue_krw, has_conflict).
  - `SupplyChainGraph` (target_quarter, nodes, edges).
  - Define an `SSEEvent` interface encompassing the Agent statuses.

### Task 3: SSE Client Hook Implementation
- **Files**: `frontend/hooks/useAgentStream.ts` (New)
- **Actions**:
  - Create a custom React hook `useAgentStream(targetNode, targetQuarter)`.
  - Use the native `EventSource` API connecting to `http://localhost:8000/api/analyze` (assuming backend runs locally).
  - Maintain states for: `logs` (array of messages), `graphData` (null until `RESULT` event), and `isAnalyzing` (boolean).
  - Handle distinct events:
    - `COLLECTING`, `ESTIMATING`, `EVALUATING`: Append parsed message to `logs`.
    - `FEEDBACK`: Append conflict details to `logs`.
    - `RESULT`: Update `graphData` state to trigger the visualizer.
  - Add robust error handling (close EventSource on error).

### Task 4: UI Components Implementation
- **Files**: `frontend/components/ui/...`
- **Actions**:
  - **ThoughtLog**: A scrollable `div` rendering the `logs` array. Automatically scroll to bottom when a new log is added using `useRef` and `useEffect`.
  - **SupplyChainGraph**: 
    - Wrap `@xyflow/react` in a `ReactFlowProvider`.
    - Use `dagre` to compute node positions dynamically (Left-to-Right layout) since the backend does not provide X/Y coordinates.
    - Style edges: Use red/dashed lines if `has_conflict` is true.
  - **TimeSlider**: A simple interactive header component letting the user select a quarter (e.g., "2024-Q3"). For now, changing this triggers a new SSE request.

### Task 5: Page Assembly & Layout
- **Files**: `frontend/app/page.tsx`
- **Actions**:
  - Convert to a `'use client'` component (or compose client components).
  - Layout Structure: Flexbox or CSS Grid.
    - Top bar: TimeSlider and an "Analyze" trigger button.
    - Main split view: Left takes up 70% width (React Flow), Right takes 30% width (ThoughtLog).

## 4. Final Verification Wave
- [ ] Dependency verification: `@xyflow/react` and `dagre` are in `package.json`.
- [ ] Build verification: Run `npm run build` in frontend to ensure no TypeScript or Hydration errors exist.
- [ ] Integration verification: 
  - Start FastAPI backend (`python main.py`).
  - Start Next.js frontend (`npm run dev`).
  - Click "Analyze".
  - Verify logs populate sequentially in the right panel.
  - Verify the graph renders correctly on the left panel upon the `RESULT` event.

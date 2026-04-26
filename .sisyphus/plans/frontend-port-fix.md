# Work Plan: Update Frontend API Base URL to Port 9000

## 1. Context and Objective
The backend port was changed to 9000, but the frontend still attempts to connect to `http://localhost:8000`. This causes a "Failed to fetch" connection error. We need to update the default API base URL in the frontend code.

## 2. Tasks

### Task 1: Update API Base URL in `useAgentStream.ts`
**File:** `frontend/hooks/useAgentStream.ts`
**Action:**
Change the default fallback port from 8000 to 9000.
```typescript
const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";
```

### Task 2: Update Error Message in `page.tsx`
**File:** `frontend/app/page.tsx`
**Action:**
Update the error message fallback URL so it accurately reflects port 9000.
```tsx
URL ({process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000"}).
```

## 3. Final Verification Wave
- [x] Check `useAgentStream.ts` for port 9000.
- [x] Check `page.tsx` for port 9000.
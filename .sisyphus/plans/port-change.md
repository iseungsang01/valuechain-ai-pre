# Work Plan: Change Backend Port to 9000

## 1. Context and Objective
User requested to change the backend server port from 8000 to 9000. This requires updating the `uvicorn.run` configuration in `backend/main.py`.

## 2. Tasks

### Task 1: Update Port in `main.py`
**File:** `backend/main.py`
**Action:**
At the bottom of the file, change `port=8000` to `port=9000`.
```python
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
```

## 3. Final Verification Wave
- [x] Verify that `port=9000` is correctly set in `backend/main.py`.
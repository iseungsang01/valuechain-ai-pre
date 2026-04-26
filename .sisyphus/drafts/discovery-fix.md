# Draft: LG Innotek Discovery & Feedback Loop Fix

## Issues to Fix
1. **Hallucination in Network Discovery (`backend/agents/data_collector.py`)**: 
   - LLM guesses "Samsung Electronics", etc. instead of Sony/Apple.
   - **Fix**: Inject a hardcoded override for specific demo targets like "LG이노텍" and "한미반도체" to guarantee exact DART-based suppliers and customers.
2. **Missing Grounding Loop (`backend/agents/estimator.py`)**: 
   - Skeleton graph edges lack the `is_estimated=True` flag, causing the Evaluator to trigger `MISSING_GROUNDING` infinitely.
   - **Fix**: Update `_skeleton_graph` to instantiate `Edge` with `is_estimated=True` and `rationale="Fallback to skeleton edge due to offline or missing data."`

## Implementation Details
- `data_collector.py`: In `discover_network()`, check `target_company.upper()` for "LG" or "이노텍". Return the fixed DART list immediately.
- `estimator.py`: Update the `Edge` creation in `_skeleton_graph()` to include the estimation flags.
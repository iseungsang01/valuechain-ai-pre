# Work Plan: Backend Spec Compliance — AGENT.md § 2 & SPEC.md § 2.3.1

## 1. Goal & Context
Oracle 검증 결과, 현재 백엔드는 ValueChain AI의 3대 핵심 기조를 절반만 충족하고 있습니다.
- **이중 회계 엣지**: ✅ 부합 (스키마 한정)
- **분기별 망 전체 동기화**: ⚠️ 부분 부합 (단일 기업 입력)
- **필수 출처 원칙(Grounding)**: ❌ **미부합** (가짜 URL 사용)
- **SPEC § 2.3.1 Conflict 검사**: ❌ **미구현**
- **SPEC § 2.3 재시도 루프(Max 2)**: ❌ **단절**

본 작업의 목표는 위 위반사항을 P0 → P1 → P2 순으로 수정하여 백엔드가 기획서 원본과 정확히 일치하도록 만들고, 동시에 24시간 해커톤 시연 안정성을 유지하는 것입니다.

## 2. Scope Boundaries

**IN:**
- `Evaluator`에 SPEC § 2.3.1의 누락된 **Conflict (A↔B 이중 회계 불일치)** 검사 구현
- `Evaluator`에 **Freshness** 검사 추가 (extraction_date가 분기 종료 후 1년 이상 경과 시)
- `main.py`의 **재추정 루프 복구** (최대 2회 재시도)
- **가짜 URL 폐기** → `DDGS`(이미 requirements.txt에 있음)로 실제 분기별 검색
- **경량 LLM 추출**로 검색 결과에서 P/Q/Revenue + 인용문 JSON 추출
- `Data Collector` 시그니처를 **분기 + 타겟 노드 → 망 전체 발견**으로 정비
- `Estimator`를 LLM 호출로 변경하되, 검색 실패 시 결정적 fallback 유지 (시연 안정성)
- 데드코드 삭제 (`researcher.py`, `generator.py`, `tech_eval.py`)

**OUT:**
- 프론트엔드 변경 (SSE 이벤트 페이로드 형태가 동일하므로 영향 없음)
- 신규 외부 API 의존성 추가 (DDGS, Gemini만 사용)
- DB / 캐싱 도입
- 인증 / 배포 설정
- 다국어 분기 표기(예 "24.2Q") 정규화 — `2024-Q3` 단일 포맷 유지

## 3. Technical Approach & Task Breakdown

### Phase A — P0: 명백한 SPEC 위반 즉시 수정

#### Task A.1: Evaluator에 Conflict (이중 회계 불일치) 검사 추가
- **Files**: `backend/agents/evaluator.py`, `backend/agents/models.py`
- **Actions**:
  - `models.py`의 `ConflictType` 리터럴에 `"DOUBLE_ENTRY_MISMATCH"` 추가.
  - `evaluator.py`에 `_check_double_entry_consistency(graph)` 메서드 신설.
  - 로직: 동일 (source, target) 쌍에 대해 양측이 보고한 grounding_sources의 `metric_type=REVENUE` 값과 `metric_type=COGS` 값을 비교. 차이가 임계치(예: 10%)를 넘으면 conflict 등록.
  - 이때 grounding이 한 쪽에만 있고 다른 쪽이 비어있다면 이는 `MISSING_GROUNDING`으로 이미 잡히므로 중복 보고하지 않음.
  - `evaluate_graph()`에서 호출 추가.

#### Task A.2: Evaluator Freshness 검사 추가
- **Files**: `backend/agents/evaluator.py`, `backend/agents/models.py`
- **Actions**:
  - `ConflictType`에 `"STALE_GROUNDING"` 추가.
  - `target_quarter`("2024-Q3")를 분기 종료 datetime("2024-09-30")으로 파싱하는 헬퍼 작성.
  - 모든 edge의 모든 `grounding_sources.extraction_date`를 검사. 분기 종료 이전이거나 12개월 이상 차이 나면 conflict 등록.

#### Task A.3: main.py 피드백 루프 복구 + 최대 2회 재시도
- **Files**: `backend/main.py`
- **Actions**:
  - `MAX_RETRIES = 2` 상수 추가.
  - `while attempts < MAX_RETRIES` 루프로 `evaluator.evaluate_graph()` → invalid면 `estimator.regenerate_graph(graph, feedback)` → 재평가 흐름 구현.
  - 매 재시도마다 `EVALUATING`/`FEEDBACK` 이벤트 별도 송출(현재 프론트엔드 ThoughtLog가 이미 timestamp별로 구분).
  - 2회 후에도 invalid면 `RESULT` 이벤트로 마지막 그래프와 `validation_warning` 필드를 함께 송출.
- **참고**: SSE 이벤트 타입은 추가하지 않고 기존 5종 유지 → 프론트엔드 변경 불필요.

#### Task A.4: Estimator에 `regenerate_graph()` 메서드 신설
- **Files**: `backend/agents/estimator.py`
- **Actions**:
  - 시그니처: `regenerate_graph(prev_graph: SupplyChainGraph, feedback: str) -> SupplyChainGraph`
  - 충돌이 있는 edge들의 `estimated_revenue_krw`를 보정하는 결정적 로직 (예: COGS_EXCEEDED인 경우 초과량을 비례 축소).
  - 추후 P2에서 LLM 기반 재추정으로 교체 예정.

### Phase B — P1: 실제 출처 도입 (정직한 데모)

#### Task B.1: 가짜 URL 제거 + DDGS 검색 도입
- **Files**: `backend/agents/data_collector.py`
- **Actions**:
  - 기존 mock URL 분기 전면 삭제.
  - `from duckduckgo_search import DDGS` import.
  - `_search_quarterly_news(company, quarter, max_results=5)` 메서드 신설:
    - 분기 표기 변환 헬퍼: `"2024-Q3"` → `"2024 3분기"`, `"2024 Q3"`, `"24년 3분기"` 다국어 쿼리 동시 발사.
    - DDGS로 검색하여 (title, url, snippet) 리스트 반환.
  - 환경 변수 `LIVE_GROUNDING=true`(default)일 때만 실행, false면 결정적 fallback.

#### Task B.2: 경량 LLM 추출기 — 본문 → P/Q/Revenue JSON
- **Files**: `backend/agents/data_collector.py`, `backend/agents/base.py`
- **Actions**:
  - `base.py`에 `prompt_model_for_json(prompt, schema)` 헬퍼 추가 — `response_mime_type="application/json"`로 호출.
  - `data_collector.py`에 `_extract_metrics_from_snippet(company, quarter, snippet, url)` 메서드.
  - 프롬프트: "이 본문에서 [회사]의 [분기] ASP/Revenue/COGS 수치를 찾아 grounding_source JSON 배열로 반환. 없으면 빈 배열."
  - 결과 파싱하여 `GroundingSource` 객체 리스트로 변환. URL은 검색 결과의 실제 URL 사용.
  - 본문 스크레이핑이 필요할 때만 `r.jina.ai`(Jina Reader) 사용 — DDGS snippet으로 충분하면 LLM 호출 1회로 끝냄.

#### Task B.3: Data Collector 메인 로직 통합
- **Files**: `backend/agents/data_collector.py`
- **Actions**:
  - `collect_quarterly_data(company, quarter)`를 `collect_network_data(target_company, quarter, suppliers, customers)` 형태로 확장.
  - 모든 노드에 대해 검색 + 추출을 병렬 실행 (asyncio.gather 또는 ThreadPoolExecutor).
  - 검색 0건이면 결정적 fallback 데이터 사용 + `[FALLBACK]` 플래그 로깅.

### Phase C — P2: 망 전체 추정 + 데드코드 정리

#### Task C.1: Estimator를 LLM 기반 망 합성으로 전환
- **Files**: `backend/agents/estimator.py`
- **Actions**:
  - `generate_graph(target_quarter, sources)`에서 grounding_sources를 LLM 프롬프트에 주입.
  - 프롬프트: "다음 출처를 바탕으로 [target_quarter]의 공급망 그래프를 JSON으로 생성. 노드/엣지는 다음 스키마에 맞춰…(SupplyChainGraph 스키마 인라인)."
  - `response_mime_type="application/json"`로 호출 → `SupplyChainGraph.model_validate()` 파싱.
  - LLM 호출 실패 시 결정적 fallback 그래프 유지 (시연 안정성).

#### Task C.2: 망 발견(Network Discovery) 단계 신설
- **Files**: `backend/agents/data_collector.py`, `backend/main.py`
- **Actions**:
  - `discover_network(target_company, quarter)` 메서드: 1회 LLM 호출로 타겟의 주요 공급사·고객사 5~7개 리스트 받기.
  - `main.py`: COLLECTING 단계 직전에 `network = collector.discover_network(...)` 호출.
  - 발견된 노드 리스트를 다음 단계 검색 입력으로 사용.

#### Task C.3: 데드코드 삭제
- **Files**: 삭제 대상
  - `backend/agents/researcher.py` (NameError 폭발 위험)
  - `backend/agents/generator.py` (미사용)
  - `backend/agents/tech_eval.py` (미사용)

### Phase D — 검증 작업

#### Task D.1: 통합 테스트 시나리오 갱신
- **Files**: `backend/test_run.py`
- **Actions**:
  - LIVE_GROUNDING=true / false 양쪽 시나리오 테스트.
  - Conflict 검사 4종(COGS_EXCEEDED / MISSING_GROUNDING / DOUBLE_ENTRY_MISMATCH / STALE_GROUNDING) 각각 트리거되는 테스트 케이스.
  - 재시도 루프가 최대 2회에서 종료되는지 확인.

## 4. Final Verification Wave

- [ ] `Evaluator`가 SPEC § 2.3.1의 3종 검사(Conflict / Over-estimation / Freshness & Grounding)를 모두 구현했는지 코드 grep 확인.
- [ ] `main.py`에서 `MAX_RETRIES=2` 루프가 실제 작동하는지 `test_run.py`로 시뮬레이션.
- [ ] `data_collector.py`에 `mock.com` 문자열이 한 글자도 남아있지 않은지 grep.
- [ ] `researcher.py`, `generator.py`, `tech_eval.py` 파일 부재 확인.
- [ ] `python backend/main.py`로 서버 기동 → `/api/analyze` 호출 시 SSE 이벤트가 5종 모두 정상 송출되는지 프론트엔드와 함께 e2e 검증.
- [ ] 환경 변수 `LIVE_GROUNDING=false`일 때 인터넷 없이도 결정적 그래프가 나오는지 확인 (시연 백업).
- [ ] 환경 변수 `LIVE_GROUNDING=true`일 때 grounding_sources의 url이 실제 클릭 가능한지 1개 이상 수동 확인.

## 5. 시연 안정성 가드

- 모든 외부 호출(DDGS, Gemini, Jina) 실패 시 **결정적 fallback** 보장.
- 환경 변수로 라이브 모드/Mock 모드 전환 가능.
- 재시도 루프가 무한 루프되지 않도록 attempts 카운터 강제.
- LLM JSON 파싱 실패 시 `try/except`로 fallback 그래프 사용.

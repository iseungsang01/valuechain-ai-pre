# ValueChain AI - Detailed Specification

이 문서는 `AGENT.md`의 기획을 구체화한 하위 상세 명세서입니다. 시스템 아키텍처, 에이전트 별 상세 로직, 피드백 루프, 그리고 비즈니스 및 UI/UX 명세를 정의합니다.

## 1. Business Viability (비즈니스 타당성)
*   **Target Audience (ICP):** 
    *   초기: IT/반도체/자동차 애널리스트 및 헤지펀드 매니저
    *   확장: 기업 전략기획/구매 부서 (경쟁사 원가 추정 및 공급망 리스크 관리)
*   **Value Proposition:** 파편화된 B2B 거래 기사, 공시, 관세청 데이터를 AI가 취합하여 분기별 P(단가) x Q(수량) 로직으로 치환, 공급망 맵을 10초 만에 생성. 인간 리서처가 1주일 걸릴 작업을 즉시 제공하여 10배 이상의 효율(10x Improvement) 달성.
*   **GTM & Pricing:** 
    *   초기 특정 섹터(예: 애플 밸류체인, 엔비디아 공급망) 무료 데모 오픈을 통해 트랙션 확보.
    *   기관 대상 B2B 구독 모델(SaaS, 월 $1,000 수준의 프리미엄 터미널) 및 API 형태 제공.

## 2. Multi-Agent Architecture (네트워크 동기화 기반)

시스템은 분기(Quarter)를 기준으로 전체 공급망 네트워크를 동시에 추정하고 검증하는 구조로 동작합니다.

### 2.1 Data Collector (데이터 수집 에이전트)
*   **역할:** 기업의 공급망 노드 탐색 및 타겟 분기에 맞는 원시 데이터 수집.
*   **Time-bound Searching:** 반드시 타겟하는 **연도와 분기(예: "24.2Q", "2024년 2분기")**를 키워드에 강제 포함하여 시계열 오차를 제거.
*   **필수 데이터 구조 (Grounding):**
    ```json
    {
      "metric_type": "ASP | Q | REVENUE",
      "target_quarter": "2024-Q3",
      "value": 150.5,
      "unit": "USD",
      "source_name": "블룸버그 뉴스",
      "url": "https://...",
      "date": "2024-10-05"
    }
    ```

### 2.2 Estimator (추론 및 계산 에이전트)
*   **분기별 통합 추정 (Quarterly Batch Estimation):** 전체 네트워크를 한 번에 계산.
*   **Edge 기반 이중 회계(Double-Entry) 구조:**
    *   데이터베이스나 상태 관리를 개별 기업의 매출/비용으로 나누지 않고, **관계선(Edge)** 단위로 관리합니다.
    *   `Edge(A -> B)`의 Value = **"A사의 B사향 3분기 매출"** == **"B사의 A사발 3분기 조달 비용"**으로 1:1 매핑되어 처리됩니다.
*   **추정 로직:** `Q (고객사 완제품 분기 생산량 × 탑재율) × P (최근 보정 ASP)`.

### 2.3 Evaluator (평가자 및 자가 피드백) ⭐️ 핵심 알파
단일 엣지의 오류를 넘어 **전체 망(Network)의 논리적 모순 찾기**를 수행합니다.
*   **망 정합성 평가 (Network Consistency Evaluation):**
    1.  **충돌 (Conflict):** A사의 보고서를 바탕으로 추정한 B사향 매출(100억) vs B사 수입 통계 기반 매입 비용(50억) 간의 불일치.
    2.  **과대 추정 (Over-estimation):** 추정된 B사의 하위 공급사(A, C, D) 매입 비용 총합이 B사의 공식 발표 분기 매출원가(COGS)를 초과하는 경우.
    3.  **Freshness & Grounding:** 사용된 단가(ASP) 정보가 1년 이상 지났거나 출처 URL이 없는 경우.
*   **전체 망 동기화 피드백 루프 (Macro-Feedback Loop):**
    *   충돌 발견 시 Evaluator는 프롬프트를 자동 생성(예: *"A-B 간 3분기 간극 50억 발생. B사의 재고 축적(Inventory Build-up) 여부를 재검색하여 엣지를 재계산할 것"*).
    *   무한 루프 방지를 위해 최대 재시도 횟수(Max Retries)는 2회로 제한.

## 3. Backend-Frontend Interface (SSE)

에이전트가 네트워크의 정합성을 맞춰가는(퍼즐을 푸는) 과정을 실시간 스트리밍합니다.
*   `[COLLECTING]`: 특정 분기의 공급망 데이터를 모으는 중.
*   `[ESTIMATING]`: 엣지 기반의 분기별 1차 네트워크 매핑 진행.
*   `[EVALUATING]`: 망 정합성 평가 중 (COGS 초과 여부, 엣지 값 충돌 여부).
*   `[FEEDBACK]`: 충돌 지점(Edge) 발견, 특정 기업의 재고/환율 데이터 재검색.
*   `[RESULT]`: 동기화 완료된 JSON 네트워크 데이터.

## 4. UI/UX Component Specifications

사용자가 에이전트의 AI 사고 과정과 결과를 직관적으로 체험할 수 있는 "Wow Point" 제공.

*   **Quarterly Time Slider:** 상단 슬라이더를 통해 '24년 1분기', '24년 2분기'를 이동하면 Supply Chain Graph의 선 굵기가 다이나믹하게 변동.
*   **Supply Chain Graph (React Flow 기반):**
    *   중앙 타겟, 좌측 공급사(Upstream), 우측 고객사(Downstream) 배치.
    *   **Conflict Highlighting:** 피드백 루프가 돌고 있는(충돌이 발생해 검증 중인) 엣지는 붉은색 점선으로 깜빡이게 표시.
*   **Data & Reference View (근거 패널):**
    *   엣지 클릭 시 상세 추정 논리 (`단가 $15 * 물량 300만개 = 4500만 달러`) 표시.
    *   각 숫자 옆 `[1]` Hover 시 즉시 출처/기사 확인.
*   **Agent Thought Process Log:**
    *   Evaluator가 망의 어떤 논리적 오류를 잡아내고 수정 지시를 내렸는지(Chain of Thought) 텍스트 뷰어로 실시간 공개하여 강력한 데모/설득 포인트 구성.
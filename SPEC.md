# ValueChain AI - Detailed Specification

이 문서는 `AGENT.md`의 기획을 구체화한 하위 상세 명세서입니다. 시스템 아키텍처, 에이전트 별 상세 로직, 피드백 루프, 그리고 UI/UX 명세를 정의합니다.

## 1. Multi-Agent Architecture

시스템은 크게 수집(Collector), 추론(Estimator), 평가(Evaluator) 역할을 하는 세 개의 주요 에이전트와 이를 조율하는 오케스트레이터로 구성됩니다.

### 1.1 Data Collector (데이터 수집 에이전트)
*   **역할:** 기업의 공급망 트리(Supply Chain Tree) 노드 탐색 및 원시 데이터(Raw Data) 수집.
*   **동작 방식 (2-Track):**
    1.  **Topology Search:** 타겟 기업의 주요 공급사(Upstream)와 고객사(Downstream) 목록 확립 (최소 1~2차 뎁스).
    2.  **Metric Search:** 식별된 각 관계(Edge)에 대한 '거래 품목', 'ASP(단가)', 'Q(수량/물량)' 관련 데이터 검색.
*   **필수 데이터 구조 (Grounding):**
    모든 수집 데이터는 다음 메타데이터를 반드시 포함해야 합니다.
    ```json
    {
      "metric_type": "ASP | Q | REVENUE",
      "value": 150.5,
      "unit": "USD",
      "source_name": "블룸버그 뉴스",
      "url": "https://...",
      "date": "2023-11-05"
    }
    ```

### 1.2 Estimator (추론 및 계산 에이전트)
*   **역할:** 파편화된 수집 데이터를 논리적 수식으로 연결하여 최종 재무 수치 도출.
*   **추정 로직:**
    *   **매출 (P × Q):** 단일 기사의 P(단가)에 의존하지 않고 과거 추이 보정. Q(물량)는 '고객사의 완제품 생산량 × 타겟 기업 부품 탑재율(Take-rate)' 등을 역산하여 추론.
    *   **비용 (Cost):** 전체 비용이 아닌 핵심 원자재(BOM) 상위 3~5개 위주로 추정하여 할루시네이션(과대추정) 방지.
*   **Confidence Score (신뢰도 점수):** 사용된 데이터의 최신성, 출처의 공신력(예: 공시자료 vs 일반 블로그)에 따라 추정치에 0~100점의 신뢰도 점수 부여.

### 1.3 Evaluator (평가자 및 자가 피드백) ⭐️ 핵심
*   **역할:** Estimator의 산출물과 도출 논리를 비판적으로 검토하고, 품질 미달 시 피드백 루프 가동.
*   **평가 기준 (Criteria):**
    1.  **Freshness:** 핵심 숫자(특히 단가)가 1년 이상 된 구형 데이터인가?
    2.  **Completeness:** P(단가) 또는 Q(수량) 중 명확한 근거 없이 가설로만 채워진 부분이 있는가?
    3.  **Logical Consistency:** 각 기업별 추정 매출의 총합이 타겟 기업의 과거 전체 매출/가이던스와 비교해 비정상적으로 크거나 작지 않은가?
    4.  **Grounding Check:** 수치에 연결된 URL 출처가 명시되어 있는가?
*   **Self-Reflection Loop:** 기준 미달 시, Evaluator는 구체적인 수정 지시가 담긴 프롬프트를 생성하여 Collector에게 재작업을 지시합니다. (예: *"B사향 물량(Q) 근거가 부족함. 2024년 B사 생산 가이던스 위주로 재검색 요망"*). 무한 루프 방지를 위해 최대 재시도 횟수(Max Retries)는 2~3회로 제한합니다.

## 2. Backend-Frontend Interface (SSE)

에이전트의 다단계 추론 과정 중 사용자 이탈을 막기 위해 SSE(Server-Sent Events)를 통해 실시간 상태를 스트리밍합니다.

*   **상태 이벤트 (State Events):**
    *   `[COLLECTING]`: "A사의 주요 고객사 데이터를 탐색 중입니다..."
    *   `[ESTIMATING]`: "도출된 데이터를 바탕으로 매출액을 산출하고 있습니다..."
    *   `[EVALUATING]`: "산출된 데이터의 최신성과 논리를 검증 중입니다..."
    *   `[FEEDBACK]`: "데이터가 부족하여 24년도 수출 통계를 기준으로 재검색합니다."
    *   `[RESULT]`: (최종 결과 전송 완료)

## 3. UI/UX Component Specifications

사용자가 복잡한 공급망과 재무 데이터를 직관적이고 투명하게 확인할 수 있도록 구성합니다.

*   **Supply Chain Graph (공급망 다이어그램):**
    *   구조: 중앙 타겟 기업, 좌측 공급사(Upstream), 우측 고객사(Downstream).
    *   시각화: 거래 규모(매출/비용 추정치)에 비례하여 노드 연결선(Edge)의 굵기 조절.
*   **Data & Reference View (세부 근거 패널):**
    *   그래프 내 특정 노드나 엣지 클릭 시 상세 정보 표출.
    *   추정 논리(예: `단가 $15 * 물량 300만개 = 4500만 달러`) 명시.
    *   각 숫자 옆에 `[1]`, `[2]` 형태의 Citation(각주) 제공 및 호버 시 출처 요약 및 링크 툴팁 표시.
*   **Thought Process Log (에이전트 사고 과정 로그):**
    *   Evaluator의 피드백 과정(어떤 이유로 데이터를 기각하고 재검색했는지)을 투명하게 보여주어 결과에 대한 신뢰도 상승.
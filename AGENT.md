# ValueChain AI - Agent Instructions

## 1. Project Overview & Business Value
ValueChain AI는 투자자, 애널리스트, 기관 리서처를 위한 **공급망 기반 기업 재무 추정 및 분석 에이전트(SaaS)** 입니다.
- **Problem & Market Clarity**: 기업의 B2B 거래 내역과 단가(ASP)/물량(Q) 정보는 파편화되어 있어 수작업 추정이 매우 어렵습니다. 이 문제를 해결하여 금융/투자 시장에서 압도적인 리서치 우위를 제공합니다.
- **Core Value (AI Integration)**: 단순히 기업의 재무제표를 조회하는 것을 넘어, AI가 흩어진 기사와 통계 데이터를 조합하여 "어느 회사에 얼마를 팔고(매출), 얼마를 사는지(비용)"를 세부적으로 분석합니다.
- **Business Viability**: 헤지펀드, 증권사 리서치 센터, 전략 기획 부서를 타겟으로 하는 B2B 구독 모델(SaaS)로 포지셔닝하며, 대체 불가능한 알파(Alpha) 창출 도구로 기능합니다.

## 2. Core Analytical Mechanics (핵심 분석 메커니즘)
- **분기별 망 전체 동기화 (Quarterly Network Consistency)**: 개별 기업을 따로 추정하지 않고, 특정 분기(Quarter)를 타겟으로 공급망 전체(Network)의 노드와 엣지를 한 번에 추정합니다.
- **이중 회계(Double-Entry) 엣지**: A사가 B사에게 납품한 금액은 "A사의 B사향 매출"이자 동시에 "B사의 A사발 조달 비용"이라는 단일 엣지(Edge)로 관리되어 완벽한 정합성을 추구합니다.
- **🚨 필수 출처 원칙 (Grounding)**: 모든 추정 데이터에는 실제 뉴스 기사, 공시 자료, 수출입 통계 등의 구체적인 출처(URL)가 필수적으로 첨부되어야 합니다.

## 3. Evaluator 기반 자가 피드백 시스템 (Self-Reflection Loop)
1차 분석 결과를 단방향으로 제공하는 것이 아니라, **평가자(Evaluator)** 로직이 도출 과정과 품질을 스스로 검증합니다.
- **전체 망 모순 평가**: "추정된 B사의 매입 비용 총합이 B사의 해당 분기 발표 매출원가(COGS)를 초과하는가?", "A-B 간의 매출/비용 추정치 간 간극이 있는가?"를 검사합니다.
- **자가 피드백**: 모순이나 논리적 비약(오래된 ASP 정보 등)이 발견되면, Evaluator는 구체적 프롬프트를 자동 생성하여 데이터 재수집 및 재계산을 지시합니다.

## 4. Tech Stack & Architecture
- **Frontend**: Next.js 16.2.4 (App Router), React 19.2.4, Tailwind CSS v4, Framer Motion, React Flow (망 시각화), TypeScript
- **Backend**: Python 3.x, FastAPI, Uvicorn, Google GenAI, SSE-Starlette
- **AI Architecture (Multi-Agent System)**: 
  - `Data Collector`: 신뢰할 수 있는 출처로부터 시계열(특정 분기) 기준 공급망 데이터 수집
  - `Estimator`: ASP, 물량, 매출 및 비용을 수식화(P x Q)하여 엣지 데이터 도출
  - `Evaluator`: 망 전체 정합성(Network Consistency) 오류 검증 및 피드백 루프 실행

## 5. UI/UX & Design System (사용자 중심 대시보드)
투자자가 복잡한 공급망 밸런스를 직관적으로 인지할 수 있도록 구성합니다.
- **대시보드 UI**: 특정 분기를 선택할 수 있는 타임 슬라이더와 Supply Chain Graph 제공.
- **Conflict Highlighting**: Evaluator가 충돌을 감지해 피드백 루프를 도는 엣지(Edge)를 깜빡이는 선으로 시각화하여 AI의 사고 과정을 투명하게 노출.
- **Typography & Color**: 가독성 최우선. 출처 링크와 계산식(P x Q)을 명확히 분리하여 신뢰성 있는 뷰 제공.

## 6. ⚠️ Version Control & Git Workflow
- 에이전트는 코드 변경이나 파일 수정 작업을 완료한 후, 반드시 원격 저장소에 `git add`, `git commit`, `git push`를 수행하여 변경 사항을 동기화해야 합니다.
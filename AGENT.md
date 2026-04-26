# Octo Code - AI Agent Instructions

## 1. Project Overview
Octo Code는 개발자 중심의 디자인 시스템을 갖춘 웹 애플리케이션입니다. 
터미널과 PR 환경에 익숙한 사용자들을 위해 어두운 테마(Dark-mode-first)를 기본으로 하며, 코드 중심의 정보 밀도가 높은 직관적인 UI를 제공합니다. 
AI 에이전트 기반의 기능(Google GenAI 검색 및 응답)을 FastAPI 백엔드를 통해 스트리밍(SSE)으로 제공하는 구조를 가집니다.

## 2. Tech Stack & Architecture
- **Frontend**: Next.js 16.2.4 (App Router), React 19.2.4, Tailwind CSS v4, Framer Motion, TypeScript
- **Backend**: Python 3.x, FastAPI, Uvicorn, Google GenAI, SSE-Starlette
- **Structure**: Monorepo 형태로 `frontend/`와 `backend/` 디렉토리가 분리되어 있습니다.

## 3. 🚨 Critical AI Agent Rules (프론트엔드)
- **Next.js 16.2.4 Breaking Changes**: 기존 Next.js 구조와 크게 다를 수 있습니다. 프론트엔드 코드(특히 라우팅, 캐싱, 서버 컴포넌트 등)를 작성하거나 수정하기 전에는 **반드시 `frontend/node_modules/next/dist/docs/` 내의 문서를 확인**해야 합니다. 폐기된(Deprecated) API 사용을 절대 금지합니다.
- **Tailwind CSS v4**: v4의 문법 및 설정 방식을 준수하여 스타일링해야 합니다.

## 4. UI/UX & Design System (디자인 엄격 준수)
UI/UX 수정 및 컴포넌트 생성 시 `octo-code-DESIGN.md`를 최우선으로 따릅니다.
- **테마**: Dark mode 기본 (Light mode 고려하지 않음).
- **Colors**: 
  - Background: `#0D1117` (Base) -> `#161B22` (Cards/Panels) -> `#1C2128` (Dropdowns)
  - Primary: `#2F81F7` (Mona Blue), Success: `#238636` (Growth Green)
- **Typography**: 
  - UI 텍스트: `Inter` (최대 600 weight)
  - 코드 관련 (Diff, SHA, 파일명, 터미널 등): `JetBrains Mono`
- **Elevation**: 그림자(Shadows) 효과 사용을 지양하고, 배경색의 밝기 차이(Color Layering)로 깊이를 표현합니다.
- **Border Radius**: 기능적 UI(버튼, 카드 등)는 최대 `6px`을 초과하지 않습니다. (칩/알림 제외)
- **Animations**: 전환 및 애니메이션 효과는 150ms 이하로 설정하여 빠르고 즉각적인 느낌을 주어야 합니다.

## 5. Backend Conventions
- FastAPI 구조와 Pydantic 모델을 사용하여 엄격한 타입 검사를 수행합니다.
- AI 응답 및 장기 실행 작업은 `sse-starlette`을 활용하여 프론트로 스트리밍(Streaming) 처리합니다.
- 외부 검색(DuckDuckGo, BS4) 로직은 에이전트(agents) 디렉토리 내에 모듈화하여 관리합니다.

## 6. ⚠️ Version Control & Git Workflow (필수 및 자동화)
- **에이전트는 코드 변경이나 파일 수정 작업을 완료한 후, 반드시 원격 저장소에 반영해야 합니다.**
- **작업이 완료되는 시점에 에이전트는 자동으로 `git add`, `git commit`, `git push`를 수행하여 변경 사항을 동기화해야 합니다.** (유저의 별도 승인 없이 수행)

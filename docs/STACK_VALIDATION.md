# 기술스택 유지보수성 검증 보고서

- 검증 기준일: 2026-02-13
- 범위: `docs/TRD.md`, `docs/PRD.md`, `docs/WBS.md`에 명시된 기술스택/운영 방식

## 1) 결론
- 현재 스택은 전반적으로 **유지보수 친화적**이다.
- 다만 아래 2개는 유지보수 난이도를 높일 수 있어 **사전 통제**가 필요하다.
  - ORCA/PowerBuilder 도구체인 의존(벤더/환경 의존성)
  - 커스텀 파서/규칙 기반 분석기의 도메인 난이도

## 2) 유료/벤더 종속성 검증

### 적합 (유료 락인 낮음)
- `SQLite/PostgreSQL` 저장소: 오픈소스 기반, 라이선스 비용 부담 낮음
  - 근거: `docs/TRD.md` 3장(IR Storage)
- `CSV/JSON/HTML` 리포트: 표준 포맷, 특정 상용 BI 종속 없음
  - 근거: `docs/TRD.md` 3장(Reporter), 5.5
- `CLI` 배치 실행: 서버/에이전트형 상용 플랫폼 의존이 없음
  - 근거: `docs/TRD.md` 2장, 6장 / `docs/PRD.md` FR-08

### 주의 (벤더/라이선스 확인 필요)
- `ORCA Script` 기반 추출은 PowerBuilder 생태계 의존성이 높다.
  - 의미: 개발/운영 환경 구성과 라이선스 정책이 조직 보유 현황에 좌우될 수 있음
  - 근거: `docs/TRD.md` 3장(Source Extractor), `docs/PRD.md` 11장 가정

## 3) 기술 난이도 검증

### 적합
- 아키텍처가 단계별 분리(`extract/parse/analyze/persist/report`)되어 유지보수 시 영향 범위가 작다.
  - 근거: `docs/TRD.md` 4장
- 테스트 전략(Unit/Integration/Regression/Performance)이 명시되어 변경 안정성 확보 구조가 있다.
  - 근거: `docs/TRD.md` 11장, `docs/WBS.md` 2.5

### 주의
- PowerScript 파싱/동적 SQL 해석은 본질적으로 고난도이며 오탐/미탐 관리 비용이 크다.
  - 근거: `docs/TRD.md` 12장, `docs/PRD.md` 14장
- 규칙/예외 룰셋 확장 운영이 누적되면 유지보수 복잡도가 증가한다.
  - 근거: `docs/TRD.md` 5.3, `docs/PRD.md` NFR-03/15장

## 4) 유지보수 최적화 권고 (필수)
1. 의존성/버전 고정
- Python 버전, 주요 라이브러리, DB 드라이버를 잠그고 재현 가능한 빌드를 유지한다.

2. 추출 계층 추상화
- ORCA 호출부를 어댑터로 분리하고 인터페이스를 고정해 벤더/환경 변경 충격을 최소화한다.

3. 규칙 거버넌스
- `rules/`에 룰 버전과 변경 이력(추가 이유, 영향 범위, 회귀 결과)을 강제 기록한다.

4. 골든셋 회귀 자동화 강화
- WBS의 회귀 자동화 항목을 CI 품질게이트로 연결해 정확도 하락을 차단한다.

5. 운영 문서화
- 라이선스/환경 전제(ORCA 실행 조건, 권한, 배치 스케줄)를 Runbook에 명문화한다.

## 5) 최종 판정
- 판정: **조건부 적합 (Go with controls)**
- 사유:
  - 무료/표준 기술 비중이 높아 장기 비용 리스크는 낮음
  - 단, PowerBuilder/ORCA 의존 및 파서 난이도는 통제 없으면 유지보수 난이도 상승 가능

## 6) 실행 연결 문서
- 개선 실행안: `docs/MAINTENANCE_IMPROVEMENT_PLAN.md`
- 개선 WBS 항목: `docs/WBS.md` 9장, 10장

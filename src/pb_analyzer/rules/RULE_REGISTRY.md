# Rule Registry

분석 규칙 추가/변경 시 아래 항목을 반드시 기록한다.

## Rule Lifecycle
1. 신규 규칙 제안
2. 영향 범위 명시(객체 타입, SQL 패턴, relation_type)
3. 골든셋 회귀 결과 첨부
4. 버전 태깅 및 배포

## Registry Template
| rule_id | version | owner | purpose | scope | risk | regression_result | introduced_at |
|---|---|---|---|---|---|---|---|
| ex.table-identifier-001 | 1.0.0 | analyzer-team | 테이블명 식별 보강 | embedded_sql | false positive 가능 | pass(precision +1.2%) | 2026-02-13 |

## Change Policy
- patch: 기존 규칙 버그 수정, 호환성 영향 없음
- minor: 예외 패턴 추가, 일부 결과 확장 가능
- major: 해석 방식 변경, 결과 호환성 깨질 수 있음

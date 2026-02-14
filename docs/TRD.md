# TRD (Technical Requirements Document)

## 1. 문서 정보
- 시스템명: PowerBuilder AS-IS 분석기 (`PB Analyzer`)
- 문서 버전: v0.1
- 작성일: 2026-02-13

## 2. 기술 목표
- PowerBuilder 추출 소스로부터 구조화된 중간 모델(IR) 생성
- 호출/화면이동/SQL/테이블 영향 관계를 기계적으로 산출
- 반복 실행 가능한 CLI 기반 분석 파이프라인 제공

## 3. 상위 아키텍처
1. Source Extractor
- ORCA Script 기반 추출물 수집
- 버전/모듈/실행 배치 정보 메타데이터화

2. Parser & Analyzer
- 토크나이징/규칙 파싱
- 엔티티/관계 추론
- SQL 정규화 및 테이블 식별

3. IR Storage
- SQLite 또는 PostgreSQL 저장
- 실행 단위(run_id) 분리 저장

4. Reporter
- 표준 리포트 생성(CSV/HTML/JSON)
- 영향분석 질의 템플릿 제공

## 4. 데이터 흐름
1. `extract`: PBL/PBR -> 텍스트 추출물 생성
2. `parse`: 객체/스크립트 파싱
3. `analyze`: 관계/SQL/영향도 추론
4. `persist`: IR DB 적재
5. `report`: 화면/함수/테이블 리포트 출력

## 5. 컴포넌트 요구사항

### 5.1 Extractor
- 입력: PowerBuilder 산출물 경로
- 출력: 객체별 텍스트 파일 + 메타데이터(manifest)
- 요구사항:
  - 추출 실패 객체 목록 수집
  - 동일 소스 재실행 시 동일 파일명 규칙 유지

### 5.2 Parser
- 입력: 추출 텍스트
- 출력: AST-lite 또는 토큰 시퀀스 + 파싱 결과
- 요구사항:
  - Window/UserObject/Menu/DataWindow/Event/Function 식별
  - 함수 선언/호출, 이벤트 핸들러 매핑
  - 구문 오류 허용(fail-soft) 및 오류 위치 로깅

### 5.3 Analyzer
- 입력: 파싱 결과
- 출력: 관계 레코드
- 요구사항:
  - `calls`, `opens`, `uses_dw`, `reads_table`, `writes_table`, `triggers_event`
  - SQL 문자열 정규화(공백/대소문자/주석 처리)
  - 테이블명 식별 규칙 + 예외 룰셋 지원

### 5.4 Storage
- 엔티티 최소 스키마:
  - `objects(id, run_id, type, name, module, source_path)`
  - `events(id, run_id, object_id, event_name, script_ref)`
  - `functions(id, run_id, object_id, function_name, signature)`
  - `relations(id, run_id, src_id, dst_id, relation_type, confidence)`
  - `sql_statements(id, run_id, owner_id, sql_text_norm, sql_kind)`
  - `sql_tables(id, run_id, sql_id, table_name, rw_type)`
  - `runs(run_id, started_at, finished_at, status, source_version)`
- 요구사항:
  - 인덱스: `relations(relation_type, src_id, dst_id)`, `sql_tables(table_name)`
  - 재실행 비교를 위한 `run_id` 버전 관리

### 5.5 Reporter
- 출력 포맷: `csv`, `json`, `html`
- 필수 리포트:
  - 화면 인벤토리
  - 이벤트-함수 맵
  - 테이블 영향도(테이블->화면/함수 역추적)
  - 화면 이동/호출 그래프
  - 미사용 객체 후보

## 6. CLI 요구사항
- 명령 예시:
  - `pb-analyzer extract --input <src> --out <work>`
  - `pb-analyzer analyze --manifest <file> --db <db>`
  - `pb-analyzer report --db <db> --out <dir> --format html`
  - `pb-analyzer run-all --input <src> --out <dir> --db <db>`
- 종료 코드:
  - `0`: 성공
  - `1`: 사용자 입력/환경 오류
  - `2`: 분석 단계 오류(부분 실패 포함)

## 7. 정확도/품질 요구사항
- 골든셋(20화면) 기준:
  - 정밀도 85% 이상
  - 재현율 75% 이상
- 동일 입력 반복 실행 시 결과 일치율 100%
- 핵심 리포트 생성 실패율 0%

## 8. 성능 요구사항
- 기준 데이터셋 전체 분석 30분 이내(목표)
- 메모리 상한선 초과 시 배치 분할 처리
- 대량 SQL 처리 시 스트리밍 적재 지원

## 9. 로깅/오류 처리
- 실행 단계별 로그(건수, 시간, 오류)
- 파싱 실패 객체는 skip 후 계속 진행
- 최종 요약 리포트에 실패 객체/원인/위치 포함

## 10. 보안/운영
- 소스코드 및 SQL 텍스트는 내부 보안 정책에 따라 저장
- 외부 전송 없이 로컬/사내 환경 실행 원칙
- 운영 배치 스케줄(일/주) 실행 및 결과 아카이브

## 11. 테스트 요구사항 연계
- Unit: 파서/SQL 정규화 규칙 테스트
- Integration: extract->analyze->report 파이프라인
- Regression: 골든셋 자동 비교
- Performance: 기준 데이터셋 부하 테스트

## 12. 오픈 이슈
- 동적 SQL 문자열 결합 패턴 처리 한계
- 사용자 정의 프레임워크/헬퍼 함수 해석 우선순위
- 그래프 시각화 기술 스택(정적 HTML vs 웹앱) 결정

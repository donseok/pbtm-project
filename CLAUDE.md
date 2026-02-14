# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PB Analyzer는 PowerBuilder 레거시 애플리케이션의 구조/의존관계/SQL 영향도를 자동 분석하는 정적 분석 도구다. ORCA Script로 추출한 소스를 파싱하여 호출/화면이동/SQL/테이블 관계를 IR(Intermediate Representation) DB에 저장하고 리포트를 생성한다.

## Commands

```bash
# Setup
python -m pip install -e .[dev]

# Lint & type check
ruff check src tests
mypy src

# Tests
python -m pytest tests/unit                          # unit tests only
python -m pytest tests/integration/pipeline          # integration tests
python -m pytest tests/unit/parser -k "test_name"    # single test

# Full quality gate (lint + type check + tests + golden-set metrics)
tools/ci/quality_gate.sh

# Golden-set metrics generation & check
python tools/ci/generate_golden_metrics.py --db <db> --golden tests/regression/golden_set/expected.json --output metrics.json
python tools/ci/check_golden_metrics.py --precision-min 0.85 --recall-min 0.75

# CLI 서브커맨드
pb-analyzer run-all --input <src> --out <work> --db <db> [--extractor auto] [--format html] [--orca-cmd <cmd>]
pb-analyzer extract --input <src> --out <work> [--extractor auto] [--orca-cmd <cmd>]
pb-analyzer analyze --manifest <manifest.json> --db <db> [--run-id <id>] [--source-version <ver>]
pb-analyzer report --db <db> --out <dir> --format <csv|json|html>
pb-analyzer diff --db <db> --run-old <old_run_id> --run-new <new_run_id>
pb-analyzer dashboard --db <db> [--host 127.0.0.1] [--port 8787] [--run-id <id>] [--limit 200]
```

## Architecture

5단계 파이프라인으로 구성된다: `extract → parse → analyze → persist → report`

```
src/pb_analyzer/
├── extractor/     ORCA toolchain 격리 (Protocol 기반 어댑터 패턴)
├── parser/        PowerScript 토크나이징/AST-lite (fail-soft), DataWindow SQL 파싱
├── analyzer/      관계 추론 (calls, opens, uses_dw, reads/writes_table, triggers_event), DataWindow 레코드 생성
├── storage/       SQLite IR 적재 (sqlite_store.py), run 간 diff 비교 (differ.py)
├── reporter/      CSV/JSON/HTML 리포트 6종 생성 (data_windows 포함)
├── dashboard/     웹 대시보드 (API 서버, 검색/필터, 그래프 시각화)
├── pipeline/      단계 오케스트레이션 (run_all, run_extract, run_analyze, run_report)
├── cli/           CLI 진입점, commands/ 하위에 서브커맨드별 핸들러
├── rules/         테이블 매핑/예외 규칙 (table_mapping.yaml), 규칙 레지스트리 (rule_registry.yaml)
├── observability/ 로깅 설정 (configs/logging/default.yaml 기반)
└── common/        공통 타입/예외 (models.py, exceptions.py)
```

### Key Design Decisions

- **Extractor Adapter**: `ExtractorAdapter` Protocol로 ORCA 의존성을 격리. 새 추출 도구 추가 시 Protocol 구현체만 작성. PBL 바이너리는 ORCA 우선, 미사용 시 binary string fallback.
- **Fail-soft parsing**: 파싱 에러 발생 시 해당 객체를 skip하고 계속 진행. 에러 위치를 로깅. 파일당 최대 에러 수는 `configs/parser/fail_soft.yaml`에서 설정.
- **DataWindow 파싱**: `.srd` 파일의 `retrieve="..."` 구문과 raw SQL 모두 감지. `update="..."` 에서 base_table 추출. 파싱 결과는 `ParsedDataWindow` → `DataWindowRecord`로 변환되어 `data_windows` 테이블에 적재.
- **Confidence 기반 관계 추론**: 관계 유형별 기본 confidence — `opens` 0.95, `uses_dw`/`reads_table`/`writes_table` 0.90, `calls` 0.85, `triggers_event` 0.70.
- **Table mapping**: `configs/analyzer/table_mapping.yaml`에서 SQL 정규화(대소문자, 공백, 주석) 및 테이블 예외 규칙 설정. `exception_rules`에 등록된 테이블은 분석에서 제외.
- **run_id versioning**: 모든 분석 결과가 `run_id`로 격리 저장되어 실행 간 비교/회귀 분석 가능.
- **Run diff**: `storage/differ.py`에서 두 run_id 간 객체, 관계, SQL, DataWindow를 set 비교하여 추가/삭제 항목 도출. `pb-analyzer diff` CLI로 실행.
- **Golden-set regression**: `tools/ci/generate_golden_metrics.py`로 골든셋 대비 precision/recall/F1을 계산. `tests/regression/golden_set/expected.json`에 기대 결과 정의.
- **Rule Registry**: 분석 규칙 변경 시 semver 버전, owner, regression 결과 필수. `configs/analyzer/rule_registry.yaml` 참조.
- **Exception handling**: `UserInputError`(종료코드 1)와 `AnalysisStageError`(종료코드 2)로 CLI 종료 코드 매핑. `__main__.py`에서 일괄 처리.

### IR Schema

`sql/schema/001_init.sql`에 정의, `sql/indexes/002_indexes.sql`에 인덱스 정의. 핵심 테이블: `runs`, `objects`, `events`, `functions`, `relations`, `sql_statements`, `sql_tables`, `data_windows`. `relations.relation_type`은 CHECK 제약으로 허용값 제한, `confidence`는 0.0~1.0 범위. `sql_statements.sql_kind`는 SELECT/INSERT/UPDATE/DELETE/MERGE/OTHER. UNIQUE 제약: `objects(run_id, type, name)`, `data_windows(run_id, object_id, dw_name)`.

### Configs

```
configs/
├── parser/fail_soft.yaml          # fail-soft 파싱 설정 (max_errors_per_file 등)
├── analyzer/rule_registry.yaml    # 규칙 거버넌스 (semver, 승인 정책)
├── analyzer/table_mapping.yaml    # SQL 정규화, 테이블 예외 규칙
└── logging/default.yaml           # 로깅 포맷/핸들러
```

## Code Style

- Python >= 3.11, ruff line-length=100, mypy strict mode
- 프로젝트 문서/주석은 한국어 사용
- Dataclass에 `frozen=True` 사용 (불변 값 객체). `PipelineOutcome`만 mutable (`field(default_factory=...)` 사용)
- `from __future__ import annotations` 사용
- 의존성: PyYAML만 런타임 의존. dev 의존: pytest, pytest-cov, ruff, mypy, types-PyYAML

## Quality Gates

CI(`.github/workflows/quality-gate.yml`)에서 PR/push to main 시 자동 실행:
1. ruff lint
2. mypy strict type check
3. Unit + Integration 테스트 (coverage 80% 이상)
4. Golden-set regression: precision >= 0.85, recall >= 0.75

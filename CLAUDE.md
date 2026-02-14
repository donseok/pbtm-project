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

# Golden-set metrics check
python tools/ci/check_golden_metrics.py --precision-min 0.85 --recall-min 0.75
```

## Architecture

5단계 파이프라인으로 구성된다: `extract → parse → analyze → persist → report`

```
src/pb_analyzer/
├── extractor/    ORCA toolchain 격리 (Protocol 기반 어댑터 패턴)
├── parser/       PowerScript 토크나이징/AST-lite (fail-soft: 구문오류 시 skip 후 계속)
├── analyzer/     관계 추론 (calls, opens, uses_dw, reads, writes, triggers_event)
├── storage/      SQLite(기본)/PostgreSQL IR 적재, run_id 기반 버전 관리
├── reporter/     CSV/JSON/HTML 리포트 생성
├── pipeline/     단계 오케스트레이션
├── cli/          CLI 진입점 (extract, analyze, report, run-all)
├── rules/        분석 규칙 (semver 버전관리, rule_registry.yaml 기반)
├── observability/ 로깅/메트릭
└── common/       공통 타입/유틸
```

### Key Design Decisions

- **Extractor Adapter**: `ExtractorAdapter` Protocol로 ORCA 의존성을 격리. 새 추출 도구 추가 시 Protocol 구현체만 작성.
- **Fail-soft parsing**: 파싱 에러 발생 시 해당 객체를 skip하고 계속 진행. 에러 위치를 로깅. 파일당 최대 에러 수는 `configs/parser/fail_soft.yaml`에서 설정.
- **run_id versioning**: 모든 분석 결과가 `run_id`로 격리 저장되어 실행 간 비교/회귀 분석 가능.
- **Rule Registry**: 분석 규칙 변경 시 semver 버전, owner, regression 결과 필수. `configs/analyzer/rule_registry.yaml` 참조.

### IR Schema

`sql/schema/001_init.sql`에 정의. 핵심 테이블: `runs`, `objects`, `events`, `functions`, `relations`, `sql_statements`, `sql_tables`, `data_windows`. `relations.relation_type`은 CHECK 제약으로 허용값 제한, `confidence`는 0.0~1.0 범위.

## Code Style

- Python 3.11 (pinned), ruff line-length=100, mypy strict mode
- 프로젝트 문서/주석은 한국어 사용
- Dataclass에 `frozen=True` 사용 (불변 값 객체)
- `from __future__ import annotations` 사용

## Quality Gates

CI(`.github/workflows/quality-gate.yml`)에서 PR/push to main 시 자동 실행:
1. ruff lint
2. mypy strict type check
3. Unit + Integration 테스트 (coverage 80% 이상)
4. Golden-set regression: precision >= 0.85, recall >= 0.75

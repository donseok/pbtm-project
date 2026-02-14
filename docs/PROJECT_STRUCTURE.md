# PROJECT STRUCTURE

## 설계 기준 (TRD 반영)
- 파이프라인 단계 분리: `extract -> parse -> analyze -> persist -> report`
- 컴포넌트 책임 분리: Extractor/Parser/Analyzer/Storage/Reporter
- 품질 축 분리: Unit/Integration/Regression/Performance 테스트 독립 운영
- 실행 결과 분리: `run_id` 기반 결과물은 `workspace/runs`, 리포트는 `workspace/reports`

## 추천 폴더 구조
```text
.
├── configs/                # 실행/분석 규칙 설정
├── docs/                   # PRD/TRD/WBS 및 아키텍처 문서
├── examples/               # 샘플 manifest/명령
├── sql/                    # IR 스키마/인덱스 정의
├── src/pb_analyzer/        # 애플리케이션 소스
│   ├── cli/                # CLI 진입점 및 서브커맨드
│   ├── pipeline/           # 단계 오케스트레이션
│   ├── extractor/          # ORCA 기반 추출
│   ├── parser/             # 토크나이징/파싱(fail-soft)
│   ├── analyzer/           # 관계/SQL/테이블 영향 분석
│   ├── storage/            # SQLite/PostgreSQL 적재
│   ├── reporter/           # CSV/JSON/HTML 리포트 생성
│   ├── dashboard/          # 웹 대시보드(API + UI, 검색/필터, 그래프 시각화)
│   ├── rules/              # 예외/매핑 규칙
│   ├── observability/      # 로깅/메트릭
│   └── common/             # 공통 타입/유틸
├── tests/
│   ├── unit/               # 파서/SQL 정규화 단위 테스트
│   ├── integration/        # extract->analyze->report 통합 테스트
│   ├── regression/         # 골든셋 자동 비교
│   └── performance/        # 부하/성능 테스트
├── tools/                  # 배치/CI/데이터 준비 스크립트
└── workspace/              # 실행 산출물 작업공간
```

## TRD 요구사항 매핑
- `5.1 Extractor` -> `src/pb_analyzer/extractor`, `examples/manifests`
- `5.2 Parser` -> `src/pb_analyzer/parser`, `tests/unit/parser`
- `5.3 Analyzer` -> `src/pb_analyzer/analyzer`, `configs/analyzer`
- `5.4 Storage` -> `src/pb_analyzer/storage`, `sql/schema`, `sql/indexes`
- `5.5 Reporter` -> `src/pb_analyzer/reporter`, `workspace/reports`
- `11. 테스트 요구사항` -> `tests/unit|integration|regression|performance`

## Extractor 입력 지원 (MVP+)
- 텍스트 추출 소스 폴더/파일: `.srw`, `.sru`, `.srm`, `.srd`, `.srf`, `.sql`, `.txt` 등
- 압축 파일: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`
- PowerBuilder 바이너리: `.pbl`, `.pbr`, `.pbd`
  - ORCA 명령 템플릿(`--orca-cmd` 또는 `PB_ANALYZER_ORCA_CMD`)이 있으면 ORCA 우선 사용
  - ORCA 미사용 시 binary string fallback으로 분석 가능한 텍스트를 최대한 복원

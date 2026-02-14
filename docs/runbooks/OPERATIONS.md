# 운영 Runbook

## 1. 목적
PB Analyzer 배치 운영 시 필요한 실행 조건, 장애 대응, 아카이브 절차를 정의한다.

## 2. 사전 점검
- Python 3.11 설치 확인
- ORCA/PowerBuilder 실행 환경 및 라이선스 상태 확인
- 입력 소스 경로 접근 권한 확인
- DB 경로(또는 PostgreSQL 연결정보) 확인

## 3. 표준 실행
```bash
pb-analyzer run-all --input <src> --out <work> --db <db> --extractor auto
```

### 입력 형태별 실행 예시
```bash
# 1) 텍스트 추출 소스 폴더(.srw/.sru/.srd ...)
pb-analyzer run-all --input ./pb-src --out ./workspace/job1 --db ./workspace/job1.db

# 2) 압축 파일(zip/tar.gz)
pb-analyzer run-all --input ./pb-src.zip --out ./workspace/job2 --db ./workspace/job2.db

# 3) PBL/PBR 바이너리 (ORCA 명령 템플릿 사용)
pb-analyzer run-all \
  --input ./legacy-pbl \
  --out ./workspace/job3 \
  --db ./workspace/job3.db \
  --extractor orca \
  --orca-cmd "orca-cli /in {input} /out {output}"
```

## 4. 배치 정책
- 일 배치: 야간 1회 실행
- 주 배치: 주간 전체 재분석 + 리포트 아카이브
- 아카이브 위치: `workspace/archive/YYYYMMDD`

## 5. 장애 대응
1. 종료 코드 확인 (`0`, `1`, `2`)
2. 실패 단계 추적 (`extract/parse/analyze/persist/report`)
3. 실패 객체 목록 확인 후 재시도
4. 동일 오류 3회 반복 시 규칙/파서 이슈로 분류하여 티켓화

## 6. 변경 관리
- 규칙 변경 시 `src/pb_analyzer/rules/RULE_REGISTRY.md` 업데이트
- 골든셋 회귀 통과 전 운영 반영 금지

## 7. 웹 대시보드
```bash
# 기본 실행
pb-analyzer dashboard --db ./workspace/job1.db

# 포트/호스트/기본 run_id 지정
pb-analyzer dashboard --db ./workspace/job1.db --host 0.0.0.0 --port 8787 --run-id <run_id>
```

- 브라우저 접속: `http://127.0.0.1:8787`
- API 예시:
  - `/api/runs`
  - `/api/all?run_id=<run_id>&limit=200`
  - `/api/all?run_id=<run_id>&limit=200&search=w_main&relation_type=opens`
  - `/api/graph?run_id=<run_id>&object_name=w_main`
  - `/api/table-impact?run_id=<run_id>&limit=100`

### 필터 파라미터
- `search`: 객체명/모듈/경로/관계타입 통합 검색
- `object_name`: 특정 객체명 기준 필터
- `table_name`: 특정 테이블명 기준 필터
- `relation_type`: `calls|opens|uses_dw|reads_table|writes_table|triggers_event`

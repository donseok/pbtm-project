# PB Analyzer 사용자 매뉴얼

## 1. 개요

PB Analyzer는 PowerBuilder 레거시 애플리케이션의 구조, 의존관계, SQL 영향도를 자동 분석하는 정적 분석 도구이다. ORCA Script로 추출한 소스를 파싱하여 호출/화면이동/SQL/테이블 관계를 IR(Intermediate Representation) DB에 저장하고 리포트를 생성한다.

### 주요 기능
- PowerBuilder 객체 인벤토리 추출 (Window, UserObject, Menu, DataWindow, Function, Event)
- 함수/이벤트 호출 관계 분석 (`calls`, `triggers_event`)
- 화면 전환 관계 분석 (`opens`)
- DataWindow SQL 추출 및 테이블 매핑 (`uses_dw`, `reads_table`, `writes_table`)
- Embedded SQL 추출 및 CRUD 정규화
- 실행 간 비교(diff) 기능
- CSV/JSON/HTML 6종 리포트 생성
- 웹 대시보드

## 2. 설치

### 요구 사항
- Python 3.11 이상
- (선택) ORCA Script 실행 환경 (PBL/PBR 바이너리 분석 시)

### 설치 방법
```bash
# 기본 설치
python -m pip install -e .

# 개발 도구 포함 설치
python -m pip install -e .[dev]
```

### 환경 변수

| 변수 | 설명 |
|------|------|
| `PB_ANALYZER_ORCA_CMD` | ORCA 명령 템플릿. `--orca-cmd` 옵션 대신 환경 변수로 설정 가능. `{input}`과 `{output}` 플레이스홀더 사용. |

## 3. 파이프라인 구조

5단계 파이프라인으로 구성된다:

```
extract → parse → analyze → persist → report
```

| 단계 | 설명 |
|------|------|
| **extract** | 소스 파일(.srw, .sru, .srm, .srd 등)에서 manifest 생성 |
| **parse** | PowerScript 토크나이징, 이벤트/함수/SQL/DataWindow 파싱 |
| **analyze** | 관계 추론 (calls, opens, uses_dw, reads_table, writes_table, triggers_event) |
| **persist** | SQLite IR DB에 결과 적재 (run_id 기반 버전 관리) |
| **report** | CSV/JSON/HTML 리포트 생성 |

## 4. CLI 커맨드

### 4.1 전체 실행 (run-all)

추출부터 리포트 생성까지 전체 파이프라인을 일괄 실행한다.

```bash
pb-analyzer run-all --input <소스경로> --out <출력경로> --db <DB경로> [옵션]
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--input` | O | 입력 소스 경로 (폴더, zip, pbl) | - |
| `--out` | O | 작업 산출물 출력 경로 | - |
| `--db` | O | IR SQLite DB 경로 | - |
| `--extractor` | X | 추출기 종류 (auto, orca, text) | auto |
| `--format` | X | 리포트 형식 (csv, json, html) | html |
| `--orca-cmd` | X | ORCA 명령 템플릿 (`{input}`, `{output}` 플레이스홀더 사용) | - |

**사용 예시:**
```bash
# 텍스트 소스 폴더
pb-analyzer run-all --input ./pb-src --out ./workspace/job1 --db ./workspace/job1.db

# JSON 리포트 생성
pb-analyzer run-all --input ./pb-src --out ./workspace/job1 --db ./workspace/job1.db --format json

# 압축 파일 입력
pb-analyzer run-all --input ./pb-src.zip --out ./workspace/job2 --db ./workspace/job2.db

# PBL 바이너리 (ORCA 사용)
pb-analyzer run-all \
  --input ./legacy-pbl \
  --out ./workspace/job3 \
  --db ./workspace/job3.db \
  --extractor orca \
  --orca-cmd "orca-cli /in {input} /out {output}"
```

**출력 예시:**
```
[OK] run_id=20260214_143022
[OK] manifest=./workspace/job1/manifest.json
[OK] reports=6
```

부분 실패 시:
```
[OK] run_id=20260214_143022
[OK] manifest=./workspace/job1/manifest.json
[OK] reports=6
[WARN] partial failures: 2
[WARN] parse issue: w_broken (synthetic syntax marker detected)
```

### 4.2 추출 (extract)

소스 파일에서 manifest를 생성한다.

```bash
pb-analyzer extract --input <소스경로> --out <출력경로> [--extractor auto] [--orca-cmd <명령>]
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--input` | O | 입력 소스 경로 | - |
| `--out` | O | 출력 경로 (manifest.json 생성) | - |
| `--extractor` | X | 추출기 종류 (auto, orca, text) | auto |
| `--orca-cmd` | X | ORCA 명령 템플릿 (`{input}`, `{output}` 플레이스홀더) | - |

**출력 예시:**
```
[OK] manifest=./workspace/job1/manifest.json
```

추출 실패 객체가 있을 경우:
```
[OK] manifest=./workspace/job1/manifest.json
[WARN] extraction failures=2
```

### 4.3 분석 (analyze)

manifest를 기반으로 파싱 → 분석 → DB 적재를 수행한다.

```bash
pb-analyzer analyze --manifest <manifest경로> --db <DB경로> [--run-id <run_id>] [--source-version <버전>]
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--manifest` | O | extract 단계에서 생성된 manifest.json 경로 |
| `--db` | O | IR SQLite DB 경로 |
| `--run-id` | X | 분석 실행 식별자 (미지정 시 자동 생성) |
| `--source-version` | X | 소스 버전 태그 |

**출력 예시:**
```
[OK] run_id=20260214_143022
[OK] persisted objects=8, events=25, functions=12, relations=35, sql=18, data_windows=3
```

### 4.4 리포트 (report)

IR DB에서 리포트를 생성한다.

```bash
pb-analyzer report --db <DB경로> --out <출력경로> --format <csv|json|html>
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--db` | O | IR SQLite DB 경로 |
| `--out` | O | 리포트 출력 디렉터리 |
| `--format` | O | 리포트 형식 (csv, json, html) |

**출력 예시:**
```
[OK] generated_reports=6
[OK] report=./workspace/reports/screen_inventory.json
[OK] report=./workspace/reports/event_function_map.json
[OK] report=./workspace/reports/table_impact.json
[OK] report=./workspace/reports/screen_call_graph.json
[OK] report=./workspace/reports/unused_object_candidates.json
[OK] report=./workspace/reports/data_windows.json
```

**생성되는 리포트 6종:**

| 리포트 | 파일명 | 설명 |
|--------|--------|------|
| 화면 인벤토리 | `screen_inventory` | 전체 객체 목록 (type, name, module, source_path) |
| 이벤트-함수 맵 | `event_function_map` | 객체별 이벤트와 호출된 함수 목록 |
| 테이블 영향도 | `table_impact` | 테이블별 R/W 접근 객체와 SQL 종류 |
| 화면 호출 그래프 | `screen_call_graph` | opens/calls 관계 그래프 (src → dst) |
| 미사용 객체 후보 | `unused_object_candidates` | 관계/이벤트/함수가 없는 객체 목록 |
| DataWindow 목록 | `data_windows` | 객체별 사용 DataWindow, base_table, SQL |

### 4.5 실행 비교 (diff)

두 분석 실행(run_id) 간의 차이를 비교한다.

```bash
pb-analyzer diff --db <DB경로> --run-old <이전_run_id> --run-new <최신_run_id>
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--db` | O | IR SQLite DB 경로 |
| `--run-old` | O | 이전 실행 run_id |
| `--run-new` | O | 최신 실행 run_id |

**비교 대상 4개 영역:**
- **객체(object)**: 추가/삭제된 객체
- **관계(relation)**: 추가/삭제된 관계 (calls, opens, uses_dw 등)
- **SQL 문(sql_statement)**: 추가/삭제된 SQL
- **DataWindow(data_window)**: 추가/삭제된 DataWindow 매핑

**출력 예시:**
```
[DIFF] added=3, removed=1, changed=0
  [+] object: Window:w_new_screen
  [+] relation: w_new_screen->w_main:opens
  [+] data_window: w_new_screen:dw_new:tb_orders
  [-] sql_statement: w_old_screen:SELECT:SELECT * FROM tb_old
```

차이가 없는 경우:
```
[OK] 두 실행 결과에 차이가 없습니다.
```

### 4.6 웹 대시보드 (dashboard)

분석 결과를 웹 UI로 조회한다.

```bash
pb-analyzer dashboard --db <DB경로> [--host 127.0.0.1] [--port 8787] [--run-id <run_id>] [--limit 200]
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--db` | O | IR SQLite DB 경로 | - |
| `--host` | X | 바인드 주소 | 127.0.0.1 |
| `--port` | X | 리슨 포트 | 8787 |
| `--run-id` | X | 기본 표시할 run_id | (최신 run) |
| `--limit` | X | 쿼리당 최대 결과 수 | 200 |

**API 엔드포인트:**
| 엔드포인트 | 설명 |
|-----------|------|
| `/api/runs` | 전체 실행 목록 |
| `/api/all?run_id=<id>&limit=200` | 관계 전체 조회 |
| `/api/graph?run_id=<id>&object_name=<name>` | 객체 중심 그래프 |
| `/api/table-impact?run_id=<id>&limit=100` | 테이블 영향도 |

**필터 파라미터:**
- `search`: 객체명/모듈/경로/관계타입 통합 검색
- `object_name`: 특정 객체 기준 필터
- `table_name`: 특정 테이블 기준 필터
- `relation_type`: `calls|opens|uses_dw|reads_table|writes_table|triggers_event`

## 5. 지원 파일 형식

### 입력 소스
| 확장자 | 객체 유형 | 설명 |
|--------|----------|------|
| `.srw` | Window | 화면 정의 (이벤트, 함수, SQL, 화면이동) |
| `.sru` | UserObject | 사용자 정의 객체 (공통 함수 등) |
| `.srm` | Menu | 메뉴 정의 (화면 호출) |
| `.srd` | DataWindow | 데이터윈도우 정의 (SQL, 테이블 매핑) |
| `.srf` | Function | 전역 함수 정의 |
| `.sql` | SQL | SQL 스크립트 |
| `.zip/.tar.gz` | Archive | 압축 파일 (자동 해제 후 분석) |
| `.pbl/.pbr/.pbd` | Binary | PowerBuilder 바이너리 (ORCA 우선, 미사용 시 binary string fallback) |

### 추출기 유형 (Extractor)

| 추출기 | 설명 |
|--------|------|
| `auto` | 입력 파일 확장자에 따라 자동 선택 (기본값) |
| `text` | 텍스트 기반 소스 파일 직접 읽기 (.srw, .sru, .srm, .srd 등) |
| `orca` | ORCA Script를 통한 PBL/PBR/PBD 바이너리 추출 |

- `auto` 모드에서 PBL/PBR/PBD 파일 발견 시: `--orca-cmd` 또는 `PB_ANALYZER_ORCA_CMD` 환경 변수가 설정되어 있으면 ORCA를 사용하고, 미설정 시 binary string fallback으로 분석 가능한 텍스트를 최대한 복원한다.
- 텍스트 소스 폴더와 압축 파일(zip/tar.gz)은 `text` 추출기로 자동 처리된다.

### DataWindow 파싱

DataWindow 파일(`.srd`) 또는 Window/UserObject 내 DataWindow 사용을 분석한다.

**파싱 대상:**
- `retrieve="SELECT ..."` 구문에서 SQL과 FROM/JOIN 테이블 추출
- `update="table_name"` 구문에서 base_table 추출
- Window 이벤트 내 `dw_*.SetTransObject()`/`dw_*.Retrieve()` 호출에서 DataWindow 사용 관계 추출

**예시 DataWindow 소스 (`.srd`):**
```
release 12;
datawindow(units=0 timer_interval=0 color=536870912 processing=0)
table(column=(type=char(20) updatewhereclause=yes name=lot_no dbname="tb_prod_result.lot_no")
  retrieve="SELECT pr.lot_no, pr.prod_cd, tp.prod_nm FROM tb_prod_result pr JOIN tb_product tp ON tp.prod_cd = pr.prod_cd WHERE pr.plant_cd = :as_plant_cd ORDER BY pr.lot_no"
  update="tb_prod_result"
)
```

→ 분석 결과: base_table=`tb_prod_result`, SQL에서 `tb_prod_result`, `tb_product` 테이블 참조 감지

## 6. 관계 유형 (Relation Types)

| 관계 유형 | 설명 | 기본 confidence | 예시 |
|----------|------|:--------------:|------|
| `calls` | 함수/이벤트 호출 | 0.85 | `w_main`이 `f_calc()`를 호출 |
| `opens` | 화면 열기/이동 | 0.95 | `w_main`에서 `Open(w_detail)` |
| `uses_dw` | DataWindow 사용 | 0.90 | `w_main`이 `dw_list`를 참조 |
| `reads_table` | 테이블 읽기 (SELECT) | 0.90 | SELECT 문에서 참조하는 테이블 |
| `writes_table` | 테이블 쓰기 (INSERT/UPDATE/DELETE) | 0.90 | INSERT/UPDATE/DELETE 대상 테이블 |
| `triggers_event` | 이벤트 트리거 | 0.70 | `TriggerEvent("ue_save")` 호출 |

> `confidence`는 0.0~1.0 범위의 추론 신뢰도 값이다. `opens`(명시적 `Open()` 호출)가 가장 높고, `triggers_event`(이벤트 이름 기반 추론)가 가장 낮다.

## 7. IR 데이터베이스 스키마

분석 결과는 SQLite DB에 저장된다. 핵심 테이블:

| 테이블 | 주요 컬럼 | 설명 |
|--------|----------|------|
| `runs` | run_id, started_at, finished_at, status, source_version | 분석 실행 이력 |
| `objects` | type, name, module, source_path | 분석된 PB 객체 |
| `events` | event_name, script_ref | 이벤트 목록 |
| `functions` | function_name, signature | 함수 목록 |
| `relations` | src_id, dst_id, relation_type, confidence | 객체 간 관계 |
| `sql_statements` | owner_id, sql_kind, sql_text_norm | SQL 문 |
| `sql_tables` | sql_id, table_name, rw_type | SQL에서 참조하는 테이블 |
| `data_windows` | object_id, dw_name, base_table, sql_select | DataWindow 매핑 |

**제약 조건:**
- 모든 테이블의 레코드는 `run_id`로 격리 저장되어 실행 간 비교/회귀 분석이 가능
- `objects(run_id, type, name)`: 동일 run 내 객체 중복 불가
- `data_windows(run_id, object_id, dw_name)`: 동일 run 내 DataWindow 중복 불가
- `relations.relation_type`: CHECK 제약으로 허용값 제한
- `relations.confidence`: 0.0~1.0 범위의 추론 신뢰도 값
- `sql_statements.sql_kind`: SELECT, INSERT, UPDATE, DELETE, MERGE, OTHER 중 하나
- `sql_tables.rw_type`: READ 또는 WRITE

## 8. 골든셋 회귀 테스트

분석 정확도를 정량 평가하기 위한 골든셋 메커니즘을 제공한다.

### 8.1 골든셋 구조

기대 결과를 JSON으로 정의한다 (`tests/regression/golden_set/expected.json`):

```json
{
  "objects": [
    {"type": "Window", "name": "w_prod_result"},
    {"type": "DataWindow", "name": "dw_prod_result"}
  ],
  "relations": [
    {"src": "w_prod_result", "dst": "dw_prod_result", "type": "uses_dw"},
    {"src": "w_prod_result", "dst": "tb_prod_result", "type": "writes_table"}
  ],
  "data_windows": [
    {"object": "dw_prod_result", "dw_name": "dw_prod_result", "base_table": "tb_prod_result"}
  ],
  "sql_statements": [
    {"owner": "w_prod_result", "kind": "UPDATE"},
    {"owner": "w_prod_result", "kind": "INSERT"}
  ]
}
```

### 8.2 메트릭 생성

```bash
python tools/ci/generate_golden_metrics.py \
    --db workspace/runs/latest.db \
    --golden tests/regression/golden_set/expected.json \
    --output workspace/reports/latest/metrics.json \
    [--run-id <run_id>]
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--db` | O | 분석 결과 SQLite DB 경로 |
| `--golden` | X | 골든셋 JSON 경로 (기본: `tests/regression/golden_set/expected.json`) |
| `--output` | X | 메트릭 JSON 출력 경로 (기본: `workspace/reports/latest/metrics.json`) |
| `--run-id` | X | 특정 run_id (미지정 시 최신 run 사용) |

**출력 메트릭:**
```json
{
  "precision": 0.92,
  "recall": 0.85,
  "f1": 0.88,
  "true_positives": 17,
  "expected_count": 20,
  "actual_count": 18
}
```

### 8.3 CI 품질 게이트 기준
- Precision >= 0.85
- Recall >= 0.75

```bash
python tools/ci/check_golden_metrics.py --precision-min 0.85 --recall-min 0.75
```

## 9. 종료 코드

| 코드 | 의미 |
|------|------|
| `0` | 정상 완료 |
| `1` | 오류 발생 (파일 미존재, 잘못된 인자 등) |
| `2` | 부분 성공 (일부 객체 파싱 실패, 경고 포함) |

## 10. Fail-soft 파싱

파싱 에러 발생 시 해당 객체를 skip하고 나머지를 계속 처리한다.

- 에러가 발생한 객체의 위치와 원인을 로그에 기록
- 파일당 최대 에러 수는 `configs/parser/fail_soft.yaml`에서 설정 가능
- 종료 코드 `2`로 부분 실패를 알림
- 실패 객체 목록은 `[WARN]` 로그로 출력

## 11. 사용 시나리오 예시

### 시나리오 1: 화면 변경 전 영향 분석

특정 화면을 변경하기 전에 연관 이벤트, 함수, 테이블 목록을 조회한다.

```bash
# 1. 전체 분석 실행
pb-analyzer run-all --input ./pb-src --out ./workspace --db ./workspace/analysis.db --format json

# 2. JSON 리포트에서 특정 화면 관련 정보 확인
#    - screen_call_graph.json: 해당 화면의 opens/calls 관계
#    - event_function_map.json: 해당 화면의 이벤트/함수 목록
#    - table_impact.json: 해당 화면이 접근하는 테이블 목록
#    - data_windows.json: 해당 화면이 사용하는 DataWindow 목록
```

### 시나리오 2: 테이블 변경 영향 역추적

특정 테이블을 변경할 때 영향 받는 화면과 함수를 역추적한다.

```bash
# 웹 대시보드에서 테이블 영향도 조회
pb-analyzer dashboard --db ./workspace/analysis.db

# 브라우저에서 테이블 기준 필터:
# http://127.0.0.1:8787/api/table-impact?run_id=<id>&table_name=tb_prod_result
```

### 시나리오 3: 소스 변경 전후 비교

소스 변경 전후 분석 결과를 비교하여 변경 영향을 확인한다.

```bash
# 1. 변경 전 분석
pb-analyzer run-all --input ./pb-src-before --out ./workspace/before --db ./workspace/analysis.db

# 2. 변경 후 분석
pb-analyzer run-all --input ./pb-src-after --out ./workspace/after --db ./workspace/analysis.db

# 3. 두 실행 결과 비교
pb-analyzer diff --db ./workspace/analysis.db --run-old <before_run_id> --run-new <after_run_id>
```

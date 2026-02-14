# PB Analyzer 사용자 매뉴얼

PowerBuilder 소스를 자동으로 분석하여 화면/함수/테이블 영향도를 확인할 수 있는 도구입니다.

---

## 목차

1. [설치하기](#1-설치하기)
2. [소스 준비하기 (인풋)](#2-소스-준비하기-인풋)
3. [분석 실행하기](#3-분석-실행하기)
4. [결과 확인하기 (아웃풋)](#4-결과-확인하기-아웃풋)
5. [웹 대시보드로 보기](#5-웹-대시보드로-보기)
6. [자주 묻는 질문](#6-자주-묻는-질문)

---

## 1. 설치하기

### 필요 환경

- Python 3.11

### 설치 순서

```bash
# 1) 프로젝트 폴더로 이동
cd pbtm-project

# 2) 가상환경 생성 및 활성화
python3.11 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3) 패키지 설치
pip install -e .
```

설치가 끝나면 `pb-analyzer` 명령을 사용할 수 있습니다.

```bash
pb-analyzer --help
```

---

## 2. 소스 준비하기 (인풋)

PB Analyzer는 다양한 형태의 PowerBuilder 소스를 입력으로 받을 수 있습니다.

### 2.1 지원하는 입력 형태

| 입력 형태 | 예시 | 설명 |
|-----------|------|------|
| **소스 폴더** | `./pb_sources/` | 추출된 텍스트 파일이 들어있는 폴더 |
| **단일 파일** | `w_main.srw` | 파일 하나만 분석할 때 |
| **압축 파일** | `sources.zip`, `sources.tar.gz` | 소스를 압축한 파일 |
| **PB 바이너리** | `app.pbl`, `app.pbr`, `app.pbd` | PowerBuilder 라이브러리 파일 |

### 2.2 소스 폴더 구조 예시

가장 기본적인 입력 방식입니다. ORCA Script 등으로 추출한 텍스트 파일을 폴더에 넣어주세요.

```
pb_sources/
├── w_main.srw          ← Window 소스
├── w_detail.srw        ← Window 소스
├── w_search.srw        ← Window 소스
├── u_helper.sru        ← UserObject 소스
├── m_main.srm          ← Menu 소스
├── dw_order_list.srd   ← DataWindow 소스
├── f_validate.srf      ← Function 소스
└── module_a/           ← 하위 폴더도 인식
    ├── w_sub.srw
    └── dw_sub_list.srd
```

### 2.3 인식하는 파일 확장자

| 확장자 | 객체 유형 |
|--------|-----------|
| `.srw` | Window |
| `.sru` | UserObject |
| `.srm` | Menu |
| `.srd` | DataWindow |
| `.srf` | Function |
| `.pbt` | Library |
| `.txt`, `.psr`, `.psx`, `.inc` | Script |
| `.sql` | SQL |

> 하위 폴더를 포함하여 모든 파일을 자동으로 탐색합니다.
> 한글 인코딩(CP949, EUC-KR)도 자동 감지합니다.

### 2.4 압축 파일로 입력하기

소스 폴더를 ZIP이나 TAR로 압축한 채로 바로 입력할 수 있습니다.

```bash
# 소스를 ZIP으로 압축
zip -r pb_sources.zip pb_sources/

# 압축 파일을 바로 분석
pb-analyzer run-all --input pb_sources.zip --out ./결과 --db ./분석.db
```

지원 압축 형식: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`

### 2.5 PB 바이너리 파일로 입력하기

ORCA Script로 추출하지 않은 `.pbl`, `.pbr`, `.pbd` 파일도 입력할 수 있습니다.

**방법 1: 자동 문자열 추출 (ORCA 없이)**

```bash
pb-analyzer run-all --input app.pbl --out ./결과 --db ./분석.db
```

바이너리에서 텍스트 문자열을 자동으로 추출합니다. ORCA 대비 정확도가 낮을 수 있습니다.

**방법 2: ORCA Script 연동**

ORCA가 설치된 환경에서는 ORCA를 사용하면 더 정확한 결과를 얻을 수 있습니다.

```bash
pb-analyzer run-all \
  --input app.pbl \
  --out ./결과 \
  --db ./분석.db \
  --extractor orca \
  --orca-cmd "orca_export.bat {input} {output}"
```

`{input}`과 `{output}`은 실행 시 자동으로 실제 경로로 치환됩니다.

---

## 3. 분석 실행하기

### 3.1 한번에 전체 분석 (가장 간편한 방법)

```bash
pb-analyzer run-all \
  --input ./pb_sources \
  --out ./결과 \
  --db ./분석.db \
  --format html
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--input` | O | 소스 경로 (폴더, 파일, 압축 파일) | - |
| `--out` | O | 결과물 저장 폴더 | - |
| `--db` | O | 분석 결과 DB 파일 경로 | - |
| `--format` | - | 리포트 형식 (`html`, `csv`, `json`) | `html` |
| `--extractor` | - | 추출기 (`auto`, `orca`, `filesystem`) | `auto` |
| `--orca-cmd` | - | ORCA 명령 템플릿 | - |

**실행 결과 예시:**

```
[OK] run_id=run_20260214T093000Z_a1b2c3d4
[OK] manifest=./결과/extract/manifest.json
[OK] reports=1
```

### 3.2 단계별 실행

전체 파이프라인을 개별 단계로 나누어 실행할 수도 있습니다.

```bash
# 단계 1: 소스 추출
pb-analyzer extract --input ./pb_sources --out ./추출결과

# 단계 2: 분석 + DB 저장
pb-analyzer analyze --manifest ./추출결과/manifest.json --db ./분석.db

# 단계 3: 리포트 생성
pb-analyzer report --db ./분석.db --out ./리포트 --format html
```

이 방법은 특정 단계만 재실행하고 싶을 때 유용합니다. 예를 들어 DB는 그대로 두고 리포트만 다른 형식으로 다시 생성할 수 있습니다.

```bash
# JSON 리포트 추가 생성
pb-analyzer report --db ./분석.db --out ./리포트_json --format json

# CSV 리포트 추가 생성
pb-analyzer report --db ./분석.db --out ./리포트_csv --format csv
```

### 3.3 종료 코드

| 코드 | 의미 | 대응 |
|------|------|------|
| `0` | 성공 | 정상 완료 |
| `1` | 입력 오류 | 경로, 파일 형식, 권한 등 확인 |
| `2` | 부분 실패 | 일부 객체 분석 실패. 결과는 생성됨. 경고 메시지 확인 |

---

## 4. 결과 확인하기 (아웃풋)

### 4.1 결과 폴더 구조

`run-all`을 실행하면 다음과 같은 구조가 생성됩니다.

```
결과/
├── extract/
│   ├── manifest.json          ← 추출된 객체 목록
│   └── objects/               ← 추출된 텍스트 파일들
│       ├── window__w_main__a1b2c3.txt
│       ├── window__w_detail__d4e5f6.txt
│       └── ...
├── reports/
│   └── report.html            ← HTML 리포트 (브라우저로 열기)
분석.db                         ← 분석 결과 DB (SQLite)
```

### 4.2 리포트 확인하기

#### HTML 리포트 (브라우저에서 열기)

```bash
# macOS
open 결과/reports/report.html

# Windows
start 결과\reports\report.html

# Linux
xdg-open 결과/reports/report.html
```

HTML 리포트에는 5개 테이블이 포함됩니다:

| 섹션 | 내용 | 활용 |
|------|------|------|
| **Screen Inventory** | 전체 화면/객체 목록 | "시스템에 화면이 몇 개인지?" |
| **Event Function Map** | 이벤트 → 함수 호출 관계 | "이 버튼을 누르면 어떤 함수가 실행되는지?" |
| **Table Impact** | 테이블 → 읽기/쓰기 객체 매핑 | "이 테이블을 변경하면 어디가 영향받는지?" |
| **Screen Call Graph** | 화면 간 전환/호출 관계 | "이 화면에서 어디로 이동하는지?" |
| **Unused Object Candidates** | 미사용 추정 객체 목록 | "정리할 수 있는 코드가 있는지?" |

#### JSON 리포트 (프로그래밍 활용)

`--format json`으로 생성하면 리포트별 JSON 파일이 생깁니다.

```
리포트/
├── screen_inventory.json
├── event_function_map.json
├── table_impact.json
├── screen_call_graph.json
└── unused_object_candidates.json
```

JSON 예시 (`table_impact.json`):

```json
[
  {
    "table_name": "TB_ORDER",
    "rw_type": "READ",
    "owner_object": "w_order_search",
    "sql_kind": "SELECT"
  },
  {
    "table_name": "TB_ORDER",
    "rw_type": "WRITE",
    "owner_object": "w_order_edit",
    "sql_kind": "UPDATE"
  }
]
```

#### CSV 리포트 (엑셀에서 열기)

`--format csv`로 생성하면 리포트별 CSV 파일이 생깁니다. 엑셀이나 구글 시트에서 바로 열 수 있습니다.

```
리포트/
├── screen_inventory.csv
├── event_function_map.csv
├── table_impact.csv
├── screen_call_graph.csv
└── unused_object_candidates.csv
```

### 4.3 DB 직접 조회하기

분석 결과는 SQLite DB에 저장되므로 SQL로 직접 질의할 수 있습니다.

```bash
sqlite3 분석.db
```

**자주 쓰는 질의:**

```sql
-- 전체 객체 수 확인
SELECT type, COUNT(*) as count FROM objects GROUP BY type ORDER BY count DESC;

-- 특정 테이블(TB_ORDER) 영향받는 화면 찾기
SELECT DISTINCT owner.name, owner.type, st.rw_type, ss.sql_kind
FROM sql_tables st
JOIN sql_statements ss ON ss.id = st.sql_id
JOIN objects owner ON owner.id = ss.owner_id
WHERE st.table_name = 'TB_ORDER'
ORDER BY owner.name;

-- 특정 화면(w_main)에서 호출하는 함수/화면 찾기
SELECT dst.name, dst.type, r.relation_type, r.confidence
FROM relations r
JOIN objects src ON src.id = r.src_id
JOIN objects dst ON dst.id = r.dst_id
WHERE src.name = 'w_main'
ORDER BY r.relation_type, dst.name;

-- 미사용 객체 후보 확인
SELECT o.type, o.name
FROM objects o
LEFT JOIN relations r1 ON r1.src_id = o.id
LEFT JOIN relations r2 ON r2.dst_id = o.id
WHERE r1.id IS NULL AND r2.id IS NULL AND o.type <> 'Table'
ORDER BY o.type, o.name;

-- 분석 실행 이력 확인
SELECT run_id, started_at, finished_at, status FROM runs ORDER BY started_at DESC;
```

---

## 5. 웹 대시보드로 보기

분석 결과를 인터랙티브 웹 대시보드에서 확인할 수 있습니다.

### 5.1 대시보드 시작

```bash
pb-analyzer dashboard --db ./분석.db
```

```
[OK] dashboard_url=http://127.0.0.1:8787
[OK] press Ctrl+C to stop
```

브라우저에서 `http://127.0.0.1:8787`을 열면 대시보드가 표시됩니다.

### 5.2 대시보드 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--db` | 분석 DB 파일 경로 (필수) | - |
| `--host` | 서버 주소 | `127.0.0.1` |
| `--port` | 포트 번호 | `8787` |
| `--run-id` | 특정 실행 결과만 표시 | 최신 실행 |
| `--limit` | 테이블 최대 행 수 | `200` |

```bash
# 포트를 변경하고 싶을 때
pb-analyzer dashboard --db ./분석.db --port 9090

# 특정 실행 결과를 보고 싶을 때
pb-analyzer dashboard --db ./분석.db --run-id run_20260214T093000Z_a1b2c3d4
```

### 5.3 대시보드 화면 구성

대시보드에 접속하면 다음 정보를 한 화면에서 확인할 수 있습니다:

| 영역 | 내용 |
|------|------|
| **Summary Cards** | 객체 수, 관계 수, SQL 수 요약 |
| **Relation Breakdown** | 관계 유형별 건수 (calls, opens, uses_dw 등) |
| **Run Info** | 실행 ID, 상태, 시작/종료 시간 |
| **화면 인벤토리** | 전체 화면/객체 목록 테이블 |
| **이벤트-함수 맵** | 이벤트 → 함수 호출 관계 테이블 |
| **테이블 영향도** | 테이블별 읽기/쓰기 영향 테이블 |
| **화면 이동/호출 그래프** | 화면 간 전환 관계 테이블 |
| **미사용 객체 후보** | 참조되지 않는 객체 목록 |

상단의 `run_id` 드롭다운으로 과거 실행 결과를 선택하여 비교할 수 있습니다.

### 5.4 대시보드 API

대시보드는 REST API도 제공합니다. 외부 도구에서 데이터를 가져올 때 사용할 수 있습니다.

| 엔드포인트 | 설명 |
|------------|------|
| `GET /api/runs` | 실행 이력 목록 |
| `GET /api/all?run_id=...&limit=200` | 전체 분석 데이터 |
| `GET /api/summary` | 요약 통계 |
| `GET /api/screen-inventory` | 화면 인벤토리 |
| `GET /api/event-function-map` | 이벤트-함수 맵 |
| `GET /api/table-impact` | 테이블 영향도 |
| `GET /api/screen-call-graph` | 화면 호출 그래프 |
| `GET /api/unused-object-candidates` | 미사용 객체 후보 |
| `GET /health` | 서버 상태 확인 |

```bash
# API로 테이블 영향도 조회
curl http://127.0.0.1:8787/api/table-impact | python -m json.tool
```

---

## 6. 자주 묻는 질문

### Q: 분석 결과가 부정확한 것 같습니다

PB Analyzer는 정적 분석 도구이므로 다음 경우 정확도가 낮을 수 있습니다:
- **동적 SQL**: 문자열 변수를 조합해서 SQL을 만드는 경우
- **동적 호출**: 변수에 담긴 이름으로 함수를 호출하는 경우
- **바이너리 입력**: `.pbl` 직접 분석은 ORCA 추출 대비 정확도가 낮습니다

가능하면 ORCA Script로 추출한 텍스트 소스를 사용해 주세요.

### Q: 이전 실행 결과와 비교할 수 있나요?

네. 매번 분석할 때마다 고유한 `run_id`가 부여되어 DB에 저장됩니다. 같은 DB 파일을 재사용하면 이전 결과가 보존됩니다.

```bash
# 첫 번째 분석
pb-analyzer run-all --input ./소스_v1 --out ./결과 --db ./분석.db

# 두 번째 분석 (같은 DB에 추가)
pb-analyzer run-all --input ./소스_v2 --out ./결과 --db ./분석.db

# 대시보드에서 run_id 선택하여 비교
pb-analyzer dashboard --db ./분석.db
```

### Q: 대용량 프로젝트도 분석 가능한가요?

기준 데이터셋 기준 30분 이내 완료를 목표로 설계되어 있습니다. 메모리 부족 시 대상 폴더를 나누어 실행할 수 있습니다.

### Q: 분석 중 일부 파일이 실패하면 어떻게 되나요?

실패한 파일은 건너뛰고 나머지를 계속 분석합니다 (fail-soft). 종료 코드 `2`와 함께 경고 메시지가 출력되며, 결과물은 정상 생성됩니다. `manifest.json`의 `failed_objects` 항목에서 실패 목록을 확인할 수 있습니다.

### Q: 특정 단계만 다시 실행할 수 있나요?

네. `extract`, `analyze`, `report` 명령을 개별적으로 실행할 수 있습니다. 예를 들어 DB는 유지한 채 리포트 형식만 바꾸려면:

```bash
pb-analyzer report --db ./분석.db --out ./리포트_csv --format csv
```

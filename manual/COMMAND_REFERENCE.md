# PB Analyzer 명령어 레퍼런스

---

## run-all (전체 파이프라인)

소스 추출부터 리포트 생성까지 한번에 실행합니다.

```bash
pb-analyzer run-all --input <소스경로> --out <출력폴더> --db <DB파일>
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|:----:|------|--------|
| `--input` | O | 소스 경로 (폴더, 파일, 압축 파일, PB 바이너리) | - |
| `--out` | O | 결과물 저장 폴더 | - |
| `--db` | O | SQLite DB 파일 경로 (없으면 자동 생성) | - |
| `--format` | | 리포트 형식: `html`, `csv`, `json` | `html` |
| `--extractor` | | 추출기: `auto`, `orca`, `filesystem` | `auto` |
| `--orca-cmd` | | ORCA 명령 템플릿 (`{input}`, `{output}` 자리표시자 사용) | - |

**사용 예시:**

```bash
# 기본 사용
pb-analyzer run-all --input ./소스 --out ./결과 --db ./분석.db

# CSV 리포트로 생성
pb-analyzer run-all --input ./소스 --out ./결과 --db ./분석.db --format csv

# 압축 파일 분석
pb-analyzer run-all --input sources.zip --out ./결과 --db ./분석.db

# ORCA 연동
pb-analyzer run-all --input app.pbl --out ./결과 --db ./분석.db \
  --extractor orca --orca-cmd "orca_export.bat {input} {output}"
```

**출력 예시:**

```
[OK] run_id=run_20260214T093000Z_a1b2c3d4
[OK] manifest=./결과/extract/manifest.json
[OK] reports=1
```

**생성되는 파일:**

```
결과/
├── extract/
│   ├── manifest.json
│   └── objects/
│       └── (추출된 텍스트 파일들)
└── reports/
    └── report.html          # --format에 따라 다름
분석.db
```

---

## extract (소스 추출)

PowerBuilder 소스를 텍스트 파일로 추출합니다.

```bash
pb-analyzer extract --input <소스경로> --out <출력폴더>
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|:----:|------|--------|
| `--input` | O | 소스 경로 | - |
| `--out` | O | 추출 결과 저장 폴더 | - |
| `--extractor` | | 추출기 선택 | `auto` |
| `--orca-cmd` | | ORCA 명령 템플릿 | - |

**사용 예시:**

```bash
pb-analyzer extract --input ./소스 --out ./추출결과
```

**출력:**

```
[OK] manifest=./추출결과/manifest.json
```

---

## analyze (분석 + DB 저장)

추출된 소스를 파싱하고 관계를 분석하여 DB에 저장합니다.

```bash
pb-analyzer analyze --manifest <manifest파일> --db <DB파일>
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|:----:|------|--------|
| `--manifest` | O | extract로 생성된 manifest.json 경로 | - |
| `--db` | O | 분석 결과를 저장할 SQLite DB 파일 | - |
| `--run-id` | | 실행 ID (미지정 시 자동 생성) | 자동 생성 |
| `--source-version` | | 소스 버전 태그 | - |

**사용 예시:**

```bash
# 기본 사용
pb-analyzer analyze --manifest ./추출결과/manifest.json --db ./분석.db

# 소스 버전 태그 지정
pb-analyzer analyze --manifest ./추출결과/manifest.json --db ./분석.db \
  --source-version "v2.3.1"
```

**출력:**

```
[OK] run_id=run_20260214T093000Z_a1b2c3d4
[OK] persisted objects=45, events=120, functions=89, relations=230, sql=67
```

---

## report (리포트 생성)

분석 DB를 기반으로 리포트를 생성합니다.

```bash
pb-analyzer report --db <DB파일> --out <출력폴더> --format <형식>
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|:----:|------|--------|
| `--db` | O | 분석 결과 DB 파일 | - |
| `--out` | O | 리포트 저장 폴더 | - |
| `--format` | O | 출력 형식: `html`, `csv`, `json` | - |

**사용 예시:**

```bash
# HTML 리포트
pb-analyzer report --db ./분석.db --out ./리포트 --format html

# CSV 리포트 (엑셀용)
pb-analyzer report --db ./분석.db --out ./리포트_csv --format csv

# JSON 리포트 (프로그래밍용)
pb-analyzer report --db ./분석.db --out ./리포트_json --format json
```

**형식별 생성 파일:**

| 형식 | 생성 파일 |
|------|-----------|
| `html` | `report.html` |
| `json` | `screen_inventory.json`, `event_function_map.json`, `table_impact.json`, `screen_call_graph.json`, `unused_object_candidates.json` |
| `csv` | `screen_inventory.csv`, `event_function_map.csv`, `table_impact.csv`, `screen_call_graph.csv`, `unused_object_candidates.csv` |

---

## dashboard (웹 대시보드)

분석 결과를 웹 브라우저에서 인터랙티브하게 조회합니다.

```bash
pb-analyzer dashboard --db <DB파일>
```

| 옵션 | 필수 | 설명 | 기본값 |
|------|:----:|------|--------|
| `--db` | O | 분석 결과 DB 파일 | - |
| `--host` | | 서버 바인딩 주소 | `127.0.0.1` |
| `--port` | | 서버 포트 | `8787` |
| `--run-id` | | 특정 실행 결과만 표시 | 최신 실행 |
| `--limit` | | 테이블당 최대 행 수 (10~2000) | `200` |

**사용 예시:**

```bash
# 기본 사용
pb-analyzer dashboard --db ./분석.db

# 포트 변경
pb-analyzer dashboard --db ./분석.db --port 9090

# 외부 접속 허용 + 행 제한 확장
pb-analyzer dashboard --db ./분석.db --host 0.0.0.0 --limit 500
```

**종료:** `Ctrl+C`

---

## 추출기 (--extractor) 옵션 상세

| 추출기 | 설명 | 사용 시점 |
|--------|------|-----------|
| `auto` | 입력 형태를 자동 판별하여 최적 방식 선택 | 대부분의 경우 (기본값) |
| `filesystem` | 폴더 내 텍스트 파일만 읽음 | 이미 ORCA로 추출된 소스일 때 |
| `orca` | ORCA Script 우선 실행, 실패 시 자동 폴백 | PB 바이너리를 정확하게 분석할 때 |

`auto` 추출기의 자동 판별 순서:
1. 폴더 → 내부 파일 탐색
2. `.zip`, `.tar.*` → 압축 해제 후 탐색
3. `.pbl`, `.pbr`, `.pbd` → ORCA 또는 바이너리 폴백
4. 단일 텍스트 파일 → 직접 읽기

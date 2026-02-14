# PB Analyzer 빠른 시작 가이드

5분 안에 첫 분석을 실행하는 방법입니다.

---

## 1단계: 설치

```bash
cd pbtm-project
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2단계: 소스 준비

분석할 PowerBuilder 소스 파일(`.srw`, `.sru`, `.srd` 등)을 하나의 폴더에 넣어주세요.

```
내소스/
├── w_main.srw
├── w_detail.srw
├── dw_order.srd
└── u_common.sru
```

> 압축 파일(`.zip`)이나 PB 바이너리(`.pbl`)도 가능합니다.

## 3단계: 분석 실행

```bash
pb-analyzer run-all \
  --input ./내소스 \
  --out ./결과 \
  --db ./분석.db \
  --format html
```

## 4단계: 결과 확인

### 방법 A: HTML 리포트 열기

```bash
open 결과/reports/report.html     # macOS
```

### 방법 B: 웹 대시보드로 보기

```bash
pb-analyzer dashboard --db ./분석.db
```

브라우저에서 http://127.0.0.1:8787 접속

### 방법 C: DB 직접 질의

```bash
sqlite3 분석.db "SELECT type, COUNT(*) FROM objects GROUP BY type;"
```

---

## 명령어 요약

| 명령 | 용도 |
|------|------|
| `pb-analyzer run-all --input ... --out ... --db ...` | 전체 분석 (추출+분석+리포트) |
| `pb-analyzer extract --input ... --out ...` | 소스 추출만 |
| `pb-analyzer analyze --manifest ... --db ...` | 분석+DB 저장만 |
| `pb-analyzer report --db ... --out ... --format html` | 리포트 생성만 |
| `pb-analyzer dashboard --db ...` | 웹 대시보드 실행 |

## 리포트 형식

| 형식 | 결과 파일 | 용도 |
|------|-----------|------|
| `html` | `report.html` 1개 | 브라우저에서 바로 확인 |
| `json` | 리포트별 `.json` 5개 | 프로그래밍 활용, API 연동 |
| `csv` | 리포트별 `.csv` 5개 | 엑셀, 구글 시트에서 열기 |

자세한 내용은 [USER_GUIDE.md](./USER_GUIDE.md)를 참고하세요.

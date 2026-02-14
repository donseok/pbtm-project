# 유지보수 개선 실행안

## 목표
- 유료/벤더 락인 최소화
- 파서/규칙 복잡도의 운영 리스크 통제
- 인력 교체 시에도 재현 가능한 운영체계 확보

## 실행 항목 (우선순위순)
1. 의존성 고정 체계 도입
- 산출물: `pyproject.toml`
- 완료 기준: Python/개발도구 버전 고정, CI 동일 버전 사용

2. ORCA 의존성 격리
- 산출물: `src/pb_analyzer/extractor/adapter.py`
- 완료 기준: 파이프라인이 `ExtractorAdapter` 인터페이스만 참조

3. 규칙 거버넌스 확립
- 산출물: `src/pb_analyzer/rules/RULE_REGISTRY.md`, `configs/analyzer/rule_registry.yaml`
- 완료 기준: 규칙 변경 시 버전/리스크/회귀결과 필수 기입

4. 품질 게이트 자동화
- 산출물: `tools/ci/quality_gate.sh`, `tools/ci/check_golden_metrics.py`, `.github/workflows/quality-gate.yml`
- 완료 기준: PR 단위에서 Unit/Integration/골든셋 지표 자동 검증

5. 운영 Runbook 고도화
- 산출물: `docs/runbooks/OPERATIONS.md`
- 완료 기준: 신규 운영자도 문서만으로 배치/장애대응 수행 가능

## 일정 제안
- Week 1: 1~2번
- Week 2: 3~4번
- Week 3: 5번 + 운영 리허설

#!/usr/bin/env bash
set -euo pipefail

echo "=== Lint ==="
python -m ruff check src tests

echo "=== Type Check ==="
python -m mypy src

echo "=== Unit Tests ==="
python -m pytest tests/unit --cov=pb_analyzer --cov-report=term-missing --cov-fail-under=80

echo "=== Integration Tests ==="
python -m pytest tests/integration/pipeline

echo "=== Golden-set Metrics ==="
METRICS_FILE="${METRICS_FILE:-tests/regression/compare/metrics.sample.json}"
python tools/ci/check_golden_metrics.py \
  --metrics "$METRICS_FILE" \
  --precision-min 0.85 \
  --recall-min 0.75

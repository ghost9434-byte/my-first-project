#!/bin/bash
# .env 를 읽어 조회하고 결과를 results/ 에 시각별로 저장합니다. (launchd/수동 공용)
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./.env; set +a
mkdir -p results
OUT="results/$(date +%Y%m%d_%H%M%S).txt"
python3 flight_search.py --provider "${PROVIDER:-serpapi}" \
  --origins ${ORIGINS} --out ${OUT_DATES} --back ${BACK_DATES} | tee "$OUT"
ln -sf "$(basename "$OUT")" results/latest.txt
# 최근 30개만 보관
ls -1t results/2*.txt 2>/dev/null | tail -n +31 | xargs -I{} rm -f {} || true

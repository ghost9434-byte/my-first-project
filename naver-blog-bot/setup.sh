#!/bin/bash
# 처음 한 번만 실행: 자동화 도구 설치
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "파이썬이 없습니다. 뜨는 설치 창에서 '설치'를 눌러 주시고, 끝나면 이 명령을 다시 실행해 주세요."
  xcode-select --install || true
  exit 1
fi

if [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "구글 크롬이 필요합니다. https://www.google.com/chrome 에서 설치 후 다시 실행해 주세요."
  exit 1
fi

python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet playwright
echo ""
echo "✅ 설치가 끝났습니다. 다음으로 'bash login.sh' 를 실행해 네이버에 로그인해 주세요."

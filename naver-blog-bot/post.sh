#!/bin/bash
# 사용법: bash post.sh                     (클로드가 보낸 새 글을 받아서 임시저장)
#         bash post.sh <글폴더> --step      (특정 글을 단계마다 멈추며 시험)
cd "$(dirname "$0")"
if git -C .. rev-parse --git-dir >/dev/null 2>&1; then
  echo "새 글 받는 중..."
  git -C .. pull --ff-only --quiet || echo "⚠️ 새 글을 받지 못했습니다. 인터넷 연결을 확인해 주세요. (있는 글로 계속합니다)"
fi
.venv/bin/python blog_bot.py post "$@"

#!/bin/bash
# (예약 실행용) 월·수·금 정해진 시간에 블로그 클로드가 새 사진으로 글을 써서 임시저장한다.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
PHOTOS="${BLOG_PHOTO_DIR:-$HOME/Desktop/SH SUCCESSHUB/오피스 사진들}"

LOCK="/tmp/naver-blog-bot.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK"; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

mkdir -p logs
LOG="logs/schedule-$(date +%Y%m%d-%H%M).log"
notify() {
  osascript -e "display notification \"$2\" with title \"블로그 예약 글\" subtitle \"$1\" sound name \"Glass\"" >/dev/null 2>&1
  echo "[알림] $1 - $2" >> "$LOG"
}

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 예약 글쓰기 ====="
  git -C .. pull --ff-only --autostash --quiet || echo "(최신 안내서를 받지 못했습니다. 있는 것으로 진행)"
  .venv/bin/python thumbs.py "$PHOTOS"
} >> "$LOG" 2>&1

if ! command -v claude >/dev/null 2>&1; then
  notify "확인이 필요합니다" "claude 명령을 찾지 못했습니다. 클로드에게 알려 주세요."
  exit 1
fi

OUT=$(cd .. && claude -p "$(cat naver-blog-bot/schedule_prompt.md)" \
        --permission-mode acceptEdits \
        --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash" 2>&1)
echo "$OUT" >> "$LOG"

RESULT=$(echo "$OUT" | grep -E "^RESULT_(OK|FAIL):" | tail -1)
case "$RESULT" in
  RESULT_OK:*)   notify "임시저장 완료" "${RESULT#RESULT_OK: } — 블로그 앱에서 확인 후 발행해 주세요." ;;
  RESULT_FAIL:*) notify "글을 쓰지 못했습니다" "${RESULT#RESULT_FAIL: }" ;;
  *)             notify "확인이 필요합니다" "예약 글쓰기가 멈췄습니다. 블로그 대화에 알려 주세요." ;;
esac

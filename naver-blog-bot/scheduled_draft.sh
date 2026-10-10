#!/bin/bash
# (예약 실행용) 월·수·금 정해진 시간에 블로그 클로드가 새 사진으로 글을 써서 임시저장한다.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
PHOTOS="${BLOG_PHOTO_DIR:-$HOME/Desktop/SH SUCCESSHUB/오피스 사진들}"

# 매시간 깨어나서, 가장 최근 예약 시각(월·수·금 정해진 시간)의 글을 아직 안 썼으면 쓴다.
# 그래서 그 시각에 맥이 꺼져 있었어도 다음에 켜지면 놓친 글을 쓴다. (--now 로 실행하면 바로 쓴다)
if [ "$1" != "--now" ]; then
  DUE=$(.venv/bin/python - "$(cat .schedule_time 2>/dev/null || echo 03:00)" "$(cat .last_schedule 2>/dev/null)" <<'PY'
import sys, datetime as dt
hh, mm = map(int, sys.argv[1].split(":"))
now = dt.datetime.now()
slot = None
for back in range(0, 8):
    d = (now - dt.timedelta(days=back)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if d.weekday() in (0, 2, 4) and d <= now:
        slot = d
        break
last = sys.argv[2].strip()
done = bool(last) and dt.datetime.fromisoformat(last) >= slot
print("no" if (slot is None or done) else "yes")
PY
)
  [ "$DUE" = "yes" ] || exit 0
fi

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

OUT=$(cd .. && claude --no-chrome -p "$(cat naver-blog-bot/schedule_prompt.md)" \
        --permission-mode acceptEdits \
        --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash" 2>&1)
echo "$OUT" >> "$LOG"

date '+%Y-%m-%dT%H:%M:%S' > .last_schedule   # 이번 예약은 처리함 (실패해도 같은 시각엔 다시 안 함)
RESULT=$(echo "$OUT" | grep -E "^RESULT_(OK|FAIL):" | tail -1)
case "$RESULT" in
  RESULT_OK:*)   notify "임시저장 완료" "${RESULT#RESULT_OK: } — 블로그 앱에서 확인 후 발행해 주세요." ;;
  RESULT_FAIL:*) notify "글을 쓰지 못했습니다" "${RESULT#RESULT_FAIL: }" ;;
  *)             notify "확인이 필요합니다" "예약 글쓰기가 멈췄습니다. 블로그 대화에 알려 주세요." ;;
esac

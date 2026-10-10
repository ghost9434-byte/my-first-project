#!/bin/bash
# (자동 실행용) 새 글이 있으면 발행하고, 결과를 맥 알림으로 알려 준다.
# install_auto.sh 가 10분마다 이 파일을 실행하도록 맥에 등록한다.
cd "$(dirname "$0")"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
export NAVER_BOT_NONINTERACTIVE=1

LOCK="/tmp/naver-blog-bot.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # 이전 실행이 아직 진행 중 (2시간 넘게 남아 있으면 지난 실행이 비정상 종료된 것)
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK"; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

mkdir -p logs
LOG="logs/auto-$(date +%Y%m%d).log"
OUT=$(bash "${NAVER_BOT_POST_SCRIPT:-post.sh}" 2>&1)
echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
echo "$OUT" >> "$LOG"

notify() {
  osascript -e "display notification \"$2\" with title \"블로그 올리기\" subtitle \"$1\" sound name \"Glass\"" >/dev/null 2>&1
  echo "[알림] $1 - $2" >> "$LOG"
}
TITLE=$(echo "$OUT" | sed -n 's/^제목: //p' | head -1)
if echo "$OUT" | grep -q "올릴 새 글이 없습니다"; then
  exit 0
elif echo "$OUT" | grep -q "카테고리로 발행했습니다"; then
  notify "발행 완료" "${TITLE:-새 글}"
elif echo "$OUT" | grep -q "임시저장을 눌렀습니다"; then
  notify "임시저장 완료" "${TITLE:-새 글} (발행은 블로그에서 직접 해 주세요)"
else
  notify "확인이 필요합니다" "블로그 올리기가 멈췄습니다. 클로드에게 알려 주세요."
fi

#!/bin/bash
# 월·수·금 오전 10시에 예약 글쓰기(임시저장까지)를 등록한다. 시간 바꾸기: bash install_schedule.sh 9 30  (9시 30분)
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOUR="${1:-10}"; MIN="${2:-0}"
LABEL="com.shsuccesshub.blogdraft"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$BOT_DIR/logs"
DAYS=""
for D in 1 3 5; do
  DAYS="$DAYS<dict><key>Weekday</key><integer>$D</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>"
done
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$BOT_DIR/scheduled_draft.sh</string></array>
  <key>StartCalendarInterval</key>
  <array>$DAYS</array>
  <key>StandardOutPath</key><string>$BOT_DIR/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$BOT_DIR/logs/launchd.log</string>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1
if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null; then
  printf "✅ 예약 글쓰기를 켰습니다: 월·수·금 %02d:%02d (임시저장까지, 끝나면 맥 알림)\n" "$HOUR" "$MIN"
  echo "   지금 한 번 시험: bash $BOT_DIR/scheduled_draft.sh"
  echo "   끄기: bash $BOT_DIR/uninstall_schedule.sh"
else
  echo "❌ 예약 글쓰기를 켜지 못했습니다. 이 화면을 클로드에게 보내 주세요."
fi

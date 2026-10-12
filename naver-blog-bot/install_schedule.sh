#!/bin/bash
# 월·수·금 새벽 3시에 예약 글쓰기(임시저장까지)를 등록한다. 시간 바꾸기: bash install_schedule.sh 9 30  (9시 30분)
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOUR="${1:-3}"; MIN="${2:-0}"
LABEL="com.shsuccesshub.blogdraft"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$BOT_DIR/logs"
printf "%02d:%02d\n" "$HOUR" "$MIN" > "$BOT_DIR/.schedule_time"
# 예약 시각 4분 전에도 한 번 부른다 (맥 예약 깨우기 2시 55분 직후, 다시 잠들기 전에 시작하도록)
T=$(( (10#$HOUR * 60 + 10#$MIN + 1440 - 4) % 1440 )); CH=$(( T / 60 )); CM=$(( T % 60 ))
# 처음 켤 때 지난 예약분을 바로 쓰지 않도록, 지금까지는 처리한 것으로 둔다
[ -f "$BOT_DIR/.last_schedule" ] || date '+%Y-%m-%dT%H:%M:%S' > "$BOT_DIR/.last_schedule"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$BOT_DIR/scheduled_draft.sh</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>$CH</integer><key>Minute</key><integer>$CM</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>$CH</integer><key>Minute</key><integer>$CM</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>$CH</integer><key>Minute</key><integer>$CM</integer></dict>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$BOT_DIR/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$BOT_DIR/logs/launchd.log</string>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1
if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null; then
  printf "✅ 예약 글쓰기를 켰습니다: 월·수·금 %02d:%02d (임시저장까지, 끝나면 맥 알림)\n" "$HOUR" "$MIN"
  echo "   그 시각에 맥이 꺼져 있었으면, 다음에 켜질 때 놓친 글을 씁니다."
  echo "   지금 한 번 시험: bash $BOT_DIR/scheduled_draft.sh --now"
  echo "   끄기: bash $BOT_DIR/uninstall_schedule.sh"
else
  echo "❌ 예약 글쓰기를 켜지 못했습니다. 이 화면을 클로드에게 보내 주세요."
fi

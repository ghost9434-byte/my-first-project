#!/bin/bash
# 맥이 10분마다 새 글을 확인해 자동으로 발행하도록 등록한다. (처음 한 번)
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.shsuccesshub.blogbot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$BOT_DIR/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$BOT_DIR/auto_run.sh</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$BOT_DIR/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$BOT_DIR/logs/launchd.log</string>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1
if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null; then
  echo "✅ 자동 올리기를 켰습니다. 맥북이 켜져 있으면 10분마다 새 글을 확인해 발행합니다."
  echo "   끄려면: bash $BOT_DIR/uninstall_auto.sh"
else
  echo "❌ 자동 올리기를 켜지 못했습니다. 이 화면을 클로드에게 보내 주세요."
fi

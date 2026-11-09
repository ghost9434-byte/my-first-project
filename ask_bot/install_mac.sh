#!/bin/bash
# Mac mini 에서 검색 비서를 웹 서버로 상시 실행(재부팅 후에도 자동 시작)하도록 등록합니다.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.askbot.server"; PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
command -v python3 >/dev/null || { echo "xcode-select --install 후 다시 실행하세요."; exit 1; }
[ -f "$DIR/.env" ] || { cp "$DIR/.env.example" "$DIR/.env"; echo ".env 를 만들었습니다. 키를 입력한 뒤 다시 실행: $DIR/.env"; exit 1; }
chmod 600 "$DIR/.env"; chmod +x "$DIR/serve.sh"; mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/serve.sh</string></array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/logs/out.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/err.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "등록 완료. 접속: http://$(hostname).local:${PORT:-8080}/?t=<ASK_TOKEN>   해제: launchctl unload $PLIST"

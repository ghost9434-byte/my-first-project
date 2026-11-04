#!/bin/bash
# Mac mini 에서 한 번만 실행: 6시간마다 자동 조회하도록 launchd 에 등록합니다.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.flightsearch.bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INTERVAL="${1:-21600}"   # 초 단위, 기본 6시간 (예: ./install_mac.sh 3600)

command -v python3 >/dev/null || { echo "python3 가 없습니다. 'xcode-select --install' 후 다시 실행하세요."; exit 1; }
[ -f "$DIR/.env" ] || { cp "$DIR/.env.example" "$DIR/.env"; echo ".env 를 만들었습니다. 키를 입력한 뒤 다시 실행하세요: $DIR/.env"; exit 1; }
chmod +x "$DIR/run.sh"; chmod 600 "$DIR/.env"
mkdir -p "$DIR/results" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/run.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/results/launchd.log</string>
  <key>StandardErrorPath</key><string>$DIR/results/launchd.err</string>
</dict></plist>
PL

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "등록 완료: ${INTERVAL}초마다 실행. 최신 결과: $DIR/results/latest.txt"
echo "해제: launchctl unload $PLIST"

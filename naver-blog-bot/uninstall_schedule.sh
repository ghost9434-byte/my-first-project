#!/bin/bash
LABEL="com.shsuccesshub.blogdraft"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || launchctl unload -w "$PLIST" >/dev/null 2>&1
rm -f "$PLIST"
echo "✅ 예약 글쓰기를 껐습니다."

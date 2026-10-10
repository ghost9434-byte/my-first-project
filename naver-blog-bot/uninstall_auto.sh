#!/bin/bash
# 자동 올리기를 끈다. (바탕화면 아이콘은 그대로 쓸 수 있음)
LABEL="com.shsuccesshub.blogbot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || launchctl unload -w "$PLIST" >/dev/null 2>&1
rm -f "$PLIST"
echo "✅ 자동 올리기를 껐습니다."

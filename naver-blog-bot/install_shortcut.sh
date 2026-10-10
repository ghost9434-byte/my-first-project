#!/bin/bash
# 바탕화면에 '블로그 올리기' 바로가기를 만든다. (처음 한 번만 실행)
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/Desktop/블로그 올리기.command"
cat > "$TARGET" <<SCRIPT
#!/bin/bash
# 더블클릭하면 클로드가 올려 둔 새 글을 받아 네이버 블로그에 발행합니다.
clear
echo "=== 네이버 블로그 올리기 ==="
bash "$BOT_DIR/post.sh"
echo ""
read -p "끝났습니다. 이 창은 닫으셔도 됩니다 (엔터)... "
SCRIPT
chmod +x "$TARGET"
echo "✅ 바탕화면에 '블로그 올리기' 바로가기를 만들었습니다. 더블클릭하면 실행됩니다."

# 아이콘을 오피스 로고로 (assets/logo.png 가 있을 때, 또는 첫 번째 인자로 그림 파일을 주면)
LOGO="${1:-$BOT_DIR/assets/logo.png}"
if [ -f "$LOGO" ] && command -v osascript >/dev/null 2>&1; then
  RESULT=$(osascript -l JavaScript <<JS 2>&1
ObjC.import('AppKit');
var img = \$.NSImage.alloc.initWithContentsOfFile('$LOGO');
img.isNil() ? 'noimage' : (\$.NSWorkspace.sharedWorkspace.setIconForFileOptions(img, '$TARGET', 0) ? 'ok' : 'fail');
JS
)
  if [ "$RESULT" = "ok" ]; then
    echo "✅ 바로가기 아이콘을 오피스 로고로 바꿨습니다."
  else
    echo "⚠️ 아이콘은 바꾸지 못했습니다 ($RESULT). 바로가기는 그대로 쓰실 수 있습니다."
  fi
fi

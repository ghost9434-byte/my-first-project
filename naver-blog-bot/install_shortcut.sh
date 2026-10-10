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

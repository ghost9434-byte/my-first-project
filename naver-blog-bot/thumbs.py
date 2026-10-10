"""(예약 글쓰기용) 사진 폴더의 사진을 클로드가 볼 수 있게 작은 JPG 미리보기로 만든다.

    .venv/bin/python thumbs.py "<사진 폴더>"
→ .thumbs/ 에 미리보기를 만들고, .thumbs/index.tsv 에 '미리보기<TAB>원본 경로' 를 적는다.
  이미 쓴 사진(.used_photos 에 적힌 원본)은 index 에서 뺀다.
"""
import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent
THUMBS = BASE / ".thumbs"
USED = BASE / ".used_photos"
EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


def main():
    src = Path(sys.argv[1]).expanduser()
    if not src.is_dir():
        print(f"사진 폴더가 없습니다: {src}")
        sys.exit(1)
    THUMBS.mkdir(exist_ok=True)
    used = set(USED.read_text(encoding="utf-8").splitlines()) if USED.exists() else set()
    rows, skipped = [], 0
    for f in sorted(p for p in src.rglob("*") if p.suffix.lower() in EXT and not p.name.startswith(".")):
        if str(f) in used:
            skipped += 1
            continue
        key = hashlib.md5(str(f).encode()).hexdigest()[:10]
        t = THUMBS / f"{key}.jpg"
        if not t.exists():
            try:
                im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
                im.thumbnail((768, 768))
                im.save(t, quality=80)
            except Exception as e:
                print(f"건너뜀 (열 수 없음): {f.name} - {e}")
                continue
        rows.append(f"{t}\t{f}")
    (THUMBS / "index.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"아직 안 쓴 사진 {len(rows)}장 (이미 쓴 사진 {skipped}장 제외) → {THUMBS / 'index.tsv'}")


if __name__ == "__main__":
    main()

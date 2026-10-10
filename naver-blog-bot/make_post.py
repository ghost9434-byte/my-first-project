"""(클로드용) 사진으로 새 글 폴더를 만든다.

python3 make_post.py <글이름> <사진1> <사진2> ...
→ posts/<오늘날짜>-<글이름>/images/ 에 사진을 JPG(긴 변 1600px)로 바꿔 넣고
  post.json 뼈대를 만든다. 본문은 클로드가 채운다.
"""
import json
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    slug, photos = sys.argv[1], sys.argv[2:]
    folder = BASE / "posts" / f"{date.today():%Y-%m-%d}-{slug}"
    (folder / "images").mkdir(parents=True, exist_ok=True)
    names = []
    for i, src in enumerate(photos, 1):
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        im.thumbnail((1600, 1600))
        name = f"photo{i:02d}.jpg"
        im.save(folder / "images" / name, quality=88)
        names.append(f"images/{name}")
    post = folder / "post.json"
    if not post.exists():
        blocks = [{"type": "image", "file": names[0]}, {"type": "html", "html": "<p>본문</p>"}]
        blocks += [{"type": "image", "file": n} for n in names[1:]]
        post.write_text(json.dumps({"blog_id": "shsuccesshub", "title": "제목", "category": "목포 맛집·생활정보",
                                    "tags": [], "publish": True, "blocks": blocks},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(folder)
    for n in names:
        print("  " + n)


if __name__ == "__main__":
    main()

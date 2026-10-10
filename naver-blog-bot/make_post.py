"""(클로드용) 사진·동영상으로 새 글 폴더를 만든다.

python3 make_post.py <글이름> <사진1> <사진2> <동영상1> ...
→ posts/<오늘날짜>-<글이름>/images/ 에 사진을 JPG(긴 변 1600px)로 바꿔 넣고
  동영상은 videos/ 에 넣는다 (ffmpeg 가 있으면 촬영 위치 등 정보를 지운다. 화질은 그대로).
  post.json 뼈대를 만든다. 본문은 클로드가 채운다.
"""
import json
import shutil
import subprocess
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
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".wmv", ".mkv", ".mpg", ".mpeg", ".3gp", ".webm"}


def copy_video(src, dst):
    """촬영 위치 같은 정보를 지우고 복사한다. ffmpeg 가 없으면 그대로 복사."""
    ff = shutil.which("ffmpeg")
    if ff:
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-map", "0", "-map_metadata", "-1",
                            "-c", "copy", "-movflags", "+faststart", str(dst)], capture_output=True)
        if r.returncode == 0:
            return "위치정보 지움"
    shutil.copy2(src, dst)
    return "그대로 복사 (ffmpeg 없음: 촬영 위치 정보가 남아 있을 수 있음)"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    slug, photos = sys.argv[1], sys.argv[2:]
    folder = BASE / "posts" / f"{date.today():%Y-%m-%d}-{slug}"
    (folder / "images").mkdir(parents=True, exist_ok=True)
    names, videos = [], []
    photo_no = 0
    for src in photos:
        if Path(src).suffix.lower() in VIDEO_EXT:
            (folder / "videos").mkdir(exist_ok=True)
            name = f"video{len(videos) + 1:02d}{Path(src).suffix.lower()}"
            how = copy_video(src, folder / "videos" / name)
            videos.append(f"videos/{name}")
            print(f"  동영상 {name}: {how}")
            continue
        photo_no += 1
        i = photo_no
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        im.thumbnail((1600, 1600))
        name = f"photo{i:02d}.jpg"
        im.save(folder / "images" / name, quality=88)
        names.append(f"images/{name}")
    post = folder / "post.json"
    if not post.exists():
        blocks = [{"type": "image", "file": n} for n in names[:1]] + [{"type": "html", "html": "<p>본문</p>"}]
        blocks += [{"type": "image", "file": n} for n in names[1:]]
        blocks += [{"type": "video", "file": v, "title": "동영상 제목", "desc": ""} for v in videos]
        post.write_text(json.dumps({"blog_id": "shsuccesshub", "title": "제목", "category": "목포 맛집·생활정보",
                                    "tags": [], "publish": True, "blocks": blocks},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(folder)
    for n in names + videos:
        print("  " + n)


if __name__ == "__main__":
    main()

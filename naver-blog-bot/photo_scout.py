"""(클로드용) 사진 묶음에서 '언제, 어디를 다녀왔는지' 방문 목록을 만든다 — 맛집·여행 글감 찾기.

    .venv/bin/python photo_scout.py ~/Downloads/블로그후보.zip [다른 폴더나 zip ...]
    .venv/bin/python photo_scout.py <폴더> --offline        # 지도 검색 없이 날짜·좌표만

하는 일
  1. 사진(JPG·HEIC·PNG)의 촬영 시각과 GPS 위치를 읽는다. (구글 포토에서 받은 zip 도 그대로 넣으면 된다)
  2. 같은 날, 가까운 곳(1km 안, 3시간 안)에서 찍은 사진을 '방문 1건'으로 묶는다.
  3. scout_exclude.json 에 적어 둔 곳 근처 사진은 뺀다 (없으면 모두 쓴다 — 회장님은 댁·오피스 사진도 괜찮다고 하심).
  4. 방문마다 지역 이름(오픈스트리트맵)과, 카카오 키가 있으면 근처 식당·카페 후보 이름을 붙인다.
→ scout/visits.md (목록), scout/visit-XX.jpg (사진 모음), scout/visits.json

식당 이름은 '후보'일 뿐이다. 사진 위치는 몇십 미터 틀릴 수 있으니 글에 쓰기 전에 회장님께 확인받는다.

설정 (맥북에만 두는 파일, GitHub로 오가지 않음)
  scout_exclude.json : [{"name": "댁", "lat": 34.8, "lon": 126.4, "radius_m": 500}, ...]
  카카오 키           : 환경 변수 KAKAO_REST_KEY 또는 파일 .kakao_key (한 줄)
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent
OUT = BASE / "scout"
CACHE = BASE / ".scout_cache.json"
EXCLUDE = BASE / "scout_exclude.json"
PHOTO_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png"}
UA = "shsuccesshub-blog-bot/1.0 (personal blog helper)"
GAP_HOURS, GAP_KM = 3, 1.0


# ---------- 사진 정보 읽기 ----------
def _deg(v):
    d, m, s = (float(x) for x in v)
    return d + m / 60 + s / 3600


def read_photo(path):
    """(촬영 시각, 위도, 경도) — 없으면 None. 구글 테이크아웃의 .json 짝 파일도 본다."""
    when = lat = lon = None
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            dt = ex.get_ifd(0x8769).get(36867) or ex.get(306)
            if dt:
                when = datetime.strptime(str(dt)[:19], "%Y:%m:%d %H:%M:%S")
            g = ex.get_ifd(0x8825)
            if g.get(2) and g.get(4):
                lat, lon = _deg(g[2]), _deg(g[4])
                if g.get(1) == "S":
                    lat = -lat
                if g.get(3) == "W":
                    lon = -lon
    except Exception:
        pass
    side = Path(str(path) + ".json")
    if (lat is None or when is None) and side.exists():
        try:
            j = json.loads(side.read_text(encoding="utf-8"))
            geo = j.get("geoDataExif") or j.get("geoData") or {}
            if lat is None and geo.get("latitude"):
                lat, lon = geo["latitude"], geo["longitude"]
            ts = (j.get("photoTakenTime") or {}).get("timestamp")
            if when is None and ts:
                when = datetime.fromtimestamp(int(ts))
        except Exception:
            pass
    if lat is not None and abs(lat) < 1e-6 and abs(lon) < 1e-6:
        lat = lon = None
    return when, lat, lon


def km(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def gather(sources, work):
    """폴더와 zip 에서 사진 파일을 모은다. zip 은 work 폴더에 풀어 둔다."""
    files = []
    for src in sources:
        src = Path(src).expanduser()
        if src.suffix.lower() == ".zip":
            dest = work / src.stem
            if not dest.exists():
                with zipfile.ZipFile(src) as z:
                    z.extractall(dest)
            src = dest
        if src.is_file():
            files.append(src)
        elif src.is_dir():
            files += [p for p in src.rglob("*") if p.suffix.lower() in PHOTO_EXT and not p.name.startswith("._")]
    return sorted(set(files))


def load_exclude():
    if EXCLUDE.exists():
        return json.loads(EXCLUDE.read_text(encoding="utf-8"))
    return []


def group_visits(items):
    """items: [(시각, 위도, 경도, 경로)] 시간순 → 방문 묶음."""
    visits = []
    for it in sorted(items, key=lambda x: x[0]):
        if visits:
            last = visits[-1][-1]
            if (it[0] - last[0]).total_seconds() < GAP_HOURS * 3600 and km(it[1:3], last[1:3]) < GAP_KM:
                visits[-1].append(it)
                continue
        visits.append([it])
    return visits


# ---------- 지도 검색 ----------
def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


class Places:
    def __init__(self, offline=False):
        self.offline = offline
        self.cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        key = os.environ.get("KAKAO_REST_KEY") or ""
        kf = BASE / ".kakao_key"
        if not key and kf.exists():
            key = kf.read_text().strip()
        self.kakao = key
        self.last_osm = 0.0

    def save(self):
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")

    def area(self, lat, lon):
        """동네 이름 (오픈스트리트맵, 1초에 한 번만 묻는다)."""
        k = f"osm:{lat:.4f},{lon:.4f}"
        if k in self.cache or self.offline:
            return self.cache.get(k, "")
        wait = 1.1 - (time.time() - self.last_osm)
        if wait > 0:
            time.sleep(wait)
        try:
            q = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 16, "accept-language": "ko"})
            j = _get("https://nominatim.openstreetmap.org/reverse?" + q, {"User-Agent": UA})
            a = j.get("address", {})
            parts = [a.get(x) for x in ("province", "state", "city", "county", "borough", "town", "suburb", "village", "quarter")]
            name = " ".join(dict.fromkeys(p for p in parts if p))
            if j.get("name") and j.get("name") not in name:
                name += f" ({j['name']})"
        except Exception as e:
            name = f"(지역 이름을 못 가져옴: {e.__class__.__name__})"
        self.last_osm = time.time()
        self.cache[k] = name
        return name

    def nearby(self, lat, lon, radius=60):
        """근처 식당(FD6)·카페(CE7) 후보 — 카카오 키가 있을 때만."""
        if not self.kakao or self.offline:
            return []
        out = []  # 카카오 약관상 결과를 저장하지 않고 그때그때 묻는다
        for cat in ("FD6", "CE7", "AT4"):
            try:
                q = urllib.parse.urlencode({"category_group_code": cat, "x": lon, "y": lat, "radius": radius, "sort": "distance"})
                j = _get("https://dapi.kakao.com/v2/local/search/category.json?" + q,
                         {"Authorization": f"KakaoAK {self.kakao}"})
                for d in j.get("documents", [])[:3]:
                    out.append({"name": d["place_name"], "kind": d.get("category_name", "").split(" > ")[-1],
                                "dist_m": int(d.get("distance") or 0), "addr": d.get("road_address_name") or d.get("address_name"),
                                "phone": d.get("phone", ""), "url": d.get("place_url", "")})
            except Exception:
                pass
        out.sort(key=lambda d: d["dist_m"])
        return out[:5]


# ---------- 결과 ----------
def contact_sheet(paths, dest, cols=4, cell=300):
    paths = paths[:12]
    rows = math.ceil(len(paths) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    for i, p in enumerate(paths):
        try:
            with Image.open(p) as im:
                t = ImageOps.exif_transpose(im).convert("RGB")
                t.thumbnail((cell - 6, cell - 6))
                sheet.paste(t, ((i % cols) * cell + 3, (i // cols) * cell + 3))
        except Exception:
            pass
    sheet.save(dest, quality=80)


def main():
    ap = argparse.ArgumentParser(description="사진 위치·날짜로 방문 목록 만들기")
    ap.add_argument("sources", nargs="+", help="사진 폴더 또는 구글 포토에서 받은 zip")
    ap.add_argument("--offline", action="store_true", help="지도 검색 없이")
    ap.add_argument("--min-photos", type=int, default=2, help="이보다 적은 방문은 목록에서 뺀다")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    work = OUT / "_unzipped"
    work.mkdir(exist_ok=True)
    files = gather(a.sources, work)
    print(f"사진 {len(files)}장을 읽습니다...", flush=True)
    exclude = load_exclude()
    items, no_gps, excluded = [], 0, 0
    for f in files:
        when, lat, lon = read_photo(f)
        if when is None or lat is None:
            no_gps += 1
            continue
        if any(km((lat, lon), (e["lat"], e["lon"])) * 1000 < e.get("radius_m", 500) for e in exclude):
            excluded += 1
            continue
        items.append((when, lat, lon, f))
    visits = [v for v in group_visits(items) if len(v) >= a.min_photos]
    places = Places(a.offline)
    result = []
    for n, v in enumerate(visits, 1):
        lat = sum(x[1] for x in v) / len(v)
        lon = sum(x[2] for x in v) / len(v)
        rec = {"no": n, "start": v[0][0].strftime("%Y-%m-%d %H:%M"), "end": v[-1][0].strftime("%H:%M"),
               "lat": round(lat, 6), "lon": round(lon, 6), "photos": [str(x[3]) for x in v],
               "area": places.area(lat, lon), "candidates": places.nearby(lat, lon)}
        contact_sheet([x[3] for x in v], OUT / f"visit-{n:02d}.jpg")
        result.append(rec)
        print(f"  {n:>2}. {rec['start']} · {rec['area'] or '(지역 미확인)'} · 사진 {len(v)}장", flush=True)
    places.save()

    (OUT / "visits.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# 방문 목록 ({datetime.now():%Y-%m-%d %H:%M} 만듦)\n",
          f"사진 {len(files)}장 중 위치 있는 {len(items)}장 → 방문 {len(result)}건"
          f" (위치·시각 없음 {no_gps}장, 제외 지역이라 뺀 사진 {excluded}장)\n",
          "식당 이름은 후보입니다. 글에 쓰기 전에 회장님께 확인받으세요.\n"]
    for r in result:
        md.append(f"## {r['no']}. {r['start']}~{r['end']} · {r['area'] or '(지역 미확인)'}")
        md.append(f"- 사진 {len(r['photos'])}장 · 모음: scout/visit-{r['no']:02d}.jpg · 지도: "
                  f"https://map.kakao.com/link/map/{r['lat']},{r['lon']}")
        for c in r["candidates"]:
            md.append(f"- 후보: {c['name']} ({c['kind']}, {c['dist_m']}m) {c['addr']} {c['phone']}")
        md.append("")
    (OUT / "visits.md").write_text("\n".join(md), encoding="utf-8")
    print(f"✅ 저장: {OUT / 'visits.md'}")


if __name__ == "__main__":
    main()

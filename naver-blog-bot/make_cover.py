"""(클로드용) 글 맨 위 대표 사진 만들기 — 실제 사진 위에 제목을 얹는다.

    .venv/bin/python make_cover.py <글폴더> <사진> --title 소도 --label "목포 맛집 · 덕자 전문점" \
        --sub "찰진 덕자회와 칼칼한 덕자찜" --info "☎ 061-281-0086 · 목포시 부흥로 1" [--style auto|photo|band|frame]

→ <글폴더>/images/cover.jpg (1080×1080, 네이버 목록·모바일 썸네일에 맞는 정사각형)
--style (기본 auto: 카테고리로 고름 — 개인 글(일상·여행·식물)=diary, 맛집·생활정보=photo, 오피스 소식·창업정보=frame, 그 밖=band)
  photo : 사진 꽉 + 아래쪽 어둡게 + 흰 큰 제목 (맛집 블로그에서 가장 흔한 모양, 기본)
  band  : 사진 꽉 + 가운데 흰 띠 + 진한 제목
  frame : 사진 살짝 어둡게 + 흰 테두리 + 가운데 굵은 제목
  clean : 위에 큰 사진 + 아래 흰 바탕에 빨간 포인트·검정 굵은 제목 (회장님 개인 글 기본, 한미약품 홈페이지 색감)
  diary : 크림색 종이 위에 폴라로이드 사진 + 손글씨 제목 (개인 글의 다른 모양)
--en "MY ROOM · PLANT" : clean 모양 제목 위 영문 한 줄 (없으면 SH SUCCESS HUB)
--focus 0.5,0.4 : 사진에서 남길 중심 (가로,세로 0~1). 음식이 아래쪽이면 세로를 키운다.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:  # 아이폰 HEIC 사진도 바로 쓸 수 있게
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent
FONTS = BASE / "assets" / "fonts"
BLUE = (47, 93, 212)
SIZE = 1080


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


TITLE = lambda s: font("BlackHanSans-Regular.ttf", s)
BOLD = lambda s: font("NanumGothic-ExtraBold.ttf", s)
TEXT = lambda s: font("NanumGothic-Bold.ttf", s)
HAND = lambda s: font("NanumPenScript-Regular.ttf", s)
PRET = lambda s, w="Bold": font(f"Pretendard-{w}.otf", s)
POP = lambda s, w="SemiBold": font(f"Poppins-{w}.ttf", s)
# 회장님이 좋아하시는 한미약품 홈페이지 색감 (맥북 클로드가 홈페이지에서 읽은 값)
RED = (225, 37, 27)        # #E1251B
INK_BLACK = (0, 0, 0)
GRAY_D, GRAY_M, GRAY_L = (82, 82, 82), (105, 105, 105), (139, 139, 139)
BG_LIGHT = (249, 249, 249)  # #F9F9F9
PAPER = (244, 239, 228)
INK = (52, 46, 40)


def crop_square(img, focus=(0.5, 0.5), size=SIZE):
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = min(max(int(w * focus[0] - side / 2), 0), w - side)
    top = min(max(int(h * focus[1] - side / 2), 0), h - side)
    return img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)


def crop_rect(img, w, h, focus=(0.5, 0.5)):
    """원본에서 w:h 비율로 잘라 w×h 로 만든다 (focus 가 남길 중심)."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    W, H = img.size
    if W / H > w / h:
        cw, ch = int(H * w / h), H
    else:
        cw, ch = W, int(W * h / w)
    left = min(max(int(W * focus[0] - cw / 2), 0), W - cw)
    top = min(max(int(H * focus[1] - ch / 2), 0), H - ch)
    return img.crop((left, top, left + cw, top + ch)).resize((w, h), Image.LANCZOS)


CLEAN_PH = 740  # clean 모양에서 사진이 차지하는 높이


def fit(text, maker, start, max_w):
    """한 줄이 max_w 를 넘지 않는 가장 큰 글자 크기."""
    s = start
    while s > 20 and maker(s).getlength(text) > max_w:
        s -= 4
    return maker(s)


def shadow_text(base, xy, text, f, fill=(255, 255, 255), anchor="la", blur=6, alpha=150):
    sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 2, xy[1] + 3), text, font=f, fill=(0, 0, 0, alpha), anchor=anchor)
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(base).text(xy, text, font=f, fill=fill, anchor=anchor)


def pill(base, xy, text, f, bg=BLUE, fg=(255, 255, 255), pad=(26, 14), anchor="l"):
    d = ImageDraw.Draw(base)
    w = d.textlength(text, font=f)
    hgt = f.size + pad[1] * 2
    x = xy[0] - (w / 2 + pad[0] if anchor == "m" else 0)
    box = (x, xy[1], x + w + pad[0] * 2, xy[1] + hgt)
    d.rounded_rectangle(box, radius=hgt // 2, fill=bg)
    d.text((x + pad[0], xy[1] + hgt / 2), text, font=f, fill=fg, anchor="lm")
    return box


def gradient(size, start_frac, max_alpha):
    """아래로 갈수록 어두워지는 막."""
    g = Image.new("L", (1, size))
    for y in range(size):
        t = max(0.0, (y / size - start_frac) / (1 - start_frac))
        g.putpixel((0, y), int(max_alpha * t ** 1.4))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    layer.putalpha(g.resize((size, size)))
    return layer


def brand(base, color=(255, 255, 255, 210), anchor="rd", xy=None):
    d = ImageDraw.Draw(base)
    d.text(xy or (SIZE - 48, SIZE - 40), "SH SUCCESS HUB", font=BOLD(24), fill=color, anchor=anchor)


def style_photo(img, a):
    base = img.convert("RGBA")
    base.alpha_composite(gradient(SIZE, 0.35, 225))
    x, w = 72, SIZE - 144
    y = SIZE - 96
    if a.info:
        f = TEXT(32)
        ImageDraw.Draw(base).text((x, y), a.info, font=f, fill=(255, 255, 255, 235), anchor="ld")
        y -= 60
    for line in reversed(a.sub.split("|") if a.sub else []):
        shadow_text(base, (x, y), line, TEXT(40), anchor="ld")
        y -= 56
    tf = fit(a.title, TITLE, 170, w)
    y -= 12
    shadow_text(base, (x, y), a.title, tf, anchor="ld", blur=10, alpha=170)
    y -= tf.size + 22
    if a.label:
        pill(base, (x, y - 56), a.label, BOLD(30))
    brand(base, anchor="ra", xy=(SIZE - 48, 44))
    return base


def style_band(img, a):
    base = img.convert("RGBA")
    sub = a.sub.split("|") if a.sub else []
    tf = fit(a.title, TITLE, 150, SIZE - 220)
    band_h = 70 + (50 if a.label else 0) + tf.size + 20 + 52 * len(sub) + (56 if a.info else 0) + 40
    top = (SIZE - band_h) // 2
    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle((0, top, SIZE, top + band_h), fill=(255, 255, 255, 228))
    base.alpha_composite(ov)
    d = ImageDraw.Draw(base)
    d.rectangle((SIZE // 2 - 40, top, SIZE // 2 + 40, top + 8), fill=BLUE)
    y = top + 60
    if a.label:
        d.text((SIZE / 2, y), a.label, font=BOLD(32), fill=BLUE, anchor="mt")
        y += 50
    d.text((SIZE / 2, y), a.title, font=tf, fill=(34, 34, 34), anchor="mt")
    y += tf.size + 24
    for line in sub:
        d.text((SIZE / 2, y), line, font=TEXT(36), fill=(70, 70, 70), anchor="mt")
        y += 52
    if a.info:
        d.text((SIZE / 2, y + 10), a.info, font=TEXT(28), fill=(110, 110, 110), anchor="mt")
    brand(base, color=(255, 255, 255, 220))
    return base


def style_frame(img, a):
    base = img.convert("RGBA")
    base.alpha_composite(Image.new("RGBA", base.size, (0, 0, 0, 105)))
    base.alpha_composite(gradient(SIZE, 0.0, 70))
    d = ImageDraw.Draw(base)
    m = 44
    d.rectangle((m, m, SIZE - m, SIZE - m), outline=(255, 255, 255, 235), width=4)
    sub = a.sub.split("|") if a.sub else []
    tf = fit(a.title, TITLE, 190, SIZE - 2 * m - 120)
    block = (60 if a.label else 0) + tf.size + 30 + 54 * len(sub)
    y = (SIZE - block) // 2 - 20
    if a.label:
        shadow_text(base, (SIZE / 2, y), a.label, BOLD(34), anchor="mt")
        y += 60
    shadow_text(base, (SIZE / 2, y), a.title, tf, anchor="mt", blur=12, alpha=180)
    y += tf.size + 34
    for line in sub:
        shadow_text(base, (SIZE / 2, y), line, TEXT(38), anchor="mt")
        y += 54
    if a.info:
        pill(base, (SIZE / 2, SIZE - m - 120), a.info, BOLD(28), anchor="m")
    brand(base, anchor="md", xy=(SIZE / 2, SIZE - m - 26))
    return base


def style_clean(img, a):
    """개인 글 기본: 깔끔한 기업 홈페이지 느낌. 사진은 크게, 글은 흰 바탕에 정갈하게."""
    base = Image.new("RGBA", (SIZE, SIZE), BG_LIGHT + (255,))
    ph = CLEAN_PH
    base.paste(img, (0, 0))
    d = ImageDraw.Draw(base)
    x = 76
    d.rectangle((x, ph + 44, x + 56, ph + 50), fill=RED)
    en = (getattr(a, "en", "") or "SH SUCCESS HUB").upper()
    d.text((x + 76, ph + 47), "  ".join(en.split(" ")) if len(en) < 18 else en, font=POP(24), fill=RED, anchor="lm")
    tf = PRET(70)
    while tf.getlength(a.title) > SIZE - 2 * x and tf.size > 44:
        tf = PRET(tf.size - 4)
    d.text((x, ph + 76), a.title, font=tf, fill=INK_BLACK, anchor="la")
    y = ph + 76 + tf.size + 18
    if a.sub:
        d.text((x, y), a.sub.replace("|", " · "), font=PRET(32, "Medium"), fill=GRAY_M, anchor="la")
    foot = SIZE - 40
    if a.label:
        d.text((x, foot), a.label, font=PRET(22, "SemiBold"), fill=GRAY_L, anchor="ld")
    if a.info:
        d.text((SIZE - x, foot), a.info, font=POP(22, "Medium"), fill=GRAY_L, anchor="rd")
    return base


def style_diary(img, a):
    """개인 글용: 오피스 글과 확 다르게 — 종이 위에 붙인 폴라로이드와 손글씨."""
    import random
    rnd = random.Random(a.title)
    # 종이 (아주 옅은 결)
    base = Image.new("RGBA", (SIZE, SIZE), PAPER + (255,))
    grain = Image.effect_noise((SIZE, SIZE), 18).convert("L").point(lambda v: 128 + (v - 128) // 3)
    base = Image.blend(base, Image.merge("RGBA", (grain, grain, grain, Image.new("L", (SIZE, SIZE), 255))), 0.06)
    # 폴라로이드
    ph = 640
    pad, bottom = 30, 150
    card = Image.new("RGBA", (ph + pad * 2, ph + pad + bottom), (253, 252, 248, 255))
    card.paste(img.resize((ph, ph), Image.LANCZOS), (pad, pad))
    d = ImageDraw.Draw(card)
    hf = HAND(110)
    while hf.getlength(a.title) > ph and hf.size > 50:
        hf = HAND(hf.size - 6)
    d.text((card.width / 2, ph + pad + bottom / 2 + 4), a.title, font=hf, fill=INK, anchor="mm")
    angle = rnd.choice([-3.2, -2.4, 2.4, 3.2])
    rot = card.rotate(angle, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    shadow.putalpha(rot.getchannel("A").point(lambda v: 70 if v else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    x, y = (SIZE - rot.width) // 2, 34
    base.alpha_composite(shadow, (x + 8, y + 14))
    base.alpha_composite(rot, (x, y))
    # 마스킹 테이프
    tape = Image.new("RGBA", (210, 54), (226, 208, 170, 175))
    tape = tape.rotate(-angle * 2.5 + rnd.choice([-6, 6]), resample=Image.BICUBIC, expand=True)
    base.alpha_composite(tape, (SIZE // 2 - tape.width // 2, y - 6))
    # 아래 작은 글: 분류 · 한 줄 · 날짜
    dd = ImageDraw.Draw(base)
    y0 = y + rot.height + 6
    if a.label:
        dd.text((SIZE / 2, y0), a.label, font=BOLD(26), fill=(150, 120, 80), anchor="mt")
        y0 += 42
    if a.sub:
        dd.text((SIZE / 2, y0), a.sub.replace("|", " · "), font=HAND(46), fill=INK, anchor="mt")
    dd.text((SIZE - 44, SIZE - 30), a.info or "SH SUCCESS HUB", font=HAND(34), fill=(120, 110, 98), anchor="rd")
    return base


STYLES = {"photo": style_photo, "band": style_band, "frame": style_frame, "clean": style_clean, "diary": style_diary}

# 글감(카테고리)에 따라 모양을 고른다 (회장님: "글감에 따라 알아서")
#   맛집·생활정보 → photo (음식이 크게 보이게) / 오피스 소식·창업정보 → frame (행사·소식, 무게감)
#   룸·회의실·오시는 길·필독 → band (정보 위주, 깔끔하게)
def auto_style(category=""):
    c = category or ""
    if any(k in c for k in ("일상", "여행", "식물", "대표", "오피스 밖")):  # 회장님 개인 글
        return "clean"
    if "맛집" in c or "생활" in c:
        return "photo"
    if "소식" in c or "창업" in c:
        return "frame"
    if c:
        return "band"
    return "photo"


def make(photo, out, title, label="", sub="", info="", style="photo", focus=(0.5, 0.5), category="", en=""):
    if style == "auto":
        style = auto_style(category)
    a = argparse.Namespace(title=title, label=label, sub=sub, info=info, en=en, focus=focus)
    if style == "clean":
        img = crop_rect(Image.open(photo), SIZE, CLEAN_PH, focus)
    else:
        img = crop_square(Image.open(photo), focus)
    STYLES[style](img, a).convert("RGB").save(out, "JPEG", quality=90)
    return out, style


def main():
    ap = argparse.ArgumentParser(description="대표 사진 만들기 (실사 사진 + 제목)")
    ap.add_argument("folder", help="글 폴더 (posts/<이름> 또는 그 이름)")
    ap.add_argument("photo")
    ap.add_argument("--title", required=True)
    ap.add_argument("--label", default="", help="제목 위 작은 말 (예: 목포 맛집 · 덕자 전문점)")
    ap.add_argument("--sub", default="", help="제목 아래 한두 줄. 줄은 | 로 나눈다")
    ap.add_argument("--info", default="", help="전화·주소 한 줄")
    ap.add_argument("--style", choices=["auto", *STYLES], default="auto",
                    help="auto(기본): 글 폴더 post.json 의 카테고리로 고름")
    ap.add_argument("--category", default="", help="auto 일 때 쓸 카테고리 (없으면 post.json 에서 읽음)")
    ap.add_argument("--en", default="", help="clean 모양: 제목 위 영문 한 줄 (예: MY ROOM · PLANT)")
    ap.add_argument("--focus", default="0.5,0.5")
    ap.add_argument("--out", default="cover.jpg")
    a = ap.parse_args()
    folder = Path(a.folder)
    if not folder.exists():
        folder = BASE / "posts" / a.folder
    (folder / "images").mkdir(parents=True, exist_ok=True)
    out = folder / "images" / a.out
    category = a.category
    if not category and (folder / "post.json").exists():
        category = json.loads((folder / "post.json").read_text(encoding="utf-8")).get("category", "")
    _, style = make(a.photo, out, a.title, a.label, a.sub, a.info, a.style,
                    tuple(float(v) for v in a.focus.split(",")), category, a.en)
    print(f"✅ 대표 사진: {out} (모양: {style}, 카테고리: {category or '-'})")


if __name__ == "__main__":
    main()

"""내 블로그 글 전체 읽어 오기.

    .venv/bin/python read_blog.py            # 최근 글 30편
    .venv/bin/python read_blog.py --limit 10

블로그 RSS 로 글 목록(제목, 날짜, 카테고리, 주소)을 받고, 글마다 모바일 화면을 열어
본문 글자·사진 수·태그·공감/댓글 수를 모은다.
→ blog_snapshot/posts.json (자료), blog_snapshot/posts.md (읽기 쉬운 정리), blog_snapshot/<글번호>.png (화면)
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from blog_bot import BASE, Bot, BotError
from read_page import scroll_all

BLOG_ID = "shsuccesshub"
RSS_URL = os.environ.get("NAVER_BOT_RSS_URL", "https://rss.blog.naver.com/{blog}.xml")
POST_URL = os.environ.get("NAVER_BOT_POST_URL", "https://m.blog.naver.com/{blog}/{log}")
OUT = BASE / "blog_snapshot"


def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        get = lambda k: (it.findtext(k) or "").strip()
        link = get("link")
        m = re.search(r"/(\d{6,})", link) or re.search(r"logNo=(\d+)", link)
        date = get("pubDate")
        try:
            date = parsedate_to_datetime(date).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        items.append({"title": get("title"), "link": link, "log_no": m.group(1) if m else "",
                      "date": date, "category": get("category"), "tags": get("tag"),
                      "summary": re.sub(r"<[^>]+>", "", get("description"))[:200]})
    return items


POST_JS = r"""() => {
  const main = document.querySelector('.se-main-container') || document.querySelector('#viewTypeSelector, .post_ct, #postViewArea');
  const text = main ? main.innerText.trim() : '';
  const images = main ? main.querySelectorAll('img').length : 0;
  const tags = [...document.querySelectorAll('a, span')].map(e => e.innerText.trim())
                 .filter(t => /^#[^\s#]{1,30}$/.test(t));
  const grab = (re) => { const m = document.body.innerText.match(re); return m ? m[1] : ''; };
  return {text, images, tags: [...new Set(tags)].slice(0, 30),
          likes: grab(/공감\s*([\d,]+)/), comments: grab(/댓글\s*([\d,]+)/)};
}"""


def tags_str(t):
    if isinstance(t, list):
        return " ".join(t) or "-"
    return t or "-"


def main():
    ap = argparse.ArgumentParser(description="내 블로그 글 읽어 오기")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--blog", default=BLOG_ID)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    bot = Bot()
    try:
        with sync_playwright() as pw:
            ctx, page = bot.open_browser(pw)
            try:
                r = ctx.request.get(RSS_URL.format(blog=args.blog))
                if not r.ok:
                    raise BotError(f"글 목록(RSS)을 받지 못했습니다 (응답 {r.status})")
                items = parse_rss(r.text())[: args.limit]
                print(f"글 {len(items)}편을 읽습니다.", flush=True)
                for n, it in enumerate(items, 1):
                    if not it["log_no"]:
                        continue
                    page.goto(POST_URL.format(blog=args.blog, log=it["log_no"]), wait_until="domcontentloaded")
                    bot.wait(2)
                    scroll_all(page, bot)
                    try:
                        it.update(page.evaluate(POST_JS))
                    except Exception as e:
                        it["error"] = str(e)
                    try:
                        page.screenshot(path=str(OUT / f"{it['log_no']}.png"), full_page=True)
                    except Exception:
                        pass
                    print(f"  {n}. {it['title']} — 글자 {len(it.get('text', ''))}자, 사진 {it.get('images', 0)}장", flush=True)
            finally:
                ctx.close()
    except BotError as e:
        print(f"❌ {e}")
        sys.exit(1)

    (OUT / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# {args.blog} 블로그 글 모음 ({datetime.now():%Y-%m-%d %H:%M} 기준, {len(items)}편)\n"]
    for it in items:
        md.append(f"## {it['title']}\n- 날짜: {it['date']} · 카테고리: {it['category']} · 사진 {it.get('images', 0)}장"
                  f" · 공감 {it.get('likes') or '-'} · 댓글 {it.get('comments') or '-'}\n- 주소: {it['link']}\n"
                  f"- 태그: {tags_str(it.get('tags'))}\n\n{it.get('text', '')[:3000]}\n")
    (OUT / "posts.md").write_text("\n".join(md), encoding="utf-8")
    print(f"✅ 저장: {OUT / 'posts.md'}")


if __name__ == "__main__":
    main()
